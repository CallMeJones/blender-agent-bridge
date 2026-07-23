"""Blender-only handlers for the animation domain."""

from __future__ import annotations

import bpy

from .. import (
    advanced_helpers,
    animation_analysis,
    animation_brief,
    animation_workflow,
    blender_compat,
    context_bundle,
    live_preview,
    world_model,
)
from ..handler_runtime import (
    _REPAIR_LOOP_DEFAULT_TOOLS,
    _WORKFLOW_GENERATION_TOOLS,
    _action_summary,
    _animation_data_summary,
    _append_action,
    _bounded_float,
    _bounded_int,
    _brief_frame_range,
    _constraint_summary,
    _driver_summary,
    _execute_repair_tool,
    _execute_workflow_tool,
    _float_list,
    _mark_animation_workflow_seen,
    _name_list,
    _object_related_actions,
    _optional_float,
    _optional_float_list,
    _repair_loop_brief_text,
    _repair_loop_review,
    _repair_operation_blocker,
    _repair_operation_key,
    _repair_operation_mutates,
    _repair_operation_parts,
    _resolve_objects,
    _workflow_review,
    _workflow_tool_parts,
)


def get_animation_details(context, args):
    max_actions = _bounded_int(args.get("max_actions"), 8, maximum=25)
    max_keyframes = _bounded_int(args.get("max_keyframes_per_curve"), 8, maximum=32)
    action_names = _name_list(args.get("action_names"))
    objects, missing_objects = _resolve_objects(context, args)
    actions = []
    missing_actions = []
    seen = set()

    for obj in objects:
        for action in _object_related_actions(obj):
            _append_action(actions, seen, action)

    if action_names:
        for name in action_names:
            action = bpy.data.actions.get(name)
            if action:
                _append_action(actions, seen, action)
            else:
                missing_actions.append(name)
    elif not actions:
        actions.extend(list(bpy.data.actions)[:max_actions])

    return {
        "ok": True,
        "scene": {
            "frame_current": int(context.scene.frame_current),
            "frame_start": int(context.scene.frame_start),
            "frame_end": int(context.scene.frame_end),
            "fps": int(context.scene.render.fps),
        },
        "objects": [
            {
                "name": obj.name,
                "type": obj.type,
                "animation_data": context_bundle._object_summary(obj).get("animation"),
                "object_animation": _animation_data_summary(obj),
                "data_animation": _animation_data_summary(obj.data) if getattr(obj, "data", None) else None,
                "constraints": [_constraint_summary(constraint) for constraint in list(obj.constraints)[:24]],
                "drivers": _driver_summary(obj),
                "shape_key_animation": _animation_data_summary(obj.data.shape_keys)
                if obj.type == "MESH" and obj.data and obj.data.shape_keys
                else None,
                "materials": [
                    {
                        "slot_index": index,
                        "name": slot.material.name if slot.material else None,
                        "material_animation": _animation_data_summary(slot.material) if slot.material else None,
                        "node_tree_animation": _animation_data_summary(blender_compat.node_tree(slot.material))
                        if slot.material and blender_compat.node_tree(slot.material)
                        else None,
                    }
                    for index, slot in enumerate(obj.material_slots)
                ],
            }
            for obj in objects
        ],
        "actions": [
            _action_summary(action, max_keyframes_per_curve=max_keyframes)
            for action in actions[:max_actions]
        ],
        "total_action_count": len(bpy.data.actions),
        "missing_object_names": missing_objects,
        "missing_action_names": missing_actions,
    }


def get_animation_scene_context(context, args):
    return world_model.animation_scene_context(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", False)),
        max_objects=_bounded_int(args.get("max_objects"), 20, maximum=80),
    )


def create_animation_brief(context, args):
    return animation_brief.create_animation_brief(
        context,
        prompt=str(args.get("prompt") or ""),
        subject_names=_name_list(args.get("subject_names")),
        action=str(args.get("action") or ""),
        style=str(args.get("style") or ""),
        camera=str(args.get("camera") or ""),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        constraints=_name_list(args.get("constraints")),
        success_criteria=_name_list(args.get("success_criteria")),
    )


def create_timing_chart(context, args):
    return animation_brief.create_timing_chart(
        context,
        prompt=str(args.get("prompt") or ""),
        brief=args.get("brief") if isinstance(args.get("brief"), dict) else None,
        subject_names=_name_list(args.get("subject_names")),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        beats=args.get("beats") if isinstance(args.get("beats"), list) else None,
    )


def plan_animation_workflow(context, args):
    result = animation_workflow.plan_animation_workflow(
        context,
        prompt=str(args.get("prompt") or ""),
        subject_names=_name_list(args.get("subject_names")),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        mode=str(args.get("mode") or "full"),
        selected_only=bool(args.get("selected_only", False)),
        max_objects=_bounded_int(args.get("max_objects"), 20, minimum=1, maximum=80),
        brief=args.get("brief") if isinstance(args.get("brief"), dict) else None,
        timing_chart=args.get("timing_chart") if isinstance(args.get("timing_chart"), dict) else None,
        playblast=args.get("playblast") if isinstance(args.get("playblast"), dict) else None,
        findings=args.get("findings") if isinstance(args.get("findings"), list) else None,
    )
    if isinstance(result, dict) and result.get("ok"):
        _mark_animation_workflow_seen(context, result)
    return result


def run_animation_workflow(context, args):
    prompt = str(args.get("prompt") or "")
    mode = str(args.get("mode") or "full").strip().lower()
    max_generation_steps = _bounded_int(args.get("max_generation_steps"), 8, minimum=1, maximum=20)
    apply_generation = bool(args.get("apply_generation", True))
    run_review = bool(args.get("run_review", True))
    capture_playblast = bool(args.get("capture_playblast", False))
    apply_repairs = bool(args.get("apply_repairs", False))

    plan_result = plan_animation_workflow(
        context,
        {
            "prompt": prompt,
            "subject_names": _name_list(args.get("subject_names")),
            "frame_start": args.get("frame_start"),
            "frame_end": args.get("frame_end"),
            "mode": mode,
            "selected_only": bool(args.get("selected_only", False)),
            "max_objects": _bounded_int(args.get("max_objects"), 20, minimum=1, maximum=80),
            "brief": args.get("brief") if isinstance(args.get("brief"), dict) else None,
            "timing_chart": args.get("timing_chart") if isinstance(args.get("timing_chart"), dict) else None,
            "playblast": args.get("playblast") if isinstance(args.get("playblast"), dict) else None,
            "findings": args.get("findings") if isinstance(args.get("findings"), list) else None,
        },
    )
    if not plan_result.get("ok"):
        return plan_result
    workflow = plan_result.get("workflow") if isinstance(plan_result.get("workflow"), dict) else {}
    if workflow.get("status") == "needs_clarification":
        return {
            "ok": True,
            "message": "Animation workflow needs clarification before mutating the scene",
            "status": "needs_clarification",
            "workflow": workflow,
            "executed": [],
            "skipped": [],
            "review": {},
            "repair_loop": {},
            "pending_preview": bool(getattr(context.scene.claude_blender, "pending_preview", False)) if hasattr(context.scene, "claude_blender") else False,
            "result_type": "live_preview_helper_workflow",
        }
    if workflow.get("status") == "blocked_by_scene_context":
        return {
            "ok": True,
            "message": "Animation workflow is blocked by scene context; inspect preflight_warnings before mutating the scene",
            "status": "blocked_by_scene_context",
            "workflow": workflow,
            "executed": [],
            "skipped": [],
            "review": {},
            "repair_loop": {},
            "pending_preview": bool(getattr(context.scene.claude_blender, "pending_preview", False)) if hasattr(context.scene, "claude_blender") else False,
            "result_type": "live_preview_helper_workflow",
        }

    executed = []
    skipped = []
    generation_count = 0
    if apply_generation and mode in {"generate", "full", "repair", "review"}:
        for index, tool_call in enumerate(workflow.get("next_tool_calls") or []):
            tool, tool_args = _workflow_tool_parts(tool_call)
            if tool not in _WORKFLOW_GENERATION_TOOLS:
                if tool:
                    skipped.append({"index": index, "tool": tool, "reason": "tool is handled by review/repair or outside workflow generation allowlist"})
                continue
            if generation_count >= max_generation_steps:
                skipped.append({"index": index, "tool": tool, "reason": "max_generation_steps reached"})
                continue
            result = _execute_workflow_tool(context, tool, tool_args)
            executed.append(
                {
                    "index": index,
                    "tool": tool,
                    "arguments": tool_args,
                    "ok": bool(result.get("ok")),
                    "message": str(result.get("message") or ""),
                    "result": result,
                }
            )
            generation_count += 1
    elif not apply_generation:
        for index, tool_call in enumerate(workflow.get("next_tool_calls") or []):
            tool, _tool_args = _workflow_tool_parts(tool_call)
            if tool in _WORKFLOW_GENERATION_TOOLS:
                skipped.append({"index": index, "tool": tool, "reason": "apply_generation is false"})

    brief = workflow.get("brief") if isinstance(workflow.get("brief"), dict) else {}
    timing_chart = workflow.get("timing_chart") if isinstance(workflow.get("timing_chart"), dict) else {}
    frame_start, frame_end = animation_workflow._frame_range(context, brief)
    review = {}
    repair_loop = {}
    if run_review:
        review = _workflow_review(
            context,
            prompt=prompt,
            brief=brief,
            timing_chart=timing_chart,
            frame_start=frame_start,
            frame_end=frame_end,
            capture_playblast=capture_playblast,
            playblast=args.get("playblast") if isinstance(args.get("playblast"), dict) else None,
        )
        repair_operations = (review.get("repair_plan") or {}).get("repair_operations") or []
        if apply_repairs and repair_operations:
            repair_loop = run_animation_repair_loop(
                context,
                {
                    "brief": brief,
                    "prompt": prompt,
                    "findings": review.get("findings") or [],
                    "repair_operations": repair_operations,
                    "max_iterations": _bounded_int(args.get("max_repair_iterations"), 1, minimum=1, maximum=4),
                    "max_operations": _bounded_int(args.get("max_repair_operations"), 3, minimum=1, maximum=12),
                    "apply_mutating_repairs": True,
                    "recapture_after_mutation": bool(args.get("recapture_after_repair", False)),
                },
            )
    failed = [item for item in executed if not item.get("ok")]
    if failed:
        status = "generation_failed"
    elif repair_loop:
        status = repair_loop.get("status") or "repairs_applied_needs_review"
    elif run_review and (review.get("finding_count") or 0) > 0:
        status = "generated_needs_repair"
    elif executed:
        status = "generated_reviewed"
    else:
        status = "planned"
    return {
        "ok": True,
        "message": f"Animation workflow finished with status: {status}",
        "status": status,
        "workflow": workflow,
        "executed": executed,
        "skipped": skipped,
        "review": review,
        "repair_loop": repair_loop,
        "generation_blockers": workflow.get("generation_blockers") or [],
        "pending_preview": bool(getattr(context.scene.claude_blender, "pending_preview", False)) if hasattr(context.scene, "claude_blender") else False,
        "result_type": "live_preview_helper_workflow",
    }


def run_animation_task(context, args):
    prompt = str(args.get("prompt") or "")
    result = run_animation_workflow(
        context,
        {
            "prompt": prompt,
            "mode": "full",
            "apply_generation": True,
            "run_review": True,
            "capture_playblast": False,
            "apply_repairs": False,
        },
    )
    if isinstance(result, dict):
        enriched = dict(result)
        enriched.setdefault("message", "Animation task routed through run_animation_workflow")
        enriched["invoked_workflow_tool"] = "run_animation_workflow"
        enriched["task_prompt"] = prompt
        return enriched
    return result


def analyze_motion_arcs(context, args):
    return animation_analysis.analyze_motion_arcs(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", False)),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        max_samples=_bounded_int(args.get("max_samples"), 16, minimum=2, maximum=120),
    )


def analyze_fcurve_spacing(context, args):
    return animation_analysis.analyze_fcurve_spacing(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", False)),
        paths=_name_list(args.get("paths")),
    )


def analyze_pose_clarity(context, args):
    return animation_analysis.analyze_pose_clarity(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", False)),
    )


def analyze_animation_principles(context, args):
    return animation_analysis.analyze_animation_principles(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", False)),
        prompt=str(args.get("prompt") or ""),
        brief=args.get("brief") if isinstance(args.get("brief"), dict) else None,
        timing_chart=args.get("timing_chart") if isinstance(args.get("timing_chart"), dict) else None,
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
    )


def sample_animation_state(context, args):
    return animation_analysis.sample_animation_state(
        context,
        object_names=_name_list(args.get("object_names")),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        sample_step=_bounded_int(args.get("sample_step"), 4, minimum=1, maximum=10000),
        selected_only=bool(args.get("selected_only", False)),
    )


def analyze_contact_sliding(context, args):
    return animation_analysis.analyze_contact_sliding(
        context,
        object_names=_name_list(args.get("object_names")),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        sample_step=_bounded_int(args.get("sample_step"), 2, minimum=1, maximum=10000),
        contact_z=float(args.get("contact_z", 0.0)),
        contact_tolerance=float(args.get("contact_tolerance", 0.05)),
        sliding_tolerance=float(args.get("sliding_tolerance", 0.08)),
        selected_only=bool(args.get("selected_only", False)),
    )


def analyze_collision_penetration(context, args):
    return animation_analysis.analyze_collision_penetration(
        context,
        object_names=_name_list(args.get("object_names")),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        sample_step=_bounded_int(args.get("sample_step"), 4, minimum=1, maximum=10000),
        tolerance=float(args.get("tolerance", 0.0)),
        selected_only=bool(args.get("selected_only", False)),
    )


def analyze_center_of_mass(context, args):
    return animation_analysis.analyze_center_of_mass(
        context,
        object_names=_name_list(args.get("object_names")),
        support_object_names=_name_list(args.get("support_object_names")),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        sample_step=_bounded_int(args.get("sample_step"), 4, minimum=1, maximum=10000),
        support_margin=_bounded_float(args.get("support_margin"), 0.05, minimum=0.0, maximum=1000.0),
        contact_tolerance=_bounded_float(args.get("contact_tolerance"), 0.12, minimum=0.0, maximum=1000.0),
        selected_only=bool(args.get("selected_only", False)),
    )


def analyze_camera_framing(context, args):
    return animation_analysis.analyze_camera_framing(
        context,
        object_names=_name_list(args.get("object_names")),
        camera_name=str(args.get("camera_name") or ""),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        sample_step=_bounded_int(args.get("sample_step"), 8, minimum=1, maximum=10000),
        margin=float(args.get("margin", 0.05)),
        selected_only=bool(args.get("selected_only", False)),
    )


def analyze_motion_physics(context, args):
    return animation_analysis.analyze_motion_physics(
        context,
        object_names=_name_list(args.get("object_names")),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        sample_step=_bounded_int(args.get("sample_step"), 2, minimum=1, maximum=10000),
        max_speed=_optional_float(args.get("max_speed")),
        max_acceleration=_optional_float(args.get("max_acceleration")),
        selected_only=bool(args.get("selected_only", False)),
    )


def compare_animation_to_brief(context, args):
    return animation_analysis.compare_animation_to_brief(
        context,
        brief=args.get("brief") if isinstance(args.get("brief"), dict) else None,
        prompt=str(args.get("prompt") or ""),
        subject_names=_name_list(args.get("subject_names")),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
    )


def review_playblast_against_brief(context, args):
    return animation_analysis.review_playblast_against_brief(
        context,
        playblast=args.get("playblast") if isinstance(args.get("playblast"), dict) else None,
        brief=args.get("brief") if isinstance(args.get("brief"), dict) else None,
        prompt=str(args.get("prompt") or ""),
    )


def review_inspection_renders_against_brief(context, args):
    return animation_analysis.review_inspection_renders_against_brief(
        context,
        inspection_render_metadata=args.get("inspection_render") if isinstance(args.get("inspection_render"), dict) else None,
        brief=args.get("brief") if isinstance(args.get("brief"), dict) else None,
        prompt=str(args.get("prompt") or ""),
    )


def repair_animation_from_findings(context, args):
    return animation_analysis.repair_animation_from_findings(
        context,
        findings=args.get("findings") if isinstance(args.get("findings"), list) else [],
        brief=args.get("brief") if isinstance(args.get("brief"), dict) else None,
    )


def run_animation_repair_loop(context, args):
    brief = args.get("brief") if isinstance(args.get("brief"), dict) else None
    prompt = str(args.get("prompt") or "")
    latest_playblast = args.get("playblast") if isinstance(args.get("playblast"), dict) else None
    seed_findings = args.get("findings") if isinstance(args.get("findings"), list) else []
    seed_operations = args.get("repair_operations") if isinstance(args.get("repair_operations"), list) else []
    max_iterations = _bounded_int(args.get("max_iterations"), 2, minimum=1, maximum=4)
    max_operations = _bounded_int(args.get("max_operations"), 4, minimum=1, maximum=12)
    apply_mutating = bool(args.get("apply_mutating_repairs", True))
    recapture_after_mutation = bool(args.get("recapture_after_mutation", True))
    requested_allowed_tools = set(_name_list(args.get("allowed_tools")))
    allowed_tools = set(_REPAIR_LOOP_DEFAULT_TOOLS)
    if requested_allowed_tools:
        allowed_tools.intersection_update(requested_allowed_tools)
    frame_start, frame_end = _brief_frame_range(context, brief or {})

    reviews = []
    executed = []
    skipped = []
    executed_keys = set()
    final_review = {}
    pending_seed_operations = list(seed_operations)

    for iteration in range(1, max_iterations + 1):
        if pending_seed_operations:
            review = {
                "ok": True,
                "status": "needs_repair",
                "message": "Using caller-provided repair operations",
                "findings": seed_findings,
                "repair_operations": pending_seed_operations,
            }
        else:
            review = _repair_loop_review(context, playblast=latest_playblast, brief=brief, prompt=prompt)
        final_review = review
        operations = list(review.get("repair_operations") or [])
        reviews.append(
            {
                "iteration": iteration,
                "status": review.get("status", ""),
                "finding_count": len(review.get("findings") or []),
                "repair_operation_count": len(operations),
            }
        )
        pending_seed_operations = []
        if review.get("status") == "pass":
            break

        executed_this_iteration = []
        mutating_this_iteration = False
        captured_this_iteration = False
        for operation_index, operation in enumerate(operations):
            if len(executed) >= max_operations:
                break
            tool, tool_args = _repair_operation_parts(operation)
            key = _repair_operation_key(tool, tool_args)
            mutates = _repair_operation_mutates(tool, operation)
            blocker = _repair_operation_blocker(tool, tool_args)
            reason = ""
            if key in executed_keys:
                reason = "operation already executed in this repair loop"
            elif tool not in allowed_tools:
                reason = "tool is not in allowed_tools for this repair loop"
            elif mutates and not apply_mutating:
                reason = "mutating repairs are disabled for this repair loop"
            elif blocker:
                reason = blocker
            if reason:
                skipped.append({"iteration": iteration, "operation_index": operation_index, "tool": tool, "reason": reason, "operation": operation})
                continue

            result = _execute_repair_tool(context, tool, tool_args)
            executed_keys.add(key)
            item = {
                "iteration": iteration,
                "operation_index": operation_index,
                "tool": tool,
                "arguments": tool_args,
                "ok": bool(result.get("ok")),
                "message": str(result.get("message") or ""),
                "mutates_scene": mutates,
                "source_finding_index": operation.get("source_finding_index") if isinstance(operation, dict) else None,
                "result": result,
            }
            executed.append(item)
            executed_this_iteration.append(item)
            mutating_this_iteration = mutating_this_iteration or mutates
            captured_this_iteration = captured_this_iteration or tool == "capture_animation_playblast"
            if isinstance(result.get("playblast"), dict):
                latest_playblast = result["playblast"]

        if (
            mutating_this_iteration
            and recapture_after_mutation
            and not captured_this_iteration
            and len(executed) < max_operations
            and "capture_animation_playblast" in allowed_tools
        ):
            capture_args = {
                "frame_start": frame_start,
                "frame_end": frame_end,
                "max_frames": 12,
                "brief": _repair_loop_brief_text(brief or {}, prompt),
            }
            result = _execute_repair_tool(context, "capture_animation_playblast", capture_args)
            item = {
                "iteration": iteration,
                "operation_index": -1,
                "tool": "capture_animation_playblast",
                "arguments": capture_args,
                "ok": bool(result.get("ok")),
                "message": str(result.get("message") or ""),
                "mutates_scene": False,
                "source_finding_index": None,
                "result": result,
            }
            executed.append(item)
            executed_this_iteration.append(item)
            captured_this_iteration = True
            if isinstance(result.get("playblast"), dict):
                latest_playblast = result["playblast"]

        if not executed_this_iteration:
            break
        final_review = _repair_loop_review(context, playblast=latest_playblast, brief=brief, prompt=prompt)
        reviews.append(
            {
                "iteration": f"{iteration}.review",
                "status": final_review.get("status", ""),
                "finding_count": len(final_review.get("findings") or []),
                "repair_operation_count": len(final_review.get("repair_operations") or []),
            }
        )
        if final_review.get("status") == "pass":
            break

    if final_review.get("status") == "pass":
        status = "pass"
    elif executed:
        status = "repairs_applied_needs_review"
    elif skipped:
        status = "needs_user_planning"
    else:
        status = "needs_repair"
    return {
        "ok": True,
        "message": f"Animation repair loop finished with status: {status}",
        "status": status,
        "executed_count": len(executed),
        "skipped_count": len(skipped),
        "reviews": reviews,
        "executed_operations": executed,
        "skipped_operations": skipped,
        "final_review": final_review,
        "latest_playblast": latest_playblast or {},
        "mutates_scene": any(item.get("mutates_scene") for item in executed),
        "pending_preview": bool(getattr(context.scene.claude_blender, "pending_preview", False)) if hasattr(context.scene, "claude_blender") else False,
    }


def create_shape_key(context, args):
    return advanced_helpers.create_shape_key(
        context,
        object_name=str(args.get("object_name") or ""),
        key_name=str(args.get("key_name") or "Agent Bridge Shape"),
        value=float(args.get("value", 0.0)),
        label=args.get("label", "Create shape key"),
    )


def animate_shape_key(context, args):
    return advanced_helpers.animate_shape_key(
        context,
        object_name=str(args.get("object_name") or ""),
        key_name=str(args.get("key_name") or "Agent Bridge Shape"),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        value_start=float(args.get("value_start", 0.0)),
        value_end=float(args.get("value_end", 1.0)),
        create_if_missing=bool(args.get("create_if_missing", True)),
        label=args.get("label", "Animate shape key"),
    )


def animate_object_bounce(context, args):
    active = context.active_object.name if context.active_object else ""
    return advanced_helpers.animate_object_bounce(
        context,
        object_name=str(args.get("object_name") or active),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        axis=str(args.get("axis") or "Z"),
        distance=float(args.get("distance", 2.0)),
        cycles=_bounded_int(args.get("cycles"), 1, minimum=1, maximum=24),
        interpolation=str(args.get("interpolation") or "BEZIER"),
        label=args.get("label", "Animate object bounce"),
    )


def create_progressive_bounce_animation(context, args):
    active = context.active_object.name if context.active_object else ""
    return advanced_helpers.create_progressive_bounce_animation(
        context,
        object_name=str(args.get("object_name") or active),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        axis=str(args.get("axis") or "Z"),
        distance=float(args.get("distance", 2.0)),
        cycles=_bounded_int(args.get("cycles"), 2, minimum=1, maximum=24),
        scale_end_factor=float(args.get("scale_end_factor", 0.6)),
        interpolation=str(args.get("interpolation") or "BEZIER"),
        label=args.get("label", "Create progressive bounce animation"),
    )


def animate_material_property(context, args):
    active = context.active_object.name if context.active_object else ""
    return advanced_helpers.animate_material_property(
        context,
        material_name=str(args.get("material_name") or ""),
        object_name=str(args.get("object_name") or active),
        property_name=str(args.get("property_name") or "base_color"),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        value_start=args.get("value_start"),
        value_end=args.get("value_end"),
        create_if_missing=bool(args.get("create_if_missing", True)),
        interpolation=str(args.get("interpolation") or "LINEAR"),
        label=args.get("label", "Animate material property"),
    )


def animate_light_property(context, args):
    active = context.active_object.name if context.active_object else ""
    return advanced_helpers.animate_light_property(
        context,
        light_name=str(args.get("light_name") or active),
        property_name=str(args.get("property_name") or "energy"),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        value_start=args.get("value_start"),
        value_end=args.get("value_end"),
        interpolation=str(args.get("interpolation") or "LINEAR"),
        label=args.get("label", "Animate light property"),
    )


def create_follow_path_animation(context, args):
    active = context.active_object.name if context.active_object else ""
    return advanced_helpers.create_follow_path_animation(
        context,
        object_name=str(args.get("object_name") or active),
        path_name=str(args.get("path_name") or ""),
        path_points=args.get("path_points") or [],
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        constraint_name=str(args.get("constraint_name") or "Agent Bridge Follow Path"),
        follow_curve=bool(args.get("follow_curve", True)),
        interpolation=str(args.get("interpolation") or "LINEAR"),
        label=args.get("label", "Create follow path animation"),
    )


def set_action_interpolation(context, args):
    return advanced_helpers.set_action_interpolation(
        context,
        action_names=_name_list(args.get("action_names")),
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", False)),
        interpolation=str(args.get("interpolation") or "LINEAR"),
        easing=str(args.get("easing") or ""),
        label=args.get("label", "Set action interpolation"),
    )


def retime_actions(context, args):
    return advanced_helpers.retime_actions(
        context,
        action_names=_name_list(args.get("action_names")),
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", False)),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        snap_to_integer=bool(args.get("snap_to_integer", True)),
        label=args.get("label", "Retime actions"),
    )


def add_action_cycles(context, args):
    return advanced_helpers.add_action_cycles(
        context,
        action_names=_name_list(args.get("action_names")),
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", False)),
        mode_before=str(args.get("mode_before") or "NONE"),
        mode_after=str(args.get("mode_after") or "REPEAT"),
        replace_existing=bool(args.get("replace_existing", False)),
        label=args.get("label", "Add action cycles"),
    )


def clear_animation(context, args):
    return advanced_helpers.clear_animation(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        include_object_animation=bool(args.get("include_object_animation", True)),
        include_data_animation=bool(args.get("include_data_animation", True)),
        include_shape_key_animation=bool(args.get("include_shape_key_animation", True)),
        include_material_animation=bool(args.get("include_material_animation", False)),
        label=args.get("label", "Clear animation"),
    )


def set_animation_preview_range(context, args):
    return advanced_helpers.set_animation_preview_range(
        context,
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        current_frame=args.get("current_frame"),
        use_preview_range=bool(args.get("use_preview_range", True)),
        label=args.get("label", "Set animation preview range"),
    )


def create_turntable_animation(context, args):
    active = context.active_object.name if context.active_object else ""
    return advanced_helpers.create_turntable_animation(
        context,
        object_name=str(args.get("object_name") or active),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        axis=str(args.get("axis") or "Z"),
        revolutions=float(args.get("revolutions", 1.0)),
        add_cycles=bool(args.get("add_cycles", False)),
        label=args.get("label", "Create turntable animation"),
    )


def create_pulse_animation(context, args):
    active = context.active_object.name if context.active_object else ""
    emission_strength_end = args.get("emission_strength_end")
    return advanced_helpers.create_pulse_animation(
        context,
        object_name=str(args.get("object_name") or active),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        scale_factor=float(args.get("scale_factor", 1.15)),
        emission_strength_end=float(emission_strength_end) if emission_strength_end is not None else None,
        label=args.get("label", "Create pulse animation"),
    )


def create_reveal_animation(context, args):
    active = context.active_object.name if context.active_object else ""
    return advanced_helpers.create_reveal_animation(
        context,
        object_name=str(args.get("object_name") or active),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        scale_start=float(args.get("scale_start", 0.01)),
        scale_end=float(args.get("scale_end", 1.0)),
        fade_material=bool(args.get("fade_material", True)),
        label=args.get("label", "Create reveal animation"),
    )


def create_staggered_motion(context, args):
    return advanced_helpers.create_staggered_motion(
        context,
        object_names=_name_list(args.get("object_names")),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        duration=_bounded_int(args.get("duration"), 24, minimum=1, maximum=10000),
        frame_step=_bounded_int(args.get("frame_step"), 6, minimum=0, maximum=10000),
        location_delta=_float_list(args.get("location_delta"), 3, (0.0, 0.0, 1.0)),
        interpolation=str(args.get("interpolation") or "BEZIER"),
        label=args.get("label", "Create staggered motion"),
    )


def block_key_poses(context, args):
    return advanced_helpers.block_key_poses(
        context,
        object_names=_name_list(args.get("object_names")),
        poses=args.get("poses") if isinstance(args.get("poses"), list) else [],
        selected_only=bool(args.get("selected_only", False)),
        interpolation=str(args.get("interpolation") or "CONSTANT"),
        label=args.get("label", "Block key poses"),
    )


def add_breakdown_pose(context, args):
    return advanced_helpers.add_breakdown_pose(
        context,
        object_names=_name_list(args.get("object_names")),
        frame=args.get("frame"),
        previous_frame=args.get("previous_frame"),
        next_frame=args.get("next_frame"),
        factor=float(args.get("factor", 0.5)),
        location=_optional_float_list(args.get("location"), 3, (0.0, 0.0, 0.0)),
        rotation=_optional_float_list(args.get("rotation"), 3, (0.0, 0.0, 0.0)),
        scale=_optional_float_list(args.get("scale"), 3, (1.0, 1.0, 1.0)),
        paths=_name_list(args.get("paths")),
        selected_only=bool(args.get("selected_only", False)),
        interpolation=str(args.get("interpolation") or "CONSTANT"),
        label=args.get("label", "Add breakdown pose"),
    )


def set_pose_hold(context, args):
    return advanced_helpers.set_pose_hold(
        context,
        object_names=_name_list(args.get("object_names")),
        frame=args.get("frame"),
        hold_frames=_bounded_int(args.get("hold_frames"), 4, minimum=1, maximum=10000),
        paths=_name_list(args.get("paths")),
        selected_only=bool(args.get("selected_only", False)),
        interpolation=str(args.get("interpolation") or "CONSTANT"),
        label=args.get("label", "Set pose hold"),
    )


def create_motion_arc(context, args):
    return advanced_helpers.create_motion_arc(
        context,
        object_names=_name_list(args.get("object_names")),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        sample_step=_bounded_int(args.get("sample_step"), 4, minimum=1, maximum=10000),
        selected_only=bool(args.get("selected_only", False)),
        name_prefix=str(args.get("name_prefix") or "Agent Bridge Motion Arc"),
        bevel_depth=float(args.get("bevel_depth", 0.015)),
        color=_float_list(args.get("color"), 4, (0.08, 0.45, 1.0, 1.0)),
        label=args.get("label", "Create motion arc"),
    )


def create_camera_dolly_animation(context, args):
    return advanced_helpers.create_camera_dolly_animation(
        context,
        camera_name=str(args.get("camera_name") or ""),
        target_name=str(args.get("target_name") or ""),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        start_location=_optional_float_list(args.get("start_location"), 3, (0.0, 0.0, 0.0)),
        end_location=_optional_float_list(args.get("end_location"), 3, (0.0, 0.0, 0.0)),
        lens_start=args.get("lens_start"),
        lens_end=args.get("lens_end"),
        interpolation=str(args.get("interpolation") or "BEZIER"),
        label=args.get("label", "Create camera dolly animation"),
    )


def create_directed_animation_shot(context, args):
    return advanced_helpers.create_directed_animation_shot(
        context,
        shot_type=str(args.get("shot_type") or "camera_push_reveal"),
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        travel_axis=str(args.get("travel_axis") or "X"),
        travel_distance=float(args.get("travel_distance", 2.0)),
        scale_start=float(args.get("scale_start", 0.2)),
        scale_end=float(args.get("scale_end", 1.0)),
        rotation_revolutions=float(args.get("rotation_revolutions", 1.0)),
        camera_name=str(args.get("camera_name") or ""),
        target_name=str(args.get("target_name") or ""),
        create_camera=bool(args.get("create_camera", True)),
        lens_start=args.get("lens_start"),
        lens_end=args.get("lens_end"),
        interpolation=str(args.get("interpolation") or "BEZIER"),
        label=args.get("label", "Create directed animation shot"),
    )


def set_scene_frame_range(context, args):
    return live_preview.set_scene_frame_range(
        context,
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        current_frame=args.get("current_frame"),
        fps=args.get("fps"),
        label=args.get("label", "Set timeline"),
    )


def animate_selected_transform(context, args):
    return live_preview.animate_selected_transform(
        context,
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        location_start=_optional_float_list(args.get("location_start"), 3, (0.0, 0.0, 0.0)),
        location_end=_optional_float_list(args.get("location_end"), 3, (0.0, 0.0, 0.0)),
        rotation_start=_optional_float_list(args.get("rotation_start"), 3, (0.0, 0.0, 0.0)),
        rotation_end=_optional_float_list(args.get("rotation_end"), 3, (0.0, 0.0, 0.0)),
        scale_start=_optional_float_list(args.get("scale_start"), 3, (1.0, 1.0, 1.0)),
        scale_end=_optional_float_list(args.get("scale_end"), 3, (1.0, 1.0, 1.0)),
        label=args.get("label", "Animate selected transform"),
    )


def create_camera_orbit(context, args):
    active = context.active_object.name if context.active_object else ""
    return live_preview.create_camera_orbit(
        context,
        target_name=str(args.get("target_name") or active),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        radius=float(args.get("radius", 5.0)),
        height=float(args.get("height", 2.5)),
        name=str(args.get("name") or "Agent Bridge Orbit Camera"),
        lens=float(args.get("lens", 35.0)),
        label=args.get("label", "Create camera orbit"),
    )


def register(handler_registry, specs):
    for spec in specs:
        try:
            handler = globals()[spec.handler_key]
        except KeyError as exc:
            raise KeyError(f"Missing handler {spec.handler_key} for {spec.name}") from exc
        handler_registry.register(spec.name, handler)
