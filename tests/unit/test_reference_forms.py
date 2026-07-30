from __future__ import annotations

import math
import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import reference_forms  # noqa: E402


class ReferenceFormTests(unittest.TestCase):
    def test_ellipsoid_topology_is_closed_and_bounded(self):
        vertices, faces = reference_forms.deformed_ellipsoid_mesh(
            center=(2.0, 3.0, 4.0),
            radii=(2.0, 1.0, 0.5),
            segments=16,
            rings=8,
        )
        self.assertEqual(len(vertices), 16 * 7 + 2)
        self.assertEqual(len(faces), 16 * 8)
        self.assertAlmostEqual(max(point[0] for point in vertices), 4.0)
        self.assertAlmostEqual(min(point[0] for point in vertices), 0.0)
        self.assertAlmostEqual(max(point[2] for point in vertices), 4.5)
        self.assertAlmostEqual(min(point[2] for point in vertices), 3.5)

    def test_basis_orients_width_depth_and_height(self):
        vertices, _faces = reference_forms.deformed_ellipsoid_mesh(
            radii=(2.0, 1.0, 0.5),
            basis=((0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            segments=32,
            rings=16,
        )
        extents = [
            max(point[axis] for point in vertices)
            - min(point[axis] for point in vertices)
            for axis in range(3)
        ]
        self.assertAlmostEqual(extents[0], 2.0, places=5)
        self.assertAlmostEqual(extents[1], 4.0, places=5)
        self.assertAlmostEqual(extents[2], 1.0, places=5)

    def test_control_displaces_only_its_local_region(self):
        plain, _faces = reference_forms.deformed_ellipsoid_mesh(
            segments=32,
            rings=16,
        )
        deformed, _faces = reference_forms.deformed_ellipsoid_mesh(
            controls=[
                {
                    "direction": [1.0, 0.0, 0.0],
                    "offset": 0.4,
                    "falloff": 0.5,
                }
            ],
            segments=32,
            rings=16,
        )
        plain_max = max(point[0] for point in plain)
        deformed_max = max(point[0] for point in deformed)
        plain_min = min(point[0] for point in plain)
        deformed_min = min(point[0] for point in deformed)
        self.assertGreater(deformed_max, plain_max + 0.35)
        self.assertTrue(math.isclose(deformed_min, plain_min, abs_tol=1e-6))

    def test_invalid_controls_and_resolution_are_bounded(self):
        vertices, faces = reference_forms.deformed_ellipsoid_mesh(
            radii=(0.0, -2.0, "bad"),
            controls=[None, {"direction": ["bad"], "offset": "bad"}],
            segments=1,
            rings=1,
        )
        self.assertEqual(len(vertices), 8 * 3 + 2)
        self.assertEqual(len(faces), 8 * 4)


if __name__ == "__main__":
    unittest.main()
