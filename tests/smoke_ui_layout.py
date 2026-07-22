"""Blender background smoke test for the compact sidebar layout."""

from __future__ import annotations

import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import bridge_server, ui  # noqa: E402


class _FakeOperator:
    pass


class _FakeLayout:
    def __init__(self):
        self.alert = False
        self.enabled = True
        self.labels = []
        self.operators = []

    def row(self, **_kwargs):
        return self

    def box(self):
        return self

    def label(self, *, text="", **_kwargs):
        self.labels.append(text)

    def operator(self, operator_id, **_kwargs):
        self.operators.append(operator_id)
        return _FakeOperator()

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

        assert ui.CLAUDEBLENDER_PT_advanced.bl_parent_id == ui.CLAUDEBLENDER_PT_sidebar.bl_idname
        assert "DEFAULT_CLOSED" in ui.CLAUDEBLENDER_PT_advanced.bl_options

        # The exact operator sets are a product boundary: adding setup or
        # diagnostics to the default panel must require an intentional test change.
        for running, expected_status, expected_operators in (
            (False, "Bridge is offline", {"claude_blender.start_bridge", "claude_blender.copy_mcp_config"}),
            (True, "Bridge is ready", {"claude_blender.stop_bridge", "claude_blender.copy_mcp_config"}),
        ):
            bridge_server.is_running = lambda running=running: running
            layout = _FakeLayout()
            panel = type("_Sidebar", (), {"layout": layout})()
            ui.CLAUDEBLENDER_PT_sidebar.draw(panel, context)
            assert layout.labels == [expected_status], layout.labels
            assert set(layout.operators) == expected_operators, layout.operators

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
        assert set(preview_layout.operators) == {
            "claude_blender.start_bridge",
            "claude_blender.copy_mcp_config",
            "claude_blender.commit_preview",
            "claude_blender.revert_last_preview_step",
            "claude_blender.revert_preview",
        }, preview_layout.operators
        state.pending_preview = False

        advanced = _FakeLayout()
        ui._draw_advanced_controls(advanced, context, state)
        assert "Client Setup" in advanced.labels, advanced.labels
        assert "External Assets" in advanced.labels, advanced.labels
        assert "Script Security" in advanced.labels, advanced.labels
        assert "Diagnostics" in advanced.labels, advanced.labels
        assert "claude_blender.copy_mcp_config_with_sketchfab" in advanced.operators, advanced.operators
        assert "claude_blender.refresh_control_center" in advanced.operators, advanced.operators

        print("smoke_ui_layout: ok")
    finally:
        bridge_server.is_running = original_is_running
        claude_blender.unregister()


if __name__ == "__main__":
    main()
