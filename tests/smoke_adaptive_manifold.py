"""Blender background smoke for manifold adaptive dual contouring.

Pins the behaviour that motivated one-vertex-per-patch. Before it, a cell
holding two surface sheets gave them a shared vertex, four faces met on one
edge, and the compiler refused the mesh. Refinement made it worse rather than
better -- measured 4 pinched edges at max_depth 7, 30 at 8, 84 at 9 -- so a
program that compiled at one depth could fail at a deeper one.
"""

from __future__ import annotations

import os
import sys

import bpy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

bpy.ops.preferences.addon_enable(module="bl_ext.user_default.claude_blender")
from bl_ext.user_default.claude_blender import shape_program as sp  # noqa: E402
from bl_ext.user_default.claude_blender import shape_program_adaptive as spa  # noqa: E402

failures = []


def check(label, condition, detail=""):
    if condition:
        print("  ok   %s" % label)
    else:
        failures.append(label)
        print("  FAIL %s %s" % (label, detail))


def bounds():
    return {"min": [-1.2, -1.2, -1.2], "max": [1.2, 1.2, 1.4]}


BODY = {"id": "body", "type": "ellipsoid", "radii": [0.62, 0.55, 0.60], "operation": "union"}


def program(*nodes):
    return {"schema_version": 1, "bounds": bounds(), "nodes": [BODY, *nodes]}


BREAKS_THROUGH = program(
    {"id": "hole", "type": "sphere", "radius": 0.30, "operation": "subtract",
     "transform": {"location": [0.0, -0.40, 0.0]}}
)
ENCLOSED = program(
    {"id": "hole", "type": "sphere", "radius": 0.20, "operation": "subtract",
     "transform": {"location": [0.0, 0.0, 0.0]}}
)
CLEAN_BREAK = program(
    {"id": "hole", "type": "sphere", "radius": 0.35, "operation": "subtract",
     "transform": {"location": [0.0, -0.75, 0.0]}}
)
UNION_ONLY = program(
    {"id": "head", "type": "sphere", "radius": 0.42, "operation": "union", "blend": 0.12,
     "transform": {"location": [0.0, -0.18, 0.72]}}
)

SWEEP_CAVITY = {
    "schema_version": 1,
    "name": "F14 sweep cavity",
    "bounds": {"min": [-6.9, -6.4, -6.5], "max": [8.3, 6.4, 6.3]},
    "nodes": [
        {
            "id": "shade",
            "type": "sweep",
            "points": [[0.0, 0.0, 0.0], [0.35, 0.0, 0.15],
                       [0.75, 0.0, 0.10], [1.25, 0.0, -0.20]],
            "radii": [0.34, 0.48, 0.70, 0.95],
            "operation": "union",
        },
        {
            "id": "cavity",
            "type": "sweep",
            "points": [[0.08, 0.06, 0.0], [0.42, 0.06, 0.14],
                       [0.82, 0.06, 0.07], [1.20, 0.06, -0.22]],
            "radii": [0.16, 0.32, 0.62, 0.58],
            "operation": "subtract",
        },
    ],
}


def compile_program(label, spec, base_depth, max_depth):
    try:
        result = spa.mesh_shape_program_adaptive(
            spec, base_depth=base_depth, max_depth=max_depth, error_threshold=0.05
        )
    except Exception as error:  # noqa: BLE001
        return None, str(error)
    faces = result.get("faces") or []
    counts, balance = spa._mesh_edge_usage(faces)
    bad = [edge for edge, count in counts.items() if count != 2 or balance[edge] != 0]
    return {"faces": faces, "bad": bad, "stats": result.get("stats") or {}}, ""


print("== a subtract cavity breaking through the surface ==")
for depth in (7, 8, 9):
    outcome, error = compile_program("breaks through", BREAKS_THROUGH, 4, depth)
    check("compiles at max_depth %d" % depth, outcome is not None, error[:70])
    if outcome:
        check("  manifold at max_depth %d" % depth, not outcome["bad"], str(outcome["bad"][:3]))

print("== refinement must not introduce pinches ==")
# This is the regression that proved the cause was topological: the program
# compiled at depth 7 and failed at depth 9.
shallow, _ = compile_program("clean break", CLEAN_BREAK, 4, 7)
deep, deep_error = compile_program("clean break", CLEAN_BREAK, 4, 9)
check("clean break compiles shallow", shallow is not None)
check("clean break compiles deep", deep is not None, deep_error[:70])
if deep:
    check("deeper refinement stays manifold", not deep["bad"], str(deep["bad"][:3]))
if shallow and deep:
    check("deeper refinement adds detail", len(deep["faces"]) > len(shallow["faces"]))

print("== multi-point sweep cavity across cell boundaries ==")
for depth in (7, 8, 9):
    outcome, error = compile_program("sweep cavity", SWEEP_CAVITY, 4, depth)
    check("sweep cavity compiles at max_depth %d" % depth, outcome is not None, error[:70])
    if outcome:
        check("  sweep cavity is manifold at max_depth %d" % depth,
              not outcome["bad"], str(outcome["bad"][:3]))
        check("  sweep cavity stays connected at max_depth %d" % depth,
              outcome["stats"].get("component_count") == 1,
              str(outcome["stats"].get("component_count")))
        if depth == 7:
            check("  depth 7 exercises cross-cell fan splitting",
                  outcome["stats"].get("topology_split_vertex_count", 0) > 0,
                  str(outcome["stats"].get("topology_split_vertex_count")))

uniform_cavity = sp.mesh_shape_program(SWEEP_CAVITY, resolution=64, smooth_iterations=0)
uniform_counts, uniform_balance = spa._mesh_edge_usage(uniform_cavity["faces"])
uniform_bad = [
    edge for edge, count in uniform_counts.items()
    if count != 2 or uniform_balance[edge] != 0
]
check("uniform sweep cavity is manifold", not uniform_bad, str(uniform_bad[:3]))
check("uniform sweep cavity is also connected",
      uniform_cavity["stats"].get("component_count") == 1,
      str(uniform_cavity["stats"].get("component_count")))

print("== unchanged behaviour ==")
enclosed_shallow, _ = compile_program("enclosed", ENCLOSED, 4, 7)
enclosed_deep, _ = compile_program("enclosed", ENCLOSED, 4, 9)
check("enclosed cavity still compiles", enclosed_shallow is not None)
check("enclosed cavity is manifold", enclosed_shallow and not enclosed_shallow["bad"])
check(
    "enclosed cavity is stable across depth",
    enclosed_shallow and enclosed_deep
    and len(enclosed_shallow["faces"]) == len(enclosed_deep["faces"]),
)

union, union_error = compile_program("union only", UNION_ONLY, 4, 7)
check("union-only program still compiles", union is not None, union_error[:70])
check("union-only program is manifold", union and not union["bad"])

print("== component detection is wired in ==")
# Two body-diagonal corners share no face, so the cell holds two patches.
components = spa.cell_surface_components(
    [-1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, 1.0], 0.0
)
check("opposite corners give two patches", len(components) == 2, str(components))

if failures:
    print("\nsmoke_adaptive_manifold: FAILED (%d)" % len(failures))
    for item in failures:
        print("  - %s" % item)
    raise SystemExit(1)
print("\nsmoke_adaptive_manifold: ok")
