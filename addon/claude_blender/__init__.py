"""Blender Agent Bridge extension entrypoint."""

from __future__ import annotations

import importlib
import sys


_TOOL_REGISTRY_RELOAD_ORDER = (
    "tool_registry.registry",
    "tool_registry.domains.inspection_docs",
    "tool_registry.domains.project_workspace",
    "tool_registry.domains.scene_editing",
    "tool_registry.domains.modeling",
    "tool_registry.domains.materials_nodes",
    "tool_registry.domains.animation",
    "tool_registry.domains.rigging_simulation",
    "tool_registry.domains.camera_render_evidence",
    "tool_registry.domains.workflows_refinement",
    "tool_registry.domains.quality_observability",
    "tool_registry.domains.external_assets",
    "tool_registry.domains.generation",
    "tool_registry.domains.scripts_transactions",
    "tool_registry",
)

_TOOL_HANDLER_RELOAD_ORDER = (
    "tool_handlers.support",
    "tool_handlers.inspection_docs",
    "tool_handlers.project_workspace",
    "tool_handlers.scene_editing",
    "tool_handlers.modeling",
    "tool_handlers.materials_nodes",
    "tool_handlers.animation",
    "tool_handlers.rigging_simulation",
    "tool_handlers.camera_render_evidence",
    "tool_handlers.workflows_refinement",
    "tool_handlers.quality_observability",
    "tool_handlers.external_assets",
    "tool_handlers.generation",
    "tool_handlers.scripts_transactions",
)

_MODULE_NAMES = (
    "blender_compat",
    "build_info",
    "user_paths",
    "properties",
    "generation_providers",
    "preferences",
    "context_budget",
    "context_bundle",
    "context_planner",
    "world_model",
    "audit_log",
    "execution_traces",
    "quality_reviews",
    "reference_benchmarks",
    "quality_benchmarks",
    "script_analysis",
    "helper_routing",
    "animation_brief",
    "animation_analysis",
    "presentation_support",
    "workflow_planning",
    "two_d_inspection",
    "advanced_support",
    "advanced_animation",
    "advanced_materials",
    "reference_metrics",
    "reference_forms",
    "shape_program",
    "shape_program_adaptive",
    "reference_parts",
    "sculpt_fields",
    "depth_fields",
    "fur_groom",
    "visual_hull",
    "reference_fitting",
    "reference_multiview",
    "reference_scene",
    "reference_annotations",
    "reference_guides",
    "reference_multiview_scene",
    "reference_depth",
    "reference_visual_hull",
    "reference_blockout",
    "shape_program_scene",
    "reference_part_scene",
    "reference_feature_stacks",
    "advanced_modeling",
    "advanced_rigging",
    "reference_fur_flow",
    "advanced_scene_editing",
    "advanced_camera_render",
    "advanced_presentation",
    "advanced_helpers",
    "viewport_capture",
    "playblast_capture",
    "inspection_render",
    "reference_comparison",
    "reference_surface_fitting",
    "semantic_sculpt",
    "adaptive_remesh",
    "reference_benchmark_scene",
    "autosave",
    "lab_parity",
    "render_jobs",
    "process_utils",
    "trusted_script_jobs",
    "asset_jobs",
    "project_files",
    "bridge_protocol",
    "bridge_server",
    "docs_index",
    "agent_tools",
    "transcript",
    "live_preview",
    "script_templates",
    "handler_runtime",
    "animation_runtime",
    "tool_dispatcher",
    "script_runner",
    "ui",
)

_modules = []


def _reload_loaded(package, module_names):
    for module_name in module_names:
        module = sys.modules.get(f"{package}.{module_name}")
        if module is not None:
            importlib.reload(module)


def _reload_modular_tool_runtime(package):
    runtime = sys.modules.get(f"{package}.handler_runtime")
    if runtime is None:
        return
    # Refresh shared helpers and domain function bodies, then let the executor
    # rebuild the dispatch table and re-inject its lookup into the runtime.
    # This makes Blender's Reload Scripts path effective without a registry
    # import cycle or stale hidden globals.
    importlib.reload(runtime)
    animation_runtime = sys.modules.get(f"{package}.animation_runtime")
    if animation_runtime is not None:
        importlib.reload(animation_runtime)
    _reload_loaded(package, _TOOL_HANDLER_RELOAD_ORDER)
    executor = sys.modules.get(f"{package}.tool_executor")
    if executor is not None:
        importlib.reload(executor)


def _load_modules():
    global _modules
    package = __name__
    loaded = []
    _reload_loaded(package, _TOOL_REGISTRY_RELOAD_ORDER)
    for module_name in _MODULE_NAMES:
        if module_name == "tool_dispatcher":
            _reload_modular_tool_runtime(package)
        full_name = f"{package}.{module_name}"
        module = importlib.import_module(full_name)
        loaded.append(importlib.reload(module))
    _modules = loaded


def register():
    _load_modules()
    for module in _modules:
        register_fn = getattr(module, "register", None)
        if register_fn:
            register_fn()


def unregister():
    for module in reversed(_modules):
        unregister_fn = getattr(module, "unregister", None)
        if unregister_fn:
            try:
                unregister_fn()
            except RuntimeError:
                # Blender may already have unregistered classes during reloads.
                pass
