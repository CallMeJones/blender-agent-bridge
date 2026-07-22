"""Blender background smoke test for the compact sidebar layout."""

from __future__ import annotations

import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import bridge_server, live_preview, preferences, script_runner, ui  # noqa: E402


class _FakeOperator:
    pass


class _FakeLayout:
    def __init__(self, *, shared=None, enabled=True):
        self.alert = False
        self.enabled = enabled
        shared = shared or {
            "labels": [],
            "operators": [],
            "operator_enabled": [],
            "properties": [],
        }
        self._shared = shared
        self.labels = shared["labels"]
        self.operators = shared["operators"]
        self.operator_enabled = shared["operator_enabled"]
        self.properties = shared["properties"]

    def row(self, **_kwargs):
        return _FakeLayout(shared=self._shared, enabled=self.enabled)

    def box(self):
        return _FakeLayout(shared=self._shared, enabled=self.enabled)

    def label(self, *, text="", **_kwargs):
        self.labels.append(text)

    def operator(self, operator_id, **_kwargs):
        self.operators.append(operator_id)
        self.operator_enabled.append((operator_id, self.enabled))
        return _FakeOperator()

    def prop(self, _owner, property_name, **_kwargs):
        self.properties.append(property_name)

    def separator(self):
        return None


def main():
    claude_blender.register()
    original_is_running = bridge_server.is_running
    try:
        context = bpy.context
        state = context.scene.claude_blender
        state.bridge_source_status = ""
        state.pending_script = False
        state.pending_preview = False
        state.last_script_error_summary = ""
        state.last_checkpoint_path = ""
        state.last_checkpoint_status = "No script checkpoint yet"
        script_runner.revoke_external_script_trust_window(context)

        panels = [cls for cls in ui.classes if issubclass(cls, bpy.types.Panel)]
        assert panels == [ui.CLAUDEBLENDER_PT_sidebar], panels
        assert not hasattr(ui, "CLAUDEBLENDER_PT_advanced")
        for removed_operator in (
            "CLAUDEBLENDER_OT_run_approved_script",
            "CLAUDEBLENDER_OT_approve_external_script_run",
            "CLAUDEBLENDER_OT_reject_script",
        ):
            assert not hasattr(ui, removed_operator), removed_operator
        assert not hasattr(ui, "_draw_pending_script_review")
        globally_discoverable = {
            ui.CLAUDEBLENDER_OT_commit_preview,
            ui.CLAUDEBLENDER_OT_revert_preview,
            ui.CLAUDEBLENDER_OT_revert_last_preview_step,
            ui.CLAUDEBLENDER_OT_revoke_external_script_trust,
            ui.CLAUDEBLENDER_OT_start_bridge,
            ui.CLAUDEBLENDER_OT_stop_bridge,
            ui.CLAUDEBLENDER_OT_copy_mcp_config,
        }
        for cls in (candidate for candidate in ui.classes if issubclass(candidate, bpy.types.Operator)):
            options = getattr(cls, "bl_options", set())
            if cls in globally_discoverable:
                assert "INTERNAL" not in options, cls
            else:
                assert "INTERNAL" in options, cls
        for removed_renderer in (
            "_draw_advanced_controls",
            "_draw_preview_manifest_section",
            "_draw_audit_section",
            "_draw_visual_evidence_section",
            "_draw_status_section",
        ):
            assert not hasattr(ui, removed_renderer), removed_renderer

        # The exact operator sets are a product boundary: adding setup or
        # diagnostics to the default panel must require an intentional test change.
        for running, expected_status, expected_operators in (
            (
                False,
                "Bridge is offline",
                [
                    "claude_blender.start_bridge",
                    "claude_blender.copy_mcp_config",
                    "claude_blender.approve_external_script_trust",
                ],
            ),
            (
                True,
                "Bridge is ready",
                [
                    "claude_blender.stop_bridge",
                    "claude_blender.copy_mcp_config",
                    "claude_blender.approve_external_script_trust",
                ],
            ),
        ):
            bridge_server.is_running = lambda running=running: running
            layout = _FakeLayout()
            panel = type("_Sidebar", (), {"layout": layout})()
            ui.CLAUDEBLENDER_PT_sidebar.draw(panel, context)
            assert layout.labels == [expected_status], layout.labels
            assert layout.operators == expected_operators, layout.operators

        ready_layout = _FakeLayout()
        ready_panel = type("_Sidebar", (), {"layout": ready_layout})()
        ui.CLAUDEBLENDER_PT_sidebar.draw(ready_panel, context)
        trust_operator = ready_layout.operators.index("claude_blender.approve_external_script_trust")
        assert ready_layout.operator_enabled[trust_operator] == (
            "claude_blender.approve_external_script_trust",
            True,
        )

        trusted = script_runner.approve_external_script_trust_window(context, session=True)
        assert trusted["ok"] and trusted["session"], trusted
        bridge_server.is_running = lambda: False
        trusted_layout = _FakeLayout()
        trusted_panel = type("_Sidebar", (), {"layout": trusted_layout})()
        ui.CLAUDEBLENDER_PT_sidebar.draw(trusted_panel, context)
        assert trusted_layout.labels == ["Bridge is offline", "Script trust active"], trusted_layout.labels
        assert trusted_layout.operators == [
            "claude_blender.start_bridge",
            "claude_blender.copy_mcp_config",
            "claude_blender.revoke_external_script_trust",
        ], trusted_layout.operators
        assert script_runner.revoke_external_script_trust_window(context)["ok"]

        state.last_script_error_summary = "Old script failure"
        state.last_checkpoint_status = "Checkpoint disabled"
        history_layout = _FakeLayout()
        history_panel = type("_Sidebar", (), {"layout": history_layout})()
        ui.CLAUDEBLENDER_PT_sidebar.draw(history_panel, context)
        assert history_layout.labels == ["Bridge is offline"], history_layout.labels
        assert history_layout.operators == [
            "claude_blender.start_bridge",
            "claude_blender.copy_mcp_config",
            "claude_blender.approve_external_script_trust",
        ], history_layout.operators

        state.last_script_error_summary = ""
        state.last_checkpoint_status = "No script checkpoint yet"

        # Even stale state created through an old/internal staging API must not
        # resurrect the removed per-script approval controls.
        staged = script_runner.stage_script(
            context,
            code="value = 1",
            intent="Create a test value",
            expected_changes="No scene changes",
            risk_level="low",
        )
        assert staged["ok"], staged
        script_layout = _FakeLayout()
        script_panel = type("_Sidebar", (), {"layout": script_layout})()
        ui.CLAUDEBLENDER_PT_sidebar.draw(script_panel, context)
        assert script_layout.labels == ["Bridge is offline"], script_layout.labels
        assert script_layout.operators == [
            "claude_blender.start_bridge",
            "claude_blender.copy_mcp_config",
            "claude_blender.approve_external_script_trust",
        ], script_layout.operators
        assert script_runner.reject_pending_script(context)["ok"]

        blocked = script_runner.stage_script(
            context,
            code="import subprocess",
            intent="Blocked test script",
            risk_level="high",
        )
        assert blocked["ok"] and blocked["analysis"]["blocked"], blocked
        blocked_layout = _FakeLayout()
        blocked_panel = type("_Sidebar", (), {"layout": blocked_layout})()
        ui.CLAUDEBLENDER_PT_sidebar.draw(blocked_panel, context)
        assert blocked_layout.labels == ["Bridge is offline"], blocked_layout.labels
        assert blocked_layout.operators == [
            "claude_blender.start_bridge",
            "claude_blender.copy_mcp_config",
            "claude_blender.approve_external_script_trust",
        ], blocked_layout.operators
        assert script_runner.reject_pending_script(context)["ok"]

        bridge_server.is_running = lambda: False
        state.pending_preview = True
        state.pending_preview_label = "Preview changes"
        state.pending_preview_summary = ""
        state.pending_preview_warnings = ""
        preview_layout = _FakeLayout()
        preview_panel = type("_Sidebar", (), {"layout": preview_layout})()
        ui.CLAUDEBLENDER_PT_sidebar.draw(preview_panel, context)
        assert preview_layout.labels == [
            "Bridge is offline",
            "Pending",
            "Live Preview:",
            "Preview changes",
        ], preview_layout.labels
        assert preview_layout.operators == [
            "claude_blender.start_bridge",
            "claude_blender.copy_mcp_config",
            "claude_blender.approve_external_script_trust",
            "claude_blender.commit_preview",
            "claude_blender.revert_preview",
        ], preview_layout.operators
        state.pending_preview = False

        transaction = live_preview.begin("Imported asset", context)
        transaction["applied_steps"].append(
            {
                "type": "import_external_asset",
                "created_data": [{"kind": "object", "name": "Synthetic Imported Object"}],
            }
        )
        state.pending_preview = True
        state.pending_preview_label = "Imported asset"
        imported_layout = _FakeLayout()
        imported_panel = type("_Sidebar", (), {"layout": imported_layout})()
        ui.CLAUDEBLENDER_PT_sidebar.draw(imported_panel, context)
        assert "claude_blender.revert_last_preview_step" in imported_layout.operators, imported_layout.operators
        transaction["status"] = "reverted"
        state.pending_preview = False

        cube = bpy.data.objects["Cube"]
        start_location = tuple(cube.location)
        moved = live_preview.apply_location_delta(context, (1, 0, 0), label="UI revert smoke")
        assert moved["ok"] and state.pending_preview, moved
        assert "FINISHED" in bpy.ops.claude_blender.revert_preview()
        assert tuple(cube.location) == start_location
        assert not state.pending_preview

        prefs_layout = _FakeLayout()
        prefs_panel = type("_Preferences", (), {"layout": prefs_layout})()
        preferences.CLAUDEBLENDER_AP_preferences.draw(prefs_panel, context)
        assert prefs_layout.labels == ["Safety", "Connection"], prefs_layout.labels
        assert prefs_layout.properties == [
            "execution_mode",
            "checkpoints_enabled",
            "autosave_enabled",
            "bridge_port",
            "bridge_auth_token",
            "mcp_launch_mode",
        ], prefs_layout.properties

        print("smoke_ui_layout: ok")
    finally:
        bridge_server.is_running = original_is_running
        claude_blender.unregister()


if __name__ == "__main__":
    main()
