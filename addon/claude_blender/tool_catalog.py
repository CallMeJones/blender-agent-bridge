"""Pure catalog categories, ranking, facets and discovery guidance.

Schema-budget projection remains in agent_tools; this module ranks full tools.
"""
import re
import functools
try:
    from . import agent_tools, bridge_protocol, helper_routing, tool_registry
except ImportError:
    import agent_tools, bridge_protocol, helper_routing, tool_registry

ANIMATION_ROUTE_TOOLS = {
    "run_animation_task",
    "plan_animation_workflow",
    "run_animation_workflow",
    "create_animation_brief",
    "create_timing_chart",
    "get_animation_scene_context",
    "analyze_animation_principles",
    "compare_animation_to_brief",
    "review_playblast_against_brief",
    "review_inspection_renders_against_brief",
    "repair_animation_from_findings",
    "run_animation_repair_loop",
    "capture_animation_playblast",
    "set_rig_pose_hold",
    "set_rig_custom_property_keyframes",
    "get_rig_pose_library_details",
    "apply_rig_pose_from_action",
    "apply_rig_pose_marker",
    "apply_rig_action_clip",
    "offset_rig_limb_controls",
}


LOOKDEV_REVIEW_ROUTE_TERMS = {
    "lookdev",
    "look-dev",
    "look dev",
    "lookdev turntable",
    "look-dev turntable",
    "look dev turntable",
    "turntable review",
    "review turntable",
    "inspection still",
    "artifact validation",
    "render evidence",
    "review still",
}


CATALOG_SEARCH_STOP_WORDS = {
    "a",
    "add",
    "an",
    "and",
    "after",
    "before",
    "build",
    "create",
    "for",
    "from",
    "in",
    "into",
    "it",
    "make",
    "my",
    "of",
    "on",
    "or",
    "please",
    "the",
    "then",
    "this",
    "to",
    "use",
    "with",
    "your",
}


RENDER_OUTPUT_ROUTE_TERMS = {
    "render pass",
    "render passes",
    "view layer pass",
    "viewlayer pass",
    "aov",
    "aovs",
    "shader aov",
    "custom aov",
    "cryptomatte",
    "crypto matte",
    "normal pass",
    "depth pass",
    "z pass",
    "position pass",
    "vector pass",
    "uv pass",
    "ambient occlusion pass",
    "ao pass",
}


PROCEDURAL_TEXTURE_ROUTE_TERMS = {
    "procedural texture",
    "procedural material",
    "procedural shader",
    "noise texture",
    "voronoi",
    "wave texture",
    "checker texture",
    "musgrave",
    "procedural marble",
    "procedural wood",
    "procedural fabric",
    "marble texture",
    "marble material",
    "wood texture",
    "wood material",
    "fabric texture",
    "fabric material",
    "cellular texture",
}


BAKE_MAP_ROUTE_TERMS = {
    "bake map",
    "bake maps",
    "baked map",
    "baked maps",
    "texture bake",
    "map bake",
    "bake texture",
    "bake textures",
    "bake ao",
    "bake normal",
    "bake diffuse",
    "bake base color",
    "bake albedo",
    "ambient occlusion bake",
    "normal bake",
    "diffuse bake",
    "game ready",
    "game-ready",
}


ADVANCED_ROUTE_TERMS = {
    "advanced",
    "advanced 3d",
    "advanced 2d",
    "storyboard",
    "animatic",
    "cutout",
    "cut-out",
    "motion graphics",
    "grease pencil",
    "procedural",
    "geometry node",
    "geometry-node",
    "geometry nodes",
    "node network",
    "array stack",
    "modifier stack",
    "hard surface",
    "cloth simulation",
    "camera dolly",
    "dolly shot",
    "directed shot",
    "shot template",
    "object kit",
    "object design",
    "design brief",
    "design mapper",
    "object family",
    "kitbash",
    "scatter grid",
    "radial array",
    "pipe run",
    "lamp",
    "modular wall panel",
    "desk lamp",
    "architect lamp",
    "task lamp",
    "clamp lamp",
    "spring arm",
    "spring arms",
    "counterweight",
    "wide shade",
    "appliance",
    "coffee machine",
    "espresso",
    "electronics",
    "control panel",
    "console",
    "furniture",
    "chair",
    "table",
    "shelf",
    "product prop",
    "edit mesh",
    "extrude",
    "inset",
    "loop cut",
    "loop-cut",
    "knife",
    "proportional edit",
    "bridge",
    "dissolve",
    "merge",
    "curve to mesh",
    "convert curve",
    "boolean",
    "cutter",
    "mirror",
    "symmetry",
    "symmetrize",
    "solidify",
    "screw",
    "thread",
    "mesh quality",
    "modeling quality",
    "validate model",
    "non-manifold",
    "loose geometry",
    "director",
    "director workflow",
    "helper path",
    "asset import",
    *LOOKDEV_REVIEW_ROUTE_TERMS,
    *RENDER_OUTPUT_ROUTE_TERMS,
    *PROCEDURAL_TEXTURE_ROUTE_TERMS,
    *BAKE_MAP_ROUTE_TERMS,
}


ADVANCED_ROUTE_TOOLS = {
    "plan_director_workflow",
    "plan_model_quality_workflow",
    "plan_advanced_scene_workflow",
    "plan_asset_import_workflow",
    "get_2d_animation_details",
    "apply_procedural_array_stack",
    "edit_mesh",
    "inspect_modeling_quality",
    "curve_to_mesh",
    "boolean_op",
    "mirror_model",
    "symmetrize_model",
    "solidify_model",
    "screw_model",
    "create_camera_dolly_animation",
    "create_camera_orbit",
    "create_lookdev_turntable_review",
    "configure_render_outputs",
    "add_cloth_simulation_to_selected",
    "capture_viewport",
    "get_visual_evidence_resources",
}


TWO_D_ROUTE_TERMS = {"advanced 2d", "storyboard", "animatic", "cutout", "cut-out", "motion graphics", "grease pencil"}


PROCEDURAL_ROUTE_TERMS = {
    "advanced 3d",
    "procedural",
    "geometry node",
    "geometry-node",
    "geometry nodes",
    "node network",
    "array stack",
    "modifier stack",
    "hard surface",
    "object kit",
    "object design",
    "design brief",
    "design mapper",
    "object family",
    "kit",
    "kitbash",
    "scatter grid",
    "radial array",
    "mechanical part",
    "modular wall panel",
    "wall panel",
    "pipe run",
    "lamp",
    "desk lamp",
    "architect lamp",
    "task lamp",
    "clamp lamp",
    "spring arm",
    "spring arms",
    "counterweight",
    "wide shade",
    "appliance",
    "coffee machine",
    "espresso",
    "electronics",
    "control panel",
    "console",
    "furniture",
    "chair",
    "table",
    "shelf",
    "product prop",
    "edit mesh",
    "extrude",
    "inset",
    "loop cut",
    "loop-cut",
    "knife",
    "proportional edit",
    "bridge",
    "dissolve",
    "merge",
    "curve to mesh",
    "convert curve",
    "boolean",
    "cutter",
    "boolean cutter",
    "boolean difference",
    "mirror",
    "mirror model",
    "symmetry",
    "symmetrize",
    "solidify",
    "screw",
    "thread",
    "wall thickness",
}


SIMULATION_SETUP_ROUTE_TERMS = {"cloth simulation", "cloth sim", "simulation setup", "physics setup"}


CAMERA_MOVE_ROUTE_TERMS = {
    "camera animation",
    "camera dolly",
    "camera move",
    "camera orbit",
    "camera push",
    "directed shot",
    "dolly shot",
    "lens keyframe",
    "orbit reveal",
    "push in",
    "shot template",
}


UV_UNWRAP_ROUTE_TERMS = {
    "uv unwrap",
    "unwrap",
    "unwraps",
    "uv coordinate",
    "uv coordinates",
    "texture coordinate",
    "texture coordinates",
    "texture-ready",
    "texture ready",
    "uv map",
    "uv layout",
    "uv island",
    "uv islands",
    "pack islands",
    "pack uv",
    "mark seams",
    "uv seams",
    "overlapping uvs",
    "overlap uvs",
    "texel density",
}


GENERIC_SELECTED_OBJECT_TOOLS = {
    "set_selected_location_delta",
    "set_selected_transform",
    "select_objects",
}


SCRIPT_EXPLICIT_TERMS = {
    "script",
    "python",
    "custom code",
    "custom python",
    "draft_script",
    "draft_privileged_script",
    "helper tools cannot express",
    "helpers cannot express",
    "trusted script",
}


EXTERNAL_ASSET_STRONG_ROUTE_TERMS = {
    "asset catalog",
    "asset library",
    "asset job",
    "async asset",
    "environment map",
    "external asset",
    "external assets",
    "hdri",
    "hdris",
    "imported asset",
    "imported assets",
    "model library",
    "poly haven",
    "polyhaven",
    "queued import",
    "sketchfab",
}


EXTERNAL_ASSET_ACTION_TERMS = {
    "cache",
    "cached",
    "caching",
    "download",
    "downloads",
    "downloading",
    "fetch",
    "import",
    "imports",
    "importing",
    "search",
}


EXTERNAL_ASSET_OBJECT_TERMS = {
    "asset",
    "assets",
    "environment map",
    "hdri",
    "hdris",
    "model",
    "models",
    "texture",
    "textures",
}


EXTERNAL_ASSET_DIRECT_TERMS = {
    "direct",
    "direct import",
    "download_poly_haven_asset",
    "download_sketchfab_model",
    "import_external_asset_job_result",
    "import_poly_haven_asset",
    "import_sketchfab_model",
    "legacy",
    "one-shot",
    "synchronous",
    "sync",
}


EXTERNAL_ASSET_WORKFLOW_TOOLS = {
    "search_poly_haven_assets",
    "inspect_poly_haven_asset_files",
    "search_sketchfab_models",
    "start_external_asset_download",
    "get_external_asset_job_status",
    "cancel_external_asset_job",
    "start_external_asset_import_job",
    "get_external_asset_import_job_status",
    "prepare_imported_asset_presentation",
    "cancel_external_asset_import_job",
    "get_external_asset_cache_diagnostics",
}


EXTERNAL_ASSET_DIRECT_TOOLS = {
    "download_poly_haven_asset",
    "import_poly_haven_asset",
    "download_sketchfab_model",
    "import_sketchfab_model",
    "import_external_asset_job_result",
}


EXTERNAL_ASSET_ASYNC_WORKFLOW = [
    "start_external_asset_download",
    "get_external_asset_job_status",
    "start_external_asset_import_job",
    "get_external_asset_import_job_status",
]


CACHE_CLEANUP_WRITE_TOOLS = {"delete_external_asset_job", "prune_external_asset_cache"}


GUARDRAIL_COMMIT_REVERT_TOOLS = ["commit_preview", "revert_preview"]


BACKGROUND_JOB_STATUS_TOOLS = {
    "start_render_job": "get_render_job_status",
    "assemble_render_job_video": "get_render_job_status",
    "start_external_asset_download": "get_external_asset_job_status",
    "start_external_asset_import_job": "get_external_asset_import_job_status",
}


INSPECTION_INTENT_TERMS = {
    "diagnostic",
    "diagnostics",
    "inspect",
    "inspection",
    "list",
    "show",
    "status",
}


MUTATION_INTENT_TERMS = {
    "add",
    "animate",
    "apply",
    "bake",
    "build",
    "commit",
    "create",
    "delete",
    "download",
    "edit",
    "fix",
    "import",
    "make",
    "model",
    "modify",
    "repair",
    "revert",
    "run",
    "save",
    "set",
    "stage",
    "write",
}


WORKFLOW_CREATION_TERMS = {"build", "create", "design", "make", "model"}


WORKFLOW_MATERIAL_TERMS = {"material", "materials", "shader", "texture"}


WORKFLOW_CAMERA_TERMS = {"camera", "light", "lighting", "render", "screenshot", "viewport"}


WORKFLOW_PREVIEW_TERMS = {"commit", "preview", "revert"}


TOOL_CATEGORY_LABELS = {
    "inspect": "Scene Inspection",
    "transform": "Selection And Transform",
    "creation": "Object Creation",
    "materials": "Materials And Shading",
    "two_d": "2D And Storyboard",
    "animation": "Animation",
    "camera_render": "Camera, Light, And Render",
    "geometry": "Geometry And Modifiers",
    "rigging": "Rigging And Constraints",
    "simulation": "Simulation",
    "organization": "Collections And Organization",
    "preview": "Preview Control",
    "script": "Session-Trusted Python",
    "scene": "Scene Settings",
    "navigation": "Workspace And View Navigation",
    "project_files": "Project Files",
    "external_assets": "External Asset Catalogs",
    "other": "Other",
}


GENERIC_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "message": {"type": "string"},
    },
    "additionalProperties": True,
}


def _tool_annotations(tool):
    tool = tool if isinstance(tool, dict) else {}
    annotations = dict(tool.get("annotations") or {})
    name = str(tool.get("name") or "")
    if name in bridge_protocol.TOOL_CONTRACTS:
        defaults = bridge_protocol.mcp_annotations_for_tool(name)
        defaults.update(annotations)
        return defaults
    return annotations


def _tool_search_text(tool):
    annotations = _tool_annotations(tool)
    schema = tool.get("inputSchema") or {}
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    category = _tool_category(tool)
    parts = [
        tool.get("name", ""),
        tool.get("title", ""),
        tool.get("description", ""),
        category,
        TOOL_CATEGORY_LABELS.get(category, ""),
        annotations.get("riskLevel", ""),
        annotations.get("approvalPolicy", ""),
        annotations.get("recoveryHint", ""),
        " ".join(str(item) for item in annotations.get("permissions", []) or []),
        " ".join(str(item) for item in properties),
    ]
    return " ".join(str(part).lower() for part in parts if part)


def _contains_any_phrase(text, phrases):
    normalized = str(text or "").lower()
    for phrase in phrases:
        phrase_text = str(phrase or "").strip().lower()
        if not phrase_text:
            continue
        pattern = re.escape(phrase_text).replace(r"\ ", r"\s+")
        if re.search(rf"(?<![a-z0-9_]){pattern}(?![a-z0-9_])", normalized):
            return True
    return False


def _is_external_asset_route_query(text):
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    if _contains_any_phrase(normalized, EXTERNAL_ASSET_STRONG_ROUTE_TERMS):
        return True
    return _contains_any_phrase(normalized, EXTERNAL_ASSET_ACTION_TERMS) and _contains_any_phrase(
        normalized,
        EXTERNAL_ASSET_OBJECT_TERMS,
    )


# Only groups with a single discovery responsibility override legacy categories.
# Mixed groups such as advanced_create retain the compatibility fallback below.
GROUP_CATEGORIES = {"external_assets": "external_assets", "generation_quality": "external_assets",
                    "preview_control": "preview"}
_REGISTRY_CATEGORIES = {
    spec.name: next((GROUP_CATEGORIES[group] for group in spec.groups if group in GROUP_CATEGORIES), None)
    for spec in tool_registry.REGISTRY.specs()
}


def _tool_category(tool):
    name = str((tool or {}).get("name") or "").lower()
    declared = _REGISTRY_CATEGORIES.get(name)
    if declared:
        return declared
    if name in {"draft_script", "draft_privileged_script", "run_approved_script"}:
        return "script"
    if name in {"commit_preview", "revert_preview"}:
        return "preview"
    if name in {
        "list_poly_haven_categories",
        "search_poly_haven_assets",
        "inspect_poly_haven_asset_files",
        "download_poly_haven_asset",
        "import_poly_haven_asset",
        "search_sketchfab_models",
        "download_sketchfab_model",
        "import_sketchfab_model",
        "start_external_asset_download",
        "get_external_asset_job_status",
        "cancel_external_asset_job",
        "import_external_asset_job_result",
        "start_external_asset_import_job",
        "get_external_asset_import_job_status",
        "prepare_imported_asset_presentation",
        "cancel_external_asset_import_job",
        "delete_external_asset_job",
        "get_external_asset_cache_diagnostics",
        "prune_external_asset_cache",
    }:
        return "external_assets"
    if name in {"get_workspace_layout", "jump_to_workspace", "set_viewport_view", "focus_object_in_viewport"}:
        return "navigation"
    if name in {"get_blend_file_diagnostics", "save_blend_file", "open_blend_file", "create_new_blender_project", "autosave_current_blend_file"}:
        return "project_files"
    if name in {"start_render_job", "get_render_job_status", "cancel_render_job", "assemble_render_job_video", "validate_render_job_output", "create_lookdev_turntable_review", "configure_render_outputs"}:
        return "camera_render"
    if name == "get_2d_animation_details":
        return "two_d"
    if name == "plan_advanced_scene_workflow":
        return "inspect"
    if name in {"inspect_material_setup", "repair_material_setup", "bake_maps"}:
        return "materials"
    if name.startswith("get_") or name.startswith("list_") or name.startswith("inspect_") or name in {
        "inspect_scene",
        "search_blender_docs",
        "capture_viewport",
        "capture_animation_playblast",
        "capture_object_inspection_renders",
        "inspect_modeling_quality",
        "get_visual_evidence_resources",
        "review_inspection_renders_against_brief",
    }:
        return "inspect"
    if name == "analyze_center_of_mass":
        return "animation"
    if "material" in name or "shader" in name or name == "set_world_background":
        return "materials"
    if "camera" in name or "render" in name or name in {"add_light", "set_active_camera"}:
        return "camera_render"
    if "animate" in name or "animation" in name or "frame" in name:
        return "animation"
    if name in {"edit_mesh", "curve_to_mesh", "boolean_op", "mirror_model", "symmetrize_model", "solidify_model", "screw_model", "uv_unwrap", "mark_uv_seams"}:
        return "geometry"
    if "geometry" in name or "modifier" in name or "bevel" in name or "subsurf" in name or "shape_key" in name:
        return "geometry"
    if "rigging" in name or "armature" in name or "constraint" in name or name in {"set_rig_pose_hold", "set_rig_custom_property_keyframes", "get_rig_pose_library_details", "apply_rig_pose_from_action", "apply_rig_pose_marker", "apply_rig_action_clip", "offset_rig_limb_controls"}:
        return "rigging"
    if "simulation" in name or "particle" in name:
        return "simulation"
    if "collection" in name:
        return "organization"
    if name.startswith("create_") or name.startswith("add_") or name.startswith("apply_"):
        return "creation"
    if "transform" in name or "selected" in name or name == "select_objects":
        return "transform"
    if name.startswith("set_"):
        return "scene"
    return "other"


def _tool_summary(tool, *, include_schema=True):
    annotations = _tool_annotations(tool)
    category = _tool_category(tool)
    guardrail_warnings = _guardrail_warnings_for_tool(tool)
    summary = {
        "name": tool.get("name", ""),
        "title": tool.get("title", ""),
        "description": tool.get("description", ""),
        "category": category,
        "risk_level": annotations.get("riskLevel", ""),
        "permissions": list(annotations.get("permissions", []) or []),
        "mutates_scene": bool(annotations.get("mutatesScene", False)),
    }
    optional_values = {
        "has_side_effects": bool(annotations.get("hasSideEffects", False)),
        "requires_approval": bool(annotations.get("requiresApproval", False)),
        "requires_live_preview": bool(annotations.get("requiresLivePreview", False)),
        "timeout_seconds": int(annotations.get("timeoutSeconds", 0) or 0),
        "long_running": bool(annotations.get("longRunningHint", False)),
        "returns_background_job": bool(annotations.get("returnsBackgroundJob", False)),
        "duration_hint": str(annotations.get("durationHint", "") or ""),
        "timeout_recovery": dict(annotations.get("timeoutRecovery") or {}),
        "human_in_loop_required": bool(annotations.get("humanInLoopRequired", False)),
        "requires_user_path": bool(annotations.get("requiresUserPath", False)),
        "path_policy": str(annotations.get("pathPolicy", "") or ""),
        "requires_explicit_one_time_approval": bool(annotations.get("requiresExplicitOneTimeApproval", False)),
        "approval_policy": str(annotations.get("approvalPolicy", "") or ""),
        "recovery_hint": str(annotations.get("recoveryHint", "") or ""),
    }
    for key, value in optional_values.items():
        if value not in ("", None, False, 0, [], {}):
            summary[key] = value
    if annotations.get("trustWindowAutoRunAllowed", True) is False:
        summary["trust_window_auto_run_allowed"] = False
    if guardrail_warnings:
        summary["guardrail_warnings"] = guardrail_warnings
        summary["guardrail_warning_count"] = len(guardrail_warnings)
    if include_schema:
        summary["input_schema"] = tool.get("inputSchema") or {}
        summary["output_schema"] = tool.get("outputSchema") or GENERIC_OUTPUT_SCHEMA
        summary["annotations"] = annotations
    return summary


def _catalog_filters(arguments):
    return {
        "query": str(arguments.get("query") or "").strip(),
        "category": str(arguments.get("category") or "").strip().lower(),
        "permission": str(arguments.get("permission") or "").strip().lower(),
        "risk_level": str(arguments.get("risk_level") or "").strip().lower(),
        "mutates_scene": arguments.get("mutates_scene") if isinstance(arguments.get("mutates_scene"), bool) else None,
        "requires_approval": (
            arguments.get("requires_approval") if isinstance(arguments.get("requires_approval"), bool) else None
        ),
        "requires_live_preview": (
            arguments.get("requires_live_preview") if isinstance(arguments.get("requires_live_preview"), bool) else None
        ),
    }


def _tool_matches_filters(tool, filters):
    annotations = _tool_annotations(tool)
    category = _tool_category(tool)
    if filters["category"] and category != filters["category"]:
        return False
    if filters["permission"]:
        permissions = [str(item).lower() for item in annotations.get("permissions", []) or []]
        if filters["permission"] not in permissions:
            return False
    if filters["risk_level"] and str(annotations.get("riskLevel") or "").lower() != filters["risk_level"]:
        return False
    if filters["mutates_scene"] is not None and bool(annotations.get("mutatesScene", False)) is not filters["mutates_scene"]:
        return False
    if filters["requires_approval"] is not None and bool(annotations.get("requiresApproval", False)) is not filters["requires_approval"]:
        return False
    if (
        filters["requires_live_preview"] is not None
        and bool(annotations.get("requiresLivePreview", False)) is not filters["requires_live_preview"]
    ):
        return False
    return True


@functools.lru_cache(maxsize=128)
def _catalog_query_features(normalized_query):
    terms = tuple(
        term
        for term in re.findall(r"[a-z0-9_]+", normalized_query)
        if term not in CATALOG_SEARCH_STOP_WORDS
    )
    animation_query = helper_routing.is_animation_workflow_request(normalized_query)
    model_quality_query = helper_routing.is_reference_model_quality_request(normalized_query)
    authored_content_query = agent_tools.is_open_ended_authored_content(normalized_query)
    workflow_domain_count = sum(
        (
            _contains_any_phrase(normalized_query, WORKFLOW_MATERIAL_TERMS),
            animation_query,
            _contains_any_phrase(normalized_query, WORKFLOW_CAMERA_TERMS),
            _contains_any_phrase(normalized_query, WORKFLOW_PREVIEW_TERMS),
        )
    )
    return {
        "terms": terms,
        "animation_query": animation_query,
        "model_quality_query": model_quality_query,
        "advanced_query": _contains_any_phrase(normalized_query, ADVANCED_ROUTE_TERMS) or model_quality_query,
        "two_d_query": _contains_any_phrase(normalized_query, TWO_D_ROUTE_TERMS),
        "procedural_query": _contains_any_phrase(normalized_query, PROCEDURAL_ROUTE_TERMS) or model_quality_query,
        "simulation_setup_query": _contains_any_phrase(normalized_query, SIMULATION_SETUP_ROUTE_TERMS),
        "camera_move_query": _contains_any_phrase(normalized_query, CAMERA_MOVE_ROUTE_TERMS),
        "uv_unwrap_query": _contains_any_phrase(normalized_query, UV_UNWRAP_ROUTE_TERMS),
        "explicit_script_query": _contains_any_phrase(normalized_query, SCRIPT_EXPLICIT_TERMS),
        "authored_content_query": authored_content_query,
        "helper_preference_query": helper_routing.prefers_bounded_helpers(normalized_query),
        "external_asset_query": _is_external_asset_route_query(normalized_query),
        "explicit_direct_asset_query": _contains_any_phrase(normalized_query, EXTERNAL_ASSET_DIRECT_TERMS),
        "project_file_operations": helper_routing.project_file_operation_kinds(normalized_query),
        "render_job_query": helper_routing.is_render_job_request(normalized_query),
        "render_setup_query": helper_routing.is_render_setup_request(normalized_query),
        "lookdev_review_query": helper_routing.is_lookdev_review_request(normalized_query),
        "inspection_render_query": helper_routing.is_inspection_render_request(normalized_query),
        "leading_term": terms[0].strip(".,:;!?") if terms else "",
        "broad_workflow_query": (
            _contains_any_phrase(normalized_query, WORKFLOW_CREATION_TERMS)
            and workflow_domain_count >= 3
        ),
    }


def _score_tool_match(tool, query):
    normalized_query = str(query or "").strip().lower()
    if not normalized_query:
        return 0
    features = _catalog_query_features(normalized_query)
    terms = features["terms"]
    text = _tool_search_text(tool)
    name = str(tool.get("name") or "").lower()
    title = str(tool.get("title") or "").lower()
    category = _tool_category(tool)
    animation_query = features["animation_query"]
    model_quality_query = features["model_quality_query"]
    advanced_query = features["advanced_query"]
    two_d_query = features["two_d_query"]
    procedural_query = features["procedural_query"]
    simulation_setup_query = features["simulation_setup_query"]
    camera_move_query = features["camera_move_query"]
    uv_unwrap_query = features["uv_unwrap_query"]
    explicit_script_query = features["explicit_script_query"]
    authored_content_query = features["authored_content_query"]
    helper_preference_query = features["helper_preference_query"]
    external_asset_query = features["external_asset_query"]
    explicit_direct_asset_query = features["explicit_direct_asset_query"]
    project_file_operations = features["project_file_operations"]
    render_job_query = features["render_job_query"]
    render_setup_query = features["render_setup_query"]
    lookdev_review_query = features["lookdev_review_query"]
    inspection_render_query = features["inspection_render_query"]
    if name == "plan_model_quality_workflow" and not model_quality_query and normalized_query != name:
        return None
    leading_term = features["leading_term"]
    inspection_only_query = (
        leading_term in INSPECTION_INTENT_TERMS
        and not _contains_any_phrase(normalized_query, MUTATION_INTENT_TERMS)
    )
    broad_workflow_query = features["broad_workflow_query"]
    matched_terms = [term for term in terms if term in text]
    if not matched_terms:
        if animation_query and (name in ANIMATION_ROUTE_TOOLS or category == "animation"):
            score = 25
        elif advanced_query and (name in ADVANCED_ROUTE_TOOLS or category in {"two_d", "geometry", "simulation", "camera_render"}):
            score = 25
        elif authored_content_query and name == "draft_script":
            score = 25
        elif broad_workflow_query and name in {"plan_director_workflow", "plan_advanced_scene_workflow"}:
            score = 25
        elif external_asset_query and (name in EXTERNAL_ASSET_WORKFLOW_TOOLS or category == "external_assets"):
            score = 25
        else:
            return None
    else:
        score = sum(text.count(term) for term in terms)
        score += len(matched_terms) * 5
        if len(matched_terms) == len(terms):
            score += 15
    if name == normalized_query:
        score += 1000
    elif name.startswith(normalized_query):
        score += 200
    if title == normalized_query:
        score += 500
    elif title.startswith(normalized_query):
        score += 100
    if inspection_only_query:
        if bool(_tool_annotations(tool).get("mutatesScene", False)):
            score -= 2500
        if name == "get_blend_file_diagnostics" and "blend file" in normalized_query:
            score += 3500
        elif name == "list_scene_objects" and "scene" in normalized_query and "list" in normalized_query:
            score += 3000
        elif name == "inspect_scene" and "inspect scene" in normalized_query:
            score += 2500
    if broad_workflow_query:
        if name == "plan_director_workflow":
            score += 6000
        elif name == "plan_advanced_scene_workflow":
            score += 4000
    if project_file_operations:
        project_routes = {
            "create": "create_new_blender_project",
            "open": "open_blend_file",
            "save": "save_blend_file",
        }
        if name in {
            project_routes[kind]
            for kind in project_file_operations
        }:
            score += 4000
        elif name == "get_blend_file_diagnostics":
            score += 1200
        elif name == "draft_script" and not authored_content_query:
            score -= 4000
    if render_job_query:
        if name == "start_render_job":
            score += 3500
        elif name in {
            "get_render_job_status",
            "validate_render_job_output",
            "assemble_render_job_video",
        }:
            score += 1000
        elif name == "draft_script" and not authored_content_query:
            score -= 3000
    if render_setup_query:
        if name == "configure_render_outputs":
            score += 4000
        elif name == "set_render_settings":
            score += 3500
        elif name == "set_render_engine":
            score += 3000
        elif name == "get_render_camera_compositor_details":
            score += 1800
        elif name == "draft_script" and not authored_content_query:
            score -= 3000
    if lookdev_review_query:
        if name == "create_lookdev_turntable_review":
            score += 5000
        elif name == "draft_script":
            score -= 3000
    if inspection_render_query:
        if name == "capture_object_inspection_renders":
            score += 1200 if authored_content_query else 5000
        elif name == "review_inspection_renders_against_brief":
            score += 900 if authored_content_query else 4000
        elif name == "repair_animation_from_findings":
            score += 700 if authored_content_query else 3000
    if uv_unwrap_query:
        if name == "uv_unwrap":
            score += 1400
        elif name == "mark_uv_seams" and any(term in normalized_query for term in ("seam", "seams", "hard edge", "sharp edge", "boundary")):
            score += 1350
        elif name == "inspect_uv_layout" and any(term in normalized_query for term in ("inspect", "validate", "quality", "overlap", "overlapping", "texel", "coverage", "uv layout")):
            score += 1300
        elif name == "inspect_uv_layout":
            score += 900
        elif name == "create_image_texture_material":
            score -= 150
    if animation_query:
        if name == "run_animation_task":
            score += 1200
        elif name == "plan_animation_workflow":
            score += 1000
        elif name == "run_animation_workflow":
            score += 950
        elif name in ANIMATION_ROUTE_TOOLS:
            score += 500
        elif category == "animation":
            score += 250
        if name in GENERIC_SELECTED_OBJECT_TOOLS:
            score -= 250
        if name == "draft_script":
            if authored_content_query:
                score += 1800
            elif not explicit_script_query:
                score -= 1000
    if advanced_query:
        if model_quality_query:
            if name == "plan_model_quality_workflow":
                score += 4200
            elif (
                name == "compare_model_to_reference"
                and any(
                    term in normalized_query
                    for term in (
                        "redline",
                        "silhouette",
                        "landmark",
                        "compare model",
                        "compare render",
                        "reference comparison",
                    )
                )
            ):
                score += 6500
            elif (
                name == "fit_surface_to_multiview_references"
                and any(
                    term in normalized_query
                    for term in (
                        "multi-view fit",
                        "multiview fit",
                        "fit surface",
                        "reference fitting",
                        "reference fitter",
                        "joint silhouette",
                    )
                )
            ):
                score += 7000
            elif (
                name == "create_multiview_depth_surface"
                and any(
                    term in normalized_query
                    for term in (
                        "depth fusion",
                        "depth map",
                        "depth maps",
                        "depth surface",
                        "sparse depth",
                        "depth-constrained",
                    )
                )
            ):
                score += 6900
            elif (
                name == "create_multiview_visual_hull"
                and any(
                    term in normalized_query
                    for term in (
                        "visual hull",
                        "silhouette carving",
                        "multi-view volume",
                        "multiview volume",
                    )
                )
            ):
                score += 6800
            elif (
                name == "create_multiview_reference_guides"
                and any(
                    term in normalized_query
                    for term in (
                        "multi-view",
                        "multiview",
                        "front and side",
                        "reference views",
                        "3d landmark",
                        "landmark reconstruction",
                    )
                )
            ):
                score += 6500
            elif name == "adaptive_remesh" and any(
                term in normalized_query
                for term in ("adaptive remesh", "adaptive remeshing", "sculpt topology")
            ):
                score += 6800
            elif (
                name == "evaluate_reference_model_benchmark"
                and any(
                    term in normalized_query
                    for term in (
                        "benchmark",
                        "quality gate",
                        "metric profile",
                        "review profile",
                        "refined profile",
                        "blockout profile",
                    )
                )
            ):
                score += 6500
            elif name in {"capture_viewport", "capture_object_inspection_renders", "inspect_modeling_quality"}:
                score += 900
        if name == "plan_director_workflow" and any(term in normalized_query for term in ("director", "whole workflow", "end to end", "end-to-end")):
            score += 5000
        if name == "plan_advanced_scene_workflow":
            score += 3600 if explicit_script_query else 3000
        if name == "plan_asset_import_workflow" and external_asset_query:
            score += 1800
        if name == "configure_render_outputs" and _contains_any_phrase(normalized_query, RENDER_OUTPUT_ROUTE_TERMS):
            score += 1900
        if name == "bake_maps" and _contains_any_phrase(normalized_query, BAKE_MAP_ROUTE_TERMS):
            score += 1900
        if name == "create_lookdev_turntable_review" and _contains_any_phrase(
            normalized_query, LOOKDEV_REVIEW_ROUTE_TERMS
        ):
            score += 1800
        if two_d_query:
            if name == "get_2d_animation_details":
                score += 900
        if procedural_query:
            if name == "inspect_modeling_quality" and any(term in normalized_query for term in ("mesh quality", "modeling quality", "validate model", "non-manifold", "loose geometry", "missing material")):
                score += 1300
            elif name == "apply_procedural_array_stack":
                score += 900
            elif name == "edit_mesh" and any(term in normalized_query for term in ("edit mesh", "extrude", "inset", "loop cut", "loop-cut", "knife", "proportional edit", "bridge", "dissolve", "merge")):
                score += 1250
            elif name == "curve_to_mesh" and any(term in normalized_query for term in ("curve to mesh", "convert curve", "mesh copy")):
                score += 1250
            elif name == "boolean_op" and any(term in normalized_query for term in ("boolean", "cutter", "cut", "difference", "union", "intersect")):
                score += 1200
            elif name == "mirror_model" and "mirror" in normalized_query:
                score += 1200
            elif name == "symmetrize_model" and any(term in normalized_query for term in ("symmetry", "symmetrize", "symmetrical")):
                score += 1200
            elif name == "solidify_model" and any(term in normalized_query for term in ("solidify", "thickness", "shell")):
                score += 1200
            elif name == "screw_model" and any(term in normalized_query for term in ("screw", "thread", "spring", "spiral", "helix")):
                score += 1200
            elif name == "inspect_material_setup" and any(
                term in normalized_query
                for term in (
                    "inspect material",
                    "validate material",
                    "material setup",
                    "material quality",
                    "texture setup",
                    "texture wiring",
                    "pbr setup",
                    "colorspace",
                    "color space",
                    "missing texture",
                )
            ):
                score += 1300
            elif name == "repair_material_setup" and any(
                term in normalized_query
                for term in (
                    "repair material",
                    "fix material",
                    "fix texture",
                    "repair texture",
                    "fix pbr",
                    "repair pbr",
                    "colorspace",
                    "color space",
                    "uv map link",
                    "uv vector",
                )
            ):
                score += 1250
            elif name == "create_shader_material" and any(term in normalized_query for term in ("material", "chrome", "brass", "metal", "glass", "rubber", "wood", "screen", "display", "enamel", "paint", "color", "colour")):
                score += 850
            elif name == "create_procedural_texture_material" and _contains_any_phrase(normalized_query, PROCEDURAL_TEXTURE_ROUTE_TERMS):
                score += 1050
            elif name == "bake_maps" and _contains_any_phrase(normalized_query, BAKE_MAP_ROUTE_TERMS):
                score += 1300
            elif name == "create_image_texture_material" and any(
                term in normalized_query
                for term in (
                    "image texture",
                    "texture map",
                    "texture maps",
                    "pbr",
                    "albedo",
                    "diffuse map",
                    "normal map",
                    "roughness map",
                    "metallic map",
                    "arm map",
                    "orm map",
                    "ambient occlusion",
                    "ao map",
                    "bump map",
                    "uv map",
                )
            ):
                score += 900
            elif name == "set_render_engine" and any(
                term in normalized_query
                for term in ("render engine", "cycles", "eevee", "denoise", "samples", "lookdev", "look-dev", "color management", "view transform")
            ):
                score += 900
            elif name == "configure_render_outputs" and _contains_any_phrase(normalized_query, RENDER_OUTPUT_ROUTE_TERMS):
                score += 1200
            elif name == "create_lookdev_turntable_review" and _contains_any_phrase(
                normalized_query, LOOKDEV_REVIEW_ROUTE_TERMS
            ):
                score += 1200
            elif name == "uv_unwrap" and any(term in normalized_query for term in ("uv", "unwrap", "texture coordinate", "texture-ready", "texture ready")):
                score += 850
            elif name == "mark_uv_seams" and any(term in normalized_query for term in ("uv seam", "mark seam", "seam unwrap", "hard edge")):
                score += 850
            elif name == "inspect_uv_layout" and any(term in normalized_query for term in ("uv layout", "overlapping uv", "texel density", "uv coverage")):
                score += 850
            elif name in {"get_geometry_nodes_details", "add_geometry_nodes_modifier", "add_bevel_and_subsurf"}:
                score += 500
        if simulation_setup_query:
            if name == "add_cloth_simulation_to_selected":
                score += 900
            elif name in {"get_simulation_details", "inspect_simulation_bake", "stage_persistent_simulation_bake"}:
                score += 650
        if camera_move_query:
            if name == "create_camera_dolly_animation":
                score += 900
            elif name == "create_camera_orbit":
                score += 850
            elif name in {"set_camera_settings", "capture_animation_playblast"}:
                score += 450
        if not (two_d_query or procedural_query or simulation_setup_query or camera_move_query) and name in ADVANCED_ROUTE_TOOLS:
            score += 350
        if name == "draft_script":
            if authored_content_query:
                score += 1400
            elif not explicit_script_query:
                score -= 1000
    elif name == "draft_script" and not explicit_script_query and not authored_content_query:
        score -= 100
    if authored_content_query and name == "draft_script":
        score += 1800
    if external_asset_query:
        if name == "plan_asset_import_workflow":
            score += 1300
        elif name == "plan_director_workflow" and any(term in normalized_query for term in ("present", "presentation", "stage", "organize", "workflow")):
            score += 900
        if name == "draft_privileged_script" and explicit_script_query:
            score += 1100
        if name == "start_external_asset_download":
            score += 1200
        elif name == "start_external_asset_import_job":
            score += 1050
        elif name == "get_external_asset_job_status":
            score += 900
        elif name == "get_external_asset_import_job_status":
            score += 850
        elif name == "prepare_imported_asset_presentation":
            score += 780
        elif name in {"search_poly_haven_assets", "search_sketchfab_models", "inspect_poly_haven_asset_files"}:
            score += 600
        elif name in EXTERNAL_ASSET_WORKFLOW_TOOLS:
            score += 350
        elif category == "external_assets":
            score += 150
        if name in EXTERNAL_ASSET_DIRECT_TOOLS and not explicit_direct_asset_query:
            score -= 900
    elif category == "external_assets" and not explicit_direct_asset_query:
        score -= 120
    if explicit_script_query and not helper_preference_query:
        if name == "draft_script":
            score += 3200
        elif name == "start_trusted_script_job":
            score += (
                2400
                if _contains_any_phrase(
                    normalized_query,
                    {"async", "background", "job", "long", "timeout"},
                )
                else 1800
            )
        elif name == "draft_privileged_script":
            score -= 500
    if not animation_query and category == "animation":
        return None
    if (
        not animation_query
        and not camera_move_query
        and name in {
            "capture_animation_playblast",
            "create_camera_dolly_animation",
            "create_camera_orbit",
            "create_turntable_animation",
        }
    ):
        return None
    if helper_preference_query and name == "draft_script":
        score -= 6000
    return score


def _catalog_facets(tools):
    categories = {}
    risk_levels = {}
    permissions = {}
    for tool in tools:
        annotations = _tool_annotations(tool)
        category = _tool_category(tool)
        categories[category] = categories.get(category, 0) + 1
        risk = str(annotations.get("riskLevel") or "unknown")
        risk_levels[risk] = risk_levels.get(risk, 0) + 1
        for permission in annotations.get("permissions", []) or []:
            key = str(permission)
            permissions[key] = permissions.get(key, 0) + 1
    return {
        "categories": [
            {
                "name": name,
                "label": TOOL_CATEGORY_LABELS.get(name, TOOL_CATEGORY_LABELS["other"]),
                "count": count,
            }
            for name, count in sorted(categories.items())
        ],
        "risk_levels": [{"name": name, "count": count} for name, count in sorted(risk_levels.items())],
        "permissions": [{"name": name, "count": count} for name, count in sorted(permissions.items())],
    }


def _guardrail_warnings_for_tool(tool, arguments=None):
    tool = tool if isinstance(tool, dict) else {"name": str(tool or "")}
    name = str(tool.get("name") or "")
    arguments_known = isinstance(arguments, dict)
    arguments = arguments if arguments_known else {}
    annotations = _tool_annotations(tool)
    warnings = []
    if name in {"draft_script", "draft_privileged_script"}:
        warnings.append(
            {
                "code": "trusted_script_checkpoint_only",
                "severity": "warning",
                "message": (
                    "Trusted Python runs immediately with checkpoint and Blender undo recovery. It does not create "
                    "a live preview transaction, and commit_preview or revert_preview cannot commit or undo its "
                    "changes. Use bounded preview helpers or disclose checkpoint-only execution when the user "
                    "requires a pending preview."
                ),
                "live_preview_supported": False,
                "recovery": ["checkpoint_restore", "blender_undo"],
            }
        )
    if name in EXTERNAL_ASSET_DIRECT_TOOLS:
        warnings.append(
            {
                "code": "synchronous_external_asset_fallback",
                "severity": "info",
                "message": (
                    "This is a synchronous external asset fallback/debug path. For normal MCP client workflows, "
                    "prefer the async download/cache job and queued import workflow."
                ),
                "preferred_workflow": list(EXTERNAL_ASSET_ASYNC_WORKFLOW),
            }
        )
    if name in CACHE_CLEANUP_WRITE_TOOLS and not arguments_known:
        warnings.append(
            {
                "code": "cache_cleanup_dry_run_first",
                "severity": "info",
                "message": (
                    "This cache maintenance tool can delete external asset cache or job metadata. Use dry_run=true "
                    "first, review the planned deletion, then retry with dry_run=false only when intended."
                ),
                "safe_first_arguments": {"dry_run": True},
            }
        )
    elif name in CACHE_CLEANUP_WRITE_TOOLS and arguments.get("dry_run") is False:
        warnings.append(
            {
                "code": "cache_cleanup_writes",
                "severity": "warning",
                "message": (
                    "This call can delete external asset cache or job metadata. Prefer running with dry_run=true "
                    "first and only retry with dry_run=false after reviewing the planned deletion."
                ),
                "safe_first_arguments": {"dry_run": True},
            }
        )
    if annotations.get("destructiveHint"):
        warnings.append(
            {
                "code": "destructive_scene_operation",
                "severity": "warning",
                "message": (
                    "This can replace or discard the active Blender session. Confirm the user's intent, preserve "
                    "the checkpoint policy, and avoid retrying blindly after a timeout."
                ),
                "confirmation_arguments": ["confirm_discard_current", "user_confirmed_path"],
            }
        )
    if annotations.get("humanInLoopRequired") or annotations.get("requiresUserPath"):
        warnings.append(
            {
                "code": "user_confirmed_path_required",
                "severity": "warning",
                "message": (
                    "This operation needs a user-confirmed path or explicit human confirmation. Do not invent a "
                    "filesystem path on the client's behalf."
                ),
                "path_policy": str(annotations.get("pathPolicy") or ""),
            }
        )
    if annotations.get("requiresExplicitOneTimeApproval"):
        warnings.append(
            {
                "code": "explicit_one_time_approval_required",
                "severity": "warning",
                "message": (
                    "This requires a fresh one-time approval in Blender; session script trust cannot auto-run it."
                ),
                "approval_policy": str(annotations.get("approvalPolicy") or ""),
            }
        )
    elif annotations.get("requiresApproval"):
        warnings.append(
            {
                "code": "approval_required",
                "severity": "warning",
                "message": (
                    "This may run session-trusted Python. Do not claim execution succeeded until Blender returns "
                    "a successful execution result."
                ),
                "approval_policy": str(annotations.get("approvalPolicy") or ""),
            }
        )
    if annotations.get("mutatesScene") and annotations.get("requiresLivePreview"):
        warnings.append(
            {
                "code": "live_preview_pending",
                "severity": "info",
                "message": (
                    "This mutates the live scene through the preview workflow. Inspect the result, then use "
                    "commit_preview, revert_preview, or Blender undo as appropriate."
                ),
                "follow_up_tools": list(GUARDRAIL_COMMIT_REVERT_TOOLS),
            }
        )
    timeout_recovery = dict(annotations.get("timeoutRecovery") or {})
    if annotations.get("returnsBackgroundJob"):
        warnings.append(
            {
                "code": "background_job_polling_required",
                "severity": "info",
                "message": (
                    "This starts a background job. Poll the matching status tool until terminal state instead "
                    "of starting duplicate work."
                ),
                "poll_after_seconds": int(timeout_recovery.get("poll_after_seconds") or 5),
                "status_tool": str(
                    BACKGROUND_JOB_STATUS_TOOLS.get(name)
                    or timeout_recovery.get("resource_tool")
                    or timeout_recovery.get("status_tool")
                    or ""
                ),
                "bridge_status_tool": str(timeout_recovery.get("status_tool") or "blender_bridge_status"),
                "resource_tool": str(timeout_recovery.get("resource_tool") or ""),
            }
        )
    elif annotations.get("longRunningHint"):
        warnings.append(
            {
                "code": "long_running_synchronous_call",
                "severity": "info",
                "message": (
                    "This can keep Blender busy until the bounded timeout. If the client times out, wait and "
                    "use the recovery status/resource path before rerunning."
                ),
                "timeout_recovery": timeout_recovery,
            }
        )
    return warnings
