"""Preview-safe Blender adapter for measured multi-view surface fitting."""

from __future__ import annotations

import json
import math

import bpy
from mathutils import Vector

from . import (
    live_preview,
    reference_comparison,
    reference_depth,
    reference_fitting,
    reference_scene,
    reference_visual_hull,
)


def _mesh_object(context, object_name):
    name = str(object_name or "").strip()
    obj = bpy.data.objects.get(name) if name else context.active_object
    if obj is None:
        return None, f"Mesh object not found: {name}" if name else "No active mesh object"
    if obj.type != "MESH":
        return None, f"Object is not a mesh: {obj.name}"
    return obj, ""


def _validate_object(obj, *, max_vertices):
    if obj.mode != "OBJECT":
        return f"Multi-view fitting requires Object Mode: {obj.name} is in {obj.mode} mode"
    if not getattr(obj, "is_editable", True) or not getattr(obj.data, "is_editable", True):
        return f"Linked mesh data is not editable: {obj.name}"
    linked_objects = [
        candidate.name
        for candidate in bpy.data.objects
        if candidate.type == "MESH" and candidate.data is obj.data
    ]
    if len(linked_objects) > 1:
        return (
            f"Mesh data is shared by {len(linked_objects)} objects: {obj.data.name}. "
            "Make the fitted mesh single-user first."
        )
    if len(obj.data.vertices) > int(max_vertices):
        return (
            f"Mesh contains {len(obj.data.vertices)} vertices; limit is {int(max_vertices)}"
        )
    if obj.data.shape_keys:
        return (
            "Mesh has shape keys; multi-view fitting requires a mesh without shape keys "
            "until shape-key block editing and rollback are supported"
        )
    if not obj.data.polygons:
        return "Mesh has no faces"
    return ""


def _world_points(obj):
    return [tuple(obj.matrix_world @ vertex.co) for vertex in obj.data.vertices]


def _faces(obj):
    return [tuple(polygon.vertices) for polygon in obj.data.polygons]


def _write_world_points(obj, points):
    inverse = obj.matrix_world.inverted()
    for vertex, point in zip(obj.data.vertices, points):
        vertex.co = inverse @ Vector(point)
    obj.data.update(calc_edges=True)


def _landmark_constraints(master, names):
    requested = {
        str(name).strip().casefold()
        for name in names or []
        if str(name).strip()
    }
    if not requested:
        return []
    constraints = []
    found = set()
    for obj in reference_scene.guide_objects(master, "landmark_3d"):
        name = str(obj.get("reference_guide_name") or obj.name).strip()
        if requested and name.casefold() not in requested:
            continue
        constraints.append(
            {
                "name": name,
                "target": list(obj.matrix_world.translation),
                "weight": 1.0,
            }
        )
        found.add(name.casefold())
    missing = sorted(requested - found)
    if missing:
        raise ValueError("Reconstructed 3D landmark(s) not found: " + ", ".join(missing))
    return constraints


def _comparison_summary(result):
    if not result.get("ok"):
        return {
            "ok": False,
            "message": result.get("message") or "Reference comparison failed",
            "guide_collection": result.get("guide_collection", ""),
            "camera": result.get("camera", ""),
        }
    metrics = result.get("metrics") or {}
    resolution = result.get("resolution") or [1, 1]
    diagonal = max(1.0, math.hypot(float(resolution[0]), float(resolution[1])))
    score = float(metrics.get("silhouette_iou") or 0.0) - (
        float(metrics.get("mean_edge_distance_pixels") or 0.0) / diagonal * 0.25
    )
    return {
        "ok": True,
        "guide_collection": result.get("guide_collection", ""),
        "camera": result.get("camera", ""),
        "comparison_id": result.get("comparison_id", ""),
        "metadata_uri": result.get("metadata_uri", ""),
        "score": score,
        "metrics": metrics,
        "landmark_errors": result.get("landmark_errors") or [],
        "repair_priorities": result.get("repair_priorities") or [],
        "images": result.get("images") or [],
    }


def _capture_evidence(context, obj, views, *, max_axis, mask_threshold, capture_dir):
    results = []
    for view in views:
        result = reference_comparison.compare_model_to_reference(
            context,
            collection_name=view.get("collection") or "",
            camera_name=view.get("camera") or "",
            object_names=[obj.name],
            selected_only=False,
            outline_name=view.get("outline_name") or "",
            reference_mask_source="outline",
            max_axis=max_axis,
            mask_threshold=mask_threshold,
            capture_dir=capture_dir,
        )
        summary = _comparison_summary(result)
        summary["view_name"] = view["name"]
        results.append(summary)
    successful = [item for item in results if item["ok"]]
    return {
        "views": results,
        "successful_view_count": len(successful),
        "aggregate_score": (
            sum(item["score"] for item in successful) / len(successful)
            if successful
            else None
        ),
    }


def fit_surface_to_multiview_references(
    context,
    *,
    object_name="",
    collection_name="",
    view_names=None,
    outline_overrides=None,
    depth_sources=None,
    landmark_names=None,
    iterations=6,
    step_candidates=None,
    minimum_improvement=1.0e-5,
    silhouette_weight=1.0,
    depth_weight=0.5,
    landmark_weight=0.5,
    worst_view_weight=0.25,
    per_view_regression_tolerance=0.002,
    regularization=0.35,
    propagation_steps=4,
    propagation_decay=0.8,
    feature_preservation=0.25,
    maximum_step=0.0,
    maximum_total_displacement=0.0,
    preserve_volume=0.0,
    pinned_vertex_indices=None,
    max_depth_axis=256,
    capture_evidence=False,
    evidence_max_axis=256,
    evidence_mask_threshold=0.5,
    evidence_regression_tolerance=0.002,
    capture_dir=None,
    max_vertices=100000,
    label="Fit surface to multi-view references",
):
    """Derive and optimize joint corrections from calibrated reference views."""

    obj, error = _mesh_object(context, object_name)
    if error:
        return {"ok": False, "message": error}
    error = _validate_object(
        obj,
        max_vertices=max_vertices,
    )
    if error:
        return {"ok": False, "message": error, "object": obj.name}
    master, error = reference_visual_hull.resolve_multiview_collection(collection_name)
    if error:
        return {"ok": False, "message": error, "object": obj.name}
    try:
        views, skipped_views = reference_visual_hull.source_silhouette_views(
            master,
            view_names,
            outline_overrides,
        )
        views, depth_summary = reference_depth.attach_depth_sources(
            views,
            depth_sources,
            max_axis=max_depth_axis,
        )
        landmarks = _landmark_constraints(master, landmark_names)
        original = _world_points(obj)
        faces = _faces(obj)
        fit = reference_fitting.fit_surface_to_references(
            original,
            faces,
            views,
            landmarks=landmarks,
            iterations=iterations,
            step_candidates=step_candidates or [0.25, 0.5, 1.0],
            minimum_improvement=minimum_improvement,
            silhouette_weight=silhouette_weight,
            depth_weight=depth_weight,
            landmark_weight=landmark_weight,
            worst_view_weight=worst_view_weight,
            per_view_regression_tolerance=per_view_regression_tolerance,
            regularization=regularization,
            propagation_steps=propagation_steps,
            propagation_decay=propagation_decay,
            feature_preservation=feature_preservation,
            maximum_step=maximum_step,
            maximum_total_displacement=maximum_total_displacement,
            preserve_volume=preserve_volume,
            pinned_vertex_indices=pinned_vertex_indices,
        )
        depth_measurement_counts = {
            (view["name"].casefold(), layer["mode"]): layer["sample_count"]
            for view in fit["baseline"]["per_view"]
            for layer in view["depth_layers"]
        }
        unused_depth_sources = [
            item
            for item in depth_summary
            if depth_measurement_counts.get(
                (item["view_name"].casefold(), item["mode"]),
                0,
            ) == 0
        ]
        if unused_depth_sources:
            raise ValueError(
                "Calibrated depth source(s) did not overlap eligible front/back surface vertices: "
                + ", ".join(
                    f"{item['view_name']}:{item['mode']} ({item['name']})"
                    for item in unused_depth_sources
                )
            )
    except (TypeError, ValueError, OverflowError) as exc:
        return {
            "ok": False,
            "code": "invalid_reference_fit",
            "message": str(exc),
            "object": obj.name,
            "guide_collection": master.name,
        }

    warnings = []
    if skipped_views:
        warnings.append(
            "Skipped calibrated view(s) without a cyclic outline: "
            + ", ".join(skipped_views)
        )
    if not fit["changed"]:
        return {
            "ok": True,
            "changed": False,
            "message": "No candidate improved the bounded multi-view objective; mesh unchanged",
            "object": obj.name,
            "guide_collection": master.name,
            "views": [view["name"] for view in views],
            "depth_sources": depth_summary,
            "baseline": fit["baseline"],
            "final": fit["final"],
            "objective_improvement": 0.0,
            "history": fit["history"],
            "stop_reason": fit["stop_reason"],
            "integrity": fit["integrity"],
            "workload": fit["workload"],
            "warnings": warnings,
        }

    before_evidence = None
    if capture_evidence:
        before_evidence = _capture_evidence(
            context,
            obj,
            views,
            max_axis=evidence_max_axis,
            mask_threshold=evidence_mask_threshold,
            capture_dir=capture_dir,
        )
        if before_evidence["successful_view_count"] != len(views):
            return {
                "ok": False,
                "changed": False,
                "code": "incomplete_multiview_evidence",
                "message": "Could not render baseline evidence for every selected view; mesh unchanged",
                "object": obj.name,
                "guide_collection": master.name,
                "baseline": fit["baseline"],
                "evidence": {"before": before_evidence, "after": None},
                "warnings": warnings,
            }
    operation = live_preview.begin_isolated(label, context)
    transaction = operation["transaction"]
    try:
        live_preview._record_mesh_data_snapshot(obj)
        live_preview._record_id_property(
            "object",
            obj.name,
            "reference_multiview_fit_metadata_json",
        )
        _write_world_points(obj, fit["points"])
        after_evidence = None
        if capture_evidence:
            after_evidence = _capture_evidence(
                context,
                obj,
                views,
                max_axis=evidence_max_axis,
                mask_threshold=evidence_mask_threshold,
                capture_dir=capture_dir,
            )
            if after_evidence["successful_view_count"] != len(views):
                _write_world_points(obj, original)
                live_preview.abort_isolated(operation, context)
                return {
                    "ok": False,
                    "changed": False,
                    "code": "incomplete_multiview_evidence",
                    "message": "Could not render final evidence for every selected view; mesh restored",
                    "object": obj.name,
                    "guide_collection": master.name,
                    "baseline": fit["baseline"],
                    "candidate": fit["final"],
                    "evidence": {"before": before_evidence, "after": after_evidence},
                    "warnings": warnings,
                }
            before_score = before_evidence.get("aggregate_score")
            after_score = after_evidence.get("aggregate_score")
            if after_score < before_score - max(0.0, evidence_regression_tolerance):
                _write_world_points(obj, original)
                live_preview.abort_isolated(operation, context)
                return {
                    "ok": True,
                    "changed": False,
                    "message": "Rendered cross-view verification regressed; mesh restored",
                    "object": obj.name,
                    "guide_collection": master.name,
                    "baseline": fit["baseline"],
                    "candidate": fit["final"],
                    "evidence": {"before": before_evidence, "after": after_evidence},
                    "warnings": warnings,
                }
        metadata = {
            "guide_collection": master.name,
            "views": [view["name"] for view in views],
            "depth_sources": depth_summary,
            "landmark_bindings": fit["landmark_bindings"],
            "baseline_objective": fit["baseline"]["objective"],
            "final_objective": fit["final"]["objective"],
            "objective_improvement": fit["objective_improvement"],
            "integrity": fit["integrity"],
            "workload": fit["workload"],
        }
        obj["reference_multiview_fit_metadata_json"] = json.dumps(
            metadata,
            ensure_ascii=True,
            sort_keys=True,
        )
        transaction["applied_steps"].append(
            {
                "type": "fit_surface_to_multiview_references",
                "label": label,
                "object": obj.name,
                "guide_collection": master.name,
                "views": [view["name"] for view in views],
                "objective_improvement": fit["objective_improvement"],
            }
        )
        transaction = live_preview.finish_isolated(operation)
        live_preview.redraw(context)
        live_preview._mark_pending(context, label)
        return {
            "ok": True,
            "changed": True,
            "message": (
                f"Improved {obj.name} across {len(views)} calibrated views by "
                f"{fit['objective_improvement']:.6g}"
            ),
            "object": obj.name,
            "guide_collection": master.name,
            "views": [view["name"] for view in views],
            "depth_sources": depth_summary,
            "landmark_bindings": fit["landmark_bindings"],
            "baseline": fit["baseline"],
            "final": fit["final"],
            "objective_improvement": fit["objective_improvement"],
            "history": fit["history"],
            "stop_reason": fit["stop_reason"],
            "deformation": fit["deformation"],
            "integrity": fit["integrity"],
            "workload": fit["workload"],
            "evidence": (
                {"before": before_evidence, "after": after_evidence}
                if capture_evidence
                else None
            ),
            "warnings": warnings,
            "transaction_id": transaction["id"],
        }
    except Exception as exc:
        try:
            _write_world_points(obj, original)
        except Exception:
            pass
        live_preview.abort_isolated(operation, context)
        return {
            "ok": False,
            "message": f"Multi-view surface fitting failed: {type(exc).__name__}: {exc}",
            "object": obj.name,
            "guide_collection": master.name,
        }


def register():
    pass


def unregister():
    pass
