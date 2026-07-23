"""Lossless, opt-in response controls for large read-only inspection tools."""

from __future__ import annotations

import copy
import hashlib
import json
import math


CONTROLLED_TOOL_FIELDS = {
    "inspect_scene": ("objects", "available_tools"),
    "list_scene_objects": ("objects",),
    "get_object_details": ("objects",),
    "get_collection_layer_details": ("collections", "view_layers", "objects"),
    "get_animation_details": ("actions", "objects"),
    "get_animation_scene_context": ("objects", "likely_edit_targets", "required_inspections"),
    "get_2d_animation_details": ("objects", "scenes", "materials"),
    "get_material_node_details": ("materials",),
    "get_geometry_nodes_details": ("objects",),
    "get_shader_nodes_details": ("materials",),
    "inspect_material_setup": ("materials", "objects", "issues"),
    "inspect_uv_layout": ("objects",),
    "get_rigging_details": ("objects",),
    "get_rig_pose_library_details": ("objects", "actions"),
    "get_shape_key_details": ("objects",),
    "get_curve_text_details": ("objects",),
    "get_simulation_details": ("objects",),
    "inspect_simulation_bake": ("objects", "samples"),
}

CONTROL_SCHEMA_PROPERTIES = {
    "detail": {
        "type": "string",
        "enum": ["summary", "full"],
        "default": "full",
        "description": "Optional response detail. Full preserves the complete existing result and remains the default.",
    },
    "fields": {
        "type": "array",
        "items": {"type": "string"},
        "minItems": 1,
        "uniqueItems": True,
        "description": (
            "Optional dotted response fields to return, such as objects.name or materials.nodes. "
            "Status and response metadata are always retained."
        ),
    },
    "page": {
        "type": "integer",
        "minimum": 1,
        "description": "Optional 1-based page for one top-level result collection.",
    },
    "page_size": {
        "type": "integer",
        "minimum": 1,
        "maximum": 100,
        "description": "Optional number of collection items per page. Defaults to 25 when pagination is requested.",
    },
    "page_field": {
        "type": "string",
        "description": (
            "Optional top-level array field to paginate, such as objects, materials, or actions. "
            "The tool's primary collection is used when omitted."
        ),
    },
    "known_digest": {
        "type": "string",
        "minLength": 8,
        "maxLength": 64,
        "description": (
            "Optional digest from a previous complete response. A match returns not_modified; "
            "a mismatch returns the complete current result."
        ),
    },
}

_IDENTITY_KEYS = frozenset(
    {
        "name",
        "type",
        "label",
        "status",
        "code",
        "frame",
        "frame_current",
        "frame_start",
        "frame_end",
        "fps",
        "selected",
        "active",
        "enabled",
        "visible",
        "hidden_viewport",
        "hidden_render",
        "object_count",
        "material_count",
        "action_count",
        "node_count",
        "issue_count",
        "severity",
        "message",
        "note",
    }
)
_ALWAYS_FIELDS = frozenset(
    {
        "ok",
        "code",
        "message",
        "warning",
        "warnings",
        "error",
        "errors",
        "missing_object_names",
        "missing_material_names",
        "missing_action_names",
        "pagination",
    }
)


def supports_response_controls(tool_name):
    return str(tool_name or "") in CONTROLLED_TOOL_FIELDS


def augment_input_schema(tool_name, schema):
    """Return a copied schema with common controls for supported inspectors."""

    result = copy.deepcopy(dict(schema or {}))
    if not supports_response_controls(tool_name):
        return result
    result.setdefault("type", "object")
    properties = result.get("properties")
    if not isinstance(properties, dict):
        properties = {}
    else:
        properties = copy.deepcopy(properties)
    for name, definition in CONTROL_SCHEMA_PROPERTIES.items():
        properties.setdefault(name, copy.deepcopy(definition))
    result["properties"] = properties
    return result


def discovery_input_schema(tool_name, schema):
    """Keep optional response controls on demand instead of repeating them at startup."""

    result = copy.deepcopy(dict(schema or {}))
    if not supports_response_controls(tool_name):
        return result
    properties = result.get("properties")
    if not isinstance(properties, dict):
        return result
    for name in CONTROL_SCHEMA_PROPERTIES:
        properties.pop(name, None)
    return result


def canonical_digest(value):
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _bounded_int(value, default, minimum, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(int(minimum), min(int(maximum), parsed))


def _page_field(tool_name, result, requested):
    requested = str(requested or "").strip()
    if requested:
        return requested if isinstance(result.get(requested), list) else ""
    for candidate in CONTROLLED_TOOL_FIELDS.get(tool_name, ()):
        if isinstance(result.get(candidate), list):
            return candidate
    for key, value in result.items():
        if key not in _ALWAYS_FIELDS and isinstance(value, list):
            return str(key)
    return ""


def _paginate(tool_name, result, arguments):
    if not any(key in arguments for key in ("page", "page_size", "page_field")):
        return result
    field = _page_field(tool_name, result, arguments.get("page_field"))
    if not field:
        result["pagination"] = {
            "field": str(arguments.get("page_field") or ""),
            "page": _bounded_int(arguments.get("page"), 1, 1, 1_000_000),
            "page_size": _bounded_int(arguments.get("page_size"), 25, 1, 100),
            "available": False,
        }
        return result
    values = list(result.get(field) or [])
    page = _bounded_int(arguments.get("page"), 1, 1, 1_000_000)
    page_size = _bounded_int(arguments.get("page_size"), 25, 1, 100)
    start = (page - 1) * page_size
    end = min(len(values), start + page_size)
    result[field] = values[start:end]
    result["pagination"] = {
        "field": field,
        "page": page,
        "page_size": page_size,
        "total_items": len(values),
        "total_pages": int(math.ceil(len(values) / page_size)) if values else 0,
        "has_previous": page > 1 and bool(values),
        "has_next": end < len(values),
    }
    return result


def _summary_item(value):
    if not isinstance(value, dict):
        return value
    summary = {}
    for key, child in value.items():
        if key in _IDENTITY_KEYS and not isinstance(child, (dict, list)):
            summary[key] = child
        elif key in _IDENTITY_KEYS and isinstance(child, list) and all(
            not isinstance(item, (dict, list)) for item in child
        ):
            summary[key] = child[:12]
        elif isinstance(child, (list, dict)):
            summary[f"{key}_count"] = len(child)
    if not summary:
        scalar_items = [
            (key, child)
            for key, child in value.items()
            if not isinstance(child, (dict, list))
        ]
        summary.update(scalar_items[:6])
    return summary


def _summarize(result):
    summary = {}
    for key, value in result.items():
        if not isinstance(value, (dict, list)):
            summary[key] = value
        elif isinstance(value, list):
            summary[key] = [_summary_item(item) for item in value[:25]]
            summary[f"{key}_count"] = len(value)
            if len(value) > 25:
                summary[f"{key}_summary_truncated"] = len(value) - 25
        else:
            summary[key] = _summary_item(value)
    return summary


def _field_tree(fields):
    tree = {}
    for raw in fields:
        parts = [part for part in str(raw or "").split(".") if part]
        if not parts:
            continue
        node = tree
        for part in parts:
            node = node.setdefault(part, {})
    return tree


def _project(value, tree):
    if not tree:
        return copy.deepcopy(value)
    if isinstance(value, list):
        return [_project(item, tree) for item in value]
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    result = {}
    for key, child_tree in tree.items():
        if key in value:
            result[key] = _project(value[key], child_tree)
    return result


def _select_fields(result, fields):
    requested = [str(item) for item in fields if str(item or "").strip()]
    tree = _field_tree(requested)
    projected = _project(result, tree)
    for key in _ALWAYS_FIELDS:
        if key in result:
            projected.setdefault(key, copy.deepcopy(result[key]))
    selected_roots = {path.split(".", 1)[0] for path in requested}
    projected["field_selection"] = {
        "requested": requested,
        "missing": sorted(root for root in selected_roots if root not in result),
    }
    return projected


def apply_response_controls(tool_name, arguments, result):
    """Apply optional controls after computing a digest of the complete result."""

    if not supports_response_controls(tool_name) or not isinstance(result, dict):
        return result
    arguments = arguments if isinstance(arguments, dict) else {}
    complete = copy.deepcopy(result)
    digest = canonical_digest(complete)
    known_digest = str(arguments.get("known_digest") or "").strip().lower()
    if known_digest:
        if known_digest == digest:
            return {
                "ok": bool(complete.get("ok", True)),
                "not_modified": True,
                "response_digest": digest,
                "tool": str(tool_name),
            }
        complete["response_digest"] = digest
        complete["not_modified"] = False
        complete["known_digest_match"] = False
        return complete

    controlled = _paginate(str(tool_name), complete, arguments)
    if str(arguments.get("detail") or "full").strip().lower() == "summary":
        controlled = _summarize(controlled)
        controlled["response_detail"] = "summary"
    fields = arguments.get("fields")
    if isinstance(fields, list) and fields:
        controlled = _select_fields(controlled, fields)
    controlled["response_digest"] = digest
    return controlled
