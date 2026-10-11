import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "addon"))
from claude_blender import retopology_policy as policy


class RetopologyPolicyTests(unittest.TestCase):
    def test_local_defaults_preserve_appearance(self):
        options = policy.local_options({})
        self.assertEqual(options["method"], "quadriflow")
        self.assertTrue(options["bake_textures"])
        self.assertFalse(options["use_symmetry"])
        self.assertEqual(options["map_types"], ["base_color", "normal", "roughness", "metallic", "emission"])

    def test_bounds_reject_instead_of_clamp(self):
        for options in ({"target_faces": True}, {"target_faces": 0}, {"resolution": 8192},
                        {"ray_distance_ratio": float("nan")}, {"bake_textures": "false"}, {"map_types": []},
                        {"map_types": ["unknown"]}, {"method": "voxel"}, {"timeout_seconds": 2}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                policy.local_options(options)

    def test_atlas_pixel_budget_includes_coverage(self):
        with self.assertRaises(ValueError):
            policy.local_options({"resolution": 4096})
        self.assertEqual(policy.validate_atlas(2048), list(policy.DEFAULT_MAPS))
        self.assertTrue(policy.local_options({"bake_textures": False}, kind="bake")["bake_textures"])


if __name__ == "__main__":
    unittest.main()
