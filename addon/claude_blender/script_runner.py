"""Binary session-trusted generated Python execution."""

from __future__ import annotations

import ast
import contextlib
import datetime as _dt
import io
import os
import re
import textwrap
import time
import traceback

import bpy
from bpy.app.handlers import persistent

from . import audit_log, script_analysis, script_execution, transcript, user_paths

TRUSTED_SCRIPT_NAME = "Agent Bridge Trusted Script"
TRUSTED_SCRIPT_METADATA_NAME = "Agent Bridge Trusted Script Metadata"
SCRIPT_LOG_NAME = "Agent Bridge Script Log"

MAX_SCRIPT_CHARS = 500_000
MAX_STATE_TEXT_CHARS = 1800
EXTERNAL_TRUST_TTL_SECONDS = 15 * 60
NO_EXTERNAL_TRUST_STATUS = "No external script trust"
EXTERNAL_TRUST_EXPIRED_STATUS = "External script trust expired"
EXTERNAL_TRUST_SESSION_STATUS = "External script trust active for this Blender session"
CHECKPOINT_FILENAME_RE = re.compile(
    r"-(?:agent|claude)-\d{8}-\d{6}(?:-\d{6})?(?:-\d+)?\.blend$",
    re.IGNORECASE,
)

_runtime_external_trust_expires_at = 0.0
_runtime_external_trust_session = False


def _default_checkpoint_dir():
    return user_paths.user_data_path("checkpoints")


def _safe_filename(value):
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "untitled").strip("._")
    return value[:80] or "untitled"


def _text_block(name):
    text = bpy.data.texts.get(name)
    if text is None:
        text = bpy.data.texts.new(name)
    return text


def _write_text_block(name, body):
    text = _text_block(name)
    text.clear()
    text.write(body)
    return text


def _short_text(value, max_chars=MAX_STATE_TEXT_CHARS):
    value = str(value or "").strip()
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}... [truncated]"


def analyze_trusted_script(source):
    """Validate a trusted script without pretending static analysis is a sandbox."""
    source = str(source or "")
    if len(source) > MAX_SCRIPT_CHARS:
        return {
            "ok": False,
            "blocked": True,
            "issues": [f"Script is too large: {len(source)} chars > {MAX_SCRIPT_CHARS}"],
            "warnings": [],
            "risk_level": "blocked",
            "risk_reasons": ["script_too_large"],
            "checkpoint_recommended": True,
            "explicit_approval_required": False,
            "explicit_approval_reasons": [],
            "privileged_capabilities": [],
            "trust_window_allowed": False,
            "trusted_manual_mode": True,
            "authorization_model": script_execution.AUTHORIZATION_MODEL,
        }
    try:
        ast.parse(source)
    except SyntaxError as exc:
        return {
            "ok": False,
            "blocked": True,
            "issues": [f"Syntax error: {exc}"],
            "warnings": [],
            "risk_level": "blocked",
            "risk_reasons": ["syntax_error"],
            "checkpoint_recommended": True,
            "explicit_approval_required": False,
            "explicit_approval_reasons": [],
            "privileged_capabilities": [],
            "trust_window_allowed": False,
            "trusted_manual_mode": True,
            "authorization_model": script_execution.AUTHORIZATION_MODEL,
        }
    try:
        advisory = script_analysis.analyze_script(source)
    except Exception as exc:
        advisory = {
            "ok": True,
            "blocked": False,
            "issues": [],
            "warnings": [f"Static advisory analysis unavailable: {type(exc).__name__}: {exc}"],
            "risk_level": "high",
            "risk_reasons": ["static_advisory_unavailable"],
            "checkpoint_recommended": True,
            "explicit_approval_required": False,
            "explicit_approval_reasons": [],
            "privileged_capabilities": [],
            "trust_window_allowed": True,
        }

    persistent_operation_findings = list(advisory.get("explicit_approval_reasons", []))
    findings = list(advisory.get("issues", [])) + persistent_operation_findings
    warnings = list(advisory.get("warnings", []))
    warnings.extend(f"Advisory under session trust: {finding}" for finding in findings)
    result = dict(advisory)
    result.update(
        {
            "ok": True,
            "blocked": False,
            "issues": [],
            "warnings": warnings,
            "advisory_findings": findings,
            "risk_level": "high" if findings or advisory.get("explicit_approval_required") else advisory.get("risk_level", "low"),
            "checkpoint_recommended": bool(
                findings
                or advisory.get("explicit_approval_required")
                or advisory.get("checkpoint_recommended")
            ),
            "explicit_approval_required": False,
            "explicit_approval_reasons": [],
            "trust_window_allowed": True,
            "trusted_manual_mode": True,
            "authorization_model": script_execution.AUTHORIZATION_MODEL,
        }
    )
    return result


def _scene_state(context=None):
    scene = getattr(context, "scene", None) if context else None
    if scene is None:
        scene = getattr(bpy.context, "scene", None)
    return getattr(scene, "claude_blender", None) if scene else None


def _external_trust_expires_at(state):
    return float(_runtime_external_trust_expires_at or 0.0)


def _trust_duration_label(seconds):
    seconds = max(0, int(seconds))
    if seconds >= 60:
        minutes, remaining_seconds = divmod(seconds, 60)
        return f"{minutes}m {remaining_seconds:02d}s"
    return f"{seconds}s"


def external_script_trust_snapshot(context=None, *, state=None):
    state = state or _scene_state(context)
    now = time.time()
    expires_at = _external_trust_expires_at(state)
    session_active = bool(state and _runtime_external_trust_session)
    stored_status = getattr(state, "external_script_trust_status", NO_EXTERNAL_TRUST_STATUS) if state else NO_EXTERNAL_TRUST_STATUS
    stored_expires_at = getattr(state, "external_script_trust_expires_at", "") if state else ""
    seconds_remaining = max(0, int(expires_at - now + 0.999)) if expires_at else 0
    stored_expired = stored_status == EXTERNAL_TRUST_EXPIRED_STATUS
    active = bool(session_active or (state and expires_at and seconds_remaining > 0))
    expired = bool(state and ((expires_at and not active) or stored_expired))
    stale_scene_state = bool(stored_expires_at and not expires_at and not session_active)
    if session_active:
        status = EXTERNAL_TRUST_SESSION_STATUS
    elif active:
        status = f"External script trust active: {_trust_duration_label(seconds_remaining)} remaining"
    elif expired:
        status = EXTERNAL_TRUST_EXPIRED_STATUS
    elif str(stored_status).startswith("External script trust active"):
        status = NO_EXTERNAL_TRUST_STATUS
    else:
        status = stored_status or NO_EXTERNAL_TRUST_STATUS
    return {
        "active": active,
        "expired": expired,
        "status": status,
        "expires_at": expires_at if expires_at else 0.0,
        "seconds_remaining": seconds_remaining,
        "can_run_without_token": active,
        "runtime_only": True,
        "session": session_active,
        "stale_scene_state": stale_scene_state,
    }


def clear_external_script_trust(context=None, *, state=None, status=NO_EXTERNAL_TRUST_STATUS):
    global _runtime_external_trust_expires_at, _runtime_external_trust_session
    state = state or _scene_state(context)
    _runtime_external_trust_expires_at = 0.0
    _runtime_external_trust_session = False
    if not state:
        return False
    state.external_script_trust_status = str(status or NO_EXTERNAL_TRUST_STATUS)
    state.external_script_trust_expires_at = ""
    return True


def _coerce_ttl_seconds(value, default):
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return int(default)


def external_script_trust_active(context=None, *, state=None):
    return bool(external_script_trust_snapshot(context, state=state)["active"])


def external_script_trust_status(context=None, *, state=None):
    return external_script_trust_snapshot(context, state=state)["status"]


def _audit_external_script_trust(action, *, state=None, ttl_seconds=None, expires_at=None, status=""):
    try:
        audit_log.append_event(
            "external_script_trust",
            source="blender",
            action=str(action),
            ttl_seconds=ttl_seconds,
            expires_at=expires_at,
            active=external_script_trust_active(state=state) if state else False,
            status=status or (external_script_trust_status(state=state) if state else ""),
        )
    except Exception:
        pass


def expire_external_script_trust_if_needed(context=None, *, state=None):
    state = state or _scene_state(context)
    snapshot = external_script_trust_snapshot(state=state)
    expires_at = snapshot["expires_at"]
    if not expires_at or not snapshot["expired"]:
        return False
    clear_external_script_trust(state=state, status=EXTERNAL_TRUST_EXPIRED_STATUS)
    _audit_external_script_trust(
        "expire",
        state=state,
        expires_at=expires_at,
        status=EXTERNAL_TRUST_EXPIRED_STATUS,
    )
    return True


def clear_external_script_trust_for_all_scenes(*, status=NO_EXTERNAL_TRUST_STATUS, audit_action="clear"):
    global _runtime_external_trust_expires_at, _runtime_external_trust_session
    had_runtime_trust = bool(_runtime_external_trust_expires_at or _runtime_external_trust_session)
    _runtime_external_trust_expires_at = 0.0
    _runtime_external_trust_session = False
    cleared = 0
    for scene in getattr(bpy.data, "scenes", []):
        state = getattr(scene, "claude_blender", None)
        if not state:
            continue
        had_scene_status = (
            bool(getattr(state, "external_script_trust_expires_at", ""))
            or getattr(state, "external_script_trust_status", NO_EXTERNAL_TRUST_STATUS) != NO_EXTERNAL_TRUST_STATUS
        )
        if had_scene_status:
            state.external_script_trust_status = str(status or NO_EXTERNAL_TRUST_STATUS)
            state.external_script_trust_expires_at = ""
            cleared += 1
    if had_runtime_trust or cleared:
        _audit_external_script_trust(audit_action, status=status)
    return cleared


def approve_external_script_trust_window(context, *, ttl_seconds=EXTERNAL_TRUST_TTL_SECONDS, session=False):
    global _runtime_external_trust_expires_at, _runtime_external_trust_session
    state = _scene_state(context)
    if not state:
        return {"ok": False, "message": "No Blender scene state is available"}
    session = bool(session)
    if session:
        _runtime_external_trust_expires_at = 0.0
        _runtime_external_trust_session = True
        state.external_script_trust_expires_at = "session"
        state.external_script_trust_status = external_script_trust_status(state=state)
        state.status = state.external_script_trust_status
        _audit_external_script_trust(
            "grant",
            state=state,
            ttl_seconds=None,
            expires_at=None,
            status=state.external_script_trust_status,
        )
        transcript.record_system_message(
            "User approved external script trust for this Blender session. "
            "Agent-generated Python now has the same process permissions as Blender's Run Script command, including "
            "filesystem, network, subprocess, and Blender API access, until revoke, file load, add-on reload, or exit."
        )
        return {
            "ok": True,
            "message": "External script trust approved for this Blender session",
            "expires_at": 0.0,
            "ttl_seconds": 0,
            "session": True,
        }
    ttl = _coerce_ttl_seconds(ttl_seconds, EXTERNAL_TRUST_TTL_SECONDS)
    expires_at = time.time() + ttl
    _runtime_external_trust_expires_at = expires_at
    _runtime_external_trust_session = False
    state.external_script_trust_expires_at = f"{expires_at:.6f}"
    state.external_script_trust_status = external_script_trust_status(state=state)
    state.status = state.external_script_trust_status
    _audit_external_script_trust(
        "grant",
        state=state,
        ttl_seconds=ttl,
        expires_at=expires_at,
        status=state.external_script_trust_status,
    )
    transcript.record_system_message(
        "User approved external script trust. "
        "Agent-generated Python now has the same process permissions as Blender's Run Script command, including "
        "filesystem, network, subprocess, and Blender API access, until trust expires, is revoked, or is cleared."
    )
    return {
        "ok": True,
        "message": "External script trust approved",
        "expires_at": expires_at,
        "ttl_seconds": ttl,
        "session": False,
    }


def revoke_external_script_trust_window(context):
    state = _scene_state(context)
    if not state:
        return {"ok": False, "message": "No Blender scene state is available"}
    clear_external_script_trust(state=state, status="External script trust revoked")
    state.status = "External script trust revoked"
    _audit_external_script_trust("revoke", state=state, status="External script trust revoked")
    transcript.record_system_message("User turned external script trust off.")
    return {"ok": True, "message": "External script trust revoked"}


def _is_checkpoint_path(path):
    return bool(path and CHECKPOINT_FILENAME_RE.search(os.path.basename(path)))


def checkpoint_metadata(context, path, *, ok=None, message=""):
    raw_path = str(path or "").strip()
    path = bpy.path.abspath(raw_path) if raw_path else ""
    exists = bool(path and os.path.exists(path))
    size_bytes = os.path.getsize(path) if exists else 0
    scene = getattr(context, "scene", None) if context else getattr(bpy.context, "scene", None)
    restorable = bool(exists and path.lower().endswith(".blend") and _is_checkpoint_path(path))
    return {
        "ok": bool(exists) if ok is None else bool(ok),
        "path": path,
        "message": str(message or ("Checkpoint available" if exists else "Checkpoint not found")),
        "exists": exists,
        "restorable": restorable,
        "created_by_bridge": _is_checkpoint_path(path),
        "size_bytes": int(size_bytes),
        "scene_name": scene.name if scene else "",
        "current_filepath": bpy.data.filepath or "",
    }


def create_checkpoint(context, checkpoint_dir=None):
    directory = bpy.path.abspath(checkpoint_dir or _default_checkpoint_dir())
    os.makedirs(directory, exist_ok=True)
    current_path = bpy.data.filepath
    if current_path:
        base = os.path.splitext(os.path.basename(current_path))[0]
    else:
        base = context.scene.name if context and context.scene else "unsaved"
    timestamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    stem = os.path.join(directory, f"{_safe_filename(base)}-agent-{timestamp}")
    path = f"{stem}.blend"
    collision_index = 1
    while os.path.lexists(path):
        path = f"{stem}-{collision_index:02d}.blend"
        collision_index += 1
    try:
        bpy.ops.wm.save_as_mainfile(filepath=path, check_existing=False, copy=True)
    except Exception as exc:
        return checkpoint_metadata(
            context,
            path,
            ok=False,
            message=f"Checkpoint failed: {type(exc).__name__}: {exc}",
        )
    metadata = checkpoint_metadata(context, path, ok=True, message="Checkpoint saved")
    metadata["created_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    metadata["source_filepath"] = current_path or ""
    return metadata


def restore_checkpoint(context, checkpoint_path=None):
    state = _scene_state(context)
    path = checkpoint_path or (state.last_checkpoint_path if state else "")
    metadata = checkpoint_metadata(context, path)
    if not metadata["path"]:
        message = "No checkpoint path available"
        if state:
            state.last_checkpoint_restored_status = message
            state.status = message
        return {"ok": False, "message": message, "checkpoint": metadata}
    if not metadata["exists"]:
        message = f"Checkpoint not found: {metadata['path']}"
        if state:
            state.last_checkpoint_restored_status = message
            state.status = message
        metadata["message"] = message
        return {"ok": False, "message": message, "checkpoint": metadata}
    if not metadata["restorable"]:
        message = f"Checkpoint is not a .blend file: {metadata['path']}"
        if metadata["exists"] and metadata["path"].lower().endswith(".blend"):
            message = f"Blend file was not created by Agent Bridge checkpointing: {metadata['path']}"
        if state:
            state.last_checkpoint_restored_status = message
            state.status = message
        metadata["ok"] = False
        metadata["message"] = message
        return {"ok": False, "message": message, "checkpoint": metadata}
    try:
        bpy.ops.wm.open_mainfile(filepath=metadata["path"])
    except Exception as exc:
        message = f"Checkpoint restore failed: {type(exc).__name__}: {exc}"
        state = _scene_state()
        if state:
            state.last_checkpoint_restored_status = message
            state.status = message
        metadata["ok"] = False
        metadata["message"] = message
        return {"ok": False, "message": message, "checkpoint": metadata}

    state = _scene_state()
    message = f"Checkpoint restored: {metadata['path']}"
    if state:
        state.last_checkpoint_status = "Checkpoint restored"
        state.last_checkpoint_path = metadata["path"]
        state.last_checkpoint_restored_status = message
        state.last_checkpoint_restored_path = metadata["path"]
        state.status = message
    transcript.record_system_message(message)
    metadata = checkpoint_metadata(bpy.context, metadata["path"], ok=True, message="Checkpoint restored")
    return {"ok": True, "message": "Checkpoint restored", "checkpoint": metadata}


def _metadata_text(
    *,
    intent,
    expected_changes,
    risk_level,
    target_objects,
    analysis,
):
    lines = [
        "# Agent Bridge Trusted Script",
        "",
        f"Intent: {intent or 'No intent provided'}",
        f"Declared risk: {risk_level or 'unspecified'}",
        f"Detected risk: {analysis.get('risk_level', 'unknown')}",
        f"Checkpoint recommended: {'yes' if analysis.get('checkpoint_recommended') else 'no'}",
        "Execution mode: Blender Run Script equivalent",
        "Authorization: binary session trust",
        f"Targets: {', '.join(target_objects) if target_objects else 'unspecified'}",
        "",
        "Expected changes:",
        expected_changes or "No expected changes provided",
        "",
        "Static analysis:",
        "ADVISORY ONLY (session trust grants Blender Run Script permissions)",
    ]
    for issue in analysis.get("issues", []):
        lines.append(f"- {issue}")
    for warning in analysis.get("warnings", []):
        lines.append(f"- Warning: {warning}")
    for finding in analysis.get("advisory_findings", []):
        lines.append(f"- Advisory finding: {finding}")
    for reason in analysis.get("risk_reasons", [])[:12]:
        lines.append(f"- Risk: {reason}")
    return "\n".join(lines)


def run_trusted_script(
    context,
    *,
    code,
    intent="",
    expected_changes="",
    risk_level="medium",
    target_objects=None,
    checkpoint_enabled=True,
    checkpoint_dir=None,
):
    expire_external_script_trust_if_needed(context)
    if not external_script_trust_active(context):
        return {
            "ok": False,
            "blocked": True,
            "code": "script_trust_required",
            "message": "Agent script trust is off",
            "requires_user_approval": False,
            "auto_run_attempted": False,
            "auto_ran": False,
        }
    target_objects = [str(obj) for obj in (target_objects or []) if str(obj)]
    code = textwrap.dedent(str(code or "")).strip()
    if not code:
        return {
            "ok": False,
            "message": (
                "No script code was provided. Retry draft_script with complete Blender Python "
                "source in the code field; do not ask the user to paste code manually."
            ),
            "missing_code": True,
            "blocked": True,
            "code": "invalid_script_payload",
            "auto_run_attempted": False,
            "auto_ran": False,
        }
    analysis = analyze_trusted_script(code)
    if not analysis["ok"]:
        return {
            "ok": False,
            "blocked": True,
            "code": "invalid_script_payload",
            "message": "Trusted script payload is invalid",
            "analysis": analysis,
            "requires_user_approval": False,
            "auto_run_attempted": False,
            "auto_ran": False,
        }
    script_text = _write_text_block(TRUSTED_SCRIPT_NAME, code)
    text_name = script_text.name
    metadata = _metadata_text(
        intent=str(intent or ""),
        expected_changes=str(expected_changes or ""),
        risk_level=str(risk_level or "medium"),
        target_objects=target_objects,
        analysis=analysis,
    )
    _write_text_block(TRUSTED_SCRIPT_METADATA_NAME, metadata)
    state = _scene_state(context)
    if state:
        state.last_script_error_summary = ""
        state.status = "Trusted script running"

    transcript.record_system_message(
        "Running session-trusted script:\n"
        f"{metadata}\n\n"
        f"Script text datablock: {text_name}"
    )
    prepared = {
        "ok": True,
        "message": "Trusted script prepared for immediate execution",
        "text_datablock": text_name,
        "metadata_datablock": TRUSTED_SCRIPT_METADATA_NAME,
        "analysis": analysis,
        "requires_user_approval": False,
        "trusted_manual_mode": True,
        "authorization_model": script_execution.AUTHORIZATION_MODEL,
    }

    checkpoint = {"ok": False, "message": "Checkpoint disabled", "path": ""}
    if checkpoint_enabled:
        checkpoint = create_checkpoint(context, checkpoint_dir=checkpoint_dir)
        state = _scene_state(context)
        if state:
            state.last_checkpoint_status = checkpoint["message"]
            state.last_checkpoint_path = checkpoint.get("path", "")
            state.last_checkpoint_restored_status = "No checkpoint restored"
            state.last_checkpoint_restored_path = ""
        if not checkpoint["ok"]:
            transcript.record_system_message(checkpoint["message"])
            if state:
                state.status = checkpoint["message"]
            return {
                "ok": False,
                "blocked": True,
                "code": "checkpoint_failed",
                "message": checkpoint["message"],
                "checkpoint": checkpoint,
                "analysis": analysis,
                "prepared": prepared,
                "authorization_model": script_execution.AUTHORIZATION_MODEL,
                "requires_user_approval": False,
                "auto_run_attempted": False,
                "auto_ran": False,
            }
    elif state:
        state.last_checkpoint_status = "Checkpoint disabled"
        state.last_checkpoint_path = ""

    expire_external_script_trust_if_needed(context)
    if not external_script_trust_active(context):
        if state:
            state.status = "Agent script trust is off"
        return {
            "ok": False,
            "blocked": True,
            "code": "script_trust_required",
            "message": "Agent script trust was revoked before execution",
            "requires_user_approval": False,
            "auto_run_attempted": False,
            "auto_ran": False,
            "checkpoint": checkpoint,
            "prepared": prepared,
        }

    stdout = io.StringIO()
    namespace = {
        "__name__": "__blender_agent_trusted_script__",
        "bpy": bpy,
        "context": context,
        "scene": context.scene,
    }
    try:
        bpy.ops.ed.undo_push(message="Before Agent Bridge trusted script")
    except Exception:
        pass

    try:
        compiled = compile(code, text_name, "exec")
        with contextlib.redirect_stdout(stdout):
            exec(compiled, namespace, namespace)
    except Exception:
        output = stdout.getvalue()
        error = traceback.format_exc()
        log = (
            "Script failed.\n\n"
            f"CHECKPOINT:\n{checkpoint.get('path') or checkpoint.get('message')}\n\n"
            f"STDOUT:\n{output}\n\n"
            f"ERROR:\n{error}"
        )
        _write_text_block(SCRIPT_LOG_NAME, log)
        state = _scene_state()
        if state:
            state.last_script_error_summary = _short_text(error)
            state.last_script_log_name = SCRIPT_LOG_NAME
            state.status = "Script failed"
        transcript.record_system_message(log)
        return {
            "ok": False,
            "message": "Script failed",
            "error": error,
            "stdout": output,
            "log_datablock": SCRIPT_LOG_NAME,
            "checkpoint": checkpoint,
            "analysis": analysis,
            "prepared": prepared,
            "authorization_model": script_execution.AUTHORIZATION_MODEL,
            "auto_run_attempted": True,
            "auto_ran": False,
        }

    output = stdout.getvalue()
    log = (
        "Script executed successfully.\n\n"
        f"CHECKPOINT:\n{checkpoint.get('path') or checkpoint.get('message')}\n\n"
        f"STDOUT:\n{output or '(none)'}"
    )
    _write_text_block(SCRIPT_LOG_NAME, log)
    state = _scene_state()
    if state:
        state.last_script_error_summary = ""
        state.last_script_log_name = SCRIPT_LOG_NAME
        state.status = "Script executed"
    transcript.record_system_message(log)
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    return {
        "ok": True,
        "message": "Script executed with Blender Run Script permissions",
        "stdout": output,
        "log_datablock": SCRIPT_LOG_NAME,
        "checkpoint": checkpoint,
        "analysis": analysis,
        "prepared": prepared,
        "authorization_model": script_execution.AUTHORIZATION_MODEL,
        "auto_run_attempted": True,
        "auto_ran": True,
    }


@persistent
def _clear_external_script_trust_on_load(_dummy):
    clear_external_script_trust_for_all_scenes(
        status=NO_EXTERNAL_TRUST_STATUS,
        audit_action="clear_on_load",
    )


def _remove_external_trust_load_handler():
    handlers = bpy.app.handlers.load_post
    for handler in list(handlers):
        if (
            getattr(handler, "__name__", "") == "_clear_external_script_trust_on_load"
            and str(getattr(handler, "__module__", "")).endswith(".script_runner")
        ):
            handlers.remove(handler)


def register():
    clear_external_script_trust_for_all_scenes(
        status=NO_EXTERNAL_TRUST_STATUS,
        audit_action="clear_on_register",
    )
    _remove_external_trust_load_handler()
    bpy.app.handlers.load_post.append(_clear_external_script_trust_on_load)


def unregister():
    _remove_external_trust_load_handler()
    clear_external_script_trust_for_all_scenes(
        status=NO_EXTERNAL_TRUST_STATUS,
        audit_action="clear_on_unregister",
    )
