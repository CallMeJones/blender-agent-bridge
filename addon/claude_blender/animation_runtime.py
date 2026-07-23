"""Animation workflow execution and repair orchestration."""

from __future__ import annotations

import json
import re
import time

import bpy

from . import animation_analysis, blender_compat, context_bundle
from .handler_runtime import _attach_preview_change_report

_ANIMATION_WORKFLOW_MARKERS = {}

_ANIMATION_WORKFLOW_TTL_SECONDS = 15 * 60

_ANIMATION_INTENT_TERMS = {
    "animate",
    "animation",
    "bounce",
    "jump",
    "keyframe",
    "keyframes",
    "pose",
    "timing",
    "arc",
    "motion arc",
    "settle",
    "squash",
    "stretch",
    "playblast",
    "f-curve",
    "fcurve",
    "block key",
    "blocking",
    "anticipation",
    "contact sliding",
}

def _animation_workflow_marker_key(context):
    scene = getattr(context, "scene", None)
    return getattr(scene, "name", "") or "active_scene"

def _mark_animation_workflow_seen(context, result=None):
    workflow = result.get("workflow") if isinstance(result, dict) and isinstance(result.get("workflow"), dict) else {}
    fallback_policy = workflow.get("script_fallback_policy") if isinstance(workflow.get("script_fallback_policy"), dict) else {}
    _ANIMATION_WORKFLOW_MARKERS[_animation_workflow_marker_key(context)] = {
        "marked_at": time.monotonic(),
        "status": str(workflow.get("status") or ""),
        "script_fallback_allowed": bool(fallback_policy.get("allowed", True)) and workflow.get("status") != "needs_clarification",
    }

def _animation_workflow_recent_context(context):
    marker = _ANIMATION_WORKFLOW_MARKERS.get(_animation_workflow_marker_key(context))
    if not marker:
        return {}
    if isinstance(marker, dict):
        marked_at = marker.get("marked_at")
    else:
        marked_at = marker
        marker = {"marked_at": marked_at, "script_fallback_allowed": True}
    if not marked_at:
        return {}
    if (time.monotonic() - float(marked_at)) > _ANIMATION_WORKFLOW_TTL_SECONDS:
        return {}
    return dict(marker)

def _animation_workflow_recently_seen(context):
    return bool(_animation_workflow_recent_context(context))

def _animation_script_fallback_recently_allowed(context):
    marker = _animation_workflow_recent_context(context)
    if not marker:
        return False
    return bool(marker.get("script_fallback_allowed", False))

def _looks_like_animation_intent(text):
    normalized = str(text or "").lower()
    for term in _ANIMATION_INTENT_TERMS:
        term_text = str(term or "").strip().lower()
        if not term_text:
            continue
        pattern = re.escape(term_text).replace(r"\ ", r"\s+")
        if re.search(rf"(?<![a-z0-9_]){pattern}(?![a-z0-9_])", normalized):
            return True
    return False

def _keyframe_summary(point):
    co = getattr(point, "co", (0.0, 0.0))
    return {
        "frame": round(float(co[0]), 4),
        "value": round(float(co[1]), 5),
        "interpolation": getattr(point, "interpolation", None),
    }

def _driver_summary(data_block, *, max_drivers=12):
    animation_data = getattr(data_block, "animation_data", None)
    drivers = list(getattr(animation_data, "drivers", []) or []) if animation_data else []
    return [
        {
            "data_path": driver.data_path,
            "array_index": int(driver.array_index),
            "expression": getattr(driver.driver, "expression", ""),
            "type": getattr(driver.driver, "type", None),
            "variables": [
                {
                    "name": variable.name,
                    "type": variable.type,
                    "targets": [
                        {
                            "id": getattr(target.id, "name", None),
                            "data_path": target.data_path,
                            "transform_type": getattr(target, "transform_type", None),
                        }
                        for target in list(variable.targets)[:4]
                    ],
                }
                for variable in list(getattr(driver.driver, "variables", []))[:8]
            ],
        }
        for driver in drivers[:max_drivers]
    ]

def _animation_data_summary(data_block, *, max_drivers=8):
    animation_data = getattr(data_block, "animation_data", None)
    if animation_data is None:
        return {"has_animation_data": False, "action": None, "driver_count": 0, "nla_track_count": 0}
    action = animation_data.action
    drivers = list(getattr(animation_data, "drivers", []) or [])
    nla_tracks = list(getattr(animation_data, "nla_tracks", []) or [])
    result = {
        "has_animation_data": True,
        "action": action.name if action else None,
        "driver_count": len(drivers),
        "nla_track_count": len(nla_tracks),
        "drivers": _driver_summary(data_block, max_drivers=max_drivers),
    }
    if action:
        frame_range = list(getattr(action, "frame_range", (0, 0)))
        result["action_frame_range"] = [round(float(value), 4) for value in frame_range]
    if nla_tracks:
        result["nla_tracks"] = [
            {
                "name": track.name,
                "mute": bool(getattr(track, "mute", False)),
                "solo": bool(getattr(track, "is_solo", False)),
                "strip_count": len(getattr(track, "strips", []) or []),
            }
            for track in nla_tracks[:12]
        ]
    return result

def _constraint_summary(constraint):
    item = {
        "name": constraint.name,
        "type": constraint.type,
        "influence": round(float(getattr(constraint, "influence", 0.0)), 5),
        "mute": bool(getattr(constraint, "mute", False)),
        "target": getattr(getattr(constraint, "target", None), "name", None),
        "subtarget": getattr(constraint, "subtarget", ""),
    }
    for attr in (
        "track_axis",
        "up_axis",
        "owner_space",
        "target_space",
        "use_curve_follow",
        "use_fixed_location",
        "offset_factor",
        "forward_axis",
    ):
        if hasattr(constraint, attr):
            value = getattr(constraint, attr)
            item[attr] = round(float(value), 5) if isinstance(value, float) else value
    return item

def _action_from(data_block):
    animation_data = getattr(data_block, "animation_data", None)
    return animation_data.action if animation_data else None

def _append_action(actions, seen, action):
    if action and action.name not in seen:
        seen.add(action.name)
        actions.append(action)

def _object_related_actions(obj):
    actions = [_action_from(obj)]
    data = getattr(obj, "data", None)
    if data:
        actions.append(_action_from(data))
    if obj.type == "MESH" and data and getattr(data, "shape_keys", None):
        actions.append(_action_from(data.shape_keys))
    for slot in obj.material_slots:
        material = slot.material
        if material:
            actions.append(_action_from(material))
            node_tree = blender_compat.node_tree(material)
            if node_tree:
                actions.append(_action_from(node_tree))
    return [action for action in actions if action]

def _action_owners(action):
    owners = []
    for obj in bpy.data.objects:
        if _action_from(obj) == action:
            owners.append({"kind": "object", "name": obj.name, "type": obj.type})
        data = getattr(obj, "data", None)
        if data and _action_from(data) == action:
            owners.append({"kind": "object_data", "object": obj.name, "name": data.name, "type": obj.type})
        if obj.type == "MESH" and data and getattr(data, "shape_keys", None) and _action_from(data.shape_keys) == action:
            owners.append({"kind": "shape_keys", "object": obj.name, "name": data.shape_keys.name})
    for material in bpy.data.materials:
        if _action_from(material) == action:
            owners.append({"kind": "material", "name": material.name})
        node_tree = blender_compat.node_tree(material)
        if node_tree and _action_from(node_tree) == action:
            owners.append({"kind": "material_node_tree", "material": material.name, "name": node_tree.name})
    return owners[:40]

def _action_summary(action, *, max_keyframes_per_curve=8):
    fcurves = context_bundle._iter_action_fcurves(action)
    frame_range = list(getattr(action, "frame_range", (0, 0)))
    return {
        "name": action.name,
        "users": int(getattr(action, "users", 0)),
        "frame_range": [round(float(value), 4) for value in frame_range],
        "fcurve_count": len(fcurves),
        "owners": _action_owners(action),
        "fcurves": [
            {
                "data_path": fcurve.data_path,
                "array_index": int(fcurve.array_index),
                "extrapolation": getattr(fcurve, "extrapolation", None),
                "mute": bool(getattr(fcurve, "mute", False)),
                "keyframe_count": len(fcurve.keyframe_points),
                "frame_range": [
                    round(float(min((point.co[0] for point in fcurve.keyframe_points), default=0.0)), 4),
                    round(float(max((point.co[0] for point in fcurve.keyframe_points), default=0.0)), 4),
                ],
                "keyframes": [
                    _keyframe_summary(point)
                    for point in list(fcurve.keyframe_points)[:max_keyframes_per_curve]
                ],
            }
            for fcurve in fcurves[:40]
        ],
    }

_WORKFLOW_GENERATION_TOOLS = {
    "select_objects",
    "set_scene_frame_range",
    "set_animation_preview_range",
    "animate_object_bounce",
    "create_progressive_bounce_animation",
    "create_turntable_animation",
    "create_camera_orbit",
    "create_reveal_animation",
    "create_pulse_animation",
    "create_camera_dolly_animation",
    "animate_shape_key",
    "animate_material_property",
}

def _missing_tool_handler(_name):
    return None

_tool_handler_lookup = _missing_tool_handler

def configure_tool_handler_lookup(lookup):
    """Inject the composed handler lookup without importing the registry here."""

    global _tool_handler_lookup
    _tool_handler_lookup = lookup

def _workflow_tool_parts(tool_call):
    tool_call = tool_call if isinstance(tool_call, dict) else {}
    tool = str(tool_call.get("name") or "")
    tool_args = tool_call.get("input") if isinstance(tool_call.get("input"), dict) else {}
    return tool, dict(tool_args or {})

def _execute_workflow_tool(context, tool, tool_args):
    fn = _tool_handler_lookup(tool)
    if fn is None:
        return {"ok": False, "message": f"Unknown Blender tool: {tool}"}
    try:
        result = fn(context, tool_args)
    except Exception as exc:
        return {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = {"ok": False, "message": result}
    if not isinstance(result, dict):
        result = {"ok": False, "message": "Tool returned an unexpected result"}
    return _attach_preview_change_report(result)

def _workflow_findings(*results):
    findings = []
    seen = set()
    for result in results:
        if isinstance(result, dict):
            for item in result.get("findings") or []:
                if not isinstance(item, dict):
                    continue
                key = (
                    str(item.get("severity") or ""),
                    str(item.get("principle") or ""),
                    str(item.get("requirement") or ""),
                    str(item.get("object") or ""),
                    str(item.get("frame") or ""),
                    str(item.get("message") or ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                findings.append(item)
    return findings

def _workflow_review(context, *, prompt, brief, timing_chart, frame_start, frame_end, capture_playblast, playblast=None):
    subject_names = animation_analysis._name_list((brief or {}).get("subject_names"))
    if not subject_names and isinstance(brief, dict):
        subject_names = [
            str(item.get("name"))
            for item in (brief.get("subjects") or [])
            if isinstance(item, dict) and item.get("name")
        ]
    principles = animation_analysis.analyze_animation_principles(
        context,
        object_names=subject_names,
        prompt=prompt,
        brief=brief,
        timing_chart=timing_chart,
        frame_start=frame_start,
        frame_end=frame_end,
    )
    comparison = animation_analysis.compare_animation_to_brief(
        context,
        brief=brief,
        prompt=prompt,
        subject_names=subject_names,
        frame_start=frame_start,
        frame_end=frame_end,
    )
    playblast_result = {}
    review_playblast = playblast if isinstance(playblast, dict) else None
    if capture_playblast:
        playblast_result = _execute_workflow_tool(
            context,
            "capture_animation_playblast",
            {
                "frame_start": frame_start,
                "frame_end": frame_end,
                "max_frames": 12,
                "brief": (brief or {}).get("user_visible_interpretation") or prompt,
            },
        )
        if isinstance(playblast_result.get("playblast"), dict):
            review_playblast = playblast_result["playblast"]
    if review_playblast is None:
        review_playblast = {
            "available": False,
            "playblast_id": "workflow-no-playblast",
            "frames": [],
            "sampled_frames": [],
        }
    visual_review = animation_analysis.review_playblast_against_brief(
        context,
        playblast=review_playblast,
        brief=brief,
        prompt=prompt,
    )
    findings = _workflow_findings(principles, comparison, visual_review)
    repair_plan = animation_analysis.repair_animation_from_findings(context, findings=findings, brief=brief)
    return {
        "principles": principles,
        "comparison": comparison,
        "playblast_capture": playblast_result,
        "visual_review": visual_review,
        "findings": findings,
        "finding_count": len(findings),
        "repair_plan": repair_plan,
    }

_REPAIR_LOOP_READ_ONLY_TOOLS = {
    "analyze_camera_framing",
    "capture_animation_playblast",
    "capture_object_inspection_renders",
    "create_timing_chart",
    "get_shape_key_details",
    "get_simulation_details",
    "inspect_simulation_bake",
    "get_rig_pose_library_details",
    "get_rigging_details",
    "review_playblast_against_brief",
    "review_inspection_renders_against_brief",
    "repair_animation_from_findings",
}

_REPAIR_LOOP_DEFAULT_TOOLS = {
    "analyze_camera_framing",
    "capture_animation_playblast",
    "capture_object_inspection_renders",
    "create_timing_chart",
    "set_action_interpolation",
    "set_pose_hold",
    "set_rig_pose_hold",
    "set_rig_custom_property_keyframes",
    "apply_rig_pose_from_action",
    "apply_rig_pose_marker",
    "apply_rig_action_clip",
    "offset_rig_limb_controls",
    "add_breakdown_pose",
    "block_key_poses",
    "create_camera_orbit",
    "animate_object_bounce",
    "create_progressive_bounce_animation",
    "animate_shape_key",
    "animate_material_property",
    "set_scene_frame_range",
    "retime_actions",
    "get_shape_key_details",
    "get_simulation_details",
    "inspect_simulation_bake",
    "get_rigging_details",
}

def _brief_frame_range(context, brief):
    timing = (brief or {}).get("timing") if isinstance(brief, dict) else {}
    if not isinstance(timing, dict):
        timing = {}
    return (
        int(timing.get("frame_start", context.scene.frame_start)),
        int(timing.get("frame_end", context.scene.frame_end)),
    )

def _repair_loop_brief_text(brief, prompt):
    text = str((brief or {}).get("user_visible_interpretation") or prompt or "").strip()
    return text[:1000]

def _repair_operation_parts(operation):
    operation = operation if isinstance(operation, dict) else {}
    tool_call = operation.get("tool_call") if isinstance(operation.get("tool_call"), dict) else {}
    tool = str(tool_call.get("name") or operation.get("tool") or "")
    tool_args = tool_call.get("input") if isinstance(tool_call.get("input"), dict) else None
    if tool_args is None:
        tool_args = operation.get("arguments") if isinstance(operation.get("arguments"), dict) else {}
    return tool, dict(tool_args or {})

def _repair_operation_key(tool, tool_args):
    return (tool, json.dumps(tool_args, sort_keys=True, default=str))

def _repair_operation_mutates(tool, operation):
    return tool not in _REPAIR_LOOP_READ_ONLY_TOOLS

def _repair_operation_blocker(tool, tool_args):
    if not tool:
        return "repair operation has no tool name"
    if tool == "review_playblast_against_brief":
        return "review operations are handled by the loop itself"
    if tool == "repair_animation_from_findings":
        return "repair planning operations are handled by the loop itself"
    if tool == "block_key_poses" and not tool_args.get("poses"):
        return "block_key_poses requires explicit poses; this repair needs a planning pass first"
    if tool in {"set_pose_hold", "set_action_interpolation", "add_breakdown_pose"} and not tool_args.get("object_names"):
        return f"{tool} requires object_names"
    if tool == "set_rig_pose_hold" and not tool_args.get("armature_name"):
        return "set_rig_pose_hold requires armature_name"
    if tool == "set_rig_custom_property_keyframes":
        if not tool_args.get("armature_name"):
            return "set_rig_custom_property_keyframes requires armature_name"
        if not tool_args.get("property_targets"):
            return "set_rig_custom_property_keyframes requires property_targets"
    if tool == "apply_rig_pose_from_action":
        if not tool_args.get("armature_name"):
            return "apply_rig_pose_from_action requires armature_name"
        if not tool_args.get("action_name"):
            return "apply_rig_pose_from_action requires action_name"
    if tool == "apply_rig_pose_marker":
        if not tool_args.get("armature_name"):
            return "apply_rig_pose_marker requires armature_name"
        if not (tool_args.get("action_name") or tool_args.get("pose_marker")):
            return "apply_rig_pose_marker requires action_name or pose_marker"
    if tool == "apply_rig_action_clip":
        if not tool_args.get("armature_name"):
            return "apply_rig_action_clip requires armature_name"
        if not tool_args.get("action_name"):
            return "apply_rig_action_clip requires action_name"
    if tool == "offset_rig_limb_controls":
        if not tool_args.get("armature_name"):
            return "offset_rig_limb_controls requires armature_name"
        if not (tool_args.get("control_offsets") or tool_args.get("bone_names") or tool_args.get("property_targets")):
            return "offset_rig_limb_controls requires control_offsets, bone_names, or property_targets"
    if tool == "capture_object_inspection_renders" and not tool_args.get("object_names"):
        return "capture_object_inspection_renders requires object_names"
    if tool in {"animate_object_bounce", "create_progressive_bounce_animation"} and not tool_args.get("object_name"):
        return f"{tool} requires object_name"
    if tool == "animate_shape_key" and not tool_args.get("object_name"):
        return "animate_shape_key requires object_name"
    if tool == "animate_material_property" and not (tool_args.get("material_name") or tool_args.get("object_name")):
        return "animate_material_property requires material_name or object_name"
    if tool == "retime_actions" and not (tool_args.get("object_names") or tool_args.get("action_names")):
        return "retime_actions requires object_names or action_names"
    if tool == "create_camera_orbit" and not tool_args.get("target_name"):
        return "create_camera_orbit requires target_name"
    return ""

def _execute_repair_tool(context, tool, tool_args):
    fn = _tool_handler_lookup(tool)
    if fn is None:
        return {"ok": False, "message": f"Unknown Blender tool: {tool}"}
    try:
        result = fn(context, tool_args)
    except Exception as exc:
        return {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = {"ok": False, "message": result}
    if not isinstance(result, dict):
        result = {"ok": False, "message": "Tool returned an unexpected result"}
    return _attach_preview_change_report(result)

def _repair_loop_review(context, *, playblast=None, brief=None, prompt=""):
    return animation_analysis.review_playblast_against_brief(
        context,
        playblast=playblast if isinstance(playblast, dict) else None,
        brief=brief if isinstance(brief, dict) else None,
        prompt=str(prompt or ""),
    )



def register():

    pass





def unregister():

    pass
