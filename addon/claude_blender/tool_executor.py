"""Compose the canonical handler registry and execute tools on Blender's main thread."""

from __future__ import annotations

import json
from . import animation_runtime, handler_runtime, live_preview, tool_registry


TOOL_FUNCTIONS = tool_registry.build_handlers()
animation_runtime.configure_tool_handler_lookup(TOOL_FUNCTIONS.get)


def execute_tool(context, name, args, *, handler=None):
    fn = handler or TOOL_FUNCTIONS.get(name)
    if fn is None:
        return handler_runtime._json_result({"ok": False, "message": f"Unknown Blender tool: {name}"})
    transaction_before = live_preview.current_transaction()
    txn_id_before = (
        transaction_before["id"]
        if transaction_before and transaction_before.get("status") == "pending"
        else None
    )
    contract = tool_registry.contracts().get(name, {})
    scope = (
        live_preview.begin_isolated(str((args or {}).get("label") or name), context)
        if contract.get("requires_live_preview") else None
    )
    try:
        result = fn(context, args or {})
        if scope and isinstance(result, str):
            result = json.loads(result)
    except Exception as exc:
        result = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
    if isinstance(result, str):
        return result
    if scope:
        if result.get("ok", True):
            transaction = live_preview.finish_isolated(scope)
            if "transaction_id" in result:
                result["transaction_id"] = transaction["id"]
        else:
            had_changes = live_preview.isolated_has_changes(scope)
            rollback = live_preview.abort_isolated(scope, context)
            result = dict(result, auto_reverted_preview=had_changes and bool(rollback.get("ok")),
                          auto_revert_message=rollback.get("message", ""),
                          auto_revert_manifest=rollback.get("manifest", {}))
            if rollback.get("rollback_warning_summary"):
                result["auto_revert_warnings"] = rollback["rollback_warning_summary"]
        live_preview.discard_empty_isolated(scope, context)
    else:
        result = handler_runtime._maybe_auto_revert_failed_preview(context, result, txn_id_before)
    result = handler_runtime._attach_preview_change_report(result)
    return handler_runtime._json_result(result)
