# Security

Blender Agent Bridge gives AI agents structured access to a live Blender scene. Treat generated Blender Python as powerful local code.

## Supported Versions

Security fixes are provided for the latest tagged GitHub release. The `main` branch is the development line for the next release and may change without notice; it is tested in CI but is not a separately supported distribution channel. Older tags are unsupported once a newer release is published.

| Version | Supported |
| --- | --- |
| Latest tagged release | Yes |
| `main` development branch | Best effort until tagged |
| Older tagged releases | No |

If a report affects an older version, reproduce it against the latest tagged release when safe to do so. Maintainers may ask reporters to verify a fix on `main` before the next release.

## Reporting

Please report security issues privately through [GitHub Security Advisories](https://github.com/CallMeJones/blender-agent-bridge/security/advisories/new). If private advisories are unavailable, contact the maintainer through the repository before publishing details. Do not open a public issue for an unpatched vulnerability.

Do not include API keys, bridge tokens, proprietary `.blend` files, or private scene screenshots in a public issue.

## Security Model

- Generated arbitrary Python must be staged with `draft_script` and approved inside Blender before execution.
- The MCP bridge binds to `127.0.0.1` only and can require a bearer token.
- Live helper tools are bounded and should use reversible preview transactions.
- Checkpoints are saved before approved scripts when enabled.
- Runtime external script trust presets allow iterative tokenless script runs only for staged scripts that still pass static checks. Trust is cleared by revoke, add-on reload, file load, or bridge restart depending on the preset.
- MCP capture resources expose local viewport screenshots and sampled playblast frames to connected MCP clients. Keep screenshots and playblast capture off when visual context is not needed, and treat project-local `.claude_blender/captures/` folders as generated artifacts.
- Audit events are written locally to `~/.claude_blender/audit.jsonl` by default. Script/code-like arguments, tokens, keys, and passwords are redacted before logging.
- Static script checks are guardrails, not a sandbox. Blender Python can still access local files, network, and process state if the user approves it.
- Static checks reject dynamic builtin and Blender-operator reflection, dangerous Python object-graph introspection, indirect container calls, module-registry access, and references to blocked callables before trust-window execution.

## Hardening Checklist Before Release

The security and privacy go/no-go items are maintained in [docs/LAUNCH_CHECKLIST.md](docs/LAUNCH_CHECKLIST.md). Detailed test commands are in [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md). Do not maintain a duplicate release-status checklist here.
