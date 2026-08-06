"""Versioned metric gates for render-to-reference benchmark evaluations.

**This suite measures silhouette conformance, not model quality.** Every gate
here -- IoU, edge distance, centroid offset, error regions, landmarks -- is
derived from the same 2D comparison of a render against a reference
silhouette. Nothing in it inspects topology, so it cannot tell a clean
editable mesh from a dense shell that happens to fill the same outline.

That distinction is not academic. Measured during evaluation: a lumpy voxel
column scored 0.926 while a clean sculptable base mesh of the same subject
scored 0.557, because the column filled the reference hull more completely.
An agent treating the number as an overall verdict discards the useful model
and iterates toward the blob, with measurements to justify it.

The result payload therefore states its own scope. Callers ranking two
candidates **MUST** bring a structural signal of their own; this suite can
disqualify a wrong shape, and cannot say which of two right-enough shapes is
better to work with.
"""

from __future__ import annotations

import math


REFERENCE_BENCHMARK_SCHEMA_VERSION = 1
REFERENCE_BENCHMARK_SUITE_VERSION = "2026.07.1"
PROFILE_ORDER = ("blockout", "refined", "review")

PROFILES = {
    "blockout": {
        "min_silhouette_iou": 0.50,
        "max_mean_edge_distance_ratio": 0.035,
        "max_p95_edge_distance_ratio": 0.080,
        "max_centroid_offset_ratio": 0.060,
        "max_landmark_error_ratio": 0.080,
        "max_error_region_magnitude": 0.350,
        "require_landmarks": False,
    },
    "refined": {
        "min_silhouette_iou": 0.72,
        "max_mean_edge_distance_ratio": 0.020,
        "max_p95_edge_distance_ratio": 0.050,
        "max_centroid_offset_ratio": 0.035,
        "max_landmark_error_ratio": 0.050,
        "max_error_region_magnitude": 0.220,
        "require_landmarks": False,
    },
    "review": {
        "min_silhouette_iou": 0.88,
        "max_mean_edge_distance_ratio": 0.010,
        "max_p95_edge_distance_ratio": 0.025,
        "max_centroid_offset_ratio": 0.020,
        "max_landmark_error_ratio": 0.030,
        "max_error_region_magnitude": 0.100,
        "require_landmarks": False,
    },
}


def list_profiles():
    return [
        {
            "profile": name,
            "suite_version": REFERENCE_BENCHMARK_SUITE_VERSION,
            "thresholds": dict(PROFILES[name]),
        }
        for name in PROFILE_ORDER
    ]


def profile_satisfies(actual_profile, required_profile):
    try:
        return PROFILE_ORDER.index(str(actual_profile)) >= PROFILE_ORDER.index(
            str(required_profile)
        )
    except ValueError:
        return False


def resolved_thresholds(profile, overrides=None):
    profile = str(profile or "refined").strip().lower()
    if profile not in PROFILES:
        raise ValueError(
            f"Unknown reference benchmark profile: {profile}; "
            f"expected one of {', '.join(PROFILE_ORDER)}"
        )
    thresholds = dict(PROFILES[profile])
    overrides = overrides if isinstance(overrides, dict) else {}
    for key in tuple(thresholds):
        if key not in overrides:
            continue
        if key == "require_landmarks":
            if not isinstance(overrides[key], bool):
                raise ValueError("require_landmarks must be boolean")
            thresholds[key] = overrides[key]
            continue
        thresholds[key] = _bounded_ratio(overrides[key], key)
    return thresholds


def evaluate_comparison(
    metrics,
    landmark_errors=None,
    *,
    profile="refined",
    threshold_overrides=None,
):
    """Evaluate comparator metrics against one versioned quality profile."""
    if not isinstance(metrics, dict):
        raise ValueError("metrics must be a comparison metric object")
    width = _positive_number(metrics.get("width"), "metrics.width")
    height = _positive_number(metrics.get("height"), "metrics.height")
    diagonal = math.hypot(width, height)
    threshold_overrides = (
        threshold_overrides
        if isinstance(threshold_overrides, dict)
        else {}
    )
    thresholds = resolved_thresholds(profile, threshold_overrides)
    profile = str(profile or "refined").strip().lower()
    override_keys = sorted(
        key
        for key in threshold_overrides
        if key in thresholds
    )

    iou = _bounded_ratio(
        metrics.get("silhouette_iou"),
        "metrics.silhouette_iou",
    )
    mean_edge_ratio = _metric_ratio(
        metrics,
        normalized_key="mean_edge_distance_normalized",
        pixel_key="mean_edge_distance_pixels",
        diagonal=diagonal,
    )
    p95_edge_ratio = _metric_ratio(
        metrics,
        normalized_key="p95_edge_distance_normalized",
        pixel_key="p95_edge_distance_pixels",
        diagonal=diagonal,
    )
    centroid = metrics.get("centroid_offset")
    if not isinstance(centroid, dict):
        raise ValueError("metrics.centroid_offset must be an object")
    centroid_ratio = math.hypot(
        _finite_number(
            centroid.get("dx_pixels"),
            "metrics.centroid_offset.dx_pixels",
        ),
        _finite_number(
            centroid.get("dy_pixels"),
            "metrics.centroid_offset.dy_pixels",
        ),
    ) / diagonal
    error_regions = (
        metrics.get("error_regions")
        if isinstance(metrics.get("error_regions"), list)
        else []
    )
    largest_region = max(
        (
            _nonnegative_number(
                region.get("magnitude"),
                "metrics.error_regions[].magnitude",
            )
            for region in error_regions
            if isinstance(region, dict)
        ),
        default=0.0,
    )
    landmark_errors = (
        landmark_errors if isinstance(landmark_errors, list) else []
    )
    landmark_ratios = []
    for index, error in enumerate(landmark_errors):
        if not isinstance(error, dict):
            continue
        landmark_ratios.append(
            _nonnegative_number(
                error.get("distance_pixels"),
                f"landmark_errors[{index}].distance_pixels",
            )
            / diagonal
        )
    largest_landmark = max(landmark_ratios, default=0.0)

    gates = [
        _minimum_gate(
            "silhouette_iou",
            iou,
            thresholds["min_silhouette_iou"],
        ),
        _maximum_gate(
            "mean_edge_distance_ratio",
            mean_edge_ratio,
            thresholds["max_mean_edge_distance_ratio"],
        ),
        _maximum_gate(
            "p95_edge_distance_ratio",
            p95_edge_ratio,
            thresholds["max_p95_edge_distance_ratio"],
        ),
        _maximum_gate(
            "centroid_offset_ratio",
            centroid_ratio,
            thresholds["max_centroid_offset_ratio"],
        ),
        _maximum_gate(
            "largest_error_region_magnitude",
            largest_region,
            thresholds["max_error_region_magnitude"],
        ),
    ]
    warnings = []
    if landmark_ratios:
        gates.append(
            _maximum_gate(
                "largest_landmark_error_ratio",
                largest_landmark,
                thresholds["max_landmark_error_ratio"],
            )
        )
    elif thresholds["require_landmarks"]:
        gates.append(
            {
                "gate": "largest_landmark_error_ratio",
                "operator": "<=",
                "actual": None,
                "threshold": thresholds["max_landmark_error_ratio"],
                "passed": False,
                "score": 0.0,
                "reason": "No matched landmark errors were available",
            }
        )
    else:
        warnings.append(
            "No matched landmark targets were supplied; landmark gating was skipped"
        )

    failed = [gate["gate"] for gate in gates if not gate["passed"]]
    quality_score = round(
        100.0 * sum(gate["score"] for gate in gates) / max(1, len(gates)),
        2,
    )
    return {
        "schema_version": REFERENCE_BENCHMARK_SCHEMA_VERSION,
        "suite_version": REFERENCE_BENCHMARK_SUITE_VERSION,
        "profile": profile,
        "passed": not failed,
        "status": "passed" if not failed else "failed",
        # Named for what it measures. "quality_score" is kept for callers that
        # already read it, but the name invited exactly the misreading this
        # payload now heads off.
        "silhouette_conformance_score": quality_score,
        "quality_score": quality_score,
        "verdict_scope": "silhouette_conformance_only",
        "is_overall_quality_verdict": False,
        "not_measured": [
            "topology (component count, manifoldness, watertightness)",
            "whether the mesh is editable, riggable, or sensibly distributed",
            "polygon budget and face-area distribution",
            "anything not visible in a 2D silhouette",
        ],
        "interpretation": (
            "Silhouette conformance only. Use it to disqualify a shape that does not match "
            "the reference, never to rank two candidates: a dense shell that fills the "
            "reference hull scores higher than a clean editable mesh of the same subject "
            "(measured: 0.926 against 0.557). To choose between candidates, or to drive a "
            "repair loop, bring a structural measurement as well."
        ),
        "gate_count": len(gates),
        "passed_gate_count": len(gates) - len(failed),
        "failed_gates": failed,
        "gates": gates,
        "thresholds": thresholds,
        "threshold_overrides_applied": bool(override_keys),
        "threshold_override_keys": override_keys,
        "actuals": {
            "silhouette_iou": iou,
            "mean_edge_distance_ratio": mean_edge_ratio,
            "p95_edge_distance_ratio": p95_edge_ratio,
            "centroid_offset_ratio": centroid_ratio,
            "largest_error_region_magnitude": largest_region,
            "largest_landmark_error_ratio": (
                largest_landmark if landmark_ratios else None
            ),
            "matched_landmark_count": len(landmark_ratios),
        },
        "warnings": warnings,
    }


def _minimum_gate(name, actual, threshold):
    passed = actual >= threshold
    score = 1.0 if passed else actual / max(threshold, 1.0e-12)
    return {
        "gate": name,
        "operator": ">=",
        "actual": round(actual, 8),
        "threshold": threshold,
        "passed": passed,
        "score": round(max(0.0, min(1.0, score)), 6),
    }


def _maximum_gate(name, actual, threshold):
    passed = actual <= threshold
    if passed:
        score = 1.0
    elif threshold <= 0.0:
        score = 0.0
    else:
        score = threshold / max(actual, 1.0e-12)
    return {
        "gate": name,
        "operator": "<=",
        "actual": round(actual, 8),
        "threshold": threshold,
        "passed": passed,
        "score": round(max(0.0, min(1.0, score)), 6),
    }


def _metric_ratio(metrics, *, normalized_key, pixel_key, diagonal):
    normalized = metrics.get(normalized_key)
    if normalized is not None:
        return _bounded_ratio(normalized, f"metrics.{normalized_key}")
    pixels = _nonnegative_number(
        metrics.get(pixel_key),
        f"metrics.{pixel_key}",
    )
    return pixels / diagonal


def _finite_number(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _positive_number(value, field):
    number = _finite_number(value, field)
    if number <= 0.0:
        raise ValueError(f"{field} must be greater than zero")
    return number


def _nonnegative_number(value, field):
    number = _finite_number(value, field)
    if number < 0.0:
        raise ValueError(f"{field} must not be negative")
    return number


def _bounded_ratio(value, field):
    number = _finite_number(value, field)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{field} must be between 0 and 1")
    return number
