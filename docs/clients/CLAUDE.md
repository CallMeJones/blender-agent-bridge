# Claude Desktop And Claude Code

Last verified: 2026-07-19

## Prerequisites

Install and enable Blender Agent Bridge, start it in Blender, and install Claude Desktop or Claude Code. Bundled mode has no additional dependency. `uvx / PyPI` requires `uvx` on `PATH`.

## Configuration

The safest path is **Copy MCP Config** in Blender and replacing the complete `blender_agent_bridge` entry. A bundled entry has this shape:

```json
{
  "mcpServers": {
    "blender_agent_bridge": {
      "command": "<python-executable>",
      "args": ["<installed-extension>/claude_blender/mcp_server.py", "--bridge-url", "http://127.0.0.1:<port>"],
      "env": {"BLENDER_BRIDGE_TOKEN": "<bridge-token>"}
    }
  }
}
```

Pinned `uvx` mode on macOS/Linux changes the command to `uvx` and args to:

```json
["--from", "blender-bridge==0.3.1", "blender-bridge", "--bridge-url", "http://127.0.0.1:<port>"]
```

On Windows use `"command": "cmd"` and prefix the args with `"/c", "uvx"`. Claude Code can also register the copied JSON with `claude mcp add-json blender_agent_bridge '<json>'`. Preserve the generated environment values and optional Sketchfab token.

## Restart And Smoke Test

Fully restart Claude Desktop after editing its config. In Claude Code, reconnect or restart the session and use `/mcp` to confirm the server. Ask: `Check Blender bridge status, list scene objects, and make no changes.`

## Troubleshooting

Only one active MCP server may connect to the Blender bridge. Disable duplicates across Claude Desktop, Claude Code, and other clients. For spawn failures, check quoted Windows paths or the app-visible `PATH`; for compatibility failures, choose the matching launch mode in Blender and copy a fresh config.

Official reference: [Claude Code MCP servers](https://code.claude.com/docs/en/mcp).
