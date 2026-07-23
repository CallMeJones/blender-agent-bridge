"""Blender-only handlers for the scene_editing domain."""

from __future__ import annotations

import bpy

from .. import advanced_helpers, live_preview
from ..handler_runtime import _float_list, _name_list, _optional_float_list


def select_objects(context, args):
    names = _name_list(args.get("object_names"))
    extend = bool(args.get("extend", False))
    active_name = str(args.get("active_object_name") or "").strip()
    if not names and active_name:
        names = [active_name]
    if not names:
        return {"ok": False, "message": "No object names were provided"}
    if not extend:
        bpy.ops.object.select_all(action="DESELECT")
    selected = []
    missing = []
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None:
            missing.append(name)
            continue
        obj.select_set(True)
        selected.append(obj.name)
    active = bpy.data.objects.get(active_name) if active_name else None
    if active is None and selected:
        active = bpy.data.objects.get(selected[0])
    if active:
        active.select_set(True)
        context.view_layer.objects.active = active
    live_preview.redraw(context)
    state = getattr(context.scene, "claude_blender", None)
    if state:
        state.status = f"Selected {len(selected)} object(s)"
    return {
        "ok": bool(selected),
        "message": f"Selected {len(selected)} object(s)",
        "selected_objects": selected,
        "active_object": active.name if active else None,
        "missing_object_names": missing,
    }


def set_current_frame(context, args):
    frame = int(args.get("frame", context.scene.frame_current))
    context.scene.frame_set(frame)
    live_preview.redraw(context)
    state = getattr(context.scene, "claude_blender", None)
    if state:
        state.status = f"Current frame: {context.scene.frame_current}"
    return {
        "ok": True,
        "message": f"Set current frame to {context.scene.frame_current}",
        "frame_current": int(context.scene.frame_current),
    }


def set_selected_location_delta(context, args):
    delta = _float_list(args.get("delta"), 3, (0.0, 0.0, 0.0))
    return live_preview.apply_location_delta(
        context,
        delta,
        label=args.get("label", "Move selected objects"),
    )


def set_selected_transform(context, args):
    return live_preview.set_selected_transform(
        context,
        location=_optional_float_list(args.get("location"), 3, (0.0, 0.0, 0.0)),
        rotation=_optional_float_list(args.get("rotation"), 3, (0.0, 0.0, 0.0)),
        scale=_optional_float_list(args.get("scale"), 3, (1.0, 1.0, 1.0)),
        label=args.get("label", "Set selected transform"),
    )


def create_primitive(context, args):
    return live_preview.create_primitive(
        context,
        primitive_type=str(args.get("primitive_type") or "CUBE"),
        name=str(args.get("name") or "Agent Bridge Object"),
        location=_float_list(args.get("location"), 3, (0.0, 0.0, 0.0)),
        rotation=_float_list(args.get("rotation"), 3, (0.0, 0.0, 0.0)),
        scale=_float_list(args.get("scale"), 3, (1.0, 1.0, 1.0)),
        label=args.get("label", "Create primitive"),
    )


def create_collection(context, args):
    return live_preview.create_collection(
        context,
        name=str(args.get("name") or "Agent Bridge Collection"),
        label=args.get("label", "Create collection"),
    )


def link_selected_to_collection(context, args):
    return live_preview.link_selected_to_collection(
        context,
        collection_name=str(args.get("collection_name") or "Agent Bridge Collection"),
        label=args.get("label", "Link selected to collection"),
    )


def add_modifier_to_selected(context, args):
    return live_preview.add_modifier_to_selected(
        context,
        modifier_type=str(args.get("modifier_type") or "BEVEL"),
        name=str(args.get("name") or ""),
        amount=float(args.get("amount", 0.1)),
        segments=int(args.get("segments", 2)),
        levels=int(args.get("levels", 1)),
        count=int(args.get("count", 3)),
        relative_offset=_float_list(args.get("relative_offset"), 3, (1.2, 0.0, 0.0)),
        label=args.get("label", "Add modifier"),
    )


def create_empty(context, args):
    return advanced_helpers.create_empty(
        context,
        name=str(args.get("name") or "Agent Bridge Empty"),
        location=_float_list(args.get("location"), 3, (0.0, 0.0, 0.0)),
        rotation=_float_list(args.get("rotation"), 3, (0.0, 0.0, 0.0)),
        scale=_float_list(args.get("scale"), 3, (1.0, 1.0, 1.0)),
        empty_display_type=str(args.get("empty_display_type") or "PLAIN_AXES"),
        empty_display_size=float(args.get("empty_display_size", 1.0)),
        select_new=bool(args.get("select_new", True)),
        label=args.get("label", "Create empty"),
    )


def set_object_visibility(context, args):
    return advanced_helpers.set_object_visibility(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        hide_viewport=args.get("hide_viewport"),
        hide_render=args.get("hide_render"),
        hide_select=args.get("hide_select"),
        label=args.get("label", "Set object visibility"),
    )


def set_object_display(context, args):
    return advanced_helpers.set_object_display(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        display_type=str(args.get("display_type") or ""),
        show_name=args.get("show_name"),
        show_wire=args.get("show_wire"),
        show_in_front=args.get("show_in_front"),
        color=_optional_float_list(args.get("color"), 4, (1.0, 1.0, 1.0, 1.0)),
        empty_display_type=str(args.get("empty_display_type") or ""),
        empty_display_size=args.get("empty_display_size"),
        label=args.get("label", "Set object display"),
    )


def duplicate_selected_objects(context, args):
    return advanced_helpers.duplicate_selected_objects(
        context,
        name_prefix=str(args.get("name_prefix") or "Agent Bridge Copy "),
        offset=_float_list(args.get("offset"), 3, (0.0, 0.0, 0.0)),
        linked_data=bool(args.get("linked_data", False)),
        copy_animation=bool(args.get("copy_animation", False)),
        select_new=bool(args.get("select_new", True)),
        label=args.get("label", "Duplicate selected objects"),
    )


def parent_selected_to_empty(context, args):
    return advanced_helpers.parent_selected_to_empty(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        name=str(args.get("name") or "Agent Bridge Parent"),
        location=_optional_float_list(args.get("location"), 3, (0.0, 0.0, 0.0)),
        empty_display_type=str(args.get("empty_display_type") or "PLAIN_AXES"),
        keep_transform=bool(args.get("keep_transform", True)),
        label=args.get("label", "Parent selected to empty"),
    )


def align_selected_objects(context, args):
    return advanced_helpers.align_selected_objects(
        context,
        axis=str(args.get("axis") or "Z"),
        mode=str(args.get("mode") or "ACTIVE"),
        value=args.get("value"),
        label=args.get("label", "Align selected objects"),
    )


def distribute_selected_objects(context, args):
    return advanced_helpers.distribute_selected_objects(
        context,
        axis=str(args.get("axis") or "X"),
        start=args.get("start"),
        end=args.get("end"),
        label=args.get("label", "Distribute selected objects"),
    )


def register(handler_registry, specs):
    for spec in specs:
        try:
            handler = globals()[spec.handler_key]
        except KeyError as exc:
            raise KeyError(f"Missing handler {spec.handler_key} for {spec.name}") from exc
        handler_registry.register(spec.name, handler)
