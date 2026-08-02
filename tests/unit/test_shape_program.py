from __future__ import annotations

from collections import Counter
import math
import os
import sys
import unittest
from unittest import mock


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import shape_program  # noqa: E402


def _program(nodes, bounds=None):
    return {
        "schema_version": 1,
        "name": "Test Shape",
        "bounds": bounds
        or {"min": [-2.0, -2.0, -2.0], "max": [2.0, 2.0, 2.0]},
        "nodes": nodes,
    }


class ShapeProgramTests(unittest.TestCase):
    def test_supported_primitives_have_inside_and_outside_regions(self):
        primitives = [
            {"id": "shape", "type": "sphere", "radius": 0.8},
            {"id": "shape", "type": "ellipsoid", "radii": [0.8, 0.6, 0.5]},
            {"id": "shape", "type": "box", "size": [1.2, 1.0, 0.8], "rounding": 0.1},
            {"id": "shape", "type": "capsule", "point_a": [0, 0, -0.5], "point_b": [0, 0, 0.5], "radius": 0.3},
            {"id": "shape", "type": "cylinder", "radius": 0.6, "depth": 1.0, "rounding": 0.1},
            {"id": "shape", "type": "torus", "major_radius": 0.7, "minor_radius": 0.2},
            {"id": "shape", "type": "superquadric", "radii": [0.8, 0.6, 0.5], "exponents": [0.7, 1.4]},
            {"id": "shape", "type": "sweep", "points": [[0, 0, -0.5], [0, 0, 0.5]], "radii": [0.3, 0.15]},
        ]
        for node in primitives:
            with self.subTest(node_type=node["type"]):
                inside = [0.0, 0.0, 0.0]
                if node["type"] == "torus":
                    inside = [0.7, 0.0, 0.0]
                self.assertLess(shape_program.evaluate_shape_program(_program([node]), inside), 0.0)
                self.assertGreater(shape_program.evaluate_shape_program(_program([node]), [1.9, 1.9, 1.9]), 0.0)

    def test_boolean_operations_and_smooth_blends_compose_in_order(self):
        program = _program(
            [
                {"id": "body", "type": "sphere", "radius": 1.0},
                {
                    "id": "socket",
                    "type": "sphere",
                    "operation": "subtract",
                    "radius": 0.35,
                    "blend": 0.1,
                },
                {
                    "id": "crop",
                    "type": "box",
                    "operation": "intersect",
                    "size": [3.0, 3.0, 1.2],
                    "rounding": 0.05,
                },
            ]
        )
        self.assertGreater(shape_program.evaluate_shape_program(program, [0, 0, 0]), 0.0)
        self.assertLess(shape_program.evaluate_shape_program(program, [0.7, 0, 0]), 0.0)
        self.assertGreater(shape_program.evaluate_shape_program(program, [0, 0, 0.9]), 0.0)

    def test_parent_transforms_form_a_semantic_hierarchy(self):
        program = _program(
            [
                {
                    "id": "parent",
                    "type": "sphere",
                    "radius": 0.1,
                    "transform": {"location": [1.0, 0.0, 0.0]},
                },
                {
                    "id": "child",
                    "parent_id": "parent",
                    "type": "sphere",
                    "radius": 0.4,
                    "transform": {"location": [1.0, 0.0, 0.0]},
                },
            ]
        )
        self.assertLess(shape_program.evaluate_shape_program(program, [2.0, 0.0, 0.0]), 0.0)
        self.assertGreater(shape_program.evaluate_shape_program(program, [0.0, 0.0, 0.0]), 0.0)

    def test_prepared_evaluator_reuses_canonical_transform_state(self):
        program = _program(
            [
                {"id": "body", "type": "sphere", "radius": 1.0},
                {
                    "id": "tail",
                    "type": "sweep",
                    "parent_id": "body",
                    "points": [[0, 0, 0], [0, 0, 1], [0.5, 0, 1.5]],
                    "radii": [0.2, 0.15, 0.05],
                },
            ]
        )
        prepared = shape_program.prepare_shape_program(program)
        point = [0.1, 0.0, 0.3]
        self.assertEqual(
            prepared.evaluate(point),
            shape_program.evaluate_shape_program(program, point),
        )
        self.assertEqual(prepared.node_units, 2)
        self.assertEqual(prepared.primitive_units, 3)
        self.assertEqual(prepared.transform_units, 3)
        self.assertEqual(prepared.work_units_per_sample, 6)

    def test_normalization_rejects_ambiguous_or_unsafe_graphs(self):
        with self.assertRaisesRegex(shape_program.ShapeProgramError, "Duplicate"):
            shape_program.normalize_shape_program(
                _program(
                    [
                        {"id": "same", "type": "sphere"},
                        {"id": "same", "type": "box"},
                    ]
                )
            )
        with self.assertRaisesRegex(shape_program.ShapeProgramError, "cycle"):
            shape_program.normalize_shape_program(
                _program(
                    [
                        {"id": "first", "parent_id": "second", "type": "sphere"},
                        {"id": "second", "parent_id": "first", "type": "sphere"},
                    ]
                )
            )
        with self.assertRaisesRegex(shape_program.ShapeProgramError, "first enabled"):
            shape_program.normalize_shape_program(
                _program([{"id": "cut", "type": "sphere", "operation": "subtract"}])
            )

    def test_digest_is_stable_across_input_key_order(self):
        first = _program([{"id": "body", "type": "sphere", "radius": 1.0}])
        second = {
            "nodes": [{"radius": 1.0, "type": "sphere", "id": "body"}],
            "bounds": {"max": [2, 2, 2], "min": [-2, -2, -2]},
            "name": "Test Shape",
            "schema_version": 1,
        }
        self.assertEqual(
            shape_program.shape_program_digest(first),
            shape_program.shape_program_digest(second),
        )

    def test_marching_tetrahedra_produces_a_watertight_mesh(self):
        result = shape_program.mesh_shape_program(
            _program([{"id": "body", "type": "sphere", "radius": 1.0}]),
            resolution=16,
            smooth_iterations=0,
        )
        edge_use = Counter(
            tuple(sorted((face[index], face[(index + 1) % 3])))
            for face in result["faces"]
            for index in range(3)
        )
        self.assertGreater(result["stats"]["vertex_count"], 100)
        self.assertTrue(all(count == 2 for count in edge_use.values()))
        self.assertEqual(result["stats"]["vertex_count"], len(result["vertices"]))
        self.assertEqual(result["stats"]["face_count"], len(result["faces"]))

    def test_compile_rejects_surfaces_that_cross_bounds(self):
        with self.assertRaisesRegex(shape_program.ShapeProgramError, "expand bounds"):
            shape_program.mesh_shape_program(
                _program(
                    [{"id": "body", "type": "sphere", "radius": 1.0}],
                    bounds={"min": [-0.5, -0.5, -0.5], "max": [0.5, 0.5, 0.5]},
                ),
                resolution=8,
            )

    def test_compile_workload_is_checked_before_sampling(self):
        program = _program([{"id": "body", "type": "sphere", "radius": 1.0}])
        with mock.patch.object(shape_program, "MAX_SDF_EVALUATIONS", 1):
            with self.assertRaisesRegex(shape_program.ShapeProgramError, "evaluation work units"):
                shape_program.mesh_shape_program(program, resolution=8)

    def test_sweep_segments_are_counted_in_compile_workload(self):
        program = _program(
            [
                {
                    "id": "tail",
                    "type": "sweep",
                    "points": [[0.0, 0.0, index * 0.1] for index in range(8)],
                    "radii": [0.1] * 8,
                }
            ],
            bounds={"min": [-1, -1, -1], "max": [1, 1, 2]},
        )
        result = shape_program.mesh_shape_program(
            program, resolution=8, smooth_iterations=0
        )
        self.assertEqual(
            result["stats"]["node_evaluation_count"] * 7,
            result["stats"]["primitive_evaluation_count"],
        )
        self.assertGreater(
            result["stats"]["estimated_work_units"],
            result["stats"]["primitive_evaluation_count"],
        )

    def test_numeric_payloads_reject_boolean_and_extreme_coordinates(self):
        with self.assertRaisesRegex(shape_program.ShapeProgramError, "must be a number"):
            shape_program.normalize_shape_program(
                _program([{"id": "body", "type": "sphere", "radius": True}])
            )
        with self.assertRaisesRegex(shape_program.ShapeProgramError, "magnitude"):
            shape_program.normalize_shape_program(
                _program(
                    [
                        {
                            "id": "body",
                            "type": "sphere",
                            "transform": {"location": [1.0e9, 0.0, 0.0]},
                        }
                    ]
                )
            )
        with self.assertRaisesRegex(shape_program.ShapeProgramError, "boolean"):
            shape_program.normalize_shape_program(
                _program([{"id": "body", "type": "sphere", "enabled": "false"}])
            )
        with self.assertRaisesRegex(shape_program.ShapeProgramError, "magnitude"):
            shape_program.normalize_shape_program(
                _program([{"id": "body", "type": "ellipsoid", "radii": [1.0e9, 1, 1]}])
            )
        with self.assertRaisesRegex(shape_program.ShapeProgramError, "at least"):
            shape_program.normalize_shape_program(
                _program([{"id": "body", "type": "box", "size": [1.0e-12, 1, 1]}])
            )

    def test_transform_chains_reject_unsafe_cumulative_scale(self):
        with self.assertRaisesRegex(shape_program.ShapeProgramError, "cumulative"):
            shape_program.normalize_shape_program(
                _program(
                    [
                        {
                            "id": "parent",
                            "type": "sphere",
                            "transform": {"scale": [0.005, 0.005, 0.005]},
                        },
                        {
                            "id": "child",
                            "parent_id": "parent",
                            "type": "sphere",
                            "transform": {"scale": [0.005, 0.005, 0.005]},
                        },
                    ]
                )
            )

    def test_superquadric_evaluation_stays_finite_for_bounded_extremes(self):
        distance = shape_program.evaluate_shape_program(
            _program(
                [
                    {
                        "id": "body",
                        "type": "superquadric",
                        "radii": [1.0e-5, 1.0e-5, 1.0e-5],
                        "exponents": [0.1, 4.0],
                    }
                ]
            ),
            [1.0e6, 1.0e6, 1.0e6],
        )
        self.assertTrue(math.isfinite(distance))


if __name__ == "__main__":
    unittest.main()
