# Gemini CLI

Last verified: 2026-07-19

## Prerequisites

Install and enable Blender Agent Bridge, start it in Blender, and install Gemini CLI. Bundled mode uses the Python runtime already selected by Blender's copied config. `uvx / PyPI` requires `uvx` on `PATH`.

## Configuration

Add the copied server to Gemini CLI's `settings.json` under `mcpServers`. Bundled mode:

Use the hyphenated server id `blender-agent-bridge`; current Gemini CLI policy parsing can misread MCP server names that contain underscores.

```json
{
  "mcpServers": {
    "blender-agent-bridge": {
      "command": "<python-executable>",
      "args": ["<installed-extension>/claude_blender/mcp_server.py", "--bridge-url", "http://127.0.0.1:<port>"],
      "env": {"BLENDER_BRIDGE_TOKEN": "<bridge-token>"},
      "trust": false
    }
  }
}
```

Pinned `uvx` mode on macOS/Linux uses:

```json
"command": "uvx",
"args": ["--from", "blender-bridge==0.4.0", "blender-bridge", "--bridge-url", "http://127.0.0.1:<port>"]
```

On Windows use `"command": "cmd"` and prefix args with `"/c", "uvx"`. Preserve Blender's generated environment block. Leave `trust` false until you have inspected the tool surface and safety model.

## Restart And Smoke Test

Restart Gemini CLI or open a new session, run `/mcp list`, then ask: `Check Blender bridge status, find and invoke the scene-object inspection tool, and make no changes.`

## Troubleshooting

Only one active MCP process may target the Blender bridge. If discovery fails, check `/mcp`, the settings scope, command path, and copied port/token. Replace stale configs after extension updates; do not work around a protocol or registry mismatch.

Official reference: [Gemini CLI MCP servers](https://geminicli.com/docs/tools/mcp-server/).
