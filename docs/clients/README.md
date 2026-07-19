# MCP Client Guides

Last verified: 2026-07-19

Blender Agent Bridge works with MCP hosts that can launch a local stdio server. Bundled mode is the default and needs no extra package manager. The optional `uvx` mode runs the matching `blender-bridge` PyPI package and is useful when the client should not depend on the extension's installation path.

| Client | Local stdio support | Guide |
| --- | --- | --- |
| Codex and ChatGPT desktop app | Yes, through the shared Codex MCP configuration | [Codex](CODEX.md) |
| Claude Desktop and Claude Code | Yes | [Claude](CLAUDE.md) |
| Cursor | Yes | [Cursor](CURSOR.md) |
| VS Code, Cline, and Roo Code | Yes | [VS Code](VSCODE.md) |
| ChatGPT | Desktop through Codex; web requires a remote MCP endpoint | [ChatGPT](CHATGPT.md) |
| Gemini CLI | Yes | [Gemini CLI](GEMINI.md) |
| OpenCode | Yes | [OpenCode](OPENCODE.md) |
| Ollama | Through an MCP-capable host such as OpenCode | [Ollama](OLLAMA.md) |

## Rules Shared By Every Client

- Install and enable the Blender extension, open the **Agent Bridge** sidebar, and start the bridge first.
- Run only one MCP server instance against a Blender bridge at a time. Disable old or duplicate client entries before switching clients.
- Prefer **Copy MCP Config** in Blender. It supplies the current port, token, protocol, registry digest, version pin, and the correct bundled path.
- Bundled mode remains the zero-install default. `uvx / PyPI` requires [`uv`](https://docs.astral.sh/uv/getting-started/installation/) and runs the exact matching version.
- After changing the extension, launch mode, or config, replace the complete client entry and restart or refresh the MCP host.
- Safe smoke prompt: `Check Blender bridge status, list scene objects, and make no changes.`

