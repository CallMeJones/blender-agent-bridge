from __future__ import annotations

import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import reference_metrics  # noqa: E402


class ReferenceMetricTests(unittest.TestCase):
    def test_identical_polygon_masks_score_perfectly(self):
        mask = reference_metrics.rasterize_polygon(
            [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)],
            100,
            80,
        )
        result = reference_metrics.compare_masks(mask, mask, 100, 80)
        self.assertEqual(result["silhouette_iou"], 1.0)
        self.assertEqual(result["silhouette_dice"], 1.0)
        self.assertEqual(result["mean_edge_distance_pixels"], 0.0)
        self.assertEqual(result["error_regions"], [])

    def test_shifted_mask_reports_offset_and_regional_errors(self):
        reference = reference_metrics.rasterize_polygon(
            [(0.2, 0.2), (0.6, 0.2), (0.6, 0.8), (0.2, 0.8)],
            120,
            90,
        )
        model = reference_metrics.rasterize_polygon(
            [(0.3, 0.2), (0.7, 0.2), (0.7, 0.8), (0.3, 0.8)],
            120,
            90,
        )
        result = reference_metrics.compare_masks(
            reference, model, 120, 90
        )
        self.assertLess(result["silhouette_iou"], 1.0)
        self.assertGreater(
            result["centroid_offset"]["dx_pixels"], 10.0
        )
        self.assertTrue(result["error_regions"])
        self.assertTrue(
            any(
                item["problem"] == "model_missing"
                for item in result["error_regions"]
            )
        )
        self.assertTrue(
            any(
                item["problem"] == "model_excess"
                for item in result["error_regions"]
            )
        )

    def test_landmarks_return_target_to_reference_corrections(self):
        errors = reference_metrics.compare_landmarks(
            {"eye": [0.25, 0.4]},
            {"eye": [0.35, 0.3]},
            1000,
            500,
        )
        self.assertEqual(errors[0]["dx_pixels"], 100.0)
        self.assertEqual(errors[0]["dy_pixels"], -50.0)
        self.assertEqual(errors[0]["correction_normalized"], [-0.1, 0.1])

    def test_invalid_or_empty_masks_fail_loudly(self):
        with self.assertRaisesRegex(ValueError, "at least three"):
            reference_metrics.rasterize_polygon([], 10, 10)
        with self.assertRaisesRegex(ValueError, "Reference mask"):
            reference_metrics.compare_masks(
                bytearray(100),
                bytearray([1] * 100),
                10,
                10,
            )
        with self.assertRaisesRegex(ValueError, "expected 100"):
            reference_metrics.compare_masks(
                bytearray(99),
                bytearray(100),
                10,
                10,
            )


if __name__ == "__main__":
    unittest.main()
