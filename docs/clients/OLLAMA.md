# Ollama Through An MCP-Capable Host

Last verified: 2026-07-19

## Prerequisites

Ollama supplies the local model, not the MCP host. Install Ollama plus an MCP-capable host such as OpenCode, then install and enable Blender Agent Bridge and start its bridge. Bundled mode needs no package manager. `uvx / PyPI` requires `uvx` on the host's `PATH`.

## Configuration

Launch or configure the chosen host for Ollama, then add Blender Agent Bridge to that host. For OpenCode, bundled mode uses:

```json
{
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

Pinned `uvx` mode on macOS/Linux changes `command` to:

```json
["uvx", "--from", "blender-bridge==0.4.0", "blender-bridge", "--bridge-url", "http://127.0.0.1:<port>"]
```

On Windows start the array with `"cmd", "/c", "uvx"`. Use Blender's copied values for the port, token, digest, and optional Sketchfab token. Other Ollama-compatible MCP hosts need the equivalent local stdio fields.

## Restart And Smoke Test

Restart the host after changing its config, confirm the Ollama model is selected, and ask: `Check Blender bridge status, find and invoke the scene-object inspection tool, and make no changes.`

## Troubleshooting

Only one MCP host instance should connect to Blender. Ollama model availability and MCP process availability are separate: if the model responds but tools do not, inspect the host's MCP status and command environment. Recopy the bridge config after updates or compatibility errors.

Official references: [Ollama integrations](https://docs.ollama.com/integrations/opencode) and [OpenCode MCP servers](https://dev.opencode.ai/docs/mcp-servers/).
