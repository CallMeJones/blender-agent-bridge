# Claude Desktop And Claude Code

Last verified: 2026-07-28

## Prerequisites

Install and enable Blender Agent Bridge, start it in Blender, and install Claude Desktop or Claude Code. Bundled mode has no additional dependency. `uvx / PyPI` requires `uvx` on `PATH`.

## Configuration

For Claude Desktop, the lowest-friction path is the
`blender-agent-bridge-<version>.mcpb` asset from the matching GitHub release.
Install and start the Blender extension separately, open the MCPB in Claude
Desktop, keep the default bridge URL unless its port changed, and enter the
optional Blender bridge token in the connector's sensitive setting.

The MCPB packages the matching dependency-free Python MCP server code. Its MCPB
v0.4 `uv` runtime is managed by Claude Desktop, including the compatible Python
environment, so users do not need to install or configure Python. The connector
does not install Blender, grant script trust, upload scene data, or widen the
five-tool manifest.

For Claude Code or manual Claude Desktop setup, use **Copy MCP Config** in
Blender and replace the complete `blender` entry. A bundled entry has this shape:

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
["--from", "blender-bridge==0.5.6", "blender-bridge", "--bridge-url", "http://127.0.0.1:<port>"]
```

On Windows use `"command": "cmd"` and prefix the args with `"/c", "uvx"`. Claude Code can also register the object inside `mcpServers.blender` at user scope with `claude mcp add-json --scope user blender '<server-object-json>'`. Preserve any generated environment values, such as bridge or Sketchfab tokens and the `uvx` runtime marker.

## Restart And Smoke Test

Fully restart Claude Desktop after editing its config. In Claude Code, reconnect or restart the session and use `/mcp` to confirm the server. The normal manifest contains exactly `blender_bridge_status`, `blender_tool_catalog`, `search_blender_tools`, `get_blender_tool_schema`, and `invoke_blender_tool`. Ask: `Check Blender bridge status, find and invoke the scene-object inspection tool, and make no changes.`

When the command is installed, `blender-bridge doctor` independently verifies
the bridge socket, add-on/runtime parity, five-tool manifest, schema lookup, and
a read-only scene-object gateway call. Add `--client-config <path>` to inspect
the active JSON config for missing commands, old server paths, version pins, and
registry metadata. See [Connection Diagnostics](../CONNECTION_DIAGNOSTICS.md).

## Prompt Caching

Claude Code manages prompt caching automatically unless it is explicitly disabled. Keep the Blender MCP server connected and avoid changing its advertised tools mid-session. Claude places tool definitions in a cache-sensitive prompt layer when they are not deferred; reconnects or definition changes can cause a cache rebuild. Use Claude's reported `cache_creation_input_tokens` and `cache_read_input_tokens` to verify behavior rather than assuming a hit.

## Troubleshooting

Only one active MCP server may connect to the Blender bridge. Disable duplicates across Claude Desktop, Claude Code, and other clients. Claude may retrieve only five tools from a larger connector manifest, which is why the default Blender surface is the five gateways. Seeing only planning helpers indicates a stale or non-default `direct` manifest; install the matching MCPB or copy the latest config and reconnect. For spawn failures, run doctor against the active config to distinguish a missing executable from an old bundled path. For compatibility failures, install matching add-on and connector versions and refresh Claude.

Official reference: [Claude Code MCP servers](https://code.claude.com/docs/en/mcp).
