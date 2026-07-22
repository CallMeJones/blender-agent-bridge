from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import build_info, mcp_server  # noqa: E402


class FakeBridgeHandler(BaseHTTPRequestHandler):
    registry_digest = build_info.TOOL_REGISTRY_DIGEST
    include_compatibility_metadata = True

    def log_message(self, _format, *_args):
        return

    def _send(self, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            payload = {"ok": True, "addon_version": build_info.ADDON_VERSION}
            if self.include_compatibility_metadata:
                payload.update(
                    {
                        "bridge_version": build_info.BRIDGE_VERSION,
                        "tool_registry_digest": self.registry_digest,
                    }
                )
            self._send(payload)
            return
        if self.path == "/tools":
            self._send(
                {
                    "ok": True,
                    "tools": [
                        {
                            "name": "list_scene_objects",
                            "description": "List objects",
                            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                            "annotations": {"mutatesScene": False},
                        }
                    ],
                }
            )
            return
        if self.path == "/resources":
            self._send({"ok": True, "resources": []})
            return
        self._send({"ok": False, "message": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self._send({"ok": True, "result": {"ok": True, "echo": payload}})


class MCPStdioTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeBridgeHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        env = os.environ.copy()
        executable = str(env.get("BLENDER_BRIDGE_EXECUTABLE") or "").strip()
        if executable:
            command = [executable]
            env.pop("PYTHONPATH", None)
        else:
            command = [sys.executable, "-m", "claude_blender.mcp_runtime.server"]
            env["PYTHONPATH"] = os.path.join(ROOT, "addon")
        self.process = subprocess.Popen(
            [
                *command,
                "--bridge-url",
                f"http://127.0.0.1:{self.server.server_port}",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

    def tearDown(self):
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=5)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def rpc(self, request_id, method, params=None):
        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()
        response = json.loads(self.process.stdout.readline())
        self.assertEqual(request_id, response["id"])
        return response

    def test_initialize_list_and_read_only_call(self):
        initialized = self.rpc(1, "initialize", {"protocolVersion": "2025-06-18"})
        self.assertEqual("0.3.1", initialized["result"]["serverInfo"]["version"])
        listed = self.rpc(2, "tools/list", {})
        names = {tool["name"] for tool in listed["result"]["tools"]}
        self.assertIn("list_scene_objects", names)
        unsupported_top_level = {"oneOf", "anyOf", "allOf"}
        for tool in listed["result"]["tools"]:
            self.assertFalse(
                unsupported_top_level.intersection(tool["inputSchema"]),
                f"{tool['name']} exposes an incompatible top-level schema combiner",
            )
        asset_import = next(
            tool for tool in listed["result"]["tools"] if tool["name"] == "start_external_asset_import_job"
        )
        self.assertIn("At least one of these property sets is required", asset_import["inputSchema"]["description"])
        called = self.rpc(3, "tools/call", {"name": "list_scene_objects", "arguments": {}})
        structured = called["result"]["structuredContent"]
        self.assertTrue(structured["ok"])
        self.assertEqual("list_scene_objects", structured["echo"]["name"])

        canonical = self.rpc(
            4,
            "tools/call",
            {"name": "get_blender_tool_schema", "arguments": {"name": "start_external_asset_import_job"}},
        )
        self.assertIn("anyOf", canonical["result"]["structuredContent"]["tool"]["inputSchema"])

    def test_registry_mismatch_fails_closed(self):
        FakeBridgeHandler.registry_digest = "0" * 64
        try:
            called = self.rpc(1, "tools/call", {"name": "list_scene_objects", "arguments": {}})
            self.assertTrue(called["result"]["isError"])
            self.assertEqual("bridge_incompatible", called["result"]["structuredContent"]["code"])
        finally:
            FakeBridgeHandler.registry_digest = build_info.TOOL_REGISTRY_DIGEST

    def test_missing_compatibility_metadata_fails_closed(self):
        FakeBridgeHandler.include_compatibility_metadata = False
        try:
            called = self.rpc(1, "tools/call", {"name": "list_scene_objects", "arguments": {}})
            self.assertTrue(called["result"]["isError"])
            structured = called["result"]["structuredContent"]
            self.assertEqual("bridge_incompatible", structured["code"])
            self.assertFalse(structured["data"]["compatibility_metadata_complete"])
        finally:
            FakeBridgeHandler.include_compatibility_metadata = True


class MCPClientSchemaTests(unittest.TestCase):
    def test_simple_any_of_is_flattened_without_mutating_canonical_schema(self):
        canonical = {
            "type": "object",
            "properties": {"left": {"type": "string"}, "right": {"type": "string"}},
            "anyOf": [{"required": ["left"]}, {"required": ["right"]}],
        }

        exposed = mcp_server._client_input_schema(canonical)

        self.assertIn("anyOf", canonical)
        self.assertNotIn("anyOf", exposed)
        self.assertIn("At least one of these property sets is required: left; right.", exposed["description"])

    def test_simple_all_of_merges_required_properties(self):
        exposed = mcp_server._client_input_schema(
            {
                "type": "object",
                "required": ["base"],
                "allOf": [{"required": ["left"]}, {"required": ["right", "base"]}],
            }
        )

        self.assertEqual(["base", "left", "right"], exposed["required"])
        self.assertNotIn("allOf", exposed)

    def test_complex_top_level_combiner_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Cannot safely flatten"):
            mcp_server._client_input_schema({"type": "object", "anyOf": [{"properties": {"x": {}}}]})


class MCPRuntimeStandaloneTests(unittest.TestCase):
    def test_malformed_bridge_url_reports_warning_without_crashing_runtime(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.join(ROOT, "addon")
        request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "claude_blender.mcp_runtime.server",
                "--bridge-url",
                "http://[",
            ],
            input=request + "\n",
            capture_output=True,
            text=True,
            env=env,
            timeout=5,
            check=False,
        )

        self.assertEqual(0, completed.returncode)
        response = json.loads(completed.stdout)
        self.assertEqual(1, response["id"])
        self.assertIn("blender_bridge_status", {tool["name"] for tool in response["result"]["tools"]})
        self.assertIn("tools/list bridge warning: Invalid IPv6 URL", completed.stderr)


if __name__ == "__main__":
    unittest.main()
