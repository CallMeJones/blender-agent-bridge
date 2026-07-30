# Connection Diagnostics

`blender-bridge doctor` is the deterministic, read-only health check for the
complete client-to-Blender path. It never mutates the scene and never prints
bridge tokens or other environment values.

## What It Checks

The command reports each layer separately:

1. The current Python executable and MCP runtime version.
2. An optional JSON or TOML MCP client config and its Blender server entry.
3. Bridge URL validity, transport security, and loopback use.
4. TCP reachability at the configured host and port.
5. Blender/add-on health, loaded-source staleness, protocol compatibility, and
   tool-registry parity.
6. The exact five-tool MCP manifest.
7. Canonical schema lookup for `list_scene_objects`.
8. A real `blender_tool_catalog` invocation of `list_scene_objects`.

The final probe is a scene read. It does not create a preview, change selection,
write a file, or require script trust.

## Run It

Keep Blender open and press **Start** in the Agent Bridge panel. If
`blender-bridge` is installed:

```text
blender-bridge doctor
```

For machine-readable output:

```text
blender-bridge doctor --json
```

To inspect the exact client entry as well:

```text
blender-bridge doctor --client-config <path-to-client-config>
```

JSON configs using `mcpServers`, `mcp_servers`, native VS Code `servers`, or
OpenCode `mcp` containers are supported. The entry may use `blender`,
`blender-agent-bridge`, `blender_agent_bridge`, or another name carrying the
generated Blender environment metadata. String commands and OpenCode command
arrays normalize to the same check. TOML configs are supported on Python 3.11
and newer. The checker reports
missing commands, removed bundled-server paths, stale `uvx` version pins, and
old registry metadata without returning the config's environment values.
When a config is supplied, its bridge URL and token drive the actual probe.
Explicit `--bridge-url` or `--token` values must match the selected config.
Remote bridge targets require HTTPS; plaintext HTTP is accepted only for
loopback hosts.

Without a global install, run the matching PyPI release:

```text
uvx --from blender-bridge==<add-on-version> blender-bridge doctor
```

If Blender uses a bridge token, provide it through `BLENDER_BRIDGE_TOKEN` in
the local process environment. Do not place tokens in issue reports or command
output.

## Reading Failures

| Failure | Meaning | Recovery |
| --- | --- | --- |
| MCP command missing | The client points at a removed executable or unavailable runtime. | Copy a fresh MCP config or reinstall the MCPB connector. |
| Bundled server path missing | The Blender extension moved or was replaced. | Start the current extension, copy its complete config, and replace the old entry. |
| TCP connection refused | Blender is closed, the bridge is stopped, or the port is wrong. | Start the bridge and verify its port. |
| Explicit target differs from client config | The doctor would test a different connection than the selected client. | Remove the override or replace the client entry with the intended target. |
| Remote plaintext HTTP | A bearer token could cross the network without transport encryption. | Use loopback HTTP or an authenticated HTTPS endpoint. |
| TCP succeeds but health returns 404 or invalid JSON | Another process likely occupies the port. | Stop that process or change the Blender bridge port, then refresh the config. |
| HTTP 401 | The bridge token is missing or wrong. | Replace the complete client entry from Blender or update the connector's sensitive token setting. |
| Registry/protocol mismatch | The add-on and MCP runtime are from different builds. | Install matching versions, copy fresh config, and restart the client. |
| Loaded source stale | Files changed after Blender imported the add-on. | Reload scripts or restart Blender. |
| Five-tool manifest mismatch | A non-default surface is configured or the client cached an older manifest. | Remove the surface override, replace config, and fully refresh the client. |

The command validates the current runtime. A client can still display an older
cached tool list, so fully restart or refresh it after any config or connector
change. The visible list should contain exactly:

- `blender_bridge_status`
- `blender_tool_catalog`
- `search_blender_tools`
- `get_blender_tool_schema`
- `invoke_blender_tool`
