"""Blender smoke test for traces, benchmarks, and durable model-quality state."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import (  # noqa: E402
    bridge_server,
    execution_traces,
    quality_benchmarks,
    quality_reviews,
)


def _call(name, arguments=None):
    payload = bridge_server._execute_tool({"name": name, "arguments": arguments or {}})
    assert payload["ok"] is True, payload
    return payload["result"]


def _scores(value):
    return [
        {
            "criterion": criterion,
            "score": value,
            "evidence": ["blender://visual-evidence/reference-front"],
            "finding": f"{criterion} compared against the front evidence",
            "repair_action": f"Repair {criterion}",
        }
        for criterion in ("silhouette_match", "proportion_match", "evidence_ready")
    ]


def main():
    root = tempfile.mkdtemp(prefix="blender-agent-quality-observability-")
    old_trace_root = os.environ.get(execution_traces.TRACE_ROOT_ENV)
    original_review_root = quality_reviews._root
    original_benchmark_root = quality_benchmarks._root
    registered = False
    try:
        os.environ[execution_traces.TRACE_ROOT_ENV] = os.path.join(root, "traces")
        claude_blender.register()
        registered = True
        quality_reviews._root = lambda create=False: os.path.join(root, "reviews")
        quality_benchmarks._root = lambda create=False: os.path.join(root, "benchmarks")

        trace_started = _call(
            "start_execution_trace",
            {"name": "Blender quality smoke", "prompt": "Inspect and score a reference model"},
        )
        trace_id = trace_started["trace"]["trace_id"]
        _call("list_scene_objects", {"max_objects": 10})
        trace = _call(
            "get_execution_trace",
            {"trace_id": trace_id, "include_events": True},
        )
        observed = [
            event["data"]["tool_name"]
            for event in trace["events"]
            if event["event"] == "tool_call"
        ]
        assert "list_scene_objects" in observed, observed

        brief = {
            "subject": "smoke product",
            "silhouette": ["wide rounded body"],
            "primary_masses": ["body"],
            "secondary_forms": [],
            "landmarks": [],
            "proportion_checks": ["width is twice height"],
            "surface_cues": [],
            "negative_constraints": [],
            "source_notes": ["smoke fixture"],
            "inspection_views": ["front", "side"],
        }
        review_started = _call(
            "start_model_quality_review",
            {
                "reference_brief": brief,
                "target_objects": [],
                "evidence_uris": ["blender://visual-evidence/reference-front"],
                "quality_floor": 4,
                "max_repair_passes": 1,
            },
        )
        review_id = review_started["review"]["review_id"]
        failed = _call(
            "submit_model_quality_evaluation",
            {"review_id": review_id, "scores": _scores(3), "blind": True},
        )
        assert failed["review"]["status"] == "repair_required", failed
        repaired = _call(
            "record_model_quality_repair",
            {
                "review_id": review_id,
                "repairs": [
                    {
                        "criterion": "silhouette_match",
                        "action": "Adjusted the primary body mass",
                    }
                ],
                "evidence_uris": ["blender://visual-evidence/reference-front-repaired"],
            },
        )
        assert repaired["next_packet"]["blind_packet"] is True, repaired
        passed = _call(
            "submit_model_quality_evaluation",
            {"review_id": review_id, "scores": _scores(4), "blind": True},
        )
        assert passed["review"]["status"] == "ready_for_user_review", passed
        _call(
            "finalize_execution_trace",
            {
                "trace_id": trace_id,
                "outcome": "completed",
                "token_usage": {"input_tokens": 20, "output_tokens": 10},
            },
        )

        benchmark = _call(
            "start_quality_benchmark_run",
            {
                "task_id": "fresh_gateway_execution",
                "client_name": "blender-smoke",
                "model_name": "fixture",
            },
        )
        run_id = benchmark["run"]["run_id"]
        _call("list_scene_objects", {"max_objects": 10})
        benchmark_finished = _call(
            "finish_quality_benchmark_run",
            {"run_id": run_id, "outcome": "completed"},
        )
        assert benchmark_finished["expectations_passed"] is True, benchmark_finished

        resource_uris = {item["uri"] for item in bridge_server._resources()}
        assert execution_traces.LATEST_TRACE_RESOURCE_URI in resource_uris, resource_uris
        assert quality_reviews.LATEST_REVIEW_RESOURCE_URI in resource_uris, resource_uris
        assert quality_benchmarks.LATEST_BENCHMARK_RESOURCE_URI in resource_uris, resource_uris
        for uri in (
            execution_traces.LATEST_TRACE_RESOURCE_URI,
            quality_reviews.LATEST_REVIEW_RESOURCE_URI,
            quality_benchmarks.LATEST_BENCHMARK_RESOURCE_URI,
        ):
            resource = bridge_server._read_resource(uri)
            assert resource and resource["mimeType"] == "application/json", (uri, resource)
        print("smoke_quality_observability: ok")
    finally:
        if registered:
            claude_blender.unregister()
        quality_reviews._root = original_review_root
        quality_benchmarks._root = original_benchmark_root
        if old_trace_root is None:
            os.environ.pop(execution_traces.TRACE_ROOT_ENV, None)
        else:
            os.environ[execution_traces.TRACE_ROOT_ENV] = old_trace_root
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
