# Cursor

Last verified: 2026-07-23

## Prerequisites

Install and enable Blender Agent Bridge, start the bridge, and install Cursor. Bundled mode needs no separate runtime. Install `uv` only if you select `uvx / PyPI` in Blender.

## Configuration

Put the server in the Cursor MCP settings UI or `.cursor/mcp.json`. Prefer the complete JSON from **Copy MCP Config**. Bundled mode uses:

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

Pinned `uvx` mode on macOS/Linux uses `"command": "uvx"` with:

```json
"args": ["--from", "blender-bridge==0.4.0", "blender-bridge", "--bridge-url", "http://127.0.0.1:<port>"]
```

On Windows, use `"command": "cmd"` and prefix args with `"/c", "uvx"`. Keep all environment fields copied by Blender, including the optional Sketchfab token.

## Restart And Smoke Test

Save the file, refresh Cursor's MCP servers or restart Cursor. The expected default manifest is the five status/catalog/search/schema/invoke gateway tools. Ask: `Check Blender bridge status, find and invoke the scene-object inspection tool, and make no changes.`

## Prompt Caching

The Blender server returns deterministic initialization and tool definitions, which preserves a stable cacheable prefix. Cursor controls the model/provider request and does not expose an MCP setting that lets this bridge force prompt caching. Keep the server connected and tool set unchanged during a session, and use Cursor or the configured provider's usage reporting when it exposes cached-token metrics.

## Troubleshooting

Keep only one active server connected to Blender. If Cursor shows no tools, check the MCP settings status, replace stale config, and verify the command is visible in Cursor's environment. Registry or protocol mismatch errors require the matching runtime version, not a disabled safety check.

Official reference: [Cursor Model Context Protocol](https://docs.cursor.com/context/model-context-protocol).
