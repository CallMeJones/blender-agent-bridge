# Blender Agent Bridge

The safe, production-shaped bridge between Blender and external AI agents.

Blender Agent Bridge is a Blender extension plus a localhost MCP bridge. It lets tools such as Codex, Claude Desktop, Claude Code, Cursor, and other MCP-capable clients inspect the open Blender scene, gather visual evidence, make preview-capable edits, and run Python under explicit session trust.

<p align="center">
  <img src="docs/assets/egypt-dogfight-hero.jpg" alt="Two aircraft in a generated Blender dogfight scene with smoke and motion blur" />
</p>

<p align="center">
  <a href="addon/claude_blender/blender_manifest.toml"><img alt="Blender 4.2+" src="https://img.shields.io/badge/Blender-4.2%2B-F5792A"></a>
  <a href="https://github.com/CallMeJones/blender-agent-bridge/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/CallMeJones/blender-agent-bridge"></a>
  <a href="https://github.com/CallMeJones/blender-agent-bridge/actions/workflows/mcp-smoke.yml"><img alt="Build, smoke, release" src="https://github.com/CallMeJones/blender-agent-bridge/actions/workflows/mcp-smoke.yml/badge.svg"></a>
  <img alt="MCP bridge" src="https://img.shields.io/badge/MCP-localhost%20bridge-3B82F6">
  <img alt="LLM host" src="https://img.shields.io/badge/LLM%20provider-external-10B981">
  <a href="LICENSE"><img alt="License GPL-3.0-or-later" src="https://img.shields.io/badge/License-GPL--3.0--or--later-111827"></a>
</p>

<p align="center">
  <a href="https://polyhaven.com/"><img alt="Poly Haven assets" src="https://img.shields.io/badge/Assets-Poly%20Haven-2E7D32"></a>
  <a href="https://sketchfab.com/"><img alt="Sketchfab assets" src="https://img.shields.io/badge/Assets-Sketchfab-1CAAD9"></a>
  <a href="https://platform.tripo3d.ai/"><img alt="Tripo3D generation" src="https://img.shields.io/badge/Image--to--3D-Tripo-2563EB"></a>
  <a href="https://www.meshy.ai/"><img alt="Meshy generation" src="https://img.shields.io/badge/Image--to--3D-Meshy-7C3AED"></a>
  <a href="https://github.com/VAST-AI-Research/TripoSR"><img alt="Local TripoSR generation" src="https://img.shields.io/badge/Local%20Image--to--3D-TripoSR-374151"></a>
  <a href="#configure-a-self-hosted-studio-endpoint"><img alt="Self-hosted studio generation" src="https://img.shields.io/badge/Self--hosted-Studio%20endpoint-455A64"></a>
</p>

## 1. Install the Blender Extension

Install Blender `4.2.0` or newer. CI continuously checks Blender 4.2 LTS, 4.5 LTS, and 5.1; newer versions are allowed and use capability checks instead of an artificial maximum-version gate.

### Recommended: install from the extension repository

1. In Blender, open `Edit > Preferences > Get Extensions`.
2. Enable online access if Blender asks.
3. Press `Repositories`.
4. In the repository popover, press `+`, choose `Add Remote Repository`, and name it `Blender Agent Bridge`.
5. Paste this repository URL:

   ```text
   https://callmejones.github.io/blender-agent-bridge/index.json
   ```

6. Close the repository popover, open the down-arrow extension settings menu, and choose `Refresh Remote`.
7. Search for `Blender Agent Bridge`.
8. Press `Install`, then confirm the extension is enabled.
9. Close Preferences. In the 3D View, press `N` to open the sidebar and select the `Agent Bridge` tab.
10. Press `Start`. The panel should report that the bridge is on.

Updates use the same repository: sync it in `Get Extensions`, install the offered update, restart Blender, and copy a fresh MCP config.

### Manual fallback: install the release ZIP

1. Open the [latest GitHub release](https://github.com/CallMeJones/blender-agent-bridge/releases/latest).
2. Under **Assets**, download `claude_blender-<version>.zip`.
3. Do **not** download GitHub's generated `Source code` ZIP; it is not an installable Blender extension.
4. In Blender, open `Edit > Preferences > Get Extensions`.
5. Open the extension menu, choose `Install from Disk`, and select the downloaded `claude_blender-<version>.zip`.
6. Enable `Blender Agent Bridge`, close Preferences, open the 3D View sidebar with `N`, select `Agent Bridge`, and press `Start`.

The extension ZIP already includes the MCP server, so the recommended bundled mode needs no Python package, `pip`, `uv`, or `uvx` installation. See [Install from GitHub](docs/INSTALL_FROM_GITHUB.md) for checksum verification, command-line installation, updates, and troubleshooting.

### Current release evidence

The current public release passed the [tagged release gate](https://github.com/CallMeJones/blender-agent-bridge/actions/workflows/mcp-smoke.yml): conventional unit tests, the complete Blender smoke suite, and clean installed-extension live smoke on Blender 4.2.0, 4.5.0, and 5.1.2. The gate promotes and verifies one tested extension ZIP, MCPB, wheel, source distribution, GitHub Release, PyPI release, and Pages repository set. A fresh isolated Blender 5.1 profile also installed and enabled the exact version advertised by the public extension repository.

## 2. Connect Claude, Codex, or Cursor

The MCP server is already bundled with the Blender extension. After pressing `Start`, press `Copy MCP Config`. Blender copies a complete `mcpServers.blender` JSON entry containing the correct local Python path, bridge URL, session token, version metadata, and tool-registry digest. Keep every generated `command`, `args`, and `env` value together; this generated entry is the source of truth for Codex, Cursor, Claude Code, and manual Claude Desktop setup.

| Client | Exact setup |
| --- | --- |
| **Claude Desktop** | Recommended: open the `blender-agent-bridge-<version>.mcpb` asset from the matching GitHub release and enter the bridge URL/token shown in Blender. Manual fallback: merge the complete copied `mcpServers` object into Claude Desktop's config, then fully restart it. |
| **Claude Code** | Take only the object inside `mcpServers.blender`, then run `claude mcp add-json --scope user blender '<server-object-json>'`. Run `claude mcp list`, restart Claude Code, and use `/mcp` to confirm it connected. |
| **Codex app, CLI, or IDE extension** | Do not install the MCPB. Open **Settings > MCP servers > Add server**, choose local **STDIO**, and copy the generated `command`, every `args` item, and every `env` value. Alternatively, convert the same entry to `[mcp_servers.blender]` in `~/.codex/config.toml`. Save it, select **Restart**, then use `/mcp` or `codex mcp list`. |
| **Cursor** | Do not install the MCPB. Merge the complete generated JSON into `~/.cursor/mcp.json` for all projects or `.cursor/mcp.json` for one project. Preserve other servers, refresh Cursor's MCP servers or restart Cursor, then check **Settings > MCP**. |

The MCPB installs only the Claude Desktop connector; it is not the installation format for Codex or Cursor. Install and start the Blender extension separately. The MCPB packages the same dependency-free Python MCP server code and five-tool gateway as the release. Its MCPB v0.4 `uv` runtime is managed by the host, so users do not need to install or configure Python. The sensitive token setting stays in the client configuration.

If you want a local coding agent to configure itself, copy the config in Blender and give that agent the matching one-line prompt:

**Claude Code**

```text
Install the Blender MCP config currently on my clipboard at user scope as server blender; preserve every command, argument, environment value, and existing MCP server, never print token values, then verify it with claude mcp list.
```

**Codex**

```text
Install the Blender MCP config currently on my clipboard as a user MCP server named blender; convert the JSON to Codex TOML without changing command, args, or env, preserve my existing config, never print token values, then verify it is listed and tell me to restart MCP.
```

**Cursor**

```text
Merge the Blender MCP config currently on my clipboard into my global ~/.cursor/mcp.json as server blender without deleting existing servers, never print token values, then verify Cursor can see it and tell me to refresh MCP.
```

If the agent cannot read the clipboard, use the manual route above. The generated config contains a localhost bridge token: keep it in local configuration, never paste it into an issue or public chat, and press `Copy MCP Config` again after changing the extension or bridge settings. Keep only one `blender` entry in each client, and connect only one active MCP server to a Blender bridge at a time. Full walkthroughs: [Claude](docs/clients/CLAUDE.md), [Codex](docs/clients/CODEX.md), and [Cursor](docs/clients/CURSOR.md).

## 3. Test the Connection

Keep Blender open with the bridge running, refresh or restart the MCP client, then ask:

```text
Check Blender bridge status, find and invoke the scene-object inspection tool, and make no changes.
```

The default tool list must contain exactly `blender_bridge_status`, `blender_tool_catalog`, `search_blender_tools`, `get_blender_tool_schema`, and `invoke_blender_tool`. Helpers such as `list_scene_objects` are intentionally not top-level tools: the client must find them through search, fetch their schema, and call them through the gateway. A planner naming a non-advertised helper does not mean that helper is unavailable.

For a deterministic command-line check, run `blender-bridge doctor`. It verifies the MCP executable, optional client config, bridge socket, add-on/runtime compatibility, five-tool manifest, schema lookup, and a real read-only gateway invocation. See [Connection Diagnostics](docs/CONNECTION_DIAGNOSTICS.md).

Then try a reversible edit:

```text
Move the selected cube up 1 Blender unit and make it red. Leave the change as a preview.
```

Helper preview edits stay pending in Blender until you use `Commit`, `Revert`, or Blender undo. Generated Python is refused while **Trust Agent Scripts** is off. With trust on, it runs immediately with the same filesystem, network, subprocess, project-file, persistent-cache, and Blender API permissions as Blender's **Run Script** command. Trusted-script changes use checkpoints and Blender undo; they do not create a pending live preview, and `Commit`/`Revert` do not apply to them.

The public beta is live: read the [release announcement](https://github.com/CallMeJones/blender-agent-bridge/discussions/12) and share structured [beta feedback](https://github.com/CallMeJones/blender-agent-bridge/discussions/13).

## After Updates

Restart Blender, press `Start`, copy the MCP config again, replace the old client config, and refresh or restart the client. This prevents cached server paths and tool lists from keeping an older extension active.

## Why This Exists

AI agents are getting good at using tools, but Blender needs guardrails. This bridge gives agents real scene context and practical tools without turning Blender into a chat app or writing provider API keys into `.blend` files or Blender preferences.

- Blender stays the execution layer: scene state, viewport evidence, preview changes, binary script trust, checkpoints, and local resources.
- The external client stays the agent host: model connection, conversation memory, provider account, planning, and user chat.
- With runtime script trust active, authored object generation, modeling, animation, materials, custom nodes, rigging, and look development default to one cohesive generated Python script unless the user requests helpers or no Python. Trust-off sessions use bounded helpers instead; generated scripts are refused until trust is granted.
- Long cohesive scripts can run in an isolated background Blender process against a copied `.blend`, with polling, cancellation, and an explicitly confirmed apply step that checkpoints the live file.
- Replayable execution traces record compact gateway activity, local generated-script artifacts, timings, outcomes, and reported token usage without expanding the five-tool MCP manifest.
- Reference-model workflows persist blind evidence scorecards and bounded repair passes until they reach `ready_for_user_review` or `blocked_quality_floor`.
- Multi-view clients can fuse calibrated silhouettes and optional signed depth into a watertight surface, automatically fit that surface against all views and reconstructed landmarks, adapt topology by region and curvature, and turn remaining critiques into form-aware semantic or screen-space repairs without an external image-to-3D model.
- Connected LLMs can author persistent semantic shape programs from general SDF primitives and tapered sweeps, compile them into continuous watertight meshes with uniform or adaptive-dual extraction, target high octree depth only around important local forms, probe their fields, and revise named forms without an external model or category-specific base mesh.
- Blender has one deliberately small sidebar panel: bridge status/start-stop, `Copy MCP Config`, **Trust Agent Scripts**/**Revoke**, and pending preview **Commit**/**Revert**. Diagnostics, manifests, audit state, captures, and asset configuration stay in bridge/tool responses instead of returning as sidebar sections.
- Bounded helpers handle inspection, project files, external assets, long jobs, persistent bakes, evidence, preview decisions, and deliberately isolated edits. Operational clauses remain separate from, and do not demote, the trusted script used for authored work.

## Assets and Image-to-3D Providers

Every provider is optional. Turning off **Allow Third-Party Uploads** disables hosted generation without disabling the bridge. Authored scripts, bounded modeling helpers, scene inspection, previews, rendering, project workflows, Poly Haven, local TripoSR, and a configured studio endpoint continue to work independently.

| Provider | What the bridge supports | Setup | Network, cost, and quality |
| --- | --- | --- | --- |
| [Poly Haven](https://polyhaven.com/) | Search and import HDRIs, PBR textures, and models with source metadata. | None. | Downloads from Poly Haven's open API; assets are CC0. |
| [Sketchfab](https://sketchfab.com/) | Public model search plus authenticated glTF downloads and imports with author, source, and license provenance. | Search needs no key. Downloads need your Sketchfab API token. | Asset licenses vary; attribution and the model's license follow the imported asset. |
| [Tripo](https://platform.tripo3d.ai/) (Tripo3D API) | Hosted single-image and calibrated multi-view image-to-3D jobs, polling, cached results, import, and provenance. | Tripo API key plus **Allow Third-Party Uploads**. | Uploads references and consumes Tripo API credits. Best hosted route when multiple views are available. |
| [Meshy](https://docs.meshy.ai/en/api) | Hosted single-image and multi-image image-to-3D jobs, balance checks, polling, cached GLB import, and provenance. | Meshy API key plus **Allow Third-Party Uploads**. | Uploads references and consumes Meshy account credits. Generated topology can be dense or fragmented and should be evaluated after import. |
| [TripoSR](https://github.com/VAST-AI-Research/TripoSR) | Direct local single-image reconstruction, persistent tuning defaults, Z-up import normalization, cleanup, and evaluation renders. | A separate Python environment with TripoSR and CUDA-capable PyTorch, plus the local checkout path. | No vendor key, upload, or API credits. Treat it as a fast blockout route: one image cannot reveal hidden side or back structure. |
| **Studio endpoint** | Self-hosted single-view or multi-view generation through a small bridge-compatible HTTP API, with polling, cached import, and provenance. | A service base URL and optional bearer token under **Set Up Providers**. The inference service itself is not bundled. | Counts as local/self-hosted, so no third-party-upload or vendor-spend approval is required. Plain HTTP is limited to localhost/private-network hosts; public hostnames require HTTPS. |

When more than one generation provider is ready, the bridge asks which provider to use and starts nothing until the user answers. It does not silently prefer local, hosted, cheap, or fast. Hosted Tripo and Meshy jobs also require an explicit spend approval in Blender before a request is sent. The agent can poll the exact approval request and detect Approve, Decline, or expiry without asking the user to report the click. Local TripoSR and the self-hosted studio endpoint do not create spend requests. A sole local provider may be selected automatically; a hosted provider never is.

The release has live evidence for Tripo single-view and multi-view generation, Meshy single-view generation plus provider cancellation/recovery, and TripoSR generation, texture baking, cancellation/recovery, import, and evaluation. Meshy's multi-image client is implemented but not yet live-proven. The studio endpoint is contract- and unit-tested but still needs a real service deployment for live evidence. Hunyuan3D and TRELLIS appear only as strategy-level readiness diagnostics today; they do not have direct launchers and must not be presented as runnable providers.

### Configure Poly Haven and Sketchfab

Poly Haven works immediately. For Sketchfab downloads:

1. In Blender's `Agent Bridge` sidebar, expand `Image-To-3D Generation` and press `Set Up Providers`.
2. Copy your token from [Sketchfab account settings](https://sketchfab.com/settings/password) into **Sketchfab API Token**.
3. Leave **Remember Keys On This Machine** enabled to use the operating system credential store where available, or turn it off to keep the token only until Blender closes. The panel identifies the storage mechanism it selected.

The token field blanks itself after accepting the value; the status line below it confirms whether the token is set. As an alternative for automated MCP environments, set `SKETCHFAB_API_TOKEN` or `BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN` in the MCP server process.

### Configure hosted Tripo and Meshy

1. Create a key in the [Tripo API portal](https://platform.tripo3d.ai/api-keys) and/or [Meshy API settings](https://www.meshy.ai/settings/api).
2. Open `Agent Bridge > Image-To-3D Generation > Set Up Providers`.
3. Enable **Allow Third-Party Uploads**.
4. Paste the key into **Tripo API Key** or **Meshy API Key**. The field clears after secure capture and the status line reports that the key is set.
5. Ask the agent to check generation provider diagnostics before starting the first job.

Keys entered here are held in session memory. With **Remember Keys On This Machine** enabled, they use the operating system credential facility where available; otherwise the panel reports a private user-only file fallback without describing it as encrypted. Keys are never written to `userpref.blend`, project `.blend` files, manifests, or audit logs. Tripo and Meshy use separate API billing from this extension, so review the provider's current credit pricing before approval.

### Configure local TripoSR

TripoSR runs outside Blender's bundled Python. The official project requires Python 3.8 or newer, a platform-compatible PyTorch installation, and approximately 6 GB of VRAM at its default settings. Create a dedicated environment rather than installing Torch into Blender:

```text
git clone https://github.com/VAST-AI-Research/TripoSR.git
python -m venv .venv-triposr

# Replace TRIPOSR_PYTHON below with:
# Windows: .venv-triposr\Scripts\python.exe
# macOS/Linux: .venv-triposr/bin/python
TRIPOSR_PYTHON -m pip install --upgrade pip setuptools
TRIPOSR_PYTHON -m pip install -r TripoSR/requirements.txt
```

Install the CUDA-compatible PyTorch build recommended by the [official PyTorch selector](https://pytorch.org/get-started/locally/) into that same environment. Then open `Set Up Providers` and set:

- **Generation Python** to the environment's Python executable.
- **TripoSR Folder** to the cloned directory containing `run.py`.
- **TripoSR Defaults** only when you need to trade detail, VRAM, background removal, or texture behavior for a particular machine.

Verify the environment independently before using the bridge:

```text
cd TripoSR
TRIPOSR_PYTHON run.py examples/chair.png --output-dir output
```

The provider diagnostics should then report TripoSR as runnable. For final assets with meaningful unseen structure, use calibrated multi-view input with Tripo or Meshy, or author and refine the model in Blender.

### Configure a self-hosted studio endpoint

The studio route is for an image-to-3D service running on this computer, another machine on the local network, or an HTTPS server your studio controls. The bridge does not install or operate that service. In **Set Up Providers**, enter its base URL under **Studio Endpoint** and, when required, enter an **Endpoint Token**. The token follows the same session/credential-store rules as the hosted provider keys.

The service contract is intentionally small:

```text
POST /image-to-3d
  {"views": [{"name": "front", "image_url": "data:..."}], ...}
  -> {"task_id": "..."}

GET /tasks/{task_id}
  -> {"status": "...", "progress": 0, "model_url": "..."}

GET /balance
  -> optional; the job continues when the service does not expose it
```

Task creation may also include `model`, `face_limit`, and `texture`. Status responses may return the GLB URL as `model_url` or `model_urls.glb`. Plain HTTP is accepted only for localhost, private/link-local IPs, single-label hosts, or `.local`/`.localhost` names; use HTTPS for a public domain. The bridge treats this route as local/self-hosted and does not show a vendor spend prompt, so the service owner remains responsible for its compute and billing policy. A Hunyuan3D or TRELLIS server can eventually sit behind this contract even though direct launchers are not currently included.

## Showcase: Egypt Dogfight

These compressed images come from the `egypt.blend` project used while testing the bridge. The agent inspected a scene, used helper/workflow tools, captured playblast and render evidence, repaired issues, kicked off longer render jobs through bridge tooling, and validated the resulting output without relying on shell scripts or hidden in-Blender chat loops.

<p align="center">
  <img src="docs/assets/egypt-dogfight-preview.gif" alt="Short animated preview of a Blender aircraft dogfight generated and reviewed through Blender Agent Bridge" />
</p>

<p align="center">
  <img src="docs/assets/egypt-workflow-strip.jpg" alt="Three stills showing planning, visual evidence capture, and helper repair in the Egypt dogfight scene" />
</p>

| Visual evidence | Diagnostic close-up | Render/playblast review |
| --- | --- | --- |
| ![Wide dogfight render](docs/assets/egypt-dogfight-wide.jpg) | ![Aircraft inspection close-up](docs/assets/egypt-inspection-closeup.jpg) | ![Crash playblast frame](docs/assets/egypt-crash-playblast.jpg) |

The source `.blend` file and full 1080p videos are not committed here; the repository only includes small showcase exports so the GitHub checkout stays light. See [docs/assets/PROVENANCE.md](docs/assets/PROVENANCE.md) for their origin, hashes, licensing boundary, and known third-party-source limitations.

## What Agents Can Do

- Inspect the current scene, selection, materials, animation, rigs, cameras, nodes, render settings, and `.blend` health.
- Keep complete inspection results by default, with optional summaries, field selection, pagination, and digest-based unchanged responses for lower-token follow-ups.
- Make reversible preview edits to common objects, materials, animation, lighting, cameras, rigs, and scene organization.
- Capture viewport, playblast, inspection-render, thumbnail, and render-job evidence.
- Search and import Poly Haven or Sketchfab assets through asynchronous download and import jobs.
- Generate and import image-to-3D assets through hosted Tripo or Meshy, run TripoSR locally for single-image blockouts, or call a configured self-hosted studio endpoint.
- Run animation and background-render workflows, including progress polling and output validation.
- Use bounded project-directory tools, or run custom Blender Python only after the user enables session script trust.

## Safety Model

Connected agents do not get blanket access by default. Enabling session script trust deliberately grants broad Blender-process access.

| Path | Behavior |
| --- | --- |
| Preview edits | Show `Commit` and `Revert` controls in Blender and retain normal Blender undo support. |
| Project tools | Restrict generic file access to the current saved project directory. Save/open/new-project operations require explicit confirmed paths. |
| Local bridge | Off by default and bound to `127.0.0.1`. Optional bearer authentication is available; without it, any local client that can reach the bridge may call its tools. |
| Generated Python | Refused while trust is off. With trust on, it has Blender **Run Script** permissions, including filesystem, network, subprocess, project-file, persistent-cache, and full Blender API access. |
| Script trust | Runtime-only and visibly revocable. It clears on Revoke, timed expiry, add-on reload, or Blender exit. Opening, creating, restoring, copying, renaming, saving, or modifying `.blend` files does not change an active grant, and file operations never extend a timed grant's expiry. Static findings are advisory, not a sandbox. |
| Credentials | Provider keys are held in session memory and redacted from responses. Optional persistence uses the operating system credential facility where available, with a clearly reported user-only file fallback; keys are never written to Blender preferences, `.blend` files, manifests, or audit logs. |

See [SECURITY.md](SECURITY.md), [PRIVACY.md](PRIVACY.md), and [docs/SAFETY_MODEL.md](docs/SAFETY_MODEL.md) for the detailed model.

## How It Works

```mermaid
flowchart LR
  user["User in Blender"] --> agent["External AI client"]
  agent --> mcp["Blender Agent Bridge MCP"]
  mcp --> bridge["Localhost bridge in Blender"]
  bridge --> scene["Open .blend scene"]
  bridge --> helpers["Safe helper tools"]
  bridge --> evidence["Viewport, playblast, render resources"]
  bridge --> assets["External asset cache/jobs"]
  bridge --> files["Project file lifecycle"]
  bridge --> scripts["Session-trusted Python"]
  helpers --> preview["Live preview transaction"]
  preview --> commit["Commit / Revert / Undo"]
  scripts --> trust["Trust / Revoke"]
```

The default MCP surface exposes exactly five stable gateway tools. Every Blender helper remains searchable, schema-addressable, and executable through that gateway, so clients that retrieve only a handful of tools cannot strand themselves with planners but no execution path. An opt-in `direct` surface restores the previous curated direct helpers, while `full` is reserved for compatibility and debugging. Initialization and tool definitions are deterministic for provider prompt-cache reuse, and content-free payload telemetry identifies response-size hotspots without storing scene output. Blender owns the open scene, previews, evidence, and trusted execution; the external MCP client owns the model, conversation, provider account, and provider cache policy.

The gateway catalog also includes versioned quality benchmark tasks, durable model-review state, execution traces, and async trusted-script jobs. These are discovered and invoked on demand, so quality and observability improve without paying the token cost of more top-level tools.

For reference construction and form repair, see [docs/MULTIVIEW_RECONSTRUCTION.md](docs/MULTIVIEW_RECONSTRUCTION.md) and [docs/SEMANTIC_SCULPTING.md](docs/SEMANTIC_SCULPTING.md).

See [docs/EXTERNAL_BRIDGE_MCP.md](docs/EXTERNAL_BRIDGE_MCP.md) for setup and troubleshooting.

Client-specific instructions: [Codex](docs/clients/CODEX.md), [Claude](docs/clients/CLAUDE.md), [Cursor](docs/clients/CURSOR.md), [VS Code/Cline/Roo](docs/clients/VSCODE.md), [ChatGPT](docs/clients/CHATGPT.md), [Gemini CLI](docs/clients/GEMINI.md), [OpenCode](docs/clients/OPENCODE.md), and [Ollama hosts](docs/clients/OLLAMA.md).

Community: browse the [curated showcase](docs/SHOWCASE.md), propose a [showcase submission](https://github.com/CallMeJones/blender-agent-bridge/issues/new?template=showcase.yml), join [Discussions](https://github.com/CallMeJones/blender-agent-bridge/discussions), report [issues](https://github.com/CallMeJones/blender-agent-bridge/issues), or read [Contributing](CONTRIBUTING.md) and [Adding a Tool](docs/ADDING_A_TOOL.md).

## Try These Prompts

With an object selected:

```text
Move the selected cube up 1 Blender unit and make it red.
```

```text
Make the selected cube bounce twice over 72 frames, getting smaller each bounce. Check it against the brief and leave it as a preview.
```

```text
Capture close-up inspection renders of the selected vehicle underside, review them against the brief, and suggest repair operations.
```

```text
Search Poly Haven for a sunset HDRI, cache it as an external asset job, poll until it is ready, then queue the import into the world as a preview.
```

```text
Check which image-to-3D providers are ready and explain their cost, privacy, and quality tradeoffs. Do not start a job.
```

```text
Generate a 3D model from these confirmed reference-image paths. If more than one provider is available, ask me which provider to use before starting anything.
```

```text
Render a playblast as a background job, poll it, assemble the MP4, and validate the output.
```

Live helper changes, including external asset imports, remain pending until you use `Commit`, `Revert`, or Blender undo. Generated Python never enters a pending approval queue: trust off refuses it, and trust on runs it immediately with Blender Run Script-equivalent permissions.

## Development

Contributor setup, build commands, and the complete test matrix live in [Development](docs/DEVELOPMENT.md), [Testing Guide](docs/TESTING_GUIDE.md), and [Release](docs/RELEASE.md). Current priorities and deliberately deferred work live in [Next on the Roadmap](docs/ROADMAP_NEXT.md). See [Contributing](CONTRIBUTING.md) before opening a change, and [Adding a Tool](docs/ADDING_A_TOOL.md) for registry and handler conventions.

The [documentation index](docs/README.md) links the architecture, MCP, preview, safety, client, and launch guides.

## License

Blender Agent Bridge source and release ZIPs are licensed under the GNU General Public License, version 3 or any later version. The Blender extension manifest declares this as `SPDX:GPL-3.0-or-later`; see [LICENSE](LICENSE) for the full license text. Release ZIPs include the license file at the package root. The separately distributed showcase media under `docs/assets/` is governed by [its provenance notice](docs/assets/PROVENANCE.md), not the extension's GPL license.
