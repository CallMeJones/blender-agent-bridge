"""Deterministic reference-image intake, scoring, and repair orchestration."""

from __future__ import annotations

import hashlib
import math
import os

import bpy

from . import (
    reference_benchmarks,
    reference_comparison,
    reference_guides,
    reference_image_masks,
    reference_multiview_scene,
    reference_scene,
    semantic_sculpt,
)


MAX_REFERENCE_IMAGES = 6
MAX_REFERENCE_FILE_BYTES = 256 * 1024 * 1024
MAX_MASK_AXIS = 512
MAX_MASK_PIXELS = MAX_MASK_AXIS * MAX_MASK_AXIS


def _finite(value, field, default=None, *, minimum=None, maximum=None):
    if value is None:
        value = default
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    if minimum is not None:
        number = max(float(minimum), number)
    if maximum is not None:
        number = min(float(maximum), number)
    return number


def _path(value, field):
    path = os.path.abspath(
        bpy.path.abspath(os.path.expanduser(str(value or "").strip()))
    )
    if not path or not os.path.isfile(path):
        raise ValueError(f"{field} does not exist: {path}")
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        raise ValueError(f"{field} could not be inspected: {exc}") from exc
    if size > MAX_REFERENCE_FILE_BYTES:
        raise ValueError(
            f"{field} exceeds the {MAX_REFERENCE_FILE_BYTES}-byte reference file limit"
        )
    return path


def _digest_file(path):
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return {"path": path, "sha256": digest.hexdigest(), "size_bytes": size}


def _load_pixels(path, *, max_axis):
    image = None
    try:
        image = bpy.data.images.load(path, check_existing=False)
        source_width = int(image.size[0])
        source_height = int(image.size[1])
        if source_width < 1 or source_height < 1:
            raise ValueError(f"image has no readable pixels: {path}")
        max_axis = max(16, min(MAX_MASK_AXIS, int(max_axis or MAX_MASK_AXIS)))
        scale = min(1.0, max_axis / max(source_width, source_height))
        width = max(1, int(round(source_width * scale)))
        height = max(1, int(round(source_height * scale)))
        if width * height > MAX_MASK_PIXELS:
            raise ValueError("sampled mask would exceed the synchronous pixel limit")
        if (width, height) != (source_width, source_height):
            image.scale(width, height)
            image.update()
        return {
            "source_size": [source_width, source_height],
            "sampled_size": [width, height],
            "pixels": list(image.pixels[:]),
        }
    finally:
        if image is not None and bpy.data.images.get(image.name) is image:
            bpy.data.images.remove(image)


def _annotation_source_count(item):
    return sum(
        (
            isinstance(item.get("annotations"), dict),
            bool(str(item.get("annotations_json") or "").strip()),
            bool(str(item.get("annotations_path") or "").strip()),
        )
    )


def _generated_annotation(item, image_path, *, max_mask_axis):
    mask_path = str(item.get("mask_path") or "").strip()
    mask_source = _path(mask_path, "mask_path") if mask_path else image_path
    sample = _load_pixels(mask_source, max_axis=max_mask_axis)
    mask = reference_image_masks.mask_from_pixels(
        sample,
        mode=item.get("mask_mode") or ("luminance" if mask_path else "auto"),
        threshold=_finite(
            item.get("mask_threshold"),
            "mask_threshold",
            0.5,
            minimum=0.0,
            maximum=1.0,
        ),
        background_color=item.get("background_color"),
    )
    width, height = sample["sampled_size"]
    outline = reference_image_masks.outline_from_mask(
        mask,
        width,
        height,
        max_points=int(item.get("max_outline_points") or 96),
    )
    if outline["foreground_coverage"] <= 0.001 or outline["foreground_coverage"] >= 0.995:
        raise ValueError(
            "derived foreground mask is empty or full; supply annotations or a better mask"
        )
    bounds = outline["bounds"]
    silhouette_warnings = _silhouette_plausibility_warnings(outline, bounds)
    subject = str(item.get("subject") or "reference model")
    return {
        "version": 1,
        "subject": subject,
        "coordinate_space": "normalized",
        "origin": "top_left",
        "image_size": [1.0, 1.0],
        "outlines": [
            {
                "name": str(item.get("outline_name") or "silhouette"),
                "points": outline["points"],
                "closed": True,
            }
        ],
        "masses": [
            {
                "name": str(item.get("mass_name") or "primary_mass"),
                "bounds": [bounds["x"], bounds["y"], bounds["width"], bounds["height"]],
            }
        ],
        "_intake_summary": {
            "mask_source": "mask_path" if mask_path else "image",
            "mask_path": mask_source,
            "sampled_size": sample["sampled_size"],
            "source_size": sample["source_size"],
            "foreground_coverage": outline["foreground_coverage"],
            "edge_pixel_count": outline["edge_pixel_count"],
            "outline_point_count": len(outline["points"]),
            "image_identity": _digest_file(image_path),
            "warnings": silhouette_warnings,
        },
    }


def prepare_reference_images(
    context,
    *,
    references,
    subject="reference model",
    collection_name="Reference Image Intake Guides",
    subject_center=(0.0, 0.0, 1.5),
    subject_height=0.0,
    active_view="",
    create_guides=True,
    require_annotations=False,
    max_mask_axis=256,
    label="Prepare reference images",
):
    """Normalize one or more reference images and optionally create guides."""

    if not isinstance(references, list) or not 1 <= len(references) <= MAX_REFERENCE_IMAGES:
        return {
            "ok": False,
            "message": f"references must contain 1 to {MAX_REFERENCE_IMAGES} image objects",
        }
    prepared = []
    summaries = []
    try:
        for index, raw in enumerate(references):
            if not isinstance(raw, dict):
                raise ValueError(f"references[{index}] must be an object")
            image_path = _path(raw.get("image_path"), f"references[{index}].image_path")
            axis = str(raw.get("axis") or ("FRONT" if index == 0 else "RIGHT")).strip().upper()
            view = {
                "name": str(raw.get("name") or f"view_{index + 1}").strip()
                or f"view_{index + 1}",
                "image_path": image_path,
                "axis": axis,
                "view_direction": raw.get("view_direction"),
                "up_direction": raw.get("up_direction"),
                "default_coordinate_space": str(
                    raw.get("default_coordinate_space") or "pixel"
                ),
                "default_origin": str(raw.get("default_origin") or "top_left"),
                "plane_height": raw.get("plane_height"),
                "subject_height": raw.get(
                    "subject_height",
                    0.0 if axis in {"TOP", "BOTTOM"} else subject_height,
                ),
                "subject_bounds": raw.get("subject_bounds"),
                "camera_margin": raw.get("camera_margin"),
                "guide_offset": raw.get("guide_offset"),
                "include_image_plane": raw.get("include_image_plane", True),
                "image_alpha": raw.get("image_alpha", 0.35),
            }
            source_count = _annotation_source_count(raw)
            summary = {"name": view["name"], "image_path": image_path}
            if source_count == 1:
                for key in ("annotations", "annotations_json", "annotations_path"):
                    if key in raw:
                        view[key] = raw.get(key)
                summary["annotation_source"] = "supplied"
            elif source_count == 0 and not require_annotations:
                annotation = _generated_annotation(
                    raw,
                    image_path,
                    max_mask_axis=max_mask_axis,
                )
                summary.update(annotation.pop("_intake_summary"))
                summary["annotation_source"] = "generated_foreground_mask"
                view["annotations"] = annotation
                view["default_coordinate_space"] = "normalized"
                view["default_origin"] = "top_left"
            else:
                raise ValueError(
                    f"references[{index}] must supply exactly one annotation source"
                )
            prepared.append(view)
            summaries.append(summary)
    except (OSError, ValueError, OverflowError) as exc:
        return {"ok": False, "message": str(exc), "prepared_views": prepared}

    # Collect per-view silhouette warnings to the top level. Left only inside
    # each summary they are easy to miss, which is how an unusable outline was
    # previously reported as a clean success.
    intake_warnings = []
    for summary in summaries:
        for warning in summary.get("warnings") or []:
            intake_warnings.append("%s: %s" % (summary.get("name") or "view", warning))

    message = f"Prepared {len(prepared)} reference image(s)"
    if intake_warnings:
        message += (
            "; %d generated silhouette warning(s) -- inspect the outline before building from it"
            % len(intake_warnings)
        )

    result = {
        "ok": True,
        "message": message,
        "prepared_views": prepared,
        "intake": summaries,
        "warnings": intake_warnings,
        "silhouette_quality": "suspect" if intake_warnings else "plausible",
    }
    if not create_guides:
        return result
    try:
        if len(prepared) == 1:
            view = prepared[0]
            guide_result = reference_guides.create_reference_guides_from_annotations(
                context,
                image_path=view["image_path"],
                annotations=view.get("annotations"),
                annotations_json=str(view.get("annotations_json") or ""),
                annotations_path=str(view.get("annotations_path") or ""),
                default_coordinate_space=view["default_coordinate_space"],
                default_origin=view["default_origin"],
                subject=str(subject or ""),
                collection_name=collection_name,
                plane_height=_finite(
                    view.get("plane_height"),
                    "plane_height",
                    3.0,
                    minimum=0.01,
                    maximum=100.0,
                ),
                subject_height=_finite(
                    view.get("subject_height"),
                    "subject_height",
                    0.0,
                    minimum=0.0,
                    maximum=100.0,
                ),
                subject_bounds=view.get("subject_bounds"),
                camera_margin=_finite(
                    view.get("camera_margin"),
                    "camera_margin",
                    0.05,
                    minimum=0.0,
                    maximum=1.0,
                ),
                guide_offset_y=_finite(
                    view.get("guide_offset"),
                    "guide_offset",
                    -0.02,
                    minimum=-10.0,
                    maximum=10.0,
                ),
                include_image_plane=bool(view.get("include_image_plane", True)),
                image_alpha=_finite(
                    view.get("image_alpha"),
                    "image_alpha",
                    0.35,
                    minimum=0.0,
                    maximum=1.0,
                ),
                create_camera=True,
                label=label,
            )
        else:
            guide_result = reference_multiview_scene.create_multiview_reference_guides(
                context,
                views=prepared,
                subject=subject,
                collection_name=collection_name,
                subject_center=subject_center,
                subject_height=subject_height,
                active_view=active_view,
                require_reconstruction=False,
                label=label,
            )
    except (TypeError, ValueError, OverflowError) as exc:
        return {
            "ok": False,
            "message": str(exc),
            "prepared_views": prepared,
            "intake": summaries,
        }
    result["guide_result"] = guide_result
    result["ok"] = bool(guide_result.get("ok"))
    guide_message = guide_result.get("message") or result["message"]
    # Keep the silhouette warning visible: the guide message would otherwise
    # replace it and the caller would build on a suspect outline unknowingly.
    if intake_warnings:
        guide_message += (
            "; %d generated silhouette warning(s) -- inspect the outline before building from it"
            % len(intake_warnings)
        )
    result["message"] = guide_message
    return result


def _reference_collection(collection_name):
    name = str(collection_name or "").strip()
    if name:
        collection = bpy.data.collections.get(name)
        if collection is None:
            return None, f"Reference guide collection not found: {name}"
        if bool(collection.get("reference_modeling_guides", False)) or bool(
            collection.get("reference_multiview_guides", False)
        ):
            return collection, ""
        return None, f"Collection is not tagged as reference guides: {name}"
    matches = [
        collection
        for collection in bpy.data.collections
        if bool(collection.get("reference_modeling_guides", False))
        or bool(collection.get("reference_multiview_guides", False))
    ]
    if not matches:
        return None, "No reference guide collection is available"
    if len(matches) > 1:
        return None, "Multiple reference guide collections are available; supply collection_name"
    return matches[0], ""


def _view_entries(collection):
    metadata = reference_scene.json_prop(collection, reference_scene.REFERENCE_GUIDE_METADATA_PROP)
    views = metadata.get("views") if isinstance(metadata, dict) else None
    if isinstance(views, list) and views:
        return [
            {
                "view_name": str(view.get("name") or ""),
                "collection_name": str(view.get("collection") or ""),
                "camera_name": str(view.get("camera") or ""),
            }
            for view in views
            if isinstance(view, dict)
        ]
    camera, error = reference_scene.comparison_camera(collection, "")
    if error:
        raise ValueError(error)
    return [
        {
            "view_name": str(camera.get("reference_view_name") or collection.name),
            "collection_name": collection.name,
            "camera_name": camera.name,
        }
    ]


def _aggregate_scores(evaluations):
    scores = [
        float(item["score"]["score"])
        for item in evaluations
        if item.get("ok") and isinstance(item.get("score"), dict)
    ]
    ious = [
        float(item["comparison"]["metrics"].get("silhouette_iou") or 0.0)
        for item in evaluations
        if item.get("ok")
    ]
    if not scores:
        return {"score": 0.0, "mean_score": 0.0, "worst_score": 0.0, "mean_iou": 0.0}
    return {
        "score": round(sum(scores) / len(scores), 6),
        "mean_score": round(sum(scores) / len(scores), 6),
        "worst_score": round(min(scores), 6),
        "mean_iou": round(sum(ious) / max(1, len(ious)), 6),
    }


def _comparison_score(comparison, *, edge_weight, landmark_weight):
    if not comparison.get("ok"):
        raise ValueError(comparison.get("message") or "Reference comparison failed")
    metrics = comparison.get("metrics") or {}
    resolution = comparison.get("resolution") or [1, 1]
    diagonal = max(1.0, math.hypot(float(resolution[0]), float(resolution[1])))
    iou = float(metrics.get("silhouette_iou") or 0.0)
    edge = float(metrics.get("mean_edge_distance_pixels") or 0.0) / diagonal
    landmark_errors = list(comparison.get("landmark_errors") or [])
    landmark = (
        sum(float(item.get("distance_pixels") or 0.0) for item in landmark_errors)
        / len(landmark_errors)
        / diagonal
        if landmark_errors
        else 0.0
    )
    values = (iou, edge, landmark, float(edge_weight), float(landmark_weight))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Reference comparison produced a non-finite score component")
    return {
        "score": iou - values[3] * edge - values[4] * landmark,
        "silhouette_iou": iou,
        "normalized_edge_error": edge,
        "normalized_landmark_error": landmark,
        "comparison_id": comparison.get("comparison_id", ""),
    }


def evaluate_multiview_reference_match(
    context,
    *,
    collection_name="",
    object_names=None,
    selected_only=True,
    view_names=None,
    outline_name="",
    reference_mask_source="auto",
    landmark_targets=None,
    benchmark_profile="refined",
    threshold_overrides=None,
    max_axis=384,
    mask_threshold=0.5,
    edge_weight=0.25,
    landmark_weight=0.1,
    capture_dir=None,
):
    """Compare a model against every calibrated reference view and aggregate scores."""

    collection, error = _reference_collection(collection_name)
    if error:
        return {"ok": False, "message": error}
    requested = {str(name).casefold() for name in list(view_names or []) if str(name).strip()}
    try:
        entries = _view_entries(collection)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    if requested:
        entries = [
            entry
            for entry in entries
            if entry["view_name"].casefold() in requested
            or entry["camera_name"].casefold() in requested
            or entry["collection_name"].casefold() in requested
        ]
    if not entries:
        return {"ok": False, "message": "No calibrated reference views matched"}

    evaluations = []
    failures = []
    for entry in entries[:MAX_REFERENCE_IMAGES]:
        comparison = reference_comparison.compare_model_to_reference(
            context,
            collection_name=entry["collection_name"],
            camera_name=entry["camera_name"],
            object_names=object_names or [],
            selected_only=selected_only,
            outline_name=outline_name,
            reference_mask_source=reference_mask_source,
            landmark_targets=landmark_targets or [],
            max_axis=max_axis,
            mask_threshold=mask_threshold,
            capture_dir=capture_dir,
        )
        if not comparison.get("ok"):
            failures.append(
                {
                    "view_name": entry["view_name"],
                    "message": comparison.get("message") or "comparison failed",
                }
            )
            evaluations.append({"ok": False, **entry, "comparison": comparison})
            continue
        try:
            score = _comparison_score(
                comparison,
                edge_weight=edge_weight,
                landmark_weight=landmark_weight,
            )
            benchmark = reference_benchmarks.evaluate_comparison(
                comparison.get("metrics") or {},
                comparison.get("landmark_errors") or [],
                profile=benchmark_profile,
                threshold_overrides=threshold_overrides or {},
            )
        except ValueError as exc:
            failures.append({"view_name": entry["view_name"], "message": str(exc)})
            evaluations.append({"ok": False, **entry, "comparison": comparison})
            continue
        evaluations.append(
            {
                "ok": True,
                **entry,
                "comparison": comparison,
                "score": score,
                "benchmark": benchmark,
                "repair_priorities": comparison.get("repair_priorities") or [],
            }
        )
    passed = [item for item in evaluations if item.get("ok")]
    worst = min(
        passed,
        key=lambda item: item["score"]["score"],
        default=None,
    )
    failed_gates = sorted(
        {
            gate
            for item in passed
            for gate in (item.get("benchmark") or {}).get("failed_gates", [])
        }
    )
    return {
        "ok": bool(passed) and not failures,
        "message": f"Evaluated {len(passed)} calibrated reference view(s)",
        "collection": collection.name,
        "evaluated_view_count": len(passed),
        "failed_view_count": len(failures),
        "failures": failures,
        "aggregate": _aggregate_scores(passed),
        "worst_view": (
            {
                "view_name": worst["view_name"],
                "collection_name": worst["collection_name"],
                "camera_name": worst["camera_name"],
                "score": worst["score"],
                "benchmark": worst["benchmark"],
                "repair_priorities": worst["repair_priorities"][:5],
            }
            if worst
            else {}
        ),
        "failed_gates": failed_gates,
        "evaluations": evaluations,
    }


def _region_center(name):
    rows = {"upper": 1.0 / 6.0, "middle": 0.5, "lower": 5.0 / 6.0}
    columns = {"left": 1.0 / 6.0, "center": 0.5, "right": 5.0 / 6.0}
    parts = str(name or "").split("_", 1)
    if len(parts) != 2:
        return [0.5, 0.5]
    return [columns.get(parts[1], 0.5), rows.get(parts[0], 0.5)]


def _controls_from_priorities(priorities, *, max_controls, step):
    controls = []
    center = [0.5, 0.5]
    for item in list(priorities or []):
        if item.get("type") != "silhouette_region":
            continue
        source = _region_center(item.get("name"))
        direction = [source[0] - center[0], source[1] - center[1]]
        length = max(1.0e-6, math.hypot(direction[0], direction[1]))
        direction = [direction[0] / length, direction[1] / length]
        problem = str(item.get("problem") or "")
        if problem == "model_missing":
            target = [source[0] + direction[0] * step, source[1] + direction[1] * step]
        elif problem == "model_excess":
            target = [source[0] - direction[0] * step, source[1] - direction[1] * step]
        else:
            target = [source[0], source[1]]
        controls.append(
            {
                "source": [max(0.0, min(1.0, source[0])), max(0.0, min(1.0, source[1]))],
                "target": [max(0.0, min(1.0, target[0])), max(0.0, min(1.0, target[1]))],
                "radius": max(0.04, min(0.35, math.sqrt(float(item.get("magnitude") or 0.01)))),
                "strength": 1.0,
            }
        )
        if len(controls) >= max_controls:
            break
    return controls


# A generated silhouette can be structurally valid and still be nonsense. On a
# white-uniform-on-white-page subject the derived outline wandered through empty
# page and reported a clean success, which then poisoned the hull, the fit, the
# part graph and the score with nothing to stop it. These checks use statistics
# already computed, so they cost nothing and only ever warn.
MASS_FILLS_FRAME_RATIO = 0.90
PLAUSIBLE_COVERAGE_RANGE = (0.05, 0.60)
BORDER_PROXIMITY = 0.02
BORDER_POINT_FRACTION = 0.25


def _silhouette_plausibility_warnings(outline, bounds):
    """Warn when a derived outline looks like a failed segmentation."""

    warnings = []
    width = float(bounds.get("width") or 0.0)
    height = float(bounds.get("height") or 0.0)
    if width >= MASS_FILLS_FRAME_RATIO and height >= MASS_FILLS_FRAME_RATIO:
        warnings.append(
            "The derived primary mass fills %.0f%% x %.0f%% of the frame, which usually means the "
            "subject was not separated from the background. Supply a mask image or annotation JSON."
            % (100.0 * width, 100.0 * height)
        )

    coverage = float(outline.get("foreground_coverage") or 0.0)
    low, high = PLAUSIBLE_COVERAGE_RANGE
    if coverage < low or coverage > high:
        warnings.append(
            "Derived foreground coverage is %.1f%%, outside the %.0f-%.0f%% band typical of a "
            "framed subject. Check the generated silhouette before building from it."
            % (100.0 * coverage, 100.0 * low, 100.0 * high)
        )

    points = outline.get("points") or []
    if points:
        on_border = sum(
            1
            for point in points
            if len(point) >= 2
            and (
                point[0] <= BORDER_PROXIMITY
                or point[0] >= 1.0 - BORDER_PROXIMITY
                or point[1] <= BORDER_PROXIMITY
                or point[1] >= 1.0 - BORDER_PROXIMITY
            )
        )
        fraction = on_border / float(len(points))
        if fraction >= BORDER_POINT_FRACTION:
            warnings.append(
                "%.0f%% of the outline sits on the image border, which usually means the mask "
                "leaked into the background rather than tracing the subject."
                % (100.0 * fraction)
            )
    return warnings


# A pass may trade a little all-view score for a large worst-view gain, but a
# real decline means the pass made the model worse overall.
AGGREGATE_REGRESSION_TOLERANCE = 0.002
# Repeated passes previously grew a figure's bounding box by 32% as spikes were
# pushed outward. Silhouette IoU barely registers that; extent does.
MAXIMUM_REPAIR_EXTENT_GROWTH = 0.05


def _repair_target_object(context, object_name):
    """Resolve the mesh the repair will edit, or None when it is ambiguous."""

    import bpy

    name = str(object_name or "").strip()
    if name:
        obj = bpy.data.objects.get(name)
        return obj if obj is not None and obj.type == "MESH" else None
    selected = [obj for obj in getattr(context, "selected_objects", []) or [] if obj.type == "MESH"]
    if len(selected) == 1:
        return selected[0]
    active = getattr(getattr(context, "view_layer", None), "objects", None)
    active = getattr(active, "active", None)
    return active if active is not None and active.type == "MESH" else None


def _object_extent(obj):
    """Largest world-space bounding-box dimension, used as a growth budget."""

    if obj is None:
        return 0.0
    try:
        return float(max(obj.dimensions))
    except (AttributeError, TypeError, ValueError):
        return 0.0


def _aggregate_score(evaluation):
    aggregate = (evaluation or {}).get("aggregate") or {}
    for key in ("mean_score", "score", "mean_iou"):
        value = aggregate.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def _aggregate_regression(before, after):
    """How much the all-view score fell. Positive means it got worse."""

    return _aggregate_score(before) - _aggregate_score(after)


def auto_reference_sculpt_repair(
    context,
    *,
    object_name="",
    collection_name="",
    view_names=None,
    region_names=None,
    allow_all_vertices=False,
    outline_name="",
    reference_mask_source="auto",
    strength_candidates=None,
    minimum_improvement=0.0005,
    max_controls=4,
    control_step=0.045,
    maximum_world_displacement=0.05,
    max_axis=256,
    mask_threshold=0.5,
    edge_weight=0.25,
    landmark_weight=0.1,
    landmark_targets=None,
    capture_dir=None,
    label="Auto reference sculpt repair",
):
    """Generate screen-space controls from the worst measured view and optimize them."""

    before = evaluate_multiview_reference_match(
        context,
        collection_name=collection_name,
        object_names=[object_name] if object_name else [],
        selected_only=not bool(object_name),
        view_names=view_names or [],
        outline_name=outline_name,
        reference_mask_source=reference_mask_source,
        landmark_targets=landmark_targets or [],
        max_axis=max_axis,
        mask_threshold=mask_threshold,
        edge_weight=edge_weight,
        landmark_weight=landmark_weight,
        capture_dir=capture_dir,
    )
    if not before.get("ok"):
        return {"ok": False, "message": before.get("message") or "baseline evaluation failed", "baseline": before}
    worst = before.get("worst_view") or {}
    controls = _controls_from_priorities(
        worst.get("repair_priorities") or [],
        max_controls=max(1, min(8, int(max_controls or 4))),
        step=max(0.001, min(0.2, float(control_step or 0.045))),
    )
    if not controls:
        return {
            "ok": True,
            "changed": False,
            "message": "No silhouette repair controls were generated from the current score",
            "baseline": before,
        }
    # The repair below optimizes the single worst view. Improving that view can
    # take the gain out of the others, so capture enough state to undo the pass
    # if the full-view aggregate ends up worse than it started.
    repair_target = _repair_target_object(context, object_name)
    points_before = semantic_sculpt._local_points(repair_target) if repair_target else None
    extent_before = _object_extent(repair_target) if repair_target else 0.0

    repair = semantic_sculpt.optimize_screen_space_sculpt(
        context,
        object_name=object_name,
        collection_name=worst.get("collection_name") or collection_name,
        camera_name=worst.get("camera_name") or "",
        outline_name=outline_name,
        reference_mask_source=reference_mask_source,
        region_names=region_names or [],
        controls=controls,
        origin="top_left",
        strength_candidates=strength_candidates or [0.5, 1.0, 1.5],
        minimum_improvement=minimum_improvement,
        edge_weight=edge_weight,
        landmark_weight=landmark_weight,
        landmark_targets=landmark_targets or [],
        max_axis=max_axis,
        mask_threshold=mask_threshold,
        allow_all_vertices=allow_all_vertices,
        maximum_world_displacement=maximum_world_displacement,
        max_vertices=100000,
        capture_dir=capture_dir,
        label=label,
    )
    if not repair.get("ok") or not repair.get("changed"):
        return {
            "ok": bool(repair.get("ok")),
            "changed": False,
            "message": repair.get("message") or "repair did not improve the score",
            "baseline": before,
            "generated_controls": controls,
            "repair": repair,
        }
    after = evaluate_multiview_reference_match(
        context,
        collection_name=collection_name,
        object_names=[object_name] if object_name else [],
        selected_only=not bool(object_name),
        view_names=view_names or [],
        outline_name=outline_name,
        reference_mask_source=reference_mask_source,
        landmark_targets=landmark_targets or [],
        max_axis=max_axis,
        mask_threshold=mask_threshold,
        edge_weight=edge_weight,
        landmark_weight=landmark_weight,
        capture_dir=capture_dir,
    )
    regression = _aggregate_regression(before, after)
    extent_after = _object_extent(repair_target) if repair_target else 0.0
    extent_growth = (
        (extent_after - extent_before) / extent_before if extent_before > 1e-9 else 0.0
    )
    over_budget = extent_growth > MAXIMUM_REPAIR_EXTENT_GROWTH

    if (regression > AGGREGATE_REGRESSION_TOLERANCE or over_budget) and points_before is not None:
        # The worst view improved but the model as a whole did not. Undo the
        # pass rather than reporting a change the caller would have to detect
        # by re-scoring, which is how repeated passes silently destroy a mesh.
        semantic_sculpt._write_points(repair_target, points_before)
        restored = evaluate_multiview_reference_match(
            context,
            collection_name=collection_name,
            object_names=[object_name] if object_name else [],
            selected_only=not bool(object_name),
            view_names=view_names or [],
            outline_name=outline_name,
            reference_mask_source=reference_mask_source,
            landmark_targets=landmark_targets or [],
            max_axis=max_axis,
            mask_threshold=mask_threshold,
            edge_weight=edge_weight,
            landmark_weight=landmark_weight,
            capture_dir=capture_dir,
        )
        reason = (
            "grew the model extent by %.1f%% (budget %.0f%%)" % (
                100.0 * extent_growth, 100.0 * MAXIMUM_REPAIR_EXTENT_GROWTH
            )
            if over_budget
            else "reduced the all-view score by %.4f" % regression
        )
        return {
            "ok": True,
            "changed": False,
            "reverted": True,
            "message": (
                "Repair improved the worst view but %s, so the mesh was restored. "
                "Further automatic passes are unlikely to help; inspect the model and "
                "make a targeted correction instead." % reason
            ),
            "baseline": before,
            "rejected": after,
            "after": restored,
            "aggregate_regression": regression,
            "extent_growth": extent_growth,
            "generated_controls": controls,
            "repair": repair,
        }

    return {
        "ok": bool(after.get("ok")),
        "changed": True,
        "reverted": False,
        "message": "Applied one measured reference-sculpt repair pass",
        "baseline": before,
        "after": after,
        "aggregate_regression": regression,
        "extent_growth": extent_growth,
        "generated_controls": controls,
        "repair": repair,
    }


def register():
    pass


def unregister():
    pass
