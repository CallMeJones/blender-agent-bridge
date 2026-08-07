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


def _light_subject_on_light_backdrop():
    """A near-white subject on a white backdrop, with a graded drop shadow.

    Reproduces the case measured on a real reference sheet: a nurse in a white
    uniform against a white sweep. The apron sampled rgb(0.92, 0.93, 0.94)
    against a rgb(1, 1, 1) backdrop -- a distance of 0.10, far closer to the
    backdrop than to anything a brightness threshold could use.

    Two details are load-bearing and both come from the real image. The shadow
    *grades* into the backdrop rather than stepping, because a flood that
    compares each candidate to the neighbour it came from follows a gradient
    and stops at a step. And the subject carries dark line work, as this style
    of reference art does; that outline is what halts the flood at the
    subject, not the fill colour, which is nearly backdrop-coloured.
    """

    width, height = 24, 32
    subject_x, subject_y = range(8, 16), range(6, 28)

    def colour(x, y):
        if x in subject_x and y in subject_y:
            edge = x in (8, 15) or y in (6, 27)
            return (0.18, 0.17, 0.20) if edge else (0.92, 0.93, 0.94)
        if 16 <= x < 20 and 8 <= y < 30:
            # Grades back to the backdrop over four columns.
            depth = (20 - x) / 4.0
            return (1.0 - 0.14 * depth, 1.0 - 0.11 * depth, 1.0 - 0.04 * depth)
        return (1.0, 1.0, 1.0)

    pixels = []
    for y in range(height):
        for x in range(width):
            red, green, blue = colour(x, y)
            pixels.extend([red, green, blue, 1.0])
    sample = {"sampled_size": (width, height), "pixels": pixels}
    subject = {(x, y) for y in subject_y for x in subject_x}
    return sample, subject, width, height


class LightOnLightMaskTests(unittest.TestCase):
    """The case both existing modes get wrong, in opposite directions."""

    def setUp(self):
        self.sample, self.subject, self.width, self.height = _light_subject_on_light_backdrop()

    def _selected(self, mask):
        return {
            (index % self.width, index // self.width)
            for index, value in enumerate(mask)
            if value
        }

    def test_border_flood_finds_the_subject_and_nothing_else(self):
        mask = reference_image_masks.mask_from_pixels(
            self.sample, mode="border_flood", threshold=0.08
        )
        self.assertEqual(self.subject, self._selected(mask))

    def test_luminance_cannot_separate_a_white_subject_from_a_white_backdrop(self):
        # Documents why border_flood exists: this selects nearly everything.
        mask = reference_image_masks.mask_from_pixels(
            self.sample, mode="luminance", threshold=0.80
        )
        self.assertGreater(len(self._selected(mask)), len(self.subject) * 3)

    def test_background_color_eats_the_white_uniform(self):
        # The other direction: the apron fill is within threshold of the
        # backdrop, so only the dark outline survives and the mask is a hollow
        # ring rather than a body.
        mask = reference_image_masks.mask_from_pixels(
            self.sample, mode="background_color", threshold=0.25,
            background_color=[1.0, 1.0, 1.0],
        )
        selected = self._selected(mask)
        self.assertIn((8, 15), selected)       # outline kept
        self.assertNotIn((12, 15), selected)   # uniform fill lost
        self.assertLess(len(selected), len(self.subject) // 2)

    def test_the_tinted_shadow_is_background_not_subject(self):
        mask = reference_image_masks.mask_from_pixels(
            self.sample, mode="border_flood", threshold=0.08
        )
        selected = self._selected(mask)
        self.assertNotIn((17, 20), selected)
        self.assertIn((12, 20), selected)

    def test_the_result_is_stable_across_a_range_of_tolerances(self):
        # A mask that only works at one hand-tuned number is not a fix.
        # The floor is set by the shadow's per-pixel gradient step, measured
        # at roughly 0.046 in this fixture: a tolerance below it stops inside
        # the shadow and reports it as subject.
        for tolerance in (0.06, 0.08, 0.10, 0.12):
            mask = reference_image_masks.mask_from_pixels(
                self.sample, mode="border_flood", threshold=tolerance
            )
            self.assertEqual(self.subject, self._selected(mask), tolerance)

    def test_auto_reaches_border_flood_instead_of_raising(self):
        # Previously auto chose background_color with no colour to supply and
        # raised. Opaque alpha plus no background_color is the common case for
        # a flattened reference sheet.
        mask = reference_image_masks.mask_from_pixels(
            self.sample, mode="auto", threshold=0.08
        )
        self.assertEqual(self.subject, self._selected(mask))

    def test_auto_still_prefers_a_supplied_background_colour(self):
        supplied = reference_image_masks.mask_from_pixels(
            self.sample, mode="auto", threshold=0.25, background_color=[1.0, 1.0, 1.0]
        )
        direct = reference_image_masks.mask_from_pixels(
            self.sample, mode="background_color", threshold=0.25,
            background_color=[1.0, 1.0, 1.0],
        )
        self.assertEqual(self._selected(direct), self._selected(supplied))

    def test_an_unknown_mode_names_every_supported_mode(self):
        with self.assertRaises(ValueError) as caught:
            reference_image_masks.mask_from_pixels(
                self.sample, mode="magic", threshold=0.1
            )
        self.assertIn("border_flood", str(caught.exception))
