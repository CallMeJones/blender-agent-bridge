"""A blocked catalog provider must leave scene/status requests responsive."""
from pathlib import Path
import sys
import threading
import time
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))
import claude_blender
from claude_blender import bridge_server, execution_lanes, external_assets
from unittest import mock

claude_blender.register()
entered, release = threading.Event(), threading.Event()
original = external_assets._fetch_json
main_thread = threading.get_ident()

def blocked_fetch(*_args, **_kwargs):
    assert threading.get_ident() != main_thread
    # This path must use captured policy, with no worker access to bpy.app.
    assert external_assets._network_context.policy is not None
    entered.set()
    assert release.wait(5)
    return {"wood": 2}

try:
    external_assets._fetch_json = blocked_fetch
    queue = bridge_server._requests
    op = queue.submit(lambda: bridge_server._execute_tool({
        "name": "list_poly_haven_categories", "arguments": {}, "operation_id": "blocked-provider"}), 30)
    queue.pump()
    assert entered.wait(3)
    heartbeats = []
    for index in range(3):
        status = queue.submit(lambda: bridge_server._scene_status(), 30)
        queue.pump()
        assert queue.wait(status, 0)["ok"]
        heartbeats.append(index)
    assert len(heartbeats) == 3 and not op.event.is_set()
    release.set()
    deadline = time.monotonic() + 5
    while not op.event.is_set() and time.monotonic() < deadline:
        queue.pump()
        time.sleep(0.01)
    assert queue.wait(op, 0)["ok"]
    imported = []
    def fake_download(**_kwargs):
        assert threading.get_ident() != main_thread
        return {"ok": True, "provider": "poly_haven", "asset_type": "models"}
    def fake_import(context, **_kwargs):
        assert threading.get_ident() == main_thread
        assert context.scene is bpy.context.scene
        imported.append(1)
        return {"ok": True}
    with mock.patch.object(external_assets, "download_poly_haven_asset", side_effect=fake_download), mock.patch.object(external_assets, "import_cached_asset", side_effect=fake_import):
        pending = queue.submit(lambda: bridge_server._execute_tool({
            "name": "import_poly_haven_asset", "arguments": {"asset_id": "fixture"}}), 30)
        deadline = time.monotonic() + 5
        while not pending.event.is_set() and time.monotonic() < deadline:
            queue.pump()
            time.sleep(0.01)
        assert queue.wait(pending, 0)["ok"]
        assert imported == [1]
        plan = execution_lanes.prepare(bpy.context, "import_poly_haven_asset", {"asset_id": "fixture"})
        original_scene = bpy.context.window.scene
        temporary_scene = bpy.data.scenes.new("Changed while downloading")
        try:
            bpy.context.window.scene = temporary_scene
            result = plan.finish({"ok": True})
            assert result["code"] == "scene_changed_during_download", result
            assert imported == [1]
        finally:
            bpy.context.window.scene = original_scene
            bpy.data.scenes.remove(temporary_scene)
    print("smoke_bridge_worker_lane: ok")
finally:
    release.set()
    external_assets._fetch_json = original
    claude_blender.unregister()
