from __future__ import annotations

import os
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CLIENT_DIR = os.path.join(ROOT, "docs", "clients")
GUIDES = (
    "CODEX.md",
    "CLAUDE.md",
    "CURSOR.md",
    "VSCODE.md",
    "CHATGPT.md",
    "GEMINI.md",
    "OPENCODE.md",
    "OLLAMA.md",
)


class ClientGuideTests(unittest.TestCase):
    def test_every_supported_client_has_complete_dual_runtime_guidance(self):
        for filename in GUIDES:
            with self.subTest(filename=filename):
                path = os.path.join(CLIENT_DIR, filename)
                with open(path, "r", encoding="utf-8") as handle:
                    text = handle.read()
                lowered = text.lower()
                self.assertRegex(text, r"Last verified: 20\d{2}-\d{2}-\d{2}")
                self.assertIn("prerequisite", lowered)
                self.assertIn("bundled", lowered)
                self.assertIn("uvx", lowered)
                self.assertIn("windows", lowered)
                self.assertIn("macos", lowered)
                self.assertIn("linux", lowered)
                self.assertIn("restart", lowered)
                self.assertIn("check blender bridge status, list scene objects, and make no changes", lowered)
                self.assertIn("only one", lowered)
                self.assertIn("official reference", lowered)
                self.assertIn("troubleshoot", lowered)

    def test_matrix_links_every_guide(self):
        with open(os.path.join(CLIENT_DIR, "README.md"), "r", encoding="utf-8") as handle:
            matrix = handle.read()
        for filename in GUIDES:
            self.assertIn(filename, matrix)


if __name__ == "__main__":
    unittest.main()
