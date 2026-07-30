"""Calibrated render-to-reference comparison and redline evidence."""

from __future__ import annotations

import math
import os
import shutil

import bpy
from mathutils import Vector

from . import inspection_render, reference_metrics, reference_scene


REFERENCE_GUIDE_METADATA_PROP = reference_scene.REFERENCE_GUIDE_METADATA_PROP
RENDERABLE_TYPES = {"MESH", "CURVE", "FONT", "SURFACE", "META", "VOLUME"}
_json_prop = reference_scene.json_prop
_guide_collection = reference_scene.guide_collection
_guide_objects = reference_scene.guide_objects
_comparison_camera = reference_scene.comparison_camera
_curve_world_points = reference_scene.curve_world_points
_project_point = reference_scene.project_point


def _outline_points(scene, collection, camera, outline_name):
    curves = _guide_objects(collection, "curve")
    requested = str(outline_name or "").strip()
    if requested:
        curves = [
            obj
            for obj in curves
            if str(obj.get("reference_guide_name") or obj.name) == requested
        ]
        if not curves:
            return [], "", f"Reference outline not found: {requested}"
    else:
        cyclic = [
            obj
            for obj in curves
            if any(bool(spline.use_cyclic_u) for spline in obj.data.splines)
        ]
        curves = cyclic or curves
    if not curves:
        return [], "", "Reference guides contain no outline curve"
    outline = curves[0]
    points = [
        _project_point(scene, camera, point)
        for point in _curve_world_points(outline)[:512]
    ]
    if len(points) < 3:
        return [], "", "Reference outline has fewer than three projected points"
    return (
        points,
        str(outline.get("reference_guide_name") or outline.name),
        "",
    )


_image_path = reference_scene.image_path
_camera_margin = reference_scene.camera_margin


def _resolution(scene, collection, max_axis):
    metadata = _json_prop(collection, REFERENCE_GUIDE_METADATA_PROP)
    pipeline = metadata.get("annotation_pipeline")
    calibration = (
        pipeline.get("calibration")
        if isinstance(pipeline, dict)
        else {}
    )
    camera_meta = (
        calibration.get("camera")
        if isinstance(calibration, dict)
        else {}
    )
    source = (
        camera_meta.get("render_resolution")
        if isinstance(camera_meta, dict)
        else None
    )
    if not isinstance(source, (list, tuple)) or len(source) < 2:
        source = [
            int(scene.render.resolution_x),
            int(scene.render.resolution_y),
        ]
    width = max(1, int(source[0]))
    height = max(1, int(source[1]))
    max_axis = max(64, min(1024, int(max_axis or 512)))
    scale = min(1.0, max_axis / max(width, height))
    return max(64, int(round(width * scale))), max(
        64, int(round(height * scale))
    )


def _resolve_targets(context, object_names, selected_only):
    names = [
        str(name).strip()
        for name in object_names or []
        if str(name).strip()
    ]
    missing = []
    if names:
        objects = []
        for name in names[:64]:
            obj = bpy.data.objects.get(name)
            if obj is None:
                missing.append(name)
            elif obj.type in RENDERABLE_TYPES:
                objects.append(obj)
    elif selected_only:
        objects = [
            obj
            for obj in context.selected_objects
            if obj.type in RENDERABLE_TYPES
        ][:64]
    elif context.active_object and context.active_object.type in RENDERABLE_TYPES:
        objects = [context.active_object]
    else:
        objects = []
    return objects, missing


def _target_tree(objects):
    result = set(objects)
    for obj in list(objects):
        result.update(obj.children_recursive)
    return result


def _mask_material():
    material = bpy.data.materials.new("Agent Bridge Reference Mask")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    shader.inputs["Roughness"].default_value = 1.0
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def _read_alpha_mask(path, width, height, threshold):
    image = None
    try:
        image = bpy.data.images.load(path, check_existing=False)
        if int(image.size[0]) != width or int(image.size[1]) != height:
            raise ValueError(
                f"Rendered mask is {image.size[0]}x{image.size[1]}, expected {width}x{height}"
            )
        pixels = list(image.pixels[:])
        mask = bytearray(width * height)
        for top_y in range(height):
            source_y = height - 1 - top_y
            source_row = source_y * width * 4
            target_row = top_y * width
            for x in range(width):
                mask[target_row + x] = (
                    1 if pixels[source_row + x * 4 + 3] >= threshold else 0
                )
        return mask
    finally:
        if image is not None:
            bpy.data.images.remove(image)


def _render_model_mask(
    context,
    *,
    camera,
    targets,
    path,
    width,
    height,
    threshold,
):
    scene = context.scene
    view_layer = context.view_layer
    target_objects = _target_tree(targets)
    changed_visibility = []
    original = {
        "camera": scene.camera,
        "resolution_x": int(scene.render.resolution_x),
        "resolution_y": int(scene.render.resolution_y),
        "resolution_percentage": int(scene.render.resolution_percentage),
        "filepath": str(scene.render.filepath),
        "file_format": str(scene.render.image_settings.file_format),
        "color_mode": str(scene.render.image_settings.color_mode),
        "film_transparent": bool(scene.render.film_transparent),
        "material_override": view_layer.material_override,
    }
    material = None
    try:
        for obj in bpy.data.objects:
            desired = obj not in target_objects
            previous = bool(obj.hide_render)
            if previous == desired:
                continue
            obj.hide_render = desired
            changed_visibility.append((obj, previous))
        material = _mask_material()
        view_layer.material_override = material
        scene.camera = camera
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        scene.render.resolution_percentage = 100
        scene.render.filepath = path
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"
        scene.render.film_transparent = True
        bpy.ops.render.render(write_still=True)
        if not os.path.isfile(path):
            raise RuntimeError("Blender did not write the model-mask render")
        return _read_alpha_mask(path, width, height, threshold)
    finally:
        view_layer.material_override = original["material_override"]
        scene.camera = original["camera"]
        scene.render.resolution_x = original["resolution_x"]
        scene.render.resolution_y = original["resolution_y"]
        scene.render.resolution_percentage = original["resolution_percentage"]
        scene.render.filepath = original["filepath"]
        scene.render.image_settings.file_format = original["file_format"]
        scene.render.image_settings.color_mode = original["color_mode"]
        scene.render.film_transparent = original["film_transparent"]
        visibility_restore_errors = []
        for obj, hidden in reversed(changed_visibility):
            try:
                if bpy.data.objects.get(obj.name) is obj:
                    obj.hide_render = hidden
            except Exception as exc:
                visibility_restore_errors.append(
                    f"{obj.name}: {type(exc).__name__}: {exc}"
                )
        if material is not None and bpy.data.materials.get(material.name):
            bpy.data.materials.remove(material)
        if visibility_restore_errors:
            raise RuntimeError(
                "Could not restore render visibility for "
                + "; ".join(visibility_restore_errors[:8])
            )


def _alpha_reference_mask(
    image_path,
    *,
    width,
    height,
    margin,
    threshold,
):
    image = None
    try:
        image = bpy.data.images.load(image_path, check_existing=False)
        source_width = int(image.size[0])
        source_height = int(image.size[1])
        source_max_axis = max(source_width, source_height)
        working_max_axis = max(width, height)
        if source_max_axis > working_max_axis:
            scale = working_max_axis / source_max_axis
            source_width = max(1, int(round(source_width * scale)))
            source_height = max(1, int(round(source_height * scale)))
            image.scale(source_width, source_height)
        pixels = list(image.pixels[:])
        source_foreground = sum(
            1
            for index in range(3, len(pixels), 4)
            if pixels[index] >= threshold
        )
        source_coverage = source_foreground / max(
            1, source_width * source_height
        )
        if source_coverage <= 0.001 or source_coverage >= 0.995:
            raise ValueError(
                "Reference alpha is empty or fully opaque; supply an annotated outline"
            )
        scale = 1.0 + margin * 2.0
        result = bytearray(width * height)
        for top_y in range(height):
            frame_v = (top_y + 0.5) / height
            source_v = 0.5 + (frame_v - 0.5) * scale
            if source_v < 0.0 or source_v >= 1.0:
                continue
            source_top_y = min(
                source_height - 1, int(source_v * source_height)
            )
            source_y = source_height - 1 - source_top_y
            for x in range(width):
                frame_u = (x + 0.5) / width
                source_u = 0.5 + (frame_u - 0.5) * scale
                if source_u < 0.0 or source_u >= 1.0:
                    continue
                source_x = min(
                    source_width - 1, int(source_u * source_width)
                )
                alpha_index = (source_y * source_width + source_x) * 4 + 3
                if pixels[alpha_index] >= threshold:
                    result[top_y * width + x] = 1
        return result
    finally:
        if image is not None:
            bpy.data.images.remove(image)


def _save_pixels(path, width, height, top_left_pixels):
    image = bpy.data.images.new(
        "Agent Bridge Reference Evidence",
        width=width,
        height=height,
        alpha=True,
    )
    try:
        blender_pixels = [0.0] * (width * height * 4)
        for top_y in range(height):
            source_row = top_y * width * 4
            target_row = (height - 1 - top_y) * width * 4
            blender_pixels[target_row : target_row + width * 4] = (
                top_left_pixels[source_row : source_row + width * 4]
            )
        image.pixels = blender_pixels
        image.filepath_raw = path
        image.file_format = "PNG"
        image.save()
    finally:
        bpy.data.images.remove(image)


def _save_reference_mask(path, mask, width, height):
    pixels = []
    for value in mask:
        pixels.extend((0.1, 0.65, 1.0, 1.0 if value else 0.0))
    _save_pixels(path, width, height, pixels)


def _save_redline(path, reference, model, width, height):
    pixels = []
    for reference_value, model_value in zip(reference, model):
        if reference_value and model_value:
            pixels.extend((0.12, 0.82, 0.35, 0.9))
        elif reference_value:
            pixels.extend((0.05, 0.45, 1.0, 1.0))
        elif model_value:
            pixels.extend((1.0, 0.08, 0.08, 1.0))
        else:
            pixels.extend((0.015, 0.02, 0.03, 1.0))
    _save_pixels(path, width, height, pixels)


def _landmark_points(scene, collection, camera, landmark_targets):
    reference = {}
    for obj in _guide_objects(collection, "landmark"):
        name = str(
            obj.get("reference_guide_name")
            or obj.get("reference_landmark_name")
            or obj.name
        )
        reference[name] = _project_point(
            scene, camera, obj.matrix_world.translation
        )

    targets = {}
    missing = []
    for item in list(landmark_targets or [])[:128]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        object_name = str(item.get("object_name") or "").strip()
        location = item.get("location")
        if not name:
            continue
        if object_name:
            obj = bpy.data.objects.get(object_name)
            if obj is None:
                missing.append(object_name)
                continue
            world_point = obj.matrix_world.translation
        elif isinstance(location, (list, tuple)) and len(location) >= 3:
            world_point = Vector(
                (float(location[0]), float(location[1]), float(location[2]))
            )
        else:
            continue
        targets[name] = _project_point(scene, camera, world_point)
    return reference, targets, missing


def _cleanup_artifact(artifact):
    path = str((artifact or {}).get("render_dir") or "")
    if path and os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def compare_model_to_reference(
    context,
    *,
    collection_name="",
    camera_name="",
    object_names=None,
    selected_only=True,
    outline_name="",
    reference_mask_source="auto",
    landmark_targets=None,
    max_axis=512,
    mask_threshold=0.5,
    capture_dir=None,
):
    """Render model targets and compare them with calibrated reference evidence."""

    collection, error = _guide_collection(collection_name)
    if error:
        return {"ok": False, "message": error}
    camera, error = _comparison_camera(collection, camera_name)
    if error:
        return {"ok": False, "message": error}
    reference_identity = reference_scene.reference_identity(collection, camera)
    targets, missing_objects = _resolve_targets(
        context, object_names, selected_only
    )
    if not targets:
        return {
            "ok": False,
            "message": "No renderable model targets were resolved",
            "missing_object_names": missing_objects,
        }

    width, height = _resolution(context.scene, collection, max_axis)
    threshold = max(0.01, min(0.99, float(mask_threshold or 0.5)))
    source = str(reference_mask_source or "auto").strip().lower()
    artifact = inspection_render.begin_inspection_artifact(
        context,
        prefix="reference-comparison",
        capture_dir=capture_dir,
    )
    model_path = os.path.join(artifact["render_dir"], "model-mask.png")
    reference_path = os.path.join(
        artifact["render_dir"], "reference-mask.png"
    )
    redline_path = os.path.join(
        artifact["render_dir"], "redline-overlay.png"
    )
    projection_state = {
        "resolution_x": int(context.scene.render.resolution_x),
        "resolution_y": int(context.scene.render.resolution_y),
        "resolution_percentage": int(
            context.scene.render.resolution_percentage
        ),
        "pixel_aspect_x": float(context.scene.render.pixel_aspect_x),
        "pixel_aspect_y": float(context.scene.render.pixel_aspect_y),
    }

    try:
        context.scene.render.resolution_x = width
        context.scene.render.resolution_y = height
        context.scene.render.resolution_percentage = 100
        context.scene.render.pixel_aspect_x = 1.0
        context.scene.render.pixel_aspect_y = 1.0
        model_mask = _render_model_mask(
            context,
            camera=camera,
            targets=targets,
            path=model_path,
            width=width,
            height=height,
            threshold=threshold,
        )

        reference_mask = None
        resolved_source = ""
        resolved_outline = ""
        source_errors = []
        if source in {"auto", "outline"}:
            points, resolved_outline, outline_error = _outline_points(
                context.scene,
                collection,
                camera,
                outline_name,
            )
            if points:
                reference_mask = reference_metrics.rasterize_polygon(
                    points, width, height
                )
                resolved_source = "outline"
            elif outline_error:
                source_errors.append(outline_error)
        if reference_mask is None and source in {"auto", "alpha"}:
            reference_image_path = _image_path(collection)
            if reference_image_path:
                try:
                    reference_mask = _alpha_reference_mask(
                        reference_image_path,
                        width=width,
                        height=height,
                        margin=_camera_margin(camera),
                        threshold=threshold,
                    )
                    resolved_source = "alpha"
                except ValueError as exc:
                    source_errors.append(str(exc))
            else:
                source_errors.append(
                    "Reference guide collection has no readable image path"
                )
        if reference_mask is None:
            raise ValueError("; ".join(source_errors) or "No reference mask")

        metrics = reference_metrics.compare_masks(
            reference_mask, model_mask, width, height
        )
        reference_landmarks, target_landmarks, missing_landmark_objects = (
            _landmark_points(
                context.scene,
                collection,
                camera,
                landmark_targets,
            )
        )
        landmark_errors = reference_metrics.compare_landmarks(
            reference_landmarks, target_landmarks, width, height
        )
        _save_reference_mask(
            reference_path, reference_mask, width, height
        )
        _save_redline(
            redline_path, reference_mask, model_mask, width, height
        )
        metadata = inspection_render.publish_inspection_artifact(
            artifact,
            images=[
                {
                    "image_id": "model-mask",
                    "path": model_path,
                    "object": ", ".join(obj.name for obj in targets),
                    "view": "reference_camera",
                    "note": "Rendered model silhouette",
                },
                {
                    "image_id": "reference-mask",
                    "path": reference_path,
                    "object": collection.name,
                    "view": "reference_camera",
                    "note": f"Reference mask from {resolved_source}",
                },
                {
                    "image_id": "redline-overlay",
                    "path": redline_path,
                    "object": ", ".join(obj.name for obj in targets),
                    "view": "reference_camera",
                    "note": (
                        "Green=overlap, blue=reference missing from model, "
                        "red=model outside reference"
                    ),
                },
            ],
            metadata={
                "scene": context.scene.name,
                "frame": int(context.scene.frame_current),
                "resource_type": "reference_model_comparison",
                "guide_collection": collection.name,
                "camera": camera.name,
                "reference_identity": reference_identity,
                "object_names": [obj.name for obj in targets],
                "missing_object_names": missing_objects,
                "reference_mask_source": resolved_source,
                "outline_name": resolved_outline,
                "metrics": metrics,
                "landmark_errors": landmark_errors,
                "missing_landmark_object_names": missing_landmark_objects,
            },
        )
        return {
            "ok": True,
            "message": "Compared model render with calibrated reference",
            "guide_collection": collection.name,
            "camera": camera.name,
            "reference_identity": reference_identity,
            "object_names": [obj.name for obj in targets],
            "missing_object_names": missing_objects,
            "reference_mask_source": resolved_source,
            "outline_name": resolved_outline,
            "resolution": [width, height],
            "metrics": metrics,
            "landmark_errors": landmark_errors,
            "missing_landmark_object_names": missing_landmark_objects,
            "comparison_id": metadata["render_id"],
            "metadata_uri": metadata["metadata_uri"],
            "images": metadata["images"],
            "repair_priorities": [
                {
                    "type": "silhouette_region",
                    **region,
                }
                for region in metrics["error_regions"][:5]
            ]
            + [
                {
                    "type": "landmark",
                    **item,
                }
                for item in landmark_errors[:5]
            ],
        }
    except Exception as exc:
        _cleanup_artifact(artifact)
        return {
            "ok": False,
            "message": (
                f"Reference comparison failed: {type(exc).__name__}: {exc}"
            ),
            "guide_collection": collection.name,
            "camera": camera.name,
            "object_names": [obj.name for obj in targets],
            "missing_object_names": missing_objects,
        }
    finally:
        context.scene.render.resolution_x = projection_state["resolution_x"]
        context.scene.render.resolution_y = projection_state["resolution_y"]
        context.scene.render.resolution_percentage = projection_state[
            "resolution_percentage"
        ]
        context.scene.render.pixel_aspect_x = projection_state[
            "pixel_aspect_x"
        ]
        context.scene.render.pixel_aspect_y = projection_state[
            "pixel_aspect_y"
        ]


def register():
    pass


def unregister():
    pass
