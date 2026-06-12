"""Smoke test for the stdio MCP server using a fake Blender bridge."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MCP_SERVER = os.path.join(ROOT, "addon", "claude_blender", "mcp_server.py")


class FakeBridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send(self, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            self._send({"ok": True, "scene": "Fake Scene", "bridge_version": "test"})
        elif parsed.path == "/tools":
            self._send(
                {
                    "ok": True,
                    "tools": [
                        {
                            "name": "list_scene_objects",
                            "title": "List Scene Objects",
                            "description": "List objects",
                            "inputSchema": {"type": "object", "properties": {}},
                            "annotations": {"mutatesScene": False},
                        }
                    ],
                }
            )
        elif parsed.path == "/resources":
            self._send(
                {
                    "ok": True,
                    "resources": [
                        {
                            "uri": "blender://scene/status",
                            "name": "scene-status",
                            "title": "Scene Status",
                            "mimeType": "application/json",
                        }
                    ],
                }
            )
        elif parsed.path == "/resource":
            self._send(
                {
                    "ok": True,
                    "uri": "blender://scene/status",
                    "mimeType": "application/json",
                    "text": '{"ok": true, "scene": "Fake Scene"}',
                }
            )
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if self.path == "/tool":
            self._send(
                {
                    "ok": True,
                    "result": {
                        "ok": True,
                        "tool": payload.get("name"),
                        "objects": [{"name": "Cube", "type": "MESH"}],
                    },
                }
            )
        else:
            self.send_error(404)


def _send(proc, payload):
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    assert line, "MCP server closed stdout"
    return json.loads(line)


def main():
    fake_bridge = ThreadingHTTPServer(("127.0.0.1", 0), FakeBridgeHandler)
    thread = threading.Thread(target=fake_bridge.serve_forever, daemon=True)
    thread.start()
    bridge_url = f"http://127.0.0.1:{fake_bridge.server_address[1]}"
    proc = subprocess.Popen(
        ["python", MCP_SERVER, "--bridge-url", bridge_url],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        initialized = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "smoke", "version": "1"},
                },
            },
        )
        assert initialized["result"]["capabilities"]["tools"] == {"listChanged": False}, initialized

        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        listed = _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {tool["name"] for tool in listed["result"]["tools"]}
        assert {"blender_bridge_status", "list_scene_objects"}.issubset(names), listed

        called = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_scene_objects", "arguments": {}},
            },
        )
        assert called["result"]["isError"] is False, called
        assert called["result"]["structuredContent"]["objects"][0]["name"] == "Cube", called

        resources = _send(proc, {"jsonrpc": "2.0", "id": 4, "method": "resources/list"})
        uris = {item["uri"] for item in resources["result"]["resources"]}
        assert "blender://bridge/status" in uris
        assert "blender://scene/status" in uris

        resource = _send(
            proc,
            {"jsonrpc": "2.0", "id": 5, "method": "resources/read", "params": {"uri": "blender://scene/status"}},
        )
        assert resource["result"]["contents"][0]["mimeType"] == "application/json", resource
        print("smoke_mcp_server: ok")
    finally:
        proc.kill()
        proc.wait(timeout=5)
        fake_bridge.shutdown()
        fake_bridge.server_close()


if __name__ == "__main__":
    main()
