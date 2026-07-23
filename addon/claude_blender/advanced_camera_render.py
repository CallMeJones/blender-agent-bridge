"""Advanced Blender helpers for camera render evidence."""



from __future__ import annotations

import os

import bpy

from . import inspection_render, live_preview

from .advanced_support import (
    _bounds_world,
    _clamped_float,
    _create_area_light,
    _create_cube_object,
    _create_empty_target,
    _existing_light_warning,
    _material_for_color,
    _normalize_frame_range,
    _preserve_selection,
    _record_camera_settings,
    _record_scene_render,
    _scene_light_names,
    _track_to_target,
)

from .advanced_animation import (
    create_turntable_animation,
)



LIGHTING_PRESETS = {
    "product_softbox": [
        ("Key", (-1.2, -1.4, 1.5), 650.0, 1.15, (1.0, 0.93, 0.84)),
        ("Fill", (1.3, -0.9, 0.8), 180.0, 1.7, (0.78, 0.86, 1.0)),
        ("Rim", (0.0, 1.35, 1.15), 360.0, 0.75, (1.0, 1.0, 0.94)),
    ],
    "dramatic_rim": [
        ("Key", (-1.4, -1.1, 1.1), 430.0, 0.75, (1.0, 0.86, 0.7)),
        ("Rim", (1.15, 1.35, 1.55), 850.0, 0.6, (0.68, 0.82, 1.0)),
        ("Top", (0.0, -0.1, 2.0), 150.0, 1.2, (1.0, 0.96, 0.9)),
    ],
    "gallery_even": [
        ("Left Softbox", (-1.35, -0.55, 1.25), 320.0, 1.45, (1.0, 0.95, 0.9)),
        ("Right Softbox", (1.35, -0.55, 1.25), 320.0, 1.45, (0.9, 0.95, 1.0)),
        ("Top Wash", (0.0, 0.0, 2.0), 220.0, 1.8, (1.0, 1.0, 0.96)),
    ],
}

RENDER_QUALITY_PRESETS = {
    "preview": {"resolution": (640, 360), "samples": 32, "denoise": False},
    "lookdev": {"resolution": (1280, 720), "samples": 96, "denoise": True},
    "final": {"resolution": (1920, 1080), "samples": 256, "denoise": True},
}

RENDER_PASS_ALIASES = {
    "combined": "use_pass_combined",
    "z": "use_pass_z",
    "depth": "use_pass_z",
    "mist": "use_pass_mist",
    "normal": "use_pass_normal",
    "position": "use_pass_position",
    "vector": "use_pass_vector",
    "uv": "use_pass_uv",
    "object_index": "use_pass_object_index",
    "material_index": "use_pass_material_index",
    "diffuse_color": "use_pass_diffuse_color",
    "diffuse_direct": "use_pass_diffuse_direct",
    "diffuse_indirect": "use_pass_diffuse_indirect",
    "glossy_color": "use_pass_glossy_color",
    "glossy_direct": "use_pass_glossy_direct",
    "glossy_indirect": "use_pass_glossy_indirect",
    "transmission_color": "use_pass_transmission_color",
    "transmission_direct": "use_pass_transmission_direct",
    "transmission_indirect": "use_pass_transmission_indirect",
    "subsurface_color": "use_pass_subsurface_color",
    "subsurface_direct": "use_pass_subsurface_direct",
    "subsurface_indirect": "use_pass_subsurface_indirect",
    "emit": "use_pass_emit",
    "emission": "use_pass_emit",
    "environment": "use_pass_environment",
    "shadow": "use_pass_shadow",
    "ambient_occlusion": "use_pass_ambient_occlusion",
    "ao": "use_pass_ambient_occlusion",
    "cryptomatte_object": "use_pass_cryptomatte_object",
    "crypto_object": "use_pass_cryptomatte_object",
    "cryptomatte_material": "use_pass_cryptomatte_material",
    "crypto_material": "use_pass_cryptomatte_material",
    "cryptomatte_asset": "use_pass_cryptomatte_asset",
    "crypto_asset": "use_pass_cryptomatte_asset",
    "cryptomatte_accurate": "use_pass_cryptomatte_accurate",
    "grease_pencil": "use_pass_grease_pencil",
}

AOV_TYPES = {"COLOR", "VALUE"}

def _view_layer_render_state(view_layer):
    pass_flags = {}
    rna = getattr(view_layer, "bl_rna", None)
    if view_layer is not None and rna is not None:
        for prop in rna.properties:
            identifier = getattr(prop, "identifier", "")
            if identifier.startswith("use_pass_") or identifier in {"pass_alpha_threshold", "pass_cryptomatte_depth"}:
                try:
                    value = getattr(view_layer, identifier)
                except Exception:
                    continue
                if isinstance(value, bool):
                    pass_flags[identifier] = bool(value)
                elif isinstance(value, (int, float)):
                    pass_flags[identifier] = value
    aovs = []
    for aov in list(getattr(view_layer, "aovs", []) or []):
        aovs.append({"name": str(getattr(aov, "name", "")), "type": str(getattr(aov, "type", "COLOR"))})
    return {"pass_flags": pass_flags, "aovs": aovs}

def _record_view_layer_render_outputs(scene, view_layer):
    transaction = live_preview.begin()
    key = f"scene:{scene.name}:view_layer:{view_layer.name}:render_outputs"
    if key in transaction["before_state"]:
        return
    state = _view_layer_render_state(view_layer)
    transaction["before_state"][key] = {
        "kind": "view_layer_render_outputs",
        "scene_name": scene.name,
        "view_layer_name": view_layer.name,
        "pass_flags": state["pass_flags"],
        "aovs": state["aovs"],
    }
    transaction["changed_data_blocks"].append(f"{scene.name}:{view_layer.name}")

def _record_world_background(world):
    transaction = live_preview.begin()
    key = f"world:{world.name}:background"
    if key in transaction["before_state"]:
        return
    transaction["before_state"][key] = {
        "kind": "world_background",
        "world_name": world.name,
        "color": tuple(float(component) for component in world.color),
    }
    transaction["changed_data_blocks"].append(world.name)

def _record_scene_world(scene):
    transaction = live_preview.begin()
    key = f"scene:{scene.name}:world"
    if key in transaction["before_state"]:
        return
    transaction["before_state"][key] = {
        "kind": "scene_world",
        "scene_name": scene.name,
        "world_name": scene.world.name if scene.world else None,
    }

def _valid_render_engines(scene):
    """Available render engine identifiers, or empty set when introspection fails."""
    try:
        prop = scene.render.bl_rna.properties["engine"]
        return {item.identifier for item in prop.enum_items}
    except Exception:
        return set()

def _normalize_render_quality_preset(quality_preset):
    key = str(quality_preset or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {"draft": "preview", "fast": "preview", "workbench": "preview", "look_dev": "lookdev", "production": "final"}
    key = aliases.get(key, key)
    return key if key in RENDER_QUALITY_PRESETS else ""

def _set_render_sample_count(scene, samples):
    applied = {}
    value = max(1, min(4096, int(samples)))
    cycles = getattr(scene, "cycles", None)
    if cycles:
        if hasattr(cycles, "samples"):
            cycles.samples = value
            applied["cycles_samples"] = value
        if hasattr(cycles, "preview_samples"):
            cycles.preview_samples = min(value, max(1, getattr(cycles, "preview_samples", value)))
            applied["cycles_preview_samples"] = int(cycles.preview_samples)
    eevee = getattr(scene, "eevee", None)
    if eevee:
        if hasattr(eevee, "taa_render_samples"):
            eevee.taa_render_samples = value
            applied["eevee_taa_render_samples"] = value
        if hasattr(eevee, "taa_samples"):
            eevee.taa_samples = min(value, max(1, getattr(eevee, "taa_samples", value)))
            applied["eevee_taa_samples"] = int(eevee.taa_samples)
    return applied

def _set_render_denoise(scene, denoise):
    applied = {}
    cycles = getattr(scene, "cycles", None)
    if cycles and hasattr(cycles, "use_denoising"):
        cycles.use_denoising = bool(denoise)
        applied["cycles_use_denoising"] = bool(cycles.use_denoising)
    return applied

def _set_color_management(scene, *, view_transform="", look="", exposure=None, gamma=None):
    view_settings = getattr(scene, "view_settings", None)
    applied = {}
    warnings = []
    if view_settings is None:
        return applied, ["Scene has no color management view settings"]
    for attr, value in (("view_transform", view_transform), ("look", look)):
        if not str(value or "").strip():
            continue
        try:
            setattr(view_settings, attr, str(value))
            applied[attr] = getattr(view_settings, attr)
        except Exception as exc:
            warnings.append(f"Could not set color management {attr}={value!r}: {type(exc).__name__}: {exc}")
    for attr, value in (("exposure", exposure), ("gamma", gamma)):
        if value is None:
            continue
        try:
            setattr(view_settings, attr, float(value))
            applied[attr] = float(getattr(view_settings, attr))
        except Exception as exc:
            warnings.append(f"Could not set color management {attr}={value!r}: {type(exc).__name__}: {exc}")
    return applied, warnings

def set_render_settings(
    context,
    *,
    engine="",
    resolution=None,
    fps=None,
    frame_start=None,
    frame_end=None,
    film_transparent=None,
    quality_preset="",
    samples=None,
    denoise=None,
    view_transform="",
    look="",
    exposure=None,
    gamma=None,
    label="Set render settings",
):
    scene = context.scene
    if engine:
        valid_engines = _valid_render_engines(scene)
        if valid_engines and str(engine) not in valid_engines:
            return {
                "ok": False,
                "message": (
                    f"Unsupported render engine: {engine}. "
                    f"Available engines: {', '.join(sorted(valid_engines))}"
                ),
            }
    preset_key = _normalize_render_quality_preset(quality_preset)
    preset = RENDER_QUALITY_PRESETS.get(preset_key, {})
    transaction = live_preview.begin(label)
    _record_scene_render(scene)
    if engine:
        scene.render.engine = str(engine)
    applied = {"engine": scene.render.engine}
    warnings = []
    if preset and resolution is None:
        resolution = preset["resolution"]
    if preset and samples is None:
        samples = preset["samples"]
    if preset and denoise is None:
        denoise = preset["denoise"]
    if resolution is not None:
        scene.render.resolution_x = max(16, min(16384, int(resolution[0])))
        scene.render.resolution_y = max(16, min(16384, int(resolution[1])))
        applied["resolution"] = [scene.render.resolution_x, scene.render.resolution_y]
    if fps is not None:
        scene.render.fps = max(1, min(240, int(fps)))
        applied["fps"] = scene.render.fps
    if frame_start is not None:
        scene.frame_start = int(frame_start)
    if frame_end is not None:
        scene.frame_end = int(frame_end)
    if scene.frame_start > scene.frame_end:
        scene.frame_start, scene.frame_end = scene.frame_end, scene.frame_start
    if frame_start is not None or frame_end is not None:
        applied["frame_range"] = [scene.frame_start, scene.frame_end]
    if film_transparent is not None:
        scene.render.film_transparent = bool(film_transparent)
        applied["film_transparent"] = scene.render.film_transparent
    if samples is not None:
        applied.update(_set_render_sample_count(scene, samples))
    if denoise is not None:
        denoise_applied = _set_render_denoise(scene, denoise)
        if denoise_applied:
            applied.update(denoise_applied)
        else:
            warnings.append("Denoise was requested but no supported denoise setting is available for this render engine")
    color_applied, color_warnings = _set_color_management(
        scene,
        view_transform=view_transform,
        look=look,
        exposure=exposure,
        gamma=gamma,
    )
    applied.update(color_applied)
    warnings.extend(color_warnings)
    transaction["applied_steps"].append(
        {
            "type": "set_render_settings",
            "label": label,
            "scene": scene.name,
            "quality_preset": preset_key,
            "applied": applied,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": "Updated render settings",
        "quality_preset": preset_key,
        "applied": applied,
        "warnings": warnings,
        "transaction_id": transaction["id"],
    }

def set_render_engine(
    context,
    *,
    engine="",
    quality_preset="",
    samples=None,
    denoise=None,
    view_transform="",
    look="",
    exposure=None,
    gamma=None,
    label="Set render engine",
):
    return set_render_settings(
        context,
        engine=engine,
        quality_preset=quality_preset,
        samples=samples,
        denoise=denoise,
        view_transform=view_transform,
        look=look,
        exposure=exposure,
        gamma=gamma,
        label=label,
    )

def _normalize_render_pass_name(name):
    key = str(name or "").strip().lower().replace("-", "_").replace(" ", "_")
    return RENDER_PASS_ALIASES.get(key, "")

def _normalize_aov_spec(item):
    if not isinstance(item, dict):
        return None, "AOV entries must be objects with name and type"
    name = str(item.get("name") or "").strip()
    if not name:
        return None, "AOV name is required"
    if len(name) > 64:
        return None, f"AOV name is too long: {name[:32]}..."
    aov_type = str(item.get("type") or "COLOR").strip().upper()
    if aov_type not in AOV_TYPES:
        return None, f"Unsupported AOV type for {name}: {aov_type}. Use COLOR or VALUE."
    return {"name": name, "type": aov_type}, ""

def configure_render_outputs(
    context,
    *,
    view_layer_name="",
    enabled_passes=None,
    disabled_passes=None,
    aovs=None,
    clear_existing_aovs=False,
    pass_alpha_threshold=None,
    pass_cryptomatte_depth=None,
    label="Configure render outputs",
):
    scene = context.scene
    view_layer = scene.view_layers.get(str(view_layer_name or "")) if view_layer_name else getattr(context, "view_layer", None)
    if view_layer is None:
        return {"ok": False, "message": f"View layer not found: {view_layer_name}" if view_layer_name else "No active view layer"}

    enabled_passes = enabled_passes or []
    disabled_passes = disabled_passes or []
    aovs = aovs or []
    requested_changes = bool(enabled_passes or disabled_passes or aovs or clear_existing_aovs)
    if pass_alpha_threshold is not None or pass_cryptomatte_depth is not None:
        requested_changes = True
    if not requested_changes:
        return {"ok": False, "message": "Provide at least one render pass, AOV, or pass setting to change"}

    normalized_aovs = []
    for item in aovs:
        spec, error = _normalize_aov_spec(item)
        if error:
            return {"ok": False, "message": error}
        normalized_aovs.append(spec)
    aov_collection = getattr(view_layer, "aovs", None)
    if normalized_aovs or clear_existing_aovs:
        if aov_collection is None or not hasattr(aov_collection, "add"):
            return {"ok": False, "message": "Shader AOVs are not available on this Blender version"}

    pass_requests = [(name, True) for name in enabled_passes] + [(name, False) for name in disabled_passes]
    valid_pass_requests = []
    unsupported_passes = []
    for pass_name, state in pass_requests:
        attr = _normalize_render_pass_name(pass_name)
        if not attr or not hasattr(view_layer, attr):
            unsupported_passes.append(str(pass_name))
            continue
        valid_pass_requests.append((pass_name, attr, state))
    has_non_pass_change = bool(normalized_aovs or clear_existing_aovs or pass_alpha_threshold is not None or pass_cryptomatte_depth is not None)
    if pass_requests and not valid_pass_requests and not has_non_pass_change:
        return {"ok": False, "message": f"Unsupported render pass name(s): {', '.join(unsupported_passes)}"}

    warnings = []
    applied_passes = {}
    transaction = live_preview.begin(label)
    _record_view_layer_render_outputs(scene, view_layer)

    for pass_name, attr, state in valid_pass_requests:
        try:
            setattr(view_layer, attr, bool(state))
            applied_passes[attr] = bool(getattr(view_layer, attr))
        except Exception as exc:
            warnings.append(f"Could not set render pass {pass_name}: {type(exc).__name__}: {exc}")

    applied_settings = {}
    if pass_alpha_threshold is not None:
        if hasattr(view_layer, "pass_alpha_threshold"):
            value = _clamped_float(pass_alpha_threshold, 0.5, 0.0, 1.0)
            view_layer.pass_alpha_threshold = value
            applied_settings["pass_alpha_threshold"] = float(view_layer.pass_alpha_threshold)
        else:
            warnings.append("Alpha threshold pass setting is not available on this Blender version")
    if pass_cryptomatte_depth is not None:
        if hasattr(view_layer, "pass_cryptomatte_depth"):
            value = max(2, min(16, int(pass_cryptomatte_depth)))
            view_layer.pass_cryptomatte_depth = value
            applied_settings["pass_cryptomatte_depth"] = int(view_layer.pass_cryptomatte_depth)
        else:
            warnings.append("Cryptomatte depth pass setting is not available on this Blender version")

    if unsupported_passes:
        warnings.append(f"Unsupported render pass name(s): {', '.join(unsupported_passes)}")

    applied_aovs = []
    if normalized_aovs or clear_existing_aovs:
        if clear_existing_aovs:
            for existing in list(aov_collection):
                aov_collection.remove(existing)
        for spec in normalized_aovs:
            aov = aov_collection.get(spec["name"]) if hasattr(aov_collection, "get") else None
            if aov is None:
                aov = aov_collection.add()
                aov.name = spec["name"]
            aov.type = spec["type"]
            applied_aovs.append({"name": aov.name, "type": aov.type})

    state = _view_layer_render_state(view_layer)
    transaction["applied_steps"].append(
        {
            "type": "configure_render_outputs",
            "label": label,
            "scene": scene.name,
            "view_layer": view_layer.name,
            "enabled_passes": [str(name) for name in enabled_passes],
            "disabled_passes": [str(name) for name in disabled_passes],
            "applied_passes": applied_passes,
            "applied_settings": applied_settings,
            "aovs": applied_aovs,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": "Configured render outputs",
        "view_layer": view_layer.name,
        "applied_passes": applied_passes,
        "applied_settings": applied_settings,
        "aovs": state["aovs"],
        "enabled_passes": sorted(name for name, enabled in state["pass_flags"].items() if enabled),
        "warnings": warnings,
        "transaction_id": transaction["id"],
    }

def set_camera_settings(
    context,
    *,
    camera_name="",
    lens=None,
    sensor_width=None,
    dof_enabled=None,
    focus_object_name="",
    aperture_fstop=None,
    label="Set camera settings",
):
    camera = bpy.data.objects.get(camera_name) if camera_name else context.scene.camera
    if camera is None or camera.type != "CAMERA":
        return {"ok": False, "message": "A camera object is required"}
    transaction = live_preview.begin(label)
    _record_camera_settings(camera)
    data = camera.data
    if lens is not None:
        data.lens = max(1.0, min(1000.0, float(lens)))
    if sensor_width is not None:
        data.sensor_width = max(1.0, min(200.0, float(sensor_width)))
    if dof_enabled is not None:
        data.dof.use_dof = bool(dof_enabled)
    if focus_object_name:
        focus = bpy.data.objects.get(focus_object_name)
        if focus is None:
            return {"ok": False, "message": f"Focus object not found: {focus_object_name}"}
        data.dof.focus_object = focus
    if aperture_fstop is not None:
        data.dof.aperture_fstop = max(0.1, min(128.0, float(aperture_fstop)))
    transaction["applied_steps"].append({"type": "set_camera_settings", "label": label, "camera": camera.name})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Updated camera settings for {camera.name}", "camera": camera.name, "transaction_id": transaction["id"]}

def set_world_background(context, *, color, label="Set world background"):
    _record_scene_world(context.scene)
    world = context.scene.world or bpy.data.worlds.new("Agent Bridge World")
    if context.scene.world is None:
        context.scene.world = world
        live_preview._record_created_id("world", world.name)
    transaction = live_preview.begin(label)
    _record_world_background(world)
    values = list(color)
    world.color = (
        float(values[0]),
        float(values[1]),
        float(values[2]),
    )
    transaction["applied_steps"].append({"type": "set_world_background", "label": label, "world": world.name})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Updated world background {world.name}", "transaction_id": transaction["id"]}

def create_studio_product_stage(
    context,
    *,
    target_name="",
    stage_name="Agent Bridge Product Stage",
    floor=True,
    backdrop=True,
    lighting=True,
    camera=True,
    label="Create studio product stage",
):
    target = bpy.data.objects.get(target_name) if target_name else context.active_object
    if target is None or not hasattr(target, "bound_box"):
        return {"ok": False, "message": "A target object with bounds is required for a studio stage"}
    existing_lights = _scene_light_names(context) if lighting else []
    transaction = live_preview.begin(label, context)
    bounds = _bounds_world(target)
    min_x, min_y, min_z = bounds["min"]
    max_x, max_y, max_z = bounds["max"]
    center_x, center_y, center_z = bounds["center"]
    sx, sy, sz = bounds["size"]
    max_dim = max(1.0, sx, sy, sz)
    stage_name = str(stage_name or "Agent Bridge Product Stage")
    floor_material = _material_for_color(f"{stage_name} Warm Gray", (0.58, 0.57, 0.54, 1.0))
    backdrop_material = _material_for_color(f"{stage_name} Soft Backdrop", (0.72, 0.71, 0.68, 1.0))

    created = []
    floor_thickness = max(0.02, max_dim * 0.025)
    if floor:
        created.append(
            _create_cube_object(
                context,
                f"{stage_name} Floor",
                (center_x, center_y, min_z - floor_thickness / 2.0),
                (max_dim * 2.8, max_dim * 2.2, floor_thickness),
                floor_material,
            ).name
        )
    if backdrop:
        created.append(
            _create_cube_object(
                context,
                f"{stage_name} Backdrop",
                (center_x, max_y + max_dim * 0.72, min_z + max_dim * 0.7),
                (max_dim * 2.8, floor_thickness, max_dim * 1.45),
                backdrop_material,
            ).name
        )

    target_empty = _create_empty_target(
        context,
        f"{stage_name} Target",
        (center_x, center_y, center_z),
        display_size=max_dim * 0.12,
    )
    created.append(target_empty.name)

    lights = []
    if lighting:
        key = _create_area_light(
            context,
            f"{stage_name} Key Light",
            (min_x - max_dim * 1.2, min_y - max_dim * 1.35, max_z + max_dim * 1.3),
            energy=650.0,
            size=max_dim * 1.15,
            color=(1.0, 0.93, 0.84),
            target=target_empty,
        )
        fill = _create_area_light(
            context,
            f"{stage_name} Fill Light",
            (max_x + max_dim * 1.3, min_y - max_dim * 0.9, max_z + max_dim * 0.75),
            energy=180.0,
            size=max_dim * 1.7,
            color=(0.78, 0.86, 1.0),
            target=target_empty,
        )
        rim = _create_area_light(
            context,
            f"{stage_name} Rim Light",
            (center_x, max_y + max_dim * 1.25, max_z + max_dim * 1.1),
            energy=360.0,
            size=max_dim * 0.75,
            color=(1.0, 1.0, 0.94),
            target=target_empty,
        )
        lights = [key.name, fill.name, rim.name]
        created.extend(lights)

    camera_name = ""
    if camera:
        live_preview._record_scene_camera(context.scene)
        data = bpy.data.cameras.new(name=f"{stage_name} Camera")
        data.lens = 70.0
        data.dof.use_dof = True
        data.dof.focus_object = target_empty
        data.dof.aperture_fstop = 5.6
        camera_obj = bpy.data.objects.new(name=f"{stage_name} Camera", object_data=data)
        camera_obj.location = (center_x - max_dim * 1.8, min_y - max_dim * 2.2, center_z + max_dim * 1.0)
        context.scene.collection.objects.link(camera_obj)
        live_preview._record_created_id("object", camera_obj.name)
        live_preview._record_created_id("camera", data.name)
        _track_to_target(camera_obj, target_empty)
        context.scene.camera = camera_obj
        camera_name = camera_obj.name
        created.append(camera_obj.name)

    transaction["applied_steps"].append(
        {
            "type": "create_studio_product_stage",
            "label": label,
            "target": target.name,
            "created_objects": created,
            "lights": lights,
            "camera": camera_name,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    lighting_warning = _existing_light_warning(existing_lights, len(lights), source="the studio product stage")
    return {
        "ok": True,
        "message": f"Created product stage around {target.name}",
        "target": target.name,
        "created_objects": created,
        "lights": lights,
        "camera": camera_name,
        "lighting_warning": lighting_warning or "",
        "warnings": [lighting_warning] if lighting_warning else [],
        "transaction_id": transaction["id"],
    }

def apply_lighting_preset(
    context,
    *,
    target_name="",
    preset="product_softbox",
    rig_name="Agent Bridge Lighting",
    label="Apply lighting preset",
):
    target = bpy.data.objects.get(target_name) if target_name else context.active_object
    if target is None or not hasattr(target, "bound_box"):
        return {"ok": False, "message": "A target object with bounds is required for a lighting preset"}
    preset_key = str(preset or "product_softbox").lower()
    lights_spec = LIGHTING_PRESETS.get(preset_key) or LIGHTING_PRESETS["product_softbox"]
    existing_lights = _scene_light_names(context)
    transaction = live_preview.begin(label, context)
    bounds = _bounds_world(target)
    center_x, center_y, center_z = bounds["center"]
    sx, sy, sz = bounds["size"]
    max_dim = max(1.0, sx, sy, sz)
    rig_name = str(rig_name or "Agent Bridge Lighting")
    target_empty = _create_empty_target(
        context,
        f"{rig_name} Target",
        (center_x, center_y, center_z),
        display_size=max_dim * 0.12,
    )
    created = [target_empty.name]
    lights = []
    for suffix, factors, energy, size, color in lights_spec:
        location = (
            center_x + factors[0] * max_dim,
            center_y + factors[1] * max_dim,
            center_z + factors[2] * max_dim,
        )
        light = _create_area_light(
            context,
            f"{rig_name} {suffix}",
            location,
            energy=energy,
            size=max_dim * size,
            color=color,
            target=target_empty,
        )
        lights.append(light.name)
        created.append(light.name)
    transaction["applied_steps"].append(
        {
            "type": "apply_lighting_preset",
            "label": label,
            "target": target.name,
            "preset": preset_key if preset_key in LIGHTING_PRESETS else "product_softbox",
            "created_objects": created,
            "lights": lights,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    lighting_warning = _existing_light_warning(existing_lights, len(lights), source="the lighting preset")
    return {
        "ok": True,
        "message": f"Applied {preset_key if preset_key in LIGHTING_PRESETS else 'product_softbox'} lighting around {target.name}",
        "target": target.name,
        "preset": preset_key if preset_key in LIGHTING_PRESETS else "product_softbox",
        "created_objects": created,
        "lights": lights,
        "lighting_warning": lighting_warning or "",
        "warnings": [lighting_warning] if lighting_warning else [],
        "transaction_id": transaction["id"],
    }

def create_product_turntable_setup(
    context,
    *,
    target_name="",
    frame_start=1,
    frame_end=120,
    revolutions=1.0,
    radius=0.0,
    height=0.0,
    setup_name="Agent Bridge Product Turntable",
    create_stage=True,
    label="Create product turntable setup",
):
    target = bpy.data.objects.get(target_name) if target_name else context.active_object
    if target is None or not hasattr(target, "bound_box"):
        return {"ok": False, "message": "A target object with bounds is required for a turntable setup"}
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Product turntable setup")
    if error:
        return error
    transaction = live_preview.begin(label, context)
    bounds = _bounds_world(target)
    sx, sy, sz = bounds["size"]
    max_dim = max(1.0, sx, sy, sz)
    stage_result = {}
    if create_stage:
        stage_result = create_studio_product_stage(
            context,
            target_name=target.name,
            stage_name=f"{setup_name} Stage",
            floor=True,
            backdrop=True,
            lighting=True,
            camera=False,
            label=label,
        )
    animation_result = create_turntable_animation(
        context,
        object_name=target.name,
        frame_start=frame_start,
        frame_end=frame_end,
        axis="Z",
        revolutions=revolutions,
        add_cycles=True,
        label=label,
    )
    orbit_result = live_preview.create_camera_orbit(
        context,
        target_name=target.name,
        frame_start=frame_start,
        frame_end=frame_end,
        radius=float(radius) if float(radius or 0.0) > 0.0 else max_dim * 2.6,
        height=float(height) if float(height or 0.0) > 0.0 else max_dim * 0.9,
        name=f"{setup_name} Camera",
        lens=70.0,
        label=label,
    )
    transaction["applied_steps"].append(
        {
            "type": "create_product_turntable_setup",
            "label": label,
            "target": target.name,
            "frame_start": frame_start,
            "frame_end": frame_end,
            "stage_created": bool(stage_result.get("ok")),
            "camera": orbit_result.get("camera", ""),
            "action": animation_result.get("action", ""),
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": bool(animation_result.get("ok") and orbit_result.get("ok") and (not create_stage or stage_result.get("ok"))),
        "message": f"Created product turntable setup for {target.name}",
        "target": target.name,
        "stage": stage_result,
        "animation": animation_result,
        "camera_orbit": orbit_result,
        "transaction_id": transaction["id"],
    }

def _lookdev_render_engine(scene, render_engine):
    requested = str(render_engine or "").strip()
    valid = _valid_render_engines(scene)
    if not requested or requested.lower() == "auto":
        return "CYCLES" if "CYCLES" in valid else scene.render.engine
    requested_upper = requested.upper()
    aliases = {
        "EEVEE": "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in valid else "BLENDER_EEVEE",
        "WORKBENCH": "BLENDER_WORKBENCH",
    }
    candidate = aliases.get(requested_upper, requested_upper)
    return candidate

def _validate_inspection_artifacts(metadata):
    images = list((metadata or {}).get("images") or [])
    available = []
    missing = []
    for image in images:
        path = str(image.get("path") or "")
        exists = bool(path and os.path.isfile(path))
        size_bytes = os.path.getsize(path) if exists else int(image.get("size_bytes") or 0)
        item = {
            "image_id": image.get("image_id", ""),
            "object": image.get("object", ""),
            "view": image.get("view", ""),
            "path": path,
            "resource_uri": image.get("resource_uri", ""),
            "size_bytes": int(size_bytes),
            "width": int(image.get("width") or 0),
            "height": int(image.get("height") or 0),
        }
        if bool(image.get("available")) and exists and size_bytes > 0:
            available.append(item)
        else:
            missing.append(item)
    return {
        "ok": bool(images) and len(available) == len(images),
        "requested_image_count": len(images),
        "available_image_count": len(available),
        "missing_image_count": len(missing),
        "metadata_uri": (metadata or {}).get("metadata_uri", ""),
        "latest_metadata_uri": (metadata or {}).get("latest_metadata_uri", ""),
        "images": available,
        "missing_images": missing,
    }

def create_lookdev_turntable_review(
    context,
    *,
    target_name="",
    frame_start=1,
    frame_end=96,
    revolutions=1.0,
    setup_name="Agent Bridge Lookdev Turntable",
    create_stage=True,
    create_turntable=True,
    render_engine="auto",
    quality_preset="preview",
    samples=None,
    denoise=True,
    view_transform="",
    look="",
    exposure=None,
    gamma=None,
    capture_inspection=True,
    views=None,
    resolution_x=320,
    resolution_y=240,
    distance_factor=2.6,
    capture_dir=None,
    label="Create look-dev turntable review",
):
    """Create a bounded look-dev/turntable setup and render review evidence."""

    target = bpy.data.objects.get(target_name) if target_name else context.active_object
    if target is None or not hasattr(target, "bound_box"):
        return {"ok": False, "message": "A target object with bounds is required for look-dev turntable review"}
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Look-dev turntable review")
    if error:
        return error

    render_result = set_render_engine(
        context,
        engine=_lookdev_render_engine(context.scene, render_engine),
        quality_preset=quality_preset,
        samples=samples,
        denoise=denoise,
        view_transform=view_transform,
        look=look,
        exposure=exposure,
        gamma=gamma,
        label=label,
    )
    if not render_result.get("ok"):
        return render_result

    setup_result = {}
    with _preserve_selection(context):
        if create_turntable:
            setup_result = create_product_turntable_setup(
                context,
                target_name=target.name,
                frame_start=frame_start,
                frame_end=frame_end,
                revolutions=revolutions,
                setup_name=setup_name,
                create_stage=create_stage,
                label=label,
            )
        elif create_stage:
            setup_result = create_studio_product_stage(
                context,
                target_name=target.name,
                stage_name=f"{setup_name} Stage",
                floor=True,
                backdrop=False,
                lighting=True,
                camera=True,
                label=label,
            )

    inspection_result = {}
    validation = {"ok": True, "requested_image_count": 0, "available_image_count": 0, "missing_image_count": 0, "images": [], "missing_images": []}
    if capture_inspection:
        requested_views = [str(view) for view in (views or ("front", "side", "front_below")) if str(view).strip()]
        inspection_result = inspection_render.capture_object_inspection_renders(
            context,
            object_names=[target.name],
            views=requested_views,
            frame=frame_start,
            resolution_x=resolution_x,
            resolution_y=resolution_y,
            lens=70.0,
            distance_factor=distance_factor,
            camera_name=f"{setup_name} Inspection Camera",
            note=f"Look-dev turntable review for {target.name}",
            capture_dir=capture_dir,
        )
        validation = _validate_inspection_artifacts(inspection_result.get("inspection_render") or {})

    transaction = live_preview.begin(label, context)
    transaction["applied_steps"].append(
        {
            "type": "create_lookdev_turntable_review",
            "label": label,
            "target": target.name,
            "frame_start": frame_start,
            "frame_end": frame_end,
            "render_engine": render_result.get("applied", {}).get("engine", ""),
            "quality_preset": render_result.get("quality_preset", ""),
            "created_turntable": bool(create_turntable and setup_result.get("ok")),
            "capture_inspection": bool(capture_inspection),
            "artifact_validation": validation,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    setup_ok = (not (create_turntable or create_stage)) or bool(setup_result.get("ok"))
    evidence_ok = (not capture_inspection) or bool(validation.get("ok"))
    return {
        "ok": bool(render_result.get("ok") and setup_ok and evidence_ok),
        "message": f"Created look-dev turntable review for {target.name}",
        "target": target.name,
        "render_settings": render_result,
        "setup": setup_result,
        "inspection_render": inspection_result.get("inspection_render", {}),
        "artifact_validation": validation,
        "transaction_id": transaction["id"],
    }





def register():

    pass





def unregister():

    pass

