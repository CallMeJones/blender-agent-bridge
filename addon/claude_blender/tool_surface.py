"""MCP tool-surface policy.

The canonical registry always owns every Blender tool. This module only decides
which entry points are advertised by ``tools/list`` for a given client setup.
"""

from __future__ import annotations

import os


TOOL_SURFACE_ENV = "BLENDER_MCP_TOOL_SURFACE"
LEGACY_FULL_TOOL_LIST_ENV = "BLENDER_MCP_FULL_TOOL_LIST"

GATEWAY = "gateway"
DIRECT = "direct"
FULL = "full"
DEFAULT = GATEWAY
VALID = frozenset({GATEWAY, DIRECT, FULL})


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def resolve(environ=None):
    """Return the configured surface, preserving the legacy full-list flag."""

    environ = os.environ if environ is None else environ
    configured = str(environ.get(TOOL_SURFACE_ENV) or "").strip().lower()
    if configured:
        if configured not in VALID:
            choices = ", ".join(sorted(VALID))
            raise ValueError(f"{TOOL_SURFACE_ENV} must be one of: {choices}")
        return configured
    if _truthy(environ.get(LEGACY_FULL_TOOL_LIST_ENV)):
        return FULL
    return DEFAULT


def advertised_names(surface, gateway_names, direct_names, full_names):
    """Return an ordered, duplicate-free tool-name tuple for one surface."""

    if surface not in VALID:
        raise ValueError(f"Unsupported MCP tool surface: {surface!r}")
    if surface == GATEWAY:
        selected = gateway_names
    elif surface == DIRECT:
        selected = (*gateway_names, *direct_names)
    else:
        selected = (*gateway_names, *full_names)
    return tuple(dict.fromkeys(str(name) for name in selected if str(name)))
