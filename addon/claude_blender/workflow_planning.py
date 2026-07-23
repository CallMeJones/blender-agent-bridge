"""Read-only helper-first planning for advanced Blender workflows."""

from __future__ import annotations

import bpy

from . import presentation_support, script_execution


ADVANCED_WORKFLOW_DOMAINS = {
    "2d_storyboard": {
        "keywords": {"2d", "two dimensional", "storyboard", "animatic", "storyboard panel", "storyboard panels", "2d panel", "2d panels", "grease pencil", "grease-pencil", "cutout", "cut-out", "motion graphic"},
        "tools": [
            "get_2d_animation_details",
            "create_text_object",
            "create_curve_path",
            "create_camera_dolly_animation",
            "capture_animation_playblast",
        ],
        "script_boundary": "Use composable text, curve, camera, and evidence helpers when they fit; under active session trust draft_script can handle custom Grease Pencil stroke editing, SVG conversion, or bespoke vector workflows.",
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
        "script_boundary": "Use draft_script for custom node graphs or destructive mesh operators after inspection and Blender API lookup.",
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
        "script_boundary": "Prefer workflow helpers for common blocking/review/repair; under active session trust draft_script can handle custom advanced animation, rig, or driver code.",
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
        if any(keyword in text for keyword in spec["keywords"]):
            matches.append(domain)
    return matches or ["advanced_animation" if "animate" in text or "animation" in text else "procedural_3d"]


def plan_advanced_scene_workflow(context, *, prompt="", domains=None, target_objects=None, label="Plan advanced scene workflow"):
    matched_domains = _advanced_domain_matches(prompt, domains)
    existing_targets = []
    missing_targets = []
    for name in [str(item) for item in target_objects or [] if str(item).strip()]:
        if bpy.data.objects.get(name):
            existing_targets.append(name)
        else:
            missing_targets.append(name)
    steps = []
    recommended_tools = []
    script_boundaries = []
    for domain in matched_domains:
        spec = ADVANCED_WORKFLOW_DOMAINS[domain]
        tools = list(spec["tools"])
        recommended_tools.extend(tool for tool in tools if tool not in recommended_tools)
        script_boundaries.append({"domain": domain, "policy": spec["script_boundary"]})
        steps.append(
            {
                "domain": domain,
                "inspect_first": tools[0],
                "helper_path": tools[1:],
                "script_fallback": spec["script_boundary"],
            }
        )
    return {
        "ok": True,
        "message": f"Planned advanced workflow across {len(matched_domains)} domain(s)",
        "domains": matched_domains,
        "target_objects": existing_targets,
        "missing_target_objects": missing_targets,
        "recommended_tools": recommended_tools,
        "steps": steps,
        "script_fallback_policy": {
            "helper_first": True,
            "requires_explicit_helper_gap": True,
            "search_docs_before_unfamiliar_python": True,
            "domain_boundaries": script_boundaries,
        },
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
    return call


def _prompt_has_any(prompt, terms):
    text = str(prompt or "").lower()
    return any(term in text for term in terms)


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
    """Read-only director plan that composes existing helper-first workflows."""

    prompt = str(prompt or "").strip()
    target_names = [str(item) for item in (target_objects or []) if str(item).strip()]
    deliverable_names = [str(item) for item in (deliverables or []) if str(item).strip()]
    asset_requested = _prompt_has_any(prompt, {"asset", "assets", "poly haven", "polyhaven", "sketchfab", "download", "import model", "import asset", "hdri", "texture"})
    domains = _advanced_domain_matches(prompt)
    if asset_requested and "asset_import" not in domains:
        domains.append("asset_import")
    if _prompt_has_any(prompt, {"director", "shot", "review", "playblast", "evidence"}) and "advanced_animation" not in domains:
        domains.append("advanced_animation")

    phases = [
        {
            "name": "inspect",
            "tool_calls": [
                _planned_tool_call("list_scene_objects", {"max_objects": 80}, reason="Establish the current scene contents before planning edits."),
                _planned_tool_call("get_blend_file_diagnostics", {}, reason="Check file/checkpoint/missing-data state before broad work."),
                _planned_tool_call(
                    "plan_advanced_scene_workflow",
                    {"prompt": prompt, "domains": [domain for domain in domains if domain != "asset_import"], "target_objects": target_names},
                    reason="Resolve helper-first domain paths and script boundaries.",
                ),
            ],
        }
    ]

    if asset_requested:
        phases.append(
            {
                "name": "asset_import",
                "tool_calls": [
                    _planned_tool_call(
                        "plan_asset_import_workflow",
                        {"prompt": prompt, "target_object_name": target_names[0] if target_names else ""},
                        reason="Plan async asset discovery, cache, import, and post-import presentation.",
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
                    ),
                    _planned_tool_call(
                        "inspect_modeling_quality",
                        {"object_names": target_names, "selected_only": not bool(target_names)},
                        reason="Establish the current modeling-quality baseline before helpers or trusted custom scripts mutate it.",
                    ),
                ],
            }
        )

    if "advanced_animation" in domains:
        phases.append(
            {
                "name": "animate_review_repair",
                "tool_calls": [
                    _planned_tool_call("plan_animation_workflow", {"prompt": prompt, "subject_names": target_names}, reason="Create the animation brief, scene routing, and timing chart."),
                    _planned_tool_call(
                        "run_animation_workflow",
                        {"prompt": prompt, "subject_names": target_names, "capture_playblast": True, "apply_repairs": True},
                        reason="Run helper-backed generation, visual review, and bounded repair when helpers fit.",
                        mutates_scene=True,
                        requires_live_preview=True,
                    ),
                ],
            }
        )

    preview_decision_options = [
        {
            "decision": "commit",
            "blocked_until": "user explicitly approves the pending preview",
            "tool_call": _planned_tool_call("commit_preview", {}, reason="Call only after the user explicitly approves the preview.", mutates_scene=True),
        },
        {
            "decision": "revert",
            "blocked_until": "user explicitly reverts the pending preview or a smoke test must clean up",
            "tool_call": _planned_tool_call("revert_preview", {}, reason="Call only after the user chooses Revert or a smoke test cleans up.", mutates_scene=True),
        },
    ]
    phases.append(
        {
            "name": "evidence_and_decision",
            "tool_calls": [
                _planned_tool_call("capture_viewport", {"max_bytes": 900000}, reason="Capture final viewport evidence for the user."),
                _planned_tool_call("get_visual_evidence_resources", {"include_unavailable": True}, reason="Report latest viewport, playblast, render, and inspection artifacts."),
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
        "target_objects": target_names,
        "deliverables": deliverable_names or ["preview", "visual evidence", "commit/revert decision"],
        "phases": phases,
        "next_tool_calls": flat_calls,
        "preview_decision_options": preview_decision_options,
        "preview_policy": {
            "leave_pending": True,
            "commit_only_on_user_request": True,
            "revert_after_smoke": True,
        },
        "script_fallback_policy": {
            "helper_first": True,
            "draft_script_allowed_after_helper_gap_when_session_trusted": True,
            "trusted_script_authorization_model": script_execution.AUTHORIZATION_MODEL,
            "privileged_generated_scripts_allowed_when_session_trusted": True,
            "persistent_bake_scripts_allowed_when_session_trusted": True,
        },
    }
