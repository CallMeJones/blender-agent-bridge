"""Stdio MCP server that forwards tool/resource calls to Blender's localhost bridge."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "claude-blender"
SERVER_VERSION = "0.1.0"
DEFAULT_BRIDGE_URL = "http://127.0.0.1:8765"


def _json_dumps(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=False)


def _stderr(message):
    print(message, file=sys.stderr, flush=True)


class BridgeClient:
    def __init__(self, base_url, token="", timeout=30):
        self.base_url = str(base_url or DEFAULT_BRIDGE_URL).rstrip("/")
        self.token = str(token or "")
        self.timeout = float(timeout)

    def _headers(self):
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def get(self, path, params=None):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Bridge HTTP {exc.code}: {detail}") from exc
        except OSError as exc:
            raise RuntimeError(f"Bridge unavailable at {self.base_url}: {exc}") from exc

    def post(self, path, payload):
        headers = self._headers()
        headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=max(self.timeout, 65.0)) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Bridge HTTP {exc.code}: {detail}") from exc
        except OSError as exc:
            raise RuntimeError(f"Bridge unavailable at {self.base_url}: {exc}") from exc


class BlenderMCPServer:
    def __init__(self, bridge):
        self.bridge = bridge

    def initialize(self, params):
        requested = (params or {}).get("protocolVersion") or PROTOCOL_VERSION
        return {
            "protocolVersion": requested if isinstance(requested, str) else PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False},
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "title": "Claude for Blender Bridge",
                "version": SERVER_VERSION,
            },
            "instructions": (
                "Connects AI clients to the running Blender scene through the Claude for Blender localhost bridge. "
                "Start the bridge inside Blender before using scene tools. Mutating tools affect the live scene and may leave preview changes pending."
            ),
        }

    def _bridge_status_tool(self):
        return {
            "name": "blender_bridge_status",
            "title": "Blender Bridge Status",
            "description": "Check whether the MCP server can reach the running Blender localhost bridge.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {"mutatesScene": False},
        }

    def tools_list(self):
        tools = [self._bridge_status_tool()]
        try:
            response = self.bridge.get("/tools")
            tools.extend(response.get("tools") or [])
        except Exception as exc:
            _stderr(f"tools/list bridge warning: {exc}")
        return {"tools": tools}

    def tools_call(self, params):
        params = params or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name == "blender_bridge_status":
            status = self._bridge_status()
            return {
                "content": [{"type": "text", "text": json.dumps(status, indent=2, sort_keys=True)}],
                "structuredContent": status,
                "isError": not bool(status.get("ok")),
            }
        response = self.bridge.post("/tool", {"name": name, "arguments": arguments})
        result = response.get("result", response)
        ok = bool(response.get("ok", True)) and bool(result.get("ok", True) if isinstance(result, dict) else True)
        text = json.dumps(result, indent=2, sort_keys=True, default=str)
        return {
            "content": [{"type": "text", "text": text}],
            "structuredContent": result if isinstance(result, dict) else {"text": text},
            "isError": not ok,
        }

    def _bridge_status(self):
        try:
            return self.bridge.get("/health")
        except Exception as exc:
            return {"ok": False, "bridge_url": self.bridge.base_url, "message": str(exc)}

    def resources_list(self):
        resources = [
            {
                "uri": "blender://bridge/status",
                "name": "bridge-status",
                "title": "Blender Bridge Connection Status",
                "description": "MCP server connection status for the Blender bridge",
                "mimeType": "application/json",
            }
        ]
        try:
            response = self.bridge.get("/resources")
            resources.extend(response.get("resources") or [])
        except Exception as exc:
            _stderr(f"resources/list bridge warning: {exc}")
        return {"resources": resources}

    def resources_read(self, params):
        uri = (params or {}).get("uri")
        if uri == "blender://bridge/status":
            status = self._bridge_status()
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(status, indent=2, sort_keys=True),
                    }
                ]
            }
        response = self.bridge.get("/resource", {"uri": uri})
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": response.get("mimeType", "text/plain"),
                    "text": response.get("text", ""),
                }
            ]
        }

    def handle_request(self, message):
        method = message.get("method")
        params = message.get("params") or {}
        if method == "initialize":
            return self.initialize(params)
        if method == "ping":
            return {}
        if method == "tools/list":
            return self.tools_list()
        if method == "tools/call":
            return self.tools_call(params)
        if method == "resources/list":
            return self.resources_list()
        if method == "resources/read":
            return self.resources_read(params)
        if method == "resources/templates/list":
            return {"resourceTemplates": []}
        raise KeyError(f"Method not found: {method}")


def _response(request_id, result=None, error=None):
    payload = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result if result is not None else {}
    return payload


def _error(code, message, data=None):
    payload = {"code": int(code), "message": str(message)}
    if data is not None:
        payload["data"] = data
    return payload


def serve(server, input_stream=None, output_stream=None):
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    for raw_line in input_stream:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            output_stream.write(_json_dumps(_response(None, error=_error(-32700, f"Parse error: {exc}"))) + "\n")
            output_stream.flush()
            continue
        if isinstance(message, list):
            responses = [_handle_one(server, item) for item in message]
            responses = [item for item in responses if item is not None]
            if responses:
                output_stream.write(_json_dumps(responses) + "\n")
                output_stream.flush()
            continue
        response = _handle_one(server, message)
        if response is not None:
            output_stream.write(_json_dumps(response) + "\n")
            output_stream.flush()


def _handle_one(server, message):
    request_id = message.get("id")
    method = message.get("method")
    if method == "notifications/initialized":
        return None
    if request_id is None:
        return None
    try:
        result = server.handle_request(message)
        return _response(request_id, result=result)
    except KeyError as exc:
        return _response(request_id, error=_error(-32601, str(exc)))
    except Exception as exc:
        return _response(request_id, error=_error(-32603, f"{type(exc).__name__}: {exc}"))


def main(argv=None):
    parser = argparse.ArgumentParser(description="MCP server for Claude for Blender")
    parser.add_argument("--bridge-url", default=os.environ.get("BLENDER_BRIDGE_URL", DEFAULT_BRIDGE_URL))
    parser.add_argument("--token", default=os.environ.get("BLENDER_BRIDGE_TOKEN", ""))
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("BLENDER_BRIDGE_TIMEOUT", "30")))
    args = parser.parse_args(argv)
    serve(BlenderMCPServer(BridgeClient(args.bridge_url, token=args.token, timeout=args.timeout)))


if __name__ == "__main__":
    main()
