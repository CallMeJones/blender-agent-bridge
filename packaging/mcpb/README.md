# Blender Agent Bridge MCPB

This connector launches the Blender Agent Bridge MCP server packaged inside the
bundle. It does not install Blender or the Blender extension. Its MCPB v0.4
`uv` runtime asks the host to manage the compatible Python environment, so the
user does not need to install or configure Python.

Before connecting:

1. Install Blender Agent Bridge in Blender.
2. Open the Agent Bridge sidebar and press **Start**.
3. Leave the bridge URL at `http://127.0.0.1:8765` unless you changed the port.
4. If Blender has a bridge token configured, enter the same token in the
   connector's sensitive **Bridge token** setting.

The connector exposes exactly five top-level gateway tools. Every scene helper
remains available through catalog search, schema lookup, and gateway invocation.
