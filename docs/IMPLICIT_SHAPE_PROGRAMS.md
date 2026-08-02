# Implicit Shape Programs

Implicit shape programs let the connected MCP client describe a novel continuous form as a compact semantic graph. Blender Agent Bridge validates that graph, evaluates its signed-distance field (SDF), extracts a watertight triangle mesh, and stores the canonical program on the object for later revision.

This is an LLM-native modeling path. It does not call Hunyuan3D, TRELLIS, another provider, or a category-specific base-mesh library. The connected LLM supplies the semantic decomposition; the bridge performs bounded geometry math and preview-safe scene mutation.

## Tools

- `compile_shape_program` creates one continuous mesh and stores its canonical program, digest, and compiler settings.
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

Nodes may use `parent_id`. Parent transforms move and scale semantic children as a unit, which lets a client widen a head while keeping its muzzle and ears attached. Program coordinates are object-local, so later object transforms do not invalidate the stored graph.

## Primitive Vocabulary

| Type | Main fields | Typical use |
| --- | --- | --- |
| `sphere` | `radius` | joints, sockets, round masses |
| `ellipsoid` | `radii` | heads, bodies, cheeks, paws |
| `box` | `size`, `rounding` | panels, housings, clipped masses |
| `capsule` | `point_a`, `point_b`, `radius` | limbs, handles, bones |
| `cylinder` | `radius`, `depth`, `rounding` | shafts, necks, mechanical forms |
| `torus` | `major_radius`, `minor_radius` | rings, rims, curled forms |
| `superquadric` | `radii`, `exponents` | boxy-to-pointed organic masses |
| `sweep` | `points`, `radii` | tails, horns, cables, branches, curved limbs |

Every node also supports local `location`, XYZ Euler `rotation` in radians, positive `scale`, `enabled`, and an optional `semantic_role` label.

## Recommended Reference Workflow

1. Prepare and calibrate the reference images.
2. Decompose visible structure into named masses, cavities, and paths.
3. Author a low-node-count shape program with generous bounds.
4. Compile at resolution 20-32 for silhouette iteration.
5. Render or compare all calibrated views.
6. Inspect the stored program and revise named nodes rather than replacing the mesh blindly.
7. Increase compile resolution only after proportions stabilize.
8. Commit the shape, then apply adaptive remeshing, semantic repair, feature stacks, materials, and fur as needed.

`update_shape_program` changes topology. It clears vertex groups whose indices no longer describe the regenerated surface and reports their names. Preview revert restores the prior mesh, metadata, and weights. Shape-key meshes are refused.

## Bounds And Limits

Compilation is deliberately bounded:

- 64 nodes per program;
- 64 points per sweep;
- resolution 8-96 along the longest bounds axis;
- fixed grid-sample, node-evaluation, vertex, and face ceilings;
- rejection when the surface reaches a compile boundary;
- closed marching-tetrahedra output with shared lattice vertices.

Use the smallest bounds that still leave clear space around the form. Oversized bounds waste resolution; undersized bounds are rejected instead of producing an open mesh.

## Current Limits

The v1 decoder is a uniform grid, not an adaptive octree, so very thin details need tighter bounds or a higher resolution. The primitive vocabulary expresses continuous mass and path structure, not arbitrary engraved detail, pores, individual hair, or learned hidden-surface inference. Use calibrated visual hull/depth tools for multi-view evidence, semantic sculpt tools for measured local correction, and fur-flow/groom tools after the core surface is stable.
