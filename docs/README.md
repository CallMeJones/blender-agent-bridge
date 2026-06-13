# Claude For Blender Docs

Start with the top-level `README.md`, then use these deeper notes for development, safety, and external MCP setup.

## MCP Client Refresh

Some MCP clients cache tool lists and server configs. After installing a new zip or pressing `Copy MCP Config`, replace the old client config and refresh or restart the MCP client. The copied config includes `CLAUDE_BLENDER_MCP_CONFIG_VERSION`, add-on version, bridge version, MCP server version, and a short note in the server `env` block so stale configs are easier to spot.
