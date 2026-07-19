# Contributing to Blender Agent Bridge

Thanks for helping make Blender automation safer and more useful. This is a maintainer-led project; proposals that preserve the local-first safety model, clear tool contracts, and reversible scene changes are especially welcome.

## Before You Start

- Use the latest `main` branch for development and the latest tagged release for user support.
- Search existing issues before opening a new one.
- Open an issue before a large feature, protocol change, new dependency, or safety-model change so scope can be agreed before implementation.
- Never include API keys, bridge tokens, proprietary `.blend` files, private captures, or third-party assets without redistribution rights.

## Development Setup

1. Install Blender 5.1 or newer and Python 3.12 or newer for the pure-Python checks.
2. Fork and clone the repository.
3. Create a focused branch from `main`.
4. Follow [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for a linked development extension or build a ZIP with:

   ```powershell
   python scripts\build_extension_zip.py --blender "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
   ```

For catalog or handler work, follow [Adding a Tool](docs/ADDING_A_TOOL.md). Tool metadata belongs in one of the eleven explicit registry domains; do not recreate definitions in the catalog, contracts, router, or dispatcher map.

## Required Evidence

Run the smallest owner test while developing, then the relevant gates from [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md). At minimum, most changes should pass:

```powershell
python -m compileall addon\claude_blender tests
python tests\smoke_release_consistency.py
python tests\smoke_bridge_protocol_validation.py
python tests\smoke_helper_routing.py
python tests\smoke_mcp_server.py
python tests\smoke_tool_contract_inventory.py
git diff --check
```

Changes touching Blender APIs, helpers, previews, scripts, rendering, resources, the bridge, or packaging must also run the relevant Blender-background tests. Release-sensitive changes should run the clean installed-extension smoke.

## Safety Expectations

- Prefer bounded structured helpers over arbitrary Python.
- Mutating helpers must use visible preview/commit/revert behavior where practical.
- Project-file paths must be supplied or confirmed by the user.
- New filesystem, network, subprocess, asset-import, or project-file capabilities require explicit contracts, audit redaction, refusal tests, and documentation.
- Static script checks are guardrails, not a sandbox; never describe them as one.
- Add regression coverage for allowed, refused, malformed, and rollback paths.

## Pull Requests

Keep pull requests focused. Include:

- the problem and intended behavior;
- safety and compatibility impact;
- tests run and their results;
- screenshots or generated evidence when UI or visual behavior changes;
- any remaining limitations.

Disclose substantial AI-assisted code generation so reviewers know where extra contract and safety scrutiny may be useful. The author remains responsible for understanding and validating every submitted change.

## Contribution License

The project is licensed under `GPL-3.0-or-later`. By submitting a contribution, you represent that you have the right to submit it and agree that it is licensed under the same `GPL-3.0-or-later` terms. No contributor license agreement or copyright assignment is currently required.

Documentation showcase media under `docs/assets/` has a separate provenance notice and must not be replaced or expanded with uncleared media. See [docs/assets/PROVENANCE.md](docs/assets/PROVENANCE.md).

Community projects can be proposed through the [showcase submission form](https://github.com/CallMeJones/blender-agent-bridge/issues/new?template=showcase.yml). Contributors looking for a bounded starting point can review [good first issue candidates](docs/GOOD_FIRST_ISSUES.md) and ask a maintainer to promote an available candidate into a labelled issue.
