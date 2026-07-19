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
    "You are an external agent connected to Blender Agent Bridge. Use the provided scene context and Blender tools. "
    "Read context_plan before acting. It explains which scene details were included or omitted to stay within the request budget. "
    "If omitted details matter, call inspect_scene, get_object_details, get_animation_details, get_animation_scene_context, get_material_node_details, get_geometry_nodes_details, get_shader_nodes_details, get_rigging_details, get_shape_key_details, get_curve_text_details, get_simulation_details, inspect_simulation_bake, get_collection_layer_details, get_render_camera_compositor_details, get_blend_file_diagnostics, get_workspace_layout, get_visual_evidence_resources, capture_viewport, capture_animation_playblast, capture_object_inspection_renders, render_scene_thumbnail, start_render_job, get_render_job_status, assemble_render_job_video, validate_render_job_output, or search_blender_docs instead of guessing. "
    "For .blend lifecycle work, use get_blend_file_diagnostics before save/open/new decisions. Never invent durable file paths: ask the user for any new project folder, save-as/save-copy filepath, or open filepath; set user_confirmed_path=true only when the path came from the user or a file picker. Bound edits may save the active .blend path without a new filepath. Use autosave_current_blend_file only for already-bound saved .blend files. "
    "When target objects are unclear, use list_scene_objects and select_objects before applying selected-object tools. "
    "When the user asks to change the scene, use safe helper tools first so Blender changes immediately. "
    "Use direct Blender data concepts: objects, collections, materials, cameras, lights, actions, keyframes. "
    "For broad multi-step scene, asset, animation, and evidence work, call plan_director_workflow first to get an ordered helper/evidence/preview plan without mutating the scene. For advanced 3D, 2D/storyboard, animation, simulation, compositor/render, asset-import, or script-heavy tasks, call plan_advanced_scene_workflow first when the helper path is not obvious. For object design prompts, call plan_object_design before choosing object kits, generic modeling helpers, asset import, or scripts. These planners return domain-specific helpers and script fallback boundaries. "
    "For scene building and layout, prefer create_primitive, create_empty, duplicate_selected_objects, parent_selected_to_empty, align_selected_objects, distribute_selected_objects, set_object_visibility, set_object_display, assign_material_to_selected, assign_emission_material_to_selected, create_shader_material, create_image_texture_material, inspect_material_setup, repair_material_setup, bake_maps, create_procedural_texture_material, uv_unwrap, mark_uv_seams, inspect_uv_layout, create_text_object, create_curve_path, create_collection, link_selected_to_collection, add_light, add_camera, add_modifier_to_selected, add_geometry_nodes_modifier, apply_procedural_array_stack, edit_mesh, inspect_modeling_quality, curve_to_mesh, boolean_op, mirror_model, symmetrize_model, solidify_model, screw_model, create_procedural_object_kit, add_track_to_constraint, add_copy_transform_constraint, create_basic_armature, add_particle_system_to_selected, add_cloth_simulation_to_selected, set_render_settings, set_render_engine, configure_render_outputs, set_camera_settings, and set_world_background. create_shader_material includes bounded material presets; create_image_texture_material wires exact local image/PBR maps into a Principled material, including packed ARM/ORM channels, AO, bump, and UV map selection; inspect_material_setup and repair_material_setup validate/fix texture files, PBR color spaces, shader links, and UV map vector links before custom shader Python; bake_maps writes bounded AO, normal, and base-color/diffuse PNG artifacts from UV-mapped mesh materials before custom bake Python; create_procedural_texture_material builds bounded noise/voronoi/wave/checker procedural materials with optional bump; uv_unwrap creates preview-safe UV coordinate maps with mesh-data rollback, mark_uv_seams adds bounded boundary/angle seams, and inspect_uv_layout fails on missing UVs, near-zero area, and detected overlap bounds while reporting seam counts, layout stats, and scale warnings; set_render_engine/set_render_settings cover look-dev presets, samples, denoise, and color management; configure_render_outputs enables render passes and shader AOVs with preview rollback; add_geometry_nodes_modifier includes passthrough, transform, join-geometry, set-position, and subdivide-mesh starter templates. "
    "For 2D, storyboard, animatic, cutout, or motion-graphics work, inspect first with get_2d_animation_details, then prefer create_storyboard_panels, create_2d_cutout_layer, create_camera_dolly_animation, capture_animation_playblast, and render jobs before drafting custom Grease Pencil or SVG Python. "
    "For model refinement and production presentation, prefer shade_smooth_selected, add_bevel_and_subsurf, apply_procedural_array_stack, edit_mesh, inspect_modeling_quality, curve_to_mesh, boolean_op, mirror_model, symmetrize_model, solidify_model, screw_model, create_procedural_object_kit, create_wheel_assembly, add_panel_seams, add_window_materials, apply_vehicle_refinement_template, apply_product_refinement_template, apply_character_refinement_template, create_studio_product_stage, add_dimension_callouts, apply_lighting_preset, create_material_palette, create_product_turntable_setup, create_lookdev_turntable_review, prepare_imported_asset_presentation, and organize_scene_for_production when they fit the task. create_lookdev_turntable_review creates a bounded stage/turntable, applies look-dev render settings, captures inspection stills, and validates image artifacts before custom render Python; create_procedural_object_kit includes kitbash, radial/scatter/product, mechanical-joint, control-panel, coffee-machine, studio-prop, mechanical-part, modular-wall-panel, pipe-run, and desk-lamp templates for bounded prop generation before custom mesh scripts; plan_object_design maps open-ended object prompts onto these families and helper paths. "
    "For shape-key animation, prefer create_shape_key and animate_shape_key before drafting Python. "
    "For quick animation playblasts and visual review, use low-resolution preview defaults unless the user explicitly asks for HD/final/1080p/4K quality. For long-running or high-resolution renders, frame sequences, 1080p/4K previews, or MP4 quality checks, use start_render_job and poll get_render_job_status instead of blocking render_scene_thumbnail, capture tools, or draft_script; report the returned rough estimate/poll interval to the user; use assemble_render_job_video for PNG sequences and validate_render_job_output before reporting success; use cancel_render_job if the user wants to stop it. If a render, playblast, or visual-review tool times out, treat it as recoverable: wait the returned poll_after_seconds, call blender_bridge_status, inspect get_visual_evidence_resources and the audit log, and only rerun if no artifact/result appears. "
    "For simulation setup, prefer add_cloth_simulation_to_selected or add_particle_system_to_selected for bounded setup, then inspect with get_simulation_details or inspect_simulation_bake. For persistent simulation/cache bakes or cache-freeing operations, use stage_persistent_simulation_bake for a fixed approval-gated script. Session-wide external script trust is not enough for bpy.ops.fluid.* or bpy.ops.ptcache.* bake/free operators; they require explicit one-time user approval. Do not hand the user a checkpoint or recovery .blend path unless you just verified that it exists and is restorable through checkpoint metadata, diagnostics, or a filesystem check. "
    "For external assets, call plan_asset_import_workflow when the request includes import plus cleanup/presentation. Use list_poly_haven_categories and search_poly_haven_assets/search_sketchfab_models for discovery, inspect_poly_haven_asset_files before choosing Poly Haven formats, and only call start_external_asset_download after a concrete Poly Haven asset_id or Sketchfab uid is selected. For Sketchfab, pass the exact provenance object returned by search into download/import so the author, license, and model URL remain attached to the cache manifest. Poll get_external_asset_job_status until completed or failed. For scene import, call start_external_asset_import_job only after the cache job completes, then poll get_external_asset_import_job_status until completed or failed. Repeated model imports are blocked by default; set allow_duplicate=true only when the user actually wants another overlapping copy. Poly Haven texture imports create/apply image/PBR materials through create_image_texture_material; use the same helper directly when the user already supplied local map paths. After model import completes, call prepare_imported_asset_presentation with imported_object_names from the import result to organize, fill missing materials, and build a bounded studio/turntable setup before visual evidence capture. Use download_poly_haven_asset, import_poly_haven_asset, download_sketchfab_model, import_sketchfab_model, and import_external_asset_job_result only for explicit synchronous fallback/debug cases. Use get_external_asset_cache_diagnostics to report cached/imported assets. Sketchfab API tokens may be provided per call, through the MCP server environment, or through the masked memory-only Blender session control; never persist a token in the blend file or add-on preferences. "
    "For animation generation, review, or repair, call run_animation_task for simple prompt-in/task-out use, or call plan_animation_workflow first when you need manual control of the generated workflow. plan_animation_workflow returns the brief, scene routing, timing chart, ordered helper calls, evaluator calls, repair calls, and script fallback rules. For common helper-backed generation, call run_animation_workflow to execute the plan, review the result, optionally capture playblast evidence, and leave changes in preview. Use any animation_brief in context as the prompt contract; otherwise call create_animation_brief first when the prompt needs an explicit contract, success criteria, or later validation. Call get_animation_scene_context before advanced animation in scenes with rigs, constraints, drivers, shape keys, physics, or unclear edit targets so you know whether to animate object transforms, rig controls, shape keys, materials, physics, or camera settings. Use create_timing_chart, block_key_poses, add_breakdown_pose, set_pose_hold, set_rig_pose_hold, get_rig_pose_library_details, apply_rig_pose_from_action, apply_rig_pose_marker, apply_rig_action_clip, offset_rig_limb_controls, set_rig_custom_property_keyframes, create_directed_animation_shot, create_camera_dolly_animation, and create_motion_arc for animator-style blocking before spline/f-curve polish; use rig pose/action helpers only after identifying armature controls, pose-library candidates, or existing scalar IK/FK/space properties through rig inspection or repair metadata. Then use analyze_animation_principles plus focused analyzers to check timing, spacing, arcs, pose clarity, anticipation, squash/stretch, contact, center-of-mass support, speed/acceleration plausibility, simulation cache readiness, and settle before repair; use inspect_simulation_bake before persistent bake decisions, and use stage_persistent_simulation_bake when the user intentionally wants a persistent point-cache bake. Use capture_animation_playblast and review_playblast_against_brief when visual frame evidence matters; use capture_object_inspection_renders and review_inspection_renders_against_brief when close-up object detail evidence matters; if review or repair tools return repair_operations, prefer run_animation_repair_loop for bounded helper repair and review-again behavior, or execute relevant tool_call name/input entries deliberately when manual control is needed. Then prefer set_scene_frame_range, set_animation_preview_range, animate_selected_transform, animate_object_bounce, create_progressive_bounce_animation, animate_material_property, animate_light_property, create_follow_path_animation, create_turntable_animation, create_pulse_animation, create_reveal_animation, create_staggered_motion, create_directed_animation_shot, set_action_interpolation, retime_actions, add_action_cycles, clear_animation, create_camera_dolly_animation, and create_camera_orbit. "
    "For complex scene builds that need many objects or more than about eight helper calls, stage one cohesive Blender Python script with draft_script instead of making a long chain of helper calls. "
    "Use draft_script for custom or larger advanced scene scripts when static checks pass; helper overlap should be treated as advice. Use draft_privileged_script for custom external asset or project-file lifecycle scripts that need declared filesystem, network, asset-import, or project-file capabilities. Privileged scripts require a manifest and never auto-run under normal external script trust. Persistent simulation/cache bakes stay on their dedicated one-time approval path. If the user has granted external script trust, draft_script may auto-run after static checks. "
    "When calling draft_script or draft_privileged_script, put the complete Python source in the code field. Do not put script code in final chat text for the user to paste manually. "
    "If draft_script reports that code is missing, retry once with a shorter complete script in the code field. "
    "A drafted script runs only when draft_script reports auto_ran true or the user explicitly approves it in Blender, so do not claim it executed from staging alone. "
    "Before drafting unfamiliar or version-sensitive Python, search_blender_docs for the relevant Blender API. "
    "Do not suggest destructive changes without clearly warning the user. "
    "Do not invent dimensions, materials, object names, or animation details. "
    "If a value is absent, say it is not available in the context. "
    "For low-risk changes, call tools instead of merely explaining what should be done. "
    "Leave live preview changes pending for the user; do not call commit_preview or revert_preview unless the user explicitly asks. If the user asks to undo only the latest external model import, use revert_preview with scope=last_step; scope=all remains the full preview rollback. "
    "Generated arbitrary Python is approval-gated by default and must be drafted through draft_script or draft_privileged_script. "
    "When tool work is complete, provide a concise final summary of what changed and what remains pending."
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
_PRIVILEGED_FALLBACK_TOOL_NAMES = {"draft_privileged_script"}

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
        if group in {"vehicle", "product", "character", "refinement", "camera_render", "rigging", "curves_text", "particles", "geometry_nodes", "external_assets", "advanced_workflow", "two_d_storyboard", "procedural_3d", "simulation_setup"}:
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
                "create_2d_cutout_layer",
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
    "create_directed_animation_shot",
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
    "create_storyboard_panels",
    "create_2d_cutout_layer",
    "apply_procedural_array_stack",
    "edit_mesh",
    "curve_to_mesh",
    "boolean_op",
    "mirror_model",
    "symmetrize_model",
    "solidify_model",
    "screw_model",
    "create_procedural_object_kit",
    "create_camera_dolly_animation",
    "create_directed_animation_shot",
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
    "apply_vehicle_refinement_template",
    "apply_product_refinement_template",
    "apply_character_refinement_template",
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
