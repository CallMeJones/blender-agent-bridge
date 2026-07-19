# OpenCode

Last verified: 2026-07-19

## Prerequisites

Install and enable Blender Agent Bridge, start the bridge, and install OpenCode. Bundled mode adds no dependency. `uvx / PyPI` requires `uvx` on the OpenCode process's `PATH`.

## Configuration

OpenCode represents a local MCP command as an array. Translate the complete command and environment from Blender's **Copy MCP Config** output into `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "blender_agent_bridge": {
      "type": "local",
      "command": ["<python-executable>", "<installed-extension>/claude_blender/mcp_server.py", "--bridge-url", "http://127.0.0.1:<port>"],
      "environment": {"BLENDER_BRIDGE_TOKEN": "<bridge-token>"},
      "enabled": true
    }
  }
}
```

Pinned `uvx` command on macOS/Linux:

```json
["uvx", "--from", "blender-bridge==0.3.0", "blender-bridge", "--bridge-url", "http://127.0.0.1:<port>"]
```

On Windows start the command array with `"cmd", "/c", "uvx"`. Preserve the copied token, compatibility fields, and optional Sketchfab token in `environment`.

## Restart And Smoke Test

Restart OpenCode or reload its MCP configuration, then ask: `Check Blender bridge status, list scene objects, and make no changes.`

## Troubleshooting

Keep only one bridge entry active across all clients. If the server is unavailable, verify the config scope, executable array, and Blender bridge state. Compatibility errors mean the PyPI version or bundled server is stale; recopy a matching config.

Official reference: [OpenCode MCP servers](https://dev.opencode.ai/docs/mcp-servers/).
