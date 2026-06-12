"""Smoke tests for the Claude tool loop display/finalization behavior."""

from __future__ import annotations

import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import agent_loop, anthropic_client  # noqa: E402


def main():
    claude_blender.register()

    original_create = anthropic_client.create_message_raw
    original_execute = agent_loop._execute_tool_sync
    original_loops = anthropic_client.MAX_TOOL_LOOPS
    calls = {"count": 0}
    max_tokens_seen = []

    def fake_create_message_raw(*, messages, model, tools=None, max_tokens=1024):
        calls["count"] += 1
        max_tokens_seen.append(max_tokens)
        if tools is None:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "I built part of the scene and the live preview is still pending.",
                    }
                ]
            }
        return {
            "content": [
                {
                    "type": "tool_use",
                    "id": f"tool-{calls['count']}",
                    "name": "inspect_scene",
                    "input": {},
                }
            ]
        }

    def fake_execute_tool_sync(scene_name, tool_block):
        return '{"ok": true, "message": "simulated tool result"}'

    try:
        anthropic_client.create_message_raw = fake_create_message_raw
        agent_loop._execute_tool_sync = fake_execute_tool_sync
        anthropic_client.MAX_TOOL_LOOPS = 2
        text = agent_loop._run_tool_loop(
            scene_name=bpy.context.scene.name,
            prompt="build a complex scene",
            context_bundle={},
            model="fake-model",
        )
        assert "live preview is still pending" in text, text
        assert "Tool-call budget reached after 2 Blender tool call(s)" in text, text
        assert not text.lstrip().startswith("{"), text
        assert anthropic_client.TOOL_LOOP_MAX_TOKENS in max_tokens_seen, max_tokens_seen

        fallback = anthropic_client.extract_text(
            {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool-fallback",
                        "name": "create_primitive",
                        "input": {},
                    }
                ]
            }
        )
        assert "requested Blender tool calls" in fallback, fallback
    finally:
        anthropic_client.create_message_raw = original_create
        agent_loop._execute_tool_sync = original_execute
        anthropic_client.MAX_TOOL_LOOPS = original_loops
        claude_blender.unregister()

    print("smoke_agent_loop: ok")


if __name__ == "__main__":
    main()
