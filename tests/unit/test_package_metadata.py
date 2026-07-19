from __future__ import annotations

import os
import sys
import tomllib
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import build_info  # noqa: E402


class PackageMetadataTests(unittest.TestCase):
    def test_distribution_matches_extension_and_has_no_runtime_dependencies(self):
        with open(os.path.join(ROOT, "pyproject.toml"), "rb") as handle:
            project = tomllib.load(handle)["project"]
        self.assertEqual("blender-bridge", project["name"])
        self.assertEqual(build_info.ADDON_VERSION, project["version"])
        self.assertEqual(">=3.10", project["requires-python"])
        self.assertEqual("GPL-3.0-or-later", project["license"])
        self.assertEqual([], project["dependencies"])
        self.assertEqual(
            "claude_blender.mcp_runtime.server:main",
            project["scripts"]["blender-bridge"],
        )

    def test_importing_runtime_does_not_import_bpy(self):
        sys.modules.pop("bpy", None)
        __import__("claude_blender.mcp_runtime.server")
        self.assertNotIn("bpy", sys.modules)


if __name__ == "__main__":
    unittest.main()
