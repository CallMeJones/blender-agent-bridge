"""Diagnostic object render capture and MCP resource helpers."""

from __future__ import annotations

from array import array
import base64
import json
import math
import os
import time
import uuid

import bpy
import mathutils

from . import viewport_capture


LATEST_INSPECTION_RENDER_METADATA_URI = "blender://inspection-renders/latest/metadata"
METADATA_FILENAME = "metadata.json"
DEFAULT_VIEWS = ("front_below", "side")
VIEW_OFFSETS = {
    "front_below": (1.2, -0.8, -0.8),
    "underside": (0.0, -0.4, -1.2),
    "side": (1.4, 0.0, -0.2),
    "front": (0.0, -1.4, 0.1),
    "rear": (0.0, 1.4, 0.1),
    "top": (0.0, -0.2, 1.4),
}
RENDERABLE_OBJECT_TYPES = {"MESH", "CURVE", "FONT", "SURFACE", "META", "VOLUME", "POINTCLOUD"}
MAX_CONTACT_SHEET_IMAGES = 12


def _safe_id(value, fallback="item"):
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in str(value or ""))
    safe = safe.strip("._")
    return safe[:80] or fallback


def _render_id():
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _metadata_uri(render_id):
    return f"blender://inspection-renders/{render_id}/metadata"


def _image_resource_uri(render_id, image_id):
    return f"blender://inspection-renders/{render_id}/images/{_safe_id(image_id)}"


def _render_root_info(context=None, *, preferred_dir=None, create=False):
    capture_info = viewport_capture.resolve_capture_dir(context, preferred_dir=preferred_dir, create=create)
    root = os.path.join(capture_info["capture_dir"], "inspection-renders")
    if create:
        os.makedirs(root, exist_ok=True)
    return {**capture_info, "inspection_render_root": root}


def _render_dir_candidates(capture_dir=None, *, context=None, preferred_dir=None):
    if capture_dir:
        info = {
            "capture_dir": capture_dir,
            "storage_scope": "explicit",
            "project_id": viewport_capture.project_id(context),
            "session_id": viewport_capture.capture_session_id(),
            "base_dir": capture_dir,
            "fallback_reason": "",
        }
        return [{**info, "inspection_render_root": os.path.join(capture_dir, "inspection-renders")}]
    return [
        {**info, "inspection_render_root": os.path.join(info["capture_dir"], "inspection-renders")}
        for info in viewport_capture.capture_dir_candidates(context=context, preferred_dir=preferred_dir)
    ]


def _metadata_path(render_dir):
    return os.path.join(render_dir, METADATA_FILENAME)


def _write_metadata(metadata):
    path = metadata.get("metadata_path") or _metadata_path(metadata["render_dir"])
    temp_path = f"{path}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(metadata, handle, indent=2, sort_keys=True)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise
    return path


def begin_inspection_artifact(
    context,
    *,
    prefix="artifact",
    capture_dir=None,
):
    """Allocate a project/session-scoped directory for generated PNG evidence."""

    artifact_id = f"{_safe_id(prefix, 'artifact')}-{_render_id()}"
    capture_info = _render_root_info(
        context, preferred_dir=capture_dir, create=True
    )
    render_dir = os.path.join(
        capture_info["inspection_render_root"], artifact_id
    )
    os.makedirs(render_dir, exist_ok=False)
    return {
        "render_id": artifact_id,
        "render_dir": render_dir,
        "project_id": capture_info.get("project_id", ""),
        "session_id": capture_info.get("session_id", ""),
        "storage_scope": capture_info.get("storage_scope", ""),
        "capture_dir": capture_info.get("capture_dir", ""),
        "base_dir": capture_info.get("base_dir", ""),
        "fallback_reason": capture_info.get("fallback_reason", ""),
    }


def publish_inspection_artifact(
    artifact,
    *,
    images,
    metadata=None,
):
    """Publish existing PNG files through inspection-render MCP resources."""

    artifact = dict(artifact or {})
    render_id = _safe_id(artifact.get("render_id"), "")
    render_dir = os.path.abspath(str(artifact.get("render_dir") or ""))
    if not render_id or not render_dir or not os.path.isdir(render_dir):
        raise ValueError("A prepared inspection artifact directory is required")

    published_images = []
    for raw in list(images or [])[:32]:
        if not isinstance(raw, dict):
            continue
        image_id = _safe_id(raw.get("image_id"), "")
        path = os.path.abspath(str(raw.get("path") or ""))
        try:
            inside_artifact = (
                os.path.commonpath([render_dir, path]) == render_dir
            )
        except ValueError:
            inside_artifact = False
        if not image_id or not inside_artifact:
            raise ValueError(
                "Published inspection images must stay inside the artifact directory"
            )
        available = os.path.isfile(path)
        width, height = _image_size(path) if available else (0, 0)
        published_images.append(
            {
                **raw,
                "image_id": image_id,
                "path": path,
                "resource_uri": _image_resource_uri(render_id, image_id),
                "available": available,
                "size_bytes": os.path.getsize(path) if available else 0,
                "width": width,
                "height": height,
            }
        )

    available_images = [
        item for item in published_images if item.get("available")
    ]
    payload = {
        **artifact,
        **dict(metadata or {}),
        "ok": bool(available_images),
        "requested": True,
        "available": bool(available_images),
        "render_id": render_id,
        "render_dir": render_dir,
        "metadata_uri": _metadata_uri(render_id),
        "latest_metadata_uri": LATEST_INSPECTION_RENDER_METADATA_URI,
        "created_at": time.time(),
        "image_count": len(available_images),
        "requested_image_count": len(published_images),
        "images": published_images,
    }
    payload["metadata_path"] = _metadata_path(render_dir)
    _write_metadata(payload)
    return payload


def _read_metadata(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _metadata_candidates(capture_dir=None, *, context=None, preferred_dir=None):
    candidates = []
    for info in _render_dir_candidates(capture_dir, context=context, preferred_dir=preferred_dir):
        root = info["inspection_render_root"]
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            metadata_path = os.path.join(root, name, METADATA_FILENAME)
            if os.path.isfile(metadata_path):
                candidates.append((metadata_path, info))
    return candidates


def _metadata_for_id(render_id, capture_dir=None, *, context=None, preferred_dir=None):
    render_id = _safe_id(render_id, "")
    if not render_id:
        return None
    for info in _render_dir_candidates(capture_dir, context=context, preferred_dir=preferred_dir):
        metadata_path = os.path.join(info["inspection_render_root"], render_id, METADATA_FILENAME)
        if os.path.isfile(metadata_path):
            return _read_metadata(metadata_path)
    return None


def latest_inspection_render_metadata(capture_dir=None, *, context=None, preferred_dir=None):
    newest = []
    for metadata_path, _info in _metadata_candidates(capture_dir, context=context, preferred_dir=preferred_dir):
        try:
            metadata = _read_metadata(metadata_path)
        except (OSError, json.JSONDecodeError):
            continue
        newest.append((metadata.get("created_at", 0.0), os.path.getmtime(metadata_path), metadata))
    if newest:
        return max(newest, key=lambda item: (item[0], item[1]))[2]
    info = _render_root_info(context, preferred_dir=preferred_dir)
    return {
        "ok": False,
        "available": False,
        "project_id": info.get("project_id", ""),
        "session_id": info.get("session_id", ""),
        "storage_scope": info.get("storage_scope", ""),
        "metadata_uri": LATEST_INSPECTION_RENDER_METADATA_URI,
        "note": "No inspection render capture is available yet",
    }


def inspection_render_metadata(render_id, capture_dir=None, *, context=None, preferred_dir=None):
    metadata = _metadata_for_id(render_id, capture_dir, context=context, preferred_dir=preferred_dir)
    if metadata:
        return metadata
    info = _render_root_info(context, preferred_dir=preferred_dir)
    return {
        "ok": False,
        "available": False,
        "render_id": str(render_id or ""),
        "project_id": info.get("project_id", ""),
        "session_id": info.get("session_id", ""),
        "storage_scope": info.get("storage_scope", ""),
        "metadata_uri": _metadata_uri(render_id),
        "note": "Inspection render capture was not found for this Blender project/session",
    }


def inspection_render_image_resource(render_id, image_id, capture_dir=None, *, context=None, preferred_dir=None):
    metadata = _metadata_for_id(render_id, capture_dir, context=context, preferred_dir=preferred_dir)
    if not metadata:
        return None
    image_id = _safe_id(image_id, "")
    if not image_id:
        return None
    for image in metadata.get("images") or []:
        if str(image.get("image_id") or "") != image_id:
            continue
        path = image.get("path") or ""
        if not image.get("available") or not os.path.isfile(path):
            return None
        with open(path, "rb") as handle:
            data = base64.b64encode(handle.read()).decode("ascii")
        return {
            "mimeType": "image/png",
            "blob": data,
            "path": path,
            "renderId": metadata.get("render_id", ""),
            "imageId": image_id,
            "objectName": image.get("object", ""),
            "view": image.get("view", ""),
            "resourceUri": image.get("resource_uri", ""),
            "metadataUri": metadata.get("metadata_uri", ""),
            "sizeBytes": int(image.get("size_bytes", 0) or 0),
            "width": int(image.get("width", 0) or 0),
            "height": int(image.get("height", 0) or 0),
        }
    return None


def parse_inspection_render_resource_uri(uri):
    uri = str(uri or "")
    prefix = "blender://inspection-renders/"
    if not uri.startswith(prefix):
        return "", "", ""
    tail = uri[len(prefix) :]
    if tail == "latest/metadata":
        return "latest", "metadata", ""
    parts = tail.split("/")
    if len(parts) == 2 and parts[1] == "metadata":
        return _safe_id(parts[0], ""), "metadata", ""
    if len(parts) == 3 and parts[1] == "images":
        return _safe_id(parts[0], ""), "image", _safe_id(parts[2], "")
    return "", "", ""


def _iter_target_objects(obj):
    yield obj
    for child in obj.children_recursive:
        yield child


def _object_bounds(obj):
    corners = []
    for item in _iter_target_objects(obj):
        if getattr(item, "type", "") in {"MESH", "CURVE", "FONT", "SURFACE", "META"} and getattr(item, "bound_box", None):
            corners.extend(item.matrix_world @ mathutils.Vector(corner) for corner in item.bound_box)
    if not corners:
        center = obj.matrix_world.translation.copy()
        return center, 1.0
    min_v = mathutils.Vector((min(point.x for point in corners), min(point.y for point in corners), min(point.z for point in corners)))
    max_v = mathutils.Vector((max(point.x for point in corners), max(point.y for point in corners), max(point.z for point in corners)))
    center = (min_v + max_v) * 0.5
    radius = max((point - center).length for point in corners)
    return center, max(0.25, float(radius))


def _look_at(camera, target):
    direction = target - camera.location
    if direction.length <= 0.0001:
        direction = mathutils.Vector((0.0, 0.0, -1.0))
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _image_size(path):
    image = None
    try:
        image = bpy.data.images.load(path, check_existing=False)
        return int(image.size[0]), int(image.size[1])
    except Exception:
        return 0, 0
    finally:
        if image is not None:
            try:
                bpy.data.images.remove(image)
            except Exception:
                pass


def _contact_sheet_image(images, render_dir, render_id, *, columns=3):
    available = [item for item in images if item.get("available") and os.path.isfile(item.get("path", ""))]
    available = available[:MAX_CONTACT_SHEET_IMAGES]
    if len(available) < 2:
        return {}

    loaded = []
    sheet = None
    try:
        for item in available:
            loaded.append((item, bpy.data.images.load(item["path"], check_existing=False)))
        cell_width = max(int(image.size[0]) for _item, image in loaded)
        cell_height = max(int(image.size[1]) for _item, image in loaded)
        columns = max(1, min(int(columns), len(loaded)))
        rows = int(math.ceil(len(loaded) / float(columns)))
        width = cell_width * columns
        height = cell_height * rows
        if width > 16384 or height > 16384:
            return {"available": False, "note": "Contact sheet dimensions exceed Blender's safe image limit"}

        background = array("f", (0.04, 0.04, 0.04, 1.0)) * (width * height)
        for index, (_item, source) in enumerate(loaded):
            source_width = int(source.size[0])
            source_height = int(source.size[1])
            source_pixels = array("f", [0.0]) * (source_width * source_height * 4)
            source.pixels.foreach_get(source_pixels)
            column = index % columns
            row = index // columns
            offset_x = column * cell_width
            offset_y = (rows - row - 1) * cell_height
            for source_y in range(source_height):
                source_start = source_y * source_width * 4
                source_end = source_start + source_width * 4
                target_start = ((offset_y + source_y) * width + offset_x) * 4
                background[target_start : target_start + source_width * 4] = source_pixels[
                    source_start:source_end
                ]

        image_id = "contact-sheet"
        path = os.path.join(render_dir, f"{image_id}.png")
        sheet = bpy.data.images.new(
            f"Agent Bridge Contact Sheet {render_id}",
            width=width,
            height=height,
            alpha=True,
        )
        sheet.pixels.foreach_set(background)
        sheet.filepath_raw = path
        sheet.file_format = "PNG"
        sheet.save()
        return {
            "image_id": image_id,
            "object": ", ".join(dict.fromkeys(str(item.get("object") or "") for item in available)),
            "view": "contact_sheet",
            "path": path,
            "resource_uri": _image_resource_uri(render_id, image_id),
            "available": os.path.isfile(path),
            "size_bytes": os.path.getsize(path) if os.path.isfile(path) else 0,
            "width": width,
            "height": height,
            "source_image_ids": [str(item.get("image_id") or "") for item in available],
            "source_image_count": len(available),
            "partial": len(images) > len(available),
            "note": "",
        }
    except Exception as exc:
        return {
            "image_id": "contact-sheet",
            "view": "contact_sheet",
            "available": False,
            "note": f"Contact sheet creation failed: {type(exc).__name__}: {exc}",
        }
    finally:
        if sheet is not None:
            bpy.data.images.remove(sheet)
        for _item, image in loaded:
            if image.name in bpy.data.images:
                bpy.data.images.remove(image)


def _duration_label(seconds):
    try:
        seconds = int(round(float(seconds)))
    except (TypeError, ValueError):
        seconds = 0
    if seconds <= 0:
        return "unknown"
    if seconds < 90:
        return f"about {seconds}s"
    minutes = int(round(seconds / 60.0))
    return f"about {minutes} min"


def _estimated_render_seconds(image_count, resolution_x, resolution_y):
    try:
        count = max(1, int(image_count))
        width = max(64, int(resolution_x))
        height = max(64, int(resolution_y))
    except (TypeError, ValueError):
        count = 1
        width = 800
        height = 600
    megapixels = (width * height) / 1_000_000.0
    per_image = max(2.0, 3.0 * max(0.1, megapixels))
    return max(2, int(round(count * per_image)))


def _poll_interval_seconds(estimated_seconds):
    try:
        estimated = int(round(float(estimated_seconds)))
    except (TypeError, ValueError):
        estimated = 0
    if estimated <= 10:
        return 2
    if estimated <= 60:
        return 5
    return 10


def _view_list(views):
    if isinstance(views, str):
        requested = [views]
    elif isinstance(views, (list, tuple)):
        requested = [str(item) for item in views if str(item).strip()]
    else:
        requested = []
    normalized = []
    for item in requested or list(DEFAULT_VIEWS):
        key = item.strip().lower().replace("-", "_").replace(" ", "_")
        if key in {"under", "below", "bottom"}:
            key = "underside"
        if key in {"front_under", "front_below_3_4", "front_below_three_quarter"}:
            key = "front_below"
        if key not in VIEW_OFFSETS:
            continue
        if key not in normalized:
            normalized.append(key)
    return normalized or list(DEFAULT_VIEWS)


def _workbench_render_engine(scene):
    try:
        identifiers = {
            item.identifier
            for item in scene.render.bl_rna.properties["engine"].enum_items
        }
    except (AttributeError, KeyError, TypeError):
        return ""
    for candidate in ("BLENDER_WORKBENCH", "BLENDER_WORKBENCH_NEXT"):
        if candidate in identifiers:
            return candidate
    return ""


def _render_still_with_fallback(scene, *, render_callable=None):
    """Render once, retrying geometry evidence in Workbench when needed."""

    render_callable = render_callable or (lambda: bpy.ops.render.render(write_still=True))
    primary_engine = str(scene.render.engine)
    try:
        render_callable()
        return {
            "render_engine": primary_engine,
            "fallback_used": False,
            "primary_error": "",
        }
    except Exception as primary_error:  # noqa: BLE001 - preserve render evidence when Eevee/Cycles fails
        fallback_engine = _workbench_render_engine(scene)
        if not fallback_engine or fallback_engine == primary_engine:
            raise
        scene.render.engine = fallback_engine
        try:
            render_callable()
            return {
                "render_engine": fallback_engine,
                "fallback_used": True,
                "primary_error": f"{type(primary_error).__name__}: {primary_error}",
            }
        except Exception as fallback_error:  # noqa: BLE001 - combine both renderer failures for diagnostics
            raise RuntimeError(
                "Primary render failed (%s: %s); Workbench fallback failed (%s: %s)"
                % (
                    type(primary_error).__name__,
                    primary_error,
                    type(fallback_error).__name__,
                    fallback_error,
                )
            ) from fallback_error
        finally:
            scene.render.engine = primary_engine


def _create_inspection_lights(scene, camera_name):
    lights = []
    for suffix, energy in (("Key", 1200.0), ("Fill", 700.0), ("Rim", 900.0)):
        data = bpy.data.lights.new(
            f"{_safe_id(camera_name, 'Agent_Bridge_Inspection')}_{suffix}_Data",
            type="AREA",
        )
        data.energy = energy
        data.shape = "DISK"
        obj = bpy.data.objects.new(
            f"{_safe_id(camera_name, 'Agent_Bridge_Inspection')}_{suffix}",
            data,
        )
        scene.collection.objects.link(obj)
        lights.append(obj)
    return lights


def _position_inspection_lights(lights, center, radius):
    offsets = (
        mathutils.Vector((-1.4, -2.0, 1.8)),
        mathutils.Vector((1.8, -1.2, 0.8)),
        mathutils.Vector((0.2, 1.8, 2.0)),
    )
    distance = max(2.0, float(radius) * 3.0)
    area_size = max(1.0, float(radius) * 2.0)
    energy_scale = max(1.0, float(radius) ** 2)
    for light, offset, base_energy in zip(lights, offsets, (1200.0, 700.0, 900.0)):
        light.location = center + offset.normalized() * distance
        light.data.size = area_size
        light.data.energy = base_energy * energy_scale
        _look_at(light, center)


def capture_object_inspection_renders(
    context,
    *,
    object_names=None,
    views=None,
    frame=None,
    resolution_x=800,
    resolution_y=600,
    lens=50.0,
    distance_factor=3.0,
    camera_name="Agent Bridge Inspection Camera",
    note="",
    capture_dir=None,
    isolate_targets=False,
    create_contact_sheet=False,
):
    scene = context.scene
    names = [str(name) for name in (object_names or []) if str(name).strip()]
    if not names:
        active = getattr(context, "active_object", None)
        if active:
            names = [active.name]
    if not names:
        return {"ok": False, "message": "No object names were provided for inspection renders"}

    requested_views = _view_list(views)
    requested_image_count = len(names) * len(requested_views)
    estimated_seconds = _estimated_render_seconds(requested_image_count, resolution_x, resolution_y)
    poll_interval = _poll_interval_seconds(estimated_seconds)
    render_id = _render_id()
    capture_info = _render_root_info(context, preferred_dir=capture_dir, create=True)
    render_dir = os.path.join(capture_info["inspection_render_root"], render_id)
    os.makedirs(render_dir, exist_ok=True)
    target_frame = int(frame if frame is not None else scene.frame_current)

    original = {
        "frame": int(scene.frame_current),
        "camera": scene.camera,
        "resolution_x": int(scene.render.resolution_x),
        "resolution_y": int(scene.render.resolution_y),
        "resolution_percentage": int(scene.render.resolution_percentage),
        "filepath": str(scene.render.filepath),
        "file_format": str(scene.render.image_settings.file_format),
        "engine": str(scene.render.engine),
    }
    camera_data = bpy.data.cameras.new(f"{_safe_id(camera_name, 'Agent_Bridge_Inspection_Camera')}_Data")
    camera_data.lens = float(lens)
    camera = bpy.data.objects.new(_safe_id(camera_name, "Agent_Bridge_Inspection_Camera"), camera_data)
    scene.collection.objects.link(camera)
    existing_light_states = [
        (obj, bool(obj.hide_render))
        for obj in scene.objects
        if getattr(obj, "type", "") == "LIGHT" and hasattr(obj, "hide_render")
    ]
    for obj, _was_hidden in existing_light_states:
        obj.hide_render = True
    inspection_lights = _create_inspection_lights(scene, camera_name)

    images = []
    missing = []
    contact_sheet = {}
    hidden_states = []
    if isolate_targets:
        hidden_states = [
            (obj, bool(obj.hide_render))
            for obj in scene.objects
            if getattr(obj, "type", "") in RENDERABLE_OBJECT_TYPES and hasattr(obj, "hide_render")
        ]
    try:
        scene.frame_set(target_frame)
        scene.render.resolution_x = max(64, min(4096, int(resolution_x)))
        scene.render.resolution_y = max(64, min(4096, int(resolution_y)))
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        scene.camera = camera
        for name in names:
            obj = bpy.data.objects.get(name)
            if obj is None:
                missing.append(name)
                continue
            if isolate_targets:
                visible = set(_iter_target_objects(obj))
                for candidate, _was_hidden in hidden_states:
                    candidate.hide_render = candidate not in visible
            center, radius = _object_bounds(obj)
            _position_inspection_lights(inspection_lights, center, radius)
            distance = max(1.0, radius * float(distance_factor))
            for view in requested_views:
                offset = mathutils.Vector(VIEW_OFFSETS[view])
                if offset.length <= 0.0:
                    offset = mathutils.Vector((0.0, -1.0, 0.25))
                camera.location = center + offset.normalized() * distance
                _look_at(camera, center)
                image_id = _safe_id(f"{obj.name}-{view}")
                path = os.path.join(render_dir, f"{image_id}.png")
                item = {
                    "image_id": image_id,
                    "object": obj.name,
                    "view": view,
                    "path": path,
                    "resource_uri": _image_resource_uri(render_id, image_id),
                    "camera_location": [round(float(value), 6) for value in camera.location],
                    "target_location": [round(float(value), 6) for value in center],
                    "available": False,
                    "size_bytes": 0,
                    "width": 0,
                    "height": 0,
                    "note": "",
                    "render_engine": str(scene.render.engine),
                    "fallback_used": False,
                }
                try:
                    scene.render.filepath = path
                    render_info = _render_still_with_fallback(scene)
                    item.update(render_info)
                    if os.path.isfile(path):
                        width, height = _image_size(path)
                        item.update(
                            {
                                "available": True,
                                "size_bytes": os.path.getsize(path),
                                "width": width,
                                "height": height,
                            }
                        )
                        if item.get("fallback_used"):
                            item["note"] = "Primary renderer failed; captured with Workbench fallback."
                    else:
                        item["note"] = "Render completed but the PNG output was not written."
                except Exception as exc:
                    item["note"] = f"Inspection render failed: {type(exc).__name__}: {exc}"
                images.append(item)
        if create_contact_sheet:
            contact_sheet = _contact_sheet_image(
                images,
                render_dir,
                render_id,
                columns=len(requested_views),
            )
            if contact_sheet.get("available"):
                images.append(contact_sheet)
    finally:
        for obj, was_hidden in existing_light_states:
            if obj.name in bpy.data.objects:
                obj.hide_render = was_hidden
        for light in inspection_lights:
            light_data = getattr(light, "data", None)
            if light.name in bpy.data.objects:
                bpy.data.objects.remove(light, do_unlink=True)
            if light_data is not None and light_data.name in bpy.data.lights:
                bpy.data.lights.remove(light_data)
        for obj, was_hidden in hidden_states:
            if obj.name in bpy.data.objects:
                obj.hide_render = was_hidden
        scene.render.resolution_x = original["resolution_x"]
        scene.render.resolution_y = original["resolution_y"]
        scene.render.resolution_percentage = original["resolution_percentage"]
        scene.render.filepath = original["filepath"]
        scene.render.image_settings.file_format = original["file_format"]
        scene.render.engine = original["engine"]
        scene.camera = original["camera"]
        scene.frame_set(original["frame"])
        if camera.name in bpy.data.objects:
            bpy.data.objects.remove(camera, do_unlink=True)
        if camera_data.name in bpy.data.cameras:
            bpy.data.cameras.remove(camera_data)

    available_images = [image for image in images if image.get("available")]
    view_images = [image for image in images if image.get("view") != "contact_sheet"]
    failed_images = [image for image in view_images if not image.get("available")]
    fallback_images = [image for image in view_images if image.get("fallback_used")]
    metadata = {
        "ok": bool(available_images),
        "requested": True,
        "available": bool(available_images),
        "render_id": render_id,
        "project_id": capture_info.get("project_id", ""),
        "session_id": capture_info.get("session_id", ""),
        "storage_scope": capture_info.get("storage_scope", ""),
        "capture_dir": capture_info.get("capture_dir", ""),
        "base_dir": capture_info.get("base_dir", ""),
        "fallback_reason": capture_info.get("fallback_reason", ""),
        "render_dir": render_dir,
        "metadata_uri": _metadata_uri(render_id),
        "latest_metadata_uri": LATEST_INSPECTION_RENDER_METADATA_URI,
        "created_at": time.time(),
        "scene": scene.name,
        "frame": target_frame,
        "object_names": names,
        "missing_object_names": missing,
        "views": requested_views,
        "targets_isolated": bool(isolate_targets),
        "lighting": "temporary_three_point_area",
        "contact_sheet": contact_sheet,
        "image_count": len(available_images),
        "requested_image_count": len(images),
        "failed_image_count": len(failed_images),
        "fallback_image_count": len(fallback_images),
        "render_complete": not failed_images and len(view_images) == requested_image_count,
        "estimated_seconds": estimated_seconds,
        "estimated_duration": _duration_label(estimated_seconds),
        "poll_after_seconds": poll_interval,
        "timeout_safe": False,
        "resource_type": "png_inspection_renders",
        "note": str(note or "")[:1000],
        "images": images,
        "client_guidance": (
            "Inspection renders run synchronously on Blender's main thread. "
            f"Rough expected duration was {_duration_label(estimated_seconds)} for {requested_image_count} image(s). "
            "If an MCP client times out, wait, call blender_bridge_status, then inspect latest inspection-render metadata before recapturing."
        ),
    }
    metadata["metadata_path"] = _metadata_path(render_dir)
    _write_metadata(metadata)
    return {
        "ok": bool(available_images),
        "message": "Captured object inspection render(s)" if available_images else "No inspection renders were captured",
        "inspection_render": metadata,
        "missing_object_names": missing,
    }


def register():
    pass


def unregister():
    pass
