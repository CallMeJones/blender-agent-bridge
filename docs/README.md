# Blender Agent Bridge Docs

Start with the top-level `README.md`, then use these deeper notes for development, safety, and external MCP setup.

## User And Release Guides

- [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md) - canonical public-beta launch status across UI, testing, compatibility, security, packaging, GitHub, and community work.
- [INSTALL_FROM_GITHUB.md](INSTALL_FROM_GITHUB.md) - GitHub remote-repository install, manual release ZIP fallback, update steps, troubleshooting, and maintainer release smoke.
- [RELEASE.md](RELEASE.md) - release build, GitHub Actions, GitHub Pages, and detailed verification commands.
- [TESTING_GUIDE.md](TESTING_GUIDE.md) - comprehensive automated testing runbook for feature, tool, bridge, MCP, visual, safety, and release coverage.
- [clients/README.md](clients/README.md) - verified bundled and `uvx` setup guides for Codex, Claude, Cursor, VS Code/Cline/Roo, ChatGPT, Gemini CLI, OpenCode, and Ollama hosts.
- [SHOWCASE.md](SHOWCASE.md) - curated community showcase and submission requirements.
- [ADDING_A_TOOL.md](ADDING_A_TOOL.md) - canonical registry, handler, safety, snapshot, and test workflow for contributors.
- [GOOD_FIRST_ISSUES.md](GOOD_FIRST_ISSUES.md) - bounded tasks maintainers can promote into labelled contributor issues.

## Current Implementation Notes

- Viewport captures are exposed to MCP clients through `blender://captures/latest`, `blender://captures/latest/metadata`, and exact `blender://captures/{capture_id}` resources.
- Sampled animation playblast frames are exposed through `blender://playblasts/latest/metadata`, exact playblast metadata resources, and frame PNG resources for animation review.
- Render thumbnails are exposed through `blender://render-thumbnails/latest`, exact thumbnail resources, and matching metadata resources.
- Async render jobs are exposed through `blender://render-jobs/latest/metadata`, exact job metadata resources, frame PNG resources, and log resources.
- Saved `.blend` files store generated captures and playblast frames in project-local `.claude_blender/captures/<session_id>` folders by default. Unsaved or unwritable projects use Blender's extension user-data directory, falling back to `~/.claude_blender` only outside extension-aware Blender runtimes.
- External script trust is runtime-only: a pending non-privileged script can offer `Trust Session`, and active trust always exposes `Revoke` in the sidebar.
- The helper catalog now includes production kits for lighting presets, material palettes, product/vehicle/character refinement, product turntable staging, and scene organization.

## MCP Client Refresh

Some MCP clients cache tool lists and server configs. After installing a new zip or pressing `Copy MCP Config`, replace the old client config and refresh or restart the MCP client. The copied config includes `CLAUDE_BLENDER_MCP_CONFIG_VERSION`, add-on version, bridge version, MCP server version, and a short note in the server `env` block so stale configs are easier to spot.
