# Reference Image Intake And Scored Repair

This layer turns ordinary local reference images into calibrated guide inputs
without requiring another LLM or any external segmentation service.

## Tools

- `prepare_reference_images`: validates one to six local images, accepts supplied
  annotation JSON, or derives a bounded cyclic silhouette and primary mass from
  alpha, a supplied mask image, luminance, or an explicit background color. It can
  return prepared view JSON or create calibrated guide scenes directly.
- `evaluate_multiview_reference_match`: renders the model through every selected
  calibrated reference camera, compares silhouettes and optional landmarks, applies
  the versioned reference benchmark, and returns aggregate plus worst-view evidence.
- `auto_reference_sculpt_repair`: evaluates all selected views, generates coarse
  screen-space controls from the worst-view redline regions, tries bounded sculpt
  strengths, keeps only a measured improvement, and re-scores the full view set.

## Deterministic Boundary

The bridge does not infer arbitrary foregrounds from complex photos. Automatic
outline generation is deterministic and works best with transparent PNGs, clean
masks, luminance masks, or known background colors. For busy photos, the client
should provide annotation JSON or a mask image.

## Recommended Loop

1. Call `prepare_reference_images`.
2. Build with `create_multiview_visual_hull` or `create_multiview_depth_surface`.
3. Fit with `fit_surface_to_multiview_references`.
4. Score with `evaluate_multiview_reference_match`.
5. Repair with semantic regions plus `auto_reference_sculpt_repair` or lower-level
   sculpt tools.
6. Score again before claiming the model matches the reference.
