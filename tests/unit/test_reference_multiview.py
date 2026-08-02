from __future__ import annotations

import math
import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import reference_multiview  # noqa: E402


class ReferenceMultiViewTests(unittest.TestCase):
    def test_axis_bases_are_orthonormal_and_custom_basis_is_corrected(self):
        for axis in ("FRONT", "BACK", "LEFT", "RIGHT", "TOP", "BOTTOM"):
            right, forward, up = reference_multiview.view_basis(axis)
            self.assertAlmostEqual(math.dist((0, 0, 0), right), 1.0)
            self.assertAlmostEqual(math.dist((0, 0, 0), forward), 1.0)
            self.assertAlmostEqual(math.dist((0, 0, 0), up), 1.0)
            self.assertAlmostEqual(sum(a * b for a, b in zip(right, forward)), 0.0)
            self.assertAlmostEqual(sum(a * b for a, b in zip(right, up)), 0.0)
            self.assertAlmostEqual(sum(a * b for a, b in zip(forward, up)), 0.0)
            self.assertEqual(
                tuple(
                    round(value, 7)
                    for value in (
                        forward[1] * up[2] - forward[2] * up[1],
                        forward[2] * up[0] - forward[0] * up[2],
                        forward[0] * up[1] - forward[1] * up[0],
                    )
                ),
                right,
            )
        right, forward, up = reference_multiview.view_basis(
            "CUSTOM",
            view_direction=(0.0, 2.0, 0.0),
            up_direction=(0.0, 0.2, 1.0),
        )
        self.assertEqual(forward, (0.0, 1.0, 0.0))
        self.assertAlmostEqual(sum(a * b for a, b in zip(forward, up)), 0.0)
        self.assertEqual(right, (1.0, 0.0, 0.0))

    def test_image_point_maps_top_left_coordinates_into_world_ray(self):
        ray = reference_multiview.image_point_to_ray(
            (0.75, 0.25),
            image_aspect=2.0,
            plane_height=4.0,
            center=(0.0, 0.0, 1.0),
            basis=reference_multiview.view_basis("FRONT"),
        )
        self.assertEqual(ray["origin"], (2.0, 0.0, 2.0))
        self.assertEqual(ray["direction"], (0.0, 1.0, 0.0))

    def test_orthogonal_rays_reconstruct_exact_point(self):
        point = (0.7, -0.4, 1.2)
        result = reference_multiview.triangulate_rays(
            [
                {
                    "origin": (point[0], 0.0, point[2]),
                    "direction": (0.0, 1.0, 0.0),
                    "view": "front",
                },
                {
                    "origin": (0.0, point[1], point[2]),
                    "direction": (1.0, 0.0, 0.0),
                    "view": "left",
                },
            ]
        )
        for actual, expected in zip(result["point"], point):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(result["rms_residual"], 0.0)
        self.assertEqual(result["views"], ["front", "left"])

    def test_inconsistent_rays_report_residual(self):
        result = reference_multiview.triangulate_rays(
            [
                {
                    "origin": (1.0, 0.0, 2.0),
                    "direction": (0.0, 1.0, 0.0),
                },
                {
                    "origin": (0.0, 3.0, 2.4),
                    "direction": (1.0, 0.0, 0.0),
                },
            ]
        )
        self.assertGreater(result["rms_residual"], 0.15)
        self.assertLess(result["rms_residual"], 0.25)

    def test_parallel_or_incomplete_rays_fail_loudly(self):
        with self.assertRaisesRegex(
            reference_multiview.MultiViewCalibrationError,
            "at least two",
        ):
            reference_multiview.triangulate_rays(
                [{"origin": (0, 0, 0), "direction": (0, 1, 0)}]
            )
        with self.assertRaisesRegex(
            reference_multiview.MultiViewCalibrationError,
            "too parallel",
        ):
            reference_multiview.triangulate_rays(
                [
                    {"origin": (0, 0, 0), "direction": (0, 1, 0)},
                    {"origin": (1, 0, 0), "direction": (0, -1, 0)},
                ]
            )


if __name__ == "__main__":
    unittest.main()
