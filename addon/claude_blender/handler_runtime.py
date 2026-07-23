"""Shared non-domain handler runtime support."""

from __future__ import annotations

import json


from . import live_preview

def _json_result(result):
    return json.dumps(result, indent=2, sort_keys=True)

_RENDER_JOB_INTENT_TERMS = {
    "render animation",
    "full render",
    "quality render",
    "playblast",
    "1080p",
    "4k",
    "frames",
    "frame sequence",
    "samples",
    "bpy.ops.render.render",
    "animation=true",
    "write_still=false",
}

def _looks_like_render_job_intent(text):
    normalized = str(text or "").lower()
    if "render" not in normalized and "playblast" not in normalized and "bpy.ops.render.render" not in normalized:
        return False
    return any(term in normalized for term in _RENDER_JOB_INTENT_TERMS)

def _idprops_summary(data_block):
    result = {}
    for key in list(data_block.keys())[:20]:
        value = data_block.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[str(key)] = value
        else:
            result[str(key)] = repr(value)[:160]
    return result

def _mesh_data_layers(mesh):
    if mesh is None:
        return {}
    return {
        "uv_layers": [layer.name for layer in list(mesh.uv_layers)[:12]],
        "color_attributes": [attribute.name for attribute in list(mesh.color_attributes)[:12]],
        "shape_keys": [block.name for block in list(mesh.shape_keys.key_blocks)[:12]] if mesh.shape_keys else [],
    }

def _socket_value(value):
    if isinstance(value, (int, float, bool, str)) or value is None:
        return value
    try:
        return [round(float(item), 5) for item in value]
    except (TypeError, ValueError):
        return repr(value)[:160]

def _socket_summary(socket):
    result = {
        "name": socket.name,
        "type": socket.type,
        "is_linked": bool(socket.is_linked),
    }
    try:
        result["default_value"] = _socket_value(socket.default_value)
    except AttributeError:
        pass
    return result

def _compact_targets(step):
    for key in (
        "objects",
        "selected_objects",
        "assigned_objects",
        "actions",
        "materials",
        "created",
        "created_objects",
        "duplicates",
        "collections",
        "lights",
        "cameras",
    ):
        value = step.get(key)
        if not value or isinstance(value, bool):
            continue
        if isinstance(value, list):
            names = []
            for item in value[:8]:
                if isinstance(item, dict):
                    names.append(str(item.get("object") or item.get("action") or item.get("name") or item))
                else:
                    names.append(str(item))
            return names
        return [str(value)]
    for key in ("object", "target", "camera", "material", "collection", "action", "world"):
        value = step.get(key)
        if value:
            return [str(value)]
    return []

def _format_count(noun, count):
    count = int(count or 0)
    suffix = "" if count == 1 else "s"
    return f"{count} {noun}{suffix}"

def _preview_expected_changes(step, label, kind, target_text):
    custom = str(step.get("expected_changes") or "").strip()
    if custom:
        return custom
    if kind == "create_studio_product_stage":
        return (
            f"{label}: creates a studio stage for {step.get('target') or target_text} with "
            f"{_format_count('object', len(step.get('created_objects') or []))}, "
            f"{_format_count('light', len(step.get('lights') or []))}, "
            f"and {'a camera' if step.get('camera') else 'no camera'}."
        )
    if kind == "add_dimension_callouts":
        axes = ", ".join(sorted((step.get("measurements") or {}).keys())) or "bounds"
        return f"{label}: adds dimension callouts for {step.get('target') or target_text} covering {axes}."
    if kind == "apply_lighting_preset":
        return (
            f"{label}: adds the {step.get('preset', 'production')} lighting preset around "
            f"{step.get('target') or target_text} with {_format_count('light', len(step.get('lights') or []))}."
        )
    if kind == "create_material_palette":
        return (
            f"{label}: creates the {step.get('palette', 'production')} palette with "
            f"{_format_count('material', len(step.get('materials') or []))} and "
            f"{_format_count('swatch', len(step.get('swatches') or []))}."
        )
    if kind == "create_product_turntable_setup":
        return (
            f"{label}: sets up {step.get('target') or target_text} for a turntable from frame "
            f"{step.get('frame_start')} to {step.get('frame_end')}, with "
            f"{'stage, ' if step.get('stage_created') else ''}"
            f"camera {step.get('camera') or 'none'} and action {step.get('action') or 'none'}."
        )
    if kind == "prepare_imported_asset_presentation":
        features = ", ".join(step.get("features") or []) or "presentation setup"
        return (
            f"{label}: prepares imported asset objects around {step.get('target') or target_text} "
            f"with {features}."
        )
    if kind == "edit_mesh":
        return f"{label}: applies {step.get('operation', 'edit_mesh')} to {target_text} with mesh-data rollback."
    if kind == "curve_to_mesh":
        return f"{label}: creates {_format_count('mesh object', len(step.get('created') or []))} from curve/text sources."
    if kind == "uv_unwrap":
        return f"{label}: writes {step.get('method', 'smart_project')} UVs on {target_text} with mesh-data rollback."
    if kind == "mark_uv_seams":
        return f"{label}: marks {step.get('mode', 'sharp_angle')} UV seams on {target_text} with mesh-data rollback."
    if kind == "create_image_texture_material":
        maps = ", ".join(step.get("maps") or []) or "image maps"
        return f"{label}: wires {maps} into material {step.get('material') or 'material'} with preview rollback."
    if kind == "repair_material_setup":
        return f"{label}: repairs material texture color spaces and UV map links with preview rollback."
    if kind == "bake_maps":
        maps = ", ".join(step.get("map_types") or []) or "maps"
        return (
            f"{label}: bakes {maps} for {target_text} to {step.get('output_dir') or 'the bake output folder'} "
            f"at {step.get('resolution')} px."
        )
    if kind == "boolean_op":
        cutters = ", ".join(step.get("cutters") or []) or "selected cutters"
        return (
            f"{label}: adds {step.get('operation', 'DIFFERENCE').lower()} Boolean modifiers to "
            f"{step.get('target') or target_text} using {cutters}."
        )
    if kind == "mirror_model":
        axes = ", ".join(step.get("axis") or []) or "X"
        return f"{label}: adds non-destructive Mirror modifiers on {axes} for {target_text}."
    if kind == "symmetrize_model":
        return (
            f"{label}: adds non-destructive symmetry Mirror modifiers on "
            f"{step.get('axis', 'X')} ({step.get('direction', 'POSITIVE_TO_NEGATIVE')}) for {target_text}."
        )
    if kind == "solidify_model":
        return f"{label}: adds Solidify modifiers to {target_text} with thickness {step.get('thickness')}."
    if kind == "screw_model":
        return (
            f"{label}: adds Screw modifiers to {target_text} on {step.get('axis', 'Z')} "
            f"with offset {step.get('screw_offset')}."
        )
    if kind == "organize_scene_for_production":
        return (
            f"{label}: links {_format_count('object', len(step.get('linked') or []))} into "
            f"{_format_count('production collection', len(step.get('collections') or []))} without deleting original links."
        )
    return f"{label}: {kind} affects {target_text}."

def _preview_change_report(transaction):
    steps = list((transaction or {}).get("applied_steps") or [])
    if not steps:
        return {}
    step = steps[-1]
    label = str(step.get("label") or step.get("type") or "Live preview change")
    kind = str(step.get("type") or "preview_change")
    targets = _compact_targets(step)
    target_text = ", ".join(targets[:5]) if targets else "current scene"
    if len(targets) > 5:
        target_text += f", +{len(targets) - 5} more"
    manifest = live_preview.transaction_manifest(transaction)
    rollback_scopes = manifest.get("rollback_scopes") or []
    rollback_text = ", ".join(rollback_scopes[:5]) if rollback_scopes else "none"
    expected_changes = _preview_expected_changes(step, label, kind, target_text)
    expected_with_rollback = f"{expected_changes} Rollback snapshots: {rollback_text}."
    return {
        "label": label,
        "type": kind,
        "targets": targets,
        "expected_changes": expected_with_rollback,
        "rollback_snapshot_count": int(manifest.get("snapshot_count", 0) or 0),
        "rollback_scopes": rollback_scopes,
    }

def _attach_preview_change_report(result):
    if not isinstance(result, dict) or not result.get("ok") or not result.get("transaction_id"):
        return result
    transaction = live_preview.current_transaction()
    if not transaction or transaction.get("id") != result.get("transaction_id"):
        return result
    report = _preview_change_report(transaction)
    if not report:
        return result
    enriched = dict(result)
    enriched.setdefault("expected_changes", report["expected_changes"])
    enriched.setdefault("preview_change_report", report)
    return enriched

def _maybe_auto_revert_failed_preview(context, result, txn_id_before):
    if not isinstance(result, dict) or result.get("ok", True):
        return result
    try:
        current = live_preview.current_transaction()
        if (
            current
            and current.get("status") == "pending"
            and current.get("id") != txn_id_before
        ):
            revert_result = live_preview.revert(context)
            result = dict(result)
            result["auto_reverted_preview"] = bool(revert_result.get("ok"))
            result["auto_revert_message"] = revert_result.get("message", "")
            result["auto_revert_manifest"] = revert_result.get("manifest", {})
            warning_summary = revert_result.get("rollback_warning_summary")
            if warning_summary:
                result["auto_revert_warnings"] = warning_summary
        elif current and current.get("status") == "pending" and current.get("id") == txn_id_before:
            result = dict(result)
            result["auto_reverted_preview"] = False
            result["auto_revert_message"] = "Preserved the preview transaction that existed before this failed tool call"
    except Exception as rollback_exc:
        result = dict(result)
        result["auto_reverted_preview"] = False
        result["auto_revert_message"] = f"Preview auto-revert failed: {type(rollback_exc).__name__}: {rollback_exc}"
    return result

def register():
    pass

def unregister():
    pass
