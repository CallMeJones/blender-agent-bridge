"""Real background remeshing, cancellation, exact source preservation and preview import."""
import json
from pathlib import Path
import sys
import tempfile
import time
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))
import claude_blender
from claude_blender import job_runtime, preferences, retopology_jobs, tool_dispatcher


def call(name, args=None):
    return json.loads(tool_dispatcher.execute_tool(bpy.context, name, args or {}))


def wait(job_id):
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        job = call("get_retopology_job_status", {"job_id": job_id})["retopology_job"]
        if job["status"] in retopology_jobs.TERMINAL:
            return job
        time.sleep(.2)
    raise AssertionError("Retopology smoke timed out")


claude_blender.register()
old_preferences = preferences.get_preferences
with tempfile.TemporaryDirectory(prefix="bab-retopology-") as cache:
    preferences.get_preferences = lambda _context: type("Prefs", (), {"capture_cache_dir": cache})()
    try:
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16)
        source = bpy.context.object
        original = ([tuple(v.co) for v in source.data.vertices], [tuple(f.vertices) for f in source.data.polygons])
        baseline = {kind: set(getattr(bpy.data, kind).keys()) for kind in ("objects", "meshes", "materials", "images")}
        for method in ("decimate", "quadriflow"):
            started = call("start_retopology_job", {"object_names": [source.name], "method": method,
                                                    "target_faces": 100, "bake_textures": False})
            assert started["ok"], started
            assert original == ([tuple(v.co) for v in source.data.vertices], [tuple(f.vertices) for f in source.data.polygons])
            job = wait(started["job_id"])
            assert job["status"] == "completed", job
            imported = call("import_retopology_job_result", {"job_id": started["job_id"]})
            assert imported["ok"], imported
            target = bpy.data.objects[imported["objects"][0]]
            assert len(target.data.polygons) < len(source.data.polygons)
            if method == "quadriflow":
                assert sum(len(f.vertices) == 4 for f in target.data.polygons) > len(target.data.polygons) * .8
                engine = bpy.context.scene.render.engine
                camera = bpy.context.scene.camera
                bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
                rendered = call("evaluate_retopology_result", {"source_object_name": source.name, "target_object_name": target.name,
                                                              "include_renders": True})
                assert rendered["ok"] and len(rendered["previews"]) == 2, rendered
                for preview in rendered["previews"]:
                    assert preview["ok"] and len(preview["inspection_render"]["images"]) == 4, preview
                    assert all(Path(image["path"]).is_file() for image in preview["inspection_render"]["images"])
                assert bpy.context.scene.camera == camera
                bpy.context.scene.render.engine = engine
            assert call("import_retopology_job_result", {"job_id": started["job_id"]})["objects"] == imported["objects"]
            assert call("revert_preview")["ok"]
            for kind, names in baseline.items():
                assert set(getattr(bpy.data, kind).keys()) == names, kind
            if method == "decimate":
                with open(job["result_path"], "ab") as handle:
                    handle.write(b"changed-after-completion")
                refused = call("import_retopology_job_result", {"job_id": started["job_id"]})
                assert not refused["ok"] and "changed" in refused["message"], refused
            else:
                Path(job["job_dir"], "result.json").write_text("{}")
                invalid = call("get_retopology_job_status", {"job_id": started["job_id"]})
                assert invalid["retopology_job"]["status"] == "failed", invalid
        started = call("start_retopology_job", {"object_names": [source.name], "target_faces": 100, "bake_textures": False})
        cancelled = call("cancel_retopology_job", {"job_id": started["job_id"]})
        assert cancelled["ok"] and cancelled["retopology_job"]["status"] == "cancelled", cancelled
        assert not call("import_retopology_job_result", {"job_id": started["job_id"]})["ok"]
        started = call("start_retopology_job", {"object_names": [source.name], "target_faces": 100, "bake_textures": False})
        process = retopology_jobs._PROCESSES[started["job_id"]]
        directory = started["retopology_job"]["job_dir"]
        metadata_path = Path(directory, "metadata.json")
        metadata = json.loads(metadata_path.read_text())
        metadata["created_at"] -= metadata["timeout_seconds"] + 1
        job_runtime.write_json(str(metadata_path), metadata)
        timed_out = call("get_retopology_job_status", {"job_id": started["job_id"]})["retopology_job"]
        assert timed_out["status"] == "timed_out" and process.poll() is not None, timed_out
        job_runtime.write_json(str(Path(directory, "status.json")), {"status": "completed"})
        assert call("get_retopology_job_status", {"job_id": started["job_id"]})["retopology_job"]["status"] == "timed_out"
        assert original == ([tuple(v.co) for v in source.data.vertices], [tuple(f.vertices) for f in source.data.polygons])
        copies = [source.copy() for _ in range(4)]
        for obj in copies:
            bpy.context.scene.collection.objects.link(obj)
        limited = call("start_retopology_job", {"object_names": [source.name] + [obj.name for obj in copies]})
        assert not limited["ok"] and "Combined texture atlases" in limited["message"], limited
        for obj in copies:
            bpy.data.objects.remove(obj, do_unlink=True)
        assert call("get_retopology_job_status", {"job_id": "../escape"})["ok"] is False
        print("smoke_retopology_jobs: ok")
    finally:
        retopology_jobs.unregister()
        preferences.get_preferences = old_preferences
        claude_blender.unregister()
