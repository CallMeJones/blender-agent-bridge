"""Read-only animation sampling, validation, and repair-planning helpers."""

from __future__ import annotations

import math

import bpy
import mathutils
from bpy_extras.object_utils import world_to_camera_view

from . import animation_brief, live_preview


def _name_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    return [str(item).strip() for item in value if str(item).strip()]


def _bounded_int(value, default, *, minimum=1, maximum=240):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = int(default)
    return max(int(minimum), min(int(maximum), value))


def _resolve_objects(context, object_names=None, *, selected_only=False, max_objects=12):
    names = _name_list(object_names)
    missing = []
    if names:
        objects = []
        for name in names:
            obj = bpy.data.objects.get(name)
            if obj:
                objects.append(obj)
            else:
                missing.append(name)
    elif selected_only and context.selected_objects:
        objects = list(context.selected_objects)
    elif context.active_object:
        objects = [context.active_object]
    else:
        objects = list(context.scene.objects)
    return [obj for obj in objects if obj][:max_objects], missing


def _frame_samples(scene, frame_start=None, frame_end=None, sample_step=4, max_samples=48):
    start = int(frame_start if frame_start is not None else scene.frame_start)
    end = int(frame_end if frame_end is not None else scene.frame_end)
    if end < start:
        start, end = end, start
    step = _bounded_int(sample_step, 4, minimum=1, maximum=240)
    frames = list(range(start, end + 1, step))
    if not frames or frames[-1] != end:
        frames.append(end)
    if len(frames) > max_samples:
        stride = max(1, math.ceil(len(frames) / max_samples))
        frames = frames[::stride]
        if frames[-1] != end:
            frames.append(end)
    return sorted(set(int(frame) for frame in frames))


def _world_center(obj):
    if not getattr(obj, "bound_box", None):
        return tuple(float(value) for value in obj.matrix_world.translation)
    points = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
    return tuple(sum(point[index] for point in points) / len(points) for index in range(3))


def _bbox_world(obj):
    corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in getattr(obj, "bound_box", [])]
    if not corners:
        loc = obj.matrix_world.translation
        corners = [loc]
    mins = [min(point[index] for point in corners) for index in range(3)]
    maxs = [max(point[index] for point in corners) for index in range(3)]
    return mins, maxs


def _bbox_intersects(a, b, tolerance=0.0):
    amin, amax = a
    bmin, bmax = b
    return all(amin[index] <= bmax[index] + tolerance and amax[index] + tolerance >= bmin[index] for index in range(3))


def _distance(a, b):
    return math.sqrt(sum((float(a[index]) - float(b[index])) ** 2 for index in range(3)))


def _set_frame_preserved(context, frames, fn):
    scene = context.scene
    current = int(scene.frame_current)
    results = []
    try:
        for frame in frames:
            scene.frame_set(int(frame))
            context.view_layer.update()
            results.append(fn(int(frame)))
    finally:
        scene.frame_set(current)
        context.view_layer.update()
    return results


def sample_animation_state(context, *, object_names=None, frame_start=None, frame_end=None, sample_step=4, selected_only=False):
    objects, missing = _resolve_objects(context, object_names, selected_only=selected_only)
    frames = _frame_samples(context.scene, frame_start, frame_end, sample_step)
    if not objects:
        return {"ok": False, "message": "No objects found for animation sampling", "missing_object_names": missing}

    def snapshot(frame):
        return {
            "frame": frame,
            "objects": [
                {
                    "name": obj.name,
                    "location": [round(float(value), 6) for value in obj.location],
                    "rotation_euler": [round(float(value), 6) for value in obj.rotation_euler],
                    "scale": [round(float(value), 6) for value in obj.scale],
                    "world_location": [round(float(value), 6) for value in obj.matrix_world.translation],
                }
                for obj in objects
            ],
        }

    return {
        "ok": True,
        "message": f"Sampled {len(objects)} object(s) across {len(frames)} frame(s)",
        "frames": _set_frame_preserved(context, frames, snapshot),
        "sampled_frames": frames,
        "missing_object_names": missing,
    }


def _action_for_object(obj):
    return obj.animation_data.action if obj.animation_data and obj.animation_data.action else None


def _iter_fcurves(action):
    return live_preview._iter_action_fcurves(action) if action else []


def _find_fcurve(action, data_path, index):
    return next((fcurve for fcurve in _iter_fcurves(action) if fcurve.data_path == data_path and int(fcurve.array_index) == int(index)), None)


def analyze_fcurve_spacing(context, *, object_names=None, action_names=None, selected_only=False, paths=None):
    objects, missing = _resolve_objects(context, object_names, selected_only=selected_only)
    wanted_paths = set(_name_list(paths))
    actions = []
    seen = set()
    for obj in objects:
        action = _action_for_object(obj)
        if action and action.name not in seen:
            actions.append(action)
            seen.add(action.name)
    for name in _name_list(action_names):
        action = bpy.data.actions.get(name)
        if action and action.name not in seen:
            actions.append(action)
            seen.add(action.name)
        elif not action:
            missing.append(name)
    analyses = []
    object_analyses = []
    findings = []
    for action in actions:
        curves = []
        for fcurve in _iter_fcurves(action):
            if wanted_paths and fcurve.data_path not in wanted_paths:
                continue
            points = sorted((float(point.co.x), float(point.co.y)) for point in fcurve.keyframe_points)
            frame_gaps = [round(points[index + 1][0] - points[index][0], 6) for index in range(len(points) - 1)]
            value_gaps = [round(points[index + 1][1] - points[index][1], 6) for index in range(len(points) - 1)]
            interpolation = sorted({point.interpolation for point in fcurve.keyframe_points})
            curves.append(
                {
                    "data_path": fcurve.data_path,
                    "array_index": int(fcurve.array_index),
                    "keyframe_count": len(points),
                    "frame_gaps": frame_gaps,
                    "value_gaps": value_gaps,
                    "interpolation": interpolation,
                }
            )
            if len(points) >= 3 and len(set(frame_gaps)) == 1 and len(set(value_gaps)) == 1:
                findings.append(
                    {
                        "severity": "info",
                        "action": action.name,
                        "data_path": fcurve.data_path,
                        "message": "Even frame and value spacing may read mechanically linear.",
                    }
                )
        analyses.append({"action": action.name, "fcurves": curves})
    for obj in objects:
        action = _action_for_object(obj)
        keyframes = []
        segments = []
        if action:
            keyframes = sorted(
                {
                    int(round(point.co.x))
                    for fcurve in _iter_fcurves(action)
                    if not wanted_paths or fcurve.data_path in wanted_paths
                    for point in fcurve.keyframe_points
                }
            )
            locations = []
            for frame in keyframes:
                values = []
                for index in range(3):
                    fcurve = _find_fcurve(action, "location", index)
                    values.append(float(fcurve.evaluate(frame)) if fcurve else float(obj.location[index]))
                locations.append(tuple(values))
            for index, frame in enumerate(keyframes[:-1]):
                segments.append(
                    {
                        "from": frame,
                        "to": keyframes[index + 1],
                        "distance": round(_distance(locations[index], locations[index + 1]), 6) if locations else 0.0,
                    }
                )
        object_analyses.append(
            {
                "object": obj.name,
                "action": action.name if action else "",
                "paths": sorted(wanted_paths) if wanted_paths else ["location", "rotation_euler", "scale"],
                "keyframes": keyframes,
                "segments": segments,
            }
        )
    return {"ok": True, "message": f"Analyzed {len(actions)} action(s)", "actions": analyses, "objects": object_analyses, "findings": findings, "missing": missing}


def analyze_motion_arcs(context, *, object_names=None, frame_start=None, frame_end=None, sample_step=4, max_samples=48, selected_only=False):
    objects, missing = _resolve_objects(context, object_names, selected_only=selected_only)
    frames = _frame_samples(context.scene, frame_start, frame_end, sample_step, max_samples=max_samples)
    if not objects:
        return {"ok": False, "message": "No objects found for motion arc analysis", "missing_object_names": missing}
    samples = {obj.name: [] for obj in objects}

    def collect(frame):
        for obj in objects:
            loc = tuple(float(value) for value in obj.matrix_world.translation)
            samples[obj.name].append((frame, loc))

    _set_frame_preserved(context, frames, collect)
    arcs = []
    findings = []
    for obj in objects:
        points = samples[obj.name]
        segments = [_distance(points[index][1], points[index + 1][1]) for index in range(len(points) - 1)]
        total_distance = sum(segments)
        arcs.append(
            {
                "object": obj.name,
                "frame_start": frames[0],
                "frame_end": frames[-1],
                "sample_count": len(points),
                "total_distance": round(total_distance, 6),
                "path_length": round(total_distance, 6),
                "segment_lengths": [round(value, 6) for value in segments],
                "points": [{"frame": frame, "location": [round(component, 6) for component in loc]} for frame, loc in points],
            }
        )
        if total_distance <= 0.0001:
            findings.append({"severity": "warning", "object": obj.name, "message": "Object has no sampled world-space motion."})
    return {"ok": True, "message": f"Analyzed motion arcs for {len(objects)} object(s)", "arcs": arcs, "objects": arcs, "findings": findings, "missing_object_names": missing}


def analyze_pose_clarity(context, *, object_names=None, selected_only=False):
    objects, missing = _resolve_objects(context, object_names, selected_only=selected_only)
    poses = []
    findings = []
    for obj in objects:
        action = _action_for_object(obj)
        if not action:
            findings.append({"severity": "warning", "object": obj.name, "message": "Object has no action to analyze for pose clarity."})
            continue
        frames = sorted({int(round(point.co.x)) for fcurve in _iter_fcurves(action) for point in fcurve.keyframe_points})
        transform_paths = sorted({fcurve.data_path for fcurve in _iter_fcurves(action) if fcurve.data_path in {"location", "rotation_euler", "scale"}})
        holds = []
        for index, frame in enumerate(frames[:-1]):
            next_frame = frames[index + 1]
            if next_frame - frame <= 6:
                holds.append({"frame": frame, "hold_to": next_frame, "duration": next_frame - frame})
        if len(frames) < 3:
            findings.append({"severity": "info", "object": obj.name, "message": "Animation has fewer than three keyed poses; readability may depend heavily on interpolation."})
        if "location" not in transform_paths and "rotation_euler" not in transform_paths:
            findings.append({"severity": "info", "object": obj.name, "message": "No transform pose changes found on location or rotation curves."})
        poses.append(
            {
                "object": obj.name,
                "action": action.name,
                "keyed_frames": frames,
                "transform_paths": transform_paths,
                "hold_candidates": holds,
                "holds": holds,
                "pose_count": len(frames),
            }
        )
    return {"ok": True, "message": f"Analyzed pose clarity for {len(objects)} object(s)", "objects": poses, "findings": findings, "missing_object_names": missing}


def analyze_animation_principles(context, *, object_names=None, selected_only=False, prompt="", brief=None, timing_chart=None, frame_start=None, frame_end=None):
    objects, missing = _resolve_objects(context, object_names, selected_only=selected_only)
    subject_names = [obj.name for obj in objects]
    brief = _brief_from_args(
        context,
        brief=brief,
        prompt=prompt,
        subject_names=subject_names or object_names,
        frame_start=frame_start,
        frame_end=frame_end,
    ) if (brief or prompt) else (brief or {})
    timing_chart = timing_chart if isinstance(timing_chart, dict) else {}
    arcs = analyze_motion_arcs(context, object_names=subject_names or object_names, selected_only=selected_only, frame_start=frame_start, frame_end=frame_end)
    spacing = analyze_fcurve_spacing(context, object_names=subject_names or object_names, selected_only=selected_only, paths=["location", "rotation_euler", "scale"])
    clarity = analyze_pose_clarity(context, object_names=subject_names or object_names, selected_only=selected_only)
    findings = []
    findings.extend(arcs.get("findings") or [])
    findings.extend(spacing.get("findings") or [])
    findings.extend(clarity.get("findings") or [])
    action = str((brief or {}).get("action") or "").lower()
    key_poses = timing_chart.get("key_poses") or []
    roles = {str(item.get("role") or "").lower() for item in key_poses if isinstance(item, dict)}
    labels = {str(item.get("label") or "").lower() for item in key_poses if isinstance(item, dict)}
    principle_checks = []
    for obj in objects:
        action_data = _action_for_object(obj)
        has_scale = bool(action_data and any(fcurve.data_path == "scale" for fcurve in _iter_fcurves(action_data)))
        has_location = bool(action_data and any(fcurve.data_path == "location" for fcurve in _iter_fcurves(action_data)))
        check = {
            "object": obj.name,
            "action": action_data.name if action_data else "",
            "staging": "pass" if context.scene.camera or (brief or {}).get("camera") else "info",
            "timing_spacing": "pass",
            "arcs": "pass" if has_location else "warning",
            "pose_clarity": "pass",
            "anticipation": "not_evaluated",
            "squash_stretch": "not_evaluated",
            "follow_through_settle": "not_evaluated",
            "secondary_action": "not_evaluated",
            "contact_weight": "not_evaluated",
        }
        if action in {"bounce", "jump", "fall"}:
            has_anticipation = "anticipation" in roles or any("anticipation" in label for label in labels)
            has_settle = "settle" in roles or any("settle" in label for label in labels)
            check["anticipation"] = "pass" if has_anticipation else "info"
            check["squash_stretch"] = "pass" if has_scale else "info"
            check["follow_through_settle"] = "pass" if has_settle else "warning"
            check["contact_weight"] = "pass" if ("contact" in roles or has_scale) else "info"
            if not has_anticipation:
                findings.append(
                    {
                        "severity": "info",
                        "principle": "anticipation",
                        "object": obj.name,
                        "message": "No explicit anticipation pose was found for the action.",
                        "recommendation": "Add a small wind-up, crouch, or pre-contact pose before the main action.",
                    }
                )
            if not has_scale:
                findings.append(
                    {
                        "severity": "info",
                        "principle": "squash_stretch",
                        "object": obj.name,
                        "message": "No scale keys were found for squash/stretch.",
                        "recommendation": "Add squash on contact and stretch on launch when the style allows it.",
                    }
                )
            if not has_settle:
                findings.append({"severity": "warning", "principle": "settle", "object": obj.name, "message": "Timing chart has no explicit settle pose."})
            if "contact" not in roles and timing_chart:
                findings.append({"severity": "warning", "principle": "contact", "object": obj.name, "message": "Timing chart has no explicit contact pose."})
        secondary_actions = (brief or {}).get("secondary_actions") or []
        if secondary_actions:
            scale_required = any("scale" in str(item).lower() or "smaller" in str(item).lower() or "bigger" in str(item).lower() for item in secondary_actions)
            check["secondary_action"] = "pass" if (not scale_required or has_scale) else "warning"
            if scale_required and not has_scale:
                findings.append({"severity": "warning", "principle": "secondary_action", "object": obj.name, "message": "The brief asks for scale change, but no scale animation was found."})
        principle_checks.append(check)
    warning_count = sum(1 for item in findings if str(item.get("severity", "")).lower() in {"warning", "warn", "error"})
    status = "pass" if warning_count == 0 else "needs_repair"
    return {
        "ok": True,
        "message": "Analyzed animation principles",
        "status": status,
        "brief_contract_id": (brief or {}).get("contract_id", ""),
        "principle_checks": principle_checks,
        "warning_count": warning_count,
        "ready_for_repair": warning_count > 0,
        "principles": {
            "staging": "camera framing should be checked separately with analyze_camera_framing",
            "timing_spacing": spacing,
            "arcs": arcs,
            "pose_clarity": clarity,
        },
        "motion_arcs": arcs.get("objects", []),
        "spacing": spacing.get("objects", []),
        "pose_clarity": clarity.get("objects", []),
        "findings": findings,
        "missing_object_names": missing,
    }


def analyze_contact_sliding(context, *, object_names=None, frame_start=None, frame_end=None, sample_step=2, contact_z=0.0, contact_tolerance=0.05, sliding_tolerance=0.08, selected_only=False):
    objects, missing = _resolve_objects(context, object_names, selected_only=selected_only)
    frames = _frame_samples(context.scene, frame_start, frame_end, sample_step)
    contacts = {obj.name: [] for obj in objects}

    def collect(frame):
        for obj in objects:
            mins, _maxs = _bbox_world(obj)
            if abs(float(mins[2]) - float(contact_z)) <= float(contact_tolerance):
                contacts[obj.name].append(
                    {
                        "frame": frame,
                        "xy": [round(float(obj.matrix_world.translation.x), 6), round(float(obj.matrix_world.translation.y), 6)],
                        "min_z": round(float(mins[2]), 6),
                    }
                )

    _set_frame_preserved(context, frames, collect)
    findings = []
    for obj in objects:
        contact_points = contacts[obj.name]
        if len(contact_points) < 2:
            continue
        first = contact_points[0]["xy"]
        last = contact_points[-1]["xy"]
        slide = math.sqrt((last[0] - first[0]) ** 2 + (last[1] - first[1]) ** 2)
        if slide > float(sliding_tolerance):
            findings.append(
                {
                    "severity": "warning",
                    "object": obj.name,
                    "message": "Contact points slide across the ground plane.",
                    "slide_distance": round(slide, 6),
                }
            )
    return {"ok": True, "message": f"Analyzed contact sliding for {len(objects)} object(s)", "contacts": contacts, "findings": findings, "missing_object_names": missing}


def analyze_collision_penetration(context, *, object_names=None, frame_start=None, frame_end=None, sample_step=4, tolerance=0.0, selected_only=False):
    objects, missing = _resolve_objects(context, object_names, selected_only=selected_only, max_objects=20)
    frames = _frame_samples(context.scene, frame_start, frame_end, sample_step, max_samples=32)
    findings = []

    def collect(frame):
        boxes = [(obj, _bbox_world(obj)) for obj in objects]
        for index, (left, left_box) in enumerate(boxes):
            for right, right_box in boxes[index + 1 :]:
                if _bbox_intersects(left_box, right_box, tolerance=float(tolerance)):
                    findings.append({"severity": "warning", "frame": frame, "objects": [left.name, right.name], "message": "World bounding boxes intersect."})

    _set_frame_preserved(context, frames, collect)
    return {"ok": True, "message": f"Checked {len(objects)} object(s) for bbox intersections", "findings": findings, "sampled_frames": frames, "missing_object_names": missing}


def analyze_camera_framing(context, *, object_names=None, camera_name="", frame_start=None, frame_end=None, sample_step=8, margin=0.05, selected_only=False):
    scene = context.scene
    camera = bpy.data.objects.get(camera_name) if camera_name else scene.camera
    if not camera or camera.type != "CAMERA":
        return {"ok": False, "message": "A camera is required for framing analysis"}
    objects, missing = _resolve_objects(context, object_names, selected_only=selected_only)
    frames = _frame_samples(scene, frame_start, frame_end, sample_step, max_samples=24)
    findings = []
    samples = []

    def collect(frame):
        for obj in objects:
            center = world_to_camera_view(scene, camera, obj.matrix_world.translation)
            visible = float(margin) <= center.x <= 1.0 - float(margin) and float(margin) <= center.y <= 1.0 - float(margin) and center.z > 0
            sample = {
                "frame": frame,
                "object": obj.name,
                "camera": camera.name,
                "normalized": [round(float(center.x), 6), round(float(center.y), 6), round(float(center.z), 6)],
                "center_visible": bool(visible),
            }
            samples.append(sample)
            if not visible:
                findings.append({"severity": "warning", **sample, "message": "Subject center is outside the camera-safe region."})

    _set_frame_preserved(context, frames, collect)
    return {"ok": True, "message": f"Analyzed camera framing for {len(objects)} object(s)", "samples": samples, "findings": findings, "missing_object_names": missing}


def _brief_from_args(context, brief=None, prompt="", subject_names=None, frame_start=None, frame_end=None):
    if isinstance(brief, dict) and brief:
        return brief
    result = animation_brief.create_animation_brief(
        context,
        prompt=prompt,
        subject_names=subject_names,
        frame_start=frame_start,
        frame_end=frame_end,
    )
    return result.get("brief") if result.get("ok") else {}


def compare_animation_to_brief(context, *, brief=None, prompt="", subject_names=None, frame_start=None, frame_end=None):
    brief = _brief_from_args(context, brief=brief, prompt=prompt, subject_names=subject_names, frame_start=frame_start, frame_end=frame_end)
    if not brief:
        return {"ok": False, "message": "A prompt or animation brief is required"}
    subjects = [item["name"] for item in brief.get("subjects") or []] or brief.get("subject_names") or []
    timing = brief.get("timing") or {}
    start = int(frame_start if frame_start is not None else timing.get("frame_start", context.scene.frame_start))
    end = int(frame_end if frame_end is not None else timing.get("frame_end", context.scene.frame_end))
    findings = []
    if not subjects:
        findings.append({"severity": "error", "requirement": "subject", "message": "No resolved animation subject."})
    missing = [name for name in subjects if bpy.data.objects.get(name) is None]
    for name in missing:
        findings.append({"severity": "error", "requirement": "subject", "object": name, "message": "Subject object is missing."})
    samples = sample_animation_state(context, object_names=subjects, frame_start=start, frame_end=end, sample_step=max(1, int((end - start) / 24) or 1))
    if samples.get("ok"):
        moved = False
        by_object = {}
        for frame in samples["frames"]:
            for obj in frame["objects"]:
                by_object.setdefault(obj["name"], []).append(obj)
        for _name, items in by_object.items():
            if len(items) < 2:
                continue
            first_location = items[0]["world_location"]
            if any(_distance(first_location, item["world_location"]) > 0.001 for item in items[1:]):
                moved = True
        if brief.get("action") and not moved:
            findings.append({"severity": "warning", "requirement": "action", "message": "Sampled subject transforms do not show clear motion."})
    if brief.get("validation_plan", {}).get("check_camera_framing"):
        camera_findings = analyze_camera_framing(context, object_names=subjects, camera_name=brief.get("camera") or "", frame_start=start, frame_end=end)
        findings.extend(camera_findings.get("findings") or [])
    status = "pass" if not findings else "needs_repair"
    return {
        "ok": True,
        "message": "Compared animation against brief",
        "status": status,
        "brief_contract_id": brief.get("contract_id", ""),
        "findings": findings,
        "sample_summary": samples if samples.get("ok") else {},
    }


def review_playblast_against_brief(context, *, playblast=None, brief=None, prompt=""):
    metadata = playblast if isinstance(playblast, dict) else {}
    findings = []
    if not metadata.get("available") and not metadata.get("frames"):
        findings.append({"severity": "warning", "message": "No playblast frames are available for review."})
    frames = metadata.get("frames") or []
    if frames and len(frames) < 3:
        findings.append({"severity": "info", "message": "Playblast has very few sampled frames; timing review may be weak."})
    comparison = compare_animation_to_brief(context, brief=brief, prompt=prompt) if (brief or prompt) else {}
    findings.extend(comparison.get("findings") or [])
    return {
        "ok": True,
        "message": "Reviewed playblast metadata and current animation state against brief",
        "status": "pass" if not findings else "needs_repair",
        "playblast_id": metadata.get("playblast_id", ""),
        "frame_count": len(frames),
        "findings": findings,
        "comparison": comparison,
    }


def repair_animation_from_findings(context, *, findings=None, brief=None):
    suggestions = []
    for finding in findings or []:
        text = str(finding.get("message") or "").lower()
        if "camera" in text or "framing" in text:
            suggestions.append({"tool": "create_camera_orbit", "reason": "Repair camera framing around the subject."})
        elif "linear" in text or "spacing" in text:
            suggestions.append({"tool": "set_action_interpolation", "reason": "Adjust interpolation/easing for less mechanical spacing."})
        elif "contact" in text or "slide" in text:
            suggestions.append({"tool": "set_pose_hold", "reason": "Hold or re-key contact poses to reduce sliding."})
        elif "motion" in text:
            suggestions.append({"tool": "block_key_poses", "reason": "Create or revise readable key poses."})
    if not suggestions and brief:
        suggestions.append({"tool": "create_timing_chart", "reason": "Rebuild a timing chart from the prompt contract before targeted repair."})
    return {
        "ok": True,
        "message": f"Created {len(suggestions)} repair suggestion(s)",
        "suggested_tool_calls": suggestions,
        "mutates_scene": False,
    }
