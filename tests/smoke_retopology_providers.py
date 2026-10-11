"""Offline paid-job approval, real FBX/GLB imports and failed-import rollback."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))
import claude_blender
from claude_blender import (asset_jobs, external_assets, generation_clients, generation_providers,
                            generation_spend, preferences, retopology_providers, tool_dispatcher)


def call(name, args=None):
    return json.loads(tool_dispatcher.execute_tool(bpy.context, name, args or {}))


def wait(job_id):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        job = call("get_provider_retopology_job_status", {"job_id": job_id})["asset_job"]
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(.05)
    raise AssertionError("Provider smoke timed out")


claude_blender.register()
old_preferences = preferences.get_preferences
old_overlay = generation_providers.environment_overlay
old_run = retopology_providers.run
old_mode = os.environ.get(asset_jobs.ASSET_JOB_MODE_ENV)
generation_spend.clear_requests()
generation_providers.clear_session_generation_policy()
with tempfile.TemporaryDirectory(prefix="bab-retopo-provider-") as cache:
    preferences.get_preferences = lambda _context: type("Prefs", (), {"capture_cache_dir": cache})()
    generation_providers.environment_overlay = lambda _prefs: {"MESHY_API_KEY": "offline-fixture-secret", "TRIPO_API_KEY": "offline-fixture-secret",
                                                              generation_providers.EGRESS_ENV_VAR: generation_providers.EGRESS_ALLOW}
    os.environ[asset_jobs.ASSET_JOB_MODE_ENV] = "thread"
    requests = []
    try:
        source = bpy.data.objects["Cube"]
        bpy.ops.object.select_all(action="DESELECT")
        source.select_set(True)
        bpy.context.view_layer.objects.active = source
        fbx_path, glb_path = str(Path(cache, "fixture.fbx")), str(Path(cache, "fixture.glb"))
        bpy.ops.export_scene.fbx(filepath=fbx_path, use_selection=True, object_types={"MESH"}, add_leaf_bones=False)
        bpy.ops.export_scene.gltf(filepath=glb_path, export_format="GLB", use_selection=True)
        baseline = {kind: set(getattr(bpy.data, kind).keys()) for kind in
                    ("objects", "meshes", "materials", "images", "collections", "node_groups")}
        original = [tuple(v.co) for v in source.data.vertices]

        def run(config, args, *, provider, api_key, **kwargs):
            task_id = provider + "-retopo-fixture"
            def transport(method, url, headers, body, timeout):
                requests.append((provider, method, url, json.loads(body) if body else None))
                if provider == "meshy":
                    data = {"result": task_id} if method == "POST" else {
                        "status": "SUCCEEDED", "progress": 100,
                        "model_urls": {"glb": "https://fixtures.example/model.glb", "fbx": "https://fixtures.example/model.fbx"}}
                else:
                    data = {"code": 0, "data": {"task_id": task_id} if method == "POST" else {
                        "status": "success", "progress": 100, "output": {"model_url": "https://fixtures.example/model.glb"}}}
                return 200, json.dumps(data)
            client_type = generation_clients.MeshyClient if provider == "meshy" else generation_clients.TripoClient
            def download(url, path, **options):
                shutil.copyfile(fbx_path if path.endswith(".fbx") else glb_path, path)
                return {"ok": True, "bytes": os.path.getsize(path)}
            return old_run(config, args, provider=provider, api_key=api_key, client=client_type(api_key, transport=transport),
                           downloader=download, poll_interval=0, **kwargs)
        retopology_providers.run = run

        allowed_overlay = generation_providers.environment_overlay
        generation_providers.environment_overlay = lambda prefs: dict(allowed_overlay(prefs), **{
            generation_providers.EGRESS_ENV_VAR: generation_providers.EGRESS_DENY})
        blocked = call("start_provider_retopology_job", {"provider": "meshy", "source_task_id": "private-fixture"})
        assert not blocked["ok"] and not generation_spend.pending_requests() and not requests, blocked
        generation_providers.environment_overlay = allowed_overlay
        generation_providers.set_session_generation_policy(generation_providers.POLICY_LOCAL_ONLY)
        blocked = call("start_provider_retopology_job", {"provider": "tripo", "source_task_id": "private-fixture"})
        assert not blocked["ok"] and not generation_spend.pending_requests() and not requests, blocked
        generation_providers.clear_session_generation_policy()

        for provider in ("meshy", "tripo"):
            args = {"provider": provider, "source_task_id": provider + "-original", "target_faces": 5000}
            before_requests = len(requests)
            pending = call("start_provider_retopology_job", args)
            assert pending.get("awaiting_user_approval") and len(requests) == before_requests, pending
            assert pending["spend_approval"]["view_count"] == 0
            assert pending["spend_approval"]["estimated_credits"] == (5 if provider == "meshy" else 40)
            altered = call("start_provider_retopology_job", dict(args, target_faces=6000))
            assert altered["spend_approval"]["fingerprint"] != pending["spend_approval"]["fingerprint"]
            generation_spend.set_status(altered["spend_approval"]["request_id"], generation_spend.STATUS_DENIED)
            assert not call("start_provider_retopology_job", dict(args, target_faces=6000)).get("awaiting_user_approval")
            # This writes the same test store as the UI operator; no live provider is contacted.
            generation_spend.set_status(pending["spend_approval"]["request_id"], generation_spend.STATUS_APPROVED)
            started = call("start_provider_retopology_job", args)
            assert started["ok"], started
            assert not call("start_provider_retopology_job", args)["ok"]
            job = wait(started["job_id"])
            assert job["status"] == "completed", job
            assert job["provider_task_kind"] == ("remesh" if provider == "meshy" else "retopology")
            assert "offline-fixture-secret" not in Path(job["metadata_path"]).read_text()
            imported = call("import_provider_retopology_job_result", {"job_id": started["job_id"]})
            assert imported["ok"], imported
            targets = [bpy.data.objects[name] for name in imported["imported_objects"] if bpy.data.objects[name].type == "MESH"]
            assert len(targets) == 1
            assert all(len(face.vertices) == (4 if provider == "meshy" else 3) for face in targets[0].data.polygons)
            if provider == "meshy":
                primary_manifest = Path(job["manifest_path"]).read_text()
                variant = call("import_provider_retopology_job_result", {"job_id": started["job_id"], "preferred_format": "glb"})
                assert variant["ok"], variant
                assert set(variant["imported_objects"]).isdisjoint(imported["imported_objects"])
                assert Path(job["manifest_path"]).read_text() == primary_manifest
                assert all(len(f.vertices) == 3 for name in variant["imported_objects"]
                           for f in bpy.data.objects[name].data.polygons)
            assert [tuple(v.co) for v in source.data.vertices] == original
            assert call("revert_preview")["ok"]
            for kind, names in baseline.items():
                assert set(getattr(bpy.data, kind).keys()) == names, kind

            # An importer that creates data before failing must leave no scene debris.
            old_import = external_assets._import_model_file
            def broken_import(path):
                mesh = bpy.data.meshes.new("Partial failed import mesh")
                obj = bpy.data.objects.new("Partial failed import object", mesh)
                bpy.context.scene.collection.objects.link(obj)
                return {"ok": False, "message": "injected partial import failure"}
            external_assets._import_model_file = broken_import
            try:
                failed = call("import_provider_retopology_job_result", {"job_id": started["job_id"]})
                assert not failed["ok"] and failed["auto_reverted_preview"], failed
                for kind, names in baseline.items():
                    assert set(getattr(bpy.data, kind).keys()) == names, kind
            finally:
                external_assets._import_model_file = old_import
        assert len([r for r in requests if r[1] == "POST"]) == 2, requests
        print("smoke_retopology_providers: ok")
    finally:
        while asset_jobs._THREADS:
            for thread in list(asset_jobs._THREADS.values()):
                thread.join(timeout=5)
        retopology_providers.run = old_run
        preferences.get_preferences = old_preferences
        generation_providers.environment_overlay = old_overlay
        generation_spend.clear_requests()
        generation_providers.clear_session_generation_policy()
        if old_mode is None:
            os.environ.pop(asset_jobs.ASSET_JOB_MODE_ENV, None)
        else:
            os.environ[asset_jobs.ASSET_JOB_MODE_ENV] = old_mode
        claude_blender.unregister()
