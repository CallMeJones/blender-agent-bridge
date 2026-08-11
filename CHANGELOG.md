# Changelog

## Unreleased

### Reference modeling

- Closed the remaining adaptive dual-contouring cross-cell residue by splitting disconnected face fans only after local topology refinement is exhausted. A connected multi-point sweep/subtract regression now stays manifold at maximum depths 7, 8, and 9 and matches uniform-mode component structure.

### UI

- Refresh the Agent Bridge sidebar immediately after approving or revoking session script trust instead of waiting for the next mouse hover to trigger a redraw.

## 0.5.4 - 2026-08-10

### Generation

- Fixed local TripoSR texture baking across mixed CPU/CUDA tensor placement and converted xatlas OBJ-atlas payloads into real textured GLBs instead of accepting OBJ text mislabeled with a `.glb` suffix.
- Added a Blender import smoke for baked TripoSR assets that verifies the packed texture, material node, provider provenance, and X -90 / Z +90 orientation normalization.
- Persisted hosted generation task identity in recoverable job metadata and made the existing external-asset cancel path delete pending or in-progress Meshy image and multi-image tasks at the provider before terminating the local worker. Credentials remain session-only and are never added to job files.
- Live-proved Meshy provider-side cancellation and restart recovery from the installed Blender 5.1.2 extension: the job persisted its remote image-task identity before cancellation, Meshy acknowledged the provider DELETE, and a post-Reload Scripts lookup recovered the terminal job and remote cancellation receipt from its previous capture session. Terminal recovery self-heals stale child progress written by older builds.
- Added and live-proved `get_generation_approval_status`, which detected a real Blender Decline click while the client polled the exact request instead of asking the user to report it. Hosted Tripo and Meshy remain gated; local TripoSR remains approval-free. Approved requests now expire and include the paid texture choice in their single-use fingerprint.

### Reference modeling

- Raised the bounded SDF work allowance to 64 million operations and cached parent transforms per sample, allowing representative 32-node adaptive programs to compile within the existing sample ceiling.
- Added elliptical capsule and sweep cross-sections with oriented ellipsoidal end caps, targeted subtract/intersect booleans, and disconnected-component reporting to implicit shape programs, with the strict public tool schema updated to expose every new field.

### Live validation

- Passed Blender 5.1 live smokes for reference feature stacks, part-derived weight/groom flow, multi-view depth surfaces, adaptive remesh, edit-mesh helpers, lower-level semantic sculpting, and retained adaptive-manifold diagnostics at maximum depths 7, 8, and 9.
- Added a generic installed-extension generated-manifest evaluation smoke and used it on a hard-surface desk fan, covering import provenance, orientation normalization, topology, materials, components, and the expected single-view relief-shell warning.

### Release validation

- Bound public MCPB verification and release recovery to the retained tested-candidate sidecar instead of comparing against a cross-platform archive rebuild.
- Isolated installed-extension smoke subprocesses from ambient `PYTHONHOME` and `PYTHONPATH`, preventing a repository uv interpreter from injecting an incompatible standard library into Blender's bundled Python.
- Restored the pure-Python external-asset smoke after adding Blender-dependent recovery coverage by moving that probe into `smoke_generation_jobs` and running the generation smoke on ordinary pushes and release tags.

## 0.5.3 - 2026-08-09

### Release validation

- Installed the `uv` runtime dependency in tagged Linux Blender jobs before exercising the packaged MCPB connector.

## 0.5.2 - 2026-08-09

### Release validation

- Kept hosted installed-extension smoke focused on behavior that Xvfb can prove reliably: installation, live bridge workflows, rendered evidence inventory, bundled MCP, MCPB, and scene preservation. Direct viewport and playblast capture remain required in local interactive Blender release smoke, where real display pixels are available.

## 0.5.1 - 2026-08-09

### Routing

- Kept dynamic helper selection within its declared 32,000-character schema budget by making part-graph/base-mesh helpers optional for generic reference matching and the multi-view evaluator optional for single-view semantic sculpting. Explicit part, feature-stack, fur-flow, and multi-view requests still retain those helpers.

## 0.5.0 - 2026-08-09

### Generation

- Added first job backends for Meshy and for local/self-hosted generation. Meshy is the hosted third-party path; TripoSR direct local process and the studio HTTP endpoint are the two local/self-hosted execution contracts. All three reuse the shared external-asset job lifecycle, status polling, cache manifest, and import tail.
- Added Meshy request/status handling for image-to-3D and multi-image-to-3D, including balance preflight, GLB URL extraction, 402 credit handling, and secret redaction.
- Added a bridge-compatible local/self-hosted studio endpoint contract with optional bearer auth: `POST /image-to-3d`, optional `GET /balance`, and `GET /tasks/{id}`.
- Added local/self-hosted TripoSR execution via a configured Python interpreter and checkout root, with stdout/stderr capture and generated-mesh discovery.
- Fixed TripoSR local execution to create the indexed output folder expected by TripoSR's exporter before running the subprocess.
- Exposed TripoSR tuning knobs on `start_generation_job`: `mc_resolution`, `no_remove_bg`, `foreground_ratio`, `chunk_size`, `bake_texture`, and `texture_resolution`.
- Added persistent TripoSR defaults for those six controls in add-on preferences; explicit `start_generation_job` arguments still override the saved values for one run.
- Fixed generation cancellation and TripoSR timeout handling to terminate the complete worker descendant tree, preventing local inference processes from surviving a cancelled Blender worker. Timeout failures now report as timeouts instead of misleading process-start failures.
- Hosted generation manifests now retain stable source provenance without persisting temporary signed download query parameters.
- Marked TripoSR manifests and planning output as a local single-view blockout route rather than a final-quality route.
- Normalized TripoSR imports into Blender Z-up with a provider-specific X -90 / Z +90 root rotation recorded in the generated asset manifest; the correction now composes the object matrix so it also applies to GLB roots using quaternion rotation mode.
- Added `cleanup_generated_asset` for preview-safe generated mesh cleanup: shade smooth, Weighted Normal, optional Decimate, optional Voxel Remesh, and material preservation.
- Added `evaluate_generated_asset` for generated-output review: topology/material/component/metadata-aware orientation checks, isolated front/side/top inspection renders, an automatically published contact sheet, and single-view TripoSR relief-shell warnings. Temporary render visibility is restored even when capture fails.
- Hardened generated-output evaluation for hosted meshes: assets above 500,000 faces and assets with more than 32 disconnected components are called out explicitly, failed Eevee/Cycles inspection views retry through Workbench, and incomplete visual evidence contributes its own finding instead of silently returning an empty contact sheet.
- Limited automatic orientation failures to providers such as raw TripoSR that require a known import transform; bounding-box dominance for wide hosted subjects is now informational because it cannot establish semantic up direction.
- Added temporary deterministic three-point lighting to inspection renders and restore all prior light visibility afterward, preventing generated assets from being judged through an accidentally unlit scene.
- Tightened local provider diagnostics so local-process providers need both a Python interpreter and a checkout/root. Hunyuan3D and TRELLIS now expose that strategy-level readiness while remaining unimplemented launchers.
- Preserved provider identity through generation manifests and exposed a `texture` option on the public generation job schema.
- Kept generation policy and third-party egress controls isolated from the main bridge: disabling generation still leaves trusted scripts and bounded modeling helpers available. When more than one runnable generation provider is available, planning now asks the user to choose and direct job starts refuse to guess; a sole local/self-hosted provider may be selected automatically, while a hosted provider always requires explicit selection.

### Reference modeling

- Added explicit `cell_size` support to multi-view visual hull and depth-surface carving so callers can request world-unit resolution instead of only longest-axis subdivision.
- Added generic-character automatic part defaults. A single primary guide mass now produces body, head, left/right arm, and left/right leg parts when head/body were not explicitly labeled.
- Added optional subject-height calibration for annotated and prepared single/multi-view guides. Silhouette-derived bounds now map the subject, rather than the whole image frame, to a requested world-space height; frame-scale mode records estimated subject height and warns on cross-view scale spread.

### Reference intake

- Added a `border_flood` mask mode that treats whatever the image border can reach as background. It is the only mode that separates a light subject from a light backdrop: on a measured reference sheet the apron read rgb(0.92, 0.93, 0.94) against a rgb(1, 1, 1) backdrop, where `luminance` calls the apron and the backdrop both subject and `background_color` calls both background, deleting the uniform. Neither errors; both return a plausible mask. `auto` now reaches it instead of selecting `background_color` with no colour to supply and raising.
- Partial and mislabelled view sets now warn. Slots are positional, so a three-quarter image placed in `left` degrades the mesh rather than failing, and a missing slot is invented rather than omitted.

### Measurement honesty

- The reference benchmark now separates a wrong shape from a right shape posed differently. A character authored in an A-pose against a reference with clasped hands scored 0.666 silhouette IoU against a 0.72 threshold while mean edge distance held at 1.2-1.7%; the model was correct and the gate said otherwise. `conformance_diagnosis` reports `conformant`, `area_difference`, or `shape_drift`, and the area case states that a deliberate pose cannot pass the gate and should not be chased.
- Added an optional structural benchmark term backed by `inspect_modeling_quality`. It keeps silhouette and topology verdicts separate, gates loose/non-manifold geometry and an optional face budget, and requires both terms for a combined pass without claiming riggability or production topology.
- `inspect_modeling_quality` no longer counts boundary edges as non-manifold. bmesh reports them that way, which is true of the term and useless as a defect count: an open garment shell is meant to have a hem, and a caller clearing that number welds a skirt shut. Only edges shared by more than two faces count; boundary edges keep a separate count.

### Diagnostics

- Cleared orphaned live-preview UI state after add-on reload, disable, or Blender file load when the in-memory rollback transaction no longer exists, while preserving Commit/Revert controls for genuine pending transactions.
- Fixed Reload Scripts to refresh the generation provider policy, registry, and handler modules, with inventory tests that prevent the provider selector or future modular domains from being omitted from the reload order.

- Stale add-on source now leads the bridge status. It was already reported with the exact remedy, buried among sixty sibling fields, and a live session ran on old code while the status read "connected".
- A generation job now checks the account balance in the worker subprocess before uploading, so an account short of credits fails before the user's reference art leaves the machine rather than after.

### Documentation

- Expanded the README with a supported-provider showcase and setup guide for Poly Haven, Sketchfab, hosted Tripo/Meshy generation, and local TripoSR, including provider-choice, upload, spend-approval, provenance, and credential-storage behavior.
- Added `CONTEXT.md`, fixing the vocabulary shared by module names, tool descriptions, and agent conversations. Records the pure-module / `_scene`-adapter split, and the ambiguities that produced real defects.
- Recorded in ADR-001 that Decision 1 held: `asset_jobs` should not be split now that it carries both catalog downloads and paid generation.

### Release engineering

- Isolated credential-store tests to a temporary user-data root so local release verification cannot read, overwrite, or delete remembered provider keys.
- Added repository-wide Gitleaks defaults with a narrow rule-specific exception for benchmark metric keyword arguments, and required extracted artifact-content scans before publication.

### Credentials

- Routed every third-party provider key through one panel and one mechanism. Keys are held in memory for the Blender session and, with `Remember Keys On This Machine` on by default, kept in the operating system's own credential store: DPAPI on Windows, the login keychain on macOS, Secret Service on Linux. Where no store is reachable the fallback is a file readable only by the user account, reported in those words and never described as encrypted.
- Stopped writing API keys to `userpref.blend`. The preference field is an entry box that blanks itself once a key is accepted, so no key reaches that file on any path, and a key left there by an earlier build is migrated out and cleared on startup.
- Gave Sketchfab a panel field matching Tripo and Meshy, so one class of secret no longer has two policies with the newer one weaker. Poly Haven has no field and the panel says why: open API, every asset CC0.

### Paid generation

- Added a hard spend gate. A job that costs money cannot start until a person approves it in the Agent Bridge sidebar; no tool argument can satisfy it. Approvals are single-use, fingerprinted to the exact job, and expire after ten minutes. The previous `confirm_paid` argument is removed: it looked like consent and an agent could set it in the same turn it discovered the cost.
- Moved the gate to `asset_jobs.start_external_asset_download`, the single seam every job passes through, driven by a required `spends_money` declaration per provider so a new provider cannot be added without deciding.
- Added `plan_image_to_3d_approach`, which lists every route with its cost, whether reference images leave the machine, and what mesh it produces, and asks the user to choose. It asks only when more than one route is ready, so a default install is never interrupted by a one-item menu.
- Added `set_generation_policy` so a standing instruction such as "no APIs this session" is enforced by the bridge rather than remembered by the agent, and is quoted back if a later attempt is refused.

### Honesty of diagnostics

- Separated "configured" from "can actually run". A provider with no job backend reported clean once its paths were set and then refused every job; it now reports `runnable` false with a blocker saying configuration will not help, and offers no remedies to act on.
- Made the reference benchmark state its own scope. It measures silhouette conformance, not model quality, and a dense shell filling the reference hull scores higher than a clean editable mesh of the same subject (measured: 0.926 against 0.557). The result now carries `verdict_scope`, `is_overall_quality_verdict`, and what it does not measure, and the tool no longer tells agents to drive a repair loop on it.
- Made the uploads preference authoritative in both directions. Previously it could permit egress but not deny it, so a stale environment variable left the checkbox reading disabled while hosted providers stayed reachable.
- Schema errors now name the accepted properties and suggest the nearest match instead of only reporting what was rejected.

### Protocol

- Stopped refusing calls on a tool-registry digest mismatch. Only five gateway tools are exposed and every helper resolves at invocation time against the registry inside Blender, so a client config generated against an older registry cannot misroute a call. Digests are reported as advisory; a bridge protocol version mismatch still fails closed.

### Interface

- Moved provider setup out of the viewport sidebar into add-on preferences, grouped by purpose, leaving the sidebar a readiness summary and a button. A credential field does not belong in the part of the UI users record and screen-share.

## 0.4.1 - 2026-08-02

- Made copied MCP configs compact by default: bundled configs omit `env` unless a bridge token or Sketchfab token is present, and `uvx / PyPI` configs include only the runtime marker plus real auth values.
- Fixed viewport blank-capture detection to inspect rendered pixel content more reliably before accepting visual evidence.
- Fixed inspection-render URI handoff so clients can read the generated resource after URI-only capture responses.
- Scrubbed Python home variables from MCPB launch smoke environments so host-managed `uv` launches are tested without inheriting a developer interpreter.
- Added a deterministic `blender-bridge doctor` command that separates client config, executable/path, socket, bridge health, loaded-source, protocol/registry, five-tool manifest, schema, and read-only gateway failures without exposing credentials.
- Added reproducible MCPB v0.4 `uv` packaging for a one-click Claude Desktop connector, including a host-managed Python environment, sensitive bridge-token configuration, matching runtime metadata, checksumed release artifacts, public artifact verification, tests, and cross-platform installation/recovery guidance.
- Strengthened the release-consistency gate so unreleased behavior cannot pass under an already-published version, then aligned tracked install guides with the promoted 0.4.1 publication version.
- Replaced the competing 28-tool default MCP manifest with five stable gateway tools so retrieval-based clients cannot load planners while omitting the catalog execution path. Every canonical helper remains searchable, schema-addressable, and invokable; `BLENDER_MCP_TOOL_SURFACE=direct` restores the former curated surface, `full` exposes every helper, and the legacy full-list flag remains supported.
- Made gateway registration independent of Blender/bridge availability, added explicit `mcp_tool_surface` diagnostics, enriched gateway descriptions for cross-client retrieval, and added default-gateway execution plus Claude/Codex/Cursor five-result reachability regressions.
- Hardened gateway search for read-only inspection and broad multi-domain builds, bounded response-control projection metadata, and collapsed arbitrary unknown tool names into a single content-free telemetry/audit identifier.
- Added a tracked publication-version control so release checks no longer depend on the ignored, generated Pages repository, and updated release verification docs to require the executable five-gateway path.

## 0.4.0 - 2026-07-23

- Removed eight opinionated finished-content generators: procedural object kits, object-design planning, vehicle/product/character refinement templates, storyboard panels, 2D cutout layers, and directed animation shots. Broad authored-content requests now route through reusable helpers, asset import, or a trusted script.
- Split advanced Blender helpers into cohesive animation, camera/render, materials, modeling, presentation, rigging, scene-editing, and shared-support modules; retained the old helper module as a compatibility facade; split animation orchestration from the generic handler runtime; moved planning, 2D inspection, and neutral handler arguments to focused modules; and made `tool_executor.py` the sole registry-composition owner.
- Fixed helper-first orbit workflows and animation-review playblast capture to execute through the explicit handler lookup instead of relying on removed global injection.
- Simplified agent guidance and updated current-facing documentation, routing fixtures, registry snapshots, and smoke coverage to match the 181-tool registry.

## 0.3.1 - 2026-07-22

- Reduced Blender Agent Bridge to one compact sidebar for bridge status, start/stop, MCP config, binary session script trust/revocation, and preview commit/revert. Removed the per-script Run/Reject/Allow-Once UI. Trust off refuses generated Python; trust on grants the same filesystem, network, process, project-file, persistent-cache, and Blender API permissions as Blender's Run Script command.
- Removed the underlying pending-script properties, approval tokens, staging/reject/run helpers, and legacy execution-mode preference so the per-script workflow cannot reappear through dormant state. The compatibility `run_approved_script` endpoint now only returns a permanent refusal.
- Aligned README, security, privacy, architecture, and MCP guidance with binary trust; added documentation drift tests; replaced live `staged` response metadata with `prepared`; and made non-execution reasons report the actual invalid-payload, checkpoint, or trust failure.
- Made script checkpoints collision-safe at sub-second frequency and blocked native Windows hidden files/directories from the bounded project-file tools in addition to dot-prefixed paths.
- Added bounded project-directory list/read/write tools rooted at the current saved `.blend`, with traversal/link protection, hidden-path exclusion, 4 MiB limits, opt-in overwrite, and blocked executable/script/library/`.blend` targets.
- Hardened external-asset downloads with DNS-pinned public-address connections, redirect revalidation, credential isolation, and a 4 GiB streaming limit.
- Made PyPI publication safely resumable by comparing tested artifact hashes before upload, skipping only verified existing files, and checking the complete public artifact set afterward.
- Made copied Bundled MCP configs use Blender's own Python interpreter and verified that exact command from a clean installed extension.
- Made `tools/list` flatten simple top-level JSON Schema combinators for Claude-compatible MCP registration while retaining the canonical schema for bridge validation and explicit schema lookup.
- Isolated registry metadata from caller mutation, strengthened cross-process determinism tests, and avoided redundant source-tree hashing in bridge status diagnostics.
- Replaced broad runtime/global namespace injection in all domain handlers with explicit dependencies, and consolidated trusted-script authorization/status reporting under one pure policy module.
- Fixed look-dev review evidence to honor the configured capture cache and isolated Blender smoke artifacts from developer home directories.

## 0.3.0 - 2026-07-20

- Added the canonical 186-contract modular tool registry, optional `blender-bridge` PyPI/uvx runtime, registry compatibility handshake, conventional unit-test lane, and multi-client/community documentation for the upcoming 0.3.0 release.
- Added a compact External Assets setup block and masked one-time `Copy MCP + Sketchfab` flow; Poly Haven is shown as keyless, ordinary copied configs include an empty Sketchfab token field, and provider tokens remain out of Blender preferences, `.blend` files, and audit logs.
- Added Blender 4.2, 4.5, and 5.1 compatibility coverage, capability-based material/world/compositor node-tree handling (including Blender 5.1's node-group compositor API), and warning-only handling for untested future versions above the 4.2 minimum.
- Fixed external asset workers to opt into online mode explicitly, Poly Haven dependency paths, per-import rollback, duplicate model warnings, Material Preview focus, implicit active-UV inspection, live cache-diagnostic reconciliation after rollback, diagnostic source filenames, and Sketchfab discovery provenance across background workers.
- Hardened external asset networking against local/private destination URLs, unsafe redirects, and cross-origin credential forwarding; destructive cache pruning now targets only bridge-owned cache roots, never the root itself, and reconciles live Blender imports before deletion.
- Closed the known static-analysis escapes through Python object reflection, computed builtin/operator names, callable containers, `sys.modules`, and driver namespace assignment; these cases are now hard CI regressions.
- Updated the GitHub Release publisher to the current Node 24-compatible action line for future tags.

## 0.2.0 - 2026-07-19

- Kept the Blender sidebar lean around bridge start/stop, MCP config, script trust, pending script approval, preview commit/revert, and checkpoint restore; rich diagnostics remain available through bridge/operator responses instead of always showing in the panel.
- Relaxed `draft_script` routing so helper-overlap scene, material, and animation scripts can stage or auto-run under trust after static checks, while external asset, project-file, and persistent simulation bake/free paths stayed in a separate privileged lane at the time.
- Added the original `draft_privileged_script` manifest and one-time-approval path; it is now retained as a compatibility alias to the binary session-trust execution path.
- Raised the approval-gated script size ceiling to 500k characters for larger procedural scene scripts and allowed safe in-memory `io` use while continuing to block file-opening aliases such as `io.open`.
- Hardened script analysis so aliased Blender project-file/window operators such as `ops.wm.save_as_mainfile`, `wm.open_mainfile`, and assigned `save_as_mainfile` functions cannot bypass the privileged approval path.
- Clarified that privileged script manifests are user review/audit context rather than a runtime filesystem or network sandbox.
- Added bounded `create_procedural_object_kit` templates for kitbash towers, radial arrays, scatter grids, product stacks, mechanical joints, and control panels, all using live-preview rollback.
- Added bounded shader material presets and Geometry Nodes starter templates to the existing live-preview helpers.
- Expanded material presets, Geometry Nodes starters, and procedural object kits with screen/rubber/wood materials, set-position/subdivide node groups, studio props, mechanical parts, modular wall panels, and pipe runs.
- Added `plan_asset_import_workflow` and `plan_director_workflow` so clients can plan async asset import, post-import presentation, animation/review/repair, evidence capture, and commit/revert decisions before mutating the scene.
- Hardened animation repair planning for scale-decrease/count mismatches, shape-key/morph repair, material glow/fade/color animation, and inspect-first simulation/cache checks.
- Added real-client routing regression fixtures plus an optional `scripts/live_workflow_sweep.py` bridge sweep for major helper-first workflows.
- Fixed preview change summaries so boolean bookkeeping flags are not reported as affected targets.
- Added bounded `create_directed_animation_shot` templates for camera push/reveal, orbit reveal, product turntable, path slide, staggered reveal, storyboard dolly, crane reveal, and truck slide shots.
- Expanded animation workflow generation so move/path/orbit/fall/crane/truck prompts can route through directed shot helpers before script fallback.
- Tightened crane/truck animation action inference so plain vehicle-subject prompts do not route to camera-shot helpers.
- Added smoke coverage for the sidebar control center, audit log preview, visual evidence inventory, object-kit helpers, directed-shot helpers, and MCP search routing.
- Hardened the optional live Pages smoke so it downloads the advertised extension ZIP and verifies the repository index hash and archive size.
- Updated the release workflow to current Node 24-compatible official GitHub Actions.
- Polished MCP client routing so external asset requests prefer async download/cache jobs and queued import jobs over synchronous fallback tools without misrouting ordinary material texture edits.
- Added MCP guardrail warnings for synchronous external asset fallback calls and non-dry-run external asset cache cleanup.
- Expanded MCP guardrail warnings across destructive project-file operations, user-confirmed paths, approval-gated scripts, live-preview mutations, synchronous long-running tools, and background job polling.
- Hardened MCP guardrail warnings to fall back to local bridge contracts when live tool annotations are sparse, and corrected render-job polling guidance to point at `get_render_job_status`.
- Filled sparse MCP tool annotations from local bridge contracts and marked MP4 assembly as a pollable background render job.
- Raised the documented and declared minimum supported Blender version to `5.1.0`, matching the tested Windows and Linux baseline.
- Changed release publishing so tagged builds run the complete Blender suite and clean installed-extension smoke before one archive is promoted to both GitHub Releases and the Blender Pages repository.
- Added contribution, support, issue-reporting, supported-version, and showcase-asset provenance guidance for the public project.

## 0.1.5

- Fixed the queued external asset import job schema so MCP and bridge validation accept `source_job_id`, the legacy `job_id` alias, or `manifest_path` before dispatch.
- Moved the subprocess external asset worker into a real `asset_job_worker` module instead of generating the full worker body per job.
- Added deterministic Blender-background smoke coverage for subprocess asset downloads completing successfully and feeding queued main-thread imports.
- Allowed loopback-only provider fixture URLs to run under Blender's offline external-access gate while keeping normal Poly Haven and Sketchfab URLs guarded.
- Updated external asset job docs, release docs, and package metadata for the 0.1.5 release.

## 0.1.4

- Added asynchronous external asset download/cache jobs for Poly Haven and Sketchfab, with separate polling, cancellation, and main-thread import-result tools.
- Moved external asset download/cache jobs into background Blender worker processes by default, with stronger cancellation and an in-process compatibility mode for focused tests.
- Added resumable external asset downloads with `.part` files, HTTP Range resume, bounded retry/backoff, and checksum/size revalidation.
- Added Sketchfab archive extraction quotas for member count, uncompressed bytes, member size, path depth, symlinks, and compression ratio.
- Added cached-manifest import support so completed asset jobs can be imported without rerunning the download step.
- Added queued external asset import jobs with start/status/cancel tools so main-thread imports have the same pollable shape as downloads.
- Added external asset cache maintenance tools for dry-run pruning and terminal job metadata deletion.
- Added external asset job progress fields for phase, current file/url, bytes downloaded, expected size, per-file progress, attempts, and resume state.
- Added an opt-in live-network external asset smoke test, skipped by default and requiring explicit env vars for downloads.
- Hardened asset job metadata writes for Windows polling races and redacted Sketchfab secrets from persisted job metadata.

## 0.1.2

- Fixed Sketchfab download/import auth for MCP clients by forwarding `SKETCHFAB_API_TOKEN` / `BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN` from the Claude/Codex MCP server environment into Blender as redacted per-call arguments.
- Added MCP status diagnostics for Sketchfab external-asset auth so stale client environments are visible through `blender_bridge_status`.
- Kept Sketchfab OAuth deferred; the public auth path for this release remains API-token based.
- Lowered the declared minimum Blender version to `5.0.0` for Blender 5.x compatibility.

## 0.1.1

- Added human-in-the-loop `.blend` lifecycle path policy: save-as/save-copy, open, and new-project operations require a user-confirmed path.
- Added in-place autosave for the active bound `.blend` file, with no snapshot files and no invented path for unsaved scenes.
- Added MCP path-policy annotations and compact-catalog recovery smoke coverage so clients can discover when to ask the user for a path.
- Hardened the stdio MCP server with protocol fallback, pagination, prompts, resource templates, structured tool errors, output schemas, and JSON Schema argument validation.
- Added normalized bridge tool contracts with risk levels, permissions, output schemas, and MCP annotations.
- Added local JSONL audit logging for MCP and bridge tool calls with redaction for code, tokens, keys, passwords, and credential-like fields.
- Exposed recent audit events through `blender://audit/latest`.
- Added pure-Python smoke tests and GitHub Actions coverage for the MCP/audit surface.
- Added a reproducible extension zip builder with SHA-256 sidecar output.
- Added Phase 2A safety hardening: transaction rollback manifests, rollback warnings, shader material node-link restoration, and pure static script risk classification.
- Added a compact `blender_tool_catalog` MCP entry point for search, facets, schema lookup, and validated invocation across the full Blender helper catalog.
- Added live external script trust status fields to bridge/MCP status, including countdown, tokenless-run capability, stale scene-state detection, and MCP client refresh guidance.
- Added runtime external script trust presets for 15 minutes, 1 hour, 4 hours, or the current Blender session, with revoke/reload/bridge-start clearing behavior.
- Added MCP viewport capture resources, including latest capture metadata and exact `blender://captures/{capture_id}` reads.
- Added project/session-scoped capture storage: saved `.blend` files use project-local `.claude_blender/captures/<session_id>` folders by default, with global fallback for unsaved or unwritable projects.
- Added sampled animation playblast frame capture with MCP metadata and exact `blender://playblasts/{playblast_id}/frames/{frame}` PNG resources for visual animation review.
- Added production helper kits for lighting presets, material palettes, product turntable staging, and scene organization.

## 0.1.0

- Initial public release.
