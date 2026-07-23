"""Advanced Blender helpers for scene editing."""



from __future__ import annotations


import bpy
from mathutils import Vector

from . import live_preview

from .advanced_support import (
    _axis_index,
    _coerce_color,
    _coerce_vector,
    _link_object_like_source,
    _resolve_edit_objects,
    _resolve_named_or_selected_objects,
)



EMPTY_DISPLAY_TYPES = {"PLAIN_AXES", "ARROWS", "SINGLE_ARROW", "CIRCLE", "CUBE", "SPHERE", "CONE", "IMAGE"}

OBJECT_DISPLAY_TYPES = {"TEXTURED", "SOLID", "WIRE", "BOUNDS"}

def _created_data_kind(obj):
    if obj.type == "MESH":
        return "mesh"
    if obj.type in {"CURVE", "FONT"}:
        return "curve"
    if obj.type == "CAMERA":
        return "camera"
    if obj.type == "LIGHT":
        return "light"
    if obj.type == "ARMATURE":
        return "armature"
    return ""

def create_empty(
    context,
    *,
    name="Agent Bridge Empty",
    location=(0.0, 0.0, 0.0),
    rotation=(0.0, 0.0, 0.0),
    scale=(1.0, 1.0, 1.0),
    empty_display_type="PLAIN_AXES",
    empty_display_size=1.0,
    select_new=True,
    label="Create empty",
):
    transaction = live_preview.begin(label, context)
    obj = bpy.data.objects.new(name or "Agent Bridge Empty", object_data=None)
    display_type = str(empty_display_type or "PLAIN_AXES").upper()
    obj.empty_display_type = display_type if display_type in EMPTY_DISPLAY_TYPES else "PLAIN_AXES"
    obj.empty_display_size = max(0.01, float(empty_display_size))
    obj.location = _coerce_vector(location, (0.0, 0.0, 0.0))
    obj.rotation_euler = _coerce_vector(rotation, (0.0, 0.0, 0.0))
    obj.scale = _coerce_vector(scale, (1.0, 1.0, 1.0))
    context.scene.collection.objects.link(obj)
    live_preview._record_created_id("object", obj.name)
    if select_new:
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        context.view_layer.objects.active = obj
    transaction["applied_steps"].append({"type": "create_empty", "label": label, "object": obj.name})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Created empty {obj.name}", "object": obj.name, "transaction_id": transaction["id"]}

def set_object_visibility(
    context,
    *,
    object_names=None,
    selected_only=True,
    hide_viewport=None,
    hide_render=None,
    hide_select=None,
    label="Set object visibility",
):
    if hide_viewport is None and hide_render is None and hide_select is None:
        return {"ok": False, "message": "At least one visibility flag is required"}
    objects, missing = _resolve_edit_objects(context, object_names=object_names, selected_only=selected_only)
    if not objects:
        return {"ok": False, "message": "No objects found for visibility update", "missing_object_names": missing}
    transaction = live_preview.begin(label, context)
    changed = []
    warnings = []
    for obj in objects:
        live_preview._record_object_visibility(obj)
        if hide_viewport is not None:
            value = bool(hide_viewport)
            obj.hide_viewport = value
            try:
                obj.hide_set(value)
            except Exception as exc:
                warnings.append(f"Could not set viewport hide state for {obj.name}: {type(exc).__name__}: {exc}")
        if hide_render is not None:
            obj.hide_render = bool(hide_render)
        if hide_select is not None:
            obj.hide_select = bool(hide_select)
        changed.append(obj.name)
    transaction["applied_steps"].append({"type": "set_object_visibility", "label": label, "objects": changed})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Updated visibility for {len(changed)} object(s)",
        "objects": changed,
        "missing_object_names": missing,
        "warnings": warnings,
        "transaction_id": transaction["id"],
    }

def set_object_display(
    context,
    *,
    object_names=None,
    selected_only=True,
    display_type="",
    show_name=None,
    show_wire=None,
    show_in_front=None,
    color=None,
    empty_display_type="",
    empty_display_size=None,
    label="Set object display",
):
    has_change = any(
        value is not None and value != ""
        for value in (display_type, show_name, show_wire, show_in_front, color, empty_display_type, empty_display_size)
    )
    if not has_change:
        return {"ok": False, "message": "At least one display setting is required"}
    objects, missing = _resolve_edit_objects(context, object_names=object_names, selected_only=selected_only)
    if not objects:
        return {"ok": False, "message": "No objects found for display update", "missing_object_names": missing}
    display_type = str(display_type or "").upper()
    empty_display_type = str(empty_display_type or "").upper()
    display_color = _coerce_color(color) if color is not None else None
    transaction = live_preview.begin(label, context)
    changed = []
    for obj in objects:
        live_preview._record_object_display(obj)
        if display_type:
            obj.display_type = display_type if display_type in OBJECT_DISPLAY_TYPES else "TEXTURED"
        if show_name is not None:
            obj.show_name = bool(show_name)
        if show_wire is not None and hasattr(obj, "show_wire"):
            obj.show_wire = bool(show_wire)
        if show_in_front is not None:
            obj.show_in_front = bool(show_in_front)
        if display_color is not None:
            obj.color = display_color
        if obj.type == "EMPTY":
            if empty_display_type:
                obj.empty_display_type = empty_display_type if empty_display_type in EMPTY_DISPLAY_TYPES else "PLAIN_AXES"
            if empty_display_size is not None:
                obj.empty_display_size = max(0.01, float(empty_display_size))
        changed.append(obj.name)
    transaction["applied_steps"].append({"type": "set_object_display", "label": label, "objects": changed})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Updated display settings for {len(changed)} object(s)", "objects": changed, "missing_object_names": missing, "transaction_id": transaction["id"]}

def duplicate_selected_objects(
    context,
    *,
    name_prefix="Agent Bridge Copy ",
    offset=(0.0, 0.0, 0.0),
    linked_data=False,
    copy_animation=False,
    select_new=True,
    label="Duplicate selected objects",
):
    selected = [obj for obj in context.selected_objects if obj]
    if not selected:
        return {"ok": False, "message": "No selected objects to duplicate"}
    transaction = live_preview.begin(label, context)
    offset = _coerce_vector(offset, (0.0, 0.0, 0.0))
    created = []
    if select_new:
        bpy.ops.object.select_all(action="DESELECT")
    for obj in selected:
        duplicate = obj.copy()
        duplicate.name = f"{name_prefix}{obj.name}" if name_prefix else f"{obj.name} Copy"
        if obj.data and not linked_data:
            duplicate.data = obj.data.copy()
            duplicate.data.name = f"{duplicate.name} Data"
        if duplicate.animation_data and not copy_animation:
            duplicate.animation_data_clear()
        duplicate.location.x += float(offset[0])
        duplicate.location.y += float(offset[1])
        duplicate.location.z += float(offset[2])
        _link_object_like_source(context, obj, duplicate)
        live_preview._record_created_id("object", duplicate.name)
        data_kind = _created_data_kind(duplicate)
        if data_kind and duplicate.data and duplicate.data is not obj.data:
            live_preview._record_created_id(data_kind, duplicate.data.name)
        if select_new:
            duplicate.select_set(True)
            context.view_layer.objects.active = duplicate
        created.append(duplicate.name)
    transaction["applied_steps"].append(
        {
            "type": "duplicate_selected_objects",
            "label": label,
            "source_objects": [obj.name for obj in selected],
            "created_objects": created,
            "linked_data": bool(linked_data),
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Duplicated {len(created)} object(s)",
        "objects": created,
        "transaction_id": transaction["id"],
    }

def parent_selected_to_empty(
    context,
    *,
    object_names=None,
    selected_only=True,
    name="Agent Bridge Parent",
    location=None,
    empty_display_type="PLAIN_AXES",
    keep_transform=True,
    label="Parent selected to empty",
):
    objects, missing = _resolve_named_or_selected_objects(
        context,
        object_names,
        selected_only=selected_only,
        fallback_active=False,
    )
    selected = []
    seen = set()
    for obj in objects:
        if obj.name in seen:
            continue
        seen.add(obj.name)
        selected.append(obj)
    if not selected:
        result = {"ok": False, "message": "No target objects to parent" if object_names else "No selected objects to parent"}
        if missing:
            result["missing_object_names"] = missing
        return result
    transaction = live_preview.begin(label, context)
    if location is None:
        center = Vector((0.0, 0.0, 0.0))
        for obj in selected:
            center += obj.matrix_world.translation
        center /= len(selected)
        location = center
    location = _coerce_vector(location, (0.0, 0.0, 0.0))
    empty = bpy.data.objects.new(name or "Agent Bridge Parent", object_data=None)
    empty.empty_display_type = empty_display_type if empty_display_type in {"PLAIN_AXES", "ARROWS", "CUBE", "SPHERE"} else "PLAIN_AXES"
    empty.empty_display_size = 1.0
    empty.location = location
    context.scene.collection.objects.link(empty)
    live_preview._record_created_id("object", empty.name)
    for obj in selected:
        live_preview._record_object_parent(obj)
        live_preview._record_object_transform(obj)
        world_matrix = obj.matrix_world.copy()
        obj.parent = empty
        if keep_transform:
            obj.matrix_parent_inverse = empty.matrix_world.inverted()
            obj.matrix_world = world_matrix
    bpy.ops.object.select_all(action="DESELECT")
    empty.select_set(True)
    context.view_layer.objects.active = empty
    transaction["applied_steps"].append(
        {
            "type": "parent_selected_to_empty",
            "label": label,
            "empty": empty.name,
            "children": [obj.name for obj in selected],
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Parented {len(selected)} object(s) to {empty.name}",
        "empty": empty.name,
        "children": [obj.name for obj in selected],
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }

def align_selected_objects(context, *, axis="Z", mode="ACTIVE", value=None, label="Align selected objects"):
    selected = [obj for obj in context.selected_objects if obj]
    if len(selected) < 2:
        return {"ok": False, "message": "Select at least two objects to align"}
    axis_index, axis = _axis_index(axis)
    mode = str(mode or "ACTIVE").upper()
    if mode == "VALUE":
        if value is None:
            return {"ok": False, "message": "Alignment mode VALUE requires a numeric value"}
        target = float(value)
    elif mode == "MIN":
        target = min(float(obj.location[axis_index]) for obj in selected)
    elif mode == "MAX":
        target = max(float(obj.location[axis_index]) for obj in selected)
    elif mode == "CENTER":
        target = sum(float(obj.location[axis_index]) for obj in selected) / len(selected)
    else:
        active = context.view_layer.objects.active if context.view_layer else None
        if active is None:
            return {"ok": False, "message": "Alignment mode ACTIVE requires an active object"}
        target = float(active.location[axis_index])
        mode = "ACTIVE"

    transaction = live_preview.begin(label, context)
    for obj in selected:
        live_preview._record_object_transform(obj)
        obj.location[axis_index] = target
    transaction["applied_steps"].append(
        {
            "type": "align_selected_objects",
            "label": label,
            "objects": [obj.name for obj in selected],
            "axis": axis,
            "mode": mode,
            "value": target,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Aligned {len(selected)} object(s) on {axis}",
        "objects": [obj.name for obj in selected],
        "axis": axis,
        "value": target,
        "transaction_id": transaction["id"],
    }

def distribute_selected_objects(
    context,
    *,
    axis="X",
    start=None,
    end=None,
    label="Distribute selected objects",
):
    selected = [obj for obj in context.selected_objects if obj]
    if len(selected) < 2:
        return {"ok": False, "message": "Select at least two objects to distribute"}
    axis_index, axis = _axis_index(axis)
    ordered = sorted(selected, key=lambda obj: (float(obj.location[axis_index]), obj.name))
    if start is None:
        start = float(ordered[0].location[axis_index])
    if end is None:
        end = float(ordered[-1].location[axis_index])
    start = float(start)
    end = float(end)
    transaction = live_preview.begin(label, context)
    positions = {}
    for index, obj in enumerate(ordered):
        factor = index / max(1, len(ordered) - 1)
        position = start + (end - start) * factor
        live_preview._record_object_transform(obj)
        obj.location[axis_index] = position
        positions[obj.name] = position
    transaction["applied_steps"].append(
        {
            "type": "distribute_selected_objects",
            "label": label,
            "objects": [obj.name for obj in ordered],
            "axis": axis,
            "start": start,
            "end": end,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Distributed {len(ordered)} object(s) on {axis}",
        "objects": [obj.name for obj in ordered],
        "positions": positions,
        "transaction_id": transaction["id"],
    }





def register():

    pass





def unregister():

    pass

