"""Live Blender adapter for render-to-reference benchmark evaluation."""

from __future__ import annotations

from . import (
    advanced_modeling,
    quality_benchmarks,
    reference_benchmarks,
    reference_comparison,
    reference_scene,
)


def _structural_metrics(inspection):
    objects = [item for item in inspection.get("objects") or [] if isinstance(item, dict)]
    totals = {
        "object_count": len(objects),
        "vertices": 0,
        "faces": 0,
        "loose_vertices": 0,
        "loose_edges": 0,
        "non_manifold_edges": 0,
        "unassigned_polygons": 0,
        "inspection_issue_count": int(inspection.get("issue_count") or 0),
        "boundary_edges": 0,
    }
    for item in objects:
        topology = item.get("topology") if isinstance(item.get("topology"), dict) else {}
        materials = item.get("materials") if isinstance(item.get("materials"), dict) else {}
        for key in ("vertices", "faces", "loose_vertices", "loose_edges", "non_manifold_edges", "boundary_edges"):
            totals[key] += int(topology.get(key) or 0)
        totals["unassigned_polygons"] += int(materials.get("unassigned_polygons") or 0)
    return {
        **totals,
        "source": "inspect_modeling_quality",
        "details": objects,
    }


def evaluate_reference_model_benchmark(
    context,
    *,
    profile="refined",
    threshold_overrides=None,
    run_id="",
    collection_name="",
    camera_name="",
    object_names=None,
    selected_only=False,
    outline_name="",
    reference_mask_source="auto",
    landmark_targets=None,
    max_axis=1024,
    mask_threshold=0.05,
    capture_dir=None,
    include_structure=False,
    structural_max_faces=0,
    structural_require_materials=False,
    structural_weight=0.25,
):
    """Render, compare, gate, and optionally record one benchmark evaluation."""
    run_id = str(run_id or "").strip()
    target = {}
    if run_id:
        target = quality_benchmarks.validate_reference_evaluation_target(
            run_id
        )
        if not target.get("ok"):
            return target
        collection, error = reference_scene.guide_collection(collection_name)
        if error:
            return {"ok": False, "message": error}
        camera, error = reference_scene.comparison_camera(
            collection,
            camera_name,
        )
        if error:
            return {"ok": False, "message": error}
        identity_result = quality_benchmarks.validate_reference_identity(
            target["run"],
            reference_scene.reference_identity(collection, camera),
        )
        if not identity_result.get("ok"):
            return identity_result
    try:
        reference_benchmarks.resolved_thresholds(
            profile,
            threshold_overrides,
        )
    except ValueError as exc:
        return {
            "ok": False,
            "code": "invalid_reference_benchmark_profile",
            "message": str(exc),
        }
    comparison = reference_comparison.compare_model_to_reference(
        context,
        collection_name=collection_name,
        camera_name=camera_name,
        object_names=object_names,
        selected_only=selected_only,
        outline_name=outline_name,
        reference_mask_source=reference_mask_source,
        landmark_targets=landmark_targets,
        max_axis=max_axis,
        mask_threshold=mask_threshold,
        capture_dir=capture_dir,
    )
    if not comparison.get("ok"):
        return comparison
    if run_id:
        identity_result = quality_benchmarks.validate_reference_identity(
            target["run"],
            comparison.get("reference_identity"),
        )
        if not identity_result.get("ok"):
            return identity_result
    structural_metrics = None
    structural_inspection = {}
    if include_structure:
        structural_inspection = advanced_modeling.inspect_modeling_quality(
            context,
            object_names=object_names or [],
            selected_only=selected_only,
            include_children=True,
            require_materials=structural_require_materials,
            max_objects=64,
        )
        if not structural_inspection.get("ok"):
            return {
                "ok": False,
                "code": "invalid_structural_benchmark_target",
                "message": structural_inspection.get("message") or "Structural inspection failed",
                "structural_inspection": structural_inspection,
            }
        structural_metrics = _structural_metrics(structural_inspection)
    try:
        evaluation = reference_benchmarks.evaluate_comparison(
            comparison["metrics"],
            comparison.get("landmark_errors"),
            profile=profile,
            threshold_overrides=threshold_overrides,
            structural_metrics=structural_metrics,
            structural_max_faces=structural_max_faces,
            structural_require_materials=structural_require_materials,
            structural_weight=structural_weight,
        )
    except ValueError as exc:
        return {
            "ok": False,
            "code": "invalid_reference_benchmark_metrics",
            "message": str(exc),
            "comparison_id": comparison.get("comparison_id", ""),
            "metadata_uri": comparison.get("metadata_uri", ""),
        }

    recording = {}
    if run_id:
        recording = quality_benchmarks.record_reference_evaluation(
            run_id,
            evaluation=evaluation,
            comparison_id=comparison.get("comparison_id", ""),
            metadata_uri=comparison.get("metadata_uri", ""),
            reference_identity=comparison.get("reference_identity"),
        )
        if not recording.get("ok"):
            return {
                "ok": False,
                "code": recording.get(
                    "code",
                    "reference_benchmark_record_failed",
                ),
                "message": recording.get(
                    "message",
                    "Reference benchmark evaluation could not be recorded",
                ),
                "evaluation": evaluation,
                "comparison_id": comparison.get("comparison_id", ""),
                "metadata_uri": comparison.get("metadata_uri", ""),
            }

    return {
        "ok": True,
        "message": (
            f"Reference benchmark {evaluation['profile']} profile passed"
            if evaluation["passed"]
            else (
                f"Reference benchmark {evaluation['profile']} profile failed "
                f"{len(evaluation['failed_gates'])} gate(s)"
            )
        ),
        "passed": evaluation["passed"],
        "profile": evaluation["profile"],
        "evaluation": evaluation,
        "run_id": run_id,
        "recording": recording,
        "comparison_id": comparison["comparison_id"],
        "metadata_uri": comparison["metadata_uri"],
        "images": comparison["images"],
        "guide_collection": comparison["guide_collection"],
        "camera": comparison["camera"],
        "reference_identity": comparison.get("reference_identity", {}),
        "object_names": comparison["object_names"],
        "metrics": comparison["metrics"],
        "landmark_errors": comparison["landmark_errors"],
        "repair_priorities": comparison["repair_priorities"],
        "structural_inspection": structural_inspection,
    }


def register():
    pass


def unregister():
    pass
