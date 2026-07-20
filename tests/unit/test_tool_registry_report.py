from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ADDON = os.path.join(ROOT, "addon")
sys.path.insert(0, ADDON)

from claude_blender import tool_registry  # noqa: E402
from claude_blender.tool_registry.report import (  # noqa: E402
    build_registry_report,
    render_registry_report,
)


class ToolRegistryReportTests(unittest.TestCase):
    def test_report_counts_canonical_registry(self):
        report = build_registry_report(tool_registry.REGISTRY)

        self.assertEqual(1, report["schema_version"])
        self.assertEqual(186, report["tool_count"])
        self.assertEqual(tool_registry.TOOL_REGISTRY_DIGEST, report["registry_digest"])
        self.assertEqual(
            {"catalog": 161, "compact_direct": 24, "internal": 1},
            {row["name"]: row["tool_count"] for row in report["exposures"]},
        )
        self.assertEqual(report["tool_count"], sum(row["tool_count"] for row in report["owners"]))
        self.assertEqual(report["tool_count"], sum(row["tool_count"] for row in report["exposures"]))

    def test_report_sections_have_stable_ordering(self):
        report = build_registry_report(tool_registry.REGISTRY)

        for section in ("owners", "groups", "exposures"):
            names = [row["name"] for row in report[section]]
            self.assertEqual(sorted(names), names)
        self.assertEqual(
            render_registry_report(tool_registry.REGISTRY),
            render_registry_report(tool_registry.REGISTRY),
        )

    def test_module_cli_emits_json_without_importing_bpy(self):
        environment = dict(os.environ)
        environment["PYTHONPATH"] = ADDON
        command = (
            "import sys; "
            "from claude_blender.tool_registry import report; "
            "assert report.main() == 0; "
            "assert 'bpy' not in sys.modules"
        )
        completed = subprocess.run(
            [sys.executable, "-c", command],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(186, payload["tool_count"])


if __name__ == "__main__":
    unittest.main()
