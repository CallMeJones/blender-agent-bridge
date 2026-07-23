"""Blender background smoke test for advanced safe helper tools."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import advanced_helpers, advanced_modeling, agent_tools, blender_compat, context_bundle, live_preview, preferences, tool_dispatcher  # noqa: E402


ADVANCED_TOOLS = {
    "plan_advanced_scene_workflow",
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
    "add_particle_system_to_selected",
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
        "resolution": (scene.render.resolution_x, scene.render.resolution_y),
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


def _write_test_image(path, color):
    image = bpy.data.images.new(name=os.path.basename(path), width=2, height=2, alpha=True)
    image.pixels = list(color) * 4
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
        final = _snapshot(scene, cube, camera)
        assert final == initial, {"initial": initial, "final": final}
        restored_topology = _material_topology(existing_material)
        assert restored_topology == existing_topology, {
            "expected": existing_topology,
            "actual": restored_topology,
        }
        print("smoke_advanced_helpers: ok")
    finally:
        preferences.get_preferences = original_get_preferences
        claude_blender.unregister()
        shutil.rmtree(capture_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
