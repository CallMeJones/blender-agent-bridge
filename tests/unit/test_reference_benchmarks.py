from __future__ import annotations

import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import reference_benchmarks, reference_metrics  # noqa: E402


def _comparison(reference_polygon, model_polygon, *, width=240, height=180):
    reference = reference_metrics.rasterize_polygon(
        reference_polygon,
        width,
        height,
    )
    model = reference_metrics.rasterize_polygon(
        model_polygon,
        width,
        height,
    )
    return reference_metrics.compare_masks(reference, model, width, height)


class ReferenceBenchmarkTests(unittest.TestCase):
    def test_identical_silhouette_passes_review_profile(self):
        polygon = [(0.2, 0.15), (0.8, 0.15), (0.8, 0.85), (0.2, 0.85)]
        metrics = _comparison(polygon, polygon)
        evaluation = reference_benchmarks.evaluate_comparison(
            metrics,
            [
                {
                    "name": "center",
                    "distance_pixels": 0.0,
                }
            ],
            profile="review",
        )
        self.assertTrue(evaluation["passed"])
        self.assertEqual(100.0, evaluation["quality_score"])
        self.assertEqual([], evaluation["failed_gates"])
        self.assertFalse(evaluation["threshold_overrides_applied"])

    def test_shifted_silhouette_fails_refined_profile_with_named_gates(self):
        reference = [(0.2, 0.15), (0.7, 0.15), (0.7, 0.85), (0.2, 0.85)]
        shifted = [(0.32, 0.15), (0.82, 0.15), (0.82, 0.85), (0.32, 0.85)]
        evaluation = reference_benchmarks.evaluate_comparison(
            _comparison(reference, shifted),
            profile="refined",
        )
        self.assertFalse(evaluation["passed"])
        self.assertFalse(evaluation["threshold_overrides_applied"])
        self.assertIn("silhouette_iou", evaluation["failed_gates"])
        self.assertIn("centroid_offset_ratio", evaluation["failed_gates"])
        self.assertTrue(evaluation["warnings"])

    def test_threshold_overrides_are_bounded_and_can_require_landmarks(self):
        polygon = [(0.2, 0.15), (0.8, 0.15), (0.8, 0.85), (0.2, 0.85)]
        evaluation = reference_benchmarks.evaluate_comparison(
            _comparison(polygon, polygon),
            profile="blockout",
            threshold_overrides={"require_landmarks": True},
        )
        self.assertFalse(evaluation["passed"])
        self.assertTrue(evaluation["threshold_overrides_applied"])
        self.assertEqual(
            ["require_landmarks"],
            evaluation["threshold_override_keys"],
        )
        self.assertIn(
            "largest_landmark_error_ratio",
            evaluation["failed_gates"],
        )
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            reference_benchmarks.resolved_thresholds(
                "review",
                {"min_silhouette_iou": 1.1},
            )
        with self.assertRaisesRegex(ValueError, "must be boolean"):
            reference_benchmarks.resolved_thresholds(
                "review",
                {"require_landmarks": "false"},
            )

    def test_negative_pixel_distances_are_rejected(self):
        polygon = [(0.2, 0.15), (0.8, 0.15), (0.8, 0.85), (0.2, 0.85)]
        metrics = _comparison(polygon, polygon)
        metrics.pop("mean_edge_distance_normalized")
        metrics["mean_edge_distance_pixels"] = -1.0
        with self.assertRaisesRegex(ValueError, "must not be negative"):
            reference_benchmarks.evaluate_comparison(metrics)

        with self.assertRaisesRegex(ValueError, "must not be negative"):
            reference_benchmarks.evaluate_comparison(
                _comparison(polygon, polygon),
                [{"name": "center", "distance_pixels": -1.0}],
            )

    def test_stricter_profiles_satisfy_looser_run_requirements(self):
        self.assertTrue(
            reference_benchmarks.profile_satisfies("review", "refined")
        )
        self.assertFalse(
            reference_benchmarks.profile_satisfies("blockout", "refined")
        )
        self.assertFalse(
            reference_benchmarks.profile_satisfies("unknown", "refined")
        )

    def test_optional_structure_blocks_a_broken_mesh_with_a_perfect_outline(self):
        polygon = [(0.2, 0.15), (0.8, 0.15), (0.8, 0.85), (0.2, 0.85)]
        evaluation = reference_benchmarks.evaluate_comparison(
            _comparison(polygon, polygon),
            profile="review",
            structural_metrics={
                "object_count": 1,
                "vertices": 100,
                "faces": 200,
                "loose_vertices": 0,
                "loose_edges": 0,
                "non_manifold_edges": 3,
                "inspection_issue_count": 1,
            },
        )
        self.assertEqual(100.0, evaluation["silhouette_conformance_score"])
        self.assertFalse(evaluation["passed"])
        self.assertEqual("silhouette_and_structure", evaluation["verdict_scope"])
        self.assertIn("structure.non_manifold_edges", evaluation["failed_gates"])
        self.assertFalse(evaluation["structural_evaluation"]["passed"])

    def test_optional_structure_can_enforce_a_face_budget(self):
        structural = reference_benchmarks.evaluate_structure(
            {
                "object_count": 1,
                "vertices": 1000,
                "faces": 2500,
                "loose_vertices": 0,
                "loose_edges": 0,
                "non_manifold_edges": 0,
                "inspection_issue_count": 0,
            },
            max_faces=2000,
        )
        self.assertFalse(structural["passed"])
        self.assertIn("face_budget", structural["failed_gates"])


if __name__ == "__main__":
    unittest.main()


def _conformance_metrics(iou, mean_edge, p95_edge):
    return {
        "width": 512,
        "height": 512,
        "reference_pixels": 1000,
        "model_pixels": 1000,
        "intersection_pixels": int(1000 * iou),
        "union_pixels": 1000,
        "silhouette_iou": iou,
        "mean_edge_distance_normalized": mean_edge,
        "p95_edge_distance_normalized": p95_edge,
        "centroid_offset": {"dx_pixels": 1, "dy_pixels": 1},
        "error_regions": [],
    }


class ConformanceDiagnosisTests(unittest.TestCase):
    """A wrong shape and a right shape in a different pose are not the same."""

    def _diagnose(self, iou, mean_edge, p95_edge, profile="refined"):
        result = reference_benchmarks.evaluate_comparison(
            _conformance_metrics(iou, mean_edge, p95_edge), profile=profile
        )
        return result["conformance_diagnosis"]

    def test_the_measured_a_pose_case_reads_as_area_not_drift(self):
        # The real numbers: a character authored in an A-pose against a
        # reference with clasped hands. The model was correct; the gate failed.
        diagnosis = self._diagnose(0.666, 0.014, 0.030)
        self.assertEqual("area_difference", diagnosis["kind"])
        self.assertIn("pose", diagnosis["summary"])
        self.assertIn("should not be chased", diagnosis["summary"])

    def test_a_wandering_contour_reads_as_shape_drift(self):
        diagnosis = self._diagnose(0.60, 0.070, 0.140)
        self.assertEqual("shape_drift", diagnosis["kind"])
        self.assertIn("shape", diagnosis["summary"])

    def test_a_passing_model_is_reported_as_conformant(self):
        self.assertEqual("conformant", self._diagnose(0.90, 0.010, 0.020)["kind"])

    def test_a_close_contour_with_failing_area_is_never_called_drift(self):
        # The distinction has to hold across the range, not at one point.
        for iou in (0.40, 0.55, 0.66, 0.71):
            self.assertEqual(
                "area_difference",
                self._diagnose(iou, 0.012, 0.024)["kind"],
                iou,
            )

    def test_the_diagnosis_travels_with_the_scope_statement(self):
        result = reference_benchmarks.evaluate_comparison(
            _conformance_metrics(0.666, 0.014, 0.030), profile="refined"
        )
        self.assertFalse(result["is_overall_quality_verdict"])
        self.assertEqual("silhouette_conformance_only", result["verdict_scope"])
        self.assertTrue(result["conformance_diagnosis"]["summary"])
