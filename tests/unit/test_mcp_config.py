from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import build_info  # noqa: E402


class MCPConfigTests(unittest.TestCase):
    def test_mcp_server_path_resolves_linked_extension_install(self):
        linked_path = os.path.join("linked", "claude_blender", "mcp_server.py")
        resolved_path = os.path.join("source", "claude_blender", "mcp_server.py")
        with (
            mock.patch.object(build_info, "addon_root", return_value=os.path.dirname(linked_path)),
            mock.patch.object(build_info.os.path, "realpath", return_value=resolved_path) as realpath,
        ):
            self.assertEqual(resolved_path, build_info.mcp_server_path())
        realpath.assert_called_once_with(linked_path)

    def test_bundled_python_executable_prefers_embedded_interpreter(self):
        with tempfile.TemporaryDirectory() as temporary:
            bin_dir = os.path.join(temporary, "bin")
            os.makedirs(bin_dir)
            python_name = "python.exe" if os.name == "nt" else "python3.11"
            python_path = os.path.join(bin_dir, python_name)
            with open(python_path, "wb"):
                pass
            if os.name != "nt":
                os.chmod(python_path, 0o755)
            blender_path = os.path.join(temporary, "blender.exe" if os.name == "nt" else "blender")
            with open(blender_path, "wb"):
                pass

            self.assertEqual(
                os.path.abspath(python_path),
                build_info.bundled_python_executable(executable=blender_path, prefix=temporary),
            )

    def test_bundled_python_executable_falls_back_to_path_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(
                "python",
                build_info.bundled_python_executable(
                    executable=os.path.join(temporary, "blender"),
                    prefix=temporary,
                ),
            )

    def test_bundled_mode_remains_default(self):
        config = build_info.mcp_config("http://127.0.0.1:8765")
        server = config["mcpServers"]["blender"]
        self.assertEqual("python", server["command"])
        self.assertEqual(build_info.mcp_server_path(), server["args"][0])
        self.assertNotIn("env", server)

    def test_bundled_config_includes_only_real_env_values(self):
        config = build_info.mcp_config(
            "http://127.0.0.1:8765",
            token="bridge-token",
            sketchfab_api_token="sketchfab-token",
        )
        server = config["mcpServers"]["blender"]
        self.assertEqual(
            {
                "BLENDER_BRIDGE_TOKEN": "bridge-token",
                "SKETCHFAB_API_TOKEN": "sketchfab-token",
            },
            server["env"],
        )

    def test_diagnostic_env_is_opt_in(self):
        env = build_info.mcp_config_env(include_diagnostics=True)
        self.assertEqual("bundled", env["CLAUDE_BLENDER_MCP_RUNTIME_MODE"])
        self.assertEqual(build_info.ADDON_VERSION, env["CLAUDE_BLENDER_ADDON_VERSION"])
        self.assertEqual(build_info.source_tree_hash(), env["CLAUDE_BLENDER_ADDON_SOURCE_HASH"])
        self.assertEqual(build_info.TOOL_REGISTRY_DIGEST, env["CLAUDE_BLENDER_TOOL_REGISTRY_DIGEST"])
        self.assertNotIn("SKETCHFAB_API_TOKEN", env)

    def test_generation_credentials_are_never_emitted_into_mcp_config(self):
        # The generation handler runs inside Blender and reads add-on
        # preferences. A key pasted into the MCP client config would be
        # invisible to it, so offering a slot here would point users at a
        # channel that cannot work.
        for env in (
            build_info.mcp_config_env(include_diagnostics=True),
            build_info.mcp_config_env(token="bridge-token"),
        ):
            for name in ("TRIPO_API_KEY", "MESHY_API_KEY", "BLENDER_AGENT_BRIDGE_GENERATION_EGRESS"):
                self.assertNotIn(name, env)

    def test_uvx_windows_config_is_version_pinned(self):
        config = build_info.mcp_config(
            "http://127.0.0.1:8765",
            launch_mode="uvx",
            platform_name="nt",
        )
        server = config["mcpServers"]["blender"]
        self.assertEqual("cmd", server["command"])
        self.assertEqual(
            ["/c", "uvx", "--from", f"blender-bridge=={build_info.MCP_SERVER_VERSION}", "blender-bridge"],
            server["args"][:5],
        )
        self.assertEqual("uvx", server["env"]["CLAUDE_BLENDER_MCP_RUNTIME_MODE"])
        self.assertEqual(["CLAUDE_BLENDER_MCP_RUNTIME_MODE"], list(server["env"]))

    def test_uvx_posix_config_invokes_uvx_directly(self):
        config = build_info.mcp_config("http://127.0.0.1:8765", launch_mode="uvx", platform_name="posix")
        server = config["mcpServers"]["blender"]
        self.assertEqual("uvx", server["command"])
        self.assertEqual(
            ["--from", f"blender-bridge=={build_info.MCP_SERVER_VERSION}", "blender-bridge"],
            server["args"][:3],
        )

    def test_invalid_runtime_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            build_info.mcp_config("http://127.0.0.1:8765", launch_mode="remote-cloud")


if __name__ == "__main__":
    unittest.main()
