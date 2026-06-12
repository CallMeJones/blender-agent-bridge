"""Smoke tests for chat-style prompt continuation helpers."""

from __future__ import annotations

import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import agent_loop, chat_history, ui  # noqa: E402


class _FakePrefs:
    model = "fake-model"
    capture_cache_dir = ""
    max_screenshot_bytes = 0
    execution_mode = "live_helpers"


def main():
    claude_blender.register()
    try:
        state = bpy.context.scene.claude_blender
        state.last_response = "I need to stage a script, but code was missing."
        state.pending_script = False
        continued = ui._resolve_prompt("ok", state)
        assert "Continue the current Blender task" in continued, continued
        assert "draft_script" in continued, continued
        assert "paste code manually" in continued, continued

        direct = ui._resolve_prompt("Create a blue sphere", state)
        assert direct == "Create a blue sphere", direct

        state.pending_script = True
        acknowledged = ui._resolve_prompt("continue", state)
        assert "Run Approved Script" in acknowledged, acknowledged
        assert "Do not execute it yourself" in acknowledged, acknowledged

        chat_history.clear_history(bpy.context.scene)
        original_prefs = ui._prefs
        original_submit = ui.agent_loop.submit_prompt
        captured = {}

        def fake_prefs(context):
            return _FakePrefs()

        def fake_submit(**kwargs):
            captured.update(kwargs)

        ui._prefs = fake_prefs
        ui.agent_loop.submit_prompt = fake_submit
        try:
            state.pending_script = False
            state.prompt = "Create a blue sphere"
            result = bpy.ops.claude_blender.send_prompt()
            assert {"FINISHED"} == result, result
            assert state.prompt == "", state.prompt
            assert captured["prompt"] == "Create a blue sphere", captured
            messages = chat_history.recent_messages(limit=4)
            assert messages[-1]["role"] == "user", messages
            assert "Create a blue sphere" in messages[-1]["content"], messages
        finally:
            ui._prefs = original_prefs
            ui.agent_loop.submit_prompt = original_submit

        agent_loop._apply_result(
            bpy.context.scene.name,
            True,
            "Created a blue sphere as a pending live preview.",
            prompt="Create a blue sphere",
            context_summary="4 objects, 1 selected",
        )
        messages = chat_history.recent_messages(limit=4)
        assert messages[-1]["role"] == "assistant", messages
        assert "blue sphere" in messages[-1]["content"], messages

        copied = bpy.ops.claude_blender.copy_chat_history()
        assert {"FINISHED"} == copied, copied
        assert "blue sphere" in chat_history.chat_text()

        print("smoke_chat_interface: ok")
    finally:
        claude_blender.unregister()


if __name__ == "__main__":
    main()
