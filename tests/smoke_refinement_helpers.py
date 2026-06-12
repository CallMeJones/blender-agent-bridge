"""Blender background smoke test for model refinement helpers."""

from __future__ import annotations

import json
import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import anthropic_client, context_bundle, tool_dispatcher  # noqa: E402


REFINEMENT_TOOLS = {
    "shade_smooth_selected",
    "add_bevel_and_subsurf",
    "create_wheel_assembly",
    "add_panel_seams",
    "add_window_materials",
    "apply_vehicle_refinement_template",
}


def _execute(context, name, args=None):
    result = json.loads(tool_dispatcher.execute_tool(context, name, args or {}))
    assert result.get("ok"), f"{name} failed: {result}"
    return result


def _select_object(context, obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _snapshot(cube):
    return {
        "objects": set(bpy.data.objects.keys()),
        "meshes": set(bpy.data.meshes.keys()),
        "curves": set(bpy.data.curves.keys()),
        "materials": set(bpy.data.materials.keys()),
        "actions": set(bpy.data.actions.keys()),
        "cube_modifiers": [modifier.name for modifier in cube.modifiers],
        "cube_smooth": [bool(poly.use_smooth) for poly in cube.data.polygons],
    }


def main():
    claude_blender.register()
    context = bpy.context
    cube = bpy.data.objects["Cube"]
    _select_object(context, cube)
    initial = _snapshot(cube)
    try:
        bundle = context_bundle.build_context_bundle(context)
        assert REFINEMENT_TOOLS.issubset(set(bundle["available_tools"]))
        full_names = {tool["name"] for tool in anthropic_client.blender_tool_definitions()}
        assert REFINEMENT_TOOLS.issubset(full_names)

        _execute(context, "shade_smooth_selected", {"add_weighted_normals": True})
        assert all(poly.use_smooth for poly in cube.data.polygons)
        assert cube.modifiers.get("Claude Weighted Normals")

        _execute(context, "add_bevel_and_subsurf", {"bevel_width": 0.05, "bevel_segments": 3, "subsurf_levels": 1})
        assert cube.modifiers.get("Claude Detail Bevel")
        assert cube.modifiers.get("Claude Detail Subdivision")

        wheel = _execute(context, "create_wheel_assembly", {"name": "Claude Test Wheel", "location": [2.2, -1.2, -0.6], "radius": 0.35})
        assert len(wheel["objects"]) == 2

        seams = _execute(context, "add_panel_seams", {"target_name": "Cube"})
        assert seams["objects"]

        glass = _execute(context, "add_window_materials", {"target_name": "Cube", "create_panels": True})
        assert glass["created_objects"]

        _execute(context, "revert_preview", {})
        final = _snapshot(cube)
        assert final == initial, {"initial": initial, "final": final}

        _select_object(context, cube)
        vehicle = _execute(context, "apply_vehicle_refinement_template", {"target_name": "Cube", "detail_level": "medium"})
        assert vehicle["created_objects"]
        assert any("Wheel" in name for name in vehicle["created_objects"])
        assert cube.modifiers.get("Claude Detail Bevel")
        _execute(context, "revert_preview", {})
        final = _snapshot(cube)
        assert final == initial, {"initial": initial, "final": final}

        print("smoke_refinement_helpers: ok")
    finally:
        claude_blender.unregister()


if __name__ == "__main__":
    main()
