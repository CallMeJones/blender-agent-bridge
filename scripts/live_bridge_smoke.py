"""Quick live smoke for a running Blender Agent Bridge instance.

Run this with Blender open, the extension loaded, and the bridge started:

    python scripts/live_bridge_smoke.py
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def _read_json(url: str, *, timeout: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_tool(base_url: str, name: str, arguments: dict, *, timeout: float) -> dict:
    payload = json.dumps({"name": name, "arguments": arguments}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/tool",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = payload.get("result")
    if isinstance(result, dict):
        return result
    return payload


def _require_ok(label: str, result: dict) -> None:
    if not result.get("ok"):
        raise RuntimeError(f"{label} failed: {result.get('message') or result}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test a running Blender Agent Bridge.")
    parser.add_argument("--bridge-url", default="http://127.0.0.1:8765")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--skip-playblast", action="store_true")
    args = parser.parse_args()

    base_url = args.bridge_url.rstrip("/")
    try:
        health = _read_json(f"{base_url}/health", timeout=args.timeout)
        _require_ok("bridge health", health)
        print(
            "bridge ok:",
            f"Blender {health.get('blender_version', '?')}",
            f"source {health.get('addon_runtime_source_status', '?')}",
        )

        viewport = _post_tool(base_url, "capture_viewport", {"max_bytes": 900000}, timeout=args.timeout)
        _require_ok("capture_viewport", viewport)
        visual = viewport.get("visual_context") or {}
        print("viewport ok:", visual.get("resource_uri"), visual.get("path"))

        if not args.skip_playblast:
            playblast = _post_tool(
                base_url,
                "capture_animation_playblast",
                {
                    "frame_start": 1,
                    "frame_end": 24,
                    "max_frames": 2,
                    "quality": "preview",
                    "max_width": 640,
                    "max_height": 360,
                    "max_bytes": 500000,
                    "brief": "Live smoke: verify sampled playblast evidence resources.",
                },
                timeout=max(args.timeout, 60.0),
            )
            _require_ok("capture_animation_playblast", playblast)
            metadata = playblast.get("playblast") or {}
            print("playblast ok:", metadata.get("playblast_id"), f"{metadata.get('frame_count', 0)} frame(s)")

        evidence = _post_tool(
            base_url,
            "get_visual_evidence_resources",
            {"include_unavailable": True},
            timeout=args.timeout,
        )
        _require_ok("get_visual_evidence_resources", evidence)
        available = int(evidence.get("available_count") or 0)
        if available < 1:
            raise RuntimeError(f"visual evidence inventory has no available resources: {evidence}")
        latest = evidence.get("latest_available") or {}
        print("evidence ok:", f"{available} available", f"latest {latest.get('kind', 'unknown')}")
        return 0
    except (OSError, urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"live bridge smoke failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
