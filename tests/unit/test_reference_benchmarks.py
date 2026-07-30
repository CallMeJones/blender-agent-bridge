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


if __name__ == "__main__":
    unittest.main()
