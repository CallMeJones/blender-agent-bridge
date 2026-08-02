"""Blender background smoke for deterministic reference image intake and scoring."""

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
    image = bpy.data.images.new("Reference Intake Smoke", width=64, height=64, alpha=True)
    try:
        pixels = []
        for y in range(64):
            for x in range(64):
                inside = 14 <= x <= 49 and 12 <= y <= 51
                pixels.extend([0.8, 0.85, 1.0, 1.0 if inside else 0.0])
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
    temp_dir = tempfile.mkdtemp(prefix="reference-intake-smoke-")
    try:
        context = bpy.context
        image_path = os.path.join(temp_dir, "reference.png")
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
                "subject": "smoke subject",
                "collection_name": "Reference Intake Smoke Guides",
            },
        )
        assert prepared["guide_result"]["annotation_summary"]["counts"]["outlines"] == 1
        assert prepared["intake"][0]["outline_point_count"] >= 3

        bpy.ops.mesh.primitive_cube_add(size=1.5, location=(0.0, 0.0, 1.5))
        cube = context.active_object
        cube.name = "Reference Intake Smoke Target"

        scored = _execute(
            context,
            "evaluate_multiview_reference_match",
            {
                "collection_name": "Reference Intake Smoke Guides",
                "object_names": [cube.name],
                "selected_only": False,
                "reference_mask_source": "outline",
                "benchmark_profile": "blockout",
                "max_axis": 128,
            },
        )
        assert scored["evaluated_view_count"] == 1
        assert scored["aggregate"]["mean_iou"] >= 0.0

        bad = _execute(
            context,
            "prepare_reference_images",
            {
                "references": [
                    {
                        "image_path": image_path,
                        "annotations": {"version": 1},
                        "annotations_json": "{}",
                    }
                ],
            },
            expect_ok=False,
        )
        assert "exactly one annotation source" in bad["message"]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        try:
            claude_blender.unregister()
        except Exception:
            pass


if __name__ == "__main__":
    main()
