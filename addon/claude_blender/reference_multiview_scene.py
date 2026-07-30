"""Blender scene construction for calibrated multi-view reference guides."""

from __future__ import annotations

import json
import math
import os

import bpy
from mathutils import Matrix, Vector

from . import live_preview, reference_guides, reference_multiview
from .advanced_support import _record_scene_render


REFERENCE_GUIDE_METADATA_PROP = "reference_guide_metadata_json"
MAX_VIEWS = 6


def _json_prop(data_block, key, value):
    try:
        data_block[key] = json.dumps(value, ensure_ascii=True, sort_keys=True)
    except Exception:
        data_block[key] = "{}"


def _safe_name(value, fallback):
    text = " ".join(str(value or "").strip().split())
    return (text or fallback)[:120]


def _finite_float(value, default, *, minimum=None, maximum=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if not math.isfinite(number):
        number = float(default)
    if minimum is not None:
        number = max(float(minimum), number)
    if maximum is not None:
        number = min(float(maximum), number)
    return number


def _finite_vector3(value, default):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise reference_multiview.MultiViewCalibrationError(
            "subject_center must contain three numbers"
        )
    return tuple(
        _finite_float(
            component,
            default[index],
            minimum=-10000.0,
            maximum=10000.0,
        )
        for index, component in enumerate(value)
    )


def _scene_inventory():
    return {
        "objects": set(bpy.data.objects.keys()),
        "collections": set(bpy.data.collections.keys()),
        "curves": set(bpy.data.curves.keys()),
        "meshes": set(bpy.data.meshes.keys()),
        "cameras": set(bpy.data.cameras.keys()),
        "materials": set(bpy.data.materials.keys()),
        "images": set(bpy.data.images.keys()),
    }


def _cleanup_since(inventory):
    for name in list(bpy.data.objects.keys()):
        if name not in inventory["objects"]:
            try:
                bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
            except Exception:
                pass
    for name in list(bpy.data.collections.keys()):
        if name not in inventory["collections"]:
            try:
                bpy.data.collections.remove(bpy.data.collections[name])
            except Exception:
                pass
    for collection_name, data_blocks in (
        ("curves", bpy.data.curves),
        ("meshes", bpy.data.meshes),
        ("cameras", bpy.data.cameras),
        ("materials", bpy.data.materials),
        ("images", bpy.data.images),
    ):
        for name in list(data_blocks.keys()):
            if name not in inventory[collection_name]:
                try:
                    data_blocks.remove(data_blocks[name])
                except Exception:
                    pass


def _validate_views(views, active_view):
    if not isinstance(views, list) or not 2 <= len(views) <= MAX_VIEWS:
        raise reference_multiview.MultiViewCalibrationError(
            f"views must contain between 2 and {MAX_VIEWS} calibrated view objects"
        )
    prepared = []
    seen = set()
    for index, raw in enumerate(views):
        if not isinstance(raw, dict):
            raise reference_multiview.MultiViewCalibrationError(
                f"views[{index}] must be an object"
            )
        name = _safe_name(raw.get("name"), f"view_{index + 1}")
        canonical = name.casefold()
        if canonical in seen:
            raise reference_multiview.MultiViewCalibrationError(
                f"view names must be unique: {name}"
            )
        seen.add(canonical)
        image_path = os.path.abspath(
            os.path.expanduser(str(raw.get("image_path") or "").strip())
        )
        if not image_path or not os.path.isfile(image_path):
            raise reference_multiview.MultiViewCalibrationError(
                f"views[{index}].image_path does not exist: {image_path}"
            )
        annotation_sources = sum(
            (
                raw.get("annotations") is not None,
                bool(str(raw.get("annotations_json") or "").strip()),
                bool(str(raw.get("annotations_path") or "").strip()),
            )
        )
        if annotation_sources != 1:
            raise reference_multiview.MultiViewCalibrationError(
                f"views[{index}] must supply exactly one annotation source"
            )
        axis = str(raw.get("axis") or "").strip().upper()
        basis = reference_multiview.view_basis(
            axis,
            view_direction=raw.get("view_direction"),
            up_direction=raw.get("up_direction"),
        )
        prepared.append(
            {
                **raw,
                "name": name,
                "image_path": image_path,
                "axis": axis,
                "basis": basis,
                "plane_height": _finite_float(
                    raw.get("plane_height"),
                    3.0,
                    minimum=0.01,
                    maximum=100.0,
                ),
                "camera_margin": _finite_float(
                    raw.get("camera_margin"),
                    0.05,
                    minimum=0.0,
                    maximum=1.0,
                ),
            }
        )
    requested_active = str(active_view or "").strip()
    if requested_active and requested_active.casefold() not in seen:
        raise reference_multiview.MultiViewCalibrationError(
            f"active_view does not match a configured view: {requested_active}"
        )
    active = requested_active or prepared[0]["name"]
    for view in prepared:
        view["active"] = view["name"].casefold() == active.casefold()
    return prepared


def _basis_transform(center, basis):
    right, forward, up = (Vector(vector) for vector in basis)
    rotation = Matrix((right, forward, up)).transposed().to_4x4()
    center = Vector(center)
    return (
        Matrix.Translation(center)
        @ rotation
        @ Matrix.Translation(-center)
    )


def _attach_child_collection(master, child, scene):
    if master.children.get(child.name) is None:
        master.children.link(child)
    if scene.collection.children.get(child.name) is not None:
        scene.collection.children.unlink(child)


def _create_view_camera(
    context,
    collection,
    *,
    view_name,
    center,
    basis,
    plane_height,
    image_aspect,
    margin,
    render_resolution,
    active,
):
    right, forward, up = (Vector(vector) for vector in basis)
    center = Vector(center)
    distance = max(1.0, float(plane_height) * 2.0)
    location = center - forward * distance
    data = bpy.data.cameras.new(
        _safe_name(f"{collection.name} {view_name} Camera", "Reference Camera")
    )
    data.type = "ORTHO"
    data.ortho_scale = float(plane_height) * (1.0 + float(margin) * 2.0)
    data.clip_start = max(0.001, distance / 1000.0)
    data.clip_end = max(100.0, distance * 10.0)
    data.show_passepartout = True
    data.passepartout_alpha = 0.85
    camera = bpy.data.objects.new(data.name, data)
    collection.objects.link(camera)
    camera.location = location
    camera_rotation = Matrix((right, up, -forward)).transposed()
    camera.rotation_euler = camera_rotation.to_euler()
    live_preview._record_created_id("object", camera.name)
    live_preview._record_created_id("camera", data.name)
    camera["reference_guide_kind"] = "camera"
    camera["reference_guide_name"] = f"{view_name}_camera"
    camera["reference_view_name"] = view_name
    metadata = {
        "kind": "camera",
        "name": f"{view_name}_camera",
        "view": view_name,
        "camera_type": "ORTHO",
        "location": list(camera.location),
        "target": list(center),
        "ortho_scale": float(data.ortho_scale),
        "margin": float(margin),
        "image_aspect": float(image_aspect),
        "render_resolution": list(render_resolution),
        "render_aspect": float(render_resolution[0]) / max(
            1.0,
            float(render_resolution[1]),
        ),
        "render_pixel_aspect": [1.0, 1.0],
        "render_aspect_matched": True,
        "active": bool(active),
    }
    _json_prop(camera, REFERENCE_GUIDE_METADATA_PROP, metadata)
    return camera, metadata


def _create_connector(collection, name, start, end, landmark_name, view_name):
    curve = bpy.data.curves.new(f"{name} Data", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.002
    curve.bevel_resolution = 1
    spline = curve.splines.new("POLY")
    spline.points.add(1)
    spline.points[0].co = (*start, 1.0)
    spline.points[1].co = (*end, 1.0)
    obj = bpy.data.objects.new(name, curve)
    collection.objects.link(obj)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("curve", curve.name)
    obj.display_type = "WIRE"
    obj.hide_render = True
    obj["reference_guide_kind"] = "reconstruction_ray"
    obj["reference_guide_name"] = landmark_name
    obj["reference_view_name"] = view_name
    return obj


def create_multiview_reference_guides(
    context,
    *,
    views,
    subject="reference model",
    collection_name="Multi-View Reference Guides",
    subject_center=(0.0, 0.0, 1.5),
    active_view="",
    include_image_planes=True,
    image_alpha=0.35,
    guide_offset=-0.02,
    create_connectors=True,
    require_reconstruction=True,
    minimum_views_per_landmark=2,
    minimum_ray_angle_degrees=1.0,
    max_landmark_residual=0.1,
    match_render_aspect=True,
    label="Create multi-view reference guides",
):
    """Create calibrated per-view guides and reconstruct shared 3D landmarks."""
    try:
        prepared_views = _validate_views(views, active_view)
        center = _finite_vector3(subject_center, (0.0, 0.0, 1.5))
    except reference_multiview.MultiViewCalibrationError as exc:
        return {"ok": False, "code": "invalid_multiview_calibration", "message": str(exc)}

    inventory = _scene_inventory()
    had_pending_transaction = bool(
        live_preview.current_transaction()
        and live_preview.current_transaction().get("status") == "pending"
    )
    transaction = live_preview.begin(label, context)
    previous_step_count = len(transaction.get("applied_steps", []))
    previous_before_keys = set(transaction.get("before_state", {}))
    previous_changed_data_blocks = list(
        transaction.get("changed_data_blocks", [])
    )
    previous_scene_camera = context.scene.camera
    previous_render = {
        "resolution_x": context.scene.render.resolution_x,
        "resolution_y": context.scene.render.resolution_y,
        "resolution_percentage": context.scene.render.resolution_percentage,
        "pixel_aspect_x": context.scene.render.pixel_aspect_x,
        "pixel_aspect_y": context.scene.render.pixel_aspect_y,
    }
    view_results = []
    landmark_rays = {}
    reconstructed = []
    unresolved = []
    warnings = []
    master = None
    try:
        master = bpy.data.collections.new(
            _safe_name(collection_name, "Multi-View Reference Guides")
        )
        context.scene.collection.children.link(master)
        live_preview._record_created_id("collection", master.name)
        master["reference_multiview_guides"] = True
        master["reference_guide_subject"] = str(subject or "reference model")

        for view_index, view in enumerate(prepared_views):
            child_name = _safe_name(
                f"{master.name} {view['name']}",
                f"{master.name} View {view_index + 1}",
            )
            result = reference_guides.create_reference_guides_from_annotations(
                context,
                image_path=view["image_path"],
                annotations=view.get("annotations"),
                annotations_json=str(view.get("annotations_json") or ""),
                annotations_path=str(view.get("annotations_path") or ""),
                default_coordinate_space=str(
                    view.get("default_coordinate_space") or "pixel"
                ),
                default_origin=str(view.get("default_origin") or "top_left"),
                subject=str(subject or "reference model"),
                collection_name=child_name,
                plane_height=view["plane_height"],
                plane_location=center,
                guide_offset_y=_finite_float(
                    view.get("guide_offset"),
                    guide_offset,
                    minimum=-10.0,
                    maximum=10.0,
                ),
                include_image_plane=bool(
                    view.get("include_image_plane", include_image_planes)
                ),
                image_alpha=_finite_float(
                    view.get("image_alpha"),
                    image_alpha,
                    minimum=0.0,
                    maximum=1.0,
                ),
                create_camera=False,
                activate_camera=False,
                match_render_aspect=False,
                label=f"{label}: {view['name']}",
            )
            if not result.get("ok"):
                raise RuntimeError(
                    f"View {view['name']} failed: {result.get('message') or result}"
                )
            child = bpy.data.collections.get(result["collection"])
            if child is None:
                raise RuntimeError(
                    f"View collection disappeared after creation: {result['collection']}"
                )
            _attach_child_collection(master, child, context.scene)
            transform = _basis_transform(center, view["basis"])
            for obj in list(child.objects):
                obj.matrix_world = transform @ obj.matrix_world
                obj["reference_view_name"] = view["name"]
            child["reference_multiview_master"] = master.name
            child["reference_view_name"] = view["name"]
            child["reference_view_axis"] = view["axis"]
            image_size = list(result.get("image_size") or [1.0, 1.0])
            image_aspect = max(1.0e-9, float(image_size[0])) / max(
                1.0e-9,
                float(image_size[1]),
            )
            render_resolution = reference_guides._reference_render_resolution(
                image_size
            )
            camera, camera_metadata = _create_view_camera(
                context,
                child,
                view_name=view["name"],
                center=center,
                basis=view["basis"],
                plane_height=view["plane_height"],
                image_aspect=image_aspect,
                margin=view["camera_margin"],
                render_resolution=render_resolution,
                active=view["active"],
            )
            per_view_landmarks = {}
            for landmark in result.get("landmarks") or []:
                landmark_name = str(landmark.get("name") or "").strip()
                obj = bpy.data.objects.get(str(landmark.get("object") or ""))
                if not landmark_name or obj is None:
                    continue
                if landmark_name in per_view_landmarks:
                    warnings.append(
                        f"Duplicate landmark {landmark_name} in view {view['name']} was ignored"
                    )
                    continue
                origin = tuple(obj.matrix_world.translation)
                ray = {
                    "origin": origin,
                    "direction": view["basis"][1],
                    "view": view["name"],
                    "object": obj.name,
                }
                per_view_landmarks[landmark_name] = ray
                landmark_rays.setdefault(landmark_name, []).append(ray)
            view_metadata = {
                "name": view["name"],
                "axis": view["axis"],
                "basis": {
                    "right": list(view["basis"][0]),
                    "forward": list(view["basis"][1]),
                    "up": list(view["basis"][2]),
                },
                "center": list(center),
                "plane_height": view["plane_height"],
                "image_size": image_size,
                "image_aspect": image_aspect,
                "camera": camera.name,
                "camera_metadata": camera_metadata,
                "render_resolution": render_resolution,
                "collection": child.name,
                "landmark_count": len(per_view_landmarks),
                "annotation_source": dict(result.get("annotation_source") or {}),
                "active": bool(view["active"]),
            }
            _json_prop(child, "reference_multiview_calibration_json", view_metadata)
            view_results.append(view_metadata)

        minimum_views = max(
            2,
            min(
                len(prepared_views),
                int(minimum_views_per_landmark or 2),
            ),
        )
        residual_limit = _finite_float(
            max_landmark_residual,
            0.1,
            minimum=0.0,
            maximum=1000.0,
        )
        for landmark_name in sorted(landmark_rays):
            rays = landmark_rays[landmark_name]
            if len(rays) < minimum_views:
                unresolved.append(
                    {
                        "name": landmark_name,
                        "views": [ray["view"] for ray in rays],
                        "reason": (
                            f"requires at least {minimum_views} annotated views"
                        ),
                    }
                )
                continue
            try:
                reconstruction = reference_multiview.triangulate_rays(
                    rays,
                    minimum_angle_degrees=_finite_float(
                        minimum_ray_angle_degrees,
                        1.0,
                        minimum=0.0,
                        maximum=90.0,
                    ),
                )
            except reference_multiview.MultiViewCalibrationError as exc:
                unresolved.append(
                    {
                        "name": landmark_name,
                        "views": [ray["view"] for ray in rays],
                        "reason": str(exc),
                    }
                )
                continue
            empty = bpy.data.objects.new(
                _safe_name(
                    f"{master.name} 3D Landmark {landmark_name}",
                    f"{master.name} 3D Landmark",
                ),
                None,
            )
            master.objects.link(empty)
            live_preview._record_created_id("object", empty.name)
            empty.empty_display_type = "SPHERE"
            empty.empty_display_size = max(
                0.01,
                min(view["plane_height"] for view in prepared_views) * 0.02,
            )
            empty.location = reconstruction["point"]
            empty["reference_guide_kind"] = "landmark_3d"
            empty["reference_guide_name"] = landmark_name
            empty["reference_landmark_name"] = landmark_name
            confidence = (
                "within_residual_limit"
                if reconstruction["max_residual"] <= residual_limit
                else "high_residual"
            )
            metadata = {
                **reconstruction,
                "point": list(reconstruction["point"]),
                "confidence": confidence,
                "residual_limit": residual_limit,
            }
            _json_prop(empty, REFERENCE_GUIDE_METADATA_PROP, metadata)
            if confidence == "high_residual":
                warnings.append(
                    f"Landmark {landmark_name} has max residual "
                    f"{reconstruction['max_residual']:.4f}, above {residual_limit:.4f}"
                )
            connectors = []
            if create_connectors:
                for ray in rays:
                    connector = _create_connector(
                        master,
                        _safe_name(
                            f"{master.name} Ray {landmark_name} {ray['view']}",
                            "Reference Reconstruction Ray",
                        ),
                        ray["origin"],
                        reconstruction["point"],
                        landmark_name,
                        ray["view"],
                    )
                    connectors.append(connector.name)
            reconstructed.append(
                {
                    "name": landmark_name,
                    "object": empty.name,
                    "location": list(reconstruction["point"]),
                    "views": list(reconstruction["views"]),
                    "rms_residual": reconstruction["rms_residual"],
                    "max_residual": reconstruction["max_residual"],
                    "largest_ray_angle_degrees": reconstruction[
                        "largest_ray_angle_degrees"
                    ],
                    "confidence": confidence,
                    "connectors": connectors,
                }
            )

        if require_reconstruction and not reconstructed:
            reasons = "; ".join(
                f"{item['name']}: {item['reason']}" for item in unresolved[:8]
            )
            raise RuntimeError(
                "No shared landmark could be reconstructed"
                + (f": {reasons}" if reasons else "")
            )

        active_result = next(
            result for result in view_results if result["active"]
        )
        active_camera = bpy.data.objects.get(active_result["camera"])
        if active_camera is not None:
            live_preview._record_scene_camera(context.scene)
            context.scene.camera = active_camera
        if match_render_aspect:
            resolution = reference_guides._reference_render_resolution(
                active_result["image_size"]
            )
            _record_scene_render(context.scene)
            context.scene.render.resolution_x = resolution[0]
            context.scene.render.resolution_y = resolution[1]
            context.scene.render.pixel_aspect_x = 1.0
            context.scene.render.pixel_aspect_y = 1.0
            active_result["render_resolution"] = resolution

        master_metadata = {
            "subject": str(subject or "reference model"),
            "center": list(center),
            "views": view_results,
            "reconstructed_landmark_count": len(reconstructed),
            "unresolved_landmark_count": len(unresolved),
            "active_view": active_result["name"],
        }
        _json_prop(master, REFERENCE_GUIDE_METADATA_PROP, master_metadata)
        transaction["applied_steps"].append(
            {
                "type": "create_multiview_reference_guides",
                "label": label,
                "collection": master.name,
                "views": [result["name"] for result in view_results],
                "landmarks_3d": [item["name"] for item in reconstructed],
            }
        )
        live_preview.redraw(context)
        live_preview._mark_pending(context, label)
        return {
            "ok": True,
            "message": (
                f"Created {len(view_results)} calibrated reference views and "
                f"{len(reconstructed)} reconstructed 3D landmarks"
            ),
            "collection": master.name,
            "views": view_results,
            "landmarks_3d": reconstructed,
            "unresolved_landmarks": unresolved,
            "warnings": warnings,
            "active_view": active_result["name"],
            "transaction_id": transaction["id"],
        }
    except Exception as exc:
        _cleanup_since(inventory)
        context.scene.camera = (
            previous_scene_camera
            if previous_scene_camera is None
            or bpy.data.objects.get(previous_scene_camera.name) is not None
            else None
        )
        for name, value in previous_render.items():
            setattr(context.scene.render, name, value)
        transaction["applied_steps"] = transaction.get("applied_steps", [])[
            :previous_step_count
        ]
        transaction["changed_data_blocks"] = previous_changed_data_blocks
        for key in list(transaction.get("before_state", {})):
            if key not in previous_before_keys:
                transaction["before_state"].pop(key, None)
        if not had_pending_transaction:
            try:
                live_preview.revert(context)
            except Exception:
                pass
        return {
            "ok": False,
            "code": "multiview_guide_creation_failed",
            "message": f"Could not create multi-view reference guides: {exc}",
            "warnings": warnings,
        }


def register():
    pass


def unregister():
    pass
