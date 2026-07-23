"""Blender-only handlers for the materials_nodes domain."""

from __future__ import annotations

import bpy

from .. import advanced_materials as advanced_helpers, blender_compat, context_bundle, live_preview, world_model
from ..handler_runtime import (
    _idprops_summary,
    _socket_summary,
)
from .support import _bounded_float, _bounded_int, _float_list, _name_list, _optional_float_list


def get_material_node_details(context, args):
    names = _name_list(args.get("material_names"))
    max_materials = _bounded_int(args.get("max_materials"), 8, maximum=25)
    max_nodes = _bounded_int(args.get("max_nodes"), 18, maximum=60)
    materials = []
    missing = []
    seen = set()

    if names:
        for name in names:
            material = bpy.data.materials.get(name)
            if material:
                materials.append(material)
                seen.add(material.name)
            else:
                missing.append(name)
    else:
        source_objects = list(context.selected_objects) if args.get("selected_only", True) else list(context.scene.objects)
        for obj in source_objects:
            for slot in obj.material_slots:
                material = slot.material
                if material and material.name not in seen:
                    materials.append(material)
                    seen.add(material.name)
                if len(materials) >= max_materials:
                    break
            if len(materials) >= max_materials:
                break

    details = []
    for material in materials[:max_materials]:
        item = context_bundle._material_summary(material)
        item["custom_properties"] = _idprops_summary(material)
        material_tree = blender_compat.node_tree(material)
        if material_tree:
            nodes = list(material_tree.nodes)
            links = list(material_tree.links)
            item["nodes"] = [
                {
                    "name": node.name,
                    "label": node.label,
                    "type": node.type,
                    "inputs": [_socket_summary(socket) for socket in list(node.inputs)[:12]],
                    "outputs": [_socket_summary(socket) for socket in list(node.outputs)[:12]],
                }
                for node in nodes[:max_nodes]
            ]
            item["links"] = [
                {
                    "from_node": link.from_node.name,
                    "from_socket": link.from_socket.name,
                    "to_node": link.to_node.name,
                    "to_socket": link.to_socket.name,
                }
                for link in links[:40]
            ]
            if len(nodes) > max_nodes:
                item["truncated_nodes"] = len(nodes) - max_nodes
            if len(links) > 40:
                item["truncated_links"] = len(links) - 40
        details.append(item)

    return {
        "ok": True,
        "materials": details,
        "missing_material_names": missing,
    }


def get_geometry_nodes_details(context, args):
    return world_model.geometry_nodes_details(
        context,
        object_names=_name_list(args.get("object_names")),
        max_objects=_bounded_int(args.get("max_objects"), 12, maximum=50),
    )


def get_shader_nodes_details(context, args):
    return world_model.shader_nodes_details(
        context,
        material_names=_name_list(args.get("material_names")),
        selected_only=bool(args.get("selected_only", True)),
        max_materials=_bounded_int(args.get("max_materials"), 12, maximum=50),
    )


def assign_material_to_selected(context, args):
    name = str(args.get("name") or "Agent Bridge Material")
    color = _float_list(args.get("color"), 4, (0.8, 0.1, 0.1, 1.0))
    return live_preview.assign_material_to_selected(
        context,
        name=name,
        color=color,
        label=args.get("label", "Assign material"),
    )


def assign_emission_material_to_selected(context, args):
    name = str(args.get("name") or "Agent Bridge Emission")
    color = _float_list(args.get("color"), 4, (0.2, 0.6, 1.0, 1.0))
    return live_preview.assign_emission_material_to_selected(
        context,
        name=name,
        color=color,
        strength=float(args.get("strength", 1.5)),
        label=args.get("label", "Assign emission material"),
    )


def create_shader_material(context, args):
    return advanced_helpers.create_shader_material(
        context,
        name=str(args.get("name") or "Agent Bridge Shader Material"),
        base_color=_float_list(args.get("base_color"), 4, (0.8, 0.8, 0.8, 1.0)) if "base_color" in args else None,
        metallic=float(args["metallic"]) if "metallic" in args else None,
        roughness=float(args["roughness"]) if "roughness" in args else None,
        alpha=float(args["alpha"]) if "alpha" in args else None,
        emission_color=_optional_float_list(args.get("emission_color"), 4, (0.0, 0.0, 0.0, 1.0)),
        emission_strength=float(args["emission_strength"]) if "emission_strength" in args else None,
        preset=str(args.get("preset") or "custom"),
        assign_to_selected=bool(args.get("assign_to_selected", True)),
        label=args.get("label", "Create shader material"),
    )


def create_image_texture_material(context, args):
    return advanced_helpers.create_image_texture_material(
        context,
        name=str(args.get("name") or "Agent Bridge Image Texture Material"),
        base_color_path=str(args.get("base_color_path") or ""),
        roughness_path=str(args.get("roughness_path") or ""),
        metallic_path=str(args.get("metallic_path") or ""),
        normal_path=str(args.get("normal_path") or ""),
        alpha_path=str(args.get("alpha_path") or ""),
        emission_path=str(args.get("emission_path") or ""),
        ambient_occlusion_path=str(args.get("ambient_occlusion_path") or ""),
        arm_path=str(args.get("arm_path") or ""),
        orm_path=str(args.get("orm_path") or ""),
        bump_path=str(args.get("bump_path") or ""),
        displacement_path=str(args.get("displacement_path") or ""),
        base_color=_float_list(args.get("base_color"), 4, (0.8, 0.8, 0.8, 1.0)) if "base_color" in args else None,
        metallic=_bounded_float(args.get("metallic"), 0.0, minimum=0.0, maximum=1.0) if "metallic" in args else None,
        roughness=_bounded_float(args.get("roughness"), 0.5, minimum=0.0, maximum=1.0) if "roughness" in args else None,
        alpha=_bounded_float(args.get("alpha"), 1.0, minimum=0.0, maximum=1.0) if "alpha" in args else None,
        emission_strength=_bounded_float(args.get("emission_strength"), 0.0, minimum=0.0, maximum=100.0)
        if "emission_strength" in args
        else None,
        normal_strength=_bounded_float(args.get("normal_strength"), 1.0, minimum=0.0, maximum=10.0),
        bump_strength=_bounded_float(args.get("bump_strength"), 0.12, minimum=0.0, maximum=10.0),
        bump_distance=_bounded_float(args.get("bump_distance"), 0.05, minimum=0.0, maximum=10.0),
        uv_map_name=str(args.get("uv_map_name") or ""),
        replace_existing_links=bool(args.get("replace_existing_links", True)),
        assign_to_objects=bool(args.get("assign_to_objects", True)),
        object_names=args.get("object_names") if isinstance(args.get("object_names"), list) else None,
        selected_only=bool(args.get("selected_only", True)),
        label=args.get("label", "Create image texture material"),
    )


def inspect_material_setup(context, args):
    return advanced_helpers.inspect_material_setup(
        context,
        material_names=_name_list(args.get("material_names")),
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        require_uv_maps=bool(args.get("require_uv_maps", False)),
        expected_uv_map_name=str(args.get("expected_uv_map_name") or ""),
        max_materials=_bounded_int(args.get("max_materials"), 32, minimum=1, maximum=128),
    )


def repair_material_setup(context, args):
    return advanced_helpers.repair_material_setup(
        context,
        material_names=_name_list(args.get("material_names")),
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        uv_map_name=str(args.get("uv_map_name") or ""),
        fix_color_spaces=bool(args.get("fix_color_spaces", True)),
        reconnect_uv_maps=bool(args.get("reconnect_uv_maps", True)),
        max_materials=_bounded_int(args.get("max_materials"), 32, minimum=1, maximum=128),
        label=args.get("label", "Repair material setup"),
    )


def bake_maps(context, args):
    return advanced_helpers.bake_maps(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        map_types=_name_list(args.get("map_types")) or None,
        output_dir=str(args.get("output_dir") or ""),
        resolution=_bounded_int(args.get("resolution"), 512, minimum=16, maximum=4096),
        margin=_bounded_int(args.get("margin"), 16, minimum=0, maximum=128),
        samples=_bounded_int(args.get("samples"), 32, minimum=1, maximum=4096),
        uv_map_name=str(args.get("uv_map_name") or ""),
        overwrite=bool(args.get("overwrite", False)),
        label=args.get("label", "Bake maps"),
    )


def create_procedural_texture_material(context, args):
    return advanced_helpers.create_procedural_texture_material(
        context,
        name=str(args.get("name") or "Agent Bridge Procedural Texture Material"),
        preset=str(args.get("preset") or "custom"),
        texture_type=str(args.get("texture_type") or ""),
        color_a=_float_list(args.get("color_a"), 4, (0.08, 0.08, 0.085, 1.0)) if "color_a" in args else None,
        color_b=_float_list(args.get("color_b"), 4, (0.82, 0.78, 0.68, 1.0)) if "color_b" in args else None,
        scale=_bounded_float(args.get("scale"), 18.0, minimum=0.01, maximum=500.0) if "scale" in args else None,
        detail=_bounded_float(args.get("detail"), 8.0, minimum=0.0, maximum=16.0) if "detail" in args else None,
        texture_roughness=_bounded_float(args.get("texture_roughness"), 0.55, minimum=0.0, maximum=1.0)
        if "texture_roughness" in args
        else None,
        distortion=_bounded_float(args.get("distortion"), 0.0, minimum=0.0, maximum=100.0) if "distortion" in args else None,
        randomness=_bounded_float(args.get("randomness"), 0.5, minimum=0.0, maximum=1.0) if "randomness" in args else None,
        metallic=_bounded_float(args.get("metallic"), 0.0, minimum=0.0, maximum=1.0) if "metallic" in args else None,
        material_roughness=_bounded_float(args.get("material_roughness"), 0.58, minimum=0.0, maximum=1.0)
        if "material_roughness" in args
        else None,
        alpha=_bounded_float(args.get("alpha"), 1.0, minimum=0.0, maximum=1.0) if "alpha" in args else None,
        bump_strength=_bounded_float(args.get("bump_strength"), 0.0, minimum=0.0, maximum=10.0) if "bump_strength" in args else None,
        bump_distance=_bounded_float(args.get("bump_distance"), 0.04, minimum=0.0, maximum=10.0) if "bump_distance" in args else None,
        wave_type=str(args.get("wave_type") or "BANDS"),
        replace_existing_links=bool(args.get("replace_existing_links", True)),
        assign_to_objects=bool(args.get("assign_to_objects", True)),
        object_names=args.get("object_names") if isinstance(args.get("object_names"), list) else None,
        selected_only=bool(args.get("selected_only", True)),
        label=args.get("label", "Create procedural texture material"),
    )


def uv_unwrap(context, args):
    return advanced_helpers.uv_unwrap(
        context,
        object_names=args.get("object_names") if isinstance(args.get("object_names"), list) else None,
        selected_only=bool(args.get("selected_only", True)),
        method=str(args.get("method") or "smart_project"),
        uv_map_name=str(args.get("uv_map_name") or "Agent Bridge UVs"),
        replace_existing=bool(args.get("replace_existing", False)),
        margin=float(args.get("margin", 0.02)),
        pack_islands=bool(args.get("pack_islands", True)),
        projection_axis=str(args.get("projection_axis") or "Z"),
        label=args.get("label", "UV unwrap"),
    )


def mark_uv_seams(context, args):
    return advanced_helpers.mark_uv_seams(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        mode=str(args.get("mode") or "sharp_angle"),
        angle_degrees=_bounded_float(args.get("angle_degrees"), 60.0, minimum=0.0, maximum=180.0),
        include_boundary=bool(args.get("include_boundary", True)),
        clear_existing=bool(args.get("clear_existing", False)),
        label=args.get("label", "Mark UV seams"),
    )


def inspect_uv_layout(context, args):
    return advanced_helpers.inspect_uv_layout(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        include_children=bool(args.get("include_children", True)),
        uv_map_name=str(args.get("uv_map_name") or ""),
        max_objects=_bounded_int(args.get("max_objects"), 64, minimum=1, maximum=256),
        max_overlap_pairs=_bounded_int(args.get("max_overlap_pairs"), 200, minimum=0, maximum=1000),
    )


def add_geometry_nodes_modifier(context, args):
    return advanced_helpers.add_geometry_nodes_modifier(
        context,
        name=str(args.get("name") or "Agent Bridge Geometry Nodes"),
        node_group_name=str(args.get("node_group_name") or "Agent Bridge Geometry Nodes"),
        template=str(args.get("template") or "passthrough"),
        selected_only=bool(args.get("selected_only", True)),
        label=args.get("label", "Add Geometry Nodes modifier"),
    )


def add_window_materials(context, args):
    return advanced_helpers.add_window_materials(
        context,
        target_name=str(args.get("target_name") or ""),
        material_name=str(args.get("material_name") or "Agent Bridge Blue Glass"),
        color=_float_list(args.get("color"), 4, (0.08, 0.35, 0.65, 0.42)),
        create_panels=bool(args.get("create_panels", True)),
        label=args.get("label", "Add window materials"),
    )


def create_material_palette(context, args):
    return advanced_helpers.create_material_palette(
        context,
        palette_name=str(args.get("palette_name") or "Agent Bridge Material Palette"),
        palette=str(args.get("palette") or "product_neutral"),
        create_swatches=bool(args.get("create_swatches", True)),
        assign_to_selected=bool(args.get("assign_to_selected", False)),
        label=args.get("label", "Create material palette"),
    )


def register(handler_registry, specs):
    for spec in specs:
        try:
            handler = globals()[spec.handler_key]
        except KeyError as exc:
            raise KeyError(f"Missing handler {spec.handler_key} for {spec.name}") from exc
        handler_registry.register(spec.name, handler)
