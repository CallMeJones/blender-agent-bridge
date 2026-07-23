# Cursor

Last verified: 2026-07-19

## Prerequisites

Install and enable Blender Agent Bridge, start the bridge, and install Cursor. Bundled mode needs no separate runtime. Install `uv` only if you select `uvx / PyPI` in Blender.

## Configuration

Put the server in the Cursor MCP settings UI or `.cursor/mcp.json`. Prefer the complete JSON from **Copy MCP Config**. Bundled mode uses:

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

Pinned `uvx` mode on macOS/Linux uses `"command": "uvx"` with:

```json
"args": ["--from", "blender-bridge==0.4.0", "blender-bridge", "--bridge-url", "http://127.0.0.1:<port>"]
```

On Windows, use `"command": "cmd"` and prefix args with `"/c", "uvx"`. Keep all environment fields copied by Blender, including the optional Sketchfab token.

## Restart And Smoke Test

Save the file, refresh Cursor's MCP servers or restart Cursor, and ask: `Check Blender bridge status, list scene objects, and make no changes.`

## Troubleshooting

Keep only one active server connected to Blender. If Cursor shows no tools, check the MCP settings status, replace stale config, and verify the command is visible in Cursor's environment. Registry or protocol mismatch errors require the matching runtime version, not a disabled safety check.

Official reference: [Cursor Model Context Protocol](https://docs.cursor.com/context/model-context-protocol).
