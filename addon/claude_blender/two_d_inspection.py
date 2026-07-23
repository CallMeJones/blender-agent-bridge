"""Read-only inspection for 2D, storyboard, and motion-graphics scenes."""

from __future__ import annotations

import bpy

from . import blender_compat


def _animation_owner_name(obj):
    action = obj.animation_data.action if getattr(obj, "animation_data", None) else None
    return action.name if action else ""


def _object_2d_summary(obj):
    data = getattr(obj, "data", None)
    material_names = []
    if hasattr(obj, "material_slots"):
        material_names = [slot.material.name for slot in obj.material_slots if slot.material]
    return {
        "name": obj.name,
        "type": obj.type,
        "data": getattr(data, "name", ""),
        "location": [round(float(component), 5) for component in obj.location],
        "dimensions": [round(float(component), 5) for component in obj.dimensions],
        "material_names": material_names[:8],
        "action": _animation_owner_name(obj),
        "layer_like": obj.type in {"FONT", "CURVE"} or "GREASE" in obj.type,
    }


def get_2d_animation_details(context, *, max_items=32):
    scene = context.scene
    limit = max(1, min(128, int(max_items or 32)))
    grease_objects = [obj for obj in bpy.data.objects if "GREASE" in obj.type][:limit]
    text_objects = [obj for obj in bpy.data.objects if obj.type == "FONT"][:limit]
    curve_objects = [obj for obj in bpy.data.objects if obj.type == "CURVE"][:limit]
    flat_meshes = [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and min(float(component) for component in obj.dimensions) <= 0.05
    ][:limit]
    gp_collections = {}
    for attr in ("grease_pencils", "grease_pencils_v3"):
        collection = getattr(bpy.data, attr, None)
        if collection is not None:
            gp_collections[attr] = len(collection)
    camera = scene.camera
    compositor_tree = blender_compat.node_tree(scene)
    return {
        "ok": True,
        "message": "Collected 2D/storyboard animation context",
        "grease_pencil_data_counts": gp_collections,
        "grease_pencil_objects": [_object_2d_summary(obj) for obj in grease_objects],
        "text_objects": [_object_2d_summary(obj) for obj in text_objects],
        "curve_objects": [_object_2d_summary(obj) for obj in curve_objects],
        "flat_mesh_layers": [_object_2d_summary(obj) for obj in flat_meshes],
        "camera": {
            "name": camera.name if camera else "",
            "type": camera.data.type if camera and camera.type == "CAMERA" else "",
            "ortho_scale": float(camera.data.ortho_scale) if camera and camera.type == "CAMERA" else None,
        },
        "timeline": {
            "frame_current": int(scene.frame_current),
            "frame_start": int(scene.frame_start),
            "frame_end": int(scene.frame_end),
            "fps": int(scene.render.fps),
        },
        "render": {
            "resolution": [int(scene.render.resolution_x), int(scene.render.resolution_y)],
            "film_transparent": bool(scene.render.film_transparent),
        },
        "compositor": {
            "use_nodes": compositor_tree is not None,
            "node_count": len(compositor_tree.nodes) if compositor_tree else 0,
        },
        "recommended_tools": [
            "create_text_object",
            "create_curve_path",
            "create_camera_dolly_animation",
            "capture_animation_playblast",
            "get_render_camera_compositor_details",
        ],
    }
