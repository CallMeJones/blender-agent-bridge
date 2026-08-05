# Next On The Roadmap

Written 2026-08-05, after a live evaluation session against a real character
subject. Findings referenced as F1-F26 live in
`test-artifacts/sculpt-eval-20260803/IMPROVEMENTS.md` (local only, gitignored);
the architecture decisions are in `docs/adr/ADR-001-generation-provider-layer.md`.

---

## 0. Immediate, before anything else

1. **Push `a58f78e`.** It is committed locally but the push failed on DNS
   (`Could not resolve host: github.com`). Run `git push origin main`.
2. **Reload scripts in Blender, then restart the MCP client.** Three commits
   changed the registry digest, so the running MCP server is stale and mutating
   calls will be refused until it restarts. The status tool now says so loudly.
3. **Run Tripo test 2.** Single-view generation succeeded end to end (30
   credits, ~2 minutes, a genuinely good character). The multi-view run has
   never been executed. `NurseGuides` must be rebuilt from the saved masks
   first if the result is to be scored.

---

## 1. Finish the generation layer

The Tripo path works end to end. Everything else in the provider table is
declared but has no job backend, so `job_implemented` is False and those
providers are reported for planning yet never selected.

- **Meshy provider.** Second hosted backend; validates that the provider
  abstraction is not accidentally Tripo-shaped.
- **TripoSR provider.** The local path. The environment already exists at
  `.venv-tripo` with a working scikit-image shim for `torchmcubes`. Wiring it
  makes the local-first routing rule meaningful rather than theoretical.
- **Hunyuan3D / TRELLIS.** Need more VRAM than the 8 GB development card.
  Hunyuan3D-2mv is the architecturally correct fit for calibrated multi-view
  reference sheets and is the most interesting untested option.

ADR-001 action items still outstanding:

- **Item 5-6: session-scoped credentials.** API keys currently persist in
  `userpref.blend` in plain text. The repo already has a session-only pattern
  (`external_assets.set_session_sketchfab_api_token`); generalise it into a
  keyed store and make persistence an explicit opt-in. Two policies for one
  class of secret, with the newer one weaker, is the actual defect.
- **Item 7: generalise MCP credential forwarding.** `SKETCHFAB_AUTH_FORWARD_TOOLS`
  is a hard-coded set. A `{tool: credential_spec}` table would let a locked-down
  studio keep keys in the MCP client config and out of `userpref.blend`.

---

## 2. Open defects

**F14 residue.** Manifold dual contouring took the seven-node lamp from 140
pinched edges to 2, and fixed every diagnostic case. The remaining 2 are likely
patches meeting *across* a cell boundary rather than within one cell, which is a
different mechanism from the one now handled. Uniform meshing remains correct
for every case.

**32-node programs exceed the SDF work-unit limit.** Pre-existing, verified
against the previous commit rather than assumed. A 32-node character program
cannot compile in adaptive mode at all. Either the budget needs raising or the
evaluator needs to be cheaper per sample.

**F12: the reference benchmark prefers unusable models.** Silhouette IoU ranked
a lumpy voxel column at 0.926 and a clean sculptable base mesh at 0.557, because
the hull is built from the same silhouettes it is scored against. The docs tell
agents to use this score to decide the next correction, so as it stands it
advises discarding the useful model. Needs either a structural term or an honest
renaming; it is not an overall quality verdict.

**F5: guides calibrate the frame, not the subject.** `plane_height` maps to the
image frame, so reference sheets that are not identically framed land at
different world scales. Measured spread on a real three-view set: 0.9735 /
0.9622 / 0.9504 subject-height-to-frame. Nothing warns.

**F6: hull resolution is measured on the longest bounds axis.** For a standing
figure that is height, so the body cross-section got 19x21 cells at the maximum
setting -- 2.3 cm voxels on a 1.7 m figure -- while using 6% of the cell budget
and 15% of the edge budget. Derive resolution from the budget, or accept a
per-axis triple or a `cell_size`.

**F7: the automatic path produces no semantic parts.** `prepare_reference_images`
emits exactly one mass, so `create_reference_part_graph` returns one generic
part and seven downstream part tools are inert. Hand-authored `part_hints` work
correctly. Either generate candidate parts or say plainly that decomposition is
the client's job.

**F18-F20: shape program expressiveness.** Only `ellipsoid`, `box` and
`superquadric` have non-circular cross-sections, so limbs and garments built
from `sweep` or `capsule` inflate. Booleans are global, so a cut meant for one
part carves everything in that volume. Stacked primitives silently disconnect
when they do not overlap, and nothing reports the component count.

---

## 3. Untested surface

Roughly 14 tools were never exercised in the evaluation:

- feature stacks: `create_eye_stack`, `create_muzzle_stack`, `create_ear_stack`
- `create_part_weight_vertex_groups`, `create_fur_flow_field_from_parts`
- `create_multiview_depth_surface`, `adaptive_remesh`, `edit_mesh`
- the six lower-level semantic sculpt tools

Also untested: install from a packaged zip on a clean machine, Blender 4.2 and
4.5, and any subject that is not this one character.

---

## 4. Launch readiness

The blocking issue is fixed: a stale MCP config used to look healthy and only
fail on the first mutating call. Status now leads with `BLOCKED:` and a remedy.

**Lead with**: image-to-3D generation, and the bridge fundamentals -- script
trust, checkpoints, preview commit/revert, evidence capture, source-staleness
detection. All of these behaved correctly throughout a long adversarial session.

**Do not lead with**: the sculpt repair loop or adaptive shape programs.
Repair now protects itself from destroying a mesh but still will not converge,
and adaptive mode has a known residue on programs with touching surfaces.

**The strongest demonstration** is the comparison itself: a hand-authored
blockout beside a generated model from the same reference image. One took a
session of authoring and produced a mannequin; the other took two minutes and
30 credits and produced a character with a face, hair and a garment pocket.
