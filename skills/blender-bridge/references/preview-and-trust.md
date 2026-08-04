# Preview And Script Trust

## Preview Contract

Mutating helpers can leave a live preview transaction pending.

- Inspect the tool result for preview state and changed targets.
- Capture or inspect evidence before asking for a decision.
- Call `commit_preview` only after explicit user approval.
- Call `revert_preview` only after explicit rejection, a requested rollback, or verified cleanup need.
- Fetch each decision tool's current schema before invocation.
- Report pending preview honestly when no decision has been made.

Do not silently commit because a task appears successful. Do not revert merely because more work is required; continue repairing inside the supported preview workflow.

## Script Trust

`draft_script` is available through the gateway, but generated Python is controlled by Blender's runtime-only **Trust Agent Scripts** switch.

With trust off:

- Blender refuses generated Python.
- No pending per-script approval is created.
- Use bounded helpers when they can deliver the requested result.
- For authored object, animation, material, node, rig, or look-development work, ask the user to enable trust when a cohesive script is the higher-quality path.

With trust on:

- Generated Python runs immediately.
- It is checkpoint-backed, not a live preview transaction; `commit_preview` and `revert_preview` do not apply to its changes.
- It has Blender Run Script-equivalent filesystem, network, process, project-file, cache, and Blender API access.
- Static findings are advisory rather than an approval boundary.
- Opening, creating, restoring, copying, renaming, saving, or modifying `.blend` files does not change the active runtime grant.
- A timed grant keeps its original expiry across every file operation.
- Revoke, timed expiry, add-on reload, or Blender exit clears trust.
- Verify the result confirms execution, such as `auto_ran=true`, before claiming success.

## Scripted Authoring

Before using `draft_script`:

1. Inspect the scene and relevant targets.
2. Confirm trust is active and the user did not request helpers.
3. Build the script from the current brief, target names, and measured scene state.
4. Read `bpy.app.version` and inspect RNA `enum_items` before assigning version-sensitive identifiers.
5. Prefer one cohesive, idempotent script over fragmented snippets or long primitive-helper chains.
6. Supply complete `intent`, `expected_changes`, `risk_level`, `code`, and any schema-required targets.
7. Inspect outputs, errors, changed objects, and preview state.
8. When the user requires a pending preview, use bounded preview helpers or clearly disclose that trusted-script changes are checkpoint-only before execution.
9. On failure, restore the checkpoint, confirm trust remains active, and repair the script from the traceback before reducing scope or changing execution mode.

Use bounded project-file, asset, render, capture, save, and cache helpers when their validation or recovery is valuable, even while trust is active.
