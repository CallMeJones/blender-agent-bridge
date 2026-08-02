from __future__ import annotations

import math
import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import fur_groom  # noqa: E402


class FurGroomTests(unittest.TestCase):
    def test_area_weighted_sampling_is_deterministic_and_favors_large_faces(self):
        triangles = [
            {
                "vertices": [(0, 0, 0), (1, 0, 0), (0, 1, 0)],
                "normal": (0, 0, 1),
            },
            {
                "vertices": [(10, 0, 0), (14, 0, 0), (10, 4, 0)],
                "normal": (0, 0, 1),
            },
        ]
        first = fur_groom.sample_surface(triangles, 200, seed=19)
        second = fur_groom.sample_surface(triangles, 200, seed=19)
        self.assertEqual(first, second)
        large_face_samples = sum(sample["point"][0] >= 10.0 for sample in first)
        self.assertGreater(large_face_samples, 175)

    def test_minimum_spacing_prevents_overlapping_roots(self):
        triangles = [
            {
                "vertices": [(0, 0, 0), (4, 0, 0), (0, 4, 0)],
                "normal": (0, 0, 1),
            }
        ]
        samples = fur_groom.sample_surface(
            triangles,
            35,
            seed=7,
            minimum_spacing=0.25,
            oversample=12,
        )
        self.assertEqual(len(samples), 35)
        for index, sample in enumerate(samples):
            for other in samples[index + 1 :]:
                distance = math.dist(sample["point"], other["point"])
                self.assertGreaterEqual(distance, 0.25)

    def test_density_weight_and_flow_controls_shape_sampling_and_direction(self):
        triangles = [
            {
                "vertices": [(0, 0, 0), (2, 0, 0), (0, 2, 0)],
                "normal": (0, 0, 1),
                "weight": 0.0,
            },
            {
                "vertices": [(5, 0, 0), (7, 0, 0), (5, 2, 0)],
                "normal": (0, 0, 1),
                "weight": 1.0,
            },
        ]
        samples = fur_groom.sample_surface(triangles, 20, seed=2)
        self.assertTrue(all(sample["point"][0] >= 5.0 for sample in samples))
        direction = fur_groom.blend_flow_controls(
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            [
                {
                    "location": (0.0, 0.0, 0.0),
                    "direction": (0.0, 1.0, 0.0),
                    "radius": 2.0,
                    "strength": 5.0,
                }
            ],
        )
        self.assertGreater(direction[1], direction[0])
        density = fur_groom.blend_density_controls(
            (0.0, 0.0, 0.0),
            [{"location": (0.0, 0.0, 0.0), "radius": 2.0, "strength": 3.0}],
        )
        self.assertAlmostEqual(3.0, density)
        self.assertEqual(
            0.0,
            fur_groom.blend_density_controls(
                (3.0, 0.0, 0.0),
                [{"location": (0.0, 0.0, 0.0), "radius": 2.0, "strength": 3.0}],
            ),
        )

    def test_region_counts_respect_budget_and_explicit_counts(self):
        regions = [
            {"name": "face", "count": 10},
            {"name": "body", "density": 3.0},
            {"name": "tail", "density": 1.0},
        ]
        self.assertEqual(
            fur_groom.allocate_region_counts(regions, 50),
            [10, 30, 10],
        )
        self.assertEqual(
            sum(
                fur_groom.allocate_region_counts(
                    [{"count": 80}, {"count": 40}],
                    60,
                )
            ),
            60,
        )

    def test_strand_path_lays_down_and_tapers_without_leaving_root(self):
        path = fur_groom.strand_path(
            (1.0, 2.0, 3.0),
            (0.0, 0.0, 1.0),
            (1.0, 0.0, 0.0),
            length=0.5,
            point_count=6,
            flow_strength=1.0,
            normal_lift=0.1,
            clump_vector=(0.0, 0.2, 0.0),
            clump_strength=0.5,
            noise_strength=0.1,
            seed=3,
        )
        self.assertEqual(path[0], (1.0, 2.0, 3.0))
        self.assertEqual(len(path), 6)
        self.assertGreater(path[-1][0], path[0][0])
        self.assertGreater(path[-1][1], path[0][1])

    def test_part_graph_fur_flow_field_creates_localized_regions(self):
        field = fur_groom.part_graph_fur_flow_field(
            [
                {
                    "name": "head",
                    "role": "head",
                    "center": [0.0, 0.0, 1.5],
                    "radii": [0.5, 0.35, 0.4],
                    "basis": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                },
                {
                    "name": "muzzle",
                    "role": "muzzle",
                    "center": [0.0, -0.35, 1.35],
                    "radii": [0.22, 0.12, 0.12],
                    "basis": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                },
                {
                    "name": "left_eye",
                    "role": "eye",
                    "center": [-0.15, -0.45, 1.5],
                    "radii": [0.05, 0.03, 0.06],
                },
            ],
            count=120,
        )

        self.assertEqual(1, field["schema_version"])
        self.assertEqual(2, len(field["regions"]))
        self.assertEqual(120, sum(region["count"] for region in field["regions"]))
        self.assertTrue(
            all(region["density_controls"] for region in field["regions"])
        )
        self.assertNotIn(
            "left_eye_fur",
            {region["name"] for region in field["regions"]},
        )

        long_name = "head_" + "detail_" * 20
        long_name_field = fur_groom.part_graph_fur_flow_field(
            [
                {
                    "name": long_name,
                    "role": "head",
                    "center": [0.0, 0.0, 1.5],
                    "radii": [0.5, 0.35, 0.4],
                }
            ]
        )
        self.assertEqual(long_name, long_name_field["regions"][0]["part_name"])
        self.assertLessEqual(len(long_name_field["regions"][0]["name"]), 80)

    def test_part_weight_at_point_uses_soft_ellipsoid_membership(self):
        part = {
            "name": "head",
            "role": "head",
            "center": [0.0, 0.0, 0.0],
            "radii": [1.0, 0.5, 0.5],
            "basis": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        }

        center = fur_groom.part_weight_at_point((0.0, 0.0, 0.0), part)
        near_edge = fur_groom.part_weight_at_point((0.8, 0.0, 0.0), part)
        outside = fur_groom.part_weight_at_point((2.0, 0.0, 0.0), part)

        self.assertAlmostEqual(1.0, center)
        self.assertGreater(center, near_edge)
        self.assertGreater(near_edge, 0.0)
        self.assertEqual(0.0, outside)


if __name__ == "__main__":
    unittest.main()
