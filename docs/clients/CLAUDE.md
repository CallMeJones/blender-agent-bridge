# Claude Desktop And Claude Code

Last verified: 2026-07-23

## Prerequisites

Install and enable Blender Agent Bridge, start it in Blender, and install Claude Desktop or Claude Code. Bundled mode has no additional dependency. `uvx / PyPI` requires `uvx` on `PATH`.

## Configuration

The safest path is **Copy MCP Config** in Blender and replacing the complete `blender` entry. A bundled entry has this shape:

```json
{
  "mcpServers": {
    "blender": {
      "command": "<python-executable>",
      "args": ["<installed-extension>/claude_blender/mcp_server.py", "--bridge-url", "http://127.0.0.1:<port>"],
      "env": {"BLENDER_BRIDGE_TOKEN": "<bridge-token>"}
    }
  }
}
```

Pinned `uvx` mode on macOS/Linux changes the command to `uvx` and args to:

```json
["--from", "blender-bridge==0.4.0", "blender-bridge", "--bridge-url", "http://127.0.0.1:<port>"]
```

On Windows use `"command": "cmd"` and prefix the args with `"/c", "uvx"`. Claude Code can also register the object inside `mcpServers.blender` at user scope with `claude mcp add-json --scope user blender '<server-object-json>'`. Preserve the generated environment values and optional Sketchfab token.

## Restart And Smoke Test

Fully restart Claude Desktop after editing its config. In Claude Code, reconnect or restart the session and use `/mcp` to confirm the server. The normal manifest contains exactly `blender_bridge_status`, `blender_tool_catalog`, `search_blender_tools`, `get_blender_tool_schema`, and `invoke_blender_tool`. Ask: `Check Blender bridge status, find and invoke the scene-object inspection tool, and make no changes.`

## Prompt Caching

Claude Code manages prompt caching automatically unless it is explicitly disabled. Keep the Blender MCP server connected and avoid changing its advertised tools mid-session. Claude places tool definitions in a cache-sensitive prompt layer when they are not deferred; reconnects or definition changes can cause a cache rebuild. Use Claude's reported `cache_creation_input_tokens` and `cache_read_input_tokens` to verify behavior rather than assuming a hit.

## Troubleshooting

Only one active MCP server may connect to the Blender bridge. Disable duplicates across Claude Desktop, Claude Code, and other clients. Claude may retrieve only five tools from a larger connector manifest, which is why the default Blender surface is the five gateways. Seeing only planning helpers indicates a stale or non-default `direct` manifest; copy the latest config and reconnect. For spawn failures, check quoted Windows paths or the app-visible `PATH`; for compatibility failures, choose the matching launch mode in Blender and copy a fresh config.

Official reference: [Claude Code MCP servers](https://code.claude.com/docs/en/mcp).
