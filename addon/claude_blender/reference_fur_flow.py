"""Reference part graph to fur-flow groom adapter."""

from __future__ import annotations

import json

from . import (
    advanced_rigging,
    fur_groom,
    live_preview,
    reference_part_scene,
    reference_parts,
)
from .advanced_support import _resolve_edit_objects


PART_VERTEX_GROUPS_METADATA_PROP = "reference_part_vertex_groups_json"
_MAX_VERTEX_GROUP_NAME_BYTES = 63
_MAX_MASK_VERTICES_PER_OBJECT = 250_000
_MAX_MASK_WEIGHT_EVALUATIONS = 4_000_000


def _clean_names(values):
    return [str(value).strip() for value in values or [] if str(value).strip()][:64]


def _truncate_utf8(value, max_bytes):
    encoded = str(value).encode("utf-8")
    if len(encoded) <= max_bytes:
        return str(value)
    return encoded[:max_bytes].decode("utf-8", errors="ignore").rstrip()


def _safe_name(value, fallback):
    text = " ".join(str(value or "").strip().split())
    keep = [char if char.isalnum() or char in {"_", "-", " "} else "_" for char in text]
    cleaned = " ".join("".join(keep).split()) or fallback
    return _truncate_utf8(cleaned, _MAX_VERTEX_GROUP_NAME_BYTES) or fallback


def _set_json_prop(data_block, key, value):
    data_block[key] = json.dumps(value, sort_keys=True)


def _bounded_float(value, default, *, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        number = float(default)
    if number != number:
        number = float(default)
    return max(float(minimum), min(float(maximum), number))


def _parts_from_graph(collection_name, *, part_names, include_roles):
    collection, error = reference_part_scene.resolve_part_graph_collection(collection_name)
    if error:
        return None, [], error
    graph = reference_part_scene.load_part_graph(collection)
    parts = [part for part in list(graph.get("parts") or []) if isinstance(part, dict)]
    requested = set(_clean_names(part_names))
    if requested:
        available = {str(part.get("name") or "") for part in parts}
        missing = sorted(requested - available)
        if missing:
            return collection, [], "Reference part(s) not found: " + ", ".join(missing[:16])
        parts = [part for part in parts if str(part.get("name") or "") in requested]
    roles = set(_clean_names(include_roles))
    if roles:
        parts = [part for part in parts if str(part.get("role") or "generic") in roles]
    return collection, parts, ""


def _group_name(name_prefix, part_name):
    return _safe_name(f"{name_prefix} {part_name}", "Reference Part Weight")


def _unique_group_names(parts, name_prefix):
    names = []
    used = set()
    for part in parts:
        base = _group_name(name_prefix, str(part.get("name") or "part"))
        candidate = base
        suffix_index = 2
        while candidate in used:
            suffix = f" {suffix_index}"
            candidate = (
                _truncate_utf8(
                    base,
                    _MAX_VERTEX_GROUP_NAME_BYTES - len(suffix.encode("utf-8")),
                )
                + suffix
            )
            suffix_index += 1
        names.append(candidate)
        used.add(candidate)
    return names


def _organic_parts(parts, max_parts):
    result = []
    for part in list(parts or [])[:64]:
        if not isinstance(part, dict):
            continue
        if str(part.get("role") or "generic") not in reference_parts.ORGANIC_ROLES:
            continue
        result.append(part)
        if len(result) >= max(1, min(32, int(max_parts or 16))):
            break
    return result


def _vertex_group_weight_summary(obj, group):
    assigned = 0
    max_weight = 0.0
    for vertex in obj.data.vertices:
        assignment = next(
            (item for item in vertex.groups if item.group == group.index),
            None,
        )
        if assignment is None or assignment.weight <= 0.0:
            continue
        assigned += 1
        max_weight = max(max_weight, float(assignment.weight))
    return assigned, max_weight


def _mask_workload_error(
    meshes,
    part_count,
    *,
    max_vertices_per_object=_MAX_MASK_VERTICES_PER_OBJECT,
    max_weight_evaluations=_MAX_MASK_WEIGHT_EVALUATIONS,
):
    total_evaluations = 0
    for obj in meshes:
        vertex_count = len(obj.data.vertices)
        if vertex_count > max_vertices_per_object:
            return (
                f"Part masks support at most {max_vertices_per_object} vertices "
                f"per synchronous object; {obj.name} has {vertex_count}. "
                "Remesh first or use a lower-resolution source mesh."
            )
        total_evaluations += vertex_count * part_count
    if total_evaluations > max_weight_evaluations:
        return (
            f"Part mask workload requires {total_evaluations} vertex/part "
            f"evaluations; the synchronous limit is {max_weight_evaluations}. "
            "Reduce object_names or part_names and retry."
        )
    return ""


def _apply_part_weight_vertex_groups(
    *,
    objects,
    parts,
    part_graph_collection_name,
    name_prefix,
    radius_scale,
    falloff_power,
    minimum_weight,
    replace_existing,
):
    meshes = [obj for obj in objects if obj and obj.type == "MESH"]
    if not meshes:
        return {
            "ok": False,
            "message": "No mesh objects found for part weight vertex groups",
            "objects": [],
            "warnings": [],
        }
    if not parts:
        return {
            "ok": False,
            "message": "No usable reference parts found for vertex-group masks",
            "objects": [],
            "warnings": [],
        }
    workload_error = _mask_workload_error(meshes, len(parts))
    if workload_error:
        return {
            "ok": False,
            "code": "part_mask_workload_exceeded",
            "message": workload_error,
            "objects": [],
            "warnings": [],
        }

    radius_scale = _bounded_float(radius_scale, 1.35, minimum=0.05, maximum=100.0)
    falloff_power = _bounded_float(falloff_power, 2.0, minimum=0.05, maximum=16.0)
    minimum_weight = _bounded_float(minimum_weight, 0.001, minimum=0.0, maximum=1.0)
    prepared = []
    warnings = []
    group_names = _unique_group_names(parts, name_prefix)
    for obj in meshes:
        live_preview._record_object_vertex_groups(obj)
        live_preview._record_id_property(
            "object",
            obj.name,
            PART_VERTEX_GROUPS_METADATA_PROP,
        )
        object_groups = []
        for part, group_name in zip(parts, group_names):
            part_name = str(part.get("name") or "part")
            existing = obj.vertex_groups.get(group_name)
            if existing is not None:
                if not replace_existing:
                    group = existing
                    assigned, max_weight = _vertex_group_weight_summary(obj, group)
                    if assigned <= 0:
                        warnings.append(f"Existing vertex group has no weights {obj.name}:{group_name}")
                        continue
                    reused = True
                else:
                    obj.vertex_groups.remove(existing)
                    group = obj.vertex_groups.new(name=group_name)
                    assigned = 0
                    max_weight = 0.0
                    reused = False
            else:
                group = obj.vertex_groups.new(name=group_name)
                assigned = 0
                max_weight = 0.0
                reused = False
            if not reused:
                for vertex in obj.data.vertices:
                    point = obj.matrix_world @ vertex.co
                    weight = fur_groom.part_weight_at_point(
                        tuple(point),
                        part,
                        radius_scale=radius_scale,
                        falloff_power=falloff_power,
                        minimum_weight=minimum_weight,
                    )
                    if weight <= 0.0:
                        continue
                    group.add([vertex.index], weight, "REPLACE")
                    assigned += 1
                    max_weight = max(max_weight, weight)
            if assigned <= 0:
                warnings.append(f"No vertices matched part {part_name} on {obj.name}")
                if not reused:
                    obj.vertex_groups.remove(group)
                    continue
            object_groups.append(
                {
                    "part_name": part_name,
                    "role": str(part.get("role") or "generic"),
                    "vertex_group": group.name,
                    "assigned_vertices": assigned,
                    "max_weight": round(max_weight, 6),
                    "reused": reused,
                }
            )
        if object_groups:
            metadata = {
                "schema_version": 1,
                "part_graph_collection": part_graph_collection_name,
                "groups": object_groups,
                "radius_scale": radius_scale,
                "falloff_power": falloff_power,
                "minimum_weight": minimum_weight,
            }
            _set_json_prop(obj, PART_VERTEX_GROUPS_METADATA_PROP, metadata)
            prepared.append({"object": obj.name, "groups": object_groups})
    if not prepared:
        return {
            "ok": False,
            "message": "No part vertex groups received any weights",
            "objects": [],
            "warnings": warnings,
        }
    return {
        "ok": True,
        "message": f"Prepared part weight vertex groups on {len(prepared)} mesh object(s)",
        "objects": prepared,
        "warnings": warnings,
    }


def _part_vertex_group_lookup(vertex_group_result):
    groups = {}
    for object_result in vertex_group_result.get("objects") or []:
        for group in object_result.get("groups") or []:
            groups.setdefault(str(group.get("part_name") or ""), str(group.get("vertex_group") or ""))
    return groups


def _attach_vertex_groups_to_field(field, vertex_group_result):
    by_part = _part_vertex_group_lookup(vertex_group_result)
    for region in field.get("regions") or []:
        group_name = by_part.get(str(region.get("part_name") or ""))
        if group_name:
            region["vertex_group"] = group_name
    return field


def create_part_weight_vertex_groups(
    context,
    *,
    part_graph_collection_name="",
    object_names=None,
    selected_only=True,
    part_names=None,
    include_roles=None,
    name_prefix="Reference Part",
    radius_scale=1.35,
    falloff_power=2.0,
    minimum_weight=0.001,
    replace_existing=True,
    max_parts=16,
    label="Create part weight vertex groups",
):
    collection, parts, error = _parts_from_graph(
        part_graph_collection_name,
        part_names=part_names or [],
        include_roles=include_roles or [],
    )
    if error:
        return {"ok": False, "message": error}
    parts = _organic_parts(parts, max_parts)
    objects, missing = _resolve_edit_objects(
        context,
        object_names=_clean_names(object_names),
        selected_only=selected_only,
        max_objects=64,
    )
    operation = live_preview.begin_isolated(label, context)
    try:
        result = _apply_part_weight_vertex_groups(
            objects=objects,
            parts=parts,
            part_graph_collection_name=collection.name,
            name_prefix=name_prefix,
            radius_scale=radius_scale,
            falloff_power=falloff_power,
            minimum_weight=minimum_weight,
            replace_existing=replace_existing,
        )
        if not result.get("ok"):
            live_preview.abort_isolated(operation, context)
            result["missing_object_names"] = missing
            return result
        transaction = operation["transaction"]
        transaction["applied_steps"].append(
            {
                "type": "create_part_weight_vertex_groups",
                "label": label,
                "part_graph_collection": collection.name,
                "objects": [item["object"] for item in result["objects"]],
            }
        )
        transaction = live_preview.finish_isolated(operation)
        live_preview.redraw(context)
        live_preview._mark_pending(context, label)
        result.update(
            {
                "part_graph_collection": collection.name,
                "parts": [str(part.get("name") or "") for part in parts],
                "missing_object_names": missing,
                "transaction_id": transaction["id"],
            }
        )
        return result
    except Exception as exc:
        live_preview.abort_isolated(operation, context)
        return {
            "ok": False,
            "message": f"Part weight vertex groups failed: {type(exc).__name__}: {exc}",
            "missing_object_names": missing,
        }


def create_fur_flow_field_from_parts(
    context,
    *,
    part_graph_collection_name="",
    part_names=None,
    include_roles=None,
    preset="kitten_soft",
    count=600,
    max_regions=16,
    apply_groom=False,
    use_part_vertex_groups=True,
    vertex_group_name_prefix="Reference Part",
    vertex_group_radius_scale=1.35,
    vertex_group_falloff_power=2.0,
    vertex_group_minimum_weight=0.001,
    replace_existing_vertex_groups=True,
    object_names=None,
    selected_only=True,
    name_prefix="Reference Fur Flow",
    material_name="",
    color=(0.82, 0.82, 0.78, 1.0),
    seed=17,
    label="Create fur flow field from parts",
):
    collection, parts, error = _parts_from_graph(
        part_graph_collection_name,
        part_names=part_names or [],
        include_roles=include_roles or [],
    )
    if error:
        return {"ok": False, "message": error}
    field = fur_groom.part_graph_fur_flow_field(
        parts,
        preset=preset,
        count=count,
        include_roles=include_roles or None,
        max_regions=max_regions,
    )
    if not field["regions"]:
        return {
            "ok": False,
            "message": "No fur-flow regions could be generated from the reference part graph",
            "part_graph_collection": collection.name,
            "warnings": field["warnings"],
            "field": field,
        }

    result = {
        "ok": True,
        "message": f"Created fur-flow field with {len(field['regions'])} region(s)",
        "part_graph_collection": collection.name,
        "parts": [str(part.get("name") or "") for part in parts],
        "field": field,
        "applied": False,
    }
    if not apply_groom:
        return result

    vertex_group_operation = None
    if use_part_vertex_groups:
        objects, missing = _resolve_edit_objects(
            context,
            object_names=_clean_names(object_names),
            selected_only=selected_only,
            max_objects=64,
        )
        vertex_group_operation = live_preview.begin_isolated(label, context)
        try:
            vertex_group_result = _apply_part_weight_vertex_groups(
                objects=objects,
                parts=_organic_parts(parts, max_regions),
                part_graph_collection_name=collection.name,
                name_prefix=vertex_group_name_prefix,
                radius_scale=vertex_group_radius_scale,
                falloff_power=vertex_group_falloff_power,
                minimum_weight=vertex_group_minimum_weight,
                replace_existing=replace_existing_vertex_groups,
            )
            if not vertex_group_result.get("ok"):
                live_preview.abort_isolated(vertex_group_operation, context)
                result.update(
                    {
                        "ok": False,
                        "message": vertex_group_result.get("message", "Part vertex-group creation failed"),
                        "vertex_group_result": vertex_group_result,
                        "missing_object_names": missing,
                    }
                )
                return result
            vertex_group_operation["transaction"]["applied_steps"].append(
                {
                    "type": "create_part_weight_vertex_groups",
                    "label": f"{label} masks",
                    "part_graph_collection": collection.name,
                    "objects": [item["object"] for item in vertex_group_result["objects"]],
                }
            )
            field = _attach_vertex_groups_to_field(field, vertex_group_result)
            result["field"] = field
            result["vertex_group_result"] = vertex_group_result
        except Exception as exc:
            live_preview.abort_isolated(vertex_group_operation, context)
            result.update(
                {
                    "ok": False,
                    "message": f"Part vertex-group creation failed: {type(exc).__name__}: {exc}",
                }
            )
            return result

    groom = advanced_rigging.create_directional_fur_curves(
        context,
        object_names=_clean_names(object_names),
        selected_only=selected_only,
        name_prefix=name_prefix,
        count=count,
        flow_controls=field["flow_controls"],
        density_controls=[],
        regions=field["regions"],
        material_name=material_name,
        color=color,
        seed=seed,
        label=label,
    )
    result["applied"] = bool(groom.get("ok"))
    result["groom_result"] = groom
    result["transaction_id"] = groom.get("transaction_id", "")
    if not groom.get("ok"):
        result["ok"] = False
        result["message"] = groom.get("message", "Fur-flow groom application failed")
        if vertex_group_operation is not None:
            live_preview.abort_isolated(vertex_group_operation, context)
        return result
    if vertex_group_operation is not None:
        transaction = live_preview.finish_isolated(vertex_group_operation)
        live_preview.redraw(context)
        live_preview._mark_pending(context, label)
        result["transaction_id"] = transaction["id"]
    return result


def register():
    pass


def unregister():
    pass
