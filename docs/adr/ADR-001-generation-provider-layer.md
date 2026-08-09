# ADR-001: Image-To-3D Generation Provider Layer

**Status:** Proposed
**Date:** 2026-08-04
**Deciders:** Repository owner
**Supersedes:** none

## Context

A generation provider layer was added to route image-to-3D work across local models
(TripoSR, Hunyuan3D, TRELLIS), a self-hosted studio endpoint, and hosted APIs (Tripo,
Meshy). Shipped so far: `generation_providers.py` (capability table, egress policy,
hardware probe), `generation_clients.py` (verified Tripo v3 client), add-on preferences,
and one read-only tool `get_generation_provider_diagnostics`.

Three decisions are still open, and all three become expensive after the first release
because tool names, `order`, and the registry digest are compatibility-sensitive.

Forces at play:

- **Deployment spread is the whole point.** The reference machine is an 8 GB Turing card
  that can run only TripoSR; a studio may have a 40 GB card or a shared inference box.
  The same tool surface must serve both.
- **Studios often cannot upload client art at all.** This is contractual, not a
  preference, and it makes local support a requirement rather than an optimisation.
- **Generation is slow and remote.** A hosted task is submit-then-poll over minutes.
  Blender's bridge handlers run on the main thread via `bpy.app.timers`; anything
  blocking there freezes the UI and every queued bridge request.
- **Empirical result from this session:** the single-image path (TripoSR) produced a
  bas-relief rather than a model. Multi-view conditioning is the case worth optimising
  for, and multi-view means several uploads per job.

Connectors note: no knowledge base or project tracker is authorised in this session, so
no prior ADRs were searched and no tickets were created. This is the first ADR in the
repo; `docs/adr/` is created by this file.

---

## Decision 1: Reuse `asset_jobs` rather than growing a second job lifecycle

**Decision: reuse.** Generalise the provider dispatch in `asset_jobs` /
`asset_job_worker` and register generation backends as job providers.

### Options Considered

#### Option A: Reuse the existing async job machinery

| Dimension | Assessment |
|---|---|
| Complexity | Medium — one dispatch seam to open, two call sites |
| Cost | ~1 day; touches two shared modules |
| Scalability | High — inherits subprocess isolation, cancel, restart recovery |
| Team familiarity | High — the pattern is already documented and used |

**Pros**
- `asset_job_worker.run()` is already a clean two-branch dispatch producing a manifest
  (`asset_job_worker.py:134-156`). Its contract is exactly "produce a cached file plus a
  manifest", which generation satisfies: upload → submit → poll → download → manifest.
- The worker runs in a **subprocess**. A generation job polling a remote API for minutes
  never touches Blender's main thread. This is the single strongest argument: it is the
  difference between a UI freeze and a background job.
- Inherits, at no cost: job dirs under the capture root, atomic metadata, progress
  callbacks, cancel, status recovery across bridge restarts, log tail, root-confined
  delete, and the `bpy.app.timers` import queue that mutates the scene safely.
- Inherits the whole tail: `start_external_asset_import_job`,
  `prepare_imported_asset_presentation`, `external_asset_cache_diagnostics`,
  `prune_external_asset_cache`.
- Provenance stamping (`ASSET_PROVIDER_PROPERTY`, `ASSET_SOURCE_URL_PROPERTY`) comes
  free and matters **more** for generated assets, because `ProviderSpec.license_note`
  records per-vendor output-rights terms that must travel with the object.

**Cons**
- `provider` on an existing public tool widens from "asset catalog" to "asset source".
- `asset_jobs._redacted_parameters` (`asset_jobs.py:203`) needs a per-provider redaction
  hook instead of its current `if/elif`.
- Two hard-coded allowlists must be replaced: `asset_jobs.py:546` and
  `asset_job_worker.py:138`.

#### Option B: Keep a separate generation lifecycle

| Dimension | Assessment |
|---|---|
| Complexity | Low to start, High to finish |
| Cost | Low now; ~1000 lines duplicated later |
| Scalability | Low — main-thread polling unless a second worker is written |
| Team familiarity | Low — a second protocol to learn and document |

**Pros**
- No changes to shared modules; zero risk to the existing asset path.
- Generation-specific concepts (credits, task ids, model versions) stay unentangled.

**Cons**
- Duplicates the entire job lifecycle, including the parts that are easy to get wrong:
  cancel, restart recovery, atomic status writes, safe scene mutation.
- **Two polling protocols in one public tool surface.** `TripoClient.task_status()`
  already returns `{status, terminal, succeeded, progress, model_url}` while `asset_jobs`
  returns `{status, progress, poll_after_seconds, manifest_path, manifest_summary}`. An
  agent would need to know which kind of job it started to know how to poll it.
- Without a subprocess worker, polling blocks Blender's main thread.

### Trade-off Analysis

Option B is cheaper this week and more expensive every week after. The decisive factor is
not code volume but the **subprocess boundary**: generation is long-running remote I/O,
and `asset_jobs` already solved running that off Blender's main thread. Rebuilding that
correctly is the hard part, and it is the part Option B defers.

The counter-argument — that generation is a different verb (synthesise vs discover) — is
real but applies to the *head* of the pipeline, not the tail. Discovery differs; caching,
manifesting, importing and presenting are identical.

### Consequences

- Easier: generation gets cancel, recovery, provenance, cache diagnostics and pruning for
  free, and agents learn one polling protocol.
- Harder: two shared modules change, so the existing Poly Haven / Sketchfab paths need
  regression coverage before and after.
- Revisit if: a provider needs a fundamentally different artifact shape than
  "one cached file plus manifest".

---

## Decision 2: Session-scoped credentials by default, persistence as explicit opt-in

**Decision: follow the existing session-token pattern**, generalised from Sketchfab-specific
globals into a small keyed store. Keep persistence available but off by default and clearly
labelled.

### Options Considered

#### Option A: Session-only (match the Sketchfab precedent)

| Dimension | Assessment |
|---|---|
| Complexity | Low — generalise 4 existing functions |
| Cost | Hours |
| Security | Strong — key never written to disk |
| Ergonomics | Weaker — re-enter each Blender launch |

The repo already answers this exact question:
`external_assets.set_session_sketchfab_api_token` (`external_assets.py:69-83`) keeps the
token in process memory only, driven by `CLAUDEBLENDER_OT_set_session_sketchfab_token`.

#### Option B: Persist in add-on preferences (as currently shipped)

| Dimension | Assessment |
|---|---|
| Complexity | Already done |
| Cost | Zero |
| Security | **Weak — plaintext in `userpref.blend`** |
| Ergonomics | Best — set once |

`bpy.props.StringProperty(subtype="PASSWORD")` masks the widget but does not encrypt
storage. The property descriptions already admit this, which is a tell that the weaker
option was shipped knowingly.

#### Option C: Both, with session preferred

Session store is the default path; a clearly-labelled "remember on this machine" toggle
writes to preferences for solo users who want it.

### Trade-off Analysis

The project currently has **two policies for one class of secret**, and the newer one is
weaker — a third-party API key that bills real money is stored less carefully than a
Sketchfab download token. That inconsistency is the actual defect; either policy applied
uniformly would be defensible.

Option C respects the reality that a solo artist on a personal machine and a studio under
an IP agreement want different things, while making the safe choice the default. It also
composes with Decision 1: once the MCP forwarding table is generalised
(`mcp_server.SKETCHFAB_AUTH_FORWARD_TOOLS:78` → a `{tool: credential_spec}` map), a
locked-down studio can keep keys in the MCP client config and out of `userpref.blend`
entirely.

### Consequences

- Easier: studios can guarantee no key on disk; one credential mechanism to reason about.
- Harder: session keys must be re-entered per launch unless the user opts in.
- Revisit if: an OS keyring integration becomes worth the cross-platform cost.

---

## Decision 3: Give generation its own registry domain — now, not later

**Decision: create `tool_registry/domains/generation.py`** and move
`get_generation_provider_diagnostics` into it at a fresh order band (1900+), **before**
the tool surface is published.

### Options Considered

#### Option A: Own domain

| Dimension | Assessment |
|---|---|
| Complexity | Low — one new module in `DOMAIN_MODULES` |
| Cost | Minutes now; a public rename plus digest change later |
| Clarity | High — the module boundary matches the registry boundary |

**Pros**
- `generation_providers.py` and `generation_clients.py` already declare generation as a
  peer subsystem; the registry currently disagrees with the code layout.
- `external_assets` is defined by "discover a *published* asset in a catalog, cache it,
  import it". Generation synthesises a new asset from reference images — it shares the
  tail, not the head, and its inputs come from the reference pipeline that `modeling` owns.
- With submit/poll/import tools added, `external_assets` would grow from 19 to ~25 tools
  spanning two unrelated verbs.

**Cons**
- `docs/ADDING_A_TOOL.md` §1 requires justification for a new domain, and one read-only
  diagnostics tool is thin justification *today*.
- Mild tension with Decision 1: if generation rides `start_external_asset_download`, an
  argument exists that `external_assets` is the honest owner.

#### Option B: Stay in `external_assets`

**Pros:** no new domain to justify; precedent exists since
`external_asset_cache_diagnostics` already carries an `auth` block.
**Cons:** the boundary drifts further with every generation tool added, and moving later
costs a public rename plus a snapshot and digest change.

### Trade-off Analysis

These two decisions genuinely pull against each other, and the resolution is to separate
**mechanism** from **surface**. Decision 1 says generation should *reuse the job
mechanism*; that is an implementation detail. Decision 3 concerns the *tool surface an
agent sees*. A generation tool can be owned by a `generation` domain while its
implementation calls into `asset_jobs` — domains describe capability, not plumbing.

Timing is the tiebreaker. `name`, `order` and `owner` are compatibility-sensitive and the
registry digest already gates client compatibility (a mismatch blocked every mutating call
earlier in this session). Moving one tool now is free; moving four tools after release is
a breaking change.

### Consequences

- Easier: generation tools group coherently; `external_assets` keeps one meaning.
- Harder: one more domain module to maintain; `DOMAIN_MODULES` ordering must be chosen
  deliberately.
- Revisit if: generation never grows past two or three tools, in which case the domain
  was over-provisioned but harmless.

---

## Action Items

1. [ ] Replace the hard-coded provider allowlists (`asset_jobs.py:546`,
       `asset_job_worker.py:138`) with a dispatch table mapping
       `provider -> callable(args, progress_callback) -> manifest`.
2. [ ] Register `poly_haven` and `sketchfab` through the new table; add regression tests
       proving both paths are unchanged.
3. [ ] Add a per-provider redaction hook to `asset_jobs._redacted_parameters:203`.
4. [ ] Create `tool_registry/domains/generation.py`; move
       `get_generation_provider_diagnostics` to order 1900; run
       `scripts/update_tool_snapshot.py` and update the three count tripwires.
5. [x] Generalise `set_session_sketchfab_api_token` into
       `set_session_credential(name, value)` / `session_credential(name)`.
       Done in `session_credentials.py`; the Sketchfab helpers now delegate to
       it, so one keyed store serves every provider.
6. [x] Point the generation panel at the session store; add an explicit
       "remember on this machine" toggle. Resolved differently and better than
       written: persistence does not go to `userpref.blend` at all. See the
       amendment below.
7. [ ] Generalise `mcp_server.SKETCHFAB_AUTH_FORWARD_TOOLS:78` into a
       `{tool_name: credential_spec}` table so generation can ride the existing forwarder.
8. [ ] Add generation job tools (`start_generation_job`, status via the shared asset job
       status tool) once items 1-4 land.

## Notes On What Was Already Decided Correctly

Recorded so these are not relitigated:

- **`ProviderSpec` as a declarative capability table.** Adding a seventh model is a data
  entry, not a branch. Every blocker is reported with a remedy rather than the first
  failure only.
- **Egress denied by default, resolved in one place.** Unrecognised values deny; a
  self-hosted endpoint counts as local and needs no egress.
- **bpy-free, torch-free provider module with injected probe and transport.** Satisfies
  `ADDING_A_TOOL.md` §3 and keeps routing testable headless.
- **Verifying the API against the live service rather than its documentation.** Three
  public sources disagreed; probing established the real shapes, and a zero-credit account
  distinguished "structurally valid" (code 2010) from "malformed" (code 1004) for free.

## Amendment, 2026-08-06: Credentials Go To The OS, Not To Preferences

Item 6 originally proposed a toggle that would persist keys into
`userpref.blend`. Implementing it exposed the reason not to: that file is
unencrypted, is copied between machines with a user's configuration, and
`docs/SAFETY_MODEL.md` already promised keys would not live there. The
generation providers added in this ADR had quietly broken that promise, while
Sketchfab kept a session-only token -- two policies for one class of secret,
with the newer one weaker.

Hashing was considered and rejected outright: it is one-way, so a hashed key
can never be sent to the provider. Encrypting with a key stored beside the
ciphertext was rejected as obfuscation rather than protection.

**Decision.** Credentials take exactly one route, for every provider:

1. The preference field is an entry box only. On assignment the value is moved
   out and the field blanked, so no key is ever written to `userpref.blend` --
   including on the upgrade path, where a key left there by an earlier build is
   migrated out and the field cleared.
2. `session_credentials` holds the value in memory and is the single read path
   for every provider.
3. `credential_store` persists it in the facility the operating system already
   provides: DPAPI on Windows, the login keychain on macOS, Secret Service on
   Linux. Detection round-trips a sentinel before selecting a backend, so a
   tool that is installed but cannot reach its daemon -- the normal case on a
   headless render node -- is not chosen and then found broken on first use.
4. Where no such facility exists, the fallback is a file created `0600`, the
   mechanism `~/.aws/credentials` and `~/.netrc` use. It is reported as
   "readable only by your user account" and never described as encrypted, and
   a file whose permissions have widened is discarded rather than read.

Remembering is on by default, at the user's explicit direction, so a key is
entered once rather than every session.

**Consequence.** Poly Haven keeps no field at all -- its API is open and every
asset is CC0 -- and the panel says why, so the absence does not read as an
oversight. Adding a provider means adding one row to
`preferences.CREDENTIAL_FIELDS`; a test asserts every secret preference is
paired with a credential name, so a new provider cannot quietly reintroduce
disk-only storage.

## Review, 2026-08-06: Decision 1 Held

An architecture review asked whether `asset_jobs` should be split, on the
grounds that it now carries two verbs: catalog downloads (Poly Haven,
Sketchfab) and paid generation (Tripo). Recorded here so the question is not
reopened without new evidence.

**It held.** Decision 1 predicted that discovery differs while caching,
manifesting, importing and presenting are identical, and that is what
happened. The generation path reuses the subprocess worker, cancel, restart
recovery, provenance stamping and the whole import tail without modification.

The one asymmetry that did appear was absorbed rather than leaked. Paid
providers need human spend approval and free ones do not, so the approval gate
sits at `start_external_asset_download` -- the single seam every job of every
kind passes through -- driven by a required `spends_money` field on each
provider's entry in `JOB_PROVIDER_SPECS`. Requiring the field rather than
defaulting it means a provider cannot be added without deciding, and a test
fails if one omits it. Splitting the module would have given the gate two
homes and made "did we gate this provider?" a question with two places to look.

**Revisit if:** a provider needs an artifact shape other than "one cached file
plus a manifest" -- the original revisit condition, unchanged -- or if the two
verbs acquire genuinely different job lifecycles rather than different heads.
Two verbs sharing one lifecycle is the condition this decision was made for.

## Amendment, 2026-08-09: Provider Choice Does Not Gate The Bridge

Generation controls have one ownership boundary: generation. Disabling hosted
egress or setting a restrictive generation session policy must not unregister,
disable, or otherwise change the main bridge, trusted script execution, bounded
modeling helpers, inspection tools, or non-generation asset workflows. When no
generation route is allowed, planning directs the caller back to authored
scripts and helpers instead of treating the bridge as unavailable.

Provider choice is also explicit whenever it is meaningful. The planning tool
asks the user to choose when two or more runnable generation providers satisfy
the request. `start_generation_job` repeats that guard and starts no work when a
caller omits the provider, so skipping the planner cannot silently spend money,
upload an image, or choose a lower-quality route. A sole local/self-hosted route
may auto-select. A hosted route always requires explicit selection, even when it
is the only runnable generation provider.
