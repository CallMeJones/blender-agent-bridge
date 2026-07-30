"""Shared Blender scene accessors for calibrated reference-guide workflows."""

from __future__ import annotations

import json
import math
import os

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


REFERENCE_GUIDE_METADATA_PROP = "reference_guide_metadata_json"


def _finite_number(value):
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and (not isinstance(value, float) or math.isfinite(value))
    )


def json_prop(item, key):
    try:
        value = item.get(key)
    except Exception:
        value = None
    if not value:
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def guide_collection(collection_name, *, require_unique=True):
    name = str(collection_name or "").strip()
    if name:
        collection = bpy.data.collections.get(name)
        if collection is None:
            return None, f"Reference guide collection not found: {name}"
        if not bool(collection.get("reference_modeling_guides", False)):
            return None, f"Collection is not tagged as reference guides: {name}"
        return collection, ""
    collections = [
        collection
        for collection in bpy.data.collections
        if bool(collection.get("reference_modeling_guides", False))
    ]
    if not collections:
        return None, "No reference guide collection is available"
    if require_unique and len(collections) > 1:
        return (
            None,
            "Multiple reference guide collections are available; supply collection_name",
        )
    return collections[0], ""


def guide_objects(collection, kind):
    return [
        obj
        for obj in collection.objects
        if str(obj.get("reference_guide_kind") or "") == str(kind or "")
    ]


def _collection_tree(collection):
    yield collection
    for child in collection.children:
        yield from _collection_tree(child)


def _collection_contains_object(collection, obj):
    return any(candidate.objects.get(obj.name) is obj for candidate in _collection_tree(collection))


def _calibrated_camera_error(collection, camera):
    if camera is None or camera.type != "CAMERA":
        return "Comparison camera was not found"
    if not _collection_contains_object(collection, camera):
        return (
            f"Comparison camera is not part of reference guide collection "
            f"{collection.name}: {camera.name}"
        )
    if str(camera.get("reference_guide_kind") or "") != "camera":
        return f"Comparison camera is not tagged as a calibrated reference camera: {camera.name}"
    metadata = json_prop(camera, REFERENCE_GUIDE_METADATA_PROP)
    ortho_scale = metadata.get("ortho_scale")
    target = metadata.get("target")
    if (
        getattr(camera.data, "type", "") != "ORTHO"
        or str(metadata.get("camera_type") or "").upper() != "ORTHO"
        or not _finite_number(ortho_scale)
        or ortho_scale <= 0.0
        or not isinstance(target, list)
        or len(target) != 3
        or any(not _finite_number(value) for value in target)
    ):
        return f"Comparison camera lacks valid orthographic reference calibration: {camera.name}"
    return ""


def comparison_camera(collection, camera_name=""):
    name = str(camera_name or "").strip()
    if name:
        camera = bpy.data.objects.get(name)
        error = _calibrated_camera_error(collection, camera)
        if error:
            return None, error
        return camera, ""
    cameras = [
        obj
        for candidate in _collection_tree(collection)
        for obj in guide_objects(candidate, "camera")
        if not _calibrated_camera_error(collection, obj)
    ]
    if not cameras:
        return (
            None,
            "Reference guides have no calibrated camera; recreate them with create_camera=true",
        )
    if len(cameras) == 1:
        return cameras[0], ""
    metadata = json_prop(collection, REFERENCE_GUIDE_METADATA_PROP)
    active_view = str(metadata.get("active_view") or "")
    active = [
        camera
        for camera in cameras
        if (
            active_view
            and str(camera.get("reference_view_name") or "") == active_view
        )
        or bool(json_prop(camera, REFERENCE_GUIDE_METADATA_PROP).get("active"))
    ]
    if len(active) == 1:
        return active[0], ""
    return (
        None,
        "Multiple calibrated cameras are available; supply camera_name",
    )


def reference_identity(collection, camera=None):
    candidates = list(_collection_tree(collection))
    if camera is not None:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.objects.get(camera.name) is camera
        ]
    identities = []
    for candidate in candidates:
        metadata = json_prop(candidate, REFERENCE_GUIDE_METADATA_PROP)
        identity = metadata.get("reference_image")
        if not isinstance(identity, dict):
            identity = {}
        digest = str(
            identity.get("sha256")
            or candidate.get("reference_image_sha256")
            or ""
        ).strip().lower()
        if digest:
            try:
                size_bytes = max(0, int(identity.get("size_bytes") or 0))
            except (TypeError, ValueError, OverflowError):
                size_bytes = 0
            identities.append(
                {
                    "sha256": digest,
                    "size_bytes": size_bytes,
                    "path": str(identity.get("path") or ""),
                }
            )
    unique = {item["sha256"]: item for item in identities}
    return next(iter(unique.values())) if len(unique) == 1 else {}


def curve_world_points(obj, *, max_points=512):
    points = []
    if obj.type != "CURVE":
        return points
    for spline in obj.data.splines:
        if spline.type == "BEZIER":
            source = [point.co for point in spline.bezier_points]
        else:
            source = [point.co.to_3d() for point in spline.points]
        points.extend(obj.matrix_world @ Vector(point) for point in source)
        if len(points) >= max_points:
            break
    return points[: max(1, int(max_points or 1))]


def project_point(scene, camera, world_point):
    projected = world_to_camera_view(scene, camera, Vector(world_point))
    return [float(projected.x), float(1.0 - projected.y)]


def image_path(collection):
    for obj in guide_objects(collection, "image_plane"):
        metadata = json_prop(obj, REFERENCE_GUIDE_METADATA_PROP)
        path = os.path.abspath(
            bpy.path.abspath(str(metadata.get("image_path") or ""))
        )
        if os.path.isfile(path):
            return path
    return ""


def camera_margin(camera):
    metadata = json_prop(camera, REFERENCE_GUIDE_METADATA_PROP)
    try:
        return max(0.0, min(1.0, float(metadata.get("margin") or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def camera_basis(camera):
    rotation = camera.matrix_world.to_quaternion()
    right = (rotation @ Vector((1.0, 0.0, 0.0))).normalized()
    depth = (rotation @ Vector((0.0, 0.0, -1.0))).normalized()
    up = (rotation @ Vector((0.0, 1.0, 0.0))).normalized()
    return right, depth, up
