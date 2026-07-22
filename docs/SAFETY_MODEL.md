# Safety Model

## Core Principle

External agents can suggest changes, inspect scene state, and call narrow tools. They should not receive unchecked authority to run arbitrary Python in Blender by default.

## Execution Modes

### Suggest Only

External agents can analyze and draft code, but nothing runs.

Use this when:

- The user is exploring an idea.
- The script touches file paths, deletes data, imports modules, or edits many objects.
- The model is using unfamiliar APIs.

### Binary Script Trust

Generated Python has one session-wide switch; there is no per-script approval queue.

- With **Trust Agent Scripts** off, `draft_script` is refused without creating a Text datablock or pending UI.
- With trust on, ordinary generated Python runs immediately after static checks. Blocked scripts are refused and never staged.
- Trust is runtime-only and lasts until **Revoke**, add-on reload, file load, or Blender exit. Starting or stopping the bridge does not silently change the user's choice.
- `draft_privileged_script` and `run_approved_script` remain compatibility endpoints but always refuse execution. Privileged generated Python cannot be enabled by session trust.
- Filesystem, network, external-asset, project-file, render, capture, save, and persistent-cache outcomes must use bounded structured tools. Persistent simulation bake scripts are disabled; inspect first and bake manually in Blender.
- Static checks are guardrails, not a sandbox. A trusted ordinary script executes inside Blender with Blender's OS permissions, so the switch means trusting the connected agent for the current session.
- Execution pushes a Blender undo step when possible, saves a timestamped `.blend` checkpoint when enabled, and records stdout/errors in `Agent Bridge Script Log`.
- The single sidebar contains connection controls, the binary trust/revoke control, and pending preview **Commit**/**Revert** actions only. The removed **Run Now**, **Reject**, and **Allow Agent Once** operators are not registered.

### Limited Autonomous

External agents can call only allowlisted tools such as `inspect_scene`, `capture_viewport`, `capture_animation_playblast`, `capture_object_inspection_renders`, `set_object_transform`, or `add_light`. Arbitrary Python stays blocked.

Use this later for fast iterative workflows.

### Live Helpers

External agents can apply low-risk helper changes immediately to the open scene. Each change must be part of a preview transaction with visible commit/revert controls.

Use this for transforms, primitive/empty creation, object visibility/display, materials, UV unwraps, bounded map-bake artifact output, lights, cameras, timeline settings, camera orbit setup, bounded keyframe edits, and bounded advanced helpers such as shader material setup, Geometry Nodes starter modifiers, shape keys, text/curve creation, simple particles, basic armatures, copy-transform constraints, render settings, camera settings, and world background color.

Advanced helpers are not a general Blender automation sandbox. They should create or edit narrow, reversible data-blocks. Custom geometry-node networks, production rigs, compositor graphs, simulations, destructive mesh operations, import/export, and broad scene edits should stay in approval-required Python.
Refinement templates are also bounded live helpers. They may create multiple primitives/materials/curves at once, but every created data-block must be recorded in preview rollback. Templates should improve composition and detail without pretending to replace real topology modeling.

### External Bridge / MCP

External clients can connect through the optional localhost bridge and stdio MCP server. This does not create a second safety model; it exposes the same tools/resources through a different transport.

Defaults and boundaries:

- The bridge is off until the user starts it from Blender.
- The bridge binds only to `127.0.0.1`.
- Add-on preferences can require a bearer token for HTTP bridge requests.
- MCP clients call `mcp_server.py`; they do not import Blender Python or touch `bpy`.
- Mutating helper tools still run inside Blender and use the live-preview/revert path.
- Generated Python is refused while session script trust is off. With trust on, `draft_script` runs ordinary scripts after static checks.
- External script trust can run animation-like and helper-overlap scripts after static checks pass. Responses may still include helper advice so clients can choose a structured helper path when it clearly fits.
- Privileged generated scripts and persistent simulation/cache bake/free scripts are disabled. Use bounded structured tools or perform the operation manually in Blender.
- Viewport screenshots, sampled animation playblast frames, inspection renders, render thumbnails, and async render-job outputs exposed through MCP resources are local artifacts. Saved `.blend` files use a project-local `.claude_blender/captures/` folder by default, while unsaved or unwritable projects use Blender's extension user-data directory. Async render jobs launch a background Blender process from a temporary `.blend` copy and can be cancelled with `cancel_render_job` while the bridge session is tracking the process.
- MCP search summaries, schema lookups, and tool-call results may include `guardrail_warnings` for client routing and recovery. These warnings are advisory; Blender-side path checks, approval gates, preview rollback, and static script analysis remain the enforcement layer.
- The Blender sidebar surfaces only connection state, binary session trust, and pending preview decisions. Source freshness, recovery, audit, rollback, active-operation, and visual-evidence details remain available through bridge/tool responses rather than a secondary Blender panel.
- External clients should surface tool calls clearly because MCP tools are model-controlled.

## Risk Checks

Flag or block proposed scripts that include:

- File deletion, overwrite, or broad filesystem traversal.
- Network calls from generated scripts.
- Shell/process execution.
- Dynamic imports, `exec`, `eval`, `compile`, or unsafe deserialization.
- Attempts to read environment variables or credential files.
- Large destructive scene operations without a checkpoint.
- Infinite loops or modal handlers that are hard to stop.
- Use of `bpy.ops` without clear context/mode reasoning.
- Deleting or renaming many objects, collections, materials, or actions.
- Mutating linked library data without warning.

These checks are guardrails, not a true sandbox. Blender Python runs with broad local privileges, so session trust and checkpointing remain essential.

Live-preview reverts return a rollback manifest and warnings when restoration is incomplete. This is visibility, not a guarantee that every possible Blender API mutation is reversible.

If a helper call opens a new preview transaction and then fails, the dispatcher auto-reverts that new transaction and reports `auto_reverted_preview` plus the rollback manifest in the failed tool result. A preview transaction that already existed before the failed call is preserved instead of being unwound.

## Safer Defaults

- Prefer helper tools for simple edits.
- Allow live preview only for typed helper tools with rollback support.
- Prefer direct `bpy.data` and RNA API changes over context-sensitive operators when possible.
- Require docs lookup before unfamiliar or version-sensitive scripting.
- Require a change plan before non-trivial generated Python.
- Keep arbitrary Python disabled for limited autonomous mode.

## Privacy Rules

- Do not store provider API keys in Blender Agent Bridge.
- Let users toggle screenshot inclusion.
- Let users choose whether file paths, object names, material names, and custom properties are sent.
- Do not send raw mesh data unless the user requests it.
- Do not send the full docs cache, full scene graph, or large tool output; send compact summaries and top matching snippets.
- Keep transcripts local by default.
- Warn before using beta file upload features with different retention behavior.

## Recovery

Before trusted execution:

- Push an undo step when possible.
- Save a timestamped bridge-created `.blend` checkpoint when checkpoints are enabled.
- Record the generated script and result log locally.
- Require active session script trust before accepting `draft_script`.
- Refuse blocked or privileged scripts without creating a pending approval state.
- For animation-like scripts, enforce workflow-first routing before considering trust auto-run.

During live preview:

- Record before-state for each helper step.
- Keep the transaction pending until the user commits it.
- Provide a one-click revert for pending preview changes.
- Show rollback coverage and warnings after commit/revert.
- Escalate to approval-required mode when rollback state cannot be captured confidently.

After execution:

- Show success/failure clearly.
- Offer undo for the last action.
- Offer explicit restore of the last bridge-created checkpoint.
- Return execution errors and checkpoint status back through tool results so the external client can draft a repaired script without running it automatically.

## Documentation Access

Docs access should be restricted to official sources by default:

- `docs.blender.org`
- `projects.blender.org/blender`
- `developer.blender.org` only when API/manual docs are insufficient

The docs tool should return focused snippets and source URLs. It should not scrape unrelated web content in MVP.
