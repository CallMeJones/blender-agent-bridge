"""Blender-only handlers for the camera_render_evidence domain."""

from __future__ import annotations

from .. import handler_runtime as _runtime

for _runtime_name, _runtime_value in vars(_runtime).items():
    if not _runtime_name.startswith("__"):
        globals()[_runtime_name] = _runtime_value
del _runtime_name, _runtime_value


def get_render_camera_compositor_details(context, args):
    return world_model.render_camera_compositor_details(context)


def set_render_settings(context, args):
    return advanced_helpers.set_render_settings(
        context,
        engine=str(args.get("engine") or ""),
        resolution=args.get("resolution"),
        fps=args.get("fps"),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        film_transparent=args.get("film_transparent"),
        quality_preset=str(args.get("quality_preset") or ""),
        samples=args.get("samples"),
        denoise=args.get("denoise"),
        view_transform=str(args.get("view_transform") or ""),
        look=str(args.get("look") or ""),
        exposure=args.get("exposure"),
        gamma=args.get("gamma"),
        label=args.get("label", "Set render settings"),
    )


def set_render_engine(context, args):
    return advanced_helpers.set_render_engine(
        context,
        engine=str(args.get("engine") or ""),
        quality_preset=str(args.get("quality_preset") or ""),
        samples=args.get("samples"),
        denoise=args.get("denoise"),
        view_transform=str(args.get("view_transform") or ""),
        look=str(args.get("look") or ""),
        exposure=args.get("exposure"),
        gamma=args.get("gamma"),
        label=args.get("label", "Set render engine"),
    )


def configure_render_outputs(context, args):
    return advanced_helpers.configure_render_outputs(
        context,
        view_layer_name=str(args.get("view_layer_name") or ""),
        enabled_passes=args.get("enabled_passes") or [],
        disabled_passes=args.get("disabled_passes") or [],
        aovs=args.get("aovs") or [],
        clear_existing_aovs=bool(args.get("clear_existing_aovs", False)),
        pass_alpha_threshold=args.get("pass_alpha_threshold"),
        pass_cryptomatte_depth=args.get("pass_cryptomatte_depth"),
        label=args.get("label", "Configure render outputs"),
    )


def set_camera_settings(context, args):
    return advanced_helpers.set_camera_settings(
        context,
        camera_name=str(args.get("camera_name") or ""),
        lens=args.get("lens"),
        sensor_width=args.get("sensor_width"),
        dof_enabled=args.get("dof_enabled"),
        focus_object_name=str(args.get("focus_object_name") or ""),
        aperture_fstop=args.get("aperture_fstop"),
        label=args.get("label", "Set camera settings"),
    )


def set_world_background(context, args):
    return advanced_helpers.set_world_background(
        context,
        color=_float_list(args.get("color"), 3, (0.05, 0.05, 0.07)),
        label=args.get("label", "Set world background"),
    )


def create_studio_product_stage(context, args):
    return advanced_helpers.create_studio_product_stage(
        context,
        target_name=str(args.get("target_name") or ""),
        stage_name=str(args.get("stage_name") or "Agent Bridge Product Stage"),
        floor=bool(args.get("floor", True)),
        backdrop=bool(args.get("backdrop", True)),
        lighting=bool(args.get("lighting", True)),
        camera=bool(args.get("camera", True)),
        label=args.get("label", "Create studio product stage"),
    )


def apply_lighting_preset(context, args):
    return advanced_helpers.apply_lighting_preset(
        context,
        target_name=str(args.get("target_name") or ""),
        preset=str(args.get("preset") or "product_softbox"),
        rig_name=str(args.get("rig_name") or "Agent Bridge Lighting"),
        label=args.get("label", "Apply lighting preset"),
    )


def create_product_turntable_setup(context, args):
    return advanced_helpers.create_product_turntable_setup(
        context,
        target_name=str(args.get("target_name") or ""),
        frame_start=int(args.get("frame_start", 1)),
        frame_end=int(args.get("frame_end", 120)),
        revolutions=float(args.get("revolutions", 1.0)),
        radius=float(args.get("radius", 0.0)),
        height=float(args.get("height", 0.0)),
        setup_name=str(args.get("setup_name") or "Agent Bridge Product Turntable"),
        create_stage=bool(args.get("create_stage", True)),
        label=args.get("label", "Create product turntable setup"),
    )


def create_lookdev_turntable_review(context, args):
    return advanced_helpers.create_lookdev_turntable_review(
        context,
        target_name=str(args.get("target_name") or ""),
        frame_start=int(args.get("frame_start", 1)),
        frame_end=int(args.get("frame_end", 96)),
        revolutions=float(args.get("revolutions", 1.0)),
        setup_name=str(args.get("setup_name") or "Agent Bridge Lookdev Turntable"),
        create_stage=bool(args.get("create_stage", True)),
        create_turntable=bool(args.get("create_turntable", True)),
        render_engine=str(args.get("render_engine") or "auto"),
        quality_preset=str(args.get("quality_preset") or "preview"),
        samples=args.get("samples"),
        denoise=bool(args.get("denoise", True)),
        view_transform=str(args.get("view_transform") or ""),
        look=str(args.get("look") or ""),
        exposure=args.get("exposure"),
        gamma=args.get("gamma"),
        capture_inspection=bool(args.get("capture_inspection", True)),
        views=_name_list(args.get("views")),
        resolution_x=_bounded_int(args.get("resolution_x"), 320, minimum=64, maximum=4096),
        resolution_y=_bounded_int(args.get("resolution_y"), 240, minimum=64, maximum=4096),
        distance_factor=float(args.get("distance_factor", 2.6)),
        label=args.get("label", "Create look-dev turntable review"),
    )


def add_light(context, args):
    light_type = str(args.get("light_type") or "POINT").upper()
    if light_type not in {"POINT", "SUN", "SPOT", "AREA"}:
        light_type = "POINT"
    return live_preview.add_light(
        context,
        light_type=light_type,
        name=str(args.get("name") or "Agent Bridge Light"),
        location=_float_list(args.get("location"), 3, (3.0, -4.0, 4.0)),
        energy=float(args.get("energy", 500.0)),
        color=_float_list(args.get("color"), 3, (1.0, 0.92, 0.82)),
        label=args.get("label", "Add light"),
    )


def add_camera(context, args):
    return live_preview.add_camera(
        context,
        name=str(args.get("name") or "Agent Bridge Camera"),
        location=_float_list(args.get("location"), 3, (4.0, -6.0, 4.0)),
        rotation=_float_list(args.get("rotation"), 3, (1.1, 0.0, 0.65)),
        lens=float(args.get("lens", 50.0)),
        label=args.get("label", "Add camera"),
    )


def set_active_camera(context, args):
    return live_preview.set_active_camera(
        context,
        camera_name=str(args.get("camera_name") or ""),
        label=args.get("label", "Set active camera"),
    )


def capture_viewport(context, args):
    prefs = preferences.get_preferences(context)
    max_bytes = args.get("max_bytes")
    if max_bytes is None:
        max_bytes = getattr(prefs, "max_screenshot_bytes", viewport_capture.DEFAULT_MAX_BYTES)
    metadata, attachments = viewport_capture.capture_viewport(
        context,
        capture_dir=getattr(prefs, "capture_cache_dir", None),
        max_bytes=_bounded_int(max_bytes, viewport_capture.DEFAULT_MAX_BYTES, minimum=262144, maximum=20 * 1024 * 1024),
    )
    return {
        "ok": bool(metadata.get("available")),
        "message": metadata.get("note") or "Viewport screenshot capture complete",
        "visual_context": metadata,
        "attachment_available": bool(attachments),
        "attachment_keys": sorted(attachments.keys()),
    }


def capture_animation_playblast(context, args):
    prefs = preferences.get_preferences(context)
    max_bytes = args.get("max_bytes")
    if max_bytes is None:
        max_bytes = getattr(prefs, "max_screenshot_bytes", viewport_capture.DEFAULT_MAX_BYTES)
    metadata = playblast_capture.capture_animation_playblast(
        context,
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        max_frames=_bounded_int(
            args.get("max_frames"),
            playblast_capture.DEFAULT_MAX_FRAMES,
            minimum=1,
            maximum=playblast_capture.MAX_PLAYBLAST_FRAMES,
        ),
        max_bytes=_bounded_int(max_bytes, viewport_capture.DEFAULT_MAX_BYTES, minimum=262144, maximum=20 * 1024 * 1024),
        quality=str(args.get("quality") or playblast_capture.DEFAULT_PLAYBLAST_QUALITY),
        max_width=args.get("max_width"),
        max_height=args.get("max_height"),
        brief=str(args.get("brief") or ""),
        shading=str(args.get("shading") or ""),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
    )
    return {
        "ok": bool(metadata.get("available")),
        "message": metadata.get("note") or "Animation playblast capture complete",
        "playblast": metadata,
    }


def capture_object_inspection_renders(context, args):
    prefs = preferences.get_preferences(context)
    metadata_result = inspection_render.capture_object_inspection_renders(
        context,
        object_names=_name_list(args.get("object_names")),
        views=_name_list(args.get("views")),
        frame=args.get("frame"),
        resolution_x=_bounded_int(args.get("resolution_x"), 800, minimum=64, maximum=4096),
        resolution_y=_bounded_int(args.get("resolution_y"), 600, minimum=64, maximum=4096),
        lens=_bounded_float(args.get("lens"), 50.0, minimum=1.0, maximum=300.0),
        distance_factor=_bounded_float(args.get("distance_factor"), 3.0, minimum=0.5, maximum=20.0),
        camera_name=str(args.get("camera_name") or "Agent Bridge Inspection Camera"),
        note=str(args.get("note") or args.get("brief") or ""),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
    )
    return metadata_result


def get_visual_evidence_resources(context, args):
    prefs = preferences.get_preferences(context)
    return lab_parity.get_visual_evidence_resources(
        context,
        include_unavailable=bool(args.get("include_unavailable", True)),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
    )


def render_scene_thumbnail(context, args):
    prefs = preferences.get_preferences(context)
    return lab_parity.render_scene_thumbnail(
        context,
        filepath=str(args.get("filepath") or ""),
        frame=args.get("frame"),
        resolution_x=_bounded_int(args.get("resolution_x"), 512, minimum=32, maximum=4096),
        resolution_y=_bounded_int(args.get("resolution_y"), 512, minimum=32, maximum=4096),
        camera_name=str(args.get("camera_name") or ""),
        note=str(args.get("note") or ""),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
        allow_blocking_render=bool(args.get("allow_blocking_render", False)),
    )


def start_render_job(context, args):
    prefs = preferences.get_preferences(context)
    return render_jobs.start_render_job(
        context,
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        resolution_x=args.get("resolution_x"),
        resolution_y=args.get("resolution_y"),
        resolution_percentage=args.get("resolution_percentage"),
        samples=args.get("samples"),
        fps=args.get("fps"),
        camera_name=str(args.get("camera_name") or ""),
        output_kind=str(args.get("output_kind") or "frames"),
        quality=str(args.get("quality") or "auto"),
        job_name=str(args.get("job_name") or ""),
        note=str(args.get("note") or ""),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
    )


def get_render_job_status(context, args):
    prefs = preferences.get_preferences(context)
    job_id = str(args.get("job_id") or "")
    job = render_jobs.render_job_status(
        job_id,
        context=context,
        preferred_dir=getattr(prefs, "capture_cache_dir", None),
    )
    return {
        "ok": bool(job.get("available", False)),
        "message": "Render job status collected" if job.get("available") else job.get("message", "Render job was not found"),
        "render_job": job,
    }


def cancel_render_job(context, args):
    prefs = preferences.get_preferences(context)
    return render_jobs.cancel_render_job(
        str(args.get("job_id") or ""),
        context=context,
        preferred_dir=getattr(prefs, "capture_cache_dir", None),
    )


def assemble_render_job_video(context, args):
    prefs = preferences.get_preferences(context)
    return render_jobs.assemble_render_job_video(
        str(args.get("job_id") or ""),
        context=context,
        preferred_dir=getattr(prefs, "capture_cache_dir", None),
        fps=args.get("fps"),
        output_path=str(args.get("output_path") or ""),
        quality=str(args.get("quality") or "HIGH"),
        overwrite=bool(args.get("overwrite", True)),
        allow_partial=bool(args.get("allow_partial", False)),
    )


def validate_render_job_output(context, args):
    prefs = preferences.get_preferences(context)
    validation = render_jobs.validate_render_job_output(
        str(args.get("job_id") or ""),
        context=context,
        preferred_dir=getattr(prefs, "capture_cache_dir", None),
        require_video=bool(args.get("require_video", True)),
        min_video_size_bytes=args.get("min_video_size_bytes", 1),
    )
    return {
        "ok": bool(validation.get("ok")),
        "message": validation.get("message", "Render output validation complete"),
        "validation": validation,
    }


def register(handler_registry, specs):
    for spec in specs:
        try:
            handler = globals()[spec.handler_key]
        except KeyError as exc:
            raise KeyError(f"Missing handler {spec.handler_key} for {spec.name}") from exc
        handler_registry.register(spec.name, handler)
