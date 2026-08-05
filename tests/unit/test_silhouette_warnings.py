from __future__ import annotations

import os
import sys
import types
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))


def _load():
    """Extract just the plausibility checks, which are free of Blender types.

    The module imports bpy at top level, so the block is compiled on its own.
    Bounds are found by locating the helper and taking everything up to the
    next top-level definition after it, rather than assuming file ordering.
    """

    path = os.path.join(ROOT, "addon", "claude_blender", "reference_image_intake.py")
    source = open(path, encoding="utf-8").read()
    start = source.index("MASS_FILLS_FRAME_RATIO")
    marker = source.index("def _silhouette_plausibility_warnings")
    after = source.find("\ndef ", marker + 1)
    end = after if after != -1 else len(source)
    module = types.ModuleType("silhouette_checks")
    exec(compile(source[start:end], "silhouette_checks", "exec"), module.__dict__)
    return module


CHECKS = _load()


def _outline(coverage, points=None):
    return {
        "foreground_coverage": coverage,
        "points": points if points is not None else [[0.4, 0.4], [0.5, 0.5], [0.6, 0.6]],
    }


def _bounds(width, height, x=0.0, y=0.0):
    return {"x": x, "y": y, "width": width, "height": height}


class MassFillsFrameTests(unittest.TestCase):
    def test_observed_failure_is_flagged(self):
        # Measured on the white-on-white subject: mass spanned 0.041..0.959 x
        # and 0.004..0.977 y, i.e. essentially the whole frame.
        warnings = CHECKS._silhouette_plausibility_warnings(
            _outline(0.43), _bounds(0.918, 0.973)
        )
        self.assertTrue(any("fills" in w for w in warnings), warnings)

    def test_normal_subject_bounds_are_not_flagged(self):
        warnings = CHECKS._silhouette_plausibility_warnings(_outline(0.30), _bounds(0.55, 0.88))
        self.assertFalse(any("fills" in w for w in warnings), warnings)

    def test_tall_narrow_subject_is_not_flagged(self):
        # A standing figure is tall but not wide; only both axes together are
        # evidence of a failed separation.
        warnings = CHECKS._silhouette_plausibility_warnings(_outline(0.35), _bounds(0.40, 0.97))
        self.assertFalse(any("fills" in w for w in warnings), warnings)


class CoverageBandTests(unittest.TestCase):
    def test_implausibly_high_coverage_is_flagged(self):
        warnings = CHECKS._silhouette_plausibility_warnings(_outline(0.82), _bounds(0.5, 0.5))
        self.assertTrue(any("coverage" in w for w in warnings), warnings)

    def test_implausibly_low_coverage_is_flagged(self):
        warnings = CHECKS._silhouette_plausibility_warnings(_outline(0.02), _bounds(0.5, 0.5))
        self.assertTrue(any("coverage" in w for w in warnings), warnings)

    def test_measured_good_masks_are_not_flagged(self):
        # Coverage of the hand-built flood-fill masks that actually worked.
        for coverage in (0.506, 0.380, 0.432, 0.294):
            warnings = CHECKS._silhouette_plausibility_warnings(
                _outline(coverage), _bounds(0.5, 0.9)
            )
            self.assertFalse(any("coverage" in w for w in warnings), (coverage, warnings))


class BorderHuggingTests(unittest.TestCase):
    def test_outline_on_the_border_is_flagged(self):
        points = [[0.0, 0.1], [0.0, 0.5], [1.0, 0.5], [0.5, 1.0], [0.5, 0.5]]
        warnings = CHECKS._silhouette_plausibility_warnings(
            _outline(0.30, points), _bounds(0.5, 0.5)
        )
        self.assertTrue(any("border" in w for w in warnings), warnings)

    def test_interior_outline_is_not_flagged(self):
        points = [[0.3, 0.3], [0.7, 0.3], [0.7, 0.7], [0.3, 0.7]]
        warnings = CHECKS._silhouette_plausibility_warnings(
            _outline(0.30, points), _bounds(0.5, 0.5)
        )
        self.assertFalse(any("border" in w for w in warnings), warnings)

    def test_a_few_border_points_are_tolerated(self):
        points = [[0.0, 0.5]] + [[0.3 + 0.01 * i, 0.4] for i in range(20)]
        warnings = CHECKS._silhouette_plausibility_warnings(
            _outline(0.30, points), _bounds(0.5, 0.5)
        )
        self.assertFalse(any("border" in w for w in warnings), warnings)


class NoFalsePositiveTests(unittest.TestCase):
    def test_a_plausible_silhouette_produces_no_warnings(self):
        points = [[0.25 + 0.02 * i, 0.15 + 0.03 * i] for i in range(20)]
        warnings = CHECKS._silhouette_plausibility_warnings(
            _outline(0.42, points), _bounds(0.48, 0.92)
        )
        self.assertEqual([], warnings)

    def test_missing_points_do_not_raise(self):
        warnings = CHECKS._silhouette_plausibility_warnings(
            {"foreground_coverage": 0.3, "points": []}, _bounds(0.5, 0.5)
        )
        self.assertEqual([], warnings)


if __name__ == "__main__":
    unittest.main()
