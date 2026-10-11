"""Stdio MCP server that forwards tool/resource calls to Blender's localhost bridge."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request

try:
    from . import (
        agent_tools,
        audit_log,
        bridge_protocol,
        build_info,
        execution_traces,
        external_assets,
        helper_routing,
        response_controls,
        tool_registry,
        tool_surface,
    )
except ImportError:  # Allows direct execution as addon/claude_blender/mcp_server.py.
    package_parent = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if package_parent not in sys.path:
        sys.path.insert(0, package_parent)
    try:
        from claude_blender import (
            agent_tools,
            audit_log,
            bridge_protocol,
            build_info,
            execution_traces,
            external_assets,
            helper_routing,
            response_controls,
            tool_registry,
            tool_surface,
        )
    except ImportError:
        import agent_tools
        import audit_log
        import build_info
        import execution_traces
        import bridge_protocol
        import external_assets
        import helper_routing
        import response_controls
        import tool_registry
        import tool_surface


try:
    from . import tool_catalog
except ImportError:
    from claude_blender import tool_catalog

ADVANCED_ROUTE_TERMS = tool_catalog.ADVANCED_ROUTE_TERMS
ADVANCED_ROUTE_TOOLS = tool_catalog.ADVANCED_ROUTE_TOOLS
ANIMATION_ROUTE_TOOLS = tool_catalog.ANIMATION_ROUTE_TOOLS
BACKGROUND_JOB_STATUS_TOOLS = tool_catalog.BACKGROUND_JOB_STATUS_TOOLS
BAKE_MAP_ROUTE_TERMS = tool_catalog.BAKE_MAP_ROUTE_TERMS
CACHE_CLEANUP_WRITE_TOOLS = tool_catalog.CACHE_CLEANUP_WRITE_TOOLS
CAMERA_MOVE_ROUTE_TERMS = tool_catalog.CAMERA_MOVE_ROUTE_TERMS
CATALOG_SEARCH_STOP_WORDS = tool_catalog.CATALOG_SEARCH_STOP_WORDS
EXTERNAL_ASSET_ACTION_TERMS = tool_catalog.EXTERNAL_ASSET_ACTION_TERMS
EXTERNAL_ASSET_ASYNC_WORKFLOW = tool_catalog.EXTERNAL_ASSET_ASYNC_WORKFLOW
EXTERNAL_ASSET_DIRECT_TERMS = tool_catalog.EXTERNAL_ASSET_DIRECT_TERMS
EXTERNAL_ASSET_DIRECT_TOOLS = tool_catalog.EXTERNAL_ASSET_DIRECT_TOOLS
EXTERNAL_ASSET_OBJECT_TERMS = tool_catalog.EXTERNAL_ASSET_OBJECT_TERMS
EXTERNAL_ASSET_STRONG_ROUTE_TERMS = tool_catalog.EXTERNAL_ASSET_STRONG_ROUTE_TERMS
EXTERNAL_ASSET_WORKFLOW_TOOLS = tool_catalog.EXTERNAL_ASSET_WORKFLOW_TOOLS
GENERIC_OUTPUT_SCHEMA = tool_catalog.GENERIC_OUTPUT_SCHEMA
GENERIC_SELECTED_OBJECT_TOOLS = tool_catalog.GENERIC_SELECTED_OBJECT_TOOLS
GUARDRAIL_COMMIT_REVERT_TOOLS = tool_catalog.GUARDRAIL_COMMIT_REVERT_TOOLS
INSPECTION_INTENT_TERMS = tool_catalog.INSPECTION_INTENT_TERMS
LOOKDEV_REVIEW_ROUTE_TERMS = tool_catalog.LOOKDEV_REVIEW_ROUTE_TERMS
MUTATION_INTENT_TERMS = tool_catalog.MUTATION_INTENT_TERMS
PROCEDURAL_ROUTE_TERMS = tool_catalog.PROCEDURAL_ROUTE_TERMS
PROCEDURAL_TEXTURE_ROUTE_TERMS = tool_catalog.PROCEDURAL_TEXTURE_ROUTE_TERMS
RENDER_OUTPUT_ROUTE_TERMS = tool_catalog.RENDER_OUTPUT_ROUTE_TERMS
SCRIPT_EXPLICIT_TERMS = tool_catalog.SCRIPT_EXPLICIT_TERMS
SIMULATION_SETUP_ROUTE_TERMS = tool_catalog.SIMULATION_SETUP_ROUTE_TERMS
TOOL_CATEGORY_LABELS = tool_catalog.TOOL_CATEGORY_LABELS
TWO_D_ROUTE_TERMS = tool_catalog.TWO_D_ROUTE_TERMS
UV_UNWRAP_ROUTE_TERMS = tool_catalog.UV_UNWRAP_ROUTE_TERMS
WORKFLOW_CAMERA_TERMS = tool_catalog.WORKFLOW_CAMERA_TERMS
WORKFLOW_CREATION_TERMS = tool_catalog.WORKFLOW_CREATION_TERMS
WORKFLOW_MATERIAL_TERMS = tool_catalog.WORKFLOW_MATERIAL_TERMS
WORKFLOW_PREVIEW_TERMS = tool_catalog.WORKFLOW_PREVIEW_TERMS
_catalog_facets = tool_catalog._catalog_facets
_catalog_filters = tool_catalog._catalog_filters
_catalog_query_features = tool_catalog._catalog_query_features
_contains_any_phrase = tool_catalog._contains_any_phrase
_guardrail_warnings_for_tool = tool_catalog._guardrail_warnings_for_tool
_is_external_asset_route_query = tool_catalog._is_external_asset_route_query
_score_tool_match = tool_catalog._score_tool_match
_tool_annotations = tool_catalog._tool_annotations
_tool_category = tool_catalog._tool_category
_tool_matches_filters = tool_catalog._tool_matches_filters
_tool_search_text = tool_catalog._tool_search_text
_tool_summary = tool_catalog._tool_summary


try:
    from . import bridge_client
except ImportError:
    from claude_blender import bridge_client

BRIDGE_MAIN_THREAD_TIMEOUT_GRACE_SECONDS = bridge_client.BRIDGE_MAIN_THREAD_TIMEOUT_GRACE_SECONDS
BridgeClient = bridge_client.BridgeClient
BridgeTimeoutError = bridge_client.BridgeTimeoutError
DEFAULT_BRIDGE_MAIN_THREAD_TIMEOUT_SECONDS = bridge_client.DEFAULT_BRIDGE_MAIN_THREAD_TIMEOUT_SECONDS
DEFAULT_BRIDGE_URL = bridge_client.DEFAULT_BRIDGE_URL
MCP_TIMEOUT_GRACE_SECONDS = bridge_client.MCP_TIMEOUT_GRACE_SECONDS
_bridge_timeout_for_tool = bridge_client._bridge_timeout_for_tool
_env_float = bridge_client._env_float
_timeout_recovery_data = bridge_client._timeout_recovery_data

def _digest_comparison(status):
    """Name the three digests and say which one disagrees.

    Three values are involved and only two were ever shown, so a stale client
    config -- the common case, and the one where the other two necessarily
    agree -- looked like the bridge complaining about nothing.
    """

    runtime = str(status.get("mcp_tool_registry_digest") or "")
    addon = str(status.get("tool_registry_digest") or "")
    config = str(status.get("mcp_config_tool_registry_digest") or "")

    def short(value):
        return value[:12] if value else "(absent)"

    differing = []
    if addon and addon != runtime:
        differing.append("blender_addon")
    if config and config != runtime:
        differing.append("mcp_client_config")
    return {
        "mcp_runtime": short(runtime),
        "blender_addon": short(addon),
        "mcp_client_config": short(config),
        "differs_from_runtime": differing,
        "summary": (
            "All three tool registry digests agree."
            if not differing
            else "%s disagrees with the running MCP server (%s)."
            % (", ".join(differing), short(runtime))
        ),
    }


PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = (PROTOCOL_VERSION,)
SERVER_NAME = "blender-agent-bridge"
SERVER_VERSION = build_info.MCP_SERVER_VERSION
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 100
TOOL_SURFACE_ENV = tool_surface.TOOL_SURFACE_ENV
SKETCHFAB_AUTH_FORWARD_TOOLS = {"download_sketchfab_model", "import_sketchfab_model", "start_external_asset_download"}
DIRECT_TOOL_NAMES = tuple(
    spec.name for spec in tool_registry.REGISTRY.specs() if spec.exposure == "compact_direct"
)
CATALOG_TOOL_NAME = "blender_tool_catalog"
GATEWAY_TOOL_NAMES = (
    "blender_bridge_status",
    CATALOG_TOOL_NAME,
    "search_blender_tools",
    "get_blender_tool_schema",
    "invoke_blender_tool",
)
WRAPPER_TOOL_NAMES = frozenset(GATEWAY_TOOL_NAMES)
TELEMETRY_TOOL_NAMES = frozenset(
    (*GATEWAY_TOOL_NAMES, *(spec.name for spec in tool_registry.REGISTRY.specs() if spec.exposure != "internal"))
)


STATUS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "bridge_url": {"type": "string"},
        "message": {"type": "string"},
        "bridge_version": {"type": "string"},
        "blender_version": {"type": "string"},
        "addon_id": {"type": "string"},
        "addon_name": {"type": "string"},
        "addon_version": {"type": "string"},
        "addon_path": {"type": "string"},
        "addon_source_hash": {"type": "string"},
        "addon_loaded_source_hash": {"type": "string"},
        "addon_runtime_source_stale": {"type": "boolean"},
        "addon_runtime_source_status": {"type": "string"},
        "addon_runtime_source_message": {"type": "string"},
        "addon_reload_required": {"type": "boolean"},
        "addon_reload_guidance": {"type": "string"},
        "blender_version_min": {"type": "string"},
        "blender_compatibility": {"type": "object"},
        "expected_addon_source_hash": {"type": "string"},
        "addon_source_hash_match": {"type": ["boolean", "null"]},
        "addon_source_hash_status": {"type": "string"},
        "addon_source_hash_message": {"type": "string"},
        "mcp_server_source_hash": {"type": "string"},
        "addon_mcp_source_hash_match": {"type": ["boolean", "null"]},
        "mcp_config_source_hash": {"type": "string"},
        "mcp_config_source_hash_match": {"type": ["boolean", "null"]},
        "source_hash_status": {"type": "string"},
        "source_hash_message": {"type": "string"},
        "mcp_server_version": {"type": "string"},
        "mcp_server_path": {"type": "string"},
        "mcp_config_version": {"type": "string"},
        "mcp_runtime_mode": {"type": "string"},
        "mcp_tool_surface": {"type": "string", "enum": ["gateway", "direct", "full"]},
        "tool_registry_digest": {"type": "string"},
        "mcp_tool_registry_digest": {"type": "string"},
        "mcp_config_tool_registry_digest": {"type": "string"},
        "tool_registry_digest_match": {"type": ["boolean", "null"]},
        "bridge_protocol_match": {"type": ["boolean", "null"]},
        "addon_mcp_version_match": {"type": ["boolean", "null"]},
        "compatible": {"type": ["boolean", "null"]},
        "compatibility_status": {"type": "string"},
        "compatibility_message": {"type": "string"},
        "blocked": {"type": "boolean"},
        "blocking_issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "message": {"type": "string"},
                    "remedy": {"type": "string"},
                },
            },
        },
        "build_diagnostics": {"type": "string"},
        "scene": {"type": "string"},
        "bridge_busy": {"type": "boolean"},
        "recoverable": {"type": "boolean"},
        "poll_after_seconds": {"type": "integer"},
        "active_tool_name": {"type": "string"},
        "active_operation": {"type": "object"},
        "last_operation": {"type": "object"},
        "recovery_hint": {"type": "string"},
        "external_script_trust": {"type": "boolean"},
        "external_script_trust_status": {"type": "string"},
        "external_script_trust_expires_at": {"type": "number"},
        "external_script_trust_seconds_remaining": {"type": "integer"},
        "external_script_trust_can_run_without_token": {"type": "boolean"},
        "external_script_trust_session": {"type": "boolean"},
        "external_script_trust_stale_scene_state": {"type": "boolean"},
        "mcp_external_asset_auth": {"type": "object"},
        "mcp_client_refresh_hint": {"type": "string"},
    },
    "required": ["ok"],
    "additionalProperties": True,
}

RESOURCE_TEMPLATES = [
    {
        "uriTemplate": "blender://scene/{resource}",
        "name": "scene-resource",
        "title": "Blender Scene Resource",
        "description": "Scene resources such as status or context exposed by the running Blender bridge.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "blender://tools/{resource}",
        "name": "tool-resource",
        "title": "Blender Tool Resource",
        "description": "Tool metadata resources such as compact catalog or the explicit full contract registry.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "blender://transcript/{resource}",
        "name": "transcript-resource",
        "title": "Blender Transcript Resource",
        "description": "Transcript resources from the Blender add-on.",
        "mimeType": "text/plain",
    },
    {
        "uriTemplate": "blender://audit/{resource}",
        "name": "audit-resource",
        "title": "Blender Audit Resource",
        "description": "Compact audit summaries or explicit recent local audit events for MCP and bridge tool calls.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "blender://captures/{capture_id}",
        "name": "capture-resource",
        "title": "Blender Capture Resource",
        "description": "Exact viewport screenshot PNG resources captured by the running Blender bridge.",
        "mimeType": "image/png",
    },
    {
        "uriTemplate": "blender://captures/{capture_id}/metadata",
        "name": "capture-metadata-resource",
        "title": "Blender Capture Metadata Resource",
        "description": "Exact viewport screenshot metadata for a capture from the running Blender bridge.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "blender://playblasts/{playblast_id}/metadata",
        "name": "playblast-metadata-resource",
        "title": "Blender Playblast Metadata Resource",
        "description": "Animation playblast metadata with sampled frame resource URIs.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "blender://playblasts/{playblast_id}/frames/{frame}",
        "name": "playblast-frame-resource",
        "title": "Blender Playblast Frame Resource",
        "description": "Sampled animation playblast frame PNG resources captured by the running Blender bridge.",
        "mimeType": "image/png",
    },
    {
        "uriTemplate": "blender://inspection-renders/{render_id}/metadata",
        "name": "inspection-render-metadata-resource",
        "title": "Blender Inspection Render Metadata Resource",
        "description": "Diagnostic object render metadata with close-up image resource URIs.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "blender://inspection-renders/{render_id}/images/{image_id}",
        "name": "inspection-render-image-resource",
        "title": "Blender Inspection Render Image Resource",
        "description": "Diagnostic close-up object render PNG resources captured by the running Blender bridge.",
        "mimeType": "image/png",
    },
    {
        "uriTemplate": "blender://render-thumbnails/{thumbnail_id}",
        "name": "render-thumbnail-resource",
        "title": "Blender Render Thumbnail Resource",
        "description": "Scene thumbnail PNG resources rendered by the running Blender bridge.",
        "mimeType": "image/png",
    },
    {
        "uriTemplate": "blender://render-thumbnails/{thumbnail_id}/metadata",
        "name": "render-thumbnail-metadata-resource",
        "title": "Blender Render Thumbnail Metadata Resource",
        "description": "Scene thumbnail metadata for a rendered still from the running Blender bridge.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "blender://render-jobs/{job_id}/metadata",
        "name": "render-job-metadata-resource",
        "title": "Blender Render Job Metadata Resource",
        "description": "Async render job status, output paths, progress, and resource URIs.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "blender://render-jobs/{job_id}/frames/{frame}",
        "name": "render-job-frame-resource",
        "title": "Blender Render Job Frame Resource",
        "description": "Exact PNG frame output from an async render job.",
        "mimeType": "image/png",
    },
    {
        "uriTemplate": "blender://render-jobs/{job_id}/log",
        "name": "render-job-log-resource",
        "title": "Blender Render Job Log Resource",
        "description": "Background Blender render process log for an async render job.",
        "mimeType": "text/plain",
    },
    {
        "uriTemplate": "blender://render-jobs/{job_id}/video",
        "name": "render-job-video-resource",
        "title": "Blender Render Job Video Resource",
        "description": "MP4 output from an async video render job when small enough to return through MCP.",
        "mimeType": "video/mp4",
    },
]

PROMPTS = {
    "inspect_scene": {
        "name": "inspect_scene",
        "title": "Inspect Blender Scene",
        "description": "Ask an MCP client to inspect the active Blender scene before making changes.",
        "arguments": [
            {
                "name": "goal",
                "description": "Optional user goal or question to focus the inspection.",
                "required": False,
            }
        ],
        "template": (
            "Inspect the current Blender scene using read-only tools first. "
            "Summarize the relevant objects, materials, animation, camera, lights, and render context. "
            "User goal: {goal}"
        ),
    },
    "safe_scene_change": {
        "name": "safe_scene_change",
        "title": "Plan Safe Blender Change",
        "description": "Plan a scene change using capability-routed helpers or session-trusted Python.",
        "arguments": [
            {
                "name": "goal",
                "description": "The scene change the user wants.",
                "required": True,
            }
        ],
        "template": (
            "Make this Blender change safely: {goal}\n\n"
            "Use read-only inspection first if needed. With active script trust, prefer one cohesive draft_script for "
            "authored object generation, modeling, animation, materials, nodes, rigging, and look development unless "
            "the user explicitly asks for helpers, a helper path, or no Python. For mixed requests, keep that authored "
            "script path and use bounded helpers separately for project files, external assets, long renders, "
            "persistent bakes, evidence capture, and preview decisions."
        ),
    },
    "blender_bridge_workflow": {
        "name": "blender_bridge_workflow",
        "title": "Operate Blender Through The Gateway",
        "description": "Guide any MCP client through compact helper discovery, schema lookup, invocation, recovery, and preview decisions.",
        "arguments": [
            {
                "name": "goal",
                "description": "The live Blender task to complete.",
                "required": True,
            }
        ],
        "template": (
            "Complete this live Blender task through Blender Agent Bridge: {goal}\n\n"
            "Call blender_bridge_status when live state matters. Use the stable five-tool gateway: search with "
            "search_blender_tools and include_schemas=false, fetch the current schema for one selected helper with "
            "get_blender_tool_schema, then call invoke_blender_tool with schema-valid arguments. A helper named by a "
            "planner remains available through the gateway even when it is absent from top-level tools/list. Inspect "
            "before mutation, follow executable and deferred planner calls, refresh actual object names after broad "
            "changes, and do not stop at planning when execution was requested. With active script trust, use one "
            "cohesive draft_script as the default authored-mutation path for object generation, modeling, animation, "
            "materials, nodes, rigging, and look development unless the user explicitly requests helpers, a helper path, "
            "or no Python. Do not let render, capture, save, or import clauses suppress the script path for separate "
            "authored work in the same request. Use start_trusted_script_job for cohesive scripts likely to exceed the "
            "bridge timeout, poll status, and apply the copied-file result only after explicit user approval. For "
            "substantial work, start and finalize a compact execution trace. Use bounded helpers for "
            "inspection, project files, external assets, long jobs, evidence, and preview decisions. Treat bridge_timeout as recoverable: wait the returned interval, "
            "check status and evidence, then retry only when the prior operation is no longer running. Leave changes in "
            "preview until the user explicitly chooses commit_preview or revert_preview."
        ),
    },
    "director_workflow": {
        "name": "director_workflow",
        "title": "Plan Director Workflow",
        "description": "Guide an MCP client through capability-routed scene authoring, assets, evidence, and preview decisions.",
        "arguments": [
            {
                "name": "goal",
                "description": "The broad scene, asset, animation, or presentation goal.",
                "required": True,
            }
        ],
        "template": (
            "Handle this Blender goal through Director Workflow v0: {goal}\n\n"
            "Call plan_director_workflow first. Follow its phases for inspection, asset import planning, "
            "authored construction, animation review/repair, viewport/playblast/render evidence, and explicit commit/revert "
            "decisions. When trust is active, prefer one cohesive draft_script for authored modeling, animation, materials, "
            "nodes, and rigging unless the user explicitly requests helpers, a helper path, or no Python. Clear the "
            "director plan's asset, brief, and target-refresh gates before invoking its deferred script. Use "
            "plan_asset_import_workflow for external assets and "
            "bounded structured tools for project files, long renders, persistent bakes, evidence, and preview decisions."
        ),
    },
    "advanced_animation_workflow": {
        "name": "advanced_animation_workflow",
        "title": "Run Advanced Animation Workflow",
        "description": "Guide an MCP client through animation planning, script-first authored execution, evaluation, and repair.",
        "arguments": [
            {
                "name": "goal",
                "description": "The animation generation, review, or repair goal.",
                "required": True,
            }
        ],
        "template": (
            "Handle this Blender animation task through the Milestone 7 workflow: {goal}\n\n"
            "Call plan_animation_workflow first to establish the brief, scene routing, timing chart, and hardening checks. "
            "When script trust is active, author and invoke one cohesive draft_script for animation generation unless the "
            "user explicitly requests helpers. Use run_animation_workflow as the bounded helper path when trust is off, "
            "helpers were requested, or one exact helper completely expresses the motion. "
            "Use evaluator, validation, playblast-review, and evidence helpers after generation. "
            "When rendered visual evidence is needed for object details, use capture_object_inspection_renders. "
            "Under trust, static findings are advisory and the script runs immediately."
        ),
    },
    "advanced_scene_workflow": {
        "name": "advanced_scene_workflow",
        "title": "Plan Advanced 3D And 2D Workflow",
        "description": "Guide an MCP client through capability-routed advanced authoring, simulation, and render planning.",
        "arguments": [
            {
                "name": "goal",
                "description": "The advanced Blender scene, 2D, animation, simulation, or render goal.",
                "required": True,
            }
        ],
        "template": (
            "Handle this advanced Blender task through capability-routed planning: {goal}\n\n"
            "Call plan_advanced_scene_workflow first when scene context or domain boundaries are unclear. With active "
            "script trust, prefer one cohesive draft_script for authored 2D/3D object generation, modeling, animation, "
            "materials, nodes, and rigging unless the user requests helpers. Inspect relevant scene, geometry-node, rig, "
            "or material state before authoring the script. Use exact helpers for isolated operations when requested. For cloth setup, use "
            "add_cloth_simulation_to_selected, then get_simulation_details or inspect_simulation_bake before any "
            "persistent bake. For render-pass, cryptomatte, or shader AOV setup, prefer configure_render_outputs before custom compositor/render Python. "
            "For look-dev review, prefer create_lookdev_turntable_review to set up bounded staging/turntable, render controls, inspection stills, and artifact validation. "
            "Static findings are advisory under trust. Prefer bounded structured tools for external assets and project files "
            "when their validation or recovery helps. Persistent bake/free scripts may run under active trust and can block Blender."
        ),
    },
    "reference_modeling_workflow": {
        "name": "reference_modeling_workflow",
        "title": "Build A Model From Visual Reference",
        "description": "Guide an MCP client through adaptive visual decomposition, model-quality planning, evidence scoring, repair, and preview review.",
        "arguments": [
            {
                "name": "goal",
                "description": "The model creation, comparison, or repair goal tied to a supplied visual reference.",
                "required": True,
            },
            {
                "name": "reference_notes",
                "description": "Optional source, crop, view, or ambiguity notes supplied with the visual reference.",
                "required": False,
            },
        ],
        "template": (
            "Build, compare, or repair a Blender model against the actual supplied visual reference: {goal}\n"
            "Reference notes: {reference_notes}\n\n"
            "Use compact gateway search, fetch only selected helper schemas, and invoke helpers through "
            "invoke_blender_tool. Analyze the actual image into a structured reference_brief containing silhouette, "
            "primary masses, secondary forms, landmarks, measurable proportion checks, explicit surface cues, negative "
            "constraints, source notes, and inspection views. Use only supplied or visibly measured values; do not invent "
            "focal lengths, tolerances, material parameters, anatomy, dimensions, or symmetry. Preserve unresolved "
            "ambiguity. Do not use canned category bases, category-specific builders, memorized anatomy, or geometry "
            "recipes. Fetch and invoke plan_model_quality_workflow as the required entry point, then follow "
            "its construction_strategy, next_tool_calls, and deferred_tool_calls instead of stopping at the plan. "
            "For continuous masses, cavities, attachments, and tapered paths, prefer compile_shape_program, inspect its "
            "stored graph, and revise exact named nodes with update_shape_program. Use uniform meshing for broad iteration, "
            "then adaptive_dual with explicit local refinement regions after proportions stabilize. Use sample_shape_program_sdf when "
            "boolean behavior is uncertain. When required geometry falls outside that bounded vocabulary and script "
            "trust is active, author one cohesive draft_script for primary construction and broad repairs. Read "
            "bpy.app.version and validate version-sensitive RNA enum identifiers before assignment. For localized "
            "image-space form repair, define persistent named regions with "
            "define_semantic_sculpt_regions, inspect their coverage, and choose exactly one of apply_semantic_sculpt, "
            "apply_screen_space_sculpt, or optimize_screen_space_sculpt. Prefer the optimizer when calibrated silhouette "
            "evidence is available because it retains only a measured improvement. Inspect the baseline scene, "
            "refresh after construction, resolve actual existing and newly created target names, and pass them into "
            "later inspections and evidence calls. Gate surface detail behind silhouette, proportion, landmark, and form "
            "scores at or above the quality floor. Capture a reference-matched viewport plus stable front and side/profile "
            "views, repair the weakest failed criteria for no more than the planner's bounded pass limit, and recapture "
            "the same evidence after each pass. Create durable quality state with start_model_quality_review, request "
            "blind packets, submit complete scorecards, and record each repair before rescoring. Apply only surface "
            "treatments visible in the reference. Passing every gate means ready_for_user_review, not committed or "
            "saved. Leave the final preview pending until the user "
            "explicitly chooses commit_preview or revert_preview."
        ),
    },
    "external_asset_workflow": {
        "name": "external_asset_workflow",
        "title": "Use Async External Asset Workflow",
        "description": "Guide an MCP client through discovery, async download/cache, queued import, and polling for external assets.",
        "arguments": [
            {
                "name": "goal",
                "description": "The external asset search, cache, or import goal.",
                "required": True,
            }
        ],
        "template": (
            "Handle this Blender external asset task through the async job workflow: {goal}\n\n"
            "Use list_poly_haven_categories, search_poly_haven_assets, inspect_poly_haven_asset_files, "
            "or search_sketchfab_models for discovery. For any download/cache or import request, first choose "
            "a concrete Poly Haven asset_id or Sketchfab uid, then call start_external_asset_download and "
            "poll get_external_asset_job_status until completed or failed. Then call start_external_asset_import_job for scene import and poll "
            "get_external_asset_import_job_status until completed or failed. After import completes, call "
            "prepare_imported_asset_presentation with imported_object_names from the import result before "
            "visual evidence capture. Use cancel_external_asset_job or "
            "cancel_external_asset_import_job if the user asks to stop. Treat download_poly_haven_asset, "
            "import_poly_haven_asset, download_sketchfab_model, import_sketchfab_model, and "
            "import_external_asset_job_result as synchronous fallback/debug paths, not the normal client workflow."
        ),
    },
    "trusted_script": {
        "name": "trusted_script",
        "title": "Run Session-Trusted Blender Python",
        "description": "Run Blender Python after the user enables Trust Agent Scripts inside Blender.",
        "arguments": [
            {
                "name": "goal",
                "description": "The scripted Blender task.",
                "required": True,
            }
        ],
        "template": (
            "Run Blender Python for this task only after the user enables Trust Agent Scripts: {goal}\n\n"
            "Search Blender docs before unfamiliar APIs. Call draft_script with complete code, intent, expected_changes, "
            "risk_level, and target_objects for normal authored work. For a cohesive script likely to exceed the bridge "
            "timeout or benefit from isolated execution, call start_trusted_script_job, poll "
            "get_trusted_script_job_status, and apply the result only after explicit user approval. Trust off refuses "
            "the request; trust on grants Blender Run Script-equivalent permissions. Do not claim success from job "
            "submission or unless synchronous draft_script confirms execution."
        ),
    },
}


def _json_dumps(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=False)


def _stderr(message):
    print(message, file=sys.stderr, flush=True)


def _decode_cursor(cursor):
    if cursor in (None, ""):
        return 0
    try:
        return max(0, int(str(cursor)))
    except ValueError:
        return 0


def _page_items(items, params, result_key):
    params = params or {}
    start = _decode_cursor(params.get("cursor"))
    try:
        requested_limit = int(params.get("limit") or DEFAULT_PAGE_SIZE)
    except (TypeError, ValueError):
        requested_limit = DEFAULT_PAGE_SIZE
    limit = max(1, min(MAX_PAGE_SIZE, requested_limit))
    end = min(len(items), start + limit)
    result = {result_key: items[start:end]}
    if end < len(items):
        result["nextCursor"] = str(end)
    return result


_validate_schema = bridge_protocol.validate_arguments


def _normalize_tool_definition(tool):
    result = dict(tool or {})
    result.setdefault("inputSchema", result.pop("input_schema", {"type": "object"}))
    result.setdefault("outputSchema", GENERIC_OUTPUT_SCHEMA)
    result.setdefault("annotations", {})
    result["annotations"] = _tool_annotations(result)
    return result


def _client_input_schema(schema):
    """Return a host-compatible schema while retaining canonical validation internally."""

    result = copy.deepcopy(schema if isinstance(schema, dict) else {"type": "object"})
    requirement_hints = []
    for combiner in ("anyOf", "oneOf", "allOf"):
        branches = result.pop(combiner, None)
        if branches is None:
            continue
        if not isinstance(branches, list) or not branches:
            raise ValueError(f"Unsupported top-level {combiner} in MCP input schema")
        required_sets = []
        for branch in branches:
            if not isinstance(branch, dict) or set(branch) != {"required"}:
                raise ValueError(f"Cannot safely flatten top-level {combiner} in MCP input schema")
            required = branch.get("required")
            if not isinstance(required, list) or not required or not all(isinstance(item, str) for item in required):
                raise ValueError(f"Invalid required-property branch in top-level {combiner}")
            required_sets.append(required)
        if combiner == "allOf":
            merged_required = list(result.get("required") or [])
            for required in required_sets:
                for name in required:
                    if name not in merged_required:
                        merged_required.append(name)
            result["required"] = merged_required
            continue
        alternatives = [" + ".join(required) for required in required_sets]
        qualifier = "At least one" if combiner == "anyOf" else "Exactly one"
        requirement_hints.append(f"{qualifier} of these property sets is required: {'; '.join(alternatives)}.")
    if requirement_hints:
        description = str(result.get("description") or "").strip()
        result["description"] = " ".join(part for part in (description, *requirement_hints) if part)
    return result


def _client_tool_definition(tool):
    result = dict(tool if isinstance(tool, dict) else {})
    result["inputSchema"] = _client_input_schema(result.get("inputSchema"))
    result["inputSchema"] = response_controls.discovery_input_schema(
        result.get("name"),
        result["inputSchema"],
    )
    # Output schemas remain canonical internally and are available through
    # get_blender_tool_schema. They are optional in MCP tools/list and add
    # substantial context without helping the model choose or call a tool.
    result.pop("outputSchema", None)
    result["annotations"] = _client_tool_annotations(result.get("annotations"))
    return result


_CLIENT_ANNOTATION_ALWAYS = frozenset(
    {
        "mutatesScene",
        "hasSideEffects",
        "requiresApproval",
        "requiresLivePreview",
        "riskLevel",
        "permissions",
        "readOnlyHint",
        "destructiveHint",
        "idempotentHint",
        "openWorldHint",
    }
)
_CLIENT_ANNOTATION_TRUE_ONLY = frozenset(
    {
        "returnsBackgroundJob",
        "longRunningHint",
        "humanInLoopRequired",
        "requiresUserPath",
        "requiresExplicitOneTimeApproval",
    }
)
_CLIENT_ANNOTATION_FALSE_ONLY = frozenset({"trustWindowAutoRunAllowed"})
_CLIENT_ANNOTATION_NONEMPTY = frozenset(
    {
        "timeoutSeconds",
        "durationHint",
        "timeoutRecovery",
        "pathPolicy",
        "approvalPolicy",
        "recoveryHint",
    }
)


def _client_tool_annotations(annotations):
    """Project canonical annotations into a capability-preserving sparse discovery view."""

    annotations = dict(annotations or {})
    result = {}
    for key, value in annotations.items():
        if key in _CLIENT_ANNOTATION_ALWAYS:
            result[key] = copy.deepcopy(value)
        elif key in _CLIENT_ANNOTATION_TRUE_ONLY and value is True:
            result[key] = True
        elif key in _CLIENT_ANNOTATION_FALSE_ONLY and value is False:
            result[key] = False
        elif key in _CLIENT_ANNOTATION_NONEMPTY and value not in ("", None, False, 0, [], {}):
            result[key] = copy.deepcopy(value)
    return result


def _contract_tool_definition(name, contract):
    normalized = bridge_protocol.normalized_tool_contract(name, contract)
    return {
        "name": name,
        "title": normalized.get("title") or name.replace("_", " ").title(),
        "description": normalized.get("description", ""),
        "inputSchema": normalized.get("input_schema") or {"type": "object", "properties": {}, "additionalProperties": True},
        "outputSchema": normalized.get("output_schema") or GENERIC_OUTPUT_SCHEMA,
        "annotations": bridge_protocol.mcp_annotations_for_tool(name),
    }


def _read_only_annotations(permissions=None):
    return {
        "mutatesScene": False,
        "hasSideEffects": False,
        "requiresApproval": False,
        "requiresLivePreview": False,
        "riskLevel": "read",
        "permissions": list(permissions or ["tools:read"]),
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }


def _gateway_tool_definitions():
    return [
        {
            "name": CATALOG_TOOL_NAME,
            "title": "Blender Tool Catalog",
            "description": (
                "Universal gateway to every Blender helper. Search, inspect schemas, or invoke scene inspection, "
                "modeling, materials, nodes, rigging, animation, simulation, camera, lighting, rendering, viewport "
                "capture, external assets, trusted scripts, and preview commit/revert tools."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["search", "schema", "invoke", "categories"],
                        "description": "Catalog action. Defaults to search.",
                    },
                    "query": {"type": "string", "description": "Search text such as material, camera, script, or preview"},
                    "limit": {"type": "integer", "description": "Maximum matching tools to return"},
                    "name": {"type": "string", "description": "Tool name for schema or invoke actions"},
                    "operation_id": {"type": "string", "minLength": 1, "maxLength": 128, "description": "Optional idempotency key for invocation; use status to recover an ambiguous result."},
                    "known_digest": {
                        "type": "string",
                        "minLength": 8,
                        "maxLength": 64,
                        "description": "Prior schema digest for a tiny not_modified schema response.",
                    },
                    "arguments": {"type": "object", "description": "Target tool arguments for invoke", "additionalProperties": True},
                    "category": {"type": "string", "description": "Filter by catalog category"},
                    "permission": {"type": "string", "description": "Filter by a required permission such as scene:mutate"},
                    "mutates_scene": {"type": "boolean", "description": "Filter by whether tools can mutate the scene"},
                    "requires_approval": {"type": "boolean", "description": "Filter by approval requirement"},
                    "requires_live_preview": {"type": "boolean", "description": "Filter by live-preview requirement"},
                    "risk_level": {"type": "string", "description": "Filter by risk level such as read, preview, or approval"},
                    "include_schemas": {"type": "boolean", "description": "Include input/output schemas in search results"},
                },
                "additionalProperties": False,
            },
            "outputSchema": GENERIC_OUTPUT_SCHEMA,
            "annotations": {
                "mutatesScene": True,
                "hasSideEffects": True,
                "requiresApproval": False,
                "requiresLivePreview": False,
                "riskLevel": "dynamic",
                "permissions": ["tools:read", "scene:read", "scene:mutate", "script:trusted_run"],
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": False,
            },
        },
        {
            "name": "search_blender_tools",
            "title": "Search Blender Tools",
            "description": (
                "Search every Blender helper by name, description, category, risk, and permissions. Use this for "
                "scene inspection, modeling, materials, nodes, rigging, animation, simulation, camera, lighting, "
                "rendering, viewport capture, external assets, trusted scripts, and preview commit/revert. Returns "
                "compact summaries; then call get_blender_tool_schema for one selected tool."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search text such as material, camera, script, or preview"},
                    "limit": {"type": "integer", "description": "Maximum matching tools to return"},
                    "category": {"type": "string", "description": "Filter by catalog category"},
                    "permission": {"type": "string", "description": "Filter by a required permission such as scene:mutate"},
                    "mutates_scene": {"type": "boolean", "description": "Filter by whether tools can mutate the scene"},
                    "requires_approval": {"type": "boolean", "description": "Filter by approval requirement"},
                    "requires_live_preview": {"type": "boolean", "description": "Filter by live-preview requirement"},
                    "risk_level": {"type": "string", "description": "Filter by risk level such as read, preview, or approval"},
                    "include_schemas": {
                        "type": "boolean",
                        "description": "Include input/output schemas in search results. Defaults to false to protect context budget.",
                    },
                },
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "ok": {"type": "boolean"},
                    "tools": {"type": "array"},
                    "count": {"type": "integer"},
                },
                "required": ["ok", "tools"],
                "additionalProperties": True,
            },
            "annotations": _read_only_annotations(),
        },
        {
            "name": "get_blender_tool_schema",
            "title": "Get Blender Tool Schema",
            "description": (
                "Return the canonical input schema, output schema, and safety annotations for any Blender helper "
                "named by a planner or search result, including helpers not advertised as top-level tools. Pass a "
                "prior known_digest to receive a tiny not_modified response when unchanged."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "known_digest": {
                        "type": "string",
                        "minLength": 8,
                        "maxLength": 64,
                        "description": "Schema digest returned by an earlier call.",
                    },
                },
                "required": ["name"],
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "ok": {"type": "boolean"},
                    "tool": {"type": "object"},
                },
                "required": ["ok"],
                "additionalProperties": True,
            },
            "annotations": _read_only_annotations(),
        },
        {
            "name": "invoke_blender_tool",
            "title": "Invoke Blender Tool",
            "description": (
                "Execute any Blender helper from the complete catalog after looking up its schema: scene inspection, "
                "modeling, materials, nodes, rigging, animation, simulation, cameras, lights, renders, viewport "
                "evidence, external assets, trusted scripts, and preview commit/revert. The target schema is validated "
                "before forwarding to Blender."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "arguments": {"type": "object", "additionalProperties": True},
                    "operation_id": {"type": "string", "minLength": 1, "maxLength": 128},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
            "outputSchema": GENERIC_OUTPUT_SCHEMA,
            "annotations": {
                "mutatesScene": True,
                "hasSideEffects": True,
                "requiresApproval": False,
                "requiresLivePreview": False,
                "riskLevel": "dynamic",
                "permissions": ["scene:read", "scene:mutate", "script:trusted_run"],
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": False,
            },
        },
    ]


def _static_tool_definitions():
    tools = []
    seen = set()
    try:
        for tool in agent_tools.blender_tool_definitions():
            name = str(tool.get("name") or "")
            if not name:
                continue
            contract = bridge_protocol.normalized_tool_contract(
                name,
                bridge_protocol.TOOL_CONTRACTS.get(name, {}),
            )
            tools.append(
                {
                    "name": name,
                    "title": contract.get("title") or name.replace("_", " ").title(),
                    "description": tool.get("description", contract.get("description", "")),
                    "inputSchema": tool.get("input_schema") or tool.get("inputSchema") or {"type": "object"},
                    "outputSchema": contract.get("output_schema") or GENERIC_OUTPUT_SCHEMA,
                    "annotations": bridge_protocol.mcp_annotations_for_tool(name),
                }
            )
            seen.add(name)
    except Exception as exc:
        _stderr(f"static tools warning: {exc}")
    for name, contract in bridge_protocol.TOOL_CONTRACTS.items():
        if name not in seen:
            tools.append(_contract_tool_definition(name, contract))
            seen.add(name)
    return tools


def _merge_tool_definitions(primary, fallback):
    merged = []
    seen = set()
    for tool in list(primary or []) + list(fallback or []):
        name = str((tool or {}).get("name") or "")
        if not name or name in seen:
            continue
        merged.append(_normalize_tool_definition(tool))
        seen.add(name)
    return merged


def _truthy_env(name):
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _bounded_limit(value, default=12, maximum=50):
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = int(default)
    return max(1, min(int(maximum), result))


def _tool_result(content_text, structured, *, is_error=False):
    if not isinstance(structured, dict):
        structured = {"ok": not is_error, "text": str(content_text)}
    structured.setdefault("ok", not is_error)
    return {
        "content": [{"type": "text", "text": str(content_text)}],
        "structuredContent": structured,
        "isError": bool(is_error),
    }


def _json_text(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _catalog_search_content(structured):
    tools = list((structured or {}).get("tools") or [])
    lines = [
        f"Found {len(tools)} of {int((structured or {}).get('total', len(tools)) or 0)} matching Blender tools."
    ]
    for tool in tools:
        name = str(tool.get("name") or "")
        category = str(tool.get("category") or "other")
        risk = str(tool.get("risk_level") or "unknown")
        description = str(tool.get("description") or "").strip()
        flags = []
        if tool.get("mutates_scene"):
            flags.append("mutates scene")
        if tool.get("requires_live_preview"):
            flags.append("live preview")
        if tool.get("returns_background_job"):
            flags.append("background job")
        if tool.get("long_running"):
            flags.append("long-running")
        suffix = f"; {', '.join(flags)}" if flags else ""
        lines.append(f"- {name} [{category}; {risk}{suffix}]: {description}")
        for warning in tool.get("guardrail_warnings") or []:
            message = str((warning or {}).get("message") or "").strip()
            if message:
                lines.append(f"  Warning: {message}")
    if not (structured or {}).get("include_schemas"):
        lines.append("Call get_blender_tool_schema for the selected tool, then invoke_blender_tool.")
    return "\n".join(lines)


def _bridge_status_content(status):
    status = dict(status or {})
    if status.get("operation_id"):
        return _json_text(status)
    if status.get("ok"):
        blocking = [item for item in (status.get("blocking_issues") or []) if isinstance(item, dict)]
        if blocking:
            # Lead with the blocker. Reporting "connected" first and burying the
            # incompatibility reads as healthy, and the caller only discovers
            # otherwise when their first mutating call is refused.
            lines = [
                "BLOCKED: the Blender bridge is reachable but mutating tools will be refused.",
            ]
            for item in blocking:
                lines.append(
                    "- %s %s" % (str(item.get("message") or "").strip(), str(item.get("remedy") or "").strip())
                )
            lines.append("Read-only inspection still works, so this will not surface until a tool tries to change the scene.")
            return " ".join(part for part in lines if part.strip())

        # Stale source leads for the same reason a blocker does. Calls still
        # succeed, which is exactly the problem: they succeed against tools
        # from before the add-on files changed, and the caller has no way to
        # tell. Observed -- a session ran for some time on old code while the
        # reader reported the harmless config-hash note instead, because that
        # one was the more prominent of the two.
        if status.get("addon_runtime_source_stale"):
            guidance = str(status.get("addon_reload_guidance") or "").strip()
            return " ".join(
                part
                for part in (
                    "STALE: the Blender add-on files changed after Blender loaded them, so "
                    "tools are being served from the older code.",
                    guidance or "Reload scripts in Blender, or restart it.",
                    "Everything below describes the loaded version, not the files on disk.",
                )
                if part
            )

        parts = ["Blender bridge is connected."]
        tool_surface_name = str(status.get("mcp_tool_surface") or "").strip()
        if tool_surface_name:
            parts.append(f"MCP tool surface: {tool_surface_name}.")
        compatibility = str(status.get("compatibility_message") or "").strip()
        if compatibility:
            parts.append(compatibility)
        if status.get("bridge_busy"):
            parts.append(
                f"Blender is busy; retry after {int(status.get('poll_after_seconds') or 5)} seconds."
            )
        trust_status = str(status.get("external_script_trust_status") or "").strip()
        if trust_status:
            parts.append(f"Script trust: {trust_status}.")
        return " ".join(parts)
    message = str(status.get("message") or "Bridge unavailable.").strip()
    return f"Blender bridge is unavailable: {message}"


def _tool_error(message, *, code="tool_error", data=None):
    structured = {"ok": False, "code": str(code), "message": str(message)}
    if data is not None:
        structured["data"] = data
        if isinstance(data, dict) and data.get("operation_id"):
            structured["operation_id"] = data["operation_id"]
    return _tool_result(_json_text(structured), structured, is_error=True)


def _guardrail_warnings_for_call(name, arguments, tool=None):
    if isinstance(tool, dict):
        guardrail_tool = dict(tool)
        guardrail_tool.setdefault("name", str(name or ""))
    else:
        guardrail_tool = {"name": str(name or "")}
        try:
            guardrail_tool["annotations"] = bridge_protocol.mcp_annotations_for_tool(str(name or ""))
        except Exception:
            guardrail_tool["annotations"] = {}
    return _guardrail_warnings_for_tool(guardrail_tool, arguments if isinstance(arguments, dict) else {})


def _attach_guardrail_warnings(structured, name, arguments, tool=None):
    warnings = _guardrail_warnings_for_call(name, arguments, tool=tool)
    if not warnings or not isinstance(structured, dict):
        return structured
    existing = structured.get("guardrail_warnings")
    if not isinstance(existing, list):
        existing = []
    seen = {str(item.get("code") or "") for item in existing if isinstance(item, dict)}
    deduped = list(existing)
    for warning in warnings:
        code = str(warning.get("code") or "")
        if code and code in seen:
            continue
        deduped.append(warning)
        if code:
            seen.add(code)
    structured["guardrail_warnings"] = deduped
    structured["guardrail_warning_count"] = len(structured["guardrail_warnings"])
    return structured


def _audit_tool_call(name, arguments, result, *, tool=None):
    try:
        structured = result.get("structuredContent") if isinstance(result, dict) else {}
        annotations = _tool_annotations(tool or {"name": str(name or "")})
        tool_name = _bounded_tool_identifier(name)
        audit_log.append_event(
            "mcp_tool_call",
            source="mcp",
            tool_name=tool_name,
            ok=bool(structured.get("ok", False)) if isinstance(structured, dict) else False,
            is_error=bool(result.get("isError", True)) if isinstance(result, dict) else True,
            code=structured.get("code", "") if isinstance(structured, dict) else "",
            risk_level=annotations.get("riskLevel", ""),
            mutates_scene=bool(annotations.get("mutatesScene", False)),
            requires_approval=bool(annotations.get("requiresApproval", False)),
            arguments=audit_log.summarize_arguments(arguments),
        )
        execution_traces.record_tool_call(
            layer="mcp",
            operation_id=(result.get("structuredContent") or {}).get("operation_id", ""),
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            contract=annotations,
        )
    except Exception as exc:
        _stderr(f"audit warning: {exc}")


def _bounded_tool_identifier(name):
    requested_name = str(name or "")
    return requested_name if requested_name in TELEMETRY_TOOL_NAMES else "(unknown)"


class BlenderMCPServer:
    def __init__(self, bridge):
        self.bridge = bridge
        self._tool_cache = None
        self._full_tool_cache = None
        self._log_level = "info"
        self._tool_surface = tool_surface.resolve()
        self._compatibility_cache = None
        self._compatibility_cache_at = 0.0
        self._payload_telemetry = {}

    def initialize(self, params):
        requested = (params or {}).get("protocolVersion") or PROTOCOL_VERSION
        protocol = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
        return {
            "protocolVersion": protocol,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False},
                "prompts": {"listChanged": False},
                "logging": {},
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "title": "Blender Agent Bridge",
                "version": SERVER_VERSION,
            },
            "instructions": (
                "Connects MCP-capable AI clients to the running Blender scene through the Blender Agent Bridge localhost service. "
                "Start the bridge inside Blender before using scene tools. By default, tools/list exposes exactly five "
                "stable gateway tools. The complete Blender helper catalog remains reachable through "
                "search_blender_tools, get_blender_tool_schema, and invoke_blender_tool. A planner may name helpers "
                "that are not top-level tools; this means they must be looked up and invoked through the gateway, not "
                "that they are unavailable. Mutating tools affect the live scene and may leave preview changes pending. "
                "For broad advanced 3D, 2D/storyboard, animation, simulation, or render tasks, call "
                "plan_advanced_scene_workflow first when the helper path is unclear. "
                "When session script trust is active, prefer one cohesive draft_script for authored object generation, "
                "modeling, animation, materials, custom nodes, rigging, and look development unless the user explicitly "
                "requests helpers, a helper path, or no Python. For mixed requests, keep the authored script path and "
                "route project files, external assets, long jobs, evidence, and preview decisions through bounded "
                "helpers; those operational clauses do not demote the authored work. "
                "For cohesive scripts likely to exceed the bridge timeout, use start_trusted_script_job, poll "
                "get_trusted_script_job_status, and apply the copied-file result only after explicit user approval. "
                "For substantial authored runs, start and finalize an execution trace. Reference-model workflows must "
                "advance durable blind scoring and bounded repair state to ready_for_user_review or "
                "blocked_quality_floor. "
                "For external asset downloads/imports, use the async path by default after discovery selects a concrete "
                "asset_id or uid: start_external_asset_download, poll get_external_asset_job_status, then start_external_asset_import_job and poll "
                "get_external_asset_import_job_status, then call prepare_imported_asset_presentation for cleanup/staging. Treat direct provider download/import tools as synchronous "
                "fallbacks for explicit direct/debug use. "
                "If a bridge_timeout occurs, treat it as recoverable: wait the returned poll_after_seconds, call "
                "blender_bridge_status, then inspect visual evidence resources or audit logs before rerunning work. "
                "Generated Python is refused unless the user enables session script trust in Blender. Once enabled, "
                "trusted Python has Blender Run Script-equivalent filesystem, network, process, and Blender API access. "
                "Large read-only inspectors keep full responses by default; their on-demand schemas support optional "
                "summary, fields, pagination, and known_digest controls, and a digest mismatch always returns the "
                "complete current result."
            ),
        }

    def _bridge_status_tool(self):
        return {
            "name": "blender_bridge_status",
            "title": "Blender Bridge Status",
            "description": "Check whether the MCP server can reach the running Blender localhost bridge.",
            "inputSchema": {"type": "object", "properties": {"operation_id": {"type": "string", "minLength": 1, "maxLength": 128, "description": "Recover retained operation state and result without waiting for Blender."}}, "additionalProperties": False},
            "outputSchema": STATUS_OUTPUT_SCHEMA,
            "annotations": {
                "mutatesScene": False,
                "riskLevel": "read",
                "permissions": ["bridge:status"],
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def _load_full_tools(self):
        bridge_tools = []
        try:
            response = self.bridge.get("/tools")
            bridge_tools = response.get("tools") or []
        except Exception as exc:
            _stderr(f"tools/list bridge warning: {exc}")
        tools = _merge_tool_definitions(bridge_tools, _static_tool_definitions())
        self._full_tool_cache = tools
        return tools

    def _full_tool_definition(self, name):
        tools = self._full_tool_cache or self._load_full_tools()
        for tool in tools:
            if tool.get("name") == name:
                return tool
        tools = self._load_full_tools()
        for tool in tools:
            if tool.get("name") == name:
                return tool
        return None

    def _load_tools(self):
        definitions = {
            tool["name"]: _normalize_tool_definition(tool)
            for tool in _gateway_tool_definitions()
        }
        definitions["blender_bridge_status"] = self._bridge_status_tool()
        full_tools = []
        if self._tool_surface != tool_surface.GATEWAY:
            full_tools = self._load_full_tools()
            for tool in full_tools:
                name = str(tool.get("name") or "")
                if name and name not in definitions:
                    definitions[name] = tool
        advertised = tool_surface.advertised_names(
            self._tool_surface,
            GATEWAY_TOOL_NAMES,
            DIRECT_TOOL_NAMES,
            tuple(tool["name"] for tool in full_tools),
        )
        tools = [definitions[name] for name in advertised if name in definitions]
        self._tool_cache = tools
        return tools

    def _tool_definition(self, name):
        tools = self._tool_cache or self._load_tools()
        for tool in tools:
            if tool.get("name") == name:
                return tool
        tools = self._load_tools()
        for tool in tools:
            if tool.get("name") == name:
                return tool
        return None

    def _bridge_tool_arguments(self, name, arguments):
        if name == "start_external_asset_download" and str((arguments or {}).get("provider") or "").strip().lower() != "sketchfab":
            return arguments
        if name in SKETCHFAB_AUTH_FORWARD_TOOLS:
            return external_assets.sketchfab_auth_arguments_from_env(arguments)
        return arguments

    def tools_list(self, params=None):
        page = _page_items(self._load_tools(), params, "tools")
        page["tools"] = [_client_tool_definition(tool) for tool in page["tools"]]
        return page

    def tools_call(self, params):
        result = self._tools_call(params)
        params = params or {}
        tool_name = params.get("name")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        if tool_name == "invoke_blender_tool":
            tool_name = arguments.get("name") or tool_name
        elif tool_name == CATALOG_TOOL_NAME and arguments.get("action") == "invoke":
            tool_name = arguments.get("name") or tool_name
        self._record_payload_size(tool_name, result)
        return result

    def _record_payload_size(self, name, result):
        tool_name = _bounded_tool_identifier(name)
        size_bytes = len(_json_text(result).encode("utf-8"))
        entry = self._payload_telemetry.setdefault(
            tool_name,
            {
                "tool_name": tool_name,
                "call_count": 0,
                "total_response_bytes": 0,
                "max_response_bytes": 0,
                "last_response_bytes": 0,
            },
        )
        entry["call_count"] += 1
        entry["total_response_bytes"] += size_bytes
        entry["max_response_bytes"] = max(entry["max_response_bytes"], size_bytes)
        entry["last_response_bytes"] = size_bytes

    def _payload_telemetry_summary(self):
        tools = []
        for entry in self._payload_telemetry.values():
            row = dict(entry)
            row["average_response_bytes"] = int(
                round(row["total_response_bytes"] / max(1, row["call_count"]))
            )
            tools.append(row)
        tools.sort(key=lambda item: (-item["total_response_bytes"], item["tool_name"]))
        return {
            "tools": tools,
            "tool_count": len(tools),
            "call_count": sum(item["call_count"] for item in tools),
            "total_response_bytes": sum(item["total_response_bytes"] for item in tools),
            "privacy": "Contains only tool identifiers and response byte counts.",
        }

    def _tools_call(self, params):
        params = params or {}
        name = params.get("name")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(name, str) or not name:
            result = _tool_error("Missing tool name", code="invalid_request")
            _audit_tool_call(name, arguments, result)
            return result
        if not isinstance(arguments, dict):
            result = _tool_error("Tool arguments must be a JSON object", code="invalid_arguments")
            _audit_tool_call(name, arguments, result)
            return result
        tool = self._tool_definition(name)
        if tool is None:
            result = _tool_error(f"Unknown tool: {name}", code="unknown_tool")
            _audit_tool_call(name, arguments, result)
            return result
        call_arguments = self._bridge_tool_arguments(name, arguments)
        validation_errors = _validate_schema(call_arguments, tool.get("inputSchema") or {"type": "object"})
        if validation_errors:
            result = _tool_error(
                "Tool arguments failed schema validation",
                code="invalid_arguments",
                data={"errors": validation_errors},
            )
            _audit_tool_call(name, call_arguments, result, tool=tool)
            return result
        if name == "blender_bridge_status":
            status = self._bridge_status(str(arguments.get("operation_id") or ""))
            result = _tool_result(
                _bridge_status_content(status),
                status,
                is_error=not bool(status.get("ok")),
            )
            _audit_tool_call(name, arguments, result, tool=tool)
            return result
        if name == "search_blender_tools":
            result = self._search_blender_tools(arguments)
            _audit_tool_call(name, arguments, result, tool=tool)
            return result
        if name == CATALOG_TOOL_NAME:
            result = self._blender_tool_catalog(arguments)
            _audit_tool_call(name, arguments, result, tool=tool)
            return result
        if name == "get_blender_tool_schema":
            result = self._get_blender_tool_schema(arguments)
            _audit_tool_call(name, arguments, result, tool=tool)
            return result
        if name == "invoke_blender_tool":
            result = self._invoke_blender_tool(arguments)
            _audit_tool_call(name, arguments, result, tool=tool)
            return result
        compatibility_error = self._compatibility_error()
        if compatibility_error is not None:
            _audit_tool_call(name, call_arguments, compatibility_error, tool=tool)
            return compatibility_error
        operation_id = uuid.uuid4().hex
        try:
            response = self.bridge.post(
                "/tool",
                {"name": name, "arguments": call_arguments, "operation_id": operation_id},
                timeout=_bridge_timeout_for_tool(name),
            )
        except BridgeTimeoutError as exc:
            result = _tool_error(str(exc), code="bridge_timeout", data=dict(getattr(exc, "data", {}), operation_id=operation_id))
            _audit_tool_call(name, call_arguments, result, tool=tool)
            return result
        except Exception as exc:
            result = _tool_error(str(exc), code="bridge_unavailable", data={"operation_id": operation_id, "status_tool": "blender_bridge_status", "request_may_still_be_running": True})
            _audit_tool_call(name, call_arguments, result, tool=tool)
            return result
        result = response.get("result", response)
        if isinstance(result, dict):
            result.setdefault("operation_id", response.get("operation_id", operation_id))
        ok = bool(response.get("ok", True)) and bool(result.get("ok", True) if isinstance(result, dict) else True)
        result = _attach_guardrail_warnings(result, name, call_arguments, tool=tool)
        text = _json_text(result)
        tool_result = _tool_result(text, result if isinstance(result, dict) else {"text": text}, is_error=not ok)
        _audit_tool_call(name, call_arguments, tool_result, tool=tool)
        return tool_result

    def _search_catalog(self, arguments):
        limit = _bounded_limit(arguments.get("limit"), default=12, maximum=50)
        include_schemas = bool(arguments.get("include_schemas", False))
        filters = _catalog_filters(arguments)
        matches = []
        for tool in self._load_full_tools():
            if not _tool_matches_filters(tool, filters):
                continue
            score = _score_tool_match(tool, filters["query"])
            if score is None:
                continue
            matches.append((score, str(tool.get("name") or ""), tool))
        matches.sort(key=lambda item: (-item[0], item[1]))
        tools = [_tool_summary(tool, include_schema=include_schemas) for _, _, tool in matches[:limit]]
        structured = {
            "ok": True,
            "query": filters["query"],
            "count": len(tools),
            "total": len(matches),
            "include_schemas": include_schemas,
            "schema_lookup_tool": "get_blender_tool_schema",
            "invoke_tool": "invoke_blender_tool",
            "tools": tools,
            "filters": {
                key: value
                for key, value in filters.items()
                if value not in ("", None)
            },
        }
        return _tool_result(_catalog_search_content(structured), structured)

    def _search_blender_tools(self, arguments):
        return self._search_catalog(arguments)

    def _catalog_categories(self, arguments):
        filters = _catalog_filters(arguments)
        tools = [
            tool
            for tool in self._load_full_tools()
            if _tool_matches_filters(tool, filters) and _score_tool_match(tool, filters["query"]) is not None
        ]
        structured = {"ok": True, "total": len(tools), "facets": _catalog_facets(tools)}
        return _tool_result(_json_text(structured), structured)

    def _blender_tool_catalog(self, arguments):
        action = str(arguments.get("action") or "search").strip().lower()
        if action == "search":
            return self._search_catalog(arguments)
        if action == "categories":
            return self._catalog_categories(arguments)
        if action == "schema":
            return self._get_blender_tool_schema(
                {
                    "name": arguments.get("name"),
                    "known_digest": arguments.get("known_digest"),
                }
            )
        if action == "invoke":
            return self._invoke_blender_tool(
                {
                    "name": arguments.get("name"),
                    "arguments": arguments.get("arguments") or {},
                    "operation_id": arguments.get("operation_id"),
                }
            )
        return _tool_error(f"Unknown catalog action: {action}", code="invalid_arguments")

    def _get_blender_tool_schema(self, arguments):
        name = str(arguments.get("name") or "").strip()
        # Canonical schema lookup must prefer the full registry definition.
        # Directly advertised tools use a compact discovery projection that
        # intentionally omits optional response controls.
        tool = self._full_tool_definition(name) or self._tool_definition(name)
        if tool is None:
            return _tool_error(f"Unknown Blender tool: {name}", code="unknown_tool")
        normalized = _normalize_tool_definition(tool)
        schema_digest = response_controls.canonical_digest(normalized)
        known_digest = str(arguments.get("known_digest") or "").strip().lower()
        if known_digest and known_digest == schema_digest:
            structured = {
                "ok": True,
                "not_modified": True,
                "name": name,
                "schema_digest": schema_digest,
            }
            return _tool_result(_json_text(structured), structured)
        guardrail_warnings = _guardrail_warnings_for_tool(normalized)
        if guardrail_warnings:
            normalized["guardrail_warnings"] = guardrail_warnings
            normalized["guardrail_warning_count"] = len(guardrail_warnings)
        structured = {
            "ok": True,
            "tool": normalized,
            "schema_digest": schema_digest,
            "not_modified": False,
        }
        return _tool_result(_json_text(structured), structured)

    def _invoke_blender_tool(self, arguments):
        target_name = str(arguments.get("name") or "").strip()
        if target_name in WRAPPER_TOOL_NAMES:
            return _tool_error(f"Cannot invoke MCP wrapper tool through invoke_blender_tool: {target_name}", code="invalid_target")
        target_args = arguments.get("arguments") or {}
        if not isinstance(target_args, dict):
            return _tool_error("Target tool arguments must be a JSON object", code="invalid_arguments")
        target_tool = self._full_tool_definition(target_name)
        if target_tool is None:
            return _tool_error(f"Unknown Blender tool: {target_name}", code="unknown_tool")
        target_args = self._bridge_tool_arguments(target_name, target_args)
        validation_errors = _validate_schema(target_args, target_tool.get("inputSchema") or {"type": "object"})
        if validation_errors:
            return _tool_error(
                "Target tool arguments failed schema validation",
                code="invalid_arguments",
                data={"target": target_name, "errors": validation_errors},
            )
        compatibility_error = self._compatibility_error()
        if compatibility_error is not None:
            return compatibility_error
        operation_id = str(arguments.get("operation_id") or uuid.uuid4().hex)
        try:
            response = self.bridge.post(
                "/tool",
                {"name": target_name, "arguments": target_args, "operation_id": operation_id},
                timeout=_bridge_timeout_for_tool(target_name),
            )
        except BridgeTimeoutError as exc:
            return _tool_error(str(exc), code="bridge_timeout", data=dict(getattr(exc, "data", {}), operation_id=operation_id))
        except Exception as exc:
            return _tool_error(str(exc), code="bridge_unavailable", data={"operation_id": operation_id, "status_tool": "blender_bridge_status", "request_may_still_be_running": True})
        result = response.get("result", response)
        if isinstance(result, dict):
            result.setdefault("operation_id", response.get("operation_id", operation_id))
        ok = bool(response.get("ok", True)) and bool(result.get("ok", True) if isinstance(result, dict) else True)
        if isinstance(result, dict):
            result.setdefault("invoked_tool", target_name)
            structured = result
        else:
            structured = {"ok": ok, "text": str(result), "invoked_tool": target_name}
        structured = _attach_guardrail_warnings(structured, target_name, target_args, tool=target_tool)
        text = _json_text(structured)
        return _tool_result(text, structured, is_error=not ok)

    def _augment_bridge_status(self, status):
        status = dict(status or {})
        message = str(status.get("message") or "")
        timed_out = "timed out" in message.lower() or "timeout" in message.lower()
        if timed_out and not status.get("bridge_busy"):
            status["bridge_busy"] = True
            status["recoverable"] = True
            status["poll_after_seconds"] = int(status.get("poll_after_seconds") or 5)
            status["recovery_hint"] = (
                "The bridge HTTP server is reachable but Blender did not answer the status probe in time. "
                "A main-thread operation may still be running; wait, then retry blender_bridge_status before rerunning tools."
            )
        elif status.get("bridge_busy"):
            status["recoverable"] = bool(status.get("recoverable", True))
            status["poll_after_seconds"] = int(status.get("poll_after_seconds") or 5)
        mcp_source_hash = build_info.source_tree_hash()
        addon_source_hash = str(status.get("addon_source_hash") or "").strip()
        config_source_hash = build_info.expected_source_hash_from_env()
        runtime_mode = build_info.mcp_runtime_mode_from_env()
        mcp_registry_digest = build_info.TOOL_REGISTRY_DIGEST
        addon_registry_digest = str(status.get("tool_registry_digest") or "").strip()
        config_registry_digest = build_info.expected_tool_registry_digest_from_env()
        reported_bridge_version = str(status.get("bridge_version") or "").strip()
        reported_addon_version = str(status.get("addon_version") or "").strip()
        if "addon_loaded_source_hash" not in status:
            status["addon_loaded_source_hash"] = ""
            status["addon_runtime_source_stale"] = False
            status["addon_runtime_source_status"] = "unknown"
            status["addon_runtime_source_message"] = (
                "Bridge did not report loaded-source diagnostics; reload or update the add-on for runtime staleness checks."
            )
        status["mcp_server_source_hash"] = mcp_source_hash
        status["mcp_runtime_mode"] = runtime_mode
        status["mcp_tool_surface"] = self._tool_surface
        status["mcp_tool_registry_digest"] = mcp_registry_digest
        status["mcp_config_tool_registry_digest"] = config_registry_digest
        status["tool_registry_digest_match"] = (
            None if not addon_registry_digest else addon_registry_digest == mcp_registry_digest
        )
        status["bridge_protocol_match"] = (
            None if not reported_bridge_version else reported_bridge_version == bridge_protocol.BRIDGE_VERSION
        )
        status["addon_mcp_version_match"] = (
            None if not reported_addon_version else reported_addon_version == SERVER_VERSION
        )
        compatibility_reasons = []
        blocking_issues = []
        advisory_issues = []
        compatibility_known = bool(addon_registry_digest and reported_bridge_version)

        # Registry digests are reported, never enforced. Only five gateway
        # tools are exposed, and their names are fixed; every helper is
        # resolved at invocation time against the registry running inside
        # Blender. A client config generated against an older registry
        # therefore cannot route a call anywhere wrong -- there is nothing
        # stale for it to route from. Blocking on it bought no safety and
        # cost a copy-config-and-restart cycle after every registry change.
        if addon_registry_digest and addon_registry_digest != mcp_registry_digest:
            advisory_issues.append({
                "code": "addon_mcp_registry_mismatch",
                "message": "The Blender add-on and the running MCP server were built from different tool registries.",
                "impact": "Advisory only. Helpers resolve against the add-on, so calls still route correctly.",
                "remedy": "Reload scripts in Blender (or restart it) if a newly added helper is missing.",
            })
        if config_registry_digest and config_registry_digest != mcp_registry_digest:
            advisory_issues.append({
                "code": "config_registry_mismatch",
                "message": "The MCP client config was generated against a different tool registry.",
                "impact": "Advisory only. The gateway tool names are fixed, so nothing routes from the config.",
                "remedy": "No action needed. Copy MCP Config only if you want the diagnostic to read clean.",
            })

        # A protocol mismatch is the one genuine incompatibility: the two sides
        # would be speaking different request and response shapes.
        if reported_bridge_version and reported_bridge_version != bridge_protocol.BRIDGE_VERSION:
            compatibility_reasons.append("Blender bridge protocol version differs from the MCP runtime")
            blocking_issues.append({
                "code": "bridge_protocol_mismatch",
                "message": "The Blender bridge and the MCP server speak different protocol versions.",
                "remedy": "Install matching add-on and MCP server versions, then restart both.",
            })
        # Surfaced at the top level so a caller cannot miss it among ~60 sibling
        # fields. Empty when nothing is wrong.
        status["blocking_issues"] = blocking_issues
        status["blocked"] = bool(blocking_issues)
        status["advisory_issues"] = advisory_issues
        if compatibility_reasons:
            status["compatible"] = False
            status["compatibility_status"] = "incompatible"
            status["compatibility_message"] = "; ".join(compatibility_reasons)
        elif compatibility_known:
            status["compatible"] = True
            status["compatibility_status"] = "compatible"
            if advisory_issues:
                status["compatibility_message"] = (
                    "Bridge protocol is compatible. Tool registry digests differ, which is "
                    "advisory: helpers resolve against the live registry in Blender."
                )
            else:
                status["compatibility_message"] = (
                    "Bridge protocol and canonical tool registry are compatible."
                    if status["addon_mcp_version_match"] is not False
                    else "Bridge protocol and tool registry are compatible; add-on and MCP versions differ."
                )
        else:
            status["compatible"] = None
            status["compatibility_status"] = "unknown"
            status["compatibility_message"] = (
                "Bridge did not report protocol and tool-registry compatibility metadata."
            )
        status["mcp_external_asset_auth"] = {
            "sketchfab": external_assets.sketchfab_auth_diagnostics(),
            "note": (
                "These credentials are checked in the MCP server process. "
                "For Sketchfab bridge calls, the MCP server forwards API token values to Blender as redacted tool arguments."
            ),
        }
        status["addon_mcp_source_hash_match"] = (
            None if not addon_source_hash else addon_source_hash == mcp_source_hash
        )
        status["mcp_config_source_hash"] = config_source_hash
        status["mcp_config_source_hash_match"] = (
            None if not config_source_hash else config_source_hash == mcp_source_hash
        )
        if runtime_mode == build_info.MCP_RUNTIME_UVX:
            status["addon_mcp_source_hash_match"] = None
            status["mcp_config_source_hash_match"] = None
            status["source_hash_status"] = "not_applicable"
            status["source_hash_message"] = (
                "The uvx/PyPI runtime uses protocol and tool-registry compatibility; filesystem source hashes may differ."
            )
        elif addon_source_hash and addon_source_hash != mcp_source_hash:
            status["source_hash_status"] = "mismatch"
            status["source_hash_message"] = (
                "Running Blender add-on source hash differs from this MCP server source hash; "
                "install or reload the latest add-on zip, copy fresh MCP config, and restart the MCP client."
            )
        elif config_source_hash and config_source_hash != mcp_source_hash:
            status["source_hash_status"] = "mcp_config_mismatch"
            status["source_hash_message"] = (
                "MCP config source hash differs from this MCP server source hash; "
                "copy fresh MCP config and restart the MCP client."
            )
        elif addon_source_hash:
            status["source_hash_status"] = "match"
            status["source_hash_message"] = "Blender add-on and MCP server source hashes match."
        else:
            status["source_hash_status"] = str(status.get("addon_source_hash_status") or "unknown")
            status["source_hash_message"] = str(status.get("addon_source_hash_message") or "")
        return status

    def _compatibility_error(self):
        now = time.monotonic()
        if self._compatibility_cache is None or now - self._compatibility_cache_at >= 5.0:
            self._compatibility_cache = self._bridge_status()
            self._compatibility_cache_at = now
        status = self._compatibility_cache
        if status.get("compatible") is True:
            return None
        blocking = [item for item in (status.get("blocking_issues") or []) if isinstance(item, dict)]
        # Lead with what to do, not with which hashes differ. This is usually the
        # first mutating call a new user makes, so the message has to be a fix.
        if blocking:
            summary = "; ".join(
                "%s %s" % (str(item.get("message") or "").strip(), str(item.get("remedy") or "").strip())
                for item in blocking
            )
        else:
            summary = str(
                status.get("compatibility_message")
                or "Blender bridge did not provide a compatible protocol and tool-registry handshake"
            )
        return _tool_error(
            summary,
            code="bridge_incompatible",
            data={
                "blocking_issues": blocking,
                "compatibility_status": status.get("compatibility_status"),
                "bridge_version": status.get("bridge_version"),
                "expected_bridge_version": bridge_protocol.BRIDGE_VERSION,
                "tool_registry_digest": status.get("tool_registry_digest"),
                "mcp_tool_registry_digest": status.get("mcp_tool_registry_digest"),
                # Without this the payload showed only the add-on and runtime
                # digests, which agree whenever the config is the stale one.
                # A reader saw two identical values beside a mismatch error and
                # reasonably concluded the block was spurious. The value that
                # actually differs has to be the one on display.
                "mcp_config_tool_registry_digest": status.get("mcp_config_tool_registry_digest"),
                "digest_comparison": _digest_comparison(status),
                "compatibility_metadata_complete": bool(
                    status.get("bridge_version") and status.get("tool_registry_digest")
                ),
                "recovery_hint": "Install matching add-on and blender-bridge versions, copy a fresh MCP config, and restart the client.",
            },
        )

    def _bridge_status(self, operation_id=""):
        if operation_id:
            try:
                return self.bridge.get("/operation", {"operation_id": operation_id})
            except Exception as exc:
                return {"ok": False, "operation_id": operation_id, "message": str(exc)}
        try:
            return self._augment_bridge_status(self.bridge.get("/health"))
        except Exception as exc:
            diagnostics = build_info.diagnostics_dict(bridge_url=self.bridge.base_url)
            return self._augment_bridge_status({"ok": False, "message": str(exc), **diagnostics})

    def resources_list(self, params=None):
        resources = [
            {
                "uri": "blender://bridge/status",
                "name": "bridge-status",
                "title": "Blender Bridge Connection Status",
                "description": "MCP server connection status for the Blender bridge",
                "mimeType": "application/json",
            },
            {
                "uri": "blender://mcp/payload-telemetry",
                "name": "mcp-payload-telemetry",
                "title": "MCP Payload Size Telemetry",
                "description": "Aggregate tool response byte sizes without arguments or scene content",
                "mimeType": "application/json",
            },
        ]
        try:
            response = self.bridge.get("/resources")
            resources.extend(response.get("resources") or [])
        except Exception as exc:
            _stderr(f"resources/list bridge warning: {exc}")
        return _page_items(resources, params, "resources")

    def resources_read(self, params):
        uri = (params or {}).get("uri")
        if uri == "blender://bridge/status":
            status = self._bridge_status()
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": _json_text(status),
                    }
                ]
            }
        if uri == "blender://mcp/payload-telemetry":
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": _json_text(self._payload_telemetry_summary()),
                    }
                ]
            }
        response = self.bridge.get("/resource", {"uri": uri})
        content = {
            "uri": uri,
            "mimeType": response.get("mimeType", "text/plain"),
        }
        if "blob" in response:
            content["blob"] = response.get("blob", "")
        else:
            content["text"] = response.get("text", "")
        return {
            "contents": [content]
        }

    def resource_templates_list(self, params=None):
        return _page_items(RESOURCE_TEMPLATES, params, "resourceTemplates")

    def prompts_list(self, params=None):
        prompts = [
            {
                "name": prompt["name"],
                "title": prompt.get("title", prompt["name"]),
                "description": prompt.get("description", ""),
                "arguments": prompt.get("arguments", []),
            }
            for prompt in PROMPTS.values()
        ]
        return _page_items(prompts, params, "prompts")

    def prompts_get(self, params):
        params = params or {}
        name = params.get("name")
        prompt = PROMPTS.get(name)
        if prompt is None:
            raise KeyError(f"Prompt not found: {name}")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        required = [item["name"] for item in prompt.get("arguments", []) if item.get("required")]
        missing = [key for key in required if not str(arguments.get(key) or "").strip()]
        if missing:
            raise ValueError(f"Missing required prompt arguments: {', '.join(missing)}")
        values = {item["name"]: str(arguments.get(item["name"]) or "") for item in prompt.get("arguments", [])}
        return {
            "description": prompt.get("description", ""),
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": prompt["template"].format(**values),
                    },
                }
            ],
        }

    def handle_request(self, message):
        method = message.get("method")
        params = message.get("params") or {}
        if method == "initialize":
            return self.initialize(params)
        if method == "ping":
            return {}
        if method == "logging/setLevel":
            self._log_level = str(params.get("level") or "info")
            return {}
        if method == "tools/list":
            return self.tools_list(params)
        if method == "tools/call":
            return self.tools_call(params)
        if method == "resources/list":
            return self.resources_list(params)
        if method == "resources/read":
            return self.resources_read(params)
        if method == "resources/templates/list":
            return self.resource_templates_list(params)
        if method == "prompts/list":
            return self.prompts_list(params)
        if method == "prompts/get":
            return self.prompts_get(params)
        raise KeyError(f"Method not found: {method}")


def _response(request_id, result=None, error=None):
    payload = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result if result is not None else {}
    return payload


def _error(code, message, data=None):
    payload = {"code": int(code), "message": str(message)}
    if data is not None:
        payload["data"] = data
    return payload


def serve(server, input_stream=None, output_stream=None):
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    for raw_line in input_stream:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            output_stream.write(_json_dumps(_response(None, error=_error(-32700, f"Parse error: {exc}"))) + "\n")
            output_stream.flush()
            continue
        if isinstance(message, list):
            responses = [_handle_one(server, item) for item in message]
            responses = [item for item in responses if item is not None]
            if responses:
                output_stream.write(_json_dumps(responses) + "\n")
                output_stream.flush()
            continue
        response = _handle_one(server, message)
        if response is not None:
            output_stream.write(_json_dumps(response) + "\n")
            output_stream.flush()


def _handle_one(server, message):
    if not isinstance(message, dict):
        return _response(None, error=_error(-32600, "Invalid Request"))
    request_id = message.get("id")
    method = message.get("method")
    if method in {"notifications/initialized", "notifications/cancelled", "$/cancelRequest"}:
        return None
    if request_id is None:
        return None
    try:
        result = server.handle_request(message)
        return _response(request_id, result=result)
    except KeyError as exc:
        return _response(request_id, error=_error(-32601, str(exc)))
    except Exception as exc:
        return _response(request_id, error=_error(-32603, f"{type(exc).__name__}: {exc}"))


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["doctor"]:
        try:
            from . import connection_diagnostics
        except ImportError:  # Allows direct execution as addon/claude_blender/mcp_server.py.
            from claude_blender import connection_diagnostics

        return connection_diagnostics.main(arguments[1:])
    parser = argparse.ArgumentParser(description="MCP server for Blender Agent Bridge")
    parser.add_argument("--version", action="version", version=f"%(prog)s {SERVER_VERSION}")
    parser.add_argument("--bridge-url", default=os.environ.get("BLENDER_BRIDGE_URL", DEFAULT_BRIDGE_URL))
    parser.add_argument("--token", default=os.environ.get("BLENDER_BRIDGE_TOKEN", ""))
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("BLENDER_BRIDGE_TIMEOUT", "30")))
    args = parser.parse_args(arguments)
    serve(BlenderMCPServer(BridgeClient(args.bridge_url, token=args.token, timeout=args.timeout)))


if __name__ == "__main__":
    raise SystemExit(main())
