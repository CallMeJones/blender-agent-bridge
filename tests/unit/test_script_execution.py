from __future__ import annotations

import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "addon"))


from claude_blender import script_execution  # noqa: E402


class ScriptExecutionStatusTests(unittest.TestCase):
    def test_attempted_run_reports_active_trust(self):
        status = script_execution.status_fields(
            {"auto_run_attempted": True, "auto_ran": True, "code": "script_ran"}
        )
        self.assertEqual("external_script_trust_active", status["auto_run_reason"])
        self.assertEqual("", status["auto_run_skipped_reason"])
        self.assertTrue(status["auto_run_attempted"])
        self.assertTrue(status["auto_ran"])

    def test_trust_refusal_preserves_compatibility_reason(self):
        status = script_execution.status_fields({"code": "script_trust_required"})
        self.assertEqual("external_script_trust_required", status["auto_run_reason"])
        self.assertEqual("script_trust_required", status["auto_run_skipped_reason"])

    def test_operational_failure_reports_its_exact_code(self):
        status = script_execution.status_fields({"code": "invalid_script_payload"})
        self.assertEqual("invalid_script_payload", status["auto_run_reason"])
        self.assertEqual("invalid_script_payload", status["auto_run_skipped_reason"])

    def test_empty_or_invalid_result_is_not_attempted(self):
        for result in (None, {}, "not a result"):
            with self.subTest(result=result):
                status = script_execution.status_fields(result)
                self.assertEqual("not_attempted", status["auto_run_reason"])
                self.assertEqual("not_attempted", status["auto_run_skipped_reason"])
                self.assertEqual(
                    script_execution.AUTHORIZATION_MODEL,
                    status["authorization_model"],
                )


if __name__ == "__main__":
    unittest.main()
