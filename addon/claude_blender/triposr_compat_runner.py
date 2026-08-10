"""Run TripoSR with narrow compatibility fixes owned by the bridge."""

from __future__ import annotations

import os
import runpy
import sys


def _install_texture_bake_compatibility():
    try:
        from tsr import bake_texture as bake_module
    except ModuleNotFoundError as error:
        if error.name == "tsr":
            return False
        raise
    import numpy as np
    import torch

    def positions_to_colors(model, scene_code, positions_texture, texture_resolution):
        flattened = np.ascontiguousarray(positions_texture.reshape(-1, 4)).copy()
        tensor_options = {"device": scene_code.device}
        if getattr(scene_code.dtype, "is_floating_point", False):
            tensor_options["dtype"] = scene_code.dtype
        positions = torch.as_tensor(flattened[:, :-1], **tensor_options)
        with torch.no_grad():
            queried_grid = model.renderer.query_triplane(
                model.decoder,
                positions,
                scene_code,
            )
        rgb_f = queried_grid["color"].detach().cpu().numpy().reshape(-1, 3)
        rgba_f = np.insert(rgb_f, 3, flattened[:, -1], axis=1)
        rgba_f[rgba_f[:, -1] == 0.0] = [0, 0, 0, 0]
        return rgba_f.reshape(texture_resolution, texture_resolution, 4)

    bake_module.positions_to_colors = positions_to_colors
    return True


def _argument_value(argv, name, default=""):
    try:
        return argv[argv.index(name) + 1]
    except (ValueError, IndexError):
        return default


def _convert_baked_obj_payloads_to_glb(argv):
    if "--bake-texture" not in argv:
        return []
    if _argument_value(argv, "--model-save-format", "obj").lower() != "glb":
        return []
    output_dir = os.path.abspath(_argument_value(argv, "--output-dir", "output"))

    import trimesh
    from PIL import Image

    converted = []
    for root, _dirs, files in os.walk(output_dir):
        if "mesh.glb" not in files or "texture.png" not in files:
            continue
        mesh_path = os.path.join(root, "mesh.glb")
        with open(mesh_path, "rb") as handle:
            if handle.read(4) == b"glTF":
                continue
        mesh = trimesh.load(mesh_path, file_type="obj", process=False)
        if isinstance(mesh, trimesh.Scene):
            geometries = tuple(mesh.geometry.values())
            if len(geometries) != 1:
                raise RuntimeError(
                    "TripoSR baked OBJ compatibility expected one mesh geometry"
                )
            mesh = geometries[0]
        uvs = getattr(getattr(mesh, "visual", None), "uv", None)
        if uvs is None:
            raise RuntimeError("TripoSR baked OBJ compatibility found no UV atlas")
        texture_path = os.path.join(root, "texture.png")
        material = trimesh.visual.texture.SimpleMaterial(
            image=Image.open(texture_path).convert("RGBA"),
            name="TripoSR Baked Texture",
        )
        mesh.visual = trimesh.visual.texture.TextureVisuals(
            uv=uvs,
            material=material,
        )
        payload = mesh.export(file_type="glb")
        if not isinstance(payload, (bytes, bytearray)) or payload[:4] != b"glTF":
            raise RuntimeError("TripoSR baked texture conversion did not produce GLB")
        temporary_path = mesh_path + ".tmp"
        with open(temporary_path, "wb") as handle:
            handle.write(payload)
        os.replace(temporary_path, mesh_path)
        converted.append(mesh_path)
    if not converted:
        raise RuntimeError("TripoSR baked texture conversion found no OBJ payload")
    return converted


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        raise SystemExit("TripoSR compatibility runner requires the path to run.py")
    run_path = os.path.abspath(argv[0])
    runtime_root = os.path.dirname(run_path)
    if runtime_root not in sys.path:
        sys.path.insert(0, runtime_root)
    texture_compatibility_installed = _install_texture_bake_compatibility()
    sys.argv = [run_path, *argv[1:]]
    runpy.run_path(run_path, run_name="__main__")
    if texture_compatibility_installed:
        _convert_baked_obj_payloads_to_glb(argv[1:])


if __name__ == "__main__":
    main()
