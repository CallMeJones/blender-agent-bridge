from __future__ import annotations

import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
ORCHESTRATOR = ROOT / "scripts" / "installed_extension_live_smoke.py"
STARTUP_FIXTURE = ROOT / "scripts" / "installed_extension_startup.py"
LIVE_BRIDGE_SMOKE = ROOT / "scripts" / "live_bridge_smoke.py"
WORKFLOW = ROOT / ".github" / "workflows" / "mcp-smoke.yml"


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

    def test_headless_ci_skips_only_display_dependent_capture(self):
        orchestrator = ORCHESTRATOR.read_text(encoding="utf-8")
        live_bridge = LIVE_BRIDGE_SMOKE.read_text(encoding="utf-8")
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn('parser.add_argument("--skip-viewport", action="store_true")', live_bridge)
        self.assertIn('if args.skip_viewport:', orchestrator)
        self.assertIn('bridge_smoke.append("--skip-viewport")', orchestrator)
        self.assertIn("python3 -m pip install uv", workflow)
        self.assertIn("--skip-viewport", workflow)
        self.assertIn("--skip-playblast", workflow)


if __name__ == "__main__":
    unittest.main()
