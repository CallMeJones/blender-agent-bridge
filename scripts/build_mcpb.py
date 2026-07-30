"""Build a deterministic MCPB connector for Blender Agent Bridge."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ADDON_PARENT = os.path.join(ROOT, "addon")
if ADDON_PARENT not in sys.path:
    sys.path.insert(0, ADDON_PARENT)

from claude_blender import build_info  # noqa: E402


MCPB_MANIFEST_VERSION = "0.4"
MCPB_NAME = "blender-agent-bridge"
SOURCE_DATE = (2020, 1, 1, 0, 0, 0)


def mcpb_filename(version=None):
    return f"{MCPB_NAME}-{version or build_info.MCP_SERVER_VERSION}.mcpb"


def build_manifest():
    return {
        "manifest_version": MCPB_MANIFEST_VERSION,
        "name": MCPB_NAME,
        "display_name": build_info.ADDON_NAME,
        "version": build_info.MCP_SERVER_VERSION,
        "description": (
            "Safe five-tool MCP gateway for inspecting and operating a running Blender Agent Bridge extension."
        ),
        "long_description": (
            "Connects Claude Desktop to the localhost bridge started by the separately installed Blender extension. "
            "Includes deterministic diagnostics, schema lookup, and gateway invocation without requiring a "
            "user-managed Python installation."
        ),
        "author": {
            "name": "Michael",
            "url": "https://github.com/CallMeJones",
        },
        "repository": {
            "type": "git",
            "url": "https://github.com/CallMeJones/blender-agent-bridge",
        },
        "homepage": "https://github.com/CallMeJones/blender-agent-bridge",
        "documentation": "https://github.com/CallMeJones/blender-agent-bridge/tree/main/docs",
        "support": "https://github.com/CallMeJones/blender-agent-bridge/issues",
        "server": {
            "type": "uv",
            "entry_point": "src/main.py",
            "mcp_config": {
                "command": "uv",
                "args": [
                    "run",
                    "--directory",
                    "${__dirname}",
                    "src/main.py",
                ],
                "env": {
                    "BLENDER_BRIDGE_URL": "${user_config.bridge_url}",
                    "BLENDER_BRIDGE_TOKEN": "${user_config.bridge_token}",
                    "CLAUDE_BLENDER_ADDON_ID": build_info.ADDON_ID,
                    "CLAUDE_BLENDER_ADDON_VERSION": build_info.ADDON_VERSION,
                    "CLAUDE_BLENDER_ADDON_SOURCE_HASH": build_info.source_tree_hash(),
                    "CLAUDE_BLENDER_BRIDGE_VERSION": build_info.BRIDGE_VERSION,
                    "CLAUDE_BLENDER_MCP_SERVER_VERSION": build_info.MCP_SERVER_VERSION,
                    "CLAUDE_BLENDER_MCP_CONFIG_VERSION": build_info.MCP_CONFIG_VERSION,
                    "CLAUDE_BLENDER_MCP_RUNTIME_MODE": build_info.MCP_RUNTIME_BUNDLED,
                    "CLAUDE_BLENDER_TOOL_REGISTRY_DIGEST": build_info.TOOL_REGISTRY_DIGEST,
                },
            },
        },
        "tools_generated": True,
        "user_config": {
            "bridge_url": {
                "type": "string",
                "title": "Blender bridge URL",
                "description": "Loopback URL shown in Blender's Agent Bridge panel.",
                "default": "http://127.0.0.1:8765",
                "required": True,
            },
            "bridge_token": {
                "type": "string",
                "title": "Bridge token",
                "description": "Optional bearer token configured in Blender.",
                "default": "",
                "sensitive": True,
                "required": False,
            },
        },
        "compatibility": {
            "claude_desktop": ">=0.10.0",
            "platforms": ["darwin", "win32", "linux"],
            "runtimes": {"python": ">=3.10,<4.0"},
        },
        "keywords": ["blender", "3d", "mcp", "modeling", "animation"],
        "license": "GPL-3.0-or-later",
        "privacy_policies": [
            "https://github.com/CallMeJones/blender-agent-bridge/blob/main/PRIVACY.md"
        ],
    }


def _copy_package(stage_root):
    source = os.path.join(ROOT, "addon", "claude_blender")
    target = os.path.join(stage_root, "src", "claude_blender")
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def _write_pyproject(stage_root):
    contents = "\n".join(
        (
            "[project]",
            'name = "blender-agent-bridge-mcpb"',
            f'version = "{build_info.MCP_SERVER_VERSION}"',
            'requires-python = ">=3.10,<4.0"',
            "dependencies = []",
            "",
        )
    )
    with open(os.path.join(stage_root, "pyproject.toml"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(contents)


def _write_stage(stage_root):
    os.makedirs(os.path.join(stage_root, "src"), exist_ok=True)
    _copy_package(stage_root)
    shutil.copy2(
        os.path.join(ROOT, "packaging", "mcpb", "server", "main.py"),
        os.path.join(stage_root, "src", "main.py"),
    )
    shutil.copy2(
        os.path.join(ROOT, "packaging", "mcpb", "README.md"),
        os.path.join(stage_root, "README.md"),
    )
    shutil.copy2(os.path.join(ROOT, "LICENSE"), os.path.join(stage_root, "LICENSE"))
    shutil.copy2(os.path.join(ROOT, "PRIVACY.md"), os.path.join(stage_root, "PRIVACY.md"))
    _write_pyproject(stage_root)
    with open(os.path.join(stage_root, "manifest.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(build_manifest(), handle, indent=2, sort_keys=True)
        handle.write("\n")


def _archive_stage(stage_root, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for current_root, dirnames, filenames in os.walk(stage_root):
            dirnames.sort()
            for filename in sorted(filenames):
                path = os.path.join(current_root, filename)
                relative = os.path.relpath(path, stage_root).replace(os.sep, "/")
                info = zipfile.ZipInfo(relative, SOURCE_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                with open(path, "rb") as handle:
                    archive.writestr(info, handle.read())


def build_mcpb(output_dir, *, stage_dir=""):
    output_dir = os.path.abspath(output_dir)
    filename = mcpb_filename()
    output_path = os.path.join(output_dir, filename)
    if stage_dir:
        stage_root = os.path.abspath(stage_dir)
        if os.path.exists(stage_root):
            if not os.path.isdir(stage_root) or os.listdir(stage_root):
                raise RuntimeError(f"MCPB stage directory must be an empty directory: {stage_root}")
        os.makedirs(stage_root, exist_ok=True)
        _write_stage(stage_root)
        _archive_stage(stage_root, output_path)
    else:
        with tempfile.TemporaryDirectory(prefix="blender-agent-bridge-mcpb-") as stage_root:
            _write_stage(stage_root)
            _archive_stage(stage_root, output_path)
    digest = hashlib.sha256()
    with open(output_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    digest_path = output_path + ".sha256"
    with open(digest_path, "w", encoding="ascii", newline="\n") as handle:
        handle.write(f"{digest.hexdigest()}  {os.path.basename(output_path)}\n")
    return output_path, digest_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=os.path.join(ROOT, "dist"))
    parser.add_argument(
        "--stage-dir",
        default="",
        help="Optional empty directory to retain for official MCPB schema validation.",
    )
    args = parser.parse_args(argv)
    output_path, digest_path = build_mcpb(args.output_dir, stage_dir=args.stage_dir)
    print(output_path)
    print(digest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
