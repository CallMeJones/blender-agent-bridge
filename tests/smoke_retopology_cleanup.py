"""Source preservation, conservative cleanup, independent materials and rollback."""
import json
from pathlib import Path
import sys
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))
import claude_blender
from claude_blender import blender_compat, live_preview, retopology, tool_dispatcher


def call(name, args=None):
    return json.loads(tool_dispatcher.execute_tool(bpy.context, name, args or {}))


def identity(obj):
    return ([tuple(v.co) for v in obj.data.vertices], [tuple(f.vertices) for f in obj.data.polygons],
            [m.name for m in obj.data.materials], [tuple(loop.uv) for uv in obj.data.uv_layers for loop in uv.data])


claude_blender.register()
try:
    source = bpy.data.objects["Cube"]
    mat = bpy.data.materials.new("Retopology source material")
    blender_compat.ensure_node_tree(mat)
    source.data.materials.clear()
    source.data.materials.append(mat)
    original = identity(source)
    baseline = {kind: set(getattr(bpy.data, kind).keys()) for kind in ("objects", "meshes", "materials")}
    inspected = call("inspect_retopology_source", {"object_names": [source.name]})
    assert inspected["ok"], inspected
    assert inspected["sources"][0]["geometry"]["quads"] == 6
    assert live_preview.current_transaction() is None
    prepared = call("prepare_retopology_copy", {"object_names": [source.name]})
    assert prepared["ok"], prepared
    copy = bpy.data.objects[prepared["copies"][0]["working_copy"]]
    assert copy.data is not source.data
    assert copy.data.materials[0] is not mat
    assert identity(source) == original
    compared = call("evaluate_retopology_result", {"source_object_name": source.name, "target_object_name": copy.name,
                                                     "intended_use": "character"})
    assert compared["ok"] and compared["comparison"]["shape_passed"], compared
    assert compared["comparison"]["max_distance"] < 1e-6
    assert not compared["animation_ready"]
    same = call("evaluate_retopology_result", {"source_object_name": source.name, "target_object_name": source.name})
    assert not same["ok"] and "distinct" in same["message"], same
    copy.location.x += 10
    bpy.context.view_layer.update()
    compared = call("evaluate_retopology_result", {"source_object_name": source.name, "target_object_name": copy.name})
    assert not compared["comparison"]["shape_passed"], compared
    assert call("revert_preview")["ok"]
    for kind, names in baseline.items():
        assert set(getattr(bpy.data, kind).keys()) == names, (kind, names, set(getattr(bpy.data, kind).keys()))
    cleaner = retopology.clean_mesh
    def fail(*args, **kwargs):
        cleaner(*args, **kwargs)
        raise RuntimeError("injected cleanup failure")
    retopology.clean_mesh = fail
    try:
        failed = call("prepare_retopology_copy", {"object_names": [source.name]})
        assert not failed["ok"] and failed["auto_reverted_preview"], failed
    finally:
        retopology.clean_mesh = cleaner
    assert identity(source) == original
    for kind, names in baseline.items():
        assert set(getattr(bpy.data, kind).keys()) == names, kind
    override = bpy.data.materials.new("Object material override")
    source.material_slots[0].link = "OBJECT"
    source.material_slots[0].material = override
    prepared = call("prepare_retopology_copy", {"object_names": [source.name]})
    assert prepared["ok"], prepared
    copy = bpy.data.objects[prepared["copies"][0]["working_copy"]]
    assert copy.data.materials[0].name.startswith(override.name)
    assert source.material_slots[0].material == override and source.data.materials[0] == mat
    assert call("revert_preview")["ok"]
    source.material_slots[0].link = "DATA"
    bpy.data.materials.remove(override)
    subdivision = source.modifiers.new("Evaluated topology fixture", "SUBSURF")
    subdivision.levels = 1
    prepared = call("prepare_retopology_copy", {"object_names": [source.name]})
    assert prepared["ok"], prepared
    copy = bpy.data.objects[prepared["copies"][0]["working_copy"]]
    compared = call("evaluate_retopology_result", {"source_object_name": source.name, "target_object_name": copy.name})
    assert compared["ok"] and compared["comparison"]["shape_passed"], compared
    assert compared["comparison"]["face_reduction_ratio"] == 0, compared
    assert call("revert_preview")["ok"]
    source.modifiers.remove(subdivision)
    mesh = bpy.data.meshes.new("Disconnected fixture")
    mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0),(10,0,0),(11,0,0),(10,1,0),(99,99,99)], [], [(0,1,2),(3,4,5)])
    report = retopology.clean_mesh(mesh)
    assert report["after"] == {"vertices": 6, "faces": 2}, report
    assert report["removed_components"] == 0
    report = retopology.clean_mesh(mesh, min_component_faces=2)
    assert report["after"]["faces"] == 1 and report["removed_components"] == 1, report
    bpy.data.meshes.remove(mesh)
    # Character copies capture the evaluated pose without copying or removing shape keys.
    source.shape_key_add(name="Basis")
    morph = source.shape_key_add(name="Fixture morph")
    morph.data[0].co.x += .5
    morph.value = 1
    bpy.context.view_layer.update()
    prepared = call("prepare_retopology_copy", {"object_names": [source.name]})
    assert prepared["ok"], prepared
    copy = bpy.data.objects[prepared["copies"][0]["working_copy"]]
    assert copy.data.shape_keys is None and source.data.shape_keys is not None
    assert abs(copy.data.vertices[0].co.x - morph.data[0].co.x) < 1e-6
    assert call("revert_preview")["ok"]
    assert source.data.shape_keys.key_blocks["Fixture morph"].value == 1
    print("smoke_retopology_cleanup: ok")
finally:
    claude_blender.unregister()
