from __future__ import annotations

import json
import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import mcp_server  # noqa: E402


class OfflineBridge:
    base_url = "http://127.0.0.1:9876"

    def get(self, path):
        raise RuntimeError("offline token-budget probe")

    def post(self, path, payload):
        raise RuntimeError("offline token-budget probe")


def payload_chars(value):
    return len(json.dumps(value, separators=(",", ":"), sort_keys=True, default=str))


class MCPTokenBudgetTests(unittest.TestCase):
    def setUp(self):
        self.server = mcp_server.BlenderMCPServer(OfflineBridge())

    def test_default_discovery_preserves_tools_and_input_schemas_within_budget(self):
        tools = self.server.tools_list({})["tools"]
        expected_names = set(mcp_server.WRAPPER_TOOL_NAMES) | set(mcp_server.COMPACT_DIRECT_TOOL_NAMES)

        self.assertEqual(expected_names, {tool["name"] for tool in tools})
        self.assertTrue(all(tool.get("inputSchema", {}).get("type") == "object" for tool in tools))
        self.assertTrue(all("outputSchema" not in tool for tool in tools))
        self.assertLessEqual(payload_chars(tools), 33_000)

        canonical = self.server._get_blender_tool_schema({"name": "start_render_job"})
        self.assertIn("outputSchema", canonical["structuredContent"]["tool"])

    def test_default_catalog_search_preserves_results_within_budget(self):
        result = self.server._search_catalog({"query": "material"})
        structured = result["structuredContent"]
        content = result["content"][0]["text"]

        self.assertEqual(12, structured["count"])
        self.assertFalse(structured["include_schemas"])
        self.assertTrue(all(tool["name"] in content for tool in structured["tools"]))
        self.assertIn("get_blender_tool_schema", content)
        self.assertLessEqual(payload_chars(result), 16_000)

    def test_status_keeps_diagnostics_structured_and_human_text_concise(self):
        status = self.server._bridge_status()
        result = mcp_server._tool_result(
            mcp_server._bridge_status_content(status),
            status,
            is_error=not bool(status.get("ok")),
        )

        self.assertIn("mcp_server_source_hash", result["structuredContent"])
        self.assertIn("tool_registry_digest", result["structuredContent"])
        self.assertLess(len(result["content"][0]["text"]), 500)
        self.assertLessEqual(payload_chars(result), 3_000)

    def test_json_tool_content_is_compact_without_data_loss(self):
        structured = {
            "ok": True,
            "objects": [{"name": "Cube", "visible": True}],
            "message": "Scene inspected",
        }

        text = mcp_server._json_text(structured)

        self.assertEqual(structured, json.loads(text))
        self.assertEqual(
            json.dumps(structured, separators=(",", ":"), sort_keys=True),
            text,
        )
        self.assertNotIn("\n", text)


if __name__ == "__main__":
    unittest.main()
