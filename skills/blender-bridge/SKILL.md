---
name: blender-bridge
description: Operate Blender Agent Bridge through its stable five-tool MCP gateway for scene inspection, modeling, materials, rigging, animation, simulation, rendering, external assets, trusted scripts, and preview decisions. Use whenever an agent must work in a live Blender scene through Blender Bridge, especially when only gateway tools are exposed, a planner names non-top-level helpers, or a call needs trust, timeout recovery, or commit/revert handling.
---

# Blender Bridge

Treat Blender as the source of truth and execution layer. When the user asks for a scene change, continue through execution and verification; a plan alone is not completion.

## Operate Through The Gateway

1. Call `blender_bridge_status` before work that depends on the live scene.
2. Inspect relevant scene state before mutation.
3. Call `search_blender_tools` with `include_schemas=false`.
4. Split mixed requests into authored and operational work. Select `draft_script` for the authored pass under active trust, and bounded helpers for imports, project files, long renders, bakes, evidence, and preview decisions.
5. Call `get_blender_tool_schema` for that execution target.
6. Call `invoke_blender_tool` with schema-valid arguments.
7. Inspect the result before choosing the next helper.

Use `blender_tool_catalog` as a combined fallback for clients that cannot reliably call the three dedicated discovery operations. Do not request the full catalog or all helper schemas.

A helper named by a planner remains available through schema lookup and gateway invocation even when it is absent from top-level `tools/list`. Never report it as unavailable until schema lookup or invocation returns a concrete error.

Read [references/gateway.md](references/gateway.md) for discovery, schema, invocation, and token-discipline details.

## Preserve Runtime Safety

- Inspect actual object names and refresh scene state after creation, import, rename, or broad mutation.
- With active trust, prefer one cohesive script for object generation, modeling, animation, materials, custom nodes, rigging, and look development unless the user explicitly requests helpers, a helper path, or no Python.
- Do not let operational suffixes such as "render frames," "capture evidence," "save the blend," or "import an asset" suppress the script-first path for separate authored work in the same request.
- Honor a planner's `execution_strategy`: do not execute `helper_fallback_tool_calls` merely because they are listed when the selected path is `cohesive_trusted_script`.
- Replace a deferred `draft_script` code placeholder only after its input handoff and completion gate are satisfied.
- Prefer bounded helpers for inspection, project files, external assets, long jobs, persistent bakes, evidence, preview decisions, or explicitly requested isolated edits.
- When trust is off, use a bounded helper path or ask the user to enable trust before authored work that would materially benefit from a cohesive script.
- Do not claim a script ran unless its result confirms execution.
- Keep reversible changes in preview until the user explicitly chooses commit or revert.
- Do not invent checkpoint, autosave, backup, or output paths.

Read [references/preview-and-trust.md](references/preview-and-trust.md) before scripts or preview decisions.

## Recover Before Retrying

Treat `bridge_timeout` as an uncertain in-progress result, not an immediate failure. Wait for the returned interval, check status, inspect current evidence or diagnostics, and retry only when the prior operation is known not to be running.

Read [references/diagnostics-and-recovery.md](references/diagnostics-and-recovery.md) for timeouts, stale clients, long jobs, and verified recovery.

## Complete With Evidence

Report:

- helpers actually invoked;
- concrete scene targets and outputs;
- validation or visual evidence;
- unresolved blockers;
- whether preview changes remain pending.

Do not infer success from a planner response, a submitted job, or a timed-out call.
