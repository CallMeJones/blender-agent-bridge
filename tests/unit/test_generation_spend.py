from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import generation_spend  # noqa: E402


class GenerationSpendTests(unittest.TestCase):
    def setUp(self):
        generation_spend.clear_requests()

    def tearDown(self):
        generation_spend.clear_requests()

    def test_request_state_reports_ui_decisions(self):
        with mock.patch.object(generation_spend.time, "time", return_value=100.0):
            request = generation_spend.request_approval("tripo", "fingerprint")
            state = generation_spend.request_state(request["request_id"])
        self.assertEqual(generation_spend.STATUS_PENDING, state["status"])

        with mock.patch.object(generation_spend.time, "time", return_value=101.0):
            generation_spend.set_status(request["request_id"], generation_spend.STATUS_APPROVED)
            state = generation_spend.request_state(request["request_id"])
        self.assertEqual(generation_spend.STATUS_APPROVED, state["status"])
        self.assertEqual(101.0, state["decided_at"])

    def test_approved_request_expires_before_it_can_be_consumed(self):
        with mock.patch.object(generation_spend.time, "time", return_value=100.0):
            request = generation_spend.request_approval("tripo", "fingerprint")
            generation_spend.set_status(request["request_id"], generation_spend.STATUS_APPROVED)
        with mock.patch.object(generation_spend.time, "time", return_value=701.0):
            self.assertEqual(
                generation_spend.STATUS_EXPIRED,
                generation_spend.request_state(request["request_id"])["status"],
            )
            self.assertFalse(generation_spend.consume_approval("fingerprint"))

    def test_paid_texture_choice_changes_the_fingerprint(self):
        base = {"views": {"front": "front.png"}, "model": "model", "face_limit": 1000}
        without_texture = generation_spend.job_fingerprint("tripo", {**base, "texture": False})
        with_texture = generation_spend.job_fingerprint("tripo", {**base, "texture": True})
        self.assertNotEqual(without_texture, with_texture)

    def test_replacing_image_bytes_at_the_same_path_changes_the_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "front.png")
            with open(path, "wb") as handle:
                handle.write(b"\x89PNG\r\n\x1a\nfirst")
            before = generation_spend.job_fingerprint("tripo", {"views": {"front": path}})
            with open(path, "wb") as handle:
                handle.write(b"\x89PNG\r\n\x1a\nsecond")
            after = generation_spend.job_fingerprint("tripo", {"views": {"front": path}})
        self.assertNotEqual(before, after)

    def test_every_meshy_output_choice_is_bound_to_the_fingerprint(self):
        base = {
            "views": {"front": "front.png"},
            "meshy_options": {
                "preset": "blender_working",
                "ai_model": "meshy-7",
                "texture_resolution": "4k",
                "target_polycount": 100000,
            },
            "estimated_cost": 30,
        }
        original = generation_spend.job_fingerprint("meshy", base)
        changed = {
            **base,
            "meshy_options": {**base["meshy_options"], "texture_resolution": "8k"},
            "estimated_cost": 35,
        }
        self.assertNotEqual(original, generation_spend.job_fingerprint("meshy", changed))

    def test_meshy_approval_exposes_exact_cost_preset_and_reference_names(self):
        request = generation_spend.request_approval(
            "meshy",
            "fingerprint",
            reference_files=["front.png", "rear.png"],
            reference_details=[
                {
                    "view": "front",
                    "path": "C:/references/front.png",
                    "bytes": 1048576,
                    "format": "png",
                    "sha256": "a" * 64,
                },
                {
                    "view": "rear",
                    "path": "C:/references/rear.png",
                    "bytes": 2048,
                    "format": "png",
                    "sha256": "b" * 64,
                },
            ],
            estimated_credits=35,
            options_summary="blender_working",
        )
        self.assertEqual(["front.png", "rear.png"], request["reference_files"])
        self.assertEqual("front", request["reference_details"][0]["view"])
        self.assertEqual(1048576, request["reference_details"][0]["bytes"])
        self.assertEqual("a" * 64, request["reference_details"][0]["sha256"])
        self.assertEqual(35, request["estimated_credits"])
        self.assertEqual("blender_working", request["options_summary"])

    def test_unknown_request_is_not_observable(self):
        self.assertIsNone(generation_spend.request_state("missing"))


if __name__ == "__main__":
    unittest.main()
