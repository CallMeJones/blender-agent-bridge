# Codex

Last verified: 2026-07-28

## Prerequisites

Install and enable Blender Agent Bridge, start it from Blender's **Agent
Bridge** sidebar, and install Codex or the ChatGPT desktop app. Bundled mode
needs nothing else. The release `.mcpb` is only for Claude Desktop; do not
install it in Codex. For `uvx / PyPI`, install `uv` so `uvx` is on the client
process's `PATH`.

## Configuration

1. In Blender's **Agent Bridge** sidebar, press **Start**.
2. Press **Copy MCP Config**. The generated values are the source of truth for
   the installed extension path, Blender Python executable, bridge URL, token,
   version metadata, and registry digest.
3. In Codex, open **Settings > MCP servers > Add server** and choose local
   **STDIO**.
4. Name the server `blender`, then copy the generated `command`, every `args`
   item in order, and every `env` value without rewriting paths or dropping
   metadata.
5. Save the server and select **Restart**. Remove or disable any older
   `blender` entry before reconnecting.

Codex reads user configuration from `~/.codex/config.toml`; on Windows this is
normally `C:\Users\<you>\.codex\config.toml`. Trusted projects can also use
`.codex/config.toml`. The desktop app, CLI, and IDE extension share this
configuration.

To let Codex install the copied entry, open a new task after pressing **Copy MCP
Config** and ask:

```text
Install the Blender MCP config currently on my clipboard as a user MCP server named blender; convert the JSON to Codex TOML without changing command, args, or env, preserve my existing config, never print token values, then verify it is listed and tell me to restart MCP.
```

If Codex cannot access the clipboard, enter the generated values through
Settings or convert the generated JSON to TOML manually. Do not reconstruct the
token, executable, extension path, or registry metadata from examples.

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

On Windows, an `uvx` entry uses `command = "cmd"` and begins `args` with `"/c",
"uvx"`. Preserve the complete generated `env` table, including an optional
`SKETCHFAB_API_TOKEN`. You can also add a server with `codex mcp add`, but the
Blender-generated entry remains authoritative.

## Restart And Smoke Test

Keep Blender open with the bridge running. Restart Codex or refresh its MCP
servers, then use `/mcp` in Codex or `codex mcp list` in a terminal to confirm
that `blender` is connected.

The expected default manifest contains exactly:

- `blender_bridge_status`
- `blender_tool_catalog`
- `search_blender_tools`
- `get_blender_tool_schema`
- `invoke_blender_tool`

Ask:

```text
Check Blender bridge status, find and invoke the scene-object inspection tool, and make no changes.
```

The client should discover `list_scene_objects`, retrieve its schema, and invoke
it through the gateway. It should not report that planner-named helpers are
unavailable merely because they are not top-level tools.

## Prompt Caching

The Blender server keeps initialization and tool definitions byte-stable so they are eligible for OpenAI's prefix cache. OpenAI API prompt caching is automatic for eligible prefixes; a custom Responses API client can additionally use one stable `prompt_cache_key` for equivalent Blender sessions and inspect cached-token usage in the response. Codex owns its provider request, so there is no MCP config flag that can force caching from the bridge.

## Troubleshooting

Run only one server instance against the bridge. If the tools are missing,
remove duplicate entries, copy the config again, verify Blender says the bridge
is running, and check that the configured Python or `uvx` is available to the
app. Seeing a planner-only or direct-helper manifest means the client is stale
or has a non-default tool-surface override. A compatibility error means the
extension and runtime disagree; copy a fresh matching config rather than
bypassing the check. Never post the generated bridge token in chat, logs, or an
issue.

Official reference: [Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
