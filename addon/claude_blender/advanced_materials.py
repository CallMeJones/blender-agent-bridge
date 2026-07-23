"""Advanced Blender helpers for materials nodes."""



from __future__ import annotations

import math
import os
import re
import time

import bpy
from mathutils import Vector

from . import blender_compat, live_preview, viewport_capture

from .advanced_support import (
    MATERIAL_PALETTES,
    _bounds_world,
    _clamped_float,
    _create_cube_object,
    _ensure_principled_material,
    _find_node,
    _material_for_color,
    _mesh_edit_blockers,
    _preserve_selection,
    _record_scene_render,
    _record_shader_material,
    _resolve_edit_objects,
    _set_socket_value,
)



SHADER_MATERIAL_PRESETS = {
    "custom": {},
    "brushed_metal": {
        "base_color": (0.55, 0.56, 0.54, 1.0),
        "metallic": 1.0,
        "roughness": 0.28,
        "alpha": 1.0,
        "emission_strength": 0.0,
    },
    "brushed_chrome": {
        "base_color": (0.82, 0.84, 0.82, 1.0),
        "metallic": 1.0,
        "roughness": 0.16,
        "alpha": 1.0,
        "emission_strength": 0.0,
    },
    "painted_enamel": {
        "base_color": (0.86, 0.08, 0.04, 1.0),
        "metallic": 0.0,
        "roughness": 0.24,
        "alpha": 1.0,
        "emission_strength": 0.0,
    },
    "matte_plastic": {
        "base_color": (0.08, 0.18, 0.42, 1.0),
        "metallic": 0.0,
        "roughness": 0.72,
        "alpha": 1.0,
        "emission_strength": 0.0,
    },
    "clear_glass": {
        "base_color": (0.72, 0.9, 1.0, 0.32),
        "metallic": 0.0,
        "roughness": 0.04,
        "alpha": 0.32,
        "emission_strength": 0.0,
    },
    "emissive_accent": {
        "base_color": (0.05, 0.26, 1.0, 1.0),
        "metallic": 0.0,
        "roughness": 0.18,
        "alpha": 1.0,
        "emission_color": (0.05, 0.38, 1.0, 1.0),
        "emission_strength": 1.8,
    },
    "matte_ceramic": {
        "base_color": (0.86, 0.84, 0.78, 1.0),
        "metallic": 0.0,
        "roughness": 0.58,
        "alpha": 1.0,
        "emission_strength": 0.0,
    },
    "rubber_black": {
        "base_color": (0.008, 0.008, 0.007, 1.0),
        "metallic": 0.0,
        "roughness": 0.86,
        "alpha": 1.0,
        "emission_strength": 0.0,
    },
    "warm_wood": {
        "base_color": (0.48, 0.28, 0.12, 1.0),
        "metallic": 0.0,
        "roughness": 0.42,
        "alpha": 1.0,
        "emission_strength": 0.0,
    },
    "screen_glow": {
        "base_color": (0.02, 0.08, 0.16, 1.0),
        "metallic": 0.0,
        "roughness": 0.2,
        "alpha": 1.0,
        "emission_color": (0.02, 0.62, 1.0, 1.0),
        "emission_strength": 2.4,
    },
}

UV_UNWRAP_METHODS = {"smart_project", "cube_project", "planar_project"}

UV_PROJECTION_AXES = {"X", "Y", "Z"}

UV_SEAM_MODES = {"sharp_angle", "boundary", "sharp_and_boundary", "clear"}

TEXTURE_IMAGE_EXTENSIONS = {".bmp", ".exr", ".hdr", ".jpeg", ".jpg", ".png", ".tga", ".tif", ".tiff", ".webp"}

IMAGE_TEXTURE_MAP_SPECS = {
    "base_color": {"socket_names": ("Base Color",), "colorspace": "sRGB", "output": "Color"},
    "roughness": {"socket_names": ("Roughness",), "colorspace": "Non-Color", "output": "Color"},
    "metallic": {"socket_names": ("Metallic",), "colorspace": "Non-Color", "output": "Color"},
    "normal": {"socket_names": ("Normal",), "colorspace": "Non-Color", "normal_map": True},
    "alpha": {"socket_names": ("Alpha",), "colorspace": "Non-Color", "output": "Alpha"},
    "emission": {"socket_names": ("Emission Color",), "colorspace": "sRGB", "output": "Color"},
    "ambient_occlusion": {"colorspace": "Non-Color", "output": "Color"},
    "arm": {"colorspace": "Non-Color", "packed_channels": {"ambient_occlusion": "Red", "roughness": "Green", "metallic": "Blue"}},
    "orm": {"colorspace": "Non-Color", "packed_channels": {"ambient_occlusion": "Red", "roughness": "Green", "metallic": "Blue"}},
    "bump": {"socket_names": ("Normal",), "colorspace": "Non-Color", "bump_map": True},
    "displacement": {"colorspace": "Non-Color", "warn_only": True},
}

BAKE_MAP_SPECS = {
    "ambient_occlusion": {"bake_type": "AO", "suffix": "ao", "colorspace": "Non-Color"},
    "normal": {"bake_type": "NORMAL", "suffix": "normal", "colorspace": "Non-Color"},
    "base_color": {"bake_type": "DIFFUSE", "suffix": "base_color", "colorspace": "sRGB", "pass_filter": {"COLOR"}},
}

BAKE_MAP_ALIASES = {
    "ao": "ambient_occlusion",
    "ambient_occlusion": "ambient_occlusion",
    "ambient-occlusion": "ambient_occlusion",
    "ambient occlusion": "ambient_occlusion",
    "normal": "normal",
    "normal_map": "normal",
    "normal-map": "normal",
    "normal map": "normal",
    "base_color": "base_color",
    "base-color": "base_color",
    "base color": "base_color",
    "diffuse": "base_color",
    "diffuse_color": "base_color",
    "diffuse-color": "base_color",
    "diffuse color": "base_color",
    "albedo": "base_color",
}

PROCEDURAL_TEXTURE_TYPES = {"noise", "voronoi", "wave", "checker"}

PROCEDURAL_TEXTURE_PRESETS = {
    "custom": {},
    "stone_noise": {
        "texture_type": "noise",
        "color_a": (0.18, 0.17, 0.15, 1.0),
        "color_b": (0.68, 0.66, 0.58, 1.0),
        "scale": 38.0,
        "detail": 12.0,
        "texture_roughness": 0.58,
        "distortion": 8.0,
        "material_roughness": 0.82,
        "bump_strength": 0.08,
        "bump_distance": 0.04,
    },
    "marble_noise": {
        "texture_type": "noise",
        "color_a": (0.05, 0.05, 0.052, 1.0),
        "color_b": (0.86, 0.84, 0.78, 1.0),
        "scale": 18.0,
        "detail": 14.0,
        "texture_roughness": 0.62,
        "distortion": 15.0,
        "material_roughness": 0.28,
        "bump_strength": 0.035,
        "bump_distance": 0.025,
    },
    "wood_wave": {
        "texture_type": "wave",
        "color_a": (0.28, 0.13, 0.045, 1.0),
        "color_b": (0.78, 0.46, 0.19, 1.0),
        "scale": 14.0,
        "detail": 7.0,
        "texture_roughness": 0.56,
        "distortion": 12.0,
        "material_roughness": 0.46,
        "bump_strength": 0.05,
        "bump_distance": 0.035,
        "wave_type": "RINGS",
    },
    "cellular_voronoi": {
        "texture_type": "voronoi",
        "color_a": (0.04, 0.055, 0.065, 1.0),
        "color_b": (0.5, 0.74, 0.78, 1.0),
        "scale": 28.0,
        "detail": 4.0,
        "texture_roughness": 0.5,
        "randomness": 0.82,
        "material_roughness": 0.55,
        "bump_strength": 0.04,
        "bump_distance": 0.025,
    },
    "fabric_checker": {
        "texture_type": "checker",
        "color_a": (0.06, 0.07, 0.08, 1.0),
        "color_b": (0.34, 0.38, 0.39, 1.0),
        "scale": 34.0,
        "material_roughness": 0.92,
        "bump_strength": 0.025,
        "bump_distance": 0.015,
    },
}

GEOMETRY_NODE_TEMPLATES = {"passthrough", "transform", "join_geometry", "set_position", "subdivide_mesh"}

def create_shader_material(
    context,
    *,
    name,
    base_color=None,
    metallic=None,
    roughness=None,
    alpha=None,
    emission_color=None,
    emission_strength=None,
    preset="custom",
    assign_to_selected=True,
    label="Create shader material",
):
    transaction = live_preview.begin(label, context)
    preset_key = str(preset or "custom").strip().lower().replace("-", "_").replace(" ", "_")
    preset_spec = SHADER_MATERIAL_PRESETS.get(preset_key) or {}
    if preset_key not in SHADER_MATERIAL_PRESETS:
        preset_key = "custom"
    if base_color is None:
        base_color = preset_spec.get("base_color", (0.8, 0.8, 0.8, 1.0))
    if metallic is None:
        metallic = preset_spec.get("metallic", 0.0)
    if roughness is None:
        roughness = preset_spec.get("roughness", 0.5)
    if alpha is None:
        alpha = preset_spec.get("alpha", 1.0)
    if emission_color is None:
        emission_color = preset_spec.get("emission_color")
    if emission_strength is None:
        emission_strength = preset_spec.get("emission_strength", 0.0)
    material = bpy.data.materials.get(name)
    created = material is None
    if material is None:
        material = bpy.data.materials.new(name or "Agent Bridge Shader Material")
        live_preview._record_created_id("material", material.name)
    else:
        _record_shader_material(material)

    rgba = (
        float(base_color[0]),
        float(base_color[1]),
        float(base_color[2]),
        float(base_color[3]) if len(base_color) > 3 else float(alpha),
    )
    material.diffuse_color = rgba
    principled = _ensure_principled_material(material)
    _set_socket_value(principled.inputs.get("Base Color"), rgba)
    _set_socket_value(principled.inputs.get("Metallic"), max(0.0, min(1.0, float(metallic))))
    _set_socket_value(principled.inputs.get("Roughness"), max(0.0, min(1.0, float(roughness))))
    _set_socket_value(principled.inputs.get("Alpha"), max(0.0, min(1.0, float(alpha))))
    if emission_color is not None:
        emission = (
            float(emission_color[0]),
            float(emission_color[1]),
            float(emission_color[2]),
            float(emission_color[3]) if len(emission_color) > 3 else 1.0,
        )
        _set_socket_value(principled.inputs.get("Emission Color"), emission)
    _set_socket_value(principled.inputs.get("Emission Strength"), max(0.0, float(emission_strength)))
    if alpha < 1.0:
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "BLENDED"
        elif hasattr(material, "blend_method"):
            material.blend_method = "BLEND"

    assigned = []
    if assign_to_selected:
        for obj in context.selected_objects:
            if obj.type != "MESH" or obj.data is None:
                continue
            live_preview._record_object_materials(obj)
            if obj.material_slots:
                obj.material_slots[0].material = material
            else:
                obj.data.materials.append(material)
            assigned.append(obj.name)

    transaction["applied_steps"].append(
        {
            "type": "create_shader_material",
            "label": label,
            "material": material.name,
            "created": created,
            "preset": preset_key,
            "assigned_objects": assigned,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"{'Created' if created else 'Updated'} shader material {material.name}",
        "material": material.name,
        "preset": preset_key,
        "assigned_objects": assigned,
        "transaction_id": transaction["id"],
    }

def _resolve_texture_image_path(path):
    raw = str(path or "").strip()
    if not raw:
        return "", "empty path"
    resolved = bpy.path.abspath(raw) if raw.startswith("//") else os.path.expanduser(raw)
    resolved = os.path.abspath(resolved)
    extension = os.path.splitext(resolved)[1].lower()
    if extension not in TEXTURE_IMAGE_EXTENSIONS:
        return resolved, f"unsupported image extension {extension or '(none)'}"
    if not os.path.isfile(resolved):
        return resolved, "file does not exist"
    return resolved, ""

def _load_preview_image(path, *, colorspace):
    before_names = set(bpy.data.images.keys())
    image = bpy.data.images.load(path, check_existing=True)
    if image.name not in before_names:
        live_preview._record_created_id("image", image.name)
    else:
        _record_image_settings(image)
    try:
        image.colorspace_settings.name = colorspace
    except Exception:
        pass
    return image

def _record_image_settings(image):
    transaction = live_preview.begin()
    key = f"image:{image.name}:settings"
    if key in transaction["before_state"]:
        return
    transaction["before_state"][key] = {
        "kind": "image_settings",
        "image_name": image.name,
        "colorspace": getattr(image.colorspace_settings, "name", ""),
    }
    transaction["changed_data_blocks"].append(image.name)

def _principled_socket(principled, names):
    for name in names:
        socket = principled.inputs.get(name)
        if socket:
            return socket
    return None

def _remove_links_to_socket(node_tree, socket):
    removed = 0
    for link in list(node_tree.links):
        if link.to_socket == socket:
            node_tree.links.remove(link)
            removed += 1
    return removed

def _socket_by_name(sockets, *names):
    for name in names:
        socket = sockets.get(name)
        if socket:
            return socket
    return None

def _link_uv_map_node(material, image_node, uv_map_name, uv_nodes):
    uv_name = str(uv_map_name or "").strip()
    if not uv_name:
        return ""
    uv_node = uv_nodes.get(uv_name)
    if uv_node is None:
        uv_node = material.node_tree.nodes.new(type="ShaderNodeUVMap")
        uv_node.name = f"Agent Bridge UV Map {uv_name}"
        uv_node.label = uv_node.name
        uv_node.uv_map = uv_name
        uv_node.location = (-860, 320 - len(uv_nodes) * 160)
        uv_nodes[uv_name] = uv_node
    vector_input = image_node.inputs.get("Vector")
    uv_output = uv_node.outputs.get("UV")
    if vector_input and uv_output:
        material.node_tree.links.new(uv_output, vector_input)
    return uv_node.name

def _create_texture_image_node(material, *, map_type, image, index, uv_map_name="", uv_nodes=None):
    nodes = material.node_tree.nodes
    image_node = nodes.new(type="ShaderNodeTexImage")
    image_node.name = f"Agent Bridge {map_type.replace('_', ' ').title()} Texture"
    image_node.label = image_node.name
    image_node.image = image
    image_node.location = (-620, 260 - index * 180)
    if uv_nodes is None:
        uv_nodes = {}
    uv_node_name = _link_uv_map_node(material, image_node, uv_map_name, uv_nodes)
    return image_node, uv_node_name

def _make_separate_color_node(material, image_node, index):
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    separate_node = nodes.new(type="ShaderNodeSeparateColor")
    separate_node.name = f"Agent Bridge Packed PBR Channels {index + 1}"
    separate_node.label = separate_node.name
    separate_node.location = (-350, 260 - index * 180)
    color_output = image_node.outputs.get("Color")
    color_input = separate_node.inputs.get("Color")
    if color_output and color_input:
        links.new(color_output, color_input)
    return separate_node

def _socket_link_blocker(socket, map_type, *, replace_existing_links, linked_sockets):
    if socket is None:
        return f"Skipped {map_type}: Principled socket is not available"
    if socket.name in linked_sockets:
        return f"Skipped {map_type}: {socket.name} already has a map from this material update"
    if socket.is_linked and not replace_existing_links:
        return f"Skipped {map_type}: target socket is already linked"
    return ""

def _ambient_occlusion_link_blocker(principled, *, replace_existing_links, linked_sockets):
    base_socket = principled.inputs.get("Base Color")
    if base_socket is None:
        return "Skipped ambient occlusion: Principled Base Color socket is not available"
    if not list(base_socket.links):
        return "Loaded ambient occlusion map but did not multiply it: Base Color has no image link"
    if base_socket.name not in linked_sockets and base_socket.is_linked and not replace_existing_links:
        return "Skipped ambient occlusion multiply: target Base Color is already linked"
    return ""

def _link_ambient_occlusion(material, principled, ao_output, warnings, *, replace_existing_links, linked_sockets):
    if ao_output is None:
        warnings.append("Skipped ambient occlusion: image texture output is not available")
        return None
    blocker = _ambient_occlusion_link_blocker(
        principled,
        replace_existing_links=replace_existing_links,
        linked_sockets=linked_sockets,
    )
    if blocker:
        warnings.append(blocker)
        return None
    base_socket = principled.inputs["Base Color"]
    existing_links = list(base_socket.links)
    previous_output = existing_links[-1].from_socket
    material.node_tree.links.remove(existing_links[-1])
    mix_node = material.node_tree.nodes.new(type="ShaderNodeMixRGB")
    mix_node.name = "Agent Bridge Ambient Occlusion Multiply"
    mix_node.label = mix_node.name
    mix_node.blend_type = "MULTIPLY"
    mix_node.location = (-130, 260)
    _set_socket_value(mix_node.inputs.get("Factor"), 1.0)
    material.node_tree.links.new(previous_output, mix_node.inputs["Color1"])
    material.node_tree.links.new(ao_output, mix_node.inputs["Color2"])
    material.node_tree.links.new(mix_node.outputs["Color"], base_socket)
    linked_sockets.add(base_socket.name)
    return mix_node

def create_image_texture_material(
    context,
    *,
    name,
    base_color_path=None,
    roughness_path=None,
    metallic_path=None,
    normal_path=None,
    alpha_path=None,
    emission_path=None,
    ambient_occlusion_path=None,
    arm_path=None,
    orm_path=None,
    bump_path=None,
    displacement_path=None,
    base_color=None,
    metallic=None,
    roughness=None,
    alpha=None,
    emission_strength=None,
    normal_strength=1.0,
    bump_strength=0.12,
    bump_distance=0.05,
    uv_map_name="",
    replace_existing_links=True,
    assign_to_objects=True,
    object_names=None,
    selected_only=True,
    label="Create image texture material",
):
    requested_paths = {
        "base_color": base_color_path,
        "roughness": roughness_path,
        "metallic": metallic_path,
        "normal": normal_path,
        "alpha": alpha_path,
        "emission": emission_path,
        "ambient_occlusion": ambient_occlusion_path,
        "arm": arm_path,
        "orm": orm_path,
        "bump": bump_path,
        "displacement": displacement_path,
    }
    requested_paths = {key: value for key, value in requested_paths.items() if str(value or "").strip()}
    if not requested_paths:
        return {
            "ok": False,
            "message": "create_image_texture_material needs at least one local image map path",
            "required_hint": "Use create_shader_material for scalar-only materials.",
        }

    resolved_paths = {}
    path_errors = []
    for map_type, path in requested_paths.items():
        resolved, error = _resolve_texture_image_path(path)
        if error:
            path_errors.append({"map_type": map_type, "path": str(path), "resolved_path": resolved, "error": error})
        else:
            resolved_paths[map_type] = resolved
    if path_errors:
        return {
            "ok": False,
            "message": "Texture image path validation failed",
            "path_errors": path_errors,
        }

    transaction = live_preview.begin(label, context)
    material = bpy.data.materials.get(name)
    created = material is None
    if material is None:
        material = bpy.data.materials.new(name or "Agent Bridge Image Texture Material")
        live_preview._record_created_id("material", material.name)
    else:
        _record_shader_material(material)

    if base_color is None and created:
        base_color = (0.8, 0.8, 0.8, 1.0)
    if metallic is None and created:
        metallic = 0.0
    if roughness is None and created:
        roughness = 0.5
    if alpha is None and created:
        alpha = 1.0
    if emission_strength is None:
        emission_strength = 0.0

    principled = _ensure_principled_material(material)
    if base_color is not None:
        rgba = (
            float(base_color[0]),
            float(base_color[1]),
            float(base_color[2]),
            float(base_color[3]) if len(base_color) > 3 else float(alpha or 1.0),
        )
        material.diffuse_color = rgba
        _set_socket_value(principled.inputs.get("Base Color"), rgba)
    if metallic is not None:
        _set_socket_value(principled.inputs.get("Metallic"), max(0.0, min(1.0, float(metallic))))
    if roughness is not None:
        _set_socket_value(principled.inputs.get("Roughness"), max(0.0, min(1.0, float(roughness))))
    if alpha is not None:
        _set_socket_value(principled.inputs.get("Alpha"), max(0.0, min(1.0, float(alpha))))
    _set_socket_value(principled.inputs.get("Emission Strength"), max(0.0, float(emission_strength)))

    nodes = material.node_tree.nodes
    links = material.node_tree.links
    linked_maps = []
    warnings = []
    uv_nodes = {}
    linked_sockets = set()

    def link_output_to_socket(output, socket, map_type, source_node, target_node=None):
        if output is None:
            warnings.append(f"Skipped {map_type}: image texture output is not available")
            return False
        blocker = _socket_link_blocker(
            socket,
            map_type,
            replace_existing_links=replace_existing_links,
            linked_sockets=linked_sockets,
        )
        if blocker:
            warnings.append(blocker)
            return False
        if socket.is_linked:
            _remove_links_to_socket(material.node_tree, socket)
        links.new(output, socket)
        linked_sockets.add(socket.name)
        linked_maps.append(
            {
                "map_type": map_type,
                "path": source_node.image.filepath if getattr(source_node, "image", None) else "",
                "image": source_node.image.name if getattr(source_node, "image", None) else "",
                "image_node": source_node.name,
                "target_node": target_node.name if target_node else source_node.name,
                "socket": socket.name,
            }
        )
        return True

    for index, (map_type, path) in enumerate(resolved_paths.items()):
        spec = IMAGE_TEXTURE_MAP_SPECS[map_type]
        if spec.get("warn_only"):
            warnings.append(f"Validated {map_type} map path but did not wire true displacement yet")
            continue
        if spec.get("packed_channels"):
            packed_blockers = {}
            for packed_target in spec["packed_channels"]:
                if packed_target == "ambient_occlusion":
                    blocker = _ambient_occlusion_link_blocker(
                        principled,
                        replace_existing_links=replace_existing_links,
                        linked_sockets=linked_sockets,
                    )
                else:
                    socket = _principled_socket(principled, IMAGE_TEXTURE_MAP_SPECS[packed_target]["socket_names"])
                    blocker = _socket_link_blocker(
                        socket,
                        packed_target,
                        replace_existing_links=replace_existing_links,
                        linked_sockets=linked_sockets,
                    )
                if blocker:
                    packed_blockers[packed_target] = blocker
            if len(packed_blockers) == len(spec["packed_channels"]):
                warnings.extend(packed_blockers.values())
                continue
        elif map_type == "ambient_occlusion":
            blocker = _ambient_occlusion_link_blocker(
                principled,
                replace_existing_links=replace_existing_links,
                linked_sockets=linked_sockets,
            )
            if blocker:
                warnings.append(blocker)
                continue
        else:
            socket = _principled_socket(principled, spec["socket_names"])
            blocker = _socket_link_blocker(
                socket,
                map_type,
                replace_existing_links=replace_existing_links,
                linked_sockets=linked_sockets,
            )
            if blocker:
                warnings.append(blocker)
                continue
        image = _load_preview_image(path, colorspace=spec["colorspace"])
        image_node, uv_node_name = _create_texture_image_node(
            material,
            map_type=map_type,
            image=image,
            index=index,
            uv_map_name=uv_map_name,
            uv_nodes=uv_nodes,
        )
        target_node = image_node

        if spec.get("packed_channels"):
            separate_node = _make_separate_color_node(material, image_node, index)
            channel_outputs = separate_node.outputs
            for packed_target, channel_name in spec["packed_channels"].items():
                output = _socket_by_name(channel_outputs, channel_name)
                if packed_target == "ambient_occlusion":
                    mix_node = _link_ambient_occlusion(
                        material,
                        principled,
                        output,
                        warnings,
                        replace_existing_links=replace_existing_links,
                        linked_sockets=linked_sockets,
                    )
                    if mix_node is not None:
                        linked_maps.append(
                            {
                                "map_type": "ambient_occlusion",
                                "source_map": map_type,
                                "channel": channel_name,
                                "path": path,
                                "image": image.name,
                                "image_node": image_node.name,
                                "target_node": mix_node.name,
                                "socket": "Base Color",
                                "uv_map": uv_map_name,
                                "uv_node": uv_node_name,
                            }
                        )
                    continue
                socket = _principled_socket(principled, IMAGE_TEXTURE_MAP_SPECS[packed_target]["socket_names"])
                if link_output_to_socket(output, socket, packed_target, image_node, separate_node):
                    linked_maps[-1]["source_map"] = map_type
                    linked_maps[-1]["channel"] = channel_name
                    linked_maps[-1]["uv_map"] = uv_map_name
                    linked_maps[-1]["uv_node"] = uv_node_name
            continue

        if map_type == "ambient_occlusion":
            output = image_node.outputs.get(spec.get("output", "Color"))
            mix_node = _link_ambient_occlusion(
                material,
                principled,
                output,
                warnings,
                replace_existing_links=replace_existing_links,
                linked_sockets=linked_sockets,
            )
            if mix_node is not None:
                linked_maps.append(
                    {
                        "map_type": map_type,
                        "path": path,
                        "image": image.name,
                        "image_node": image_node.name,
                        "target_node": mix_node.name,
                        "socket": "Base Color",
                        "uv_map": uv_map_name,
                        "uv_node": uv_node_name,
                    }
                )
            continue

        if spec.get("normal_map"):
            socket = _principled_socket(principled, spec["socket_names"])
            normal_node = nodes.new(type="ShaderNodeNormalMap")
            normal_node.name = "Agent Bridge Normal Map"
            normal_node.label = normal_node.name
            normal_node.location = (-350, 260 - index * 180)
            _set_socket_value(normal_node.inputs.get("Strength"), max(0.0, min(10.0, float(normal_strength))))
            links.new(image_node.outputs["Color"], normal_node.inputs["Color"])
            link_output_to_socket(normal_node.outputs["Normal"], socket, map_type, image_node, normal_node)
            target_node = normal_node
            if linked_maps and linked_maps[-1]["map_type"] == map_type:
                linked_maps[-1]["uv_map"] = uv_map_name
                linked_maps[-1]["uv_node"] = uv_node_name
            continue

        if spec.get("bump_map"):
            socket = _principled_socket(principled, spec["socket_names"])
            bump_node = nodes.new(type="ShaderNodeBump")
            bump_node.name = "Agent Bridge Bump Map"
            bump_node.label = bump_node.name
            bump_node.location = (-350, 260 - index * 180)
            _set_socket_value(bump_node.inputs.get("Strength"), max(0.0, min(10.0, float(bump_strength))))
            _set_socket_value(bump_node.inputs.get("Distance"), max(0.0, min(10.0, float(bump_distance))))
            links.new(image_node.outputs["Color"], bump_node.inputs["Height"])
            if not link_output_to_socket(bump_node.outputs["Normal"], socket, map_type, image_node, bump_node):
                warnings.append("Bump map was loaded but not wired because the normal socket is already owned")
            if linked_maps and linked_maps[-1]["map_type"] == map_type:
                linked_maps[-1]["uv_map"] = uv_map_name
                linked_maps[-1]["uv_node"] = uv_node_name
            continue

        socket = _principled_socket(principled, spec["socket_names"])
        output_name = spec.get("output", "Color")
        if output_name == "Alpha" and image_node.outputs.get("Alpha"):
            output = image_node.outputs["Alpha"]
        else:
            output = image_node.outputs.get("Color")
        link_output_to_socket(output, socket, map_type, image_node, target_node)
        if linked_maps and linked_maps[-1]["map_type"] == map_type:
            linked_maps[-1]["uv_map"] = uv_map_name
            linked_maps[-1]["uv_node"] = uv_node_name

    if (alpha is not None and float(alpha) < 1.0) or "alpha" in resolved_paths:
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "BLENDED"
        elif hasattr(material, "blend_method"):
            material.blend_method = "BLEND"

    assigned = []
    missing = []
    if assign_to_objects:
        objects, missing = _resolve_edit_objects(context, object_names=object_names, selected_only=selected_only)
        for obj in objects:
            if obj.type != "MESH" or obj.data is None:
                continue
            live_preview._record_object_materials(obj)
            if obj.material_slots:
                obj.material_slots[0].material = material
            else:
                obj.data.materials.append(material)
            assigned.append(obj.name)
            if uv_map_name and obj.data.uv_layers.get(str(uv_map_name)) is None:
                warnings.append(f"Assigned {material.name} to {obj.name}, but UV map {uv_map_name!r} was not found on that mesh")

    transaction["applied_steps"].append(
        {
            "type": "create_image_texture_material",
            "label": label,
            "material": material.name,
            "created": created,
            "maps": [item["map_type"] for item in linked_maps],
            "assigned_objects": assigned,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"{'Created' if created else 'Updated'} image texture material {material.name}",
        "material": material.name,
        "maps": linked_maps,
        "assigned_objects": assigned,
        "missing_object_names": missing,
        "warnings": warnings,
        "transaction_id": transaction["id"],
    }

MATERIAL_TEXTURE_MAP_ALIASES = {
    "base_color": ("base color", "base_color", "albedo", "diffuse", "color texture"),
    "roughness": ("roughness", "rough"),
    "metallic": ("metallic", "metalness", "metal"),
    "normal": ("normal", "normal map"),
    "alpha": ("alpha", "opacity", "transparent"),
    "emission": ("emission", "emissive"),
    "ambient_occlusion": ("ambient occlusion", "ambient_occlusion", " occlusion", " ao "),
    "arm": (" arm ", "arm texture", "arm map"),
    "orm": (" orm ", "orm texture", "orm map"),
    "bump": ("bump", "height"),
    "displacement": ("displacement", "displace"),
}

def _normalize_material_name_list(names):
    if not isinstance(names, list):
        return []
    return [str(name).strip() for name in names if str(name or "").strip()]

def _resolve_material_setup_targets(context, *, material_names=None, object_names=None, selected_only=True, max_materials=32):
    requested_materials = _normalize_material_name_list(material_names)
    max_count = max(1, min(128, int(max_materials or 32)))
    materials = []
    missing_materials = []
    seen = set()
    objects = []
    missing_objects = []

    should_resolve_objects = bool(object_names) or (not requested_materials and selected_only)
    if should_resolve_objects:
        objects, missing_objects = _resolve_edit_objects(context, object_names=object_names, selected_only=selected_only)

    for material_name in requested_materials:
        material = bpy.data.materials.get(material_name)
        if material is None:
            missing_materials.append(material_name)
            continue
        if material.name not in seen:
            seen.add(material.name)
            materials.append(material)
        if len(materials) >= max_count:
            break

    if not requested_materials:
        for obj in objects:
            for slot in getattr(obj, "material_slots", []) or []:
                material = slot.material
                if material and material.name not in seen:
                    seen.add(material.name)
                    materials.append(material)
                if len(materials) >= max_count:
                    break
            if len(materials) >= max_count:
                break

    return materials, objects, missing_materials, missing_objects

def _objects_using_material(context, material, candidate_objects=None):
    if material is None:
        return []
    pool = candidate_objects if candidate_objects else list(getattr(context.scene, "objects", []) or [])
    objects = []
    for obj in pool:
        for slot in getattr(obj, "material_slots", []) or []:
            if slot.material == material:
                objects.append(obj)
                break
    return objects

def _infer_material_texture_map_type(node):
    text_parts = [getattr(node, "name", ""), getattr(node, "label", "")]
    image = getattr(node, "image", None)
    if image:
        text_parts.extend([getattr(image, "name", ""), getattr(image, "filepath", "")])
    normalized = f" {' '.join(text_parts).lower().replace('_', ' ')} "
    for map_type, aliases in MATERIAL_TEXTURE_MAP_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return map_type
    return "unknown"

def _image_texture_nodes(material):
    tree = blender_compat.node_tree(material)
    if tree is None:
        return []
    return [node for node in tree.nodes if getattr(node, "type", "") == "TEX_IMAGE"]

def _node_has_outgoing_links(material, node):
    if material is None or not material.node_tree:
        return False
    return any(link.from_node == node for link in material.node_tree.links)

def _socket_identity(socket):
    node = getattr(socket, "node", None)
    return (getattr(node, "name", ""), getattr(socket, "identifier", getattr(socket, "name", "")))

def _socket_reaches_socket(material, output_socket, target_socket, *, max_depth=8):
    if material is None or material.node_tree is None or output_socket is None or target_socket is None:
        return False
    links = list(material.node_tree.links)
    stack = [(output_socket, 0)]
    seen = set()
    while stack:
        socket, depth = stack.pop()
        key = _socket_identity(socket)
        if key in seen:
            continue
        seen.add(key)
        for link in links:
            if link.from_socket != socket:
                continue
            if link.to_socket == target_socket:
                return True
            if depth >= max_depth:
                continue
            for next_output in getattr(link.to_node, "outputs", []) or []:
                stack.append((next_output, depth + 1))
    return False

def _material_texture_target_socket(principled, map_type):
    if principled is None:
        return None
    if map_type == "ambient_occlusion":
        return principled.inputs.get("Base Color")
    spec = IMAGE_TEXTURE_MAP_SPECS.get(map_type) or {}
    socket_names = spec.get("socket_names")
    if not socket_names:
        return None
    return _principled_socket(principled, socket_names)

def _image_color_output(node):
    if node is None:
        return None
    return node.outputs.get("Color") or (node.outputs[0] if node.outputs else None)

def _shader_path_issue_for_texture(material, principled, node, map_type):
    if map_type not in IMAGE_TEXTURE_MAP_SPECS:
        return ""
    spec = IMAGE_TEXTURE_MAP_SPECS.get(map_type) or {}
    if spec.get("warn_only"):
        return ""
    target_socket = _material_texture_target_socket(principled, map_type)
    if target_socket is None:
        return ""
    output = _image_color_output(node)
    if not _socket_reaches_socket(material, output, target_socket):
        return f"{node.name}: {map_type} map does not reach Principled {target_socket.name}"
    return ""

def _packed_channel_shader_path_issues(material, principled, node, map_type):
    spec = IMAGE_TEXTURE_MAP_SPECS.get(map_type) or {}
    packed_channels = spec.get("packed_channels") or {}
    if not packed_channels:
        return []
    image_output = _image_color_output(node)
    separate_nodes = []
    for link in list(material.node_tree.links):
        if link.from_socket == image_output and getattr(link.to_node, "type", "") == "SEPARATE_COLOR":
            separate_nodes.append(link.to_node)
    if not separate_nodes:
        return [f"{node.name}: packed {map_type} map is not connected to a Separate Color node"]

    issues = []
    for packed_target, channel_name in packed_channels.items():
        target_socket = _material_texture_target_socket(principled, packed_target)
        if target_socket is None:
            continue
        channel_reaches_target = False
        for separate_node in separate_nodes:
            channel_output = _socket_by_name(separate_node.outputs, channel_name)
            if _socket_reaches_socket(material, channel_output, target_socket):
                channel_reaches_target = True
                break
        if not channel_reaches_target:
            issues.append(f"{node.name}: packed {map_type} {channel_name} channel does not reach Principled {target_socket.name}")
    return issues

def _image_node_uv_map_name(node):
    vector_input = node.inputs.get("Vector") if node else None
    if vector_input is None:
        return ""
    for link in list(getattr(vector_input, "links", []) or []):
        from_node = link.from_node
        if getattr(from_node, "type", "") == "UVMAP":
            return str(getattr(from_node, "uv_map", "") or "")
    return ""

def _image_file_report(image):
    if image is None:
        return {
            "image": "",
            "image_datablock_name": "",
            "source_filename": "",
            "filepath": "",
            "source_filepath": "",
            "packed": False,
            "missing": True,
            "message": "image texture node has no image",
        }
    raw_path = str(getattr(image, "filepath", "") or "")
    resolved = bpy.path.abspath(raw_path) if raw_path.startswith("//") else os.path.expanduser(raw_path)
    resolved = os.path.abspath(resolved) if resolved else ""
    packed = bool(getattr(image, "packed_file", None))
    missing = bool(resolved and not packed and not os.path.isfile(resolved))
    return {
        "image": image.name,
        "image_datablock_name": image.name,
        "source_filename": os.path.basename(resolved or raw_path),
        "filepath": resolved,
        "source_filepath": resolved,
        "packed": packed,
        "missing": missing,
        "message": "image file does not exist" if missing else "",
    }

def _expected_material_colorspace(map_type):
    spec = IMAGE_TEXTURE_MAP_SPECS.get(map_type)
    return str((spec or {}).get("colorspace") or "")

def _material_setup_quality(context, material, *, assigned_objects=None, require_uv_maps=False, expected_uv_map_name=""):
    issues = []
    warnings = []
    image_nodes = _image_texture_nodes(material)
    principled = _find_node(material, "BSDF_PRINCIPLED") if blender_compat.node_tree_enabled(material) else None
    require_uv = bool(require_uv_maps or str(expected_uv_map_name or "").strip())
    expected_uv = str(expected_uv_map_name or "").strip()
    assigned_objects = list(assigned_objects or [])
    texture_reports = []

    result = {
        "material": material.name if material else "",
        "use_nodes": blender_compat.node_tree_enabled(material),
        "has_principled": bool(principled),
        "image_texture_count": len(image_nodes),
        "assigned_objects": [obj.name for obj in assigned_objects],
        "textures": texture_reports,
        "issues": issues,
        "warnings": warnings,
        "passed": True,
    }
    if material is None:
        issues.append("material not found")
        result["passed"] = False
        return result
    if not blender_compat.node_tree_enabled(material):
        issues.append("material does not use shader nodes")
        result["passed"] = False
        return result
    if principled is None:
        warnings.append("material has no Principled BSDF node")
    if not image_nodes:
        warnings.append("material has no image texture nodes")

    for node in image_nodes:
        image = getattr(node, "image", None)
        map_type = _infer_material_texture_map_type(node)
        expected_colorspace = _expected_material_colorspace(map_type)
        actual_colorspace = str(getattr(getattr(image, "colorspace_settings", None), "name", "") or "") if image else ""
        file_report = _image_file_report(image)
        uv_map = _image_node_uv_map_name(node)
        linked = _node_has_outgoing_links(material, node)
        shader_path_issues = _packed_channel_shader_path_issues(material, principled, node, map_type)
        if not shader_path_issues:
            shader_path_issue = _shader_path_issue_for_texture(material, principled, node, map_type)
            if shader_path_issue:
                shader_path_issues = [shader_path_issue]
        texture_report = {
            "node": node.name,
            "map_type": map_type,
            "image": file_report["image"],
            "image_datablock_name": file_report["image_datablock_name"],
            "source_filename": file_report["source_filename"],
            "filepath": file_report["filepath"],
            "source_filepath": file_report["source_filepath"],
            "packed": file_report["packed"],
            "file_missing": file_report["missing"],
            "colorspace": actual_colorspace,
            "expected_colorspace": expected_colorspace,
            "uv_map": uv_map,
            "linked": linked,
            "shader_path_ok": not shader_path_issues,
        }
        texture_reports.append(texture_report)
        if file_report["missing"]:
            issues.append(f"{node.name}: {file_report['message']}")
        if image is None:
            issues.append(f"{node.name}: image texture node has no image")
        if expected_colorspace and actual_colorspace and actual_colorspace != expected_colorspace:
            issues.append(f"{node.name}: {map_type} map uses {actual_colorspace} colorspace, expected {expected_colorspace}")
        if not linked:
            issues.append(f"{node.name}: image texture node is not linked to the shader graph")
        issues.extend(shader_path_issues)
        if require_uv and not uv_map:
            active_uv_names = {
                mesh.uv_layers.active.name
                for obj in assigned_objects
                for mesh in [obj.data if getattr(obj, "type", "") == "MESH" else None]
                if mesh and mesh.uv_layers and mesh.uv_layers.active
            }
            if not active_uv_names:
                issues.append(f"{node.name}: image texture node has no explicit UV Map vector input and assigned meshes have no active UV map")
            else:
                texture_report["uv_mode"] = "implicit_active_uv"
                texture_report["active_uv_maps"] = sorted(active_uv_names)
                if expected_uv and active_uv_names != {expected_uv}:
                    issues.append(
                        f"{node.name}: implicit texture coordinates use active UV map(s) {sorted(active_uv_names)!r}, "
                        f"expected {expected_uv!r}"
                    )
        if expected_uv and uv_map and uv_map != expected_uv:
            issues.append(f"{node.name}: uses UV map {uv_map!r}, expected {expected_uv!r}")
        checked_uv = expected_uv or uv_map
        if checked_uv:
            for obj in assigned_objects:
                mesh = obj.data if getattr(obj, "type", "") == "MESH" else None
                if mesh and mesh.uv_layers.get(checked_uv) is None:
                    issues.append(f"{node.name}: assigned object {obj.name} is missing UV map {checked_uv!r}")

    result["passed"] = not issues
    return result

def inspect_material_setup(
    context,
    *,
    material_names=None,
    object_names=None,
    selected_only=True,
    require_uv_maps=False,
    expected_uv_map_name="",
    max_materials=32,
):
    materials, objects, missing_materials, missing_objects = _resolve_material_setup_targets(
        context,
        material_names=material_names,
        object_names=object_names,
        selected_only=selected_only,
        max_materials=max_materials,
    )
    if not materials:
        return {
            "ok": False,
            "passed": False,
            "message": "No materials found for material setup inspection",
            "materials": [],
            "missing_material_names": missing_materials,
            "missing_object_names": missing_objects,
        }
    results = []
    for material in materials:
        assigned_objects = _objects_using_material(context, material, objects)
        results.append(
            _material_setup_quality(
                context,
                material,
                assigned_objects=assigned_objects,
                require_uv_maps=require_uv_maps,
                expected_uv_map_name=expected_uv_map_name,
            )
        )
    issue_count = sum(len(item["issues"]) for item in results)
    warning_count = sum(len(item["warnings"]) for item in results)
    return {
        "ok": True,
        "passed": issue_count == 0,
        "message": "Material setup inspection passed" if issue_count == 0 else "Material setup inspection found issues",
        "materials": results,
        "material_count": len(results),
        "issue_count": issue_count,
        "warning_count": warning_count,
        "missing_material_names": missing_materials,
        "missing_object_names": missing_objects,
        "policy": {
            "require_uv_maps": bool(require_uv_maps),
            "expected_uv_map_name": str(expected_uv_map_name or ""),
        },
    }

def _active_uv_name_from_objects(objects):
    for obj in objects or []:
        mesh = obj.data if getattr(obj, "type", "") == "MESH" else None
        active = mesh.uv_layers.active if mesh and mesh.uv_layers else None
        if active:
            return active.name
    return ""

def repair_material_setup(
    context,
    *,
    material_names=None,
    object_names=None,
    selected_only=True,
    uv_map_name="",
    fix_color_spaces=True,
    reconnect_uv_maps=True,
    max_materials=32,
    label="Repair material setup",
):
    materials, objects, missing_materials, missing_objects = _resolve_material_setup_targets(
        context,
        material_names=material_names,
        object_names=object_names,
        selected_only=selected_only,
        max_materials=max_materials,
    )
    if not materials:
        return {
            "ok": False,
            "message": "No materials found for material setup repair",
            "materials": [],
            "missing_material_names": missing_materials,
            "missing_object_names": missing_objects,
        }

    target_uv_map = str(uv_map_name or "").strip() or _active_uv_name_from_objects(objects)
    transaction = None
    repaired = []
    warnings = []

    def ensure_transaction():
        nonlocal transaction
        if transaction is None:
            transaction = live_preview.begin(label, context)
        return transaction

    for material in materials:
        if not blender_compat.node_tree_enabled(material):
            warnings.append(f"Skipped {material.name}: material does not use shader nodes")
            continue
        image_nodes = _image_texture_nodes(material)
        material_repairs = []

        if fix_color_spaces:
            for node in image_nodes:
                image = getattr(node, "image", None)
                map_type = _infer_material_texture_map_type(node)
                expected = _expected_material_colorspace(map_type)
                if not image or not expected:
                    continue
                actual = str(getattr(image.colorspace_settings, "name", "") or "")
                if actual == expected:
                    continue
                ensure_transaction()
                _record_image_settings(image)
                try:
                    image.colorspace_settings.name = expected
                    material_repairs.append(
                        {
                            "type": "color_space",
                            "node": node.name,
                            "image": image.name,
                            "map_type": map_type,
                            "from": actual,
                            "to": expected,
                        }
                    )
                except Exception as exc:
                    warnings.append(f"Could not set colorspace for {image.name}: {type(exc).__name__}: {exc}")

        if reconnect_uv_maps and target_uv_map:
            assigned_objects = _objects_using_material(context, material, objects)
            missing_uv = []
            for obj in assigned_objects:
                mesh = obj.data if getattr(obj, "type", "") == "MESH" else None
                if mesh and mesh.uv_layers.get(target_uv_map) is None:
                    missing_uv.append(obj.name)
            if missing_uv:
                warnings.append(f"Skipped UV relink for {material.name}: {', '.join(missing_uv[:5])} missing UV map {target_uv_map!r}")
            else:
                nodes_to_relink = [node for node in image_nodes if _image_node_uv_map_name(node) != target_uv_map]
                if nodes_to_relink:
                    ensure_transaction()
                    _record_shader_material(material)
                    uv_node = material.node_tree.nodes.new(type="ShaderNodeUVMap")
                    uv_node.name = f"Agent Bridge Repair UV Map {target_uv_map}"
                    uv_node.label = uv_node.name
                    uv_node.uv_map = target_uv_map
                    uv_node.location = (-900, 480)
                    uv_output = uv_node.outputs.get("UV")
                    for node in nodes_to_relink:
                        vector_input = node.inputs.get("Vector")
                        if vector_input is None or uv_output is None:
                            continue
                        _remove_links_to_socket(material.node_tree, vector_input)
                        material.node_tree.links.new(uv_output, vector_input)
                    material_repairs.append(
                        {
                            "type": "uv_relink",
                            "uv_map": target_uv_map,
                            "image_nodes": [node.name for node in nodes_to_relink],
                        }
                    )

        if material_repairs:
            repaired.append({"material": material.name, "repairs": material_repairs})

    if transaction is None:
        return {
            "ok": True,
            "message": "No material setup repairs were needed",
            "materials": repaired,
            "warnings": warnings,
            "missing_material_names": missing_materials,
            "missing_object_names": missing_objects,
        }

    transaction["applied_steps"].append(
        {
            "type": "repair_material_setup",
            "label": label,
            "materials": repaired,
            "uv_map_name": target_uv_map,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    post_inspection = inspect_material_setup(
        context,
        material_names=[item["material"] for item in repaired],
        object_names=[obj.name for obj in objects],
        selected_only=False,
        require_uv_maps=bool(target_uv_map),
        expected_uv_map_name=target_uv_map,
        max_materials=max_materials,
    )
    return {
        "ok": True,
        "message": f"Repaired material setup for {len(repaired)} material(s)",
        "materials": repaired,
        "warnings": warnings,
        "post_inspection": post_inspection,
        "missing_material_names": missing_materials,
        "missing_object_names": missing_objects,
        "transaction_id": transaction["id"],
    }

def _normalize_bake_map_type(map_type):
    key = str(map_type or "").strip().lower().replace("_", " ")
    return BAKE_MAP_ALIASES.get(key.replace(" ", "_")) or BAKE_MAP_ALIASES.get(key.replace(" ", "-")) or BAKE_MAP_ALIASES.get(key, "")

def _normalize_bake_map_types(map_types):
    requested = map_types or ["ambient_occlusion", "normal", "base_color"]
    normalized = []
    unsupported = []
    for item in requested:
        map_type = _normalize_bake_map_type(item)
        if map_type:
            if map_type not in normalized:
                normalized.append(map_type)
        else:
            unsupported.append(str(item))
    return normalized, unsupported

def _safe_bake_name(value, fallback="bake"):
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip()).strip("._")
    return text[:96] or fallback

def _resolve_bake_output_dir(context, output_dir):
    raw = str(output_dir or "").strip()
    if raw:
        resolved = bpy.path.abspath(raw) if raw.startswith("//") else os.path.expanduser(raw)
        resolved = os.path.abspath(resolved)
    else:
        capture_info = viewport_capture.resolve_capture_dir(context, create=True)
        run_id = time.strftime("%Y%m%d-%H%M%S")
        resolved = os.path.join(capture_info["capture_dir"], "bake-maps", run_id)
    os.makedirs(resolved, exist_ok=True)
    return resolved

def _unique_bake_path(output_dir, filename, *, overwrite=False):
    path = os.path.join(output_dir, filename)
    if overwrite or not os.path.exists(path):
        return path
    stem, extension = os.path.splitext(filename)
    for index in range(2, 1000):
        candidate = os.path.join(output_dir, f"{stem}-{index}{extension}")
        if not os.path.exists(candidate):
            return candidate
    return path

def _resolve_uv_layer_for_bake(obj, uv_map_name):
    mesh = obj.data if obj and obj.type == "MESH" else None
    if mesh is None:
        return None, "Object is not a mesh"
    uv_layers = getattr(mesh, "uv_layers", None)
    if not uv_layers or not len(uv_layers):
        return None, "Mesh has no UV map; run uv_unwrap first"
    requested = str(uv_map_name or "").strip()
    uv_layer = uv_layers.get(requested) if requested else uv_layers.active
    if uv_layer is None and not requested:
        uv_layer = uv_layers[0]
    if uv_layer is None:
        return None, f"UV map not found: {requested}"
    return uv_layer, ""

def _active_uv_layer_for_bake(obj, uv_map_name):
    uv_layer, error = _resolve_uv_layer_for_bake(obj, uv_map_name)
    if error:
        return None, error
    mesh = obj.data if obj and obj.type == "MESH" else None
    if mesh is not None:
        mesh.uv_layers.active = uv_layer
    return uv_layer, ""

def _bake_materials_for_object(obj):
    materials = []
    for slot in list(getattr(obj, "material_slots", []) or []):
        material = getattr(slot, "material", None)
        if material and material.node_tree:
            materials.append(material)
    return materials

def _preflight_bake_objects(objects, uv_map_name):
    issues = []
    for obj in objects:
        _, uv_error = _resolve_uv_layer_for_bake(obj, uv_map_name)
        if uv_error:
            issues.append({"object": obj.name, "message": uv_error})
        if not _bake_materials_for_object(obj):
            issues.append({"object": obj.name, "message": "Object has no node-based material to bake"})
    return issues

def _add_bake_target_nodes(materials, image):
    created = []
    previous_active = []
    for material in materials:
        nodes = material.node_tree.nodes
        previous_active.append((material, getattr(nodes, "active", None)))
        node = nodes.new(type="ShaderNodeTexImage")
        node.name = "Agent Bridge Bake Target"
        node.label = "Agent Bridge Bake Target"
        node.image = image
        node.location = (-780, -520)
        nodes.active = node
        created.append((material, node))
    return created, previous_active

def _remove_bake_target_nodes(created_nodes, previous_active_nodes):
    for material, node in reversed(created_nodes):
        if material and material.node_tree and node and node.name in material.node_tree.nodes:
            material.node_tree.nodes.remove(node)
    for material, active_node in previous_active_nodes:
        if not material or not material.node_tree or active_node is None:
            continue
        if active_node.name in material.node_tree.nodes:
            material.node_tree.nodes.active = active_node

def _bake_artifact_report(path, *, object_name, map_type, image, width, height):
    exists = bool(path and os.path.isfile(path))
    size_bytes = os.path.getsize(path) if exists else 0
    return {
        "object": object_name,
        "map_type": map_type,
        "image": image.name if image else "",
        "path": path,
        "available": bool(exists and size_bytes > 0),
        "size_bytes": int(size_bytes),
        "width": int(width),
        "height": int(height),
    }

def bake_maps(
    context,
    *,
    object_names=None,
    selected_only=True,
    map_types=None,
    output_dir="",
    resolution=512,
    margin=16,
    samples=32,
    uv_map_name="",
    overwrite=False,
    label="Bake maps",
):
    """Bake bounded material maps to PNG artifacts."""

    requested_map_types, unsupported = _normalize_bake_map_types(map_types)
    if unsupported:
        return {
            "ok": False,
            "message": f"Unsupported bake map type(s): {', '.join(unsupported)}",
            "supported_map_types": sorted(BAKE_MAP_SPECS),
        }
    if not requested_map_types:
        return {"ok": False, "message": "At least one bake map type is required", "supported_map_types": sorted(BAKE_MAP_SPECS)}

    resolution = max(16, min(4096, int(resolution or 512)))
    margin = max(0, min(128, int(margin or 0)))
    samples = max(1, min(4096, int(samples or 1)))
    objects, missing = _resolve_edit_objects(
        context,
        object_names=object_names,
        selected_only=selected_only,
        include_active=True,
        max_objects=16,
    )
    objects = [obj for obj in objects if obj and obj.type == "MESH"]
    if not objects:
        return {
            "ok": False,
            "message": "bake_maps needs at least one mesh object",
            "missing_object_names": missing,
        }
    preflight_issues = _preflight_bake_objects(objects, uv_map_name)
    if missing or preflight_issues:
        return {
            "ok": False,
            "message": "bake_maps preflight failed",
            "objects": [obj.name for obj in objects],
            "missing_object_names": missing,
            "map_types": requested_map_types,
            "resolution": resolution,
            "margin": margin,
            "samples": samples,
            "uv_map_name": str(uv_map_name or ""),
            "baked_maps": [],
            "baked_map_count": 0,
            "issues": preflight_issues,
            "issue_count": len(preflight_issues) + len(missing),
        }

    try:
        resolved_output_dir = _resolve_bake_output_dir(context, output_dir)
    except OSError as exc:
        return {"ok": False, "message": f"Could not create bake output directory: {type(exc).__name__}: {exc}"}

    scene = context.scene
    transaction = live_preview.begin(label, context)
    _record_scene_render(scene)

    previous_frame = int(scene.frame_current)
    previous_engine = str(scene.render.engine)
    previous_samples = getattr(getattr(scene, "cycles", None), "samples", None)
    issues = []
    warnings = []
    baked_maps = []
    previous_uv_layers = {}
    previous_mode = getattr(context.object, "mode", "OBJECT") if getattr(context, "object", None) else "OBJECT"

    try:
        if previous_mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception as exc:
                warnings.append(f"Could not leave {previous_mode} mode before baking: {type(exc).__name__}: {exc}")
        try:
            scene.render.engine = "CYCLES"
        except Exception as exc:
            return {"ok": False, "message": f"Cycles render engine is required for baking: {type(exc).__name__}: {exc}"}
        cycles = getattr(scene, "cycles", None)
        if cycles is not None and hasattr(cycles, "samples"):
            cycles.samples = samples

        with _preserve_selection(context):
            for obj in objects:
                mesh = obj.data
                previous_uv_layers[obj.name] = getattr(mesh.uv_layers, "active", None)
                uv_layer, uv_error = _active_uv_layer_for_bake(obj, uv_map_name)
                if uv_error:
                    issues.append({"object": obj.name, "message": uv_error})
                    continue
                materials = _bake_materials_for_object(obj)
                if not materials:
                    issues.append({"object": obj.name, "message": "Object has no node-based material to bake"})
                    continue

                for material in materials:
                    _record_shader_material(material)

                bpy.ops.object.select_all(action="DESELECT")
                obj.select_set(True)
                context.view_layer.objects.active = obj

                for map_type in requested_map_types:
                    spec = BAKE_MAP_SPECS[map_type]
                    filename = f"{_safe_bake_name(obj.name)}_{spec['suffix']}_{resolution}.png"
                    path = _unique_bake_path(resolved_output_dir, filename, overwrite=overwrite)
                    image_name = f"Agent Bridge Bake {obj.name} {map_type}"
                    image = bpy.data.images.new(image_name, width=resolution, height=resolution, alpha=True, float_buffer=False)
                    try:
                        image.colorspace_settings.name = spec["colorspace"]
                    except Exception:
                        pass
                    created_nodes, previous_active_nodes = _add_bake_target_nodes(materials, image)
                    try:
                        bake_kwargs = {
                            "type": spec["bake_type"],
                            "margin": margin,
                            "use_clear": True,
                            "save_mode": "INTERNAL",
                        }
                        if spec.get("pass_filter"):
                            bake_kwargs["pass_filter"] = spec["pass_filter"]
                        bpy.ops.object.bake(**bake_kwargs)
                        image.filepath_raw = path
                        image.file_format = "PNG"
                        image.save()
                        report = _bake_artifact_report(
                            path,
                            object_name=obj.name,
                            map_type=map_type,
                            image=image,
                            width=resolution,
                            height=resolution,
                        )
                        if not report["available"]:
                            issues.append({"object": obj.name, "map_type": map_type, "message": f"Bake output is missing or empty: {path}"})
                        baked_maps.append(report)
                    except Exception as exc:
                        issues.append({"object": obj.name, "map_type": map_type, "message": f"{type(exc).__name__}: {exc}"})
                    finally:
                        _remove_bake_target_nodes(created_nodes, previous_active_nodes)
                        if image and image.name in bpy.data.images:
                            bpy.data.images.remove(image)
    finally:
        for object_name, uv_layer in previous_uv_layers.items():
            obj = bpy.data.objects.get(object_name)
            if obj and obj.type == "MESH" and uv_layer and uv_layer.name in obj.data.uv_layers:
                obj.data.uv_layers.active = obj.data.uv_layers[uv_layer.name]
        scene.frame_set(previous_frame)
        if previous_engine and scene.render.engine != previous_engine:
            try:
                scene.render.engine = previous_engine
            except Exception:
                pass
        cycles = getattr(scene, "cycles", None)
        if cycles is not None and previous_samples is not None and hasattr(cycles, "samples"):
            cycles.samples = previous_samples

    transaction["applied_steps"].append(
        {
            "type": "bake_maps",
            "label": label,
            "objects": [obj.name for obj in objects],
            "map_types": requested_map_types,
            "output_dir": resolved_output_dir,
            "baked_map_count": len([item for item in baked_maps if item.get("available")]),
            "resolution": resolution,
            "uv_map_name": str(uv_map_name or ""),
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    ok = bool(baked_maps) and all(item.get("available") for item in baked_maps) and not issues and not missing
    return {
        "ok": ok,
        "message": "Baked maps" if ok else "Baked maps with issues",
        "objects": [obj.name for obj in objects],
        "missing_object_names": missing,
        "map_types": requested_map_types,
        "output_dir": resolved_output_dir,
        "resolution": resolution,
        "margin": margin,
        "samples": samples,
        "uv_map_name": str(uv_map_name or ""),
        "baked_maps": baked_maps,
        "baked_map_count": len([item for item in baked_maps if item.get("available")]),
        "issues": issues,
        "issue_count": len(issues) + len(missing),
        "warnings": warnings,
        "transaction_id": transaction["id"],
    }

def _normalize_procedural_texture_type(texture_type):
    key = str(texture_type or "noise").strip().lower().replace("-", "_").replace(" ", "_")
    if key in {"musgrave", "fractal", "fractal_noise", "clouds"}:
        key = "noise"
    if key in {"cellular", "cells"}:
        key = "voronoi"
    if key in {"wood", "rings"}:
        key = "wave"
    return key if key in PROCEDURAL_TEXTURE_TYPES else ""

def _normalize_procedural_texture_preset(preset):
    key = str(preset or "custom").strip().lower().replace("-", "_").replace(" ", "_")
    return key if key in PROCEDURAL_TEXTURE_PRESETS else "custom"

def _rgba_tuple(value, fallback):
    source = value if value is not None else fallback
    return (
        float(source[0]),
        float(source[1]),
        float(source[2]),
        float(source[3]) if len(source) > 3 else 1.0,
    )

def _set_procedural_texture_inputs(texture_node, *, texture_type, scale, detail, texture_roughness, distortion, randomness, wave_type):
    _set_socket_value(texture_node.inputs.get("Scale"), max(0.01, min(500.0, float(scale))))
    if texture_node.inputs.get("Detail"):
        _set_socket_value(texture_node.inputs.get("Detail"), max(0.0, min(16.0, float(detail))))
    for socket_name in ("Roughness", "Detail Roughness"):
        if texture_node.inputs.get(socket_name):
            _set_socket_value(texture_node.inputs.get(socket_name), max(0.0, min(1.0, float(texture_roughness))))
    if texture_node.inputs.get("Distortion"):
        _set_socket_value(texture_node.inputs.get("Distortion"), max(0.0, min(100.0, float(distortion))))
    if texture_node.inputs.get("Randomness"):
        _set_socket_value(texture_node.inputs.get("Randomness"), max(0.0, min(1.0, float(randomness))))
    if texture_type == "wave" and hasattr(texture_node, "wave_type"):
        wave = str(wave_type or "BANDS").strip().upper()
        if wave in {"BANDS", "RINGS"}:
            texture_node.wave_type = wave

def create_procedural_texture_material(
    context,
    *,
    name,
    preset="custom",
    texture_type="",
    color_a=None,
    color_b=None,
    scale=None,
    detail=None,
    texture_roughness=None,
    distortion=None,
    randomness=None,
    metallic=None,
    material_roughness=None,
    alpha=None,
    bump_strength=None,
    bump_distance=None,
    wave_type="BANDS",
    replace_existing_links=True,
    assign_to_objects=True,
    object_names=None,
    selected_only=True,
    label="Create procedural texture material",
):
    preset_key = _normalize_procedural_texture_preset(preset)
    preset_spec = PROCEDURAL_TEXTURE_PRESETS[preset_key]
    texture_key = _normalize_procedural_texture_type(texture_type or preset_spec.get("texture_type") or "noise")
    if not texture_key:
        return {
            "ok": False,
            "message": f"Unsupported procedural texture type: {texture_type}",
            "supported_texture_types": sorted(PROCEDURAL_TEXTURE_TYPES),
        }

    color_a = _rgba_tuple(color_a, preset_spec.get("color_a", (0.08, 0.08, 0.085, 1.0)))
    color_b = _rgba_tuple(color_b, preset_spec.get("color_b", (0.82, 0.78, 0.68, 1.0)))
    scale = _clamped_float(scale, preset_spec.get("scale", 18.0), 0.01, 500.0)
    detail = _clamped_float(detail, preset_spec.get("detail", 8.0), 0.0, 16.0)
    texture_roughness = _clamped_float(texture_roughness, preset_spec.get("texture_roughness", 0.55), 0.0, 1.0)
    distortion = _clamped_float(distortion, preset_spec.get("distortion", 0.0), 0.0, 100.0)
    randomness = _clamped_float(randomness, preset_spec.get("randomness", 0.5), 0.0, 1.0)
    metallic = _clamped_float(metallic, preset_spec.get("metallic", 0.0), 0.0, 1.0)
    material_roughness = _clamped_float(material_roughness, preset_spec.get("material_roughness", 0.58), 0.0, 1.0)
    alpha = _clamped_float(alpha, preset_spec.get("alpha", 1.0), 0.0, 1.0)
    bump_strength = _clamped_float(bump_strength, preset_spec.get("bump_strength", 0.0), 0.0, 10.0)
    bump_distance = _clamped_float(bump_distance, preset_spec.get("bump_distance", 0.04), 0.0, 10.0)
    wave_type = str(wave_type or preset_spec.get("wave_type", "BANDS")).strip().upper()

    transaction = live_preview.begin(label, context)
    material = bpy.data.materials.get(name)
    created = material is None
    if material is None:
        material = bpy.data.materials.new(name or "Agent Bridge Procedural Texture Material")
        live_preview._record_created_id("material", material.name)
    else:
        _record_shader_material(material)

    material.diffuse_color = color_a
    principled = _ensure_principled_material(material)
    _set_socket_value(principled.inputs.get("Metallic"), metallic)
    _set_socket_value(principled.inputs.get("Roughness"), material_roughness)
    _set_socket_value(principled.inputs.get("Alpha"), alpha)
    if alpha < 1.0:
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "BLENDED"
        elif hasattr(material, "blend_method"):
            material.blend_method = "BLEND"

    nodes = material.node_tree.nodes
    links = material.node_tree.links
    warnings = []
    created_nodes = []
    linked_sockets = set()

    base_socket = principled.inputs.get("Base Color")
    base_blocker = _socket_link_blocker(
        base_socket,
        "procedural_base_color",
        replace_existing_links=replace_existing_links,
        linked_sockets=linked_sockets,
    )
    if base_blocker:
        warnings.append(base_blocker)
    can_link_base_color = not base_blocker and base_socket is not None

    normal_socket = None
    bump_blocker = ""
    can_link_bump = False
    if bump_strength > 0.0:
        normal_socket = _principled_socket(principled, ("Normal",))
        bump_blocker = _socket_link_blocker(
            normal_socket,
            "procedural_bump",
            replace_existing_links=replace_existing_links,
            linked_sockets=linked_sockets,
        )
        if bump_blocker:
            warnings.append(bump_blocker)
        can_link_bump = not bump_blocker and normal_socket is not None

    if not can_link_base_color and not can_link_bump:
        transaction["applied_steps"].append(
            {
                "type": "create_procedural_texture_material",
                "label": label,
                "material": material.name,
                "created": created,
                "preset": preset_key,
                "texture_type": texture_key,
                "assigned_objects": [],
            }
        )
        live_preview.redraw(context)
        live_preview._mark_pending(context, label)
        return {
            "ok": True,
            "message": f"{'Created' if created else 'Updated'} procedural texture material {material.name}",
            "material": material.name,
            "preset": preset_key,
            "texture_type": texture_key,
            "nodes": [],
            "base_color_linked": False,
            "bump_linked": False,
            "assigned_objects": [],
            "missing_object_names": [],
            "warnings": warnings,
            "transaction_id": transaction["id"],
        }

    node_type = {
        "noise": "ShaderNodeTexNoise",
        "voronoi": "ShaderNodeTexVoronoi",
        "wave": "ShaderNodeTexWave",
        "checker": "ShaderNodeTexChecker",
    }[texture_key]
    texture_node = nodes.new(type=node_type)
    texture_node.name = f"Agent Bridge {texture_key.title()} Procedural Texture"
    texture_node.label = texture_node.name
    texture_node.location = (-620, 180)
    created_nodes.append(texture_node.name)
    _set_procedural_texture_inputs(
        texture_node,
        texture_type=texture_key,
        scale=scale,
        detail=detail,
        texture_roughness=texture_roughness,
        distortion=distortion,
        randomness=randomness,
        wave_type=wave_type,
    )

    color_output = None
    factor_output = None
    if texture_key == "checker":
        _set_socket_value(texture_node.inputs.get("Color1"), color_a)
        _set_socket_value(texture_node.inputs.get("Color2"), color_b)
        color_output = texture_node.outputs.get("Color")
        factor_output = texture_node.outputs.get("Factor")
    else:
        factor_output = texture_node.outputs.get("Factor") or texture_node.outputs.get("Distance")
        if texture_key == "voronoi":
            factor_output = texture_node.outputs.get("Distance") or factor_output

    if can_link_base_color and texture_key != "checker":
        ramp_node = nodes.new(type="ShaderNodeValToRGB")
        ramp_node.name = "Agent Bridge Procedural Color Ramp"
        ramp_node.label = ramp_node.name
        ramp_node.location = (-350, 180)
        created_nodes.append(ramp_node.name)
        ramp_node.color_ramp.elements[0].position = 0.18
        ramp_node.color_ramp.elements[0].color = color_a
        ramp_node.color_ramp.elements[1].position = 1.0
        ramp_node.color_ramp.elements[1].color = color_b
        if factor_output and ramp_node.inputs.get("Factor"):
            links.new(factor_output, ramp_node.inputs["Factor"])
        color_output = ramp_node.outputs.get("Color")

    base_color_linked = False
    if can_link_base_color and color_output and base_socket:
        if base_socket.is_linked:
            _remove_links_to_socket(material.node_tree, base_socket)
        links.new(color_output, base_socket)
        linked_sockets.add(base_socket.name)
        base_color_linked = True

    bump_linked = False
    if can_link_bump:
        bump_node = nodes.new(type="ShaderNodeBump")
        bump_node.name = "Agent Bridge Procedural Bump"
        bump_node.label = bump_node.name
        bump_node.location = (-120, -80)
        created_nodes.append(bump_node.name)
        _set_socket_value(bump_node.inputs.get("Strength"), bump_strength)
        _set_socket_value(bump_node.inputs.get("Distance"), bump_distance)
        height_output = factor_output or texture_node.outputs.get("Factor") or texture_node.outputs.get("Distance")
        if height_output and bump_node.inputs.get("Height"):
            links.new(height_output, bump_node.inputs["Height"])
        if normal_socket and normal_socket.is_linked:
            _remove_links_to_socket(material.node_tree, normal_socket)
        if normal_socket and bump_node.outputs.get("Normal"):
            links.new(bump_node.outputs["Normal"], normal_socket)
            linked_sockets.add(normal_socket.name)
            bump_linked = True

    assigned = []
    missing = []
    if assign_to_objects:
        objects, missing = _resolve_edit_objects(context, object_names=object_names, selected_only=selected_only)
        for obj in objects:
            if obj.type != "MESH" or obj.data is None:
                continue
            live_preview._record_object_materials(obj)
            if obj.material_slots:
                obj.material_slots[0].material = material
            else:
                obj.data.materials.append(material)
            assigned.append(obj.name)

    transaction["applied_steps"].append(
        {
            "type": "create_procedural_texture_material",
            "label": label,
            "material": material.name,
            "created": created,
            "preset": preset_key,
            "texture_type": texture_key,
            "assigned_objects": assigned,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"{'Created' if created else 'Updated'} procedural texture material {material.name}",
        "material": material.name,
        "preset": preset_key,
        "texture_type": texture_key,
        "nodes": created_nodes,
        "base_color_linked": base_color_linked,
        "bump_linked": bump_linked,
        "assigned_objects": assigned,
        "missing_object_names": missing,
        "warnings": warnings,
        "transaction_id": transaction["id"],
    }

def _normalize_uv_unwrap_method(method):
    key = str(method or "smart_project").strip().lower().replace("-", "_").replace(" ", "_")
    if key in {"smart", "smart_uv", "smart_uv_project"}:
        key = "smart_project"
    if key in {"cube", "box", "box_project"}:
        key = "cube_project"
    if key in {"planar", "plane"}:
        key = "planar_project"
    return key if key in UV_UNWRAP_METHODS else "smart_project"

def _normalize_uv_projection_axis(axis):
    key = str(axis or "Z").strip().upper()
    return key if key in UV_PROJECTION_AXES else "Z"

def _mesh_axis_bounds(mesh):
    if mesh is None or not mesh.vertices:
        return [(0.0, 1.0), (0.0, 1.0), (0.0, 1.0)]
    bounds = []
    for axis_index in range(3):
        values = [float(vertex.co[axis_index]) for vertex in mesh.vertices]
        low = min(values)
        high = max(values)
        if abs(high - low) <= 0.000001:
            high = low + 1.0
        bounds.append((low, high))
    return bounds

def _project_uv_value(co, axis_index, bounds, margin):
    low, high = bounds[axis_index]
    value = (float(co[axis_index]) - low) / max(0.000001, high - low)
    value = max(0.0, min(1.0, value))
    return margin + value * (1.0 - margin * 2.0)

def _uv_projection_axes(method, normal, projection_axis):
    if method == "planar_project":
        axis_index = {"X": 0, "Y": 1, "Z": 2}.get(projection_axis, 2)
        if axis_index == 0:
            return (1, 2), (0, 1)
        if axis_index == 1:
            return (0, 2), (1, 1)
        return (0, 1), (2, 1)

    normal_values = [abs(float(normal[index])) for index in range(3)]
    dominant = max(range(3), key=lambda index: normal_values[index])
    sign = 1 if float(normal[dominant]) >= 0.0 else -1
    if dominant == 0:
        return (1, 2), (0, sign)
    if dominant == 1:
        return (0, 2), (1, sign)
    return (0, 1), (2, sign)

def _uv_atlas_cell(axis_key):
    cells = {
        (2, 1): (0, 0),
        (2, -1): (1, 0),
        (0, 1): (2, 0),
        (0, -1): (0, 1),
        (1, 1): (1, 1),
        (1, -1): (2, 1),
    }
    return cells.get(axis_key, (0, 0))

def _write_uv_projection(mesh, uv_layer, *, method, projection_axis, margin, pack_islands):
    bounds = _mesh_axis_bounds(mesh)
    loop_count = 0
    polygons = 0
    margin = max(0.0, min(0.25, float(margin)))
    for polygon in mesh.polygons:
        axes, axis_key = _uv_projection_axes(method, polygon.normal, projection_axis)
        cell_x, cell_y = _uv_atlas_cell(axis_key)
        use_atlas = bool(pack_islands and method in {"smart_project", "cube_project"})
        for loop_index in polygon.loop_indices:
            vertex = mesh.vertices[mesh.loops[loop_index].vertex_index]
            u = _project_uv_value(vertex.co, axes[0], bounds, margin)
            v = _project_uv_value(vertex.co, axes[1], bounds, margin)
            if use_atlas:
                cell_width = 1.0 / 3.0
                cell_height = 1.0 / 2.0
                u = cell_x * cell_width + u * cell_width
                v = cell_y * cell_height + v * cell_height
            uv_layer.data[loop_index].uv = (u, v)
            loop_count += 1
        polygons += 1
    return {"polygons": polygons, "loops": loop_count}

def _normalize_uv_seam_mode(mode):
    key = str(mode or "sharp_angle").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "sharp": "sharp_angle",
        "angle": "sharp_angle",
        "hard_edges": "sharp_angle",
        "boundaries": "boundary",
        "boundary_edges": "boundary",
        "both": "sharp_and_boundary",
        "all": "sharp_and_boundary",
        "clear_existing": "clear",
        "remove": "clear",
    }
    key = aliases.get(key, key)
    return key if key in UV_SEAM_MODES else "sharp_angle"

def _mesh_edge_face_map(mesh):
    face_map = {}
    if mesh is None:
        return face_map
    for polygon in mesh.polygons:
        for edge_key in polygon.edge_keys:
            key = tuple(sorted(edge_key))
            face_map.setdefault(key, []).append(polygon.index)
    return face_map

def _edge_face_angle_degrees(mesh, polygon_indices):
    if mesh is None or len(polygon_indices or []) < 2:
        return 0.0
    max_angle = 0.0
    indices = list(polygon_indices)
    for left_index, left_poly_index in enumerate(indices[:-1]):
        left_normal = Vector(mesh.polygons[left_poly_index].normal)
        if left_normal.length <= 1e-9:
            continue
        left_normal.normalize()
        for right_poly_index in indices[left_index + 1 :]:
            right_normal = Vector(mesh.polygons[right_poly_index].normal)
            if right_normal.length <= 1e-9:
                continue
            right_normal.normalize()
            dot = max(-1.0, min(1.0, float(left_normal.dot(right_normal))))
            max_angle = max(max_angle, math.degrees(math.acos(dot)))
    return max_angle

def _uv_layer_for_mesh(mesh, uv_map_name=""):
    if mesh is None or not mesh.uv_layers:
        return None
    name = str(uv_map_name or "").strip()
    if name:
        return mesh.uv_layers.get(name)
    return mesh.uv_layers.active or mesh.uv_layers[0]

def _uv_polygon_area(coords):
    if len(coords) < 3:
        return 0.0
    area = 0.0
    ax, ay = coords[0]
    for index in range(1, len(coords) - 1):
        bx, by = coords[index]
        cx, cy = coords[index + 1]
        area += abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) * 0.5
    return area

def _world_polygon_area(obj, polygon):
    if obj is None or obj.type != "MESH" or obj.data is None or len(polygon.vertices) < 3:
        return 0.0
    vertices = [obj.matrix_world @ obj.data.vertices[index].co for index in polygon.vertices]
    area = 0.0
    origin = vertices[0]
    for index in range(1, len(vertices) - 1):
        area += ((vertices[index] - origin).cross(vertices[index + 1] - origin)).length * 0.5
    return area

def _uv_bbox(coords):
    if not coords:
        return None
    u_values = [item[0] for item in coords]
    v_values = [item[1] for item in coords]
    return (min(u_values), min(v_values), max(u_values), max(v_values))

def _uv_bbox_positive_overlap(left, right, epsilon=1e-6):
    if left is None or right is None:
        return False
    width = min(left[2], right[2]) - max(left[0], right[0])
    height = min(left[3], right[3]) - max(left[1], right[1])
    return width > epsilon and height > epsilon

def _uv_layout_quality(obj, *, uv_map_name="", max_overlap_pairs=200):
    mesh = obj.data if obj and obj.type == "MESH" else None
    issues = []
    warnings = []
    seam_count = sum(1 for edge in mesh.edges if edge.use_seam) if mesh else 0
    result = {
        "object": obj.name if obj else "",
        "mesh": mesh.name if mesh else "",
        "uv_map": "",
        "has_uvs": False,
        "active_uv_map": "",
        "face_count": len(mesh.polygons) if mesh else 0,
        "loop_count": len(mesh.loops) if mesh else 0,
        "seam_count": seam_count,
        "edge_count": len(mesh.edges) if mesh else 0,
        "out_of_bounds_loops": 0,
        "possible_overlap_pairs": 0,
        "overlap_pair_checks": 0,
        "overlap_samples": [],
        "uv_bounds": None,
        "uv_bounds_area": 0.0,
        "uv_area_sum": 0.0,
        "world_surface_area": 0.0,
        "uv_area_to_surface_area": 0.0,
        "issues": issues,
        "warnings": warnings,
        "passed": True,
    }
    if mesh is None:
        issues.append("not a mesh")
        result["passed"] = False
        return result

    active_layer = mesh.uv_layers.active
    result["active_uv_map"] = active_layer.name if active_layer else ""
    uv_layer = _uv_layer_for_mesh(mesh, uv_map_name)
    requested_name = str(uv_map_name or "").strip()
    if uv_layer is None:
        issues.append(f"UV map not found: {requested_name}" if requested_name else "no UV map")
        result["passed"] = False
        return result

    result["uv_map"] = uv_layer.name
    result["has_uvs"] = True
    all_coords = []
    face_bboxes = []
    uv_area = 0.0
    surface_area = 0.0
    out_of_bounds = 0
    for polygon in mesh.polygons:
        coords = []
        for loop_index in polygon.loop_indices:
            if loop_index >= len(uv_layer.data):
                continue
            uv = uv_layer.data[loop_index].uv
            coord = (float(uv.x), float(uv.y))
            coords.append(coord)
            all_coords.append(coord)
            if coord[0] < -1e-6 or coord[0] > 1.0 + 1e-6 or coord[1] < -1e-6 or coord[1] > 1.0 + 1e-6:
                out_of_bounds += 1
        face_area = _uv_polygon_area(coords)
        if face_area > 1e-12:
            bbox = _uv_bbox(coords)
            if bbox is not None:
                face_bboxes.append((polygon.index, bbox))
        uv_area += face_area
        surface_area += _world_polygon_area(obj, polygon)

    if not all_coords:
        issues.append("UV map has no loop coordinates")
    else:
        bounds = _uv_bbox(all_coords)
        bounds_area = max(0.0, (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])) if bounds else 0.0
        result["uv_bounds"] = [round(value, 6) for value in bounds]
        result["uv_bounds_area"] = round(bounds_area, 6)
    result["out_of_bounds_loops"] = out_of_bounds
    if out_of_bounds:
        warnings.append(f"{out_of_bounds} UV loop coordinate(s) outside 0..1")
    result["uv_area_sum"] = round(uv_area, 6)
    result["world_surface_area"] = round(surface_area, 6)
    result["uv_area_to_surface_area"] = round(uv_area / surface_area, 6) if surface_area > 1e-12 else 0.0
    if uv_area <= 1e-9 and mesh.polygons:
        issues.append("UV layout has near-zero area")

    max_reported_overlaps = max(0, min(1000, int(max_overlap_pairs or 0)))
    max_faces = min(len(face_bboxes), 300)
    overlap_count = 0
    checks = 0
    if max_reported_overlaps > 0:
        for left_index in range(max_faces):
            left_face, left_bbox = face_bboxes[left_index]
            for right_index in range(left_index + 1, max_faces):
                right_face, right_bbox = face_bboxes[right_index]
                checks += 1
                if _uv_bbox_positive_overlap(left_bbox, right_bbox):
                    overlap_count += 1
                    if len(result["overlap_samples"]) < 12:
                        result["overlap_samples"].append([left_face, right_face])
                    if overlap_count >= max_reported_overlaps:
                        break
            if overlap_count >= max_reported_overlaps:
                break
    result["possible_overlap_pairs"] = overlap_count
    result["overlap_pair_checks"] = checks
    if overlap_count:
        issues.append(f"{overlap_count} possible overlapping UV face-bound pair(s)")

    scale = tuple(float(component) for component in getattr(obj, "scale", (1.0, 1.0, 1.0)))
    if any(abs(abs(component) - 1.0) > 0.001 for component in scale):
        warnings.append("object has unapplied scale")
    if seam_count == 0 and len(mesh.edges) > 0 and len(mesh.polygons) > 6:
        warnings.append("mesh has no marked UV seams")

    result["passed"] = not issues
    return result

def mark_uv_seams(
    context,
    *,
    object_names=None,
    selected_only=True,
    mode="sharp_angle",
    angle_degrees=60.0,
    include_boundary=True,
    clear_existing=False,
    label="Mark UV seams",
):
    mode = _normalize_uv_seam_mode(mode)
    angle = _clamped_float(angle_degrees, 60.0, 0.0, 180.0)
    objects, missing = _resolve_edit_objects(context, object_names=object_names, selected_only=selected_only)
    meshes = [obj for obj in objects if obj.type == "MESH"]
    if not meshes:
        return {"ok": False, "message": "No mesh objects found for mark_uv_seams", "missing_object_names": missing}

    transaction = live_preview.begin(label, context)
    changed = []
    skipped = []
    for obj in meshes:
        blockers = _mesh_edit_blockers(obj, allow_shape_keys=True)
        if blockers:
            skipped.append({"object": obj.name, "reasons": blockers})
            continue
        mesh = obj.data
        live_preview._record_mesh_data_snapshot(obj)
        mesh.update(calc_edges=True)
        seams_before = sum(1 for edge in mesh.edges if edge.use_seam)
        cleared = 0
        marked = 0
        boundary_edges = 0
        sharp_angle_edges = 0
        if mode == "clear" or clear_existing:
            for edge in mesh.edges:
                if edge.use_seam:
                    edge.use_seam = False
                    cleared += 1
        if mode != "clear":
            face_map = _mesh_edge_face_map(mesh)
            for edge in mesh.edges:
                edge_key = tuple(sorted(int(index) for index in edge.vertices))
                polygon_indices = face_map.get(edge_key, [])
                is_boundary = len(polygon_indices) < 2
                if is_boundary:
                    boundary_edges += 1
                edge_angle = _edge_face_angle_degrees(mesh, polygon_indices)
                is_sharp = edge_angle >= angle
                if is_sharp:
                    sharp_angle_edges += 1
                should_mark = False
                if mode == "boundary":
                    should_mark = is_boundary
                elif mode == "sharp_and_boundary":
                    should_mark = is_sharp or is_boundary
                else:
                    should_mark = is_sharp or (bool(include_boundary) and is_boundary)
                if should_mark and not edge.use_seam:
                    edge.use_seam = True
                    marked += 1
        mesh.update()
        seams_after = sum(1 for edge in mesh.edges if edge.use_seam)
        changed.append(
            {
                "object": obj.name,
                "mesh": mesh.name,
                "mode": mode,
                "angle_degrees": round(angle, 4),
                "include_boundary": bool(include_boundary),
                "cleared_existing": cleared,
                "marked_edges": marked,
                "boundary_edges": boundary_edges,
                "sharp_angle_edges": sharp_angle_edges,
                "seams_before": seams_before,
                "seams_after": seams_after,
            }
        )

    if not changed:
        return {
            "ok": False,
            "message": "No mesh UV seams were changed",
            "objects": changed,
            "skipped": skipped,
            "missing_object_names": missing,
            "transaction_id": transaction["id"],
        }
    transaction["applied_steps"].append(
        {
            "type": "mark_uv_seams",
            "label": label,
            "objects": changed,
            "mode": mode,
            "angle_degrees": round(angle, 4),
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Updated UV seams on {len(changed)} mesh object(s)",
        "objects": changed,
        "skipped": skipped,
        "mode": mode,
        "angle_degrees": round(angle, 4),
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }

def inspect_uv_layout(
    context,
    *,
    object_names=None,
    selected_only=True,
    include_children=True,
    uv_map_name="",
    max_objects=64,
    max_overlap_pairs=200,
):
    roots, missing = _resolve_edit_objects(context, object_names=object_names, selected_only=selected_only, max_objects=max_objects)
    seen = set()
    objects = []
    for root in roots:
        candidates = [root]
        if include_children:
            candidates.extend(list(getattr(root, "children_recursive", []) or []))
        for obj in candidates:
            if obj.name in seen:
                continue
            seen.add(obj.name)
            objects.append(obj)
            if len(objects) >= max(1, int(max_objects or 1)):
                break
    mesh_objects = [obj for obj in objects if obj.type == "MESH"]
    if not mesh_objects:
        return {
            "ok": False,
            "passed": False,
            "message": "No mesh objects found for UV layout inspection",
            "objects": [],
            "missing_object_names": missing,
        }
    results = [
        _uv_layout_quality(
            obj,
            uv_map_name=uv_map_name,
            max_overlap_pairs=max_overlap_pairs,
        )
        for obj in mesh_objects
    ]
    issue_count = sum(len(item["issues"]) for item in results)
    warning_count = sum(len(item["warnings"]) for item in results)
    return {
        "ok": True,
        "passed": issue_count == 0,
        "message": "UV layout inspection passed" if issue_count == 0 else "UV layout inspection found issues",
        "objects": results,
        "object_count": len(results),
        "issue_count": issue_count,
        "warning_count": warning_count,
        "missing_object_names": missing,
        "policy": {
            "include_children": bool(include_children),
            "uv_map_name": str(uv_map_name or ""),
            "max_overlap_pairs": max(0, min(1000, int(max_overlap_pairs or 0))),
        },
    }

def uv_unwrap(
    context,
    *,
    object_names=None,
    selected_only=True,
    method="smart_project",
    uv_map_name="Agent Bridge UVs",
    replace_existing=False,
    margin=0.02,
    pack_islands=True,
    projection_axis="Z",
    label="UV unwrap",
):
    method = _normalize_uv_unwrap_method(method)
    projection_axis = _normalize_uv_projection_axis(projection_axis)
    objects, missing = _resolve_edit_objects(context, object_names=object_names, selected_only=selected_only)
    meshes = [obj for obj in objects if obj.type == "MESH"]
    if not meshes:
        return {"ok": False, "message": "No mesh objects found for uv_unwrap", "missing_object_names": missing}

    transaction = live_preview.begin(label, context)
    changed = []
    skipped = []
    for obj in meshes:
        blockers = _mesh_edit_blockers(obj, allow_shape_keys=True)
        if blockers:
            skipped.append({"object": obj.name, "reasons": blockers})
            continue
        mesh = obj.data
        live_preview._record_mesh_data_snapshot(obj)
        layer_name = str(uv_map_name or "Agent Bridge UVs").strip() or "Agent Bridge UVs"
        existing = mesh.uv_layers.get(layer_name)
        replaced = False
        if existing is not None and replace_existing:
            mesh.uv_layers.remove(existing)
            existing = None
            replaced = True
        uv_layer = existing or mesh.uv_layers.new(name=layer_name, do_init=False)
        mesh.uv_layers.active = uv_layer
        counts = _write_uv_projection(
            mesh,
            uv_layer,
            method=method,
            projection_axis=projection_axis,
            margin=margin,
            pack_islands=pack_islands,
        )
        mesh.update()
        layout = _uv_layout_quality(obj, uv_map_name=uv_layer.name, max_overlap_pairs=80)
        changed.append(
            {
                "object": obj.name,
                "mesh": mesh.name,
                "uv_map": uv_layer.name,
                "method": method,
                "projection_axis": projection_axis,
                "replaced_existing": replaced,
                "seam_count": layout.get("seam_count", 0),
                "uv_bounds": layout.get("uv_bounds"),
                "uv_bounds_area": layout.get("uv_bounds_area", 0.0),
                "uv_area_sum": layout.get("uv_area_sum", 0.0),
                "possible_overlap_pairs": layout.get("possible_overlap_pairs", 0),
                "layout_issues": layout.get("issues", []),
                "layout_warnings": layout.get("warnings", []),
                **counts,
            }
        )

    if not changed:
        return {
            "ok": False,
            "message": "No mesh UVs were changed",
            "objects": changed,
            "skipped": skipped,
            "missing_object_names": missing,
            "transaction_id": transaction["id"],
        }
    transaction["applied_steps"].append(
        {
            "type": "uv_unwrap",
            "label": label,
            "objects": changed,
            "method": method,
            "uv_map_name": str(uv_map_name or "Agent Bridge UVs"),
            "pack_islands": bool(pack_islands),
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Created or updated UV maps on {len(changed)} mesh object(s)",
        "objects": changed,
        "skipped": skipped,
        "method": method,
        "uv_map_name": str(uv_map_name or "Agent Bridge UVs"),
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }

def _new_geometry_node(group, node_type, name, location, warnings):
    try:
        node = group.nodes.new(node_type)
    except Exception as exc:
        warnings.append(f"Could not create {node_type}: {type(exc).__name__}: {exc}")
        return None
    node.name = name
    node.label = name
    node.location = location
    return node

def _link_node_sockets(group, from_socket, to_socket, warnings):
    if from_socket is None or to_socket is None:
        warnings.append("Skipped a Geometry Nodes template link because a required socket was missing")
        return False
    try:
        group.links.new(from_socket, to_socket)
        return True
    except Exception as exc:
        warnings.append(f"Could not link Geometry Nodes sockets: {type(exc).__name__}: {exc}")
        return False

def _build_geometry_node_template(group, template):
    template_key = str(template or "passthrough").strip().lower().replace("-", "_").replace(" ", "_")
    if template_key not in GEOMETRY_NODE_TEMPLATES:
        template_key = "passthrough"
    warnings = []
    group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    group_input = group.nodes.new("NodeGroupInput")
    group_output = group.nodes.new("NodeGroupOutput")
    group_input.location = (-420, 0)
    group_output.location = (260, 0)
    source = group_input.outputs.get("Geometry")
    target = group_output.inputs.get("Geometry")
    if template_key == "transform":
        transform = _new_geometry_node(group, "GeometryNodeTransform", "Agent Bridge Transform Geometry", (-80, 0), warnings)
        if transform is not None:
            _link_node_sockets(group, source, transform.inputs.get("Geometry"), warnings)
            _link_node_sockets(group, transform.outputs.get("Geometry"), target, warnings)
        else:
            _link_node_sockets(group, source, target, warnings)
    elif template_key == "set_position":
        set_position = _new_geometry_node(group, "GeometryNodeSetPosition", "Agent Bridge Set Position", (-80, 0), warnings)
        if set_position is not None:
            _link_node_sockets(group, source, set_position.inputs.get("Geometry"), warnings)
            _link_node_sockets(group, set_position.outputs.get("Geometry"), target, warnings)
        else:
            _link_node_sockets(group, source, target, warnings)
    elif template_key == "subdivide_mesh":
        subdivide = _new_geometry_node(group, "GeometryNodeSubdivideMesh", "Agent Bridge Subdivide Mesh", (-80, 0), warnings)
        if subdivide is not None:
            if subdivide.inputs.get("Level") is not None:
                _set_socket_value(subdivide.inputs.get("Level"), 1)
            _link_node_sockets(group, source, subdivide.inputs.get("Mesh"), warnings)
            _link_node_sockets(group, subdivide.outputs.get("Mesh"), target, warnings)
        else:
            _link_node_sockets(group, source, target, warnings)
    elif template_key == "join_geometry":
        join = _new_geometry_node(group, "GeometryNodeJoinGeometry", "Agent Bridge Join Geometry", (-80, 0), warnings)
        if join is not None:
            geometry_input = join.inputs.get("Geometry")
            _link_node_sockets(group, source, geometry_input, warnings)
            _link_node_sockets(group, join.outputs.get("Geometry"), target, warnings)
        else:
            _link_node_sockets(group, source, target, warnings)
    else:
        _link_node_sockets(group, source, target, warnings)
    return template_key, warnings

def add_geometry_nodes_modifier(
    context,
    *,
    name,
    node_group_name,
    template="passthrough",
    selected_only=True,
    label="Add Geometry Nodes modifier",
):
    targets = [obj for obj in (context.selected_objects if selected_only else context.scene.objects) if obj.type == "MESH"]
    if not targets:
        return {"ok": False, "message": "No mesh objects available for Geometry Nodes modifier"}
    transaction = live_preview.begin(label, context)
    group = bpy.data.node_groups.get(node_group_name)
    created_group = group is None
    if group is None:
        group = bpy.data.node_groups.new(node_group_name or "Agent Bridge Geometry Nodes", "GeometryNodeTree")
        live_preview._record_created_id("node_group", group.name)
        template_key, warnings = _build_geometry_node_template(group, template)
    else:
        template_key = str(template or "passthrough").strip().lower().replace("-", "_").replace(" ", "_")
        if template_key not in GEOMETRY_NODE_TEMPLATES:
            template_key = "passthrough"
        warnings = ["Existing node group reused without editing its node tree, so preview rollback stays reversible."]
    changed = []
    for obj in targets:
        modifier = obj.modifiers.new(name or "Agent Bridge Geometry Nodes", "NODES")
        modifier.node_group = group
        live_preview._record_created_modifier(obj, modifier)
        changed.append(obj.name)
    transaction["applied_steps"].append(
        {
            "type": "add_geometry_nodes_modifier",
            "label": label,
            "objects": changed,
            "node_group": group.name,
            "created_group": created_group,
            "template": template_key,
            "warnings": warnings,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Added Geometry Nodes modifier to {len(changed)} mesh object(s)",
        "objects": changed,
        "node_group": group.name,
        "template": template_key,
        "warnings": warnings,
        "transaction_id": transaction["id"],
    }

def add_window_materials(
    context,
    *,
    target_name="",
    material_name="Agent Bridge Blue Glass",
    color=(0.08, 0.35, 0.65, 0.42),
    create_panels=True,
    label="Add window materials",
):
    target = bpy.data.objects.get(target_name) if target_name else context.active_object
    transaction = live_preview.begin(label)
    material = bpy.data.materials.get(material_name)
    if material is None:
        material = bpy.data.materials.new(material_name)
        live_preview._record_created_id("material", material.name)
    else:
        _record_shader_material(material)
    rgba = (
        float(color[0]),
        float(color[1]),
        float(color[2]),
        float(color[3]) if len(color) > 3 else 0.45,
    )
    material.diffuse_color = rgba
    principled = _ensure_principled_material(material)
    _set_socket_value(principled.inputs.get("Base Color"), rgba)
    _set_socket_value(principled.inputs.get("Alpha"), rgba[3])
    _set_socket_value(principled.inputs.get("Roughness"), 0.08)
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "BLENDED"
    elif hasattr(material, "blend_method"):
        material.blend_method = "BLEND"

    assigned = []
    for obj in context.scene.objects:
        lowered = obj.name.lower()
        if obj.type == "MESH" and any(word in lowered for word in ("window", "glass", "windshield")):
            live_preview._record_object_materials(obj)
            if obj.material_slots:
                obj.material_slots[0].material = material
            else:
                obj.data.materials.append(material)
            assigned.append(obj.name)

    created = []
    if create_panels and target and target.type == "MESH":
        bounds = _bounds_world(target)
        min_x, min_y, min_z = bounds["min"]
        max_x, max_y, max_z = bounds["max"]
        sx, sy, sz = bounds["size"]
        thickness = max(0.015, min(sx, sy, sz) * 0.025)
        z = min_z + sz * 0.72
        panel_height = max(0.05, sz * 0.22)
        created.append(
            _create_cube_object(
                context,
                f"{target.name} Windshield Glass",
                (min_x + sx * 0.3, min_y - thickness, z),
                (sx * 0.18, thickness, panel_height),
                material,
            ).name
        )
        created.append(
            _create_cube_object(
                context,
                f"{target.name} Rear Glass",
                (max_x - sx * 0.28, min_y - thickness, z),
                (sx * 0.16, thickness, panel_height),
                material,
            ).name
        )
        for side_name, y in (("Left", min_y - thickness), ("Right", max_y + thickness)):
            created.append(
                _create_cube_object(
                    context,
                    f"{target.name} {side_name} Side Glass",
                    (min_x + sx * 0.52, y, z),
                    (sx * 0.24, thickness, panel_height),
                    material,
                ).name
            )
    transaction["applied_steps"].append(
        {"type": "add_window_materials", "label": label, "material": material.name, "assigned": assigned, "created": created}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Prepared window material {material.name}",
        "material": material.name,
        "assigned_objects": assigned,
        "created_objects": created,
        "transaction_id": transaction["id"],
    }

def create_material_palette(
    context,
    *,
    palette_name="Agent Bridge Material Palette",
    palette="product_neutral",
    create_swatches=True,
    assign_to_selected=False,
    label="Create material palette",
):
    palette_key = str(palette or "product_neutral").lower()
    entries = MATERIAL_PALETTES.get(palette_key) or MATERIAL_PALETTES["product_neutral"]
    transaction = live_preview.begin(label, context)
    palette_name = str(palette_name or "Agent Bridge Material Palette")
    selected_for_assignment = [obj for obj in context.selected_objects if obj.type == "MESH" and obj.data]
    materials = []
    for suffix, color in entries:
        material = _material_for_color(f"{palette_name} {suffix}", color)
        materials.append(material)

    swatches = []
    if create_swatches:
        active = context.active_object
        if active is not None and hasattr(active, "bound_box"):
            bounds = _bounds_world(active)
            min_x, min_y, min_z = bounds["min"]
            sx, sy, sz = bounds["size"]
            max_dim = max(1.0, sx, sy, sz)
            start = (min_x, min_y - max_dim * 0.35, min_z + max_dim * 0.05)
            size = max_dim * 0.08
            gap = size * 1.35
        else:
            start = (0.0, -2.0, 0.05)
            size = 0.12
            gap = 0.18
        for index, material in enumerate(materials):
            swatch = _create_cube_object(
                context,
                f"{palette_name} Swatch {index + 1}",
                (start[0] + gap * index, start[1], start[2]),
                (size, size, size),
                material,
            )
            swatches.append(swatch.name)

    assigned = []
    if assign_to_selected:
        for index, obj in enumerate(selected_for_assignment):
            material = materials[index % len(materials)]
            live_preview._record_object_materials(obj)
            obj.data.materials.clear()
            obj.data.materials.append(material)
            assigned.append({"object": obj.name, "material": material.name})

    transaction["applied_steps"].append(
        {
            "type": "create_material_palette",
            "label": label,
            "palette": palette_key if palette_key in MATERIAL_PALETTES else "product_neutral",
            "materials": [material.name for material in materials],
            "swatches": swatches,
            "assigned": assigned,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Created {len(materials)} material palette entries",
        "palette": palette_key if palette_key in MATERIAL_PALETTES else "product_neutral",
        "materials": [material.name for material in materials],
        "swatches": swatches,
        "assigned": assigned,
        "transaction_id": transaction["id"],
    }





def register():

    pass





def unregister():

    pass

