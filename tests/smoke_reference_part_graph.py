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
from claude_blender import tool_dispatcher  # noqa: E402


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
