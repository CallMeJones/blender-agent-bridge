# ChatGPT

Last verified: 2026-07-19

## Prerequisites And Supported Paths

Install and enable Blender Agent Bridge and start its local bridge. The ChatGPT desktop app can use local stdio MCP servers through its shared Codex host and configuration. ChatGPT web uses remote MCP-backed plugin tools instead; it cannot launch this local stdio command on your computer. A web deployment therefore needs a separately secured remote MCP adapter or OpenAI Secure MCP Tunnel, which this project does not deploy automatically.

Bundled mode needs no extra runtime. `uvx / PyPI` needs `uvx` on the desktop app's `PATH`. There is no separate ChatGPT-local JSON file: configure the shared Codex MCP host as described below.

## ChatGPT Desktop Configuration

Use Blender's **Copy MCP Config** values in `~/.codex/config.toml`, or add the server through the desktop app's MCP settings. Bundled mode launches:

```text
<python-executable> <installed-extension>/claude_blender/mcp_server.py --bridge-url http://127.0.0.1:<port>
```

Pinned `uvx` mode on macOS/Linux launches:

```text
uvx --from blender-bridge==0.3.0 blender-bridge --bridge-url http://127.0.0.1:<port>
```

Windows uses `cmd /c uvx --from blender-bridge==0.3.0 blender-bridge ...`. Translate the generated command, args, and environment into the shared `[mcp_servers.blender_agent_bridge]` TOML shape shown in the [Codex guide](CODEX.md). Preserve `BLENDER_BRIDGE_TOKEN`, registry/version fields, and the optional Sketchfab token; do not paste bridge secrets into chat messages.

Restart or refresh the ChatGPT desktop app's MCP host after replacing the entry, then ask: `Check Blender bridge status, list scene objects, and make no changes.`

## ChatGPT Web Path

Do not expose Blender's unauthenticated localhost bridge to the public internet. A ChatGPT web deployment needs a separately secured remote MCP adapter or Secure MCP Tunnel, authentication, and an explicit threat review. After configuring that supported remote path, refresh or restart ChatGPT so it receives the approved app snapshot, then use the same smoke prompt.

## Troubleshooting

Only one MCP server instance should target Blender. Disable duplicate desktop/CLI hosts before switching. If desktop tools are missing, verify the shared Codex entry and refresh the local MCP host. For ChatGPT web, verify the remote/tunnel endpoint and workspace app approval without weakening bridge authentication or exposing Blender's loopback listener.

Official references: [Codex MCP configuration](https://developers.openai.com/codex/mcp/), [Apps in ChatGPT](https://help.openai.com/en/articles/11487775-connectors-in-chatgpt), and [Developer mode and MCP apps](https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt-beta).
