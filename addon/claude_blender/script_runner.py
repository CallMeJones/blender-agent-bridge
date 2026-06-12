"""Approval-gated generated Python staging and execution."""

from __future__ import annotations

import ast
import contextlib
import datetime as _dt
import io
import os
import re
import textwrap
import traceback

import bpy

from . import transcript

PENDING_SCRIPT_NAME = "Claude Pending Script"
SCRIPT_LOG_NAME = "Claude Script Log"
SCRIPT_FAILURE_PROMPT_NAME = "Claude Script Repair Context"

MAX_SCRIPT_CHARS = 80_000
MAX_STATE_TEXT_CHARS = 1800

BLOCKED_NAMES = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "open",
    "input",
    "globals",
    "locals",
}

BLOCKED_MODULES = {
    "os",
    "subprocess",
    "socket",
    "shutil",
    "pathlib",
    "requests",
    "urllib",
    "http",
    "ftplib",
    "pickle",
}

WARNING_ATTRS = {
    "delete",
    "remove",
    "unlink",
    "orphans_purge",
    "save_as_mainfile",
    "open_mainfile",
    "quit_blender",
}


def _default_checkpoint_dir():
    return os.path.join(os.path.expanduser("~"), ".claude_blender", "checkpoints")


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


def _read_text_block(name):
    text = bpy.data.texts.get(name)
    return text.as_string() if text else ""


def _short_text(value, max_chars=MAX_STATE_TEXT_CHARS):
    value = str(value or "").strip()
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}... [truncated]"


def _join_lines(values, *, empty="", max_chars=MAX_STATE_TEXT_CHARS):
    lines = [str(value) for value in values or [] if str(value)]
    if not lines:
        return empty
    return _short_text("\n".join(f"- {line}" for line in lines), max_chars=max_chars)


def _line(node):
    return getattr(node, "lineno", "?")


def _call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def analyze_script(source):
    blocks = []
    warnings = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {
            "ok": False,
            "blocked": True,
            "issues": [f"Syntax error: {exc}"],
            "warnings": [],
        }
    if len(source) > MAX_SCRIPT_CHARS:
        blocks.append(f"Script is too large: {len(source)} chars > {MAX_SCRIPT_CHARS}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            root_name = call_name.split(".")[0]
            if root_name in BLOCKED_NAMES:
                blocks.append(f"Line {_line(node)} blocked call: {call_name}")
            if call_name in {"bpy.ops.wm.save_as_mainfile", "bpy.ops.wm.open_mainfile", "bpy.ops.wm.quit_blender"}:
                blocks.append(f"Line {_line(node)} blocked Blender file/window operation: {call_name}")
            attr_name = call_name.split(".")[-1]
            if attr_name in WARNING_ATTRS:
                warnings.append(f"Line {_line(node)} risky call: {call_name}")
        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value is True:
            warnings.append(f"Line {_line(node)} possible unbounded loop: while True")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in BLOCKED_MODULES:
                    blocks.append(f"Line {_line(node)} blocked import: {alias.name}")
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in BLOCKED_MODULES:
                blocks.append(f"Line {_line(node)} blocked import: {node.module}")
    return {
        "ok": not blocks,
        "blocked": bool(blocks),
        "issues": blocks,
        "warnings": warnings,
    }


def create_checkpoint(context, checkpoint_dir=None):
    directory = bpy.path.abspath(checkpoint_dir or _default_checkpoint_dir())
    os.makedirs(directory, exist_ok=True)
    current_path = bpy.data.filepath
    if current_path:
        base = os.path.splitext(os.path.basename(current_path))[0]
    else:
        base = context.scene.name if context and context.scene else "unsaved"
    timestamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(directory, f"{_safe_filename(base)}-claude-{timestamp}.blend")
    try:
        bpy.ops.wm.save_as_mainfile(filepath=path, check_existing=False, copy=True)
    except Exception as exc:
        return {
            "ok": False,
            "path": path,
            "message": f"Checkpoint failed: {type(exc).__name__}: {exc}",
        }
    return {
        "ok": True,
        "path": path,
        "message": "Checkpoint saved",
    }


def _metadata_text(*, intent, expected_changes, risk_level, target_objects, analysis):
    lines = [
        "# Claude Pending Script",
        "",
        f"Intent: {intent or 'No intent provided'}",
        f"Risk: {risk_level or 'unspecified'}",
        f"Targets: {', '.join(target_objects) if target_objects else 'unspecified'}",
        "",
        "Expected changes:",
        expected_changes or "No expected changes provided",
        "",
        "Static analysis:",
        "PASS" if analysis["ok"] else "BLOCKED",
    ]
    for issue in analysis.get("issues", []):
        lines.append(f"- {issue}")
    for warning in analysis.get("warnings", []):
        lines.append(f"- Warning: {warning}")
    return "\n".join(lines)


def stage_script(context, *, code, intent="", expected_changes="", risk_level="medium", target_objects=None):
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
        }
    analysis = analyze_script(code)
    script_text = _write_text_block(PENDING_SCRIPT_NAME, code)
    metadata = _metadata_text(
        intent=str(intent or ""),
        expected_changes=str(expected_changes or ""),
        risk_level=str(risk_level or "medium"),
        target_objects=target_objects,
        analysis=analysis,
    )
    _write_text_block(f"{PENDING_SCRIPT_NAME} Metadata", metadata)

    state = getattr(context.scene, "claude_blender", None)
    if state:
        issue_text = _join_lines(analysis.get("issues"))
        warning_text = _join_lines(analysis.get("warnings"))
        if analysis.get("blocked"):
            status = "Blocked by static checks"
        elif analysis.get("warnings"):
            status = f"Pending approval with {len(analysis.get('warnings', []))} warning(s)"
        else:
            status = "Pending approval"
        state.pending_script = True
        state.pending_script_blocked = bool(analysis.get("blocked"))
        state.pending_script_text_name = script_text.name
        state.pending_script_intent = str(intent or "")[:1000]
        state.pending_script_expected_changes = str(expected_changes or "")[:1000]
        state.pending_script_risk = str(risk_level or "medium")[:80]
        state.pending_script_status = status
        state.pending_script_issues = issue_text
        state.pending_script_warnings = warning_text
        state.last_script_error_summary = ""
        state.status = state.pending_script_status

    transcript.record_system_message(
        "Drafted pending script:\n"
        f"{metadata}\n\n"
        f"Script text datablock: {script_text.name}"
    )
    return {
        "ok": True,
        "message": "Script staged for approval" if analysis["ok"] else "Script staged but blocked by static checks",
        "text_datablock": script_text.name,
        "metadata_datablock": f"{PENDING_SCRIPT_NAME} Metadata",
        "analysis": analysis,
        "requires_user_approval": True,
    }


def reject_pending_script(context):
    state = getattr(context.scene, "claude_blender", None)
    if state:
        state.pending_script = False
        state.pending_script_blocked = False
        state.pending_script_status = "Pending script rejected"
        state.pending_script_text_name = ""
        state.pending_script_intent = ""
        state.pending_script_expected_changes = ""
        state.pending_script_risk = ""
        state.pending_script_issues = ""
        state.pending_script_warnings = ""
        state.status = "Pending script rejected"
    transcript.record_system_message("Pending script rejected by user.")
    return {"ok": True, "message": "Pending script rejected"}


def pending_script_source(context):
    state = getattr(context.scene, "claude_blender", None)
    text_name = state.pending_script_text_name if state else PENDING_SCRIPT_NAME
    return _read_text_block(text_name or PENDING_SCRIPT_NAME)


def script_log_text():
    return _read_text_block(SCRIPT_LOG_NAME)


def repair_context_text(context):
    source = pending_script_source(context)
    log_text = script_log_text()
    body = (
        "The user approved this Blender Python script, but execution failed.\n\n"
        "Pending script:\n"
        f"{source or '(missing)'}\n\n"
        "Execution log / traceback:\n"
        f"{log_text or '(missing)'}\n"
    )
    _write_text_block(SCRIPT_FAILURE_PROMPT_NAME, body)
    return body


def run_pending_script(context, *, checkpoint_enabled=True, checkpoint_dir=None):
    state = getattr(context.scene, "claude_blender", None)
    text_name = state.pending_script_text_name if state else PENDING_SCRIPT_NAME
    source = _read_text_block(text_name or PENDING_SCRIPT_NAME)
    if not source:
        return {"ok": False, "message": "No pending script text found"}
    analysis = analyze_script(source)
    if not analysis["ok"]:
        if state:
            state.pending_script_blocked = True
            state.pending_script_status = "Blocked by static checks"
            state.pending_script_issues = _join_lines(analysis.get("issues"))
            state.pending_script_warnings = _join_lines(analysis.get("warnings"))
            state.status = state.pending_script_status
        return {"ok": False, "message": "Script blocked by static checks", "analysis": analysis}

    checkpoint = {"ok": False, "message": "Checkpoint disabled", "path": ""}
    if checkpoint_enabled:
        checkpoint = create_checkpoint(context, checkpoint_dir=checkpoint_dir)
        if state:
            state.last_checkpoint_status = checkpoint["message"]
            state.last_checkpoint_path = checkpoint.get("path", "")
        if not checkpoint["ok"]:
            transcript.record_system_message(checkpoint["message"])
            if state:
                state.status = checkpoint["message"]
                state.pending_script_status = "Checkpoint failed"
            return {
                "ok": False,
                "message": checkpoint["message"],
                "checkpoint": checkpoint,
            }
    elif state:
        state.last_checkpoint_status = "Checkpoint disabled"
        state.last_checkpoint_path = ""

    stdout = io.StringIO()
    namespace = {
        "__name__": "__claude_blender_pending_script__",
        "bpy": bpy,
        "context": context,
        "scene": context.scene,
    }
    try:
        bpy.ops.ed.undo_push(message="Before Claude approved script")
    except Exception:
        pass

    try:
        compiled = compile(source, text_name or PENDING_SCRIPT_NAME, "exec")
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
        if state:
            state.pending_script_status = "Script failed"
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
        }

    output = stdout.getvalue()
    log = (
        "Script executed successfully.\n\n"
        f"CHECKPOINT:\n{checkpoint.get('path') or checkpoint.get('message')}\n\n"
        f"STDOUT:\n{output or '(none)'}"
    )
    _write_text_block(SCRIPT_LOG_NAME, log)
    if state:
        state.pending_script = False
        state.pending_script_blocked = False
        state.pending_script_status = "Script executed"
        state.pending_script_text_name = ""
        state.pending_script_intent = ""
        state.pending_script_expected_changes = ""
        state.pending_script_risk = ""
        state.pending_script_issues = ""
        state.pending_script_warnings = ""
        state.last_script_error_summary = ""
        state.last_script_log_name = SCRIPT_LOG_NAME
        state.status = "Script executed"
    transcript.record_system_message(log)
    try:
        context.view_layer.update()
    except Exception:
        pass
    return {
        "ok": True,
        "message": "Script executed",
        "stdout": output,
        "log_datablock": SCRIPT_LOG_NAME,
        "checkpoint": checkpoint,
    }


def register():
    pass


def unregister():
    pass
