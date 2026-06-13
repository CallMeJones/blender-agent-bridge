"""Blender background smoke test for animation workflow helper tools."""

from __future__ import annotations

import json
import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import anthropic_client, bridge_protocol, context_bundle, live_preview, tool_dispatcher  # noqa: E402


ANIMATION_TOOLS = {
    "animate_object_bounce",
    "animate_material_property",
    "create_follow_path_animation",
}


def _execute(context, name, args=None):
    result = json.loads(tool_dispatcher.execute_tool(context, name, args or {}))
    assert result.get("ok"), f"{name} failed: {result}"
    return result


def _select_object(context, obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _snapshot(scene, cube, camera):
    return {
        "objects": set(bpy.data.objects.keys()),
        "curves": set(bpy.data.curves.keys()),
        "materials": set(bpy.data.materials.keys()),
        "actions": set(bpy.data.actions.keys()),
        "cube_location": tuple(round(float(value), 6) for value in cube.location),
        "cube_materials": [slot.material.name if slot.material else None for slot in cube.material_slots],
        "camera_constraints": [constraint.name for constraint in camera.constraints],
        "camera_action": camera.animation_data.action.name if camera.animation_data and camera.animation_data.action else None,
        "scene_camera": scene.camera.name if scene.camera else None,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "frame_current": scene.frame_current,
    }


def _action_keyframes(action):
    frames = []
    for fcurve in live_preview._iter_action_fcurves(action):
        frames.extend(round(point.co.x, 4) for point in fcurve.keyframe_points)
    return sorted(set(frames))


def main():
    claude_blender.register()
    context = bpy.context
    scene = context.scene
    cube = bpy.data.objects["Cube"]
    camera = bpy.data.objects["Camera"]
    _select_object(context, cube)
    initial = _snapshot(scene, cube, camera)

    try:
        bundle = context_bundle.build_context_bundle(context)
        assert ANIMATION_TOOLS.issubset(set(bundle["available_tools"]))
        tool_names = {tool["name"] for tool in anthropic_client.blender_tool_definitions()}
        assert ANIMATION_TOOLS.issubset(tool_names)
        contract_names = set(bridge_protocol.TOOL_CONTRACTS)
        assert ANIMATION_TOOLS.issubset(contract_names)

        bounce = _execute(
            context,
            "animate_object_bounce",
            {
                "object_name": "Cube",
                "frame_start": 1,
                "frame_end": 48,
                "axis": "Z",
                "distance": 2.5,
                "cycles": 2,
            },
        )
        cube_action = bpy.data.actions[bounce["action"]]
        assert _action_keyframes(cube_action) == [float(frame) for frame in bounce["frames"]]

        material_result = _execute(
            context,
            "animate_material_property",
            {
                "object_name": "Cube",
                "property_name": "emission_strength",
                "frame_start": 1,
                "frame_end": 48,
                "value_start": 0.0,
                "value_end": 3.0,
            },
        )
        material = bpy.data.materials[material_result["material"]]
        assert material.node_tree.animation_data and material.node_tree.animation_data.action
        assert material.node_tree.animation_data.action.name == material_result["action"]

        follow = _execute(
            context,
            "create_follow_path_animation",
            {
                "object_name": "Camera",
                "path_name": "Claude Camera Motion Path",
                "path_points": [[-4.0, -4.0, 3.0], [0.0, -6.0, 4.0], [4.0, -4.0, 3.0]],
                "frame_start": 1,
                "frame_end": 48,
                "constraint_name": "Claude Camera Follow Path",
            },
        )
        assert follow["path"] in bpy.data.objects
        assert camera.constraints.get("Claude Camera Follow Path")
        assert camera.animation_data and camera.animation_data.action

        state = scene.claude_blender
        assert state.pending_preview
        assert state.pending_preview_summary

        reverted = _execute(context, "revert_preview", {})
        assert not reverted.get("rollback_warnings"), reverted
        assert not state.pending_preview
        final = _snapshot(scene, cube, camera)
        assert final == initial, {"initial": initial, "final": final, "reverted": reverted}

        print("smoke_animation_helpers: ok")
    finally:
        claude_blender.unregister()


if __name__ == "__main__":
    main()
