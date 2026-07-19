"""Semantic bridge contract for JSON bridge and MCP access.

The Blender extension owns real scene reads/writes through bpy. A local
companion process exposes these tool names over MCP without changing the core
tool semantics.
"""

from __future__ import annotations

try:
    from . import build_info, tool_registry
except ImportError:  # Allows direct imports from addon/claude_blender.
    import build_info
    import tool_registry


BRIDGE_VERSION = build_info.BRIDGE_VERSION
CONTRACT_SCHEMA_VERSION = "1.0"
DEFAULT_TOOL_TIMEOUT_SECONDS = 60


DEFAULT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean", "description": "Whether the tool completed successfully"},
        "message": {"type": "string", "description": "Human-readable status or error message"},
    },
    "additionalProperties": True,
}


# Canonical 3D viewport shading modes for capture_animation_playblast. Single source of
# truth for the tool schema (here and in agent_tools) and the runtime validation set in
# playblast_capture, so they cannot drift.
PLAYBLAST_SHADING_MODES = ["WIREFRAME", "SOLID", "MATERIAL", "RENDERED"]


# Helpers that add lights surface a non-fatal warning when the scene was already lit,
# so callers can detect over-exposure risk from the structured result.
LIGHTING_AWARE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean", "description": "Whether the tool completed successfully"},
        "message": {"type": "string", "description": "Human-readable status or error message"},
        "created_objects": {"type": "array", "items": {"type": "string"}},
        "lights": {"type": "array", "items": {"type": "string"}},
        "lighting_warning": {
            "type": "string",
            "description": "Set when stacking lights onto an already-lit scene may over-expose the render; empty otherwise.",
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["ok"],
    "additionalProperties": True,
}


TOOL_CONTRACTS = tool_registry.contracts()


def _risk_level(contract):
    if contract.get("risk_level"):
        return str(contract["risk_level"])
    if contract.get("requires_approval"):
        return "approval"
    if contract.get("mutates_scene"):
        return "preview"
    return "read"


def _permissions(contract):
    configured = contract.get("permissions")
    if configured:
        return [str(item) for item in configured]
    if contract.get("requires_approval"):
        return ["scene:read", "script:stage"]
    if contract.get("mutates_scene"):
        permissions = ["scene:read", "scene:mutate"]
        if contract.get("requires_live_preview"):
            permissions.append("preview:write")
        return permissions
    return ["scene:read"]


def normalized_tool_contract(name, contract=None):
    raw = dict(contract if contract is not None else TOOL_CONTRACTS.get(name, {}))
    risk_level = _risk_level(raw)
    normalized = {
        "name": str(name),
        "title": str(raw.get("title") or str(name).replace("_", " ").title()),
        "description": str(raw.get("description") or ""),
        "mutates_scene": bool(raw.get("mutates_scene", False)),
        "requires_live_preview": bool(raw.get("requires_live_preview", False)),
        "requires_approval": bool(raw.get("requires_approval", False)),
        "has_side_effects": bool(raw.get("has_side_effects", raw.get("mutates_scene", False))),
        "requires_selection": bool(raw.get("requires_selection", False)),
        "supports_headless": bool(raw.get("supports_headless", not raw.get("mutates_scene", False))),
        "risk_level": risk_level,
        "timeout_seconds": int(raw.get("timeout_seconds") or DEFAULT_TOOL_TIMEOUT_SECONDS),
        "long_running": bool(raw.get("long_running", False)),
        "returns_background_job": bool(raw.get("returns_background_job", False)),
        "duration_hint": str(raw.get("duration_hint") or ""),
        "timeout_recovery": raw.get("timeout_recovery") if isinstance(raw.get("timeout_recovery"), dict) else {},
        "permissions": _permissions(raw),
        "output_schema": raw.get("output_schema") or DEFAULT_OUTPUT_SCHEMA,
        "human_in_loop_required": bool(raw.get("human_in_loop_required", False)),
        "requires_user_path": bool(raw.get("requires_user_path", False)),
        "path_policy": str(raw.get("path_policy") or ""),
        "explicit_approval_required": bool(raw.get("explicit_approval_required", False)),
        "trust_window_auto_run_allowed": bool(raw.get("trust_window_auto_run_allowed", not bool(raw.get("explicit_approval_required", False)))),
        "approval_policy": str(raw.get("approval_policy") or ""),
        "recovery_hint": str(raw.get("recovery_hint") or ""),
    }
    for key, value in raw.items():
        normalized.setdefault(key, value)
    return normalized


def output_schema_for_tool(name):
    return normalized_tool_contract(name).get("output_schema") or DEFAULT_OUTPUT_SCHEMA


def mcp_annotations_for_tool(name):
    contract = normalized_tool_contract(name)
    mutates = bool(contract["mutates_scene"])
    side_effects = bool(contract["has_side_effects"])
    approval = bool(contract["requires_approval"])
    destructive = bool(contract.get("destructive", False))
    return {
        "mutatesScene": mutates,
        "hasSideEffects": side_effects,
        "requiresApproval": approval,
        "requiresLivePreview": bool(contract["requires_live_preview"]),
        "riskLevel": contract["risk_level"],
        "permissions": list(contract["permissions"]),
        "timeoutSeconds": int(contract["timeout_seconds"]),
        "longRunningHint": bool(contract.get("long_running", False)),
        "returnsBackgroundJob": bool(contract.get("returns_background_job", False)),
        "durationHint": str(contract.get("duration_hint") or ""),
        "timeoutRecovery": dict(contract.get("timeout_recovery") or {}),
        "humanInLoopRequired": bool(contract.get("human_in_loop_required", False)),
        "requiresUserPath": bool(contract.get("requires_user_path", False)),
        "pathPolicy": str(contract.get("path_policy") or ""),
        "requiresExplicitOneTimeApproval": bool(contract.get("explicit_approval_required", False)),
        "trustWindowAutoRunAllowed": bool(contract.get("trust_window_auto_run_allowed", True)),
        "approvalPolicy": str(contract.get("approval_policy") or ""),
        "recoveryHint": str(contract.get("recovery_hint") or ""),
        "readOnlyHint": not side_effects,
        "destructiveHint": destructive,
        "idempotentHint": False,
        "openWorldHint": "network" in contract["permissions"],
    }


def list_tool_contracts():
    return {
        "bridge_version": BRIDGE_VERSION,
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "tools": {
            name: normalized_tool_contract(name, contract)
            for name, contract in TOOL_CONTRACTS.items()
        },
    }


def _schema_types(schema):
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return set(str(item) for item in schema_type)
    if isinstance(schema_type, str):
        return {schema_type}
    return set()


def _matches_json_type(value, schema_type):
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "null":
        return value is None
    return True


def _integer_schema_value(schema, key):
    value = schema.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def validate_arguments(value, schema, path="$"):
    """Validate a value against the JSON Schema subset used by this project.

    Dependency-free and bpy-free so both the in-Blender bridge and the
    standalone stdio MCP server can enforce the same tool contract. Returns a
    list of human-readable error strings (empty when valid).
    """

    if not isinstance(schema, dict):
        return []
    errors = []
    schema_types = _schema_types(schema)
    if schema_types and not any(_matches_json_type(value, item) for item in schema_types):
        errors.append(f"{path}: expected {', '.join(sorted(schema_types))}")
        return errors
    if "enum" in schema and value not in schema.get("enum", []):
        errors.append(f"{path}: expected one of {schema.get('enum')}")
        return errors
    for combiner in ("anyOf", "oneOf"):
        variants = schema.get(combiner)
        if not isinstance(variants, list):
            continue
        matches = 0
        first_variant_errors = []
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            variant_errors = validate_arguments(value, variant, path)
            if not variant_errors:
                matches += 1
            elif not first_variant_errors:
                first_variant_errors = variant_errors
        if combiner == "anyOf" and matches < 1:
            detail = f"; first variant: {first_variant_errors[0]}" if first_variant_errors else ""
            errors.append(f"{path}: expected to match at least one schema in anyOf{detail}")
        if combiner == "oneOf" and matches != 1:
            errors.append(f"{path}: expected to match exactly one schema in oneOf; matched {matches}")
    if isinstance(value, dict):
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}: required property is missing")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}.{key}: additional property is not allowed")
        for key, child_schema in properties.items():
            if key in value:
                errors.extend(validate_arguments(value[key], child_schema, f"{path}.{key}"))
    if isinstance(value, list):
        min_items = _integer_schema_value(schema, "minItems")
        max_items = _integer_schema_value(schema, "maxItems")
        if min_items is not None and len(value) < min_items:
            errors.append(f"{path}: expected at least {min_items} item(s)")
        if max_items is not None and len(value) > max_items:
            errors.append(f"{path}: expected at most {max_items} item(s)")
        if isinstance(schema.get("items"), dict):
            item_schema = schema["items"]
            for index, item in enumerate(value):
                errors.extend(validate_arguments(item, item_schema, f"{path}[{index}]"))
    if isinstance(value, str):
        min_length = _integer_schema_value(schema, "minLength")
        max_length = _integer_schema_value(schema, "maxLength")
        if min_length is not None and len(value) < min_length:
            errors.append(f"{path}: expected at least {min_length} character(s)")
        if max_length is not None and len(value) > max_length:
            errors.append(f"{path}: expected at most {max_length} character(s)")
    return errors


def register():
    pass


def unregister():
    pass
