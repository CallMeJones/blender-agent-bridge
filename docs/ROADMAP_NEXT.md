# Next On The Roadmap

Last updated 2026-08-11 after the public `v0.5.4` release.

This document is forward-looking. Completed implementation detail belongs in
[`CHANGELOG.md`](../CHANGELOG.md); release procedure and evidence requirements
belong in [`RELEASE.md`](RELEASE.md) and [`TESTING_GUIDE.md`](TESTING_GUIDE.md).
Findings F1-F26 refer to the retained sculpt evaluation notes, and generation
architecture is governed by
[`ADR-001-generation-provider-layer.md`](adr/ADR-001-generation-provider-layer.md).

---

## 0. Released Baseline

### Release confidence

- `v0.5.4` is published from commit
  `9215aa7bbc01f0b0beedd6f790d1fd36694bffdc` as a GitHub Release, Blender
  extension repository archive, MCPB connector, PyPI wheel, and source
  distribution.
- The tagged release workflow passed 519 unit tests, the complete Blender smoke
  suite, and clean installed-extension live smoke on Blender 4.2.0, 4.5.0, and
  5.1.2. It also verified the tested ZIP, MCPB, PyPI artifacts, GitHub Release,
  and Pages repository by identity.
- A separate clean Blender 5.1 profile on the release workstation synced the
  public repository, downloaded the published archive, installed and enabled
  `claude_blender`, and reported version `0.5.4`.
- Generation remains optional. With third-party uploads disabled and no
  provider configured, scene inspection, scripts, bounded helpers, previews,
  rendering, project tools, and the five-tool MCP gateway continue to work.

### Generation baseline

- Hosted Tripo and Meshy, local TripoSR, and the local/LAN studio endpoint all
  reuse the shared asset-job lifecycle, polling, cache manifest, import,
  provenance, and presentation path.
- Multiple runnable providers require an explicit provider choice. The bridge
  never silently selects a hosted provider; a sole local/self-hosted route may
  be selected automatically.
- Hosted Tripo and Meshy require a single-use spend decision in Blender. Agents
  can poll the exact request and observe Approve, Decline, expiry, or prior
  consumption. Local TripoSR and the studio endpoint do not use the spend gate.
- TripoSR has persistent runtime paths and tuning defaults, full process-tree
  cancellation, recovery, Z-up import normalization, optional texture baking,
  generated-asset cleanup, and front/side/top evaluation with contact sheets.
- Provider keys are session-held and optionally persisted in the operating
  system credential store or a clearly reported user-only fallback file. They
  are not written to Blender preferences, `.blend` files, manifests, or audit
  logs.

### Live provider evidence

| Route | Implemented contract | Live evidence at `v0.5.4` |
| --- | --- | --- |
| Tripo | Hosted single-image and four-view generation, spend approval, polling, import, and sanitized provenance. | Single-view and paid multi-view generation/import are proven. |
| Meshy | Hosted single-image and multi-image generation, balance preflight, provider cancellation, polling, import, and sanitized provenance. | Single-view generation/import plus provider-side cancellation and restart recovery are proven. Multi-image execution is not yet live-proven. |
| TripoSR | Direct local single-image process with persistent controls, cancellation/recovery, orientation normalization, texture baking, cleanup, and evaluation. | Generation, cancellation/recovery, textured and untextured imports, and non-character fan/teapot evaluation are proven. It remains a blockout route because one image cannot reveal hidden structure. |
| Studio endpoint | Local/private-network HTTP or HTTPS contract with optional bearer token, one or more views, polling, optional balance, and shared import/provenance. | Contract and unit coverage pass. No real studio service has been supplied for a live run. |
| Hunyuan3D / TRELLIS | Readiness strategy and hardware/runtime diagnostics only. | No launcher exists; neither is a runnable backend yet. |

### Reference and modeling baseline

- F5 subject calibration is complete: silhouette-derived or explicit subject
  bounds can map to a requested world-space height, with cross-view scale
  warnings.
- The representative 32-node SDF budget is complete under the bounded
  64-million-work-unit evaluator with cached parent transforms.
- F18-F20 shape-program expressiveness is complete: elliptical capsules,
  variable sweep sections, targeted booleans, and disconnected-component
  reporting are exposed through the strict schema.
- The optional structural benchmark term is complete and remains separate from
  silhouette conformance. It does not claim riggability or production topology.
- F6 supports explicit world-unit scalar `cell_size`; automatic budget-derived
  defaults and per-axis sizing remain conditional improvements.
- F7 supplies automatic body/head/limb parts for generic characters. Broader
  semantic decomposition remains evidence-driven rather than claimed as a
  generic solution.
- Live Blender 5.1 evidence covers selected feature stacks, part-derived weight
  and grooming flow, multi-view depth surfaces, adaptive remesh, edit-mesh
  helpers, lower-level semantic sculpt tools, and adaptive-manifold diagnostics
  at maximum depths 7, 8, and 9.

---

## 1. Immediate Priorities

### 1. Broaden non-character validation

Add three deliberately different live subjects:

- a vehicle with thin structural features and repeated hard-surface parts;
- a garment with open boundaries, folds, and no expectation of watertightness;
- a larger asymmetric prop with meaningful unseen-side structure.

For each subject, retain input provenance, provider route, import metadata,
front/side/top evidence, component and topology findings, cleanup results, and
an honest statement of what the references cannot establish. Use local TripoSR
where a single-view blockout is useful and a hosted route only with explicit
provider choice and spend approval.

This evidence decides whether to implement broader F7 semantic-part defaults or
new F6 hull-resolution behavior. Do not add category heuristics before the live
cases show a repeatable rule.

### 2. Extend adaptive topology evidence beyond F14

F14 is closed. The original seven-node lamp coordinates were not retained, but
the bridge audit and evaluation report preserved its structure and isolated
failure: a multi-point sweep with a subtracted sweep cavity. A deterministic
connected fixture now reproduces the cross-cell residue, exercises the final
vertex-fan split at maximum depth 7, remains manifold and connected at depths 7,
8, and 9, and matches the uniform fallback's component structure.

Keep that regression in the Blender smoke matrix. Add another adaptive topology
fixture only when a materially different failure appears; do not keep expanding
the suite with coordinate variants of the same sweep/subtract case.

### 3. Complete a separate-machine install

Blender 4.2/4.5/5.1 tagged CI and a clean public-repository install on the
release workstation are complete. The remaining release-confidence check is a
genuinely separate machine or VM that has not used the development checkout.

Install from the public repository, start the bridge, connect one supported MCP
client, perform a read-only gateway call, leave one reversible edit as a
preview, and verify update discovery. Record the Blender, OS, client, and
extension versions without retaining tokens.

### 4. Live-prove the studio endpoint

This is blocked until a compatible service URL is available. Once supplied,
prove both one-view and multi-view jobs through task start, polling, download,
import, provenance, failure redaction, and restart recovery. Test an optional
bearer token and both a local/private HTTP address and an HTTPS hostname when
the deployment supports them.

### 5. Choose a Hunyuan3D/TRELLIS execution path

Do this only when suitable GPU hardware or a studio inference service exists.
Choose between:

- a direct `local_process` launcher with isolated process-tree cancellation; or
- a model-specific service hidden behind the existing studio endpoint contract.

A runnable backend needs installation diagnostics, bounded arguments, progress
and cancellation behavior, standard manifests, import provenance, failure
redaction, tests, and live evidence. Configuration-only readiness is not enough.

---

## 2. Remaining Work By Area

### Generation

- Live-prove Meshy multi-image generation and compare its topology,
  fragmentation, materials, and hidden-side structure with the existing
  single-image evidence.
- Live-prove the studio endpoint when a service exists.
- Implement Hunyuan3D/TRELLIS only after choosing hardware and ownership.
- Keep provider-side cancellation claims scoped accurately: Meshy deletion and
  local TripoSR process-tree cancellation are proven. Add remote cancellation
  for another provider only when its public or studio contract supports it.
- Generalize MCP credential forwarding only if a real client-held generation or
  studio credential must cross the MCP server. Blender-side session/OS
  credentials already cover current generation routes.

### Reference and modeling

| Finding | Status | Remaining decision |
| --- | --- | --- |
| F5 subject calibration | Done | Broaden live subject evidence only. |
| F6 hull resolution | Partial | Add automatic budget defaults or per-axis sizing only if new subjects show the scalar `cell_size` path is insufficient. |
| F7 semantic parts | Partial | Extend beyond characters only after vehicle, garment, and prop evidence establishes useful rules. |
| F14 dual-contouring residue | Done | Preserve the connected sweep/subtract regression at depths 7/8/9 and its uniform parity check. |
| 32-node SDF budget | Done | Guard the current bounded performance contract. |
| Structural benchmark term | Done | Preserve its limited scope; do not turn it into an overall quality verdict. |
| F18-F20 shape-program expressiveness | Done | Add new primitives only for demonstrated authoring gaps. |

### Validation

- Complete the separate-machine public-repository install.
- Add vehicle, garment, and asymmetric-prop live evidence.
- Add Meshy multi-image and studio-endpoint live evidence.
- Keep future Blender versions in compatible-but-untested status until their own
  tagged smoke evidence exists. The continuous matrix remains 4.2, 4.5, and
  5.1.

---

## 3. Deferred Or Conditional

- MCP credential-forwarding generalization is not required by the current
  Blender-owned credential flow.
- Hunyuan3D/TRELLIS direct launchers wait for hardware or service ownership.
- F6 automatic sizing and broader F7 decomposition wait for subject evidence.
- Sculpt repair loops and adaptive shape programs remain advanced tools, not
  primary launch claims, until their convergence and quality limits narrow.

---

## 4. Launch Posture

**Lead with:** image-to-3D generation, explicit provider choice and spend
approval, script trust, checkpoints, preview Commit/Revert, evidence capture,
provider diagnostics, source-staleness detection, packaged installation, and
the honest measurement story.

**Qualify clearly:** TripoSR is a local single-view blockout route; generated
provider topology may need cleanup; the studio endpoint is implemented but not
live-proven; Hunyuan3D and TRELLIS are strategy-only; silhouette conformance is
not an overall model-quality verdict.

**Do not lead with:** automatic semantic decomposition, the sculpt repair loop,
or adaptive shape programs. They are useful bounded capabilities with known
quality and convergence limits.
