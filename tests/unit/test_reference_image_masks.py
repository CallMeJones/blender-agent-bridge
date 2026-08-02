from __future__ import annotations

import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import reference_image_masks  # noqa: E402


class ReferenceImageMaskTests(unittest.TestCase):
    def test_alpha_mask_and_outline_are_bounded(self):
        pixels = []
        for y in range(4):
            for x in range(4):
                alpha = 1.0 if 1 <= x <= 2 and 1 <= y <= 2 else 0.0
                pixels.extend([1.0, 1.0, 1.0, alpha])
        mask = reference_image_masks.mask_from_pixels(
            {"sampled_size": [4, 4], "pixels": pixels},
            mode="alpha",
            threshold=0.5,
        )
        self.assertEqual(4, sum(mask))
        outline = reference_image_masks.outline_from_mask(
            mask,
            4,
            4,
            max_points=12,
        )
        self.assertEqual(
            {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5},
            outline["bounds"],
        )
        self.assertGreaterEqual(len(outline["points"]), 3)
        self.assertLessEqual(len(outline["points"]), 12)

    def test_background_color_mask_requires_background(self):
        pixels = [1.0, 1.0, 1.0, 1.0] * 4
        with self.assertRaisesRegex(ValueError, "background_color"):
            reference_image_masks.mask_from_pixels(
                {"sampled_size": [2, 2], "pixels": pixels},
                mode="background_color",
                threshold=0.1,
            )

    def test_background_color_mask_separates_foreground(self):
        pixels = [
            1.0, 1.0, 1.0, 1.0,
            0.0, 0.0, 0.0, 1.0,
            1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0,
        ]
        mask = reference_image_masks.mask_from_pixels(
            {"sampled_size": [2, 2], "pixels": pixels},
            mode="background_color",
            threshold=0.5,
            background_color=[1.0, 1.0, 1.0],
        )
        self.assertEqual([0, 1, 0, 0], list(mask))


if __name__ == "__main__":
    unittest.main()
