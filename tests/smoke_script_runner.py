"""Blender background smoke test for approval-gated script execution."""

from __future__ import annotations

import os
import json
import shutil
import sys
import tempfile

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import script_runner, tool_dispatcher  # noqa: E402


OBJECT_NAME = "Claude Script Smoke Object"
MESH_NAME = "Claude Script Smoke Mesh"


def _cleanup():
    obj = bpy.data.objects.get(OBJECT_NAME)
    if obj is not None:
        bpy.data.objects.remove(obj, do_unlink=True)
    mesh = bpy.data.meshes.get(MESH_NAME)
    if mesh is not None:
        bpy.data.meshes.remove(mesh)


def main():
    checkpoint_dir = tempfile.mkdtemp(prefix="claude-blender-checkpoints-")
    claude_blender.register()
    try:
        context = bpy.context
        state = context.scene.claude_blender
        _cleanup()

        blocked = script_runner.stage_script(
            context,
            intent="Try a blocked filesystem operation",
            expected_changes="No scene changes should occur",
            risk_level="high",
            target_objects=[],
            code="import os\nos.remove('example.blend')",
        )
        assert blocked["ok"], blocked
        assert blocked["analysis"]["blocked"], blocked
        assert state.pending_script
        assert state.pending_script_blocked
        assert state.pending_script_issues

        blocked_run = script_runner.run_pending_script(context, checkpoint_enabled=False)
        assert not blocked_run["ok"], blocked_run
        assert state.pending_script_blocked

        rejected = script_runner.reject_pending_script(context)
        assert rejected["ok"], rejected
        assert not state.pending_script

        missing = script_runner.stage_script(
            context,
            intent="Missing code",
            expected_changes="No changes",
            risk_level="low",
            target_objects=[],
            code="",
        )
        assert not missing["ok"], missing
        assert missing["missing_code"], missing
        assert "code field" in missing["message"], missing

        failing = script_runner.stage_script(
            context,
            intent="Trigger a runtime failure",
            expected_changes="No scene changes should remain",
            risk_level="low",
            target_objects=[],
            code="raise RuntimeError('intentional smoke failure')",
        )
        assert failing["analysis"]["ok"], failing
        failed_run = script_runner.run_pending_script(context, checkpoint_enabled=False)
        assert not failed_run["ok"], failed_run
        assert state.pending_script
        assert state.pending_script_status == "Script failed"
        assert "RuntimeError" in state.last_script_error_summary
        repair_context = script_runner.repair_context_text(context)
        assert "intentional smoke failure" in repair_context
        assert script_runner.SCRIPT_FAILURE_PROMPT_NAME in bpy.data.texts

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
        staged = script_runner.stage_script(
            context,
            intent="Create a simple smoke-test mesh object",
            expected_changes="A triangle mesh object appears at location 1, 2, 3",
            risk_level="low",
            target_objects=[OBJECT_NAME],
            code=safe_code,
        )
        assert staged["ok"], staged
        assert staged["analysis"]["ok"], staged
        assert state.pending_script
        assert not state.pending_script_blocked

        rejected = script_runner.reject_pending_script(context)
        assert rejected["ok"], rejected
        alternate_field = json.loads(
            tool_dispatcher.execute_tool(
                context,
                "draft_script",
                {
                    "intent": "Stage from alternate field",
                    "expected_changes": "A harmless print script is staged",
                    "risk_level": "low",
                    "script": "print('alternate field staged')",
                },
            )
        )
        assert alternate_field["ok"], alternate_field
        assert state.pending_script
        assert not state.pending_script_blocked

        rejected = script_runner.reject_pending_script(context)
        assert rejected["ok"], rejected
        staged = script_runner.stage_script(
            context,
            intent="Create a simple smoke-test mesh object",
            expected_changes="A triangle mesh object appears at location 1, 2, 3",
            risk_level="low",
            target_objects=[OBJECT_NAME],
            code=safe_code,
        )
        assert staged["ok"], staged
        assert staged["analysis"]["ok"], staged
        assert state.pending_script
        assert not state.pending_script_blocked

        result = script_runner.run_pending_script(
            context,
            checkpoint_enabled=True,
            checkpoint_dir=checkpoint_dir,
        )
        assert result["ok"], result
        assert result["checkpoint"]["ok"], result
        assert os.path.exists(result["checkpoint"]["path"]), result
        assert state.last_checkpoint_path == result["checkpoint"]["path"]
        assert OBJECT_NAME in bpy.data.objects
        assert tuple(round(value, 4) for value in bpy.data.objects[OBJECT_NAME].location) == (1.0, 2.0, 3.0)
        assert script_runner.SCRIPT_LOG_NAME in bpy.data.texts
        assert not state.pending_script

        _cleanup()
        claude_blender.unregister()
        print("smoke_script_runner: ok")
    finally:
        shutil.rmtree(checkpoint_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
