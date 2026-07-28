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

1. Use `create_reference_modeling_guides` to create the reference plane, outline curves, landmark empties, mass ellipses, and measurements.
2. Use normalized image coordinates unless the user supplies pixel coordinates and image size.
3. Name guides for script handoff, such as `primary_outline`, `feature_left_center`, `secondary_mass`, or `major_width`.
4. Inspect the result with `inspect_reference_modeling_guides(include_points=true)` before writing an authored modeling script.
5. Feed the inspected collection metadata into the script; do not make the script rediscover guide objects by vague selection state.

If annotation data is missing, create a `reference_brief` that explicitly lists the missing guide inputs and use the planner to request or proceed with lower-confidence guide seeds.

## Sculpt Against Guides

For organic subjects, prefer continuous deformed forms over stacked primitives:

- Build broad ellipsoid or metaball-like masses that match silhouette first.
- Blend or join adjacent soft forms only after their measured positions are acceptable.
- Place landmarks from guide empties before adding expressive detail.
- Keep visible features, openings, attachments, supports, and extensions tied to named guide points or measured ratios.
- Preserve the source camera/framing as a comparison view and keep front/side diagnostic views stable across repair passes.

Do not add fur, hair, whiskers, fabric fibers, or glossy finish to hide a weak silhouette, wrong eye placement, or broken mass transition.

## Fur And Surface Flow

When the reference shows fur or directional fibers:

1. Record flow regions in `surface_cues`, including direction, length, density, color variation, and where the flow changes.
2. Use `create_directional_fur_curves` for short preview-safe groom strokes on named mesh surfaces after form gates pass.
3. Use multiple passes for different flow regions instead of one global direction when the reference clearly changes direction.
4. Treat directional fur curves as a scaffold for review; final hair systems or custom curves may still require authored script work.

## Redline Repair

After each render or viewport capture, convert visual critique into measurable repairs:

- "The upper mass should be wider here" becomes a named mass or outline-width adjustment.
- "The paired features are lower" becomes landmark and vertical-spacing repair.
- "The side attachments are smaller" becomes scale and attachment-position repair.
- "The opening is too flat" becomes form-continuity and curve-depth repair.
- "Fur direction wrong" becomes surface-flow region repair.

Repair the weakest below-floor criterion first, recapture the same views, then rescore from the durable review packet. Never call the result realistic or faithful unless the evidence gates support that claim.
