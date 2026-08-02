"""Blender background smoke test for semantic and screen-space sculpt tools."""

from __future__ import annotations

import json
import math
import os
import sys

import bpy
from mathutils import Vector


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import (  # noqa: E402
    live_preview,
    reference_comparison,
    reference_scene,
    tool_dispatcher,
)


def _execute(context, name, args=None, *, expect_ok=True):
    result = json.loads(tool_dispatcher.execute_tool(context, name, args or {}))
    if expect_ok:
        assert result.get("ok"), f"{name} failed: {result}"
    else:
        assert not result.get("ok"), f"{name} unexpectedly succeeded: {result}"
    return result


def _coordinates(obj):
    return tuple(tuple(float(value) for value in vertex.co) for vertex in obj.data.vertices)


def _assert_coordinates_close(actual, expected, tolerance=1e-6):
    assert len(actual) == len(expected)
    for actual_point, expected_point in zip(actual, expected):
        assert max(
            abs(actual_value - expected_value)
            for actual_value, expected_value in zip(actual_point, expected_point)
        ) <= tolerance, (actual_point, expected_point)


def _create_fixture(context):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=24,
        ring_count=12,
        radius=1.0,
        location=(0.0, 0.0, 0.0),
    )
    obj = context.active_object
    obj.name = "Semantic Sculpt Subject"

    collection = bpy.data.collections.new("Semantic Sculpt Guides")
    collection["reference_modeling_guides"] = True
    context.scene.collection.children.link(collection)

    camera_data = bpy.data.cameras.new("Semantic Sculpt Camera Data")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 4.0
    camera = bpy.data.objects.new("Semantic Sculpt Camera", camera_data)
    camera.location = (0.0, -6.0, 0.0)
    camera.rotation_euler = ((Vector((0.0, 0.0, 0.0)) - camera.location).to_track_quat("-Z", "Y").to_euler())
    camera["reference_guide_kind"] = "camera"
    camera["reference_guide_metadata_json"] = json.dumps(
        {
            "camera_type": "ORTHO",
            "ortho_scale": 4.0,
            "target": [0.0, 0.0, 0.0],
            "margin": 0.0,
            "active": True,
        }
    )
    collection.objects.link(camera)
    context.scene.camera = camera
    context.scene.render.resolution_x = 640
    context.scene.render.resolution_y = 480
    context.scene.render.resolution_percentage = 100
    return obj, collection, camera


def _screen_arguments(context, obj, collection, camera):
    probe_index = max(
        range(len(obj.data.vertices)),
        key=lambda index: float(obj.data.vertices[index].co.x),
    )
    probe_world = obj.matrix_world @ obj.data.vertices[probe_index].co
    source = reference_scene.project_point(context.scene, camera, probe_world)
    arguments = {
        "object_name": obj.name,
        "collection_name": collection.name,
        "camera_name": camera.name,
        "region_names": ["right side"],
        "controls": [
            {
                "source": source,
                "target": [source[0] + 0.05, source[1]],
                "radius": 0.35,
                "strength": 1.0,
            }
        ],
        "front_faces_only": False,
        "maximum_world_displacement": 1.0,
    }
    return arguments, probe_index


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    claude_blender.register()
    context = bpy.context
    try:
        obj, collection, camera = _create_fixture(context)
        unsculpted = _coordinates(obj)

        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(4.0, 0.0, 0.0))
        whole_mesh_probe = context.active_object
        whole_mesh_probe.name = "Whole Mesh Target Probe"
        whole_mesh_result = _execute(
            context,
            "adaptive_remesh",
            {
                "object_name": whole_mesh_probe.name,
                "target_edge_length": 2.1,
                "passes": 1,
                "region_detail": 1.0,
                "curvature_detail": 0.0,
            },
            expect_ok=False,
        )
        assert "No edges exceeded" in whole_mesh_result["message"], whole_mesh_result
        assert len(whole_mesh_probe.data.vertices) == 8
        bpy.data.objects.remove(whole_mesh_probe, do_unlink=True)

        linked = obj.copy()
        linked.name = "Linked Semantic Sculpt Subject"
        context.scene.collection.objects.link(linked)
        linked_failure = _execute(
            context,
            "define_semantic_sculpt_regions",
            {
                "object_name": obj.name,
                "regions": [
                    {
                        "name": "blocked linked region",
                        "selector": {
                            "type": "vertex_indices",
                            "vertex_indices": [0],
                        },
                    }
                ],
            },
            expect_ok=False,
        )
        assert "shared" in linked_failure["message"].lower()
        bpy.data.objects.remove(linked, do_unlink=True)

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(4.0, 0.0, 0.0))
        shape_key_probe = context.active_object
        shape_key_probe.name = "Shape Key Sculpt Probe"
        shape_key_probe.shape_key_add(name="Basis")
        shape_key_probe.shape_key_add(name="Raised")
        shape_key_before = _coordinates(shape_key_probe)
        shape_key_failure = _execute(
            context,
            "apply_semantic_sculpt",
            {
                "object_name": shape_key_probe.name,
                "allow_all_vertices": True,
                "operation": "translate",
                "arguments": {"vector": [0.1, 0.0, 0.0]},
            },
            expect_ok=False,
        )
        assert "shape keys" in shape_key_failure["message"].lower()
        _assert_coordinates_close(_coordinates(shape_key_probe), shape_key_before)
        shape_key_mesh = shape_key_probe.data
        bpy.data.objects.remove(shape_key_probe, do_unlink=True)
        bpy.data.meshes.remove(shape_key_mesh)

        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        mode_failure = _execute(
            context,
            "define_semantic_sculpt_regions",
            {
                "object_name": obj.name,
                "regions": [
                    {
                        "name": "blocked edit region",
                        "selector": {
                            "type": "vertex_indices",
                            "vertex_indices": [0],
                        },
                    }
                ],
            },
            expect_ok=False,
        )
        assert "object mode" in mode_failure["message"].lower()
        bpy.ops.object.mode_set(mode="OBJECT")

        duplicate_failure = _execute(
            context,
            "define_semantic_sculpt_regions",
            {
                "object_name": obj.name,
                "regions": [
                    {
                        "name": "duplicate",
                        "selector": {
                            "type": "vertex_indices",
                            "vertex_indices": [0],
                        },
                    },
                    {
                        "name": "duplicate",
                        "selector": {
                            "type": "vertex_indices",
                            "vertex_indices": [1],
                        },
                    },
                ],
            },
            expect_ok=False,
        )
        assert "more than once" in duplicate_failure["message"]

        heavy_mesh = bpy.data.meshes.new("Selector Limit Mesh")
        heavy_mesh.from_pydata(
            [(float(index), 0.0, 0.0) for index in range(2001)],
            [],
            [],
        )
        heavy_obj = bpy.data.objects.new("Selector Limit Subject", heavy_mesh)
        context.scene.collection.objects.link(heavy_obj)
        selector_limit_failure = _execute(
            context,
            "define_semantic_sculpt_regions",
            {
                "object_name": heavy_obj.name,
                "regions": [
                    {
                        "name": f"region {region_index}",
                        "selectors": [
                            {
                                "type": "vertex_indices",
                                "vertex_indices": [0],
                            }
                            for _selector_index in range(16)
                        ],
                    }
                    for region_index in range(64)
                ],
            },
            expect_ok=False,
        )
        assert "evaluation limit" in selector_limit_failure["message"].lower()
        bpy.data.objects.remove(heavy_obj, do_unlink=True)
        bpy.data.meshes.remove(heavy_mesh)

        polygon_limit_mesh = bpy.data.meshes.new("Polygon Limit Mesh")
        polygon_limit_mesh.from_pydata(
            [(float(index), 0.0, 0.0) for index in range(5000)],
            [],
            [],
        )
        polygon_limit_obj = bpy.data.objects.new(
            "Polygon Limit Subject",
            polygon_limit_mesh,
        )
        context.scene.collection.objects.link(polygon_limit_obj)
        polygon_limit_failure = _execute(
            context,
            "define_semantic_sculpt_regions",
            {
                "object_name": polygon_limit_obj.name,
                "regions": [
                    {
                        "name": "dense outline",
                        "selector": {
                            "type": "screen_polygon",
                            "collection_name": collection.name,
                            "camera_name": camera.name,
                            "points": [
                                [
                                    0.5 + 0.25 * math.cos(2.0 * math.pi * index / 256),
                                    0.5 + 0.25 * math.sin(2.0 * math.pi * index / 256),
                                ]
                                for index in range(256)
                            ],
                            "feather": 0.1,
                        },
                    }
                ],
            },
            expect_ok=False,
        )
        assert "edge-evaluation limit" in polygon_limit_failure["message"].lower()
        bpy.data.objects.remove(polygon_limit_obj, do_unlink=True)
        bpy.data.meshes.remove(polygon_limit_mesh)

        defined = _execute(
            context,
            "define_semantic_sculpt_regions",
            {
                "object_name": obj.name,
                "regions": [
                    {
                        "name": "right side",
                        "selectors": [
                            {
                                "type": "box",
                                "coordinate_space": "local",
                                "minimum": [0.0, -2.0, -2.0],
                                "maximum": [2.0, 2.0, 2.0],
                                "feather": 0.1,
                            }
                        ],
                    }
                ],
            },
        )
        assert defined["regions"][0]["vertex_count"] > 0
        inspected = _execute(
            context,
            "inspect_semantic_sculpt_regions",
            {"object_name": obj.name, "include_weights": True, "max_weights": 4096},
        )
        assert [region["name"] for region in inspected["regions"]] == ["right side"]
        weighted_indices = {
            item["vertex_index"] for item in inspected["regions"][0]["weights"]
        }
        assert weighted_indices
        assert live_preview.commit(context)["ok"]

        region_attribute = inspected["regions"][0]["attribute"]
        deleted = _execute(
            context,
            "define_semantic_sculpt_regions",
            {
                "object_name": obj.name,
                "regions": [{"name": "right side", "write_mode": "delete"}],
            },
        )
        assert [item["name"] for item in deleted["deleted_regions"]] == ["right side"]
        assert obj.data.attributes.get(region_attribute) is None
        assert not _execute(
            context,
            "inspect_semantic_sculpt_regions",
            {"object_name": obj.name},
        )["regions"]
        assert live_preview.revert(context)["ok"]
        assert obj.data.attributes.get(region_attribute) is not None
        assert _execute(
            context,
            "inspect_semantic_sculpt_regions",
            {"object_name": obj.name},
        )["regions"]

        semantic_before = _coordinates(obj)
        semantic = _execute(
            context,
            "apply_semantic_sculpt",
            {
                "object_name": obj.name,
                "region_names": ["right side"],
                "operation": "translate",
                "arguments": {"vector": [0.1, 0.0, 0.0]},
            },
        )
        assert semantic["deformation"]["moved_vertex_count"] > 0
        semantic_after = _coordinates(obj)
        assert any(
            semantic_after[index][0] > semantic_before[index][0]
            for index in weighted_indices
        )

        pending_id = live_preview.current_transaction()["id"]
        failed = _execute(
            context,
            "apply_semantic_sculpt",
            {
                "object_name": obj.name,
                "region_names": ["missing region"],
                "operation": "translate",
                "arguments": {"vector": [1.0, 0.0, 0.0]},
            },
            expect_ok=False,
        )
        assert failed.get("auto_reverted_preview") is False
        assert live_preview.current_transaction()["id"] == pending_id
        _assert_coordinates_close(_coordinates(obj), semantic_after)
        assert live_preview.revert(context)["ok"]
        _assert_coordinates_close(_coordinates(obj), semantic_before)
        assert _execute(
            context,
            "inspect_semantic_sculpt_regions",
            {"object_name": obj.name},
        )["regions"]

        remesh_vertex_count = len(obj.data.vertices)
        remeshed = _execute(
            context,
            "adaptive_remesh",
            {
                "object_name": obj.name,
                "region_names": ["right side"],
                "target_edge_length": 0.18,
                "passes": 1,
                "project_to_source": True,
                "max_result_vertices": 5000,
            },
        )
        assert remeshed["after"]["vertices"] > remesh_vertex_count, remeshed
        assert "right side" in remeshed["semantic_regions_retained"], remeshed
        remeshed_regions = _execute(
            context,
            "inspect_semantic_sculpt_regions",
            {"object_name": obj.name},
        )
        assert remeshed_regions["regions"][0]["vertex_count"] > len(weighted_indices)
        assert live_preview.revert(context)["ok"]
        assert len(obj.data.vertices) == remesh_vertex_count

        form_before = _coordinates(obj)
        form_aware = _execute(
            context,
            "apply_form_aware_sculpt",
            {
                "object_name": obj.name,
                "region_names": ["right side"],
                "operation": "pinch",
                "strength": 0.1,
                "iterations": 2,
                "falloff_steps": 1,
                "maximum_world_displacement": 0.05,
                "feature_preservation": 0.5,
            },
        )
        assert form_aware["deformation"]["moved_vertex_count"] > 0
        assert form_aware["deformation"]["maximum_local_displacement"] <= 0.050001
        assert live_preview.revert(context)["ok"]
        _assert_coordinates_close(_coordinates(obj), form_before)

        capped_before = [vertex.co.copy() for vertex in obj.data.vertices]
        capped_arguments, _capped_probe_index = _screen_arguments(
            context,
            obj,
            collection,
            camera,
        )
        capped_arguments["maximum_world_displacement"] = 0.001
        capped_arguments["preserve_volume"] = 1.0
        capped = _execute(
            context,
            "apply_screen_space_sculpt",
            capped_arguments,
        )
        basis = obj.matrix_world.to_3x3()
        maximum_displacement = max(
            (basis @ (vertex.co - original)).length
            for vertex, original in zip(obj.data.vertices, capped_before)
        )
        assert maximum_displacement <= 0.001001, maximum_displacement
        assert capped["volume"]["applied"] is True
        assert capped["volume"]["post_compensation_limited_vertex_count"] > 0
        assert live_preview.revert(context)["ok"]

        screen_before = _coordinates(obj)
        screen_arguments, probe_index = _screen_arguments(
            context,
            obj,
            collection,
            camera,
        )
        screen = _execute(
            context,
            "apply_screen_space_sculpt",
            screen_arguments,
        )
        assert screen["deformation"]["moved_vertex_count"] > 0
        screen_after = _coordinates(obj)
        assert max(point[0] for point in screen_after) > max(
            point[0] for point in screen_before
        )
        projected_probe = reference_scene.project_point(
            context.scene,
            camera,
            obj.matrix_world @ obj.data.vertices[probe_index].co,
        )
        assert abs(
            projected_probe[0] - screen_arguments["controls"][0]["target"][0]
        ) < 1e-5, (projected_probe, screen_arguments)
        assert live_preview.revert(context)["ok"]
        _assert_coordinates_close(_coordinates(obj), screen_before)

        original_compare = reference_comparison.compare_model_to_reference
        try:
            def constant_compare(_context, **_arguments):
                return {
                    "ok": True,
                    "comparison_id": "constant",
                    "resolution": [100, 100],
                    "metrics": {
                        "silhouette_iou": 0.5,
                        "mean_edge_distance_pixels": 0.0,
                    },
                    "landmark_errors": [],
                }

            reference_comparison.compare_model_to_reference = constant_compare
            unchanged_before = _coordinates(obj)
            unchanged = _execute(
                context,
                "optimize_screen_space_sculpt",
                {
                    **_screen_arguments(context, obj, collection, camera)[0],
                    "strength_candidates": [0.5, 1.0],
                    "minimum_improvement": 0.0001,
                },
            )
            assert unchanged["changed"] is False
            _assert_coordinates_close(_coordinates(obj), unchanged_before)

            verification_call_count = 0

            def regressing_verification(_context, **_arguments):
                nonlocal verification_call_count
                verification_call_count += 1
                iou = {1: 0.5, 2: 0.6, 3: 0.49}[verification_call_count]
                return {
                    "ok": True,
                    "comparison_id": f"verification-{verification_call_count}",
                    "resolution": [100, 100],
                    "metrics": {
                        "silhouette_iou": iou,
                        "mean_edge_distance_pixels": 0.0,
                    },
                    "landmark_errors": [],
                }

            reference_comparison.compare_model_to_reference = regressing_verification
            regressed = _execute(
                context,
                "optimize_screen_space_sculpt",
                {
                    **_screen_arguments(context, obj, collection, camera)[0],
                    "strength_candidates": [1.0],
                    "minimum_improvement": 0.0001,
                },
            )
            assert regressed["changed"] is False
            assert "final verification" in regressed["message"].lower()
            _assert_coordinates_close(_coordinates(obj), unchanged_before)

            baseline_max_x = max(point[0] for point in unchanged_before)

            def improving_compare(_context, **_arguments):
                current_max_x = max(float(vertex.co.x) for vertex in obj.data.vertices)
                return {
                    "ok": True,
                    "comparison_id": "improving",
                    "resolution": [100, 100],
                    "metrics": {
                        "silhouette_iou": 0.5 + (current_max_x - baseline_max_x) * 0.1,
                        "mean_edge_distance_pixels": 0.0,
                    },
                    "landmark_errors": [],
                    "images": [],
                }

            reference_comparison.compare_model_to_reference = improving_compare
            improved = _execute(
                context,
                "optimize_screen_space_sculpt",
                {
                    **_screen_arguments(context, obj, collection, camera)[0],
                    "strength_candidates": [0.5, 1.0, 1.5],
                    "minimum_improvement": 0.0001,
                },
            )
            assert improved["changed"] is True
            assert improved["selected_strength"] == 1.5
            assert improved["score_improvement"] > 0.0
            assert max(float(vertex.co.x) for vertex in obj.data.vertices) > baseline_max_x
            assert live_preview.revert(context)["ok"]
            _assert_coordinates_close(_coordinates(obj), unchanged_before)
        finally:
            reference_comparison.compare_model_to_reference = original_compare

        assert any(
            attribute.name.startswith("semantic_region::")
            for attribute in obj.data.attributes
        )
        assert len(unsculpted) == len(obj.data.vertices)
        print("smoke_semantic_sculpt: ok")
    finally:
        transaction = live_preview.current_transaction()
        if transaction and transaction.get("status") == "pending":
            live_preview.revert(context)
        claude_blender.unregister()


if __name__ == "__main__":
    main()
