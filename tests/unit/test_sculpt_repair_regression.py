from __future__ import annotations

import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))


def _load_module():
    """Import the decision helpers without pulling in bpy.

    reference_image_intake imports bpy at module scope, so the pure decision
    functions are exercised by loading the source in isolation. They are
    deliberately free of Blender types for exactly this reason.
    """

    import types

    path = os.path.join(ROOT, "addon", "claude_blender", "reference_image_intake.py")
    source = open(path, encoding="utf-8").read()
    start = source.index("AGGREGATE_REGRESSION_TOLERANCE")
    end = source.index("def auto_reference_sculpt_repair(")
    module = types.ModuleType("repair_decisions")
    exec(compile(source[start:end], "repair_decisions", "exec"), module.__dict__)
    return module


DECIDE = _load_module()


def _evaluation(score):
    return {"aggregate": {"mean_score": score, "mean_iou": score}}


class AggregateRegressionTests(unittest.TestCase):
    def test_improvement_is_negative_regression(self):
        self.assertLess(DECIDE._aggregate_regression(_evaluation(0.55), _evaluation(0.60)), 0)

    def test_decline_is_positive_regression(self):
        regression = DECIDE._aggregate_regression(_evaluation(0.59), _evaluation(0.55))
        self.assertAlmostEqual(0.04, regression, places=6)

    def test_the_observed_eight_pass_decline_is_rejected(self):
        # Measured trajectory: peaked at 0.5929, ended at 0.5562.
        regression = DECIDE._aggregate_regression(_evaluation(0.5929), _evaluation(0.5562))
        self.assertGreater(regression, DECIDE.AGGREGATE_REGRESSION_TOLERANCE)

    def test_a_marginal_trade_is_tolerated(self):
        regression = DECIDE._aggregate_regression(_evaluation(0.6000), _evaluation(0.5990))
        self.assertLessEqual(regression, DECIDE.AGGREGATE_REGRESSION_TOLERANCE)

    def test_missing_aggregate_does_not_raise(self):
        self.assertEqual(0.0, DECIDE._aggregate_score({}))
        self.assertEqual(0.0, DECIDE._aggregate_score(None))

    def test_falls_back_through_score_keys(self):
        self.assertEqual(0.42, DECIDE._aggregate_score({"aggregate": {"score": 0.42}}))
        self.assertEqual(0.31, DECIDE._aggregate_score({"aggregate": {"mean_iou": 0.31}}))


class ExtentBudgetTests(unittest.TestCase):
    def test_observed_32_percent_growth_exceeds_the_budget(self):
        # Measured: bounding box grew 1.713 -> 2.257 while IoU moved only 4%.
        growth = (2.257 - 1.713) / 1.713
        self.assertGreater(growth, DECIDE.MAXIMUM_REPAIR_EXTENT_GROWTH)

    def test_small_growth_is_within_budget(self):
        growth = (1.75 - 1.713) / 1.713
        self.assertLessEqual(growth, DECIDE.MAXIMUM_REPAIR_EXTENT_GROWTH)

    def test_extent_of_missing_object_is_zero(self):
        self.assertEqual(0.0, DECIDE._object_extent(None))

    def test_extent_reads_largest_dimension(self):
        class _Obj:
            dimensions = (0.42, 0.35, 1.71)

        self.assertAlmostEqual(1.71, DECIDE._object_extent(_Obj()), places=6)

    def test_extent_tolerates_an_object_without_dimensions(self):
        class _Obj:
            pass

        self.assertEqual(0.0, DECIDE._object_extent(_Obj()))


if __name__ == "__main__":
    unittest.main()
