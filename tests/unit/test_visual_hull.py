from __future__ import annotations

import os
import sys
import unittest
import math
from unittest import mock


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import sculpt_fields, visual_hull  # noqa: E402


def _view(name, right, forward, up, outline):
    return {
        "name": name,
        "right": right,
        "forward": forward,
        "up": up,
        "center": (0.0, 0.0, 0.0),
        "plane_height": 2.0,
        "image_aspect": 1.0,
        "outline": outline,
    }


class VisualHullTests(unittest.TestCase):
    def test_projection_uses_calibrated_orthographic_basis(self):
        view = _view(
            "front",
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)],
        )
        self.assertEqual((0.75, 0.25), visual_hull.project_point((0.5, 9.0, 0.5), view))

    def test_perpendicular_square_silhouettes_create_closed_hull(self):
        square = [(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)]
        result = visual_hull.carve_visual_hull(
            [
                _view(
                    "front",
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                    (0.0, 0.0, 1.0),
                    square,
                ),
                _view(
                    "side",
                    (0.0, -1.0, 0.0),
                    (-1.0, 0.0, 0.0),
                    (0.0, 0.0, 1.0),
                    square,
                ),
            ],
            bounds_center=(0.0, 0.0, 0.0),
            bounds_size=(2.0, 2.0, 2.0),
            resolution=16,
            smooth_iterations=0,
        )
        self.assertGreater(result["stats"]["occupied_voxels"], 0)
        self.assertGreater(result["stats"]["face_count"], 0)
        self.assertTrue(
            sculpt_fields.is_closed_surface(result["faces"]),
            result["stats"],
        )

    def test_parallel_views_are_rejected(self):
        square = [(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)]
        front = _view(
            "front",
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            square,
        )
        back = _view(
            "back",
            (-1.0, 0.0, 0.0),
            (0.0, -1.0, 0.0),
            (0.0, 0.0, 1.0),
            square,
        )
        with self.assertRaisesRegex(visual_hull.VisualHullError, "too parallel"):
            visual_hull.carve_visual_hull(
                [front, back],
                bounds_center=(0.0, 0.0, 0.0),
                bounds_size=(2.0, 2.0, 2.0),
                resolution=16,
            )

    def test_largest_component_still_honors_minimum_voxels(self):
        square = [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)]
        with self.assertRaisesRegex(visual_hull.VisualHullError, "component"):
            visual_hull.carve_visual_hull(
                [
                    _view(
                        "front",
                        (1.0, 0.0, 0.0),
                        (0.0, 1.0, 0.0),
                        (0.0, 0.0, 1.0),
                        square,
                    ),
                    _view(
                        "side",
                        (0.0, -1.0, 0.0),
                        (-1.0, 0.0, 0.0),
                        (0.0, 0.0, 1.0),
                        square,
                    ),
                ],
                bounds_center=(0.0, 0.0, 0.0),
                bounds_size=(2.0, 2.0, 2.0),
                resolution=16,
                minimum_component_voxels=1000,
            )

    def test_grid_workload_is_bounded(self):
        square = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        result = visual_hull.carve_visual_hull(
            [
                _view(
                    "front",
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                    (0.0, 0.0, 1.0),
                    square,
                ),
                _view(
                    "side",
                    (0.0, -1.0, 0.0),
                    (-1.0, 0.0, 0.0),
                    (0.0, 0.0, 1.0),
                    square,
                ),
            ],
            bounds_center=(0.0, 0.0, 0.0),
            bounds_size=(2.0, 1.0, 0.5),
            resolution=80,
            smooth_iterations=0,
        )
        self.assertLessEqual(
            result["stats"]["grid_cell_count"],
            visual_hull.MAX_GRID_CELLS,
        )

    def test_outline_edge_workload_is_bounded(self):
        dense = [
            (
                0.5 + 0.4 * math.cos(math.tau * index / 512),
                0.5 + 0.4 * math.sin(math.tau * index / 512),
            )
            for index in range(512)
        ]
        with self.assertRaisesRegex(visual_hull.VisualHullError, "edge evaluations"):
            visual_hull.carve_visual_hull(
                [
                    _view(
                        "front",
                        (1.0, 0.0, 0.0),
                        (0.0, 1.0, 0.0),
                        (0.0, 0.0, 1.0),
                        dense,
                    ),
                    _view(
                        "side",
                        (0.0, -1.0, 0.0),
                        (-1.0, 0.0, 0.0),
                        (0.0, 0.0, 1.0),
                        dense,
                    ),
                ],
                bounds_center=(0.0, 0.0, 0.0),
                bounds_size=(2.0, 2.0, 2.0),
                resolution=80,
            )

    def test_front_depth_layer_trims_visual_hull_occupancy(self):
        square = [(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)]
        front = _view(
            "front",
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            square,
        )
        side = _view(
            "side",
            (0.0, -1.0, 0.0),
            (-1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0),
            square,
        )
        baseline = visual_hull.carve_visual_hull(
            [front, side],
            bounds_center=(0.0, 0.0, 0.0),
            bounds_size=(2.0, 2.0, 2.0),
            resolution=16,
            smooth_iterations=0,
        )
        front["depth_layers"] = [
            {
                "mode": "front",
                "width": 1,
                "height": 1,
                "values": [0.0],
            }
        ]
        constrained = visual_hull.carve_visual_hull(
            [front, side],
            bounds_center=(0.0, 0.0, 0.0),
            bounds_size=(2.0, 2.0, 2.0),
            resolution=16,
            smooth_iterations=0,
        )
        self.assertLess(
            constrained["stats"]["occupied_voxels"],
            baseline["stats"]["occupied_voxels"],
        )
        self.assertEqual(1, constrained["stats"]["depth_layer_count"])
        self.assertGreater(constrained["stats"]["depth_evaluations"], 0)
        self.assertEqual(
            1,
            len(constrained["stats"]["depth_layer_evaluations"]),
        )
        self.assertGreater(
            constrained["stats"]["depth_layer_evaluations"][0]["evaluation_count"],
            0,
        )

    def test_depth_workload_limit_is_checked_before_carving(self):
        square = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]
        front = _view(
            "front",
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            square,
        )
        front["depth_layers"] = [
            {
                "mode": "front",
                "samples": [
                    {"point": [0.5, 0.5], "depth": 0.0, "radius": 0.2}
                ],
            }
        ]
        side = _view(
            "side",
            (0.0, -1.0, 0.0),
            (-1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0),
            square,
        )
        with mock.patch.object(visual_hull, "MAX_DEPTH_SAMPLE_EVALUATIONS", 1):
            with self.assertRaisesRegex(visual_hull.VisualHullError, "depth workload"):
                visual_hull.carve_visual_hull(
                    [front, side],
                    bounds_center=(0.0, 0.0, 0.0),
                    bounds_size=(2.0, 2.0, 2.0),
                    resolution=8,
                )


if __name__ == "__main__":
    unittest.main()
