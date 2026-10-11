---
name: blender-retopology
description: Improve Meshy, Tripo or other existing Blender meshes with deliberate editable topology, source-preserving cleanup, reduction, remeshing or reference-derived reconstruction, followed by geometry and appearance checks. Use for dense generated meshes, human-style edge flow, hard-surface rebuilding or character retopology; not for generating a new subject or rigging alone.
---

# Retopology and Reconstruction

Produce topology suited to the user's intended use while retaining the shapes and appearance they care about. A small triangle count or a high quad percentage alone is not success.

## Inspect and choose

Check `blender_bridge_status`, discover helpers through `search_blender_tools` with `include_schemas=false`, fetch each selected schema with `get_blender_tool_schema`, and invoke through `invoke_blender_tool`. Helper names below resolve through this gateway even when absent from top-level tools/list. Use actual returned names and job IDs.

Inspect the selected source with `inspect_retopology_source` before changing it. Record dimensions, triangle equivalents, face types, connected islands, open edges, UVs, materials, modifiers, rigs and shape keys. Inspect shaded and wireframe views. Ask about intended use or exact fidelity only when the answer changes the approach and cannot be inferred.

Choose and explain the approach from the evidence:

| Approach | Choose when | What it does not establish |
| --- | --- | --- |
| Cleanup | Loose, duplicate or degenerate geometry is the main problem | New edge flow or lower surface density |
| Reduction | A static prop needs fewer exported triangles and its current surface is useful | Deliberate editable loops |
| Remeshing | A continuous surface needs a more regular starting mesh | Semantic parts or deformation-ready topology |
| Reconstruction | Flat panels, cylinders, openings and attachments are buried in arbitrary triangles | Exact surface or texture equivalence |
| Hybrid | Only some parts benefit from rebuilding | Automatic semantic separation of a fused mesh |

For props read [references/hard-surface.md](references/hard-surface.md). For characters read [references/characters.md](references/characters.md). Use both for a character with mechanical accessories; keep the topology requirements distinct.

Preserve the original mesh, transforms, UVs, materials and images. `prepare_retopology_copy` provides independent static meshes and materials. Keep islands unless specific fragments have been identified as unwanted. Its copies capture the evaluated pose and do not transfer rigs or shape keys. Its default smooth shading is not a hard-surface shading prescription; inspect and restore intended sharp/flat shading on the candidate.

## Execute the chosen approach

Use `start_retopology_job` for local QuadriFlow or decimation, normally with `bake_textures=false` until shape is acceptable. `target_faces` is per object: approximate quads for QuadriFlow and triangle equivalents for decimation. Choose budgets from the asset and use, not from the pump example. Preserve symmetry only when supported by the source. Open or nonmanifold meshes may need localized repair before QuadriFlow; do not blanket-fill intentional openings.

Poll `get_retopology_job_status` until a terminal result, inspect its reports, then import a completed candidate with `import_retopology_job_result`. A timeout does not cancel a worker. Reuse the job ID and recover its state before resubmitting. Hosted Meshy/Tripo retopology is optional; use the bridge's exact-job Blender spend approval if selected. The skill grants no paid approval.

For authored reconstruction, make a measured part plan and build new objects without modifying the source. Prefer a cohesive reference-derived `draft_script` when runtime trust is active; it runs immediately with checkpoint protection, **not** preview rollback. Verify `auto_ran=true` before claiming execution. Use `start_trusted_script_job` for long copied-file authoring and apply only with the required approval. With trust off, use suitable bounded helpers or resolve trust before authored execution. Never enable trust programmatically.

Retain named editable parts and explicit relationships. Resolve actual target names after construction. An assembled review/export mesh may be a separate copy, but do not export both copies as duplicate geometry. Derive each asset from its own source; [references/pump-study.md](references/pump-study.md) is a worked example and regression fixture, not a category base or generic retopology solver.

## Evaluate geometry and appearance

Read [references/evidence.md](references/evidence.md) before acceptance. Compare the original and candidate with `evaluate_retopology_result`, then inspect matched shaded views, wireframes and important features. Its bounded global distances can miss a lost small hole or misreport intended internal caps; investigate disagreement rather than changing a tolerance to force a pass.

Rebake only after the geometry is useful. Call `start_retopology_bake_job` from the original textured source to the accepted target, poll and inspect the new copy before replacing candidate materials. Examine projection coverage, UV atlas utilization, seams, normal orientation and visible closeups. A completed job is not a successful appearance transfer. Reject defective baked materials; report procedural replacements or authored textures as an appearance change.

When visual fidelity is part of the request, use `start_model_quality_review`, a fresh `get_model_quality_review_packet` with `include_prior_scores=false`, and `submit_model_quality_evaluation`. State the reference and intended fidelity honestly. Repair the failed criterion, refresh the same evidence, and record the pass with `record_model_quality_repair`. Do not turn an authored interpretation into a claim of exact equivalence. Start/finalize an execution trace for substantial work.

Keep helper-created previews pending for the user's decision unless the conversation already authorizes keeping or rejecting that result. Checkpoint-only authored work has a different rollback path; do not call preview tools to undo a trusted script. Save or export when requested, using an authorized destination.

Report the actual source/candidate, chosen approach, editable and exported counts, retained or lost features, appearance-transfer outcome, evidence paths and outstanding review needs. For characters explicitly report missing rig, shape-key or deformation validation; never equate automatic quads with animation readiness.
