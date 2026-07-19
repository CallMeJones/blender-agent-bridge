"""Canonical Blender tool metadata and deterministic registration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping


EMPTY_INPUT_SCHEMA = MappingProxyType({"type": "object", "properties": {}, "additionalProperties": False})
DEFAULT_OUTPUT_SCHEMA = MappingProxyType(
    {
        "type": "object",
        "properties": {
            "ok": {"type": "boolean", "description": "Whether the tool completed successfully"},
            "message": {"type": "string", "description": "Human-readable status or error message"},
        },
        "additionalProperties": True,
    }
)
VALID_EXPOSURES = frozenset({"catalog", "compact_direct", "internal"})


def _copy_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Mapping[str, Any]
    contract: Mapping[str, Any]
    handler_key: str
    order: int
    groups: tuple[str, ...] = field(default_factory=tuple)
    exposure: str = "catalog"
    owner: str = ""
    output_schema: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.handler_key:
            raise ValueError("Tool name and handler_key are required")
        if self.exposure not in VALID_EXPOSURES:
            raise ValueError(f"Unsupported exposure {self.exposure!r} for {self.name}")
        if self.output_schema is None:
            object.__setattr__(
                self,
                "output_schema",
                _copy_mapping(self.contract.get("output_schema") or DEFAULT_OUTPUT_SCHEMA),
            )

    def definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": _copy_mapping(self.input_schema),
        }

    def contract_definition(self) -> dict[str, Any]:
        # Safety metadata may be authored separately, but the public contract
        # shape must always come from the canonical ToolSpec fields.  This
        # prevents MCP advertisement, raw-bridge validation, resources, and the
        # registry digest from observing different schemas.
        contract = _copy_mapping(self.contract)
        contract["description"] = self.description
        contract["input_schema"] = _copy_mapping(self.input_schema)
        contract["output_schema"] = _copy_mapping(self.output_schema)
        return contract

    def digest_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "contract": self.contract,
            "output_schema": self.output_schema,
            "handler_key": self.handler_key,
            "order": self.order,
            "groups": self.groups,
            "exposure": self.exposure,
            "owner": self.owner,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Duplicate Blender tool registration: {spec.name}")
        self._specs[spec.name] = spec

    def register_many(self, specs: Iterable[ToolSpec]) -> None:
        for spec in specs:
            self.register(spec)

    def specs(self, *, include_internal: bool = True) -> tuple[ToolSpec, ...]:
        values = sorted(self._specs.values(), key=lambda spec: (spec.order, spec.name))
        if include_internal:
            return tuple(values)
        return tuple(spec for spec in values if spec.exposure != "internal")

    def get(self, name: str) -> ToolSpec:
        try:
            return self._specs[name]
        except KeyError as exc:
            raise KeyError(f"Unknown Blender tool: {name}") from exc

    def definitions(self) -> list[dict[str, Any]]:
        return [spec.definition() for spec in self.specs(include_internal=False)]

    def contracts(self) -> dict[str, dict[str, Any]]:
        return {spec.name: spec.contract_definition() for spec in self.specs()}

    def group_map(self) -> dict[str, set[str]]:
        result: dict[str, set[str]] = {}
        for spec in self.specs():
            for group in spec.groups:
                result.setdefault(group, set()).add(spec.name)
        return result

    def digest(self) -> str:
        payload = [spec.digest_payload() for spec in self.specs()]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def validate_handlers(self, handlers: Mapping[str, Any]) -> None:
        expected = {spec.name for spec in self.specs()}
        actual = set(handlers)
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        if missing or extra:
            raise ValueError(f"Tool handler parity failed; missing={missing}, extra={extra}")
        invalid = sorted(name for name, handler in handlers.items() if not callable(handler))
        if invalid:
            raise TypeError(f"Non-callable Blender tool handlers: {invalid}")


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, Any] = {}

    def register(self, name: str, handler: Any) -> None:
        if name in self._handlers:
            raise ValueError(f"Duplicate Blender handler registration: {name}")
        if not callable(handler):
            raise TypeError(f"Handler for {name} is not callable")
        self._handlers[name] = handler

    def as_dict(self) -> dict[str, Any]:
        return dict(self._handlers)
