"""Deterministic, read-only summary of the canonical tool registry."""

from __future__ import annotations

import json
from collections import Counter
from typing import Iterable

from .registry import ToolRegistry


def _count_rows(values: Iterable[str]) -> list[dict[str, int | str]]:
    counts = Counter(values)
    return [{"name": name, "tool_count": counts[name]} for name in sorted(counts)]


def build_registry_report(registry: ToolRegistry) -> dict[str, object]:
    """Return stable counts without importing Blender-dependent handlers."""

    specs = registry.specs()
    return {
        "schema_version": 1,
        "registry_digest": registry.digest(),
        "tool_count": len(specs),
        "owners": _count_rows(spec.owner for spec in specs),
        "groups": _count_rows(group for spec in specs for group in spec.groups),
        "exposures": _count_rows(spec.exposure for spec in specs),
    }


def render_registry_report(registry: ToolRegistry) -> str:
    """Render the report as deterministic, review-friendly JSON."""

    return json.dumps(build_registry_report(registry), indent=2, sort_keys=True) + "\n"


def main() -> int:
    from . import REGISTRY

    print(render_registry_report(REGISTRY), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
