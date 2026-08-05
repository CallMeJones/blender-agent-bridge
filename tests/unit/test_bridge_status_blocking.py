from __future__ import annotations

import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import mcp_server  # noqa: E402


def _blocked_status(**overrides):
    status = {
        "ok": True,
        "mcp_tool_surface": "gateway",
        "compatibility_message": "MCP config and runtime tool registry digests differ",
        "blocked": True,
        "blocking_issues": [
            {
                "code": "config_registry_mismatch",
                "message": "The MCP client config was generated for a different tool registry than the running server.",
                "remedy": "Press Copy MCP Config in the Blender sidebar, paste it into the client config, then restart the MCP client.",
            }
        ],
    }
    status.update(overrides)
    return status


class BlockingIssueSummaryTests(unittest.TestCase):
    """A reachable-but-unusable bridge must not read as healthy.

    The failure this guards against: status reports "connected", read-only
    calls succeed, and the caller only learns otherwise when their first
    mutating call is refused.
    """

    def test_blocked_status_does_not_lead_with_connected(self):
        content = mcp_server._bridge_status_content(_blocked_status())
        self.assertFalse(content.startswith("Blender bridge is connected"))

    def test_blocked_status_leads_with_the_blocker(self):
        content = mcp_server._bridge_status_content(_blocked_status())
        self.assertTrue(content.startswith("BLOCKED:"), content[:80])

    def test_blocked_summary_names_the_remedy(self):
        content = mcp_server._bridge_status_content(_blocked_status())
        self.assertIn("Copy MCP Config", content)
        self.assertIn("restart the MCP client", content)

    def test_blocked_summary_warns_that_read_only_still_works(self):
        content = mcp_server._bridge_status_content(_blocked_status())
        self.assertIn("Read-only inspection still works", content)

    def test_healthy_status_is_unchanged(self):
        healthy = {
            "ok": True,
            "mcp_tool_surface": "gateway",
            "compatibility_message": "Bridge protocol and canonical tool registry are compatible.",
            "blocked": False,
            "blocking_issues": [],
            "external_script_trust_status": "External script trust active",
        }
        content = mcp_server._bridge_status_content(healthy)
        self.assertTrue(content.startswith("Blender bridge is connected."))
        self.assertIn("compatible", content)

    def test_missing_blocking_fields_are_tolerated(self):
        # Older bridges will not report the new fields.
        content = mcp_server._bridge_status_content({"ok": True, "mcp_tool_surface": "gateway"})
        self.assertTrue(content.startswith("Blender bridge is connected."))

    def test_unavailable_bridge_still_reports_unavailable(self):
        content = mcp_server._bridge_status_content({"ok": False, "message": "connection refused"})
        self.assertIn("unavailable", content)

    def test_every_blocking_issue_carries_a_remedy(self):
        status = _blocked_status(
            blocking_issues=[
                {"code": "a", "message": "Thing A broke.", "remedy": "Do X."},
                {"code": "b", "message": "Thing B broke.", "remedy": "Do Y."},
            ]
        )
        content = mcp_server._bridge_status_content(status)
        for token in ("Thing A broke.", "Do X.", "Thing B broke.", "Do Y."):
            self.assertIn(token, content)


class StatusSchemaTests(unittest.TestCase):
    def test_schema_declares_the_new_fields(self):
        schema = mcp_server.BRIDGE_STATUS_SCHEMA if hasattr(mcp_server, "BRIDGE_STATUS_SCHEMA") else None
        if schema is None:
            self.skipTest("bridge status schema is not exposed as a module constant")
        properties = schema.get("properties", {})
        self.assertIn("blocked", properties)
        self.assertIn("blocking_issues", properties)


if __name__ == "__main__":
    unittest.main()
