"""Thin public execution surface for the modular Blender tool handlers."""

from __future__ import annotations

from . import animation_runtime as _animation_runtime
from . import handler_runtime as _runtime
from . import tool_executor as _executor


TOOL_FUNCTIONS = _executor.TOOL_FUNCTIONS
execute_tool = _executor.execute_tool


def __getattr__(name):
    """Preserve internal helper compatibility while callers migrate by domain."""

    handler = _executor.TOOL_FUNCTIONS.get(name)
    if handler is not None:
        return handler
    if hasattr(_runtime, name):
        return getattr(_runtime, name)
    return getattr(_animation_runtime, name)


__all__ = ["TOOL_FUNCTIONS", "execute_tool"]
