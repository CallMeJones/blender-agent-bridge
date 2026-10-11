"""Semantic bridge contract for JSON bridge and MCP access.

The Blender extension owns real scene reads/writes through bpy. A local
companion process exposes these tool names over MCP without changing the core
tool semantics.
"""

from __future__ import annotations


try:
    from . import build_info, tool_registry
    from .schema_validation import validate_arguments
except ImportError:  # Allows direct imports from addon/claude_blender.
    import build_info
    import tool_registry
    from schema_validation import validate_arguments


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
        return ["scene:read", "script:trusted_run"]
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



def register():
    pass


def unregister():
    pass
