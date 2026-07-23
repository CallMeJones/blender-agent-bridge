# VS Code, Cline, And Roo Code

Last verified: 2026-07-19

## Prerequisites

Install and enable Blender Agent Bridge, start the bridge, and use a current VS Code with agent-mode MCP support, Cline, or Roo Code. Bundled mode needs no package install. `uvx / PyPI` requires `uvx` on the VS Code process's `PATH`.

## Configuration

Native VS Code uses `.vscode/mcp.json` with a top-level `servers` object. Translate the complete values from Blender's **Copy MCP Config** output:

```json
{
  "servers": {
    "blender_agent_bridge": {
      "type": "stdio",
      "command": "<python-executable>",
      "args": ["<installed-extension>/claude_blender/mcp_server.py", "--bridge-url", "http://127.0.0.1:<port>"],
      "env": {"BLENDER_BRIDGE_TOKEN": "<bridge-token>"}
    }
  }
}
```

For pinned `uvx` mode on macOS/Linux, set `command` to `uvx` and args to:

```json
["--from", "blender-bridge==0.4.0", "blender-bridge", "--bridge-url", "http://127.0.0.1:<port>"]
```

On Windows set `command` to `cmd` and prefix args with `"/c", "uvx"`. Cline and Roo Code expose MCP management in their extension UI and commonly accept the `mcpServers` JSON shape copied by Blender; use that UI rather than changing native VS Code's `servers` schema. Preserve all generated environment fields.

## Restart And Smoke Test

Use **MCP: List Servers** or the extension's MCP refresh control, then restart the agent session if needed. Ask: `Check Blender bridge status, list scene objects, and make no changes.`

## Troubleshooting

Do not enable the same bridge in native VS Code and Cline/Roo simultaneously; only one server instance should be active. If launch fails, inspect the MCP output channel, Windows quoting, and `PATH`. If compatibility fails, recopy the matching config from Blender.

Official references: [VS Code MCP servers](https://code.visualstudio.com/docs/agent-customization/mcp-servers), [Cline MCP overview](https://docs.cline.bot/mcp/mcp-overview), and [Roo Code MCP overview](https://docs.roocode.com/features/mcp/using-mcp-in-roo).
