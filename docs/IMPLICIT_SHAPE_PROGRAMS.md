# Implicit Shape Programs

Implicit shape programs let the connected MCP client describe a novel continuous form as a compact semantic graph. Blender Agent Bridge validates that graph, evaluates its signed-distance field (SDF), extracts a watertight polygon mesh, and stores the canonical program on the object for later revision.

This is an LLM-native modeling path. It does not call Hunyuan3D, TRELLIS, another provider, or a category-specific base-mesh library. The connected LLM supplies the semantic decomposition; the bridge performs bounded geometry math and preview-safe scene mutation.

## Tools

- `compile_shape_program` creates one continuous uniform or adaptive-dual mesh and stores its canonical program, digest, and compiler settings.
- `inspect_shape_program` returns the stored graph, semantic summary, mesh counts, and digest-integrity warnings.
- `update_shape_program` recompiles an existing shape object while preserving its object transform, materials, and modifiers.
- `sample_shape_program_sdf` probes up to 512 object-local program-space points without mutating Blender. Negative distances are inside the form.

All four tools are canonical Blender Agent Bridge tools. Any MCP client can find them with `search_blender_tools`, fetch the same schema with `get_blender_tool_schema`, and invoke them through `invoke_blender_tool`.

## Shape Program V1

A program contains explicit object-local bounds and up to 64 ordered nodes:

```json
{
  "schema_version": 1,
  "name": "Cartoon kitten blockout",
  "bounds": {
    "min": [-2.0, -1.5, -1.5],
    "max": [2.0, 1.5, 3.0]
  },
  "nodes": [
    {
      "id": "body",
      "type": "ellipsoid",
      "semantic_role": "body",
      "radii": [0.75, 0.6, 1.0]
    },
    {
      "id": "head",
      "type": "ellipsoid",
      "semantic_role": "head",
      "radii": [1.0, 0.72, 0.85],
      "blend": 0.25,
      "transform": {"location": [0.0, 0.0, 1.4]}
    },
    {
      "id": "tail",
      "type": "sweep",
      "semantic_role": "tail",
      "points": [
        [0.55, 0.0, -0.5],
        [1.1, 0.0, -0.2],
        [1.3, 0.0, 0.35],
        [1.0, 0.0, 0.8]
      ],
      "radii": [0.24, 0.2, 0.14, 0.07],
      "blend": 0.16
    }
  ]
}
```

The first enabled node must use `union`. Later nodes use:

- `union` to add a form;
- `subtract` to carve a cavity or separation;
- `intersect` to crop a form;
- `blend` to soften the active boolean boundary in program units.

Subtract and intersect nodes may also name earlier union nodes in `target_ids`.
That confines a cutter to the intended semantic forms; omitting `target_ids`
retains the original global sequential behavior.

Nodes may use `parent_id`. Parent transforms move and scale semantic children as a unit, which lets a client widen a head while keeping its muzzle and ears attached. Program coordinates are object-local, so later object transforms do not invalidate the stored graph.

## Primitive Vocabulary

| Type | Main fields | Typical use |
| --- | --- | --- |
| `sphere` | `radius` | joints, sockets, round masses |
| `ellipsoid` | `radii` | heads, bodies, cheeks, paws |
| `box` | `size`, `rounding` | panels, housings, clipped masses |
| `capsule` | `point_a`, `point_b`, `radius`, optional `cross_section`, `cross_section_rotation` | limbs, handles, flattened straps |
| `cylinder` | `radius`, `depth`, `rounding` | shafts, necks, mechanical forms |
| `torus` | `major_radius`, `minor_radius` | rings, rims, curled forms |
| `superquadric` | `radii`, `exponents` | boxy-to-pointed organic masses |
| `sweep` | `points`, `radii`, optional `cross_sections`, `cross_section_rotations` | tails, horns, cables, ribbons, curved limbs |

Every node also supports local `location`, XYZ Euler `rotation` in radians, positive `scale`, `enabled`, and an optional `semantic_role` label.

## Adaptive Dual Contouring

Uniform marching tetrahedra remains the default because it is predictable while proportions are changing. Set `meshing_mode` to `adaptive_dual` after the broad form stabilizes. Adaptive mode builds a sparse octree, places one QEF vertex from Hermite intersections and normals in each surface leaf, and connects vertices around sign-changing minimal octree edges. Mixed triangles and quads are preserved instead of adding transition diagonals.

```json
{
  "meshing_mode": "adaptive_dual",
  "adaptive_base_depth": 4,
  "adaptive_max_depth": 7,
  "adaptive_error_threshold": 0.05,
  "refinement_regions": [
    {
      "name": "feature_cluster",
      "type": "sphere",
      "center": [0.0, -0.45, 1.35],
      "radius": 0.9,
      "depth": 7
    },
    {
      "name": "lower_contacts",
      "type": "box",
      "min": [-0.9, -0.8, -1.1],
      "max": [0.9, 0.2, -0.35],
      "depth": 6
    }
  ]
}
```

`adaptive_base_depth` is the minimum surface depth; depth 5 corresponds to 32 root divisions. `adaptive_max_depth` is the hard ceiling for automatic QEF-error refinement, explicit regions, and bounded topology repair. Lower error thresholds refine more curved or inconsistent cells. Explicit regions refine only potentially surface-containing cells they intersect, not their full volume.

The result reports surface leaves by depth, QEF residuals, automatic/region/topology refinement counts, skipped minimal-edge segments, per-region surface/target-depth counts, and disconnected mesh-component counts. A region with zero surface leaves did not affect the mesh and should be moved or removed. The compiler rejects unpaired, inconsistently oriented, or non-manifold mesh edges instead of returning a cracked result.

## Recommended Reference Workflow

1. Prepare and calibrate the reference images.
2. Decompose visible structure into named masses, cavities, and paths.
3. Author a low-node-count shape program with generous bounds.
4. Compile in uniform mode at resolution 20-32 for silhouette iteration.
5. Render or compare all calibrated views.
6. Inspect the stored program and revise named nodes rather than replacing the mesh blindly.
7. After proportions stabilize, switch to adaptive-dual mode and target measured local detail with refinement regions.
8. Commit the shape, then apply adaptive remeshing, semantic repair, feature stacks, materials, and fur as needed.

`update_shape_program` changes topology. It clears vertex groups whose indices no longer describe the regenerated surface and reports their names. Preview revert restores the prior mesh, metadata, and weights. Shape-key meshes are refused.

## Bounds And Limits

Compilation is deliberately bounded:

- 64 nodes per program;
- 64 points per sweep;
- resolution 8-96 along the longest bounds axis;
- adaptive base depth 3-7 and maximum depth 3-9;
- at most 16 adaptive sphere/box refinement regions;
- a 64-million SDF-work ceiling, with parent transforms evaluated once per sample instead of once per child;
- fixed grid-sample, octree-cell, vertex, and face ceilings;
- rejection when the surface reaches a compile boundary;
- closed uniform marching-tetrahedra or adaptive minimal-edge dual output.

Use the smallest bounds that still leave clear space around the form. Oversized bounds waste resolution; undersized bounds are rejected instead of producing an open mesh.

## Adaptive Mode And Touching Surfaces

Adaptive dual contouring places vertices per octree cell. A cell holding two surface sheets
-- a `subtract` cavity wall beside the outer wall, most often -- needs one vertex per sheet.
Giving both a single shared vertex makes four faces meet on one edge, which is not a
manifold, and the compiler refuses such a mesh.

The compiler now groups each cell's sign-changing edges into connected surface patches and
emits one vertex per patch, so touching sheets stay separate. Faces built from a minimal
edge take the vertex belonging to the patch that edge touches. Ambiguous saddle faces are
resolved by sampling the face centre.

Measured on a sphere subtracted through the wall of an ellipsoid, previously 4 pinched
edges at max_depth 7, 30 at 8 and 84 at 9 -- refinement made it worse, and a program that
compiled at one depth could fail at a deeper one. All three now compile cleanly. On a
seven-node lamp with a hollowed shade, pinched edges fell from 140 to 2.

A small residue remains on some programs. Where it occurs the error names it as a pinched
edge and points at `meshing_mode: uniform`, which handles every case correctly.

All retained cavity-breakthrough diagnostics now compile manifold at maximum depths 7,
8, and 9. Targeted booleans also avoid accidental cuts through unrelated union forms.
The final two-edge seven-node lamp case remains an open legacy fixture problem because
that exact program was not retained for a reproducible algorithmic fix.

## Current Limits

Adaptive mode reduces empty-volume work and concentrates topology, but it is still a bounded CPU decoder rather than a learned 3D prior. Extremely ambiguous topology may require a higher base depth or uniform mode, and maximum-depth/cell/work limits can refuse oversized requests. Circular and elliptical path sections plus targeted booleans cover continuous masses, straps, garments, and local cavities; they do not express arbitrary engraved detail, pores, individual hair, or learned hidden-surface inference. Use calibrated visual hull/depth tools for multi-view evidence, semantic sculpt tools for measured local correction, and fur-flow/groom tools after the core surface is stable.
