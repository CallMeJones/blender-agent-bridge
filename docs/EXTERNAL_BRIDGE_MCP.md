# External Bridge And MCP

## MCP Runtime Choice

The extension defaults to **Bundled**, which launches the pure-Python MCP server shipped inside the installed Blender extension and requires no `uv` installation. **uvx / PyPI** launches the matching zero-dependency `blender-bridge` distribution, avoiding dependence on Blender's extension filesystem path. It does not replace the Blender extension or the localhost bridge.

Select the runtime in Blender preferences before using **Copy MCP Config**. Generated `uvx` configs pin the extension version:

```text
uvx --from blender-bridge==0.4.0 blender-bridge
```

Windows configs use `cmd /c uvx ...`; macOS and Linux invoke `uvx` directly. Blender detects a missing executable and shows installation guidance but never installs software automatically. See the [client guide matrix](clients/README.md) for complete formats.

Both launch modes send the bridge protocol and canonical tool-registry digest in their status/config handshake. Protocol or registry mismatch prevents tool calls with a compatibility error. A version difference remains a warning when protocol and digest match. Bundled mode additionally reports source-tree hashes; uvx mode deliberately does not compare filesystem layouts.

## Goal

Blender Agent Bridge exposes the live Blender scene to external agents through a localhost bridge and a stdio MCP server. This is the Codex/Claude Code style path: Blender keeps direct `bpy` access, while external clients discover tools/resources and call them over a standard protocol.

## Architecture

```text
MCP client
  -> stdio JSON-RPC
  -> addon/claude_blender/mcp_server.py
  -> HTTP JSON on 127.0.0.1
  -> bridge_server.py inside Blender
  -> tool_dispatcher.py / context_bundle.py / bpy
```

The add-on owns all Blender reads/writes. The MCP server is a small stdlib Python process that forwards requests to Blender's local bridge.

## Start The Bridge

1. Install and enable the latest `claude_blender-<version>.zip` release asset.
2. Open the add-on sidebar in the 3D View.
3. In `External Bridge`, press `Start`.
4. Optional: set `Bridge Token` in add-on preferences before starting.
5. Press `Copy MCP Config` and paste it into a client that supports local MCP servers.

The bridge binds only to `127.0.0.1`. It does not listen on your LAN.

## MCP Config Shape

The copied config looks like this:

```json
{
  "mcpServers": {
    "blender": {
      "command": "python",
      "args": [
        "C:/path/to/claude_blender/mcp_server.py",
        "--bridge-url",
        "http://127.0.0.1:8765"
      ]
    }
  }
}
```

If you set a bridge token, the copied config includes:

```json
{
  "env": {
    "BLENDER_BRIDGE_TOKEN": "your-token"
  }
}
```

The copied config also includes safe metadata in the MCP server `env` block, such as `CLAUDE_BLENDER_ADDON_VERSION`, `CLAUDE_BLENDER_ADDON_SOURCE_HASH`, `CLAUDE_BLENDER_BRIDGE_VERSION`, `CLAUDE_BLENDER_MCP_SERVER_VERSION`, `CLAUDE_BLENDER_MCP_CONFIG_VERSION`, `CLAUDE_BLENDER_MCP_RUNTIME_MODE`, `CLAUDE_BLENDER_TOOL_REGISTRY_DIGEST`, and a short `CLAUDE_BLENDER_MCP_CONFIG_NOTE`. These fields behave like a comment for humans while remaining valid JSON for stricter clients; runtime mode and registry digest additionally participate in compatibility diagnostics.

## Client Env Auth

Poly Haven needs no API key. For Sketchfab downloads, use `Copy MCP Config`, fill the empty `SKETCHFAB_API_TOKEN` environment field in the client configuration, then restart or refresh the client. The token is not saved in Blender preferences, `.blend` files, or audit logs.

External asset downloads connect directly instead of using system HTTP proxies. This keeps DNS validation and the connected destination under the same security check, but networks that require an outbound proxy must allow direct access to the provider/CDN or downloads will fail with a connection error.

OAuth is a future improvement; the current supported path is `SKETCHFAB_API_TOKEN`, with `BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN` as a bridge-specific alias.

Claude Desktop-style JSON:

```json
{
  "mcpServers": {
    "blender": {
      "command": "python",
      "args": [
        "C:/path/to/claude_blender/mcp_server.py",
        "--bridge-url",
        "http://127.0.0.1:8765"
      ],
      "env": {
        "SKETCHFAB_API_TOKEN": "your-sketchfab-api-token"
      }
    }
  }
}
```

Codex-style TOML:

```toml
[mcp_servers.blender]
command = "python"
args = ["C:/path/to/claude_blender/mcp_server.py", "--bridge-url", "http://127.0.0.1:8765"]

[mcp_servers.blender.env]
SKETCHFAB_API_TOKEN = "your-sketchfab-api-token"
```

The bridge-specific alias `BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN` is also accepted.

When a Sketchfab download/import is called through MCP, `mcp_server.py` resolves those environment variables in the Claude/Codex-launched MCP process and forwards the credential to Blender as a redacted per-call tool argument. This is deliberate: Blender itself usually does not inherit the MCP client's environment. For direct HTTP bridge calls that bypass MCP, put the credential in Blender's process environment or pass it as a per-call argument.

Use `blender_bridge_status` to check `mcp_external_asset_auth.sketchfab` and confirm whether the running MCP process actually inherited Sketchfab API-token auth. Use `get_external_asset_cache_diagnostics` to inspect cached assets and the Blender-process auth view.

## MCP Client Refresh

Some clients cache MCP tool lists, server paths, or environment values. After installing a new zip, reloading the add-on, or pressing `Copy MCP Config`, replace the old client config and refresh or restart the MCP client. If `blender_bridge_status` reports a different add-on, bridge, MCP server, config version, or source hash than Blender's sidebar, the client is probably still using stale config. The status payload compares the add-on source hash running in Blender, the MCP server source hash, and the hash embedded in copied MCP config so stale installs are visible from the client.

After updating, use this quick checklist:

1. Restart Blender or disable/enable the add-on.
2. Press `Start`.
3. Press `Copy MCP Config`.
4. Replace the old MCP client config.
5. Refresh or restart the MCP client.
6. Call `blender_bridge_status` and confirm the add-on/MCP source hash is current.

## Bridge HTTP Endpoints

These are implementation details used by the MCP server:

- `GET /health`
- `GET /tools`
- `POST /tool`
- `GET /resources`
- `GET /resource?uri=...`
- `GET /contracts`

Example direct bridge call:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8765/tool -Method Post -ContentType application/json -Body '{"name":"list_scene_objects","arguments":{"max_objects":10}}'
```

## MCP Surface

The stdio MCP server implements:

- `initialize`
- `tools/list`
- `tools/call`
- `resources/list`
- `resources/read`
- `resources/templates/list`
- `prompts/list`
- `prompts/get`
- `logging/setLevel`
- `ping`

By default it exposes exactly five stable gateway tools:

- `blender_bridge_status`
- `blender_tool_catalog`
- `search_blender_tools`
- `get_blender_tool_schema`
- `invoke_blender_tool`

Use `blender_tool_catalog` as the primary entry point for the large helper catalog:

- `{"action":"search","query":"camera","limit":8}` returns compact summaries.
- `{"action":"categories"}` returns category, risk, and permission facets.
- `{"action":"schema","name":"add_camera"}` returns one tool's input schema, output schema, and safety annotations.
- `{"action":"invoke","name":"add_camera","arguments":{...}}` validates arguments against the target tool schema before forwarding the call to Blender.

The separate `search_blender_tools`, `get_blender_tool_schema`, and `invoke_blender_tool` tools are first-class gateway operations for clients that route more reliably through one operation per step. Search results are compact by default; set `include_schemas=true` only for compatibility or debugging. For normal routing, search first, fetch exactly one schema, then invoke it. Planner output may name helpers that are not present as top-level tools; that is an instruction to use the gateway, not evidence that the helper is unavailable.

Set `BLENDER_MCP_TOOL_SURFACE` in the MCP server environment only when a non-default surface is required:

- `gateway` is the default five-tool surface and is recommended for Claude, Codex, Cursor, and other retrieval-based clients.
- `direct` exposes the gateways plus the former 23 curated direct helpers for compatibility evaluation.
- `full` exposes the gateways plus every canonical helper for debugging and legacy clients.

The legacy `BLENDER_MCP_FULL_TOOL_LIST=1` flag remains supported and maps to `full` when `BLENDER_MCP_TOOL_SURFACE` is unset. An explicit `BLENDER_MCP_TOOL_SURFACE` value wins. Do not use `direct` or `full` merely to make a planner-named helper visible; search and invoke it through the gateway instead.

`tools/list`, `resources/list`, `resources/templates/list`, and `prompts/list` support cursor pagination. Gateway discovery carries only the five entry-point schemas and essential risk/routing annotations. `get_blender_tool_schema` returns any selected helper's complete canonical input/output schemas and safety annotations; those contracts remain in force regardless of top-level exposure.

JSON returned as MCP tool text, bridge HTTP responses, and JSON resources uses compact serialization. This removes formatting whitespace only: clients receive identical names, values, arrays, objects, schemas, warnings, and resource metadata after parsing.

### Large Inspection Response Controls

Large read-only scene, material, node, rig, simulation, and animation inspectors keep their complete existing response as the default. Their schemas also expose optional controls:

- `detail: "full" | "summary"`; `full` remains the default.
- `fields: ["objects.name", "scene.frame_current"]` for dotted field projection.
- `page`, `page_size`, and optional `page_field` for one top-level collection such as `objects`, `materials`, or `actions`.
- `known_digest` to avoid resending an unchanged result.

Every complete result includes `response_digest`. A matching `known_digest` returns only `ok`, `not_modified`, `response_digest`, and the tool name. A missing or mismatched digest returns the complete current result, even if summary, field, or pagination arguments were also supplied. This fail-open-to-full rule prevents stale client state or a bad digest from hiding current scene data.

Example:

```json
{"name":"get_animation_details","arguments":{"detail":"summary","page_field":"actions","page":1,"page_size":10}}
```

```json
{"name":"get_animation_details","arguments":{"known_digest":"<response_digest from the previous complete result>"}}
```

`get_blender_tool_schema` follows the same unchanged-response pattern with `schema_digest`. Its mismatch path always returns the complete schema and safety annotations.

### Payload Size Telemetry

`blender://mcp/payload-telemetry` reports process-local aggregate response sizes by tool. It contains only tool identifiers, call counts, and response byte counts. It never records arguments, object/material names, paths, schemas, or scene content. Restarting the MCP process clears it.

### Prompt Caching

The bridge cannot enable a provider cache from MCP. It makes the cacheable prefix stable instead: initialization instructions, tool order, tool definitions, and compact serialization are deterministic and contain no timestamps or scene state.

- Claude Code manages prompt caching automatically. Keep the MCP server connected and its tool set unchanged during a session; use Claude's cache usage fields or status-line/telemetry support to verify cache reads.
- OpenAI API prompt caching is automatic for eligible stable prefixes. Custom Responses API clients should use a stable `prompt_cache_key` for equivalent Blender sessions and verify cached-token usage in the API response.
- Cursor owns its provider request and cache policy. There is no Blender MCP setting that can force or prove provider caching; verify it through Cursor/provider usage reporting when available.

Do not reconnect the server or change the advertised tool set merely to save context. Those changes can invalidate a provider prefix cache and can also reduce agent understanding. Large schemas remain available on demand through `get_blender_tool_schema`.

Catalog summaries, schema lookups, and tool-call results may include `guardrail_warnings`. These are advisory, machine-readable nudges for MCP clients; they do not replace Blender-side enforcement. Current warning categories cover synchronous external asset fallbacks, cache cleanup writes, destructive project-file operations, user-confirmed paths, session-trusted scripts, live-preview mutations, long-running synchronous calls, helper-first advanced 2D/3D/simulation/camera routing, and background job polling.

`draft_script` is available for custom and larger advanced Blender Python, with a 500k-character payload ceiling. With trust off it refuses without retaining script state. With trust on it runs immediately with the same filesystem, network, subprocess, project-file, persistent-cache, and Blender API permissions as Blender's **Run Script** command. Helper and static-analysis findings may be returned as advice, but they do not become hidden authorization filters after trust.

`draft_privileged_script` is a compatibility alias to the same binary trust path. Bounded external-asset, project-file, render, capture, save, and cache tools remain preferable when their validation, provenance, recovery, or progress reporting helps. `list_project_files`, `read_project_file`, and `write_project_file` expose the current saved `.blend` directory only; they reject unsaved projects, traversal, absolute/hidden paths, and links, and cap generic reads/writes at 4 MiB. Generic writes also reject executable/script/library and `.blend` targets. Those limits apply to the structured tools, not to trusted Python.

For broad advanced work, search for and invoke `plan_advanced_scene_workflow` or `get_2d_animation_details` through the gateway. Use the planner before custom scripts when a request mixes advanced 3D, 2D/storyboard, animation, simulation, compositor/render, or unclear helper coverage. For open-ended authored content, inspect the scene and compose reusable modeling, text, curve, material, staging, camera, animation, asset-import, and visual-evidence helpers. The bridge deliberately does not include finished-content generators for props, vehicles, products, characters, storyboards, cutouts, or designed shots. Use one custom script under active binary session trust when reusable helpers cannot express the brief.

For procedural modeling, prefer `apply_procedural_array_stack`, `edit_mesh`, `inspect_modeling_quality`, `curve_to_mesh`, `boolean_op`, `mirror_model`, `symmetrize_model`, `solidify_model`, `screw_model`, and Geometry Nodes inspection before custom mesh or node scripts. `edit_mesh` is intentionally bounded to one topology/shape operation on single-user mesh data with live-preview snapshots. `inspect_modeling_quality` is read-only and should precede scripted repair. For cloth setup, use `add_cloth_simulation_to_selected`, then inspect simulation state before any persistent bake.

Simulation tools remain canonical gateway targets. Search for the required inspection, setup, or bake helper, fetch its schema, and invoke it. `stage_persistent_simulation_bake` first inspects the requested scope, refuses while trust is off, and runs its fixed scene-wide bake template immediately while session trust is active. Baking can block Blender; if the bridge times out, wait before checking bridge status and diagnostics rather than rerunning the bake.

Project file tools are human-in-the-loop. For `save_blend_file` save-as/save-copy, `open_blend_file`, and `create_new_blender_project`, clients must ask the user for the target path or use a file picker and set `user_confirmed_path=true`; agents must not invent durable paths. Saving the already-bound active `.blend` may omit `filepath`. `autosave_current_blend_file` accepts no filepath and saves only the already-bound active `.blend` in place.

Project-directory file tools do not accept an absolute path. Their root is derived from the active saved `.blend`, so the user establishes the boundary when choosing the project save location. `write_project_file` creates ordinary parent folders when requested but does not delete or move files; overwriting is opt-in. Use the dedicated asset-download, render, capture, export, or `.blend` save tools for larger or format-specific outputs.

Recovery paths have the same standard: do not tell the user to open a checkpoint, autosave, or backup `.blend` path unless the client has just verified that exact path exists and is restorable through returned checkpoint metadata, diagnostics, or a filesystem check. If verification is unavailable, report that the path is unverified and ask the user to choose the file instead of inventing one.

`blender_bridge_status` also reports the current external script trust snapshot, including whether tokenless external script runs are allowed, seconds remaining, the runtime expiry timestamp, whether saved scene trust state is stale, and source-hash match/mismatch diagnostics. Some MCP clients cache callable tools aggressively; if a newly added Blender tool is missing, restart or refresh the MCP client after copying the latest config.

For advanced animation, search the gateway for the animation workflow before invoking individual helpers. Use `run_animation_task` when a client has one prompt and should take the default helper-first path. Use `plan_animation_workflow` for read-only manual planning before repair, generation, or arbitrary Python; it creates the animation brief, animation-aware scene context, timing chart, ordered helper/evaluator/repair tool-call payloads, and explicit `draft_script` fallback rules. For common helper-backed requests, `run_animation_workflow` executes the plan through allowlisted helpers, runs structured evaluator review, optionally captures playblast evidence, optionally applies bounded repair operations, and leaves helper edits as a normal live preview. Bounce requests that also ask the subject to get smaller route through `create_progressive_bounce_animation` instead of script fallback. The MCP catalog boosts animation workflow tools for prompts with bounce, jump, keyframe, pose, timing, arcs, settle, squash/stretch, playblast, f-curve, spacing, or contact terms, while `draft_script` is kept as an explicit script/Python fallback. `get_animation_scene_context` remains the lower-level routing tool for likely edit targets, rig-driven meshes, rig control candidates, shape keys, drivers, constraints, physics hints, contact surfaces, camera readiness, subject routing, recommended deeper inspection tools, and an `animation_hardening` block listing risk flags, required pre-mutation inspections, review tools, and repair-loop limits.

### Animation Routing Regression Prompts

Use these prompts after installing a fresh zip and refreshing the MCP client. During routing tests, revoke script trust to verify that `draft_script` is refused without pending state, then enable trust to verify immediate Blender Run Script-equivalent execution. Custom asset/project-file work should still prefer bounded structured tools when they fit, and persistent bakes should inspect before running.

| Prompt | Expected tool path | Pass condition |
| --- | --- | --- |
| `make selected cube bounce twice and get smaller each bounce` | `run_animation_task` -> `run_animation_workflow` -> `create_progressive_bounce_animation` -> review tools | The client uses `run_animation_task` or `run_animation_workflow` before any `draft_script`. |
| `block a jump with anticipation, contact, apex, settle` | `plan_animation_workflow` or `run_animation_task` -> `create_timing_chart` / blocking helpers -> evaluators | The client plans or runs the animation workflow and does not start with Python. |
| `review this animation for spacing/contact` | `run_animation_task` or `plan_animation_workflow` -> evaluator tools -> `review_playblast_against_brief` / `repair_animation_from_findings` when evidence exists | The client uses workflow/evaluator/review helpers before considering script repair, even when the prompt is too ambiguous for generation. |
| `create a 2D storyboard animatic with panels and a camera move` | `plan_advanced_scene_workflow` -> `get_2d_animation_details` -> reusable text/curve/camera helpers or `draft_script` | The planner and reusable operations are considered before one trusted script for authored panel content. |
| `make an advanced procedural hard-surface array stack` | `plan_advanced_scene_workflow` -> `get_geometry_nodes_details` -> `apply_procedural_array_stack` | The client uses helper-backed non-destructive modifier setup before custom geometry scripts. |
| `use a boolean cutter, mirror the model, symmetrize it, solidify wall thickness, and add a screw thread` | `plan_advanced_scene_workflow` -> `boolean_op` / `mirror_model` / `symmetrize_model` / `solidify_model` / `screw_model` | The client uses Phase 1 non-destructive modeling helpers before custom mesh-edit Python. |
| `extrude mesh faces, inset panels, loop cut, knife cut, proportional edit, bridge boundary loops, merge by distance, and convert curve to mesh` | `plan_advanced_scene_workflow` -> `edit_mesh` / `curve_to_mesh` | The client uses bounded Phase 1 mesh-data helpers before custom mesh-edit Python. |
| `inspect mesh quality for non-manifold edges, loose geometry, missing materials, and model readiness` | `plan_advanced_scene_workflow` -> `inspect_modeling_quality` -> `capture_object_inspection_renders` when visual evidence matters | The client uses read-only diagnostics and evidence capture before drafting repair scripts. |
| `mark hard-edge UV seams, pack UV islands, inspect for overlaps, apply a packed ARM PBR material, and render a small lookdev still` | `mark_uv_seams` -> `uv_unwrap(pack_islands=true)` -> `inspect_uv_layout` -> `create_image_texture_material(arm_path=..., uv_map_name=...)` -> `create_lookdev_turntable_review` | The client uses bounded Phase 2 UV/look-dev helpers, inspection stills, and artifact validation before custom shader/render Python. |
| `inspect and repair a PBR material setup for missing texture files, wrong color spaces, shader links, and UV map vector inputs` | `inspect_material_setup` -> `repair_material_setup` -> `inspect_material_setup` | The client validates and fixes bounded material wiring problems before custom shader-node Python. |
| `bake AO, normal, and diffuse maps for a game-ready textured asset` | `uv_unwrap` / `inspect_material_setup` -> `bake_maps(map_types=[ao,normal,diffuse])` | The client uses the bounded Phase 2 map baker before custom `bpy.ops.object.bake` scripts. |
| `enable normal, depth, ambient occlusion, cryptomatte render passes and add a custom shader AOV` | `configure_render_outputs(enabled_passes=..., aovs=...)` | The client configures ViewLayer render outputs through a preview-safe helper before custom compositor/render Python. |
| `create a procedural marble texture material with noise bump for the selected mesh` | `create_procedural_texture_material(preset=marble_noise, bump_strength=...)` | The client uses bounded procedural texture nodes before custom shader-node Python. |
| `design a futuristic wall-mounted coffee machine with chrome pipes and a small display` | `plan_advanced_scene_workflow` -> reusable modeling/material helpers, asset import, or `draft_script` -> `inspect_modeling_quality` | No product-specific generator is exposed; the client chooses composable operations or one trusted script. |
| `create a believable architect desk lamp with spring arms and capture inspection renders` | `plan_advanced_scene_workflow` -> reusable modeling/material helpers, asset import, or `draft_script` -> `capture_object_inspection_renders` | No prop grammar is exposed; the result still receives modeling and visual-evidence checks. |
| `create an advanced camera push and orbit reveal` | `plan_advanced_scene_workflow` or `plan_animation_workflow` -> `create_camera_dolly_animation` / `create_camera_orbit` -> visual review | The client composes reusable camera operations and requests explicit coordinates when needed. |
| `add cloth simulation setup and inspect it before baking` | `plan_advanced_scene_workflow` or `get_simulation_details` -> `add_cloth_simulation_to_selected` -> `inspect_simulation_bake` -> `stage_persistent_simulation_bake` | The client inspects first; a persistent bake runs only while binary session trust is active and may block Blender. |

If a client still calls `draft_script` first for these prompts, refresh or restart the MCP client, press `Copy MCP Config` again, confirm `tools/list` contains the five gateway tools, search for `run_animation_task`, and check `blender_bridge_status` for matching add-on, bridge, MCP server, config versions, and `mcp_tool_surface: gateway`.

## Resources

Current resources:

- `blender://bridge/status`
- `blender://mcp/payload-telemetry`
- `blender://scene/status`
- `blender://scene/context`
- `blender://tools/catalog`
- `blender://transcript/latest`
- `blender://audit/summary`
- `blender://captures/latest`
- `blender://captures/latest/metadata`
- `blender://captures/{capture_id}`
- `blender://captures/{capture_id}/metadata`
- `blender://playblasts/latest/metadata`
- `blender://playblasts/{playblast_id}/metadata`
- `blender://playblasts/{playblast_id}/frames/{frame}`
- `blender://inspection-renders/latest/metadata`
- `blender://inspection-renders/{render_id}/metadata`
- `blender://inspection-renders/{render_id}/images/{image_id}`
- `blender://render-thumbnails/latest`
- `blender://render-thumbnails/latest/metadata`
- `blender://render-thumbnails/{thumbnail_id}`
- `blender://render-thumbnails/{thumbnail_id}/metadata`
- `blender://render-jobs/latest/metadata`
- `blender://render-jobs/{job_id}/metadata`
- `blender://render-jobs/{job_id}/frames/{frame}`
- `blender://render-jobs/{job_id}/log`
- `blender://render-jobs/{job_id}/video`

`blender://captures/latest` is scoped to the currently connected Blender bridge and its active project/session. Capture metadata includes the exact `capture_id` resource URIs for repeat reads. By default, saved `.blend` files store captures in a hidden project-local `.claude_blender/captures/<session_id>` folder so separate projects do not overwrite each other. Unsaved or unwritable projects fall back to Blender's extension user-data directory, with `~/.claude_blender/captures/<project_id>/<session_id>` kept only as a non-extension runtime fallback. A custom capture cache preference remains a custom base directory and still gets project/session subfolders.

`blender://tools/catalog` is the resource-friendly compact catalog for eager MCP clients. It contains tool names plus risk and permission metadata, not full schemas. The full contract registry remains readable at `blender://tools/contracts` for debugging, but it is intentionally not listed as a default resource because it is large. `blender://audit/summary` is likewise the compact default audit resource; `blender://audit/latest` remains readable for explicit debugging and returns a bounded recent event window.

`capture_animation_playblast` captures sampled viewport PNG frames across an animation range when Blender is running with an interactive window. It defaults to low-resolution preview evidence capped at 640x360; pass `quality`, `max_width`, or `max_height` only when higher fidelity is needed. It advances the scene frame, updates the view layer, and flushes the viewport draw path where possible before each screenshot; frame metadata includes `captured_scene_frame` as a sanity check against stale captures. The metadata resource lists exact frame URIs so external clients can inspect timing, spacing, staging, arcs, and contact poses without relying only on keyframe data. `review_playblast_against_brief` also derives compact pixel digests, visual-subject interpretation, and frame-to-frame motion deltas from available PNGs, then emits `repair_operations` with executable `tool_call` payloads for deliberate follow-up repairs. Those operations include `target_frames` and `target_frame_range` when a visual finding points to specific sampled frames, missing coverage, weak/cropped subject evidence, or a static-looking frame span. `run_animation_workflow` uses that review path after generation, and `run_animation_repair_loop` can apply a bounded allowlisted subset of repair operations, skip under-specified repairs, and re-run review while preserving the preview commit/revert model. Rig repair findings can route through `get_rigging_details`, `set_rig_custom_property_keyframes`, and then `set_rig_pose_hold` so a client inspects armature controls, holds scalar IK/FK or space-switch properties, and keys a pose-bone hold. For IK/FK-style rigs, repair operations include `metadata.rig_targeting` with the selected controls, roles, regions, score reasons, detected IK/FK or space-switch custom properties, pose-library/action candidates, and planning notes; support/contact rig findings avoid generic object `set_pose_hold` suggestions when rig controls are the better owner. In background/headless mode capture fails soft and reports that an interactive window is required.

`capture_object_inspection_renders` renders bounded diagnostic close-ups of named objects from views such as `front_below`, `underside`, and `side`. It is meant for evidence gathering when the client needs to inspect object details before repair, for example open bays, landing gear, underside geometry, occluded parts, or small model defects. The tool writes PNG artifacts into the project/session capture cache, restores render settings and removes its temporary camera, then returns metadata and image resource URIs under `blender://inspection-renders/{render_id}/...`. `review_inspection_renders_against_brief` can then turn those PNG manifests into visual-detail findings, visual-subject interpretation, and recapture repair operations when required views or readable image evidence are missing.

`render_scene_thumbnail` renders a small PNG from the active scene camera or a named camera, stores metadata in the same project/session capture cache, restores render settings, and exposes the still through `blender://render-thumbnails/{thumbnail_id}` plus metadata resources. Use it when an MCP client needs a client-readable render output or thumbnail without falling back to custom Python.

`start_render_job` is the long-render path for high-resolution animation renders, frame sequences, MP4 quality checks, 1080p/4K previews, and anything likely to exceed the MCP request timeout. It saves a temporary copy of the current `.blend`, starts a background Blender process, and returns a `job_id`, rough estimate, and polling interval immediately. With `quality=auto`, final renders keep final-quality defaults, while playblast/preview/review/draft job names or notes default to a low-resolution preview profile unless the caller explicitly passes `quality`, `resolution_x`, `resolution_y`, or `samples`. Poll `get_render_job_status` until the job reaches `completed`, `failed`, or `cancelled`; status updates include elapsed time, frame rate when frames are available, estimated remaining time, `poll_after_seconds`, frame counts, progress, output paths, log tails, and newest frame resource URI. Logs are available at `blender://render-jobs/{job_id}/log`; exact frames are available at `blender://render-jobs/{job_id}/frames/{frame}`. After a PNG sequence completes, call `assemble_render_job_video` to start a background MP4 assembly pass, then poll `get_render_job_status` again and call `validate_render_job_output` before reporting success. MP4 output is exposed through `blender://render-jobs/{job_id}/video` when small enough for MCP, and always reports a local path in metadata. Use `cancel_render_job` when a tracked job should stop. `render_scene_thumbnail` refuses large synchronous stills by default and returns `recommended_tool: start_render_job`; pass `allow_blocking_render=true` only for an intentional one-off blocking still. `draft_script` warns clients to use this path first when a generated script appears to be a long render or playblast job.

Persistent simulation/cache bakes are separate from render jobs. Inspect with `get_simulation_details` or `inspect_simulation_bake`, then call `stage_persistent_simulation_bake` only when the user intentionally wants the scene-wide operation. Trust off refuses it; active binary session trust runs the fixed bake template immediately with Blender Run Script-equivalent permissions. Baking can keep Blender busy after an MCP timeout, so inspect status and evidence before considering a retry.

Official Blender Lab parity helpers are available as canonical gateway targets:

- `get_blend_file_diagnostics` reports save path state, backup files, verified script checkpoint metadata, missing external file paths, linked libraries, and data-block usage summaries.
- `get_workspace_layout` returns workspace/window/screen/area JSON for UI diagnostics.
- `jump_to_workspace` switches the interactive Blender UI to a named workspace and fails soft in background mode.
- `set_viewport_view` switches the first interactive 3D viewport to an axis, camera, or user view and can frame a named object.
- `focus_object_in_viewport` frames a named object in the first 3D viewport and optionally selects it; it also fails soft when no interactive 3D view exists.
- `get_visual_evidence_resources` summarizes latest viewport captures, playblasts, inspection renders, render thumbnails, and render jobs with MCP resource URIs.

External asset helpers are provider-neutral bridge tools. They do not add provider API keys to Blender preferences. Sketchfab download/import takes a per-call `api_token` or reads `SKETCHFAB_API_TOKEN` / `BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN` from the MCP server environment. Pass the `provenance` object returned by `search_sketchfab_models` into the download/import call so the exact author, license, and model URL are preserved. Repeated model imports are blocked unless `allow_duplicate=true`; `revert_preview` with `scope=last_step` removes only the latest isolated model import.

For real MCP clients, the normal route is discovery, `start_external_asset_download`, `get_external_asset_job_status` until completion, `start_external_asset_import_job` for scene import, then `get_external_asset_import_job_status` until completion. Poly Haven texture imports use the same bounded image/PBR material wiring as `create_image_texture_material`, so cached base-color, roughness, metallic, normal, alpha, emission, ambient-occlusion, packed ARM/ORM, and bump maps become preview-safe Principled materials instead of custom node scripts. `bake_maps` covers bounded AO, normal, and base-color/diffuse PNG output from existing mesh materials; omit `output_dir` for project/session capture storage, and only pass a custom `output_dir` when it came from the user, a file picker, or a prior artifact. Displacement/height maps are still validated and reported as warnings until true displacement/high-to-low baking support lands. Direct provider download/import tools remain available as synchronous fallback/debug paths, but clients should not choose them for ordinary asset-import requests.

- `list_poly_haven_categories` lists Poly Haven category slugs for HDRIs, textures, and models.
- `search_poly_haven_assets` searches Poly Haven's CC0 catalog and returns source/file API URLs.
- `inspect_poly_haven_asset_files` fetches Poly Haven's per-asset file tree with resolutions, formats, sizes, hashes, and dependency includes.
- `search_sketchfab_models` searches Sketchfab public models and returns viewer, author, license, thumbnail, and downloadability metadata.
- `start_external_asset_download` starts a background Poly Haven or Sketchfab cache job and returns a pollable job id.
- `get_external_asset_job_status` reports download progress, cached manifest paths, logs, and completion state.
- `start_external_asset_import_job` queues a completed asset job or cached manifest for Blender main-thread import, then `get_external_asset_import_job_status` reports queued/running/completed state.
- `cancel_external_asset_job`, `cancel_external_asset_import_job`, and `delete_external_asset_job` handle cancellation and job cleanup.
- `get_external_asset_cache_diagnostics` reports cached/imported providers, licenses, source URLs, file counts, cache paths, and imported Blender data-block names.
- `prune_external_asset_cache` removes old or oversized cached assets, with dry-run mode by default.
- `download_poly_haven_asset`, `import_poly_haven_asset`, `download_sketchfab_model`, `import_sketchfab_model`, and `import_external_asset_job_result` are synchronous fallback/debug paths for explicit direct use.

## Prompts

The MCP server exposes prompt templates for common safe workflows: scene inspection, reversible scene changes, broad advanced scene workflow planning, advanced animation workflow planning, async external asset import, and session-trusted Python execution.

## Safety

MCP tools are model-controlled, so the external client must make tool use visible to the user. The Blender bridge preserves the existing safety model:

- Read-only tools inspect scene context and docs.
- Live helper tools mutate the scene through preview rollback.
- Generated Python uses one binary, runtime-only switch. Trust off refuses `draft_script` without retaining script state; trust on immediately runs with Blender Run Script-equivalent process permissions.
- `draft_privileged_script` is a compatibility alias to the trusted execution path. `run_approved_script` refuses the removed per-script token flow. There are no approval tokens or pending-script actions.
- Trust can be enabled before or after starting the bridge. It is cleared by **Revoke**, add-on reload, file load, or Blender exit. Static findings remain advisory after trust.
- The bridge is off until started and binds to localhost only.
- Optional bearer token auth is available through add-on preferences.
- MCP and bridge tool calls are recorded in a local JSONL audit log in Blender's extension user-data directory by default, with `~/.claude_blender/audit.jsonl` kept as a non-extension runtime fallback. Code/token-like arguments are redacted; audit status is exposed through bridge/tool diagnostics instead of a sidebar section.

## Limitations

- The first MCP server uses stdio only, because it is the most widely supported local MCP transport.
- The localhost bridge is HTTP JSON, not MCP streamable HTTP. MCP clients should launch `mcp_server.py`.
- The default MCP surface is exactly five gateways because some clients retrieve only a handful of tools. Opt-in `direct` and `full` surfaces remain available through `BLENDER_MCP_TOOL_SURFACE`.
- External clients cannot turn on Blender-side session trust. Only the user can enable it from Blender's sidebar.
