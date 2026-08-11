# v0.5.6 Public Beta Launch Readiness

This is the canonical launch decision record for Blender Agent Bridge v0.5.6.
Detailed commands live in [TESTING_GUIDE.md](TESTING_GUIDE.md) and
[RELEASE.md](RELEASE.md). Security policy lives in
[SECURITY.md](../SECURITY.md).

Published release: **v0.5.5**

Candidate release: **v0.5.6**

Candidate commit: **the commit containing this readiness record**. Record its
immutable SHA in the release notes and tag verification output.

Current decision: **GO TO TAG after frozen-commit smokes pass.** The maintainer
authorized commit, push, smoke, tag, and publication on 2026-08-11 for the
user-POV patch release that fixes immediate paid-approval redraws, deep
Windows profile path handling, unwritable runtime directories, and Windows
process-tree cancellation.

Any behavior, test, workflow, package-input, or shipped-documentation change
after a gate is recorded invalidates the affected evidence. Recording results
or checksums in this decision record does not invalidate checks of otherwise
unchanged inputs. Freeze one reviewed commit, rebuild from it, and use only
artifacts produced from that commit for tagging.

Status keys: **Done**, **Deferred**, and **Post-tag**.

## Launch Gates

| Gate | Status | Exit condition |
| --- | --- | --- |
| Generation upload consent | Done | References are provider-counted, signature/type checked, limited to 20 MiB each and 64 MiB per job, bound to approval by byte count and SHA-256, and shown in Blender by view, filename, folder, and size. |
| Generated download security | Done | Hosted artifacts use the hardened external-asset transport; studio credentials remain same-origin; file/private destinations, unsafe redirects, limits, content types, and model payloads have owner coverage. |
| Paid-provider pricing | Done | Meshy and Tripo estimates resolve from every cost-affecting option, appear before approval, and are bound into the single-use job fingerprint. |
| Paid-approval UX | Done | Entering paid user-approval state requests an immediate Agent Bridge sidebar redraw, so approval controls appear without requiring hover-driven UI refresh. |
| Deep Windows profile paths | Done | Runtime capture and trusted-script checkpoint paths fall back to the global user-data root when extension-profile paths approach the Windows path budget. |
| Unwritable runtime directories | Done | Captures, checkpoints, credential files, and audit logs use a writable temp fallback when the configured/default user-data root cannot be written. |
| Windows cancellation | Done | Subprocess cancel/recovery uses a native descendant-process fallback when `taskkill /T /F` is unavailable or denied. |
| Tracked provider evidence | Done | The sanitized [Meshy vehicle report](assets/meshy-vehicle-multiview-report.md) and contact sheet are tracked; no credentials, signed URLs, provider IDs, local paths, or generated GLB are published. |
| Unit and pure-Python gates | Done | The candidate passes 579 tests with 2 skips plus targeted approval-redraw and path-budget smoke coverage. |
| Blender 5.1 local gates | Done | Blender 5.1.2 passes generation, UI, context/capture, and clean installed-extension live smokes from the candidate. |
| Supported Blender CI | Post-tag | Tag workflow must pass Blender 4.2, 4.5, and 5.1 plus MCP and packaging jobs. |
| Secret scan | Done | The v0.5.5 launch gate had a clean Gitleaks history/candidate scan; rerun if any release artifact or credential-handling files change before tagging. |
| Normal Codex client | Done | A normal Codex Desktop task sees exactly the five gateways, connects to the reloaded add-on, retrieves `list_scene_objects`, invokes it read-only, and confirms the unchanged-response digest path. |
| Normal Claude Desktop client | Deferred | Claude Desktop is not installed on the release workstation. MCPB schema, extracted runtime, doctor, and five-gateway smokes remain the practical beta gate. |
| Normal Cursor client | Deferred | Cursor is not installed on the release workstation. Deterministic client-profile/config routing passes; a real Cursor host session remains a public-beta follow-up. |
| Candidate artifacts and identity | Done | ZIP, MCPB, wheel, sdist, and extension-repository metadata must build and pass local identity, validation, isolated-install, and runtime checks from the frozen commit. |
| Version and release metadata | Done | Changelog entries are under `0.5.6`, `release_state.toml` and tracked install pins resolve to 0.5.6, and tag-mode release consistency must pass. |
| Publish approval | Done | Maintainer explicitly requested commit, push, smoke, tag, and publication on 2026-08-11. |
| Public artifact verification | Post-tag | The tag workflow verifies GitHub Release, Pages repository, PyPI, ZIP, MCPB, wheel, and source identities before announcement. |

## Final Candidate Evidence

Local evidence below was produced from the current working candidate. Entries
explicitly marked for rerun do not become final release evidence until the
candidate commit is frozen and the same checks pass from that commit.

| Evidence | Result |
| --- | --- |
| Candidate commit | Frozen by the commit containing this record; record the immutable SHA after push |
| Unit and pure-Python suite | Local pass: 579 passed, 2 skipped |
| Paid-generation approval UX | Blender 5.1 pass: paid approval requests trigger immediate sidebar redraw |
| Deep Windows profile installed-extension smoke | Blender 5.1 pass: captures, visual-evidence lookup, trusted-script checkpoints, credentials, audit logging, bundled MCP, and MCPB runtime pass from a deliberately deep profile |
| Blender 5.1 generation/UI/external-asset smokes | Local pass on Blender 5.1.2 |
| Blender 4.2/4.5/5.1 GitHub Actions | Pending tag workflow |
| Codex normal-client smoke | Pass in Codex Desktop: five gateways; compatible/current bridge; `list_scene_objects` schema and read-only invoke; matching digest returned `not_modified` |
| Claude Desktop normal-client smoke | Deferred to public beta; Claude Desktop is not installed on this workstation |
| Cursor normal-client smoke | Deferred to public beta; Cursor is not installed on this workstation |
| ZIP SHA-256 | Local candidate `dist/claude_blender-0.5.6.zip`: `220a8dc8e0575162466a84f8337230c06f8d11b502c6c2bf866aadede5b87c9a` |
| MCPB SHA-256 | Local candidate `dist/blender-agent-bridge-0.5.6.mcpb`: `715e8b00c846f1124cdefdcef79c10385cee367c1110643f79e1cde2e9a02869` |
| Wheel/sdist verification | Pending frozen-commit rebuild |
| Tag/public artifact identity | Pending tag workflow |

## Launch Scope

v0.5.6 may launch as a public beta once the gates above are complete. The beta
must clearly qualify local TripoSR as a single-view blockout route and generated
provider meshes as assets that still require topology and semantic evaluation.

The following are valid beta-era improvements, not launch blockers:

- Hunyuan3D and TRELLIS direct launchers
- A live studio endpoint deployment
- Perfect provider topology or automatic retopology
- Garment-specific modeling
- Completion of every remaining modeling-roadmap item
- Separate paid Meshy remesh and retexture jobs

## Release Sequence

1. Freeze and review the candidate commit.
2. Run every available local and normal-client gate; record any explicit beta
   deferral without presenting it as a pass.
3. Push the candidate and require green supported-Blender CI.
4. Build and verify one identity-consistent artifact set.
5. Create the annotated `v0.5.6` tag only after maintainer approval.
6. Let the tag workflow publish and independently verify every public artifact.
7. Announce the public beta only after the Post-tag gate passes.
