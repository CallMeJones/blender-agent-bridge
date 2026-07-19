"""Blender-only handlers for the rigging_simulation domain."""

from __future__ import annotations

from .. import handler_runtime as _runtime

for _runtime_name, _runtime_value in vars(_runtime).items():
    if not _runtime_name.startswith("__"):
        globals()[_runtime_name] = _runtime_value
del _runtime_name, _runtime_value


def get_rigging_details(context, args):
    return world_model.rigging_details(
        context,
        object_names=_name_list(args.get("object_names")),
        max_objects=_bounded_int(args.get("max_objects"), 12, maximum=50),
    )


def get_shape_key_details(context, args):
    return world_model.shape_key_details(
        context,
        object_names=_name_list(args.get("object_names")),
        max_objects=_bounded_int(args.get("max_objects"), 12, maximum=50),
    )


def get_curve_text_details(context, args):
    return world_model.curve_text_details(
        context,
        object_names=_name_list(args.get("object_names")),
        max_objects=_bounded_int(args.get("max_objects"), 20, maximum=80),
    )


def get_simulation_details(context, args):
    return world_model.simulation_details(
        context,
        object_names=_name_list(args.get("object_names")),
        max_objects=_bounded_int(args.get("max_objects"), 20, maximum=80),
    )


def inspect_simulation_bake(context, args):
    return world_model.inspect_simulation_bake(
        context,
        object_names=_name_list(args.get("object_names")),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        sample_count=_bounded_int(args.get("sample_count"), 8, minimum=1, maximum=48),
        max_objects=_bounded_int(args.get("max_objects"), 20, maximum=80),
    )


def stage_persistent_simulation_bake(context, args):
    object_names = _name_list(args.get("object_names"))
    frame_start = _bounded_int(args.get("frame_start"), context.scene.frame_start, minimum=-100000, maximum=100000)
    frame_end = _bounded_int(args.get("frame_end"), context.scene.frame_end, minimum=-100000, maximum=100000)
    if frame_end < frame_start:
        frame_start, frame_end = frame_end, frame_start
    sample = world_model.inspect_simulation_bake(
        context,
        object_names=object_names,
        frame_start=frame_start,
        frame_end=frame_end,
        sample_count=2,
        max_objects=_bounded_int(args.get("max_objects"), 20, maximum=80),
    )
    if object_names and not sample.get("object_names"):
        return {
            "ok": False,
            "message": "No requested simulation-capable objects were found to bake",
            "inspection": sample,
            "requires_user_approval": False,
        }
    if not sample.get("object_names") and not ((sample.get("bake_status") or {}).get("rigid_body_world_cache")):
        return {
            "ok": False,
            "message": "No simulation caches were found to bake",
            "inspection": sample,
            "requires_user_approval": False,
        }
    include_world = bool(args.get("include_scene_rigid_body_world", True))
    clear_existing = bool(args.get("clear_existing", False))
    code = _simulation_bake_script(
        object_names=object_names,
        frame_start=frame_start,
        frame_end=frame_end,
        clear_existing=clear_existing,
        include_scene_rigid_body_world=include_world,
    )
    range_scope = "requested objects plus scene rigid-body world" if object_names else "all simulation caches in the active scene"
    scope_warning = (
        "Blender's bpy.ops.ptcache.bake_all operator is scene-wide; object_names limit inspection "
        "and cache-range preparation, not the bake operator scope."
    )
    staged = script_runner.stage_script(
        context,
        code=code,
        intent="Bake persistent Blender simulation point caches with a fixed Agent Bridge template.",
        expected_changes=(
            f"Sets point-cache ranges to frames {frame_start}-{frame_end} for {range_scope}, "
            "then runs the scene-wide bpy.ops.ptcache.bake_all(bake=True) operator. "
            "This can take time and writes persistent cache state."
        ),
        risk_level="high",
        target_objects=object_names,
    )
    result = {
        "ok": bool(staged.get("ok")),
        "message": "Persistent simulation bake script staged for explicit approval",
        "inspection": sample,
        "staged": staged,
        "frame_range": [frame_start, frame_end],
        "range_preparation_scope": range_scope,
        "bake_operator_scope": "scene_wide_ptcache_bake_all",
        "scope_warning": scope_warning,
        "clear_existing": clear_existing,
        "include_scene_rigid_body_world": include_world,
        "requires_user_approval": bool(staged.get("requires_user_approval", True)),
        "requires_explicit_one_time_approval": True,
        "trust_window_auto_run_allowed": False,
        "approval_policy": (
            "Persistent simulation/cache bake and free operators require a fresh one-time user approval; "
            "session-wide external script trust cannot auto-run them."
        ),
        "user_action_required": "Approve the staged script with a one-time external run approval in Blender before baking.",
        "recommended_next_step": "Wait for explicit user approval; do not poll bridge recovery or rerun the bake yet.",
        "auto_run_attempted": False,
        "auto_ran": False,
    }
    if not staged.get("ok") or staged.get("analysis", {}).get("blocked"):
        return result
    analysis = staged.get("analysis") or {}
    if bool(args.get("auto_run_if_trusted", True)) and script_runner.external_script_trust_active(context):
        if analysis.get("explicit_approval_required"):
            result.update(
                {
                    "message": "Persistent simulation bake script staged; explicit one-time approval is required",
                    "auto_run_attempted": False,
                    "auto_ran": False,
                    "auto_run_skipped_reason": "explicit_approval_required",
                    "requires_user_approval": True,
                }
            )
            return result
        prefs = preferences.get_preferences(context)
        run_result = script_runner.run_externally_approved_script(
            context,
            "",
            checkpoint_enabled=bool(getattr(prefs, "checkpoints_enabled", True)),
            checkpoint_dir=getattr(prefs, "checkpoint_dir", None),
        )
        result.update(
            {
                "ok": bool(run_result.get("ok")),
                "message": (
                    "Persistent simulation bake script staged and auto-ran under active external script trust"
                    if run_result.get("ok")
                    else "Persistent simulation bake script staged but auto-run failed under active external script trust"
                ),
                "run_result": run_result,
                "auto_run_attempted": True,
                "auto_ran": bool(run_result.get("ok")),
                "auto_run_reason": "external_script_trust_active",
                "requires_user_approval": False,
            }
        )
    return result


def set_rig_pose_hold(context, args):
    return advanced_helpers.set_rig_pose_hold(
        context,
        armature_name=str(args.get("armature_name") or ""),
        bone_names=_name_list(args.get("bone_names")),
        frame=args.get("frame"),
        hold_frames=_bounded_int(args.get("hold_frames"), 4, minimum=1, maximum=60),
        paths=_name_list(args.get("paths")),
        interpolation=str(args.get("interpolation") or "CONSTANT"),
        label=args.get("label", "Set rig pose hold"),
    )


def set_rig_custom_property_keyframes(context, args):
    return advanced_helpers.set_rig_custom_property_keyframes(
        context,
        armature_name=str(args.get("armature_name") or ""),
        property_targets=args.get("property_targets") if isinstance(args.get("property_targets"), list) else [],
        frame=args.get("frame"),
        hold_frames=_bounded_int(args.get("hold_frames"), 4, minimum=1, maximum=60),
        interpolation=str(args.get("interpolation") or "CONSTANT"),
        label=args.get("label", "Set rig custom property keyframes"),
    )


def get_rig_pose_library_details(context, args):
    return advanced_helpers.get_rig_pose_library_details(
        context,
        armature_name=str(args.get("armature_name") or ""),
        action_names=_name_list(args.get("action_names")),
        bone_names=_name_list(args.get("bone_names")),
        paths=_name_list(args.get("paths")),
        max_actions=_bounded_int(args.get("max_actions"), 20, minimum=1, maximum=100),
    )


def apply_rig_pose_from_action(context, args):
    return advanced_helpers.apply_rig_pose_from_action(
        context,
        armature_name=str(args.get("armature_name") or ""),
        action_name=str(args.get("action_name") or ""),
        pose_marker=str(args.get("pose_marker") or ""),
        source_frame=args.get("source_frame"),
        target_frame=args.get("target_frame") if args.get("target_frame") is not None else args.get("frame"),
        hold_frames=_bounded_int(args.get("hold_frames"), 4, minimum=0, maximum=60),
        bone_names=_name_list(args.get("bone_names")),
        paths=_name_list(args.get("paths")),
        key_pose=bool(args.get("key_pose", True)),
        interpolation=str(args.get("interpolation") or "CONSTANT"),
        label=args.get("label", "Apply rig pose from action"),
    )


def apply_rig_pose_marker(context, args):
    return advanced_helpers.apply_rig_pose_marker(
        context,
        armature_name=str(args.get("armature_name") or ""),
        action_name=str(args.get("action_name") or ""),
        pose_marker=str(args.get("pose_marker") or ""),
        target_frame=args.get("target_frame") if args.get("target_frame") is not None else args.get("frame"),
        hold_frames=_bounded_int(args.get("hold_frames"), 4, minimum=0, maximum=60),
        bone_names=_name_list(args.get("bone_names")),
        paths=_name_list(args.get("paths")),
        key_pose=bool(args.get("key_pose", True)),
        interpolation=str(args.get("interpolation") or "CONSTANT"),
        label=args.get("label", "Apply rig pose marker"),
    )


def apply_rig_action_clip(context, args):
    return advanced_helpers.apply_rig_action_clip(
        context,
        armature_name=str(args.get("armature_name") or ""),
        action_name=str(args.get("action_name") or ""),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        source_frame_start=args.get("source_frame_start"),
        source_frame_end=args.get("source_frame_end"),
        interpolation=str(args.get("interpolation") or ""),
        label=args.get("label", "Apply rig action clip"),
    )


def offset_rig_limb_controls(context, args):
    return advanced_helpers.offset_rig_limb_controls(
        context,
        armature_name=str(args.get("armature_name") or ""),
        control_offsets=args.get("control_offsets") if isinstance(args.get("control_offsets"), list) else [],
        bone_names=_name_list(args.get("bone_names")),
        location_delta=_float_list(args.get("location_delta"), 3, (0.0, 0.0, 0.0)) if args.get("location_delta") is not None else None,
        rotation_delta=_float_list(args.get("rotation_delta"), 3, (0.0, 0.0, 0.0)) if args.get("rotation_delta") is not None else None,
        scale_multiplier=_float_list(args.get("scale_multiplier"), 3, (1.0, 1.0, 1.0)) if args.get("scale_multiplier") is not None else None,
        property_targets=args.get("property_targets") if isinstance(args.get("property_targets"), list) else [],
        frame=args.get("frame"),
        hold_frames=_bounded_int(args.get("hold_frames"), 4, minimum=0, maximum=60),
        interpolation=str(args.get("interpolation") or "BEZIER"),
        label=args.get("label", "Offset rig limb controls"),
    )


def add_particle_system_to_selected(context, args):
    return advanced_helpers.add_particle_system_to_selected(
        context,
        name=str(args.get("name") or "Agent Bridge Particles"),
        count=_bounded_int(args.get("count"), 200, maximum=20000),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        lifetime=float(args.get("lifetime", 80.0)),
        particle_size=float(args.get("particle_size", 0.05)),
        label=args.get("label", "Add particle system"),
    )


def create_basic_armature(context, args):
    return advanced_helpers.create_basic_armature(
        context,
        name=str(args.get("name") or "Agent Bridge Armature"),
        location=_float_list(args.get("location"), 3, (0.0, 0.0, 0.0)),
        rotation=_float_list(args.get("rotation"), 3, (0.0, 0.0, 0.0)),
        show_in_front=bool(args.get("show_in_front", True)),
        label=args.get("label", "Create basic armature"),
    )


def add_copy_transform_constraint(context, args):
    return advanced_helpers.add_copy_transform_constraint(
        context,
        target_name=str(args.get("target_name") or ""),
        constraint_type=str(args.get("constraint_type") or "COPY_LOCATION"),
        name=str(args.get("name") or "Agent Bridge Copy Transform"),
        influence=float(args.get("influence", 1.0)),
        label=args.get("label", "Add copy transform constraint"),
    )


def add_cloth_simulation_to_selected(context, args):
    return advanced_helpers.add_cloth_simulation_to_selected(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        name=str(args.get("name") or "Agent Bridge Cloth"),
        quality=_bounded_int(args.get("quality"), 5, minimum=1, maximum=30),
        mass=float(args.get("mass", 0.3)),
        tension_stiffness=float(args.get("tension_stiffness", 5.0)),
        compression_stiffness=float(args.get("compression_stiffness", 5.0)),
        shear_stiffness=float(args.get("shear_stiffness", 5.0)),
        air_damping=float(args.get("air_damping", 1.0)),
        label=args.get("label", "Add cloth simulation"),
    )


def add_track_to_constraint(context, args):
    return live_preview.add_track_to_constraint(
        context,
        target_name=str(args.get("target_name") or ""),
        name=str(args.get("name") or "Agent Bridge Track To"),
        track_axis=str(args.get("track_axis") or "TRACK_NEGATIVE_Z"),
        up_axis=str(args.get("up_axis") or "UP_Y"),
        influence=float(args.get("influence", 1.0)),
        label=args.get("label", "Add Track To constraint"),
    )


def register(handler_registry, specs):
    for spec in specs:
        try:
            handler = globals()[spec.handler_key]
        except KeyError as exc:
            raise KeyError(f"Missing handler {spec.handler_key} for {spec.name}") from exc
        handler_registry.register(spec.name, handler)
