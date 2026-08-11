# v0.5.5 Public Beta Launch Readiness

This is the canonical launch decision record for Blender Agent Bridge v0.5.5.
Detailed commands live in [TESTING_GUIDE.md](TESTING_GUIDE.md) and
[RELEASE.md](RELEASE.md). Security policy lives in
[SECURITY.md](../SECURITY.md).

Published release: **v0.5.4**

Candidate release: **v0.5.5**

Candidate commit: **the commit containing this readiness record**. Record its
immutable SHA in the release notes and tag verification output.

Current decision: **GO TO TAG.** The maintainer explicitly authorized the
v0.5.5 tag and publication on 2026-08-11 after the available local, normal
client, and supported-version CI gates passed. Claude Desktop and Cursor host
sessions are retained below as visible public-beta follow-ups, not claimed as
passes.

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
| Tracked provider evidence | Done | The sanitized [Meshy vehicle report](assets/meshy-vehicle-multiview-report.md) and contact sheet are tracked; no credentials, signed URLs, provider IDs, local paths, or generated GLB are published. |
| Unit and pure-Python gates | Done | The frozen candidate passes 579 tests with 2 skips plus protocol, helper-routing, tool-inventory, MCP stdio, compile, and release-consistency checks. |
| Blender 5.1 local gates | Done | Blender 5.1.2 passes generation, UI, external-asset, packaging, and clean installed-extension live smokes from the frozen candidate. |
| Supported Blender CI | Done | Candidate push run 31504535598 passes Blender 4.2, 4.5, and 5.1 plus MCP and packaging jobs. |
| Secret scan | Done | Gitleaks 8.30.1 reports no leaks in repository history or the final candidate directory scan. |
| Normal Codex client | Done | A normal Codex Desktop task sees exactly the five gateways, connects to the reloaded add-on, retrieves `list_scene_objects`, invokes it read-only, and confirms the unchanged-response digest path. |
| Normal Claude Code client | Done | Claude Code 2.1.85 with Claude Sonnet 4.6 sees the five gateways, reports add-on 0.5.5/source current, invokes `list_scene_objects` read-only, and makes no mutations. |
| Normal Claude Desktop client | Deferred | Claude Desktop is not installed on the release workstation. MCPB 2.1.2 schema, extracted runtime, doctor, and five-gateway smokes pass; a GUI-host install remains a public-beta follow-up. |
| Normal Cursor client | Deferred | Cursor is not installed on the release workstation. Deterministic client-profile/config routing passes; a real Cursor host session remains a public-beta follow-up. |
| Candidate artifacts and identity | Done | ZIP, MCPB, wheel, sdist, and extension-repository metadata build and pass local identity, validation, isolated-install, and runtime checks. |
| Version and release metadata | Done | Changelog entries are under `0.5.5`, `release_state.toml` and tracked install pins resolve to 0.5.5, and tag-mode release consistency passes. |
| Publish approval | Done | Maintainer explicitly requested commit, push, smoke, tag, and publication on 2026-08-11. |
| Public artifact verification | Post-tag | The tag workflow verifies GitHub Release, Pages repository, PyPI, ZIP, MCPB, wheel, and source identities before announcement. |

## Final Candidate Evidence

Local evidence below was produced from the current working candidate. Entries
explicitly marked for rerun do not become final release evidence until the
candidate commit is frozen and the same checks pass from that commit.

| Evidence | Result |
| --- | --- |
| Candidate commit | Frozen by the commit containing this record; record the immutable SHA after push |
| Unit and pure-Python suite | Local pass: 579 passed, 2 skipped; final frozen-commit rerun required |
| Blender 5.1 generation/UI/external-asset smokes | Local pass on Blender 5.1.2; final frozen-commit rerun required |
| Clean installed-extension and MCPB smoke | Local pass on Blender 5.1.2; temporary ZIP SHA-256 `30a63c8061f279db4b27bba5543436c1c9c3a14671c9b2b01ce5abb66d2cf1d8`; final frozen-commit rebuild required |
| Blender 4.2/4.5/5.1 GitHub Actions | Pass in candidate push run 31504535598 |
| Gitleaks history and candidate scan | Local pass with Gitleaks 8.30.1: 206 commits and final 269.68 MB candidate scan; two ignored permission-restricted local trust artifacts were outside the release candidate |
| Codex normal-client smoke | Pass in Codex Desktop: five gateways; compatible/current bridge; `list_scene_objects` schema and read-only invoke; matching digest returned `not_modified` |
| Claude Code normal-client smoke | Pass with Claude Code 2.1.85 and Claude Sonnet 4.6: five gateways, add-on 0.5.5/source current, one read-only object, no mutations |
| Claude Desktop normal-client smoke | Deferred to public beta; Claude Desktop is not installed on this workstation |
| Cursor normal-client smoke | Deferred to public beta; Cursor is not installed on this workstation |
| ZIP SHA-256 | Local candidate: `30a63c8061f279db4b27bba5543436c1c9c3a14671c9b2b01ce5abb66d2cf1d8`; Blender validation, clean install, and repository identity pass |
| MCPB SHA-256 | Local candidate: `8453c353c50f78ad2a9847506f6f6fce3e001c51bbc151b4a5888076d76d8870`; Anthropic MCPB 2.1.2 schema and staged `uv` runtime pass |
| Wheel/sdist verification | Isolated wheel reports 0.5.5; wheel SHA-256 `8cac6ac4d80e09c1fd0ae463d063c1a2f86c486e96dded5cd04166ea0059fae0`; sdist SHA-256 `94acfd39ce7452bf7a30aa6619e36e82021d878ee6ca3d254de467abd89c8740` |
| Tag/public artifact identity | Pending tag workflow |

## Launch Scope

v0.5.5 may launch as a public beta once the gates above are complete. The beta
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
5. Create the annotated `v0.5.5` tag only after maintainer approval.
6. Let the tag workflow publish and independently verify every public artifact.
7. Announce the public beta only after the Post-tag gate passes.
