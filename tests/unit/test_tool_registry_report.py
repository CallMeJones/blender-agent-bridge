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
from claude_blender.tool_registry.report import build_registry_report  # noqa: E402


class ToolRegistryReportTests(unittest.TestCase):
    def test_report_counts_canonical_registry(self):
        report = build_registry_report(tool_registry.REGISTRY)

        self.assertEqual(1, report["schema_version"])
        self.assertEqual(181, report["tool_count"])
        self.assertEqual(tool_registry.TOOL_REGISTRY_DIGEST, report["registry_digest"])
        self.assertEqual(
            {"catalog": 157, "compact_direct": 23, "internal": 1},
            {row["name"]: row["tool_count"] for row in report["exposures"]},
        )
        self.assertEqual(report["tool_count"], sum(row["tool_count"] for row in report["owners"]))
        self.assertEqual(report["tool_count"], sum(row["tool_count"] for row in report["exposures"]))

    def test_report_sections_have_stable_ordering(self):
        report = build_registry_report(tool_registry.REGISTRY)

        for section in ("owners", "groups", "exposures"):
            names = [row["name"] for row in report[section]]
            self.assertEqual(sorted(names), names)

    def test_render_is_stable_across_process_hash_seeds(self):
        outputs = {}
        for hash_seed in ("1", "2", "random"):
            environment = dict(os.environ)
            environment["PYTHONPATH"] = ADDON
            environment["PYTHONHASHSEED"] = hash_seed
            completed = subprocess.run(
                [sys.executable, "-m", "claude_blender.tool_registry.report"],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            outputs[hash_seed] = completed.stdout

        expected = outputs["1"]
        for hash_seed, output in outputs.items():
            self.assertEqual(expected, output, f"output changed for PYTHONHASHSEED={hash_seed}")
        self.assertEqual(build_registry_report(tool_registry.REGISTRY), json.loads(expected))

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
            timeout=10,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(181, payload["tool_count"])


if __name__ == "__main__":
    unittest.main()
