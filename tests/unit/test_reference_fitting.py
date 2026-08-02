from __future__ import annotations

import os
import sys
import unittest
from unittest import mock


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import depth_fields, reference_fitting  # noqa: E402


POINTS = [
    (-0.5, -0.5, -0.5),
    (0.5, -0.5, -0.5),
    (0.5, 0.5, -0.5),
    (-0.5, 0.5, -0.5),
    (-0.5, -0.5, 0.5),
    (0.5, -0.5, 0.5),
    (0.5, 0.5, 0.5),
    (-0.5, 0.5, 0.5),
]

FACES = [
    (0, 3, 2, 1),
    (4, 5, 6, 7),
    (0, 1, 5, 4),
    (3, 7, 6, 2),
    (0, 4, 7, 3),
    (1, 2, 6, 5),
]


def _view(name, right, forward, outline, depth_layers=None):
    return {
        "name": name,
        "right": right,
        "forward": forward,
        "up": (0.0, 0.0, 1.0),
        "center": (0.0, 0.0, 0.0),
        "plane_height": 2.0,
        "image_aspect": 1.0,
        "outline": outline,
        "depth_layers": depth_layers or [],
    }


class DepthFieldTests(unittest.TestCase):
    def test_grid_sampling_is_bilinear_in_top_left_coordinates(self):
        layer = depth_fields.prepare_depth_layer(
            {
                "mode": "front",
                "width": 2,
                "height": 2,
                "values": [0.0, 1.0, 2.0, 3.0],
            }
        )
        self.assertAlmostEqual(1.5, depth_fields.sample_depth(layer, (0.5, 0.5)))

    def test_sparse_samples_only_constrain_their_radius(self):
        layer = depth_fields.prepare_depth_layer(
            {
                "mode": "front",
                "samples": [{"point": [0.25, 0.5], "depth": -0.4, "radius": 0.1}],
            }
        )
        self.assertEqual(-0.4, depth_fields.sample_depth(layer, (0.25, 0.5)))
        self.assertIsNone(depth_fields.sample_depth(layer, (0.75, 0.5)))

    def test_sparse_samples_use_a_bounded_spatial_index(self):
        samples = [
            {
                "point": [(x + 0.5) / 64.0, (y + 0.5) / 64.0],
                "depth": float(y * 64 + x),
                "radius": 0.001,
            }
            for y in range(64)
            for x in range(64)
        ]
        layer = depth_fields.prepare_depth_layer({"samples": samples})
        self.assertEqual(1, layer["maximum_query_samples"])
        self.assertEqual(4096, layer["bucket_reference_count"])
        self.assertEqual(
            32.0 * 64.0 + 32.0,
            depth_fields.sample_depth(layer, ((32.5 / 64.0), (32.5 / 64.0))),
        )

    def test_pathological_sparse_overlap_is_rejected(self):
        with self.assertRaisesRegex(depth_fields.DepthFieldError, "overlap too densely"):
            depth_fields.prepare_depth_layer(
                {
                    "samples": [
                        {"point": [0.5, 0.5], "depth": 0.0, "radius": 2.0}
                        for _index in range(
                            depth_fields.MAX_SPARSE_SAMPLES_PER_BUCKET + 1
                        )
                    ]
                }
            )

    def test_duplicate_front_layers_are_rejected(self):
        with self.assertRaisesRegex(depth_fields.DepthFieldError, "at most one front"):
            depth_fields.prepare_depth_layers(
                [
                    {"mode": "front", "width": 1, "height": 1, "values": [0.0]},
                    {"mode": "front", "width": 1, "height": 1, "values": [0.1]},
                ]
            )


class ReferenceFittingTests(unittest.TestCase):
    def test_joint_front_side_fit_improves_every_view(self):
        target = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]
        views = [
            _view("front", (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), target),
            _view("side", (0.0, -1.0, 0.0), (-1.0, 0.0, 0.0), target),
        ]
        result = reference_fitting.fit_surface_to_references(
            POINTS,
            FACES,
            views,
            iterations=4,
            step_candidates=[0.5, 1.0],
            feature_preservation=0.0,
            propagation_steps=1,
            per_view_regression_tolerance=0.000001,
        )
        self.assertTrue(result["changed"], result)
        self.assertLess(result["final"]["objective"], result["baseline"]["objective"])
        before = {item["name"]: item for item in result["baseline"]["per_view"]}
        after = {item["name"]: item for item in result["final"]["per_view"]}
        for name in before:
            self.assertLessEqual(
                after[name]["combined_error"],
                before[name]["combined_error"] + 0.000001,
            )

    def test_landmark_binding_is_stable_and_bounded(self):
        outline = [(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)]
        views = [
            _view("front", (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), outline),
            _view("side", (0.0, -1.0, 0.0), (-1.0, 0.0, 0.0), outline),
        ]
        result = reference_fitting.fit_surface_to_references(
            POINTS,
            FACES,
            views,
            landmarks=[{"name": "probe", "target": [-0.55, -0.55, -0.55]}],
            iterations=2,
            step_candidates=[0.5],
            landmark_weight=2.0,
            feature_preservation=0.0,
            maximum_total_displacement=0.2,
            per_view_regression_tolerance=0.05,
        )
        self.assertEqual(0, result["landmark_bindings"][0]["vertex_index"])
        self.assertLessEqual(result["deformation"]["maximum_displacement"], 0.2 + 1e-9)

    def test_invalid_step_candidates_fail_loudly(self):
        outline = [(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)]
        with self.assertRaisesRegex(reference_fitting.ReferenceFitError, "step_candidates"):
            reference_fitting.fit_surface_to_references(
                POINTS,
                FACES,
                [
                    _view("front", (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), outline),
                    _view("side", (0.0, -1.0, 0.0), (-1.0, 0.0, 0.0), outline),
                ],
                step_candidates=[0.0],
            )

    def test_depth_workload_limit_fails_before_fitting(self):
        outline = [(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)]
        layer = depth_fields.prepare_depth_layer(
            {
                "mode": "front",
                "samples": [
                    {"point": [0.5, 0.5], "depth": -0.5, "radius": 0.25}
                ],
            }
        )
        views = [
            _view("front", (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), outline, [layer]),
            _view("side", (0.0, -1.0, 0.0), (-1.0, 0.0, 0.0), outline),
        ]
        with mock.patch.object(
            reference_fitting,
            "MAX_FIT_DEPTH_SAMPLE_EVALUATIONS",
            1,
        ):
            with self.assertRaisesRegex(
                reference_fitting.ReferenceFitError,
                "depth workload",
            ):
                reference_fitting.fit_surface_to_references(
                    POINTS,
                    FACES,
                    views,
                    iterations=1,
                    step_candidates=[0.5],
                )

    def test_surface_integrity_detects_collapsed_and_inverted_faces(self):
        collapsed = list(POINTS)
        for index in FACES[0]:
            collapsed[index] = (0.0, 0.0, -0.5)
        collapse = reference_fitting.measure_surface_integrity(
            collapsed,
            FACES,
            reference_points=POINTS,
        )
        self.assertFalse(collapse["ok"])
        self.assertGreater(collapse["degenerate_face_count"], 0)

        inverted = list(POINTS)
        inverted[1], inverted[3] = inverted[3], inverted[1]
        inversion = reference_fitting.measure_surface_integrity(
            inverted,
            FACES,
            reference_points=POINTS,
        )
        self.assertFalse(inversion["ok"])
        self.assertGreater(inversion["inverted_face_count"], 0)


if __name__ == "__main__":
    unittest.main()
