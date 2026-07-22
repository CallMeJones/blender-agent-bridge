# Privacy

Blender Agent Bridge is a local, provider-neutral bridge. **The add-on never contacts an LLM provider itself.** It has no built-in chat, no model client, and no persistent provider API-key store. External MCP clients host the model/provider and decide what to send to it after reading the resources and tool results the bridge exposes.

## Local Data

The add-on may store local Blender Text datablocks for transcripts, pending scripts, script logs, and repair context. It may also write docs caches, checkpoints, viewport screenshots, sampled playblast frame sequences, and audit logs under user-controlled local paths.

Viewport screenshots are generated only when visual context is requested. Sampled animation playblast frames are generated only when `capture_animation_playblast` is called. Saved `.blend` files store captures under a project-local `.claude_blender/captures/<session_id>` folder by default. Unsaved or unwritable projects use the global `~/.claude_blender/captures/<project_id>/<session_id>` fallback, and a custom capture cache preference acts as a custom base directory. Treat project-local captures as generated artifacts unless you intentionally keep them.

The default audit log path is:

```text
~/.claude_blender/audit.jsonl
```

Audit entries record tool names, success/failure status, risk labels, and redacted argument summaries. Script/code fields, tokens, keys, passwords, and credential-like fields are redacted.

## Data Leaving The Machine

The add-on does not send your scene, prompts, screenshots, or any other data to a model provider. User-triggered outbound requests can fetch official Blender documentation, search or download CC0 assets from Poly Haven, and search or download models from Sketchfab. Sketchfab downloads require an API token supplied per call or through the external MCP client's server environment.

`Copy Config with Sketchfab` accepts the token in a masked one-time dialog and places it in the clipboard config. The token is not saved in Blender preferences, `.blend` files, or audit logs. The clipboard and the external MCP client configuration then contain the token, so protect them according to the operating system and client's credential-handling guidance.

When you start the localhost MCP bridge, it binds to `127.0.0.1` only and exposes scene context, tool contracts, and resources to a connected MCP client on the same machine. **The connected external client — not this add-on — decides what, if anything, to forward to its own model provider.** What that client sends (the user prompt, scene context, docs snippets, viewport screenshots when the Viewport toggle is enabled, sampled playblast frames when capture is requested, etc.) is governed by that client's own privacy policy.

## User Controls

- Keep the bridge off (it is off by default) until you want an external client to connect; optionally require a bearer token.
- Keep screenshots off unless visual context is needed, and request playblast capture only when animation review needs visible frames.
- Use `Reject` for unwanted pending Python, and `Revoke Trust` to end a runtime external script trust preset before it expires.
- Delete local checkpoint, screenshot, playblast, docs-cache, transcript, and audit files from disk when no longer needed.
