from __future__ import annotations

import os
import sys
import unittest
from unittest import mock


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import mcp_server, tool_surface  # noqa: E402


class OfflineBridge:
    base_url = "http://127.0.0.1:9876"

    def get(self, path, params=None):
        if path == "/tools":
            return {"ok": True, "tools": mcp_server._static_tool_definitions()}
        raise RuntimeError(path)


class ToolSurfaceTests(unittest.TestCase):
    def _server(self, **environment):
        clean = {
            tool_surface.TOOL_SURFACE_ENV: "",
            tool_surface.LEGACY_FULL_TOOL_LIST_ENV: "",
            **environment,
        }
        with mock.patch.dict(os.environ, clean, clear=False):
            return mcp_server.BlenderMCPServer(OfflineBridge())

    def test_default_surface_is_exactly_the_five_gateways(self):
        server = self._server()
        self.assertEqual(tool_surface.GATEWAY, server._tool_surface)
        self.assertEqual(
            list(mcp_server.GATEWAY_TOOL_NAMES),
            [tool["name"] for tool in server.tools_list({})["tools"]],
        )

    def test_direct_surface_preserves_the_previous_compact_inventory(self):
        server = self._server(**{tool_surface.TOOL_SURFACE_ENV: tool_surface.DIRECT})
        self.assertEqual(tool_surface.DIRECT, server._tool_surface)
        self.assertEqual(
            set(mcp_server.GATEWAY_TOOL_NAMES) | set(mcp_server.COMPACT_DIRECT_TOOL_NAMES),
            {tool["name"] for tool in server.tools_list({})["tools"]},
        )

    def test_full_surface_contains_gateways_and_every_public_helper(self):
        server = self._server(**{tool_surface.TOOL_SURFACE_ENV: tool_surface.FULL})
        names = {tool["name"] for tool in server._load_tools()}
        self.assertEqual(tool_surface.FULL, server._tool_surface)
        self.assertTrue(set(mcp_server.GATEWAY_TOOL_NAMES).issubset(names))
        self.assertTrue(
            {
                "list_scene_objects",
                "draft_script",
                "run_approved_script",
                "commit_preview",
                "revert_preview",
            }.issubset(names)
        )

    def test_legacy_full_flag_remains_supported(self):
        server = self._server(**{tool_surface.LEGACY_FULL_TOOL_LIST_ENV: "1"})
        self.assertEqual(tool_surface.FULL, server._tool_surface)

    def test_explicit_surface_overrides_legacy_full_flag(self):
        server = self._server(
            **{
                tool_surface.TOOL_SURFACE_ENV: tool_surface.GATEWAY,
                tool_surface.LEGACY_FULL_TOOL_LIST_ENV: "1",
            }
        )
        self.assertEqual(tool_surface.GATEWAY, server._tool_surface)

    def test_invalid_surface_fails_fast(self):
        with mock.patch.dict(
            os.environ,
            {
                tool_surface.TOOL_SURFACE_ENV: "planning-only",
                tool_surface.LEGACY_FULL_TOOL_LIST_ENV: "",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "direct, full, gateway"):
                mcp_server.BlenderMCPServer(OfflineBridge())


if __name__ == "__main__":
    unittest.main()
