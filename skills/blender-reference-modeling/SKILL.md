---
name: blender-reference-modeling
description: Build, compare, review, or repair a Blender model against an actual supplied image, photograph, concept, or visual reference using adaptive decomposition, measurable proportions, evidence scoring, and bounded repair. Use only when the request explicitly concerns model creation or quality against visual form criteria; do not trigger for animation-only requests, a generic character mention, or the bare word reference.
---

# Blender Reference Modeling

Use the supplied image as the comparison source. The skill defines process and quality gates, not geometry recipes.

Apply the five-tool Blender Bridge contract. If it is not already active, read [../blender-bridge/references/gateway.md](../blender-bridge/references/gateway.md).

For image-to-form work, create measurable guide scaffolding before sculpting. Read [references/guide-first-workflow.md](references/guide-first-workflow.md) whenever the task includes an image reference, clicked/annotated landmarks, organic sculpting, or fur/hair/groom direction.

When front, side, top, or other calibrated reference views are available, reconstruct shared landmark names with `create_multiview_reference_guides`. Preserve per-view collections and cameras, inspect residuals and ray angles, and repair annotations or calibration when reconstruction confidence is low. When at least two non-parallel views also contain closed silhouettes, use `create_multiview_depth_surface` if explicitly calibrated depth exists and `create_multiview_visual_hull` otherwise. Run `fit_surface_to_multiview_references` before adaptive remeshing or localized repair so broad silhouette, depth, and landmark disagreement is solved jointly. Do not replace this evidence-backed path with guessed hidden depth.

## Non-Negotiable Contract

For every live reference-modeling build, comparison, review, or repair:

1. Discover `plan_model_quality_workflow` through compact gateway search.
2. Fetch its current schema.
3. Invoke it with the image-derived `reference_brief`.
4. Follow its executable and deferred calls through evidence and repair.
5. Advance its durable quality review to `ready_for_user_review` or `blocked_quality_floor`.

Do not substitute a standalone modeling recipe or `plan_advanced_scene_workflow` for this required entry point. The advanced planner may appear inside the returned workflow.

For a planning-only handoff, emit this gateway-ready sequence and its blockers rather than an unactionable artistic brief.

Passing the quality gates means `ready_for_user_review`, not committed or saved. Never call or instruct `commit_preview`, `revert_preview`, or a save operation as an automatic terminal step.

## Build From Observations

1. Analyze the actual reference before scene mutation.
2. Write a structured `reference_brief`.
3. Inspect scene objects and file diagnostics.
4. Create or inspect reference guide scaffolding when the source is visual and guide inputs are available.
5. Fetch and invoke `plan_model_quality_workflow`.
6. Follow its `next_tool_calls` and resolve deferred calls only when their blockers clear.
7. Build primary masses and silhouette before surface detail. Prefer a persistent implicit shape program for novel continuous forms the semantic SDF vocabulary can express; use calibrated depth fusion when measured depth exists and a visual hull otherwise, then run joint multi-view fitting.
8. Refresh scene objects and resolve the union of existing targets, construction-returned names, and new scene-diff objects.
9. Pass resolved names into every later inspection, surface, and evidence call.
10. Start durable scoring only after current target names and matched evidence URIs are available.

Read [references/reference-brief.md](references/reference-brief.md) before invoking the planner.

Do not use canned category bases, category-specific builders, memorized anatomy, or geometry recipes. Do not invent forms hidden by the source. For continuous masses, cavities, attachments, and tapered paths, prefer `compile_shape_program`; inspect its stored graph and revise named nodes with `update_shape_program`. Use a cohesive reference-derived script only when the required geometry falls outside that bounded vocabulary and script trust is active. Use bounded helpers for inspection, evidence, operational work, and deliberately isolated edits.

Reference requests commonly mix construction with evidence, rendering, or saving. Keep those operational calls separate without allowing them to replace the reference-derived construction or repair path.

Do not invent focal lengths, numeric tolerances, material parameters, anatomy, dimensions, or symmetry. Preserve ambiguous measurements as ambiguity unless the image or user resolves them. Label values as supplied, measured, derived, or uncertain.

Use `create_reference_guides_from_annotations` when a reference image and landmark/outline JSON are available; let it normalize the annotation coordinate system, create the image plane and orthographic comparison camera, and persist calibration metadata. Use `create_reference_modeling_guides` only for already-normalized or manually assembled guide inputs. Use `inspect_reference_modeling_guides` before authored construction or repair scripts so scripts receive exact guide names, world points, calibration, and the saved `reference_brief` seed instead of re-parsing the scene.

Use `compile_shape_program` for primary continuous construction when the reference can be decomposed into semantic primitives and tapered sweeps. Start with uniform meshing at low resolution, leave margin in explicit object-local program bounds, use `sample_shape_program_sdf` when a boolean or cavity is uncertain, and keep the result in preview. After broad proportions stabilize, switch to `meshing_mode: adaptive_dual`; keep `adaptive_base_depth` modest and use explicit sphere/box `refinement_regions` around measured high-salience features and form transitions instead of raising depth globally. Inspect `refinement_region_stats` to confirm each region touched the surface. Before further refinement, call `inspect_shape_program(include_program=true)` and revise exact named nodes rather than replacing the mesh blindly. Use `create_reference_blockout` only when direct guide-ellipse conversion is the better scaffold.

Use `fit_surface_to_multiview_references` for broad errors visible across calibrated views. For localized form repair, use `define_semantic_sculpt_regions` to convert image-space polygons, reference landmarks, spatial bounds, or explicit indices into persistent named mesh regions. Inspect coverage with `inspect_semantic_sculpt_regions`, then choose exactly one repair path: `apply_semantic_sculpt` for a measured 3D field, `apply_form_aware_sculpt` for tangent relax, pinch, or crease, `apply_screen_space_sculpt` for a known calibrated contour pull, or `optimize_screen_space_sculpt` to retain only a measured silhouette/landmark improvement. Recapture the same evidence before another repair. `adaptive_remesh` retains interpolated semantic attributes, but inspect coverage after it; inspect or redefine regions after other topology-changing operations. Delete obsolete regions with `write_mode: delete` so persistent attributes do not accumulate.

After each broad form or repair pass, invoke `compare_model_to_reference` through the calibrated guide camera. Use its redline image, silhouette overlap, edge-distance metrics, named error regions, and optional landmark vectors to choose the next repair. At declared blockout, refined, and review checkpoints, invoke `evaluate_reference_model_benchmark` with the corresponding versioned profile. Custom threshold overrides are diagnostic and must not be used to certify a benchmark run. The durable blind review remains the final completion gate.

## Gate Form Before Surface

Capture evidence from:

- a viewport framed to match the reference, including its three-quarter angle when applicable;
- stable front and side/profile inspection views;
- additional supported views only when they reveal a declared criterion;
- modeling and material inspectors where structural evidence matters.

Score silhouette, proportions, landmark placement, and form continuity before adding surface treatment. Require every applicable form criterion to meet the planner's quality floor.

Read [references/evidence-review.md](references/evidence-review.md) before scoring.

For fur, hair, fibers, whiskers, or plush surface flow, place coarse forms first, then use `create_directional_fur_curves` as a preview-safe groom scaffold only after silhouette and proportions are acceptable. Prefer named regions with vertex-group density masks, local flow controls, automatic spacing, restrained clumping/noise, and root-to-tip taper. Directional curves are guide/detail evidence, not a substitute for mass correction.

## Repair Weakest Criteria

Repair criteria below the quality floor in impact order. Recapture the same evidence after each pass. Use at most the planner's bounded repair limit, and report a blocker rather than declaring success when a criterion remains below the floor.

Read [references/repair-loop.md](references/repair-loop.md) when any score misses the floor.

Add materials, textures, hair, fibers, particles, or finish only when explicit `surface_cues` support them. Surface detail must not conceal unresolved form errors.

## Finish In Preview

Capture final reference-aligned evidence, invoke `start_model_quality_review`, request a blind packet with `get_model_quality_review_packet`, and submit every applicable score with `submit_model_quality_evaluation`. When repair is required, repair and recapture first, then invoke `record_model_quality_repair` to obtain a fresh blind packet before rescoring.

Report the durable terminal status, leave the preview pending, and ask the user to choose commit or revert. Do not stop after planning, initial construction, an unscored screenshot, or an in-memory scorecard.
