"""Blender smoke for importing and evaluating a generated asset manifest."""

from __future__ import annotations

import argparse
import json
import os
import sys

import bpy


def _arguments():
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--provider", default="")
    return parser.parse_args(arguments)


def main():
    args = _arguments()
    manifest_path = os.path.abspath(os.path.expanduser(args.manifest))
    if not os.path.isfile(manifest_path):
        raise RuntimeError(f"Generated manifest does not exist: {manifest_path}")

    module_name = "bl_ext.user_default.claude_blender"
    bpy.ops.preferences.addon_enable(module=module_name)
    from bl_ext.user_default.claude_blender import external_assets
    from bl_ext.user_default.claude_blender.tool_handlers import generation

    imported = external_assets.import_cached_asset(
        bpy.context,
        manifest_path=manifest_path,
        allow_duplicate=True,
        label="Generated manifest import/evaluation validation",
    )
    assert imported.get("ok"), imported
    objects = [
        bpy.data.objects[name]
        for name in imported["imported_objects"]
        if bpy.data.objects.get(name) is not None
    ]
    meshes = [obj for obj in objects if obj.type == "MESH"]
    assert meshes, imported

    provider = str(args.provider or "").strip().lower()
    if provider:
        assert all(
            obj.get(external_assets.ASSET_PROVIDER_PROPERTY) == provider
            for obj in objects
        ), [
            (obj.name, obj.get(external_assets.ASSET_PROVIDER_PROPERTY))
            for obj in objects
        ]

    evaluated = generation.evaluate_generated_asset(
        bpy.context,
        {
            "object_names": [obj.name for obj in meshes],
            "manifest_path": manifest_path,
            "include_renders": False,
        },
    )
    assert evaluated.get("ok"), evaluated
    assert evaluated.get("evaluations"), evaluated
    for item in evaluated["evaluations"]:
        assert item["topology"]["vertices"] > 0, item
        assert item["topology"]["faces"] > 0, item
        assert item["components"]["component_count"] > 0, item
        assert item["material"]["material_type"], item

    orientation = imported.get("orientation_normalization") or {}
    if provider == "triposr":
        assert orientation.get("applied") is True, orientation
        assert any(
            item.get("relief_shell_risk") for item in evaluated["evaluations"]
        ), evaluated

    print(
        json.dumps(
            {
                "ok": True,
                "provider": provider,
                "objects": [obj.name for obj in objects],
                "orientation": orientation,
                "evaluations": evaluated["evaluations"],
            },
            sort_keys=True,
        )
    )
    print("smoke_generated_manifest_evaluation: ok")


if __name__ == "__main__":
    main()
