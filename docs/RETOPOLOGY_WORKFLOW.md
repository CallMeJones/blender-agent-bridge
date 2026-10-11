# Retopology for Meshy and Tripo models

Use the retopology tools to inspect a generated mesh, clean an independent working copy, reduce its geometry and rebake its appearance. Local processing uses Blender and requires no provider account. Meshy and Tripo also have dedicated hosted retopology jobs for existing models.

Both props and characters follow the same initial workflow. Character results still need deliberate joint and facial edge loops and deformation tests before rigging. Automatic quad output is a starting point; the tools always report `animation_ready: false`.

For deliberate editable topology, use the repository's [Retopology and Reconstruction skill](../skills/blender-retopology/SKILL.md), invoked as `$blender-retopology` in hosts that support skills. It chooses between cleanup, reduction, remeshing, reconstruction and a hybrid approach, with separate hard-surface and character guidance. It reuses the current bridge tools; it does not add a universal semantic retopology solver. The [pump study](../skills/blender-retopology/references/pump-study.md) records both the useful geometry result and the rejected source bake.

## Inspect and clean a working copy

1. Call `inspect_retopology_source` with the source `object_names`, or leave them out to inspect the selected meshes. The report includes actual triangles, quads and ngons, connected surface islands, loose geometry, boundary and nonmanifold edges, UV maps, image availability and rig or shape-key warnings.
2. Call `prepare_retopology_copy` with the same names. It creates separate meshes and materials, merges near-coincident vertices, removes degenerate faces and loose geometry, and recalculates normals. The originals remain in place.
3. Review the working copies in live preview. Use `commit_preview` to keep them or `revert_preview` to discard them. A failed cleanup automatically reverts its own changes.

Surface islands are preserved by default so small details, eyes, teeth and detached accessories survive cleanup. Set `min_component_faces` only when you have identified fragments to remove. The largest surface island is retained. Cleanup does not fill holes or infer missing geometry.

Copies capture the evaluated current pose, including modifiers. They do not transfer the source rig or shape keys. Keep the original as the reference for later shape comparisons.

## Remesh and rebake locally

Call `start_retopology_job` with the working-copy names and an approximate face budget per object. For example, these arguments request an initial character candidate:

```json
{
  "object_names": ["Character_retopo_work"],
  "method": "quadriflow",
  "target_faces": 5000,
  "intended_use": "character",
  "resolution": 1024
}
```

The job snapshots its inputs, then runs cleanup, remeshing, optional surface projection and texture baking in a separate Blender process. It returns a `job_id` without replacing scene objects.

| Method | Useful starting point | Face budget |
| --- | --- | --- |
| `quadriflow` | Quad candidates for organic props and characters | Approximate quad face count. Open or nonmanifold meshes can require further repair. |
| `decimate` | Fast reduction of dense props or a triangle-based export candidate | Approximate triangle-equivalent budget. Does not create deformation edge loops. |

Symmetry is off by default to preserve asymmetric generated details. Enable `use_symmetry` only for a suitable source. `preserve_sharp` and `preserve_boundary` default to true for QuadriFlow. `project_to_source` defaults to true to move remeshed vertices back toward the original surface.

Textures are baked by default at 1024 pixels with 16 Cycles CPU samples. The new material uses base color, tangent-space normal, roughness, metallic and emission maps. Color and scalar maps are PNGs; emission is a floating-point EXR that includes emission strength. Every map is packed into the result `.blend`.

Set `bake_textures: false` for a geometry-only first pass. You can later call `start_retopology_bake_job` with a `source_object_name` and distinct `target_object_name`. This creates another target copy and preserves both inputs, including the supplied target's shading. `uv_mode: "smart_project"` creates an atlas; `uv_mode: "existing"` requires a target UV map and keeps it.

For detailed hard-surface props, compare a moderate reduction before trying a small fixed budget. Grilles, hose ribs, bolts and silhouette edges need geometry that normal maps cannot replace. Rebake from the original textured model so cleanup's recalculated normals do not become the detail reference. A real pump trial retained substantially more detail at 40,000 triangles from a 92,512-triangle source than at 10,000, using five 2048px maps and a four-pixel bake margin. This is an asset-specific example, not a universal budget.

Smart-project atlases use concave packing with padding measured in texture pixels. Each island reserves the requested `margin` on its sides, leaving twice that distance between charts for bake dilation. The bake report's `atlas.utilization_fraction` measures occupied pixels before padding, separately from projection coverage. Utilization below 25% produces a warning; increasing resolution, reducing an excessive margin or using suitable existing UVs can retain more detail.

The atlas extracts channels from a single Principled BSDF connected directly to the active material output. It supports linked image and procedural inputs to those channels. Surface shader groups or mixed surface shaders fail explicitly. Opacity, transmission and coat are not transferred; the bake report flags those material features for manual review.

## Poll, compare and keep a result

1. Poll `get_retopology_job_status` with the returned `job_id` until its status is `completed`, `failed`, `cancelled` or `timed_out`. A client timeout does not stop the worker. Reuse the job ID instead of starting duplicate work.
2. Read each result's `comparison`, `topology`, `findings` and `bake` report. Completion means processing finished; it does not establish that shape and texture quality are acceptable.
3. Call `import_retopology_job_result` to append the candidate through live preview. Repeated imports reuse that job's result already present in the current scene. Changed result files are refused.
4. Call `evaluate_retopology_result` with the original and imported object names. Set `include_renders: true` for front, side and top previews of each object, plus contact sheets. Inspect the result before committing the preview.

Shape comparisons use bounded samples of vertices and face centers in both directions. The default tolerance is 2% of the source's bounding-box diagonal. The report includes maximum, mean and 95th-percentile distances and actual face reduction. These samples do not exhaustively prove surface equivalence or detect every self-intersection.

A passing distance threshold does not prove small-feature, silhouette, shading or texture fidelity. Compare the renders and inspect important details before accepting the reduction. High projection coverage can still accompany a tiny, blurry UV atlas.

Texture projection coverage compares a white source bake with the target's UV mask, so legitimate black textures do not count as missed rays. Coverage below 98% produces a warning. Adjust `ray_distance_ratio` and `cage_extrusion_ratio` cautiously and inspect close surfaces such as fingers, lips or overlapping clothing.

Use `cancel_retopology_job` to stop the local worker and its descendants. Incomplete results cannot be imported. Cleanup, result import and provider import track newly created data so preview reverts remove their objects, meshes, materials and images.

## Hosted Meshy and Tripo retopology

Configure the provider key and third-party access as described in [Generation Providers](GENERATION_PROVIDERS.md). Then call `start_provider_retopology_job` with the provider and exactly one `source_task_id` or `model_url`:

```json
{
  "provider": "meshy",
  "source_task_id": "existing-meshy-task-id",
  "topology": "quad",
  "target_faces": 5000
}
```

Model URLs must be direct public HTTPS URLs without credentials, query tokens or fragments. For private or signed model URLs, use an existing provider task ID or the local Blender workflow.

The existing Blender UI spend gate covers these jobs. Approval is single-use and bound to the source, topology, face budget, provider model and output controls. Poll `get_generation_approval_status` using the returned approval request, then repeat the exact start call once approved. No tool argument grants approval.

Poll `get_provider_retopology_job_status`, then call `import_provider_retopology_job_result` to import a new candidate. Use `cancel_external_asset_job` for hosted jobs; local cancellation does not guarantee that the provider stops billing or processing. Meshy supports a remote remesh cancellation request.

| Provider | API route | Output behavior |
| --- | --- | --- |
| Meshy | `/openapi/v1/remesh` | Quad requests download FBX as the primary model and GLB as a companion. FBX preserves quad polygons; GLB stores triangles. |
| Tripo | `/v3/mesh/decimate` | Defaults to retopology model `v3.0`, texture baking and smart UVs. The returned GLB stores triangles even when quad output was requested. |

`preferred_format: "fbx"` or `"glb"` selects a cached variant during provider import. Variants have separate import identities and manifests. This also exposes FBX companions cached by Meshy's `editable_quad` generation preset. Missing requested formats fail explicitly rather than falling back silently.

Credit estimates reflect the provider documentation checked on 11 October 2026: Meshy remeshing is estimated at 5 credits; Tripo v3.0 is 40 for quad or 35 for triangle output, v2.0 is 30, and v1.0 is 10. Pricing may change. Tripo v1.0 has no texture baking, and smart UVs are supported only by v3.0. See the [Meshy remesh API](https://docs.meshy.ai/en/api/remesh) and [Tripo mesh decimation API](https://developers.tripo3d.ai/en/docs/mesh-decimate).

## Processing limits

Local jobs accept up to eight mesh objects, with at most one million vertices and two million faces per mesh and two million vertices across the evaluated snapshots. Two local jobs may run simultaneously. The default timeout is 30 minutes, configurable from 30 seconds to two hours.

Texture atlases plus coverage images have a combined 32-megapixel budget across the job. All five maps fit at 2048 pixels for one object; larger batches may need lower resolution or separate jobs. Hosted artifacts have an aggregate 512 MiB download limit. Sources are preserved when a limit is exceeded or a worker fails.

The deterministic retopology tests use isolated Blender fixtures for cleanup and shape-key preservation, both remeshing methods, texture values and HDR emission, projection coverage, real FBX and GLB imports, approval isolation, cancellation, timeout, stale-result refusal and partial-import rollback. Hosted API contracts use offline transports and consume no provider credits.
