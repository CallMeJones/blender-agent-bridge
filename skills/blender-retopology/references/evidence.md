# Evidence and acceptance

Choose checks from the user's use and fidelity requirements. Do not apply the pump's budgets or tolerances universally.

## Geometry

- Compare measured extents, primary masses, contact points, openings and silhouettes against the original in matched views.
- Report base/evaluated face counts, triangle equivalents, quads and actual exported triangles. GLB triangulates faces; UV seams can also split imported vertices.
- Inspect boundary/nonmanifold edges, zero-area faces, invalid coordinates, winding, overlapping components and any unexpected geometry. Intentional openings and separate parts need context.
- Check density on flat areas and loop direction on curved/critical areas; percentages cannot prove good flow.
- Verify source preservation, independent mesh/material data, intended object transforms and named editable parts.

`evaluate_retopology_result` uses bounded bidirectional vertex/face-center samples. The sampled maximum and p95 are diagnostics, not an exhaustive Hausdorff distance or proof of every feature. The default 2% diagonal threshold can miss a small but important opening on a large model. Use a local measurement, a scoped ray test or matched closeup for such features. Inspect internal caps before interpreting an assembly's global distance failure.

## Appearance

Inspect shape before texture transfer. After a bake, record:

- `bake` findings and measured projection coverage; below 98% produces a bridge warning.
- `atlas.utilization_fraction`, which measures useful UV pixels before padding. Below 25% warns about inefficient allocation; high ray coverage does not cure a tiny atlas.
- Pixel margins and chart separation, resolution, required maps, colorspaces, packed images and finite values.
- Matched renders and closeups of seams, holes, thin/close parts, normals and important surface detail.

These warning thresholds belong to the existing tools; they are not universal artistic acceptance rules. Visible black gaps or incorrect projection remain a failure even if a numeric gate passes. Separate whole-atlas coverage from any labelled exterior-only diagnostic. Do not discard visible surface misses to inflate coverage.

If a bake fails, retain the geometry candidate and the last acceptable materials. Inspect/revert a helper-created bad bake within the supported preview scope rather than deleting the source or rerunning a paid provider job. Report any switch to procedural materials or authored textures.

## Deliverable checks

For requested saved output, reload the `.blend` in a fresh background Blender process. Verify source preservation and candidate geometry, object/part names, transforms, material/image availability and UV data. Reimport the exported GLB into a fresh scene, check actual triangles, extents and relevant openings, and inspect render/export shading. Do not expect GLB to retain Blender quad polygons or seam-free vertex counts.

Report evidence paths and limitations. Headless tests can prove structural invariants; matching the subject and judging edge flow still require visual evidence. Self-scoring is not an independent review.

## Maintained regression fixtures

The repository's `smoke_retopology_reconstruction` exercises the packaged pump example and three unrelated analytical props: a flat enclosure, a hollow flange and a bent handle. It checks source preservation, triangle reduction, surface comparisons, bore rays, UVs, named parts and GLB reimport. A deliberately capped bore must be rejected by the local feature check. Character fixtures confirm that automatic evaluation cannot certify animation readiness.

Run it through `scripts/run_smoke_suite.py --test smoke_retopology_reconstruction --blender <executable>`. This is infrastructure/example validation, not evidence that an agent has solved arbitrary semantic reconstruction. For new real assets, execute the skill against the actual source and retain their matched visual evidence and reports.
