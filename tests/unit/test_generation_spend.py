from __future__ import annotations

import os
import sys
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

    def test_unknown_request_is_not_observable(self):
        self.assertIsNone(generation_spend.request_state("missing"))


if __name__ == "__main__":
    unittest.main()
