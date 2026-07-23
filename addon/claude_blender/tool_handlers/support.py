"""Shared argument normalization and object-resolution helpers for tool handlers."""

from __future__ import annotations

import re
import textwrap

import bpy


_PYTHON_FENCE_RE = re.compile(r"```(?:python|py)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def _float_list(values, length, default):
    if values is None:
        return list(default)
    result = list(values)[:length]
    while len(result) < length:
        result.append(default[len(result)])
    return [float(value) for value in result]


def _optional_float_list(values, length, default):
    if values is None:
        return None
    return _float_list(values, length, default)


def _optional_float(value):
    if value is None or value == "":
        return None
    return float(value)


def _name_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value if str(item).strip()]


def _bounded_int(value, default, *, minimum=1, maximum=100):
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = int(default)
    return max(int(minimum), min(int(maximum), result))


def _bounded_float(value, default, *, minimum=0.0, maximum=1000.0):
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = float(default)
    return max(float(minimum), min(float(maximum), result))


def _extract_script_code(args):
    for key in ("code", "script", "source", "python", "body"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value
    for key in ("expected_changes", "intent"):
        value = args.get(key)
        if not isinstance(value, str):
            continue
        match = _PYTHON_FENCE_RE.search(value)
        if match and match.group(1).strip():
            return match.group(1)
    return ""


def _resolve_objects(context, args, *, default_to_scene=False):
    names = _name_list(args.get("object_names"))
    max_objects = _bounded_int(args.get("max_objects"), 12, maximum=50)
    missing = []
    if names:
        objects = []
        for name in names:
            obj = bpy.data.objects.get(name)
            if obj:
                objects.append(obj)
            else:
                missing.append(name)
        return objects[:max_objects], missing
    if args.get("selected_only"):
        return list(context.selected_objects)[:max_objects], missing
    if context.active_object:
        return [context.active_object], missing
    if default_to_scene:
        return list(context.scene.objects)[:max_objects], missing
    return [], missing


def _simulation_bake_script(*, object_names, frame_start, frame_end, clear_existing, include_scene_rigid_body_world):
    names_literal = repr([str(name) for name in object_names or [] if str(name)])
    return textwrap.dedent(
        f"""
        import bpy

        scene = bpy.context.scene
        target_names = {names_literal}
        frame_start = {int(frame_start)}
        frame_end = {int(frame_end)}
        clear_existing = {bool(clear_existing)!r}
        include_scene_rigid_body_world = {bool(include_scene_rigid_body_world)!r}
        original_frame = int(scene.frame_current)
        scope_warning = (
            "bpy.ops.ptcache.bake_all is scene-wide; target_names only limit range preparation "
            "and inspection evidence."
        )

        def set_cache_range(cache, label, touched):
            if cache is None:
                return
            cache.frame_start = frame_start
            cache.frame_end = frame_end
            touched.append(label)

        touched_caches = []
        if include_scene_rigid_body_world and scene.rigidbody_world:
            set_cache_range(getattr(scene.rigidbody_world, "point_cache", None), "scene.rigidbody_world", touched_caches)

        objects = [bpy.data.objects.get(name) for name in target_names] if target_names else list(scene.objects)
        objects = [obj for obj in objects if obj is not None]
        for obj in objects:
            for modifier in getattr(obj, "modifiers", []):
                set_cache_range(getattr(modifier, "point_cache", None), obj.name + "." + modifier.name, touched_caches)
            for psys in getattr(obj, "particle_systems", []):
                set_cache_range(getattr(psys, "point_cache", None), obj.name + "." + psys.name, touched_caches)

        try:
            scene.frame_set(frame_start)
            if clear_existing:
                bpy.ops.ptcache.free_bake_all()
            bpy.ops.ptcache.bake_all(bake=True)
        finally:
            scene.frame_set(original_frame)

        print("=== persistent simulation bake complete ===")
        print("frame_range:", frame_start, frame_end)
        print("target_objects:", [obj.name for obj in objects])
        print("touched_caches:", touched_caches)
        print("scope_warning:", scope_warning)
        """
    ).strip()
