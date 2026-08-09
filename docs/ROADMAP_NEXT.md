# Next On The Roadmap

Last updated 2026-08-09, after the local generation/modeling backend batch on
`main`. This supersedes the 2026-08-05 note written after the live
character-reference evaluation.

Findings referenced as F1-F26 live in
`test-artifacts/sculpt-eval-20260803/IMPROVEMENTS.md` (local only, gitignored);
the architecture decisions are in
`docs/adr/ADR-001-generation-provider-layer.md`.

---

## 0. Current State

Done since the 2026-08-05 roadmap:

- `main` is pushed and matches `origin/main`; the old "push `a58f78e`" item is
  obsolete.
- `CONTEXT.md` now fixes shared vocabulary for the bridge, MCP server, gateway
  tools, reference sheets, calibrated guides, blockouts, visual hulls, part
  graphs, feature stacks, and silhouette conformance.
- ADR-001 Decision 1 held: generation reuses the shared `asset_jobs` lifecycle
  instead of getting a second async job system.
- The generation tool surface now has its own registry domain:
  `get_generation_provider_diagnostics`, `set_generation_policy`,
  `plan_image_to_3d_approach`, `start_generation_job`, and
  `get_generation_job_status`.
- Tripo has the first hosted generation job backend. It uses the shared
  subprocess worker, spend approval, status polling, cache manifest, and import
  tail.
- Credentials no longer go to `userpref.blend`. Provider keys are moved from
  entry fields into session memory and, when remembered, into the OS credential
  store or a user-readable-only fallback file.
- `border_flood` reference masks handle the light-subject-on-light-backdrop case
  that `luminance` and `background_color` both got wrong.
- Partial and mislabelled view sets now warn before and after generation starts.
- Stale add-on source now leads bridge status instead of hiding among sibling
  diagnostic fields.
- Hosted generation checks account balance in the worker before upload where
  the provider exposes balance, so a short account fails before reference art
  leaves the machine.
- Meshy adds a second hosted third-party backend. Local/self-hosted generation
  now covers both TripoSR as a direct local process and the studio endpoint as
  a local/LAN HTTP inference service.
- Local generation diagnostics now require both a Python interpreter and a
  checkout/root for local-process providers. Hunyuan3D and TRELLIS remain
  strategy-level providers until their concrete launchers are added.
- Visual hulls can now be resolved by explicit world-unit `cell_size`, not only
  by longest-axis `resolution`.
- Generic character part graphs now split a single primary mass into body,
  head, left/right arms, and left/right legs when head/body were not explicitly
  labeled.
- The reference benchmark now reports `conformance_diagnosis` as `conformant`,
  `area_difference`, or `shape_drift`, and states that pose/area differences
  should not be chased as shape errors.
- `inspect_modeling_quality` counts only edges shared by more than two faces as
  non-manifold; boundary edges are reported separately.
- The generation/modeling batch is committed locally as
  `Add generation provider backends and modeling fixes`.
- A real local TripoSR direct-process smoke passed against the sibling TripoSR
  checkout using a workspace-local Python 3.11 runtime with the existing
  Torch/CUDA dependencies. The wrapper now pre-creates TripoSR's indexed
  output folder before export, and the run produced `generated.glb` plus a
  standard asset manifest under `../outputs/triposr-smoke-20260809-2`.
- The live Blender 5.1 bridge now has TripoSR runtime paths configured for this
  session. `start_generation_job` launched TripoSR as a background generation
  job, wrote a fresh manifest under
  `../outputs/triposr-bridge-smoke-20260809`, imported that manifest back into
  Blender, passed `inspect_modeling_quality`, captured nonblank viewport
  evidence, and committed the preview.
- Follow-up TripoSR quality improvements are implemented: imports apply and
  record a provider-specific X -90 / Z +90 normalization, `start_generation_job` exposes
  TripoSR's extraction/background/texture knobs, TripoSR manifests and planning
  output label the route as local blockout quality, and the tool surface now
  includes `cleanup_generated_asset` plus `evaluate_generated_asset` for
  post-import cleanup, topology/material/component/metadata-aware orientation
  checks, optional front/side/top inspection renders, and single-view
  relief-shell warnings.

Focused verification on 2026-08-09:

- `python -m unittest tests.unit.test_reference_image_masks tests.unit.test_generation_job tests.unit.test_reference_benchmarks`
- Result: 35 tests passed.
- `python -m unittest tests.unit.test_generation_clients tests.unit.test_generation_job tests.unit.test_generation_providers tests.unit.test_generation_preferences tests.unit.test_asset_job_worker`
- Result: 136 tests passed.
- `python -m unittest tests.unit.test_visual_hull tests.unit.test_reference_parts`
- Result: 13 tests passed.
- `python -m unittest tests.unit.test_tool_registry tests.unit.test_tool_surface tests.unit.test_asset_job_worker`
- Result: 23 tests passed.
- `python -m unittest tests.unit.test_generation_clients tests.unit.test_generation_job tests.unit.test_generation_providers tests.unit.test_generation_preferences tests.unit.test_asset_job_worker tests.unit.test_visual_hull tests.unit.test_reference_parts tests.unit.test_tool_registry tests.unit.test_tool_surface`
- Result: 168 tests passed.
- `python -m unittest tests.unit.test_generation_job`
- Result: 19 tests passed after the TripoSR indexed-output regression fix.
- Live bridge smoke: `start_generation_job(provider="triposr")` with the local
  TripoSR sample chair completed as job `20260809-155544-b96c546d`; import job
  `20260809-155639-81c7489c` created `geometry_0.001`, and modeling quality
  passed with 42,078 vertices, 84,160 triangular faces, one material slot, no
  loose geometry, and no non-manifold edges.
- `python -m unittest tests.unit.test_generation_quality tests.unit.test_generation_clients tests.unit.test_generation_job tests.unit.test_generation_providers tests.unit.test_generation_preferences tests.unit.test_asset_job_worker tests.unit.test_tool_registry tests.unit.test_tool_surface tests.unit.test_external_asset_network`
- Result: 165 tests passed after the TripoSR quality-control/tool-surface
  batch and live-orientation regression fix.
- `python -m unittest <all unit modules except test_credential_store>`
- Result: 461 tests passed, 1 skipped. The credential-store suite was not run
  under escalation because it deletes/writes real remembered provider-key files
  under the user's home directory.

---

## 1. Immediate Next

1. **Run Tripo test 2: multi-view generation.** Single-view generation succeeded
   end to end at about 30 credits in roughly two minutes. The multi-view path is
   implemented and unit-covered but has not had the saved `NurseGuides` live
   test. Rebuild `NurseGuides` from the saved masks first if the result is to be
   scored.
2. **Run live smoke on the newly wired generation routes where credentials and
   runtimes exist.** Meshy is unit-covered only. TripoSR has real
   checkout/interpreter worker smoke and live bridge import evidence. The studio
   endpoint still needs a real local/LAN server smoke.
3. **Decide the next release shape.** `0.5.0` is in the changelog and code, but
   there is no local `v0.5.0` tag. Either tag/package the current release state
   or roll the post-`0.5.0` fixes into a `0.5.1` release candidate and run the
   release smoke.

---

## 2. Finish The Generation Layer

The shipped path is: provider diagnostics -> plan route -> optional session
policy -> provider job start -> shared asset-job polling -> cached generated
model -> shared import/presentation tail.

Done in this batch:

- **Hosted third-party generation.** Meshy is implemented with data-URI image
  upload, single-image and multi-image task creation, balance preflight, status
  parsing, model URL extraction, and secret redaction tests.
- **Local/self-hosted generation.** TripoSR and the studio endpoint are the two
  first execution contracts under this umbrella. TripoSR is a direct
  `local_process` worker that validates one view, requires a runtime Python and
  checkout root, captures stdout/stderr logs, finds the generated mesh, and
  emits the standard asset manifest. The studio endpoint is `local_http`: an
  optional bearer token, `POST /image-to-3d`, `GET /tasks/{id}`, optional
  `GET /balance`, provider-neutral model URL parsing, and the same shared
  manifest tail.
- **Provider parity tests.** Pure unit coverage now checks Meshy/studio request
  shape, non-leaking errors, generation-job provider preservation, balance-dict
  preflight, TripoSR missing-runtime refusal, and worker dispatch parity.

Remaining provider work:

- **Hunyuan3D / TRELLIS local/self-hosted backends.** These remain the
  higher-VRAM local routes. Hunyuan3D-2mv is still the most natural fit for
  calibrated front/back/left/right reference sheets, but the development GPU is
  below the expected floor. The registry now models their Python/root
  requirements, but no direct launcher exists. They could also be exposed behind
  the studio endpoint contract if a network inference server owns the runtime.
- **Credential forwarding generalisation.** MCP-side credential forwarding is
  still hard-coded to Sketchfab. Generation currently uses Blender-side
  session/OS credentials; only generalise this if client-held generation or
  studio-endpoint credentials need to be forwarded through the MCP server.
- **Live parity evidence.** TripoSR now has real-runtime worker smoke,
  bridge-launched generation, manifest import, topology inspection, viewport
  evidence, preview commit evidence, import orientation normalization,
  cleanup/evaluation helpers, and public extraction/texture knobs. Meshy and
  the studio endpoint still need provider-specific live smokes for
  cancel/recovery behaviour, import provenance, and real output compatibility.

---

## 3. Reference And Modeling Defects Left

**F14 residue.** Manifold dual contouring took the seven-node lamp from 140
pinched edges to 2 and fixed every diagnostic case. The remaining 2 are likely
patches meeting across a cell boundary rather than within one cell, which is a
different mechanism from the one already handled. Uniform meshing remains
correct for every case.

**32-node programs exceed the SDF work-unit limit.** Pre-existing and verified
against the previous commit. A 32-node character program cannot compile in
adaptive mode at all. Either the budget needs raising or the evaluator needs to
be cheaper per sample.

**F5: guides calibrate the frame, not the subject.** `plane_height` maps to the
image frame, so reference sheets that are not identically framed land at
different world scales. Measured spread on a real three-view set: 0.9735 /
0.9622 / 0.9504 subject-height-to-frame. The bridge still needs a subject-scale
warning or calibration mode.

**F6 hull resolution.** The `cell_size` route is implemented and unit-covered,
so callers can ask for predictable world-unit resolution. Still optional:
budget-derived defaults or a per-axis triple if the automatic path should pick
better resolution without caller input.

**F7 automatic semantic parts.** Generic characters now get body/head/arm/leg
defaults from a single primary mass, matching the earlier cute-quadruped path.
Still optional: broader decomposition for props, garments, vehicles, and other
non-character subjects.

**Reference benchmark structural term.** The benchmark is now honest about
scope and no longer claims to be an overall model-quality verdict. What remains
is optional but valuable: add an editability/topology/structure term if the
benchmark should rank usable candidates, not only reject wrong silhouettes.

**F18-F20: shape-program expressiveness.** Only `ellipsoid`, `box`, and
`superquadric` have non-circular cross-sections, so limbs and garments built
from `sweep` or `capsule` inflate. Booleans are global, so a cut meant for one
part carves everything in that volume. Stacked primitives silently disconnect
when they do not overlap, and nothing reports component count.

---

## 4. Untested Or Under-Tested Surface

These areas need live or packaged evidence before being used as launch claims:

- Tripo multi-view generation using the saved character reference set.
- Meshy hosted generation and studio-endpoint local/LAN generation.
- Clean install from a packaged zip on a fresh machine.
- Blender 4.2 and 4.5 installed-extension smoke. The code has compatibility
  work, but this release state still needs fresh evidence.
- Any subject that is not the evaluated character.
- Feature-stack live quality: `create_eye_stack`, `create_muzzle_stack`,
  `create_ear_stack`.
- Part-derived grooming in a live scene:
  `create_part_weight_vertex_groups` and `create_fur_flow_field_from_parts`.
- `create_multiview_depth_surface`, `adaptive_remesh`, and `edit_mesh` on a real
  reference-derived model.
- The lower-level semantic sculpt tools outside the scripted repair loop.

---

## 5. Launch Posture

The former blocker is fixed: stale source no longer looks healthy. It leads
bridge status with `BLOCKED:` and a concrete reload/restart remedy.

**Lead with**: image-to-3D generation, script trust, checkpoints, preview
commit/revert, evidence capture, provider diagnostics, source-staleness
detection, and the honest measurement story. These are the strongest, most
reliable surfaces right now.

**Do not lead with**: the sculpt repair loop, adaptive shape programs, or
automatic semantic decomposition. They are improving, but they still have known
quality and convergence limits.

**Strongest demo**: a hand-authored blockout beside a generated model from the
same reference image. One took a session of authoring and produced a mannequin;
the other took about two minutes and one paid Tripo job and produced a character
with face, hair, clothing, and local detail.
