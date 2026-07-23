"""Public entry point for the canonical Blender tool registry."""

from __future__ import annotations

from .registry import HandlerRegistry, ToolRegistry, ToolSpec
from .domains import (
    inspection_docs,
    project_workspace,
    scene_editing,
    modeling,
    materials_nodes,
    animation,
    rigging_simulation,
    camera_render_evidence,
    workflows_refinement,
    external_assets,
    scripts_transactions,
)


DOMAIN_MODULES = (
    inspection_docs,
    project_workspace,
    scene_editing,
    modeling,
    materials_nodes,
    animation,
    rigging_simulation,
    camera_render_evidence,
    workflows_refinement,
    external_assets,
    scripts_transactions,
)


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for module in DOMAIN_MODULES:
        module.register(registry)
    return registry


REGISTRY = build_registry()
TOOL_REGISTRY_DIGEST = REGISTRY.digest()


def definitions():
    return REGISTRY.definitions()


def contracts():
    return REGISTRY.contracts()


def group_map():
    return REGISTRY.group_map()


def build_handlers():
    registry = HandlerRegistry()
    for module in DOMAIN_MODULES:
        module.register_handlers(registry)
    handlers = registry.as_dict()
    REGISTRY.validate_handlers(handlers)
    return handlers


def handlers_from_namespace(_namespace=None):
    """Compatibility alias for the pre-v0.3 dispatcher bootstrap."""

    return build_handlers()


__all__ = [
    "DOMAIN_MODULES",
    "HandlerRegistry",
    "REGISTRY",
    "TOOL_REGISTRY_DIGEST",
    "ToolRegistry",
    "ToolSpec",
    "build_registry",
    "build_handlers",
    "contracts",
    "definitions",
    "group_map",
    "handlers_from_namespace",
]
