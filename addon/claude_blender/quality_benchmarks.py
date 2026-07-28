"""Versioned benchmark tasks and durable run manifests."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import time
import uuid

from . import execution_traces, quality_reviews, user_paths


BENCHMARK_SCHEMA_VERSION = 1
BENCHMARK_SUITE_VERSION = "2026.07.1"
LATEST_BENCHMARK_RESOURCE_URI = "blender://quality-benchmarks/latest"

TASKS = {
    "reference_cartoon_animal": {
        "title": "Cartoon animal reference modeling",
        "category": "reference_modeling",
        "reference_required": True,
        "prompt": (
            "Build the supplied cartoon-animal reference without category templates. Decompose the actual image, "
            "use a cohesive trusted construction script, capture matched views, score every criterion, repair weak "
            "criteria, and leave the result pending."
        ),
        "expected_tools_any": ["draft_script", "start_trusted_script_job"],
        "required_tools": ["plan_model_quality_workflow", "submit_model_quality_evaluation"],
        "forbidden_tools": [],
    },
    "reference_human_character": {
        "title": "Human character reference modeling",
        "category": "reference_modeling",
        "reference_required": True,
        "prompt": (
            "Build the supplied human-character reference from image-derived masses, landmarks, ratios, and surface "
            "cues. Do not introduce animal anatomy or canned character geometry. Score matched evidence and repair "
            "before stopping."
        ),
        "expected_tools_any": ["draft_script", "start_trusted_script_job"],
        "required_tools": ["plan_model_quality_workflow", "submit_model_quality_evaluation"],
        "forbidden_tools": [],
    },
    "reference_hard_surface_product": {
        "title": "Hard-surface product reference modeling",
        "category": "reference_modeling",
        "reference_required": True,
        "prompt": (
            "Build the supplied hard-surface product reference using measurable proportions, silhouette, panel "
            "relationships, negative spaces, and finish cues. Use matched inspection views and repair all scores "
            "below the quality floor."
        ),
        "expected_tools_any": ["draft_script", "start_trusted_script_job"],
        "required_tools": ["plan_model_quality_workflow", "submit_model_quality_evaluation"],
        "forbidden_tools": [],
    },
    "animation_wave_negative_routing": {
        "title": "Animation wave negative routing",
        "category": "routing",
        "reference_required": False,
        "prompt": "Animate this character waving. Do not rebuild or quality-plan the character.",
        "expected_tools_any": ["plan_animation_workflow", "run_animation_workflow", "run_animation_task", "draft_script"],
        "required_tools": [],
        "forbidden_tools": ["plan_model_quality_workflow"],
    },
    "fresh_gateway_execution": {
        "title": "Fresh five-tool gateway execution",
        "category": "gateway",
        "reference_required": False,
        "prompt": (
            "In a fresh session with only the five gateway tools visible, inspect the scene, discover a non-top-level "
            "helper, fetch its schema, invoke it, and do not report planner-named helpers as unavailable."
        ),
        "expected_tools_any": ["list_scene_objects", "get_blend_file_diagnostics"],
        "required_tools": [],
        "forbidden_tools": [],
    },
}


def _now_iso():
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds")


def _root(create=False):
    path = user_paths.user_data_path("quality-benchmark-runs")
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def _safe_id(value, fallback="benchmark"):
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in str(value or ""))
    return safe.strip("._")[:100] or fallback


def _run_id():
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:10]}"


def _path(run_id):
    return os.path.join(_root(), f"{_safe_id(run_id, '')}.json")


def _write(run):
    path = _path(run["run_id"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = f"{path}.tmp"
    with open(temp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(run, handle, indent=2, sort_keys=True, ensure_ascii=True)
    os.replace(temp, path)
    return run


def _read(run_id):
    try:
        with open(_path(run_id), "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _reference_identity(reference_uri, supplied_sha256=""):
    reference = str(reference_uri or "").strip()
    supplied = str(supplied_sha256 or "").strip().lower()
    if supplied and (len(supplied) != 64 or any(char not in "0123456789abcdef" for char in supplied)):
        return {
            "ok": False,
            "code": "invalid_benchmark_reference_sha256",
            "message": "reference_sha256 must be a 64-character hexadecimal SHA-256 digest",
        }
    identity = {
        "uri": reference[:2000],
        "sha256": supplied,
        "size_bytes": 0,
        "fingerprint_source": "supplied" if supplied else "",
        "reproducible": bool(supplied),
    }
    local_path = os.path.abspath(os.path.expanduser(reference)) if reference else ""
    if local_path and os.path.isfile(local_path):
        digest = hashlib.sha256()
        size = 0
        with open(local_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
        computed = digest.hexdigest()
        if supplied and supplied != computed:
            return {
                "ok": False,
                "code": "benchmark_reference_digest_mismatch",
                "message": "The supplied reference_sha256 does not match the local reference file",
                "expected_sha256": supplied,
                "actual_sha256": computed,
            }
        identity.update(
            {
                "sha256": computed,
                "size_bytes": size,
                "fingerprint_source": "local_file",
                "reproducible": True,
            }
        )
    return {"ok": True, "identity": identity}


def list_tasks():
    return [
        {
            "task_id": task_id,
            "suite_version": BENCHMARK_SUITE_VERSION,
            **task,
        }
        for task_id, task in sorted(TASKS.items())
    ]


def start_run(
    *,
    task_id,
    client_name="",
    model_name="",
    blender_version="",
    reference_uri="",
    reference_sha256="",
    notes="",
    replace_active_trace=False,
):
    task = TASKS.get(str(task_id or ""))
    if not task:
        return {
            "ok": False,
            "code": "unknown_quality_benchmark_task",
            "message": f"Unknown benchmark task: {task_id}",
            "available_task_ids": sorted(TASKS),
        }
    if task.get("reference_required") and not str(reference_uri or "").strip():
        return {
            "ok": False,
            "code": "benchmark_reference_required",
            "message": f"Benchmark task {task_id} requires a reference URI or local path",
        }
    reference_result = _reference_identity(reference_uri, reference_sha256)
    if not reference_result.get("ok"):
        return reference_result
    reference_identity = reference_result["identity"]
    run_id = _safe_id(_run_id())
    trace_result = execution_traces.start_trace(
        name=f"Benchmark: {task['title']}",
        prompt=task["prompt"],
        metadata={
            "benchmark_run_id": run_id,
            "benchmark_task_id": task_id,
            "benchmark_suite_version": BENCHMARK_SUITE_VERSION,
            "client_name": str(client_name or "")[:160],
            "model_name": str(model_name or "")[:160],
            "blender_version": str(blender_version or "")[:80],
            "reference_uri": reference_identity["uri"],
            "reference_sha256": reference_identity["sha256"],
        },
        replace_active=bool(replace_active_trace),
    )
    if not trace_result.get("ok"):
        return trace_result
    trace = trace_result["trace"]
    now = _now_iso()
    run = {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "suite_version": BENCHMARK_SUITE_VERSION,
        "run_id": run_id,
        "task_id": task_id,
        "task": task,
        "status": "running",
        "outcome": "",
        "created_at": now,
        "completed_at": "",
        "client_name": str(client_name or "")[:160],
        "model_name": str(model_name or "")[:160],
        "blender_version": str(blender_version or "")[:80],
        "reference_uri": reference_identity["uri"],
        "reference_identity": reference_identity,
        "notes": str(notes or "")[:4000],
        "trace_id": trace["trace_id"],
        "quality_review_id": "",
        "expectation_result": {},
        "token_usage": {},
        "run_uri": f"blender://quality-benchmarks/{run_id}",
        "latest_run_uri": LATEST_BENCHMARK_RESOURCE_URI,
    }
    _write(run)
    execution_traces.record_event(
        "benchmark_started",
        trace_id=trace["trace_id"],
        layer="benchmark",
        data={"run_id": run_id, "task_id": task_id, "suite_version": BENCHMARK_SUITE_VERSION},
        allow_control_event=True,
    )
    return {
        "ok": True,
        "message": "Quality benchmark run started",
        "run": run,
        "trace": trace,
        "task_prompt": task["prompt"],
        "client_guidance": (
            "Execute the task normally through the five-tool gateway. For reference tasks, create and complete a "
            "model quality review with this run_id as benchmark_run_id, then finish the benchmark with its review_id."
        ),
    }


def _observed_tool_names(trace_id):
    trace = execution_traces.trace_status(trace_id, include_events=True)
    names = []
    for event in trace.get("events", []):
        if event.get("event") != "tool_call":
            continue
        data = event.get("data") or {}
        tool_name = str(data.get("tool_name") or "")
        if tool_name:
            names.append(tool_name)
        arguments = data.get("arguments") if isinstance(data.get("arguments"), dict) else {}
        nested_name = str(arguments.get("name") or "")
        if tool_name in {"invoke_blender_tool", "blender_tool_catalog"} and nested_name:
            names.append(nested_name)
    return names


def _evaluate_expectations(run):
    task = run["task"]
    observed = _observed_tool_names(run["trace_id"])
    observed_set = set(observed)
    required = list(task.get("required_tools") or [])
    expected_any = list(task.get("expected_tools_any") or [])
    forbidden = list(task.get("forbidden_tools") or [])
    missing_required = [name for name in required if name not in observed_set]
    forbidden_seen = [name for name in forbidden if name in observed_set]
    any_expected_seen = not expected_any or any(name in observed_set for name in expected_any)
    reference_task = task.get("category") == "reference_modeling"
    review_id = str(run.get("quality_review_id") or "")
    review_result = quality_reviews.get_review(review_id) if review_id else {}
    review_summary = review_result.get("summary") if isinstance(review_result, dict) else {}
    review_status = str((review_summary or {}).get("status") or "")
    review_terminal = review_status in {"ready_for_user_review", "blocked_quality_floor"}
    review_link_matches = bool(
        review_id
        and str((review_summary or {}).get("benchmark_run_id") or "") == str(run.get("run_id") or "")
    )
    reference_reproducible = bool((run.get("reference_identity") or {}).get("reproducible"))
    quality_state_valid = not reference_task or (review_terminal and review_link_matches)
    reproducibility_valid = not reference_task or reference_reproducible
    return {
        "ok": (
            not missing_required
            and not forbidden_seen
            and any_expected_seen
            and quality_state_valid
            and reproducibility_valid
        ),
        "observed_tool_names": observed,
        "missing_required_tools": missing_required,
        "forbidden_tools_seen": forbidden_seen,
        "expected_any_tools": expected_any,
        "expected_any_seen": any_expected_seen,
        "reference_reproducible": reference_reproducible,
        "quality_review_required": reference_task,
        "quality_review_id": review_id,
        "quality_review_status": review_status,
        "quality_review_terminal": review_terminal,
        "quality_review_link_matches_run": review_link_matches,
    }


def finish_run(
    run_id,
    *,
    outcome,
    quality_review_id="",
    notes="",
    token_usage=None,
):
    run = _read(run_id)
    if not run:
        return {
            "ok": False,
            "available": False,
            "run_id": str(run_id or ""),
            "message": "Quality benchmark run was not found",
        }
    if run.get("status") != "running":
        return {
            "ok": False,
            "code": "quality_benchmark_already_finished",
            "message": f"Benchmark run status is {run.get('status')}",
            "run": run,
        }
    run["quality_review_id"] = str(quality_review_id or "")[:120]
    expectation = _evaluate_expectations(run)
    run.update(
        {
            "status": "completed",
            "outcome": str(outcome or "completed")[:80],
            "completed_at": _now_iso(),
            "notes": "\n".join(filter(None, [str(run.get("notes") or ""), str(notes or "")]))[:8000],
            "expectation_result": expectation,
            "token_usage": dict(token_usage or {}) if isinstance(token_usage, dict) else {},
        }
    )
    execution_traces.record_event(
        "benchmark_finished",
        trace_id=run["trace_id"],
        layer="benchmark",
        data={
            "run_id": run["run_id"],
            "outcome": run["outcome"],
            "expectation_result": expectation,
            "quality_review_id": run["quality_review_id"],
        },
        allow_control_event=True,
    )
    trace_result = execution_traces.finalize_trace(
        run["trace_id"],
        outcome=run["outcome"],
        notes=run["notes"],
        token_usage=run["token_usage"],
    )
    _write(run)
    return {
        "ok": True,
        "message": (
            "Quality benchmark completed and routing expectations passed"
            if expectation["ok"]
            else "Quality benchmark completed with expectation failures"
        ),
        "run": run,
        "trace": trace_result.get("trace"),
        "expectations_passed": expectation["ok"],
    }


def get_run(run_id):
    run = _read(run_id)
    if not run:
        return {
            "ok": False,
            "available": False,
            "run_id": str(run_id or ""),
            "message": "Quality benchmark run was not found",
        }
    return {"ok": True, "available": True, "run": run}


def list_runs(limit=20):
    root = _root()
    if not os.path.isdir(root):
        return []
    rows = []
    for name in os.listdir(root):
        if not name.endswith(".json"):
            continue
        run = _read(name[:-5])
        if run:
            rows.append(
                {
                    "run_id": run["run_id"],
                    "task_id": run["task_id"],
                    "status": run["status"],
                    "outcome": run["outcome"],
                    "created_at": run["created_at"],
                    "completed_at": run["completed_at"],
                    "trace_id": run["trace_id"],
                    "expectations_passed": (run.get("expectation_result") or {}).get("ok"),
                    "run_uri": run["run_uri"],
                }
            )
    rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
    return rows[: max(1, min(100, int(limit or 20)))]


def latest_run():
    rows = list_runs(1)
    return get_run(rows[0]["run_id"]) if rows else {
        "ok": False,
        "available": False,
        "message": "No quality benchmark runs are available",
    }


def parse_benchmark_resource_uri(uri):
    parts = str(uri or "").split("/")
    if len(parts) == 4 and parts[:3] == ["blender:", "", "quality-benchmarks"]:
        return parts[3]
    return ""


def register():
    pass


def unregister():
    pass
