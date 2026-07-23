from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class BinaryTrustDocumentationTests(unittest.TestCase):
    def test_public_security_and_privacy_docs_match_binary_trust(self):
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        privacy = (ROOT / "PRIVACY.md").read_text(encoding="utf-8")
        combined = f"{security}\n{privacy}".lower()

        for stale_phrase in (
            "approved inside blender before execution",
            "runtime external script trust presets",
            "only for staged scripts",
            "pending scripts, script logs, and repair context",
            "use `reject` for unwanted pending python",
        ):
            self.assertNotIn(stale_phrase, combined)

        for required_phrase in (
            "trust agent scripts",
            "blender's **run script** command",
            "filesystem",
            "network",
            "subprocess",
            "static script checks are advisory",
            "any local client",
            "**revoke**",
        ):
            self.assertIn(required_phrase, combined)

    def test_live_agent_guidance_does_not_restore_staging_language(self):
        guidance = (ROOT / "addon" / "claude_blender" / "agent_tools.py").read_text(encoding="utf-8").lower()
        handler = (
            ROOT
            / "addon"
            / "claude_blender"
            / "tool_handlers"
            / "scripts_transactions.py"
        ).read_text(encoding="utf-8").lower()

        self.assertNotIn("stage one cohesive blender python script", guidance)
        self.assertNotIn("from staging alone", guidance)
        self.assertNotIn('"staged": run_result.get("prepared")', handler)

    def test_current_binary_trust_guides_do_not_claim_script_staging(self):
        guide_paths = (
            "README.md",
            "SECURITY.md",
            "PRIVACY.md",
            "docs/ARCHITECTURE.md",
            "docs/EXTERNAL_BRIDGE_MCP.md",
            "docs/LIVE_PREVIEW_LOOP.md",
            "docs/SAFETY_MODEL.md",
        )
        combined = "\n".join(
            (ROOT / relative_path).read_text(encoding="utf-8").lower()
            for relative_path in guide_paths
        )

        self.assertNotIn("without staging", combined)
        self.assertNotIn("staged scripts", combined)


if __name__ == "__main__":
    unittest.main()
