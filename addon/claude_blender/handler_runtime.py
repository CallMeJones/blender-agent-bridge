"""Execute external-agent Blender tools on the main Blender thread."""

from __future__ import annotations

import json
import re
import time
import textwrap

import bpy

from . import animation_analysis, animation_brief, animation_workflow, advanced_helpers, asset_jobs, autosave, blender_compat, context_bundle, docs_index, external_assets, helper_routing, inspection_render, lab_parity, live_preview, playblast_capture, preferences, project_files, render_jobs, script_runner, viewport_capture, world_model, tool_registry


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


def _json_result(result):
    return json.dumps(result, indent=2, sort_keys=True)


_PYTHON_FENCE_RE = re.compile(r"```(?:python|py)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
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


def _looks_like_render_job_intent(text):
    normalized = str(text or "").lower()
    if "render" not in normalized and "playblast" not in normalized and "bpy.ops.render.render" not in normalized:
        return False
    return any(term in normalized for term in _RENDER_JOB_INTENT_TERMS)


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
    "create_reveal_animation",
    "create_pulse_animation",
    "create_directed_animation_shot",
    "create_camera_dolly_animation",
    "animate_shape_key",
    "animate_material_property",
}


def _workflow_tool_parts(tool_call):
    tool_call = tool_call if isinstance(tool_call, dict) else {}
    tool = str(tool_call.get("name") or "")
    tool_args = tool_call.get("input") if isinstance(tool_call.get("input"), dict) else {}
    return tool, dict(tool_args or {})


def _execute_workflow_tool(context, tool, tool_args):
    fn = TOOL_FUNCTIONS.get(tool)
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
    subject_names = _name_list((brief or {}).get("subject_names"))
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
        playblast_result = capture_animation_playblast(
            context,
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
    fn = TOOL_FUNCTIONS.get(tool)
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
    if kind == "apply_vehicle_refinement_template":
        return (
            f"{label}: adds a vehicle detail kit around {step.get('target') or target_text} with "
            f"{_format_count('created object', len(step.get('created_objects') or []))}."
        )
    if kind in {"apply_product_refinement_template", "apply_character_refinement_template"}:
        features = ", ".join(step.get("features") or []) or "bounded production details"
        return f"{label}: applies {features} around {step.get('target') or target_text}."
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


TOOL_FUNCTIONS = tool_registry.build_handlers()
globals().update(TOOL_FUNCTIONS)


def execute_tool(context, name, args):
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return _json_result({"ok": False, "message": f"Unknown Blender tool: {name}"})
    transaction_before = live_preview.current_transaction()
    txn_id_before = (
        transaction_before["id"]
        if transaction_before and transaction_before.get("status") == "pending"
        else None
    )
    try:
        result = fn(context, args or {})
    except Exception as exc:
        result = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
    if isinstance(result, str):
        return result
    # Auto-revert a transaction this failed call opened, so the scene is not left
    # half-mutated with a stale "pending" preview. Only revert a transaction that
    # did not already exist before the call (never unwind the user's prior work).
    result = _maybe_auto_revert_failed_preview(context, result, txn_id_before)
    result = _attach_preview_change_report(result)
    return _json_result(result)


def register():
    pass


def unregister():
    pass
