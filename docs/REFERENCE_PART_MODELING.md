# Reference Part Modeling

This layer turns calibrated guide scenes into named editable sculpt parts before
detail, fur, or repair passes.

## Tools

- `create_reference_part_graph`: reads a calibrated guide collection, resolves
  guide masses/landmarks, and creates a part graph collection with JSON metadata
  for part names, roles, centers, radii, camera-basis axes, parent links,
  symmetry keys, source evidence, and warnings.
- `build_part_aware_base_mesh`: consumes a part graph and creates deformed
  ellipsoid components. Organic parts can be blended into a soft voxel-remesh
  union while feature parts such as eyes and nose remain separate.

## Recommended Placement

1. `prepare_reference_images`
2. `create_multiview_reference_guides` or single-view annotation guides
3. `create_multiview_visual_hull` or `create_multiview_depth_surface`
4. `fit_surface_to_multiview_references`
5. `create_reference_part_graph`
6. `build_part_aware_base_mesh`
7. `adaptive_remesh`
8. semantic/form-aware sculpt and fur flow tools
9. `evaluate_multiview_reference_match`

## Boundary

The graph is deterministic and bounded. It uses explicit guide names, landmarks,
and optional part hints first. For `cute_quadruped` subjects it can split one
primary silhouette into default head/body/ear/muzzle/eye parts, but those are
heuristics and should be inspected or corrected with part hints before claiming
close reference fidelity.
