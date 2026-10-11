# Architecture improvements implemented

Implementation of the nine findings in [the architecture review](ARCHITECTURE_REVIEW_2026-10-11.md), starting with the four runtime risks. The external-agent / Blender execution boundary, five MCP gateways, canonical helper contracts, script trust model, and paid-generation approvals remain in place.

| Review finding | Implementation | Verification |
| --- | --- | --- |
| 1. Timed-out requests execute later | `operation_queue.py` owns bounded admission, deadlines, queued/running/terminal states, duplicate-ID protection, result retention, and shutdown. HTTP and MCP expose operation IDs and recovery. Traces and newly created job metadata carry the ID. | Queue concurrency, expiry, duplicate-ID, capacity, tick-budget, retention and shutdown tests; real HTTP expiry/deduplication/recovery smoke; MCP recovery and disconnected-client tests. |
| 2. Failed helpers contaminate pending previews | The executor isolates helpers whose contract requires preview. Success merges into the parent; failure restores only the failed operation. Empty validation/no-op scopes are discarded. Public preview APIs replace cross-module private calls and direct snapshot-storage edits. Twelve domain snapshot types have paired capture/restore codecs in `preview_snapshots.py`. | Failure injection with/without an existing preview; preserved earlier edits; shader socket rollback; live, advanced, animation, sculpt, reference and safe-editing smoke suites. |
| 3. I/O blocks the Blender thread | `execution_lanes.py` explicitly prepares worker plans for catalogs, metadata, downloads, generation diagnostics and cancellation. Asset imports download on a worker and finalize through the preview executor on the main thread. Preferences, paths, network authorization and credentials are captured before work starts. Imports refuse scene finalization if the scene changed during download. | A blocked fake provider leaves independent status requests responsive; worker and finalizer thread assertions; changed-scene rejection; existing offline asset/provider tests. |
| 4. Job cancellation differs across domains | Render and trusted-script jobs use the shared process-group launch/termination helpers. `job_runtime.py` owns child environments, PID observation and atomic status publication, including Windows replacement retries. Asset jobs no longer depend on private render-job utilities. Cancelled render status cannot be overwritten by stale child status. | Actual parent/descendant processes stopped through both domains' cancel and unregister APIs; resistant child fixture; stale-status regression; untracked PID refusal; trusted/render/asset smoke tests. |
| 5. Discovery policy has multiple owners | `tool_catalog.py` owns catalog ranking, category selection, facets and discovery warnings. Reliable registry groups determine external-asset/generation and preview categories. Mixed groups retain their existing category fallback to preserve unrelated rankings. `bridge_client.py` owns HTTP transport and timeout recovery. Schema-budget selection remains distinct. | Existing routing corpus, client-profile routing, gateway/direct/full inventory checks and generation-category regressions. |
| 6. Transport validators disagree | `schema_validation.py` is the shared dependency-free validator. MCP and the bridge both invoke it; raw HTTP no longer coerces invalid argument containers to empty objects. | Identical numeric-bound, finite-number, nested-array, object and combinator corpus through both entry points; malformed raw calls are rejected before execution. |
| 7. Worker modes duplicate provider dispatch | `asset_provider_execution.py` accepts explicit credentials, progress and cancellation callbacks. Thread and subprocess adapters share dispatch and argument adaptation. Spend approval, provider capabilities, credential transport and scene import retain their separate responsibilities. | Provider-mode argument/result parity and cancellation tests; offline generation and asset worker tests; Blender asset-import/job smoke tests. |
| 8. Reload misses active modules | Every shipped module has an explicit lifecycle classification: reloadable, persistent, external runtime or package. Previously omitted implementations now reload in the declared order. Session credentials remain persistent and saved credentials do not overwrite a newer in-memory value during reload. | Complete, non-overlapping inventory check; actual unregister/reload/register sentinels; queued work is cancelled; credentials survive and script trust remains off after reload. |
| 9. CI omits smoke tests | `tests/smoke_manifest.json` is consumed by `scripts/run_smoke_suite.py` locally and in CI. It covers every smoke script, with runtime, lane, timeout, success marker and explicit exclusion reasons. Seven previously omitted tests are in ordinary CI. Generated-manifest evaluation now has a deterministic local fixture. Tests intended for source validation load the checkout rather than an installed extension. | Manifest completeness checks; complete deterministic Blender and Python smoke runs; workflow YAML parsing; build and artifact-identity checks. |

**Operation recovery contract**

Raw `POST /tool` accepts an optional top-level `operation_id`. Both invocation gateways accept it alongside `name` and `arguments`; MCP generates an ID when omitted. The ID is returned on success, timeout and ambiguous connection failure. Call `blender_bridge_status` with `{"operation_id": "the-returned-id"}`, or authenticated `GET /operation?operation_id=...`, to retrieve the state and retained response without entering Blender's scene queue.

Reusing a retained ID with the same tool and arguments returns the same operation. Reusing it with different inputs is rejected. A request that times out before starting is expired and will never run. Running Blender code is allowed to finish; its result can be recovered. Stopping the bridge cancels queued work and discards outstanding worker scene finalizers.

Defaults are 128 outstanding operations, four I/O workers, at most eight main-thread callbacks or 10 ms between callbacks per timer tick, and a completed-history bound of 256 records / 32 MiB of serialized result data. These are bounds between callbacks; they cannot preempt one long-running Blender call. Result retention is in memory and bounded. A missing operation after eviction or restart is not evidence that a mutation did not happen. Clients must inspect the scene/job state before submitting a new mutation; they must not automatically retry an ambiguous operation after its record is gone.

**Intentional behavior corrections**

- Failed preview operations preserve earlier successful edits while removing their own changes. Validation failures do not leave empty transactions.
- Shader snapshot restoration now reaches its specific codec instead of being intercepted by the generic diffuse-color branch.
- MCP rejects invalid numeric/combinator arguments earlier, consistently with the raw bridge.
- Generation/external-asset tools use their registry groups for category filtering, fixing previously uncategorized generation helpers.
- Local asset cancellation occurs before waiting for remote provider cancellation. Running external I/O cannot be forcibly interrupted as Python code; scene finalization is suppressed during shutdown.
- Ordinary scene operations, preview commit/revert, project replacement and checkpoint-backed trusted scripts retain their respective execution semantics. Only declared I/O tools use workers; read-only annotations alone do not grant worker eligibility.

**Reproducing verification**

```powershell
python -m unittest discover -s tests/unit -p 'test_*.py'
python scripts/run_smoke_suite.py --lane release --environment python
python scripts/run_smoke_suite.py --lane release --environment blender --blender 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe'
python scripts/reference_benchmark_regression.py
python -m build --no-isolation
python scripts/build_extension_repository.py --build-zip --repo-dir public --repository-url https://callmejones.github.io/blender-agent-bridge/index.json
python scripts/run_smoke_suite.py --lane artifacts --environment python
```

Use `--list` to inspect a lane, `--test NAME` to rerun one case, and arguments after `--` for a selected fixture/publication test. The runner saves per-test logs under `.dev-session/smoke-results` and terminates a timed-out test's process tree.

The deterministic manifest contains 33 Blender smokes, 13 Python smokes and one post-build artifact check. Live provider services, publication URLs and the real texture-baked TripoSR fixture are separate lanes with explicit prerequisites. Local Blender validation uses 5.1.2 on Windows; the existing Linux 4.2/4.5/5.1 CI matrix remains configured but was not executed locally. No paid provider requests or publication were needed for this work.

Final local results: **594 unit tests run, 592 passed and two existing skips; 33/33 Blender smokes; 13/13 Python smokes; 1/1 artifact-identity check.** The offline reference benchmark, wheel/source-distribution build, extension build/validation, workflow YAML parse, all 143 add-on module parses and `git diff --check` also passed. The final raw-HTTP and package-reload regressions passed again after their last edits.

Detailed evidence is retained in `.dev-session/implementation-unit-final.log`, `implementation-blender-final.log`, `implementation-python-final.log`, `implementation-final-followups.log`, the build/benchmark logs, and per-test smoke logs. The pre-existing documentation edits and parked stash were preserved.
