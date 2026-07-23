"""Provider-neutral tool catalog and routing hints for external agents."""

from __future__ import annotations

import json

try:
    from . import bridge_protocol, helper_routing, script_analysis, tool_registry
except ImportError:  # Allows direct imports from addon/claude_blender.
    import bridge_protocol
    import helper_routing
    import script_analysis
    import tool_registry


AGENT_GUIDANCE = (
    "You are an external agent connected to Blender Agent Bridge. Read context_plan before acting and inspect omitted scene details when they matter; never guess object names, dimensions, materials, animation state, or file paths. "
    "Use tool catalog search to discover the current helper surface instead of relying on a memorized inventory. Prefer bounded helpers when their validation, rollback, provenance, recovery, or progress reporting adds value. For broad or unclear work, use the relevant read-only workflow planner before mutating the scene. "
    "For scene edits, identify targets first and leave successful live-preview changes pending for the user. Do not commit or revert unless the user explicitly asks; use last-step revert only when they want to undo the latest external import. "
    "For .blend lifecycle work, inspect diagnostics first. Never invent a durable project path: new, open, save-as, and save-copy paths must come from the user or a file picker. Project-file tools are bounded to the current saved .blend directory. "
    "Use asynchronous external-asset and render jobs for downloads, imports, long renders, frame sequences, and final video validation. Poll the returned status tools, preserve provider provenance, and treat bridge timeouts as recoverable before rerunning work. "
    "Use composable modeling, material, node, camera, animation, staging, and evidence helpers when they fit. For open-ended authored content, complex multi-object builds, custom Grease Pencil work, bespoke node graphs, production rigs, or other real helper gaps, use one cohesive trusted Blender Python script rather than a long chain of speculative template calls. "
    "Generated Python runs only while runtime script trust is active. Trust Agent Scripts is equivalent to Blender's Run Script command and permits filesystem, network, subprocess, project-file, persistent-cache, and full Blender API access. Put complete source in draft_script.code, search version-sensitive Blender documentation first, and report the exact refusal or execution error when it does not run. "
    "Use low-resolution evidence for routine review unless the user asks for final quality. Do not claim an artifact, save, import, render, checkpoint, or script run succeeded unless the tool result verifies it. "
    "When work is complete, summarize what changed, what remains pending, and any user decision still required."
)


def estimate_request_chars(*, messages=None, tools=None, system=AGENT_GUIDANCE):
    payload = {
        "system": system,
        "messages": messages or [],
        "tools": tools or [],
    }
    return len(json.dumps(payload, sort_keys=True))


def blender_tool_definitions():
    return tool_registry.definitions()


TOOL_SCHEMA_CHAR_BUDGET = 32000

_CORE_TOOL_NAMES = {
    "inspect_scene",
    "list_scene_objects",
    "get_object_details",
    "search_blender_docs",
    "get_blend_file_diagnostics",
}

_FALLBACK_TOOL_NAMES = {"draft_script"}
_PRIVILEGED_FALLBACK_TOOL_NAMES = set()

_TOOL_GROUPS = tool_registry.group_map()

_GROUP_KEYWORDS = {
    "selection": {"select", "selected", "active", "frame", "playhead", "inspect", "workspace", "tab", "focus", "viewport focus", "front view", "top view", "camera view"},
    "basic_edit": {"make", "create", "add", "move", "scale", "rotate", "transform", "object", "primitive", "empty", "marker", "collection", "duplicate", "copy", "parent", "align", "distribute", "layout", "arrange", "hide", "unhide", "visibility", "visible", "display", "wireframe", "show name", "in front", "edit mesh", "extrude", "inset", "loop cut", "loop-cut", "knife", "proportional edit", "bridge", "dissolve", "merge", "curve to mesh", "convert curve", "uv", "unwrap", "uv unwrap", "uv map", "boolean", "cutter", "mirror", "symmetry", "symmetrize", "solidify", "screw", "mesh quality", "modeling quality"},
    "materials": {"material", "shader", "texture", "textures", "texture map", "texture maps", "image texture", "pbr", "albedo", "diffuse map", "normal map", "roughness map", "metallic map", "bake map", "bake maps", "baked map", "baked maps", "texture bake", "map bake", "bake ao", "bake normal", "bake diffuse", "bake base color", "game ready", "game-ready", "texture ready", "texture-ready", "texture coordinate", "uv", "unwrap", "uv unwrap", "uv map", "color", "colour", "red", "blue", "green", "metal", "metallic", "chrome", "glass", "emission", "glow", "window"},
    "animation": {"animate", "animation", "animation brief", "prompt contract", "success criteria", "timing chart", "key pose", "key poses", "hold", "breakdown", "keyframe", "timeline", "frame", "orbit", "dolly", "camera move", "crane", "truck", "bounce", "driver", "motion", "motion arc", "arc", "follow path", "path", "retime", "interpolation", "easing", "loop", "cycles", "turntable", "pulse", "reveal", "stagger", "playblast", "timing", "spacing", "blocking", "anticipation", "squash", "stretch", "settle", "follow-through", "principles", "center of mass", "support", "contact sliding", "simulation", "physics bake", "persistent bake", "directed shot", "shot template"},
    "camera_render": {"camera", "render", "render job", "render output", "render pass", "render passes", "output resource", "quality check", "thumbnail", "still", "mp4", "video assembly", "assemble video", "validate render", "1080p", "4k", "frame sequence", "samples", "light", "lighting", "world", "background", "dof", "depth of field", "lens", "compositor", "compositing", "post process", "alpha", "transparent", "resolution", "intensity", "studio", "product stage", "presentation", "close-up", "closeup", "underside", "aov", "aovs", "shader aov", "cryptomatte", "normal pass", "depth pass", "z pass", "vector pass", "uv pass", "ambient occlusion pass"},
    "project_files": {"save", "save as", "save-as", "save copy", "autosave", "auto save", "open blend", "open file", "load blend", "new project", "create project", "blend file", ".blend", "project folder", "project directory", "checkpoint"},
    "deep_inspect": {"inspect", "analyze", "analyse", "summarize", "summary", "details", "world model", "what", "list", "screenshot", "viewport", "visual", "visual evidence", "evidence resource", "resource uri", "image", "capture", "playblast", "review", "diagnostic", "diagnostics", "quality", "mesh quality", "modeling quality", "validate model", "non-manifold", "loose geometry", "missing materials", "missing external", "linked library", "linked libraries", "blend file", "data-block", "datablock", "backup", "workspace", "layout json", "underside", "gear"},
    "external_assets": {"asset", "assets", "asset catalog", "asset library", "external asset", "external assets", "asset cache", "cache diagnostics", "poly haven", "polyhaven", "sketchfab", "hdri", "hdris", "environment map", "texture", "textures", "model library", "download model", "download asset", "import model", "import asset", "import hdri", "import texture", "sketchfab uid"},
    "advanced_create": {"advanced", "advanced 3d", "advanced 2d", "geometry nodes", "geometry-node", "node network", "shape key", "text", "curve", "particle", "armature", "constraint", "rig", "driver", "callout", "dimension", "label", "palette", "swatch", "organize", "collection", "cutout", "storyboard", "animatic", "procedural array", "object design", "design brief", "design mapper", "object family", "object kit", "kit", "kitbash", "scatter grid", "radial array", "mechanical", "mechanical part", "joint", "control panel", "modular", "wall panel", "pipe run", "desk lamp", "lamp", "architect lamp", "task lamp", "clamp lamp", "spring arm", "spring arms", "counterweight", "wide shade", "appliance", "coffee machine", "espresso", "electronics", "console", "furniture", "chair", "table", "shelf", "design grammar", "variant", "product prop", "prop generator", "edit mesh", "extrude", "inset", "loop cut", "loop-cut", "knife", "proportional edit", "bridge", "dissolve", "merge", "curve to mesh", "convert curve", "boolean", "cutter", "mirror", "symmetry", "symmetrize", "solidify", "screw", "directed shot", "shot template"},
    "refinement": {"refine", "polish", "smooth", "high poly", "high-poly", "detail", "bevel", "subdivision", "subsurf", "seam", "panel", "dimension", "callout", "stage", "palette", "lighting", "modifier stack", "edit mesh", "extrude", "inset", "bridge", "dissolve", "merge", "boolean", "cutter", "mirror", "symmetry", "symmetrize", "solidify", "thickness"},
    "vehicle": {"car", "vehicle", "truck", "wheel", "tire", "tyre", "rim", "headlight", "taillight", "windshield", "door", "grille"},
    "product": {"product", "catalog", "catalogue", "packshot", "presentation", "hero shot", "studio shot"},
    "character": {"character", "humanoid", "person", "head", "face", "eyes", "shoulder", "body", "toon", "avatar"},
    "rigging": {"rig", "armature", "bone", "constraint", "copy location", "copy rotation", "track to", "pose library", "pose marker", "ik", "fk", "space switch", "limb", "pole"},
    "curves_text": {"curve", "path", "text", "label", "spline"},
    "advanced_workflow": {"advanced workflow", "advanced 3d", "advanced 2d", "advanced animation", "director", "director workflow", "helper path", "helper gap", "which tools", "what tools", "workflow plan", "object design", "design brief", "design mapper", "object family"},
    "two_d_storyboard": {"2d", "two dimensional", "storyboard", "animatic", "storyboard panel", "storyboard panels", "2d panel", "2d panels", "cutout", "cut-out", "motion graphic", "motion graphics", "grease pencil", "grease-pencil", "2d animation"},
    "procedural_3d": {"procedural", "procedural 3d", "array stack", "modifier stack", "scatter", "scatter grid", "kitbash", "object design", "design brief", "design mapper", "object family", "object kit", "kit", "radial array", "mechanical", "mechanical joint", "mechanical part", "control panel", "modular", "wall panel", "pipe run", "desk lamp", "lamp", "architect lamp", "task lamp", "clamp lamp", "spring arm", "spring arms", "counterweight", "wide shade", "appliance", "coffee machine", "espresso", "electronics", "console", "furniture", "chair", "table", "shelf", "design grammar", "variant", "product prop", "hard surface", "hard-surface", "non destructive", "non-destructive", "edit mesh", "extrude", "inset", "loop cut", "loop-cut", "knife", "proportional edit", "bridge", "dissolve", "merge", "curve to mesh", "convert curve", "boolean", "cutter", "mirror", "symmetry", "symmetrize", "solidify", "screw", "thread", "spiral", "mesh quality", "modeling quality", "non-manifold", "loose geometry"},
    "simulation_setup": {"cloth", "cloth sim", "cloth simulation", "simulation setup", "physics setup", "sim setup"},
    "particles": {"particle", "particles", "simulation", "sim", "physics", "bake", "persistent bake", "cache", "point cache", "spark", "dust", "cloth"},
    "geometry_nodes": {"geometry node", "geometry-node", "geometry nodes", "geometry-node network", "node network", "node group", "procedural array", "array stack", "radial array"},
    "preview_control": {"commit", "revert", "undo", "cancel preview", "accept preview"},
}
_RENDER_OUTPUT_KEYWORDS = {
    "render pass",
    "render passes",
    "view layer pass",
    "aov",
    "aovs",
    "shader aov",
    "custom aov",
    "cryptomatte",
    "normal pass",
    "depth pass",
    "z pass",
    "position pass",
    "vector pass",
    "uv pass",
    "ambient occlusion pass",
    "ao pass",
}
_PROCEDURAL_TEXTURE_KEYWORDS = {
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
_UV_LAYOUT_KEYWORDS = {
    "uv",
    "uv unwrap",
    "unwrap",
    "uv map",
    "uv maps",
    "uv layout",
    "uv island",
    "uv islands",
    "pack islands",
    "pack uv",
    "texture coordinates",
    "texture coordinate",
    "texture ready",
    "texture-ready",
    "mark seams",
    "uv seams",
    "seam unwrap",
    "overlapping uvs",
    "overlap uvs",
    "texel density",
}
_AUTHORED_CONTENT_ACTIONS = {"create", "make", "build", "design", "model"}
_AUTHORED_CONTENT_SUBJECTS = {
    "appliance",
    "coffee machine",
    "control panel",
    "desk lamp",
    "furniture",
    "lamp",
    "modular wall panel",
    "product prop",
    "storyboard",
    "cutout",
}

def _tool_map():
    return {tool["name"]: tool for tool in blender_tool_definitions()}


def _tool_order():
    return [tool["name"] for tool in blender_tool_definitions()]


def _selection_text(prompt, context_bundle):
    parts = [str(prompt or "")]
    bundle = context_bundle or {}
    plan = bundle.get("context_plan")
    if isinstance(plan, dict):
        parts.append(" ".join(str(item) for item in plan.get("included", [])[:20]))
        parts.append(" ".join(str(item) for item in plan.get("omitted", [])[:20]))
    scene = bundle.get("scene_summary")
    if isinstance(scene, dict):
        parts.append(str(scene.get("object_counts_by_type") or ""))
    return "\n".join(parts).lower()


def _contains_keyword(text, keywords):
    return any(keyword in text for keyword in keywords)


def is_open_ended_authored_content(text):
    return _contains_keyword(text, _AUTHORED_CONTENT_ACTIONS) and _contains_keyword(text, _AUTHORED_CONTENT_SUBJECTS)


def _is_continuation_prompt(prompt):
    normalized = str(prompt or "").strip().lower()
    return normalized in {"ok", "okay", "continue", "go on", "do it", "yes", "yep", "keep going"}


def _schema_chars(tools):
    return len(json.dumps(tools, sort_keys=True))


def select_blender_tool_definitions(prompt="", context_bundle=None, *, max_schema_chars=TOOL_SCHEMA_CHAR_BUDGET):
    """Return request-relevant tool schemas plus selection metadata."""

    full_map = _tool_map()
    selected = set(_CORE_TOOL_NAMES)
    text = _selection_text(prompt, context_bundle)
    matched_groups = []

    if _is_continuation_prompt(prompt):
        for group in ("selection", "basic_edit", "materials", "animation", "camera_render", "advanced_create", "advanced_workflow", "two_d_storyboard", "procedural_3d", "refinement"):
            selected.update(_TOOL_GROUPS[group])
            matched_groups.append(group)
    else:
        for group, keywords in _GROUP_KEYWORDS.items():
            if _contains_keyword(text, keywords):
                selected.update(_TOOL_GROUPS[group])
                matched_groups.append(group)

    if _contains_keyword(text, _RENDER_OUTPUT_KEYWORDS):
        selected.update({"configure_render_outputs", "set_render_engine", "set_render_settings", "get_render_camera_compositor_details"})
        matched_groups.append("camera_render")
        matched_groups.append("render_outputs")

    if _contains_keyword(text, _PROCEDURAL_TEXTURE_KEYWORDS):
        selected.update({"create_procedural_texture_material", "create_shader_material", "inspect_material_setup", "get_shader_nodes_details"})
        matched_groups.append("materials")
        matched_groups.append("procedural_textures")

    if _contains_keyword(text, _UV_LAYOUT_KEYWORDS):
        selected.update({"mark_uv_seams", "uv_unwrap", "inspect_uv_layout", "create_image_texture_material", "inspect_material_setup", "repair_material_setup", "bake_maps", "create_shader_material"})
        matched_groups.append("basic_edit")
        matched_groups.append("materials")

    if helper_routing.should_include_draft_script(text, matched_groups):
        selected.update(_FALLBACK_TOOL_NAMES)
    if helper_routing.should_include_privileged_script(text, matched_groups):
        selected.update(_PRIVILEGED_FALLBACK_TOOL_NAMES)
    if is_open_ended_authored_content(text):
        selected.update(_FALLBACK_TOOL_NAMES)
        selected.update(_TOOL_GROUPS["advanced_create"])
        matched_groups.append("advanced_create")

    if not selected.intersection(TOOL_FUNCTIONS_FOR_MUTATION_COMPAT):
        selected.update({"select_objects"})

    ordered_names = [name for name in _tool_order() if name in selected and name in full_map]
    tools = [full_map[name] for name in ordered_names]

    budget = max(4000, int(max_schema_chars or TOOL_SCHEMA_CHAR_BUDGET))
    protected = set(_CORE_TOOL_NAMES)
    specific_refinement_groups = {"vehicle", "product", "character"}.intersection(matched_groups)
    for group in matched_groups:
        if group == "refinement" and specific_refinement_groups:
            continue
        if group in {"vehicle", "product", "character", "refinement", "camera_render", "rigging", "curves_text", "particles", "geometry_nodes", "external_assets", "advanced_workflow", "two_d_storyboard", "procedural_3d", "simulation_setup", "preview_control"}:
            protected.update(_TOOL_GROUPS.get(group, set()))
    if _contains_keyword(text, _RENDER_OUTPUT_KEYWORDS):
        protected.add("configure_render_outputs")
    if _contains_keyword(text, _PROCEDURAL_TEXTURE_KEYWORDS):
        protected.add("create_procedural_texture_material")
    if _contains_keyword(text, _UV_LAYOUT_KEYWORDS):
        protected.update({"mark_uv_seams", "uv_unwrap", "inspect_uv_layout", "bake_maps"})
    if "basic_edit" in matched_groups:
        protected.update({"select_objects", "set_selected_location_delta", "set_selected_transform", "assign_material_to_selected"})
    if "animation" in matched_groups:
        protected.update(
            {
                "create_animation_brief",
                "plan_advanced_scene_workflow",
                "get_animation_scene_context",
                "create_timing_chart",
                "plan_animation_workflow",
                "run_animation_workflow",
                "run_animation_task",
                "capture_viewport",
                "capture_animation_playblast",
                "capture_object_inspection_renders",
                "get_visual_evidence_resources",
                "block_key_poses",
                "add_breakdown_pose",
                "set_pose_hold",
                "set_rig_pose_hold",
                "set_rig_custom_property_keyframes",
                "get_rig_pose_library_details",
                "apply_rig_pose_from_action",
                "apply_rig_pose_marker",
                "apply_rig_action_clip",
                "offset_rig_limb_controls",
                "create_motion_arc",
                "create_camera_dolly_animation",
                "analyze_motion_arcs",
                "analyze_fcurve_spacing",
                "analyze_pose_clarity",
                "analyze_animation_principles",
                "sample_animation_state",
                "analyze_contact_sliding",
                "analyze_collision_penetration",
                "analyze_center_of_mass",
                "analyze_camera_framing",
                "analyze_motion_physics",
                "inspect_simulation_bake",
                "stage_persistent_simulation_bake",
                "compare_animation_to_brief",
                "review_playblast_against_brief",
                "review_inspection_renders_against_brief",
                "repair_animation_from_findings",
                "run_animation_repair_loop",
                "set_scene_frame_range",
                "set_animation_preview_range",
                "animate_selected_transform",
                "animate_object_bounce",
                "create_progressive_bounce_animation",
                "animate_material_property",
                "animate_light_property",
                "create_follow_path_animation",
                "create_turntable_animation",
                "create_pulse_animation",
                "create_reveal_animation",
                "create_staggered_motion",
                "set_action_interpolation",
                "retime_actions",
                "add_action_cycles",
                "clear_animation",
            }
        )
    if "deep_inspect" in matched_groups:
        protected.update(
            {
                "capture_viewport",
                "capture_animation_playblast",
                "capture_object_inspection_renders",
                "get_visual_evidence_resources",
                "review_playblast_against_brief",
                "review_inspection_renders_against_brief",
                "repair_animation_from_findings",
                "run_animation_repair_loop",
            }
        )
    explicit_material_request = _contains_keyword(
        text,
        {
            "material",
            "shader",
            "texture",
            "texture ready",
            "texture-ready",
            "texture coordinate",
            "bake map",
            "bake maps",
            "baked map",
            "baked maps",
            "texture bake",
            "map bake",
            "bake ao",
            "bake normal",
            "bake diffuse",
            "bake base color",
            "game ready",
            "game-ready",
            "uv",
            "unwrap",
            "uv unwrap",
            "uv map",
            "preset",
            "color",
            "colour",
            "red",
            "blue",
            "green",
            "metal",
            "metallic",
            "chrome",
            "glass",
            "emission",
            "glow",
        },
    )
    if "materials" in matched_groups and explicit_material_request:
        protected.update(
            {
                "get_material_node_details",
                "get_shader_nodes_details",
                "assign_material_to_selected",
                "assign_emission_material_to_selected",
                "create_shader_material",
                "create_image_texture_material",
                "inspect_material_setup",
                "repair_material_setup",
                "bake_maps",
                "uv_unwrap",
            }
        )
    if "draft_script" in selected:
        protected.add("draft_script")
    if "draft_privileged_script" in selected:
        protected.add("draft_privileged_script")
    while _schema_chars(tools) > budget:
        removable_index = next(
            (index for index in range(len(ordered_names) - 1, -1, -1) if ordered_names[index] not in protected),
            None,
        )
        if removable_index is None:
            break
        ordered_names.pop(removable_index)
        tools.pop(removable_index)

    selected_names = [tool["name"] for tool in tools]
    omitted_names = [name for name in _tool_order() if name not in selected_names]
    metadata = {
        "selected_tool_names": selected_names,
        "omitted_tool_names": omitted_names,
        "selected_tool_count": len(selected_names),
        "available_tool_count": len(full_map),
        "schema_chars": _schema_chars(tools),
        "estimated_schema_tokens": int((_schema_chars(tools) + 3) / 4),
        "matched_groups": sorted(set(matched_groups)),
        "budget_chars": budget,
    }
    return tools, metadata


TOOL_FUNCTIONS_FOR_MUTATION_COMPAT = {
    "set_selected_location_delta",
    "set_selected_transform",
    "create_primitive",
    "create_empty",
    "set_object_visibility",
    "set_object_display",
    "assign_material_to_selected",
    "assign_emission_material_to_selected",
    "create_shader_material",
    "create_image_texture_material",
    "repair_material_setup",
    "bake_maps",
    "create_procedural_texture_material",
    "uv_unwrap",
    "mark_uv_seams",
    "plan_director_workflow",
    "plan_asset_import_workflow",
    "plan_advanced_scene_workflow",
    "animate_object_bounce",
    "create_progressive_bounce_animation",
    "animate_material_property",
    "animate_light_property",
    "create_follow_path_animation",
    "set_action_interpolation",
    "retime_actions",
    "add_action_cycles",
    "clear_animation",
    "set_animation_preview_range",
    "run_animation_workflow",
    "run_animation_task",
    "run_animation_repair_loop",
    "create_turntable_animation",
    "create_pulse_animation",
    "create_reveal_animation",
    "create_staggered_motion",
    "block_key_poses",
    "add_breakdown_pose",
    "set_pose_hold",
    "set_rig_pose_hold",
    "set_rig_custom_property_keyframes",
    "get_rig_pose_library_details",
    "apply_rig_pose_from_action",
    "apply_rig_pose_marker",
    "apply_rig_action_clip",
    "offset_rig_limb_controls",
    "create_motion_arc",
    "apply_procedural_array_stack",
    "edit_mesh",
    "curve_to_mesh",
    "boolean_op",
    "mirror_model",
    "symmetrize_model",
    "solidify_model",
    "screw_model",
    "create_camera_dolly_animation",
    "add_cloth_simulation_to_selected",
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
    "cancel_external_asset_import_job",
    "delete_external_asset_job",
    "get_external_asset_cache_diagnostics",
    "prune_external_asset_cache",
    "duplicate_selected_objects",
    "parent_selected_to_empty",
    "align_selected_objects",
    "distribute_selected_objects",
    "shade_smooth_selected",
    "add_bevel_and_subsurf",
    "create_studio_product_stage",
    "add_dimension_callouts",
    "apply_lighting_preset",
    "create_material_palette",
    "create_product_turntable_setup",
    "create_lookdev_turntable_review",
    "configure_render_outputs",
    "create_procedural_texture_material",
    "prepare_imported_asset_presentation",
    "organize_scene_for_production",
    "draft_script",
}


def blender_tool_definitions_for_request(prompt="", context_bundle=None, *, max_schema_chars=TOOL_SCHEMA_CHAR_BUDGET):
    tools, _metadata = select_blender_tool_definitions(
        prompt=prompt,
        context_bundle=context_bundle,
        max_schema_chars=max_schema_chars,
    )
    return tools


def register():
    pass


def unregister():
    pass
