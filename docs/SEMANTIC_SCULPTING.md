# Semantic Sculpting

Blender Agent Bridge exposes deterministic sculpt primitives for image-capable MCP clients. The client analyzes the supplied reference and describes a small, named correction. Blender converts that description into bounded vertex weights and deformation, then keeps the result in live preview.

No external image-to-3D model is required. The bridge does not ask a learned reconstructor to invent a finished mesh.

## Responsibilities

The MCP client owns:

- visual decomposition, landmark identification, and critique;
- names such as `left_cheek`, `ear_tip`, or `lower_hull`;
- normalized source and target points measured in the calibrated reference image;
- deciding whether a visible error is a translation, inflation, smoothing, flattening, or contour pull.

Blender owns:

- resolving semantic regions to persistent mesh point attributes;
- projection through the calibrated reference camera;
- smooth falloff, front-face filtering, symmetry, displacement limits, and volume compensation;
- topology-aware tangent relaxation, pinch, crease, and curvature protection;
- bounded candidate evaluation against silhouette and landmark evidence;
- restoring the mesh when a call fails or no candidate improves the score;
- live-preview commit and revert behavior.

## Tool Sequence

All six semantic helpers are canonical catalog tools. Any MCP client can discover them with `search_blender_tools`, fetch a schema with `get_blender_tool_schema`, and call them through `invoke_blender_tool`.

1. Create calibrated image and camera guides with `create_reference_guides_from_annotations`.
2. Build or identify one editable mesh.
3. Define localized regions with `define_semantic_sculpt_regions`.
4. Verify coverage with `inspect_semantic_sculpt_regions`.
5. Use one repair tool:
   - `apply_semantic_sculpt` for a measured 3D field;
   - `apply_form_aware_sculpt` for tangent relax, pinch, or crease;
   - `apply_screen_space_sculpt` for a known image-space pull;
   - `optimize_screen_space_sculpt` to try bounded strengths and retain only a measured improvement.
6. Recapture the same evidence and rescore before another repair.
7. Add fur or surface detail only after form gates pass.

## Semantic Regions

Regions are stored as bounded `POINT`/`FLOAT` mesh attributes. A region may combine up to 16 selectors:

- local or world sphere;
- local or world axis-aligned box;
- explicit vertex indices;
- sphere around a named reference landmark;
- polygon in normalized calibrated screen coordinates.

Use `replace`, `add`, `subtract`, and `intersect` write modes to refine coverage. Delete a region by calling `define_semantic_sculpt_regions` with its `name` and `"write_mode": "delete"`; selectors are not required for deletion. The point attribute and metadata are both removed, with preview revert support until commit. Spatial feather values use scene units. Screen-polygon feather values use normalized image units.

```json
{
  "name": "define_semantic_sculpt_regions",
  "arguments": {
    "object_name": "Kitten_Base",
    "regions": [
      {
        "name": "right_cheek",
        "selectors": [
          {
            "type": "screen_polygon",
            "collection_name": "Kitten Guides",
            "camera_name": "Kitten Reference Camera",
            "origin": "top_left",
            "points": [[0.53, 0.38], [0.75, 0.38], [0.79, 0.59], [0.55, 0.61]],
            "feather": 0.025
          }
        ]
      }
    ]
  }
}
```

## Screen Controls

Each control contains normalized `source` and `target` image points, a normalized influence `radius`, and a local control `strength`. A positive global strength moves the visible mesh near `source` toward `target` while preserving each vertex's camera-space depth.

```json
{
  "name": "optimize_screen_space_sculpt",
  "arguments": {
    "object_name": "Kitten_Base",
    "collection_name": "Kitten Guides",
    "camera_name": "Kitten Reference Camera",
    "region_names": ["right_cheek"],
    "controls": [
      {
        "source": [0.68, 0.49],
        "target": [0.72, 0.50],
        "radius": 0.12,
        "strength": 1.0
      }
    ],
    "strength_candidates": [0.5, 1.0, 1.5],
    "maximum_world_displacement": 0.2,
    "preserve_volume": 0.5
  }
}
```

The optimizer renders a baseline and each candidate through the calibrated camera. It scores silhouette overlap, edge distance, and optional landmark error. It leaves the best measured improvement in preview, or restores the original mesh when the minimum improvement is not reached.

## Limits

A single image does not determine hidden depth, back-side form, or occluded anatomy. Screen-space pulls preserve existing camera-space depth; they do not reconstruct missing geometry. Multi-view references, explicit depth constraints, or a user decision are still required for ambiguous dimensions.

Semantic attributes are stable while vertex topology is stable. `adaptive_remesh` interpolates and retains them, but their coverage should still be inspected afterward. Inspect or redefine regions after other remesh, Boolean, or destructive topology operations. Shape-key meshes are rejected by default because direct basis edits can have wider consequences.

Mutation requires Object Mode and single-user, editable mesh data. Synchronous operations are limited to 250,000 vertices, and selector, screen-polygon edge, and smoothing workloads have additional bounded evaluation budgets. Volume compensation is skipped on open, non-manifold, or inconsistently wound surfaces, and a bounded correction is retained only when it reduces measured volume error.

For deterministic primary volume construction before semantic repair, see [MULTIVIEW_RECONSTRUCTION.md](MULTIVIEW_RECONSTRUCTION.md). The bridge now provides visual-hull construction and adaptive sculpt refinement; it does not claim automatic production retopology or a production groom solver.
