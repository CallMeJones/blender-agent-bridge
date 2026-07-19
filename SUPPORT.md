# Support

Blender Agent Bridge is an early, maintainer-led open-source project. Community support is best effort and has no response-time or service-level guarantee.

## Supported Setup

- Latest tagged Blender Agent Bridge release.
- Blender 5.1 or newer.
- A local MCP-capable client such as Codex, Claude Desktop, Claude Code, Cursor, or another compatible host.
- Windows and Linux receive automated coverage. Other platforms are welcome but may require community diagnosis.

Older bridge releases and untagged development snapshots are not supported distributions. See [SECURITY.md](SECURITY.md) for the security support policy.

## Getting Help

Before opening an issue:

1. Update to the latest tagged release.
2. Restart Blender or disable and re-enable the extension.
3. Start the bridge, copy the MCP configuration again, and refresh or restart the MCP client.
4. Call `blender_bridge_status` and check that the add-on, MCP server, configuration, and source hash agree.
5. Review [docs/INSTALL_FROM_GITHUB.md](docs/INSTALL_FROM_GITHUB.md) and [docs/EXTERNAL_BRIDGE_MCP.md](docs/EXTERNAL_BRIDGE_MCP.md).

Use a GitHub bug report for reproducible defects and a feature request for proposals. Include Blender version, operating system, bridge version, MCP client, reproduction steps, expected behavior, actual behavior, and redacted logs.

Do not post API keys, bridge tokens, private `.blend` files, proprietary assets, or scene captures you cannot share.

## Security Reports

Do not report vulnerabilities in a public issue. Follow the private process in [SECURITY.md](SECURITY.md).
