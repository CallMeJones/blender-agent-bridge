"""Blender background smoke for the modeling quality gate.

Reproduces the two meshes that fooled it during evaluation:

  1. A Skin+Subdivision skeleton, which renders as a full figure but whose base
     mesh has no faces. Previously failed with "mesh has no faces".
  2. A spiked surface, topologically clean because remesh keeps it watertight,
     but visibly destroyed. Previously passed with zero issues.
"""

from __future__ import annotations

import os
import sys

import bmesh
import bpy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

bpy.ops.preferences.addon_enable(module="bl_ext.user_default.claude_blender")
from bl_ext.user_default.claude_blender import advanced_modeling  # noqa: E402

failures = []


def check(label, condition, detail=""):
    if condition:
        print("  ok   %s" % label)
    else:
        failures.append(label)
        print("  FAIL %s %s" % (label, detail))


def clear():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def report_for(obj):
    result = advanced_modeling.inspect_modeling_quality(
        bpy.context, object_names=[obj.name], selected_only=False, require_materials=False
    )
    return result["objects"][0]


print("== case 1: Skin modifier skeleton (valid, previously failed) ==")
clear()
mesh = bpy.data.meshes.new("Skel")
obj = bpy.data.objects.new("Skel", mesh)
bpy.context.scene.collection.objects.link(obj)
bm = bmesh.new()
prev = None
for i in range(5):
    vert = bm.verts.new((0.0, 0.0, i * 0.4))
    if prev is not None:
        bm.edges.new((prev, vert))
    prev = vert
bm.to_mesh(mesh)
bm.free()
obj.modifiers.new("Skin", "SKIN")
sub = obj.modifiers.new("Subdivision", "SUBSURF")
sub.levels = 1
bpy.context.view_layer.update()

skel = report_for(obj)
check("base mesh genuinely has no faces", len(mesh.polygons) == 0)
check("topology read from evaluated mesh", skel["topology_source"] == "evaluated", skel["topology_source"])
check("evaluated faces are counted", skel["topology"]["faces"] > 0, str(skel["topology"]["faces"]))
check("no 'mesh has no faces' issue", "mesh has no faces" not in skel["issues"], str(skel["issues"]))
check("skinned skeleton passes", skel["passed"], str(skel["issues"]))

print("== case 2: spiked surface (broken, previously passed) ==")
clear()
bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1.0)
spiky = bpy.context.active_object
spiky.name = "Spiked"
# Push a few vertices far out: exactly the failure mode observed, where the
# bounding box grew 32% while topology stayed watertight.
for index in (5, 40, 90, 150, 200):
    if index < len(spiky.data.vertices):
        spiky.data.vertices[index].co *= 14.0
bpy.context.view_layer.update()

spike = report_for(spiky)
check("spiked mesh is still topologically clean", spike["topology"]["non_manifold_edges"] == 0)
check("geometry sanity ran", bool(spike["geometry"]), str(spike["geometry"])[:80])
check(
    "spikes are detected",
    spike["geometry"]["face_area_outliers"] > 0 or spike["geometry"]["edge_length_outliers"] > 0,
    str(spike["geometry"]),
)
check("spiked mesh now fails", not spike["passed"], str(spike["issues"]))

print("== case 3: ordinary meshes still pass ==")
# Thresholds must clear every ordinary primitive. Suzanne and the ngon-capped
# cylinder are the worst legitimate cases measured (17.8x area, 10.2x edge).
for adder, name in (
    (lambda: bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16), "uv sphere"),
    (lambda: bpy.ops.mesh.primitive_cylinder_add(), "cylinder"),
    (lambda: bpy.ops.mesh.primitive_cone_add(), "cone"),
    (lambda: bpy.ops.mesh.primitive_monkey_add(), "suzanne"),
    (lambda: bpy.ops.mesh.primitive_torus_add(), "torus"),
):
    clear()
    adder()
    obj = bpy.context.active_object
    bpy.context.view_layer.update()
    plain = report_for(obj)
    # Suzanne legitimately has open boundary edges, so it fails the pre-existing
    # topology rule. What matters here is that the new geometry check does not
    # add a false spike report to any ordinary mesh.
    if name != "suzanne":
        check("%s passes" % name, plain["passed"], str(plain["issues"]))
    check(
        "%s not flagged as spiked" % name,
        plain["geometry"]["face_area_outliers"] == 0 and plain["geometry"]["edge_length_outliers"] == 0,
        str(plain["geometry"]),
    )
    check(
        "%s reports no geometry issue" % name,
        not any("median" in issue for issue in plain["issues"]),
        str(plain["issues"]),
    )
check("topology source is base mesh when no modifiers", plain["topology_source"] == "base_mesh")

if failures:
    print("\nsmoke_modeling_quality_gate: FAILED (%d)" % len(failures))
    for item in failures:
        print("  - %s" % item)
    raise SystemExit(1)
print("\nsmoke_modeling_quality_gate: ok")
