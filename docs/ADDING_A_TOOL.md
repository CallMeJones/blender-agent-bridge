# Adding A Blender Tool

Blender Agent Bridge has one canonical metadata registry. A tool has exactly one owning domain, while cross-cutting routing is expressed through `ToolSpec.groups`. Public names, schemas, order, exposure, and safety contracts are compatibility-sensitive.

## 1. Choose The Owning Domain

Use one of the eleven explicit modules in `addon/claude_blender/tool_registry/domains/`. The ordered module list in `tool_registry/__init__.py` is intentional; do not add automatic package discovery.

If a genuinely new domain is required, add it to `DOMAIN_MODULES` in a stable position and document why an existing owner is unsuitable.

## 2. Add The Specification

Add one `ToolSpec` to that domain's `SPECS` tuple. Supply:

- `name`: stable public MCP/catalog name;
- `description`: concise selection guidance;
- `input_schema`: JSON Schema with explicit `additionalProperties` behavior;
- `contract`: mutation, confirmation, preview, network, filesystem, and output metadata used by safety validation;
- `handler_key`: Python handler name;
- `order`: stable catalog position;
- `groups`: zero or more cross-cutting routing groups;
- `exposure`: `catalog`, `compact_direct`, or `internal`;
- `owner`: the one owning domain.

Never copy the definition into `agent_tools.py`, `bridge_protocol.py`, or a routing table. Those views are generated from the registry.

## 3. Implement And Register The Handler

Implement Blender-dependent behavior in the dispatcher/handler layer, not in registry metadata. Importing `claude_blender.tool_registry` under ordinary Python must never import `bpy`. The domain's `register_handlers()` binds `handler_key` values after Blender handlers are available and registry parity rejects missing, extra, or non-callable entries.

Prefer an existing bounded helper and preview transaction over generated Python. Mutating tools must preserve commit/revert/undo semantics where practical. New file, network, subprocess, script, project, or asset capabilities need explicit contract metadata, redaction, refusal tests, and documentation.

## 4. Test The Contract

Add tests for:

- valid, malformed, and refused inputs;
- read-only versus mutation behavior;
- preview, commit, revert, and rollback where applicable;
- routing groups and compact exposure;
- Blender/headless behavior for code that imports `bpy`.

Run the focused tests, then:

```powershell
python -m unittest discover -s tests/unit -v
python tests/smoke_tool_contract_inventory.py
python tests/smoke_bridge_protocol_validation.py
python tests/smoke_helper_routing.py
python tests/smoke_release_consistency.py
```

## 5. Update The Snapshot Explicitly

Review the intended public change, then run:

```powershell
python scripts/update_tool_snapshot.py
```

Inspect `tests/snapshots/tool_registry.json` in the diff. CI validates this file but never rewrites it. Accidental renames, reordering, exposure changes, contract changes, and digest drift should therefore fail review visibly.

## 6. Document Compatibility

Update the changelog and any affected client or safety documentation. A registry change changes the canonical digest: bundled and PyPI runtimes must ship from the same version and artifact set. Protocol or digest mismatch fails tool calls; a version difference is only a warning when protocol and digest remain compatible.
