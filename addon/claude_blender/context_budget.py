"""Prompt payload budgeting helpers.

These guards keep local caches and large scenes from being shoved into a single
LLM request. They use character counts as a conservative, dependency-free proxy
for token pressure.
"""

from __future__ import annotations

import json


MAX_CONTEXT_JSON_CHARS = 120_000
MAX_TOOL_RESULT_CHARS = 24_000
MAX_DOC_RESULT_CHARS = 8_000
MAX_STRING_CHARS = 4_000
MAX_LIST_ITEMS = 50
MAX_DEPTH = 8
TRUNCATED_TEXT = "... [truncated]"


def truncate_text(text, max_chars):
    text = str(text)
    max_chars = int(max_chars)
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    # Guarantee the result never exceeds max_chars (a hard budget). When the budget
    # is too small to fit the truncation marker, hard-slice the original text.
    if max_chars <= len(TRUNCATED_TEXT):
        return text[:max_chars]
    keep = max_chars - len(TRUNCATED_TEXT)
    return f"{text[:keep]}{TRUNCATED_TEXT}"


def compact_jsonable(value, *, max_string_chars=MAX_STRING_CHARS, max_list_items=MAX_LIST_ITEMS, max_depth=MAX_DEPTH, _depth=0):
    if _depth >= max_depth:
        return "[truncated: max depth reached]"
    if isinstance(value, str):
        return truncate_text(value, max_string_chars)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        compacted = {}
        for key, item in value.items():
            if key == "_attachments":
                compacted["_attachments"] = "[omitted from text context]"
                continue
            compacted[key] = compact_jsonable(
                item,
                max_string_chars=max_string_chars,
                max_list_items=max_list_items,
                max_depth=max_depth,
                _depth=_depth + 1,
            )
        return compacted
    if isinstance(value, (list, tuple)):
        items = list(value)
        limited = [
            compact_jsonable(
                item,
                max_string_chars=max_string_chars,
                max_list_items=max_list_items,
                max_depth=max_depth,
                _depth=_depth + 1,
            )
            for item in items[:max_list_items]
        ]
        if len(items) > max_list_items:
            limited.append({"_truncated_items": len(items) - max_list_items})
        return limited
    return truncate_text(repr(value), max_string_chars)


def _slim_object_summary(obj):
    return {
        "name": obj.get("name"),
        "type": obj.get("type"),
        "location": obj.get("location"),
        "rotation_euler_radians": obj.get("rotation_euler_radians"),
        "scale": obj.get("scale"),
        "dimensions_blender_units": obj.get("dimensions_blender_units"),
        "material_slots": obj.get("material_slots"),
        "animation": obj.get("animation"),
    }


def compact_context_bundle(bundle):
    compacted = compact_jsonable(bundle)
    selection = compacted.get("selection_summary") if isinstance(compacted, dict) else None
    if isinstance(selection, dict):
        selected = selection.get("selected_objects")
        if isinstance(selected, list) and len(selected) > 10:
            selection["selected_objects"] = [
                _slim_object_summary(obj) if isinstance(obj, dict) else obj
                for obj in selected[:10]
            ]
            selection["selected_objects"].append({"_truncated_selected_objects": len(selected) - 10})
    if isinstance(compacted, dict):
        compacted["context_budget"] = {
            "policy": "Large local docs, screenshots, and scene details are never sent wholesale. This context was compacted before the LLM request.",
            "max_context_json_chars": MAX_CONTEXT_JSON_CHARS,
        }
    return compacted


def dumps_json_for_prompt(value, *, max_chars=MAX_CONTEXT_JSON_CHARS):
    compacted = compact_context_bundle(value)
    text = json.dumps(compacted, indent=2, sort_keys=True)
    if len(text) <= int(max_chars):
        return text

    more_compact = compact_jsonable(
        compacted,
        max_string_chars=1_000,
        max_list_items=20,
        max_depth=6,
    )
    if isinstance(more_compact, dict):
        more_compact["context_budget"]["truncated_for_request"] = True
    text = json.dumps(more_compact, indent=2, sort_keys=True)
    return truncate_text(text, max_chars)


def limit_json_result_text(text, *, max_chars=MAX_TOOL_RESULT_CHARS):
    return truncate_text(text, max_chars)
