"""Source-to-target PBR atlas baking in an isolated background Blender scene."""
from __future__ import annotations

from array import array
import os
import bpy
from . import blender_compat, retopology_policy

CHANNELS = retopology_policy.MAP_CHANNELS
DEFAULT_MAPS = retopology_policy.DEFAULT_MAPS


def validate_options(resolution, map_types):
    return retopology_policy.validate_atlas(resolution, map_types)


def _activate(obj, sources=()):
    bpy.ops.object.select_all(action="DESELECT")
    for source in sources:
        source.hide_set(False)
        source.hide_render = False
        source.select_set(True)
    obj.hide_set(False)
    obj.hide_render = False
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def _emission_material(material, channel=None, *, white=False):
    copied = material.copy()
    tree = blender_compat.ensure_node_tree(copied)
    output = next((n for n in tree.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None)
    if not output:
        bpy.data.materials.remove(copied)
        raise ValueError(f"Material has no active surface output: {material.name}")
    emission = tree.nodes.new("ShaderNodeEmission")
    emission.inputs["Strength"].default_value = 1.0
    if white:
        emission.inputs["Color"].default_value = (1, 1, 1, 1)
    else:
        shaders = [n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"]
        if len(shaders) != 1:
            bpy.data.materials.remove(copied)
            raise ValueError(f"PBR rebaking requires one Principled BSDF per source material: {material.name}")
        surface = output.inputs["Surface"]
        if not surface.is_linked or surface.links[0].from_node != shaders[0]:
            bpy.data.materials.remove(copied)
            raise ValueError(f"PBR rebaking requires a Principled BSDF connected directly to the active output: {material.name}")
        socket = shaders[0].inputs.get(CHANNELS[channel][0])
        if socket is None and channel == "emission":
            socket = shaders[0].inputs.get("Emission")
        if socket is None:
            bpy.data.materials.remove(copied)
            raise ValueError(f"Material channel not available: {channel}")
        if socket.is_linked:
            tree.links.new(socket.links[0].from_socket, emission.inputs["Color"])
        else:
            value = socket.default_value
            emission.inputs["Color"].default_value = tuple(value) if hasattr(value, "__len__") else (value, value, value, 1)
        if channel == "emission" and shaders[0].inputs.get("Emission Strength"):
            strength = shaders[0].inputs["Emission Strength"]
            scale = tree.nodes.new("ShaderNodeVectorMath")
            scale.operation = "SCALE"
            if socket.is_linked:
                tree.links.new(socket.links[0].from_socket, scale.inputs[0])
            else:
                scale.inputs[0].default_value = tuple(socket.default_value)[:3]
            if strength.is_linked:
                tree.links.new(strength.links[0].from_socket, scale.inputs["Scale"])
            else:
                scale.inputs["Scale"].default_value = strength.default_value
            tree.links.new(scale.outputs["Vector"], emission.inputs["Color"])
    tree.links.new(emission.outputs[0], output.inputs["Surface"])
    return copied


def _prepare_atlas_uvs(target, resolution, margin):
    """Pack charts with room for each island's bake dilation, measured in pixels."""
    while target.data.uv_layers:
        target.data.uv_layers.remove(target.data.uv_layers[0])
    target.data.uv_layers.new(name="Retopology UV")
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        bpy.ops.mesh.select_all(action="SELECT")
        if "FINISHED" not in bpy.ops.uv.smart_project(angle_limit=1.1519173, island_margin=0):
            raise RuntimeError("UV projection did not finish")
        bpy.ops.uv.select_all(action="SELECT")
        # FRACTION is a margin on each side of a chart: two charts have a
        # 2 * margin pixel gap. Unlike SCALED, it survives final atlas scaling.
        if "FINISHED" not in bpy.ops.uv.pack_islands(
                rotate=True, rotate_method="ANY", scale=True, margin_method="FRACTION",
                margin=float(margin) / resolution, shape_method="CONCAVE"):
            raise RuntimeError("UV packing did not finish")
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


def bake_atlas(source, target, output_dir, *, resolution=1024, map_types=None, samples=16,
               margin=8, ray_distance_ratio=0.05, cage_extrusion_ratio=0.01, uv_mode="smart_project",
               progress=None):
    """Bake channels without altering source materials; caller owns the isolated scene."""
    maps = validate_options(resolution, map_types)
    report = progress or (lambda *_: None)
    if uv_mode not in {"smart_project", "existing"}:
        raise ValueError("uv_mode must be smart_project or existing")
    _activate(target)
    if uv_mode == "smart_project":
        # The new UV atlas intentionally replaces UVs that topology changes invalidated.
        _prepare_atlas_uvs(target, resolution, margin)
    if not target.data.uv_layers:
        raise ValueError("Target needs a UV map before rebaking")
    if not source.data.materials:
        material = bpy.data.materials.new("Retopology Default Source")
        blender_compat.ensure_node_tree(material)
        source.data.materials.append(material)
    original_materials = list(source.data.materials)
    if any(material is None for material in original_materials):
        raise ValueError("Every source material slot must contain a material")
    material = bpy.data.materials.new(target.name + " Baked PBR")
    tree = blender_compat.ensure_node_tree(material)
    shader = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
    target.data.materials.clear()
    target.data.materials.append(material)
    for face in target.data.polygons:
        face.material_index = 0
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = int(samples)
    scene.render.bake.use_selected_to_active = True
    scene.render.bake.use_cage = False
    diagonal = max(source.dimensions.length, 1e-8)
    ray_distance = diagonal * float(ray_distance_ratio)
    extrusion = diagonal * float(cage_extrusion_ratio)
    images, artifacts = {}, []
    os.makedirs(output_dir, exist_ok=True)

    def bake_image(channel, *, coverage=False, self_mask=False):
        image = bpy.data.images.new(target.name + " " + channel, width=resolution, height=resolution,
                                    alpha=True, float_buffer=channel == "emission")
        image.generated_color = (0, 0, 0, 0)
        image.colorspace_settings.name = "Non-Color" if coverage else CHANNELS[channel][1]
        node = tree.nodes.new("ShaderNodeTexImage")
        node.image = image
        tree.nodes.active = node
        copied = []
        try:
            if channel != "normal":
                for i, mat in enumerate(original_materials):
                    replacement = _emission_material(mat, channel, white=coverage)
                    copied.append(replacement)
                    source.data.materials[i] = replacement
            if self_mask:
                previous = list(target.data.materials)
                white = _emission_material(material, white=True)
                copied.append(white)
                white_node = white.node_tree.nodes.new("ShaderNodeTexImage")
                white_node.image = image
                white.node_tree.nodes.active = white_node
                target.data.materials[0] = white
            _activate(target, () if self_mask else (source,))
            kwargs = {"type": "NORMAL" if channel == "normal" else "EMIT", "use_clear": True,
                      "use_selected_to_active": not self_mask, "use_cage": False,
                      "cage_extrusion": extrusion, "max_ray_distance": ray_distance,
                      "margin": 0 if coverage else int(margin)}
            if "FINISHED" not in bpy.ops.object.bake(**kwargs):
                raise RuntimeError(f"Texture bake did not finish: {channel}")
            if self_mask:
                target.data.materials[0] = previous[0]
            return image, node
        except Exception:
            tree.nodes.remove(node)
            if image.users == 0:
                bpy.data.images.remove(image)
            raise
        finally:
            source.data.materials.clear()
            for original in original_materials:
                source.data.materials.append(original)
            if self_mask:
                target.data.materials[0] = material
            for mat in copied:
                if mat.users == 0:
                    bpy.data.materials.remove(mat)

    for index, channel in enumerate(maps):
        report("bake", (index + 1) / (len(maps) + 2), channel)
        image, node = bake_image(channel)
        image.filepath_raw = os.path.join(output_dir, channel + (".exr" if channel == "emission" else ".png"))
        image.file_format = "OPEN_EXR" if channel == "emission" else "PNG"
        image.save()
        image.pack()
        images[channel] = node
        artifacts.append({"map_type": channel, "path": image.filepath_raw,
                          "bytes": os.path.getsize(image.filepath_raw), "resolution": resolution})
    # A white source bake compared with the target's own UV mask detects missed rays
    # without treating legitimately black material regions as failed texture coverage.
    mask, mask_node = bake_image("uv_mask", coverage=True, self_mask=True)
    hit, hit_node = bake_image("projection_coverage", coverage=True)
    mask_pixels = array("f", [0]) * (resolution * resolution * 4)
    hit_pixels = array("f", [0]) * len(mask_pixels)
    mask.pixels.foreach_get(mask_pixels)
    hit.pixels.foreach_get(hit_pixels)
    expected = covered = 0
    for i in range(0, len(mask_pixels), 4):
        if mask_pixels[i] > 0.5:
            expected += 1
            covered += hit_pixels[i] > 0.5
    for image, node in ((mask, mask_node), (hit, hit_node)):
        tree.nodes.remove(node)
        bpy.data.images.remove(image)
    for channel, node in images.items():
        socket_name = CHANNELS[channel][0]
        socket = shader.inputs.get(socket_name) or shader.inputs.get("Emission" if channel == "emission" else socket_name)
        if channel == "normal":
            normal = tree.nodes.new("ShaderNodeNormalMap")
            tree.links.new(node.outputs["Color"], normal.inputs["Color"])
            tree.links.new(normal.outputs["Normal"], shader.inputs["Normal"])
        elif socket:
            tree.links.new(node.outputs["Color"], socket)
            if channel == "emission" and shader.inputs.get("Emission Strength"):
                shader.inputs["Emission Strength"].default_value = 1.0
    coverage = covered / expected if expected else 0.0
    atlas_pixels = resolution * resolution
    utilization = expected / atlas_pixels
    warnings = ["Projection coverage is below 98%; inspect rays/cage and close surfaces"] if coverage < .98 else []
    if utilization < .25:
        warnings.append("UV atlas uses less than 25% of texture pixels before padding; "
                        "detail may be lost even with high projection coverage. "
                        "Review chart count, pixel margin, resolution or an existing UV layout")
    for original in original_materials:
        for node in original.node_tree.nodes if original.node_tree else ():
            if node.type == "BSDF_PRINCIPLED":
                for key, baseline in (("Alpha", 1), ("Transmission Weight", 0), ("Coat Weight", 0)):
                    socket = node.inputs.get(key)
                    if socket and (socket.is_linked or abs(socket.default_value - baseline) > 1e-6):
                        warnings.append(f"{original.name}: {key} is not transferred by the PBR atlas; review this material manually")
    return {"maps": artifacts, "material": material.name, "uv_map": target.data.uv_layers.active.name,
            "coverage": {"expected_pixels": expected, "covered_pixels": covered, "fraction": coverage},
            "atlas": {"used_pixels": expected, "total_pixels": atlas_pixels,
                      "utilization_fraction": utilization, "excludes_padding": True,
                      "packing": "concave_pixel_padding" if uv_mode == "smart_project" else "existing",
                      "packing_margin_pixels": margin if uv_mode == "smart_project" else None},
            "warnings": warnings}
