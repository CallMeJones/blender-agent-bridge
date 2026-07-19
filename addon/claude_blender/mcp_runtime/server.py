"""PyPI/uvx console entry point for Blender Agent Bridge."""

from __future__ import annotations

import os


# The console package is the uvx/PyPI launch path. Set this before importing the
# shared server so source-tree diagnostics use registry compatibility semantics.
os.environ["CLAUDE_BLENDER_MCP_RUNTIME_MODE"] = "uvx"

from ..mcp_server import main as _shared_main  # noqa: E402


def main(argv=None):
    return _shared_main(argv)


__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
