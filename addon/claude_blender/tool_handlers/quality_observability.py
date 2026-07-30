"""Handlers for traces, benchmarks, and model-quality review state."""

from __future__ import annotations

import bpy

from .. import (
    execution_traces,
    preferences,
    quality_benchmarks,
    quality_reviews,
    reference_benchmark_scene,
    workflow_planning,
)
from .support import _bounded_float, _bounded_int, _name_list


def start_execution_trace(context, args):
    return execution_traces.start_trace(
        name=str(args.get("name") or "Blender execution trace"),
        prompt=str(args.get("prompt") or ""),
        metadata=args.get("metadata") if isinstance(args.get("metadata"), dict) else {},
        trace_id=str(args.get("trace_id") or ""),
        replace_active=bool(args.get("replace_active", False)),
    )


def get_execution_trace(context, args):
    trace_id = str(args.get("trace_id") or "")
    if not trace_id:
        trace_id = execution_traces.active_trace_id()
    return execution_traces.trace_status(
        trace_id,
        include_events=bool(args.get("include_events", False)),
    )


def list_execution_traces(context, args):
    traces = execution_traces.list_traces(
        _bounded_int(args.get("limit"), 20, minimum=1, maximum=100)
    )
    return {"ok": True, "message": f"Found {len(traces)} execution trace(s)", "traces": traces}


def finalize_execution_trace(context, args):
    return execution_traces.finalize_trace(
        str(args.get("trace_id") or ""),
        outcome=str(args.get("outcome") or "completed"),
        notes=str(args.get("notes") or ""),
        token_usage=args.get("token_usage") if isinstance(args.get("token_usage"), dict) else {},
    )


def prepare_execution_trace_replay(context, args):
    return execution_traces.prepare_replay(
        str(args.get("trace_id") or ""),
        include_script_code=bool(args.get("include_script_code", False)),
        include_read_only=bool(args.get("include_read_only", True)),
    )


def list_quality_benchmark_tasks(context, args):
    tasks = quality_benchmarks.list_tasks()
    return {
        "ok": True,
        "message": f"Found {len(tasks)} versioned benchmark task(s)",
        "suite_version": quality_benchmarks.BENCHMARK_SUITE_VERSION,
        "tasks": tasks,
    }


def start_quality_benchmark_run(context, args):
    return quality_benchmarks.start_run(
        task_id=str(args.get("task_id") or ""),
        client_name=str(args.get("client_name") or ""),
        model_name=str(args.get("model_name") or ""),
        blender_version=".".join(str(part) for part in bpy.app.version),
        reference_uri=str(args.get("reference_uri") or ""),
        reference_sha256=str(args.get("reference_sha256") or ""),
        notes=str(args.get("notes") or ""),
        replace_active_trace=bool(args.get("replace_active_trace", False)),
    )


def get_quality_benchmark_run(context, args):
    run_id = str(args.get("run_id") or "")
    if run_id:
        return quality_benchmarks.get_run(run_id)
    latest = quality_benchmarks.latest_run()
    return latest


def evaluate_reference_model_benchmark(context, args):
    prefs = preferences.get_preferences(context)
    landmark_targets = args.get("landmark_targets")
    return reference_benchmark_scene.evaluate_reference_model_benchmark(
        context,
        profile=str(args.get("profile") or "refined"),
        threshold_overrides=(
            args.get("threshold_overrides")
            if isinstance(args.get("threshold_overrides"), dict)
            else {}
        ),
        run_id=str(args.get("run_id") or ""),
        collection_name=str(args.get("collection_name") or ""),
        camera_name=str(args.get("camera_name") or ""),
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        outline_name=str(args.get("outline_name") or ""),
        reference_mask_source=str(
            args.get("reference_mask_source") or "auto"
        ),
        landmark_targets=(
            landmark_targets if isinstance(landmark_targets, list) else []
        ),
        max_axis=_bounded_int(
            args.get("max_axis"),
            512,
            minimum=64,
            maximum=1024,
        ),
        mask_threshold=_bounded_float(
            args.get("mask_threshold"),
            0.5,
            minimum=0.01,
            maximum=0.99,
        ),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
    )


def finish_quality_benchmark_run(context, args):
    return quality_benchmarks.finish_run(
        str(args.get("run_id") or ""),
        outcome=str(args.get("outcome") or "completed"),
        quality_review_id=str(args.get("quality_review_id") or ""),
        notes=str(args.get("notes") or ""),
        token_usage=args.get("token_usage") if isinstance(args.get("token_usage"), dict) else {},
    )


def start_model_quality_review(context, args):
    brief = workflow_planning._normalize_model_quality_brief(
        args.get("reference_brief") if isinstance(args.get("reference_brief"), dict) else {},
        str(args.get("reference_description") or ""),
    )
    missing = [
        field
        for field in workflow_planning._MODEL_QUALITY_REQUIRED_BRIEF_FIELDS
        if not brief.get(field)
    ]
    if missing:
        return {
            "ok": False,
            "code": "model_quality_reference_brief_incomplete",
            "message": f"Reference brief is missing required fields: {', '.join(missing)}",
            "missing_reference_brief_fields": missing,
        }
    return quality_reviews.create_review(
        reference_brief=brief,
        rubric=workflow_planning._model_quality_rubric(brief),
        target_objects=_name_list(args.get("target_objects")),
        evidence_uris=_name_list(args.get("evidence_uris")),
        quality_floor=_bounded_int(args.get("quality_floor"), 4, minimum=1, maximum=5),
        max_repair_passes=_bounded_int(args.get("max_repair_passes"), 3, minimum=0, maximum=10),
        trace_id=str(args.get("trace_id") or execution_traces.active_trace_id()),
        benchmark_run_id=str(args.get("benchmark_run_id") or ""),
    )


def get_model_quality_review_packet(context, args):
    return quality_reviews.review_packet(
        str(args.get("review_id") or ""),
        include_prior_scores=bool(args.get("include_prior_scores", False)),
    )


def submit_model_quality_evaluation(context, args):
    return quality_reviews.submit_evaluation(
        str(args.get("review_id") or ""),
        scores=args.get("scores") if isinstance(args.get("scores"), list) else [],
        evaluator=str(args.get("evaluator") or ""),
        evidence_uris=_name_list(args.get("evidence_uris")),
        notes=str(args.get("notes") or ""),
        blind=bool(args.get("blind", True)),
    )


def record_model_quality_repair(context, args):
    return quality_reviews.record_repair(
        str(args.get("review_id") or ""),
        repairs=args.get("repairs") if isinstance(args.get("repairs"), list) else [],
        evidence_uris=_name_list(args.get("evidence_uris")),
        notes=str(args.get("notes") or ""),
        trace_id=str(args.get("trace_id") or execution_traces.active_trace_id()),
    )


def get_model_quality_review(context, args):
    review_id = str(args.get("review_id") or "")
    if review_id:
        return quality_reviews.get_review(review_id)
    return quality_reviews.latest_review()


def register(handler_registry, specs):
    for spec in specs:
        try:
            handler = globals()[spec.handler_key]
        except KeyError as exc:
            raise KeyError(f"Missing handler {spec.handler_key} for {spec.name}") from exc
        handler_registry.register(spec.name, handler)
