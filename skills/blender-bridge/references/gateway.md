# Five-Tool Gateway

## Stable Surface

The default MCP manifest contains exactly:

- `blender_bridge_status`
- `blender_tool_catalog`
- `search_blender_tools`
- `get_blender_tool_schema`
- `invoke_blender_tool`

The helper registry remains available behind these gateways. Top-level omission is a token optimization, not a capability boundary.

## Discovery Sequence

1. Check `blender_bridge_status` when live Blender state matters.
2. Search with a task-specific phrase and `include_schemas=false`.
3. Choose `draft_script` for trusted authored mutation, or one bounded helper from its name, description, annotations, and risk.
4. Fetch that selected tool's current schema.
5. Invoke it with only schema-declared arguments.
6. Use returned names, identifiers, warnings, and next calls as runtime state.

Search again when the task changes domains. Do not keep unrelated schemas in context.

For a mixed request, keep one authored script handoff and separate operational calls. A request to build and animate a product, render frames, and capture evidence means: plan and run the cohesive authored script, then use render and evidence helpers. It does not mean replacing construction and animation with helper chains.

Treat phrases such as "helpers only," "with helpers," "helper path," "without Python," and "no script" as explicit helper overrides. The mere presence of required operational helpers is not an override.

## Planner Output

Planner results may include helper names, `next_tool_calls`, `deferred_tool_calls`, schema lookups, gateway calls, or argument templates.

- Follow executable calls in order.
- Resolve a deferred call only after its stated inputs or blocker are satisfied.
- Honor `execution_strategy`; helper fallback calls are alternatives, not implicit next mutations, when the selected path is a cohesive trusted script.
- When a director plan gates a script on asset selection, import completion, target refresh, or a nested brief, clear those gates before invoking the script even if `draft_script` also appears prominently in search results.
- Replace `<complete_llm_authored_blender_python>` only with a complete script derived from resolved planner inputs and only after its completion gate passes.
- Substitute actual returned object names and job identifiers into templates.
- Fetch the current schema even when a planner supplied likely arguments.
- Continue after planning when the user requested execution.

## Replayable Runs

For substantial modeling, animation, material, rigging, or look-development work:

1. Discover and invoke `start_execution_trace` unless a trace is already active.
2. Run normal gateway discovery and invocation. The bridge records compact arguments, results, durations, and contracts. The starting prompt is hashed and counted, not stored verbatim.
3. Keep generated Python in local trace artifacts; do not paste it into repeated status calls.
4. Invoke `finalize_execution_trace` with the observed outcome and provider-reported token usage.
5. Use `prepare_execution_trace_replay` only as a dry-run plan. Mutation and stored script code remain withheld until explicitly requested and approved.

Traces improve reproducibility without expanding top-level `tools/list`.

## Token Discipline

- Keep search results compact.
- Fetch one selected schema at a time.
- Reuse `known_digest` when the client has a prior schema digest.
- Never duplicate helper schemas in prompts or skills.
- Never reconnect merely to expose every helper directly.

## Error Handling

Treat schema and invocation errors as concrete evidence:

- On an unknown helper, search for its current name or closest supported operation.
- On validation failure, reread the schema and correct arguments.
- On a permission, trust, or preview blocker, follow the returned recovery guidance.
- On timeout, use the diagnostics workflow before retrying.
