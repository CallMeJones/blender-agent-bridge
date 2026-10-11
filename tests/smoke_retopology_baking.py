"""Real PBR texture rebaking, coverage, packed images and source preservation."""
import json
from pathlib import Path
import sys
import tempfile
import time
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))
import claude_blender
from claude_blender import blender_compat, preferences, retopology_jobs, tool_dispatcher


def call(name, args=None):
    return json.loads(tool_dispatcher.execute_tool(bpy.context, name, args or {}))


def wait(job_id):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        job = call("get_retopology_job_status", {"job_id": job_id})["retopology_job"]
        if job["status"] in retopology_jobs.TERMINAL:
            return job
        time.sleep(.2)
    raise AssertionError("Bake smoke timed out")


claude_blender.register()
old_preferences = preferences.get_preferences
with tempfile.TemporaryDirectory(prefix="bab-retopology-bake-") as cache:
    preferences.get_preferences = lambda _context: type("Prefs", (), {"capture_cache_dir": cache})()
    try:
        source = bpy.data.objects["Cube"]
        mat = bpy.data.materials.new("Bake source PBR")
        tree = blender_compat.ensure_node_tree(mat)
        shader = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
        shader.inputs["Roughness"].default_value = .25
        shader.inputs["Metallic"].default_value = .7
        shader.inputs["Emission Color"].default_value = (.1,.2,.3,1)
        shader.inputs["Emission Strength"].default_value = 12
        image = bpy.data.images.new("Red blue source texture", width=32, height=32)
        image.pixels = [c for y in range(32) for x in range(32) for c in ((1,0,0,1) if x < 16 else (0,0,1,1))]
        image.pack()
        node = tree.nodes.new("ShaderNodeTexImage")
        node.image = image
        tree.links.new(node.outputs["Color"], shader.inputs["Base Color"])
        source.data.materials.clear()
        source.data.materials.append(mat)
        target = source.copy()
        target.data = source.data.copy()
        target.name = "Bake Target"
        bpy.context.scene.collection.objects.link(target)
        original = ([tuple(v.co) for v in source.data.vertices], [n.name for n in tree.nodes], list(image.pixels),
                    [tuple(loop.uv) for uv in source.data.uv_layers for loop in uv.data])
        baseline = {kind: set(getattr(bpy.data, kind).keys()) for kind in ("objects", "meshes", "materials", "images")}
        started = call("start_retopology_bake_job", {"source_object_name": source.name, "target_object_name": target.name,
                                                    "resolution": 64, "samples": 1,
                                                    "map_types": ["base_color", "normal", "roughness", "metallic", "emission"]})
        assert started["ok"], started
        job = wait(started["job_id"])
        assert job["status"] == "completed", job
        baked = job["report"]["results"][0]["bake"]
        assert baked["coverage"]["fraction"] > .98, baked
        assert len(baked["maps"]) == 5 and all(Path(m["path"]).is_file() for m in baked["maps"]), baked
        imported = call("import_retopology_job_result", {"job_id": started["job_id"]})
        assert imported["ok"], imported
        result = bpy.data.objects[imported["objects"][0]]
        assert result.data.uv_layers
        result_mat = result.data.materials[0]
        shader_result = next(n for n in result_mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        for socket in ("Base Color", "Normal", "Roughness", "Metallic", "Emission Color"):
            assert shader_result.inputs[socket].is_linked, socket
        images = {n.image.name.rsplit(" ", 1)[-1]: n.image for n in result_mat.node_tree.nodes if n.type == "TEX_IMAGE"}
        assert len(images) == 5 and all(im.packed_file for im in images.values()), images
        rough = list(images["roughness"].pixels)
        metal = list(images["metallic"].pixels)
        assert any(abs(rough[i] - .25) < .02 for i in range(0, len(rough), 4))
        assert any(abs(metal[i] - .7) < .02 for i in range(0, len(metal), 4))
        emission = list(images["emission"].pixels)
        assert any(abs(emission[i] - 1.2) < .02 and abs(emission[i+2] - 3.6) < .02 for i in range(0, len(emission), 4))
        color = list(images["base_color"].pixels)
        assert any(color[i] > .8 and color[i+2] < .2 for i in range(0,len(color),4))
        assert any(color[i+2] > .8 and color[i] < .2 for i in range(0,len(color),4))
        assert original == ([tuple(v.co) for v in source.data.vertices], [n.name for n in tree.nodes], list(image.pixels),
                            [tuple(loop.uv) for uv in source.data.uv_layers for loop in uv.data])
        assert source.data.materials[0] is mat and target.data.materials[0] is mat
        assert call("revert_preview")["ok"]
        for kind, names in baseline.items():
            assert set(getattr(bpy.data, kind).keys()) == names, kind
        # Default all-in-one remesh + rebake uses the same background pipeline.
        started = call("start_retopology_job", {"object_names": [source.name], "method": "decimate", "target_faces": 50,
                                               "resolution": 32, "samples": 1})
        assert wait(started["job_id"])["status"] == "completed"
        # Missing UVs in existing-atlas mode fail without changing either original.
        while target.data.uv_layers:
            target.data.uv_layers.remove(target.data.uv_layers[0])
        started = call("start_retopology_bake_job", {"source_object_name": source.name, "target_object_name": target.name,
                                                    "resolution": 16, "samples": 1, "uv_mode": "existing"})
        failure = wait(started["job_id"])
        assert failure["status"] == "failed" and "UV map" in failure["message"], failure
        assert not call("import_retopology_job_result", {"job_id": started["job_id"]})["ok"]
        extra_shader = tree.nodes.new("ShaderNodeBsdfPrincipled")
        started = call("start_retopology_bake_job", {"source_object_name": source.name, "target_object_name": target.name,
                                                    "resolution": 16, "samples": 1})
        failure = wait(started["job_id"])
        assert failure["status"] == "failed" and "one Principled" in failure["message"], failure
        tree.nodes.remove(extra_shader)
        # Far-away surfaces have an explicit coverage warning, including black regions.
        target.location.x += 20
        bpy.context.view_layer.update()
        started = call("start_retopology_bake_job", {"source_object_name": source.name, "target_object_name": target.name,
                                                    "resolution": 16, "samples": 1})
        job = wait(started["job_id"])
        assert job["status"] == "completed", job
        assert job["report"]["results"][0]["bake"]["coverage"]["fraction"] == 0
        assert job["report"]["results"][0]["bake"]["warnings"]
        for kind, names in baseline.items():
            assert set(getattr(bpy.data, kind).keys()) == names, kind
        print("smoke_retopology_baking: ok")
    finally:
        retopology_jobs.unregister()
        preferences.get_preferences = old_preferences
        claude_blender.unregister()
