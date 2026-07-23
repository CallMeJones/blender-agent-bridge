from __future__ import annotations

import os
import sys
import tempfile
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import build_info  # noqa: E402


class MCPConfigTests(unittest.TestCase):
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
        self.assertEqual("bundled", server["env"]["CLAUDE_BLENDER_MCP_RUNTIME_MODE"])

    def test_uvx_windows_config_is_version_pinned(self):
        config = build_info.mcp_config(
            "http://127.0.0.1:8765",
            launch_mode="uvx",
            platform_name="nt",
        )
        server = config["mcpServers"]["blender"]
        self.assertEqual("cmd", server["command"])
        self.assertEqual(
            ["/c", "uvx", "--from", "blender-bridge==0.4.0", "blender-bridge"],
            server["args"][:5],
        )
        self.assertEqual("uvx", server["env"]["CLAUDE_BLENDER_MCP_RUNTIME_MODE"])
        self.assertEqual(build_info.TOOL_REGISTRY_DIGEST, server["env"]["CLAUDE_BLENDER_TOOL_REGISTRY_DIGEST"])

    def test_uvx_posix_config_invokes_uvx_directly(self):
        config = build_info.mcp_config("http://127.0.0.1:8765", launch_mode="uvx", platform_name="posix")
        server = config["mcpServers"]["blender"]
        self.assertEqual("uvx", server["command"])
        self.assertEqual(["--from", "blender-bridge==0.4.0", "blender-bridge"], server["args"][:3])

    def test_invalid_runtime_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            build_info.mcp_config("http://127.0.0.1:8765", launch_mode="remote-cloud")


if __name__ == "__main__":
    unittest.main()
