from __future__ import annotations

import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
ORCHESTRATOR = ROOT / "scripts" / "installed_extension_live_smoke.py"
STARTUP_FIXTURE = ROOT / "scripts" / "installed_extension_startup.py"


class InstalledExtensionSmokeArchitectureTests(unittest.TestCase):
    def test_blender_startup_program_is_a_separate_compilable_fixture(self):
        orchestrator = ORCHESTRATOR.read_text(encoding="utf-8")
        fixture = STARTUP_FIXTURE.read_text(encoding="utf-8")

        ast.parse(orchestrator, filename=str(ORCHESTRATOR))
        ast.parse(fixture, filename=str(STARTUP_FIXTURE))
        self.assertNotIn("def run_interactive_ui_smoke():", orchestrator)
        self.assertIn("def run_interactive_ui_smoke():", fixture)
        self.assertIn(
            'startup_path = SCRIPTS / "installed_extension_startup.py"',
            orchestrator,
        )


if __name__ == "__main__":
    unittest.main()
