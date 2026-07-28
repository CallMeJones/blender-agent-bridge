from __future__ import annotations

import os
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
os.sys.path.insert(0, str(ROOT / "addon"))

from claude_blender import quality_reviews  # noqa: E402


BRIEF = {
    "subject": "test product",
    "silhouette": ["wide body"],
    "primary_masses": ["body"],
    "proportion_checks": ["width is twice height"],
}
RUBRIC = [
    {
        "criterion": "silhouette_match",
        "applies": True,
        "target": "Outline matches",
        "repair_action": "Adjust body",
        "evidence_from_brief": ["wide body"],
    },
    {
        "criterion": "proportion_match",
        "applies": True,
        "target": "Ratio matches",
        "repair_action": "Scale body",
        "evidence_from_brief": ["width is twice height"],
    },
]


def scorecard(silhouette, proportion):
    return [
        {
            "criterion": "silhouette_match",
            "score": silhouette,
            "evidence": ["blender://evidence/front"],
            "finding": "Compared front outline",
            "repair_action": "Adjust body width",
        },
        {
            "criterion": "proportion_match",
            "score": proportion,
            "evidence": ["blender://evidence/front"],
            "finding": "Compared width-height ratio",
            "repair_action": "Scale body",
        },
    ]


class QualityReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_patch = mock.patch.object(
            quality_reviews,
            "_root",
            side_effect=lambda create=False: self.temp_dir.name,
        )
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.temp_dir.cleanup()

    def create_review(self, max_repair_passes=2):
        result = quality_reviews.create_review(
            reference_brief=BRIEF,
            rubric=RUBRIC,
            target_objects=["Product"],
            evidence_uris=["blender://evidence/front"],
            quality_floor=4,
            max_repair_passes=max_repair_passes,
        )
        self.assertTrue(result["ok"])
        return result["review"]["review_id"]

    def test_review_requires_complete_scorecard_and_recorded_repairs(self):
        review_id = self.create_review()
        incomplete = quality_reviews.submit_evaluation(
            review_id,
            scores=scorecard(3, 4)[:1],
        )
        self.assertFalse(incomplete["ok"])
        self.assertEqual("invalid_quality_scorecard", incomplete["code"])

        failed = quality_reviews.submit_evaluation(review_id, scores=scorecard(3, 4))
        self.assertEqual("repair_required", failed["review"]["status"])
        premature = quality_reviews.submit_evaluation(review_id, scores=scorecard(4, 4))
        self.assertEqual("quality_repair_must_be_recorded", premature["code"])

        repaired = quality_reviews.record_repair(
            review_id,
            repairs=[
                {
                    "criterion": "silhouette_match",
                    "action": "Scaled body width",
                    "result": "Matched front outline",
                }
            ],
            evidence_uris=["blender://evidence/front-repaired"],
        )
        self.assertTrue(repaired["ok"])
        self.assertTrue(repaired["next_packet"]["blind_packet"])
        self.assertNotIn("prior_evaluations", repaired["next_packet"])

        passed = quality_reviews.submit_evaluation(review_id, scores=scorecard(4, 5))
        self.assertEqual("ready_for_user_review", passed["review"]["status"])
        self.assertTrue(passed["commit_allowed"])
        self.assertTrue(passed["must_leave_preview_pending"])

    def test_review_blocks_after_bounded_repair_limit(self):
        review_id = self.create_review(max_repair_passes=1)
        quality_reviews.submit_evaluation(review_id, scores=scorecard(2, 4))
        quality_reviews.record_repair(
            review_id,
            repairs=[{"criterion": "silhouette_match", "action": "Adjusted body"}],
            evidence_uris=["blender://evidence/front-repaired"],
        )
        blocked = quality_reviews.submit_evaluation(review_id, scores=scorecard(3, 4))
        self.assertEqual("blocked_quality_floor", blocked["review"]["status"])
        self.assertFalse(blocked["commit_allowed"])

    def test_zero_repairs_blocks_immediately_and_repairs_need_fresh_evidence(self):
        no_repairs_id = self.create_review(max_repair_passes=0)
        blocked = quality_reviews.submit_evaluation(
            no_repairs_id,
            scores=scorecard(3, 4),
        )
        self.assertEqual("blocked_quality_floor", blocked["review"]["status"])

        review_id = self.create_review(max_repair_passes=2)
        quality_reviews.submit_evaluation(review_id, scores=scorecard(3, 4))
        wrong_criterion = quality_reviews.record_repair(
            review_id,
            repairs=[{"criterion": "proportion_match", "action": "Changed ratio"}],
            evidence_uris=["blender://evidence/front-repaired"],
        )
        self.assertEqual("quality_repairs_required", wrong_criterion["code"])
        no_evidence = quality_reviews.record_repair(
            review_id,
            repairs=[{"criterion": "silhouette_match", "action": "Changed outline"}],
        )
        self.assertEqual("quality_repair_evidence_required", no_evidence["code"])


if __name__ == "__main__":
    unittest.main()
