# Codex

Last verified: 2026-07-23

## Prerequisites

Install and enable Blender Agent Bridge, start it from Blender's **Agent Bridge** sidebar, and install Codex or the ChatGPT desktop app. Bundled mode needs nothing else. For `uvx / PyPI`, install `uv` so `uvx` is on the client process's `PATH`.

## Configuration

Use Blender's **Copy MCP Config** button whenever possible. Codex reads user configuration from `~/.codex/config.toml`; trusted projects can also use `.codex/config.toml`.

Bundled mode launches the `mcp_server.py` shipped inside the installed extension:

```toml
[mcp_servers.blender]
command = "<python-executable>"
args = ["<installed-extension>/claude_blender/mcp_server.py", "--bridge-url", "http://127.0.0.1:<port>"]

[mcp_servers.blender.env]
BLENDER_BRIDGE_TOKEN = "<bridge-token>"
```

Pinned `uvx` mode on macOS or Linux:

```toml
[mcp_servers.blender]
command = "uvx"
args = ["--from", "blender-bridge==0.4.0", "blender-bridge", "--bridge-url", "http://127.0.0.1:<port>"]

[mcp_servers.blender.env]
BLENDER_BRIDGE_TOKEN = "<bridge-token>"
```

On Windows the generated entry uses `command = "cmd"` and begins `args` with `"/c", "uvx"`. Preserve the complete generated `env` table, including an optional `SKETCHFAB_API_TOKEN`. You can also add the server with `codex mcp add`, or use **Settings > MCP servers > Add server** in the desktop app.

## Restart And Smoke Test

Save the config, restart Codex/ChatGPT desktop or refresh its MCP servers, and keep Blender open. Ask: `Check Blender bridge status, list scene objects, and make no changes.`

## Prompt Caching

The Blender server keeps initialization and tool definitions byte-stable so they are eligible for OpenAI's prefix cache. OpenAI API prompt caching is automatic for eligible prefixes; a custom Responses API client can additionally use one stable `prompt_cache_key` for equivalent Blender sessions and inspect cached-token usage in the response. Codex owns its provider request, so there is no MCP config flag that can force caching from the bridge.

## Troubleshooting

Run only one server instance against the bridge. If the tools are missing, remove duplicate entries, copy the config again, verify Blender says the bridge is running, and check that the configured Python or `uvx` is available to the app. A compatibility error means the extension and runtime disagree; copy a fresh matching config rather than bypassing the check.

Official reference: [Codex MCP configuration](https://developers.openai.com/codex/mcp/).
