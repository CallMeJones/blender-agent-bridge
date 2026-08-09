from __future__ import annotations

import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import reference_parts  # noqa: E402


class ReferencePartsTests(unittest.TestCase):
    def test_cute_quadruped_splits_primary_form_into_named_parts(self):
        graph = reference_parts.infer_part_graph(
            subject="cute kitten",
            forms=[
                {
                    "name": "primary_subject",
                    "center": [0.0, 0.0, 1.5],
                    "radii": [1.0, 0.6, 1.2],
                    "basis": [
                        [1.0, 0.0, 0.0],
                        [0.0, 1.0, 0.0],
                        [0.0, 0.0, 1.0],
                    ],
                    "source_object": "Primary Outline",
                }
            ],
        )

        names = {part["name"] for part in graph["parts"]}
        self.assertTrue({"head", "body", "left_ear", "right_ear", "muzzle"}.issubset(names))
        self.assertEqual("cute_quadruped", graph["subject_profile"])
        self.assertGreaterEqual(graph["role_counts"]["eye"], 2)

    def test_generic_character_splits_primary_form_into_semantic_parts(self):
        graph = reference_parts.infer_part_graph(
            subject="storybook character",
            forms=[
                {
                    "name": "primary_subject",
                    "center": [0.0, 0.0, 1.2],
                    "radii": [0.7, 0.4, 1.2],
                    "basis": [
                        [1.0, 0.0, 0.0],
                        [0.0, 1.0, 0.0],
                        [0.0, 0.0, 1.0],
                    ],
                    "source_object": "Primary Outline",
                }
            ],
        )

        names = {part["name"] for part in graph["parts"]}
        self.assertTrue({"body", "head", "left_arm", "right_arm", "left_leg", "right_leg"}.issubset(names))
        self.assertEqual("generic_character", graph["subject_profile"])
        self.assertEqual(2, graph["role_counts"]["arm"])
        self.assertEqual(2, graph["role_counts"]["leg"])
        self.assertTrue(any("generic_character" in warning for warning in graph["warnings"]))

    def test_hints_override_inferred_parts(self):
        graph = reference_parts.infer_part_graph(
            subject="object",
            subject_profile="generic_object",
            forms=[
                {
                    "name": "head_mass",
                    "center": [0.0, 0.0, 1.0],
                    "radii": [0.5, 0.4, 0.5],
                }
            ],
            part_hints=[
                {
                    "name": "head_mass",
                    "role": "head",
                    "center": [1.0, 2.0, 3.0],
                    "radii": [0.2, 0.3, 0.4],
                }
            ],
        )

        part = next(item for item in graph["parts"] if item["name"] == "head_mass")
        self.assertEqual("hint", part["confidence"])
        self.assertEqual([1.0, 2.0, 3.0], part["center"])
        self.assertEqual("head", part["role"])

    def test_landmark_names_create_feature_parts(self):
        graph = reference_parts.infer_part_graph(
            subject="kitten",
            subject_profile="cute_quadruped",
            forms=[
                {
                    "name": "body",
                    "center": [0.0, 0.0, 1.0],
                    "radii": [1.0, 0.5, 1.0],
                }
            ],
            landmarks=[
                {"name": "left_eye", "location": [-0.2, -0.4, 1.4]},
                {"name": "right_eye", "location": [0.2, -0.4, 1.4]},
            ],
        )

        eyes = [part for part in graph["parts"] if part["role"] == "eye"]
        self.assertEqual(2, len(eyes))
        self.assertTrue(all(part["parent"] == "head" for part in eyes))


if __name__ == "__main__":
    unittest.main()
