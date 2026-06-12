"""Blender background smoke test for the localhost bridge server."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import bridge_server  # noqa: E402


def _request_with_pump(fn, timeout=10):
    box = {"result": None, "error": None}

    def worker():
        try:
            box["result"] = fn()
        except Exception as exc:
            box["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    deadline = time.time() + timeout
    while thread.is_alive() and time.time() < deadline:
        bridge_server._process_requests()
        time.sleep(0.02)
    thread.join(timeout=0.1)
    if thread.is_alive():
        raise TimeoutError("HTTP bridge request did not finish")
    if box["error"]:
        raise box["error"]
    return box["result"]


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _post(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    claude_blender.register()
    try:
        result = bridge_server.start_bridge(port=0)
        assert result["ok"], result
        base = result["url"]
        assert base.startswith("http://127.0.0.1:"), base

        tools = _get(base + "/tools")
        names = {tool["name"] for tool in tools["tools"]}
        assert "list_scene_objects" in names, names
        assert "apply_vehicle_refinement_template" in names, names

        health = _request_with_pump(lambda: _get(base + "/health"))
        assert health["ok"], health
        assert health["scene"] == bpy.context.scene.name

        objects = _request_with_pump(
            lambda: _post(base + "/tool", {"name": "list_scene_objects", "arguments": {"max_objects": 5}})
        )
        assert objects["ok"], objects
        assert objects["result"]["ok"], objects
        assert any(item["name"] == "Cube" for item in objects["result"]["objects"]), objects

        resources = _get(base + "/resources")
        uris = {item["uri"] for item in resources["resources"]}
        assert "blender://scene/context" in uris, resources
        resource_url = base + "/resource?" + urllib.parse.urlencode({"uri": "blender://scene/status"})
        resource = _request_with_pump(lambda: _get(resource_url))
        assert resource["ok"], resource
        assert json.loads(resource["text"])["scene"] == bpy.context.scene.name

        stopped = bridge_server.stop_bridge()
        assert stopped["ok"], stopped
        print("smoke_bridge_server: ok")
    finally:
        bridge_server.stop_bridge()
        claude_blender.unregister()


if __name__ == "__main__":
    main()
