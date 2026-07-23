# Public Beta Launch Checklist

This is the single source of truth for launching Blender Agent Bridge. Detailed commands live in [TESTING_GUIDE.md](TESTING_GUIDE.md) and [RELEASE.md](RELEASE.md); security policy lives in [SECURITY.md](../SECURITY.md).

Target: **v0.4.0 public beta**. Version 0.3.0 proved the distribution pipeline. Version 0.4.0 intentionally removes eight opinionated public generators, keeps the compact sidebar and binary trust model, and uses a pre-1.0 minor version because the public tool surface changes.

Status keys: **Done** has current evidence, **Done locally** still needs remote/tag evidence, **Required** blocks launch, **Manual** needs a maintainer or provider action, and **Optional** may follow the launch.

Any source, workflow, packaging, or user-facing documentation change after candidate evidence is collected invalidates the affected evidence. Rebuild from the final reviewed commit and record that commit SHA plus artifact SHA-256 before tagging.

## Launch Dashboard

| Gate | Status | Exit condition |
| --- | --- | --- |
| Scope and user experience | Done locally | The single compact sidebar, binary trust switch, and preview Commit/Revert states are visually reviewed. |
| Code and regression tests | Done locally | Unit, pure-Python, Blender 5.1 background, and installed-extension gates pass for the candidate. |
| Blender compatibility | Required | Blender 4.2 LTS, 4.5 LTS, and 5.1 pass in CI; newer versions remain capability-gated without an artificial maximum. |
| Security and privacy | Done locally | Trust boundaries, external downloads, secrets, permissions, and packaged artifacts are reviewed. |
| Release artifacts | Required | One tagged artifact set publishes an identical extension ZIP to GitHub Releases and Pages plus the matching wheel/sdist to PyPI. |
| GitHub and community | Manual | Repository metadata, support routes, Discussions, and starter issues are ready. |
| Public announcement | Manual | Final announcement points to the released version and verified install path. |
| Post-launch support | Required | Issues and Discussions are monitored and launch regressions have an owner. |

Launch is a **go** only when every Required gate is Done and each Manual item is either completed or explicitly accepted by the maintainer.

## 1. Scope and User Experience

- [x] **Done** — Bundled MCP remains the default; `uvx / PyPI` remains optional.
- [x] **Done** — The intentional public-tool removals are documented as a v0.4.0 pre-1.0 breaking change; the provider-neutral bridge, safety contracts, and retained helper semantics remain stable.
- [x] **Done** — The secondary panel and per-script Run/Reject/Allow-Once operators are removed; the one remaining sidebar renders only bridge/MCP setup, binary runtime script trust/revocation, and preview Commit/Revert.
- [x] **Done** — `tests/smoke_ui_layout.py` locks the exact offline, ready-to-trust, active-trust, removed-approval, conditional rollback, one-panel, and five-setting Preferences contracts.
- [x] **Done locally** — The installed single sidebar, trust confirmation, and pending-preview Commit/Revert state were visually reviewed at 1200×800 and 800×800 in Blender 5.1.2.
- [x] **Done locally** — The same installed sidebar and trust confirmation were visually reviewed at 1200×800 and 800×800 in Blender 4.2.0 and 4.5.0.
- [x] **Done locally** — A clean factory-profile walkthrough installs the official ZIP, starts the bridge, copies a Bundled config, runs the packaged MCP status/workflow/evidence smokes, and exposes preview Commit/Revert without relying on maintainer state.

## 2. Code and Regression Gates

- [x] **Done locally** — Phase 0 and Phase 1 from [TESTING_GUIDE.md](TESTING_GUIDE.md) pass on the v0.4.0 working candidate.
- [x] **Done** — The complete Blender-background suite, including `smoke_ui_layout.py`, passes on local Blender 5.1.2.
- [x] **Done locally** — `scripts/installed_extension_live_smoke.py` passes against the v0.4.0 candidate ZIP from clean temporary profiles on Blender 4.2.0, 4.5.0, and 5.1.2.
- [x] **Done** — The copied Bundled config resolves Blender's own Python interpreter and the clean installed-extension smoke launches the packaged MCP server with that exact command.
- [x] **Done** — Claude Code 2.1.85 started as a new isolated, non-persistent process with only the exact config copied by a clean installed extension, connected to Blender, invoked `blender_bridge_status` once, and returned the correct Blender/add-on/source status. Only that MCP server targeted the bridge.
- [x] **Done** — All observed local test failures were resolved and the affected owner tests were rerun.
- [ ] **Required** — Freeze the final reviewed commit, audit its exact staged scope, and record its commit SHA; generated artifacts, local capture helpers, credentials, and unrelated files must be excluded.
- [ ] **Required** — Rebuild the official ZIP, wheel, sdist, and Pages repository from that commit, then rerun installed-extension and packaged-MCP smoke against those exact artifacts.

## 3. Compatibility

- [x] **Done** — Minimum supported Blender version is 4.2.0.
- [x] **Done** — CI covers Blender 4.2 LTS, 4.5 LTS, and 5.1 and uses capability checks for newer releases.
- [x] **Done** — There is no maximum-version rejection; untested future versions receive a compatibility warning.
- [x] **Done locally** — The complete 18-test Blender-background suite and clean installed-extension live smoke pass on Blender 4.2.0, 4.5.0, and 5.1.2 for the reviewed v0.4.0 candidate; each clean install built the same official extension ZIP digest.
- [ ] **Required** — All three supported CI lanes pass for the v0.4.0 tag, including clean installed-extension smoke.
- [x] **Done locally** — Material, compositor, external-asset, preview, and UI behavior pass on each supported local lane.
- [x] **Done locally (optional)** — Blender 5.2.0, the newest stable build on 2026-07-23, passes the complete 18-test background suite and clean installed-extension live smoke. Record it as compatible-untested for v0.4.0 rather than adding a permanent fourth launch lane immediately.

## 4. Security and Privacy

- [x] **Done** — Generated Python uses binary session trust: trust off refuses without pending state, while trust on matches Blender **Run Script** permissions, including filesystem, network, subprocess, project-file, persistent-cache, and Blender API access. Static analysis is advisory under trust, not a sandbox or hidden privilege gate.
- [x] **Done** — The bridge binds to loopback and supports bearer-token authentication.
- [x] **Done** — External-asset workers opt into online mode only for explicit asset jobs.
- [x] **Done** — External downloads reject private/local destinations, pin a validated public address, constrain redirects and credential forwarding, and enforce a 4 GiB limit.
- [x] **Done** — Sketchfab session tokens are masked, memory-only, and excluded from preferences, `.blend` files, manifests, and audit logs.
- [x] **Done** — Negative bridge, MCP, script-analysis, project-path, external-asset, token-redaction, and trust tests pass through the unit, pure-Python, and Blender suites.
- [x] **Done** — `blender_manifest.toml` permissions, [SECURITY.md](../SECURITY.md), [PRIVACY.md](../PRIVACY.md), and [SAFETY_MODEL.md](SAFETY_MODEL.md) match binary session trust. Unit coverage rejects the removed staged/per-script security wording.
- [x] **Done** — The official extension ZIP contains `LICENSE` and excludes repository metadata, bytecode, logs, caches, captures, checkpoints, tokens, and private `.blend` artifacts.
- [x] **Done locally** — Gitleaks 8.30.1 reports no leaks in the 142-commit history, working candidate, or exact extension/wheel/sdist artifact inputs.
- [x] **Done locally** — Clean installed-extension smoke confirms trust-off refusal without pending state, trust-on immediate execution, permanent refusal of the removed per-script path, compatibility-alias execution under trust, revoke, reload cleanup, and bridge-restart persistence on Blender 4.2.0, 4.5.0, and 5.1.2.
- [ ] **Required** — Confirm GitHub Release and Pages extension ZIPs have the same SHA-256 digest.

## 5. Packaging and Release

- [x] **Done** — v0.3.0 proved Trusted Publishing, GitHub Release, Pages, repository install, and public artifact-identity verification from one tested artifact set.
- [x] **Done locally** — Version 0.4.0 is consistent in the extension manifest, Python package metadata, runtime output, generated `uvx` config, client guides, and changelog. The tag is intentionally deferred until review is complete.
- [x] **Done locally** — `smoke_release_consistency.py`, official Blender source/ZIP validation, wheel/sdist build, clean wheel install/runtime import, and local release/Pages artifact-identity checks pass for the reviewed candidate.
- [x] **Done locally** — PyPI confirms `blender-bridge` still belongs to this project; v0.4.0 is unpublished and requires both candidate artifacts.
- [ ] **Required** — Tag only the reviewed release commit and let the release workflow publish the already-tested artifacts.
- [ ] **Required** — Verify the public GitHub Release, PyPI package, Pages index, hosted ZIP, checksums, and installation instructions after publication.
- [x] **Done** — The changelog and announcement draft identify the one-panel compact UI, external-download hardening, deterministic registry behavior, and resumable PyPI publication using the final control labels.

## 6. GitHub and Community

- [x] **Done** — GitHub Discussions is enabled with Announcements, Ideas, Q&A, and Show and tell categories.
- [x] **Done** — Three bounded `good first issue` tasks are open.
- [x] **Done** — Client guides, showcase guidance, contribution guidance, issue templates, support policy, and security reporting are present.
- [x] **Done locally** — `LICENSE` starts with the canonical GPL text so GitHub can detect it; the extension and Python package still declare `GPL-3.0-or-later` explicitly.
- [x] **Done** — Use GitHub Discussions **Q&A** as the permanent Help surface; do not add a duplicate Help category.
- [x] **Done** — Repository description is `Safe, scene-aware MCP bridge for Blender with reversible editing and visual evidence.`
- [x] **Done** — Homepage and requested repository topics are set; GitHub license detection still needs rechecking after the follow-up change is merged.
- [x] **Done** — `main` remains direct-push-capable while there is one maintainer, but release candidates use a reviewable PR and must pass the release workflow before tagging; enable branch protection when a second regular contributor begins merging.
- [x] **Done locally** — Add a monthly GitHub Actions Dependabot check capped at two open PRs; do not add dependency automation for the zero-runtime-dependency Python package.
- [x] **Done** — GitHub vulnerability alerts are enabled. Automated security-fix PRs remain off initially.
- [x] **Done** — Reviewed starter Issues [#2](https://github.com/CallMeJones/blender-agent-bridge/issues/2), [#3](https://github.com/CallMeJones/blender-agent-bridge/issues/3), and [#4](https://github.com/CallMeJones/blender-agent-bridge/issues/4); each is bounded and already has concrete acceptance criteria.
- [ ] **Optional** — Do not launch Discord yet. Reconsider after ten distinct monthly support/contributor conversations show demand for synchronous help.

## 7. Announcement and Launch Day

- [x] **Done locally** — [PUBLIC_BETA_ANNOUNCEMENT.md](PUBLIC_BETA_ANNOUNCEMENT.md) is updated to the v0.4.0 facts, links, screenshots, and one-panel UI wording; public links must still be checked after the tag exists.
- [ ] **Required** — Test every announcement link in a signed-out browser and confirm the install repository is publicly reachable.
- [ ] **Manual** — Publish the release and wait for every required GitHub Actions job and public artifact check to pass.
- [ ] **Manual** — Publish the announcement in GitHub Discussions **Announcements** and link it from the repository and project site.
- [ ] **Manual** — Seed one focused feedback prompt: Blender version, OS, MCP client, attempted workflow, expected result, actual result, and shareable evidence.

## 8. First 72 Hours

- [ ] **Required** — Monitor security advisories, issues, and Discussions for install failures, data-loss risk, script-trust bypasses, and Blender-version regressions.
- [ ] **Required** — Label launch blockers, publish workarounds quickly, and prepare v0.4.1 only from reproduced fixes with owner tests.
- [ ] **Required** — Record recurring setup friction and update the relevant client guide rather than answering the same question only in a thread.
- [ ] **Optional** — Curate permission-cleared community work into the showcase.

## Evidence Log

| Date | Evidence | Result |
| --- | --- | --- |
| 2026-07-20 | v0.3.0 release workflow, PyPI Trusted Publishing, GitHub Release, Pages deployment, and public artifact identity | Passed |
| 2026-07-22 | `Blender 5.1.2 --background --factory-startup --python tests/smoke_ui_layout.py` | Passed |
| 2026-07-22 | 51 unit tests plus 13 pure-Python smoke/consistency checks | Passed |
| 2026-07-22 | Complete 19-test Blender 5.1.2 background suite | Passed |
| 2026-07-22 | Official source/ZIP validation, wheel/sdist build, clean wheel MCP subprocess, and local release/Pages artifact identity | Passed; final extension SHA-256 `0afc6f63ee145a1cecac5f08dc8a590b889764503888864de15b04874c6b68bf` |
| 2026-07-22 | Clean installed-extension interactive smoke: clipboard config, session token, Material Preview, bridge, workflows, evidence resources, and 29-tool MCP catalog | Passed |
| 2026-07-22 | Blender 5.1.2 sidebar review at 1200×800 and 800×800, with Advanced collapsed and expanded | Historical evidence for the removed two-panel layout; current one-panel UI still needs visual review |
| 2026-07-22 | Historical pre-consolidation approval/trust lifecycle: wrong-token rejection, one-time consumption, expiry, revoke, reload, and bridge restart | Superseded by the binary-trust implementation |
| 2026-07-22 | Copied Bundled config launched the installed MCP server with Blender 5.1.2's own Python interpreter | Passed; 29-tool MCP catalog and bridge status returned successfully |
| 2026-07-22 | Official Blender 4.2.0 and 4.5.0 portable archives checked against Blender's published SHA-256 manifests | Passed |
| 2026-07-22 | Complete 19-test background suite on Blender 4.2.0 and 4.5.0 | Passed on both versions |
| 2026-07-22 | Clean installed-extension smoke on Blender 4.2.0, 4.5.0, and 5.1.2: official ZIP, trust lifecycle, workflows, visual evidence, and each version's bundled Python MCP command | Passed on all three versions; each built ZIP matched `0afc6f63ee145a1cecac5f08dc8a590b889764503888864de15b04874c6b68bf` |
| 2026-07-22 | Blender 4.2.0 and 4.5.0 sidebar review at 1200×800 and 800×800, with Advanced collapsed and expanded | Historical evidence for the removed two-panel layout; current one-panel UI still needs visual review |
| 2026-07-22 | Real Claude Code 2.1.85 MCP host with strict config copied by the clean Blender 5.1.2 extension | Passed; connected, registered the tool surface, called `blender_bridge_status` exactly once, and returned Blender 5.1.2/add-on 0.3.1/source current |
| 2026-07-22 | Final isolated-artifact PyPI preflight | `blender-bridge` still matches this project; v0.3.1 remains unpublished (must be repeated immediately before publish) |
| 2026-07-22 | Gitleaks 8.30.1: 131-commit history, working diff, and untracked candidate files | Passed; no leaks found |
| 2026-07-22 | Updated `smoke_ui_layout.py` after active-trust, recovery, and conditional rollback fixes on Blender 4.2.0, 4.5.0, and 5.1.2 | Passed on all three versions |
| 2026-07-22 | Final staged release-candidate scope audit | Passed; 49 intended files, no generated artifacts or unrelated changes |
| 2026-07-22 | Post-evidence one-panel UI and documentation changes | Previous candidate scope, package, installed-extension, secret-scan, and artifact evidence invalidated; final-commit evidence required before tag |
| 2026-07-22 | Binary trust plus project-directory filesystem candidate: 53 unit tests, complete pure-Python gate and adversarial analyzer smoke, complete 19-test Blender 5.1.2 suite, project-file containment smoke on Blender 4.2/4.5/5.1, official source/ZIP/repository validation, artifact identity, and clean installed-extension live smoke on all three versions | Passed; candidate extension SHA-256 `e9d239b7d25a7024187946f0dffcb924f3cdce09259d7fba41be48ccf421b0a7` |
| 2026-07-22 | Gitleaks 8.30.1 on 133-commit history and final binary-trust working diff | Passed; no leaks found |
| 2026-07-23 | Blender Run Script-equivalent binary trust: 53 unit tests, complete pure-Python gate and adversarial analyzer smoke, complete 19-test Blender 5.1.2 suite, script-trust/UI owner smokes on Blender 4.2/4.5/5.1, official source/ZIP/repository validation, and clean installed-extension live smoke proving trust-off refusal plus trusted filesystem/`os`/socket/subprocess imports on all three versions | Passed; candidate extension SHA-256 `cc5c53a2edf8aa002399c5b934095a6b486817c843715208f2f74ff26ea7e84e` |
| 2026-07-23 | Gitleaks 8.30.1 on 136-commit history and Blender Run Script-equivalent trust working tree | Passed; no leaks found |
| 2026-07-23 | Final simplified-trust candidate from implementation commit `39bccbf`: 53 unit tests, complete pure-Python gate, complete 19-test Blender 5.1.2 suite, trust/project-file/UI/animation owner smokes on Blender 4.2/4.5, source/ZIP/Pages/artifact-identity validation, wheel/sdist build plus clean wheel install, and clean installed-extension live smoke on Blender 4.2/4.5/5.1 | Passed; candidate extension SHA-256 `3d124947bff22b55b709f4ca1c712eea30942bd5df5fa11ad37e4f8811145bac` |
| 2026-07-23 | Gitleaks 8.30.1 on 137-commit history, final working tree, Pages extension archive, wheel, and sdist with archive scanning enabled | Passed; no leaks found |
| 2026-07-23 | Optional newest-stable check: official Blender 5.2.0 build `fbe6228777e7`, archive SHA-256 `38b3a91c5925ea38ca714eaf15f27f0011894eff6523605c62dc8d9a1db6a335`, complete 18-test background suite, and clean installed-extension live smoke | Passed; compatible-untested for v0.4.0 rather than a required CI lane |
| 2026-07-23 | Architecture-cleanup v0.4.0 candidate: 68 unit tests, 13 pure/adversarial/release smokes, Ruff and compile checks, complete 18-test background suite on Blender 4.2.0/4.5.0/5.1.2, and clean installed-extension live smoke on all three versions | Passed; each installed smoke built SHA-256 `2e33aab2ea28f6f813f60dfb8ae355d6cca918490044130b5050828aca4fa46f` |
| 2026-07-23 | Installed UI captures on Blender 4.2.0, 4.5.0, and 5.1.2 at 1200×800 and 800×800, plus the trust dialog and narrow pending-preview Commit/Revert state | Passed visual review; no clipped controls, secondary panel, or per-script approval actions |
| 2026-07-23 | Official Blender validation, wheel/sdist build, isolated wheel install/runtime import, generated Pages repository, and local release-artifact identity | Passed; extension/Pages SHA-256 `2e33aab2ea28f6f813f60dfb8ae355d6cca918490044130b5050828aca4fa46f` |
| 2026-07-23 | Gitleaks 8.30.1 on the 142-commit history, working candidate, source/documentation inputs, extension ZIP, wheel, and sdist | Passed; no leaks found |
| 2026-07-23 | Isolated-artifact PyPI preflight | `blender-bridge` still identifies this project (latest 0.3.0); v0.4.0 is unpublished and requires wheel plus sdist upload |

Add evidence here only after it has run against the candidate being evaluated. A previous release proves the pipeline, not the current release contents.
