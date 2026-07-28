"""Asynchronous trusted Python jobs executed in background Blender processes."""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid

import bpy

from . import script_runner, user_paths


JOB_SCHEMA_VERSION = 1
LATEST_JOB_RESOURCE_URI = "blender://trusted-script-jobs/latest/metadata"
METADATA_FILENAME = "metadata.json"
CHILD_STATUS_FILENAME = "child-status.json"
SOURCE_BLEND_FILENAME = "source.blend"
RESULT_BLEND_FILENAME = "result.blend"
USER_SCRIPT_FILENAME = "trusted_user_script.py"
WRAPPER_SCRIPT_FILENAME = "trusted_job_wrapper.py"
LOG_FILENAME = "trusted-script.log"
CANCEL_FILENAME = "cancel.requested"
DEFAULT_POLL_SECONDS = 2

_PROCESSES = {}


def _safe_id(value, fallback="trusted-script-job"):
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in str(value or ""))
    return safe.strip("._")[:100] or fallback


def _job_id():
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:10]}"


def _root(create=False):
    path = user_paths.user_data_path("trusted-script-jobs")
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def _job_dir(job_id):
    return os.path.join(_root(), _safe_id(job_id, ""))


def _metadata_path(job_id):
    return os.path.join(_job_dir(job_id), METADATA_FILENAME)


def _write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = f"{path}.tmp"
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


def _child_env():
    env = dict(os.environ)
    for key in ("BLENDER_BRIDGE_TOKEN", "BLENDER_BRIDGE_URL"):
        env.pop(key, None)
    return env


def _pid_alive(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            try:
                exit_code = wintypes.DWORD()
                return bool(
                    ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                    and exit_code.value == 259
                )
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _log_tail(path, max_bytes=8192):
    if not os.path.isfile(path):
        return ""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            if size > max_bytes:
                handle.seek(-max_bytes, os.SEEK_END)
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _wrapper_text(config):
    config_text = json.dumps(config, indent=2, sort_keys=True)
    return f'''import json
import os
import time
import traceback

import bpy

CONFIG = {config_text}


def write_status(status, **extra):
    payload = {{
        "ok": status == "completed",
        "status": status,
        "updated_at": time.time(),
    }}
    payload.update(extra)
    path = CONFIG["child_status_path"]
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8", newline="\\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    os.replace(temp, path)


def agent_job_cancel_requested():
    return os.path.isfile(CONFIG["cancel_path"])


def agent_job_report_progress(progress, message="", details=None):
    value = max(0.0, min(1.0, float(progress)))
    write_status(
        "running",
        progress=value,
        message=str(message or "Trusted script running"),
        details=details if isinstance(details, dict) else {{}},
    )
    if agent_job_cancel_requested():
        raise RuntimeError("Trusted script job cancellation requested")


try:
    write_status("running", progress=0.0, message="Trusted script started")
    with open(CONFIG["user_script_path"], "r", encoding="utf-8") as handle:
        source = handle.read()
    namespace = {{
        "__name__": "__blender_agent_trusted_background_script__",
        "bpy": bpy,
        "context": bpy.context,
        "scene": bpy.context.scene,
        "agent_job_cancel_requested": agent_job_cancel_requested,
        "agent_job_report_progress": agent_job_report_progress,
    }}
    exec(compile(source, CONFIG["user_script_path"], "exec"), namespace, namespace)
    if agent_job_cancel_requested():
        raise RuntimeError("Trusted script job cancellation requested")
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    write_status("saving", progress=0.98, message="Saving trusted script result")
    bpy.ops.wm.save_as_mainfile(filepath=CONFIG["result_blend_path"], check_existing=False)
    write_status(
        "completed",
        progress=1.0,
        message="Trusted script completed",
        result_blend_path=CONFIG["result_blend_path"],
        result_size_bytes=(
            os.path.getsize(CONFIG["result_blend_path"])
            if os.path.isfile(CONFIG["result_blend_path"])
            else 0
        ),
    )
except Exception as exc:
    cancelled = agent_job_cancel_requested()
    write_status(
        "cancelled" if cancelled else "failed",
        progress=0.0,
        message=f"{{type(exc).__name__}}: {{exc}}",
        traceback=traceback.format_exc(),
    )
    if not cancelled:
        raise
'''


def _public_metadata(metadata):
    result = dict(metadata)
    result.pop("user_script_path", None)
    result["script_artifact_available"] = bool(metadata.get("user_script_path") and os.path.isfile(metadata["user_script_path"]))
    return result


def start_job(
    context,
    *,
    code,
    intent="",
    expected_changes="",
    risk_level="medium",
    target_objects=None,
    job_name="",
):
    script_runner.expire_external_script_trust_if_needed(context)
    if not script_runner.external_script_trust_active(context):
        return {
            "ok": False,
            "blocked": True,
            "code": "script_trust_required",
            "message": "Agent script trust is off",
        }
    code = str(code or "").strip()
    analysis = script_runner.analyze_trusted_script(code)
    if not analysis.get("ok"):
        return {
            "ok": False,
            "blocked": True,
            "code": "invalid_script_payload",
            "message": "Trusted script payload is invalid",
            "analysis": analysis,
        }
    job_id = _job_id()
    job_dir = _job_dir(job_id)
    os.makedirs(job_dir, exist_ok=False)
    source_blend_path = os.path.join(job_dir, SOURCE_BLEND_FILENAME)
    result_blend_path = os.path.join(job_dir, RESULT_BLEND_FILENAME)
    user_script_path = os.path.join(job_dir, USER_SCRIPT_FILENAME)
    wrapper_script_path = os.path.join(job_dir, WRAPPER_SCRIPT_FILENAME)
    log_path = os.path.join(job_dir, LOG_FILENAME)
    child_status_path = os.path.join(job_dir, CHILD_STATUS_FILENAME)
    cancel_path = os.path.join(job_dir, CANCEL_FILENAME)
    metadata = {
        "schema_version": JOB_SCHEMA_VERSION,
        "ok": True,
        "available": True,
        "job_id": job_id,
        "job_name": str(job_name or intent or "Trusted script job")[:160],
        "intent": str(intent or "")[:4000],
        "expected_changes": str(expected_changes or "")[:4000],
        "risk_level": str(risk_level or "medium")[:20],
        "target_objects": [str(item)[:240] for item in (target_objects or []) if str(item).strip()][:100],
        "status": "starting",
        "progress": 0.0,
        "created_at": time.time(),
        "started_at": 0.0,
        "completed_at": 0.0,
        "updated_at": time.time(),
        "pid": 0,
        "returncode": None,
        "job_dir": job_dir,
        "source_blend_path": source_blend_path,
        "result_blend_path": result_blend_path,
        "user_script_path": user_script_path,
        "wrapper_script_path": wrapper_script_path,
        "log_path": log_path,
        "child_status_path": child_status_path,
        "cancel_path": cancel_path,
        "metadata_path": _metadata_path(job_id),
        "metadata_uri": f"blender://trusted-script-jobs/{job_id}/metadata",
        "log_resource_uri": f"blender://trusted-script-jobs/{job_id}/log",
        "latest_metadata_uri": LATEST_JOB_RESOURCE_URI,
        "analysis": analysis,
        "timeout_safe": True,
        "poll_after_seconds": DEFAULT_POLL_SECONDS,
        "message": "Trusted script job prepared",
        "client_guidance": (
            "Poll get_trusted_script_job_status. The script runs against a copied .blend and cannot alter the live "
            "scene until apply_trusted_script_job_result is called with explicit confirmation."
        ),
    }
    _write_json(metadata["metadata_path"], metadata)
    try:
        bpy.ops.wm.save_as_mainfile(filepath=source_blend_path, check_existing=False, copy=True)
        with open(user_script_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(code)
        config = {
            "user_script_path": user_script_path,
            "result_blend_path": result_blend_path,
            "child_status_path": child_status_path,
            "cancel_path": cancel_path,
        }
        with open(wrapper_script_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(_wrapper_text(config))
        blender_binary = getattr(bpy.app, "binary_path", "") or "blender"
        command = [blender_binary, "--background", source_blend_path, "--python", wrapper_script_path]
        log_handle = open(log_path, "w", encoding="utf-8", newline="\n")
        process = subprocess.Popen(
            command,
            cwd=job_dir,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env=_child_env(),
        )
        log_handle.close()
        _PROCESSES[job_id] = process
        metadata.update(
            {
                "status": "running",
                "started_at": time.time(),
                "updated_at": time.time(),
                "pid": int(process.pid or 0),
                "message": "Trusted script started in a background Blender process",
            }
        )
        _write_json(metadata["metadata_path"], metadata)
    except Exception as exc:
        metadata.update(
            {
                "ok": False,
                "status": "failed",
                "completed_at": time.time(),
                "updated_at": time.time(),
                "message": f"Failed to start trusted script job: {type(exc).__name__}: {exc}",
            }
        )
        _write_json(metadata["metadata_path"], metadata)
        return {"ok": False, "message": metadata["message"], "trusted_script_job": _public_metadata(metadata)}
    return {
        "ok": True,
        "message": metadata["message"],
        "trusted_script_job": job_status(job_id),
    }


def job_status(job_id):
    metadata = _read_json(_metadata_path(job_id), None)
    if not metadata:
        return {
            "ok": False,
            "available": False,
            "job_id": str(job_id or ""),
            "message": "Trusted script job was not found",
        }
    job_id = metadata["job_id"]
    process = _PROCESSES.get(job_id)
    returncode = None
    if process is not None:
        returncode = process.poll()
        if returncode is not None:
            try:
                process.wait(timeout=0)
            except Exception:
                pass
            _PROCESSES.pop(job_id, None)
    child_status = _read_json(metadata.get("child_status_path") or "", {})
    metadata_status = str(metadata.get("status") or "unknown")
    status = metadata_status
    message = str(metadata.get("message") or "")
    progress = float(metadata.get("progress") or 0.0)
    if child_status:
        child_state = str(child_status.get("status") or status)
        if not (
            metadata_status in {"cancel_requested", "cancelled"}
            and child_state in {"starting", "running", "saving"}
        ):
            status = child_state
            message = str(child_status.get("message") or message)
            progress = float(child_status.get("progress") or progress)
        metadata["child_status"] = child_status
    if process is not None and returncode is None:
        status = "running"
    elif returncode == 0 and status not in {"completed", "failed", "cancelled"}:
        status = "completed" if os.path.isfile(metadata.get("result_blend_path") or "") else "failed"
        message = "Trusted script completed" if status == "completed" else "Trusted script exited without a result blend"
    elif returncode not in {None, 0} and status != "cancelled":
        status = "failed"
        message = message or f"Trusted script process exited with code {returncode}"
    elif process is None and status in {"running", "cancel_requested"}:
        if _pid_alive(metadata.get("pid")):
            message = (
                "Trusted script cancellation requested; waiting for the background process to stop"
                if status == "cancel_requested"
                else (message or "Trusted script process is still running")
            )
        else:
            cancelled = os.path.isfile(metadata.get("cancel_path") or "")
            status = "cancelled" if cancelled else "failed"
            message = (
                "Trusted script job cancelled"
                if cancelled
                else "Trusted script process stopped without recording a final result"
            )
    if status in {"completed", "failed", "cancelled"} and not metadata.get("completed_at"):
        metadata["completed_at"] = time.time()
    result_path = metadata.get("result_blend_path") or ""
    result_available = bool(result_path and os.path.isfile(result_path))
    metadata.update(
        {
            "ok": status not in {"failed"},
            "status": status,
            "message": message,
            "progress": 1.0 if status == "completed" else max(0.0, min(1.0, progress)),
            "returncode": returncode if returncode is not None else metadata.get("returncode"),
            "updated_at": time.time(),
            "poll_after_seconds": (
                DEFAULT_POLL_SECONDS
                if status in {"starting", "running", "saving", "cancel_requested", "unknown"}
                else 0
            ),
            "result_available": result_available,
            "result_size_bytes": os.path.getsize(result_path) if result_available else 0,
            "log_tail": _log_tail(metadata.get("log_path") or "", max_bytes=4096),
        }
    )
    _write_json(metadata["metadata_path"], metadata)
    return _public_metadata(metadata)


def cancel_job(job_id):
    metadata = _read_json(_metadata_path(job_id), None)
    if not metadata:
        return {
            "ok": False,
            "available": False,
            "job_id": str(job_id or ""),
            "message": "Trusted script job was not found",
        }
    status = job_status(job_id)
    if status.get("status") in {"completed", "failed", "cancelled"}:
        return {
            "ok": False,
            "code": "trusted_script_job_not_running",
            "message": f"Trusted script job is already {status.get('status')}",
            "trusted_script_job": status,
        }
    with open(metadata["cancel_path"], "w", encoding="utf-8") as handle:
        handle.write("cancel requested\n")
    process = _PROCESSES.get(job_id)
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        _PROCESSES.pop(job_id, None)
    process_still_alive = process is None and _pid_alive(metadata.get("pid"))
    final_status = "cancel_requested" if process_still_alive else "cancelled"
    metadata.update(
        {
            "ok": True,
            "status": final_status,
            "message": (
                "Trusted script cancellation requested; poll until the process stops"
                if process_still_alive
                else "Trusted script job cancelled"
            ),
            "completed_at": 0.0 if process_still_alive else time.time(),
            "updated_at": time.time(),
            "returncode": process.returncode if process is not None else metadata.get("returncode"),
        }
    )
    _write_json(metadata["metadata_path"], metadata)
    return {
        "ok": True,
        "message": metadata["message"],
        "trusted_script_job": job_status(job_id),
    }


def apply_job_result(
    context,
    job_id,
    *,
    confirm_replace_current_scene=False,
    checkpoint_enabled=True,
    checkpoint_dir=None,
):
    if not confirm_replace_current_scene:
        return {
            "ok": False,
            "blocked": True,
            "code": "trusted_script_job_apply_confirmation_required",
            "message": "Set confirm_replace_current_scene=true only after the user explicitly approves replacing the live file",
        }
    status = job_status(job_id)
    if not status.get("available", True):
        return status
    if status.get("status") != "completed" or not status.get("result_available"):
        return {
            "ok": False,
            "code": "trusted_script_job_result_not_ready",
            "message": f"Trusted script job result is not ready; status is {status.get('status')}",
            "trusted_script_job": status,
        }
    checkpoint = {"ok": True, "message": "Checkpoint disabled", "path": ""}
    if checkpoint_enabled:
        checkpoint = script_runner.create_checkpoint(context, checkpoint_dir=checkpoint_dir)
        if not checkpoint.get("ok"):
            return {
                "ok": False,
                "blocked": True,
                "code": "checkpoint_failed",
                "message": checkpoint.get("message", "Checkpoint failed"),
                "checkpoint": checkpoint,
            }
    trust = script_runner.external_script_trust_snapshot(context)
    result_path = status["result_blend_path"]
    try:
        bpy.ops.wm.open_mainfile(filepath=result_path)
    except Exception as exc:
        script_runner.preserve_external_script_trust_after_file_load(
            trust,
            audit_action="preserve_after_failed_trusted_script_job_apply",
        )
        return {
            "ok": False,
            "message": f"Failed to apply trusted script job result: {type(exc).__name__}: {exc}",
            "checkpoint": checkpoint,
            "trusted_script_job": status,
        }
    trust_result = script_runner.preserve_external_script_trust_after_file_load(
        trust,
        audit_action="preserve_on_trusted_script_job_apply",
    )
    return {
        "ok": True,
        "message": "Trusted script job result opened in Blender",
        "checkpoint": checkpoint,
        "trusted_script_job": job_status(job_id),
        "external_script_trust": trust_result["trust"],
        "trust_preserved": trust_result["preserved"],
        "current_filepath": bpy.data.filepath,
    }


def list_jobs(limit=20):
    root = _root()
    if not os.path.isdir(root):
        return []
    rows = []
    for name in os.listdir(root):
        metadata = _read_json(os.path.join(root, name, METADATA_FILENAME), None)
        if metadata:
            rows.append(job_status(metadata["job_id"]))
    rows.sort(key=lambda row: float(row.get("created_at") or 0.0), reverse=True)
    return rows[: max(1, min(100, int(limit or 20)))]


def latest_job():
    rows = list_jobs(1)
    return rows[0] if rows else {
        "ok": False,
        "available": False,
        "message": "No trusted script jobs are available",
    }


def parse_job_resource_uri(uri):
    parts = str(uri or "").split("/")
    if len(parts) == 5 and parts[:3] == ["blender:", "", "trusted-script-jobs"]:
        return parts[3], parts[4]
    return "", ""


def metadata_resource(job_id):
    status = job_status(job_id)
    return {
        "mimeType": "application/json",
        "text": json.dumps(status, indent=2, sort_keys=True, default=str),
    } if status.get("available", True) else None


def log_resource(job_id):
    metadata = _read_json(_metadata_path(job_id), None)
    if not metadata or not os.path.isfile(metadata.get("log_path") or ""):
        return None
    with open(metadata["log_path"], "r", encoding="utf-8", errors="replace") as handle:
        return {"mimeType": "text/plain", "text": handle.read()}


def register():
    pass


def unregister():
    for process in list(_PROCESSES.values()):
        if process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass
    _PROCESSES.clear()
