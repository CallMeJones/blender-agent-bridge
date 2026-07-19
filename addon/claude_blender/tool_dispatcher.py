"""Thin public execution surface for the modular Blender tool handlers."""

from __future__ import annotations

from . import handler_runtime as _runtime


TOOL_FUNCTIONS = _runtime.TOOL_FUNCTIONS
execute_tool = _runtime.execute_tool


def __getattr__(name):
    """Preserve internal helper compatibility while callers migrate by domain."""

    return getattr(_runtime, name)


__all__ = ["TOOL_FUNCTIONS", "execute_tool"]
