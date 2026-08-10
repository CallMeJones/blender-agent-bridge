# Next On The Roadmap

Last updated 2026-08-10, after the texture-baking, shape-program expressiveness,
and live-validation batch on `main`. This supersedes the 2026-08-05 note written
after the live character-reference evaluation.

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
- A non-chair live run generated a ceramic teapot from one image as job
  `20260809-172650-4846d0f5`, imported it through job
  `20260809-175020-7683fba6`, and captured isolated front/side/top evidence.
  This exposed and fixed a real orientation regression: TripoSR GLB roots use
  quaternion rotation mode, so writing only `rotation_euler` left the asset
  unchanged. Import normalization now composes the object matrix and preserves
  the root rotation mode.
- A paid hosted Tripo multi-view run completed as generation job
  `20260809-180656-8e8e1314` / provider task
  `2526945b-a7fc-45b4-ab38-5b762d149b94` from front and left character views.
  It consumed 30 credits and produced a 41.9 MB PBR GLB plus a standard
  manifest under `../outputs/tripo-multiview-live-20260809`.
- The exact hosted Tripo GLB imports successfully in a clean Blender 5.1.2
  process in 2.05 seconds, with one Tripo mesh and three 2048-square PBR
  images. A post-restart interactive import then completed as job
  `20260809-191842-12d82f5b`; the bridge remained connected, the object retained
  provider/key/source provenance, and the historical manifest was sanitized so
  the stored source URL contains no signed query string.
- TripoSR runtime paths and six tuning defaults are persistent add-on
  preferences. Job arguments remain one-run overrides. The restart audit found
  the earlier session-only paths had never been saved; the verified interpreter,
  checkout, and conservative defaults are now explicitly written to Blender's
  `userpref.blend`. A fresh Blender 5.1.2 application restart restored both
  paths plus `256 / false / 0.85 / 8192 / false / 2048`, and provider
  diagnostics reported TripoSR runnable without re-entry.
- A live TripoSR cancellation test exposed an orphaned descendant inference
  process. Workers and direct local inference now launch in isolated process
  groups, cancellation/timeout kills the full tree, and a real Windows
  parent-plus-child regression test verifies both PIDs exit. The post-fix live
  rerun cancelled high-resolution job `20260809-191508-b3285306` after it reached
  the local process, and a process-table check found zero surviving TripoSR
  descendants. Recovery job `20260809-191643-48533a07` then completed in 17
  seconds and imported through job `20260809-191705-6be322d0`.
- Hosted manifests no longer persist temporary signed download query strings;
  the full URL exists only long enough to download the asset.
- Generated-asset evaluation now isolates each target from unrelated renderable
  meshes, restores every prior visibility state, and publishes front/side/top
  PNGs plus a contact sheet. Blender 5.1 smoke proved isolation with an
  oversized overlapping mesh. Live hosted Tripo evaluation exposed a 1.46M-face,
  104-component asset and an Eevee front/side render failure; the evaluator now
  flags excessive density and fragmentation, retries failed views in Workbench,
  and reports incomplete evidence when a fallback also fails.
- The live Meshy teapot exposed two evaluator defects: wide objects were treated
  as misoriented when Z was not their longest axis, and an unlit scene made its
  pale ceramic texture render nearly black. Orientation failures are now limited
  to providers with a known missing transform (such as raw TripoSR), and
  inspection renders use temporary three-point lighting with full restoration.
  Reload Scripts also omitted the generation domain entirely; the reload lists
  are fixed and protected by a complete modular-domain inventory test.
- The post-fix interactive Reload Scripts proof passed. Blender reported the
  loaded source current, Meshy was classified upright, the 1,182-component
  fragmentation warning appeared, and all front/side/top Eevee views completed
  under temporary lighting without fallback or incomplete evidence.
- A clean temporary-profile installed-extension smoke passed on Blender 5.1.2:
  official ZIP build/install, interactive UI, workflow sweep, viewport and
  playblast evidence, bundled MCP, doctor, and packaged MCPB. Artifact SHA-256:
  `1e6fbbed9c807c578a6321f75af8f15b4a0ac98df01ae0a29005935628903162`.
- F5 subject calibration is implemented. Annotated/prepared guides can map a
  detected silhouette or explicit normalized subject bounds to a requested
  world-space `subject_height`; frame-scale mode reports estimated subject
  height and warns when vertical views differ by more than 2%.
- The reference benchmark has an optional structural term from
  `inspect_modeling_quality`. It independently gates loose/non-manifold
  geometry and an optional face budget, then requires silhouette and structure
  for a combined pass while retaining the non-overall-verdict warning.
- TripoSR texture baking is now live-proven on CUDA. A compatibility runner fixes
  mixed CPU/CUDA texture sampling and converts xatlas's OBJ atlas payload into a
  real GLB with its texture embedded. Blender 5.1.2 imported the resulting
  1.07 MB teapot GLB with one material, one packed 512-square image, provider
  provenance, and the exact X -90 / Z +90 normalization.
- Representative 32-node adaptive shape programs now fit the bounded evaluator:
  the SDF ceiling is 64 million work units and parent transforms are cached once
  per sample. F18-F20 are implemented with elliptical capsule/sweep sections,
  targeted booleans, and disconnected-component reporting.
- Blender 5.1.2 live smokes passed for eye/muzzle/ear feature stacks,
  part-derived weight groups and fur flow, multi-view depth surfaces,
  `adaptive_remesh`, `edit_mesh`, lower-level semantic sculpt tools, and all
  retained adaptive-manifold diagnostics at maximum depths 7, 8, and 9.
- Meshy provider-side cancellation is implemented and live-proven: generation
  task ids and task kinds survive restart metadata, and the shared cancel tool
  calls Meshy's single-image or multi-image DELETE endpoint before stopping the
  local worker. Terminal recovery now also ignores stale child progress so the
  cancelled message and cancellation-request flag remain authoritative.
- Paid hosted-generation decisions are now observable without a chat round trip.
  The start refusal returns a request id and polling contract;
  `get_generation_approval_status` reports Approve, Decline, expiry, or prior
  consumption. Tripo and Meshy use it, while local TripoSR remains outside the
  spend gate. A live Blender 5.1 session detected a real Tripo Decline decision
  through polling without the user reporting the click, and no provider job was
  submitted.
- Non-character coverage now includes a second category. A hard-surface red desk
  fan generated locally through TripoSR in 14 seconds and imported through the
  clean installed extension with 13,312 vertices, 26,620 manifold triangles,
  two components, stable provenance, and the expected Z-up normalization. The
  evaluator correctly classified its vertex-color material and warned that one
  view cannot establish the cage/motor structure on the unseen side.

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
- `tests/smoke_external_asset_imports.py` passed in Blender 5.1 after adding a
  quaternion-mode TripoSR orientation regression case. The ceramic-teapot
  production import reports quaternion `(0.5, -0.5, -0.5, 0.5)` and renders
  upright from front, side, and top.
- `python -m unittest <all unit modules except test_credential_store>`
- Result: 461 tests passed, 1 skipped. The credential-store suite was not run
  under escalation because it deletes/writes real remembered provider-key files
  under the user's home directory.
- Consolidated provider/calibration/benchmark/tool-surface regression run:
  194 tests passed.
- `tests/smoke_external_asset_imports.py` passed on Blender 5.1.2 with target
  isolation, contact-sheet generation, visibility restoration, and the TripoSR
  quaternion orientation case.
- `tests/smoke_advanced_helpers.py` passed on Blender 5.1.2 with subject-scale
  metadata, multi-view reconstruction, structural reference benchmarking, and
  rollback.
- `scripts/installed_extension_live_smoke.py` passed from a clean temporary
  Blender 5.1.2 profile with the official extension builder and packaged MCPB.
- Focused post-restart regression run: 20 registry, benchmark-manifest, and
  process-tree tests passed; `tests/smoke_external_asset_imports.py` passed on
  Blender 5.1.2 with the new heavy-mesh findings and renderer-fallback checks.
- Current post-Meshy regression run: 478 unit tests passed with one intentional
  skip (credential-store tests excluded to protect remembered provider keys),
  release consistency/tool-contract/bridge-protocol gates passed, and the
  generated-asset Blender 5.1.2 smoke passed. A freshly built extension ZIP and
  MCPB also passed the clean temporary-profile installed-extension workflow and
  both bundled doctor paths on Blender 5.1.2.
- Current provider-choice/isolation regression run: 483 unit tests passed with
  the same intentional credential-store skip; release consistency,
  tool-contract, and bridge-protocol gates passed. Generation-job and trusted
  script Blender 5.1.2 smokes passed, including scripts/helpers under a disabled
  generation policy and explicit TripoSR/Tripo/Meshy choice without starting a
  job. A fresh extension ZIP and MCPB passed the complete clean temporary-profile
  install, workflow, gateway, and doctor smoke on Blender 5.1.2. The interactive
  bridge also live-refused an omitted provider while all three routes were ready;
  a reload-inventory regression now keeps the provider policy module current.
- Published `v0.5.3` on 2026-08-09 after 503 unit tests, clean installed-extension
  smoke on Blender 4.2.0, 4.5.0, and 5.1.2 locally and in tagged Linux CI, official
  ZIP/MCPB validation, PyPI publication, GitHub release publication, byte-identity
  checks against retained candidates, and a fresh install through the public
  Blender extension repository.
- 2026-08-10 focused generation/modeling verification: 69 generation-client,
  generation-job, and worker tests passed; 26 uniform/adaptive shape-program
  tests passed. Blender 5.1.2 passed the baked-TripoSR installed import smoke and
  the selected feature-stack, grooming, advanced-helper, semantic-sculpt, and
  adaptive-manifold suites.
- A fresh 0.5.4 clean-profile package passed the installed extension, interactive
  UI, workflow sweep, five-tool MCP, bundled doctor, MCPB build, MCPB doctor, and
  installed MCP smokes on Blender 5.1.2. The final post-recovery-fix retained
  artifacts are byte-identical to the smoke-built candidates: extension ZIP
  SHA-256 `e14c9b6e475726f1f14e4d2ea7910078a25f83df4fbdfe1276ca9589851024e9`
  and MCPB SHA-256
  `7c47dd10eefc2d17cbbe6e4435bfae67f4b6b406b77f8b3d2f2ded991844c033`.
- Meshy provider-side cancellation is live-proven from the installed Blender
  5.1.2 extension. Generation job `20260810-101631-e24fdcb8` persisted remote
  image task `019feabe-b4da-72fb-8786-0f2e86cea48b`, Meshy acknowledged its
  provider DELETE, and the terminal cancelled job retained the task kind, task
  id, and successful remote-cancellation receipt. After Reload Scripts and a
  bridge restart, the historical-session locator recovered the same job with
  `cancel_requested: true` and the canonical cancelled message; no second paid
  provider request was made.

---

## 1. Immediate Next

1. **Supply a real studio endpoint when available.** The contract and job path
   are implemented, but live local/LAN evidence remains blocked by no configured
   service URL.
2. **Recreate or recover the exact F14 lamp fixture.** Every retained adaptive
   manifold diagnostic passes, but the historical two-edge residue cannot be
   closed algorithmically without its seven-node program.
3. **Broaden reference subjects and decomposition.** Add live vehicle, garment,
   and hard-surface/prop cases, then extend F7 semantic-part defaults beyond
   characters where those cases justify it.
4. **Add Hunyuan3D/TRELLIS launchers when suitable hardware or a studio service
   is available.** Their readiness strategy exists; direct execution does not.
5. **Finish current-candidate install coverage.** The final post-recovery 0.5.4
   artifact is clean-profile proven on Blender 5.1.2. Re-run that exact candidate
   on Blender 4.2/4.5 in release CI, then complete one genuinely separate-machine
   clean install; earlier 4.2/4.5/5.1 evidence predates these final fixes.

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
- **Provider choice and bridge isolation.** The planning tool asks which provider
  to use whenever multiple runnable routes are ready, and the job-start tool
  independently refuses to guess if a caller skips planning. A sole local route
  may auto-select; a hosted route never does. Generation egress/session policy
  remains scoped to generation, with Blender smoke coverage proving trusted
  scripts and bounded modeling helpers still run when generation is disabled.

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
- **Live parity evidence.** Tripo single-view and multi-view generation are now
  live-proven, and the multi-view GLB imports in both a clean Blender process and
  the interactive bridge while preserving sanitized provenance. TripoSR has real
  generation/import/evaluation plus post-fix descendant-tree cancellation and
  recovery evidence. Meshy single-view generation and import are live-proven by
  teapot job `20260809-194518-7ad7f3e4`: it completed in 129 seconds, consumed 30
  credits, cached a 2.96 MB textured GLB, and imported with stable Meshy
  provenance. Its evaluation found 10,259 faces and 1,182 disconnected
  components, so provider plumbing passes while editability quality does not.
  Meshy provider cancellation/recovery is now unit-covered and live-proven:
  task identity survived into recoverable metadata before the installed bridge
  sent and recorded a successful provider-side cancellation, and the terminal
  record was recovered from a prior capture session after Reload Scripts.
  Studio endpoint remains contract/unit-covered and blocked by no configured
  service.
- **TripoSR texture baking (done).** CUDA texture baking, atlas-to-GLB conversion,
  strict GLB payload validation, packed material import, provenance, and
  orientation normalization are live-proven on the ceramic teapot.

---

## 3. Reference And Modeling Defects Left

**F14 residue.** Every retained cavity-breakthrough case is manifold at adaptive
maximum depths 7, 8, and 9, and targeted booleans now prevent one common source
of unrelated cuts. The historical seven-node lamp improved from 140 pinched
edges to 2, but its exact program was not retained. Recreate that fixture before
claiming the final cross-cell residue is solved. Uniform meshing remains the
documented fallback.

**32-node SDF budget (done).** Parent transforms are evaluated once per sample,
identity transforms add no work, and the bounded ceiling is now 64 million SDF
work units. A representative 32-node transformed program is regression-covered
within the one-million adaptive-sample ceiling.

**F5 subject calibration (done).** `subject_height` now maps silhouette-derived
or explicit normalized subject bounds to a shared world height. Keeping the old
frame-height mode records the estimated subject height and emits a multi-view
spread warning above 2%.

**F6 hull resolution.** The `cell_size` route is implemented and unit-covered,
so callers can ask for predictable world-unit resolution. Still optional:
budget-derived defaults or a per-axis triple if the automatic path should pick
better resolution without caller input.

**F7 automatic semantic parts.** Generic characters now get body/head/arm/leg
defaults from a single primary mass, matching the earlier cute-quadruped path.
Still optional: broader decomposition for props, garments, vehicles, and other
non-character subjects.

**Reference benchmark structural term (done).** Callers can opt into topology
integrity and face-budget gates from the existing modeling inspector. The
payload keeps silhouette and structural scores separate and still states what
is not measured.

**F18-F20 shape-program expressiveness (done).** Capsules accept an elliptical
`cross_section` plus rotation; sweeps accept width/depth and rotation per point.
Subtract/intersect nodes may target named earlier union nodes, while omitted
targets preserve global behavior. Uniform and adaptive results report component
count, face counts per component, and disconnected-component count. The strict
bridge schema exposes all five new fields.

---

## 4. Untested Or Under-Tested Surface

These areas need live or packaged evidence before being used as launch claims:

- Studio-endpoint local/LAN generation after a real service URL exists.
- Blender 4.2/4.5 clean-profile smoke for the final post-recovery 0.5.4 archive,
  plus one packaged install on a genuinely separate machine. Blender 5.1.2 is
  proven on this workstation.
- More non-character subjects. Ceramic-teapot runs now cover both local TripoSR
  and hosted Meshy, and a hard-surface desk fan now covers local TripoSR, but
  vehicles, garments, and larger asymmetric props remain untested.
- F6 automatic hull-resolution defaults or a per-axis cell-size triple, if live
  subject evidence shows the current explicit scalar `cell_size` is insufficient.
- F7 automatic semantic decomposition for props, garments, and vehicles, after
  broader live subjects establish useful category rules.

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
