# Meshy Multi-Image Vehicle Evidence

Date: 2026-08-11

Runtime: Blender 5.1.2 with an installed development extension

![Front, side, rear, and top inspection renders of the generated vehicle](meshy-vehicle-multiview-contact-sheet.jpg)

## Scope

This sanitized record documents one paid Meshy multi-image run using four
brand-free vehicle references. It exercised Blender-side spend approval,
four-image upload, provider polling, GLB caching, preview import, sanitized
provenance, semantic orientation review, material preservation, and isolated
front/side/rear/top evaluation.

Provider task IDs, local job IDs, approval IDs, signed URLs, cache paths, API
keys, and source-machine paths are intentionally omitted. The 59 MB generated
GLB and original references are not distributed in Git.

## Result

- Provider route: Meshy multi-image-to-3D
- Reference count: four
- Provider generation time: 181 seconds
- Credits consumed: 30
- Cached GLB size: 59,178,680 bytes
- Material: one Principled BSDF texture-atlas material using one image texture
  and one UV map
- Relief-shell warning: false

The imported vehicle contains coherent front, side, rear, and top structure,
including four wheels, arches, mirrors, rails, bumpers, windows, and lights.
The tracked contact sheet is the semantically normalized state after applying
the orientation correction to the mesh.

## Topology Findings

The raw import contained:

- 1,055,939 vertices
- 1,966,800 triangular faces
- 1,754 disconnected components
- 141,570 boundary edges
- 0 non-manifold edges
- 0 loose edges and 0 loose vertices

A material-preserving, non-destructive 0.15 Decimate working state reduced the
evaluated result to 295,020 triangles while retaining the recognizable
silhouette and major features. It did not repair the underlying component
fragmentation and introduced 32 evaluated loose edges.

## Assessment

This is positive live evidence for the complete paid multi-image provider path
and for a coherent non-character result. It is suitable as a textured concept
or blockout and as a source for retopology. It is not evidence that provider
output is automatically edit-ready production topology.

The source contact sheet was exported by the bridge evaluation workflow and
compressed to JPEG for repository documentation. Its SHA-256 is
`9a68a0eec51c04d6fad849d666ae948017e38943213b769d41cb57c66c28713a`.
