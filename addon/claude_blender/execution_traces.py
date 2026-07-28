"""Durable, replay-oriented execution traces shared by Blender and MCP."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import time
import uuid

from . import user_paths


TRACE_SCHEMA_VERSION = 1
TRACE_ROOT_ENV = "BLENDER_AGENT_BRIDGE_TRACE_DIR"
LATEST_TRACE_RESOURCE_URI = "blender://execution-traces/latest/manifest"
MAX_TEXT_CHARS = 4000
MAX_RESULT_DEPTH = 5
MAX_RESULT_ITEMS = 80

_TRACE_CONTROL_TOOLS = {
    "finalize_execution_trace",
    "get_execution_trace",
    "list_execution_traces",
    "prepare_execution_trace_replay",
    "start_execution_trace",
}
_CREDENTIAL_KEY_PARTS = (
    "access_key",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
)
_SCRIPT_KEY_PARTS = ("code", "python", "script_source")
_RESULT_DROP_KEYS = {
    "audio",
    "base64",
    "blob",
    "code",
    "image",
    "log_tail",
    "python",
    "script_source",
}
_TOKEN_METRIC_KEYS = {
    "cached_tokens",
    "completion_tokens",
    "estimated_argument_tokens",
    "estimated_result_tokens",
    "input_tokens",
    "output_tokens",
    "prompt_tokens",
    "reasoning_tokens",
    "token_usage",
    "total_tokens",
}


def _now_iso():
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds")


def _trace_root(create=False):
    configured = str(os.environ.get(TRACE_ROOT_ENV) or "").strip()
    root = os.path.abspath(os.path.expanduser(configured)) if configured else user_paths.legacy_user_data_path(
        "execution-traces"
    )
    if create:
        os.makedirs(root, exist_ok=True)
    return root


def _safe_id(value, fallback="trace"):
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in str(value or ""))
    return safe.strip("._")[:100] or fallback


def _trace_id():
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:10]}"


def _trace_dir(trace_id):
    return os.path.join(_trace_root(), _safe_id(trace_id, ""))


def _manifest_path(trace_id):
    return os.path.join(_trace_dir(trace_id), "manifest.json")


def _events_path(trace_id):
    return os.path.join(_trace_dir(trace_id), "events.jsonl")


def _active_path():
    return os.path.join(_trace_root(), "_active.json")


def _write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = f"{path}.{os.getpid()}.tmp"
    with open(temp_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=True)
    os.replace(temp_path, path)
    return path


def _read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _sha256_text(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _token_estimate(value):
    try:
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)
    except Exception:
        encoded = str(value)
    return max(0, (len(encoded) + 3) // 4)


def _key_matches(key, parts):
    lowered = str(key or "").lower()
    return any(part in lowered for part in parts)


def _credential_key_matches(key, value=None):
    lowered = str(key or "").lower()
    if lowered in _TOKEN_METRIC_KEYS:
        return False
    if lowered.endswith("_tokens") and isinstance(value, (int, float)):
        return False
    return _key_matches(lowered, _CREDENTIAL_KEY_PARTS)


def _result_key_should_drop(key):
    lowered = str(key or "").lower()
    return (
        lowered in _RESULT_DROP_KEYS
        or lowered.endswith("_base64")
        or lowered.endswith("_blob")
    )


def _artifact_reference(trace_id, call_id, key, value):
    artifact_dir = os.path.join(_trace_dir(trace_id), "artifacts")
    os.makedirs(artifact_dir, exist_ok=True)
    extension = ".py" if _key_matches(key, _SCRIPT_KEY_PARTS) else ".txt"
    filename = f"{_safe_id(call_id)}-{_safe_id(key, 'payload')}{extension}"
    path = os.path.join(artifact_dir, filename)
    text = str(value)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return {
        "$artifact": os.path.relpath(path, _trace_dir(trace_id)).replace("\\", "/"),
        "sha256": _sha256_text(text),
        "chars": len(text),
        "sensitive_local_artifact": True,
    }


def _trace_arguments(value, trace_id, call_id, key="", depth=0):
    if depth > MAX_RESULT_DEPTH:
        return "[truncated]"
    if key and _credential_key_matches(key, value):
        return "[redacted]"
    if isinstance(value, dict):
        return {
            str(child_key): _trace_arguments(
                child,
                trace_id,
                call_id,
                str(child_key),
                depth + 1,
            )
            for child_key, child in list(value.items())[:MAX_RESULT_ITEMS]
        }
    if isinstance(value, (list, tuple)):
        return [
            _trace_arguments(child, trace_id, call_id, key, depth + 1)
            for child in list(value)[:MAX_RESULT_ITEMS]
        ]
    if isinstance(value, str):
        if key and _key_matches(key, _SCRIPT_KEY_PARTS):
            return _artifact_reference(trace_id, call_id, key, value)
        if len(value) > MAX_TEXT_CHARS:
            return {
                "$truncated_text": value[:MAX_TEXT_CHARS],
                "sha256": _sha256_text(value),
                "chars": len(value),
            }
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return repr(value)[:MAX_TEXT_CHARS]


def _result_summary(value, depth=0, key=""):
    if isinstance(value, dict) and "$artifact" in value:
        return {
            "$artifact": str(value.get("$artifact") or ""),
            "sha256": str(value.get("sha256") or ""),
            "chars": int(value.get("chars") or 0),
            "sensitive_local_artifact": bool(value.get("sensitive_local_artifact", True)),
        }
    if depth > MAX_RESULT_DEPTH:
        return "[truncated]"
    if key and (_result_key_should_drop(key) or _credential_key_matches(key, value)):
        return "[redacted]"
    if isinstance(value, dict):
        return {
            str(child_key): _result_summary(child, depth + 1, str(child_key))
            for child_key, child in list(value.items())[:MAX_RESULT_ITEMS]
        }
    if isinstance(value, (list, tuple)):
        return [_result_summary(child, depth + 1, key) for child in list(value)[:MAX_RESULT_ITEMS]]
    if isinstance(value, str):
        return value if len(value) <= MAX_TEXT_CHARS else f"{value[:MAX_TEXT_CHARS]}... [truncated]"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return repr(value)[:MAX_TEXT_CHARS]


def _active_trace_id():
    payload = _read_json(_active_path(), {})
    trace_id = str((payload or {}).get("trace_id") or "")
    if trace_id and os.path.isfile(_manifest_path(trace_id)):
        return trace_id
    return ""


def active_trace_id():
    """Return the current cross-process trace id, if any."""
    return _active_trace_id()


def start_trace(*, name, prompt="", metadata=None, trace_id="", replace_active=False):
    _trace_root(create=True)
    active_id = _active_trace_id()
    if active_id and not replace_active:
        return {
            "ok": False,
            "code": "execution_trace_already_active",
            "message": f"Execution trace {active_id} is already active",
            "active_trace_id": active_id,
        }
    if active_id and replace_active:
        finalize_trace(active_id, outcome="superseded", notes="Replaced by a new execution trace")
    trace_id = _safe_id(trace_id or _trace_id())
    directory = _trace_dir(trace_id)
    if os.path.exists(directory):
        return {
            "ok": False,
            "code": "execution_trace_exists",
            "message": f"Execution trace already exists: {trace_id}",
        }
    os.makedirs(os.path.join(directory, "artifacts"), exist_ok=False)
    manifest = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "trace_id": trace_id,
        "name": str(name or "Execution trace")[:160],
        "prompt": "",
        "prompt_stored": False,
        "prompt_chars": len(str(prompt or "")),
        "prompt_sha256": _sha256_text(prompt or ""),
        "metadata": _result_summary(metadata if isinstance(metadata, dict) else {}),
        "status": "active",
        "outcome": "",
        "created_at": _now_iso(),
        "completed_at": "",
        "event_count": 0,
        "estimated_trace_tokens": _token_estimate(prompt),
        "provided_token_usage": {},
        "events_path": _events_path(trace_id),
        "manifest_path": _manifest_path(trace_id),
        "manifest_uri": f"blender://execution-traces/{trace_id}/manifest",
        "latest_manifest_uri": LATEST_TRACE_RESOURCE_URI,
        "contains_sensitive_local_artifacts": True,
        "artifact_notice": (
            "Generated scripts are stored locally as replay artifacts. Credential-like arguments are redacted."
        ),
    }
    _write_json(_manifest_path(trace_id), manifest)
    _write_json(_active_path(), {"trace_id": trace_id, "activated_at": _now_iso()})
    record_event(
        "trace_started",
        trace_id=trace_id,
        layer="trace",
        data={"name": manifest["name"], "metadata": manifest["metadata"]},
        allow_control_event=True,
    )
    return {"ok": True, "message": "Execution trace started", "trace": trace_status(trace_id)}


def record_event(event_type, *, trace_id="", layer="", data=None, allow_control_event=False):
    trace_id = str(trace_id or _active_trace_id())
    if not trace_id:
        return None
    if not os.path.isfile(_manifest_path(trace_id)):
        return None
    payload = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "event_id": uuid.uuid4().hex,
        "timestamp": _now_iso(),
        "timestamp_ns": time.time_ns(),
        "process_id": os.getpid(),
        "trace_id": trace_id,
        "event": str(event_type),
        "layer": str(layer or ""),
        "data": _result_summary(data if isinstance(data, dict) else {}),
    }
    if not allow_control_event and payload["data"].get("tool_name") in _TRACE_CONTROL_TOOLS:
        return None
    with open(_events_path(trace_id), "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n")
    return payload


def record_tool_call(
    *,
    layer,
    tool_name,
    arguments=None,
    result=None,
    duration_ms=None,
    contract=None,
):
    trace_id = _active_trace_id()
    if not trace_id or str(tool_name or "") in _TRACE_CONTROL_TOOLS:
        return None
    call_id = uuid.uuid4().hex
    traced_arguments = _trace_arguments(arguments if isinstance(arguments, dict) else {}, trace_id, call_id)
    summary = _result_summary(result if isinstance(result, dict) else {})
    data = {
        "call_id": call_id,
        "tool_name": str(tool_name or ""),
        "arguments": traced_arguments,
        "result": summary,
        "ok": bool(summary.get("ok", not summary.get("isError", False))) if isinstance(summary, dict) else False,
        "duration_ms": round(float(duration_ms), 3) if duration_ms is not None else None,
        "contract": _result_summary(contract if isinstance(contract, dict) else {}),
        "estimated_argument_tokens": _token_estimate(traced_arguments),
        "estimated_result_tokens": _token_estimate(summary),
    }
    return record_event("tool_call", trace_id=trace_id, layer=layer, data=data)


def _events(trace_id):
    path = _events_path(trace_id)
    events = []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return []
    return sorted(events, key=lambda event: (int(event.get("timestamp_ns") or 0), str(event.get("event_id") or "")))


def trace_status(trace_id="", *, include_events=False):
    trace_id = str(trace_id or _active_trace_id())
    manifest = _read_json(_manifest_path(trace_id), None) if trace_id else None
    if not manifest:
        return {
            "ok": False,
            "available": False,
            "trace_id": trace_id,
            "message": "Execution trace was not found",
        }
    events = _events(trace_id)
    token_estimate = int(manifest.get("estimated_trace_tokens") or 0)
    for event in events:
        data = event.get("data") or {}
        token_estimate += int(data.get("estimated_argument_tokens") or 0)
        token_estimate += int(data.get("estimated_result_tokens") or 0)
    result = dict(manifest)
    result.update(
        {
            "ok": True,
            "available": True,
            "active": _active_trace_id() == trace_id,
            "event_count": len(events),
            "estimated_trace_tokens": token_estimate,
        }
    )
    if include_events:
        result["events"] = events
    return result


def list_traces(limit=20):
    root = _trace_root()
    if not os.path.isdir(root):
        return []
    rows = []
    for name in os.listdir(root):
        manifest = _read_json(os.path.join(root, name, "manifest.json"), None)
        if manifest:
            rows.append(
                {
                    "trace_id": manifest.get("trace_id", name),
                    "name": manifest.get("name", ""),
                    "status": manifest.get("status", ""),
                    "outcome": manifest.get("outcome", ""),
                    "created_at": manifest.get("created_at", ""),
                    "completed_at": manifest.get("completed_at", ""),
                    "manifest_uri": manifest.get("manifest_uri", ""),
                }
            )
    rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
    return rows[: max(1, min(100, int(limit or 20)))]


def finalize_trace(trace_id="", *, outcome="completed", notes="", token_usage=None):
    trace_id = str(trace_id or _active_trace_id())
    manifest = _read_json(_manifest_path(trace_id), None) if trace_id else None
    if not manifest:
        return {
            "ok": False,
            "available": False,
            "trace_id": trace_id,
            "message": "Execution trace was not found",
        }
    record_event(
        "trace_finalized",
        trace_id=trace_id,
        layer="trace",
        data={"outcome": str(outcome or "completed"), "notes": str(notes or "")[:4000]},
        allow_control_event=True,
    )
    status = trace_status(trace_id)
    manifest.update(
        {
            "status": "completed",
            "outcome": str(outcome or "completed")[:80],
            "notes": str(notes or "")[:8000],
            "completed_at": _now_iso(),
            "event_count": status.get("event_count", 0),
            "estimated_trace_tokens": status.get("estimated_trace_tokens", 0),
            "provided_token_usage": _result_summary(token_usage if isinstance(token_usage, dict) else {}),
        }
    )
    _write_json(_manifest_path(trace_id), manifest)
    active = _read_json(_active_path(), {})
    if str((active or {}).get("trace_id") or "") == trace_id:
        try:
            os.remove(_active_path())
        except FileNotFoundError:
            pass
    return {"ok": True, "message": "Execution trace finalized", "trace": trace_status(trace_id)}


def _resolve_artifacts(value, trace_id, blockers):
    if isinstance(value, dict):
        artifact = str(value.get("$artifact") or "")
        if artifact:
            path = os.path.abspath(os.path.join(_trace_dir(trace_id), artifact))
            root = os.path.abspath(_trace_dir(trace_id))
            if os.path.commonpath([root, path]) != root or not os.path.isfile(path):
                blockers.append(f"Missing replay artifact: {artifact}")
                return f"<missing_artifact:{artifact}>"
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
            if _sha256_text(text) != str(value.get("sha256") or ""):
                blockers.append(f"Replay artifact digest mismatch: {artifact}")
            return text
        if "$truncated_text" in value:
            blockers.append("A long argument was truncated and cannot be replayed automatically")
            return str(value.get("$truncated_text") or "")
        return {key: _resolve_artifacts(child, trace_id, blockers) for key, child in value.items()}
    if isinstance(value, list):
        return [_resolve_artifacts(child, trace_id, blockers) for child in value]
    if value == "[redacted]":
        blockers.append("A credential-like argument was redacted and must be supplied again")
    return value


def prepare_replay(trace_id, *, include_script_code=False, include_read_only=True):
    trace = trace_status(trace_id, include_events=True)
    if not trace.get("ok"):
        return trace
    calls = []
    blockers = []
    seen_call_ids = set()
    for event in trace.get("events", []):
        if event.get("event") != "tool_call" or event.get("layer") != "bridge":
            continue
        data = event.get("data") or {}
        tool_name = str(data.get("tool_name") or "")
        call_id = str(data.get("call_id") or "")
        if not tool_name or call_id in seen_call_ids or tool_name in _TRACE_CONTROL_TOOLS:
            continue
        seen_call_ids.add(call_id)
        contract = data.get("contract") if isinstance(data.get("contract"), dict) else {}
        mutates = bool(contract.get("mutates_scene"))
        if not include_read_only and not mutates:
            continue
        call_blockers = []
        arguments = _resolve_artifacts(data.get("arguments") or {}, trace_id, call_blockers)
        if not include_script_code and tool_name in {"draft_script", "draft_privileged_script", "start_trusted_script_job"}:
            if isinstance(arguments, dict) and "code" in arguments:
                arguments["code"] = "<stored_script_artifact; request include_script_code to resolve>"
                call_blockers.append("Script code is withheld from the default replay packet")
        blockers.extend(call_blockers)
        calls.append(
            {
                "sequence": len(calls) + 1,
                "tool_name": tool_name,
                "mutates_scene": mutates,
                "schema_lookup": {
                    "name": "get_blender_tool_schema",
                    "arguments": {"name": tool_name},
                },
                "gateway_call": {
                    "name": "invoke_blender_tool",
                    "arguments": {"name": tool_name, "arguments": arguments},
                },
                "blockers": call_blockers,
            }
        )
    return {
        "ok": True,
        "message": "Prepared execution-trace replay plan",
        "trace_id": trace_id,
        "calls": calls,
        "call_count": len(calls),
        "blockers": sorted(set(blockers)),
        "ready": not blockers,
        "dry_run_only": True,
        "client_guidance": (
            "Review the plan, resolve every blocker, fetch current schemas, then invoke calls in order. "
            "Mutating replay is never automatic."
        ),
    }


def latest_trace_manifest():
    traces = list_traces(1)
    return trace_status(traces[0]["trace_id"]) if traces else {
        "ok": False,
        "available": False,
        "message": "No execution traces are available",
    }


def parse_trace_resource_uri(uri):
    parts = str(uri or "").split("/")
    if len(parts) == 5 and parts[:3] == ["blender:", "", "execution-traces"] and parts[4] == "manifest":
        return parts[3]
    return ""


def register():
    pass


def unregister():
    pass
