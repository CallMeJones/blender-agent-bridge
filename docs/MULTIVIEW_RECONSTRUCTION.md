# Multi-View Reconstruction

Blender Agent Bridge can construct a deterministic primary volume from two to six calibrated silhouette annotations. The bridge does not call an external image-to-3D model: clients provide reference paths and client-neutral annotation JSON, while Blender owns calibration, silhouette intersection, topology limits, and preview rollback.

## Recommended Sequence

1. Create calibrated views with `create_multiview_reference_guides`.
2. Build a watertight primary volume with `create_multiview_depth_surface` when calibrated depth exists; otherwise use `create_multiview_visual_hull`.
3. Run `fit_surface_to_multiview_references` to reduce joint silhouette, depth, and reconstructed-landmark error.
4. Refine only under-sampled areas with `adaptive_remesh`.
5. Define and inspect semantic regions for remaining localized errors.
6. Apply one `apply_form_aware_sculpt`, `apply_semantic_sculpt`, or calibrated screen-space repair.
7. Compare the same views again before adding fur or fine surface detail.

All tools are canonical catalog tools. Any MCP client can find them with `search_blender_tools`, fetch exact schemas with `get_blender_tool_schema`, and invoke them through `invoke_blender_tool`.

## Visual Hull

`create_multiview_visual_hull` reads the orthographic basis, physical plane scale, subject center, and normalized cyclic outlines stored by `create_multiview_reference_guides`. It intersects those silhouette volumes on a bounded uniform grid, filters disconnected occupancy, emits only exposed voxel faces, and optionally applies bounded Taubin relaxation.

```json
{
  "name": "create_multiview_visual_hull",
  "arguments": {
    "collection_name": "Kitten Multi-View Guides",
    "view_names": ["front", "left"],
    "object_name": "Kitten Visual Hull",
    "resolution": 48,
    "component_mode": "largest",
    "smooth_iterations": 2
  }
}
```

The largest cyclic outline in each selected view is used by default. When `view_names` is omitted, calibrated landmark-only views are skipped with a warning; explicitly requesting such a view is an error. Use `outline_overrides` when a view contains more than one closed contour. Automatic bounds use axis-aligned silhouette extents where calibration permits and a conservative camera-plane bound otherwise. Supply `bounds_center` and `bounds_size` together to override them.

The synchronous grid is capped at 512,000 cells, silhouette testing at 100 million worst-case edge evaluations, and emitted surface topology at 1 million faces. Lower `resolution` or simplify very dense outlines when a workload guard refuses the call. A front/back pair is not sufficient because opposite orthographic rays are parallel; include a side, top, bottom, or suitable custom view.

## Calibrated Depth Fusion

`create_multiview_depth_surface` adds front or back depth half-spaces to the silhouette intersection. It accepts local grayscale depth images with explicit `near_depth` and `far_depth` world calibration, or sparse normalized samples whose `depth` is the signed world distance from the view center along its forward vector. The bridge does not estimate monocular depth or call another model.

```json
{
  "name": "create_multiview_depth_surface",
  "arguments": {
    "collection_name": "Kitten Multi-View Guides",
    "object_name": "Kitten Depth Surface",
    "resolution": 48,
    "depth_sources": [
      {
        "view_name": "front",
        "mode": "front",
        "image_path": "C:/references/kitten-front-depth.png",
        "near_depth": -0.7,
        "far_depth": 0.7,
        "channel": "luminance"
      }
    ]
  }
}
```

Use `invert` when white represents the near side. Transparent pixels can be ignored with `alpha_threshold`; `invalid_below` and `invalid_above` exclude sentinel values before world-depth conversion. Each view supports at most one front and one back layer. Images are downsampled under an aggregate pixel limit before carving, and every supplied layer must overlap occupied silhouette samples.

Sparse samples use the same calibration without requiring a depth image:

```json
{
  "view_name": "front",
  "mode": "front",
  "samples": [
    {"point": [0.5, 0.42], "depth": -0.34, "radius": 0.08}
  ]
}
```

Sparse samples are placed in a bounded spatial index, so reconstruction does not scan every sample for every voxel or fitted vertex. Requests with pathological sample overlap or an aggregate depth workload above the synchronous limit are refused with an actionable error; reduce resolution, iterations, candidates, source count, or sparse-sample overlap.

## Joint Surface Fitting

`fit_surface_to_multiview_references` removes the need for a client to invent individual screen-space pulls. It finds projected silhouette edges, derives nearest-outline corrections in each calibrated camera, incorporates optional depth residuals and reconstructed 3D landmarks, then diffuses the correction field through mesh adjacency. Every iteration tries bounded step sizes and rejects candidates that fail the aggregate objective, exceed the allowed regression in any view, collapse a face below 2% of its original area, or reverse face orientation. Every supplied depth layer must constrain eligible vertices. Shape-key meshes are rejected because safe key-block editing and rollback are not yet supported.

```json
{
  "name": "fit_surface_to_multiview_references",
  "arguments": {
    "object_name": "Kitten Depth Surface",
    "collection_name": "Kitten Multi-View Guides",
    "view_names": ["front", "left", "top"],
    "landmark_names": ["nose_tip", "left_eye_outer", "right_eye_outer"],
    "iterations": 6,
    "step_candidates": [0.25, 0.5, 1.0],
    "feature_preservation": 0.4,
    "maximum_total_displacement": 0.35,
    "capture_evidence": true
  }
}
```

The result reports baseline and final objectives, per-view silhouette/depth errors, accepted and rejected trials, landmark bindings, displacement statistics, surface-integrity counts, estimated depth workload, and the stop reason. `capture_evidence` additionally renders before/after masks and redlines through every selected camera; a rendered aggregate regression restores the original mesh. Successful geometry remains a live preview until the user commits it.

## Adaptive Topology

`adaptive_remesh` selectively subdivides edges whose lengths exceed a local target. Semantic-region weight can request more local density, while adjacent face-normal disagreement adds detail at curved or sharp forms. The tool can relax spacing and project the result back onto the original surface.

```json
{
  "name": "adaptive_remesh",
  "arguments": {
    "object_name": "Kitten Visual Hull",
    "target_edge_length": 0.06,
    "passes": 2,
    "region_detail": 0.75,
    "curvature_detail": 0.6,
    "project_to_source": true,
    "max_result_vertices": 250000
  }
}
```

When `region_names` is empty, refinement covers the whole mesh. Named semantic point attributes are interpolated through subdivision and retained. Adaptive remeshing and all semantic/form-aware deformation tools reject shared mesh data, shape keys, excessive input meshes, and any pass whose predicted or actual output exceeds the configured vertex limit.

This is adaptive sculpt refinement, not decimation, quad-flow retopology, or an animation-ready edge-loop guarantee.

## Form-Aware Brushes

`apply_form_aware_sculpt` uses mesh adjacency and recomputed surface normals instead of treating vertices as unrelated points:

- `tangent_relax` evens surface spacing in tangent planes;
- `pinch` pulls a region toward a weighted or explicit center without collapsing directly through the surface;
- `crease` combines tangent pinch with signed normal depth.

Topology falloff can diffuse region influence through adjacent vertices. `feature_preservation` reduces deformation where neighboring normals disagree. Symmetry, volume compensation, and a final world-space displacement cap remain available.

```json
{
  "name": "apply_form_aware_sculpt",
  "arguments": {
    "object_name": "Kitten Visual Hull",
    "region_names": ["muzzle_center"],
    "operation": "crease",
    "strength": 0.15,
    "crease_depth": -0.02,
    "falloff_steps": 2,
    "falloff_decay": 0.7,
    "feature_preservation": 0.65,
    "maximum_world_displacement": 0.08
  }
}
```

## Capability Boundary

Visual hulls recover only geometry constrained by silhouettes. Calibrated depth can recover visible concavities and front/back placement where measurements exist, but it cannot invent unseen anatomy. Joint fitting reduces explicit cross-view residuals; it does not provide learned semantic priors about what a kitten, face, hand, or machine should look like. Adaptive refinement adds local sampling but does not infer anatomy. Form-aware brushes make explicit corrections more stable; they do not decide what the correct form should be.
