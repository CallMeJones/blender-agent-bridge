# Diagnostics And Recovery

## End-To-End Connection Doctor

When the `blender-bridge` command is available, use `blender-bridge doctor` for
a deterministic read-only check of the MCP process, socket, Blender health,
version/registry parity, five-tool manifest, schema lookup, and gateway scene
inspection. Use `--json` for structured output and `--client-config <path>` to
inspect the `blender` entry in any supported JSON or TOML MCP client config
without returning its environment values. The selected config's URL and token
must drive the probe; explicit overrides must match it. Reject remote plaintext
HTTP before opening a socket or sending authentication.

Classify the failing layer before suggesting recovery:

- missing command or server path: replace the client entry;
- TCP refused: start Blender's bridge or correct the port;
- TCP accepted but HTTP is wrong: investigate an occupied port;
- HTTP 401: replace the bridge token;
- registry/protocol mismatch: align add-on and connector versions;
- current runtime passes but the client differs: restart or refresh the client.

The doctor probe is non-mutating and does not require script trust.

## Bridge Timeout

A `bridge_timeout` can mean Blender is still completing a main-thread operation.

1. Read `poll_after_seconds` and any active-operation metadata.
2. Wait at least that interval.
3. Call `blender_bridge_status`.
4. Inspect visual evidence resources, job status, diagnostics, or audit state relevant to the operation.
5. Retry only when the previous operation is known to have stopped or failed.

Never blindly rerun a bake, import, render, or broad script after a timeout.

For a failed authored script, restore only the checkpoint returned by that script call. Confirm the restore reports `trust_preserved=true`, correct the complete script from the exact traceback, and rerun the cohesive pass. Do not fragment the retry into primitive helpers solely because the first script failed.

## Long Operations

Prefer asynchronous helpers for downloads, imports, and final or long renders:

- start the job;
- preserve the returned job identifier;
- poll the matching status helper at its requested interval;
- wait for a terminal state;
- validate output before reporting completion.

A submitted job is not a completed job.

For a long cohesive authored script, use the trusted-script job sequence:

1. Invoke `start_trusted_script_job` while runtime script trust is active.
2. Poll `get_trusted_script_job_status`; use the returned log and progress rather than rerunning.
3. Cancel with `cancel_trusted_script_job` when the user requests cancellation or the job is known to be stuck.
4. Inspect the completed result metadata.
5. Invoke `apply_trusted_script_job_result` only after explicit user approval to replace the live file.

The job edits a copied `.blend`. Applying the result first checkpoints the live file and preserves active runtime trust across the file change.

## Scene And File Diagnostics

Use `get_blend_file_diagnostics` before risky work or when save, dependency, checkpoint, or recovery state matters. Use targeted inspectors for scene objects, materials, modeling quality, simulations, renders, and evidence resources.

Only recommend a checkpoint, autosave, backup, render, or cache path after a current tool result verifies that exact path and its restorable or readable state.

## Stale Client Manifest

Before claiming a helper is missing:

1. Search the gateway.
2. Fetch the named helper schema directly.
3. Check bridge and registry compatibility diagnostics.

Refresh or restart the MCP client only when the server configuration or registry version actually changed. Do not broaden `tools/list` to work around client caching.

## Recovery Report

State:

- the last confirmed operation;
- whether it may still be running;
- diagnostics inspected;
- verified recovery artifacts;
- the next safe call.
