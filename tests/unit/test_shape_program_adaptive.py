from collections import Counter
import os
import sys
import unittest
from unittest import mock


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import shape_program  # noqa: E402
from claude_blender import shape_program_adaptive  # noqa: E402


def _program(node=None, bounds=None):
    return {
        "schema_version": 1,
        "name": "Adaptive Test",
        "bounds": bounds
        or {"min": [-2.0, -2.0, -2.0], "max": [2.0, 2.0, 2.0]},
        "nodes": [node or {"id": "body", "type": "sphere", "radius": 1.0}],
    }


class AdaptiveShapeProgramTests(unittest.TestCase):
    def test_adaptive_dual_contour_is_watertight_at_coarse_depth(self):
        result = shape_program_adaptive.mesh_shape_program_adaptive(
            _program(),
            base_depth=3,
            max_depth=5,
            error_threshold=0.1,
        )
        edge_use = Counter(
            tuple(sorted((face[index], face[(index + 1) % len(face)])))
            for face in result["faces"]
            for index in range(len(face))
        )
        edge_directions = Counter()
        signed_volume = 0.0
        for face in result["faces"]:
            for index, first in enumerate(face):
                second = face[(index + 1) % len(face)]
                edge = tuple(sorted((first, second)))
                edge_directions[edge] += 1 if (first, second) == edge else -1
            for index in range(1, len(face) - 1):
                first, second, third = (
                    result["vertices"][face[item]]
                    for item in (0, index, index + 1)
                )
                signed_volume += (
                    first[0] * (second[1] * third[2] - second[2] * third[1])
                    + first[1] * (second[2] * third[0] - second[0] * third[2])
                    + first[2] * (second[0] * third[1] - second[1] * third[0])
                ) / 6.0
        self.assertEqual(result["stats"]["meshing_mode"], "adaptive_dual")
        self.assertEqual(
            set(result["stats"]["surface_depth_histogram"]), {"3"}
        )
        self.assertEqual(
            result["stats"]["surface_depth_histogram"]["3"],
            result["stats"]["vertex_count"],
        )
        self.assertEqual(result["stats"]["topology_skipped_segment_count"], 0)
        self.assertTrue(all(count == 2 for count in edge_use.values()))
        self.assertTrue(all(balance == 0 for balance in edge_directions.values()))
        self.assertGreater(signed_volume, 0.0)

    def test_topology_validation_rejects_inconsistent_face_winding(self):
        with self.assertRaisesRegex(
            shape_program.ShapeProgramError, "consistently oriented"
        ):
            shape_program_adaptive._validate_closed(
                [
                    (0, 1, 2),
                    (0, 1, 3),
                    (1, 2, 3),
                    (2, 0, 3),
                ]
            )

    def test_explicit_region_adds_local_surface_resolution(self):
        settings = {
            "base_depth": 3,
            "max_depth": 5,
            "error_threshold": 0.5,
        }
        coarse = shape_program_adaptive.mesh_shape_program_adaptive(
            _program(), **settings
        )
        refined = shape_program_adaptive.mesh_shape_program_adaptive(
            _program(),
            refinement_regions=[
                {
                    "name": "face",
                    "type": "sphere",
                    "center": [1.0, 0.0, 0.0],
                    "radius": 0.65,
                    "depth": 5,
                }
            ],
            **settings,
        )
        self.assertGreater(refined["stats"]["region_refined_cell_count"], 0)
        region_stats = refined["stats"]["refinement_region_stats"][0]
        self.assertEqual(region_stats["name"], "face")
        self.assertGreater(region_stats["surface_leaf_count"], 0)
        self.assertGreater(region_stats["target_depth_leaf_count"], 0)
        self.assertGreater(
            refined["stats"]["surface_depth_histogram"].get("5", 0),
            coarse["stats"]["surface_depth_histogram"].get("5", 0),
        )
        self.assertGreater(
            refined["stats"]["vertex_count"], coarse["stats"]["vertex_count"]
        )

    def test_rounded_box_keeps_qef_faces_nondegenerate(self):
        result = shape_program_adaptive.mesh_shape_program_adaptive(
            _program(
                {"id": "body", "type": "box", "size": [2, 2, 2], "rounding": 0.1}
            ),
            base_depth=3,
            max_depth=5,
            error_threshold=0.1,
        )
        for face in result["faces"]:
            first, second, third = (
                result["vertices"][index] for index in face[:3]
            )
            first_edge = tuple(second[axis] - first[axis] for axis in range(3))
            second_edge = tuple(third[axis] - first[axis] for axis in range(3))
            cross = (
                first_edge[1] * second_edge[2] - first_edge[2] * second_edge[1],
                first_edge[2] * second_edge[0] - first_edge[0] * second_edge[2],
                first_edge[0] * second_edge[1] - first_edge[1] * second_edge[0],
            )
            self.assertGreater(sum(value * value for value in cross), 1.0e-24)

    def test_topology_repair_refines_ambiguous_coarse_transition(self):
        program = {
            "schema_version": 1,
            "bounds": {"min": [-2, -1.6, -1.5], "max": [2.1, 1.6, 2.8]},
            "nodes": [
                {"id": "body", "type": "ellipsoid", "radii": [0.72, 0.58, 1]},
                {
                    "id": "tail",
                    "type": "sweep",
                    "points": [
                        [0.55, 0.05, -0.55],
                        [1.05, 0.08, -0.3],
                        [1.28, 0.06, 0.2],
                        [1.05, 0.03, 0.68],
                    ],
                    "radii": [0.24, 0.21, 0.16, 0.08],
                    "blend": 0.18,
                },
            ],
        }
        result = shape_program_adaptive.mesh_shape_program_adaptive(
            program,
            base_depth=3,
            max_depth=5,
            error_threshold=0.15,
            refinement_regions=[
                {
                    "name": "upper_body",
                    "type": "sphere",
                    "center": [0, 0, 1.35],
                    "radius": 1,
                    "depth": 5,
                }
            ],
        )
        self.assertEqual(result["stats"]["topology_repair_passes"], 1)
        self.assertEqual(result["stats"]["topology_refined_cell_count"], 2)
        self.assertEqual(result["stats"]["topology_skipped_segment_count"], 0)

    def test_adaptive_compile_rejects_boundary_crossing_and_bad_regions(self):
        with self.assertRaisesRegex(shape_program.ShapeProgramError, "expand bounds"):
            shape_program_adaptive.mesh_shape_program_adaptive(
                _program(
                    bounds={
                        "min": [-0.5, -0.5, -0.5],
                        "max": [0.5, 0.5, 0.5],
                    }
                ),
                base_depth=3,
                max_depth=4,
            )
        with self.assertRaisesRegex(shape_program.ShapeProgramError, "sphere or box"):
            shape_program_adaptive.mesh_shape_program_adaptive(
                _program(),
                base_depth=3,
                max_depth=4,
                refinement_regions=[{"type": "capsule", "depth": 4}],
            )

    def test_adaptive_workload_is_bounded_before_unbounded_growth(self):
        with mock.patch.object(
            shape_program_adaptive, "MAX_ADAPTIVE_SDF_SAMPLES", 1
        ):
            with self.assertRaisesRegex(shape_program.ShapeProgramError, "sample limit"):
                shape_program_adaptive.mesh_shape_program_adaptive(
                    _program(), base_depth=3, max_depth=4
                )


if __name__ == "__main__":
    unittest.main()
