"""Blender background smoke test for advanced safe helper tools."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

import bpy
from mathutils import Vector


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import advanced_helpers, advanced_modeling, advanced_rigging, agent_tools, blender_compat, context_bundle, live_preview, preferences, script_runner, tool_dispatcher  # noqa: E402
from claude_blender import quality_benchmarks, reference_benchmark_scene  # noqa: E402
from claude_blender import reference_blockout as reference_blockout_module  # noqa: E402
from claude_blender import reference_comparison as reference_comparison_module  # noqa: E402


ADVANCED_TOOLS = {
    "plan_advanced_scene_workflow",
    "plan_model_quality_workflow",
    "plan_asset_import_workflow",
    "plan_director_workflow",
    "get_2d_animation_details",
    "apply_procedural_array_stack",
    "edit_mesh",
    "inspect_modeling_quality",
    "curve_to_mesh",
    "uv_unwrap",
    "mark_uv_seams",
    "inspect_uv_layout",
    "boolean_op",
    "mirror_model",
    "symmetrize_model",
    "solidify_model",
    "screw_model",
    "create_camera_dolly_animation",
    "prepare_imported_asset_presentation",
    "add_cloth_simulation_to_selected",
    "create_shader_material",
    "create_image_texture_material",
    "inspect_material_setup",
    "repair_material_setup",
    "bake_maps",
    "create_procedural_texture_material",
    "add_geometry_nodes_modifier",
    "create_shape_key",
    "animate_shape_key",
    "create_text_object",
    "create_curve_path",
    "create_reference_guides_from_annotations",
    "prepare_reference_images",
    "create_multiview_reference_guides",
    "create_multiview_visual_hull",
    "create_multiview_depth_surface",
    "fit_surface_to_multiview_references",
    "create_reference_modeling_guides",
    "inspect_reference_modeling_guides",
    "compare_model_to_reference",
    "evaluate_multiview_reference_match",
    "auto_reference_sculpt_repair",
    "evaluate_reference_model_benchmark",
    "create_reference_blockout",
    "create_reference_part_graph",
    "build_part_aware_base_mesh",
    "add_particle_system_to_selected",
    "create_directional_fur_curves",
    "create_basic_armature",
    "add_copy_transform_constraint",
    "set_render_settings",
    "set_render_engine",
    "configure_render_outputs",
    "create_lookdev_turntable_review",
    "set_camera_settings",
    "set_world_background",
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
    world_color = tuple(scene.world.color) if scene.world else None
    return {
        "objects": set(bpy.data.objects.keys()),
        "curves": set(bpy.data.curves.keys()),
        "materials": set(bpy.data.materials.keys()),
        "images": {image.name for image in bpy.data.images if image.type == "IMAGE"},
        "image_colorspaces": {image.name: image.colorspace_settings.name for image in bpy.data.images if image.type == "IMAGE"},
        "node_groups": set(bpy.data.node_groups.keys()),
        "armatures": set(bpy.data.armatures.keys()),
        "particles": set(bpy.data.particles.keys()),
        "actions": set(bpy.data.actions.keys()),
        "mesh_topology": {
            mesh.name: (len(mesh.vertices), len(mesh.edges), len(mesh.polygons))
            for mesh in bpy.data.meshes
        },
        "mesh_vertex_coordinates": {
            mesh.name: tuple(
                tuple(round(float(component), 5) for component in vertex.co)
                for vertex in mesh.vertices
            )
            for mesh in bpy.data.meshes
            if len(mesh.vertices) <= 128
        },
        "cube_modifiers": [modifier.name for modifier in cube.modifiers],
        "cube_shape_keys": [block.name for block in cube.data.shape_keys.key_blocks] if cube.data.shape_keys else [],
        "camera_constraints": len(camera.constraints),
        "camera_lens": camera.data.lens,
        "camera_dof": camera.data.dof.use_dof,
        "scene_camera": scene.camera.name if scene.camera else "",
        "resolution": (scene.render.resolution_x, scene.render.resolution_y),
        "pixel_aspect": (
            scene.render.pixel_aspect_x,
            scene.render.pixel_aspect_y,
        ),
        "fps": scene.render.fps,
        "frame_range": (scene.frame_start, scene.frame_end),
        "film_transparent": scene.render.film_transparent,
        "render_engine": scene.render.engine,
        "view_transform": getattr(scene.view_settings, "view_transform", None),
        "look": getattr(scene.view_settings, "look", None),
        "exposure": round(float(getattr(scene.view_settings, "exposure", 0.0)), 5),
        "gamma": round(float(getattr(scene.view_settings, "gamma", 1.0)), 5),
        "cycles_samples": getattr(getattr(scene, "cycles", None), "samples", None),
        "cycles_use_denoising": getattr(getattr(scene, "cycles", None), "use_denoising", None),
        "world": scene.world.name if scene.world else None,
        "world_color": world_color,
    }


def _material_topology(material):
    node_tree = getattr(material, "node_tree", None) if material else None
    if not node_tree:
        return {"has_node_tree": False, "nodes": [], "links": []}
    return {
        "has_node_tree": True,
        "nodes": sorted(node.name for node in node_tree.nodes),
        "links": sorted(
            (
                link.from_node.name,
                getattr(link.from_socket, "identifier", link.from_socket.name),
                link.to_node.name,
                getattr(link.to_socket, "identifier", link.to_socket.name),
            )
            for link in node_tree.links
        ),
    }


def _write_test_image(path, color, width=2, height=2):
    image = bpy.data.images.new(name=os.path.basename(path), width=width, height=height, alpha=True)
    image.pixels = list(color) * (width * height)
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)
    assert os.path.isfile(path), path


def _run_phase1_modeling_helper_prop_test(context):
    parts = {}

    def primitive(name, primitive_type, location, rotation, scale):
        result = _execute(
            context,
            "create_primitive",
            {
                "primitive_type": primitive_type,
                "name": name,
                "location": location,
                "rotation": rotation,
                "scale": scale,
            },
        )
        parts[name] = bpy.data.objects[result["object"]]
        return parts[name]

    base = primitive("Agent Bridge Phase1 Lamp Base", "CYLINDER", [0.0, -4.0, 0.08], [0.0, 0.0, 0.0], [0.7, 0.7, 0.08])
    pole = primitive("Agent Bridge Phase1 Lamp Pole", "CYLINDER", [0.0, -4.0, 0.85], [0.0, 0.0, 0.0], [0.045, 0.045, 0.75])
    arm = primitive("Agent Bridge Phase1 Lamp Arm", "CYLINDER", [0.55, -4.0, 1.55], [0.0, 1.5708, 0.0], [0.04, 0.04, 0.55])
    shade = primitive("Agent Bridge Phase1 Lamp Shade", "CONE", [1.1, -4.0, 1.42], [0.0, 1.5708, 0.0], [0.34, 0.34, 0.36])
    bulb = primitive("Agent Bridge Phase1 Lamp Bulb", "UV_SPHERE", [0.92, -4.0, 1.36], [0.0, 0.0, 0.0], [0.13, 0.13, 0.13])
    thread_seed = primitive("Agent Bridge Phase1 Lamp Thread Seed", "PLANE", [0.32, -4.0, 1.55], [0.0, 1.5708, 0.0], [0.04, 0.04, 0.04])

    loop_result = _execute(
        context,
        "edit_mesh",
        {"operation": "loop_cut", "object_names": [base.name], "selected_only": False, "loop_cuts": 1},
    )
    assert loop_result["objects"][0]["after"]["vertices"] > loop_result["objects"][0]["before"]["vertices"], loop_result
    assert loop_result["objects"][0]["details"]["mode"] == "bounded_planar_loop", loop_result
    knife_result = _execute(
        context,
        "edit_mesh",
        {"operation": "knife_cut", "object_names": [shade.name], "selected_only": False, "cut_axis": "Z", "cut_position": 0.0},
    )
    assert knife_result["objects"][0]["after"]["edges"] > knife_result["objects"][0]["before"]["edges"], knife_result
    proportional_result = _execute(
        context,
        "edit_mesh",
        {
            "operation": "proportional_edit",
            "object_names": [shade.name],
            "selected_only": False,
            "axis": "Z",
            "distance": -0.05,
            "proportional_center": [0.0, 0.0, 0.35],
            "proportional_radius": 0.9,
            "proportional_falloff": "SMOOTH",
        },
    )
    assert proportional_result["objects"][0]["details"]["moved_vertices"] > 0, proportional_result
    solidify_result = _execute(
        context,
        "solidify_model",
        {"object_names": [shade.name], "selected_only": False, "thickness": 0.035, "offset": 0.0, "name": "Agent Bridge Phase1 Shade Thickness"},
    )
    assert shade.modifiers.get(solidify_result["objects"][0]["modifier"]).type == "SOLIDIFY", solidify_result
    screw_result = _execute(
        context,
        "screw_model",
        {
            "object_names": [thread_seed.name],
            "selected_only": False,
            "axis": "Z",
            "angle": 12.566370614359172,
            "screw_offset": 0.22,
            "iterations": 2,
            "steps": 16,
            "name": "Agent Bridge Phase1 Thread Screw",
        },
    )
    assert thread_seed.modifiers.get(screw_result["objects"][0]["modifier"]).type == "SCREW", screw_result

    _execute(
        context,
        "select_objects",
        {"object_names": [base.name, pole.name, arm.name, shade.name, thread_seed.name], "active_object_name": base.name},
    )
    _execute(context, "create_shader_material", {"name": "Agent Bridge Phase1 Brushed Metal", "preset": "brushed_metal", "assign_to_selected": True})
    _execute(context, "select_objects", {"object_names": [bulb.name], "active_object_name": bulb.name})
    _execute(context, "assign_emission_material_to_selected", {"name": "Agent Bridge Phase1 Warm Bulb", "color": [1.0, 0.74, 0.38, 1.0], "strength": 2.4})

    lamp_object_names = [obj.name for obj in (base, pole, arm, shade, bulb, thread_seed)]
    uv_result = _execute(
        context,
        "uv_unwrap",
        {
            "object_names": lamp_object_names,
            "selected_only": False,
            "method": "smart_project",
            "uv_map_name": "Agent Bridge Phase2 Lookdev UVs",
            "replace_existing": True,
        },
    )
    assert len(uv_result["objects"]) == len(lamp_object_names), uv_result
    bpy.ops.object.select_all(action="DESELECT")
    root_result = _execute(
        context,
        "parent_selected_to_empty",
        {"object_names": lamp_object_names, "selected_only": False, "name": "Agent Bridge Phase1 Lamp Root"},
    )
    root_name = root_result["empty"]
    assert root_result["missing_object_names"] == [], root_result
    quality = _execute(
        context,
        "inspect_modeling_quality",
        {"object_names": [root_name], "selected_only": False, "include_children": True, "require_materials": True},
    )
    assert quality["passed"] is True, quality
    assert quality["object_count"] == 6, quality
    assert quality["issue_count"] == 0, quality
    for item in quality["objects"]:
        assert item["materials"]["materials"], item
        assert item["topology"]["loose_vertices"] == 0, item
        assert item["topology"]["loose_edges"] == 0, item

    for obj in (base, pole, arm, shade, bulb, thread_seed):
        assert obj.name in bpy.data.objects
        assert obj.type == "MESH"
        assert obj.material_slots and obj.material_slots[0].material, obj.name
        assert obj.data.uv_layers.get("Agent Bridge Phase2 Lookdev UVs"), obj.name
    assert shade.modifiers.get("Agent Bridge Phase1 Shade Thickness")
    assert thread_seed.modifiers.get("Agent Bridge Phase1 Thread Screw")
    return {
        "root": root_name,
        "objects": lamp_object_names,
        "materials": ["Agent Bridge Phase1 Brushed Metal", "Agent Bridge Phase1 Warm Bulb"],
        "quality": quality,
    }








def main():
    claude_blender.register()
    context = bpy.context
    capture_dir = tempfile.mkdtemp(prefix="agent-bridge-advanced-captures-")
    original_get_preferences = preferences.get_preferences
    smoke_preferences = type(
        "_SmokePreferences",
        (),
        {
            "capture_cache_dir": capture_dir,
            "max_screenshot_bytes": 5 * 1024 * 1024,
        },
    )()
    preferences.get_preferences = lambda _context: smoke_preferences
    scene = context.scene
    cube = bpy.data.objects["Cube"]
    camera = bpy.data.objects["Camera"]
    existing_material = bpy.data.materials.new("Agent Bridge Existing Node Material")
    node_tree = blender_compat.ensure_node_tree(existing_material)
    assert node_tree is not None, "Node-enabled Blender materials should expose a shader node tree"
    nodes = node_tree.nodes
    for node in list(nodes):
        nodes.remove(node)
    diffuse = nodes.new(type="ShaderNodeBsdfDiffuse")
    output = nodes.new(type="ShaderNodeOutputMaterial")
    node_tree.links.new(diffuse.outputs["BSDF"], output.inputs["Surface"])
    cube.data.materials.clear()
    cube.data.materials.append(existing_material)
    existing_topology = _material_topology(existing_material)
    no_uv_mesh = bpy.data.meshes.new("Agent Bridge No UV Bake Fixture Mesh")
    no_uv_mesh.from_pydata(
        [(-0.5, -0.5, 0.0), (0.5, -0.5, 0.0), (0.5, 0.5, 0.0), (-0.5, 0.5, 0.0)],
        [],
        [(0, 1, 2, 3)],
    )
    no_uv_mesh.update()
    no_uv_fixture = bpy.data.objects.new("Agent Bridge No UV Bake Fixture", no_uv_mesh)
    no_uv_fixture.data.materials.append(existing_material)
    context.collection.objects.link(no_uv_fixture)
    missing_uv_bake = json.loads(
        tool_dispatcher.execute_tool(
            context,
            "bake_maps",
            {
                "object_names": [no_uv_fixture.name],
                "selected_only": False,
                "map_types": ["ao"],
                "resolution": 32,
                "samples": 1,
            },
        )
    )
    assert missing_uv_bake["ok"] is False, missing_uv_bake
    assert missing_uv_bake["baked_map_count"] == 0, missing_uv_bake
    assert "transaction_id" not in missing_uv_bake, missing_uv_bake
    assert any("Mesh has no UV map" in issue["message"] for issue in missing_uv_bake["issues"]), missing_uv_bake
    assert not scene.claude_blender.pending_preview, scene.claude_blender.pending_preview_summary
    current_transaction = live_preview.current_transaction()
    assert not current_transaction or current_transaction.get("status") != "pending", current_transaction
    bpy.data.objects.remove(no_uv_fixture, do_unlink=True)
    bpy.data.meshes.remove(no_uv_mesh)

    bridge_mesh = bpy.data.meshes.new("Agent Bridge Bridge Fixture Mesh")
    bridge_mesh.from_pydata(
        [
            (-0.5, -0.5, 0.0),
            (0.5, -0.5, 0.0),
            (0.5, 0.5, 0.0),
            (-0.5, 0.5, 0.0),
            (-0.5, -0.5, 1.0),
            (0.5, -0.5, 1.0),
            (0.5, 0.5, 1.0),
            (-0.5, 0.5, 1.0),
        ],
        [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4)],
        [],
    )
    bridge_mesh.update()
    bridge_fixture = bpy.data.objects.new("Agent Bridge Bridge Fixture", bridge_mesh)
    context.collection.objects.link(bridge_fixture)
    merge_mesh = bpy.data.meshes.new("Agent Bridge Merge Fixture Mesh")
    merge_mesh.from_pydata([(0.0, 0.0, 0.0), (0.0005, 0.0, 0.0), (1.0, 0.0, 0.0)], [(0, 2), (1, 2)], [])
    merge_mesh.update()
    merge_fixture = bpy.data.objects.new("Agent Bridge Merge Fixture", merge_mesh)
    context.collection.objects.link(merge_fixture)
    dissolve_mesh = bpy.data.meshes.new("Agent Bridge Dissolve Fixture Mesh")
    dissolve_mesh.from_pydata(
        [(0.0, 0.0, 0.0), (0.00001, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [(0, 1), (1, 2), (2, 3), (3, 0)],
        [(0, 1, 2, 3)],
    )
    dissolve_mesh.update()
    dissolve_fixture = bpy.data.objects.new("Agent Bridge Dissolve Fixture", dissolve_mesh)
    context.collection.objects.link(dissolve_fixture)
    loop_mesh = bpy.data.meshes.new("Agent Bridge Loop Fixture Mesh")
    loop_mesh.from_pydata(
        [(-0.5, -0.5, 0.0), (0.5, -0.5, 0.0), (0.5, 0.5, 0.0), (-0.5, 0.5, 0.0)],
        [(0, 1), (1, 2), (2, 3), (3, 0)],
        [(0, 1, 2, 3)],
    )
    loop_mesh.update()
    loop_fixture = bpy.data.objects.new("Agent Bridge Loop Fixture", loop_mesh)
    context.collection.objects.link(loop_fixture)
    knife_mesh = bpy.data.meshes.new("Agent Bridge Knife Fixture Mesh")
    knife_mesh.from_pydata(
        [
            (-0.5, -0.5, -0.5),
            (0.5, -0.5, -0.5),
            (0.5, 0.5, -0.5),
            (-0.5, 0.5, -0.5),
            (-0.5, -0.5, 0.5),
            (0.5, -0.5, 0.5),
            (0.5, 0.5, 0.5),
            (-0.5, 0.5, 0.5),
        ],
        [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)],
        [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)],
    )
    knife_mesh.update()
    knife_fixture = bpy.data.objects.new("Agent Bridge Knife Fixture", knife_mesh)
    context.collection.objects.link(knife_fixture)
    proportional_mesh = bpy.data.meshes.new("Agent Bridge Proportional Fixture Mesh")
    proportional_mesh.from_pydata(
        [(-0.5, 0.0, 0.0), (0.0, 0.0, 0.0), (0.5, 0.0, 0.0)],
        [(0, 1), (1, 2)],
        [],
    )
    proportional_mesh.update()
    proportional_fixture = bpy.data.objects.new("Agent Bridge Proportional Fixture", proportional_mesh)
    context.collection.objects.link(proportional_fixture)
    shape_key_mesh = bpy.data.meshes.new("Agent Bridge Shape Key Fixture Mesh")
    shape_key_mesh.from_pydata(
        [(-0.5, -0.5, 0.0), (0.5, -0.5, 0.0), (0.5, 0.5, 0.0), (-0.5, 0.5, 0.0)],
        [(0, 1), (1, 2), (2, 3), (3, 0)],
        [(0, 1, 2, 3)],
    )
    shape_key_mesh.update()
    shape_key_fixture = bpy.data.objects.new("Agent Bridge Shape Key Fixture", shape_key_mesh)
    context.collection.objects.link(shape_key_fixture)
    shape_key_fixture.shape_key_add(name="Basis")
    raised_key = shape_key_fixture.shape_key_add(name="Raised")
    for point in raised_key.data:
        point.co.z += 0.1
    failure_curve_data = bpy.data.curves.new("Agent Bridge Failure Curve", "CURVE")
    failure_curve_data.dimensions = "3D"
    failure_spline = failure_curve_data.splines.new("POLY")
    failure_spline.points.add(1)
    failure_spline.points[0].co = (0.0, 0.0, 0.0, 1.0)
    failure_spline.points[1].co = (1.0, 0.0, 0.0, 1.0)
    failure_curve = bpy.data.objects.new("Agent Bridge Failure Curve", failure_curve_data)
    context.collection.objects.link(failure_curve)
    persistent_roughness_path = os.path.join(tempfile.gettempdir(), "agent-bridge-smoke-existing-roughness.png")
    _write_test_image(persistent_roughness_path, (0.55, 0.55, 0.55, 1.0))
    persistent_roughness_image = bpy.data.images.load(persistent_roughness_path, check_existing=True)
    persistent_roughness_image.colorspace_settings.name = "sRGB"
    persistent_reference_path = os.path.join(
        capture_dir, "agent-bridge-reference-annotations.png"
    )
    _write_test_image(
        persistent_reference_path,
        (0.4, 0.45, 0.5, 1.0),
        width=400,
        height=200,
    )
    persistent_reference_image = bpy.data.images.load(
        persistent_reference_path,
        check_existing=True,
    )
    persistent_reference_name = persistent_reference_image.name
    initial = _snapshot(scene, cube, camera)

    try:
        bundle = context_bundle.build_context_bundle(context)
        assert ADVANCED_TOOLS.issubset(set(bundle["available_tools"]))
        tool_names = {tool["name"] for tool in agent_tools.blender_tool_definitions()}
        assert ADVANCED_TOOLS.issubset(tool_names)

        assert live_preview.current_transaction() is None
        invalid_dolly = json.loads(tool_dispatcher.execute_tool(context, "create_camera_dolly_animation", {"camera_name": "Cube"}))
        assert invalid_dolly["ok"] is False, invalid_dolly
        assert "not a camera" in invalid_dolly["message"], invalid_dolly
        assert live_preview.current_transaction() is None, invalid_dolly
        image_names_before_invalid_reference = set(bpy.data.images.keys())
        invalid_reference = json.loads(
            tool_dispatcher.execute_tool(
                context,
                "create_reference_modeling_guides",
                {
                    "image_path": os.path.join(ROOT, "README.md"),
                    "include_image_plane": True,
                },
            )
        )
        assert invalid_reference["ok"] is False, invalid_reference
        assert "Could not load usable reference image" in invalid_reference["message"], invalid_reference
        assert set(bpy.data.images.keys()) == image_names_before_invalid_reference
        assert live_preview.current_transaction() is None, invalid_reference
        collections_before_non_finite_reference = set(
            bpy.data.collections.keys()
        )
        non_finite_reference = json.loads(
            tool_dispatcher.execute_tool(
                context,
                "create_reference_modeling_guides",
                {
                    "image_size": [float("inf"), 100.0],
                    "include_image_plane": True,
                },
            )
        )
        assert non_finite_reference["ok"] is False, non_finite_reference
        assert "finite" in non_finite_reference["message"].lower(), non_finite_reference
        assert set(bpy.data.collections.keys()) == collections_before_non_finite_reference
        assert live_preview.current_transaction() is None, non_finite_reference
        blocked_shape_key_edit = json.loads(
            tool_dispatcher.execute_tool(
                context,
                "edit_mesh",
                {
                    "operation": "extrude_faces",
                    "object_names": [shape_key_fixture.name],
                    "selected_only": False,
                    "face_scope": "ALL",
                },
            )
        )
        assert blocked_shape_key_edit["ok"] is False, blocked_shape_key_edit
        assert blocked_shape_key_edit["objects"] == [], blocked_shape_key_edit
        assert "shape-key meshes" in blocked_shape_key_edit["skipped"][0]["reason"], blocked_shape_key_edit
        assert live_preview.current_transaction() is None, blocked_shape_key_edit

        cube_topology_before_failed_snapshot = (len(cube.data.vertices), len(cube.data.edges), len(cube.data.polygons))
        original_record_mesh_data_snapshot = live_preview._record_mesh_data_snapshot

        def _fail_record_mesh_data_snapshot(obj):
            raise RuntimeError("forced mesh snapshot failure")

        try:
            live_preview._record_mesh_data_snapshot = _fail_record_mesh_data_snapshot
            failed_mesh_edit = json.loads(
                tool_dispatcher.execute_tool(
                    context,
                    "edit_mesh",
                    {
                        "operation": "extrude_faces",
                        "object_names": ["Cube"],
                        "selected_only": False,
                        "face_scope": "TOP",
                        "direction": "AXIS",
                        "axis": "Z",
                        "distance": 0.1,
                    },
                )
            )
        finally:
            live_preview._record_mesh_data_snapshot = original_record_mesh_data_snapshot
        assert failed_mesh_edit["ok"] is False, failed_mesh_edit
        assert failed_mesh_edit["objects"] == [], failed_mesh_edit
        assert "forced mesh snapshot failure" in failed_mesh_edit["skipped"][0]["reason"], failed_mesh_edit
        assert (len(cube.data.vertices), len(cube.data.edges), len(cube.data.polygons)) == cube_topology_before_failed_snapshot
        transaction = live_preview.current_transaction()
        assert transaction is None or transaction.get("status") != "pending", transaction

        original_record_created_id = live_preview._record_created_id

        def _fail_record_created_id(kind, name):
            raise RuntimeError("forced recorder failure")

        try:
            live_preview._record_created_id = _fail_record_created_id
            failed_curve = json.loads(
                tool_dispatcher.execute_tool(
                    context,
                    "curve_to_mesh",
                    {"object_names": [failure_curve.name], "selected_only": False, "name_prefix": "Agent Bridge Failed Convert "},
                )
            )
        finally:
            live_preview._record_created_id = original_record_created_id
        assert failed_curve["ok"] is False, failed_curve
        assert not any(obj.name.startswith("Agent Bridge Failed Convert ") for obj in bpy.data.objects), failed_curve
        assert not any(mesh.name.startswith("Agent Bridge Failed Convert ") for mesh in bpy.data.meshes), failed_curve
        transaction = live_preview.current_transaction()
        assert transaction is None or transaction.get("status") != "pending", transaction

        record_call_count = {"count": 0}

        def _fail_second_record_created_id(kind, name):
            record_call_count["count"] += 1
            if record_call_count["count"] == 2:
                raise RuntimeError("forced second recorder failure")
            return original_record_created_id(kind, name)

        try:
            live_preview._record_created_id = _fail_second_record_created_id
            failed_second_record_curve = json.loads(
                tool_dispatcher.execute_tool(
                    context,
                    "curve_to_mesh",
                    {"object_names": [failure_curve.name], "selected_only": False, "name_prefix": "Agent Bridge Half Recorded "},
                )
            )
        finally:
            live_preview._record_created_id = original_record_created_id
        assert failed_second_record_curve["ok"] is False, failed_second_record_curve
        assert not any(obj.name.startswith("Agent Bridge Half Recorded ") for obj in bpy.data.objects), failed_second_record_curve
        assert not any(mesh.name.startswith("Agent Bridge Half Recorded ") for mesh in bpy.data.meshes), failed_second_record_curve
        transaction = live_preview.current_transaction()
        assert transaction is None or transaction.get("status") != "pending", transaction
        assert not any("Agent Bridge Half Recorded " in name for name in (transaction or {}).get("changed_data_blocks", [])), transaction

        original_link_object_like_source = advanced_modeling._link_object_like_source

        def _fail_link_object_like_source(context, source, duplicate):
            raise RuntimeError("forced link failure")

        try:
            advanced_modeling._link_object_like_source = _fail_link_object_like_source
            failed_link_curve = json.loads(
                tool_dispatcher.execute_tool(
                    context,
                    "curve_to_mesh",
                    {"object_names": [failure_curve.name], "selected_only": False, "name_prefix": "Agent Bridge Link Failed "},
                )
            )
        finally:
            advanced_modeling._link_object_like_source = original_link_object_like_source
        assert failed_link_curve["ok"] is False, failed_link_curve
        assert not any(obj.name.startswith("Agent Bridge Link Failed ") for obj in bpy.data.objects), failed_link_curve
        assert not any(mesh.name.startswith("Agent Bridge Link Failed ") for mesh in bpy.data.meshes), failed_link_curve
        transaction = live_preview.current_transaction()
        assert transaction is None or transaction.get("status") != "pending", transaction
        assert not any("Agent Bridge Link Failed " in name for name in (transaction or {}).get("changed_data_blocks", [])), transaction

        workflow = _execute(
            context,
            "plan_advanced_scene_workflow",
            {"prompt": "Plan advanced 2D storyboard, procedural 3D, cloth simulation, and camera animation helpers."},
        )
        assert {"two_d_storyboard", "procedural_3d", "advanced_animation", "simulation_setup"}.intersection(set(workflow["domains"]))
        assert workflow["execution_strategy"]["selection"] == "bounded_helpers_until_trust_enabled", workflow
        assert all(call["name"] != "draft_script" for call in workflow["next_tool_calls"]), workflow
        quality_args = {
                "prompt": "Match a reference image of a plush cartoon cat without using a canned template.",
                "reference_description": "Round head, large blue eyes, soft cheeks, small pink nose, smiling mouth, dense directional fur, rounded paws, and curved tail.",
                "reference_brief": {
                    "subject": "plush cartoon cat",
                    "silhouette": ["round head over a compact seated body", "curved tail visible beside the body"],
                    "primary_masses": ["head volume", "body volume", "front paws", "tail"],
                    "secondary_forms": ["cheek volumes", "muzzle volume"],
                    "landmarks": ["large paired eyes", "small nose", "smiling mouth"],
                    "proportion_checks": ["head is wider than body", "eyes occupy the middle third of the face"],
                    "surface_cues": ["dense directional fur with shorter fibers on the face"],
                    "negative_constraints": ["avoid sparse random particle spikes"],
                    "inspection_views": ["front", "side"],
                },
                "target_objects": ["Cube", "PlannedDetail"],
            }
        trust_off_quality_plan = _execute(
            context,
            "plan_model_quality_workflow",
            quality_args,
        )
        assert trust_off_quality_plan["construction_strategy"]["selection"] == (
            "bounded_helpers_until_trust_enabled"
        ), trust_off_quality_plan
        assert trust_off_quality_plan["script_fallback_policy"]["helper_first"] is True, trust_off_quality_plan
        trusted = script_runner.approve_external_script_trust_window(context, session=True)
        assert trusted["ok"] and trusted["session"], trusted
        animation_only_plan = _execute(
            context,
            "plan_advanced_scene_workflow",
            {
                "prompt": (
                    "Animate this character waving, capture a playblast, and repair "
                    "the timing."
                ),
                "target_objects": ["Cube"],
            },
        )
        assert animation_only_plan["domains"] == [
            "advanced_animation"
        ], animation_only_plan
        material_render_plan = _execute(
            context,
            "plan_advanced_scene_workflow",
            {
                "prompt": (
                    "Create a custom procedural material and render the final "
                    "animation."
                ),
                "target_objects": ["Cube"],
            },
        )
        assert "procedural_3d" in material_render_plan["domains"], material_render_plan
        assert "advanced_animation" not in material_render_plan[
            "domains"
        ], material_render_plan
        scripted_advanced_plan = _execute(
            context,
            "plan_advanced_scene_workflow",
            {
                "prompt": (
                    "Build a named-part robot with custom materials and nodes, then animate it waving "
                    "with an orbit camera."
                ),
                "target_objects": ["Cube"],
            },
        )
        assert {"procedural_3d", "advanced_animation"}.issubset(
            set(scripted_advanced_plan["domains"])
        ), scripted_advanced_plan
        assert scripted_advanced_plan["scripted_domains"] == [
            domain
            for domain in scripted_advanced_plan["domains"]
            if domain in {"model_quality", "2d_storyboard", "procedural_3d", "advanced_animation"}
        ], scripted_advanced_plan
        scripted_advanced_names = [
            call["name"] for call in scripted_advanced_plan["next_tool_calls"]
        ]
        assert "get_geometry_nodes_details" in scripted_advanced_names, scripted_advanced_plan
        assert "plan_animation_workflow" in scripted_advanced_names, scripted_advanced_plan
        assert scripted_advanced_names[-1] == "draft_script", scripted_advanced_plan
        scripted_advanced_call = scripted_advanced_plan["next_tool_calls"][-1]
        assert scripted_advanced_call["gateway_call_template"]["arguments"]["name"] == "draft_script"
        assert scripted_advanced_call["input_handoff"]["client_must_replace_placeholders"] is True
        assert "needs_reference_brief" in scripted_advanced_call["input_handoff"]["completion_gate"][
            "block_on_status"
        ]
        helper_advanced_plan = _execute(
            context,
            "plan_advanced_scene_workflow",
            {
                "prompt": "Use helpers only to build a hard-surface control panel and animate a reveal.",
                "target_objects": ["Cube"],
            },
        )
        assert helper_advanced_plan["execution_strategy"]["selection"] == (
            "bounded_helpers_requested"
        ), helper_advanced_plan
        assert not helper_advanced_plan["scripted_domains"], helper_advanced_plan
        assert all(
            call["name"] != "draft_script"
            for call in helper_advanced_plan["next_tool_calls"]
        ), helper_advanced_plan
        quality_plan = _execute(
            context,
            "plan_model_quality_workflow",
            quality_args,
        )
        assert quality_plan["status"] == "ready", quality_plan
        assert quality_plan["subject"] == "plush cartoon cat", quality_plan
        assert quality_plan["quality_floor"] == 4, quality_plan
        assert "head volume" in quality_plan["reference_breakdown"]["main_masses"], quality_plan
        quality_phase_names = [phase["name"] for phase in quality_plan["phases"]]
        assert quality_phase_names == [
            "execution_trace",
            "reference_decomposition",
            "inspect_scene",
            "block_major_masses",
            "refresh_targets",
            "form_evidence_gate",
            "semantic_form_repair",
            "surface_and_detail_pass",
            "evidence_score_repair",
            "preview_decision",
        ], quality_plan
        assert quality_plan["token_policy"]["keep_gateway_surface"] is True, quality_plan
        assert quality_plan["construction_strategy"]["selection"] == "cohesive_trusted_script", quality_plan
        assert quality_plan["construction_strategy"]["script_trust"]["active"] is True, quality_plan
        assert quality_plan["script_fallback_policy"]["helper_first"] is False, quality_plan
        assert quality_plan["script_fallback_policy"]["script_first"] is True, quality_plan
        assert quality_plan["script_fallback_policy"]["requires_session_script_trust"] is True, quality_plan
        assert "enum_items" in quality_plan["script_fallback_policy"]["script_preflight"]["enum_check"], quality_plan
        assert any(item["criterion"] == "silhouette_match" for item in quality_plan["quality_rubric"]), quality_plan
        assert quality_plan["completion_contract"]["must_not_stop_after_planning"] is True, quality_plan
        assert quality_plan["completion_contract"]["durable_quality_review_required"] is True, quality_plan
        assert quality_plan["completion_contract"]["quality_terminal_statuses"] == [
            "ready_for_user_review",
            "blocked_quality_floor",
        ], quality_plan
        assert quality_plan["construction_strategy"]["long_running_script_path"]["start"] == (
            "start_trusted_script_job"
        ), quality_plan
        assert quality_plan["target_objects"] == ["Cube"], quality_plan
        assert quality_plan["missing_target_objects"] == ["PlannedDetail"], quality_plan
        refresh_phase = next(phase for phase in quality_plan["phases"] if phase["name"] == "refresh_targets")
        assert refresh_phase["target_resolution"]["seed_with"] == ["Cube"], quality_plan
        assert quality_plan["next_tool_calls"], quality_plan
        for planned_call in quality_plan["next_tool_calls"]:
            assert planned_call["schema_lookup"]["name"] == "get_blender_tool_schema", planned_call
            assert planned_call["gateway_call"]["name"] == "invoke_blender_tool", planned_call
            assert planned_call["gateway_call"]["arguments"]["name"] == planned_call["name"], planned_call
        assert any(call["phase"] == "refresh_targets" for call in quality_plan["deferred_tool_calls"]), quality_plan
        semantic_phase = next(
            phase for phase in quality_plan["phases"] if phase["name"] == "semantic_form_repair"
        )
        assert {
            "apply_semantic_sculpt",
            "apply_form_aware_sculpt",
            "apply_screen_space_sculpt",
            "optimize_screen_space_sculpt",
        } == {
            call["name"] for call in semantic_phase["choose_one_repair_call"]
        }, quality_plan
        assert any(
            call["name"] == "define_semantic_sculpt_regions"
            and call["phase"] == "semantic_form_repair"
            for call in quality_plan["deferred_tool_calls"]
        ), quality_plan
        construction_script_calls = [
            call
            for call in quality_plan["deferred_tool_calls"]
            if call["name"] == "draft_script" and call["phase"] == "block_major_masses"
        ]
        assert len(construction_script_calls) == 1, quality_plan
        assert construction_script_calls[0]["gateway_call_template"]["arguments"]["name"] == "draft_script"
        assert construction_script_calls[0]["input_handoff"]["client_must_replace_placeholders"] is True
        resolved_target_calls = [
            call
            for call in quality_plan["deferred_tool_calls"]
            if call["name"] in {"inspect_modeling_quality", "capture_object_inspection_renders"}
        ]
        assert resolved_target_calls, quality_plan
        for planned_call in resolved_target_calls:
            assert planned_call["gateway_call_template"]["arguments"]["arguments"]["object_names"] == (
                "<resolved_target_objects>"
            ), planned_call
        durable_quality_calls = {
            call["name"]
            for call in quality_plan["deferred_tool_calls"]
            if call["phase"] == "evidence_score_repair"
        }
        assert {
            "start_model_quality_review",
            "get_model_quality_review_packet",
            "submit_model_quality_evaluation",
        }.issubset(durable_quality_calls), quality_plan
        evidence_phase = next(
            phase for phase in quality_plan["phases"] if phase["name"] == "evidence_score_repair"
        )
        assert evidence_phase["repair_gate"]["repair_tool_call"]["name"] == (
            "record_model_quality_repair"
        ), quality_plan

        human_plan = _execute(
            context,
            "plan_model_quality_workflow",
            {
                "prompt": "Model a human character from a reference image.",
                "reference_brief": {
                    "subject": "human character",
                    "silhouette": ["upright figure with relaxed shoulders"],
                    "primary_masses": ["ribcage", "pelvis", "head"],
                    "secondary_forms": ["upper arms", "forearms", "thighs", "lower legs"],
                    "landmarks": ["shoulder line", "elbows", "knees"],
                    "proportion_checks": ["head height is one eighth of total height"],
                    "surface_cues": ["matte cloth clothing"],
                },
            },
        )
        serialized_human_plan = json.dumps(human_plan).lower()
        for canned_animal_term in ("muzzle pads", "front paws", "tail curve", "chest ruff", "ear interior"):
            assert canned_animal_term not in serialized_human_plan, (canned_animal_term, human_plan)
        assert human_plan["reference_brief"]["primary_masses"] == ["ribcage", "pelvis", "head"], human_plan
        assert any("gateway_call_template" in call for call in human_plan["deferred_tool_calls"]), human_plan
        for deferred_call in human_plan["deferred_tool_calls"]:
            assert "schema_lookup" in deferred_call, deferred_call
            assert "gateway_call" in deferred_call or "gateway_call_template" in deferred_call, deferred_call

        incomplete_quality_plan = _execute(
            context,
            "plan_model_quality_workflow",
            {
                "prompt": "Match this character reference.",
                "reference_description": "A human character in a neutral stance.",
            },
        )
        assert incomplete_quality_plan["status"] == "needs_reference_brief", incomplete_quality_plan
        assert incomplete_quality_plan["completion_contract"]["ready_for_mutation"] is False, incomplete_quality_plan
        assert set(incomplete_quality_plan["missing_reference_brief_fields"]) == {
            "silhouette",
            "primary_masses",
            "proportion_checks",
        }, incomplete_quality_plan
        helper_override_args = dict(quality_args)
        helper_override_args["prompt"] = "Use helpers only to match this reference image."
        helper_override_plan = _execute(
            context,
            "plan_model_quality_workflow",
            helper_override_args,
        )
        assert helper_override_plan["construction_strategy"]["selection"] == (
            "bounded_helpers_requested"
        ), helper_override_plan
        assert helper_override_plan["script_fallback_policy"]["helper_first"] is True, helper_override_plan
        assert script_runner.revoke_external_script_trust_window(context)["ok"]
        asset_plan = _execute(
            context,
            "plan_asset_import_workflow",
            {"prompt": "Find a Poly Haven product prop, import it, organize it, stage it, and capture evidence."},
        )
        asset_phase_names = [phase["name"] for phase in asset_plan["phases"]]
        assert asset_phase_names == ["discover", "select_asset", "download", "import", "present"], asset_plan
        assert asset_plan["provider"] == "poly_haven", asset_plan
        assert asset_plan["provider_selection_required"] is False, asset_plan
        assert asset_plan["asset_selection_required"] is True, asset_plan
        assert asset_plan["selection_required"] is True, asset_plan
        asset_tool_names = [call["name"] for phase in asset_plan["phases"] for call in phase["tool_calls"]]
        assert "start_external_asset_download" not in asset_tool_names, asset_plan
        assert "start_external_asset_import_job" not in asset_tool_names, asset_plan
        assert "inspect_poly_haven_asset_files" not in asset_tool_names, asset_plan
        assert "<poly_haven_asset_id>" not in str(asset_plan), asset_plan
        assert asset_plan["phases"][-1]["tool_calls"] == [], asset_plan
        concrete_asset_plan = _execute(
            context,
            "plan_asset_import_workflow",
            {
                "prompt": "Import the selected Poly Haven model and stage it.",
                "provider": "poly_haven",
                "asset_id": "agent_bridge_test_asset",
            },
        )
        concrete_phase_names = [phase["name"] for phase in concrete_asset_plan["phases"]]
        assert concrete_phase_names == ["discover", "download", "import", "present"], concrete_asset_plan
        assert concrete_asset_plan["asset_selection_required"] is False, concrete_asset_plan
        assert concrete_asset_plan["selection_required"] is False, concrete_asset_plan
        concrete_download = next(call for phase in concrete_asset_plan["phases"] for call in phase["tool_calls"] if call["name"] == "start_external_asset_download")
        assert concrete_download["input"]["asset_id"] == "agent_bridge_test_asset", concrete_asset_plan
        assert not concrete_download["input"]["uid"], concrete_asset_plan
        concrete_present = next(call for phase in concrete_asset_plan["phases"] for call in phase["tool_calls"] if call["name"] == "prepare_imported_asset_presentation")
        assert concrete_present["input"]["presentation_preset"] == "studio", concrete_asset_plan
        assert concrete_present["input"]["imported_object_names"] == ["<imported_object_name>"], concrete_asset_plan
        assert concrete_present["input"]["use_active_fallback"] is False, concrete_asset_plan
        assert concrete_present["requires_live_preview"] is True, concrete_asset_plan
        ambiguous_asset_plan = _execute(
            context,
            "plan_asset_import_workflow",
            {"prompt": "Find a product prop asset, import it, organize it, stage it, and capture evidence."},
        )
        ambiguous_phase_names = [phase["name"] for phase in ambiguous_asset_plan["phases"]]
        assert ambiguous_phase_names == ["discover", "select_asset", "download", "import", "present"], ambiguous_asset_plan
        assert ambiguous_asset_plan["provider"] == "", ambiguous_asset_plan
        assert ambiguous_asset_plan["provider_selection_required"] is True, ambiguous_asset_plan
        assert ambiguous_asset_plan["asset_selection_required"] is False, ambiguous_asset_plan
        assert ambiguous_asset_plan["selection_required"] is True, ambiguous_asset_plan
        ambiguous_tool_names = [
            call["name"]
            for phase in ambiguous_asset_plan["phases"]
            for call in phase["tool_calls"]
        ]
        assert "search_poly_haven_assets" in ambiguous_tool_names, ambiguous_asset_plan
        assert "search_sketchfab_models" in ambiguous_tool_names, ambiguous_asset_plan
        assert "start_external_asset_download" not in ambiguous_tool_names, ambiguous_asset_plan
        assert ambiguous_asset_plan["phases"][-1]["tool_calls"] == [], ambiguous_asset_plan

        director_plan = _execute(
            context,
            "plan_director_workflow",
            {
                "prompt": "Director workflow: import an asset, inspect procedural modeling, animate a reveal, review evidence, and ask before commit.",
                "target_objects": ["Cube"],
            },
        )
        director_tool_names = [call["name"] for call in director_plan["next_tool_calls"]]
        assert "plan_asset_import_workflow" in director_tool_names, director_plan
        assert "get_geometry_nodes_details" in director_tool_names, director_plan
        assert "inspect_modeling_quality" in director_tool_names, director_plan
        assert "run_animation_workflow" in director_tool_names, director_plan
        assert "commit_preview" not in director_tool_names, director_plan
        assert "revert_preview" not in director_tool_names, director_plan
        director_decision_names = [option["tool_call"]["name"] for option in director_plan["preview_decision_options"]]
        assert director_decision_names == ["commit_preview", "revert_preview"], director_plan
        assert director_plan["preview_policy"]["commit_only_on_user_request"] is True, director_plan
        trusted_director = script_runner.approve_external_script_trust_window(context, session=True)
        assert trusted_director["ok"] and trusted_director["session"], trusted_director
        scripted_director_plan = _execute(
            context,
            "plan_director_workflow",
            {
                "prompt": (
                    "Director workflow: import a Poly Haven asset, build a named-part robot with custom "
                    "materials, animate it waving, capture evidence, and ask before commit."
                ),
                "target_objects": ["Cube"],
            },
        )
        scripted_director_names = [
            call["name"] for call in scripted_director_plan["next_tool_calls"]
        ]
        assert "plan_asset_import_workflow" in scripted_director_names, scripted_director_plan
        assert "plan_animation_workflow" in scripted_director_names, scripted_director_plan
        assert "draft_script" in scripted_director_names, scripted_director_plan
        assert "run_animation_workflow" not in scripted_director_names, scripted_director_plan
        assert "plan_advanced_scene_workflow" not in scripted_director_names, scripted_director_plan
        director_script_call = next(
            call
            for call in scripted_director_plan["next_tool_calls"]
            if call["name"] == "draft_script"
        )
        assert director_script_call["gateway_call_template"]["arguments"]["name"] == "draft_script"
        assert director_script_call["input_handoff"]["client_must_replace_placeholders"] is True
        assert director_script_call["input_handoff"]["completion_gate"][
            "require_asset_selection_and_import_when_requested"
        ] is True
        assert scripted_director_names.index("draft_script") < scripted_director_names.index(
            "capture_viewport"
        ), scripted_director_plan
        assert script_runner.revoke_external_script_trust_window(context)["ok"]
        details = _execute(context, "get_2d_animation_details", {"max_items": 12})
        assert "recommended_tools" in details

        _select_object(context, cube)
        material = _execute(
            context,
            "create_shader_material",
            {
                "name": "Agent Bridge Advanced Chrome",
                "base_color": [0.2, 0.45, 1.0, 1.0],
                "metallic": 0.8,
                "roughness": 0.22,
                "emission_color": [0.0, 0.25, 1.0, 1.0],
                "emission_strength": 0.2,
            },
        )
        assert material["material"] in bpy.data.materials
        assert cube.material_slots[0].material.name == material["material"]
        glass = _execute(
            context,
            "create_shader_material",
            {
                "name": "Agent Bridge Advanced Glass Preset",
                "preset": "clear_glass",
            },
        )
        assert glass["preset"] == "clear_glass", glass
        glass_material = bpy.data.materials[glass["material"]]
        assert round(float(glass_material.diffuse_color[3]), 2) == 0.32, tuple(glass_material.diffuse_color)
        assert cube.material_slots[0].material.name == glass["material"]
        glow = _execute(
            context,
            "create_shader_material",
            {
                "name": "Agent Bridge Advanced Screen Glow Preset",
                "preset": "screen_glow",
            },
        )
        assert glow["preset"] == "screen_glow", glow
        glow_material = bpy.data.materials[glow["material"]]
        glow_principled = next(node for node in glow_material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
        assert round(float(glow_principled.inputs["Emission Strength"].default_value), 1) == 2.4, glow["material"]
        chrome = _execute(
            context,
            "create_shader_material",
            {
                "name": "Agent Bridge Advanced Brushed Chrome Preset",
                "preset": "brushed_chrome",
            },
        )
        assert chrome["preset"] == "brushed_chrome", chrome
        chrome_material = bpy.data.materials[chrome["material"]]
        chrome_principled = next(node for node in chrome_material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
        assert round(float(chrome_principled.inputs["Metallic"].default_value), 1) == 1.0, chrome["material"]
        assert round(float(chrome_principled.inputs["Roughness"].default_value), 2) == 0.16, chrome["material"]
        enamel = _execute(
            context,
            "create_shader_material",
            {
                "name": "Agent Bridge Advanced Painted Enamel Preset",
                "preset": "painted_enamel",
            },
        )
        assert enamel["preset"] == "painted_enamel", enamel
        bpy.ops.object.select_all(action="DESELECT")
        unassigned_material = _execute(
            context,
            "create_shader_material",
            {
                "name": "Agent Bridge Advanced Unassigned Preset",
                "preset": "matte_ceramic",
            },
        )
        assert unassigned_material["preview_change_report"]["targets"] == [unassigned_material["material"]], unassigned_material
        _select_object(context, cube)
        existing_update = _execute(
            context,
            "create_shader_material",
            {
                "name": existing_material.name,
                "base_color": [0.7, 0.2, 0.2, 1.0],
                "metallic": 0.4,
                "roughness": 0.35,
            },
        )
        assert existing_update["material"] == existing_material.name
        shader_snapshot = live_preview.current_transaction()["before_state"][f"material:{existing_material.name}:shader"]
        assert "Principled BSDF" not in shader_snapshot["node_names"], shader_snapshot
        assert _material_topology(existing_material) != existing_topology

        seam_result = _execute(
            context,
            "mark_uv_seams",
            {
                "object_names": ["Cube"],
                "selected_only": False,
                "mode": "sharp_angle",
                "angle_degrees": 45.0,
                "clear_existing": True,
            },
        )
        assert seam_result["objects"][0]["marked_edges"] == 12, seam_result
        assert seam_result["objects"][0]["seams_after"] == 12, seam_result
        assert "mesh_data_snapshot" in seam_result["preview_change_report"]["rollback_scopes"], seam_result

        uv_result = _execute(
            context,
            "uv_unwrap",
            {
                "object_names": ["Cube"],
                "selected_only": False,
                "method": "smart_project",
                "uv_map_name": "Agent Bridge Advanced UVs",
                "replace_existing": True,
                "margin": 0.03,
            },
        )
        assert uv_result["method"] == "smart_project", uv_result
        assert uv_result["objects"][0]["uv_map"] == "Agent Bridge Advanced UVs", uv_result
        assert uv_result["objects"][0]["seam_count"] == 12, uv_result
        assert uv_result["objects"][0]["uv_bounds"], uv_result
        assert uv_result["objects"][0]["uv_area_sum"] > 0.0, uv_result
        assert "mesh_data_snapshot" in uv_result["preview_change_report"]["rollback_scopes"], uv_result
        uv_layer = cube.data.uv_layers.get("Agent Bridge Advanced UVs")
        assert uv_layer is not None, uv_result
        uv_values = [component for item in uv_layer.data for component in item.uv]
        assert uv_values and min(uv_values) >= 0.0 and max(uv_values) <= 1.0, uv_values
        uv_inspection = _execute(
            context,
            "inspect_uv_layout",
            {
                "object_names": ["Cube"],
                "selected_only": False,
                "uv_map_name": "Agent Bridge Advanced UVs",
                "max_overlap_pairs": 100,
            },
        )
        assert uv_inspection["passed"] is True, uv_inspection
        assert uv_inspection["issue_count"] == 0, uv_inspection
        assert uv_inspection["objects"][0]["seam_count"] == 12, uv_inspection
        assert uv_inspection["objects"][0]["has_uvs"] is True, uv_inspection
        assert uv_inspection["objects"][0]["uv_area_sum"] > 0.0, uv_inspection
        missing_uv_inspection = _execute(
            context,
            "inspect_uv_layout",
            {
                "object_names": ["Cube"],
                "selected_only": False,
                "uv_map_name": "Missing Agent Bridge UVs",
            },
        )
        assert missing_uv_inspection["passed"] is False, missing_uv_inspection
        assert missing_uv_inspection["issue_count"] == 1, missing_uv_inspection
        overlap_uv_result = _execute(
            context,
            "uv_unwrap",
            {
                "object_names": ["Cube"],
                "selected_only": False,
                "method": "planar_project",
                "uv_map_name": "Agent Bridge Overlap UVs",
                "replace_existing": True,
                "pack_islands": False,
                "projection_axis": "Z",
            },
        )
        assert overlap_uv_result["objects"][0]["possible_overlap_pairs"] > 0, overlap_uv_result
        assert overlap_uv_result["objects"][0]["layout_issues"], overlap_uv_result
        overlap_inspection = _execute(
            context,
            "inspect_uv_layout",
            {
                "object_names": ["Cube"],
                "selected_only": False,
                "uv_map_name": "Agent Bridge Overlap UVs",
                "max_overlap_pairs": 10,
            },
        )
        assert overlap_inspection["passed"] is False, overlap_inspection
        assert overlap_inspection["issue_count"] > 0, overlap_inspection
        assert overlap_inspection["objects"][0]["possible_overlap_pairs"] > 0, overlap_inspection
        assert any("overlapping UV" in issue for issue in overlap_inspection["objects"][0]["issues"]), overlap_inspection
        overlap_scan_disabled = _execute(
            context,
            "inspect_uv_layout",
            {
                "object_names": ["Cube"],
                "selected_only": False,
                "uv_map_name": "Agent Bridge Overlap UVs",
                "max_overlap_pairs": 0,
            },
        )
        assert overlap_scan_disabled["passed"] is True, overlap_scan_disabled
        assert overlap_scan_disabled["objects"][0]["possible_overlap_pairs"] == 0, overlap_scan_disabled
        assert overlap_scan_disabled["objects"][0]["overlap_pair_checks"] == 0, overlap_scan_disabled

        base_texture_path = os.path.join(tempfile.gettempdir(), "agent-bridge-smoke-base-color.png")
        arm_texture_path = os.path.join(tempfile.gettempdir(), "agent-bridge-smoke-arm.png")
        bump_texture_path = os.path.join(tempfile.gettempdir(), "agent-bridge-smoke-bump.png")
        displacement_texture_path = os.path.join(tempfile.gettempdir(), "agent-bridge-smoke-displacement.png")
        _write_test_image(base_texture_path, (0.8, 0.2, 0.1, 1.0))
        _write_test_image(arm_texture_path, (0.6, 0.35, 0.85, 1.0))
        _write_test_image(bump_texture_path, (0.5, 0.5, 0.5, 1.0))
        _write_test_image(displacement_texture_path, (0.4, 0.4, 0.4, 1.0))
        image_material = _execute(
            context,
            "create_image_texture_material",
            {
                "name": "Agent Bridge Advanced Image Texture Material",
                "base_color_path": base_texture_path,
                "arm_path": arm_texture_path,
                "bump_path": bump_texture_path,
                "displacement_path": displacement_texture_path,
                "object_names": ["Cube"],
                "selected_only": False,
                "uv_map_name": "Agent Bridge Advanced UVs",
                "bump_strength": 0.25,
                "bump_distance": 0.08,
                "replace_existing_links": False,
            },
        )
        assert image_material["material"] in bpy.data.materials
        assert {item["map_type"] for item in image_material["maps"]} == {"base_color", "ambient_occlusion", "roughness", "metallic", "bump"}, image_material
        assert any("displacement" in warning for warning in image_material["warnings"]), image_material
        assert cube.material_slots[0].material.name == image_material["material"]
        image_nodes = [node for node in bpy.data.materials[image_material["material"]].node_tree.nodes if node.type == "TEX_IMAGE"]
        material_nodes = {node.type for node in bpy.data.materials[image_material["material"]].node_tree.nodes}
        assert len(image_nodes) == 3, [node.name for node in image_nodes]
        assert {"SEPARATE_COLOR", "MIX_RGB", "BUMP", "UVMAP"}.issubset(material_nodes), material_nodes
        assert all(item.get("uv_map") == "Agent Bridge Advanced UVs" for item in image_material["maps"]), image_material
        assert "created_image" in image_material["preview_change_report"]["rollback_scopes"], image_material
        material = bpy.data.materials[image_material["material"]]
        material_inspection = _execute(
            context,
            "inspect_material_setup",
            {
                "material_names": [image_material["material"]],
                "object_names": ["Cube"],
                "selected_only": False,
                "require_uv_maps": True,
                "expected_uv_map_name": "Agent Bridge Advanced UVs",
            },
        )
        assert material_inspection["passed"] is True, material_inspection
        assert material_inspection["issue_count"] == 0, material_inspection
        first_texture_report = material_inspection["materials"][0]["textures"][0]
        assert first_texture_report["image_datablock_name"], first_texture_report
        assert first_texture_report["source_filename"], first_texture_report
        assert first_texture_report["source_filepath"], first_texture_report
        packed_channel_links = []
        for link in list(material.node_tree.links):
            if link.from_node.type == "SEPARATE_COLOR":
                packed_channel_links.append((link.from_socket, link.to_socket))
                material.node_tree.links.remove(link)
        broken_packed_inspection = _execute(
            context,
            "inspect_material_setup",
            {
                "material_names": [image_material["material"]],
                "object_names": ["Cube"],
                "selected_only": False,
                "require_uv_maps": True,
                "expected_uv_map_name": "Agent Bridge Advanced UVs",
            },
        )
        assert broken_packed_inspection["passed"] is False, broken_packed_inspection
        assert any("packed arm" in issue for issue in broken_packed_inspection["materials"][0]["issues"]), broken_packed_inspection
        for from_socket, to_socket in packed_channel_links:
            material.node_tree.links.new(from_socket, to_socket)
        arm_image_name = next(item["image"] for item in image_material["maps"] if item.get("source_map") == "arm")
        bpy.data.images[arm_image_name].colorspace_settings.name = "sRGB"
        for node in image_nodes:
            vector_input = node.inputs.get("Vector")
            if vector_input:
                for link in list(vector_input.links):
                    material.node_tree.links.remove(link)
        broken_material_inspection = _execute(
            context,
            "inspect_material_setup",
            {
                "material_names": [image_material["material"]],
                "object_names": ["Cube"],
                "selected_only": False,
                "require_uv_maps": True,
                "expected_uv_map_name": "Agent Bridge Advanced UVs",
            },
        )
        assert broken_material_inspection["passed"] is False, broken_material_inspection
        assert any("colorspace" in issue for issue in broken_material_inspection["materials"][0]["issues"]), broken_material_inspection
        assert not any("UV Map vector input" in issue for issue in broken_material_inspection["materials"][0]["issues"]), broken_material_inspection
        assert all(
            texture.get("uv_mode") == "implicit_active_uv"
            for texture in broken_material_inspection["materials"][0]["textures"]
        ), broken_material_inspection
        material_repair = _execute(
            context,
            "repair_material_setup",
            {
                "material_names": [image_material["material"]],
                "object_names": ["Cube"],
                "selected_only": False,
                "uv_map_name": "Agent Bridge Advanced UVs",
            },
        )
        repair_types = {
            repair["type"]
            for material_item in material_repair["materials"]
            for repair in material_item["repairs"]
        }
        assert {"color_space", "uv_relink"}.issubset(repair_types), material_repair
        assert material_repair["post_inspection"]["passed"] is True, material_repair
        repaired_material_inspection = _execute(
            context,
            "inspect_material_setup",
            {
                "material_names": [image_material["material"]],
                "object_names": ["Cube"],
                "selected_only": False,
                "require_uv_maps": True,
                "expected_uv_map_name": "Agent Bridge Advanced UVs",
            },
        )
        assert repaired_material_inspection["passed"] is True, repaired_material_inspection
        node_names_before_cautious_update = [node.name for node in material.node_tree.nodes]
        cautious_update = _execute(
            context,
            "create_image_texture_material",
            {
                "name": image_material["material"],
                "base_color_path": base_texture_path,
                "arm_path": arm_texture_path,
                "bump_path": bump_texture_path,
                "replace_existing_links": False,
                "assign_to_objects": False,
            },
        )
        assert cautious_update["maps"] == [], cautious_update
        assert any("target socket is already linked" in warning for warning in cautious_update["warnings"]), cautious_update
        assert [node.name for node in material.node_tree.nodes] == node_names_before_cautious_update, cautious_update

        bake_dir = tempfile.mkdtemp(prefix="agent-bridge-bake-smoke-")
        baked_maps = _execute(
            context,
            "bake_maps",
            {
                "object_names": ["Cube"],
                "selected_only": False,
                "map_types": ["ao", "normal", "diffuse"],
                "output_dir": bake_dir,
                "resolution": 32,
                "margin": 2,
                "samples": 4,
                "uv_map_name": "Agent Bridge Advanced UVs",
            },
        )
        assert baked_maps["baked_map_count"] == 3, baked_maps
        assert {item["map_type"] for item in baked_maps["baked_maps"]} == {"ambient_occlusion", "normal", "base_color"}, baked_maps
        for baked_map in baked_maps["baked_maps"]:
            assert baked_map["available"] is True, baked_map
            assert baked_map["width"] == 32 and baked_map["height"] == 32, baked_map
            assert baked_map["size_bytes"] > 0, baked_map
            assert os.path.isfile(baked_map["path"]), baked_map
        assert not [node for node in material.node_tree.nodes if node.name.startswith("Agent Bridge Bake Target")]
        assert "scene_render_settings" in baked_maps["preview_change_report"]["rollback_scopes"], baked_maps
        invalid_bake = json.loads(tool_dispatcher.execute_tool(context, "bake_maps", {"map_types": ["curvature"]}))
        assert invalid_bake["ok"] is False, invalid_bake
        assert "Unsupported bake map type" in invalid_bake["message"], invalid_bake

        procedural_material = _execute(
            context,
            "create_procedural_texture_material",
            {
                "name": "Agent Bridge Procedural Wood Smoke",
                "preset": "wood_wave",
                "object_names": ["Cube"],
                "selected_only": False,
                "bump_strength": 0.07,
            },
        )
        assert procedural_material["texture_type"] == "wave", procedural_material
        assert procedural_material["base_color_linked"] is True, procedural_material
        assert procedural_material["bump_linked"] is True, procedural_material
        assert "Cube" in procedural_material["assigned_objects"], procedural_material
        procedural = bpy.data.materials[procedural_material["material"]]
        procedural_node_names = {node.name for node in procedural.node_tree.nodes}
        assert "Agent Bridge Wave Procedural Texture" in procedural_node_names, procedural_node_names
        assert "Agent Bridge Procedural Color Ramp" in procedural_node_names, procedural_node_names
        procedural_nodes_before_cautious_update = [node.name for node in procedural.node_tree.nodes]
        cautious_procedural_update = _execute(
            context,
            "create_procedural_texture_material",
            {
                "name": procedural_material["material"],
                "preset": "marble_noise",
                "replace_existing_links": False,
                "assign_to_objects": False,
            },
        )
        assert cautious_procedural_update["nodes"] == [], cautious_procedural_update
        assert cautious_procedural_update["base_color_linked"] is False, cautious_procedural_update
        assert cautious_procedural_update["bump_linked"] is False, cautious_procedural_update
        assert len([warning for warning in cautious_procedural_update["warnings"] if "target socket is already linked" in warning]) >= 2, cautious_procedural_update
        assert [node.name for node in procedural.node_tree.nodes] == procedural_nodes_before_cautious_update, cautious_procedural_update
        invalid_procedural = json.loads(
            tool_dispatcher.execute_tool(context, "create_procedural_texture_material", {"texture_type": "not_a_texture"})
        )
        assert invalid_procedural["ok"] is False, invalid_procedural
        assert "Unsupported procedural texture type" in invalid_procedural["message"], invalid_procedural

        valid_engines = {
            item.identifier
            for item in scene.render.bl_rna.properties["engine"].enum_items
        }
        target_engine = "CYCLES" if "CYCLES" in valid_engines else scene.render.engine
        render_engine = _execute(
            context,
            "set_render_engine",
            {
                "engine": target_engine,
                "quality_preset": "preview",
                "samples": 16,
                "denoise": True,
                "view_transform": scene.view_settings.view_transform,
                "look": scene.view_settings.look,
                "exposure": 0.15,
                "gamma": 1.0,
            },
        )
        assert render_engine["applied"]["engine"] == target_engine, render_engine
        assert render_engine["quality_preset"] == "preview", render_engine
        assert render_engine["applied"].get("cycles_samples", 16) <= 16 or scene.render.engine != "CYCLES", render_engine
        assert round(float(scene.view_settings.exposure), 2) == 0.15

        render_outputs = _execute(
            context,
            "configure_render_outputs",
            {
                "enabled_passes": ["normal", "depth", "ambient_occlusion", "cryptomatte_object"],
                "disabled_passes": ["vector"],
                "aovs": [{"name": "AgentBridgeMask", "type": "COLOR"}, {"name": "AgentBridgeDepthHint", "type": "VALUE"}],
                "clear_existing_aovs": True,
                "pass_cryptomatte_depth": 4,
                "pass_alpha_threshold": 0.2,
            },
        )
        assert render_outputs["applied_passes"].get("use_pass_normal") is True, render_outputs
        assert render_outputs["applied_passes"].get("use_pass_z") is True, render_outputs
        assert render_outputs["applied_passes"].get("use_pass_ambient_occlusion") is True, render_outputs
        assert render_outputs["applied_passes"].get("use_pass_vector") is False, render_outputs
        if hasattr(context.view_layer, "use_pass_cryptomatte_object"):
            assert context.view_layer.use_pass_cryptomatte_object is True, render_outputs
        if hasattr(context.view_layer, "pass_cryptomatte_depth"):
            assert context.view_layer.pass_cryptomatte_depth == 4, render_outputs
        aov_summary = {(item["name"], item["type"]) for item in render_outputs["aovs"]}
        assert ("AgentBridgeMask", "COLOR") in aov_summary, render_outputs
        assert ("AgentBridgeDepthHint", "VALUE") in aov_summary, render_outputs

        invalid_render_outputs = json.loads(
            tool_dispatcher.execute_tool(context, "configure_render_outputs", {"enabled_passes": ["not_a_render_pass"]})
        )
        assert invalid_render_outputs["ok"] is False, invalid_render_outputs
        assert "Unsupported render pass" in invalid_render_outputs["message"], invalid_render_outputs

        phase2_render = _execute(
            context,
            "capture_object_inspection_renders",
            {
                "object_names": ["Cube"],
                "views": ["front"],
                "resolution_x": 240,
                "resolution_y": 180,
                "distance_factor": 2.6,
                "note": "Phase 2 packed PBR look-dev smoke",
            },
        )["inspection_render"]
        assert phase2_render["available"] is True, phase2_render
        assert len(phase2_render["images"]) == 1, phase2_render
        assert phase2_render["images"][0]["available"] is True, phase2_render
        assert os.path.isfile(phase2_render["images"][0]["path"]), phase2_render

        lookdev_review = _execute(
            context,
            "create_lookdev_turntable_review",
            {
                "target_name": "Cube",
                "frame_start": 1,
                "frame_end": 48,
                "quality_preset": "preview",
                "samples": 8,
                "views": ["front"],
                "resolution_x": 160,
                "resolution_y": 120,
                "distance_factor": 2.6,
            },
        )
        assert lookdev_review["setup"]["ok"] is True, lookdev_review
        assert lookdev_review["render_settings"]["quality_preset"] == "preview", lookdev_review
        validation = lookdev_review["artifact_validation"]
        assert validation["ok"] is True, lookdev_review
        assert validation["available_image_count"] == 1, lookdev_review
        assert validation["images"][0]["size_bytes"] > 0, lookdev_review
        assert os.path.isfile(validation["images"][0]["path"]), lookdev_review

        geometry_nodes = _execute(
            context,
            "add_geometry_nodes_modifier",
            {"name": "Agent Bridge Advanced GN", "node_group_name": "Agent Bridge Advanced GN Group", "template": "transform"},
        )
        assert geometry_nodes["node_group"] in bpy.data.node_groups
        assert geometry_nodes["template"] == "transform", geometry_nodes
        assert not geometry_nodes["warnings"], geometry_nodes
        assert bpy.data.node_groups[geometry_nodes["node_group"]].nodes.get("Agent Bridge Transform Geometry")
        assert cube.modifiers.get("Agent Bridge Advanced GN")
        set_position_nodes = _execute(
            context,
            "add_geometry_nodes_modifier",
            {"name": "Agent Bridge Advanced GN Set Position", "node_group_name": "Agent Bridge Advanced GN Set Position Group", "template": "set_position"},
        )
        assert set_position_nodes["template"] == "set_position", set_position_nodes
        assert bpy.data.node_groups[set_position_nodes["node_group"]].nodes.get("Agent Bridge Set Position")
        subdivide_nodes = _execute(
            context,
            "add_geometry_nodes_modifier",
            {"name": "Agent Bridge Advanced GN Subdivide", "node_group_name": "Agent Bridge Advanced GN Subdivide Group", "template": "subdivide_mesh"},
        )
        assert subdivide_nodes["template"] == "subdivide_mesh", subdivide_nodes
        assert bpy.data.node_groups[subdivide_nodes["node_group"]].nodes.get("Agent Bridge Subdivide Mesh")

        procedural = _execute(
            context,
            "apply_procedural_array_stack",
            {"object_names": ["Cube"], "selected_only": False, "count": 3, "name_prefix": "Agent Bridge Advanced Procedural"},
        )
        assert procedural["objects"][0]["object"] == "Cube"
        assert cube.modifiers.get("Agent Bridge Advanced Procedural Array")

        extruded = _execute(
            context,
            "edit_mesh",
            {
                "operation": "extrude_faces",
                "object_names": ["Cube"],
                "selected_only": False,
                "face_scope": "TOP",
                "direction": "AXIS",
                "axis": "Z",
                "distance": 0.2,
            },
        )
        assert extruded["objects"][0]["after"]["vertices"] > extruded["objects"][0]["before"]["vertices"], extruded
        inset = _execute(
            context,
            "edit_mesh",
            {
                "operation": "inset_faces",
                "object_names": ["Cube"],
                "selected_only": False,
                "face_scope": "TOP",
                "inset_thickness": 0.04,
            },
        )
        assert inset["objects"][0]["after"]["faces"] >= inset["objects"][0]["before"]["faces"], inset
        bridged = _execute(
            context,
            "edit_mesh",
            {"operation": "bridge_boundary_loops", "object_names": [bridge_fixture.name], "selected_only": False},
        )
        assert bridged["objects"][0]["after"]["faces"] > bridged["objects"][0]["before"]["faces"], bridged
        merged = _execute(
            context,
            "edit_mesh",
            {"operation": "merge_by_distance", "object_names": [merge_fixture.name], "selected_only": False, "merge_distance": 0.01},
        )
        assert merged["objects"][0]["after"]["vertices"] < merged["objects"][0]["before"]["vertices"], merged
        dissolved = _execute(
            context,
            "edit_mesh",
            {"operation": "dissolve_degenerate", "object_names": [dissolve_fixture.name], "selected_only": False, "merge_distance": 0.01},
        )
        assert dissolved["objects"][0]["after"]["vertices"] < dissolved["objects"][0]["before"]["vertices"], dissolved
        loop_cut = _execute(
            context,
            "edit_mesh",
            {"operation": "loop_cut", "object_names": [loop_fixture.name], "selected_only": False, "loop_cuts": 2, "cut_axis": "X"},
        )
        assert loop_cut["objects"][0]["after"]["vertices"] > loop_cut["objects"][0]["before"]["vertices"], loop_cut
        assert loop_cut["objects"][0]["details"]["mode"] == "bounded_planar_loop", loop_cut
        assert loop_cut["objects"][0]["details"]["axis"] == "X", loop_cut
        assert len(loop_cut["objects"][0]["details"]["positions"]) == 2, loop_cut
        knife_cut = _execute(
            context,
            "edit_mesh",
            {"operation": "knife_cut", "object_names": [knife_fixture.name], "selected_only": False, "cut_axis": "Z", "cut_position": 0.0},
        )
        assert knife_cut["objects"][0]["after"]["edges"] > knife_cut["objects"][0]["before"]["edges"], knife_cut
        proportional_before = [vertex.co.z for vertex in proportional_fixture.data.vertices]
        proportional = _execute(
            context,
            "edit_mesh",
            {
                "operation": "proportional_edit",
                "object_names": [proportional_fixture.name],
                "selected_only": False,
                "axis": "Z",
                "distance": 0.25,
                "proportional_center": [0.0, 0.0, 0.0],
                "proportional_radius": 0.6,
                "proportional_falloff": "LINEAR",
            },
        )
        assert proportional["objects"][0]["after"] == proportional["objects"][0]["before"], proportional
        assert any(vertex.co.z > before for vertex, before in zip(proportional_fixture.data.vertices, proportional_before)), proportional

        cutter = _execute(
            context,
            "create_primitive",
            {
                "primitive_type": "CUBE",
                "name": "Agent Bridge Boolean Cutter",
                "location": [0.6, 0.0, 0.0],
                "scale": [0.35, 0.35, 0.35],
            },
        )
        assert cutter["object"] in bpy.data.objects
        boolean = _execute(
            context,
            "boolean_op",
            {
                "target_object_name": "Cube",
                "cutter_object_names": [cutter["object"]],
                "operation": "DIFFERENCE",
                "solver": "FAST",
                "name_prefix": "Agent Bridge Advanced Boolean",
            },
        )
        boolean_modifier = cube.modifiers.get(boolean["modifiers"][0]["name"])
        assert boolean_modifier and boolean_modifier.type == "BOOLEAN", boolean
        assert boolean_modifier.operation == "DIFFERENCE", boolean
        assert boolean_modifier.object == bpy.data.objects[cutter["object"]], boolean

        mirror = _execute(
            context,
            "mirror_model",
            {
                "object_names": ["Cube"],
                "selected_only": False,
                "use_axis": [True, False, False],
                "name": "Agent Bridge Advanced Mirror",
            },
        )
        assert mirror["axis"] == ["X"], mirror
        mirror_modifier = cube.modifiers.get("Agent Bridge Advanced Mirror")
        assert mirror_modifier and mirror_modifier.type == "MIRROR", mirror
        assert tuple(bool(item) for item in mirror_modifier.use_axis) == (True, False, False), mirror

        symmetry = _execute(
            context,
            "symmetrize_model",
            {
                "object_names": ["Cube"],
                "selected_only": False,
                "axis": "Y",
                "direction": "NEGATIVE_TO_POSITIVE",
                "name": "Agent Bridge Advanced Symmetry",
            },
        )
        symmetry_modifier = cube.modifiers.get("Agent Bridge Advanced Symmetry")
        assert symmetry["axis"] == "Y", symmetry
        assert symmetry_modifier and symmetry_modifier.type == "MIRROR", symmetry
        assert tuple(bool(item) for item in symmetry_modifier.use_bisect_axis) == (False, True, False), symmetry

        solidify = _execute(
            context,
            "solidify_model",
            {
                "object_names": ["Cube"],
                "selected_only": False,
                "thickness": 0.08,
                "offset": 0.0,
                "name": "Agent Bridge Advanced Solidify",
            },
        )
        solidify_modifier = cube.modifiers.get("Agent Bridge Advanced Solidify")
        assert solidify_modifier and solidify_modifier.type == "SOLIDIFY", solidify
        assert round(float(solidify_modifier.thickness), 3) == 0.08, solidify
        screw = _execute(
            context,
            "screw_model",
            {
                "object_names": [loop_fixture.name],
                "selected_only": False,
                "axis": "Z",
                "angle": 6.283185307179586,
                "screw_offset": 0.35,
                "iterations": 2,
                "steps": 12,
                "name": "Agent Bridge Advanced Screw",
            },
        )
        screw_modifier = loop_fixture.modifiers.get("Agent Bridge Advanced Screw")
        assert screw_modifier and screw_modifier.type == "SCREW", screw
        assert screw["axis"] == "Z", screw
        assert round(float(screw_modifier.screw_offset), 3) == 0.35, screw

        _select_object(context, cube)
        shape_key = _execute(context, "create_shape_key", {"object_name": "Cube", "key_name": "Agent Bridge Bulge", "value": 0.25})
        assert shape_key["shape_key"] in cube.data.shape_keys.key_blocks
        _execute(
            context,
            "animate_shape_key",
            {
                "object_name": "Cube",
                "key_name": "Agent Bridge Bulge",
                "frame_start": 1,
                "frame_end": 40,
                "value_start": 0.0,
                "value_end": 1.0,
            },
        )
        assert cube.data.shape_keys.animation_data and cube.data.shape_keys.animation_data.action

        particles = _execute(
            context,
            "add_particle_system_to_selected",
            {"name": "Agent Bridge Advanced Particles", "count": 12, "frame_start": 1, "frame_end": 20, "lifetime": 30},
        )
        assert particles["objects"] == ["Cube"]
        assert cube.modifiers.get("Agent Bridge Advanced Particles")

        fur_mask = cube.vertex_groups.new(name="Agent Bridge Fur Mask")
        fur_mask.add(
            [vertex.index for vertex in cube.data.vertices],
            1.0,
            "REPLACE",
        )
        fur_curves = _execute(
            context,
            "create_directional_fur_curves",
            {
                "object_names": ["Cube"],
                "selected_only": False,
                "name_prefix": "Agent Bridge Advanced Fur",
                "count": 18,
                "length": 0.12,
                "root_width": 0.003,
                "tip_width": 0.0003,
                "flow_direction": [1.0, 0.0, 0.0],
                "curve_points": 5,
                "minimum_spacing": 0.02,
                "clump_strength": 0.2,
                "clump_size": 4,
                "noise_strength": 0.05,
                "flow_controls": [
                    {
                        "location": [0.0, 0.0, 0.0],
                        "direction": [0.0, 1.0, 0.0],
                        "radius": 5.0,
                        "strength": 0.5,
                    }
                ],
                "regions": [
                    {
                        "name": "coat",
                        "vertex_group": fur_mask.name,
                        "count": 12,
                        "length": 0.1,
                    },
                    {
                        "name": "fluff",
                        "count": 6,
                        "length": 0.16,
                        "normal_lift": 0.5,
                    },
                ],
                "seed": 11,
            },
        )
        fur_object = bpy.data.objects[fur_curves["created"][0]["object"]]
        assert fur_object.type == "CURVE", fur_curves
        assert len(fur_object.data.splines) == fur_curves["created"][0]["strand_count"], fur_curves
        assert fur_object["agent_bridge_fur_kind"] == "directional_surface_curves_v2", fur_curves
        assert {region["name"] for region in fur_curves["created"][0]["regions"]} == {"coat", "fluff"}, fur_curves
        first_fur_spline = fur_object.data.splines[0]
        assert first_fur_spline.points[0].radius > first_fur_spline.points[-1].radius, fur_curves

        empty_fur_mask = cube.vertex_groups.new(
            name="Agent Bridge Empty Fur Mask"
        )
        existing_fur_material = bpy.data.materials.new(
            "Agent Bridge Existing Fur Material"
        )
        existing_fur_material.diffuse_color = (1.0, 0.0, 0.0, 1.0)
        fur_failure_transaction = live_preview.current_transaction()
        fur_failure_state = (
            fur_failure_transaction["id"],
            len(fur_failure_transaction["before_state"]),
            len(fur_failure_transaction["applied_steps"]),
        )
        failed_empty_fur = json.loads(
            tool_dispatcher.execute_tool(
                context,
                "create_directional_fur_curves",
                {
                    "object_names": ["Cube"],
                    "selected_only": False,
                    "material_name": existing_fur_material.name,
                    "color": [0.0, 1.0, 0.0, 1.0],
                    "count": 8,
                    "regions": [
                        {
                            "name": "empty",
                            "vertex_group": empty_fur_mask.name,
                        }
                    ],
                },
            )
        )
        assert (
            failed_empty_fur["code"] == "no_fur_samples"
        ), failed_empty_fur
        assert tuple(existing_fur_material.diffuse_color) == (
            1.0,
            0.0,
            0.0,
            1.0,
        ), failed_empty_fur
        assert live_preview.current_transaction() is fur_failure_transaction
        assert (
            fur_failure_transaction["id"],
            len(fur_failure_transaction["before_state"]),
            len(fur_failure_transaction["applied_steps"]),
        ) == fur_failure_state, failed_empty_fur
        cube.vertex_groups.remove(empty_fur_mask)
        bpy.data.materials.remove(existing_fur_material)

        concave_mesh = bpy.data.meshes.new("Agent Bridge Concave Fur Surface")
        concave_mesh.from_pydata(
            [
                (0.0, 0.0, 0.0),
                (3.0, 0.0, 0.0),
                (3.0, 3.0, 0.0),
                (2.0, 3.0, 0.0),
                (2.0, 1.0, 0.0),
                (1.0, 1.0, 0.0),
                (1.0, 3.0, 0.0),
                (0.0, 3.0, 0.0),
            ],
            [],
            [tuple(range(8))],
        )
        concave_object = bpy.data.objects.new(
            "Agent Bridge Concave Fur Surface",
            concave_mesh,
        )
        scene.collection.objects.link(concave_object)
        solidify = concave_object.modifiers.new(
            "Agent Bridge Concave Fur Solidify",
            "SOLIDIFY",
        )
        solidify.thickness = 0.2
        evaluated_triangles, triangle_warning = (
            advanced_rigging._surface_triangles(concave_object)
        )
        evaluated_area = sum(
            advanced_rigging.fur_groom.triangle_area(item["vertices"])
            for item in evaluated_triangles
        )
        assert not triangle_warning, triangle_warning
        assert len(evaluated_triangles) > 6, evaluated_triangles
        assert evaluated_area > 14.0, evaluated_area
        bpy.data.objects.remove(concave_object, do_unlink=True)
        bpy.data.meshes.remove(concave_mesh)

        failed_fur_inventory = (
            set(bpy.data.objects.keys()),
            set(bpy.data.curves.keys()),
            set(bpy.data.materials.keys()),
        )
        failed_fur = json.loads(
            tool_dispatcher.execute_tool(
                context,
                "create_directional_fur_curves",
                {
                "object_names": ["Cube"],
                "selected_only": False,
                "name_prefix": "Agent Bridge Missing Mask Fur",
                "count": 8,
                "regions": [
                    {
                        "name": "missing",
                        "vertex_group": "Agent Bridge Missing Fur Mask",
                    }
                ],
                },
            )
        )
        assert not failed_fur["ok"] and failed_fur["code"] == "no_fur_samples", failed_fur
        assert (
            set(bpy.data.objects.keys()),
            set(bpy.data.curves.keys()),
            set(bpy.data.materials.keys()),
        ) == failed_fur_inventory, failed_fur

        cloth = _execute(
            context,
            "add_cloth_simulation_to_selected",
            {"object_names": ["Cube"], "selected_only": False, "name": "Agent Bridge Advanced Cloth", "quality": 3},
        )
        assert cloth["objects"][0]["modifier"] == "Agent Bridge Advanced Cloth"
        assert cube.modifiers.get("Agent Bridge Advanced Cloth")

        text = _execute(
            context,
            "create_text_object",
            {
                "name": "Agent Bridge Advanced Label",
                "body": "Advanced",
                "location": [0.0, -2.0, 1.5],
                "rotation": [1.5708, 0.0, 0.0],
                "scale": [1.0, 1.0, 1.0],
                "size": 0.5,
                "color": [0.8, 0.95, 1.0, 1.0],
            },
        )
        assert bpy.data.objects[text["object"]].type == "FONT"

        curve = _execute(
            context,
            "create_curve_path",
            {
                "name": "Agent Bridge Advanced Path",
                "points": [[-1.0, 0.0, 0.0], [0.0, 0.6, 1.0], [1.0, 0.0, 0.0]],
                "bevel_depth": 0.03,
                "color": [0.0, 0.6, 1.0, 1.0],
            },
        )
        assert bpy.data.objects[curve["object"]].type == "CURVE"

        reference_guides = _execute(
            context,
            "create_reference_modeling_guides",
            {
                "image_size": [1000, 1000],
                "coordinate_space": "normalized",
                "subject": "gray cartoon kitten",
                "collection_name": "Agent Bridge Kitten Reference Guides",
                "include_image_plane": False,
                "plane_height": 3.0,
                "landmarks": [
                    {"name": "left_eye", "point": [0.35, 0.32]},
                    {"name": "right_eye", "point": [0.65, 0.32]},
                    {"name": "nose", "point": [0.50, 0.44]},
                ],
                "curves": [
                    {
                        "name": "head_outline",
                        "points": [[0.18, 0.18], [0.82, 0.18], [0.84, 0.58], [0.50, 0.72], [0.16, 0.58]],
                        "cyclic": True,
                    }
                ],
                "masses": [
                    {"name": "head", "center": [0.5, 0.36], "radius": [0.32, 0.25]},
                ],
                "measurements": [
                    {"name": "eye_span", "from": "left_eye", "to": "right_eye"},
                ],
            },
        )
        assert reference_guides["collection"] in bpy.data.collections
        assert len(reference_guides["landmarks"]) == 3, reference_guides
        assert len(reference_guides["curves"]) == 1, reference_guides
        assert len(reference_guides["masses"]) == 1, reference_guides
        assert len(reference_guides["measurements"]) == 1, reference_guides
        assert reference_guides["reference_brief_seed"]["subject"] == "gray cartoon kitten", reference_guides
        inspected_guides = _execute(
            context,
            "inspect_reference_modeling_guides",
            {"collection_name": reference_guides["collection"], "include_points": True, "max_points_per_curve": 8},
        )
        inspected_collection = inspected_guides["collections"][0]
        assert inspected_guides["totals"]["landmarks"] == 3, inspected_guides
        assert inspected_guides["totals"]["curves"] == 1, inspected_guides
        assert inspected_guides["totals"]["masses"] == 1, inspected_guides
        assert inspected_guides["totals"]["measurements"] == 1, inspected_guides
        assert inspected_collection["subject"] == "gray cartoon kitten", inspected_guides
        assert inspected_collection["curves"][0]["world_points"], inspected_guides
        assert live_preview.current_transaction()["status"] == "pending", reference_guides

        no_plane_reference_guides = _execute(
            context,
            "create_reference_modeling_guides",
            {
                "image_path": persistent_reference_path,
                "include_image_plane": False,
                "landmarks": [
                    {"name": "center", "point": [0.5, 0.5]},
                ],
            },
        )
        assert no_plane_reference_guides["ok"] is True, no_plane_reference_guides
        assert (
            bpy.data.images.get(persistent_reference_name)
            is persistent_reference_image
        )
        annotation_image_path = persistent_reference_path
        scene.render.pixel_aspect_x = 2.0
        scene.render.pixel_aspect_y = 1.0
        annotation_guides = _execute(
            context,
            "create_reference_guides_from_annotations",
            {
                "image_path": annotation_image_path,
                "annotations_json": json.dumps(
                    {
                        "version": 1,
                        "subject": "annotation pipeline subject",
                        "coordinate_space": "pixel",
                        "origin": "top_left",
                        "image_size": [1000, 600],
                        "image_rect": [100, 100, 800, 400],
                        "landmarks": [
                            {"name": "center", "point": [500, 300]},
                            {"name": "upper", "point": [500, 180]},
                        ],
                        "outlines": [
                            {
                                "name": "primary_outline",
                                "points": [
                                    [100, 100],
                                    [900, 100],
                                    [900, 500],
                                    [100, 500],
                                ],
                                "closed": True,
                            }
                        ],
                        "masses": [
                            {
                                "name": "primary_mass",
                                "bbox": [300, 200, 400, 200],
                            }
                        ],
                        "measurements": [
                            {
                                "name": "vertical_span",
                                "from": "center",
                                "to": "upper",
                            }
                        ],
                    }
                ),
                "collection_name": "Agent Bridge Annotation Pipeline Guides",
                "plane_height": 3.0,
                "create_camera": True,
                "activate_camera": True,
            },
        )
        assert annotation_guides["image_size"] == [400.0, 200.0], annotation_guides
        assert abs(annotation_guides["plane"]["width"] - 6.0) < 1e-6, annotation_guides
        assert annotation_guides["annotation_source"]["kind"] == "json", annotation_guides
        assert len(annotation_guides["annotation_source"]["sha256"]) == 64, annotation_guides
        assert len(annotation_guides["reference_identity"]["sha256"]) == 64, annotation_guides
        assert annotation_guides["annotation_summary"]["counts"]["landmarks"] == 2, annotation_guides
        assert annotation_guides["annotation_summary"]["counts"]["outlines"] == 1, annotation_guides
        world_per_pixel = annotation_guides["calibration"]["world_units_per_reference_pixel"]
        assert abs(world_per_pixel[0] - 0.015) < 1e-6, annotation_guides
        assert abs(world_per_pixel[1] - 0.015) < 1e-6, annotation_guides
        center_location = annotation_guides["landmarks"][0]["location"]
        assert abs(center_location[0]) < 1e-6, annotation_guides
        assert abs(center_location[2] - 1.5) < 1e-6, annotation_guides
        annotation_camera = bpy.data.objects[annotation_guides["camera"]["object"]]
        assert annotation_camera.type == "CAMERA", annotation_guides
        assert annotation_camera.data.type == "ORTHO", annotation_guides
        assert abs(annotation_camera.data.ortho_scale - 3.3) < 1e-6, annotation_guides
        assert annotation_guides["camera"]["render_resolution"] == [400, 200], annotation_guides
        assert annotation_guides["camera"]["render_aspect_matched"], annotation_guides
        assert scene.render.resolution_x == 400, annotation_guides
        assert scene.render.resolution_y == 200, annotation_guides
        assert scene.render.pixel_aspect_x == 1.0, annotation_guides
        assert scene.render.pixel_aspect_y == 1.0, annotation_guides
        assert scene.camera == annotation_camera, annotation_guides
        invalid_camera_comparison = json.loads(
            tool_dispatcher.execute_tool(
                context,
                "compare_model_to_reference",
                {
                    "collection_name": annotation_guides["collection"],
                    "camera_name": camera.name,
                    "object_names": ["Cube"],
                    "selected_only": False,
                },
            )
        )
        assert not invalid_camera_comparison["ok"], invalid_camera_comparison
        assert "calibrated" in invalid_camera_comparison["message"].lower() or (
            "not part" in invalid_camera_comparison["message"].lower()
        ), invalid_camera_comparison
        inspected_annotations = _execute(
            context,
            "inspect_reference_modeling_guides",
            {
                "collection_name": annotation_guides["collection"],
                "include_points": True,
                "max_points_per_curve": 8,
            },
        )
        inspected_annotation_collection = inspected_annotations["collections"][0]
        assert inspected_annotations["totals"]["cameras"] == 1, inspected_annotations
        assert inspected_annotation_collection["camera"] == annotation_camera.name, inspected_annotations
        assert (
            inspected_annotation_collection["cameras"][0]["render_resolution"]
            == [400, 200]
        ), inspected_annotations
        assert (
            inspected_annotation_collection["annotation_pipeline"]["source"]["sha256"]
            == annotation_guides["annotation_source"]["sha256"]
        ), inspected_annotations
        assert live_preview.current_transaction()["status"] == "pending", annotation_guides
        comparison_render_state = (
            scene.render.resolution_x,
            scene.render.resolution_y,
            scene.render.resolution_percentage,
            scene.render.pixel_aspect_x,
            scene.render.pixel_aspect_y,
        )
        cube_hide_render = cube.hide_render
        reference_comparison = _execute(
            context,
            "compare_model_to_reference",
            {
                "collection_name": annotation_guides["collection"],
                "object_names": ["Cube"],
                "selected_only": False,
                "outline_name": "primary_outline",
                "reference_mask_source": "outline",
                "landmark_targets": [
                    {"name": "center", "object_name": "Cube"}
                ],
                "max_axis": 256,
            },
        )
        assert reference_comparison["ok"], reference_comparison
        assert (
            0.0
            < reference_comparison["metrics"]["silhouette_iou"]
            <= 1.0
        ), reference_comparison
        assert reference_comparison["metrics"]["error_regions"], reference_comparison
        assert reference_comparison["landmark_errors"], reference_comparison
        assert (
            reference_comparison["reference_identity"]["sha256"]
            == annotation_guides["reference_identity"]["sha256"]
        ), reference_comparison
        original_validate_reference_target = (
            quality_benchmarks.validate_reference_evaluation_target
        )
        original_compare_reference = (
            reference_comparison_module.compare_model_to_reference
        )
        try:
            quality_benchmarks.validate_reference_evaluation_target = (
                lambda _run_id: {
                    "ok": True,
                    "run": {
                        "reference_identity": {
                            "sha256": "0" * 64,
                            "reproducible": True,
                        }
                    },
                }
            )

            def _unexpected_reference_render(*_args, **_kwargs):
                raise AssertionError(
                    "mismatched benchmark reference should fail before render"
                )

            reference_comparison_module.compare_model_to_reference = (
                _unexpected_reference_render
            )
            mismatched_benchmark_reference = (
                reference_benchmark_scene.evaluate_reference_model_benchmark(
                    context,
                    run_id="mismatched-reference-fixture",
                    collection_name=annotation_guides["collection"],
                )
            )
        finally:
            quality_benchmarks.validate_reference_evaluation_target = (
                original_validate_reference_target
            )
            reference_comparison_module.compare_model_to_reference = (
                original_compare_reference
            )
        assert not mismatched_benchmark_reference["ok"], (
            mismatched_benchmark_reference
        )
        assert (
            mismatched_benchmark_reference["code"]
            == "benchmark_reference_identity_mismatch"
        ), mismatched_benchmark_reference
        assert reference_comparison["metadata_uri"].startswith(
            "blender://inspection-renders/"
        ), reference_comparison
        assert len(reference_comparison["images"]) == 3, reference_comparison
        assert all(
            image["available"] for image in reference_comparison["images"]
        ), reference_comparison
        assert (
            scene.render.resolution_x,
            scene.render.resolution_y,
            scene.render.resolution_percentage,
            scene.render.pixel_aspect_x,
            scene.render.pixel_aspect_y,
        ) == comparison_render_state, reference_comparison
        assert cube.hide_render == cube_hide_render, reference_comparison
        assert (
            bpy.data.materials.get("Agent Bridge Reference Mask") is None
        ), reference_comparison
        assert (
            live_preview.current_transaction()["status"] == "pending"
        ), reference_comparison
        reference_benchmark = _execute(
            context,
            "evaluate_reference_model_benchmark",
            {
                "collection_name": annotation_guides["collection"],
                "object_names": ["Cube"],
                "selected_only": False,
                "outline_name": "primary_outline",
                "reference_mask_source": "outline",
                "landmark_targets": [
                    {"name": "center", "object_name": "Cube"}
                ],
                "profile": "blockout",
                "max_axis": 128,
            },
        )
        assert isinstance(reference_benchmark["passed"], bool), reference_benchmark
        assert (
            reference_benchmark["evaluation"]["gate_count"] >= 5
        ), reference_benchmark
        assert (
            reference_benchmark["evaluation"]["profile"] == "blockout"
        ), reference_benchmark
        assert len(reference_benchmark["images"]) == 3, reference_benchmark
        assert all(
            image["available"] for image in reference_benchmark["images"]
        ), reference_benchmark
        assert reference_benchmark["metadata_uri"].startswith(
            "blender://inspection-renders/"
        ), reference_benchmark
        assert (
            live_preview.current_transaction()["status"] == "pending"
        ), reference_benchmark
        multiview_annotations_front = {
            "version": 1,
            "coordinate_space": "normalized",
            "origin": "top_left",
            "landmarks": [
                {"name": "shared", "point": [0.6, 0.4]},
                {"name": "front_only", "point": [0.4, 0.55]},
            ],
            "outlines": [
                {
                    "name": "front_outline",
                    "points": [[0.35, 0.2], [0.65, 0.2], [0.7, 0.8], [0.3, 0.8]],
                    "closed": True,
                }
            ],
        }
        multiview_annotations_left = {
            "version": 1,
            "coordinate_space": "normalized",
            "origin": "top_left",
            "landmarks": [{"name": "shared", "point": [0.55, 0.4]}],
            "outlines": [
                {
                    "name": "left_outline",
                    "points": [[0.4, 0.2], [0.6, 0.2], [0.65, 0.8], [0.35, 0.8]],
                    "closed": True,
                }
            ],
        }
        multiview_annotations_top = {
            "version": 1,
            "coordinate_space": "normalized",
            "origin": "top_left",
            "landmarks": [{"name": "shared", "point": [0.6, 0.6]}],
        }
        multiview_guides = _execute(
            context,
            "create_multiview_reference_guides",
            {
                "subject": "multi-view kitten",
                "collection_name": "Agent Bridge Multi-View Guides",
                "subject_center": [0.0, 0.0, 1.5],
                "active_view": "front",
                "views": [
                    {
                        "name": "front",
                        "axis": "FRONT",
                        "image_path": annotation_image_path,
                        "annotations": multiview_annotations_front,
                        "plane_height": 3.0,
                    },
                    {
                        "name": "left",
                        "axis": "LEFT",
                        "image_path": annotation_image_path,
                        "annotations": multiview_annotations_left,
                        "plane_height": 3.0,
                    },
                    {
                        "name": "top_custom",
                        "axis": "CUSTOM",
                        "view_direction": [0.0, 0.0, -1.0],
                        "up_direction": [0.0, 1.0, 0.0],
                        "image_path": annotation_image_path,
                        "annotations": multiview_annotations_top,
                        "plane_height": 3.0,
                    },
                ],
                "create_connectors": True,
                "max_landmark_residual": 0.01,
            },
        )
        assert len(multiview_guides["views"]) == 3, multiview_guides
        assert len(multiview_guides["landmarks_3d"]) == 1, multiview_guides
        shared_landmark = multiview_guides["landmarks_3d"][0]
        assert shared_landmark["name"] == "shared", multiview_guides
        assert shared_landmark["confidence"] == "within_residual_limit", multiview_guides
        assert len(shared_landmark["connectors"]) == 3, multiview_guides
        assert abs(shared_landmark["location"][0] - 0.6) < 1e-5, multiview_guides
        assert abs(shared_landmark["location"][1] + 0.3) < 1e-5, multiview_guides
        assert abs(shared_landmark["location"][2] - 1.8) < 1e-5, multiview_guides
        assert multiview_guides["unresolved_landmarks"][0]["name"] == "front_only", multiview_guides
        multiview_master = bpy.data.collections[multiview_guides["collection"]]
        assert multiview_master.get("reference_multiview_guides"), multiview_guides
        assert all(
            multiview_master.children.get(view["collection"]) is not None
            for view in multiview_guides["views"]
        ), multiview_guides
        assert scene.camera.name == multiview_guides["views"][0]["camera"], multiview_guides
        top_camera = bpy.data.objects[multiview_guides["views"][2]["camera"]]
        top_camera_up = top_camera.matrix_world.to_quaternion() @ Vector((0.0, 1.0, 0.0))
        assert (top_camera_up - Vector((0.0, 1.0, 0.0))).length < 1e-5, multiview_guides
        inspected_multiview = _execute(
            context,
            "inspect_reference_modeling_guides",
            {
                "collection_name": multiview_master.name,
                "include_points": True,
                "max_points_per_curve": 4,
            },
        )
        assert inspected_multiview["totals"]["landmarks_3d"] == 1, inspected_multiview
        assert inspected_multiview["totals"]["reconstruction_rays"] == 3, inspected_multiview

        visual_hull = _execute(
            context,
            "create_multiview_visual_hull",
            {
                "collection_name": multiview_master.name,
                "object_name": "Agent Bridge Kitten Visual Hull",
                "resolution": 24,
                "smooth_iterations": 1,
            },
        )
        hull_object = bpy.data.objects[visual_hull["object"]]
        assert hull_object.get("reference_visual_hull"), visual_hull
        assert [view["name"] for view in visual_hull["views"]] == ["front", "left"]
        assert "top_custom" in visual_hull["warnings"][0], visual_hull
        assert visual_hull["stats"]["occupied_voxels"] > 0, visual_hull
        assert len(hull_object.data.vertices) == visual_hull["stats"]["vertex_count"]
        hull_edge_counts = {}
        for polygon in hull_object.data.polygons:
            indices = list(polygon.vertices)
            for index, first in enumerate(indices):
                edge = tuple(sorted((first, indices[(index + 1) % len(indices)])))
                hull_edge_counts[edge] = hull_edge_counts.get(edge, 0) + 1
        assert hull_edge_counts and all(count == 2 for count in hull_edge_counts.values()), visual_hull

        depth_surface = _execute(
            context,
            "create_multiview_depth_surface",
            {
                "collection_name": multiview_master.name,
                "object_name": "Agent Bridge Kitten Depth Surface",
                "resolution": 20,
                "smooth_iterations": 1,
                "depth_sources": [
                    {
                        "view_name": "front",
                        "mode": "front",
                        "image_path": annotation_image_path,
                        "near_depth": -0.1,
                        "far_depth": -0.1,
                        "channel": "alpha",
                    }
                ],
            },
        )
        depth_object = bpy.data.objects[depth_surface["object"]]
        assert depth_object.get("reference_depth_surface"), depth_surface
        assert depth_surface["stats"]["depth_layer_count"] == 1, depth_surface
        assert depth_surface["stats"]["depth_evaluations"] > 0, depth_surface
        assert depth_surface["stats"]["depth_layer_evaluations"][0]["evaluation_count"] > 0

        unused_depth_surface = json.loads(
            tool_dispatcher.execute_tool(
                context,
                "create_multiview_depth_surface",
                {
                    "collection_name": multiview_master.name,
                    "object_name": "Agent Bridge Unused Depth Surface",
                    "resolution": 16,
                    "smooth_iterations": 0,
                    "depth_sources": [
                        {
                            "view_name": "front",
                            "mode": "front",
                            "image_path": annotation_image_path,
                            "near_depth": -0.1,
                            "far_depth": -0.1,
                            "channel": "alpha",
                        },
                        {
                            "view_name": "front",
                            "mode": "back",
                            "name": "outside sparse probe",
                            "samples": [
                                {
                                    "point": [0.0, 0.0],
                                    "depth": 0.1,
                                    "radius": 0.001,
                                }
                            ],
                        },
                    ],
                },
            )
        )
        assert not unused_depth_surface["ok"], unused_depth_surface
        assert "outside sparse probe" in unused_depth_surface["message"], unused_depth_surface
        assert bpy.data.objects.get("Agent Bridge Unused Depth Surface") is None

        shape_key_fit_probe = hull_object.copy()
        shape_key_fit_probe.data = hull_object.data.copy()
        shape_key_fit_probe.name = "Agent Bridge Shape Key Fit Probe"
        context.scene.collection.objects.link(shape_key_fit_probe)
        shape_key_fit_probe.shape_key_add(name="Basis")
        shape_key_fit_probe.shape_key_add(name="Raised")
        shape_key_fit_failure = json.loads(
            tool_dispatcher.execute_tool(
                context,
                "fit_surface_to_multiview_references",
                {
                    "object_name": shape_key_fit_probe.name,
                    "collection_name": multiview_master.name,
                    "view_names": ["front", "left"],
                },
            )
        )
        assert not shape_key_fit_failure["ok"], shape_key_fit_failure
        assert "shape keys" in shape_key_fit_failure["message"].lower()
        shape_key_fit_mesh = shape_key_fit_probe.data
        bpy.data.objects.remove(shape_key_fit_probe, do_unlink=True)
        bpy.data.meshes.remove(shape_key_fit_mesh)

        unused_fit_depth = json.loads(
            tool_dispatcher.execute_tool(
                context,
                "fit_surface_to_multiview_references",
                {
                    "object_name": hull_object.name,
                    "collection_name": multiview_master.name,
                    "view_names": ["front", "left"],
                    "iterations": 1,
                    "step_candidates": [0.5],
                    "depth_sources": [
                        {
                            "view_name": "front",
                            "mode": "front",
                            "image_path": annotation_image_path,
                            "near_depth": -0.1,
                            "far_depth": -0.1,
                            "channel": "alpha",
                        },
                        {
                            "view_name": "front",
                            "mode": "back",
                            "name": "outside fit probe",
                            "samples": [
                                {
                                    "point": [0.0, 0.0],
                                    "depth": 0.1,
                                    "radius": 0.001,
                                }
                            ],
                        },
                    ],
                },
            )
        )
        assert not unused_fit_depth["ok"], unused_fit_depth
        assert "outside fit probe" in unused_fit_depth["message"], unused_fit_depth

        subject_center = Vector((0.0, 0.0, 1.5))
        for vertex in hull_object.data.vertices:
            vertex.co = subject_center + (vertex.co - subject_center) * 0.82
        hull_object.data.update(calc_edges=True)
        fitted = _execute(
            context,
            "fit_surface_to_multiview_references",
            {
                "object_name": hull_object.name,
                "collection_name": multiview_master.name,
                "view_names": ["front", "left"],
                "iterations": 3,
                "step_candidates": [0.5, 1.0],
                "feature_preservation": 0.0,
                "propagation_steps": 2,
                "per_view_regression_tolerance": 0.01,
                "maximum_total_displacement": 0.5,
                "capture_evidence": True,
                "evidence_max_axis": 64,
            },
        )
        assert fitted["changed"] is True, fitted
        assert fitted["objective_improvement"] > 0.0, fitted
        assert (
            fitted["final"]["objective"] < fitted["baseline"]["objective"]
        ), fitted
        assert hull_object.get("reference_multiview_fit_metadata_json"), fitted
        assert fitted["evidence"]["before"]["successful_view_count"] == 2, fitted
        assert fitted["evidence"]["after"]["successful_view_count"] == 2, fitted

        failed_multiview_inventory = (
            set(bpy.data.objects.keys()),
            set(bpy.data.collections.keys()),
            set(bpy.data.curves.keys()),
            set(bpy.data.meshes.keys()),
            set(bpy.data.cameras.keys()),
            set(bpy.data.materials.keys()),
            set(bpy.data.images.keys()),
        )
        failed_multiview = json.loads(
            tool_dispatcher.execute_tool(
                context,
                "create_multiview_reference_guides",
                {
                    "collection_name": "Agent Bridge Parallel Multi-View Guides",
                    "views": [
                        {
                            "name": "front",
                            "axis": "FRONT",
                            "image_path": annotation_image_path,
                            "annotations": multiview_annotations_front,
                        },
                        {
                            "name": "back",
                            "axis": "BACK",
                            "image_path": annotation_image_path,
                            "annotations": multiview_annotations_left,
                        },
                    ],
                },
            )
        )
        assert not failed_multiview["ok"], failed_multiview
        assert failed_multiview["code"] == "multiview_guide_creation_failed", failed_multiview
        assert (
            set(bpy.data.objects.keys()),
            set(bpy.data.collections.keys()),
            set(bpy.data.curves.keys()),
            set(bpy.data.meshes.keys()),
            set(bpy.data.cameras.keys()),
            set(bpy.data.materials.keys()),
            set(bpy.data.images.keys()),
        ) == failed_multiview_inventory, failed_multiview
        comparison_dirs_before_failure = {
            os.path.join(root, name)
            for root, directories, _files in os.walk(capture_dir)
            for name in directories
            if name.startswith("reference-comparison-")
        }
        failed_alpha_comparison = json.loads(
            tool_dispatcher.execute_tool(
                context,
                "compare_model_to_reference",
                {
                    "collection_name": annotation_guides["collection"],
                    "object_names": ["Cube"],
                    "selected_only": False,
                    "reference_mask_source": "alpha",
                    "max_axis": 128,
                },
            )
        )
        assert not failed_alpha_comparison["ok"], failed_alpha_comparison
        assert "fully opaque" in failed_alpha_comparison["message"], failed_alpha_comparison
        assert (
            scene.render.resolution_x,
            scene.render.resolution_y,
            scene.render.resolution_percentage,
            scene.render.pixel_aspect_x,
            scene.render.pixel_aspect_y,
        ) == comparison_render_state, failed_alpha_comparison
        assert cube.hide_render == cube_hide_render, failed_alpha_comparison
        assert (
            bpy.data.materials.get("Agent Bridge Reference Mask") is None
        ), failed_alpha_comparison
        comparison_dirs_after_failure = {
            os.path.join(root, name)
            for root, directories, _files in os.walk(capture_dir)
            for name in directories
            if name.startswith("reference-comparison-")
        }
        assert (
            comparison_dirs_after_failure == comparison_dirs_before_failure
        ), failed_alpha_comparison
        reference_blockout = _execute(
            context,
            "create_reference_blockout",
            {
                "collection_name": annotation_guides["collection"],
                "mass_names": ["primary_mass"],
                "mass_settings": [
                    {
                        "name": "primary_mass",
                        "depth_ratio": 0.65,
                        "controls": [
                            {
                                "direction": [0.0, 0.0, 1.0],
                                "offset": 0.08,
                                "falloff": 0.5,
                            }
                        ],
                    }
                ],
                "name_prefix": "Agent Bridge Reference Blockout",
                "segments": 16,
                "rings": 8,
                "blend_mode": "voxel",
                "voxel_size": 0.001,
                "smooth_iterations": 1,
            },
        )
        assert len(reference_blockout["components"]) == 1, reference_blockout
        blockout_component = bpy.data.objects[
            reference_blockout["components"][0]["object"]
        ]
        blockout_result = bpy.data.objects[
            reference_blockout["blended_object"]
        ]
        assert blockout_component.type == "MESH", reference_blockout
        assert blockout_component.hide_get(), reference_blockout
        assert blockout_component.hide_render, reference_blockout
        assert blockout_result.type == "MESH", reference_blockout
        assert blockout_result.get("reference_blockout"), reference_blockout
        assert blockout_result.modifiers.get(
            "Reference Soft Union"
        ), reference_blockout
        assert blockout_result.modifiers.get(
            "Reference Surface Relax"
        ), reference_blockout
        assert (
            reference_blockout["effective_voxel_size"] > 0.001
        ), reference_blockout
        assert (
            live_preview.current_transaction()["status"] == "pending"
        ), reference_blockout
        blockout_failure_transaction = live_preview.current_transaction()
        blockout_failure_state = (
            blockout_failure_transaction["id"],
            len(blockout_failure_transaction["before_state"]),
            len(blockout_failure_transaction["applied_steps"]),
        )
        blockout_failure_inventory = (
            set(bpy.data.objects.keys()),
            set(bpy.data.meshes.keys()),
            set(bpy.data.materials.keys()),
        )
        original_blend_soft_forms = reference_blockout_module.blend_soft_forms
        try:
            reference_blockout_module.blend_soft_forms = (
                lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError("forced blockout blend failure")
                )
            )
            failed_blockout = reference_blockout_module.create_reference_blockout(
                context,
                collection_name=annotation_guides["collection"],
                mass_names=["primary_mass"],
                name_prefix="Agent Bridge Failed Reference Blockout",
                segments=16,
                rings=8,
                blend_mode="voxel",
            )
        finally:
            reference_blockout_module.blend_soft_forms = original_blend_soft_forms
        assert not failed_blockout["ok"], failed_blockout
        assert "forced blockout blend failure" in failed_blockout["message"], failed_blockout
        assert (
            set(bpy.data.objects.keys()),
            set(bpy.data.meshes.keys()),
            set(bpy.data.materials.keys()),
        ) == blockout_failure_inventory, failed_blockout
        assert (
            live_preview.current_transaction()
            is blockout_failure_transaction
        ), failed_blockout
        assert (
            blockout_failure_transaction["id"],
            len(blockout_failure_transaction["before_state"]),
            len(blockout_failure_transaction["applied_steps"]),
        ) == blockout_failure_state, failed_blockout

        converted_curve = _execute(
            context,
            "curve_to_mesh",
            {"object_names": [curve["object"]], "selected_only": False, "name_prefix": "Agent Bridge Converted "},
        )
        converted_object = bpy.data.objects[converted_curve["created"][0]["object"]]
        assert converted_object.type == "MESH", converted_curve

        armature = _execute(
            context,
            "create_basic_armature",
            {"name": "Agent Bridge Advanced Armature", "location": [2.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]},
        )
        assert bpy.data.objects[armature["object"]].type == "ARMATURE"

        _select_object(context, camera)
        _execute(
            context,
            "add_copy_transform_constraint",
            {"target_name": "Cube", "constraint_type": "COPY_LOCATION", "name": "Agent Bridge Advanced Copy Location"},
        )
        assert len(camera.constraints) == initial["camera_constraints"] + 1

        dolly = _execute(
            context,
            "create_camera_dolly_animation",
            {
                "camera_name": "Camera",
                "target_name": "Cube",
                "frame_start": 1,
                "frame_end": 36,
                "start_location": [0.0, -5.0, 2.0],
                "end_location": [0.0, -3.5, 1.4],
                "lens_start": 35,
                "lens_end": 55,
            },
        )
        assert dolly["camera"] == "Camera"
        assert dolly["action"] in bpy.data.actions

        phase1_prop = _run_phase1_modeling_helper_prop_test(context)
        assert len(phase1_prop["objects"]) == 6, phase1_prop
        assert all(name in bpy.data.objects for name in phase1_prop["objects"]), phase1_prop
        assert all(name in bpy.data.materials for name in phase1_prop["materials"]), phase1_prop

        _execute(context, "set_render_settings", {"resolution": [1280, 720], "fps": 30, "frame_start": 1, "frame_end": 48, "film_transparent": True})
        assert scene.render.resolution_x == 1280 and scene.render.resolution_y == 720
        assert scene.render.fps == 30
        assert scene.frame_end == 48

        _execute(context, "set_camera_settings", {"camera_name": "Camera", "lens": 70, "dof_enabled": True, "focus_object_name": "Cube", "aperture_fstop": 2.8})
        assert camera.data.lens == 70
        assert camera.data.dof.use_dof
        assert camera.data.dof.focus_object == cube

        _execute(context, "set_world_background", {"color": [0.02, 0.03, 0.06]})
        assert tuple(round(float(component), 4) for component in scene.world.color) == (0.02, 0.03, 0.06)

        _execute(context, "revert_preview", {})
        assert (
            bpy.data.images.get(persistent_reference_name)
            is persistent_reference_image
        )
        final = _snapshot(scene, cube, camera)
        assert final == initial, {"initial": initial, "final": final}
        restored_topology = _material_topology(existing_material)
        assert restored_topology == existing_topology, {
            "expected": existing_topology,
            "actual": restored_topology,
        }

        fresh_failure_group = cube.vertex_groups.new(
            name="Agent Bridge Fresh Failure Mask"
        )
        fresh_failure_material = bpy.data.materials.new(
            "Agent Bridge Fresh Failure Material"
        )
        fresh_failure_material.diffuse_color = (1.0, 0.0, 0.0, 1.0)
        fresh_failure = json.loads(
            tool_dispatcher.execute_tool(
                context,
                "create_directional_fur_curves",
                {
                    "object_names": ["Cube"],
                    "selected_only": False,
                    "material_name": fresh_failure_material.name,
                    "color": [0.0, 1.0, 0.0, 1.0],
                    "count": 8,
                    "regions": [
                        {
                            "name": "empty",
                            "vertex_group": fresh_failure_group.name,
                        }
                    ],
                },
            )
        )
        assert not fresh_failure["ok"], fresh_failure
        assert (
            live_preview.current_transaction()["status"] == "reverted"
        ), fresh_failure
        assert not bool(
            getattr(scene.claude_blender, "pending_preview", False)
        ), fresh_failure
        assert tuple(fresh_failure_material.diffuse_color) == (
            1.0,
            0.0,
            0.0,
            1.0,
        ), fresh_failure
        cube.vertex_groups.remove(fresh_failure_group)
        bpy.data.materials.remove(fresh_failure_material)
        assert _snapshot(scene, cube, camera) == final
        print("smoke_advanced_helpers: ok")
    finally:
        preferences.get_preferences = original_get_preferences
        claude_blender.unregister()
        shutil.rmtree(capture_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
