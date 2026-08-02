"""Blender background smoke for reference part graph and base mesh tools."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import reference_fur_flow, tool_dispatcher  # noqa: E402


def _execute(context, name, args=None, *, expect_ok=True):
    result = json.loads(tool_dispatcher.execute_tool(context, name, args or {}))
    if expect_ok:
        assert result.get("ok"), f"{name} failed: {result}"
    else:
        assert not result.get("ok"), f"{name} unexpectedly succeeded: {result}"
    return result


def _reference_png(path):
    image = bpy.data.images.new("Reference Part Smoke", width=80, height=96, alpha=True)
    try:
        pixels = []
        for y in range(96):
            for x in range(80):
                head = ((x - 40) / 30) ** 2 + ((y - 32) / 24) ** 2 <= 1.0
                body = ((x - 40) / 23) ** 2 + ((y - 66) / 26) ** 2 <= 1.0
                pixels.extend([0.8, 0.84, 0.88, 1.0 if head or body else 0.0])
        image.pixels = pixels
        image.filepath_raw = path
        image.file_format = "PNG"
        image.save()
    finally:
        if bpy.data.images.get(image.name) is image:
            bpy.data.images.remove(image)


def main():
    colliding_names = reference_fur_flow._unique_group_names(
        [{"name": "head/a"}, {"name": "head?a"}, {"name": "x" * 200}],
        "Reference Part",
    )
    assert len(set(colliding_names)) == 3, colliding_names
    assert all(len(name.encode("utf-8")) <= 63 for name in colliding_names)
    long_part_name = "head_" + "detail_" * 20
    attached_field = reference_fur_flow._attach_vertex_groups_to_field(
        {"regions": [{"part_name": long_part_name}]},
        {
            "objects": [
                {
                    "groups": [
                        {
                            "part_name": long_part_name,
                            "vertex_group": "Reference Part Head",
                        }
                    ]
                }
            ]
        },
    )
    assert attached_field["regions"][0]["vertex_group"] == "Reference Part Head"

    bpy.ops.wm.read_factory_settings(use_empty=True)
    claude_blender.register()
    temp_dir = tempfile.mkdtemp(prefix="reference-part-smoke-")
    try:
        context = bpy.context
        image_path = os.path.join(temp_dir, "kitten.png")
        _reference_png(image_path)

        prepared = _execute(
            context,
            "prepare_reference_images",
            {
                "references": [
                    {
                        "name": "front",
                        "image_path": image_path,
                        "axis": "FRONT",
                        "mask_mode": "alpha",
                        "mask_threshold": 0.5,
                    }
                ],
                "subject": "cute kitten",
                "collection_name": "Reference Part Smoke Guides",
            },
        )
        guide_collection = prepared["guide_result"]["collection"]

        graph = _execute(
            context,
            "create_reference_part_graph",
            {
                "collection_name": guide_collection,
                "subject_profile": "cute_quadruped",
                "name": "Reference Part Smoke Graph",
            },
        )
        part_names = {part["name"] for part in graph["parts"]}
        assert {"head", "body", "muzzle"}.issubset(part_names), graph
        graph_collection = bpy.data.collections[graph["collection"]]
        assert graph_collection.get("reference_part_graph"), graph

        base = _execute(
            context,
            "build_part_aware_base_mesh",
            {
                "part_graph_collection_name": graph["collection"],
                "name_prefix": "Reference Part Smoke Base",
                "segments": 12,
                "rings": 8,
                "voxel_size": 0.12,
            },
        )
        assert base["result_objects"], base
        assert bpy.data.objects[base["result_objects"][0]].get("reference_part_base_mesh"), base

        filtered = _execute(
            context,
            "build_part_aware_base_mesh",
            {
                "part_graph_collection_name": graph["collection"],
                "name_prefix": "Reference Part Smoke Organic Only",
                "include_feature_parts": False,
                "segments": 12,
                "rings": 8,
                "voxel_size": 0.12,
            },
        )
        assert not filtered["feature_objects"], filtered
        assert filtered["result_objects"], filtered

        eyes = _execute(
            context,
            "create_eye_stack",
            {
                "part_graph_collection_name": graph["collection"],
                "name_prefix": "Reference Part Smoke Eyes",
                "segments": 12,
                "rings": 8,
            },
        )
        assert len(eyes["objects"]) >= 6, eyes
        assert bpy.data.objects[eyes["objects"][0]].get("reference_feature_stack"), eyes

        muzzle = _execute(
            context,
            "create_muzzle_stack",
            {
                "part_graph_collection_name": graph["collection"],
                "name_prefix": "Reference Part Smoke Muzzle",
                "segments": 12,
                "rings": 8,
                "create_tongue": True,
            },
        )
        assert len(muzzle["objects"]) >= 5, muzzle

        ears = _execute(
            context,
            "create_ear_stack",
            {
                "part_graph_collection_name": graph["collection"],
                "name_prefix": "Reference Part Smoke Ears",
                "segments": 12,
                "rings": 8,
            },
        )
        assert len(ears["objects"]) >= 4, ears

        _execute(context, "commit_preview")
        mask_object = bpy.data.objects[base["blended_object"]]
        workload_error = reference_fur_flow._mask_workload_error(
            [mask_object],
            2,
            max_vertices_per_object=1,
        )
        assert "Remesh first" in workload_error, workload_error
        baseline_group = mask_object.vertex_groups.new(name="Smoke Existing Group")
        baseline_group.add([0], 0.75, "REPLACE")
        mask_object.vertex_groups.active_index = baseline_group.index

        masks = _execute(
            context,
            "create_part_weight_vertex_groups",
            {
                "part_graph_collection_name": graph["collection"],
                "object_names": [base["blended_object"]],
                "selected_only": False,
                "max_parts": 6,
                "radius_scale": 2.2,
            },
        )
        assert masks["objects"], masks
        first_group = masks["objects"][0]["groups"][0]["vertex_group"]
        assert mask_object.vertex_groups.get(first_group), masks

        fur_flow = _execute(
            context,
            "create_fur_flow_field_from_parts",
            {
                "part_graph_collection_name": graph["collection"],
                "object_names": [base["blended_object"]],
                "selected_only": False,
                "count": 48,
                "max_regions": 6,
                "apply_groom": True,
                "name_prefix": "Reference Part Smoke Fur",
                "vertex_group_radius_scale": 2.2,
                "replace_existing_vertex_groups": False,
            },
        )
        assert fur_flow["field"]["regions"], fur_flow
        assert any(region.get("vertex_group") for region in fur_flow["field"]["regions"]), fur_flow
        assert fur_flow["applied"], fur_flow
        assert fur_flow["groom_result"]["created"], fur_flow
        assert all(
            group["reused"]
            for item in fur_flow["vertex_group_result"]["objects"]
            for group in item["groups"]
        ), fur_flow
        fur_objects = [item["object"] for item in fur_flow["groom_result"]["created"]]

        _execute(context, "revert_preview")
        assert list(mask_object.vertex_groups.keys()) == ["Smoke Existing Group"]
        assert mask_object.vertex_groups.active_index == 0
        assert abs(mask_object.vertex_groups["Smoke Existing Group"].weight(0) - 0.75) < 1.0e-6
        assert "reference_part_vertex_groups_json" not in mask_object
        assert all(bpy.data.objects.get(name) is None for name in fur_objects)

        graph_data = reference_fur_flow.reference_part_scene.load_part_graph(
            bpy.data.collections[graph["collection"]]
        )
        organic_part = next(
            part
            for part in graph_data["parts"]
            if part.get("role") not in {"eye", "nose"}
        )
        failure_mesh = bpy.data.meshes.new("Reference Fur Failure Mesh")
        failure_mesh.from_pydata([organic_part["center"]], [], [])
        failure_object = bpy.data.objects.new(
            "Reference Fur Failure Object",
            failure_mesh,
        )
        context.scene.collection.objects.link(failure_object)
        failed_fur = _execute(
            context,
            "create_fur_flow_field_from_parts",
            {
                "part_graph_collection_name": graph["collection"],
                "object_names": [failure_object.name],
                "selected_only": False,
                "count": 12,
                "apply_groom": True,
                "vertex_group_radius_scale": 2.2,
            },
            expect_ok=False,
        )
        assert failed_fur["groom_result"]["code"] == "no_fur_samples", failed_fur
        assert not list(failure_object.vertex_groups), failed_fur
        assert "reference_part_vertex_groups_json" not in failure_object, failed_fur

        bad = _execute(
            context,
            "build_part_aware_base_mesh",
            {"part_graph_collection_name": graph["collection"], "part_names": ["missing"]},
            expect_ok=False,
        )
        assert "not found" in bad["message"], bad
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        try:
            claude_blender.unregister()
        except Exception:
            pass


if __name__ == "__main__":
    main()
