"""Blender background smoke test for binary session-trusted script execution."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import (  # noqa: E402
    agent_tools,
    audit_log,
    bridge_protocol,
    bridge_server,
    build_info,
    preferences,
    script_runner,
    tool_dispatcher,
)


OBJECT_NAME = "Agent Bridge Script Smoke Object"
MESH_NAME = "Agent Bridge Script Smoke Mesh"


def _execute(context, name, args=None):
    return json.loads(tool_dispatcher.execute_tool(context, name, args or {}))


def _cleanup():
    obj = bpy.data.objects.get(OBJECT_NAME)
    if obj is not None:
        bpy.data.objects.remove(obj, do_unlink=True)
    mesh = bpy.data.meshes.get(MESH_NAME)
    if mesh is not None:
        bpy.data.meshes.remove(mesh)


def main():
    checkpoint_dir = tempfile.mkdtemp(prefix="claude-blender-checkpoints-")
    old_audit_path = os.environ.get("CLAUDE_BLENDER_AUDIT_LOG")
    audit_path = os.path.join(checkpoint_dir, "audit.jsonl")
    os.environ["CLAUDE_BLENDER_AUDIT_LOG"] = audit_path
    registered = False
    original_get_preferences = preferences.get_preferences
    smoke_preferences = type(
        "_SmokePreferences",
        (),
        {"checkpoint_dir": checkpoint_dir, "checkpoints_enabled": True},
    )()
    try:
        claude_blender.register()
        registered = True
        preferences.get_preferences = lambda _context: smoke_preferences
        context = bpy.context
        state = context.scene.claude_blender
        _cleanup()

        for removed_name in (
            "approve_pending_script_for_external_run",
            "discard_pending_script",
            "pending_script_source",
            "reject_pending_script",
            "repair_context_text",
            "run_externally_approved_script",
            "run_pending_script",
            "stage_script",
            "validate_external_script_approval",
        ):
            assert not hasattr(script_runner, removed_name), removed_name
        for removed_property in (
            "pending_script",
            "pending_script_blocked",
            "pending_script_text_name",
            "pending_script_external_approval_hash",
        ):
            assert not hasattr(state, removed_property), removed_property

        copied = bpy.ops.claude_blender.copy_mcp_config()
        assert "FINISHED" in copied, copied
        clipboard = context.window_manager.clipboard.strip()
        copied_config = (
            json.loads(clipboard)
            if clipboard
            else build_info.mcp_config(
                f"http://127.0.0.1:{bridge_server.DEFAULT_PORT}",
                command=build_info.bundled_python_executable(),
            )
        )
        server_config = copied_config["mcpServers"]["blender"]
        assert server_config["command"] == build_info.bundled_python_executable(), server_config
        assert server_config["args"][0].endswith("mcp_server.py"), server_config
        assert server_config["env"]["CLAUDE_BLENDER_BRIDGE_VERSION"] == bridge_protocol.BRIDGE_VERSION

        internal_tool_names = {tool["name"] for tool in agent_tools.blender_tool_definitions()}
        assert "run_approved_script" not in internal_tool_names
        removed_approval = _execute(context, "run_approved_script", {"approval_token": "legacy-token"})
        assert not removed_approval["ok"], removed_approval
        assert removed_approval["code"] == "per_script_approval_removed", removed_approval

        advisory = script_runner.analyze_trusted_script(
            "import os\nimport socket\nimport subprocess\nopen('example.txt', 'w').write('ok')"
        )
        assert advisory["ok"] and not advisory["blocked"], advisory
        assert advisory["advisory_findings"], advisory
        assert "static_advisory_unavailable" not in advisory["risk_reasons"], advisory
        invalid = script_runner.analyze_trusted_script("if True print('broken')")
        assert not invalid["ok"] and invalid["blocked"], invalid
        oversized = script_runner.analyze_trusted_script("x" * (script_runner.MAX_SCRIPT_CHARS + 1))
        assert not oversized["ok"] and oversized["blocked"], oversized

        trust_off_direct = script_runner.run_trusted_script(
            context,
            code="scene['trust_off_direct'] = True",
            checkpoint_enabled=False,
        )
        assert not trust_off_direct["ok"], trust_off_direct
        assert trust_off_direct["code"] == "script_trust_required", trust_off_direct
        trust_off_tool = _execute(
            context,
            "draft_script",
            {
                "intent": "Prove trust-off refusal",
                "expected_changes": "Nothing runs",
                "risk_level": "low",
                "code": "scene['trust_off_tool'] = True",
            },
        )
        assert not trust_off_tool["ok"], trust_off_tool
        assert trust_off_tool["code"] == "script_trust_required", trust_off_tool
        assert "trust is off" in trust_off_tool["message"].lower(), trust_off_tool
        assert trust_off_tool["auto_run_reason"] == "external_script_trust_required", trust_off_tool
        assert "trust_off_direct" not in context.scene
        assert "trust_off_tool" not in context.scene
        assert script_runner.TRUSTED_SCRIPT_NAME not in bpy.data.texts

        timed = script_runner.approve_external_script_trust_window(context, ttl_seconds=900)
        assert timed["ok"] and timed["ttl_seconds"] == 900, timed
        timed_snapshot = script_runner.external_script_trust_snapshot(context, state=state)
        assert timed_snapshot["active"] and 1 <= timed_snapshot["seconds_remaining"] <= 900, timed_snapshot
        script_runner._runtime_external_trust_expires_at = time.time() - 1
        assert not script_runner.external_script_trust_active(context, state=state)
        assert script_runner.expire_external_script_trust_if_needed(context, state=state)
        assert state.external_script_trust_status == script_runner.EXTERNAL_TRUST_EXPIRED_STATUS

        trusted = script_runner.approve_external_script_trust_window(context, session=True)
        assert trusted["ok"] and trusted["session"], trusted
        session_snapshot = script_runner.external_script_trust_snapshot(context, state=state)
        assert session_snapshot["active"] and session_snapshot["session"], session_snapshot
        bridge_status = bridge_server._scene_status()
        assert bridge_status["external_script_trust"] is True, bridge_status
        assert "pending_script" not in bridge_status, bridge_status

        first_checkpoint = script_runner.create_checkpoint(context, checkpoint_dir=checkpoint_dir)
        second_checkpoint = script_runner.create_checkpoint(context, checkpoint_dir=checkpoint_dir)
        assert first_checkpoint["ok"] and second_checkpoint["ok"], (first_checkpoint, second_checkpoint)
        assert first_checkpoint["path"] != second_checkpoint["path"], (first_checkpoint, second_checkpoint)
        assert first_checkpoint["restorable"] and second_checkpoint["restorable"]
        assert os.path.isfile(first_checkpoint["path"]) and os.path.isfile(second_checkpoint["path"])

        safe_code = f"""
import bpy

mesh = bpy.data.meshes.new("{MESH_NAME}")
mesh.from_pydata(
    [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
    [],
    [(0, 1, 2)],
)
mesh.update()
obj = bpy.data.objects.new("{OBJECT_NAME}", mesh)
scene.collection.objects.link(obj)
obj.location = (1.0, 2.0, 3.0)
print("created", obj.name)
"""
        run = _execute(
            context,
            "draft_script",
            {
                "intent": "Create a smoke-test mesh",
                "expected_changes": f"Creates {OBJECT_NAME}",
                "risk_level": "low",
                "target_objects": [OBJECT_NAME],
                "code": safe_code,
            },
        )
        assert run["ok"] and run["auto_ran"], run
        assert run["authorization_model"] == "blender_run_script_equivalent", run
        assert run["run_result"]["checkpoint"]["ok"], run
        assert run["run_result"]["checkpoint"]["path"] not in {
            first_checkpoint["path"],
            second_checkpoint["path"],
        }, run
        assert OBJECT_NAME in bpy.data.objects
        assert tuple(round(value, 4) for value in bpy.data.objects[OBJECT_NAME].location) == (1.0, 2.0, 3.0)
        assert script_runner.TRUSTED_SCRIPT_NAME in bpy.data.texts
        assert script_runner.TRUSTED_SCRIPT_METADATA_NAME in bpy.data.texts
        assert script_runner.SCRIPT_LOG_NAME in bpy.data.texts

        failure = _execute(
            context,
            "draft_script",
            {
                "intent": "Exercise trusted runtime failure",
                "expected_changes": "The failure is logged",
                "risk_level": "low",
                "code": "raise RuntimeError('intentional trusted failure')",
            },
        )
        assert not failure["ok"], failure
        assert failure["run_result"]["auto_run_attempted"], failure
        assert not failure["run_result"]["auto_ran"], failure
        assert "RuntimeError" in state.last_script_error_summary

        marker_path = os.path.join(checkpoint_dir, "trusted-filesystem-marker.txt")
        filesystem_run = _execute(
            context,
            "draft_script",
            {
                "intent": "Exercise trusted OS permissions",
                "expected_changes": "Writes one temporary marker",
                "risk_level": "high",
                "code": (
                    "import os\n"
                    "import socket\n"
                    "import subprocess\n"
                    f"open({marker_path!r}, 'w').write(os.path.basename({marker_path!r}))\n"
                ),
            },
        )
        assert filesystem_run["ok"] and filesystem_run["auto_ran"], filesystem_run
        assert os.path.isfile(marker_path), filesystem_run

        privileged_alias = _execute(
            context,
            "draft_privileged_script",
            {
                "script_kind": "project_file",
                "intent": "Exercise the legacy compatibility alias",
                "expected_changes": "Sets one scene marker",
                "approval_summary": "Legacy fields are advisory only",
                "declared_paths": [],
                "declared_urls": [],
                "destructive_actions": [],
                "code": "scene['legacy_privileged_alias'] = 'ok'",
            },
        )
        assert privileged_alias["ok"] and privileged_alias["auto_ran"], privileged_alias
        assert privileged_alias["compatibility_alias"] == "draft_script", privileged_alias
        assert context.scene["legacy_privileged_alias"] == "ok"

        bake_semantics = _execute(
            context,
            "draft_script",
            {
                "intent": "Exercise persistent bake syntax under trust",
                "expected_changes": "Sets one marker without performing a real bake",
                "risk_level": "high",
                "code": (
                    "import bpy\n"
                    "if False:\n"
                    "    bpy.ops.ptcache.bake_all(bake=True)\n"
                    "scene['trusted_bake_semantics'] = 'allowed'\n"
                ),
            },
        )
        assert bake_semantics["ok"] and bake_semantics["auto_ran"], bake_semantics
        assert bake_semantics["staged"]["analysis"]["advisory_findings"], bake_semantics
        assert context.scene["trusted_bake_semantics"] == "allowed"

        restored = script_runner.restore_checkpoint(context, run["run_result"]["checkpoint"]["path"])
        assert restored["ok"], restored
        context = bpy.context
        state = context.scene.claude_blender
        assert OBJECT_NAME not in bpy.data.objects, restored
        assert restored["checkpoint"]["restorable"], restored

        non_checkpoint_path = os.path.join(checkpoint_dir, "manual.blend")
        with open(non_checkpoint_path, "wb") as handle:
            handle.write(b"not really a blend")
        refused_restore = script_runner.restore_checkpoint(context, non_checkpoint_path)
        assert not refused_restore["ok"], refused_restore
        assert not refused_restore["checkpoint"]["restorable"], refused_restore

        assert script_runner.revoke_external_script_trust_window(context)["ok"]
        revoked_direct = script_runner.run_trusted_script(
            context,
            code="scene['revoked_direct'] = True",
            checkpoint_enabled=False,
        )
        assert not revoked_direct["ok"] and revoked_direct["code"] == "script_trust_required", revoked_direct
        assert "revoked_direct" not in context.scene

        with open(audit_path, "r", encoding="utf-8") as handle:
            trust_events = [
                json.loads(line)
                for line in handle
                if line.strip() and '"event":"external_script_trust"' in line
            ]
        trust_actions = {event.get("action") for event in trust_events}
        assert {"grant", "expire", "revoke"}.issubset(trust_actions), trust_events

        _cleanup()
        print("smoke_script_runner: ok")
    finally:
        preferences.get_preferences = original_get_preferences
        if registered:
            claude_blender.unregister()
        if old_audit_path is None:
            os.environ.pop("CLAUDE_BLENDER_AUDIT_LOG", None)
        else:
            os.environ["CLAUDE_BLENDER_AUDIT_LOG"] = old_audit_path
        shutil.rmtree(checkpoint_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
