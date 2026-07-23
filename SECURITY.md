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

- Generated Python has a binary Blender-side trust boundary. With **Trust Agent Scripts** off, `draft_script` is refused without retaining script state or showing a pending-script dialog.
- With trust on, generated Python runs immediately with the same process permissions as Blender's **Run Script** command, including Blender API, filesystem, network, subprocess, project-file, and persistent-cache access.
- Trust is runtime-only and session-scoped. It is cleared by **Revoke**, add-on reload, file load, or Blender exit. Starting or stopping the bridge does not silently change it.
- The MCP bridge is off by default, binds to `127.0.0.1` only, and can require a bearer token. If no token is configured, any local client that can reach the bridge may call its tools; the trust confirmation states this before enabling generated Python.
- Live helper tools are bounded and should use reversible preview transactions.
- Checkpoints are saved before trusted scripts when enabled. Checkpoint failure blocks execution.
- MCP capture resources expose local viewport screenshots and sampled playblast frames to connected MCP clients. Keep screenshots and playblast capture off when visual context is not needed, and treat project-local `.claude_blender/captures/` folders as generated artifacts.
- Audit events are written locally to `~/.claude_blender/audit.jsonl` by default. Script/code-like arguments, tokens, keys, and passwords are redacted before logging.
- Static script checks are advisory guardrails under active trust, not a sandbox or permission filter. Only malformed Python and payloads above the 500k operational ceiling are refused.
- Bounded project-file, asset, render, capture, save, and cache tools remain preferable when their containment, provenance, rollback, polling, or recovery is useful. Their restrictions do not constrain trusted Python.

## Hardening Checklist Before Release

The security and privacy go/no-go items are maintained in [docs/LAUNCH_CHECKLIST.md](docs/LAUNCH_CHECKLIST.md). Detailed test commands are in [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md). Do not maintain a duplicate release-status checklist here.
