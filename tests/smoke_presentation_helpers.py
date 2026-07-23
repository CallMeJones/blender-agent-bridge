"""Blender background smoke test for reusable presentation helpers."""

from __future__ import annotations

import json
import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import advanced_helpers, advanced_support, agent_tools, bridge_protocol, context_bundle, tool_dispatcher  # noqa: E402


REFINEMENT_TOOLS = {
    "shade_smooth_selected",
    "add_bevel_and_subsurf",
    "create_wheel_assembly",
    "add_panel_seams",
    "add_window_materials",
    "create_studio_product_stage",
    "add_dimension_callouts",
    "apply_lighting_preset",
    "create_material_palette",
    "create_product_turntable_setup",
    "prepare_imported_asset_presentation",
    "organize_scene_for_production",
}


def _execute(context, name, args=None):
    result = json.loads(tool_dispatcher.execute_tool(context, name, args or {}))
    assert result.get("ok"), f"{name} failed: {result}"
    return result


def _execute_failure(context, name, args=None):
    result = json.loads(tool_dispatcher.execute_tool(context, name, args or {}))
    assert not result.get("ok"), f"{name} unexpectedly succeeded: {result}"
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
        "collections": set(bpy.data.collections.keys()),
        "materials": set(bpy.data.materials.keys()),
        "lights": set(bpy.data.lights.keys()),
        "cameras": set(bpy.data.cameras.keys()),
        "actions": set(bpy.data.actions.keys()),
        "scene_camera": bpy.context.scene.camera.name if bpy.context.scene.camera else None,
        "cube_materials": [slot.material.name if slot.material else None for slot in cube.material_slots],
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
        full_names = {tool["name"] for tool in agent_tools.blender_tool_definitions()}
        assert REFINEMENT_TOOLS.issubset(full_names)
        assert REFINEMENT_TOOLS.issubset(set(bridge_protocol.TOOL_CONTRACTS))

        bpy.ops.object.select_all(action="DESELECT")
        context.view_layer.objects.active = None
        empty_selection = advanced_support._selection_snapshot(context)
        _select_object(context, cube)
        advanced_support._restore_selection_snapshot(context, empty_selection)
        assert not context.selected_objects
        assert context.view_layer.objects.active is None
        _select_object(context, cube)

        _execute(context, "shade_smooth_selected", {"add_weighted_normals": True})
        assert all(poly.use_smooth for poly in cube.data.polygons)
        assert cube.modifiers.get("Agent Bridge Weighted Normals")

        _execute(context, "add_bevel_and_subsurf", {"bevel_width": 0.05, "bevel_segments": 3, "subsurf_levels": 1})
        assert cube.modifiers.get("Agent Bridge Detail Bevel")
        assert cube.modifiers.get("Agent Bridge Detail Subdivision")

        wheel = _execute(context, "create_wheel_assembly", {"name": "Agent Bridge Test Wheel", "location": [2.2, -1.2, -0.6], "radius": 0.35})
        assert len(wheel["objects"]) == 2

        seams = _execute(context, "add_panel_seams", {"target_name": "Cube"})
        assert seams["objects"]

        glass = _execute(context, "add_window_materials", {"target_name": "Cube", "create_panels": True})
        assert glass["created_objects"]

        stage = _execute(context, "create_studio_product_stage", {"target_name": "Cube", "stage_name": "Agent Bridge Test Stage"})
        assert stage["created_objects"]
        assert len(stage["lights"]) == 3
        assert stage["camera"]
        assert "studio stage" in stage["expected_changes"], stage
        # Default scene already has the "Light" object, so stacking a stage rig must warn.
        assert stage["warnings"], stage
        assert "over-expose" in stage["lighting_warning"], stage

        callouts = _execute(context, "add_dimension_callouts", {"target_name": "Cube", "unit_label": "m"})
        assert {"width", "depth", "height"} == set(callouts["measurements"])
        assert len(callouts["created_objects"]) == 6

        lighting = _execute(context, "apply_lighting_preset", {"target_name": "Cube", "preset": "dramatic_rim"})
        assert len(lighting["lights"]) == 3
        # The stage rig above is already live in this transaction, so the preset must warn too.
        assert lighting["warnings"], lighting
        assert "over-expose" in lighting["lighting_warning"], lighting

        _select_object(context, cube)
        palette = _execute(
            context,
            "create_material_palette",
            {"palette_name": "Agent Bridge Test Palette", "palette": "automotive", "assign_to_selected": True},
        )
        assert len(palette["materials"]) == 5
        assert len(palette["swatches"]) == 5
        assert palette["assigned"][0]["object"] == "Cube"

        turntable = _execute(
            context,
            "create_product_turntable_setup",
            {"target_name": "Cube", "frame_start": 1, "frame_end": 48, "setup_name": "Agent Bridge Test Turntable", "create_stage": False},
        )
        assert turntable["animation"]["action"], turntable
        assert turntable["camera_orbit"]["camera"], turntable

        imported_presentation = _execute(
            context,
            "prepare_imported_asset_presentation",
            {
                "imported_object_names": ["Cube"],
                "target_object_name": "Cube",
                "collection_prefix": "Agent Bridge Test Imported Asset",
                "presentation_preset": "turntable",
                "assign_material_if_missing": False,
                "create_stage": True,
                "create_turntable": True,
            },
        )
        assert imported_presentation["target"] == "Cube", imported_presentation
        assert imported_presentation["organization"]["ok"] is True, imported_presentation
        assert imported_presentation["stage"]["ok"] is True, imported_presentation
        assert imported_presentation["turntable"]["ok"] is True, imported_presentation
        assert "production collections" in imported_presentation["features"], imported_presentation
        assert "turntable review" in imported_presentation["features"], imported_presentation
        assert "imported asset" in imported_presentation["expected_changes"].lower(), imported_presentation

        organized = _execute(context, "organize_scene_for_production", {"collection_prefix": "Agent Bridge Test Production"})
        assert organized["collections"], organized

        # Engine guard: an unknown engine is refused cleanly (no dangling transaction),
        # while the scene's current engine still applies.
        bad_engine = _execute_failure(context, "set_render_settings", {"engine": "NOT_A_REAL_ENGINE"})
        assert "Unsupported render engine" in bad_engine["message"], bad_engine
        _execute(context, "set_render_settings", {"engine": context.scene.render.engine})

        _execute(context, "revert_preview", {})
        final = _snapshot(cube)
        assert final == initial, {"initial": initial, "final": final}

        # Shaded playblast: invalid shading is ignored, valid shading yields a restore
        # callback, and the dispatcher plumbs `shading` through without error. Background
        # mode has no interactive viewport, so capture is unavailable but must not crash.
        from claude_blender import playblast_capture  # noqa: E402

        invalid_restore, invalid_name = playblast_capture._apply_viewport_shading(context, "NONSENSE")
        assert invalid_restore is None and invalid_name == "", (invalid_restore, invalid_name)
        valid_restore, valid_name = playblast_capture._apply_viewport_shading(context, "material")
        assert callable(valid_restore) and valid_name == "MATERIAL", (valid_restore, valid_name)
        shaded = json.loads(
            tool_dispatcher.execute_tool(
                context, "capture_animation_playblast", {"shading": "MATERIAL", "max_frames": 2}
            )
        )
        assert "playblast" in shaded, shaded
        assert shaded["playblast"]["available"] is False, shaded  # headless: no interactive viewport

        print("smoke_presentation_helpers: ok")
    finally:
        claude_blender.unregister()


if __name__ == "__main__":
    main()
