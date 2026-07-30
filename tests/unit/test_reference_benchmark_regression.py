from __future__ import annotations

import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import reference_benchmark_regression  # noqa: E402


class ReferenceBenchmarkRegressionTests(unittest.TestCase):
    def test_repository_manifest_matches_expected_gate_outcomes(self):
        report = reference_benchmark_regression.run_manifest(
            reference_benchmark_regression.DEFAULT_MANIFEST
        )

        self.assertTrue(report["ok"])
        self.assertEqual(3, report["case_count"])
        self.assertEqual([], report["failed_case_ids"])
        self.assertTrue(
            all(item["matched_expectation"] for item in report["results"])
        )


if __name__ == "__main__":
    unittest.main()
