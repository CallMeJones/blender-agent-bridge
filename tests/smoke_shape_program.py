"""Blender background smoke for implicit shape-program tools."""

from __future__ import annotations

from collections import Counter
import json
import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import shape_program_scene, tool_dispatcher  # noqa: E402


def _execute(context, name, args=None, *, expect_ok=True):
    result = json.loads(tool_dispatcher.execute_tool(context, name, args or {}))
    if expect_ok:
        assert result.get("ok"), f"{name} failed: {result}"
    else:
        assert not result.get("ok"), f"{name} unexpectedly succeeded: {result}"
    return result


def _kitten_program(head_width=1.0):
    return {
        "schema_version": 1,
        "name": "Cartoon Kitten Latent",
        "bounds": {"min": [-2.0, -1.6, -1.5], "max": [2.1, 1.6, 2.8]},
        "nodes": [
            {
                "id": "body",
                "type": "ellipsoid",
                "semantic_role": "body",
                "radii": [0.72, 0.58, 1.0],
            },
            {
                "id": "head",
                "type": "ellipsoid",
                "semantic_role": "head",
                "radii": [head_width, 0.7, 0.82],
                "blend": 0.28,
                "transform": {"location": [0.0, 0.0, 1.35]},
            },
            {
                "id": "muzzle",
                "parent_id": "head",
                "type": "ellipsoid",
                "semantic_role": "muzzle",
                "radii": [0.48, 0.26, 0.28],
                "blend": 0.16,
                "transform": {"location": [0.0, -0.58, -0.12]},
            },
            {
                "id": "left_ear",
                "parent_id": "head",
                "type": "superquadric",
                "semantic_role": "ear",
                "radii": [0.32, 0.24, 0.58],
                "exponents": [0.45, 0.8],
                "blend": 0.1,
                "transform": {
                    "location": [-0.58, 0.0, 0.62],
                    "rotation": [0.0, -0.18, 0.0],
                },
            },
            {
                "id": "right_ear",
                "parent_id": "head",
                "type": "superquadric",
                "semantic_role": "ear",
                "radii": [0.32, 0.24, 0.58],
                "exponents": [0.45, 0.8],
                "blend": 0.1,
                "transform": {
                    "location": [0.58, 0.0, 0.62],
                    "rotation": [0.0, 0.18, 0.0],
                },
            },
            {
                "id": "tail",
                "type": "sweep",
                "semantic_role": "tail",
                "points": [
                    [0.55, 0.05, -0.55],
                    [1.05, 0.08, -0.3],
                    [1.28, 0.06, 0.2],
                    [1.05, 0.03, 0.68],
                ],
                "radii": [0.24, 0.21, 0.16, 0.08],
                "blend": 0.18,
            },
        ],
    }


def _coordinates(obj):
    return tuple(tuple(float(value) for value in vertex.co) for vertex in obj.data.vertices)


def _assert_closed(obj):
    edge_use = Counter()
    edge_directions = Counter()
    for polygon in obj.data.polygons:
        for index, first in enumerate(polygon.vertices):
            second = polygon.vertices[(index + 1) % len(polygon.vertices)]
            edge = tuple(sorted((first, second)))
            edge_use[edge] += 1
            edge_directions[edge] += 1 if (first, second) == edge else -1
    assert edge_use and all(count == 2 for count in edge_use.values()), Counter(
        edge_use.values()
    )
    assert all(balance == 0 for balance in edge_directions.values()), Counter(
        edge_directions.values()
    )


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    claude_blender.register()
    context = bpy.context
    try:
        program = _kitten_program()
        sampled = _execute(
            context,
            "sample_shape_program_sdf",
            {"program": program, "points": [[0, 0, 0], [1.9, 1.4, 2.6]]},
        )
        assert sampled["samples"][0]["inside"] is True, sampled
        assert sampled["samples"][1]["inside"] is False, sampled

        compiled = _execute(
            context,
            "compile_shape_program",
            {
                "program": program,
                "object_name": "Shape Program Kitten",
                "resolution": 22,
                "smooth_iterations": 1,
            },
        )
        obj = bpy.data.objects[compiled["object"]]
        assert obj.get(shape_program_scene.PROGRAM_FLAG_PROP) is True
        assert obj.get(shape_program_scene.PROGRAM_DIGEST_PROP) == compiled["stats"]["digest"]
        assert len(obj.data.vertices) == compiled["stats"]["vertex_count"]
        _assert_closed(obj)
        original_coordinates = _coordinates(obj)
        original_digest = str(obj[shape_program_scene.PROGRAM_DIGEST_PROP])

        inspected = _execute(
            context,
            "inspect_shape_program",
            {"object_name": obj.name, "include_program": True},
        )
        assert inspected["program_summary"]["node_count"] == 6, inspected
        assert inspected["program"]["nodes"][1]["id"] == "head", inspected
        assert not inspected["warnings"], inspected

        _execute(context, "commit_preview")
        group = obj.vertex_groups.new(name="Topology Dependent")
        group.add([0], 0.75, "REPLACE")
        updated = _execute(
            context,
            "update_shape_program",
            {
                "object_name": obj.name,
                "program": _kitten_program(head_width=1.12),
                "resolution": 22,
                "smooth_iterations": 1,
            },
        )
        assert updated["previous_digest"] == original_digest, updated
        assert updated["stats"]["digest"] != original_digest, updated
        assert not list(obj.vertex_groups), updated
        assert _coordinates(obj) != original_coordinates
        _assert_closed(obj)

        _execute(context, "revert_preview")
        assert str(obj[shape_program_scene.PROGRAM_DIGEST_PROP]) == original_digest
        assert _coordinates(obj) == original_coordinates
        assert list(obj.vertex_groups.keys()) == ["Topology Dependent"]
        assert abs(obj.vertex_groups["Topology Dependent"].weight(0) - 0.75) < 1.0e-6

        uniform_refusal = _execute(
            context,
            "compile_shape_program",
            {
                "program": program,
                "refinement_regions": [
                    {
                        "name": "head",
                        "type": "sphere",
                        "center": [0, 0, 1.35],
                        "radius": 1.0,
                        "depth": 5,
                    }
                ],
            },
            expect_ok=False,
        )
        assert "adaptive_dual" in uniform_refusal["message"], uniform_refusal

        adaptive = _execute(
            context,
            "compile_shape_program",
            {
                "program": program,
                "object_name": "Adaptive Shape Program Kitten",
                "meshing_mode": "adaptive_dual",
                "adaptive_base_depth": 3,
                "adaptive_max_depth": 5,
                "adaptive_error_threshold": 0.15,
                "refinement_regions": [
                    {
                        "name": "head",
                        "type": "sphere",
                        "center": [0, 0, 1.35],
                        "radius": 1.0,
                        "depth": 5,
                    }
                ],
                "smooth_iterations": 0,
            },
        )
        adaptive_name = adaptive["object"]
        adaptive_obj = bpy.data.objects[adaptive_name]
        assert adaptive["stats"]["meshing_mode"] == "adaptive_dual", adaptive
        assert adaptive["stats"]["region_refined_cell_count"] > 0, adaptive
        assert len(adaptive["stats"]["surface_depth_histogram"]) > 1, adaptive
        _assert_closed(adaptive_obj)
        adaptive_inspection = _execute(
            context,
            "inspect_shape_program",
            {"object_name": adaptive_name, "include_program": False},
        )
        assert adaptive_inspection["compile_stats"]["meshing_mode"] == "adaptive_dual"
        _execute(context, "revert_preview")
        assert bpy.data.objects.get(adaptive_name) is None

        linked = obj.copy()
        linked.name = "Linked Shape Program Kitten"
        context.scene.collection.objects.link(linked)
        linked_refusal = _execute(
            context,
            "update_shape_program",
            {"object_name": obj.name, "program": _kitten_program(1.2)},
            expect_ok=False,
        )
        assert "single-user" in linked_refusal["message"], linked_refusal
        assert _coordinates(obj) == original_coordinates
        bpy.data.objects.remove(linked, do_unlink=True)

        context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        mode_refusal = _execute(
            context,
            "update_shape_program",
            {"object_name": obj.name, "program": _kitten_program(1.2)},
            expect_ok=False,
        )
        assert "Object Mode" in mode_refusal["message"], mode_refusal
        bpy.ops.object.mode_set(mode="OBJECT")

        obj.shape_key_add(name="Basis")
        refused = _execute(
            context,
            "update_shape_program",
            {"object_name": obj.name, "program": _kitten_program(1.2)},
            expect_ok=False,
        )
        assert "shape keys" in refused["message"].lower(), refused

        existing_material = bpy.data.materials.new("Existing Shape Program Material")
        existing_material.diffuse_color = (0.8, 0.1, 0.2, 1.0)
        original_material_color = tuple(existing_material.diffuse_color)
        second = _execute(
            context,
            "compile_shape_program",
            {
                "program": {
                    "bounds": {"min": [-1, -1, -1], "max": [1, 1, 1]},
                    "nodes": [{"id": "probe", "type": "sphere", "radius": 0.5}],
                },
                "object_name": "Shape Program Revert Probe",
                "material_name": existing_material.name,
                "color": [0.1, 0.8, 0.2, 1.0],
                "resolution": 12,
                "smooth_iterations": 0,
            },
        )
        second_name = second["object"]
        assert tuple(existing_material.diffuse_color) == original_material_color
        _execute(context, "revert_preview")
        assert bpy.data.objects.get(second_name) is None
        assert bpy.data.materials.get(existing_material.name) is existing_material
    finally:
        try:
            claude_blender.unregister()
        except Exception:
            pass


if __name__ == "__main__":
    main()
