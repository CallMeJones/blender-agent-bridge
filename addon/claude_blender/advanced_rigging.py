"""Advanced Blender helpers for rigging simulation."""



from __future__ import annotations

import re

import bpy

from . import live_preview

from .advanced_support import (
    KEYFRAME_INTERPOLATIONS,
    TRANSFORM_PATH_ALIASES,
    _coerce_vector,
    _prepare_transform_action_for_edit,
    _resolve_edit_objects,
    _set_action_interpolation,
)



def _prepare_id_action_for_edit(data_block, collection_name):
    live_preview._record_id_animation(data_block, collection_name)
    action = data_block.animation_data.action if data_block.animation_data and data_block.animation_data.action else None
    if action:
        transaction = live_preview.current_transaction()
        if not (transaction and f"created:action:{action.name}" in transaction.get("before_state", {})):
            live_preview._record_action_edit(action)
        return action, False
    animation_data = data_block.animation_data_create()
    action = bpy.data.actions.new(f"{data_block.name} Agent Bridge Property Preview Action")
    animation_data.action = action
    live_preview._record_created_id("action", action.name)
    return action, True

RIG_POSE_PATHS = ("location", "rotation_euler", "rotation_quaternion", "rotation_axis_angle", "scale")

RIG_POSE_PATH_ALIASES = {
    **TRANSFORM_PATH_ALIASES,
    "quaternion": "rotation_quaternion",
    "rotation_quaternion": "rotation_quaternion",
    "axis_angle": "rotation_axis_angle",
    "rotation_axis_angle": "rotation_axis_angle",
}

def _pose_bone_rotation_path(pose_bone):
    mode = str(getattr(pose_bone, "rotation_mode", "") or "").upper()
    if mode == "QUATERNION":
        return "rotation_quaternion"
    if mode == "AXIS_ANGLE":
        return "rotation_axis_angle"
    return "rotation_euler"

def _normalize_rig_pose_paths(paths=None, *, pose_bone=None):
    normalized = []
    for path in paths or []:
        key = RIG_POSE_PATH_ALIASES.get(str(path).strip().lower())
        if key in RIG_POSE_PATHS and key not in normalized:
            normalized.append(key)
    return normalized or ["location", _pose_bone_rotation_path(pose_bone)]

def _pose_path_values(pose_bone, path):
    return tuple(float(value) for value in getattr(pose_bone, path))

_POSE_BONE_DATA_PATH_RE = re.compile(r'^pose\.bones\["((?:\\.|[^"])*)"\]\.([A-Za-z_][A-Za-z0-9_]*)$')

def _unescape_data_path_name(name):
    return str(name or "").replace('\\"', '"').replace("\\\\", "\\")

def _parse_pose_bone_data_path(data_path):
    match = _POSE_BONE_DATA_PATH_RE.match(str(data_path or ""))
    if not match:
        return "", ""
    return _unescape_data_path_name(match.group(1)), match.group(2)

def _action_frame_range(action):
    frames = sorted(
        {
            float(point.co.x)
            for fcurve in (live_preview._iter_action_fcurves(action) if action else [])
            for point in getattr(fcurve, "keyframe_points", [])
        }
    )
    if not frames:
        return None, None
    return frames[0], frames[-1]

def _action_pose_marker_frame(action, pose_marker=""):
    pose_marker = str(pose_marker or "").strip()
    markers = list(getattr(action, "pose_markers", []) or []) if action else []
    if pose_marker:
        for marker in markers:
            if marker.name == pose_marker or marker.name.lower() == pose_marker.lower():
                return int(marker.frame), marker.name, ""
        return None, "", f"Pose marker not found on action {action.name}: {pose_marker}"
    if markers:
        marker = markers[0]
        return int(marker.frame), marker.name, ""
    start, _end = _action_frame_range(action)
    if start is None:
        return None, "", f"Action has no keyframes: {action.name if action else ''}"
    return int(round(start)), "", ""

def _pose_action_channels(action, armature, *, bone_names=None, paths=None):
    requested_bones = {str(name) for name in (bone_names or []) if str(name).strip()}
    requested_paths = {
        RIG_POSE_PATH_ALIASES.get(str(path).strip().lower(), str(path).strip())
        for path in (paths or [])
        if str(path).strip()
    }
    requested_paths = {path for path in requested_paths if path in RIG_POSE_PATHS}
    channels = {}
    bones_seen = set()
    for fcurve in live_preview._iter_action_fcurves(action):
        bone_name, path = _parse_pose_bone_data_path(fcurve.data_path)
        if not bone_name or path not in RIG_POSE_PATHS:
            continue
        if requested_bones and bone_name not in requested_bones:
            continue
        if requested_paths and path not in requested_paths:
            continue
        pose_bone = armature.pose.bones.get(bone_name) if armature.pose else None
        if not pose_bone:
            continue
        bones_seen.add(bone_name)
        channels.setdefault((bone_name, path), {})[int(fcurve.array_index)] = fcurve
    missing_bones = sorted(requested_bones - bones_seen) if requested_bones else []
    return channels, missing_bones

def _action_pose_marker_summaries(action):
    return [
        {"name": marker.name, "frame": int(marker.frame)}
        for marker in list(getattr(action, "pose_markers", []) or [])
    ]

def _rig_pose_action_candidate(action, armature, *, bone_names=None, paths=None):
    channels, missing_bones = _pose_action_channels(action, armature, bone_names=bone_names, paths=paths)
    bones = sorted({bone_name for bone_name, _path in channels})
    channel_paths = sorted({path for _bone_name, path in channels})
    frame_start, frame_end = _action_frame_range(action)
    pose_markers = _action_pose_marker_summaries(action)
    applicable = bool(channels)
    likely_pose_library = bool(
        pose_markers
        or getattr(action, "asset_data", None)
        or "pose" in action.name.lower()
        or armature.name.lower() in action.name.lower()
    )
    return {
        "name": action.name,
        "applicable": applicable,
        "likely_pose_library": likely_pose_library,
        "asset_action": bool(getattr(action, "asset_data", None)),
        "users": int(getattr(action, "users", 0) or 0),
        "frame_range": [frame_start, frame_end] if frame_start is not None else [],
        "pose_markers": pose_markers,
        "matched_bones": bones,
        "matched_bone_count": len(bones),
        "matched_channel_paths": channel_paths,
        "matched_channel_count": len(channels),
        "missing_bone_names": missing_bones,
    }

def get_rig_pose_library_details(
    context,
    *,
    armature_name="",
    action_names=None,
    bone_names=None,
    paths=None,
    max_actions=20,
):
    armature = _resolve_armature_for_pose_hold(context, armature_name)
    if armature is None:
        return {"ok": False, "message": "An armature object is required for rig pose-library details"}
    requested_actions = [str(name) for name in action_names or [] if str(name).strip()]
    missing_actions = []
    if requested_actions:
        actions = []
        for name in requested_actions:
            action = bpy.data.actions.get(name)
            if action:
                actions.append(action)
            else:
                missing_actions.append(name)
    else:
        actions = list(bpy.data.actions)
    candidates = [
        _rig_pose_action_candidate(action, armature, bone_names=bone_names, paths=paths)
        for action in actions
    ]
    if not requested_actions:
        candidates = [
            item
            for item in candidates
            if item["applicable"] or item["likely_pose_library"]
        ]
    candidates.sort(
        key=lambda item: (
            item["applicable"],
            item["matched_bone_count"],
            bool(item["pose_markers"]),
            item["asset_action"],
            item["users"],
        ),
        reverse=True,
    )
    max_actions = max(1, min(100, int(max_actions or 20)))
    candidates = candidates[:max_actions]
    suggested_calls = []
    for candidate in candidates:
        if candidate["pose_markers"]:
            for marker in candidate["pose_markers"][:8]:
                suggested_calls.append(
                    {
                        "tool": "apply_rig_pose_marker",
                        "arguments": {
                            "armature_name": armature.name,
                            "action_name": candidate["name"],
                            "pose_marker": marker["name"],
                            "target_frame": int(context.scene.frame_current),
                        },
                    }
                )
        if candidate["frame_range"]:
            suggested_calls.append(
                {
                    "tool": "apply_rig_action_clip",
                    "arguments": {
                        "armature_name": armature.name,
                        "action_name": candidate["name"],
                        "frame_start": int(context.scene.frame_current),
                    },
                }
            )
    return {
        "ok": True,
        "message": f"Found {len(candidates)} rig pose/action candidate(s)",
        "armature": armature.name,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "missing_action_names": missing_actions,
        "suggested_tool_calls": suggested_calls[:50],
    }

def _resolve_pose_marker_source_action(armature, *, action_name="", pose_marker="", bone_names=None, paths=None):
    action_name = str(action_name or "").strip()
    pose_marker = str(pose_marker or "").strip()
    if action_name:
        action = bpy.data.actions.get(action_name)
        if action is None:
            return None, [], f"Action not found: {action_name}"
        candidate = _rig_pose_action_candidate(action, armature, bone_names=bone_names, paths=paths)
        return action, [candidate], ""
    if not pose_marker:
        return None, [], "action_name or pose_marker is required"
    candidates = []
    for action in bpy.data.actions:
        frame, marker_name, marker_error = _action_pose_marker_frame(action, pose_marker)
        if marker_error or frame is None:
            continue
        candidate = _rig_pose_action_candidate(action, armature, bone_names=bone_names, paths=paths)
        if not candidate["applicable"]:
            continue
        candidate["resolved_marker"] = marker_name
        candidate["resolved_frame"] = int(frame)
        candidates.append(candidate)
    candidates.sort(
        key=lambda item: (
            item["matched_bone_count"],
            item["matched_channel_count"],
            item["asset_action"],
            item["users"],
        ),
        reverse=True,
    )
    if not candidates:
        return None, [], f"No applicable rig action has pose marker: {pose_marker}"
    return bpy.data.actions.get(candidates[0]["name"]), candidates, ""

def _prepare_rig_application_action(armature, source_action=None):
    current_action = armature.animation_data.action if armature.animation_data and armature.animation_data.action else None
    if source_action is not None and current_action == source_action:
        live_preview._record_object_animation(armature)
        action = bpy.data.actions.new(name=f"{armature.name} Agent Bridge Rig Pose Preview Action")
        armature.animation_data_create().action = action
        live_preview._record_created_id("action", action.name)
        return action, True
    return _prepare_transform_action_for_edit(armature)

def _resolve_armature_for_pose_hold(context, armature_name=""):
    if armature_name:
        armature = bpy.data.objects.get(str(armature_name))
        return armature if armature and armature.type == "ARMATURE" else None
    active = context.active_object
    if active and active.type == "ARMATURE":
        return active
    for obj in context.selected_objects:
        if obj and obj.type == "ARMATURE":
            return obj
    return None

def _default_control_bone_names(armature, *, maximum=8):
    result = []
    pose_bones = list(getattr(getattr(armature, "pose", None), "bones", []) or [])
    for pose_bone in pose_bones:
        data_bone = armature.data.bones.get(pose_bone.name) if armature.data else None
        lower = pose_bone.name.lower()
        if (
            "ctrl" in lower
            or "control" in lower
            or "ik" in lower
            or "fk" in lower
            or "target" in lower
            or getattr(pose_bone, "custom_shape", None)
            or (data_bone and not data_bone.use_deform)
        ):
            result.append(pose_bone.name)
        if len(result) >= maximum:
            break
    if not result:
        result = [pose_bone.name for pose_bone in pose_bones[:maximum]]
    return result

def set_rig_pose_hold(
    context,
    *,
    armature_name="",
    bone_names=None,
    frame=None,
    hold_frames=4,
    paths=None,
    interpolation="CONSTANT",
    label="Set rig pose hold",
):
    armature = _resolve_armature_for_pose_hold(context, armature_name)
    if armature is None:
        return {"ok": False, "message": "An armature object is required for rig pose hold"}
    if armature.pose is None:
        return {"ok": False, "message": f"Armature has no pose bones: {armature.name}"}
    requested_bones = [str(name) for name in bone_names or [] if str(name).strip()]
    if not requested_bones:
        requested_bones = _default_control_bone_names(armature)
    pose_bones = []
    missing_bones = []
    for name in requested_bones:
        pose_bone = armature.pose.bones.get(name)
        if pose_bone:
            pose_bones.append(pose_bone)
        else:
            missing_bones.append(name)
    if not pose_bones:
        return {
            "ok": False,
            "message": "No matching pose bones found for rig pose hold",
            "armature": armature.name,
            "missing_bone_names": missing_bones,
        }

    frame = int(frame if frame is not None else context.scene.frame_current)
    hold_frames = max(1, int(hold_frames or 1))
    hold_frame = frame + hold_frames
    interpolation = str(interpolation or "CONSTANT").upper()

    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame)
    scene.frame_end = max(scene.frame_end, hold_frame)
    scene.frame_set(frame)
    action, created_action = _prepare_transform_action_for_edit(armature)
    keyed = []
    for pose_bone in pose_bones:
        live_preview._record_pose_bone_transform(armature, pose_bone)
        keyed_paths = []
        values_by_path = {}
        active_paths = _normalize_rig_pose_paths(paths, pose_bone=pose_bone)
        for path in active_paths:
            values = _pose_path_values(pose_bone, path)
            for key_frame in (frame, hold_frame):
                setattr(pose_bone, path, values)
                pose_bone.keyframe_insert(data_path=path, frame=key_frame)
            keyed_paths.append(path)
            values_by_path[path] = [round(float(value), 6) for value in values]
        keyed.append(
            {
                "armature": armature.name,
                "bone": pose_bone.name,
                "action": action.name,
                "created_action": created_action,
                "frame": frame,
                "hold_frame": hold_frame,
                "hold_frames": hold_frames,
                "paths": keyed_paths,
                "values": values_by_path,
            }
        )
    _set_action_interpolation(action, interpolation)
    scene.frame_set(frame)
    transaction["applied_steps"].append(
        {
            "type": "set_rig_pose_hold",
            "label": label,
            "armature": armature.name,
            "bones": [item["bone"] for item in keyed],
            "frame": frame,
            "hold_frame": hold_frame,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Set {hold_frames}-frame rig hold from frame {frame} for {len(keyed)} control bone(s)",
        "armature": armature.name,
        "bones": keyed,
        "missing_bone_names": missing_bones,
        "transaction_id": transaction["id"],
    }

def _custom_property_data_path(property_name):
    escaped = str(property_name).replace("\\", "\\\\").replace('"', '\\"')
    return f'["{escaped}"]'

def _coerce_scalar_custom_property(current, value):
    if value is None:
        value = current
    if isinstance(current, bool):
        return bool(value), None
    if isinstance(current, int) and not isinstance(current, bool):
        try:
            return int(value), None
        except (TypeError, ValueError):
            return None, f"Value {value!r} cannot be coerced to int"
    if isinstance(current, float):
        try:
            return float(value), None
        except (TypeError, ValueError):
            return None, f"Value {value!r} cannot be coerced to float"
    return None, f"Only existing bool, int, and float rig custom properties can be keyed; got {type(current).__name__}"

def _resolve_rig_property_owner(armature, target):
    owner_type = str((target or {}).get("owner_type") or "").strip()
    owner_name = str((target or {}).get("owner_name") or "").strip()
    property_name = str((target or {}).get("property_name") or "").strip()
    if not owner_type or not property_name:
        return None, owner_type, owner_name, property_name, "owner_type and property_name are required"
    if owner_type == "object":
        if owner_name and owner_name != armature.name:
            return None, owner_type, owner_name, property_name, f"Object owner must be the target armature: {armature.name}"
        return armature, owner_type, armature.name, property_name, ""
    if owner_type == "armature_data":
        data = armature.data
        if owner_name and data and owner_name != data.name:
            return None, owner_type, owner_name, property_name, f"Armature-data owner must be {data.name}"
        return data, owner_type, data.name if data else owner_name, property_name, ""
    if owner_type == "pose_bone":
        pose_bone = armature.pose.bones.get(owner_name) if armature.pose else None
        if not pose_bone:
            return None, owner_type, owner_name, property_name, f"Pose bone not found: {owner_name}"
        return pose_bone, owner_type, owner_name, property_name, ""
    return None, owner_type, owner_name, property_name, f"Unsupported rig property owner_type: {owner_type}"

def set_rig_custom_property_keyframes(
    context,
    *,
    armature_name="",
    property_targets=None,
    frame=None,
    hold_frames=4,
    interpolation="CONSTANT",
    label="Set rig custom property keyframes",
):
    armature = _resolve_armature_for_pose_hold(context, armature_name)
    if armature is None:
        return {"ok": False, "message": "An armature object is required for rig custom property keyframes"}
    targets = [target for target in (property_targets or []) if isinstance(target, dict)]
    if not targets:
        return {"ok": False, "message": "property_targets must contain at least one custom property target"}
    frame = int(frame if frame is not None else context.scene.frame_current)
    hold_frames = max(1, int(hold_frames or 1))
    hold_frame = frame + hold_frames
    interpolation = str(interpolation or "CONSTANT").upper()
    prepared = []
    missing = []
    for target in targets:
        owner, owner_type, owner_name, property_name, error = _resolve_rig_property_owner(armature, target)
        if error:
            missing.append({"owner_type": owner_type, "owner_name": owner_name, "property_name": property_name, "error": error})
            continue
        if property_name not in owner:
            missing.append(
                {
                    "owner_type": owner_type,
                    "owner_name": owner_name,
                    "property_name": property_name,
                    "error": "custom property not found",
                }
            )
            continue
        value, value_error = _coerce_scalar_custom_property(owner.get(property_name), target.get("value"))
        if value_error:
            missing.append(
                {
                    "owner_type": owner_type,
                    "owner_name": owner_name,
                    "property_name": property_name,
                    "error": value_error,
                }
            )
            continue
        prepared.append((owner, owner_type, owner_name, property_name, value))
    if not prepared:
        return {
            "ok": False,
            "message": "No rig custom properties were keyed",
            "armature": armature.name,
            "missing_property_targets": missing,
        }
    transaction = live_preview.begin(label, context)
    keyed = []
    actions = set()
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame)
    scene.frame_end = max(scene.frame_end, hold_frame)
    scene.frame_set(frame)

    for owner, owner_type, owner_name, property_name, value in prepared:
        live_preview._record_id_property(
            owner_type,
            owner_name,
            property_name,
            armature_name=armature.name if owner_type == "pose_bone" else "",
        )
        if owner_type == "armature_data":
            action, created_action = _prepare_id_action_for_edit(owner, "armatures")
        else:
            action, created_action = _prepare_transform_action_for_edit(armature)
        actions.add(action)
        data_path = _custom_property_data_path(property_name)
        for key_frame in (frame, hold_frame):
            owner[property_name] = value
            owner.keyframe_insert(data_path=data_path, frame=key_frame)
        keyed.append(
            {
                "armature": armature.name,
                "owner_type": owner_type,
                "owner_name": owner_name,
                "property_name": property_name,
                "value": value,
                "value_type": type(value).__name__,
                "frame": frame,
                "hold_frame": hold_frame,
                "hold_frames": hold_frames,
                "action": action.name if action else "",
                "created_action": bool(created_action),
                "data_path": data_path,
            }
        )
    for action in actions:
        _set_action_interpolation(action, interpolation)
    scene.frame_set(frame)
    transaction["applied_steps"].append(
        {
            "type": "set_rig_custom_property_keyframes",
            "label": label,
            "armature": armature.name,
            "keyed_count": len(keyed),
            "frame": frame,
            "hold_frame": hold_frame,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Keyed {len(keyed)} rig custom propert{'y' if len(keyed) == 1 else 'ies'}",
        "armature": armature.name,
        "keyed_properties": keyed,
        "missing_property_targets": missing,
        "transaction_id": transaction["id"],
    }

def apply_rig_pose_from_action(
    context,
    *,
    armature_name="",
    action_name="",
    pose_marker="",
    source_frame=None,
    target_frame=None,
    hold_frames=4,
    bone_names=None,
    paths=None,
    key_pose=True,
    interpolation="CONSTANT",
    label="Apply rig pose from action",
):
    armature = _resolve_armature_for_pose_hold(context, armature_name)
    if armature is None:
        return {"ok": False, "message": "An armature object is required for rig pose application"}
    if armature.pose is None:
        return {"ok": False, "message": f"Armature has no pose bones: {armature.name}"}
    action = bpy.data.actions.get(str(action_name or ""))
    if action is None:
        return {"ok": False, "message": f"Action not found: {action_name}", "armature": armature.name}
    if source_frame is None:
        source_frame, resolved_marker, marker_error = _action_pose_marker_frame(action, pose_marker)
        if marker_error:
            return {"ok": False, "message": marker_error, "armature": armature.name, "action": action.name}
    else:
        source_frame = int(source_frame)
        resolved_marker = str(pose_marker or "")
    target_frame = int(target_frame if target_frame is not None else context.scene.frame_current)
    hold_frames = max(0, int(hold_frames or 0))
    hold_frame = target_frame + hold_frames
    channels, missing_bones = _pose_action_channels(action, armature, bone_names=bone_names, paths=paths)
    if not channels:
        return {
            "ok": False,
            "message": "No matching pose-bone channels found in source action",
            "armature": armature.name,
            "action": action.name,
            "missing_bone_names": missing_bones,
        }

    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    if key_pose:
        scene.frame_start = min(scene.frame_start, target_frame)
        scene.frame_end = max(scene.frame_end, hold_frame)
        target_action, created_action = _prepare_rig_application_action(armature, source_action=action)
    else:
        target_action = None
        created_action = False
    scene.frame_set(target_frame)

    applied = []
    for bone_name in sorted({item[0] for item in channels}):
        pose_bone = armature.pose.bones.get(bone_name)
        if not pose_bone:
            continue
        live_preview._record_pose_bone_transform(armature, pose_bone)
        keyed_paths = []
        values_by_path = {}
        paths_for_bone = sorted(path for (candidate_bone, path) in channels if candidate_bone == bone_name)
        for path in paths_for_bone:
            fcurves = channels[(bone_name, path)]
            fallback = _pose_path_values(pose_bone, path)
            values = []
            for index, fallback_value in enumerate(fallback):
                fcurve = fcurves.get(index)
                values.append(float(fcurve.evaluate(source_frame)) if fcurve else float(fallback_value))
            setattr(pose_bone, path, values)
            if key_pose:
                pose_bone.keyframe_insert(data_path=path, frame=target_frame)
                if hold_frames:
                    pose_bone.keyframe_insert(data_path=path, frame=hold_frame)
                keyed_paths.append(path)
            values_by_path[path] = [round(float(value), 6) for value in values]
        applied.append(
            {
                "bone": bone_name,
                "paths": paths_for_bone,
                "keyed_paths": keyed_paths,
                "values": values_by_path,
            }
        )
    if key_pose and target_action:
        _set_action_interpolation(target_action, interpolation)
    scene.frame_set(target_frame)
    transaction["applied_steps"].append(
        {
            "type": "apply_rig_pose_from_action",
            "label": label,
            "armature": armature.name,
            "source_action": action.name,
            "pose_marker": resolved_marker,
            "source_frame": int(source_frame),
            "target_frame": target_frame,
            "hold_frame": hold_frame if hold_frames else target_frame,
            "bone_count": len(applied),
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Applied rig pose from action {action.name} to {len(applied)} bone(s)",
        "armature": armature.name,
        "source_action": action.name,
        "pose_marker": resolved_marker,
        "source_frame": int(source_frame),
        "target_frame": target_frame,
        "hold_frame": hold_frame if hold_frames else target_frame,
        "hold_frames": hold_frames,
        "key_pose": bool(key_pose),
        "target_action": target_action.name if target_action else "",
        "created_action": bool(created_action),
        "applied_bones": applied,
        "missing_bone_names": missing_bones,
        "transaction_id": transaction["id"],
    }

def apply_rig_pose_marker(
    context,
    *,
    armature_name="",
    action_name="",
    pose_marker="",
    target_frame=None,
    hold_frames=4,
    bone_names=None,
    paths=None,
    key_pose=True,
    interpolation="CONSTANT",
    label="Apply rig pose marker",
):
    armature = _resolve_armature_for_pose_hold(context, armature_name)
    if armature is None:
        return {"ok": False, "message": "An armature object is required for rig pose-marker application"}
    action, candidates, error = _resolve_pose_marker_source_action(
        armature,
        action_name=action_name,
        pose_marker=pose_marker,
        bone_names=bone_names,
        paths=paths,
    )
    if error:
        return {"ok": False, "message": error, "armature": armature.name, "candidates": candidates}
    result = apply_rig_pose_from_action(
        context,
        armature_name=armature.name,
        action_name=action.name,
        pose_marker=pose_marker,
        target_frame=target_frame,
        hold_frames=hold_frames,
        bone_names=bone_names,
        paths=paths,
        key_pose=key_pose,
        interpolation=interpolation,
        label=label,
    )
    if isinstance(result, dict):
        result.setdefault("resolved_source_action", action.name)
        result.setdefault("source_action_candidates", candidates[:10])
    return result

def apply_rig_action_clip(
    context,
    *,
    armature_name="",
    action_name="",
    frame_start=None,
    frame_end=None,
    source_frame_start=None,
    source_frame_end=None,
    interpolation="",
    label="Apply rig action clip",
):
    armature = _resolve_armature_for_pose_hold(context, armature_name)
    if armature is None:
        return {"ok": False, "message": "An armature object is required for rig action application"}
    source_action = bpy.data.actions.get(str(action_name or ""))
    if source_action is None:
        return {"ok": False, "message": f"Action not found: {action_name}", "armature": armature.name}
    source_start, source_end = _action_frame_range(source_action)
    if source_start is None or source_end is None:
        return {"ok": False, "message": f"Action has no keyframes: {source_action.name}", "armature": armature.name}
    source_start = float(source_frame_start if source_frame_start is not None else source_start)
    source_end = float(source_frame_end if source_frame_end is not None else source_end)
    if source_end < source_start:
        source_start, source_end = source_end, source_start
    frame_start = int(frame_start if frame_start is not None else context.scene.frame_current)
    source_duration = max(0.0, source_end - source_start)
    frame_end = int(frame_end if frame_end is not None else round(frame_start + source_duration))
    if frame_end < frame_start:
        frame_start, frame_end = frame_end, frame_start
    target_duration = max(0.0, float(frame_end - frame_start))
    scale = (target_duration / source_duration) if source_duration > 0 else 1.0

    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    live_preview._record_object_animation(armature)
    applied_action = source_action.copy()
    applied_action.name = f"{armature.name} {source_action.name} Applied Preview"
    live_preview._record_created_id("action", applied_action.name)
    for fcurve in live_preview._iter_action_fcurves(applied_action):
        for point in getattr(fcurve, "keyframe_points", []):
            for attr in ("co", "handle_left", "handle_right"):
                vec = getattr(point, attr)
                vec.x = frame_start + (float(vec.x) - source_start) * scale
        fcurve.update()
    if interpolation and str(interpolation).upper() in KEYFRAME_INTERPOLATIONS:
        _set_action_interpolation(applied_action, str(interpolation).upper())
    armature.animation_data_create().action = applied_action
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, frame_end)
    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {
            "type": "apply_rig_action_clip",
            "label": label,
            "armature": armature.name,
            "source_action": source_action.name,
            "applied_action": applied_action.name,
            "frame_start": frame_start,
            "frame_end": frame_end,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Applied action clip {source_action.name} to {armature.name}",
        "armature": armature.name,
        "source_action": source_action.name,
        "applied_action": applied_action.name,
        "frame_start": frame_start,
        "frame_end": frame_end,
        "source_frame_start": source_start,
        "source_frame_end": source_end,
        "retime_scale": round(float(scale), 6),
        "transaction_id": transaction["id"],
    }

def _offset_target_from_bone_names(bone_names, *, location_delta=None, rotation_delta=None, scale_multiplier=None):
    result = []
    for bone_name in bone_names or []:
        item = {"bone_name": str(bone_name)}
        if location_delta is not None:
            item["location_delta"] = location_delta
        if rotation_delta is not None:
            item["rotation_delta"] = rotation_delta
        if scale_multiplier is not None:
            item["scale_multiplier"] = scale_multiplier
        result.append(item)
    return result

def offset_rig_limb_controls(
    context,
    *,
    armature_name="",
    control_offsets=None,
    bone_names=None,
    location_delta=None,
    rotation_delta=None,
    scale_multiplier=None,
    property_targets=None,
    frame=None,
    hold_frames=4,
    interpolation="BEZIER",
    label="Offset rig limb controls",
):
    armature = _resolve_armature_for_pose_hold(context, armature_name)
    if armature is None:
        return {"ok": False, "message": "An armature object is required for rig limb control offsets"}
    offsets = [item for item in (control_offsets or []) if isinstance(item, dict)]
    if not offsets and bone_names:
        offsets = _offset_target_from_bone_names(
            bone_names,
            location_delta=location_delta,
            rotation_delta=rotation_delta,
            scale_multiplier=scale_multiplier,
        )
    property_targets = [target for target in (property_targets or []) if isinstance(target, dict)]
    if not offsets and not property_targets:
        return {"ok": False, "message": "control_offsets, bone_names, or property_targets are required"}
    frame = int(frame if frame is not None else context.scene.frame_current)
    hold_frames = max(0, int(hold_frames or 0))
    hold_frame = frame + hold_frames
    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame)
    scene.frame_end = max(scene.frame_end, hold_frame)
    property_result = {}
    if property_targets:
        property_result = set_rig_custom_property_keyframes(
            context,
            armature_name=armature.name,
            property_targets=property_targets,
            frame=frame,
            hold_frames=max(1, hold_frames or 1),
            interpolation="CONSTANT",
            label=label,
        )
    action = None
    created_action = False
    applied = []
    missing = []
    scene.frame_set(frame)
    for offset in offsets:
        bone_name = str(offset.get("bone_name") or "").strip()
        pose_bone = armature.pose.bones.get(bone_name) if armature.pose else None
        if not pose_bone:
            missing.append(bone_name)
            continue
        live_preview._record_pose_bone_transform(armature, pose_bone)
        if action is None:
            action, created_action = _prepare_transform_action_for_edit(armature)
        keyed_paths = []
        before = {
            "location": [round(float(value), 6) for value in pose_bone.location],
            "rotation_euler": [round(float(value), 6) for value in pose_bone.rotation_euler],
            "scale": [round(float(value), 6) for value in pose_bone.scale],
        }
        loc_delta = offset.get("location_delta", location_delta)
        if loc_delta is not None:
            delta = _coerce_vector(loc_delta, (0.0, 0.0, 0.0))
            pose_bone.location = [float(pose_bone.location[index]) + float(delta[index]) for index in range(3)]
            pose_bone.keyframe_insert(data_path="location", frame=frame)
            if hold_frames:
                pose_bone.keyframe_insert(data_path="location", frame=hold_frame)
            keyed_paths.append("location")
        rot_delta = offset.get("rotation_delta", rotation_delta)
        if rot_delta is not None:
            if str(getattr(pose_bone, "rotation_mode", "") or "").upper() == "QUATERNION":
                missing.append(f"{bone_name}: rotation_delta requires non-quaternion rotation mode")
            else:
                delta = _coerce_vector(rot_delta, (0.0, 0.0, 0.0))
                pose_bone.rotation_euler = [float(pose_bone.rotation_euler[index]) + float(delta[index]) for index in range(3)]
                pose_bone.keyframe_insert(data_path="rotation_euler", frame=frame)
                if hold_frames:
                    pose_bone.keyframe_insert(data_path="rotation_euler", frame=hold_frame)
                keyed_paths.append("rotation_euler")
        scale_mult = offset.get("scale_multiplier", scale_multiplier)
        if scale_mult is not None:
            multiplier = _coerce_vector(scale_mult, (1.0, 1.0, 1.0))
            pose_bone.scale = [float(pose_bone.scale[index]) * float(multiplier[index]) for index in range(3)]
            pose_bone.keyframe_insert(data_path="scale", frame=frame)
            if hold_frames:
                pose_bone.keyframe_insert(data_path="scale", frame=hold_frame)
            keyed_paths.append("scale")
        if keyed_paths:
            applied.append(
                {
                    "bone": pose_bone.name,
                    "paths": keyed_paths,
                    "before": before,
                    "after": {
                        "location": [round(float(value), 6) for value in pose_bone.location],
                        "rotation_euler": [round(float(value), 6) for value in pose_bone.rotation_euler],
                        "scale": [round(float(value), 6) for value in pose_bone.scale],
                    },
                }
            )
    if action:
        _set_action_interpolation(action, interpolation)
    scene.frame_set(frame)
    transaction["applied_steps"].append(
        {
            "type": "offset_rig_limb_controls",
            "label": label,
            "armature": armature.name,
            "offset_count": len(applied),
            "property_target_count": len(property_targets),
            "frame": frame,
            "hold_frame": hold_frame if hold_frames else frame,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    ok = bool(applied or property_result.get("ok"))
    return {
        "ok": ok,
        "message": f"Applied {len(applied)} rig control offset(s)" if ok else "No rig control offsets were applied",
        "armature": armature.name,
        "frame": frame,
        "hold_frame": hold_frame if hold_frames else frame,
        "hold_frames": hold_frames,
        "action": action.name if action else "",
        "created_action": bool(created_action),
        "offsets": applied,
        "property_result": property_result,
        "missing_controls": missing,
        "transaction_id": transaction["id"],
    }

def add_particle_system_to_selected(
    context,
    *,
    name,
    count=200,
    frame_start=1,
    frame_end=80,
    lifetime=80,
    particle_size=0.05,
    label="Add particle system",
):
    selected = [obj for obj in context.selected_objects if obj.type == "MESH"]
    if not selected:
        return {"ok": False, "message": "No selected mesh objects for particle system"}
    transaction = live_preview.begin(label)
    changed = []
    for obj in selected:
        modifier = obj.modifiers.new(name or "Agent Bridge Particles", "PARTICLE_SYSTEM")
        live_preview._record_created_modifier(obj, modifier)
        settings = modifier.particle_system.settings
        settings.name = f"{modifier.name} Settings"
        live_preview._record_created_id("particle_settings", settings.name)
        settings.count = max(1, min(20000, int(count)))
        settings.frame_start = float(frame_start)
        settings.frame_end = float(frame_end)
        settings.lifetime = max(1.0, float(lifetime))
        settings.particle_size = max(0.001, float(particle_size))
        changed.append(obj.name)
    transaction["applied_steps"].append({"type": "add_particle_system", "label": label, "objects": changed})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Added particle system to {len(changed)} mesh object(s)",
        "objects": changed,
        "transaction_id": transaction["id"],
    }

def create_basic_armature(
    context,
    *,
    name,
    location,
    rotation,
    show_in_front=True,
    label="Create basic armature",
):
    transaction = live_preview.begin(label)
    bpy.ops.object.armature_add(enter_editmode=False, location=_coerce_vector(location, (0.0, 0.0, 0.0)), rotation=_coerce_vector(rotation, (0.0, 0.0, 0.0)))
    obj = context.object
    if obj is None:
        return {"ok": False, "message": "Armature was not created"}
    obj.name = name or "Agent Bridge Armature"
    obj.data.name = f"{obj.name} Data"
    obj.show_in_front = bool(show_in_front)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("armature", obj.data.name)
    transaction["applied_steps"].append({"type": "create_basic_armature", "label": label, "object": obj.name})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Created armature {obj.name}", "object": obj.name, "transaction_id": transaction["id"]}

def add_copy_transform_constraint(
    context,
    *,
    target_name,
    constraint_type="COPY_LOCATION",
    name="Agent Bridge Copy Transform",
    influence=1.0,
    label="Add copy transform constraint",
):
    target = bpy.data.objects.get(str(target_name or ""))
    if target is None:
        return {"ok": False, "message": f"Target object not found: {target_name}"}
    constraint_type = str(constraint_type or "COPY_LOCATION").upper()
    if constraint_type not in {"COPY_LOCATION", "COPY_ROTATION", "COPY_SCALE", "COPY_TRANSFORMS"}:
        return {"ok": False, "message": f"Unsupported copy constraint type: {constraint_type}"}
    selected = [obj for obj in context.selected_objects if obj.name != target.name]
    if not selected:
        return {"ok": False, "message": "Select at least one constrained object other than the target"}
    transaction = live_preview.begin(label)
    changed = []
    for obj in selected:
        constraint = obj.constraints.new(type=constraint_type)
        constraint.name = name or f"Agent Bridge {constraint_type.title()}"
        constraint.target = target
        constraint.influence = max(0.0, min(1.0, float(influence)))
        live_preview._record_created_constraint(obj, constraint)
        changed.append(obj.name)
    transaction["applied_steps"].append(
        {"type": "add_copy_transform_constraint", "label": label, "target": target.name, "objects": changed}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Added {constraint_type} constraint to {len(changed)} object(s)", "transaction_id": transaction["id"]}

def add_cloth_simulation_to_selected(
    context,
    *,
    object_names=None,
    selected_only=True,
    name="Agent Bridge Cloth",
    quality=5,
    mass=0.3,
    tension_stiffness=5.0,
    compression_stiffness=5.0,
    shear_stiffness=5.0,
    air_damping=1.0,
    label="Add cloth simulation",
):
    objects, missing = _resolve_edit_objects(context, object_names=object_names, selected_only=selected_only)
    meshes = [obj for obj in objects if obj.type == "MESH"]
    if not meshes:
        return {"ok": False, "message": "No mesh objects found for cloth simulation", "missing_object_names": missing}
    transaction = live_preview.begin(label, context)

    def set_if_present(settings, attr, value):
        if hasattr(settings, attr):
            setattr(settings, attr, value)

    changed = []
    for obj in meshes:
        modifier = obj.modifiers.new(name or "Agent Bridge Cloth", "CLOTH")
        live_preview._record_created_modifier(obj, modifier)
        settings = modifier.settings
        set_if_present(settings, "quality", max(1, min(30, int(quality or 1))))
        set_if_present(settings, "mass", max(0.001, min(1000.0, float(mass or 0.001))))
        set_if_present(settings, "tension_stiffness", max(0.0, min(1000.0, float(tension_stiffness or 0.0))))
        set_if_present(settings, "compression_stiffness", max(0.0, min(1000.0, float(compression_stiffness or 0.0))))
        set_if_present(settings, "shear_stiffness", max(0.0, min(1000.0, float(shear_stiffness or 0.0))))
        set_if_present(settings, "air_damping", max(0.0, min(1000.0, float(air_damping or 0.0))))
        changed.append({"object": obj.name, "modifier": modifier.name})
    transaction["applied_steps"].append({"type": "add_cloth_simulation_to_selected", "label": label, "objects": changed})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Added cloth simulation to {len(changed)} mesh object(s)",
        "objects": changed,
        "missing_object_names": missing,
        "recommended_next_tools": ["get_simulation_details", "inspect_simulation_bake"],
        "transaction_id": transaction["id"],
    }





def register():

    pass





def unregister():

    pass

