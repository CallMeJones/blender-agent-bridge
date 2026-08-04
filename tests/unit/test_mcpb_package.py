from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
import zipfile


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from claude_blender import build_info  # noqa: E402
import build_mcpb  # noqa: E402


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class MCPBPackageTests(unittest.TestCase):
    def test_manifest_uses_generated_tools_and_sensitive_optional_token(self):
        manifest = build_mcpb.build_manifest()

        self.assertEqual(
            f"{build_mcpb.MCPB_NAME}-{build_info.MCP_SERVER_VERSION}.mcpb",
            build_mcpb.mcpb_filename(),
        )
        self.assertEqual("0.4", manifest["manifest_version"])
        self.assertEqual(build_info.MCP_SERVER_VERSION, manifest["version"])
        self.assertEqual("uv", manifest["server"]["type"])
        self.assertEqual("uv", manifest["server"]["mcp_config"]["command"])
        self.assertNotIn("PYTHONPATH", manifest["server"]["mcp_config"]["env"])
        self.assertEqual(
            "${user_config.bridge_url}",
            manifest["server"]["mcp_config"]["env"]["BLENDER_BRIDGE_URL"],
        )
        self.assertTrue(manifest["tools_generated"])
        self.assertNotIn("tools", manifest)
        self.assertEqual(
            build_info.TOOL_REGISTRY_DIGEST,
            manifest["server"]["mcp_config"]["env"]["CLAUDE_BLENDER_TOOL_REGISTRY_DIGEST"],
        )
        self.assertEqual(
            build_info.source_tree_hash(),
            manifest["server"]["mcp_config"]["env"]["CLAUDE_BLENDER_ADDON_SOURCE_HASH"],
        )
        self.assertTrue(manifest["user_config"]["bridge_token"]["sensitive"])
        self.assertFalse(manifest["user_config"]["bridge_token"]["required"])

    def test_archive_contains_runtime_docs_and_no_compiled_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            output_path, digest_path = build_mcpb.build_mcpb(temporary)
            with zipfile.ZipFile(output_path) as archive:
                names = archive.namelist()
                manifest = json.loads(archive.read("manifest.json"))
            self.assertTrue(output_path.endswith(f"-{build_info.MCP_SERVER_VERSION}.mcpb"))
            self.assertTrue(os.path.isfile(digest_path))
            self.assertIn("src/main.py", names)
            self.assertIn("src/claude_blender/mcp_server.py", names)
            self.assertIn("pyproject.toml", names)
            self.assertIn("README.md", names)
            self.assertIn("LICENSE", names)
            self.assertFalse(any(name.startswith("server/lib/") for name in names))
            self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") for name in names))
            self.assertEqual(build_info.MCP_SERVER_VERSION, manifest["version"])

    def test_archive_is_reproducible(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_path, _ = build_mcpb.build_mcpb(first)
            second_path, _ = build_mcpb.build_mcpb(second)
            self.assertEqual(_sha256(first_path), _sha256(second_path))

    def test_archive_launches_through_manifest_uv_runtime(self):
        uv_command = shutil.which("uv")
        if not uv_command:
            self.skipTest("uv is not installed")

        with tempfile.TemporaryDirectory() as temporary:
            output_path, _ = build_mcpb.build_mcpb(temporary)
            extracted = os.path.join(temporary, "extracted")
            with zipfile.ZipFile(output_path) as archive:
                archive.extractall(extracted)
                manifest = json.loads(archive.read("manifest.json"))
                project = tomllib.loads(archive.read("pyproject.toml").decode("utf-8"))
            config = manifest["server"]["mcp_config"]
            replacements = {
                "${__dirname}": extracted,
                "${user_config.bridge_url}": "http://127.0.0.1:8765",
                "${user_config.bridge_token}": "",
            }

            def expand(value):
                for placeholder, replacement in replacements.items():
                    value = value.replace(placeholder, replacement)
                return value

            env = dict(os.environ)
            env.update({key: expand(value) for key, value in config["env"].items()})
            for key in list(env):
                if key.upper() in {"PYTHONHOME", "UV_INTERNAL__PYTHONHOME"}:
                    env.pop(key, None)
            env["UV_NO_PROGRESS"] = "1"
            env["UV_CACHE_DIR"] = os.path.join(temporary, "uv-cache")
            env["UV_PROJECT_ENVIRONMENT"] = os.path.join(temporary, "uv-environment")
            env["UV_PYTHON_INSTALL_DIR"] = os.path.join(temporary, "uv-python")
            completed = subprocess.run(
                [
                    uv_command,
                    *[expand(value) for value in config["args"]],
                    "--version",
                ],
                cwd=extracted,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn(build_info.MCP_SERVER_VERSION, completed.stdout)
        self.assertEqual(build_info.MCP_SERVER_VERSION, project["project"]["version"])
        self.assertEqual([], project["project"]["dependencies"])

    def test_stage_directory_retains_validator_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = os.path.join(temporary, "dist")
            stage_dir = os.path.join(temporary, "stage")
            build_mcpb.build_mcpb(output_dir, stage_dir=stage_dir)
            with open(os.path.join(stage_dir, "manifest.json"), "r", encoding="utf-8") as handle:
                manifest = json.load(handle)
            self.assertTrue(os.path.isfile(os.path.join(stage_dir, "src", "main.py")))
            self.assertTrue(os.path.isfile(os.path.join(stage_dir, "pyproject.toml")))

        self.assertEqual(build_info.MCP_SERVER_VERSION, manifest["version"])


if __name__ == "__main__":
    unittest.main()
