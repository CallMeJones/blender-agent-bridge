"""Token-aware context selection for external agent requests."""

from __future__ import annotations

import copy
import json
import math

from . import context_budget

DEFAULT_MAX_CONTEXT_CHARS = 48_000
MAX_SELECTED_FULL = 8
MAX_SELECTED_SLIM = 16

ANIMATION_WORDS = {
    "animate",
    "animation",
    "keyframe",
    "keyframes",
    "timeline",
    "orbit",
    "camera",
    "motion",
    "bounce",
}

MATERIAL_WORDS = {
    "material",
    "materials",
    "color",
    "colour",
    "shader",
    "glow",
    "emission",
    "texture",
    "metal",
    "roughness",
}

WORLD_MODEL_WORDS = {
    "geometry nodes",
    "geometry node",
    "node group",
    "shader",
    "armature",
    "rig",
    "rigging",
    "constraint",
    "driver",
    "shape key",
    "shape keys",
    "curve",
    "text",
    "particle",
    "particles",
    "simulation",
    "simulations",
    "collection",
    "layer",
    "render",
    "compositor",
}


def estimate_tokens(chars):
    return int(math.ceil(max(0, int(chars)) / 4.0))


def _json_chars(value):
    return len(json.dumps(value, sort_keys=True, default=str))


def _contains_any(prompt, words):
    lowered = (prompt or "").lower()
    return any(word in lowered for word in words)


def _slim_object(obj):
    if not isinstance(obj, dict):
        return obj
    return {
        "name": obj.get("name"),
        "type": obj.get("type"),
        "location": obj.get("location"),
        "rotation_euler_radians": obj.get("rotation_euler_radians"),
        "scale": obj.get("scale"),
        "dimensions_blender_units": obj.get("dimensions_blender_units"),
        "material_slots": obj.get("material_slots"),
        "modifiers": obj.get("modifiers"),
        "constraints": obj.get("constraints"),
        "animation": obj.get("animation"),
    }


def _plan_selection(selection):
    selection = copy.deepcopy(selection or {})
    selected = selection.get("selected_objects")
    if not isinstance(selected, list):
        return selection
    planned = []
    for index, obj in enumerate(selected[:MAX_SELECTED_SLIM]):
        planned.append(copy.deepcopy(obj) if index < MAX_SELECTED_FULL else _slim_object(obj))
    if len(selected) > MAX_SELECTED_SLIM:
        planned.append({"_truncated_selected_objects": len(selected) - MAX_SELECTED_SLIM})
    selection["selected_objects"] = planned
    return selection


def _plan_animation(animation):
    animation = copy.deepcopy(animation or {})
    actions = animation.get("actions")
    if isinstance(actions, list) and len(actions) > 12:
        animation["actions"] = actions[:12] + [{"_truncated_actions": len(actions) - 12}]
    return animation


def _plan_materials(materials):
    planned = copy.deepcopy(materials or [])
    if isinstance(planned, list) and len(planned) > 12:
        return planned[:12] + [{"_truncated_materials": len(planned) - 12}]
    return planned


def _base_plan(prompt, bundle, *, max_context_chars=DEFAULT_MAX_CONTEXT_CHARS):
    include_animation = _contains_any(prompt, ANIMATION_WORDS)
    include_materials = _contains_any(prompt, MATERIAL_WORDS)
    include_world_model = _contains_any(prompt, WORLD_MODEL_WORDS)
    visual = copy.deepcopy(bundle.get("visual_context") or {})
    planned = {
        "context_plan": {
            "policy": (
                "Token-aware context planner selected a compact request bundle. "
                "Current Blender scene is authoritative; omitted details can be requested with tools."
            ),
            "char_budget": int(max_context_chars),
            "estimated_tokens_per_char_rule": "ceil(chars / 4)",
            "included": [],
            "omitted": [],
        },
        "environment": copy.deepcopy(bundle.get("environment")),
        "scene_summary": copy.deepcopy(bundle.get("scene_summary")),
        "world_model_summary": copy.deepcopy(bundle.get("world_model_summary")),
        "selection_summary": _plan_selection(bundle.get("selection_summary")),
        "active_object_detail": copy.deepcopy(bundle.get("active_object_detail")),
        "visual_context": visual,
        "available_tools": list(bundle.get("available_tools") or []),
        "privacy_redactions": copy.deepcopy(bundle.get("privacy_redactions")),
    }
    included = planned["context_plan"]["included"]
    omitted = planned["context_plan"]["omitted"]
    included.extend(
        [
            "environment",
            "scene_summary",
            "world_model_summary",
            "selection_summary",
            "active_object_detail",
            "visual_context",
            "available_tools",
        ]
    )
    if not include_world_model:
        omitted.append("deep world details: use specific get_*_details tools when geometry nodes, rigging, simulations, collections, render, or compositor details are needed")
    if include_animation:
        planned["animation_summary"] = _plan_animation(bundle.get("animation_summary"))
        included.append("animation_summary")
    else:
        omitted.append("animation_summary: omitted until animation/timeline/camera context is needed")
    if include_materials or bundle.get("material_summary"):
        planned["material_summary"] = _plan_materials(bundle.get("material_summary"))
        included.append("material_summary")
    else:
        omitted.append("material_summary: omitted until material/shader context is needed")
    return planned


def _with_attachments(planned, source_bundle):
    if "_attachments" in source_bundle:
        planned["_attachments"] = source_bundle["_attachments"]
    return planned


def plan_context_bundle(prompt, bundle, *, max_context_chars=DEFAULT_MAX_CONTEXT_CHARS):
    """Return a compact context bundle plus request-size metadata."""

    planned = _base_plan(prompt, bundle, max_context_chars=max_context_chars)
    public = {key: value for key, value in planned.items() if key != "_attachments"}
    chars = _json_chars(public)
    if chars > max_context_chars:
        planned.pop("material_summary", None)
        planned["context_plan"]["omitted"].append("material_summary: removed to fit hard budget")
        public = {key: value for key, value in planned.items() if key != "_attachments"}
        chars = _json_chars(public)
    if chars > max_context_chars:
        planned.pop("animation_summary", None)
        planned["context_plan"]["omitted"].append("animation_summary: removed to fit hard budget")
        public = {key: value for key, value in planned.items() if key != "_attachments"}
        chars = _json_chars(public)
    if chars > max_context_chars:
        planned = context_budget.compact_jsonable(
            planned,
            max_string_chars=800,
            max_list_items=12,
            max_depth=6,
        )
        if isinstance(planned, dict):
            planned.setdefault("context_plan", {})
            planned["context_plan"]["truncated_for_request"] = True
        public = {key: value for key, value in planned.items() if key != "_attachments"}
        chars = _json_chars(public)

    planned = _with_attachments(planned, bundle)
    metadata = {
        "chars": chars,
        "estimated_tokens": estimate_tokens(chars),
        "char_budget": int(max_context_chars),
        "included": list((planned.get("context_plan") or {}).get("included") or []),
        "omitted": list((planned.get("context_plan") or {}).get("omitted") or []),
    }
    if isinstance(planned, dict):
        planned.setdefault("context_plan", {})
        planned["context_plan"]["estimated_chars"] = chars
        planned["context_plan"]["estimated_tokens"] = metadata["estimated_tokens"]
    return planned, metadata


def summarize_plan(metadata):
    chars = int(metadata.get("chars") or 0)
    tokens = int(metadata.get("estimated_tokens") or 0)
    included = metadata.get("included") or []
    shown = ", ".join(included[:5])
    if len(included) > 5:
        shown += f", +{len(included) - 5}"
    return f"{chars} chars, ~{tokens} tokens; {shown or 'minimal context'}"


def register():
    pass


def unregister():
    pass
