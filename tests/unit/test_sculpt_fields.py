from __future__ import annotations

import math
import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import bridge_protocol, sculpt_fields, tool_registry  # noqa: E402


class SculptFieldTests(unittest.TestCase):
    def test_screen_controls_require_normalized_finite_coordinates(self):
        spec = tool_registry.REGISTRY.get("apply_screen_space_sculpt")
        valid = {
            "object_name": "Subject",
            "controls": [{"source": [0.5, 0.5], "target": [0.75, 0.5]}],
        }
        self.assertEqual(
            [],
            bridge_protocol.validate_arguments(valid, dict(spec.input_schema)),
        )
        outside = {
            **valid,
            "controls": [{"source": [0.5, 0.5], "target": [1.01, 0.5]}],
        }
        self.assertTrue(
            bridge_protocol.validate_arguments(outside, dict(spec.input_schema))
        )
        non_finite = {
            **valid,
            "controls": [
                {"source": [0.5, 0.5], "target": [float("nan"), 0.5]}
            ],
        }
        self.assertTrue(
            bridge_protocol.validate_arguments(non_finite, dict(spec.input_schema))
        )

    def test_spatial_selectors_create_bounded_soft_weights(self):
        points = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.25, 0.0, 0.0), (2.0, 0.0, 0.0)]
        sphere = sculpt_fields.sphere_weights(
            points,
            center=(0.0, 0.0, 0.0),
            radius=1.0,
            feather=0.5,
        )
        self.assertEqual([1.0, 1.0], sphere[:2])
        self.assertGreater(sphere[2], 0.0)
        self.assertLess(sphere[2], 1.0)
        self.assertEqual(0.0, sphere[3])

        box = sculpt_fields.box_weights(
            points,
            minimum=(-0.5, -0.5, -0.5),
            maximum=(0.5, 0.5, 0.5),
            feather=1.0,
        )
        self.assertEqual(1.0, box[0])
        self.assertGreater(box[1], 0.0)
        self.assertEqual(0.0, box[3])

    def test_screen_polygon_feathers_nearby_points(self):
        weights = sculpt_fields.polygon_weights(
            [(0.5, 0.5), (1.05, 0.5), (1.4, 0.5)],
            polygon=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
            feather=0.2,
        )
        self.assertEqual(1.0, weights[0])
        self.assertGreater(weights[1], 0.0)
        self.assertLess(weights[1], 1.0)
        self.assertEqual(0.0, weights[2])

    def test_polygon_evaluation_count_matches_edge_passes(self):
        self.assertEqual(
            400,
            sculpt_fields.polygon_evaluation_count(
                100,
                edge_count=4,
            ),
        )
        self.assertEqual(
            800,
            sculpt_fields.polygon_evaluation_count(
                100,
                edge_count=4,
                feather=0.1,
            ),
        )

    def test_region_write_modes_are_deterministic(self):
        existing = [0.0, 0.4, 1.0]
        incoming = [1.0, 0.8, 0.25]
        self.assertEqual(incoming, sculpt_fields.merge_weights(existing, incoming, "replace"))
        self.assertEqual([1.0, 0.8, 1.0], sculpt_fields.merge_weights(existing, incoming, "add"))
        for actual, expected in zip(
            sculpt_fields.merge_weights(existing, incoming, "subtract"),
            [0.0, 0.08, 0.75],
        ):
            self.assertAlmostEqual(expected, actual)
        self.assertEqual([0.0, 0.4, 0.25], sculpt_fields.merge_weights(existing, incoming, "intersect"))

    def test_weighted_sculpt_operations_leave_unselected_points_unchanged(self):
        points = [(0.0, 0.0, 0.0), (2.0, 1.0, 0.0), (4.0, 2.0, 0.0)]
        weights = [1.0, 0.5, 0.0]
        translated = sculpt_fields.translate_points(points, weights, (2.0, 0.0, 0.0))
        self.assertEqual((2.0, 0.0, 0.0), translated[0])
        self.assertEqual((3.0, 1.0, 0.0), translated[1])
        self.assertEqual(points[2], translated[2])

        inflated = sculpt_fields.inflate_points(
            points,
            [(0.0, 0.0, 1.0)] * 3,
            weights,
            2.0,
        )
        self.assertEqual((0.0, 0.0, 2.0), inflated[0])
        self.assertEqual((2.0, 1.0, 1.0), inflated[1])
        self.assertEqual(points[2], inflated[2])

        smoothed = sculpt_fields.smooth_points(
            points,
            [(1,), (0, 2), (1,)],
            [0.0, 1.0, 0.0],
            factor=1.0,
            iterations=1,
        )
        self.assertEqual(points[0], smoothed[0])
        self.assertEqual((2.0, 1.0, 0.0), smoothed[1])
        self.assertEqual(points[2], smoothed[2])

        flattened = sculpt_fields.flatten_points(
            points,
            weights,
            plane_point=(0.0, 0.0, 0.0),
            plane_normal=(0.0, 1.0, 0.0),
            factor=1.0,
        )
        self.assertEqual(points[0], flattened[0])
        self.assertEqual((2.0, 0.5, 0.0), flattened[1])
        self.assertEqual(points[2], flattened[2])

    def test_topology_falloff_diffuses_with_bounded_decay(self):
        self.assertEqual(
            [1.0, 0.5, 0.25],
            sculpt_fields.diffuse_weights(
                [1.0, 0.0, 0.0],
                [(1,), (0, 2), (1,)],
                steps=2,
                decay=0.5,
            ),
        )

    def test_tangent_relax_moves_only_weighted_points_along_surface(self):
        points = [
            (0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (1.0, 1.0, 0.0),
        ]
        faces = [(0, 1, 3), (0, 3, 2)]
        neighbors = [(1, 2, 3), (0, 3), (0, 3), (0, 1, 2)]
        relaxed = sculpt_fields.tangent_relax_points(
            points,
            faces,
            neighbors,
            [0.0, 1.0, 0.0, 0.0],
            factor=0.5,
            feature_preservation=0.0,
        )
        self.assertEqual(points[0], relaxed[0])
        self.assertEqual(points[2], relaxed[2])
        self.assertEqual(points[3], relaxed[3])
        self.assertLess(relaxed[1][0], points[1][0])
        self.assertEqual(0.0, relaxed[1][2])

    def test_crease_combines_tangent_pinch_and_normal_depth(self):
        points = [
            (-1.0, -1.0, 0.0),
            (1.0, -1.0, 0.0),
            (1.0, 1.0, 0.0),
            (-1.0, 1.0, 0.0),
        ]
        creased = sculpt_fields.pinch_points(
            points,
            [(0, 1, 2, 3)],
            [(1, 3), (0, 2), (1, 3), (0, 2)],
            [1.0] * 4,
            strength=0.25,
            depth=-0.1,
            center=(0.0, 0.0, 0.0),
            feature_preservation=0.0,
        )
        self.assertLess(math.hypot(creased[0][0], creased[0][1]), math.sqrt(2.0))
        self.assertAlmostEqual(-0.1, creased[0][2])

    def test_volume_compensation_moves_scaled_closed_mesh_toward_original(self):
        original = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        ]
        faces = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
        deformed = [tuple(value * 1.5 for value in point) for point in original]
        corrected, report = sculpt_fields.compensate_volume(
            original,
            deformed,
            faces,
            [1.0] * 4,
            strength=1.0,
        )
        before = abs(sculpt_fields.signed_volume(original, faces))
        uncorrected_error = abs(abs(sculpt_fields.signed_volume(deformed, faces)) - before)
        corrected_error = abs(abs(sculpt_fields.signed_volume(corrected, faces)) - before)
        self.assertTrue(report["applied"])
        self.assertLess(corrected_error, uncorrected_error)
        self.assertTrue(math.isclose(corrected_error, 0.0, abs_tol=1e-9))

    def test_volume_compensation_improves_single_vertex_region(self):
        original = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        ]
        deformed = list(original)
        deformed[3] = (0.0, 0.0, 1.2)
        faces = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]

        corrected, report = sculpt_fields.compensate_volume(
            original,
            deformed,
            faces,
            [0.0, 0.0, 0.0, 1.0],
            strength=1.0,
        )

        target = abs(sculpt_fields.signed_volume(original, faces))
        self.assertTrue(report["applied"])
        self.assertNotEqual(deformed, corrected)
        self.assertLess(
            abs(abs(sculpt_fields.signed_volume(corrected, faces)) - target),
            abs(abs(sculpt_fields.signed_volume(deformed, faces)) - target),
        )

    def test_volume_compensation_skips_inconsistently_wound_surface(self):
        original = [
            (10.0, 10.0, 10.0),
            (11.0, 10.0, 10.0),
            (10.0, 11.0, 10.0),
            (10.0, 10.0, 11.0),
        ]
        faces = [(0, 1, 2), (0, 1, 3), (0, 3, 2), (1, 2, 3)]

        corrected, report = sculpt_fields.compensate_volume(
            original,
            original,
            faces,
            [1.0] * 4,
            strength=1.0,
        )

        self.assertFalse(sculpt_fields.is_closed_surface(faces))
        self.assertFalse(report["applied"])
        self.assertIn("inconsistently wound", report["reason"])
        self.assertEqual(original, corrected)

    def test_volume_compensation_skips_open_surface(self):
        original = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        ]
        faces = [(0, 2, 1), (0, 1, 3), (0, 3, 2)]
        deformed = [tuple(value * 1.5 for value in point) for point in original]
        corrected, report = sculpt_fields.compensate_volume(
            original,
            deformed,
            faces,
            [1.0] * 4,
            strength=1.0,
        )
        self.assertEqual(deformed, corrected)
        self.assertFalse(report["applied"])
        self.assertIn("non-manifold", report["reason"])

    def test_symmetry_reflects_the_stronger_source_delta(self):
        deltas, weights = sculpt_fields.mirror_deltas(
            [(-1.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
            [(0.0, 0.0, 0.0), (0.2, 0.1, 0.0)],
            [0.0, 1.0],
            axis=0,
            tolerance=1e-4,
        )
        self.assertEqual((-0.2, 0.1, 0.0), deltas[0])
        self.assertEqual(1.0, weights[0])

    def test_symmetry_updates_all_colocated_mirrored_vertices(self):
        points = [
            (-1.0, 0.0, 0.0),
            (-1.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
        ]
        deltas = [
            (-0.2, 0.0, 0.0),
            (-0.2, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
        ]

        mirrored, mirrored_weights = sculpt_fields.mirror_deltas(
            points,
            deltas,
            [1.0, 1.0, 0.0, 0.0],
            axis=0,
            tolerance=1e-4,
        )

        self.assertEqual((0.2, 0.0, 0.0), mirrored[2])
        self.assertEqual((0.2, 0.0, 0.0), mirrored[3])
        self.assertEqual(1.0, mirrored_weights[2])
        self.assertEqual(1.0, mirrored_weights[3])


if __name__ == "__main__":
    unittest.main()
