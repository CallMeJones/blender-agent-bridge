"""Advanced Blender helpers for animation."""



from __future__ import annotations

import math

import bpy
from mathutils import Vector

from . import blender_compat, live_preview

from .advanced_support import (
    KEYFRAME_INTERPOLATIONS,
    TRANSFORM_PATH_ALIASES,
    _axis_index,
    _coerce_color,
    _coerce_vector,
    _create_curve_line,
    _ensure_principled_material,
    _material_for_color,
    _normalize_frame_range,
    _prepare_transform_action_for_edit,
    _record_camera_settings,
    _record_shader_material,
    _resolve_named_or_selected_objects,
    _set_action_interpolation,
    _set_socket_value,
    _socket_value,
)



def _record_shape_keys(obj):
    transaction = live_preview.begin()
    key = f"object:{obj.name}:shape_keys"
    if key in transaction["before_state"]:
        return
    keys = obj.data.shape_keys if obj.type == "MESH" and obj.data else None
    animation_data = getattr(keys, "animation_data", None) if keys else None
    action = animation_data.action if animation_data else None
    transaction["before_state"][key] = {
        "kind": "shape_keys",
        "object_name": obj.name,
        "had_shape_keys": keys is not None,
        "key_blocks": [
            {
                "name": block.name,
                "value": float(block.value),
                "slider_min": float(block.slider_min),
                "slider_max": float(block.slider_max),
            }
            for block in list(keys.key_blocks)
        ]
        if keys
        else [],
        "had_animation_data": animation_data is not None,
        "action_name": action.name if action else None,
    }
    transaction["changed_data_blocks"].append(obj.name)

def _record_material_node_tree_animation(material):
    node_tree = blender_compat.node_tree(material)
    if node_tree is None:
        return
    transaction = live_preview.begin()
    key = f"material:{material.name}:node_tree_animation"
    if key in transaction["before_state"]:
        return
    animation_data = node_tree.animation_data
    action = animation_data.action if animation_data else None
    transaction["before_state"][key] = {
        "kind": "material_node_tree_animation",
        "material_name": material.name,
        "had_animation_data": animation_data is not None,
        "action_name": action.name if action else None,
    }
    transaction["changed_data_blocks"].append(material.name)

def _assign_material_node_tree_preview_action(material):
    _record_material_node_tree_animation(material)
    action = bpy.data.actions.new(name=f"{material.name} Agent Bridge Material Preview Action")
    material.node_tree.animation_data_create().action = action
    live_preview._record_created_id("action", action.name)
    return action

def create_shape_key(context, *, object_name="", key_name="Agent Bridge Shape", value=0.0, label="Create shape key"):
    obj = bpy.data.objects.get(object_name) if object_name else context.active_object
    if obj is None or obj.type != "MESH":
        return {"ok": False, "message": "A mesh object is required for shape keys"}
    transaction = live_preview.begin(label)
    _record_shape_keys(obj)
    if obj.data.shape_keys is None:
        obj.shape_key_add(name="Basis")
    key = obj.data.shape_keys.key_blocks.get(key_name)
    created = key is None
    if key is None:
        key = obj.shape_key_add(name=key_name or "Agent Bridge Shape")
    key.value = max(float(key.slider_min), min(float(key.slider_max), float(value)))
    transaction["applied_steps"].append(
        {
            "type": "create_shape_key",
            "label": label,
            "object": obj.name,
            "shape_key": key.name,
            "created": created,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"{'Created' if created else 'Updated'} shape key {key.name} on {obj.name}",
        "object": obj.name,
        "shape_key": key.name,
        "transaction_id": transaction["id"],
    }

def animate_shape_key(
    context,
    *,
    object_name="",
    key_name,
    frame_start,
    frame_end,
    value_start=0.0,
    value_end=1.0,
    create_if_missing=True,
    label="Animate shape key",
):
    obj = bpy.data.objects.get(object_name) if object_name else context.active_object
    if obj is None or obj.type != "MESH":
        return {"ok": False, "message": "A mesh object is required for shape key animation"}
    transaction = live_preview.begin(label)
    live_preview._record_scene_timeline(context.scene)
    _record_shape_keys(obj)
    if obj.data.shape_keys is None:
        if not create_if_missing:
            return {"ok": False, "message": f"Object has no shape keys: {obj.name}"}
        obj.shape_key_add(name="Basis")
    key = obj.data.shape_keys.key_blocks.get(key_name)
    if key is None:
        if not create_if_missing:
            return {"ok": False, "message": f"Shape key not found: {key_name}"}
        key = obj.shape_key_add(name=key_name or "Agent Bridge Shape")
    frame_start = int(frame_start)
    frame_end = int(frame_end)
    if frame_start == frame_end:
        return {"ok": False, "message": "Shape key animation needs two different frames"}
    if frame_start > frame_end:
        frame_start, frame_end = frame_end, frame_start
    context.scene.frame_start = min(context.scene.frame_start, frame_start)
    context.scene.frame_end = max(context.scene.frame_end, frame_end)
    key.value = max(float(key.slider_min), min(float(key.slider_max), float(value_start)))
    key.keyframe_insert(data_path="value", frame=frame_start)
    key.value = max(float(key.slider_min), min(float(key.slider_max), float(value_end)))
    key.keyframe_insert(data_path="value", frame=frame_end)
    keys = obj.data.shape_keys
    action = keys.animation_data.action if keys.animation_data else None
    if action:
        live_preview._record_created_id("action", action.name)
        live_preview._set_linear_interpolation(action)
    context.scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {
            "type": "animate_shape_key",
            "label": label,
            "object": obj.name,
            "shape_key": key.name,
            "frame_start": frame_start,
            "frame_end": frame_end,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Animated shape key {key.name} on {obj.name}",
        "object": obj.name,
        "shape_key": key.name,
        "transaction_id": transaction["id"],
    }

def animate_object_bounce(
    context,
    *,
    object_name="",
    frame_start,
    frame_end,
    axis="Z",
    distance=2.0,
    cycles=1,
    interpolation="BEZIER",
    label="Animate object bounce",
):
    obj = bpy.data.objects.get(object_name) if object_name else context.active_object
    if obj is None:
        return {"ok": False, "message": "Object not found for bounce animation"}
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Bounce animation")
    if error:
        return error
    cycles = max(1, min(24, int(cycles)))
    axis_index, axis = _axis_index(axis)
    distance = float(distance)

    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, frame_end)

    live_preview._record_object_transform(obj)
    action = live_preview._assign_preview_action(obj)
    base_location = [float(value) for value in obj.location]
    span = frame_end - frame_start
    keyed_frames = []
    for step in range(cycles * 2 + 1):
        frame = round(frame_start + (span * step / (cycles * 2)))
        location = list(base_location)
        location[axis_index] += distance if step % 2 else 0.0
        obj.location = location
        obj.keyframe_insert(data_path="location", frame=frame)
        keyed_frames.append(int(frame))
    _set_action_interpolation(action, interpolation)
    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {
            "type": "animate_object_bounce",
            "label": label,
            "object": obj.name,
            "axis": axis,
            "distance": distance,
            "cycles": cycles,
            "frames": keyed_frames,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Animated bounce on {obj.name} over {cycles} cycle(s)",
        "object": obj.name,
        "frame_start": frame_start,
        "frame_end": frame_end,
        "frames": keyed_frames,
        "action": action.name,
        "transaction_id": transaction["id"],
    }

def create_progressive_bounce_animation(
    context,
    *,
    object_name="",
    frame_start,
    frame_end,
    axis="Z",
    distance=2.0,
    cycles=2,
    scale_end_factor=0.6,
    interpolation="BEZIER",
    label="Create progressive bounce animation",
):
    obj = bpy.data.objects.get(object_name) if object_name else context.active_object
    if obj is None:
        return {"ok": False, "message": "Object not found for progressive bounce animation"}
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Progressive bounce animation")
    if error:
        return error
    cycles = max(1, min(24, int(cycles)))
    axis_index, axis = _axis_index(axis)
    distance = float(distance)
    scale_end_factor = max(0.01, float(scale_end_factor))

    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, frame_end)

    live_preview._record_object_transform(obj)
    action = live_preview._assign_preview_action(obj)
    base_location = [float(value) for value in obj.location]
    base_scale = [float(value) for value in obj.scale]
    span = frame_end - frame_start
    step_count = cycles * 2
    keyed_frames = []
    scale_keys = []
    for step in range(step_count + 1):
        progress = step / step_count if step_count else 1.0
        frame = round(frame_start + (span * progress))
        factor = 1.0 + ((scale_end_factor - 1.0) * progress)
        location = list(base_location)
        location[axis_index] += distance if step % 2 else 0.0
        obj.location = location
        obj.scale = [component * factor for component in base_scale]
        obj.keyframe_insert(data_path="location", frame=frame)
        obj.keyframe_insert(data_path="scale", frame=frame)
        keyed_frames.append(int(frame))
        scale_keys.append({"frame": int(frame), "factor": round(float(factor), 6)})
    _set_action_interpolation(action, interpolation)
    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {
            "type": "create_progressive_bounce_animation",
            "label": label,
            "object": obj.name,
            "axis": axis,
            "distance": distance,
            "cycles": cycles,
            "frames": keyed_frames,
            "scale_end_factor": scale_end_factor,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Animated progressive bounce on {obj.name} over {cycles} cycle(s)",
        "object": obj.name,
        "frame_start": frame_start,
        "frame_end": frame_end,
        "frames": keyed_frames,
        "scale_keys": scale_keys,
        "scale_end_factor": scale_end_factor,
        "action": action.name,
        "transaction_id": transaction["id"],
    }

def _resolve_animation_material(context, material_name="", object_name="", create_if_missing=True):
    material = bpy.data.materials.get(str(material_name or "")) if material_name else None
    obj = bpy.data.objects.get(str(object_name or "")) if object_name else context.active_object
    has_material_slots = obj is not None and getattr(obj, "data", None) is not None and hasattr(obj.data, "materials")
    if material is None and has_material_slots:
        material = obj.active_material or (obj.data.materials[0] if len(obj.data.materials) else None)
    if material is None and create_if_missing:
        material = bpy.data.materials.new(str(material_name or "Agent Bridge Animated Material"))
        live_preview._record_created_id("material", material.name)
        if has_material_slots:
            live_preview._record_object_materials(obj)
            obj.data.materials.append(material)
    return material, obj

def _socket_animation_value(socket, value, fallback):
    current = socket.default_value
    if hasattr(current, "__len__") and not isinstance(current, str):
        fallback_values = list(fallback) if fallback is not None else list(current)
        if isinstance(value, (int, float)):
            values = [float(value)] * len(current)
        else:
            values = list(value if value is not None else fallback_values)
        if len(values) == 3 and len(current) >= 4:
            values.append(fallback_values[3] if len(fallback_values) > 3 else 1.0)
        while len(values) < len(current):
            index = len(values)
            values.append(fallback_values[index] if index < len(fallback_values) else 0.0)
        return tuple(float(component) for component in values[: len(current)])
    if isinstance(value, (list, tuple)):
        return float(value[0]) if value else float(fallback or 0.0)
    return float(value if value is not None else fallback)

def animate_material_property(
    context,
    *,
    material_name="",
    object_name="",
    property_name="base_color",
    frame_start,
    frame_end,
    value_start=None,
    value_end=None,
    create_if_missing=True,
    interpolation="LINEAR",
    label="Animate material property",
):
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Material animation")
    if error:
        return error
    property_key = str(property_name or "base_color").strip().lower().replace(" ", "_")
    socket_names = {
        "base_color": "Base Color",
        "diffuse_color": "Base Color",
        "color": "Base Color",
        "emission_color": "Emission Color",
        "emission": "Emission Color",
        "emission_strength": "Emission Strength",
        "glow": "Emission Strength",
        "roughness": "Roughness",
        "metallic": "Metallic",
        "alpha": "Alpha",
    }
    socket_name = socket_names.get(property_key)
    if socket_name is None:
        return {"ok": False, "message": f"Unsupported material animation property: {property_name}"}

    transaction = live_preview.begin(label, context)
    material, obj = _resolve_animation_material(context, material_name, object_name, create_if_missing)
    if material is None:
        return {"ok": False, "message": "Material not found for animation"}
    live_preview._record_scene_timeline(context.scene)
    context.scene.frame_start = min(context.scene.frame_start, frame_start)
    context.scene.frame_end = max(context.scene.frame_end, frame_end)
    _record_shader_material(material)
    principled = _ensure_principled_material(material)
    socket = principled.inputs.get(socket_name)
    if socket is None or not hasattr(socket, "default_value"):
        return {"ok": False, "message": f"Material socket not found: {socket_name}"}

    current_value = _socket_value(socket.default_value)
    start = _socket_animation_value(socket, value_start, current_value)
    end = _socket_animation_value(socket, value_end, start)
    action = _assign_material_node_tree_preview_action(material)
    _set_socket_value(socket, start)
    socket.keyframe_insert(data_path="default_value", frame=frame_start)
    _set_socket_value(socket, end)
    socket.keyframe_insert(data_path="default_value", frame=frame_end)
    if socket_name == "Base Color":
        material.diffuse_color = end
    elif socket_name == "Alpha":
        rgba = list(material.diffuse_color)
        while len(rgba) < 4:
            rgba.append(1.0)
        rgba[3] = float(end)
        material.diffuse_color = tuple(rgba)
        if hasattr(material, "blend_method"):
            material.blend_method = "BLEND"
    _set_action_interpolation(action, interpolation)
    context.scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {
            "type": "animate_material_property",
            "label": label,
            "material": material.name,
            "object": obj.name if obj else None,
            "property": property_key,
            "frame_start": frame_start,
            "frame_end": frame_end,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Animated {property_key} on material {material.name}",
        "material": material.name,
        "property": property_key,
        "socket": socket_name,
        "action": action.name,
        "transaction_id": transaction["id"],
    }

def _record_light_settings(light_obj):
    data = light_obj.data if light_obj and light_obj.type == "LIGHT" else None
    if data is None:
        return
    transaction = live_preview.begin()
    key = f"light:{data.name}:settings"
    if key in transaction["before_state"]:
        return
    transaction["before_state"][key] = {
        "kind": "light_settings",
        "light_data_name": data.name,
        "energy": float(data.energy),
        "color": tuple(float(component) for component in data.color),
        "shadow_soft_size": float(getattr(data, "shadow_soft_size", 0.0)),
        "spot_size": float(getattr(data, "spot_size", 0.0)),
        "spot_blend": float(getattr(data, "spot_blend", 0.0)),
    }
    transaction["changed_data_blocks"].append(data.name)

def _record_light_data_animation(light_obj):
    data = light_obj.data if light_obj and light_obj.type == "LIGHT" else None
    if data is None:
        return
    transaction = live_preview.begin()
    key = f"light:{data.name}:animation"
    if key in transaction["before_state"]:
        return
    animation_data = data.animation_data
    action = animation_data.action if animation_data else None
    transaction["before_state"][key] = {
        "kind": "light_data_animation",
        "light_data_name": data.name,
        "had_animation_data": animation_data is not None,
        "action_name": action.name if action else None,
    }
    transaction["changed_data_blocks"].append(data.name)

def _assign_light_preview_action(light_obj):
    _record_light_data_animation(light_obj)
    action = bpy.data.actions.new(name=f"{light_obj.name} Agent Bridge Light Preview Action")
    light_obj.data.animation_data_create().action = action
    live_preview._record_created_id("action", action.name)
    return action

def _light_animation_value(current, value):
    if hasattr(current, "__len__") and not isinstance(current, str):
        values = list(value if value is not None else current)
        while len(values) < len(current):
            values.append(current[len(values)])
        return tuple(float(component) for component in values[: len(current)])
    if isinstance(value, (list, tuple)):
        return float(value[0]) if value else float(current)
    return float(value if value is not None else current)

def animate_light_property(
    context,
    *,
    light_name="",
    property_name="energy",
    frame_start,
    frame_end,
    value_start=None,
    value_end=None,
    interpolation="LINEAR",
    label="Animate light property",
):
    light_obj = bpy.data.objects.get(light_name) if light_name else context.active_object
    if light_obj is None or light_obj.type != "LIGHT":
        light_obj = next((obj for obj in context.scene.objects if obj.type == "LIGHT"), None)
    if light_obj is None or light_obj.type != "LIGHT":
        return {"ok": False, "message": "A light object is required for light animation"}
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Light animation")
    if error:
        return error
    property_key = str(property_name or "energy").strip().lower()
    data_path_map = {
        "energy": "energy",
        "intensity": "energy",
        "color": "color",
        "colour": "color",
        "shadow_soft_size": "shadow_soft_size",
        "spot_size": "spot_size",
        "spot_blend": "spot_blend",
    }
    data_path = data_path_map.get(property_key)
    if data_path is None or not hasattr(light_obj.data, data_path):
        return {"ok": False, "message": f"Unsupported light animation property: {property_name}"}
    if value_start is None and value_end is None:
        return {"ok": False, "message": "Light animation needs at least value_end or value_start"}

    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, frame_end)
    _record_light_settings(light_obj)
    action = _assign_light_preview_action(light_obj)
    current = getattr(light_obj.data, data_path)
    start = _light_animation_value(current, value_start)
    end = _light_animation_value(start, value_end)
    setattr(light_obj.data, data_path, start)
    light_obj.data.keyframe_insert(data_path=data_path, frame=frame_start)
    setattr(light_obj.data, data_path, end)
    light_obj.data.keyframe_insert(data_path=data_path, frame=frame_end)
    _set_action_interpolation(action, interpolation)
    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {
            "type": "animate_light_property",
            "label": label,
            "light": light_obj.name,
            "property": data_path,
            "frame_start": frame_start,
            "frame_end": frame_end,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Animated {data_path} on light {light_obj.name}",
        "light": light_obj.name,
        "property": data_path,
        "action": action.name,
        "transaction_id": transaction["id"],
    }

def create_follow_path_animation(
    context,
    *,
    object_name="",
    path_name="",
    path_points=None,
    frame_start,
    frame_end,
    constraint_name="Agent Bridge Follow Path",
    follow_curve=True,
    interpolation="LINEAR",
    label="Create follow path animation",
):
    obj = bpy.data.objects.get(object_name) if object_name else context.active_object
    if obj is None:
        return {"ok": False, "message": "Object not found for follow-path animation"}
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Follow-path animation")
    if error:
        return error

    transaction = live_preview.begin(label, context)
    path_obj = bpy.data.objects.get(str(path_name or "")) if path_name else None
    if path_obj is None:
        if len(path_points or []) < 2:
            return {"ok": False, "message": "Provide an existing curve path or at least two path points"}
        path_obj = _create_curve_line(context, path_name or f"{obj.name} Follow Path", path_points, 0.02)
    if path_obj.type != "CURVE":
        return {"ok": False, "message": f"Follow path target is not a curve: {path_obj.name}"}

    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, frame_end)
    live_preview._record_object_transform(obj)
    action = live_preview._assign_preview_action(obj)
    constraint = obj.constraints.new(type="FOLLOW_PATH")
    constraint.name = constraint_name or "Agent Bridge Follow Path"
    constraint.target = path_obj
    constraint.use_curve_follow = bool(follow_curve)
    constraint.use_fixed_location = True
    live_preview._record_created_constraint(obj, constraint)
    constraint.offset_factor = 0.0
    constraint.keyframe_insert(data_path="offset_factor", frame=frame_start)
    constraint.offset_factor = 1.0
    constraint.keyframe_insert(data_path="offset_factor", frame=frame_end)
    _set_action_interpolation(action, interpolation)
    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {
            "type": "create_follow_path_animation",
            "label": label,
            "object": obj.name,
            "path": path_obj.name,
            "constraint": constraint.name,
            "frame_start": frame_start,
            "frame_end": frame_end,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Animated {obj.name} along path {path_obj.name}",
        "object": obj.name,
        "path": path_obj.name,
        "constraint": constraint.name,
        "action": action.name,
        "transaction_id": transaction["id"],
    }

def _animation_action_from(data_block):
    animation_data = getattr(data_block, "animation_data", None)
    return animation_data.action if animation_data else None

def _object_animation_actions(obj):
    actions = [_animation_action_from(obj)]
    data = getattr(obj, "data", None)
    if data:
        actions.append(_animation_action_from(data))
    if obj.type == "MESH" and data and getattr(data, "shape_keys", None):
        actions.append(_animation_action_from(data.shape_keys))
    for slot in getattr(obj, "material_slots", []):
        material = slot.material
        if material:
            actions.append(_animation_action_from(material))
            material_tree = blender_compat.node_tree(material)
            if material_tree:
                actions.append(_animation_action_from(material_tree))
    return [action for action in actions if action]

def _resolve_animation_actions(context, *, action_names=None, object_names=None, selected_only=False, max_actions=32):
    actions = []
    missing_actions = []
    missing_objects = []
    seen = set()

    def add_action(action):
        if action and action.name not in seen:
            seen.add(action.name)
            actions.append(action)

    for name in action_names or []:
        action = bpy.data.actions.get(str(name))
        if action:
            add_action(action)
        else:
            missing_actions.append(str(name))

    objects = []
    if object_names:
        for name in object_names:
            obj = bpy.data.objects.get(str(name))
            if obj:
                objects.append(obj)
            else:
                missing_objects.append(str(name))
    elif selected_only:
        objects = list(context.selected_objects)
    elif context.active_object and not actions:
        objects = [context.active_object]

    for obj in objects:
        for action in _object_animation_actions(obj):
            add_action(action)

    return actions[: max(1, int(max_actions or 1))], missing_actions, missing_objects

def _valid_interpolation(value):
    interpolation = str(value or "LINEAR").upper()
    return interpolation if interpolation in KEYFRAME_INTERPOLATIONS else "LINEAR"

def _valid_easing(value):
    easing = str(value or "").upper()
    return easing if easing in {"AUTO", "EASE_IN", "EASE_OUT", "EASE_IN_OUT"} else ""

def set_action_interpolation(
    context,
    *,
    action_names=None,
    object_names=None,
    selected_only=False,
    interpolation="LINEAR",
    easing="",
    label="Set action interpolation",
):
    actions, missing_actions, missing_objects = _resolve_animation_actions(
        context,
        action_names=action_names or [],
        object_names=object_names or [],
        selected_only=selected_only,
    )
    if not actions:
        return {"ok": False, "message": "No actions found for interpolation update", "missing_action_names": missing_actions, "missing_object_names": missing_objects}
    interpolation = _valid_interpolation(interpolation)
    easing = _valid_easing(easing)
    transaction = live_preview.begin(label, context)
    changed = []
    for action in actions:
        live_preview._record_action_edit(action)
        for fcurve in live_preview._iter_action_fcurves(action):
            for point in fcurve.keyframe_points:
                point.interpolation = interpolation
                if easing and hasattr(point, "easing"):
                    point.easing = easing
            fcurve.update()
        changed.append(action.name)
    transaction["applied_steps"].append(
        {"type": "set_action_interpolation", "label": label, "actions": changed, "interpolation": interpolation, "easing": easing}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Updated interpolation on {len(changed)} action(s)",
        "actions": changed,
        "missing_action_names": missing_actions,
        "missing_object_names": missing_objects,
        "transaction_id": transaction["id"],
    }

def _action_frame_span(action):
    frames = [
        float(point.co.x)
        for fcurve in live_preview._iter_action_fcurves(action)
        for point in fcurve.keyframe_points
    ]
    if not frames:
        return None
    return min(frames), max(frames)

def retime_actions(
    context,
    *,
    action_names=None,
    object_names=None,
    selected_only=False,
    frame_start,
    frame_end,
    snap_to_integer=True,
    label="Retime actions",
):
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Action retime")
    if error:
        return error
    actions, missing_actions, missing_objects = _resolve_animation_actions(
        context,
        action_names=action_names or [],
        object_names=object_names or [],
        selected_only=selected_only,
    )
    if not actions:
        return {"ok": False, "message": "No actions found for retiming", "missing_action_names": missing_actions, "missing_object_names": missing_objects}
    retime_plan = []
    skipped = []
    for action in actions:
        span = _action_frame_span(action)
        if span is None or span[0] == span[1]:
            skipped.append(action.name)
            continue
        retime_plan.append((action, span))
    if not retime_plan:
        return {
            "ok": False,
            "message": "No retimeable actions found",
            "actions": [],
            "skipped_actions": skipped,
            "missing_action_names": missing_actions,
            "missing_object_names": missing_objects,
        }
    transaction = live_preview.begin(label, context)
    live_preview._record_scene_timeline(context.scene)
    context.scene.frame_start = min(context.scene.frame_start, frame_start)
    context.scene.frame_end = max(context.scene.frame_end, frame_end)
    changed = []
    for action, span in retime_plan:
        old_start, old_end = span
        scale = (frame_end - frame_start) / (old_end - old_start)
        live_preview._record_action_edit(action)
        for fcurve in live_preview._iter_action_fcurves(action):
            for point in fcurve.keyframe_points:
                old_x = float(point.co.x)
                new_x = frame_start + (old_x - old_start) * scale
                if snap_to_integer:
                    new_x = round(new_x)
                handle_left_dx = float(point.handle_left.x) - old_x
                handle_right_dx = float(point.handle_right.x) - old_x
                point.co.x = new_x
                point.handle_left.x = new_x + handle_left_dx * scale
                point.handle_right.x = new_x + handle_right_dx * scale
            fcurve.update()
        changed.append(action.name)
    context.scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {
            "type": "retime_actions",
            "label": label,
            "actions": changed,
            "frame_start": frame_start,
            "frame_end": frame_end,
            "skipped_actions": skipped,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": bool(changed),
        "message": f"Retimed {len(changed)} action(s)",
        "actions": changed,
        "skipped_actions": skipped,
        "missing_action_names": missing_actions,
        "missing_object_names": missing_objects,
        "transaction_id": transaction["id"],
    }

def add_action_cycles(
    context,
    *,
    action_names=None,
    object_names=None,
    selected_only=False,
    mode_before="NONE",
    mode_after="REPEAT",
    replace_existing=False,
    label="Add action cycles",
):
    actions, missing_actions, missing_objects = _resolve_animation_actions(
        context,
        action_names=action_names or [],
        object_names=object_names or [],
        selected_only=selected_only,
    )
    if not actions:
        return {"ok": False, "message": "No actions found for cycles", "missing_action_names": missing_actions, "missing_object_names": missing_objects}
    valid_modes = {"NONE", "REPEAT", "REPEAT_OFFSET", "MIRROR"}
    mode_before = str(mode_before or "NONE").upper()
    mode_after = str(mode_after or "REPEAT").upper()
    if mode_before not in valid_modes:
        mode_before = "NONE"
    if mode_after not in valid_modes:
        mode_after = "REPEAT"
    cycles_plan = []
    for action in actions:
        fcurves_to_change = []
        for fcurve in live_preview._iter_action_fcurves(action):
            existing = [modifier for modifier in list(fcurve.modifiers) if modifier.type == "CYCLES"]
            if existing and not replace_existing:
                continue
            fcurves_to_change.append((fcurve, existing))
        if fcurves_to_change:
            cycles_plan.append((action, fcurves_to_change))
    if not cycles_plan:
        return {
            "ok": False,
            "message": "No f-curves available for cycles update",
            "actions": [],
            "missing_action_names": missing_actions,
            "missing_object_names": missing_objects,
        }
    transaction = live_preview.begin(label, context)
    changed = []
    for action, fcurves_to_change in cycles_plan:
        live_preview._record_action_edit(action)
        fcurve_count = 0
        for fcurve, existing in fcurves_to_change:
            for modifier in existing:
                fcurve.modifiers.remove(modifier)
            modifier = fcurve.modifiers.new(type="CYCLES")
            modifier.mode_before = mode_before
            modifier.mode_after = mode_after
            fcurve_count += 1
        if fcurve_count:
            changed.append({"action": action.name, "fcurves": fcurve_count})
    transaction["applied_steps"].append(
        {"type": "add_action_cycles", "label": label, "actions": changed, "mode_before": mode_before, "mode_after": mode_after}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": bool(changed),
        "message": f"Added cycles to {len(changed)} action(s)",
        "actions": changed,
        "missing_action_names": missing_actions,
        "missing_object_names": missing_objects,
        "transaction_id": transaction["id"],
    }

def _data_collection_for_object(obj):
    if obj.type == "CAMERA":
        return "cameras"
    if obj.type == "LIGHT":
        return "lights"
    if obj.type == "MESH":
        return "meshes"
    if obj.type in {"CURVE", "FONT"}:
        return "curves"
    if obj.type == "ARMATURE":
        return "armatures"
    return ""

def clear_animation(
    context,
    *,
    object_names=None,
    selected_only=True,
    include_object_animation=True,
    include_data_animation=True,
    include_shape_key_animation=True,
    include_material_animation=False,
    label="Clear animation",
):
    names = [str(name) for name in object_names or [] if str(name).strip()]
    if names:
        objects = [bpy.data.objects.get(name) for name in names]
        missing = [name for name, obj in zip(names, objects) if obj is None]
        objects = [obj for obj in objects if obj]
    elif selected_only:
        objects = list(context.selected_objects)
        missing = []
    elif context.active_object:
        objects = [context.active_object]
        missing = []
    else:
        objects = []
        missing = []
    if not objects:
        return {"ok": False, "message": "No objects found for animation clearing", "missing_object_names": missing}
    has_clearable_animation = False
    for obj in objects:
        if include_object_animation and obj.animation_data:
            has_clearable_animation = True
            break
        if include_data_animation and getattr(obj, "data", None) and obj.data.animation_data:
            has_clearable_animation = True
            break
        if include_shape_key_animation and obj.type == "MESH" and obj.data and obj.data.shape_keys and obj.data.shape_keys.animation_data:
            has_clearable_animation = True
            break
        if include_material_animation:
            for slot in obj.material_slots:
                material = slot.material
                if not material:
                    continue
                material_tree = blender_compat.node_tree(material)
                if material.animation_data or (material_tree and material_tree.animation_data):
                    has_clearable_animation = True
                    break
        if has_clearable_animation:
            break
    if not has_clearable_animation:
        return {"ok": False, "message": "No animation found to clear", "cleared": [], "missing_object_names": missing}

    transaction = live_preview.begin(label, context)
    cleared = []
    for obj in objects:
        if include_object_animation and obj.animation_data:
            live_preview._record_object_animation(obj)
            obj.animation_data_clear()
            cleared.append({"object": obj.name, "target": "object"})
        if include_data_animation and getattr(obj, "data", None) and obj.data.animation_data:
            collection = _data_collection_for_object(obj)
            if collection:
                live_preview._record_id_animation(obj.data, collection)
                obj.data.animation_data_clear()
                cleared.append({"object": obj.name, "target": "data"})
        if include_shape_key_animation and obj.type == "MESH" and obj.data and obj.data.shape_keys and obj.data.shape_keys.animation_data:
            _record_shape_keys(obj)
            obj.data.shape_keys.animation_data_clear()
            cleared.append({"object": obj.name, "target": "shape_keys"})
        if include_material_animation:
            for slot in obj.material_slots:
                material = slot.material
                if not material:
                    continue
                if material.animation_data:
                    live_preview._record_id_animation(material, "materials")
                    material.animation_data_clear()
                    cleared.append({"object": obj.name, "target": f"material:{material.name}"})
                material_tree = blender_compat.node_tree(material)
                if material_tree and material_tree.animation_data:
                    _record_material_node_tree_animation(material)
                    material_tree.animation_data_clear()
                    cleared.append({"object": obj.name, "target": f"material_node_tree:{material.name}"})
    transaction["applied_steps"].append({"type": "clear_animation", "label": label, "cleared": cleared})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Cleared {len(cleared)} animation target(s)",
        "cleared": cleared,
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }

def set_animation_preview_range(
    context,
    *,
    frame_start,
    frame_end,
    current_frame=None,
    use_preview_range=True,
    label="Set animation preview range",
):
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Preview range")
    if error:
        return error
    scene = context.scene
    transaction = live_preview.begin(label, context)
    live_preview._record_scene_playback(scene)
    scene.use_preview_range = bool(use_preview_range)
    scene.frame_preview_start = frame_start
    scene.frame_preview_end = frame_end
    if current_frame is not None:
        scene.frame_set(int(current_frame))
    transaction["applied_steps"].append(
        {"type": "set_animation_preview_range", "label": label, "frame_start": frame_start, "frame_end": frame_end, "use_preview_range": bool(use_preview_range)}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Set preview range to {frame_start}-{frame_end}", "transaction_id": transaction["id"]}

def create_turntable_animation(
    context,
    *,
    object_name="",
    frame_start,
    frame_end,
    axis="Z",
    revolutions=1.0,
    add_cycles=False,
    label="Create turntable animation",
):
    obj = bpy.data.objects.get(object_name) if object_name else context.active_object
    if obj is None:
        return {"ok": False, "message": "Object not found for turntable animation"}
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Turntable animation")
    if error:
        return error
    axis_index, axis = _axis_index(axis)
    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, frame_end)
    live_preview._record_object_transform(obj)
    action = live_preview._assign_preview_action(obj)
    base_rotation = [float(value) for value in obj.rotation_euler]
    obj.rotation_euler = base_rotation
    obj.keyframe_insert(data_path="rotation_euler", frame=frame_start)
    end_rotation = list(base_rotation)
    end_rotation[axis_index] += math.tau * float(revolutions)
    obj.rotation_euler = end_rotation
    obj.keyframe_insert(data_path="rotation_euler", frame=frame_end)
    _set_action_interpolation(action, "LINEAR")
    if add_cycles:
        live_preview._record_action_edit(action)
        for fcurve in live_preview._iter_action_fcurves(action):
            modifier = fcurve.modifiers.new(type="CYCLES")
            modifier.mode_before = "NONE"
            modifier.mode_after = "REPEAT"
    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {"type": "create_turntable_animation", "label": label, "object": obj.name, "axis": axis, "revolutions": float(revolutions)}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Created turntable animation for {obj.name}", "object": obj.name, "action": action.name, "transaction_id": transaction["id"]}

def create_pulse_animation(
    context,
    *,
    object_name="",
    frame_start,
    frame_end,
    scale_factor=1.15,
    emission_strength_end=None,
    label="Create pulse animation",
):
    obj = bpy.data.objects.get(object_name) if object_name else context.active_object
    if obj is None:
        return {"ok": False, "message": "Object not found for pulse animation"}
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Pulse animation")
    if error:
        return error
    frame_mid = int(round((frame_start + frame_end) / 2))
    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, frame_end)
    live_preview._record_object_transform(obj)
    action = live_preview._assign_preview_action(obj)
    base_scale = [float(value) for value in obj.scale]
    obj.scale = base_scale
    obj.keyframe_insert(data_path="scale", frame=frame_start)
    obj.scale = [value * float(scale_factor) for value in base_scale]
    obj.keyframe_insert(data_path="scale", frame=frame_mid)
    obj.scale = base_scale
    obj.keyframe_insert(data_path="scale", frame=frame_end)
    _set_action_interpolation(action, "SINE")
    material_action = None
    if emission_strength_end is not None:
        material_result = animate_material_property(
            context,
            object_name=obj.name,
            property_name="emission_strength",
            frame_start=frame_start,
            frame_end=frame_mid,
            value_start=0.0,
            value_end=float(emission_strength_end),
            label=label,
        )
        material_action = material_result.get("action") if material_result.get("ok") else None
    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {"type": "create_pulse_animation", "label": label, "object": obj.name, "scale_factor": float(scale_factor), "material_action": material_action}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Created pulse animation for {obj.name}", "object": obj.name, "action": action.name, "material_action": material_action, "transaction_id": transaction["id"]}

def create_reveal_animation(
    context,
    *,
    object_name="",
    frame_start,
    frame_end,
    scale_start=0.01,
    scale_end=1.0,
    fade_material=True,
    label="Create reveal animation",
):
    obj = bpy.data.objects.get(object_name) if object_name else context.active_object
    if obj is None:
        return {"ok": False, "message": "Object not found for reveal animation"}
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Reveal animation")
    if error:
        return error
    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, frame_end)
    live_preview._record_object_transform(obj)
    action = live_preview._assign_preview_action(obj)
    base_scale = [float(value) for value in obj.scale]
    obj.scale = [value * float(scale_start) for value in base_scale]
    obj.keyframe_insert(data_path="scale", frame=frame_start)
    obj.scale = [value * float(scale_end) for value in base_scale]
    obj.keyframe_insert(data_path="scale", frame=frame_end)
    _set_action_interpolation(action, "BEZIER")
    material_action = None
    if fade_material and obj.type == "MESH":
        material_result = animate_material_property(
            context,
            object_name=obj.name,
            property_name="alpha",
            frame_start=frame_start,
            frame_end=frame_end,
            value_start=0.0,
            value_end=1.0,
            label=label,
        )
        material_action = material_result.get("action") if material_result.get("ok") else None
    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {"type": "create_reveal_animation", "label": label, "object": obj.name, "material_action": material_action}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Created reveal animation for {obj.name}", "object": obj.name, "action": action.name, "material_action": material_action, "transaction_id": transaction["id"]}

def create_staggered_motion(
    context,
    *,
    object_names=None,
    frame_start,
    duration=24,
    frame_step=6,
    location_delta=(0.0, 0.0, 1.0),
    interpolation="BEZIER",
    label="Create staggered motion",
):
    names = [str(name) for name in object_names or [] if str(name).strip()]
    if names:
        objects = [bpy.data.objects.get(name) for name in names]
        missing = [name for name, obj in zip(names, objects) if obj is None]
        objects = [obj for obj in objects if obj]
    else:
        objects = list(context.selected_objects)
        missing = []
    if not objects:
        return {"ok": False, "message": "No objects found for staggered motion", "missing_object_names": missing}
    frame_start = int(frame_start)
    duration = max(1, int(duration))
    frame_step = max(0, int(frame_step))
    delta = _coerce_vector(location_delta, (0.0, 0.0, 1.0))
    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    end_frame = frame_start + (len(objects) - 1) * frame_step + duration
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, end_frame)
    animated = []
    for index, obj in enumerate(objects):
        start = frame_start + index * frame_step
        end = start + duration
        live_preview._record_object_transform(obj)
        action = live_preview._assign_preview_action(obj)
        start_location = [float(value) for value in obj.location]
        end_location = [start_location[0] + delta[0], start_location[1] + delta[1], start_location[2] + delta[2]]
        obj.location = start_location
        obj.keyframe_insert(data_path="location", frame=start)
        obj.location = end_location
        obj.keyframe_insert(data_path="location", frame=end)
        _set_action_interpolation(action, interpolation)
        animated.append({"object": obj.name, "action": action.name, "frame_start": start, "frame_end": end})
    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {"type": "create_staggered_motion", "label": label, "objects": animated, "location_delta": list(delta)}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Created staggered motion for {len(animated)} object(s)", "objects": animated, "missing_object_names": missing, "transaction_id": transaction["id"]}

TRANSFORM_PATHS = ("location", "rotation_euler", "scale")

def _normalize_transform_paths(paths=None, *, action=None):
    normalized = []
    for path in paths or []:
        key = TRANSFORM_PATH_ALIASES.get(str(path).strip().lower())
        if key and key not in normalized:
            normalized.append(key)
    if normalized:
        return normalized
    if action:
        for fcurve in live_preview._iter_action_fcurves(action):
            if fcurve.data_path in TRANSFORM_PATHS and fcurve.data_path not in normalized:
                normalized.append(fcurve.data_path)
    return normalized

def _fcurves_for_path(action, path):
    result = {}
    if not action:
        return result
    for fcurve in live_preview._iter_action_fcurves(action):
        if fcurve.data_path == path:
            result[int(fcurve.array_index)] = fcurve
    return result

def _evaluate_transform_path(action, path, frame, fallback):
    fallback_values = _coerce_vector(fallback, fallback)
    fcurves = _fcurves_for_path(action, path)
    values = []
    for index, fallback_value in enumerate(fallback_values):
        fcurve = fcurves.get(index)
        values.append(float(fcurve.evaluate(frame)) if fcurve else float(fallback_value))
    return tuple(values)

def _action_keyframes_for_paths(action, paths):
    frames = set()
    for fcurve in live_preview._iter_action_fcurves(action) if action else []:
        if fcurve.data_path not in paths:
            continue
        frames.update(int(round(point.co.x)) for point in fcurve.keyframe_points)
    return sorted(frames)

def _surrounding_frames(action, frame, paths):
    frames = _action_keyframes_for_paths(action, paths)
    previous = [item for item in frames if item < frame]
    following = [item for item in frames if item > frame]
    return (max(previous) if previous else None, min(following) if following else None)

def _set_transform_path(obj, path, values):
    if path == "location":
        obj.location = values
    elif path == "rotation_euler":
        obj.rotation_euler = values
    elif path == "scale":
        obj.scale = values

def _transform_fallback(obj, path):
    if path == "location":
        return obj.location
    if path == "rotation_euler":
        return obj.rotation_euler
    return obj.scale

def add_breakdown_pose(
    context,
    *,
    object_names=None,
    frame=None,
    previous_frame=None,
    next_frame=None,
    factor=0.5,
    location=None,
    rotation=None,
    scale=None,
    paths=None,
    selected_only=False,
    interpolation="CONSTANT",
    label="Add breakdown pose",
):
    frame = int(frame if frame is not None else context.scene.frame_current)
    factor = max(0.0, min(1.0, float(factor)))
    objects, missing = _resolve_named_or_selected_objects(context, object_names, selected_only=selected_only)
    if not objects:
        return {"ok": False, "message": "No objects found for breakdown pose", "missing_object_names": missing}

    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame)
    scene.frame_end = max(scene.frame_end, frame)
    interpolation = str(interpolation or "CONSTANT").upper()
    keyed = []
    for obj in objects:
        live_preview._record_object_transform(obj)
        action, created_action = _prepare_transform_action_for_edit(obj)
        explicit = {}
        if location is not None:
            explicit["location"] = _coerce_vector(location, obj.location)
        if rotation is not None:
            explicit["rotation_euler"] = _coerce_vector(rotation, obj.rotation_euler)
        if scale is not None:
            explicit["scale"] = _coerce_vector(scale, obj.scale)
        active_paths = _normalize_transform_paths(paths, action=action)
        if explicit:
            active_paths = [path for path in TRANSFORM_PATHS if path in explicit or path in active_paths]
        if not active_paths:
            active_paths = list(explicit)
        if not active_paths:
            return {"ok": False, "message": "Breakdown pose needs existing transform animation or explicit location, rotation, or scale values"}
        prev_frame = int(previous_frame) if previous_frame is not None else None
        next_item = int(next_frame) if next_frame is not None else None
        if prev_frame is None or next_item is None:
            inferred_prev, inferred_next = _surrounding_frames(action, frame, active_paths)
            prev_frame = prev_frame if prev_frame is not None else inferred_prev
            next_item = next_item if next_item is not None else inferred_next
        keyed_paths = []
        values_by_path = {}
        for path in active_paths:
            fallback = _transform_fallback(obj, path)
            if path in explicit:
                values = explicit[path]
            elif prev_frame is not None and next_item is not None and next_item != prev_frame:
                before = _evaluate_transform_path(action, path, prev_frame, fallback)
                after = _evaluate_transform_path(action, path, next_item, fallback)
                values = tuple(before[index] + (after[index] - before[index]) * factor for index in range(3))
            else:
                values = _evaluate_transform_path(action, path, frame, fallback)
            _set_transform_path(obj, path, values)
            obj.keyframe_insert(data_path=path, frame=frame)
            keyed_paths.append(path)
            values_by_path[path] = [round(float(value), 6) for value in values]
        _set_action_interpolation(action, interpolation)
        keyed.append(
            {
                "object": obj.name,
                "action": action.name,
                "created_action": created_action,
                "frame": frame,
                "paths": keyed_paths,
                "previous_frame": prev_frame,
                "next_frame": next_item,
                "factor": factor,
                "values": values_by_path,
            }
        )
    scene.frame_set(frame)
    transaction["applied_steps"].append({"type": "add_breakdown_pose", "label": label, "objects": keyed, "frame": frame})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Added breakdown pose at frame {frame} for {len(keyed)} object(s)",
        "objects": keyed,
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }

def set_pose_hold(
    context,
    *,
    object_names=None,
    frame=None,
    hold_frames=4,
    paths=None,
    selected_only=False,
    interpolation="CONSTANT",
    label="Set pose hold",
):
    frame = int(frame if frame is not None else context.scene.frame_current)
    hold_frames = max(1, int(hold_frames or 1))
    hold_frame = frame + hold_frames
    objects, missing = _resolve_named_or_selected_objects(context, object_names, selected_only=selected_only)
    if not objects:
        return {"ok": False, "message": "No objects found for pose hold", "missing_object_names": missing}

    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame)
    scene.frame_end = max(scene.frame_end, hold_frame)
    interpolation = str(interpolation or "CONSTANT").upper()
    held = []
    for obj in objects:
        live_preview._record_object_transform(obj)
        action, created_action = _prepare_transform_action_for_edit(obj)
        active_paths = _normalize_transform_paths(paths, action=action) or list(TRANSFORM_PATHS)
        keyed_paths = []
        values_by_path = {}
        for path in active_paths:
            values = _evaluate_transform_path(action, path, frame, _transform_fallback(obj, path))
            for key_frame in (frame, hold_frame):
                _set_transform_path(obj, path, values)
                obj.keyframe_insert(data_path=path, frame=key_frame)
            keyed_paths.append(path)
            values_by_path[path] = [round(float(value), 6) for value in values]
        _set_action_interpolation(action, interpolation)
        held.append(
            {
                "object": obj.name,
                "action": action.name,
                "created_action": created_action,
                "frame": frame,
                "hold_frame": hold_frame,
                "hold_frames": hold_frames,
                "paths": keyed_paths,
                "values": values_by_path,
            }
        )
    scene.frame_set(frame)
    transaction["applied_steps"].append({"type": "set_pose_hold", "label": label, "objects": held, "frame": frame, "hold_frame": hold_frame})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Set {hold_frames}-frame hold from frame {frame} for {len(held)} object(s)",
        "objects": held,
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }

def create_motion_arc(
    context,
    *,
    object_names=None,
    frame_start=None,
    frame_end=None,
    sample_step=4,
    selected_only=False,
    name_prefix="Agent Bridge Motion Arc",
    bevel_depth=0.015,
    color=(0.08, 0.45, 1.0, 1.0),
    label="Create motion arc",
):
    objects, missing = _resolve_named_or_selected_objects(context, object_names, selected_only=selected_only)
    if not objects:
        return {"ok": False, "message": "No objects found for motion arc", "missing_object_names": missing}
    scene = context.scene
    frame_start = int(frame_start if frame_start is not None else scene.frame_start)
    frame_end = int(frame_end if frame_end is not None else scene.frame_end)
    if frame_end < frame_start:
        frame_start, frame_end = frame_end, frame_start
    sample_step = max(1, int(sample_step or 1))
    frames = list(range(frame_start, frame_end + 1, sample_step))
    if frames[-1] != frame_end:
        frames.append(frame_end)
    if len(frames) < 2:
        frames = [frame_start, frame_start + 1]

    transaction = live_preview.begin(label, context)
    material = _material_for_color(f"{name_prefix} Material", _coerce_color(color, (0.08, 0.45, 1.0, 1.0)))
    arcs = []
    for obj in objects:
        action = obj.animation_data.action if obj.animation_data and obj.animation_data.action else None
        points = [
            _evaluate_transform_path(action, "location", frame, obj.location)
            for frame in frames
        ]
        curve = bpy.data.curves.new(f"{name_prefix} {obj.name} Data", "CURVE")
        curve.dimensions = "3D"
        curve.resolution_u = 2
        curve.bevel_depth = max(0.0, float(bevel_depth))
        spline = curve.splines.new("POLY")
        spline.points.add(len(points) - 1)
        for point, coords in zip(spline.points, points):
            point.co = (float(coords[0]), float(coords[1]), float(coords[2]), 1.0)
        arc_obj = bpy.data.objects.new(f"{name_prefix} {obj.name}", curve)
        context.scene.collection.objects.link(arc_obj)
        curve.materials.append(material)
        live_preview._record_created_id("curve", curve.name)
        live_preview._record_created_id("object", arc_obj.name)
        arcs.append(
            {
                "source_object": obj.name,
                "arc_object": arc_obj.name,
                "curve": curve.name,
                "frame_start": frame_start,
                "frame_end": frame_end,
                "sample_step": sample_step,
                "sample_count": len(points),
                "points": [[round(float(component), 6) for component in coords] for coords in points],
            }
        )
    transaction["applied_steps"].append({"type": "create_motion_arc", "label": label, "arcs": arcs})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Created {len(arcs)} motion arc(s)",
        "arcs": arcs,
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }

def block_key_poses(
    context,
    *,
    object_names=None,
    poses=None,
    selected_only=False,
    interpolation="CONSTANT",
    label="Block key poses",
):
    names = [str(name) for name in object_names or [] if str(name).strip()]
    if names:
        objects = [bpy.data.objects.get(name) for name in names]
        missing = [name for name, obj in zip(names, objects) if obj is None]
        objects = [obj for obj in objects if obj]
    elif selected_only or context.selected_objects:
        objects = list(context.selected_objects)
        missing = []
    else:
        objects = [context.active_object] if context.active_object else []
        missing = []
    objects = [obj for obj in objects if obj]
    if not objects:
        return {"ok": False, "message": "No objects found for blocking key poses", "missing_object_names": missing}
    pose_items = [pose for pose in poses or [] if isinstance(pose, dict)]
    if not pose_items:
        return {"ok": False, "message": "At least one key pose is required for blocking"}
    transform_paths = set()
    for pose in pose_items:
        if pose.get("location") is not None:
            transform_paths.add("location")
        if pose.get("rotation") is not None or pose.get("rotation_euler") is not None:
            transform_paths.add("rotation_euler")
        if pose.get("scale") is not None:
            transform_paths.add("scale")
    if not transform_paths:
        return {"ok": False, "message": "Each blocking pass needs at least one location, rotation, or scale pose value"}
    frames = []
    for pose in pose_items:
        frame = int(pose.get("frame", context.scene.frame_current))
        frames.append(frame)
        hold_frames = max(0, int(pose.get("hold_frames", 0) or 0))
        if hold_frames:
            frames.append(frame + hold_frames)
    frame_start = min(frames)
    frame_end = max(frames)
    interpolation = str(interpolation or "CONSTANT").upper()
    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, frame_end)
    blocked = []
    for obj in objects:
        live_preview._record_object_transform(obj)
        action = live_preview._assign_preview_action(obj)
        base_location = [float(value) for value in obj.location]
        base_rotation = [float(value) for value in obj.rotation_euler]
        base_scale = [float(value) for value in obj.scale]
        keyed_frames = []
        for pose in sorted(pose_items, key=lambda item: int(item.get("frame", frame_start))):
            frame = int(pose.get("frame", frame_start))
            hold_frames = max(0, int(pose.get("hold_frames", 0) or 0))
            location = _coerce_vector(pose.get("location"), base_location) if pose.get("location") is not None else None
            rotation_value = pose.get("rotation_euler", pose.get("rotation"))
            rotation = _coerce_vector(rotation_value, base_rotation) if rotation_value is not None else None
            scale = _coerce_vector(pose.get("scale"), base_scale) if pose.get("scale") is not None else None
            for key_frame in (frame, frame + hold_frames) if hold_frames else (frame,):
                if location is not None:
                    obj.location = location
                    obj.keyframe_insert(data_path="location", frame=key_frame)
                if rotation is not None:
                    obj.rotation_euler = rotation
                    obj.keyframe_insert(data_path="rotation_euler", frame=key_frame)
                if scale is not None:
                    obj.scale = scale
                    obj.keyframe_insert(data_path="scale", frame=key_frame)
                keyed_frames.append(int(key_frame))
        _set_action_interpolation(action, interpolation)
        blocked.append(
            {
                "object": obj.name,
                "action": action.name,
                "frames": sorted(set(keyed_frames)),
                "paths": sorted(transform_paths),
            }
        )
    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {
            "type": "block_key_poses",
            "label": label,
            "objects": blocked,
            "frame_start": frame_start,
            "frame_end": frame_end,
            "pose_count": len(pose_items),
            "interpolation": interpolation,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Blocked {len(pose_items)} key pose(s) for {len(blocked)} object(s)",
        "objects": blocked,
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }

def create_camera_dolly_animation(
    context,
    *,
    camera_name="",
    target_name="",
    frame_start=1,
    frame_end=96,
    start_location=None,
    end_location=None,
    lens_start=None,
    lens_end=None,
    interpolation="BEZIER",
    label="Create camera dolly animation",
):
    scene = context.scene
    camera = bpy.data.objects.get(str(camera_name or "")) if camera_name else scene.camera
    if camera is not None and camera.type != "CAMERA":
        return {"ok": False, "message": f"Object is not a camera: {camera.name}"}
    transaction = live_preview.begin(label, context)
    if camera is None:
        live_preview._record_scene_camera(scene)
        data = bpy.data.cameras.new("Agent Bridge Dolly Camera Data")
        camera = bpy.data.objects.new("Agent Bridge Dolly Camera", object_data=data)
        scene.collection.objects.link(camera)
        scene.camera = camera
        live_preview._record_created_id("object", camera.name)
        live_preview._record_created_id("camera", data.name)
    target = bpy.data.objects.get(str(target_name or "")) if target_name else None
    start = int(frame_start or scene.frame_start)
    end = int(frame_end or scene.frame_end)
    if end < start:
        start, end = end, start
    live_preview._record_scene_timeline(scene)
    live_preview._record_object_transform(camera)
    _record_camera_settings(camera)
    scene.frame_start = min(scene.frame_start, start)
    scene.frame_end = max(scene.frame_end, end)
    if start_location is not None:
        camera.location = _coerce_vector(start_location, camera.location)
    action = live_preview._assign_preview_action(camera)
    camera.keyframe_insert(data_path="location", frame=start)
    if target and not any(constraint.type == "TRACK_TO" and constraint.target == target for constraint in camera.constraints):
        constraint = camera.constraints.new(type="TRACK_TO")
        constraint.name = "Agent Bridge Dolly Track Target"
        constraint.track_axis = "TRACK_NEGATIVE_Z"
        constraint.up_axis = "UP_Y"
        constraint.target = target
        live_preview._record_created_constraint(camera, constraint)
    if end_location is None:
        base = Vector(camera.location)
        if target:
            direction = (Vector(target.location) - base)
            if direction.length > 0.0001:
                direction.normalize()
                end_location = tuple(base + direction * 2.0)
        if end_location is None:
            end_location = (camera.location.x, camera.location.y + 2.0, camera.location.z)
    camera.location = _coerce_vector(end_location, camera.location)
    camera.keyframe_insert(data_path="location", frame=end)
    _set_action_interpolation(action, interpolation)
    lens_action_name = ""
    if lens_start is not None or lens_end is not None:
        live_preview._record_id_animation(camera.data, "cameras")
        lens_action = bpy.data.actions.new(name=f"{camera.name} Agent Bridge Lens Preview Action")
        camera.data.animation_data_create().action = lens_action
        live_preview._record_created_id("action", lens_action.name)
        if lens_start is not None:
            camera.data.lens = max(1.0, min(1000.0, float(lens_start)))
        camera.data.keyframe_insert(data_path="lens", frame=start)
        if lens_end is not None:
            camera.data.lens = max(1.0, min(1000.0, float(lens_end)))
        camera.data.keyframe_insert(data_path="lens", frame=end)
        _set_action_interpolation(lens_action, interpolation)
        lens_action_name = lens_action.name
    transaction["applied_steps"].append(
        {
            "type": "create_camera_dolly_animation",
            "label": label,
            "camera": camera.name,
            "target": target.name if target else "",
            "frame_start": start,
            "frame_end": end,
            "action": action.name,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Created camera dolly animation for {camera.name}",
        "camera": camera.name,
        "target": target.name if target else "",
        "action": action.name,
        "lens_action": lens_action_name,
        "transaction_id": transaction["id"],
    }





def register():

    pass





def unregister():

    pass

