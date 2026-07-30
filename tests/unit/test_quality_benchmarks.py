from __future__ import annotations

import os
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
os.sys.path.insert(0, str(ROOT / "addon"))

from claude_blender import (  # noqa: E402
    execution_traces,
    quality_benchmarks,
    quality_reviews,
    reference_benchmarks,
)


class QualityBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.trace_dir = pathlib.Path(self.temp_dir.name, "traces")
        self.run_dir = pathlib.Path(self.temp_dir.name, "runs")
        self.review_dir = pathlib.Path(self.temp_dir.name, "reviews")
        self.env = mock.patch.dict(
            os.environ,
            {execution_traces.TRACE_ROOT_ENV: str(self.trace_dir)},
        )
        self.root_patch = mock.patch.object(
            quality_benchmarks,
            "_root",
            side_effect=lambda create=False: str(self.run_dir),
        )
        self.review_root_patch = mock.patch.object(
            quality_reviews,
            "_root",
            side_effect=lambda create=False: str(self.review_dir),
        )
        self.env.start()
        self.root_patch.start()
        self.review_root_patch.start()

    def tearDown(self):
        self.review_root_patch.stop()
        self.root_patch.stop()
        self.env.stop()
        self.temp_dir.cleanup()

    def test_animation_negative_route_detects_model_quality_planner(self):
        started = quality_benchmarks.start_run(
            task_id="animation_wave_negative_routing",
            client_name="unit",
            model_name="test",
        )
        run_id = started["run"]["run_id"]
        execution_traces.record_tool_call(
            layer="bridge",
            tool_name="plan_animation_workflow",
            arguments={"prompt": "Animate this character waving"},
            result={"ok": True},
            contract={"mutates_scene": False},
        )
        execution_traces.record_tool_call(
            layer="bridge",
            tool_name="plan_model_quality_workflow",
            arguments={"prompt": "Animate this character waving"},
            result={"ok": True},
            contract={"mutates_scene": False},
        )

        finished = quality_benchmarks.finish_run(run_id, outcome="completed")
        self.assertFalse(finished["expectations_passed"])
        self.assertEqual(
            ["plan_model_quality_workflow"],
            finished["run"]["expectation_result"]["forbidden_tools_seen"],
        )

    def test_fresh_gateway_task_passes_after_non_top_level_helper_invocation(self):
        started = quality_benchmarks.start_run(
            task_id="fresh_gateway_execution",
            client_name="unit",
            model_name="test",
        )
        run_id = started["run"]["run_id"]
        execution_traces.record_tool_call(
            layer="bridge",
            tool_name="list_scene_objects",
            arguments={},
            result={"ok": True, "objects": []},
            contract={"mutates_scene": False},
        )
        finished = quality_benchmarks.finish_run(
            run_id,
            outcome="completed",
            token_usage={"input_tokens": 10, "output_tokens": 5},
        )
        self.assertTrue(finished["expectations_passed"])
        self.assertEqual(
            {"input_tokens": 10, "output_tokens": 5},
            finished["trace"]["provided_token_usage"],
        )

    def test_reference_task_fingerprints_local_input_and_requires_linked_terminal_review(self):
        reference_path = pathlib.Path(self.temp_dir.name, "reference.png")
        reference_path.write_bytes(b"stable-reference-fixture")
        started = quality_benchmarks.start_run(
            task_id="reference_cartoon_animal",
            client_name="unit",
            model_name="test",
            reference_uri=str(reference_path),
        )
        identity = started["run"]["reference_identity"]
        self.assertTrue(identity["reproducible"])
        self.assertEqual("local_file", identity["fingerprint_source"])
        self.assertEqual(64, len(identity["sha256"]))

        finished = quality_benchmarks.finish_run(
            started["run"]["run_id"],
            outcome="completed",
        )
        expectation = finished["run"]["expectation_result"]
        self.assertFalse(finished["expectations_passed"])
        self.assertTrue(expectation["reference_reproducible"])
        self.assertTrue(expectation["quality_review_required"])
        self.assertFalse(expectation["quality_review_terminal"])
        self.assertFalse(expectation["quality_review_link_matches_run"])
        self.assertFalse(expectation["reference_metric_state_valid"])

    def test_reference_task_passes_with_fingerprinted_input_and_linked_review(self):
        reference_path = pathlib.Path(self.temp_dir.name, "linked-reference.png")
        reference_path.write_bytes(b"linked-reference-fixture")
        started = quality_benchmarks.start_run(
            task_id="reference_hard_surface_product",
            client_name="unit",
            model_name="test",
            reference_uri=str(reference_path),
        )
        run_id = started["run"]["run_id"]
        reference_identity = started["run"]["reference_identity"]
        review = quality_reviews.create_review(
            reference_brief={
                "subject": "product",
                "silhouette": ["wide body"],
                "primary_masses": ["body"],
                "proportion_checks": ["width is twice height"],
            },
            rubric=[
                {
                    "criterion": "silhouette_match",
                    "applies": True,
                    "target": "Outline matches",
                    "repair_action": "Adjust body",
                    "evidence_from_brief": ["wide body"],
                }
            ],
            evidence_uris=["blender://evidence/front"],
            quality_floor=4,
            benchmark_run_id=run_id,
        )
        review_id = review["review"]["review_id"]
        quality_reviews.submit_evaluation(
            review_id,
            scores=[
                {
                    "criterion": "silhouette_match",
                    "score": 4,
                    "evidence": ["blender://evidence/front"],
                    "finding": "Outline matches",
                    "repair_action": "No repair needed",
                }
            ],
        )
        for tool_name in (
            "plan_model_quality_workflow",
            "draft_script",
            "submit_model_quality_evaluation",
        ):
            execution_traces.record_tool_call(
                layer="bridge",
                tool_name=tool_name,
                arguments={},
                result={"ok": True},
                contract={"mutates_scene": tool_name == "draft_script"},
            )
        passing_metrics = {
            "width": 100,
            "height": 100,
            "silhouette_iou": 0.95,
            "mean_edge_distance_normalized": 0.005,
            "p95_edge_distance_pixels": 1.0,
            "centroid_offset": {
                "dx_pixels": 0.0,
                "dy_pixels": 0.0,
            },
            "error_regions": [],
        }
        evaluation = reference_benchmarks.evaluate_comparison(
            passing_metrics,
            [{"name": "center", "distance_pixels": 0.0}],
            profile="review",
        )
        recorded = quality_benchmarks.record_reference_evaluation(
            run_id,
            evaluation=evaluation,
            comparison_id="comparison-fixture",
            metadata_uri="blender://inspection-renders/comparison-fixture/metadata",
            reference_identity=reference_identity,
        )
        self.assertTrue(recorded["ok"])
        self.assertTrue(
            quality_benchmarks._evaluate_expectations(
                quality_benchmarks._read(run_id)
            )["reference_metric_state_valid"]
        )

        overridden = reference_benchmarks.evaluate_comparison(
            passing_metrics,
            [{"name": "center", "distance_pixels": 0.0}],
            profile="review",
            threshold_overrides={"min_silhouette_iou": 0.8},
        )
        self.assertTrue(overridden["passed"])
        self.assertTrue(overridden["threshold_overrides_applied"])
        overridden_recorded = quality_benchmarks.record_reference_evaluation(
            run_id,
            evaluation=overridden,
            comparison_id="custom-threshold-fixture",
            metadata_uri="blender://inspection-renders/custom-threshold-fixture/metadata",
            reference_identity=reference_identity,
        )
        self.assertTrue(overridden_recorded["ok"])
        self.assertFalse(
            quality_benchmarks._evaluate_expectations(
                quality_benchmarks._read(run_id)
            )["reference_metric_state_valid"]
        )

        failed_evaluation = reference_benchmarks.evaluate_comparison(
            passing_metrics
            | {
                "silhouette_iou": 0.5,
                "mean_edge_distance_normalized": 0.1,
                "p95_edge_distance_pixels": 20.0,
            },
            [{"name": "center", "distance_pixels": 20.0}],
            profile="review",
        )
        failed_recorded = quality_benchmarks.record_reference_evaluation(
            run_id,
            evaluation=failed_evaluation,
            comparison_id="later-regression-fixture",
            metadata_uri="blender://inspection-renders/later-regression-fixture/metadata",
            reference_identity=reference_identity,
        )
        self.assertTrue(failed_recorded["ok"])
        self.assertFalse(
            quality_benchmarks._evaluate_expectations(
                quality_benchmarks._read(run_id)
            )["reference_metric_state_valid"]
        )

        final_recorded = quality_benchmarks.record_reference_evaluation(
            run_id,
            evaluation=evaluation,
            comparison_id="final-passing-fixture",
            metadata_uri="blender://inspection-renders/final-passing-fixture/metadata",
            reference_identity=reference_identity,
        )
        self.assertTrue(final_recorded["ok"])

        finished = quality_benchmarks.finish_run(
            run_id,
            outcome="completed",
            quality_review_id=review_id,
        )
        self.assertTrue(finished["expectations_passed"])
        expectation = finished["run"]["expectation_result"]
        self.assertTrue(expectation["quality_review_terminal"])
        self.assertTrue(expectation["quality_review_link_matches_run"])
        self.assertTrue(expectation["reference_metric_state_valid"])
        self.assertTrue(expectation["latest_reference_evaluation_passed"])
        self.assertEqual(
            "review",
            expectation["latest_reference_evaluation_profile"],
        )
        self.assertFalse(
            expectation[
                "latest_reference_evaluation_used_custom_thresholds"
            ]
        )
        self.assertTrue(
            expectation["latest_reference_evaluation_has_evidence"]
        )
        self.assertEqual(4, expectation["reference_evaluation_count"])

    def test_reference_evaluation_rejects_a_different_reference_image(self):
        reference_path = pathlib.Path(self.temp_dir.name, "expected.png")
        reference_path.write_bytes(b"expected-reference")
        started = quality_benchmarks.start_run(
            task_id="reference_cartoon_animal",
            reference_uri=str(reference_path),
        )
        run = started["run"]
        mismatch = quality_benchmarks.validate_reference_identity(
            run,
            {"sha256": "a" * 64, "size_bytes": 20},
        )

        self.assertFalse(mismatch["ok"])
        self.assertEqual(
            "benchmark_reference_identity_mismatch",
            mismatch["code"],
        )


if __name__ == "__main__":
    unittest.main()
