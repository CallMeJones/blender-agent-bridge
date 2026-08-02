# Guide-First Workflow

Use this workflow when a supplied image must drive a Blender model's shape, landmarks, or surface flow.

## Decompose The Reference

Extract observations in this order:

1. `silhouette`: outer contour, widest/narrowest spans, crop, negative spaces, stance, contact/support points.
2. `primary_masses`: large volumes that create the read, such as head/body/appendages or object hull/subforms.
3. `landmarks`: high-salience features, attachment points, corners, centerlines, openings, seams, or expression anchors.
4. `proportions`: ratios, alignments, spacing, relative scale, and depth-order uncertainty.
5. `surface_flow`: visible material direction, fur/hair/fiber grain, gloss direction, edge softness, and where detail changes density.

Use only visible or user-supplied facts. Mark hidden depth, ambiguous symmetry, cropped edges, and perspective uncertainty.

## Build Guides Before Forms

When image path, landmarks, or annotation points are available:

1. Use `create_reference_guides_from_annotations` when the reference image and annotation JSON are both available. Supply the annotation object, JSON text, or trusted local JSON path, plus its pixel/normalized coordinate space and top-left/bottom-left origin when the document does not declare them.
2. Let the pipeline calibrate annotation coordinates to the actual image dimensions, image rectangle, guide plane, and orthographic comparison camera.
3. Use `create_reference_modeling_guides` only when inputs are already normalized or must be assembled manually without an annotation document.
4. Name guides for script handoff, such as `primary_outline`, `feature_left_center`, `secondary_mass`, or `major_width`.
5. Inspect the result with `inspect_reference_modeling_guides(include_points=true)` before authoring a shape program or modeling script.
6. Feed the inspected collection metadata into the chosen construction path; do not rediscover guide objects by vague selection state.

For two or more orthographic references, use `create_multiview_reference_guides` with a distinct axis or custom camera basis for every view. Reuse exact landmark names across views. Treat high residuals, nearly parallel rays, and unresolved landmarks as calibration problems; correct the source annotations or view scale before moving reconstructed 3D landmarks by eye. When two or more non-parallel views contain closed silhouettes, call `create_multiview_visual_hull` to intersect them into the primary watertight volume. A front/back pair alone cannot bound depth.

If annotation data is missing, create a `reference_brief` that explicitly lists the missing guide inputs and use the planner to request or proceed with lower-confidence guide seeds.

## Sculpt Against Guides

For organic subjects, prefer continuous deformed forms over stacked primitives:

- Build broad ellipsoid or metaball-like masses that match silhouette first.
- Prefer `compile_shape_program` when the subject can be expressed as named continuous masses, smooth boolean cavities, and tapered paths. Store `semantic_role` labels, use `parent_id` for attached forms, inspect the canonical graph, and revise exact nodes with `update_shape_program` after each measured comparison.
- Use `sample_shape_program_sdf` to verify inside/outside behavior before a dense compile. Keep explicit bounds close enough for useful resolution but far enough that the surface never touches them.
- Prefer `create_multiview_depth_surface` when explicitly calibrated depth exists and `create_multiview_visual_hull` otherwise. Run `fit_surface_to_multiview_references` to reduce broad cross-view error before using `adaptive_remesh` for bounded local density where edge length and curvature require it.
- When helpers are requested, `create_reference_blockout` can turn named mass ellipses into camera-oriented editable forms and an optional voxel-remesh union. Keep per-mass depth and deformation settings reference-derived.
- Blend or join adjacent soft forms only after their measured positions are acceptable.
- Place landmarks from guide empties before adding expressive detail.
- Keep visible features, openings, attachments, supports, and extensions tied to named guide points or measured ratios.
- Preserve the source camera/framing as a comparison view and keep front/side diagnostic views stable across repair passes.
- Use `fit_surface_to_multiview_references` for broad silhouette, depth, or reconstructed-landmark disagreement across views. Turn remaining localized critiques into persistent named regions with `define_semantic_sculpt_regions`, then inspect their weighted coverage before deformation.
- Use `apply_semantic_sculpt` for measured 3D fields and `apply_form_aware_sculpt` for topology-aware tangent relax, pinch, or crease. Use `apply_screen_space_sculpt` for a known calibrated contour pull, or `optimize_screen_space_sculpt` when candidate strengths should be scored and rejected unless they improve the reference metrics.
- `adaptive_remesh` interpolates semantic point attributes; inspect coverage afterward. Redefine semantic regions after other topology-changing operations that alter vertex identity.
- Commit the implicit blockout before topology-dependent masks or shape keys. Recompiling clears stale vertex groups and refuses shape-key meshes; preview revert restores the previous mesh and weights.

Do not add fur, hair, whiskers, fabric fibers, or glossy finish to hide a weak silhouette, wrong eye placement, or broken mass transition.

## Fur And Surface Flow

When the reference shows fur or directional fibers:

1. Record flow regions in `surface_cues`, including direction, length, density, color variation, and where the flow changes.
2. Use `create_directional_fur_curves` for short preview-safe groom strokes on named mesh surfaces after form gates pass.
3. Prefer one bounded call with named `regions`: use vertex groups as density masks, per-region directions or world-space `flow_controls`, different lengths, and low controlled noise.
4. Keep `auto_spacing` enabled unless the reference requires an explicit root spacing. Use modest clumping and a small tip width so the result reads as a coat instead of separate bristles.
5. Treat directional fur curves as a scaffold for review; final production hair systems or hand-authored hero strands may still require authored script work.

## Redline Repair

After each render or viewport capture, convert visual critique into measurable repairs:

Invoke `compare_model_to_reference` first when a calibrated camera and outline or usable image alpha are available. Blue redline regions are reference silhouette missing from the model, red regions are model excess, and green is overlap. Repair the highest-magnitude named region or landmark error before subjective polish.

At the end of a blockout, refined-form, or final review pass, invoke `evaluate_reference_model_benchmark` with the matching `blockout`, `refined`, or `review` profile. A failed gate names the measurable repair target. For official benchmark runs, use the task's required profile without threshold overrides; only the latest recorded evaluation counts.

- "The upper mass should be wider here" becomes a named mass or outline-width adjustment.
- "The paired features are lower" becomes landmark and vertical-spacing repair.
- "The side attachments are smaller" becomes scale and attachment-position repair.
- "The opening is too flat" becomes form-continuity and curve-depth repair.
- "Fur direction wrong" becomes surface-flow region repair.

Repair the weakest below-floor criterion first, recapture the same views, then rescore from the durable review packet. Never call the result realistic or faithful unless the evidence gates support that claim.
