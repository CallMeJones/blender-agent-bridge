"""Blender background smoke test for advanced safe helper tools."""

from __future__ import annotations

import json
import os
import sys
import tempfile

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import advanced_helpers, agent_tools, context_bundle, live_preview, tool_dispatcher  # noqa: E402


ADVANCED_TOOLS = {
    "plan_advanced_scene_workflow",
    "plan_object_design",
    "plan_asset_import_workflow",
    "plan_director_workflow",
    "get_2d_animation_details",
    "create_storyboard_panels",
    "create_2d_cutout_layer",
    "apply_procedural_array_stack",
    "edit_mesh",
    "inspect_modeling_quality",
    "curve_to_mesh",
    "uv_unwrap",
    "boolean_op",
    "mirror_model",
    "symmetrize_model",
    "solidify_model",
    "screw_model",
    "create_procedural_object_kit",
    "create_camera_dolly_animation",
    "create_directed_animation_shot",
    "prepare_imported_asset_presentation",
    "add_cloth_simulation_to_selected",
    "create_shader_material",
    "create_image_texture_material",
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


def _run_desk_lamp_kit_exit_test(context):
    kit = _execute(
        context,
        "create_procedural_object_kit",
        {
            "template": "desk_lamp",
            "name_prefix": "Agent Bridge Desk Lamp Kit",
            "location": [7.0, -6.0, 0.0],
            "count": 1,
            "radius": 1.25,
            "height": 1.85,
            "primary_color": [0.16, 0.17, 0.18, 1.0],
            "accent_color": [0.85, 0.62, 0.28, 1.0],
        },
    )
    assert kit["template"] == "desk_lamp", kit
    assert kit["design"]["style"] == "default", kit
    assert kit["design"]["variant"] == "default", kit
    assert kit["design"]["detail_level"] == "medium", kit
    assert {"round_base", "double_arm", "open_shade", "visible_bulb", "power_cable"}.issubset(set(kit["design"]["features"])), kit
    expected_terms = (
        "Root",
        "Weighted Base",
        "Vertical Stem",
        "Lower Arm Front",
        "Upper Arm Rear",
        "Stem Hinge",
        "Elbow Hinge",
        "Shade Hinge",
        "Open Shade",
        "Visible Bulb",
        "Power Cable",
        "Shade Glow",
    )
    for term in expected_terms:
        assert any(term in name for name in kit["objects"]), (term, kit)
    root_name = next(name for name in kit["objects"] if name.endswith(" Root"))
    mesh_names = [name for name in kit["objects"] if bpy.data.objects[name].type == "MESH"]
    assert len(mesh_names) >= 10, kit
    quality = _execute(
        context,
        "inspect_modeling_quality",
        {"object_names": [root_name], "selected_only": False, "include_children": True, "require_materials": True},
    )
    assert quality["passed"] is True, quality
    assert quality["object_count"] >= 10, quality
    assert quality["issue_count"] == 0, quality
    render_result = _execute(
        context,
        "capture_object_inspection_renders",
        {
            "object_names": [root_name],
            "views": ["front_below", "side"],
            "resolution_x": 320,
            "resolution_y": 240,
            "distance_factor": 3.0,
            "note": "Desk-lamp kit visual exit evidence",
        },
    )
    render = render_result["inspection_render"]
    assert render["available"] is True, render
    assert len(render["images"]) == 2, render
    for image in render["images"]:
        assert image["available"] is True, image
        assert image["width"] == 320 and image["height"] == 240, image
        assert image["size_bytes"] > 128, image
        assert os.path.isfile(image["path"]), image
    return {"kit": kit, "root": root_name, "quality": quality, "inspection_render": render}


def _run_desk_lamp_design_grammar_test(context):
    kit = _execute(
        context,
        "create_procedural_object_kit",
        {
            "template": "desk_lamp",
            "name_prefix": "Agent Bridge Architect Lamp Kit",
            "location": [14.5, -6.0, 0.0],
            "count": 1,
            "radius": 1.2,
            "height": 1.75,
            "style": "architect",
            "variant": "architect",
            "detail_level": "high",
            "features": ["spring_arms", "counterweight", "wide_shade", "label_parts"],
        },
    )
    assert kit["template"] == "desk_lamp", kit
    design = kit["design"]
    assert design["style"] == "architect", kit
    assert design["variant"] == "architect", kit
    assert design["detail_level"] == "high", kit
    for feature in ("spring_arms", "counterweight", "wide_shade", "label_parts"):
        assert feature in design["features"], kit
    for term in ("Lower Spring", "Upper Spring", "Counterweight", "Open Shade", "Visible Bulb"):
        assert any(term in name for name in kit["objects"]), (term, kit)
    root_name = next(name for name in kit["objects"] if name.endswith(" Root"))
    quality = _execute(
        context,
        "inspect_modeling_quality",
        {"object_names": [root_name], "selected_only": False, "include_children": True, "require_materials": True},
    )
    assert quality["passed"] is True, quality
    assert quality["issue_count"] == 0, quality
    render_result = _execute(
        context,
        "capture_object_inspection_renders",
        {
            "object_names": [root_name],
            "views": ["front_below", "side"],
            "resolution_x": 320,
            "resolution_y": 240,
            "distance_factor": 3.0,
            "note": "Architect desk-lamp design grammar visual evidence",
        },
    )
    render = render_result["inspection_render"]
    assert render["available"] is True, render
    assert len(render["images"]) == 2, render
    for image in render["images"]:
        assert image["available"] is True, image
        assert image["width"] == 320 and image["height"] == 240, image
        assert image["size_bytes"] > 128, image
        assert os.path.isfile(image["path"]), image
    return {"kit": kit, "root": root_name, "quality": quality, "inspection_render": render}


def _run_coffee_machine_kit_exit_test(context):
    kit = _execute(
        context,
        "create_procedural_object_kit",
        {
            "template": "coffee_machine",
            "name_prefix": "Agent Bridge Coffee Machine Kit",
            "location": [21.0, -6.0, 0.0],
            "count": 7,
            "radius": 1.25,
            "height": 1.8,
            "style": "industrial",
            "primary_color": [0.13, 0.14, 0.15, 1.0],
            "accent_color": [0.82, 0.48, 0.2, 1.0],
        },
    )
    assert kit["template"] == "coffee_machine", kit
    expected_terms = (
        "Root",
        "Chrome Rectangular Body",
        "Top Shell Cap",
        "Base Plinth",
        "Mirrored Front Panel",
        "Front Shell Column",
        "Dispensing Bay Backplate",
        "Mirror Trim",
        "Red Logo Badge",
        "Top Cup Warmer Tray",
        "Top Cup Warmer Grate Bar",
        "Top Reservoir Cap",
        "Center Top Pressure Pin",
        "Rear Water Reservoir",
        "Walnut Steam Knob",
        "Pressure Gauge",
        "Round Display Badge",
        "Control Button 01",
        "Brew Head",
        "Portafilter Basket",
        "Walnut Portafilter Handle",
        "Twin Nozzle",
        "Drip Tray",
        "Drip Tray Grate Bar",
        "Walnut Foot",
        "Left Hot Water Wand",
        "Right Steam Wand",
        "Chrome Pipe",
    )
    for term in expected_terms:
        assert any(term in name for name in kit["objects"]), (term, kit)
    forbidden_terms = (
        "Rear Frame Spine",
        "Frame Rail",
        "Right Side Control Fascia",
        "Right Side Status Screen",
        "Right Side Brew Head",
        "Right Side Demo Cup",
        "Demo Cup",
        "Coffee Surface",
    )
    for term in forbidden_terms:
        assert not any(term in name for name in kit["objects"]), (term, kit)
    root_name = next(name for name in kit["objects"] if name.endswith(" Root"))
    mesh_names = [name for name in kit["objects"] if bpy.data.objects[name].type == "MESH"]
    assert len(mesh_names) >= 18, kit
    quality = _execute(
        context,
        "inspect_modeling_quality",
        {"object_names": [root_name], "selected_only": False, "include_children": True, "require_materials": True},
    )
    assert quality["passed"] is True, quality
    assert quality["object_count"] >= 18, quality
    assert quality["issue_count"] == 0, quality
    render_result = _execute(
        context,
        "capture_object_inspection_renders",
        {
            "object_names": [root_name],
            "views": ["front", "side"],
            "resolution_x": 320,
            "resolution_y": 240,
            "distance_factor": 3.0,
            "note": "Coffee-machine kit visual exit evidence",
        },
    )
    render = render_result["inspection_render"]
    assert render["available"] is True, render
    assert len(render["images"]) == 2, render
    for image in render["images"]:
        assert image["available"] is True, image
        assert image["width"] == 320 and image["height"] == 240, image
        assert image["size_bytes"] > 128, image
        assert os.path.isfile(image["path"]), image
    return {"kit": kit, "root": root_name, "quality": quality, "inspection_render": render}


def main():
    claude_blender.register()
    context = bpy.context
    scene = context.scene
    cube = bpy.data.objects["Cube"]
    camera = bpy.data.objects["Camera"]
    existing_material = bpy.data.materials.new("Agent Bridge Existing Node Material")
    node_tree = existing_material.node_tree
    assert node_tree is not None, "New Blender materials should expose a shader node tree"
    nodes = node_tree.nodes
    for node in list(nodes):
        nodes.remove(node)
    diffuse = nodes.new(type="ShaderNodeBsdfDiffuse")
    output = nodes.new(type="ShaderNodeOutputMaterial")
    node_tree.links.new(diffuse.outputs["BSDF"], output.inputs["Surface"])
    cube.data.materials.clear()
    cube.data.materials.append(existing_material)
    existing_topology = _material_topology(existing_material)
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

        original_link_object_like_source = advanced_helpers._link_object_like_source

        def _fail_link_object_like_source(context, source, duplicate):
            raise RuntimeError("forced link failure")

        try:
            advanced_helpers._link_object_like_source = _fail_link_object_like_source
            failed_link_curve = json.loads(
                tool_dispatcher.execute_tool(
                    context,
                    "curve_to_mesh",
                    {"object_names": [failure_curve.name], "selected_only": False, "name_prefix": "Agent Bridge Link Failed "},
                )
            )
        finally:
            advanced_helpers._link_object_like_source = original_link_object_like_source
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
        object_design = _execute(
            context,
            "plan_object_design",
            {"prompt": "Design a futuristic wall-mounted coffee machine with chrome pipes, a small display, buttons, and beveled body."},
        )
        assert object_design["object_family"] == "appliance", object_design
        assert object_design["strategy"] == "procedural_kit_plus_generic_modeling", object_design
        assert object_design["template"] == "coffee_machine", object_design
        assert "pipe_run" in object_design["companion_templates"], object_design
        assert "display_screen" in object_design["features"], object_design
        assert "pipe_run" in object_design["features"], object_design
        assert "create_procedural_object_kit" in object_design["recommended_tools"], object_design
        assert "edit_mesh" in object_design["recommended_tools"], object_design
        assert "create_shader_material" in object_design["recommended_tools"], object_design
        assert object_design["kit_arguments"]["template"] == "coffee_machine", object_design
        assert object_design["fallback_reason"] == "", object_design
        planned_names = [call["name"] for call in object_design["planned_tool_calls"]]
        deferred_by_name = {call["name"]: call for call in object_design["deferred_tool_calls"]}
        assert "create_procedural_object_kit" in planned_names, object_design
        assert "inspect_modeling_quality" not in planned_names, object_design
        assert "capture_object_inspection_renders" not in planned_names, object_design
        assert deferred_by_name["inspect_modeling_quality"]["input_handoff"]["source_tool"] == "create_procedural_object_kit", object_design
        assert deferred_by_name["inspect_modeling_quality"]["input_handoff"]["source_result_field"] == "objects", object_design
        assert "object_names" not in deferred_by_name["inspect_modeling_quality"]["input"], object_design
        assert deferred_by_name["capture_object_inspection_renders"]["input_handoff"]["source_tool"] == "create_procedural_object_kit", object_design
        assert "object_names" not in deferred_by_name["capture_object_inspection_renders"]["input"], object_design
        control_panel_design = _execute(
            context,
            "plan_object_design",
            {"prompt": "Create a control panel."},
        )
        assert control_panel_design["object_family"] == "electronics", control_panel_design
        assert control_panel_design["template"] == "control_panel", control_panel_design
        exact_object_design = _execute(
            context,
            "plan_object_design",
            {"prompt": "Make the exact Boeing 747 landing gear from a reference image."},
        )
        assert exact_object_design["strategy"] == "asset_reference_then_refine", exact_object_design
        assert exact_object_design["template"] == "", exact_object_design
        assert exact_object_design["kit_arguments"] == {}, exact_object_design
        assert exact_object_design["fallback_reason"], exact_object_design
        assert "plan_asset_import_workflow" in exact_object_design["recommended_tools"], exact_object_design
        exact_control_panel_design = _execute(
            context,
            "plan_object_design",
            {"prompt": "Make the exact Sony control panel from a reference image."},
        )
        assert exact_control_panel_design["object_family"] == "electronics", exact_control_panel_design
        assert exact_control_panel_design["strategy"] == "asset_reference_then_refine", exact_control_panel_design
        assert exact_control_panel_design["template"] == "", exact_control_panel_design
        assert exact_control_panel_design["refinement_template"] == "control_panel", exact_control_panel_design
        assert exact_control_panel_design["kit_arguments"] == {}, exact_control_panel_design
        assert not any(call["name"] == "create_procedural_object_kit" for call in exact_control_panel_design["planned_tool_calls"]), exact_control_panel_design
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
                "prompt": "Director workflow: import an asset, create a modular wall panel kit, animate a reveal, review evidence, and ask before commit.",
                "target_objects": ["Cube"],
            },
        )
        director_tool_names = [call["name"] for call in director_plan["next_tool_calls"]]
        assert "plan_asset_import_workflow" in director_tool_names, director_plan
        assert "create_procedural_object_kit" in director_tool_names, director_plan
        assert "run_animation_workflow" in director_tool_names, director_plan
        assert "commit_preview" not in director_tool_names, director_plan
        assert "revert_preview" not in director_tool_names, director_plan
        director_decision_names = [option["tool_call"]["name"] for option in director_plan["preview_decision_options"]]
        assert director_decision_names == ["commit_preview", "revert_preview"], director_plan
        gn_plan_call = next(call for call in director_plan["next_tool_calls"] if call["name"] == "add_geometry_nodes_modifier")
        assert gn_plan_call["input"]["name"], director_plan
        assert gn_plan_call["input"]["node_group_name"], director_plan
        assert director_plan["preview_policy"]["commit_only_on_user_request"] is True, director_plan
        details = _execute(context, "get_2d_animation_details", {"max_items": 12})
        assert "recommended_tools" in details

        board = _execute(
            context,
            "create_storyboard_panels",
            {
                "panel_count": 2,
                "columns": 2,
                "name_prefix": "Agent Bridge Advanced Board",
                "frame_start": 1,
                "frame_step": 12,
            },
        )
        assert len(board["panels"]) == 2
        assert board["camera"] in bpy.data.objects

        cutout = _execute(
            context,
            "create_2d_cutout_layer",
            {
                "name": "Agent Bridge Advanced Cutout",
                "location": [0.0, -0.2, 0.0],
                "size": [0.8, 0.5],
                "frame_start": 1,
                "frame_end": 24,
                "location_end": [0.5, -0.2, 0.25],
                "text": "Layer",
            },
        )
        assert cutout["object"] in bpy.data.objects
        assert cutout["action"] in bpy.data.actions

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
        assert "mesh_data_snapshot" in uv_result["preview_change_report"]["rollback_scopes"], uv_result
        uv_layer = cube.data.uv_layers.get("Agent Bridge Advanced UVs")
        assert uv_layer is not None, uv_result
        uv_values = [component for item in uv_layer.data for component in item.uv]
        assert uv_values and min(uv_values) >= 0.0 and max(uv_values) <= 1.0, uv_values

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

        desk_lamp = _run_desk_lamp_kit_exit_test(context)
        assert desk_lamp["quality"]["passed"] is True, desk_lamp
        architect_lamp = _run_desk_lamp_design_grammar_test(context)
        assert architect_lamp["quality"]["passed"] is True, architect_lamp
        coffee_machine = _run_coffee_machine_kit_exit_test(context)
        assert coffee_machine["quality"]["passed"] is True, coffee_machine

        object_kit = _execute(
            context,
            "create_procedural_object_kit",
            {
                "template": "radial_array",
                "name_prefix": "Agent Bridge Smoke Kit",
                "location": [3.0, 0.0, 0.0],
                "count": 6,
                "radius": 1.4,
                "height": 0.7,
            },
        )
        assert object_kit["template"] == "radial_array", object_kit
        assert len(object_kit["objects"]) >= 7, object_kit
        assert bpy.data.objects[object_kit["objects"][0]].type == "MESH"

        mechanical_kit = _execute(
            context,
            "create_procedural_object_kit",
            {
                "template": "mechanical_joint",
                "name_prefix": "Agent Bridge Mechanical Kit",
                "location": [-3.0, 0.0, 0.0],
                "count": 5,
                "radius": 1.2,
                "height": 0.8,
            },
        )
        assert mechanical_kit["template"] == "mechanical_joint", mechanical_kit
        assert any("Bearing" in name for name in mechanical_kit["objects"]), mechanical_kit
        assert any("Bolt" in name for name in mechanical_kit["objects"]), mechanical_kit

        product_display = _execute(
            context,
            "create_procedural_object_kit",
            {
                "template": "product_display_rig",
                "name_prefix": "Agent Bridge Product Display Kit",
                "location": [0.0, -3.0, 0.0],
                "count": 8,
                "radius": 1.3,
                "height": 1.2,
            },
        )
        assert product_display["template"] == "product_display_rig", product_display
        assert any("Turntable Plinth" in name for name in product_display["objects"]), product_display
        assert any("Softbox Card" in name for name in product_display["objects"]), product_display

        mechanical_assembly = _execute(
            context,
            "create_procedural_object_kit",
            {
                "template": "mechanical_assembly",
                "name_prefix": "Agent Bridge Mechanical Assembly Kit",
                "location": [-4.5, -2.5, 0.0],
                "count": 5,
                "radius": 1.1,
                "height": 0.9,
            },
        )
        assert mechanical_assembly["template"] == "mechanical_assembly", mechanical_assembly
        assert any("Base Bracket" in name for name in mechanical_assembly["objects"]), mechanical_assembly
        assert any("Drive Screw" in name for name in mechanical_assembly["objects"]), mechanical_assembly

        control_panel = _execute(
            context,
            "create_procedural_object_kit",
            {
                "template": "control_panel",
                "name_prefix": "Agent Bridge Control Panel Kit",
                "location": [12.0, 8.0, 0.0],
                "count": 6,
                "radius": 1.1,
                "height": 1.5,
            },
        )
        assert control_panel["template"] == "control_panel", control_panel
        for term in (
            "Root",
            "Control Panel Enclosure",
            "Recessed Faceplate",
            "Status Display Screen",
            "Status Indicator",
            "Emergency Stop Button",
            "Rotary Control Knob",
            "Toggle Switch",
            "Slider Track",
            "Terminal Strip Port",
        ):
            assert any(term in name for name in control_panel["objects"]), (term, control_panel)
        for name in control_panel["objects"]:
            if "Terminal Strip Port" in name:
                assert max(bpy.data.objects[name].dimensions) < 0.2, (name, bpy.data.objects[name].dimensions[:])
        control_panel_root = next(name for name in control_panel["objects"] if name.endswith(" Root"))
        control_panel_quality = _execute(
            context,
            "inspect_modeling_quality",
            {"object_names": [control_panel_root], "selected_only": False, "include_children": True, "require_materials": True},
        )
        assert control_panel_quality["passed"] is True, control_panel_quality
        control_panel_render = _execute(
            context,
            "capture_object_inspection_renders",
            {
                "object_names": [control_panel_root],
                "views": ["front", "front_below"],
                "resolution_x": 320,
                "resolution_y": 240,
                "distance_factor": 4.0,
                "note": "Control-panel kit visual exit evidence",
            },
        )["inspection_render"]
        assert control_panel_render["available"] is True, control_panel_render
        assert len(control_panel_render["images"]) == 2, control_panel_render
        for image in control_panel_render["images"]:
            assert image["available"] is True, image
            assert image["width"] == 320 and image["height"] == 240, image
            assert image["size_bytes"] > 128, image
            assert os.path.isfile(image["path"]), image

        modular_panel = _execute(
            context,
            "create_procedural_object_kit",
            {
                "template": "modular_wall_panel",
                "name_prefix": "Agent Bridge Modular Wall Kit",
                "location": [3.0, 3.0, 0.0],
                "count": 4,
                "radius": 1.0,
                "height": 1.4,
            },
        )
        assert modular_panel["template"] == "modular_wall_panel", modular_panel
        assert any("Wall Panel Body" in name for name in modular_panel["objects"]), modular_panel
        assert any("Inset Bay" in name for name in modular_panel["objects"]), modular_panel

        pipe_run = _execute(
            context,
            "create_procedural_object_kit",
            {
                "template": "pipe_run",
                "name_prefix": "Agent Bridge Pipe Run Kit",
                "location": [-3.0, 3.0, 0.0],
                "count": 4,
                "radius": 1.0,
                "height": 1.0,
            },
        )
        assert pipe_run["template"] == "pipe_run", pipe_run
        assert any("Pipe 01" in name for name in pipe_run["objects"]), pipe_run
        assert any("Pipe Support" in name for name in pipe_run["objects"]), pipe_run

        phase1_prop = _run_phase1_modeling_helper_prop_test(context)
        assert len(phase1_prop["objects"]) == 6, phase1_prop
        assert all(name in bpy.data.objects for name in phase1_prop["objects"]), phase1_prop
        assert all(name in bpy.data.materials for name in phase1_prop["materials"]), phase1_prop

        directed = _execute(
            context,
            "create_directed_animation_shot",
            {
                "shot_type": "path_slide",
                "object_names": ["Cube"],
                "selected_only": False,
                "frame_start": 1,
                "frame_end": 36,
                "travel_axis": "X",
                "travel_distance": 1.25,
                "camera_name": "Camera",
            },
        )
        assert directed["shot_type"] == "path_slide", directed
        assert "Cube" in directed["objects"], directed
        assert directed["camera"] == "Camera", directed

        crane = _execute(
            context,
            "create_directed_animation_shot",
            {
                "shot_type": "crane_reveal",
                "object_names": ["Cube"],
                "selected_only": False,
                "frame_start": 1,
                "frame_end": 48,
                "camera_name": "Camera",
            },
        )
        assert crane["shot_type"] == "crane_reveal", crane
        assert crane["subjects"] == ["Cube"], crane
        assert crane["objects"] == [], crane
        assert crane["camera_action"] in bpy.data.actions, crane

        truck = _execute(
            context,
            "create_directed_animation_shot",
            {
                "shot_type": "truck_slide",
                "object_names": ["Cube"],
                "selected_only": False,
                "frame_start": 1,
                "frame_end": 48,
                "travel_axis": "X",
                "travel_distance": 1.6,
                "camera_name": "Camera",
            },
        )
        assert truck["shot_type"] == "truck_slide", truck
        assert truck["subjects"] == ["Cube"], truck
        assert truck["objects"] == [], truck
        assert truck["camera_action"] in bpy.data.actions, truck

        invalid_directed = json.loads(
            tool_dispatcher.execute_tool(
                context,
                "create_directed_animation_shot",
                {"camera_name": "Cube", "object_names": ["Cube"], "selected_only": False},
            )
        )
        assert invalid_directed["ok"] is False, invalid_directed
        assert scene.claude_blender.pending_preview is True, "invalid directed shot must not clear existing preview"

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
        claude_blender.unregister()


if __name__ == "__main__":
    main()
