"""Explicitly regenerate the canonical tool-registry snapshot."""

from __future__ import annotations

import argparse
import json
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import tool_registry  # noqa: E402


DEFAULT_OUTPUT = os.path.join(ROOT, "tests", "snapshots", "tool_registry.json")


def snapshot_payload():
    specs = tool_registry.REGISTRY.specs()
    return {
        "schema_version": 1,
        "registry_digest": tool_registry.TOOL_REGISTRY_DIGEST,
        "tool_count": len(specs),
        "catalog_tool_count": len(tool_registry.definitions()),
        "domains": {
            module.__name__.rsplit(".", 1)[-1]: [spec.name for spec in module.SPECS]
            for module in tool_registry.DOMAIN_MODULES
        },
        "specs": [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": dict(spec.input_schema),
                "output_schema": dict(spec.output_schema),
                "contract": dict(spec.contract),
                "handler_key": spec.handler_key,
                "order": spec.order,
                "groups": list(spec.groups),
                "exposure": spec.exposure,
                "owner": spec.owner,
            }
            for spec in specs
        ],
        "definitions": tool_registry.definitions(),
        "contracts": tool_registry.contracts(),
    }


def write_snapshot(path=DEFAULT_OUTPUT):
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(snapshot_payload(), handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    path = write_snapshot(args.output)
    print(f"Updated tool registry snapshot: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
