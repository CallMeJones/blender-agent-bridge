from __future__ import annotations

import os
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
os.sys.path.insert(0, str(ROOT / "addon"))

from claude_blender import execution_traces, quality_benchmarks, quality_reviews  # noqa: E402


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

        finished = quality_benchmarks.finish_run(
            run_id,
            outcome="completed",
            quality_review_id=review_id,
        )
        self.assertTrue(finished["expectations_passed"])
        expectation = finished["run"]["expectation_result"]
        self.assertTrue(expectation["quality_review_terminal"])
        self.assertTrue(expectation["quality_review_link_matches_run"])


if __name__ == "__main__":
    unittest.main()
