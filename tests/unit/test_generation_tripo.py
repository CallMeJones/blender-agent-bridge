from __future__ import annotations

import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import generation_tripo as gt  # noqa: E402


class TripoPolicyTests(unittest.TestCase):
    def test_default_standard_texture_job_costs_30(self):
        resolved = gt.resolve_job_policy({})
        self.assertEqual("v3.1-20260211", resolved["options"]["model"])
        self.assertTrue(resolved["options"]["texture"])
        self.assertEqual(30.0, resolved["estimated_credits"])

    def test_p1_pricing_is_40_untextured_and_50_textured(self):
        self.assertEqual(
            40.0,
            gt.resolve_job_policy({"model": "P1-20260311", "texture": False})["estimated_credits"],
        )
        self.assertEqual(
            50.0,
            gt.resolve_job_policy({"model": "P1-20260311", "texture": True})["estimated_credits"],
        )

    def test_non_p1_untextured_job_costs_20(self):
        resolved = gt.resolve_job_policy({"model": "v3.1-20260211", "texture": False})
        self.assertEqual(20.0, resolved["estimated_credits"])

    def test_p1_face_limit_uses_provider_range(self):
        with self.assertRaisesRegex(ValueError, "between 48 and 20000"):
            gt.normalize_job_options({"model": "P1-20260311", "face_limit": 20001})

    def test_unknown_model_is_rejected_before_approval(self):
        with self.assertRaisesRegex(ValueError, "Unknown Tripo model"):
            gt.normalize_job_options({"model": "future-model"})


if __name__ == "__main__":
    unittest.main()
