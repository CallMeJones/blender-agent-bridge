from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "addon"))
from claude_blender import build_info, mcp_server


class FakeBridge:
    base_url = "http://127.0.0.1:8765"
    def __init__(self):
        self.calls = []
    def get(self, path, params=None):
        if path == "/operation":
            return {"ok": True, "operation_id": params["operation_id"], "state": "completed", "result": {"ok": True}}
        return {"ok": True, "addon_version": build_info.ADDON_VERSION,
                "bridge_version": build_info.BRIDGE_VERSION, "tool_registry_digest": build_info.TOOL_REGISTRY_DIGEST}
    def post(self, path, payload, **_kwargs):
        self.calls.append(payload)
        return {"ok": True, "operation_id": payload["operation_id"], "result": {"ok": True}}


class OperationRecoveryTests(unittest.TestCase):
    def test_gateway_passes_identity_and_recovers_without_scene_call(self):
        bridge = FakeBridge()
        server = mcp_server.BlenderMCPServer(bridge)
        for gateway in ("invoke_blender_tool", "blender_tool_catalog"):
            args = {"name": "list_scene_objects", "arguments": {}, "operation_id": "recover-me"}
            if gateway == "blender_tool_catalog":
                args["action"] = "invoke"
            result = server.tools_call({"name": gateway, "arguments": args})["structuredContent"]
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["operation_id"], "recover-me")
            self.assertEqual(bridge.calls[-1]["operation_id"], "recover-me")
        result = server.tools_call({"name": "blender_bridge_status", "arguments": {"operation_id": "recover-me"}})["structuredContent"]
        self.assertEqual(result["state"], "completed")
        self.assertEqual(len(bridge.calls), 2)

    def test_invalid_identity_never_reaches_bridge(self):
        bridge = FakeBridge()
        server = mcp_server.BlenderMCPServer(bridge)
        result = server.tools_call({"name": "invoke_blender_tool", "arguments": {
            "name": "list_scene_objects", "operation_id": "x" * 129}})
        self.assertTrue(result["isError"])
        self.assertEqual(bridge.calls, [])

    def test_dropped_connection_still_returns_recovery_identity(self):
        bridge = FakeBridge()
        server = mcp_server.BlenderMCPServer(bridge)
        with mock.patch.object(bridge, "post", side_effect=RuntimeError("connection reset")):
            result = server.tools_call({"name": "invoke_blender_tool", "arguments": {
                "name": "list_scene_objects"}})["structuredContent"]
        self.assertFalse(result["ok"])
        self.assertTrue(result["operation_id"])
        self.assertEqual(result["data"]["status_tool"], "blender_bridge_status")
