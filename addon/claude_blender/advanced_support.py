"""Advanced Blender helpers for advanced support."""



from __future__ import annotations

from contextlib import contextmanager

import bpy
from mathutils import Vector

from . import blender_compat, live_preview



KEYFRAME_INTERPOLATIONS = {
    "CONSTANT",
    "LINEAR",
    "BEZIER",
    "SINE",
    "QUAD",
    "CUBIC",
    "QUART",
    "QUINT",
    "EXPO",
    "CIRC",
    "BACK",
    "BOUNCE",
    "ELASTIC",
}

MATERIAL_PALETTES = {
    "product_neutral": [
        ("Graphite", (0.04, 0.045, 0.05, 1.0)),
        ("Warm Silver", (0.62, 0.6, 0.56, 1.0)),
        ("Porcelain", (0.92, 0.9, 0.84, 1.0)),
        ("Signal Blue", (0.02, 0.24, 0.72, 1.0)),
        ("Safety Amber", (1.0, 0.56, 0.08, 1.0)),
    ],
    "automotive": [
        ("Paint Red", (0.8, 0.02, 0.015, 1.0)),
        ("Deep Blue", (0.02, 0.08, 0.28, 1.0)),
        ("Rubber Black", (0.005, 0.005, 0.006, 1.0)),
        ("Chrome", (0.72, 0.72, 0.68, 1.0)),
        ("Glass Blue", (0.08, 0.35, 0.65, 0.42)),
    ],
    "cinematic": [
        ("Key Warm", (1.0, 0.74, 0.42, 1.0)),
        ("Cool Fill", (0.15, 0.32, 0.82, 1.0)),
        ("Deep Shadow", (0.015, 0.014, 0.02, 1.0)),
        ("Practical Glow", (1.0, 0.85, 0.2, 1.0)),
        ("Muted Skin", (0.72, 0.48, 0.36, 1.0)),
    ],
}

def _coerce_vector(value, fallback):
    return live_preview._coerce_vector(value, fallback)

def _coerce_color(value, fallback=(1.0, 1.0, 1.0, 1.0)):
    values = list(value) if value is not None else list(fallback)
    result = values[:4]
    while len(result) < 4:
        result.append(fallback[len(result)])
    return tuple(float(component) for component in result)

def _record_shader_material(material):
    transaction = live_preview.begin()
    key = f"material:{material.name}:shader"
    if key in transaction["before_state"]:
        return
    principled = _find_node(material, "BSDF_PRINCIPLED")
    sockets = {}
    if principled:
        for socket_name in ("Base Color", "Metallic", "Roughness", "Alpha", "Emission Color", "Emission Strength"):
            socket = principled.inputs.get(socket_name)
            if socket and hasattr(socket, "default_value"):
                sockets[socket_name] = _socket_value(socket.default_value)
    node_names = []
    links = []
    material_tree = blender_compat.node_tree(material)
    if material_tree:
        node_names = [node.name for node in material_tree.nodes]
        links = [
            {
                "from_node": link.from_node.name,
                "from_socket": {
                    "name": link.from_socket.name,
                    "identifier": getattr(link.from_socket, "identifier", link.from_socket.name),
                },
                "to_node": link.to_node.name,
                "to_socket": {
                    "name": link.to_socket.name,
                    "identifier": getattr(link.to_socket, "identifier", link.to_socket.name),
                },
            }
            for link in material_tree.links
        ]
    transaction["before_state"][key] = {
        "kind": "shader_material",
        "material_name": material.name,
        "use_nodes": blender_compat.node_tree_enabled(material),
        "diffuse_color": tuple(float(component) for component in material.diffuse_color),
        "blend_method": getattr(material, "blend_method", None),
        "surface_render_method": getattr(material, "surface_render_method", None),
        "principled_socket_values": sockets,
        "node_names": node_names,
        "links": links,
    }
    transaction["changed_data_blocks"].append(material.name)

def _record_scene_render(scene):
    transaction = live_preview.begin()
    key = f"scene:{scene.name}:render_settings"
    if key in transaction["before_state"]:
        return
    view_settings = getattr(scene, "view_settings", None)
    cycles = getattr(scene, "cycles", None)
    eevee = getattr(scene, "eevee", None)
    transaction["before_state"][key] = {
        "kind": "scene_render_settings",
        "scene_name": scene.name,
        "engine": scene.render.engine,
        "resolution_x": int(scene.render.resolution_x),
        "resolution_y": int(scene.render.resolution_y),
        "fps": int(scene.render.fps),
        "frame_start": int(scene.frame_start),
        "frame_end": int(scene.frame_end),
        "frame_current": int(scene.frame_current),
        "film_transparent": bool(scene.render.film_transparent),
        "view_transform": getattr(view_settings, "view_transform", None),
        "look": getattr(view_settings, "look", None),
        "exposure": getattr(view_settings, "exposure", None),
        "gamma": getattr(view_settings, "gamma", None),
        "cycles_samples": getattr(cycles, "samples", None),
        "cycles_preview_samples": getattr(cycles, "preview_samples", None),
        "cycles_use_denoising": getattr(cycles, "use_denoising", None),
        "eevee_taa_render_samples": getattr(eevee, "taa_render_samples", None),
        "eevee_taa_samples": getattr(eevee, "taa_samples", None),
    }
    transaction["changed_data_blocks"].append(scene.name)

def _record_camera_settings(camera_obj):
    transaction = live_preview.begin()
    data = camera_obj.data if camera_obj and camera_obj.type == "CAMERA" else None
    if data is None:
        return
    key = f"camera:{data.name}:settings"
    if key in transaction["before_state"]:
        return
    transaction["before_state"][key] = {
        "kind": "camera_settings",
        "camera_name": data.name,
        "lens": float(data.lens),
        "sensor_width": float(data.sensor_width),
        "use_dof": bool(data.dof.use_dof),
        "focus_object": data.dof.focus_object.name if data.dof.focus_object else None,
        "aperture_fstop": float(data.dof.aperture_fstop),
    }
    transaction["changed_data_blocks"].append(camera_obj.name)

def _socket_value(value):
    if isinstance(value, (int, float, bool, str)) or value is None:
        return value
    try:
        return tuple(float(component) for component in value)
    except TypeError:
        return value

def _set_socket_value(socket, value):
    if not socket or not hasattr(socket, "default_value"):
        return False
    current = socket.default_value
    if hasattr(current, "__len__") and not isinstance(current, str):
        values = list(value)
        for index in range(min(len(current), len(values))):
            current[index] = float(values[index])
    else:
        socket.default_value = value
    return True

def _normalize_frame_range(frame_start, frame_end, label):
    frame_start = int(frame_start)
    frame_end = int(frame_end)
    if frame_start == frame_end:
        return None, None, {"ok": False, "message": f"{label} needs two different frames"}
    if frame_start > frame_end:
        frame_start, frame_end = frame_end, frame_start
    return frame_start, frame_end, None

def _set_action_interpolation(action, interpolation="LINEAR"):
    interpolation = str(interpolation or "LINEAR").upper()
    if interpolation not in KEYFRAME_INTERPOLATIONS:
        interpolation = "LINEAR"
    for fcurve in live_preview._iter_action_fcurves(action):
        for point in fcurve.keyframe_points:
            point.interpolation = interpolation

def _axis_index(axis):
    axis = str(axis or "Z").upper()
    return {"X": 0, "Y": 1, "Z": 2}.get(axis, 2), axis if axis in {"X", "Y", "Z"} else "Z"

def _find_node(material, node_type):
    tree = blender_compat.node_tree(material)
    if tree is None:
        return None
    return next((node for node in tree.nodes if node.type == node_type), None)

def _ensure_principled_material(material):
    tree = blender_compat.ensure_node_tree(material)
    if tree is None:
        raise RuntimeError(f"Material {material.name} does not expose a shader node tree")
    nodes = tree.nodes
    links = tree.links
    principled = _find_node(material, "BSDF_PRINCIPLED")
    if principled is None:
        principled = nodes.new(type="ShaderNodeBsdfPrincipled")
        principled.location = (0, 0)
    output = _find_node(material, "OUTPUT_MATERIAL")
    if output is None:
        output = nodes.new(type="ShaderNodeOutputMaterial")
        output.location = (260, 0)
    if principled.outputs and output.inputs.get("Surface") and not output.inputs["Surface"].is_linked:
        links.new(principled.outputs[0], output.inputs["Surface"])
    return principled

def _material_for_color(name, color):
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
        live_preview._record_created_id("material", material.name)
    else:
        live_preview._record_material(material)
    rgba = (
        float(color[0]),
        float(color[1]),
        float(color[2]),
        float(color[3]) if len(color) > 3 else 1.0,
    )
    material.diffuse_color = rgba
    _record_shader_material(material)
    principled = _ensure_principled_material(material)
    _set_socket_value(principled.inputs.get("Base Color"), rgba)
    _set_socket_value(principled.inputs.get("Alpha"), rgba[3])
    return material

def _selection_snapshot(context):
    active = context.view_layer.objects.active if context.view_layer else None
    return {
        "selected_names": [obj.name for obj in context.selected_objects],
        "active_name": active.name if active else "",
    }

def _restore_selection_snapshot(context, snapshot):
    bpy.ops.object.select_all(action="DESELECT")
    for name in snapshot.get("selected_names", []):
        obj = bpy.data.objects.get(name)
        if obj:
            obj.select_set(True)
    if context.view_layer:
        context.view_layer.objects.active = bpy.data.objects.get(snapshot.get("active_name", ""))

@contextmanager
def _preserve_selection(context):
    snapshot = _selection_snapshot(context)
    try:
        yield
    finally:
        _restore_selection_snapshot(context, snapshot)

def _bounds_world(obj):
    coords = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_x = min(vec.x for vec in coords)
    max_x = max(vec.x for vec in coords)
    min_y = min(vec.y for vec in coords)
    max_y = max(vec.y for vec in coords)
    min_z = min(vec.z for vec in coords)
    max_z = max(vec.z for vec in coords)
    return {
        "center": ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0, (min_z + max_z) / 2.0),
        "min": (min_x, min_y, min_z),
        "max": (max_x, max_y, max_z),
        "size": (max_x - min_x, max_y - min_y, max_z - min_z),
    }

def _create_cube_object(context, name, location, scale, material=None):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = context.object
    obj.name = name
    obj.data.name = f"{name} Mesh"
    obj.scale = scale
    if material:
        obj.data.materials.append(material)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("mesh", obj.data.name)
    return obj

def _create_curve_line(context, name, points, bevel_depth, material=None):
    curve = bpy.data.curves.new(f"{name} Data", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = max(0.0, float(bevel_depth))
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, values in zip(spline.points, points):
        point.co = (float(values[0]), float(values[1]), float(values[2]), 1.0)
    obj = bpy.data.objects.new(name, curve)
    context.scene.collection.objects.link(obj)
    if material:
        curve.materials.append(material)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("curve", curve.name)
    return obj

def _create_empty_target(context, name, location, *, display_size=0.4):
    empty = bpy.data.objects.new(name, object_data=None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.empty_display_size = max(0.01, float(display_size))
    empty.location = _coerce_vector(location, (0.0, 0.0, 0.0))
    context.scene.collection.objects.link(empty)
    live_preview._record_created_id("object", empty.name)
    return empty

def _track_to_target(obj, target):
    constraint = obj.constraints.new(type="TRACK_TO")
    constraint.name = "Agent Bridge Look At Target"
    constraint.target = target
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"
    live_preview._record_created_constraint(obj, constraint)
    return constraint

def _create_area_light(context, name, location, *, energy, size, color, target=None):
    data = bpy.data.lights.new(name=name, type="AREA")
    data.energy = max(0.0, float(energy))
    data.size = max(0.01, float(size))
    data.color = (float(color[0]), float(color[1]), float(color[2]))
    obj = bpy.data.objects.new(name=name, object_data=data)
    obj.location = _coerce_vector(location, (0.0, 0.0, 0.0))
    if hasattr(obj, "visible_camera"):
        obj.visible_camera = False
    context.scene.collection.objects.link(obj)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("light", data.name)
    if target is not None:
        _track_to_target(obj, target)
    return obj

def _scene_light_names(context):
    """Names of render-visible lights already in the scene (composition awareness)."""
    scene = getattr(context, "scene", None)
    if scene is None:
        return []
    names = []
    for obj in getattr(scene, "objects", []):
        if getattr(obj, "type", "") == "LIGHT" and not getattr(obj, "hide_render", False):
            names.append(obj.name)
    return names

def _existing_light_warning(existing_names, added_count, *, source):
    """Warn when a helper stacks lights on top of an already-lit scene."""
    if not existing_names or added_count <= 0:
        return None
    sample = ", ".join(existing_names[:4])
    more = "" if len(existing_names) <= 4 else f", +{len(existing_names) - 4} more"
    return (
        f"Scene already had {len(existing_names)} render-visible light(s) before {source} added "
        f"{added_count} more; stacking lighting rigs can over-expose the render. "
        f"Hide or remove competing lights ({sample}{more}) if highlights blow out."
    )

TRANSFORM_PATH_ALIASES = {
    "location": "location",
    "position": "location",
    "translation": "location",
    "rotation": "rotation_euler",
    "rotation_euler": "rotation_euler",
    "scale": "scale",
}

def _resolve_named_or_selected_objects(context, object_names=None, *, selected_only=False, fallback_active=True):
    names = [str(name) for name in object_names or [] if str(name).strip()]
    missing = []
    if names:
        objects = [bpy.data.objects.get(name) for name in names]
        missing = [name for name, obj in zip(names, objects) if obj is None]
        objects = [obj for obj in objects if obj]
    elif selected_only or context.selected_objects:
        objects = list(context.selected_objects)
    elif fallback_active and context.active_object:
        objects = [context.active_object]
    else:
        objects = []
    return [obj for obj in objects if obj], missing

def _prepare_transform_action_for_edit(obj):
    action = obj.animation_data.action if obj.animation_data and obj.animation_data.action else None
    if action:
        transaction = live_preview.current_transaction()
        if transaction and f"created:action:{action.name}" in transaction.get("before_state", {}):
            return action, False
        live_preview._record_object_animation(obj)
        live_preview._record_action_edit(action)
        return action, False
    return live_preview._assign_preview_action(obj), True

def _link_object_like_source(context, source, duplicate):
    collections = list(source.users_collection)
    if not collections:
        collections = [context.collection or context.scene.collection]
    for collection in collections:
        collection.objects.link(duplicate)

def _resolve_edit_objects(context, *, object_names=None, selected_only=True, include_active=False, max_objects=64):
    names = [str(name) for name in object_names or [] if str(name).strip()]
    missing = []
    if names:
        objects = []
        for name in names:
            obj = bpy.data.objects.get(name)
            if obj:
                objects.append(obj)
            else:
                missing.append(name)
        return objects[: max(1, int(max_objects or 1))], missing
    if selected_only:
        return list(context.selected_objects)[: max(1, int(max_objects or 1))], missing
    if include_active and context.active_object:
        return [context.active_object], missing
    return [], missing

def _clamped_float(value, default, minimum, maximum):
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = float(default)
    return max(float(minimum), min(float(maximum), result))

def _mesh_edit_blockers(obj, *, allow_shape_keys=False):
    blockers = []
    mesh = obj.data if obj and obj.type == "MESH" else None
    if mesh is None:
        blockers.append("not a mesh")
    elif mesh.users > 1:
        blockers.append("mesh data has multiple users")
    elif mesh.shape_keys and not allow_shape_keys:
        blockers.append("shape-key meshes need explicit allow_shape_keys")
    if getattr(obj, "library", None) is not None or getattr(mesh, "library", None) is not None:
        blockers.append("linked library data is read-only")
    return blockers





def register():

    pass





def unregister():

    pass

