"""Blender smoke for importing a real texture-baked TripoSR manifest."""

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
    return parser.parse_args(arguments)


def main():
    args = _arguments()
    manifest_path = os.path.abspath(os.path.expanduser(args.manifest))
    if not os.path.isfile(manifest_path):
        raise RuntimeError(f"TripoSR manifest does not exist: {manifest_path}")

    module_name = "bl_ext.user_default.claude_blender"
    bpy.ops.preferences.addon_enable(module=module_name)
    from bl_ext.user_default.claude_blender import external_assets

    result = external_assets.import_cached_asset(
        bpy.context,
        manifest_path=manifest_path,
        allow_duplicate=True,
        label="TripoSR baked texture import validation",
    )
    assert result.get("ok"), result
    objects = [
        bpy.data.objects[name]
        for name in result["imported_objects"]
        if bpy.data.objects.get(name) is not None
    ]
    meshes = [obj for obj in objects if obj.type == "MESH"]
    materials = {
        material
        for obj in meshes
        for material in obj.data.materials
        if material is not None
    }
    texture_nodes = [
        node
        for material in materials
        if material.use_nodes
        for node in material.node_tree.nodes
        if node.type == "TEX_IMAGE" and node.image is not None
    ]
    images = [node.image for node in texture_nodes]

    assert meshes, result
    assert materials, [obj.name for obj in meshes]
    assert texture_nodes, [material.name for material in materials]
    assert all(
        obj.get(external_assets.ASSET_PROVIDER_PROPERTY) == "triposr"
        for obj in objects
    ), [
        (obj.name, obj.get(external_assets.ASSET_PROVIDER_PROPERTY))
        for obj in objects
    ]
    orientation = result.get("orientation_normalization") or {}
    assert orientation.get("applied") is True, orientation
    assert (
        orientation.get("axis_transform")
        == "triposr_image_plane_to_blender_z_up"
    ), orientation

    print(
        json.dumps(
            {
                "ok": True,
                "objects": [obj.name for obj in objects],
                "mesh_count": len(meshes),
                "material_count": len(materials),
                "texture_node_count": len(texture_nodes),
                "images": [
                    {
                        "name": image.name,
                        "size": list(image.size),
                        "packed": image.packed_file is not None,
                    }
                    for image in images
                ],
                "orientation": orientation,
            },
            sort_keys=True,
        )
    )
    print("smoke_triposr_baked_import: ok")


if __name__ == "__main__":
    main()
