"""Blender scene construction and inspection for reference-modeling guides."""

from __future__ import annotations

import hashlib
import json
import math
import os

import bpy
from mathutils import Vector

from . import live_preview, reference_annotations
from .advanced_support import (
    _coerce_vector,
    _material_for_color,
    _record_scene_render,
)


REFERENCE_GUIDE_COORDINATE_SPACES = {"normalized", "pixel"}
REFERENCE_GUIDE_METADATA_PROP = "reference_guide_metadata_json"


def _require_finite_numbers(value, path):
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        try:
            number = float(value)
        except OverflowError as exc:
            raise ValueError(
                f"{path} must contain only finite numbers"
            ) from exc
        if not math.isfinite(number):
            raise ValueError(f"{path} must contain only finite numbers")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _require_finite_numbers(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _require_finite_numbers(item, f"{path}[{index}]")


def _bounded_number(value, path, *, minimum, maximum):
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(
            f"{path} must be between {minimum} and {maximum}"
        )
    return number


def _reference_image_identity(image_path):
    path = os.path.abspath(os.path.expanduser(str(image_path or "").strip()))
    if not path or not os.path.isfile(path):
        return {}
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return {
        "path": path,
        "sha256": digest.hexdigest(),
        "size_bytes": size,
    }


def _set_json_prop(data_block, key, value):
    try:
        data_block[key] = json.dumps(value, sort_keys=True)
    except Exception:
        data_block[key] = "{}"

def _get_json_prop(data_block, key, fallback=None):
    try:
        value = data_block.get(key)
        if not value:
            return fallback
        loaded = json.loads(str(value))
        return loaded if isinstance(loaded, dict) else fallback
    except Exception:
        return fallback

def _vector_list(values):
    return [float(values[0]), float(values[1]), float(values[2])]

def _has_reference_guide_inputs(*, include_image_plane, landmarks, curves, masses, measurements):
    if include_image_plane:
        return True
    for item in landmarks[:128]:
        if isinstance(item, dict) and item.get("point", item.get("center", item.get("position"))) is not None:
            return True
    for item in curves[:64]:
        if isinstance(item, dict) and len(list(item.get("points") or [])) >= 2:
            return True
    for item in masses[:64]:
        if isinstance(item, dict) and item.get("center") is not None and item.get("radius", item.get("radii")) is not None:
            return True
    for item in measurements[:64]:
        if not isinstance(item, dict):
            continue
        if item.get("from_point") is not None and item.get("to_point") is not None:
            return True
        if item.get("from") and item.get("to"):
            return True
    return False

def _as_float_pair(value, fallback=(0.5, 0.5)):
    if isinstance(value, dict):
        value = (value.get("x", fallback[0]), value.get("y", fallback[1]))
    try:
        values = list(value or [])[:2]
    except TypeError:
        values = []
    while len(values) < 2:
        values.append(fallback[len(values)])
    return float(values[0]), float(values[1])

def _as_color(value, fallback):
    try:
        values = list(value or [])[:4]
    except TypeError:
        values = []
    while len(values) < 4:
        values.append(fallback[len(values)])
    return tuple(float(component) for component in values[:4])

def _safe_label(value, fallback):
    text = str(value or fallback).strip() or str(fallback)
    keep = []
    for char in text:
        keep.append(char if char.isalnum() or char in {"_", "-", " "} else "_")
    return " ".join("".join(keep).split())[:80] or str(fallback)


def _loaded_image_for_path(image_path):
    target = os.path.normcase(os.path.abspath(image_path))
    for image in bpy.data.images:
        try:
            candidate = os.path.normcase(
                os.path.abspath(bpy.path.abspath(str(image.filepath or "")))
            )
        except Exception:
            continue
        if candidate == target:
            return image
    return None


def _remove_unused_image(image):
    if image is None:
        return
    try:
        if image.users == 0 and bpy.data.images.get(image.name) is not None:
            bpy.data.images.remove(image)
    except Exception:
        pass


def _reference_mapper(*, coordinate_space, image_size, plane_width, plane_height, plane_location, guide_offset_y):
    width = max(1.0, float((image_size or [1.0, 1.0])[0] or 1.0))
    height = max(1.0, float((image_size or [1.0, 1.0])[1] or 1.0))
    loc = _coerce_vector(plane_location, (0.0, 0.0, 1.5))
    coordinate_space = str(coordinate_space or "normalized").strip().lower()
    if coordinate_space not in REFERENCE_GUIDE_COORDINATE_SPACES:
        coordinate_space = "normalized"

    def normalize(point):
        x, y = _as_float_pair(point)
        if coordinate_space == "pixel":
            x = x / width
            y = y / height
        return max(0.0, min(1.0, x)), max(0.0, min(1.0, y))

    def map_point(point, *, y_offset=0.0):
        x, y = normalize(point)
        return (
            loc[0] + (x - 0.5) * float(plane_width),
            loc[1] + float(guide_offset_y) + float(y_offset),
            loc[2] + (0.5 - y) * float(plane_height),
        )

    return normalize, map_point

def _create_reference_plane(
    context,
    *,
    name,
    image,
    image_owned_by_preview,
    plane_width,
    plane_height,
    plane_location,
    alpha,
):
    mesh = bpy.data.meshes.new(f"{name} Mesh")
    x = float(plane_width) / 2.0
    z = float(plane_height) / 2.0
    loc = _coerce_vector(plane_location, (0.0, 0.0, 1.5))
    verts = [
        (loc[0] - x, loc[1], loc[2] - z),
        (loc[0] + x, loc[1], loc[2] - z),
        (loc[0] + x, loc[1], loc[2] + z),
        (loc[0] - x, loc[1], loc[2] + z),
    ]
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    context.scene.collection.objects.link(obj)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("mesh", mesh.name)
    material = bpy.data.materials.new(f"{name} Material")
    live_preview._record_created_id("material", material.name)
    material.diffuse_color = (1.0, 1.0, 1.0, max(0.0, min(1.0, float(alpha))))
    material.use_nodes = True
    material.blend_method = "BLEND"
    material.show_transparent_back = False
    nodes = material.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if image is not None and image_owned_by_preview:
        live_preview._record_created_id("image", image.name)
    if bsdf:
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = material.diffuse_color[3]
        if image is not None:
            tex = nodes.new(type="ShaderNodeTexImage")
            tex.image = image
            material.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    obj.data.materials.append(material)
    return obj

def _create_poly_curve_object(context, *, name, points, material, bevel_depth, cyclic=False):
    curve = bpy.data.curves.new(f"{name} Data", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = max(0.0, float(bevel_depth))
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, values in zip(spline.points, points):
        point.co = (float(values[0]), float(values[1]), float(values[2]), 1.0)
    spline.use_cyclic_u = bool(cyclic)
    obj = bpy.data.objects.new(name, curve)
    context.scene.collection.objects.link(obj)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("curve", curve.name)
    if material:
        curve.materials.append(material)
    return obj

def create_reference_modeling_guides(
    context,
    *,
    image_path="",
    image_size=None,
    coordinate_space="normalized",
    subject="reference model",
    collection_name="Reference Modeling Guides",
    plane_height=3.0,
    plane_location=(0.0, 0.0, 1.5),
    guide_offset_y=-0.02,
    include_image_plane=True,
    image_alpha=0.35,
    landmarks=None,
    curves=None,
    masses=None,
    measurements=None,
    label="Create reference modeling guides",
    _loaded_image=None,
    _owns_loaded_image=False,
):
    """Create reference-image guide geometry from image-space landmarks and outlines."""

    landmarks = list(landmarks or [])
    curves = list(curves or [])
    masses = list(masses or [])
    measurements = list(measurements or [])
    try:
        for value, path in (
            (image_size, "image_size"),
            (plane_location, "plane_location"),
            (landmarks, "landmarks"),
            (curves, "curves"),
            (masses, "masses"),
            (measurements, "measurements"),
        ):
            _require_finite_numbers(value, path)
        plane_height = _bounded_number(
            plane_height or 3.0,
            "plane_height",
            minimum=0.01,
            maximum=10000.0,
        )
        guide_offset_y = _bounded_number(
            guide_offset_y,
            "guide_offset_y",
            minimum=-10000.0,
            maximum=10000.0,
        )
        image_alpha = _bounded_number(
            image_alpha,
            "image_alpha",
            minimum=0.0,
            maximum=1.0,
        )
        location = _coerce_vector(plane_location, (0.0, 0.0, 1.5))
        for index, component in enumerate(location):
            _bounded_number(
                component,
                f"plane_location[{index}]",
                minimum=-1000000.0,
                maximum=1000000.0,
            )
    except (OverflowError, TypeError, ValueError) as exc:
        return {
            "ok": False,
            "code": "invalid_reference_guide_geometry",
            "message": str(exc),
        }
    if not _has_reference_guide_inputs(
        include_image_plane=include_image_plane,
        landmarks=landmarks,
        curves=curves,
        masses=masses,
        measurements=measurements,
    ):
        return {"ok": False, "message": "No reference guides were created; supply an image path, landmarks, curves, masses, or measurements"}
    image_size = list(image_size or [])
    loaded_image = _loaded_image
    owns_loaded_image = bool(_owns_loaded_image)
    reference_image = {}
    if image_path:
        expanded = os.path.abspath(os.path.expanduser(str(image_path)))
        if not os.path.isfile(expanded):
            return {
                "ok": False,
                "message": f"Reference image path does not exist or is not a file: {expanded}",
            }
        image_path = expanded
        try:
            reference_image = _reference_image_identity(image_path)
            if loaded_image is None:
                image_names_before_load = set(bpy.data.images.keys())
                loaded_image = bpy.data.images.load(
                    image_path, check_existing=True
                )
                owns_loaded_image = (
                    loaded_image.name not in image_names_before_load
                )
            loaded_width = float(loaded_image.size[0])
            loaded_height = float(loaded_image.size[1])
            if loaded_width <= 0.0 or loaded_height <= 0.0:
                raise ValueError("image dimensions are empty")
            if not image_size:
                image_size = [loaded_width, loaded_height]
        except Exception as exc:
            if owns_loaded_image:
                _remove_unused_image(loaded_image)
            return {
                "ok": False,
                "message": (
                    f"Could not load usable reference image {image_path}: "
                    f"{type(exc).__name__}: {exc}"
                ),
            }
        if not include_image_plane:
            if owns_loaded_image:
                _remove_unused_image(loaded_image)
            loaded_image = None
            owns_loaded_image = False
    if len(image_size) < 2:
        image_size = [1.0, 1.0]
    try:
        image_width = _bounded_number(
            image_size[0] or 1.0,
            "image_size[0]",
            minimum=1.0,
            maximum=1000000000.0,
        )
        image_height = _bounded_number(
            image_size[1] or 1.0,
            "image_size[1]",
            minimum=1.0,
            maximum=1000000000.0,
        )
    except (OverflowError, TypeError, ValueError) as exc:
        if owns_loaded_image:
            _remove_unused_image(loaded_image)
        return {
            "ok": False,
            "code": "invalid_reference_guide_geometry",
            "message": str(exc),
        }
    plane_width = plane_height * (image_width / image_height)
    normalize, map_point = _reference_mapper(
        coordinate_space=coordinate_space,
        image_size=(image_width, image_height),
        plane_width=plane_width,
        plane_height=plane_height,
        plane_location=plane_location,
        guide_offset_y=guide_offset_y,
    )

    had_pending_transaction = bool(
        live_preview.current_transaction() and live_preview.current_transaction().get("status") == "pending"
    )
    transaction = live_preview.begin(label, context)
    collection = bpy.data.collections.new(_safe_label(collection_name, "Reference Modeling Guides"))
    context.scene.collection.children.link(collection)
    live_preview._record_created_id("collection", collection.name)
    collection["reference_modeling_guides"] = True
    collection["reference_guide_subject"] = str(subject or "reference model")
    _set_json_prop(
        collection,
        REFERENCE_GUIDE_METADATA_PROP,
        {
            "subject": str(subject or "reference model"),
            "coordinate_space": str(coordinate_space or "normalized").strip().lower(),
            "image_size": [image_width, image_height],
            "reference_image": reference_image,
            "plane": {"width": plane_width, "height": plane_height, "location": list(_coerce_vector(plane_location, (0.0, 0.0, 1.5)))},
            "guide_offset_y": float(guide_offset_y),
        },
    )
    if reference_image:
        collection["reference_image_sha256"] = reference_image["sha256"]

    def move_to_collection(obj):
        if collection.objects.get(obj.name) is None:
            collection.objects.link(obj)
        for source in list(obj.users_collection):
            if source != collection:
                source.objects.unlink(obj)
        return obj

    created_curves = []
    created_landmarks = []
    created_masses = []
    created_measurements = []
    image_plane = None

    if include_image_plane:
        image_plane = _create_reference_plane(
            context,
            name=f"{collection.name} Image Plane",
            image=loaded_image,
            image_owned_by_preview=owns_loaded_image,
            plane_width=plane_width,
            plane_height=plane_height,
            plane_location=plane_location,
            alpha=image_alpha,
        )
        move_to_collection(image_plane)
        image_plane["reference_guide_kind"] = "image_plane"
        image_plane["reference_guide_name"] = "image_plane"
        _set_json_prop(
            image_plane,
            REFERENCE_GUIDE_METADATA_PROP,
            {
                "kind": "image_plane",
                "name": "image_plane",
                "image_path": image_path,
                "image_size": [image_width, image_height],
                "plane": {"width": plane_width, "height": plane_height, "location": list(_coerce_vector(plane_location, (0.0, 0.0, 1.5)))},
            },
        )

    landmark_positions = {}
    landmark_brief = []
    default_landmark_color = (1.0, 0.72, 0.16, 1.0)
    for index, item in enumerate(landmarks[:128], 1):
        if not isinstance(item, dict):
            continue
        name = _safe_label(item.get("name"), f"landmark_{index}")
        point = item.get("point", item.get("center", item.get("position")))
        if point is None:
            continue
        location = map_point(point)
        empty = bpy.data.objects.new(f"{collection.name} Landmark {name}", None)
        empty.empty_display_type = "SPHERE"
        empty.empty_display_size = max(0.01, float(item.get("size", 0.045) or 0.045))
        empty.location = location
        context.scene.collection.objects.link(empty)
        live_preview._record_created_id("object", empty.name)
        move_to_collection(empty)
        normalized = normalize(point)
        empty["reference_landmark_name"] = name
        empty["reference_landmark_normalized"] = normalized
        empty["reference_landmark_note"] = str(item.get("note") or "")
        empty["reference_guide_kind"] = "landmark"
        empty["reference_guide_name"] = name
        _set_json_prop(
            empty,
            REFERENCE_GUIDE_METADATA_PROP,
            {
                "kind": "landmark",
                "name": name,
                "normalized": [float(normalized[0]), float(normalized[1])],
                "location": _vector_list(location),
                "note": str(item.get("note") or ""),
            },
        )
        landmark_positions[name] = location
        created_landmarks.append({"name": name, "object": empty.name, "location": location, "normalized": normalized})
        landmark_brief.append(f"{name} at normalized image coordinate ({normalized[0]:.3f}, {normalized[1]:.3f})")

    curve_brief = []
    for index, item in enumerate(curves[:64], 1):
        if not isinstance(item, dict):
            continue
        raw_points = list(item.get("points") or [])
        if len(raw_points) < 2:
            continue
        name = _safe_label(item.get("name"), f"curve_{index}")
        color = _as_color(item.get("color"), (0.1, 0.55, 1.0, 1.0))
        material = _material_for_color(f"{collection.name} {name} Material", color)
        points = [map_point(point, y_offset=-0.004 * index) for point in raw_points[:512]]
        obj = _create_poly_curve_object(
            context,
            name=f"{collection.name} Curve {name}",
            points=points,
            material=material,
            bevel_depth=float(item.get("bevel_depth", 0.006) or 0.006),
            cyclic=bool(item.get("cyclic", False)),
        )
        move_to_collection(obj)
        normalized_points = [[float(value) for value in normalize(point)] for point in raw_points[:512]]
        obj["reference_guide_kind"] = "curve"
        obj["reference_guide_name"] = name
        _set_json_prop(
            obj,
            REFERENCE_GUIDE_METADATA_PROP,
            {
                "kind": "curve",
                "name": name,
                "normalized_points": normalized_points,
                "point_count": len(points),
                "cyclic": bool(item.get("cyclic", False)),
            },
        )
        created_curves.append({"name": name, "object": obj.name, "point_count": len(points), "cyclic": bool(item.get("cyclic", False))})
        curve_brief.append(f"{name} guide with {len(points)} point(s)" + (" closed" if item.get("cyclic") else ""))

    mass_brief = []
    for index, item in enumerate(masses[:64], 1):
        if not isinstance(item, dict):
            continue
        center = item.get("center")
        radius = item.get("radius", item.get("radii"))
        if center is None or radius is None:
            continue
        rx, ry = _as_float_pair(radius, (0.1, 0.1))
        if str(coordinate_space or "normalized").strip().lower() == "pixel":
            rx = rx / image_width
            ry = ry / image_height
        rx = max(0.001, min(1.0, float(rx)))
        ry = max(0.001, min(1.0, float(ry)))
        name = _safe_label(item.get("name"), f"mass_{index}")
        color = _as_color(item.get("color"), (0.1, 0.9, 0.45, 1.0))
        material = _material_for_color(f"{collection.name} {name} Mass Material", color)
        cx, cy = normalize(center)
        ellipse = [
            map_point((cx + math.cos(step / 64.0 * math.tau) * rx, cy + math.sin(step / 64.0 * math.tau) * ry))
            for step in range(64)
        ]
        obj = _create_poly_curve_object(
            context,
            name=f"{collection.name} Mass {name}",
            points=ellipse,
            material=material,
            bevel_depth=float(item.get("bevel_depth", 0.005) or 0.005),
            cyclic=True,
        )
        move_to_collection(obj)
        obj["reference_guide_kind"] = "mass"
        obj["reference_guide_name"] = name
        _set_json_prop(
            obj,
            REFERENCE_GUIDE_METADATA_PROP,
            {
                "kind": "mass",
                "name": name,
                "center": [float(cx), float(cy)],
                "radius": [float(rx), float(ry)],
                "point_count": len(ellipse),
            },
        )
        created_masses.append({"name": name, "object": obj.name, "center": (cx, cy), "radius": (rx, ry)})
        mass_brief.append(f"{name} mass centered at ({cx:.3f}, {cy:.3f}) with normalized radius ({rx:.3f}, {ry:.3f})")

    measurement_brief = []
    for index, item in enumerate(measurements[:64], 1):
        if not isinstance(item, dict):
            continue
        name = _safe_label(item.get("name"), f"measurement_{index}")
        start = None
        end = None
        if item.get("from") in landmark_positions:
            start = landmark_positions[item.get("from")]
        if item.get("to") in landmark_positions:
            end = landmark_positions[item.get("to")]
        if start is None and item.get("from_point") is not None:
            start = map_point(item.get("from_point"))
        if end is None and item.get("to_point") is not None:
            end = map_point(item.get("to_point"))
        if start is None or end is None:
            continue
        color = _as_color(item.get("color"), (1.0, 0.25, 0.25, 1.0))
        material = _material_for_color(f"{collection.name} {name} Measurement Material", color)
        obj = _create_poly_curve_object(
            context,
            name=f"{collection.name} Measurement {name}",
            points=[start, end],
            material=material,
            bevel_depth=float(item.get("bevel_depth", 0.004) or 0.004),
            cyclic=False,
        )
        move_to_collection(obj)
        distance = (Vector(end) - Vector(start)).length
        obj["reference_guide_kind"] = "measurement"
        obj["reference_guide_name"] = name
        _set_json_prop(
            obj,
            REFERENCE_GUIDE_METADATA_PROP,
            {
                "kind": "measurement",
                "name": name,
                "from": str(item.get("from") or ""),
                "to": str(item.get("to") or ""),
                "distance": float(distance),
                "start": _vector_list(start),
                "end": _vector_list(end),
            },
        )
        created_measurements.append({"name": name, "object": obj.name, "distance": distance})
        measurement_brief.append(f"{name} guide distance {distance:.3f} Blender units")

    if not any([image_plane, created_landmarks, created_curves, created_masses, created_measurements]):
        created_collection_name = collection.name
        bpy.data.collections.remove(collection)
        transaction["before_state"].pop(f"created:collection:{created_collection_name}", None)
        if created_collection_name in transaction.get("changed_data_blocks", []):
            transaction["changed_data_blocks"].remove(created_collection_name)
        if not had_pending_transaction:
            live_preview.revert(context)
        return {"ok": False, "message": "No reference guides were created; supply an image path, landmarks, curves, masses, or measurements"}

    reference_brief_seed = {
        "subject": str(subject or "reference model"),
        "source_notes": [f"Guide collection {collection.name} generated from {coordinate_space} image coordinates."],
        "silhouette": curve_brief,
        "primary_masses": mass_brief,
        "secondary_forms": [],
        "landmarks": landmark_brief,
        "proportion_checks": measurement_brief,
        "surface_cues": [],
        "negative_constraints": ["Sculpt/model against guide curves and landmarks before adding surface detail."],
        "inspection_views": ["front", "side"],
    }
    _set_json_prop(collection, "reference_brief_seed_json", reference_brief_seed)
    transaction["applied_steps"].append(
        {
            "type": "create_reference_modeling_guides",
            "label": label,
            "collection": collection.name,
            "image_plane": image_plane.name if image_plane else "",
            "landmarks": [item["name"] for item in created_landmarks],
            "curves": [item["name"] for item in created_curves],
            "masses": [item["name"] for item in created_masses],
            "measurements": [item["name"] for item in created_measurements],
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Created reference modeling guides in {collection.name}",
        "collection": collection.name,
        "image_plane": image_plane.name if image_plane else "",
        "coordinate_space": str(coordinate_space or "normalized").strip().lower(),
        "image_size": [image_width, image_height],
        "reference_identity": reference_image,
        "plane": {"width": plane_width, "height": plane_height, "location": list(_coerce_vector(plane_location, (0.0, 0.0, 1.5)))},
        "landmarks": created_landmarks,
        "curves": created_curves,
        "masses": created_masses,
        "measurements": created_measurements,
        "reference_brief_seed": reference_brief_seed,
        "transaction_id": transaction["id"],
    }

def _create_reference_guide_camera(
    context,
    *,
    collection,
    plane,
    camera_name,
    camera_margin,
    image_aspect,
    activate_camera,
):
    plane_location = _coerce_vector(
        plane.get("location"), (0.0, 0.0, 1.5)
    )
    plane_height = max(0.01, float(plane.get("height") or 3.0))
    margin = max(0.0, min(1.0, float(camera_margin or 0.0)))
    distance = max(1.0, plane_height * 2.0)
    target = Vector(plane_location)
    location = Vector(
        (plane_location[0], plane_location[1] - distance, plane_location[2])
    )

    data = bpy.data.cameras.new(
        _safe_label(camera_name, f"{collection.name} Reference Camera")
    )
    data.type = "ORTHO"
    data.ortho_scale = plane_height * (1.0 + margin * 2.0)
    data.clip_start = max(0.001, distance / 1000.0)
    data.clip_end = max(100.0, distance * 10.0)
    data.show_passepartout = True
    data.passepartout_alpha = 0.85
    camera = bpy.data.objects.new(data.name, data)
    camera.location = location
    camera.rotation_euler = (target - location).to_track_quat("-Z", "Y").to_euler()
    collection.objects.link(camera)
    live_preview._record_created_id("object", camera.name)
    live_preview._record_created_id("camera", data.name)
    if activate_camera:
        live_preview._record_scene_camera(context.scene)
        context.scene.camera = camera

    camera["reference_guide_kind"] = "camera"
    camera["reference_guide_name"] = "reference_camera"
    camera_meta = {
        "kind": "camera",
        "name": "reference_camera",
        "camera_type": "ORTHO",
        "location": _vector_list(camera.location),
        "rotation": [
            float(camera.rotation_euler[0]),
            float(camera.rotation_euler[1]),
            float(camera.rotation_euler[2]),
        ],
        "target": _vector_list(target),
        "ortho_scale": float(data.ortho_scale),
        "margin": margin,
        "image_aspect": float(image_aspect),
        "active": bool(activate_camera),
    }
    _set_json_prop(camera, REFERENCE_GUIDE_METADATA_PROP, camera_meta)
    return {"object": camera.name, **camera_meta}


def _reference_render_resolution(image_size, *, max_axis=4096):
    width = max(1.0, float(image_size[0]))
    height = max(1.0, float(image_size[1]))
    scale = min(1.0, float(max_axis) / max(width, height))
    return [
        max(1, int(round(width * scale))),
        max(1, int(round(height * scale))),
    ]


def create_reference_guides_from_annotations(
    context,
    *,
    image_path,
    annotations=None,
    annotations_json="",
    annotations_path="",
    default_coordinate_space="pixel",
    default_origin="top_left",
    subject="",
    collection_name="Reference Annotation Guides",
    plane_height=3.0,
    plane_location=(0.0, 0.0, 1.5),
    guide_offset_y=-0.02,
    include_image_plane=True,
    image_alpha=0.35,
    create_camera=True,
    camera_name="Reference Annotation Camera",
    camera_margin=0.05,
    activate_camera=True,
    match_render_aspect=True,
    label="Create reference guides from annotations",
):
    """Create a calibrated guide scene from a reference image and annotation JSON."""

    if not str(image_path or "").strip():
        return {"ok": False, "message": "image_path is required"}
    expanded_image_path = os.path.abspath(
        os.path.expanduser(str(image_path).strip())
    )
    if not os.path.isfile(expanded_image_path):
        return {
            "ok": False,
            "message": f"Reference image path does not exist: {expanded_image_path}",
        }

    try:
        document, annotation_source = (
            reference_annotations.load_annotation_document(
                annotations=annotations,
                annotations_json=annotations_json,
                annotations_path=annotations_path,
            )
        )
    except reference_annotations.ReferenceAnnotationError as exc:
        return {"ok": False, "message": str(exc)}

    existing_image = _loaded_image_for_path(expanded_image_path)
    loaded_image = existing_image
    try:
        if loaded_image is None:
            loaded_image = bpy.data.images.load(
                expanded_image_path, check_existing=True
            )
        reference_image_size = [
            float(loaded_image.size[0]),
            float(loaded_image.size[1]),
        ]
        if reference_image_size[0] <= 0.0 or reference_image_size[1] <= 0.0:
            raise ValueError("image dimensions are empty")
    except Exception as exc:
        if existing_image is None:
            _remove_unused_image(loaded_image)
        return {
            "ok": False,
            "message": (
                f"Could not load reference image {expanded_image_path}: "
                f"{type(exc).__name__}: {exc}"
            ),
        }

    try:
        normalized = reference_annotations.normalize_annotation_document(
            document,
            reference_image_size=reference_image_size,
            default_coordinate_space=default_coordinate_space,
            default_origin=default_origin,
        )
    except reference_annotations.ReferenceAnnotationError as exc:
        if existing_image is None:
            _remove_unused_image(loaded_image)
        return {"ok": False, "message": str(exc)}

    resolved_subject = (
        str(subject or "").strip()
        or normalized.get("subject")
        or "reference model"
    )
    result = create_reference_modeling_guides(
        context,
        image_path=expanded_image_path,
        image_size=reference_image_size,
        coordinate_space="normalized",
        subject=resolved_subject,
        collection_name=collection_name,
        plane_height=plane_height,
        plane_location=plane_location,
        guide_offset_y=guide_offset_y,
        include_image_plane=include_image_plane,
        image_alpha=image_alpha,
        landmarks=normalized["landmarks"],
        curves=normalized["curves"],
        masses=normalized["masses"],
        measurements=normalized["measurements"],
        label=label,
        _loaded_image=loaded_image,
        _owns_loaded_image=existing_image is None,
    )
    if not result.get("ok"):
        if existing_image is None:
            _remove_unused_image(loaded_image)
        return result

    collection = bpy.data.collections.get(result["collection"])
    if collection is None:
        return {
            "ok": False,
            "message": "Reference guide collection was not available after creation",
        }
    plane = dict(result.get("plane") or {})
    plane_width = max(0.01, float(plane.get("width") or 1.0))
    calibrated_plane_height = max(0.01, float(plane.get("height") or 1.0))
    location = _coerce_vector(plane.get("location"), plane_location)
    image_aspect = reference_image_size[0] / reference_image_size[1]
    annotation_rect = normalized["image_rect"]
    source_unit_width = annotation_rect[2]
    source_unit_height = annotation_rect[3]
    calibration = {
        "schema_version": normalized["schema_version"],
        "source_coordinate_space": normalized["source_coordinate_space"],
        "source_origin": normalized["source_origin"],
        "reference_image_size": list(reference_image_size),
        "annotation_size": list(normalized["annotation_size"]),
        "image_rect": list(annotation_rect),
        "plane": dict(plane),
        "plane_bounds": {
            "x": [
                float(location[0] - plane_width * 0.5),
                float(location[0] + plane_width * 0.5),
            ],
            "y": float(location[1]),
            "z": [
                float(location[2] - calibrated_plane_height * 0.5),
                float(location[2] + calibrated_plane_height * 0.5),
            ],
        },
        "world_units_per_reference_pixel": [
            plane_width / reference_image_size[0],
            calibrated_plane_height / reference_image_size[1],
        ],
        "world_units_per_annotation_unit": [
            plane_width / source_unit_width,
            calibrated_plane_height / source_unit_height,
        ],
        "normalized_mapping": (
            "world_x=center_x+(u-0.5)*plane_width; "
            "world_y=center_y+guide_offset_y; "
            "world_z=center_z+(0.5-v)*plane_height"
        ),
    }

    camera = {}
    if create_camera:
        render_resolution = _reference_render_resolution(reference_image_size)
        if match_render_aspect:
            _record_scene_render(context.scene)
            context.scene.render.resolution_x = render_resolution[0]
            context.scene.render.resolution_y = render_resolution[1]
            context.scene.render.pixel_aspect_x = 1.0
            context.scene.render.pixel_aspect_y = 1.0
        camera = _create_reference_guide_camera(
            context,
            collection=collection,
            plane=plane,
            camera_name=camera_name,
            camera_margin=camera_margin,
            image_aspect=image_aspect,
            activate_camera=activate_camera,
        )
        camera["render_resolution"] = list(render_resolution)
        camera["render_aspect"] = render_resolution[0] / render_resolution[1]
        camera["render_pixel_aspect"] = [1.0, 1.0]
        camera["render_aspect_matched"] = bool(match_render_aspect)
        camera_object = bpy.data.objects.get(camera.get("object", ""))
        if camera_object is not None:
            _set_json_prop(
                camera_object, REFERENCE_GUIDE_METADATA_PROP, camera
            )
        calibration["camera"] = dict(camera)

    collection_meta = (
        _get_json_prop(collection, REFERENCE_GUIDE_METADATA_PROP, {}) or {}
    )
    collection_meta["annotation_pipeline"] = {
        "source": dict(annotation_source),
        "counts": dict(normalized["counts"]),
        "clamped_point_count": int(normalized["clamped_point_count"]),
        "warnings": list(normalized["warnings"]),
        "calibration": calibration,
    }
    _set_json_prop(collection, REFERENCE_GUIDE_METADATA_PROP, collection_meta)
    collection["reference_annotation_schema_version"] = int(
        normalized["schema_version"]
    )
    collection["reference_annotation_sha256"] = annotation_source["sha256"]
    collection["reference_annotation_source_kind"] = annotation_source["kind"]

    reference_brief_seed = dict(result.get("reference_brief_seed") or {})
    source_notes = list(reference_brief_seed.get("source_notes") or [])
    source_notes.append(
        "Annotation schema "
        f"v{normalized['schema_version']} digest "
        f"{annotation_source['sha256'][:12]} calibrated from "
        f"{normalized['source_coordinate_space']} coordinates with "
        f"{normalized['source_origin']} origin."
    )
    reference_brief_seed["source_notes"] = source_notes
    _set_json_prop(collection, "reference_brief_seed_json", reference_brief_seed)

    transaction = live_preview.current_transaction()
    if transaction:
        transaction["applied_steps"].append(
            {
                "type": "create_reference_guides_from_annotations",
                "label": label,
                "collection": collection.name,
                "annotation_sha256": annotation_source["sha256"],
                "camera": camera.get("object", ""),
            }
        )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    result.update(
        {
            "message": (
                f"Created calibrated reference guides in {collection.name} "
                f"from annotation digest {annotation_source['sha256'][:12]}"
            ),
            "annotation_source": annotation_source,
            "annotation_summary": {
                "schema_version": normalized["schema_version"],
                "counts": dict(normalized["counts"]),
                "clamped_point_count": normalized["clamped_point_count"],
                "warnings": list(normalized["warnings"]),
            },
            "calibration": calibration,
            "camera": camera,
            "reference_brief_seed": reference_brief_seed,
        }
    )
    return result


def _curve_spline_point_count(obj):
    data = getattr(obj, "data", None)
    if not data or getattr(obj, "type", "") != "CURVE":
        return 0
    return sum(len(getattr(spline, "points", []) or []) for spline in data.splines)

def _curve_world_points(obj, *, max_points):
    data = getattr(obj, "data", None)
    if not data or getattr(obj, "type", "") != "CURVE":
        return []
    points = []
    matrix = obj.matrix_world
    for spline in data.splines:
        for point in spline.points:
            world = matrix @ Vector((float(point.co[0]), float(point.co[1]), float(point.co[2])))
            points.append(_vector_list(world))
            if len(points) >= max_points:
                return points
    return points

def _reference_collection_matches(collection, collection_name):
    if collection_name:
        return collection.name == collection_name
    if bool(collection.get("reference_modeling_guides", False)):
        return True
    for obj in collection.objects:
        if obj.get("reference_guide_kind") or obj.get("reference_landmark_name"):
            return True
    return False

def _inspect_reference_collection(collection, *, include_points, max_points_per_curve):
    collection_meta = _get_json_prop(collection, REFERENCE_GUIDE_METADATA_PROP, {}) or {}
    result = {
        "collection": collection.name,
        "subject": str(collection.get("reference_guide_subject") or collection_meta.get("subject") or ""),
        "coordinate_space": str(collection_meta.get("coordinate_space") or ""),
        "image_size": list(collection_meta.get("image_size") or []),
        "plane": dict(collection_meta.get("plane") or {}),
        "annotation_pipeline": dict(collection_meta.get("annotation_pipeline") or {}),
        "object_count": len(collection.objects),
        "image_plane": "",
        "camera": "",
        "cameras": [],
        "landmarks": [],
        "landmarks_3d": [],
        "curves": [],
        "masses": [],
        "measurements": [],
        "reconstruction_rays": [],
        "unclassified": [],
        "reference_brief_seed": _get_json_prop(collection, "reference_brief_seed_json", {}) or {},
    }
    for obj in sorted(collection.objects, key=lambda item: item.name):
        kind = str(obj.get("reference_guide_kind") or "").strip()
        meta = _get_json_prop(obj, REFERENCE_GUIDE_METADATA_PROP, {}) or {}
        if not kind and obj.get("reference_landmark_name"):
            kind = "landmark"
        name = str(obj.get("reference_guide_name") or meta.get("name") or obj.name)
        item = {"name": name, "object": obj.name, "type": obj.type}
        if kind == "image_plane":
            result["image_plane"] = obj.name
            item.update({
                "image_path": str(meta.get("image_path") or ""),
                "image_size": list(meta.get("image_size") or []),
                "plane": dict(meta.get("plane") or {}),
            })
            result.setdefault("image_planes", []).append(item)
        elif kind == "camera":
            item.update(
                {
                    "camera_type": str(meta.get("camera_type") or ""),
                    "location": _vector_list(obj.location),
                    "rotation": [
                        float(obj.rotation_euler[0]),
                        float(obj.rotation_euler[1]),
                        float(obj.rotation_euler[2]),
                    ],
                    "target": list(meta.get("target") or []),
                    "ortho_scale": float(meta.get("ortho_scale") or 0.0),
                    "margin": float(meta.get("margin") or 0.0),
                    "image_aspect": float(meta.get("image_aspect") or 0.0),
                    "render_resolution": list(
                        meta.get("render_resolution") or []
                    ),
                    "render_aspect": float(
                        meta.get("render_aspect") or 0.0
                    ),
                    "render_pixel_aspect": list(
                        meta.get("render_pixel_aspect") or []
                    ),
                    "render_aspect_matched": bool(
                        meta.get("render_aspect_matched", False)
                    ),
                    "active": bool(meta.get("active", False)),
                }
            )
            result["camera"] = obj.name
            result["cameras"].append(item)
        elif kind == "landmark":
            normalized = meta.get("normalized", obj.get("reference_landmark_normalized", []))
            item.update(
                {
                    "normalized": [float(value) for value in list(normalized or [])[:2]],
                    "location": _vector_list(obj.location),
                    "note": str(meta.get("note") or obj.get("reference_landmark_note") or ""),
                }
            )
            result["landmarks"].append(item)
        elif kind == "landmark_3d":
            item.update(
                {
                    "location": _vector_list(obj.matrix_world.translation),
                    "views": list(meta.get("views") or []),
                    "rms_residual": float(meta.get("rms_residual") or 0.0),
                    "max_residual": float(meta.get("max_residual") or 0.0),
                    "largest_ray_angle_degrees": float(
                        meta.get("largest_ray_angle_degrees") or 0.0
                    ),
                    "confidence": str(meta.get("confidence") or ""),
                }
            )
            result["landmarks_3d"].append(item)
        elif kind == "curve":
            item.update(
                {
                    "point_count": int(meta.get("point_count") or _curve_spline_point_count(obj)),
                    "cyclic": bool(meta.get("cyclic", False)),
                    "normalized_points": list(meta.get("normalized_points") or []),
                }
            )
            if include_points:
                item["world_points"] = _curve_world_points(obj, max_points=max_points_per_curve)
            result["curves"].append(item)
        elif kind == "mass":
            item.update(
                {
                    "center": list(meta.get("center") or []),
                    "radius": list(meta.get("radius") or []),
                    "point_count": int(meta.get("point_count") or _curve_spline_point_count(obj)),
                }
            )
            if include_points:
                item["world_points"] = _curve_world_points(obj, max_points=max_points_per_curve)
            result["masses"].append(item)
        elif kind == "measurement":
            item.update(
                {
                    "from": str(meta.get("from") or ""),
                    "to": str(meta.get("to") or ""),
                    "distance": float(meta.get("distance") or 0.0),
                    "start": list(meta.get("start") or []),
                    "end": list(meta.get("end") or []),
                }
            )
            if include_points:
                item["world_points"] = _curve_world_points(obj, max_points=max_points_per_curve)
            result["measurements"].append(item)
        elif kind == "reconstruction_ray":
            item["view"] = str(obj.get("reference_view_name") or "")
            if include_points:
                item["world_points"] = _curve_world_points(
                    obj,
                    max_points=max_points_per_curve,
                )
            result["reconstruction_rays"].append(item)
        else:
            result["unclassified"].append(item)
    return result

def inspect_reference_modeling_guides(
    context,
    *,
    collection_name="",
    include_points=False,
    max_points_per_curve=32,
    max_collections=8,
):
    """Inspect reference guide collections and return script-handoff-friendly metadata."""

    del context
    target_name = str(collection_name or "").strip()
    matched = []
    for collection in bpy.data.collections:
        if _reference_collection_matches(collection, target_name):
            matched.append(collection)
            if len(matched) >= max(1, int(max_collections or 8)):
                break
    if not matched:
        return {
            "ok": False,
            "message": f"No reference modeling guide collection found{f' named {target_name}' if target_name else ''}",
            "collections": [],
        }
    collections = [
        _inspect_reference_collection(
            collection,
            include_points=bool(include_points),
            max_points_per_curve=max(2, min(512, int(max_points_per_curve or 32))),
        )
        for collection in matched
    ]
    totals = {
        "collections": len(collections),
        "cameras": sum(len(item["cameras"]) for item in collections),
        "landmarks": sum(len(item["landmarks"]) for item in collections),
        "landmarks_3d": sum(len(item["landmarks_3d"]) for item in collections),
        "curves": sum(len(item["curves"]) for item in collections),
        "masses": sum(len(item["masses"]) for item in collections),
        "measurements": sum(len(item["measurements"]) for item in collections),
        "reconstruction_rays": sum(
            len(item["reconstruction_rays"]) for item in collections
        ),
    }
    return {
        "ok": True,
        "message": f"Inspected {totals['collections']} reference guide collection(s)",
        "totals": totals,
        "collections": collections,
    }
