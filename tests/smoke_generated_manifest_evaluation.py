"""Blender smoke for importing and evaluating a generated asset manifest."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import struct
import base64
from pathlib import Path

import bpy


def _arguments():
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="")
    parser.add_argument("--provider", default="")
    return parser.parse_args(arguments)


def main():
    args = _arguments()
    fixture = tempfile.TemporaryDirectory(prefix="bridge-generated-manifest-") if not args.manifest else None
    if fixture:
        model = Path(fixture.name) / "fixture.gltf"
        binary = struct.pack("<12f12H", 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1,
                             0, 2, 1, 0, 1, 3, 1, 2, 3, 2, 0, 3)
        model.write_text(json.dumps({
            "asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
            "nodes": [{"mesh": 0}], "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
            "buffers": [{"uri": "data:application/octet-stream;base64," + base64.b64encode(binary).decode(), "byteLength": len(binary)}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 48}, {"buffer": 0, "byteOffset": 48, "byteLength": 24}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 1]},
                          {"bufferView": 1, "componentType": 5123, "count": 12, "type": "SCALAR"}],
        }))
        manifest_file = Path(fixture.name) / "manifest.json"
        manifest_file.write_text(json.dumps({
            "ok": True, "provider": "meshy", "asset_id": "offline-fixture", "asset_type": "models",
            "import_file": str(model), "manifest_path": str(manifest_file), "cache_dir": fixture.name,
            "generation": {"provider": "meshy"}, "downloaded_files": [{"path": str(model)}],
        }))
        args.manifest, args.provider = str(manifest_file), "meshy"
    manifest_path = os.path.abspath(os.path.expanduser(args.manifest))
    if not os.path.isfile(manifest_path):
        raise RuntimeError(f"Generated manifest does not exist: {manifest_path}")

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))
    import claude_blender
    claude_blender.register()
    from claude_blender import external_assets
    from claude_blender.tool_handlers import generation

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
    claude_blender.unregister()
    if fixture:
        fixture.cleanup()
    print("smoke_generated_manifest_evaluation: ok")


if __name__ == "__main__":
    main()
