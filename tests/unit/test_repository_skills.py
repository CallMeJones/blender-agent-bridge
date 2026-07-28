from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = ROOT / "skills"


class RepositorySkillTests(unittest.TestCase):
    def test_expected_skill_pack_is_complete(self):
        expected = {
            "blender-bridge": (
                "gateway.md",
                "preview-and-trust.md",
                "diagnostics-and-recovery.md",
            ),
            "blender-reference-modeling": (
                "reference-brief.md",
                "guide-first-workflow.md",
                "evidence-review.md",
                "repair-loop.md",
            ),
        }
        for skill_name, references in expected.items():
            skill_dir = SKILLS_ROOT / skill_name
            self.assertTrue((skill_dir / "SKILL.md").is_file(), skill_name)
            self.assertTrue((skill_dir / "agents" / "openai.yaml").is_file(), skill_name)
            for reference in references:
                self.assertTrue((skill_dir / "references" / reference).is_file(), reference)

    def test_skill_metadata_and_ui_prompts_are_valid_and_compact(self):
        for skill_dir in SKILLS_ROOT.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
            match = re.match(r"^---\n(.*?)\n---\n", skill_text, flags=re.DOTALL)
            self.assertIsNotNone(match, skill_dir.name)
            frontmatter = match.group(1)
            self.assertEqual(
                [line.split(":", 1)[0] for line in frontmatter.splitlines()],
                ["name", "description"],
                skill_dir.name,
            )
            self.assertIn(f"name: {skill_dir.name}", frontmatter)
            self.assertLess(len(skill_text.splitlines()), 500, skill_dir.name)

            ui_text = (skill_dir / "agents" / "openai.yaml").read_text(encoding="utf-8")
            self.assertIn("display_name:", ui_text, skill_dir.name)
            self.assertIn("short_description:", ui_text, skill_dir.name)
            self.assertIn(f"${skill_dir.name}", ui_text, skill_dir.name)

    def test_bridge_skill_names_exact_five_tool_surface(self):
        gateway_text = (
            SKILLS_ROOT / "blender-bridge" / "references" / "gateway.md"
        ).read_text(encoding="utf-8")
        for tool_name in (
            "blender_bridge_status",
            "blender_tool_catalog",
            "search_blender_tools",
            "get_blender_tool_schema",
            "invoke_blender_tool",
        ):
            self.assertIn(f"`{tool_name}`", gateway_text)
        self.assertIn("Top-level omission is a token optimization", gateway_text)
        self.assertIn("Fetch one selected schema at a time", gateway_text)

    def test_reference_modeling_skill_has_no_canned_subject_geometry(self):
        skill_dir = SKILLS_ROOT / "blender-reference-modeling"
        combined = "\n".join(
            path.read_text(encoding="utf-8").lower()
            for path in sorted(skill_dir.rglob("*.md"))
        )
        for canned_term in (
            "muzzle",
            "front paw",
            "tail curve",
            "chest ruff",
            "ear interior",
            "build_cartoon",
            "animal base",
        ):
            self.assertNotIn(canned_term, combined)
        self.assertIn("plan_model_quality_workflow", combined)
        self.assertIn("structured `reference_brief`", combined)
        self.assertIn("do not use canned category bases", combined)
        self.assertIn("do not invent focal lengths", combined)
        self.assertIn("required entry point", combined)
        self.assertIn("ready_for_user_review", combined)
        self.assertIn("leave the preview pending", combined)

    def test_skills_make_authored_mutation_script_first(self):
        bridge_dir = SKILLS_ROOT / "blender-bridge"
        bridge_text = "\n".join(
            path.read_text(encoding="utf-8").lower()
            for path in sorted(bridge_dir.rglob("*.md"))
        )
        reference_text = "\n".join(
            path.read_text(encoding="utf-8").lower()
            for path in sorted((SKILLS_ROOT / "blender-reference-modeling").rglob("*.md"))
        )
        self.assertIn("prefer one cohesive script for object generation", bridge_text)
        self.assertIn("inspect rna `enum_items`", bridge_text)
        self.assertIn("unless the user explicitly requests helpers", bridge_text)
        self.assertIn("do not let operational suffixes", bridge_text)
        self.assertIn("the mere presence of required operational helpers is not an override", bridge_text)
        self.assertIn(
            "opening, creating, restoring, copying, renaming, saving, or modifying `.blend` files does not change",
            bridge_text,
        )
        self.assertIn("do not fragment the retry into primitive helpers", bridge_text)
        self.assertIn("start_trusted_script_job", bridge_text)
        self.assertIn("start an execution trace", bridge_text)
        self.assertNotIn("fallback after a concrete helper gap", bridge_text)
        self.assertIn("one cohesive reference-derived script", reference_text)
        self.assertIn("does not change the repair execution strategy", reference_text)
        self.assertIn("not an automatic downgrade to primitive-only construction", reference_text)
        self.assertIn("start_model_quality_review", reference_text)
        self.assertIn("fresh blind packet", reference_text)

    def test_skill_references_are_one_level_and_resolve(self):
        for skill_file in SKILLS_ROOT.glob("*/SKILL.md"):
            skill_text = skill_file.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^\]]+\]\(([^)]+\.md)\)", skill_text):
                resolved = (skill_file.parent / target).resolve()
                self.assertTrue(resolved.is_file(), f"{skill_file}: {target}")


if __name__ == "__main__":
    unittest.main()
