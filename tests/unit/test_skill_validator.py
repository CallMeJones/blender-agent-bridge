from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate_repository_skills.py"


def _run_validator(*skill_paths: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *(str(path) for path in skill_paths)],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )


class RepositorySkillValidatorTests(unittest.TestCase):
    def test_all_repository_skills_validate_without_external_client_state(self):
        result = _run_validator()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[OK]", result.stdout)
        self.assertNotIn("CODEX_HOME", result.stdout + result.stderr)

    def test_rejects_unexpected_frontmatter_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir) / "sample-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                "name: sample-skill\n"
                "description: Example skill.\n"
                "metadata: client-specific\n"
                "---\n",
                encoding="utf-8",
            )

            result = _run_validator(skill_dir)

        self.assertEqual(result.returncode, 1)
        self.assertIn("unexpected frontmatter key(s): metadata", result.stderr)

    def test_rejects_directory_name_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir) / "sample-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                "name: different-skill\n"
                "description: Example skill.\n"
                "---\n",
                encoding="utf-8",
            )

            result = _run_validator(skill_dir)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "does not match skill directory 'sample-skill'", result.stderr
        )


if __name__ == "__main__":
    unittest.main()
