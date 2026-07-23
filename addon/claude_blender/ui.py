"""Blender UI panels and operators."""

from __future__ import annotations

import json
import os
import queue
import threading

import bpy
from bpy.app.handlers import persistent

from . import (
    audit_log,
    bridge_server,
    build_info,
    context_bundle,
    context_planner,
    docs_index,
    external_assets,
    lab_parity,
    live_preview,
    preferences,
    script_runner,
    transcript,
    viewport_capture,
)


_docs_results = queue.Queue()
_docs_timer_registered = False


def _prefs(context):
    return preferences.get_preferences(context)


def _format_docs_status(status):
    errors = status.get("build_errors") or {}
    if not status.get("full_index_exists") and not status.get("manual_index_exists"):
        message = f"Docs {status['version']}: curated cache only"
    else:
        api_count = int(status.get("full_index_entries", 0) or 0)
        manual_count = int(status.get("manual_index_entries", 0) or 0)
        message = (
            f"Docs {status['version']}: "
            f"API {api_count} pages, Manual {manual_count} pages"
        )
    if errors:
        error_text = "; ".join(f"{name} failed: {detail}" for name, detail in sorted(errors.items()))
        message = f"{message} ({error_text})"
    return message[:1000]


def _format_bytes(size):
    size = int(size or 0)
    if size <= 0:
        return ""
    units = ("B", "KB", "MB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{size} {unit}"
        value /= 1024
    return f"{size} B"


def _draw_wrapped(layout, text, *, width=46, max_lines=4, empty="None"):
    lines = transcript.preview_lines(text or empty, width=width, max_lines=max_lines)
    if not lines:
        lines = [empty]
    for line in lines:
        layout.label(text=line)


def _draw_field(layout, label, text, *, width=44, max_lines=4, empty="None"):
    layout.label(text=f"{label}:")
    _draw_wrapped(layout, text, width=width, max_lines=max_lines, empty=empty)


def _draw_section(layout, title):
    box = layout.box()
    box.label(text=title)
    return box


def _write_text_datablock(name, body):
    text = bpy.data.texts.get(name)
    if text is None:
        text = bpy.data.texts.new(name)
    text.clear()
    text.write(str(body or ""))
    return text.name


def _short_hash(value):
    value = str(value or "").strip()
    return value[:12] if value else "none"


def _operation_summary(active, last):
    operation = active or last or {}
    if not operation:
        return "No bridge operation recorded"
    state = "Running" if active else "Last"
    tool = str(operation.get("tool") or "tool")
    elapsed = int(operation.get("elapsed_seconds") or 0)
    status = ""
    if not active and "ok" in operation:
        status = "ok" if operation.get("ok") else "failed"
    timeout = int(operation.get("timeout_seconds") or 0)
    bits = [f"{state}: {tool}"]
    if elapsed:
        bits.append(f"{elapsed}s")
    if timeout:
        bits.append(f"timeout {timeout}s")
    if status:
        bits.append(status)
    if operation.get("message"):
        bits.append(str(operation["message"])[:160])
    return " | ".join(bits)


def _refresh_bridge_diagnostics_state(context, state, prefs):
    url = state.bridge_url or bridge_server.bridge_url() or f"http://127.0.0.1:{getattr(prefs, 'bridge_port', bridge_server.DEFAULT_PORT)}"
    blender_version = ".".join(str(part) for part in bpy.app.version)
    diagnostics = build_info.diagnostics_dict(bridge_url=url, blender_version=blender_version)
    bridge_running = bridge_server.is_running()
    state.bridge_running = bridge_running
    state.bridge_url = url
    state.bridge_status = "Bridge running" if bridge_running else "Bridge stopped"
    runtime = str(diagnostics.get("addon_runtime_source_status") or "")
    hash_status = str(diagnostics.get("addon_source_hash_status") or "")
    hash_match = diagnostics.get("addon_source_hash_match")
    match_text = "not provided" if hash_match is None else ("match" if hash_match else "mismatch")
    state.bridge_source_status = (
        f"Source: {runtime or 'unknown'} | Config hash: {hash_status or 'unknown'}/{match_text} | "
        f"Add-on {_short_hash(diagnostics.get('addon_source_hash'))} | "
        f"Expected {_short_hash(diagnostics.get('expected_addon_source_hash'))}"
    )
    state.bridge_diagnostics_status = (
        f"Bridge: {'On' if bridge_running else 'Off'} | "
        f"Add-on {build_info.ADDON_VERSION} | Bridge {build_info.BRIDGE_VERSION} | "
        f"MCP {build_info.MCP_SERVER_VERSION} | Config {build_info.MCP_CONFIG_VERSION}"
    )
    active = bridge_server._active_operation_status()
    last = bridge_server._last_operation_status()
    state.bridge_operation_status = _operation_summary(active, last)
    state.bridge_refresh_hint = (
        "Restart or refresh the MCP client if newly added Blender tools are missing from its callable tool list."
    )
    return {
        "diagnostics": diagnostics,
        "active_operation": active,
        "last_operation": last,
    }


def _refresh_preview_manifest_state(state):
    manifest = live_preview.transaction_manifest()
    body = json.dumps(manifest, indent=2, sort_keys=True, default=str)
    state.preview_manifest_text_name = _write_text_datablock(state.preview_manifest_text_name or "Claude Preview Manifest", body)
    status = manifest.get("status", "unknown")
    if status == "none":
        state.preview_manifest_status = "No preview transaction"
    else:
        created = sum(len(values) for values in (manifest.get("created") or {}).values())
        modified = sum(len(values) for values in (manifest.get("modified") or {}).values())
        state.preview_manifest_status = (
            f"Preview: {str(status).title()}, {manifest.get('applied_step_count', 0)} step(s), "
            f"{manifest.get('snapshot_count', 0)} rollback snapshot(s), "
            f"{created} created, {modified} modified"
        )
    return body


def _refresh_audit_log_state(state, *, limit=40):
    body = audit_log.format_recent(limit)
    state.audit_log_text_name = _write_text_datablock(audit_log.AUDIT_LOG_TEXT_NAME, body)
    state.audit_log_status = audit_log.status_summary()
    return body


def _resource_line(entry):
    entry = entry or {}
    kind = str(entry.get("kind") or "resource").replace("_", " ")
    item_id = str(entry.get("id") or "")
    summary = entry.get("summary") or {}
    counts = []
    if summary.get("frame_count"):
        counts.append(f"{summary['frame_count']} frame(s)")
    if summary.get("image_count"):
        counts.append(f"{summary['image_count']} image(s)")
    if summary.get("width") and summary.get("height"):
        counts.append(f"{summary['width']}x{summary['height']}")
    bits = [kind]
    if item_id:
        bits.append(item_id)
    if counts:
        bits.append(", ".join(counts))
    return " | ".join(bits)


def _refresh_visual_evidence_state(context, state, prefs):
    capture_dir = getattr(prefs, "capture_cache_dir", None)
    resources = lab_parity.get_visual_evidence_resources(context, include_unavailable=True, capture_dir=capture_dir)
    latest = resources.get("latest_available") or {}
    if latest:
        state.visual_evidence_status = (
            f"Evidence: {resources.get('available_count', 0)} available | latest {_resource_line(latest)}"
        )
        state.visual_evidence_latest_path = str((latest.get("path_info") or {}).get("path") or latest.get("path") or "")
    else:
        state.visual_evidence_status = f"Evidence: 0 available | {resources.get('resource_count', 0)} tracked type(s)"
        state.visual_evidence_latest_path = ""
    body = json.dumps(resources, indent=2, sort_keys=True, default=str)
    state.visual_evidence_text_name = _write_text_datablock(
        state.visual_evidence_text_name or "Claude Visual Evidence",
        body,
    )
    return body


def _refresh_control_center_state(context, state, prefs):
    bridge = _refresh_bridge_diagnostics_state(context, state, prefs)
    preview_body = _refresh_preview_manifest_state(state)
    audit_body = _refresh_audit_log_state(state)
    visual_body = _refresh_visual_evidence_state(context, state, prefs)
    body = json.dumps(
        {
            "bridge": bridge,
            "preview_manifest": json.loads(preview_body),
            "audit_status": audit_log.status(),
            "visual_evidence": json.loads(visual_body),
        },
        indent=2,
        sort_keys=True,
        default=str,
    )
    _write_text_datablock("Claude Bridge Control Center", body)
    state.status = "Bridge control center refreshed"
    return body


def _update_screenshot_state(state, bundle):
    visual = bundle.get("visual_context") or {}
    if not visual.get("requested"):
        state.last_screenshot_status = "Viewport toggle is off"
        state.last_screenshot_path = ""
        state.last_screenshot_image_name = ""
        state.last_screenshot_size = 0
        return
    state.last_screenshot_path = str(visual.get("path") or "")
    state.last_screenshot_image_name = str(visual.get("preview_image") or "")
    state.last_screenshot_size = int(visual.get("size_bytes") or 0)
    if visual.get("available"):
        state.last_screenshot_status = "Screenshot captured and attached"
    else:
        state.last_screenshot_status = str(visual.get("note") or "Screenshot unavailable")


def _process_docs_results():
    global _docs_timer_registered
    while True:
        try:
            scene_name, ok, message = _docs_results.get_nowait()
        except queue.Empty:
            break
        scene = bpy.data.scenes.get(scene_name)
        if scene and hasattr(scene, "claude_blender"):
            scene.claude_blender.docs_cache_building = False
            scene.claude_blender.docs_cache_status = message
            scene.claude_blender.status = message if ok else f"Docs error: {message}"
    if _docs_results.empty():
        for scene in bpy.data.scenes:
            if hasattr(scene, "claude_blender") and scene.claude_blender.docs_cache_building:
                return 0.5
        _docs_timer_registered = False
        return None
    return 0.2


def _docs_timer_is_registered():
    try:
        return bool(bpy.app.timers.is_registered(_process_docs_results))
    except Exception:
        return bool(_docs_timer_registered)


def _register_docs_timer():
    try:
        bpy.app.timers.register(_process_docs_results, first_interval=0.2, persistent=True)
    except TypeError:
        bpy.app.timers.register(_process_docs_results, first_interval=0.2)


def _ensure_docs_timer():
    global _docs_timer_registered
    if _docs_timer_is_registered():
        _docs_timer_registered = True
        return
    _register_docs_timer()
    _docs_timer_registered = True


@persistent
def _ensure_docs_timer_after_load(_dummy):
    global _docs_timer_registered
    has_building_scene = any(
        hasattr(scene, "claude_blender") and scene.claude_blender.docs_cache_building
        for scene in bpy.data.scenes
    )
    if _docs_timer_registered or not _docs_results.empty() or has_building_scene:
        if not _docs_timer_is_registered():
            _docs_timer_registered = False
        _ensure_docs_timer()


def _remove_docs_timer_load_handler():
    handlers = bpy.app.handlers.load_post
    for handler in list(handlers):
        if (
            getattr(handler, "__name__", "") == "_ensure_docs_timer_after_load"
            and str(getattr(handler, "__module__", "")).endswith(".ui")
        ):
            handlers.remove(handler)


def _update_context_plan_state(state, metadata):
    state.context_plan_chars = int(metadata.get("chars") or 0)
    state.context_plan_tokens = int(metadata.get("estimated_tokens") or 0)
    state.context_plan_status = context_planner.summarize_plan(metadata)
    included = metadata.get("included") or []
    omitted = metadata.get("omitted") or []
    parts = []
    if included:
        parts.append("Included: " + ", ".join(included[:8]))
    if omitted:
        parts.append("Omitted: " + "; ".join(omitted[:3]))
    state.context_plan_items = " | ".join(parts)[:1000]


def _build_context_bundle(context, state, prefs, *, prompt=""):
    bundle = context_bundle.build_context_bundle(
        context,
        include_visual=state.include_screenshot,
        capture_dir=getattr(prefs, "capture_cache_dir", None),
        max_screenshot_bytes=getattr(prefs, "max_screenshot_bytes", None),
    )
    planned, metadata = context_planner.plan_context_bundle(prompt, bundle)
    _update_context_plan_state(state, metadata)
    return planned


class CLAUDEBLENDER_OT_capture_context(bpy.types.Operator):
    bl_idname = "claude_blender.capture_context"
    bl_label = "Capture Context"
    bl_description = "Capture the current Blender context bundle"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        state = context.scene.claude_blender
        prefs = _prefs(context)
        bundle = _build_context_bundle(context, state, prefs, prompt="")
        _update_screenshot_state(state, bundle)
        state.last_context_summary = context_bundle.summarize_for_status(bundle)
        state.last_response = (
            "Scene context captured.\n"
            f"{state.last_context_summary}\n"
            "Full context bundle was saved to the transcript text datablock."
        )
        transcript.record_system_message(
            "Captured context bundle:\n"
            f"{json.dumps(context_bundle.public_bundle(bundle), indent=2, sort_keys=True)}"
        )
        state.status = "Context captured"
        return {"FINISHED"}


class CLAUDEBLENDER_OT_commit_preview(bpy.types.Operator):
    bl_idname = "claude_blender.commit_preview"
    bl_label = "Commit"
    bl_description = "Commit the current live preview transaction"

    def execute(self, context):
        result = live_preview.commit(context)
        context.scene.claude_blender.status = result["message"]
        return {"FINISHED"} if result["ok"] else {"CANCELLED"}


class CLAUDEBLENDER_OT_revert_preview(bpy.types.Operator):
    bl_idname = "claude_blender.revert_preview"
    bl_label = "Revert"
    bl_description = "Revert the current live preview transaction"

    def execute(self, context):
        result = live_preview.revert(context)
        context.scene.claude_blender.status = result["message"]
        return {"FINISHED"} if result["ok"] else {"CANCELLED"}


class CLAUDEBLENDER_OT_revert_last_preview_step(bpy.types.Operator):
    bl_idname = "claude_blender.revert_last_preview_step"
    bl_label = "Revert Last Step"
    bl_description = "Remove only the latest isolated imported-asset step and preserve earlier pending preview work"

    def execute(self, context):
        result = live_preview.revert_last_created_step(context, allowed_types={"import_external_asset"})
        context.scene.claude_blender.status = result["message"]
        if result.get("rollback_warnings"):
            self.report({"WARNING"}, result["rollback_warning_summary"])
        elif not result.get("ok"):
            self.report({"WARNING"}, result["message"])
        return {"FINISHED"} if result.get("ok") else {"CANCELLED"}


class CLAUDEBLENDER_OT_undo_last(bpy.types.Operator):
    bl_idname = "claude_blender.undo_last"
    bl_label = "Undo Last Change"
    bl_description = "Undo the latest Blender change, reverting pending live previews first"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        state = context.scene.claude_blender
        transaction = live_preview.current_transaction()
        if transaction and transaction.get("status") == "pending":
            result = live_preview.revert(context)
            state.status = "Preview reverted by Undo" if result["ok"] else result["message"]
            return {"FINISHED"} if result["ok"] else {"CANCELLED"}
        try:
            result = bpy.ops.ed.undo()
        except RuntimeError as exc:
            state.status = f"Undo failed: {exc}"
            return {"CANCELLED"}
        state.pending_preview = False
        state.pending_preview_label = ""
        state.pending_preview_summary = ""
        state.pending_preview_warnings = ""
        live_preview.redraw(context)
        state.status = "Undo complete" if "FINISHED" in result else "Nothing to undo"
        return {"FINISHED"} if "FINISHED" in result else {"CANCELLED"}


def _draw_bridge_summary(layout, state):
    bridge_running = bridge_server.is_running()
    row = layout.row(align=True)
    row.label(
        text="Bridge is ready" if bridge_running else "Bridge is offline",
        icon="CHECKMARK" if bridge_running else "CANCEL",
    )
    if bridge_running:
        row.operator("claude_blender.stop_bridge", text="Stop")
    else:
        row.operator("claude_blender.start_bridge", text="Start", icon="PLAY")
    layout.operator("claude_blender.copy_mcp_config", text="Copy MCP Config", icon="COPYDOWN")

    if "Source: stale" in str(state.bridge_source_status or ""):
        stale_box = layout.box()
        stale_box.alert = True
        stale_box.label(text="Patched files are not loaded", icon="ERROR")
        _draw_wrapped(stale_box, "Save the file, then reload scripts or restart Blender", width=32, max_lines=2)
        stale_box.operator("claude_blender.reload_scripts", text="Reload Scripts", icon="FILE_REFRESH")


def _draw_script_trust_control(layout, context, state):
    trust_snapshot = script_runner.external_script_trust_snapshot(context, state=state)
    if trust_snapshot["active"]:
        row = layout.row(align=True)
        row.label(text="Script trust active", icon="UNLOCKED")
        row.operator("claude_blender.revoke_external_script_trust", text="Revoke", icon="CANCEL")
        return

    layout.operator(
        "claude_blender.approve_external_script_trust",
        text="Trust Agent Scripts",
        icon="LOCKED",
    )


def _draw_action_center(layout, state):
    has_preview = bool(state.pending_preview)
    if not has_preview:
        return

    actions = _draw_section(layout, "Pending")

    if state.pending_preview:
        _draw_field(actions, "Live Preview", state.pending_preview_label or "Pending live changes", max_lines=2)
        if state.pending_preview_summary:
            _draw_field(actions, "Rollback", state.pending_preview_summary, width=44, max_lines=4)
        if state.pending_preview_warnings:
            _draw_field(actions, "Warnings", state.pending_preview_warnings, width=44, max_lines=4)
        row = actions.row(align=True)
        row.operator("claude_blender.commit_preview", text="Commit", icon="CHECKMARK")
        if live_preview.last_created_step_revertibility(
            allowed_types={"import_external_asset"}
        ).get("ok"):
            row.operator("claude_blender.revert_last_preview_step", text="Last Step", icon="LOOP_BACK")
        row.operator("claude_blender.revert_preview", text="Revert", icon="LOOP_BACK")


class CLAUDEBLENDER_OT_approve_external_script_trust(bpy.types.Operator):
    bl_idname = "claude_blender.approve_external_script_trust"
    bl_label = "Trust Agent Scripts"
    bl_description = "Let connected agent clients run Python with Blender's Run Script permissions for this session"
    bl_options = {"REGISTER", "INTERNAL"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=540)

    def draw(self, context):
        self.layout.label(text="Trust agent-generated Python for this Blender session?", icon="ERROR")
        self.layout.label(text="Equivalent to Blender Run Script: files, network, and processes are allowed.")
        self.layout.label(text="Any client connected to this local bridge can use these permissions.")
        self.layout.label(text="Runs with Blender's OS permissions until Revoke, file load, reload, or exit.")

    def execute(self, context):
        state = context.scene.claude_blender
        result = script_runner.approve_external_script_trust_window(
            context,
            session=True,
        )
        message = result.get("message", "External script trust finished")
        if result.get("ok"):
            state.last_response = (
                "Agent script trust is active for this Blender session.\n"
                "Agent Python now has Blender Run Script permissions, including files, network, and processes.\n"
                "Trust lasts until Revoke, reload, file load, or Blender exit."
            )
            self.report({"INFO"}, "External script trust approved")
            return {"FINISHED"}
        state.last_response = f"External script trust was not approved.\n{message}"
        self.report({"ERROR"}, message)
        return {"CANCELLED"}


class CLAUDEBLENDER_OT_revoke_external_script_trust(bpy.types.Operator):
    bl_idname = "claude_blender.revoke_external_script_trust"
    bl_label = "Revoke External Trust"
    bl_description = "Revoke the active external script trust grant"
    bl_options = {"REGISTER"}

    def execute(self, context):
        state = context.scene.claude_blender
        result = script_runner.revoke_external_script_trust_window(context)
        message = result.get("message", "External script trust revoked")
        state.last_response = message
        if result.get("ok"):
            self.report({"INFO"}, message)
            return {"FINISHED"}
        self.report({"ERROR"}, message)
        return {"CANCELLED"}


class CLAUDEBLENDER_OT_restore_last_checkpoint(bpy.types.Operator):
    bl_idname = "claude_blender.restore_last_checkpoint"
    bl_label = "Restore Checkpoint"
    bl_description = "Open the last saved script checkpoint blend file"
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        result = script_runner.restore_checkpoint(context)
        state = getattr(getattr(bpy.context, "scene", None), "claude_blender", None)
        message = result.get("message", "Checkpoint restore finished")
        if state:
            state.last_response = message
        self.report({"INFO"} if result.get("ok") else {"ERROR"}, message)
        return {"FINISHED"} if result.get("ok") else {"CANCELLED"}


class CLAUDEBLENDER_OT_capture_viewport_preview(bpy.types.Operator):
    bl_idname = "claude_blender.capture_viewport_preview"
    bl_label = "Capture Preview"
    bl_description = "Capture the viewport screenshot used when the Viewport toggle is on"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        state = context.scene.claude_blender
        if not state.include_screenshot:
            state.last_screenshot_status = "Viewport toggle is off"
            state.status = state.last_screenshot_status
            return {"CANCELLED"}
        prefs = _prefs(context)
        metadata, _attachments = viewport_capture.capture_viewport(
            context,
            capture_dir=getattr(prefs, "capture_cache_dir", None),
            max_bytes=getattr(prefs, "max_screenshot_bytes", viewport_capture.DEFAULT_MAX_BYTES),
        )
        _update_screenshot_state(state, {"visual_context": metadata})
        state.status = state.last_screenshot_status
        return {"FINISHED"} if metadata.get("available") else {"CANCELLED"}


class CLAUDEBLENDER_OT_open_last_screenshot(bpy.types.Operator):
    bl_idname = "claude_blender.open_last_screenshot"
    bl_label = "Open Screenshot"
    bl_description = "Open the last captured viewport screenshot"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        state = context.scene.claude_blender
        if not state.last_screenshot_path:
            state.status = "No screenshot path available"
            return {"CANCELLED"}
        bpy.ops.wm.path_open(filepath=state.last_screenshot_path)
        state.status = "Opened screenshot"
        return {"FINISHED"}


class CLAUDEBLENDER_OT_refresh_control_center(bpy.types.Operator):
    bl_idname = "claude_blender.refresh_control_center"
    bl_label = "Refresh Control Center"
    bl_description = "Refresh bridge diagnostics, preview manifest, audit status, and visual evidence"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        state = context.scene.claude_blender
        prefs = _prefs(context)
        _refresh_control_center_state(context, state, prefs)
        return {"FINISHED"}


class CLAUDEBLENDER_OT_reload_scripts(bpy.types.Operator):
    bl_idname = "claude_blender.reload_scripts"
    bl_label = "Reload Scripts"
    bl_description = "Reload patched add-on modules from disk; save the current file first"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        operator = getattr(getattr(bpy.ops, "script", None), "reload", None)
        if operator is None or not operator.poll():
            self.report({"WARNING"}, "Reload Scripts is unavailable here; save the file and restart Blender")
            return {"CANCELLED"}
        try:
            return operator()
        except RuntimeError as exc:
            self.report({"WARNING"}, f"Reload failed ({exc}); save the file and restart Blender")
            return {"CANCELLED"}


class CLAUDEBLENDER_OT_copy_control_center(bpy.types.Operator):
    bl_idname = "claude_blender.copy_control_center"
    bl_label = "Copy Control Center"
    bl_description = "Copy bridge diagnostics, preview manifest, audit status, and visual evidence"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        state = context.scene.claude_blender
        prefs = _prefs(context)
        body = _refresh_control_center_state(context, state, prefs)
        context.window_manager.clipboard = body
        state.status = "Copied bridge control center"
        return {"FINISHED"}


class CLAUDEBLENDER_OT_refresh_preview_manifest(bpy.types.Operator):
    bl_idname = "claude_blender.refresh_preview_manifest"
    bl_label = "Refresh Preview Manifest"
    bl_description = "Refresh rollback manifest details for the current live preview transaction"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        state = context.scene.claude_blender
        _refresh_preview_manifest_state(state)
        state.status = state.preview_manifest_status
        return {"FINISHED"}


class CLAUDEBLENDER_OT_copy_preview_manifest(bpy.types.Operator):
    bl_idname = "claude_blender.copy_preview_manifest"
    bl_label = "Copy Preview Manifest"
    bl_description = "Copy rollback manifest details for the current live preview transaction"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        state = context.scene.claude_blender
        body = _refresh_preview_manifest_state(state)
        context.window_manager.clipboard = body
        state.status = "Copied preview manifest"
        return {"FINISHED"}


class CLAUDEBLENDER_OT_refresh_audit_log(bpy.types.Operator):
    bl_idname = "claude_blender.refresh_audit_log"
    bl_label = "Refresh Audit Log"
    bl_description = "Refresh the local MCP/bridge audit log preview"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        state = context.scene.claude_blender
        _refresh_audit_log_state(state)
        state.status = state.audit_log_status
        return {"FINISHED"}


class CLAUDEBLENDER_OT_copy_audit_log(bpy.types.Operator):
    bl_idname = "claude_blender.copy_audit_log"
    bl_label = "Copy Audit Log"
    bl_description = "Copy recent local MCP/bridge audit events"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        state = context.scene.claude_blender
        body = _refresh_audit_log_state(state)
        context.window_manager.clipboard = body
        state.status = "Copied audit log"
        return {"FINISHED"}


class CLAUDEBLENDER_OT_open_audit_log(bpy.types.Operator):
    bl_idname = "claude_blender.open_audit_log"
    bl_label = "Open Audit Log"
    bl_description = "Open the local MCP/bridge audit log file"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        state = context.scene.claude_blender
        info = audit_log.status()
        if not info["exists"]:
            state.audit_log_status = audit_log.status_summary()
            state.status = state.audit_log_status
            return {"CANCELLED"}
        bpy.ops.wm.path_open(filepath=info["path"])
        state.audit_log_status = audit_log.status_summary()
        state.status = "Opened audit log"
        return {"FINISHED"}


class CLAUDEBLENDER_OT_clear_audit_log(bpy.types.Operator):
    bl_idname = "claude_blender.clear_audit_log"
    bl_label = "Clear Audit Log"
    bl_description = "Delete the local MCP/bridge audit log file"
    bl_options = {"REGISTER", "INTERNAL"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        state = context.scene.claude_blender
        result = audit_log.clear()
        state.audit_log_status = result["message"]
        state.status = result["message"]
        _write_text_datablock(audit_log.AUDIT_LOG_TEXT_NAME, audit_log.format_recent(20))
        return {"FINISHED"}


class CLAUDEBLENDER_OT_refresh_visual_evidence(bpy.types.Operator):
    bl_idname = "claude_blender.refresh_visual_evidence"
    bl_label = "Refresh Visual Evidence"
    bl_description = "Refresh latest viewport, playblast, inspection render, thumbnail, and render-job evidence"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        state = context.scene.claude_blender
        prefs = _prefs(context)
        _refresh_visual_evidence_state(context, state, prefs)
        state.status = state.visual_evidence_status
        return {"FINISHED"}


class CLAUDEBLENDER_OT_copy_visual_evidence(bpy.types.Operator):
    bl_idname = "claude_blender.copy_visual_evidence"
    bl_label = "Copy Visual Evidence"
    bl_description = "Copy latest visual evidence resource inventory"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        state = context.scene.claude_blender
        prefs = _prefs(context)
        body = _refresh_visual_evidence_state(context, state, prefs)
        context.window_manager.clipboard = body
        state.status = "Copied visual evidence"
        return {"FINISHED"}


class CLAUDEBLENDER_OT_open_latest_visual_evidence(bpy.types.Operator):
    bl_idname = "claude_blender.open_latest_visual_evidence"
    bl_label = "Open Latest Visual Evidence"
    bl_description = "Open the latest available visual evidence file"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        state = context.scene.claude_blender
        path = state.visual_evidence_latest_path
        if not path:
            prefs = _prefs(context)
            _refresh_visual_evidence_state(context, state, prefs)
            path = state.visual_evidence_latest_path
        if not path:
            state.status = "No visual evidence file available"
            return {"CANCELLED"}
        bpy.ops.wm.path_open(filepath=path)
        state.status = "Opened latest visual evidence"
        return {"FINISHED"}


class CLAUDEBLENDER_OT_check_docs_cache(bpy.types.Operator):
    bl_idname = "claude_blender.check_docs_cache"
    bl_label = "Check"
    bl_description = "Check local Blender Python docs cache status"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        state = context.scene.claude_blender
        prefs = _prefs(context)
        status = docs_index.docs_cache_status(cache_dir=getattr(prefs, "docs_cache_dir", None))
        state.docs_cache_status = _format_docs_status(status)
        state.status = state.docs_cache_status
        return {"FINISHED"}


class CLAUDEBLENDER_OT_build_docs_cache(bpy.types.Operator):
    bl_idname = "claude_blender.build_docs_cache"
    bl_label = "Build Full Docs Cache"
    bl_description = "Download and index the official Blender Python API and Manual docs for this Blender version"
    bl_options = {"INTERNAL"}

    force: bpy.props.BoolProperty(
        name="Force Rebuild",
        default=False,
    )

    def execute(self, context):
        state = context.scene.claude_blender
        if state.docs_cache_building:
            state.status = "Docs cache build already running"
            return {"CANCELLED"}
        prefs = _prefs(context)
        cache_dir = getattr(prefs, "docs_cache_dir", None)
        version = docs_index.blender_docs_version()
        scene_name = context.scene.name
        force = bool(self.force)
        state.docs_cache_building = True
        state.docs_cache_status = f"Docs {version}: building..."
        state.status = state.docs_cache_status
        _ensure_docs_timer()

        def worker():
            try:
                status = docs_index.build_full_docs_cache(
                    cache_dir=cache_dir,
                    version=version,
                    force=force,
                )
                _docs_results.put((scene_name, True, _format_docs_status(status)))
            except Exception as exc:
                _docs_results.put((scene_name, False, f"{type(exc).__name__}: {exc}"))

        threading.Thread(target=worker, name="BlenderAgentBridgeDocsCache", daemon=True).start()
        return {"FINISHED"}


class CLAUDEBLENDER_OT_start_bridge(bpy.types.Operator):
    bl_idname = "claude_blender.start_bridge"
    bl_label = "Start Bridge"
    bl_description = "Start the localhost JSON bridge for external MCP clients"
    bl_options = {"REGISTER"}

    def execute(self, context):
        prefs = _prefs(context)
        result = bridge_server.start_bridge(
            port=getattr(prefs, "bridge_port", bridge_server.DEFAULT_PORT),
            auth_token=getattr(prefs, "bridge_auth_token", ""),
        )
        state = context.scene.claude_blender
        state.bridge_running = bool(result.get("ok"))
        state.bridge_url = str(result.get("url") or "")
        state.bridge_status = str(result.get("message") or "")
        state.status = state.bridge_status
        _refresh_bridge_diagnostics_state(context, state, prefs)
        return {"FINISHED"} if result.get("ok") else {"CANCELLED"}


class CLAUDEBLENDER_OT_stop_bridge(bpy.types.Operator):
    bl_idname = "claude_blender.stop_bridge"
    bl_label = "Stop Bridge"
    bl_description = "Stop the localhost JSON bridge"
    bl_options = {"REGISTER"}

    def execute(self, context):
        result = bridge_server.stop_bridge()
        state = context.scene.claude_blender
        state.bridge_running = False
        state.bridge_url = ""
        state.bridge_status = str(result.get("message") or "Bridge stopped")
        state.status = state.bridge_status
        _refresh_bridge_diagnostics_state(context, state, _prefs(context))
        return {"FINISHED"}


def _copy_mcp_config_to_clipboard(context, *, sketchfab_api_token=""):
    prefs = _prefs(context)
    url = context.scene.claude_blender.bridge_url or f"http://127.0.0.1:{getattr(prefs, 'bridge_port', bridge_server.DEFAULT_PORT)}"
    token = getattr(prefs, "bridge_auth_token", "")
    launch_mode = str(getattr(prefs, "mcp_launch_mode", "BUNDLED") or "BUNDLED").strip().lower()
    if launch_mode == build_info.MCP_RUNTIME_UVX and not build_info.uvx_executable():
        raise RuntimeError("uvx was not found on PATH; install uv or switch MCP Runtime to Bundled")
    config = build_info.mcp_config(
        url,
        token=token,
        sketchfab_api_token=sketchfab_api_token,
        command=build_info.bundled_python_executable(),
        launch_mode=launch_mode,
    )
    context.window_manager.clipboard = json.dumps(config, indent=2)
    state = context.scene.claude_blender
    _refresh_bridge_diagnostics_state(context, state, prefs)
    return state


class CLAUDEBLENDER_OT_copy_mcp_config(bpy.types.Operator):
    bl_idname = "claude_blender.copy_mcp_config"
    bl_label = "Copy MCP Config"
    bl_description = "Copy a JSON MCP server config for external MCP clients"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            state = _copy_mcp_config_to_clipboard(context)
        except RuntimeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        state.status = (
            f"Copied MCP config v{build_info.MCP_CONFIG_VERSION}; fill the empty Sketchfab token if needed"
        )
        return {"FINISHED"}


class CLAUDEBLENDER_OT_copy_mcp_config_with_sketchfab(bpy.types.Operator):
    bl_idname = "claude_blender.copy_mcp_config_with_sketchfab"
    bl_label = "Copy MCP + Sketchfab"
    bl_description = "Paste a Sketchfab API token once and copy an MCP config without saving the token in Blender"
    bl_options = {"INTERNAL"}

    sketchfab_api_token: bpy.props.StringProperty(
        name="Sketchfab API Token",
        description="Copied into the MCP config only; never saved in Blender preferences, blend files, or audit logs",
        subtype="PASSWORD",
        options={"SKIP_SAVE"},
        default="",
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=500)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Poly Haven is ready and does not require an API key.", icon="CHECKMARK")
        layout.label(text="Sketchfab public search is keyless; downloads require a token.")
        layout.separator()
        layout.prop(self, "sketchfab_api_token", text="Sketchfab Token")
        security_box = layout.box()
        security_box.label(text="One-time copy", icon="LOCKED")
        security_box.label(text="The token goes to the clipboard config only.")
        security_box.label(text="It is not stored in Blender preferences, the blend file, or audit logs.")

    def execute(self, context):
        sketchfab_api_token = str(self.sketchfab_api_token or "").strip()
        if not sketchfab_api_token:
            self.report({"ERROR"}, "Paste a Sketchfab API token or use Copy MCP Config without auth")
            return {"CANCELLED"}
        try:
            state = _copy_mcp_config_to_clipboard(
                context,
                sketchfab_api_token=sketchfab_api_token,
            )
        except RuntimeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.sketchfab_api_token = ""
        state.status = (
            f"Copied MCP config v{build_info.MCP_CONFIG_VERSION} with one-time Sketchfab auth; restart the MCP client"
        )
        if not bpy.app.background:
            def draw_confirmation(menu, _context):
                menu.layout.label(text="Poly Haven: Ready (no API key)", icon="CHECKMARK")
                menu.layout.label(text="Sketchfab token included in copied MCP config", icon="CHECKMARK")
                menu.layout.label(text="Replace the client config, then restart or refresh the MCP client.")

            context.window_manager.popup_menu(
                draw_confirmation,
                title="External Assets Ready",
                icon="CHECKMARK",
            )
        return {"FINISHED"}


class CLAUDEBLENDER_OT_set_session_sketchfab_token(bpy.types.Operator):
    bl_idname = "claude_blender.set_session_sketchfab_token"
    bl_label = "Use Sketchfab Token For This Session"
    bl_description = "Keep a masked Sketchfab token in memory until Blender closes or you clear it"
    bl_options = {"INTERNAL"}

    sketchfab_api_token: bpy.props.StringProperty(
        name="Sketchfab API Token",
        description="Memory-only token; never saved in preferences, blend files, manifests, or audit logs",
        subtype="PASSWORD",
        options={"SKIP_SAVE"},
        default="",
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=500)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "sketchfab_api_token", text="Sketchfab Token")
        layout.label(text="Stored only in this Blender process; clear it when testing is complete.", icon="LOCKED")

    def execute(self, context):
        token = str(self.sketchfab_api_token or "").strip()
        if not token:
            self.report({"ERROR"}, "Paste a Sketchfab API token")
            return {"CANCELLED"}
        external_assets.set_session_sketchfab_api_token(token)
        self.sketchfab_api_token = ""
        context.scene.claude_blender.status = "Sketchfab token available for this Blender session only"
        self.report({"INFO"}, "Sketchfab session token set in memory")
        return {"FINISHED"}


class CLAUDEBLENDER_OT_clear_session_sketchfab_token(bpy.types.Operator):
    bl_idname = "claude_blender.clear_session_sketchfab_token"
    bl_label = "Clear Sketchfab Session Token"
    bl_description = "Forget the memory-only Sketchfab token immediately"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        external_assets.clear_session_sketchfab_api_token()
        context.scene.claude_blender.status = "Sketchfab session token cleared"
        return {"FINISHED"}


class CLAUDEBLENDER_PT_sidebar(bpy.types.Panel):
    bl_idname = "CLAUDEBLENDER_PT_sidebar"
    bl_label = "Agent Bridge"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Agent Bridge"

    def draw(self, context):
        layout = self.layout
        state = context.scene.claude_blender

        # This is the entire sidebar contract: connection, active safety state,
        # and decisions that need the user's attention.
        _draw_bridge_summary(layout, state)
        _draw_script_trust_control(layout, context, state)
        _draw_action_center(layout, state)

classes = (
    CLAUDEBLENDER_OT_capture_context,
    CLAUDEBLENDER_OT_commit_preview,
    CLAUDEBLENDER_OT_revert_last_preview_step,
    CLAUDEBLENDER_OT_revert_preview,
    CLAUDEBLENDER_OT_undo_last,
    CLAUDEBLENDER_OT_approve_external_script_trust,
    CLAUDEBLENDER_OT_revoke_external_script_trust,
    CLAUDEBLENDER_OT_restore_last_checkpoint,
    CLAUDEBLENDER_OT_capture_viewport_preview,
    CLAUDEBLENDER_OT_open_last_screenshot,
    CLAUDEBLENDER_OT_refresh_control_center,
    CLAUDEBLENDER_OT_reload_scripts,
    CLAUDEBLENDER_OT_copy_control_center,
    CLAUDEBLENDER_OT_refresh_preview_manifest,
    CLAUDEBLENDER_OT_copy_preview_manifest,
    CLAUDEBLENDER_OT_refresh_audit_log,
    CLAUDEBLENDER_OT_copy_audit_log,
    CLAUDEBLENDER_OT_open_audit_log,
    CLAUDEBLENDER_OT_clear_audit_log,
    CLAUDEBLENDER_OT_refresh_visual_evidence,
    CLAUDEBLENDER_OT_copy_visual_evidence,
    CLAUDEBLENDER_OT_open_latest_visual_evidence,
    CLAUDEBLENDER_OT_check_docs_cache,
    CLAUDEBLENDER_OT_build_docs_cache,
    CLAUDEBLENDER_OT_start_bridge,
    CLAUDEBLENDER_OT_stop_bridge,
    CLAUDEBLENDER_OT_copy_mcp_config,
    CLAUDEBLENDER_OT_copy_mcp_config_with_sketchfab,
    CLAUDEBLENDER_OT_set_session_sketchfab_token,
    CLAUDEBLENDER_OT_clear_session_sketchfab_token,
    CLAUDEBLENDER_PT_sidebar,
)


def register():
    _remove_docs_timer_load_handler()
    bpy.app.handlers.load_post.append(_ensure_docs_timer_after_load)
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    _remove_docs_timer_load_handler()
    try:
        if _docs_timer_is_registered():
            bpy.app.timers.unregister(_process_docs_results)
    except Exception:
        pass
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
