"""MCPB launcher for the bundled Blender Agent Bridge Python runtime."""

from __future__ import annotations

import os


os.environ.setdefault("CLAUDE_BLENDER_MCP_RUNTIME_MODE", "bundled")

from claude_blender.mcp_server import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
