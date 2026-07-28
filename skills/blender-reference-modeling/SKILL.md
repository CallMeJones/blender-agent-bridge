---
name: blender-reference-modeling
description: Build, compare, review, or repair a Blender model against an actual supplied image, photograph, concept, or visual reference using adaptive decomposition, measurable proportions, evidence scoring, and bounded repair. Use only when the request explicitly concerns model creation or quality against visual form criteria; do not trigger for animation-only requests, a generic character mention, or the bare word reference.
---

# Blender Reference Modeling

Use the supplied image as the comparison source. The skill defines process and quality gates, not geometry recipes.

Apply the five-tool Blender Bridge contract. If it is not already active, read [../blender-bridge/references/gateway.md](../blender-bridge/references/gateway.md).

For image-to-form work, create measurable guide scaffolding before sculpting. Read [references/guide-first-workflow.md](references/guide-first-workflow.md) whenever the task includes an image reference, clicked/annotated landmarks, organic sculpting, or fur/hair/groom direction.

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
7. Build primary masses and silhouette before landmarks or surface detail.
8. Refresh scene objects and resolve the union of existing targets, construction-returned names, and new scene-diff objects.
9. Pass resolved names into every later inspection, surface, and evidence call.
10. Start durable scoring only after current target names and matched evidence URIs are available.

Read [references/reference-brief.md](references/reference-brief.md) before invoking the planner.

Do not use canned category bases, category-specific builders, memorized anatomy, or geometry recipes. Do not invent forms hidden by the source. With active trust, use one cohesive reference-derived script for primary construction and broad repair unless the user requests helpers. Use bounded helpers for inspection, evidence, operational work, and deliberately isolated edits.

Reference requests commonly mix construction with evidence, rendering, or saving. Keep those operational calls outside the authored script handoff without allowing them to demote the reference-derived construction or repair script.

Do not invent focal lengths, numeric tolerances, material parameters, anatomy, dimensions, or symmetry. Preserve ambiguous measurements as ambiguity unless the image or user resolves them. Label values as supplied, measured, derived, or uncertain.

Use `create_reference_modeling_guides` for calibrated image planes, outline curves, landmark empties, mass ellipses, and proportional measurements when the prompt or annotation data supplies enough points. Use `inspect_reference_modeling_guides` before authored construction or repair scripts so scripts receive exact guide names, world points, and the saved `reference_brief` seed instead of re-parsing the scene.

## Gate Form Before Surface

Capture evidence from:

- a viewport framed to match the reference, including its three-quarter angle when applicable;
- stable front and side/profile inspection views;
- additional supported views only when they reveal a declared criterion;
- modeling and material inspectors where structural evidence matters.

Score silhouette, proportions, landmark placement, and form continuity before adding surface treatment. Require every applicable form criterion to meet the planner's quality floor.

Read [references/evidence-review.md](references/evidence-review.md) before scoring.

For fur, hair, fibers, whiskers, or plush surface flow, place coarse forms first, then use `create_directional_fur_curves` as a preview-safe groom scaffold only after silhouette and proportions are acceptable. Directional curves are guide/detail evidence, not a substitute for mass correction.

## Repair Weakest Criteria

Repair criteria below the quality floor in impact order. Recapture the same evidence after each pass. Use at most the planner's bounded repair limit, and report a blocker rather than declaring success when a criterion remains below the floor.

Read [references/repair-loop.md](references/repair-loop.md) when any score misses the floor.

Add materials, textures, hair, fibers, particles, or finish only when explicit `surface_cues` support them. Surface detail must not conceal unresolved form errors.

## Finish In Preview

Capture final reference-aligned evidence, invoke `start_model_quality_review`, request a blind packet with `get_model_quality_review_packet`, and submit every applicable score with `submit_model_quality_evaluation`. When repair is required, repair and recapture first, then invoke `record_model_quality_repair` to obtain a fresh blind packet before rescoring.

Report the durable terminal status, leave the preview pending, and ask the user to choose commit or revert. Do not stop after planning, initial construction, an unscored screenshot, or an in-memory scorecard.
