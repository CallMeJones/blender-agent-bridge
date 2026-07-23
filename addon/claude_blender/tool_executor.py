"""Compose the canonical handler registry and execute tools on Blender's main thread."""

from __future__ import annotations

from . import animation_runtime, handler_runtime, live_preview, tool_registry


TOOL_FUNCTIONS = tool_registry.build_handlers()
animation_runtime.configure_tool_handler_lookup(TOOL_FUNCTIONS.get)


def execute_tool(context, name, args):
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return handler_runtime._json_result({"ok": False, "message": f"Unknown Blender tool: {name}"})
    transaction_before = live_preview.current_transaction()
    txn_id_before = (
        transaction_before["id"]
        if transaction_before and transaction_before.get("status") == "pending"
        else None
    )
    try:
        result = fn(context, args or {})
    except Exception as exc:
        result = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
    if isinstance(result, str):
        return result
    result = handler_runtime._maybe_auto_revert_failed_preview(context, result, txn_id_before)
    result = handler_runtime._attach_preview_change_report(result)
    return handler_runtime._json_result(result)
