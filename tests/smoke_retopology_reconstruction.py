"""Portable authored example, three prop forms and local-feature rejection.

This checks executable resources and bridge diagnostics, not an automatic
semantic reconstruction algorithm or an agent's artistic judgement.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon"))
import claude_blender
from claude_blender import tool_dispatcher

EXAMPLE = ROOT / "skills/blender-retopology/scripts/pump_study.py"


def call(name, args=None):
    result = json.loads(tool_dispatcher.execute_tool(bpy.context, name, args or {}))
    assert result["ok"], result
    return result


def fingerprint(obj):
    # Names/coordinates survive fresh reload; datablock pointers do not.
    payload = {
        "vertices": [tuple(v.co) for v in obj.data.vertices],
        "faces": [tuple(p.vertices) for p in obj.data.polygons],
        "matrix": [tuple(row) for row in obj.matrix_world],
        "uvs": [[tuple(loop.uv) for loop in layer.data] for layer in obj.data.uv_layers],
        "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def triangles(obj):
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def closed_part(obj):
    assert all(math.isfinite(c) for v in obj.data.vertices for c in v.co), obj.name
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        assert bm.faces and all(e.is_manifold for e in bm.edges), obj.name
        assert all(f.calc_area() > 1e-12 for f in bm.faces), obj.name
        assert bm.calc_volume(signed=True) > 1e-9, obj.name
    finally:
        bm.free()


def bore_open(obj):
    graph = bpy.context.evaluated_depsgraph_get()
    mesh = obj.evaluated_get(graph).data
    tree = BVHTree.FromPolygons([obj.matrix_world @ v.co for v in mesh.vertices],
                               [tuple(p.vertices) for p in mesh.polygons])
    # This fixture declares a Z-axis bore at the origin; this is not a generic detector.
    return tree.ray_cast(Vector((0, 0, -1)), Vector((0, 0, 1)), 2)[0] is None


def unwrap(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    try:
        bpy.ops.uv.smart_project(island_margin=.01)
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    assert obj.data.uv_layers.active
    assert all(math.isfinite(c) and -1e-6 <= c <= 1.000001
               for loop in obj.data.uv_layers.active.data for c in loop.uv)


def dense_panels(obj):
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=12, use_grid_fill=True)
        bmesh.ops.triangulate(bm, faces=list(bm.faces))
        bm.to_mesh(obj.data)
    finally:
        bm.free()
    obj.data.update()


def run(directory):
    directory.mkdir(parents=True, exist_ok=True)
    ns = runpy.run_path(str(EXAMPLE), run_name="pump_example_fixture")
    # Importing the example must not create scene data.
    assert bpy.data.collections.get(ns["COLLECTION"]) is None
    original_meshes = {o.name: fingerprint(o) for o in bpy.context.scene.objects if o.type == "MESH"}
    preview, parts = ns["build"]()
    parts = list(parts)
    assert all(fingerprint(bpy.data.objects[name]) == value for name, value in original_meshes.items())
    assert len(parts) == 110 and len({p.name for p in parts}) == 110
    assert triangles(preview) == 8468
    quad_fraction = sum(len(p.vertices) == 4 for p in preview.data.polygons) / len(preview.data.polygons)
    assert quad_fraction > .90
    for obj in parts:
        closed_part(obj)
        assert not obj.modifiers and obj.get("human_topology_part"), obj.name
        if "base " in obj.name:
            assert len(obj.data.polygons) <= 30
    bpy.context.view_layer.update()
    expected_dimensions = (.7294789, 1, .7890983)
    assert all(abs(d / e - 1) < .05 for d, e in zip(preview.dimensions, expected_dimensions))
    before_repeat = {kind: set(getattr(bpy.data, kind).keys())
                     for kind in ("objects", "meshes", "materials", "collections")}
    try:
        ns["build"]()
        raise AssertionError("Example accepted a duplicate build")
    except ValueError as error:
        assert "already exists" in str(error), error
    assert all(set(getattr(bpy.data, kind).keys()) == names for kind, names in before_repeat.items())

    fixture = bpy.data.collections.new("Unrelated topology fixtures")
    bpy.context.scene.collection.children.link(fixture)
    globals_ = ns["mesh_part"].__globals__
    globals_["COL"] = fixture
    sources, candidates = [], []
    for label in ("source", "candidate"):
        enclosure = ns["box"]("enclosure " + label, (3, 0, 0), (2, 1.2, .6), "silver", bevel=0)
        if label == "source":
            dense_panels(enclosure)
        flange = ns["ring"]("flange " + label, 0, 1, .975, .04, "silver",
                             segments=256 if label == "source" else 32, axis="Z", center=(0, 0))
        n = 64 if label == "source" else 16
        path = [(6 + math.cos(math.pi * i / n), 0, math.sin(math.pi * i / n)) for i in range(n + 1)]
        handle = ns["sweep"]("handle " + label, path,
                             ns["circle_section"](.08, 32 if label == "source" else 12),
                             "rubber", reference=(0, 1, 0))
        (sources if label == "source" else candidates).extend((enclosure, flange, handle))

    for obj in sources:
        unwrap(obj)
    source_fingerprints = {o.name: fingerprint(o) for o in sources}
    baseline = {kind: set(getattr(bpy.data, kind).keys()) for kind in ("objects", "meshes", "materials")}
    inspection = call("inspect_retopology_source", {"object_names": [o.name for o in sources]})
    assert len(inspection["sources"]) == 3
    prepared = call("prepare_retopology_copy", {"object_names": [o.name for o in sources]})
    for original, item in zip(sources, prepared["copies"]):
        copy = bpy.data.objects[item["working_copy"]]
        assert copy.data is not original.data
        assert copy.data.materials[0] is not original.data.materials[0]
    call("revert_preview")
    assert all(set(getattr(bpy.data, kind).keys()) == names for kind, names in baseline.items())

    reports = []
    for source, target in zip(sources, candidates):
        closed_part(target)
        unwrap(target)
        assert triangles(target) < triangles(source) / 4
        result = call("evaluate_retopology_result", {"source_object_name": source.name,
                     "target_object_name": target.name, "sample_count": 4096})
        assert result["comparison"]["shape_passed"], result
        reports.append({"source": source.name, "candidate": target.name,
                        "source_triangles": triangles(source), "candidate_triangles": triangles(target),
                        "comparison": result["comparison"]})
    assert len(candidates[0].data.polygons) == 6
    assert bore_open(sources[1]) and bore_open(candidates[1])
    # A tiny but essential bore can be lost while the global 2% gate still passes.
    capped = ns["axial"]("flange deliberately capped", [(-.02, 1), (.02, 1)], "silver",
                          segments=32, axis="Z", center=(0, 0))
    bad = call("evaluate_retopology_result", {"source_object_name": sources[1].name,
               "target_object_name": capped.name, "sample_count": 4096})
    assert bad["comparison"]["shape_passed"], bad
    assert not bore_open(capped)
    character = call("evaluate_retopology_result", {"source_object_name": sources[2].name,
                     "target_object_name": candidates[2].name, "intended_use": "character"})
    assert character["comparison"]["shape_passed"] and not character["animation_ready"]
    assert any("joint and facial" in finding for finding in character["findings"])
    assert all(fingerprint(bpy.data.objects[name]) == value for name, value in source_fingerprints.items())

    unwrap(preview)
    offset = 0
    for part in parts:
        uv = part.data.uv_layers.new(name="StudyAtlas")
        for i, loop in enumerate(uv.data):
            loop.uv = preview.data.uv_layers.active.data[offset + i].uv
        offset += len(uv.data)
    assert offset == len(preview.data.uv_layers.active.data)
    # Export named parts; exclude their assembled review copy and all source objects.
    exported = parts + candidates
    bpy.ops.object.select_all(action="DESELECT")
    for obj in exported:
        obj.select_set(True)
    expected_export_triangles = sum(triangles(obj) for obj in exported)
    glb = directory / "reconstruction-fixtures.glb"
    blend = directory / "reconstruction-fixtures.blend"
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", use_selection=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    expected = {"sources": source_fingerprints, "parts": [p.name for p in parts],
                "candidate_names": [o.name for o in candidates],
                "exported_triangles": expected_export_triangles}
    (directory / "expected.json").write_text(json.dumps(expected), encoding="utf-8")
    # Fresh process proves saved-scene loading and real export/import, without changing live Blender.
    verifier = directory / "reload_fixture.py"
    verifier.write_text(
        "import bpy, json, runpy\nfrom pathlib import Path\n"
        f"ns=runpy.run_path({str(Path(__file__).resolve())!r}, run_name='reload_helpers')\n"
        f"directory=Path({str(directory)!r})\n"
        "expected=json.loads((directory/'expected.json').read_text())\n"
        "for name,value in expected['sources'].items():\n"
        "    assert ns['fingerprint'](bpy.data.objects[name]) == value, name\n"
        "for name in expected['parts']+expected['candidate_names']:\n"
        "    obj=bpy.data.objects[name]\n"
        "    ns['closed_part'](obj)\n"
        "    assert obj.data.uv_layers.active, name\n"
        "assert ns['bore_open'](bpy.data.objects[expected['candidate_names'][1]])\n"
        "bpy.ops.wm.read_factory_settings(use_empty=True)\n"
        "bpy.ops.import_scene.gltf(filepath=str(directory/'reconstruction-fixtures.glb'))\n"
        "meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']\n"
        "assert len(meshes)==len(expected['parts'])+3, len(meshes)\n"
        "assert sum(ns['triangles'](o) for o in meshes)==expected['exported_triangles']\n"
        "assert all(o.data.uv_layers.active for o in meshes)\n"
        "assert ns['bore_open'](bpy.data.objects[expected['candidate_names'][1]])\n"
        "print('reconstruction_fresh_reload: ok')\n", encoding="utf-8")
    process = subprocess.run([bpy.app.binary_path, str(blend), "--background", "--python-exit-code", "1",
                              "--python", str(verifier)], capture_output=True, text=True, timeout=120)
    assert process.returncode == 0 and "reconstruction_fresh_reload: ok" in process.stdout, process.stdout + process.stderr
    report = {"ok": True, "pump_parts": len(parts), "pump_triangles": triangles(preview),
              "pump_quad_fraction": quad_fraction, "props": reports, "source_preserved": True,
              "local_bore_check_rejected_global_false_positive": True, "animation_ready": False,
              "exported_triangles": expected_export_triangles, "fresh_reload_passed": True}
    (directory / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    claude_blender.register()
    try:
        if args.output_dir:
            run(args.output_dir.resolve())
        else:
            with tempfile.TemporaryDirectory(prefix="bab-topology-study-") as directory:
                run(Path(directory))
        print("smoke_retopology_reconstruction: ok")
    finally:
        claude_blender.unregister()
