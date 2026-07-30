# Cursor

Last verified: 2026-07-28

## Prerequisites

Install and enable Blender Agent Bridge, start the bridge, and install Cursor.
Bundled mode needs no separate runtime. The release `.mcpb` is only for Claude
Desktop; do not install it in Cursor. Install `uv` only if you select `uvx /
PyPI` in Blender.

## Configuration

1. In Blender's **Agent Bridge** sidebar, press **Start**.
2. Press **Copy MCP Config**. The generated JSON is the source of truth for the
   installed extension path, Blender Python executable, bridge URL, token,
   version metadata, and registry digest.
3. Open Cursor's MCP settings, or edit `~/.cursor/mcp.json` for all projects or
   `.cursor/mcp.json` for one project.
4. Merge the complete generated `mcpServers.blender` entry without deleting
   other servers or rewriting generated values.
5. Remove or disable any stale duplicate `blender` entry, then refresh Cursor's
   MCP servers or restart Cursor.

On Windows, the global path is normally
`C:\Users\<you>\.cursor\mcp.json`.

To let Cursor install the copied entry, open Cursor Agent after pressing **Copy
MCP Config** and ask:

```text
Merge the Blender MCP config currently on my clipboard into my global ~/.cursor/mcp.json as server blender without deleting existing servers, never print token values, then verify Cursor can see it and tell me to refresh MCP.
```

If Cursor cannot access the clipboard, merge the generated JSON manually. Do
not reconstruct the token, executable, extension path, or registry metadata
from examples. Bundled mode has this shape:

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

On Windows, an `uvx` entry uses `"command": "cmd"` and prefixes args with
`"/c", "uvx"`. Keep all environment fields copied by Blender, including the
optional Sketchfab token.

## Restart And Smoke Test

Keep Blender open with the bridge running. Open **Settings > MCP** and confirm
that `blender` is connected after refreshing or restarting Cursor.

The expected default manifest contains exactly:

- `blender_bridge_status`
- `blender_tool_catalog`
- `search_blender_tools`
- `get_blender_tool_schema`
- `invoke_blender_tool`

Ask:

```text
Check Blender bridge status, find and invoke the scene-object inspection tool, and make no changes.
```

Cursor should discover `list_scene_objects`, retrieve its schema, and invoke it
through the gateway. It should not report that planner-named helpers are
unavailable merely because they are not top-level tools.

## Prompt Caching

The Blender server returns deterministic initialization and tool definitions, which preserves a stable cacheable prefix. Cursor controls the model/provider request and does not expose an MCP setting that lets this bridge force prompt caching. Keep the server connected and tool set unchanged during a session, and use Cursor or the configured provider's usage reporting when it exposes cached-token metrics.

## Troubleshooting

Keep only one active server connected to Blender. If Cursor shows no tools,
check the MCP settings status, remove duplicate entries, replace stale config,
and verify the command is visible in Cursor's environment. Seeing a
planner-only or direct-helper manifest means Cursor cached an older tool list or
the config enables a non-default surface. Registry or protocol mismatch errors
require the matching runtime version, not a disabled safety check. Never post
the generated bridge token in chat, logs, or an issue.

Official reference: [Cursor Model Context Protocol](https://docs.cursor.com/context/model-context-protocol).
