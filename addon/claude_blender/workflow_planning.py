"""Read-only capability routing for advanced Blender workflows."""

from __future__ import annotations

import bpy

from . import (
    helper_routing,
    presentation_support,
    script_execution,
    script_runner,
    tool_registry,
)


_SEMANTIC_SCULPT_TOOL_NAMES = [
    spec.name
    for spec in tool_registry.REGISTRY.specs()
    if "semantic_sculpt" in spec.groups
]


ADVANCED_WORKFLOW_DOMAINS = {
    "model_quality": {
        "keywords": set(),
        "tools": [
            "plan_model_quality_workflow",
            "list_scene_objects",
            "get_blend_file_diagnostics",
            "prepare_reference_images",
            "create_reference_guides_from_annotations",
            "create_multiview_reference_guides",
            "create_multiview_visual_hull",
            "create_multiview_depth_surface",
            "fit_surface_to_multiview_references",
            "create_reference_modeling_guides",
            "inspect_reference_modeling_guides",
            "create_reference_blockout",
            "adaptive_remesh",
            *_SEMANTIC_SCULPT_TOOL_NAMES,
            "compare_model_to_reference",
            "evaluate_multiview_reference_match",
            "auto_reference_sculpt_repair",
            "inspect_modeling_quality",
            "plan_advanced_scene_workflow",
            "capture_viewport",
            "capture_object_inspection_renders",
            "get_visual_evidence_resources",
        ],
        "script_boundary": (
            "Use an LLM-authored reference brief and model-quality rubric before "
            "building. For raw reference images, normalize intake and masks first. "
            "For calibrated multi-view evidence, construct a visual hull or "
            "depth-constrained surface, run joint measured fitting, score every view, "
            "and adapt topology only where needed before persistent semantic regions "
            "and measured form-aware or screen-space repairs. Under active trust, cohesive "
            "scripts remain appropriate for bespoke construction that the bounded "
            "fields cannot express."
        ),
    },
    "2d_storyboard": {
        "keywords": {"2d", "two dimensional", "storyboard", "animatic", "storyboard panel", "storyboard panels", "2d panel", "2d panels", "grease pencil", "grease-pencil", "cutout", "cut-out", "motion graphic"},
        "tools": [
            "get_2d_animation_details",
            "create_text_object",
            "create_curve_path",
            "create_camera_dolly_animation",
            "capture_animation_playblast",
        ],
        "script_boundary": "Under active trust, prefer one cohesive script for authored 2D/storyboard construction; use helpers for inspection, evidence, and explicitly requested isolated operations.",
    },
    "procedural_3d": {
        "keywords": {"advanced 3d", "procedural", "array", "scatter", "kit", "object kit", "kitbash", "mechanical", "mechanical joint", "mechanical part", "control panel", "modular", "wall panel", "pipe run", "hard surface", "hard-surface", "geometry nodes", "node group", "modifier stack", "edit mesh", "extrude", "inset", "loop cut", "loop-cut", "knife", "proportional edit", "bridge", "dissolve", "merge", "curve to mesh", "convert curve", "boolean", "cutter", "mirror", "symmetry", "symmetrize", "solidify", "screw", "thread", "spiral", "wall thickness"},
        "tools": [
            "get_geometry_nodes_details",
            "apply_procedural_array_stack",
            "edit_mesh",
            "curve_to_mesh",
            "boolean_op",
            "mirror_model",
            "symmetrize_model",
            "solidify_model",
            "screw_model",
            "add_geometry_nodes_modifier",
            "shade_smooth_selected",
            "add_bevel_and_subsurf",
            "organize_scene_for_production",
        ],
        "script_boundary": "After inspection, prefer one cohesive trusted script for authored procedural geometry, custom nodes, and multi-object construction; use exact helpers for requested isolated operations.",
    },
    "advanced_animation": {
        "keywords": {"advanced animation", "shot", "blocking", "dolly", "crane", "truck", "camera move", "camera animation", "nla", "retime", "f-curve", "pose", "acting", "motion arc"},
        "tools": [
            "plan_animation_workflow",
            "run_animation_workflow",
            "create_camera_orbit",
            "create_camera_dolly_animation",
            "block_key_poses",
            "add_breakdown_pose",
            "set_pose_hold",
            "create_motion_arc",
            "analyze_animation_principles",
        ],
        "script_boundary": "After brief, scene-context, and timing preflight, prefer one cohesive trusted script for authored animation, rig, and driver work; keep evaluation and evidence on helpers.",
    },
    "simulation_setup": {
        "keywords": {"simulation", "cloth", "physics", "particle", "rigid body", "cache", "bake"},
        "tools": [
            "get_simulation_details",
            "add_cloth_simulation_to_selected",
            "add_particle_system_to_selected",
            "inspect_simulation_bake",
            "stage_persistent_simulation_bake",
        ],
        "script_boundary": "Inspect first; persistent bake/free scripts may run only under active session trust and can block Blender while they execute.",
    },
    "asset_import": {
        "keywords": {"external asset", "asset import", "import asset", "import model", "download asset", "poly haven", "polyhaven", "sketchfab", "hdri", "texture library"},
        "tools": [
            "plan_asset_import_workflow",
            "search_poly_haven_assets",
            "search_sketchfab_models",
            "start_external_asset_download",
            "get_external_asset_job_status",
            "start_external_asset_import_job",
            "get_external_asset_import_job_status",
            "organize_scene_for_production",
            "create_studio_product_stage",
            "capture_viewport",
        ],
        "script_boundary": "Prefer bounded async asset jobs and project-file tools for validation, provenance, and progress; trusted scripts retain Blender Run Script permissions.",
    },
    "compositor_render": {
        "keywords": {"compositor", "compositing", "post", "post process", "transparent", "alpha", "render preset", "render pass", "render passes", "aov", "aovs", "cryptomatte", "normal pass", "depth pass", "mp4", "preview"},
        "tools": [
            "get_render_camera_compositor_details",
            "set_render_settings",
            "set_render_engine",
            "configure_render_outputs",
            "set_camera_settings",
            "render_scene_thumbnail",
            "start_render_job",
            "assemble_render_job_video",
            "validate_render_job_output",
        ],
        "script_boundary": "Use draft_script for custom compositor node graphs until compositor node-tree rollback support is implemented.",
    },
}


def _advanced_domain_matches(prompt, domains=None):
    requested = [str(domain).strip().lower() for domain in domains or [] if str(domain).strip()]
    if requested:
        return [domain for domain in ADVANCED_WORKFLOW_DOMAINS if domain in requested]
    text = str(prompt or "").lower()
    matches = []
    for domain, spec in ADVANCED_WORKFLOW_DOMAINS.items():
        if domain == "model_quality":
            matched = helper_routing.is_reference_model_quality_request(text)
        else:
            matched = any(keyword in text for keyword in spec["keywords"])
        if matched:
            matches.append(domain)
    authored_scene_alongside_animation_terms = {
        "build",
        "create",
        "design",
        "generate",
        "model",
        "rebuild",
        "recreate",
        "rig",
        "sculpt",
        "shade",
        "shader",
        "texture",
    }
    authored_animation = helper_routing.is_authored_animation_request(text)
    if (
        helper_routing.is_script_first_authored_request(text)
        and (
            not authored_animation
            or helper_routing.contains_any_guard_term(
                text,
                authored_scene_alongside_animation_terms,
            )
        )
        and "procedural_3d" not in matches
    ):
        matches.append("procedural_3d")
    if (
        authored_animation
        and "advanced_animation" not in matches
    ):
        matches.append("advanced_animation")
    return matches or ["procedural_3d"]


_MODEL_QUALITY_BRIEF_LIST_FIELDS = (
    "silhouette",
    "primary_masses",
    "secondary_forms",
    "landmarks",
    "proportion_checks",
    "surface_cues",
    "negative_constraints",
    "source_notes",
)
_MODEL_QUALITY_REQUIRED_BRIEF_FIELDS = ("silhouette", "primary_masses", "proportion_checks")
_MODEL_QUALITY_INSPECTION_VIEWS = {"front_below", "underside", "side", "front", "rear", "top"}


def _bounded_brief_items(value, *, max_items=24, max_chars=240):
    items = []
    seen = set()
    for raw in value if isinstance(value, (list, tuple)) else []:
        item = str(raw or "").strip()[:max_chars]
        if not item or item in seen:
            continue
        seen.add(item)
        items.append(item)
        if len(items) >= max_items:
            break
    return items


def _normalize_model_quality_brief(reference_brief, reference_description):
    source = dict(reference_brief or {}) if isinstance(reference_brief, dict) else {}
    brief = {
        "subject": str(source.get("subject") or "model").strip()[:120] or "model",
    }
    for field in _MODEL_QUALITY_BRIEF_LIST_FIELDS:
        brief[field] = _bounded_brief_items(source.get(field))
    reference_text = str(reference_description or "").strip()[:240]
    if reference_text and reference_text not in brief["source_notes"]:
        brief["source_notes"].insert(0, reference_text)
    requested_views = _bounded_brief_items(source.get("inspection_views"), max_items=6, max_chars=32)
    brief["inspection_views"] = [
        view.lower()
        for view in requested_views
        if view.lower() in _MODEL_QUALITY_INSPECTION_VIEWS
    ] or ["front", "side"]
    return brief


def _model_quality_rubric(brief):
    return [
        {
            "criterion": "silhouette_match",
            "applies": True,
            "target": "The primary-view outline and negative spaces match the supplied silhouette observations.",
            "evidence_from_brief": list(brief["silhouette"]),
            "repair_action": "Adjust primary masses before secondary forms or surface work.",
        },
        {
            "criterion": "proportion_match",
            "applies": True,
            "target": "Declared ratios, spacing, depth relationships, and contact points match the reference brief.",
            "evidence_from_brief": list(brief["proportion_checks"]),
            "repair_action": "Move or rescale named forms, then recapture the same comparison views.",
        },
        {
            "criterion": "landmark_placement",
            "applies": bool(brief["landmarks"]),
            "target": "Every declared landmark is placed, aligned, and attached consistently with the reference.",
            "evidence_from_brief": list(brief["landmarks"]),
            "repair_action": "Repair landmark position and attachment before material polish.",
        },
        {
            "criterion": "form_continuity",
            "applies": bool(brief["secondary_forms"]),
            "target": "Primary and secondary forms transition cleanly without a disconnected or stacked-primitive read.",
            "evidence_from_brief": list(brief["primary_masses"] + brief["secondary_forms"]),
            "repair_action": "Repair intersections, tangencies, transitions, and support/contact forms.",
        },
        {
            "criterion": "surface_match",
            "applies": bool(brief["surface_cues"]),
            "target": "Materials and surface treatment match the supplied cues without hiding form errors.",
            "evidence_from_brief": list(brief["surface_cues"]),
            "repair_action": "Apply only the material, texture, hair, fiber, or finish treatment explicitly required by the brief.",
        },
        {
            "criterion": "constraint_compliance",
            "applies": bool(brief["negative_constraints"]),
            "target": "The result avoids every declared must-not-do constraint.",
            "evidence_from_brief": list(brief["negative_constraints"]),
            "repair_action": "Remove or revise the violating form, detail, or surface treatment.",
        },
        {
            "criterion": "evidence_ready",
            "applies": True,
            "target": "Reference-aligned viewport and inspection captures prove the result before a commit decision.",
            "evidence_from_brief": list(brief["inspection_views"]),
            "repair_action": "Recapture consistent views after each repair pass.",
        },
    ]


def _authored_construction_strategy(context, prompt):
    trust = script_runner.external_script_trust_snapshot(context)
    helpers_requested = helper_routing.prefers_bounded_helpers(prompt)
    if helpers_requested:
        selected = "bounded_helpers_requested"
        reason = "The user explicitly requested helpers or no Python."
    elif trust["active"]:
        selected = "cohesive_trusted_script"
        reason = "Script trust is active, so bespoke authored mutation defaults to one cohesive script."
    else:
        selected = "bounded_helpers_until_trust_enabled"
        reason = "Script trust is off; use bounded helpers or ask the user to enable Trust Agent Scripts."
    return {
        "selection": selected,
        "default_when_trusted": "cohesive_trusted_script",
        "user_helper_override": helpers_requested,
        "script_trust": trust,
        "reason": reason,
        "script_first_domains": [
            "object_generation",
            "modeling",
            "animation",
            "materials",
            "custom_nodes",
            "rigging",
            "look_development",
        ],
        "bounded_helper_domains": [
            "inspection",
            "project_files",
            "external_assets",
            "long_render_jobs",
            "persistent_bakes",
            "evidence_capture",
            "preview_commit_or_revert",
        ],
        "long_running_script_path": {
            "selection_rule": (
                "Use a background trusted-script job when the cohesive script is likely to exceed the bridge timeout "
                "or benefits from isolated execution; this is still the primary script path, not a helper fallback."
            ),
            "start": "start_trusted_script_job",
            "poll": "get_trusted_script_job_status",
            "cancel": "cancel_trusted_script_job",
            "apply": "apply_trusted_script_job_result",
            "live_scene_unchanged_until_confirmed_apply": True,
        },
        "script_preflight": helper_routing.script_authoring_preflight(),
    }


def plan_model_quality_workflow(
    context,
    *,
    prompt="",
    reference_description="",
    reference_brief=None,
    target_objects=None,
    quality_floor=4,
    label="Plan model quality workflow",
):
    """Plan reference-driven modeling with evidence and repair gates."""

    prompt = str(prompt or "").strip()
    reference_text = str(reference_description or "").strip()[:4000]
    target_names = [str(item) for item in target_objects or [] if str(item).strip()]
    existing_targets = []
    missing_targets = []
    for name in target_names:
        if bpy.data.objects.get(name):
            existing_targets.append(name)
        else:
            missing_targets.append(name)
    brief = _normalize_model_quality_brief(reference_brief, reference_text)
    missing_brief_fields = [
        field for field in _MODEL_QUALITY_REQUIRED_BRIEF_FIELDS if not brief[field]
    ]
    brief_ready = not missing_brief_fields
    subject = brief["subject"]
    breakdown = {
        "silhouette": list(brief["silhouette"]),
        "main_masses": list(brief["primary_masses"] + brief["secondary_forms"]),
        "landmarks": list(brief["landmarks"]),
        "proportion_checks": list(brief["proportion_checks"]),
        "surface_language": list(brief["surface_cues"]),
        "negative_constraints": list(brief["negative_constraints"]),
    }
    rubric = _model_quality_rubric(brief)
    floor = max(1, min(5, int(quality_floor or 4)))
    construction_strategy = _authored_construction_strategy(context, prompt)
    scripted_construction = construction_strategy["selection"] == "cohesive_trusted_script"
    inspection_calls = [
        _planned_tool_call(
            "list_scene_objects",
            {"max_objects": 100},
            reason="Record the baseline scene inventory before mutation and support post-build target resolution.",
            gateway_ready=True,
        ),
        _planned_tool_call(
            "get_blend_file_diagnostics",
            {},
            reason="Check project state, missing data, and checkpoint safety before broad modeling.",
            gateway_ready=True,
        ),
    ]
    if existing_targets:
        inspection_calls.append(
            _planned_tool_call(
                "inspect_modeling_quality",
                {"object_names": existing_targets, "selected_only": False, "include_children": True},
                reason="Establish the topology and material baseline for existing target objects.",
                gateway_ready=True,
            )
        )
    construction_calls = []
    if brief_ready:
        if scripted_construction:
            construction_calls.append(
                _planned_tool_call(
                    "draft_script",
                    {},
                    reason="Author and run one cohesive checkpoint-backed script for the reference-derived primary construction.",
                    mutates_scene=True,
                    deferred=True,
                    input_handoff={
                        "arguments_template": {
                            "intent": f"Construct {subject} from the supplied reference brief",
                            "expected_changes": (
                                "Create or update the brief's named primary masses, secondary forms, and landmarks "
                                "in one coherent proportion system."
                            ),
                            "risk_level": "medium",
                            "target_objects": existing_targets,
                            "code": "<complete_llm_authored_blender_python>",
                        },
                        "resolve_from": [
                            "reference_decomposition.outputs.reference_brief",
                            "inspect_scene results",
                        ],
                        "client_must_replace_placeholders": True,
                        "script_preflight": construction_strategy["script_preflight"],
                    },
                    gateway_ready=True,
                )
            )
        else:
            construction_calls.append(
                _planned_tool_call(
                    "plan_advanced_scene_workflow",
                    {
                        "prompt": prompt or reference_text or f"Build the supplied {subject} reference brief.",
                        "domains": ["procedural_3d"],
                        "target_objects": existing_targets,
                    },
                    reason="Choose bounded construction helpers because trust is off or the user requested helpers.",
                    gateway_ready=True,
                )
            )
    refresh_call = _planned_tool_call(
        "list_scene_objects",
        {"max_objects": 100},
        reason="Refresh scene inventory after construction so downstream calls use actual created object names.",
        gateway_ready=True,
    )
    quality_inspection_call = _planned_tool_call(
        "inspect_modeling_quality",
        {},
        reason="Validate every resolved existing or newly created target before visual scoring.",
        deferred=True,
        input_handoff={
            "arguments_template": {
                "object_names": "<resolved_target_objects>",
                "selected_only": False,
                "include_children": True,
                "require_materials": bool(brief["surface_cues"]),
            },
            "resolve_from": "refresh_targets.target_resolution",
            "block_if_empty": True,
        },
        gateway_ready=True,
    )
    inspection_render_call = _planned_tool_call(
        "capture_object_inspection_renders",
        {},
        reason="Capture stable diagnostic views for every resolved existing or newly created target.",
        deferred=True,
        input_handoff={
            "arguments_template": {
                "object_names": "<resolved_target_objects>",
                "views": brief["inspection_views"],
            },
            "resolve_from": "refresh_targets.target_resolution",
            "block_if_empty": True,
        },
        gateway_ready=True,
    )
    trace_call = _planned_tool_call(
        "start_execution_trace",
        {
            "name": f"Reference model: {subject}",
            "prompt": prompt or reference_text,
            "metadata": {
                "workflow": "plan_model_quality_workflow",
                "subject": subject,
                "quality_floor": floor,
            },
        },
        reason="Create a replayable record of tool calls, generated scripts, evidence, repairs, and token usage.",
        gateway_ready=True,
    )
    trace_call["conditional"] = "invoke only when no execution trace is already active; otherwise reuse the active trace"
    quality_review_start_call = _planned_tool_call(
        "start_model_quality_review",
        {},
        reason="Create durable score and repair state from the reference brief and final matched evidence.",
        deferred=True,
        input_handoff={
            "arguments_template": {
                "reference_brief": brief,
                "target_objects": "<resolved_target_objects>",
                "evidence_uris": "<current_reference_aligned_evidence_uris>",
                "quality_floor": floor,
                "max_repair_passes": 3,
                "trace_id": "<active_trace_id_or_empty>",
                "benchmark_run_id": "<active_benchmark_run_id_or_empty>",
            },
            "resolve_from": [
                "reference_decomposition.outputs.reference_brief",
                "refresh_targets.target_resolution",
                "evidence_score_repair.get_visual_evidence_resources result",
                "active execution trace",
                "active quality benchmark run, when present",
            ],
            "block_if_empty": ["resolved_target_objects", "current_reference_aligned_evidence_uris"],
            "client_must_replace_placeholders": True,
        },
        gateway_ready=True,
    )
    quality_review_packet_call = _planned_tool_call(
        "get_model_quality_review_packet",
        {},
        reason="Request a blind packet so the current evidence is scored without anchoring on prior scores.",
        deferred=True,
        depends_on="start_model_quality_review",
        input_handoff={
            "arguments_template": {
                "review_id": "<start_model_quality_review.review.review_id>",
                "include_prior_scores": False,
            },
            "resolve_from": "start_model_quality_review result",
            "block_if_empty": True,
        },
        gateway_ready=True,
    )
    quality_evaluation_call = _planned_tool_call(
        "submit_model_quality_evaluation",
        {},
        reason="Validate and persist one complete evidence-backed scorecard for every applicable criterion.",
        deferred=True,
        depends_on="get_model_quality_review_packet",
        input_handoff={
            "arguments_template": {
                "review_id": "<model_quality_review_packet.review_id>",
                "scores": "<complete_scores_for_every_applicable_criterion>",
                "evaluator": "<client_and_model_identifier>",
                "evidence_uris": "<current_reference_aligned_evidence_uris>",
                "blind": True,
            },
            "resolve_from": [
                "get_model_quality_review_packet result",
                "actual reference image",
                "current captured evidence",
            ],
            "client_must_replace_placeholders": True,
            "block_if_empty": True,
        },
        gateway_ready=True,
    )
    quality_repair_call = _planned_tool_call(
        "record_model_quality_repair",
        {},
        reason="Record completed repairs and obtain a fresh blind packet before rescoring.",
        deferred=True,
        depends_on="submit_model_quality_evaluation returns repair_required",
        input_handoff={
            "arguments_template": {
                "review_id": "<model_quality_review_id>",
                "repairs": "<completed_repairs_for_failed_criteria>",
                "evidence_uris": "<recaptured_reference_aligned_evidence_uris>",
                "trace_id": "<active_trace_id_or_empty>",
            },
            "resolve_from": [
                "submit_model_quality_evaluation failed_criteria",
                "completed repair script or helper results",
                "recaptured evidence",
            ],
            "client_must_replace_placeholders": True,
            "block_if_empty": True,
        },
        gateway_ready=True,
    )
    semantic_region_definition_call = _planned_tool_call(
        "define_semantic_sculpt_regions",
        {},
        reason=(
            "Convert the visual critique into persistent named mesh regions before "
            "applying a bounded repair."
        ),
        mutates_scene=True,
        requires_live_preview=True,
        deferred=True,
        input_handoff={
            "arguments_template": {
                "object_name": "<one_resolved_target_object>",
                "regions": "<image_derived_region_definitions>",
            },
            "resolve_from": [
                "refresh_targets.target_resolution",
                "calibrated reference guides",
                "the highest-impact form_evidence_gate critique",
            ],
            "client_must_replace_placeholders": True,
            "block_if_empty": True,
        },
        gateway_ready=True,
    )
    semantic_region_definition_call["conditional"] = (
        "invoke only when form evidence identifies a localized shape repair"
    )
    semantic_region_inspection_call = _planned_tool_call(
        "inspect_semantic_sculpt_regions",
        {},
        reason="Verify the named region and its weighted coverage before deformation.",
        deferred=True,
        depends_on="define_semantic_sculpt_regions",
        input_handoff={
            "arguments_template": {
                "object_name": "<one_resolved_target_object>",
                "include_weights": False,
            },
            "resolve_from": "define_semantic_sculpt_regions result",
            "client_must_replace_placeholders": True,
            "block_if_empty": True,
        },
        gateway_ready=True,
    )
    semantic_region_inspection_call["conditional"] = (
        "invoke after defining or updating a semantic region"
    )
    semantic_repair_choices = [
        _planned_tool_call(
            "apply_semantic_sculpt",
            {},
            reason="Apply a measured 3D translate, inflate, smooth, or flatten field.",
            mutates_scene=True,
            requires_live_preview=True,
            deferred=True,
            input_handoff={
                "arguments_template": {
                    "object_name": "<one_resolved_target_object>",
                    "region_names": "<verified_semantic_region_names>",
                    "operation": "<translate_inflate_smooth_or_flatten>",
                    "arguments": "<reference_derived_operation_arguments>",
                },
                "resolve_from": [
                    "inspect_semantic_sculpt_regions result",
                    "the measured 3D repair target",
                ],
                "client_must_replace_placeholders": True,
                "block_if_empty": True,
            },
            gateway_ready=True,
        ),
        _planned_tool_call(
            "apply_form_aware_sculpt",
            {},
            reason=(
                "Apply a topology-aware tangent relax, pinch, or crease while "
                "protecting measured high-curvature form."
            ),
            mutates_scene=True,
            requires_live_preview=True,
            deferred=True,
            input_handoff={
                "arguments_template": {
                    "object_name": "<one_resolved_target_object>",
                    "region_names": "<verified_semantic_region_names>",
                    "operation": "<tangent_relax_pinch_or_crease>",
                    "strength": "<bounded_reference_derived_strength>",
                },
                "resolve_from": [
                    "inspect_semantic_sculpt_regions result",
                    "the measured local form or feature error",
                ],
                "client_must_replace_placeholders": True,
                "block_if_empty": True,
            },
            gateway_ready=True,
        ),
        _planned_tool_call(
            "apply_screen_space_sculpt",
            {},
            reason="Apply one calibrated image-space contour correction in preview.",
            mutates_scene=True,
            requires_live_preview=True,
            deferred=True,
            input_handoff={
                "arguments_template": {
                    "object_name": "<one_resolved_target_object>",
                    "collection_name": "<calibrated_guide_collection>",
                    "camera_name": "<calibrated_reference_camera>",
                    "region_names": "<verified_semantic_region_names>",
                    "controls": "<source_target_screen_controls>",
                },
                "resolve_from": [
                    "inspect_semantic_sculpt_regions result",
                    "calibrated reference guides",
                    "the measured contour error",
                ],
                "client_must_replace_placeholders": True,
                "block_if_empty": True,
            },
            gateway_ready=True,
        ),
        _planned_tool_call(
            "optimize_screen_space_sculpt",
            {},
            reason=(
                "Measure bounded contour strengths and retain only a reference-score "
                "improvement."
            ),
            mutates_scene=True,
            requires_live_preview=True,
            deferred=True,
            input_handoff={
                "arguments_template": {
                    "object_name": "<one_resolved_target_object>",
                    "collection_name": "<calibrated_guide_collection>",
                    "camera_name": "<calibrated_reference_camera>",
                    "region_names": "<verified_semantic_region_names>",
                    "controls": "<source_target_screen_controls>",
                    "strength_candidates": [0.5, 1.0, 1.5],
                },
                "resolve_from": [
                    "inspect_semantic_sculpt_regions result",
                    "calibrated reference guides",
                    "compare_model_to_reference redline and metrics",
                ],
                "client_must_replace_placeholders": True,
                "block_if_empty": True,
            },
            gateway_ready=True,
        ),
    ]
    phases = [
        {
            "name": "execution_trace",
            "tool_calls": [trace_call],
        },
        {
            "name": "reference_decomposition",
            "goal": "Convert the visual request into explicit form, proportion, surface, and must-not-do constraints before building.",
            "status": "complete" if brief_ready else "needs_client_input",
            "outputs": {
                "subject": subject,
                "reference_description": reference_text,
                "reference_brief": brief,
                "missing_required_fields": missing_brief_fields,
                "quality_floor": floor,
            },
            "client_action": (
                "Use the actual reference image to supply silhouette, primary_masses, and proportion_checks, "
                "then call plan_model_quality_workflow again with reference_brief."
                if not brief_ready
                else "Preserve this brief as the comparison contract for every evidence and repair pass."
            ),
        },
        {
            "name": "inspect_scene",
            "tool_calls": inspection_calls,
        },
        {
            "name": "block_major_masses",
            "blocked_until": None if brief_ready else "reference brief is complete",
            "execution_strategy": construction_strategy,
            "tool_calls": construction_calls,
            "calibrated_multiview_path": {
                "selection_rule": (
                    "Use when two or more non-parallel annotated silhouettes are available; "
                    "it supersedes a guessed single-view depth blockout."
                ),
                "sequence": [
                    "prepare_reference_images when ordinary images or masks need normalized guide inputs",
                    "create_multiview_reference_guides",
                    "create_multiview_depth_surface when calibrated depth evidence exists; otherwise create_multiview_visual_hull",
                    "fit_surface_to_multiview_references",
                    "evaluate_multiview_reference_match",
                    "adaptive_remesh",
                    "define_semantic_sculpt_regions",
                    "auto_reference_sculpt_repair or apply_form_aware_sculpt/calibrated screen-space sculpt",
                    "evaluate_multiview_reference_match",
                ],
                "preview_each_mutation": True,
                "fit_acceptance": (
                    "retain only aggregate objective improvements that stay within the configured per-view regression tolerance"
                ),
                "inspect_region_coverage_after_topology": True,
            },
            "script_handoff": {
                "status": (
                    "preferred_pending_client_authored_code"
                    if scripted_construction
                    else "available_if_trust_is_enabled_and_preference_changes"
                ),
                "schema_lookup": {
                    "name": "get_blender_tool_schema",
                    "arguments": {"name": "draft_script"},
                },
                "invoke_with": "invoke_blender_tool",
                "required_arguments": ["intent", "expected_changes", "risk_level", "code"],
                "content_requirements": {
                    "named_parts": list(
                        brief["primary_masses"] + brief["secondary_forms"] + brief["landmarks"]
                    ),
                    "preserve_constraints": list(brief["negative_constraints"]),
                    "requires_session_script_trust": True,
                    "one_cohesive_script": True,
                    "script_preflight": construction_strategy["script_preflight"],
                },
                "long_running_alternative": {
                    "selection_rule": (
                        "Use start_trusted_script_job when the cohesive script is likely to exceed the bridge timeout "
                        "or benefits from isolated background execution."
                    ),
                    "start_tool": "start_trusted_script_job",
                    "status_tool": "get_trusted_script_job_status",
                    "cancel_tool": "cancel_trusted_script_job",
                    "apply_tool": "apply_trusted_script_job_result",
                    "apply_requires_explicit_user_confirmation": True,
                    "live_scene_unchanged_until_apply": True,
                },
            },
        },
        {
            "name": "refresh_targets",
            "blocked_until": "the selected construction path completes",
            "tool_calls": [refresh_call],
            "target_resolution": {
                "baseline_source": "inspect_scene.list_scene_objects result",
                "refresh_source": "this phase list_scene_objects result",
                "seed_with": existing_targets,
                "merge": "object names returned by the construction call",
                "fallback_additions": "new visible model objects present in refresh but absent from baseline",
                "deduplicate": True,
                "output": "resolved_target_objects",
                "must_be_non_empty": True,
                "do_not_rely_on_selection_only": True,
            },
        },
        {
            "name": "form_evidence_gate",
            "blocked_until": "refresh_targets produces non-empty resolved_target_objects",
            "tool_calls": [
                _planned_tool_call(
                    "capture_viewport",
                    {"max_bytes": 900000},
                    reason="Capture the primary comparison view before surface detail can hide form problems.",
                    gateway_ready=True,
                ),
                inspection_render_call,
                _planned_tool_call(
                    "get_visual_evidence_resources",
                    {"include_unavailable": True},
                    reason="Collect form-stage evidence for silhouette and proportion scoring.",
                    gateway_ready=True,
                ),
            ],
            "scorecard": [
                item
                for item in rubric
                if item["criterion"]
                in {
                    "silhouette_match",
                    "proportion_match",
                    "landmark_placement",
                    "form_continuity",
                }
                and item["applies"]
            ],
            "repair_gate": {
                "minimum_score_per_criterion": floor,
                "repair_before_surface_detail": True,
                "max_repair_passes": 3,
                "recapture_after_each_pass": True,
            },
        },
        {
            "name": "semantic_form_repair",
            "blocked_until": (
                "form_evidence_gate identifies a below-floor localized shape error, "
                "resolved targets exist, and calibrated guide inputs are available"
            ),
            "tool_calls": [
                semantic_region_definition_call,
                semantic_region_inspection_call,
            ],
            "choose_one_repair_call": semantic_repair_choices,
            "repair_order": [
                "define or update the smallest meaningful named region",
                "inspect weighted coverage",
                "use joint multi-view fitting for broad cross-view error; otherwise choose exactly one localized 3D field, form-aware brush, direct screen pull, or measured optimizer call",
                "recapture the same evidence and rescore before another repair",
            ],
            "topology_warning": (
                "adaptive_remesh retains interpolated semantic attributes; inspect or redefine regions after any other topology-changing operation."
            ),
        },
        {
            "name": "surface_and_detail_pass",
            "blocked_until": "all applicable form_evidence_gate scores meet the quality floor",
            "execution_order": ["client_actions", "tool_calls"],
            "tool_calls": [quality_inspection_call],
            "client_actions": [
                (
                    "Under active trust, use one cohesive surface/detail script for the supplied surface_cues unless "
                    "the user requested helpers; use exact material helpers only for isolated requested operations."
                ),
                "Do not add hair, fur, fibers, particles, textures, or material families unless the reference brief explicitly requires them.",
                "Apply detail only after silhouette and proportion criteria meet the quality floor.",
            ],
        },
        {
            "name": "evidence_score_repair",
            "blocked_until": "surface_and_detail_pass completes for resolved targets",
            "tool_calls": [
                _planned_tool_call(
                    "capture_viewport",
                    {"max_bytes": 900000},
                    reason="Capture the client-framed primary view for direct reference comparison.",
                    gateway_ready=True,
                ),
                inspection_render_call,
                _planned_tool_call(
                    "get_visual_evidence_resources",
                    {"include_unavailable": True},
                    reason="Collect current evidence resources for scoring and repair decisions.",
                    gateway_ready=True,
                ),
                quality_review_start_call,
                quality_review_packet_call,
                quality_evaluation_call,
            ],
            "scorecard": rubric,
            "repair_gate": {
                "minimum_score_per_criterion": floor,
                "repair_before_commit": True,
                "score_scale": {"minimum": 1, "maximum": 5},
                "required_score_fields": ["criterion", "score", "evidence", "finding", "repair_action"],
                "repair_order": [
                    item["criterion"] for item in rubric if item["applies"]
                ],
                "max_repair_passes": 3,
                "recapture_after_each_pass": True,
                "repair_tool_call": quality_repair_call,
                "after_repair": [
                    "recapture the same evidence views",
                    "invoke record_model_quality_repair",
                    "score the returned fresh blind packet with submit_model_quality_evaluation",
                ],
            },
        },
        {
            "name": "preview_decision",
            "decision_options": [
                {
                    "decision": "commit",
                    "blocked_until": "user explicitly approves the scored preview",
                    "tool_call": _planned_tool_call(
                        "commit_preview",
                        {},
                        reason="Call only after the user approves the scored preview.",
                        mutates_scene=True,
                        gateway_ready=True,
                    ),
                },
                {
                    "decision": "revert",
                    "blocked_until": "user rejects the preview or requests cleanup",
                    "tool_call": _planned_tool_call(
                        "revert_preview",
                        {},
                        reason="Call only after the user chooses Revert or cleanup is required.",
                        mutates_scene=True,
                        gateway_ready=True,
                    ),
                },
            ],
        },
    ]
    next_tool_calls = []
    deferred_tool_calls = []
    for phase in phases:
        for tool_call in phase.get("tool_calls", []):
            queued_call = dict(tool_call)
            queued_call["phase"] = phase["name"]
            if tool_call.get("deferred_until_inputs_resolved") or phase.get("blocked_until"):
                if phase.get("blocked_until"):
                    queued_call["blocked_until"] = phase["blocked_until"]
                deferred_tool_calls.append(queued_call)
            else:
                next_tool_calls.append(queued_call)
    return {
        "ok": True,
        "status": "ready" if brief_ready else "needs_reference_brief",
        "message": (
            "Planned executable reference-driven model quality workflow"
            if brief_ready
            else "Reference brief requires client visual analysis before scene mutation"
        ),
        "label": label,
        "prompt": prompt,
        "subject": subject,
        "requested_target_objects": target_names,
        "target_objects": existing_targets,
        "missing_target_objects": missing_targets,
        "reference_brief": brief,
        "missing_reference_brief_fields": missing_brief_fields,
        "reference_breakdown": breakdown,
        "quality_rubric": rubric,
        "quality_floor": floor,
        "construction_strategy": construction_strategy,
        "phases": phases,
        "next_tool_calls": next_tool_calls,
        "deferred_tool_calls": deferred_tool_calls,
        "gateway_execution": {
            "schema_tool": "get_blender_tool_schema",
            "invoke_tool": "invoke_blender_tool",
            "planner_named_helpers_may_be_absent_from_top_level_tools": True,
            "absence_from_top_level_does_not_mean_unavailable": True,
        },
        "mcp_client_guidance": [
            "Do not stop after receiving this plan when the user asked to build or repair the model.",
            "Follow next_tool_calls in order, using each call's schema_lookup and gateway_call envelopes.",
            (
                "Follow construction_strategy: with active trust, author one cohesive draft_script for each broad "
                "construction or repair pass unless the user requested helpers."
            ),
            (
                "For a long cohesive script, invoke start_trusted_script_job, poll its status, inspect its result, "
                "and apply it only after explicit user approval; this remains the script-first path."
            ),
            (
                "Resolve the deferred construction script after brief and inspection inputs are ready; resolve "
                "target-dependent inspection and evidence calls only after refresh_targets is non-empty."
            ),
            "Use the actual reference image and captured evidence to score every applicable criterion; the planner does not infer visual anatomy or surface treatment.",
            "Use prepare_reference_images before guide creation when the client has images, alpha masks, or mask images but no annotation JSON.",
            "Do not begin surface detail until every applicable form_evidence_gate score meets the quality floor.",
            "Repair scores below the quality floor and recapture evidence, up to the bounded repair-pass limit.",
            (
                "For localized form errors, define and inspect semantic regions, then choose exactly one of "
                "apply_semantic_sculpt, apply_form_aware_sculpt, apply_screen_space_sculpt, optimize_screen_space_sculpt, or auto_reference_sculpt_repair."
            ),
            (
                "For broad silhouette or calibrated depth disagreement across views, use fit_surface_to_multiview_references before localized semantic repair."
            ),
            (
                "Prefer optimize_screen_space_sculpt when calibrated silhouette evidence "
                "is available; it restores the mesh when no candidate improves the score."
            ),
            (
                "Advance the durable model-quality review through start, blind packet, evaluation, repair record, "
                "and re-evaluation until it reports ready_for_user_review or blocked_quality_floor."
            ),
            "Leave the final preview pending until the user explicitly chooses commit or revert.",
        ],
        "completion_contract": {
            "ready_for_mutation": brief_ready,
            "blocking_reference_fields": missing_brief_fields,
            "resolved_target_objects_required": True,
            "form_scores_at_or_above_before_surface_detail": floor,
            "all_applicable_scores_at_or_above": floor,
            "max_repair_passes": 3,
            "report_blocker_if_floor_not_met_after_max_repair_passes": True,
            "reference_aligned_viewport_required": True,
            "inspection_render_required": True,
            "commit_requires_explicit_user_approval": True,
            "must_not_stop_after_planning": True,
            "durable_quality_review_required": True,
            "quality_terminal_statuses": ["ready_for_user_review", "blocked_quality_floor"],
        },
        "script_fallback_policy": {
            "legacy_field_name": True,
            "helper_first": not scripted_construction,
            "script_first": scripted_construction,
            "preferred_role": (
                "primary_authored_construction"
                if scripted_construction
                else "unavailable_or_user_overridden"
            ),
            "allowed_after": "reference decomposition and scene inspection; no helper-gap proof is required",
            "requires_session_script_trust": True,
            "script_preflight": construction_strategy["script_preflight"],
            "named_part_requirements": list(
                brief["primary_masses"] + brief["secondary_forms"] + brief["landmarks"]
            ),
            "must_leave_preview_pending": True,
            "long_running_script_path": {
                "start": "start_trusted_script_job",
                "poll": "get_trusted_script_job_status",
                "apply": "apply_trusted_script_job_result",
                "live_scene_unchanged_until_confirmed_apply": True,
            },
        },
        "token_policy": {
            "keep_gateway_surface": True,
            "fetch_schemas_on_demand": True,
            "spend_tokens_on_reference_breakdown_and_repair_critique": True,
            "do_not_reduce_default_model_quality_outputs": True,
            "execution_trace_uses_compact_results_and_local_script_artifacts": True,
        },
    }


def plan_advanced_scene_workflow(context, *, prompt="", domains=None, target_objects=None, label="Plan advanced scene workflow"):
    matched_domains = _advanced_domain_matches(prompt, domains)
    authored_strategy = _authored_construction_strategy(context, prompt)
    script_first_domains = {"model_quality", "2d_storyboard", "procedural_3d", "advanced_animation"}
    existing_targets = []
    missing_targets = []
    for name in [str(item) for item in target_objects or [] if str(item).strip()]:
        if bpy.data.objects.get(name):
            existing_targets.append(name)
        else:
            missing_targets.append(name)
    steps = []
    inspection_calls = []
    recommended_tools = []
    script_boundaries = []
    scripted_domains = []
    for domain in matched_domains:
        spec = ADVANCED_WORKFLOW_DOMAINS[domain]
        tools = list(spec["tools"])
        scripted_domain = (
            authored_strategy["selection"] == "cohesive_trusted_script"
            and domain in script_first_domains
        )
        if scripted_domain:
            scripted_domains.append(domain)
        recommended_tools.extend(tool for tool in tools if tool not in recommended_tools)
        script_boundaries.append({"domain": domain, "policy": spec["script_boundary"]})
        inspection_name = tools[0]
        inspection_input = {}
        if inspection_name == "plan_model_quality_workflow":
            inspection_input = {"prompt": prompt, "target_objects": existing_targets}
        elif inspection_name == "plan_animation_workflow":
            inspection_input = {"prompt": prompt, "subject_names": existing_targets}
        elif inspection_name == "plan_asset_import_workflow":
            inspection_input = {
                "prompt": prompt,
                "target_object_name": existing_targets[0] if existing_targets else "",
            }
        elif inspection_name in {"get_geometry_nodes_details", "get_simulation_details"}:
            inspection_input = {"object_names": existing_targets}
        inspection_calls.append(
            _planned_tool_call(
                inspection_name,
                inspection_input,
                reason=f"Inspect or plan the {domain.replace('_', ' ')} domain before mutation.",
                gateway_ready=True,
            )
        )
        steps.append(
            {
                "domain": domain,
                "inspect_first": tools[0],
                "helper_path": tools[1:],
                "execution_path": "cohesive_trusted_script" if scripted_domain else "bounded_helpers",
                "script_handoff": spec["script_boundary"],
            }
        )
    next_tool_calls = list(inspection_calls)
    if scripted_domains:
        next_tool_calls.append(
            _planned_tool_call(
                "draft_script",
                {},
                reason="Author and run one cohesive checkpoint-backed script across the resolved authored domains.",
                mutates_scene=True,
                deferred=True,
                depends_on="inspection_calls",
                input_handoff={
                    "arguments_template": {
                        "intent": prompt or "Author the planned Blender scene changes",
                        "expected_changes": (
                            "Create or update the requested authored scene, modeling, material, node, rig, "
                            "camera, and animation work as one coherent pass."
                        ),
                        "risk_level": "medium",
                        "target_objects": existing_targets,
                        "code": "<complete_llm_authored_blender_python>",
                    },
                    "resolve_from": [
                        "steps[].inspect_first",
                        "target_objects",
                        "missing_target_objects",
                    ],
                    "client_must_replace_placeholders": True,
                    "completion_gate": {
                        "require_planner_status": ["ready", "ready_for_review"],
                        "block_on_status": [
                            "needs_clarification",
                            "needs_reference_brief",
                            "blocked",
                            "blocked_by_scene_context",
                            "selection_required",
                        ],
                        "require_resolved_targets_when_editing_existing_objects": True,
                    },
                    "script_preflight": authored_strategy["script_preflight"],
                },
                gateway_ready=True,
            )
        )
    return {
        "ok": True,
        "message": f"Planned advanced workflow across {len(matched_domains)} domain(s)",
        "domains": matched_domains,
        "target_objects": existing_targets,
        "missing_target_objects": missing_targets,
        "recommended_tools": recommended_tools,
        "steps": steps,
        "next_tool_calls": next_tool_calls,
        "scripted_domains": scripted_domains,
        "execution_strategy": authored_strategy,
        "script_fallback_policy": {
            "legacy_field_name": True,
            "helper_first": authored_strategy["selection"] != "cohesive_trusted_script",
            "script_first_for_authored_domains": authored_strategy["selection"] == "cohesive_trusted_script",
            "requires_explicit_helper_gap": False,
            "search_docs_before_unfamiliar_python": True,
            "script_preflight": authored_strategy["script_preflight"],
            "domain_boundaries": script_boundaries,
        },
        "mcp_client_guidance": [
            "Execute next_tool_calls in order through schema lookup and gateway invocation.",
            "Replace the draft_script code placeholder with one complete Blender Python program derived from the inspection results.",
            "Do not invoke the deferred script while any nested planner reports missing input, unresolved selection, or a blocked status.",
            "Use each step's helper_path only when trust is off, helpers were requested, or an exact isolated helper is intentionally chosen.",
            "Keep inspection, external assets, long jobs, evidence, and preview decisions on bounded helpers.",
        ],
        "label": label,
    }


def _planned_tool_call(
    name,
    arguments=None,
    *,
    reason="",
    mutates_scene=False,
    requires_live_preview=False,
    deferred=False,
    depends_on=None,
    input_handoff=None,
    gateway_ready=False,
):
    call = {
        "name": str(name or ""),
        "input": dict(arguments or {}),
        "reason": str(reason or ""),
        "mutates_scene": bool(mutates_scene),
        "requires_live_preview": bool(requires_live_preview),
    }
    if deferred:
        call["deferred_until_inputs_resolved"] = True
    if depends_on:
        call["depends_on"] = str(depends_on)
    if input_handoff:
        call["input_handoff"] = dict(input_handoff)
    if gateway_ready:
        call["schema_lookup"] = {
            "name": "get_blender_tool_schema",
            "arguments": {"name": call["name"]},
        }
        if deferred:
            arguments_template = dict((input_handoff or {}).get("arguments_template") or {})
            call["gateway_call_template"] = {
                "name": "invoke_blender_tool",
                "arguments": {"name": call["name"], "arguments": arguments_template},
            }
        else:
            call["gateway_call"] = {
                "name": "invoke_blender_tool",
                "arguments": {"name": call["name"], "arguments": dict(call["input"])},
            }
    return call


def _infer_asset_provider(prompt, provider=""):
    requested = str(provider or "").strip().lower().replace("-", "_").replace(" ", "_")
    if requested in {"poly_haven", "sketchfab"}:
        return requested
    text = str(prompt or "").lower()
    if "sketchfab" in text:
        return "sketchfab"
    return "poly_haven" if any(term in text for term in ("poly haven", "polyhaven", "hdri", "texture", "environment map")) else ""


def plan_asset_import_workflow(
    context,
    *,
    prompt="",
    provider="",
    asset_id="",
    uid="",
    target_object_name="",
    presentation_preset="studio",
    label="Plan asset import workflow",
):
    """Plan the async external-asset path plus post-import presentation helpers."""

    prompt = str(prompt or "").strip()
    provider_key = _infer_asset_provider(prompt, provider)
    asset_id_text = str(asset_id or "").strip()
    uid_text = str(uid or "").strip()
    target_name = str(target_object_name or "").strip()
    target_exists = bool(target_name and bpy.data.objects.get(target_name))
    discovery_tools = []
    if provider_key == "sketchfab":
        discovery_tools.append(
            _planned_tool_call(
                "search_sketchfab_models",
                {"query": prompt[:200]},
                reason="Discover a Sketchfab model before starting a cached download job.",
            )
        )
    elif provider_key == "poly_haven":
        discovery_tools.extend(
            [
                _planned_tool_call("list_poly_haven_categories", {}, reason="Inspect Poly Haven categories before choosing an asset type."),
                _planned_tool_call(
                    "search_poly_haven_assets",
                    {"query": prompt[:200], "asset_type": "all"},
                    reason="Find a Poly Haven asset id for the requested import.",
                ),
            ]
        )
        if asset_id_text:
            discovery_tools.append(
                _planned_tool_call(
                    "inspect_poly_haven_asset_files",
                    {"asset_id": asset_id_text},
                    reason="Choose resolution and file formats before downloading.",
                )
            )
    else:
        discovery_tools.extend(
            [
                _planned_tool_call("search_poly_haven_assets", {"query": prompt[:200], "asset_type": "all"}, reason="Search Poly Haven when no provider is specified."),
                _planned_tool_call("search_sketchfab_models", {"query": prompt[:200]}, reason="Search Sketchfab when no provider is specified."),
            ]
        )

    provider_selection_required = not bool(provider_key)
    asset_selection_required = (provider_key == "poly_haven" and not asset_id_text) or (provider_key == "sketchfab" and not uid_text)
    selection_required = provider_selection_required or asset_selection_required
    if provider_selection_required:
        selection_fields = ["provider", "asset_id or uid"]
        selection_message = "Choose one discovered provider result before starting download/cache."
        selection_blocker = "provider and asset_id/uid are selected from discovery results"
    elif provider_key == "poly_haven":
        selection_fields = ["asset_id"]
        selection_message = "Choose a concrete Poly Haven asset_id before starting download/cache."
        selection_blocker = "Poly Haven asset_id is selected from discovery results"
    else:
        selection_fields = ["uid"]
        selection_message = "Choose a concrete Sketchfab uid before starting download/cache."
        selection_blocker = "Sketchfab uid is selected from discovery results"
    download_args = {
        "provider": provider_key,
        "asset_id": asset_id_text,
        "uid": uid_text,
    }
    import_args = {"source_job_id": "<asset_job_id>", "target_object_name": target_name}
    preset_key = presentation_support.infer_presentation_preset(prompt, presentation_preset)
    post_import_target = target_name or "<imported_object_name>"
    presentation = [
        _planned_tool_call(
            "prepare_imported_asset_presentation",
            {
                "imported_object_names": ["<imported_object_name>"],
                "target_object_name": post_import_target,
                "collection_prefix": "Agent Bridge Imported Asset",
                "presentation_preset": preset_key,
                "assign_material_if_missing": True,
                "create_stage": True,
                "create_turntable": preset_key == "turntable",
                "use_active_fallback": False,
            },
            reason="Organize imported objects, fill missing materials, and create a bounded presentation setup in preview.",
            mutates_scene=True,
            requires_live_preview=True,
        ),
        _planned_tool_call(
            "capture_viewport",
            {"max_bytes": 900000},
            reason="Capture visual evidence after import and staging.",
        ),
    ]
    phases = [{"name": "discover", "tool_calls": discovery_tools}]
    if selection_required:
        phases.append(
            {
                "name": "select_asset",
                "tool_calls": [],
                "requires_user_or_client_selection": True,
                "selection_fields": selection_fields,
                "message": selection_message,
            }
        )
        phases.extend(
            [
                {
                    "name": "download",
                    "tool_calls": [],
                    "blocked_until": selection_blocker,
                },
                {
                    "name": "import",
                    "tool_calls": [],
                    "blocked_until": "asset download/cache job completes",
                },
                {
                    "name": "present",
                    "tool_calls": [],
                    "blocked_until": "asset import completes and imported object name is known",
                },
            ]
        )
    else:
        phases.extend(
            [
                {
                    "name": "download",
                    "tool_calls": [
                        _planned_tool_call(
                            "start_external_asset_download",
                            download_args,
                            reason="Start the async download/cache job. Do not use synchronous fallback paths for normal workflows.",
                        ),
                        _planned_tool_call(
                            "get_external_asset_job_status",
                            {"job_id": "<asset_job_id>"},
                            reason="Poll until the cached manifest is completed or failed.",
                        ),
                    ],
                },
                {
                    "name": "import",
                    "tool_calls": [
                        _planned_tool_call(
                            "start_external_asset_import_job",
                            import_args,
                            reason="Queue Blender main-thread import after the cache job completes.",
                        ),
                        _planned_tool_call(
                            "get_external_asset_import_job_status",
                            {"job_id": "<asset_import_job_id>"},
                            reason="Poll until import completes before claiming scene changes.",
                        ),
                    ],
                },
                {"name": "present", "tool_calls": presentation},
            ]
        )

    return {
        "ok": True,
        "message": "Planned async external asset import and presentation workflow",
        "label": label,
        "provider": provider_key,
        "provider_selection_required": provider_selection_required,
        "asset_selection_required": asset_selection_required,
        "selection_required": selection_required,
        "target_object_name": target_name,
        "target_exists": target_exists,
        "phases": phases,
        "script_fallback_policy": {
            "helper_first": True,
            "normal_path": [
                "discover provider asset",
                "select provider and asset id/uid",
                "start_external_asset_download",
                "get_external_asset_job_status",
                "start_external_asset_import_job",
                "get_external_asset_import_job_status",
                "prepare_imported_asset_presentation",
            ],
            "synchronous_fallbacks_debug_only": ["download_poly_haven_asset", "import_poly_haven_asset", "download_sketchfab_model", "import_sketchfab_model", "import_external_asset_job_result"],
            "custom_asset_scripts": "Prefer bounded asset jobs; if a real helper gap remains, draft_script may use filesystem or network Python under active session trust.",
        },
    }


def plan_director_workflow(
    context,
    *,
    prompt="",
    target_objects=None,
    deliverables=None,
    label="Plan director workflow",
):
    """Read-only director plan that composes authored scripts and operational helpers."""

    prompt = str(prompt or "").strip()
    target_names = [str(item) for item in (target_objects or []) if str(item).strip()]
    deliverable_names = [str(item) for item in (deliverables or []) if str(item).strip()]
    asset_requested = helper_routing.contains_any_guard_term(
        prompt,
        {
            "asset catalog",
            "asset import",
            "asset library",
            "download asset",
            "download model",
            "environment map",
            "external asset",
            "hdri",
            "import an asset",
            "import asset",
            "import model",
            "poly haven",
            "polyhaven",
            "sketchfab",
            "texture library",
        },
    )
    domains = _advanced_domain_matches(prompt)
    authored_strategy = _authored_construction_strategy(context, prompt)
    if asset_requested and "asset_import" not in domains:
        domains.append("asset_import")
    if (
        helper_routing.is_authored_animation_request(prompt)
        and "advanced_animation" not in domains
    ):
        domains.append("advanced_animation")
    scripted_domains = [
        domain
        for domain in domains
        if domain in {"model_quality", "2d_storyboard", "procedural_3d", "advanced_animation"}
    ]
    scripted_authoring = bool(
        scripted_domains
        and authored_strategy["selection"] == "cohesive_trusted_script"
    )

    inspect_calls = [
        _planned_tool_call(
            "list_scene_objects",
            {"max_objects": 80},
            reason="Establish the current scene contents before planning edits.",
            gateway_ready=True,
        ),
        _planned_tool_call(
            "get_blend_file_diagnostics",
            {},
            reason="Check file/checkpoint/missing-data state before broad work.",
            gateway_ready=True,
        ),
    ]
    if not scripted_authoring:
        inspect_calls.append(
            _planned_tool_call(
                "plan_advanced_scene_workflow",
                {
                    "prompt": prompt,
                    "domains": [domain for domain in domains if domain != "asset_import"],
                    "target_objects": target_names,
                },
                reason="Resolve bounded operational and helper paths while trusted authored scripting is unavailable.",
                gateway_ready=True,
            )
        )
    phases = [{"name": "inspect", "tool_calls": inspect_calls}]

    if asset_requested:
        phases.append(
            {
                "name": "asset_import",
                "tool_calls": [
                    _planned_tool_call(
                        "plan_asset_import_workflow",
                        {"prompt": prompt, "target_object_name": target_names[0] if target_names else ""},
                        reason="Plan async asset discovery, cache, import, and post-import presentation.",
                        gateway_ready=True,
                    )
                ],
            }
        )

    if "model_quality" in domains:
        phases.append(
            {
                "name": "reference_modeling_plan",
                "tool_calls": [
                    _planned_tool_call(
                        "plan_model_quality_workflow",
                        {"prompt": prompt, "target_objects": target_names},
                        reason="Resolve the reference brief, quality rubric, evidence views, and repair gates.",
                        gateway_ready=True,
                    )
                ],
            }
        )

    if "2d_storyboard" in domains:
        phases.append(
            {
                "name": "storyboard_inspection",
                "tool_calls": [
                    _planned_tool_call(
                        "get_2d_animation_details",
                        {},
                        reason="Inspect existing 2D, storyboard, text, curve, and camera state before authored construction.",
                        gateway_ready=True,
                    )
                ],
            }
        )

    if "procedural_3d" in domains:
        phases.append(
            {
                "name": "model",
                "tool_calls": [
                    _planned_tool_call(
                        "get_geometry_nodes_details",
                        {"object_names": target_names},
                        reason="Inspect existing Geometry Nodes state before choosing composable modeling operations.",
                        gateway_ready=True,
                    ),
                    _planned_tool_call(
                        "inspect_modeling_quality",
                        {"object_names": target_names, "selected_only": not bool(target_names)},
                        reason="Establish the current modeling-quality baseline before helpers or trusted custom scripts mutate it.",
                        gateway_ready=True,
                    ),
                ],
            }
        )

    if "advanced_animation" in domains:
        animation_calls = [
            _planned_tool_call(
                "plan_animation_workflow",
                {"prompt": prompt, "subject_names": target_names},
                reason="Create the animation brief, scene routing, and timing chart.",
                gateway_ready=True,
            )
        ]
        if not scripted_authoring:
            animation_calls.append(
                _planned_tool_call(
                    "run_animation_workflow",
                    {"prompt": prompt, "subject_names": target_names, "capture_playblast": True, "apply_repairs": True},
                    reason="Run helper-backed generation, visual review, and bounded repair because scripts are unavailable or helpers were requested.",
                    mutates_scene=True,
                    requires_live_preview=True,
                    gateway_ready=True,
                )
            )
        phases.append(
            {
                "name": "animate_review_repair",
                "tool_calls": animation_calls,
            }
        )

    if scripted_authoring:
        phases.append(
            {
                "name": "scripted_authoring",
                "tool_calls": [
                    _planned_tool_call(
                        "list_scene_objects",
                        {"max_objects": 100},
                        reason="Refresh actual target names after any asset or planning phase before authored mutation.",
                        gateway_ready=True,
                    ),
                    _planned_tool_call(
                        "draft_script",
                        {},
                        reason="Author and run one cohesive checkpoint-backed script for the director's authored scene pass.",
                        mutates_scene=True,
                        deferred=True,
                        depends_on="inspect, asset_import, model, and animation planning as applicable",
                        input_handoff={
                            "arguments_template": {
                                "intent": prompt or "Author the planned Blender scene",
                                "expected_changes": (
                                    "Create or update the requested objects, materials, nodes, rigging, lights, "
                                    "camera motion, and animation as one coherent pass."
                                ),
                                "risk_level": "medium",
                                "target_objects": target_names,
                                "code": "<complete_llm_authored_blender_python>",
                            },
                            "resolve_from": [
                                "inspect",
                                "asset_import results when present",
                                "model inspection",
                                "plan_animation_workflow",
                                "scripted_authoring target refresh",
                            ],
                            "client_must_replace_placeholders": True,
                            "completion_gate": {
                                "require_asset_selection_and_import_when_requested": asset_requested,
                                "require_planner_status": ["ready", "ready_for_review"],
                                "block_on_status": [
                                    "needs_clarification",
                                    "needs_reference_brief",
                                    "blocked",
                                    "blocked_by_scene_context",
                                    "selection_required",
                                ],
                                "require_target_refresh": True,
                            },
                            "script_preflight": authored_strategy["script_preflight"],
                        },
                        gateway_ready=True,
                    ),
                ],
            }
        )

    preview_decision_options = [
        {
            "decision": "commit",
            "blocked_until": "user explicitly approves the pending preview",
            "tool_call": _planned_tool_call(
                "commit_preview",
                {},
                reason="Call only after the user explicitly approves the preview.",
                mutates_scene=True,
                gateway_ready=True,
            ),
        },
        {
            "decision": "revert",
            "blocked_until": "user explicitly reverts the pending preview or a smoke test must clean up",
            "tool_call": _planned_tool_call(
                "revert_preview",
                {},
                reason="Call only after the user chooses Revert or a smoke test cleans up.",
                mutates_scene=True,
                gateway_ready=True,
            ),
        },
    ]
    phases.append(
        {
            "name": "evidence_and_decision",
            "tool_calls": [
                _planned_tool_call(
                    "capture_viewport",
                    {"max_bytes": 900000},
                    reason="Capture final viewport evidence for the user.",
                    gateway_ready=True,
                ),
                _planned_tool_call(
                    "get_visual_evidence_resources",
                    {"include_unavailable": True},
                    reason="Report latest viewport, playblast, render, and inspection artifacts.",
                    gateway_ready=True,
                ),
            ],
            "decision_options": preview_decision_options,
        }
    )

    flat_calls = []
    for phase in phases:
        flat_calls.extend(phase.get("tool_calls") or [])
    return {
        "ok": True,
        "message": f"Planned director workflow across {len(phases)} phase(s)",
        "label": label,
        "prompt": prompt,
        "domains": domains,
        "scripted_domains": scripted_domains,
        "target_objects": target_names,
        "deliverables": deliverable_names or ["preview", "visual evidence", "commit/revert decision"],
        "execution_strategy": authored_strategy,
        "phases": phases,
        "next_tool_calls": flat_calls,
        "preview_decision_options": preview_decision_options,
        "preview_policy": {
            "leave_pending": True,
            "commit_only_on_user_request": True,
            "revert_after_smoke": True,
        },
        "mcp_client_guidance": [
            "Execute operational asset, inspection, and planning calls first.",
            "When scripted_authoring is present, replace its code placeholder and invoke draft_script before evidence capture.",
            "Honor the deferred call's completion_gate; do not script against unresolved asset choices, missing briefs, or blocked animation context.",
            "Use run_animation_workflow only on the bounded-helper path selected when trust is off or helpers were requested.",
            "Leave the resulting preview pending for the user's explicit commit or revert decision.",
        ],
        "script_fallback_policy": {
            "legacy_field_name": True,
            "helper_first": authored_strategy["selection"] != "cohesive_trusted_script",
            "script_first_for_authored_mutation": authored_strategy["selection"] == "cohesive_trusted_script",
            "draft_script_allowed_after_inspection_when_session_trusted": True,
            "trusted_script_authorization_model": script_execution.AUTHORIZATION_MODEL,
            "privileged_generated_scripts_allowed_when_session_trusted": True,
            "persistent_bake_scripts_allowed_when_session_trusted": True,
            "script_preflight": authored_strategy["script_preflight"],
        },
    }
