# Blender Agent Bridge

A Blender add-on that lets external MCP clients inspect and change an open
Blender scene through bounded tools. This file fixes the vocabulary: the same
nouns appear in module names, tool descriptions, and conversations with agents,
and drift between them has already produced real defects.

## Language

**Bridge**:
The localhost HTTP service inside Blender that executes tool calls against the
live scene.
_Avoid_: server, API, backend

**MCP server**:
The separate stdio process an MCP client launches, which proxies to the Bridge.
_Avoid_: connector, adapter

**Gateway tool**:
One of the five tools an MCP client sees at the top level.
_Avoid_: top-level tool, exposed tool

**Helper**:
A bridge tool reached through the gateway rather than listed directly. There are
238 of these; only helpers do domain work.
_Avoid_: sub-tool, internal tool, function

**Preview transaction**:
A set of scene changes held for the user to commit or revert.
_Avoid_: staging, draft, pending change

**Script trust**:
A session-scoped permission, granted by a person in Blender, allowing
agent-authored Python to run.
_Avoid_: sandbox, permission, approval

## Language: reference modelling

**Reference sheet**:
The user's supplied artwork of a subject, one or more images.
_Avoid_: concept art, input image, source image

**View**:
One image of a reference sheet, occupying a named positional slot -- `front`,
`left`, `back`, `right`. The slot is positional, so a mislabelled view degrades
the result silently rather than erroring.
_Avoid_: angle, camera, side

**Calibrated guide**:
Scene geometry that places a **view** at a known world scale and orientation, so
renders can be compared against it.
_Avoid_: reference plane, backdrop, image empty

**Blockout**:
Coarse soft geometry derived from **calibrated guides**, standing in for the
subject before detail exists.
_Avoid_: base mesh, proxy, rough

**Visual hull**:
The volume carved by intersecting the silhouettes of several **views**. Its
shape is determined entirely by those silhouettes.
_Avoid_: hull mesh, carve, voxel model

**Part graph**:
A decomposition of a subject into named **parts** with relationships, inferred
from a **reference sheet** or supplied as hints.
_Avoid_: hierarchy, rig, skeleton

**Feature stack**:
A reusable builder that produces one recurring anatomical feature -- an eye, a
muzzle, an ear -- for attachment to a **part**.
_Avoid_: component, widget, preset

**Silhouette conformance**:
How closely a render's outline matches a **view**'s outline. Measured in image
space; says nothing about topology.
_Avoid_: quality score, accuracy, match score, IoU as a standalone noun

## Relationships

- A **reference sheet** holds one or more **views**, each in a positional slot
- Each **view** produces one **calibrated guide**
- Several **calibrated guides** produce one **visual hull**; one alone cannot
- A **blockout** or **visual hull** is measured for **silhouette conformance**
  against the **views** it was derived from -- the measurement is circular by
  construction, see Flagged ambiguities
- A **part graph** decomposes a subject; **feature stacks** attach to its parts
- **Script trust** gates agent-authored Python; a **preview transaction** gates
  what that Python changed

## Module naming

The reference modules follow a discipline that is easy to miss:

- A bare name is **pure** -- no `bpy`, directly testable, e.g.
  `reference_fitting`, `reference_metrics`, `reference_parts`
- A `_scene` suffix is the **Blender adapter** for a pure module, e.g.
  `reference_multiview_scene`, `reference_part_scene`
- `reference_surface_fitting` is the Blender adapter for `reference_fitting`,
  despite not carrying the suffix. This pair reads as duplication and is not.

Keep new modules on this split: put logic in the pure module so it can be
tested without launching Blender, and keep the adapter thin.

## Flagged ambiguities

- **"quality"** was used for two unrelated things: **silhouette conformance**
  (image-space outline agreement) and whether a mesh is actually usable
  (topology, editability, polygon budget). The benchmark measured only the
  first while its field was named `quality_score`, and the tool told agents to
  drive a repair loop on it. Measured consequence: a lumpy voxel column scored
  0.926 where a clean sculptable base mesh scored 0.557, because the column
  filled the **visual hull** more completely. Resolved: the metric is
  **silhouette conformance**, it can disqualify a wrong shape and must never
  rank two candidates, and the result payload now states that scope.

- **"available"** was used for two unrelated things: a generation provider being
  configured and capable, and a job for it being able to start. A provider with
  no job backend reported available with no blockers once its paths were set,
  then refused every job. Resolved: **available** means configured; **runnable**
  means a job can start.

- **"reference"** as a bare noun is ambiguous between the user's artwork and the
  scene geometry built from it. Use **reference sheet** for the artwork and
  **calibrated guide** for the geometry.
