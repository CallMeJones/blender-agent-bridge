"""Paired capture/restore codecs for domain preview state.

Transactions and restore ordering belong to live_preview. A codec owns the
record shape it captures and the matching Blender restoration logic.
"""
import bpy
from . import blender_compat

def _socket_value(value):
    if isinstance(value, (int, float, bool, str)) or value is None:
        return value
    try:
        return tuple(float(component) for component in value)
    except TypeError:
        return value

def _find_node(material, node_type):
    tree = blender_compat.node_tree(material)
    if tree is None:
        return None
    return next((node for node in tree.nodes if node.type == node_type), None)

def _view_layer_render_state(view_layer):
    pass_flags = {}
    rna = getattr(view_layer, "bl_rna", None)
    if view_layer is not None and rna is not None:
        for prop in rna.properties:
            identifier = getattr(prop, "identifier", "")
            if identifier.startswith("use_pass_") or identifier in {"pass_alpha_threshold", "pass_cryptomatte_depth"}:
                try:
                    value = getattr(view_layer, identifier)
                except Exception:
                    continue
                if isinstance(value, bool):
                    pass_flags[identifier] = bool(value)
                elif isinstance(value, (int, float)):
                    pass_flags[identifier] = value
    aovs = []
    for aov in list(getattr(view_layer, "aovs", []) or []):
        aovs.append({"name": str(getattr(aov, "name", "")), "type": str(getattr(aov, "type", "COLOR"))})
    return {"pass_flags": pass_flags, "aovs": aovs}

def record_shader_material(transaction, material):
    key = f"material:{material.name}:shader"
    if key in transaction["before_state"]:
        return
    principled = _find_node(material, "BSDF_PRINCIPLED")
    sockets = {}
    if principled:
        for socket_name in ("Base Color", "Metallic", "Roughness", "Alpha", "Emission Color", "Emission Strength"):
            socket = principled.inputs.get(socket_name)
            if socket and hasattr(socket, "default_value"):
                sockets[socket_name] = _socket_value(socket.default_value)
    node_names = []
    links = []
    material_tree = blender_compat.node_tree(material)
    if material_tree:
        node_names = [node.name for node in material_tree.nodes]
        links = [
            {
                "from_node": link.from_node.name,
                "from_socket": {
                    "name": link.from_socket.name,
                    "identifier": getattr(link.from_socket, "identifier", link.from_socket.name),
                },
                "to_node": link.to_node.name,
                "to_socket": {
                    "name": link.to_socket.name,
                    "identifier": getattr(link.to_socket, "identifier", link.to_socket.name),
                },
            }
            for link in material_tree.links
        ]
    transaction["before_state"][key] = {
        "kind": "shader_material",
        "material_name": material.name,
        "use_nodes": blender_compat.node_tree_enabled(material),
        "diffuse_color": tuple(float(component) for component in material.diffuse_color),
        "blend_method": getattr(material, "blend_method", None),
        "surface_render_method": getattr(material, "surface_render_method", None),
        "principled_socket_values": sockets,
        "node_names": node_names,
        "links": links,
    }
    transaction["changed_data_blocks"].append(material.name)

def record_scene_render(transaction, scene):
    key = f"scene:{scene.name}:render_settings"
    if key in transaction["before_state"]:
        return
    view_settings = getattr(scene, "view_settings", None)
    cycles = getattr(scene, "cycles", None)
    eevee = getattr(scene, "eevee", None)
    transaction["before_state"][key] = {
        "kind": "scene_render_settings",
        "scene_name": scene.name,
        "engine": scene.render.engine,
        "resolution_x": int(scene.render.resolution_x),
        "resolution_y": int(scene.render.resolution_y),
        "pixel_aspect_x": float(scene.render.pixel_aspect_x),
        "pixel_aspect_y": float(scene.render.pixel_aspect_y),
        "fps": int(scene.render.fps),
        "frame_start": int(scene.frame_start),
        "frame_end": int(scene.frame_end),
        "frame_current": int(scene.frame_current),
        "film_transparent": bool(scene.render.film_transparent),
        "view_transform": getattr(view_settings, "view_transform", None),
        "look": getattr(view_settings, "look", None),
        "exposure": getattr(view_settings, "exposure", None),
        "gamma": getattr(view_settings, "gamma", None),
        "cycles_samples": getattr(cycles, "samples", None),
        "cycles_preview_samples": getattr(cycles, "preview_samples", None),
        "cycles_use_denoising": getattr(cycles, "use_denoising", None),
        "eevee_taa_render_samples": getattr(eevee, "taa_render_samples", None),
        "eevee_taa_samples": getattr(eevee, "taa_samples", None),
    }
    transaction["changed_data_blocks"].append(scene.name)

def record_camera_settings(transaction, camera_obj):
    data = camera_obj.data if camera_obj and camera_obj.type == "CAMERA" else None
    if data is None:
        return
    key = f"camera:{data.name}:settings"
    if key in transaction["before_state"]:
        return
    transaction["before_state"][key] = {
        "kind": "camera_settings",
        "camera_name": data.name,
        "lens": float(data.lens),
        "sensor_width": float(data.sensor_width),
        "use_dof": bool(data.dof.use_dof),
        "focus_object": data.dof.focus_object.name if data.dof.focus_object else None,
        "aperture_fstop": float(data.dof.aperture_fstop),
    }
    transaction["changed_data_blocks"].append(camera_obj.name)

def record_shape_keys(transaction, obj):
    key = f"object:{obj.name}:shape_keys"
    if key in transaction["before_state"]:
        return
    keys = obj.data.shape_keys if obj.type == "MESH" and obj.data else None
    animation_data = getattr(keys, "animation_data", None) if keys else None
    action = animation_data.action if animation_data else None
    transaction["before_state"][key] = {
        "kind": "shape_keys",
        "object_name": obj.name,
        "had_shape_keys": keys is not None,
        "key_blocks": [
            {
                "name": block.name,
                "value": float(block.value),
                "slider_min": float(block.slider_min),
                "slider_max": float(block.slider_max),
            }
            for block in list(keys.key_blocks)
        ]
        if keys
        else [],
        "had_animation_data": animation_data is not None,
        "action_name": action.name if action else None,
    }
    transaction["changed_data_blocks"].append(obj.name)

def record_material_node_tree_animation(transaction, material):
    node_tree = blender_compat.node_tree(material)
    if node_tree is None:
        return
    key = f"material:{material.name}:node_tree_animation"
    if key in transaction["before_state"]:
        return
    animation_data = node_tree.animation_data
    action = animation_data.action if animation_data else None
    transaction["before_state"][key] = {
        "kind": "material_node_tree_animation",
        "material_name": material.name,
        "had_animation_data": animation_data is not None,
        "action_name": action.name if action else None,
    }
    transaction["changed_data_blocks"].append(material.name)

def record_light_settings(transaction, light_obj):
    data = light_obj.data if light_obj and light_obj.type == "LIGHT" else None
    if data is None:
        return
    key = f"light:{data.name}:settings"
    if key in transaction["before_state"]:
        return
    transaction["before_state"][key] = {
        "kind": "light_settings",
        "light_data_name": data.name,
        "energy": float(data.energy),
        "color": tuple(float(component) for component in data.color),
        "shadow_soft_size": float(getattr(data, "shadow_soft_size", 0.0)),
        "spot_size": float(getattr(data, "spot_size", 0.0)),
        "spot_blend": float(getattr(data, "spot_blend", 0.0)),
    }
    transaction["changed_data_blocks"].append(data.name)

def record_light_data_animation(transaction, light_obj):
    data = light_obj.data if light_obj and light_obj.type == "LIGHT" else None
    if data is None:
        return
    key = f"light:{data.name}:animation"
    if key in transaction["before_state"]:
        return
    animation_data = data.animation_data
    action = animation_data.action if animation_data else None
    transaction["before_state"][key] = {
        "kind": "light_data_animation",
        "light_data_name": data.name,
        "had_animation_data": animation_data is not None,
        "action_name": action.name if action else None,
    }
    transaction["changed_data_blocks"].append(data.name)

def record_view_layer_render_outputs(transaction, scene, view_layer):
    key = f"scene:{scene.name}:view_layer:{view_layer.name}:render_outputs"
    if key in transaction["before_state"]:
        return
    state = _view_layer_render_state(view_layer)
    transaction["before_state"][key] = {
        "kind": "view_layer_render_outputs",
        "scene_name": scene.name,
        "view_layer_name": view_layer.name,
        "pass_flags": state["pass_flags"],
        "aovs": state["aovs"],
    }
    transaction["changed_data_blocks"].append(f"{scene.name}:{view_layer.name}")

def record_world_background(transaction, world):
    key = f"world:{world.name}:background"
    if key in transaction["before_state"]:
        return
    transaction["before_state"][key] = {
        "kind": "world_background",
        "world_name": world.name,
        "color": tuple(float(component) for component in world.color),
    }
    transaction["changed_data_blocks"].append(world.name)

def record_scene_world(transaction, scene):
    key = f"scene:{scene.name}:world"
    if key in transaction["before_state"]:
        return
    transaction["before_state"][key] = {
        "kind": "scene_world",
        "scene_name": scene.name,
        "world_name": scene.world.name if scene.world else None,
    }

def record_image_settings(transaction, image):
    key = f"image:{image.name}:settings"
    if key in transaction["before_state"]:
        return
    transaction["before_state"][key] = {
        "kind": "image_settings",
        "image_name": image.name,
        "colorspace": getattr(image.colorspace_settings, "name", ""),
    }
    transaction["changed_data_blocks"].append(image.name)

def record_mesh_smoothing(transaction, mesh):
    key = f"mesh:{mesh.name}:smoothing"
    if key in transaction["before_state"]:
        return
    transaction["before_state"][key] = {
        "kind": "mesh_smoothing",
        "mesh_name": mesh.name,
        "polygon_smooth": [bool(poly.use_smooth) for poly in mesh.polygons],
    }
    transaction["changed_data_blocks"].append(mesh.name)

def restore_scene_render_settings(before, context, rollback_warnings):
    scene = bpy.data.scenes.get(before['scene_name'])
    if scene:
        scene.render.engine = before['engine']
        scene.render.resolution_x = before['resolution_x']
        scene.render.resolution_y = before['resolution_y']
        if 'pixel_aspect_x' in before:
            scene.render.pixel_aspect_x = before['pixel_aspect_x']
        if 'pixel_aspect_y' in before:
            scene.render.pixel_aspect_y = before['pixel_aspect_y']
        scene.render.fps = before['fps']
        scene.frame_start = before['frame_start']
        scene.frame_end = before['frame_end']
        scene.render.film_transparent = before['film_transparent']
        view_settings = getattr(scene, 'view_settings', None)
        if view_settings:
            for attr in ('view_transform', 'look', 'exposure', 'gamma'):
                value = before.get(attr)
                if value is not None and hasattr(view_settings, attr):
                    try:
                        setattr(view_settings, attr, value)
                    except Exception as exc:
                        rollback_warnings.append(f"Could not restore color management {attr} for {before['scene_name']}: {type(exc).__name__}: {exc}")
        cycles = getattr(scene, 'cycles', None)
        if cycles:
            for attr, key_name in (('samples', 'cycles_samples'), ('preview_samples', 'cycles_preview_samples'), ('use_denoising', 'cycles_use_denoising')):
                value = before.get(key_name)
                if value is not None and hasattr(cycles, attr):
                    setattr(cycles, attr, value)
        eevee = getattr(scene, 'eevee', None)
        if eevee:
            for attr, key_name in (('taa_render_samples', 'eevee_taa_render_samples'), ('taa_samples', 'eevee_taa_samples')):
                value = before.get(key_name)
                if value is not None and hasattr(eevee, attr):
                    setattr(eevee, attr, value)
        scene.frame_set(before['frame_current'])


def restore_view_layer_render_outputs(before, context, rollback_warnings):
    scene = bpy.data.scenes.get(before['scene_name'])
    view_layer = scene.view_layers.get(before['view_layer_name']) if scene else None
    if view_layer:
        for attr, value in (before.get('pass_flags') or {}).items():
            if hasattr(view_layer, attr):
                try:
                    setattr(view_layer, attr, value)
                except Exception as exc:
                    rollback_warnings.append(f"Could not restore render pass {attr} for {before['view_layer_name']}: {type(exc).__name__}: {exc}")
        aovs = getattr(view_layer, 'aovs', None)
        if aovs is not None:
            for aov in list(aovs):
                try:
                    aovs.remove(aov)
                except Exception as exc:
                    rollback_warnings.append(f"Could not remove temporary AOV {getattr(aov, 'name', '<unnamed>')}: {type(exc).__name__}: {exc}")
            for item in before.get('aovs') or []:
                try:
                    aov = aovs.add()
                    aov.name = item.get('name') or 'AOV'
                    aov.type = item.get('type') or 'COLOR'
                except Exception as exc:
                    rollback_warnings.append(f"Could not restore AOV {item.get('name', '<unnamed>')}: {type(exc).__name__}: {exc}")
    else:
        rollback_warnings.append(f"Missing scene/view layer for render-output restore: {before.get('scene_name')} / {before.get('view_layer_name')}")


def restore_scene_world(before, context, rollback_warnings):
    scene = bpy.data.scenes.get(before['scene_name'])
    if scene:
        scene.world = bpy.data.worlds.get(before['world_name']) if before['world_name'] else None


def restore_world_background(before, context, rollback_warnings):
    world = bpy.data.worlds.get(before['world_name'])
    if world:
        world.color = before['color']


def restore_image_settings(before, context, rollback_warnings):
    image = bpy.data.images.get(before['image_name'])
    if image:
        try:
            image.colorspace_settings.name = before['colorspace']
        except Exception as exc:
            rollback_warnings.append(f"Could not restore image settings for {before['image_name']}: {type(exc).__name__}: {exc}")


def restore_camera_settings(before, context, rollback_warnings):
    camera = bpy.data.cameras.get(before['camera_name'])
    if camera:
        camera.lens = before['lens']
        camera.sensor_width = before['sensor_width']
        camera.dof.use_dof = before['use_dof']
        camera.dof.focus_object = bpy.data.objects.get(before['focus_object']) if before['focus_object'] else None
        camera.dof.aperture_fstop = before['aperture_fstop']


def restore_mesh_smoothing(before, context, rollback_warnings):
    mesh = bpy.data.meshes.get(before['mesh_name'])
    if mesh:
        for polygon, use_smooth in zip(mesh.polygons, before['polygon_smooth']):
            polygon.use_smooth = bool(use_smooth)


def restore_shader_material(before, context, rollback_warnings):
    material = bpy.data.materials.get(before['material_name'])
    if material:
        blender_compat.restore_node_tree_enabled(material, before['use_nodes'])
        material.diffuse_color = before['diffuse_color']
        if before['blend_method'] is not None and hasattr(material, 'blend_method'):
            material.blend_method = before['blend_method']
        if before['surface_render_method'] is not None and hasattr(material, 'surface_render_method'):
            material.surface_render_method = before['surface_render_method']
        material_tree = blender_compat.node_tree(material)
        if material_tree:
            principled = next((node for node in material_tree.nodes if node.type == 'BSDF_PRINCIPLED'), None)
            if principled:
                for socket_name, value in before['principled_socket_values'].items():
                    socket = principled.inputs.get(socket_name)
                    if not socket or not hasattr(socket, 'default_value'):
                        continue
                    current = socket.default_value
                    if hasattr(current, '__len__') and (not isinstance(current, str)):
                        for index in range(min(len(current), len(value))):
                            current[index] = value[index]
                    else:
                        socket.default_value = value
    else:
        rollback_warnings.append(f"Missing material for shader restore: {before['material_name']}")


def restore_material_node_tree_animation(before, context, rollback_warnings):
    material = bpy.data.materials.get(before['material_name'])
    node_tree = blender_compat.node_tree(material)
    if node_tree:
        if before['had_animation_data']:
            animation_data = node_tree.animation_data_create()
            animation_data.action = bpy.data.actions.get(before['action_name']) if before['action_name'] else None
        elif node_tree.animation_data:
            node_tree.animation_data_clear()


def restore_light_settings(before, context, rollback_warnings):
    light = bpy.data.lights.get(before['light_data_name'])
    if light:
        light.energy = before['energy']
        light.color = before['color']
        if hasattr(light, 'shadow_soft_size'):
            light.shadow_soft_size = before['shadow_soft_size']
        if hasattr(light, 'spot_size'):
            light.spot_size = before['spot_size']
        if hasattr(light, 'spot_blend'):
            light.spot_blend = before['spot_blend']
    else:
        rollback_warnings.append(f"Missing light data for settings restore: {before['light_data_name']}")


def restore_light_data_animation(before, context, rollback_warnings):
    light = bpy.data.lights.get(before['light_data_name'])
    if light:
        if before['had_animation_data']:
            animation_data = light.animation_data_create()
            animation_data.action = bpy.data.actions.get(before['action_name']) if before['action_name'] else None
        elif light.animation_data:
            light.animation_data_clear()
    else:
        rollback_warnings.append(f"Missing light data for animation restore: {before['light_data_name']}")


def restore_shape_keys(before, context, rollback_warnings):
    obj = bpy.data.objects.get(before['object_name'])
    if obj is None or obj.type != 'MESH' or obj.data is None:
        return
    keys = obj.data.shape_keys
    if keys:
        original_names = [item['name'] for item in before['key_blocks']]
        for key in list(keys.key_blocks):
            if key.name not in original_names:
                obj.shape_key_remove(key)
        if before['had_shape_keys']:
            for item in before['key_blocks']:
                key = keys.key_blocks.get(item['name']) if obj.data.shape_keys else None
                if key:
                    key.value = item['value']
                    key.slider_min = item['slider_min']
                    key.slider_max = item['slider_max']
        else:
            for key in list(obj.data.shape_keys.key_blocks) if obj.data.shape_keys else []:
                obj.shape_key_remove(key)
    keys = obj.data.shape_keys
    if keys:
        if before['had_animation_data']:
            animation_data = keys.animation_data_create()
            animation_data.action = bpy.data.actions.get(before['action_name']) if before['action_name'] else None
        elif keys.animation_data:
            keys.animation_data_clear()


CODECS = {
    "shader_material": (record_shader_material, restore_shader_material),
    "scene_render_settings": (record_scene_render, restore_scene_render_settings),
    "camera_settings": (record_camera_settings, restore_camera_settings),
    "shape_keys": (record_shape_keys, restore_shape_keys),
    "material_node_tree_animation": (record_material_node_tree_animation, restore_material_node_tree_animation),
    "light_settings": (record_light_settings, restore_light_settings),
    "light_data_animation": (record_light_data_animation, restore_light_data_animation),
    "view_layer_render_outputs": (record_view_layer_render_outputs, restore_view_layer_render_outputs),
    "world_background": (record_world_background, restore_world_background),
    "scene_world": (record_scene_world, restore_scene_world),
    "image_settings": (record_image_settings, restore_image_settings),
    "mesh_smoothing": (record_mesh_smoothing, restore_mesh_smoothing),
}


def capture(kind, transaction, *args):
    return CODECS[kind][0](transaction, *args)


def restore(before, context, warnings):
    codec = CODECS.get(before.get("kind"))
    if codec is None:
        return False
    codec[1](before, context, warnings)
    return True
