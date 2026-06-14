"""Viewport screenshot capture and API image attachment helpers."""

from __future__ import annotations

import base64
import math
import os
import time

import bpy


DEFAULT_MAX_BYTES = 5 * 1024 * 1024
PREVIEW_IMAGE_NAME = "Claude Viewport Preview"
MIN_RESIZED_DIMENSION = 64
MAX_RESIZE_ATTEMPTS = 8


def default_capture_dir():
    return os.path.join(os.path.expanduser("~"), ".claude_blender", "captures")


def _capture_filepath(capture_dir):
    os.makedirs(capture_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return os.path.join(capture_dir, f"viewport-{timestamp}.png")


def _has_ui_context(context):
    if bool(getattr(bpy.app, "background", False)):
        return False
    return bool(getattr(context, "window", None) and getattr(context, "screen", None))


def _capture_with_operator(context, filepath):
    area = getattr(context, "area", None)
    if area and area.type == "VIEW_3D":
        bpy.ops.screen.screenshot_area(filepath=filepath)
        return "screen.screenshot_area"
    bpy.ops.screen.screenshot(filepath=filepath)
    return "screen.screenshot"


def load_preview_image(filepath):
    """Load the screenshot into a stable Blender Image datablock."""

    existing = bpy.data.images.get(PREVIEW_IMAGE_NAME)
    if existing:
        bpy.data.images.remove(existing)
    image = bpy.data.images.load(filepath, check_existing=False)
    image.name = PREVIEW_IMAGE_NAME
    return image


def _resized_filepath(filepath):
    root, ext = os.path.splitext(filepath)
    return f"{root}-resized{ext or '.png'}"


def _image_size_tuple(image):
    try:
        return int(image.size[0]), int(image.size[1])
    except Exception:
        return 0, 0


def _resize_png_to_fit(filepath, max_bytes):
    """Downscale and re-save a PNG with Blender's image API until it fits."""

    max_bytes = int(max_bytes or DEFAULT_MAX_BYTES)
    original_size = os.path.getsize(filepath)
    if original_size <= max_bytes:
        return filepath, {
            "resized": False,
            "original_size_bytes": original_size,
            "size_bytes": original_size,
        }

    image = bpy.data.images.load(filepath, check_existing=False)
    try:
        width, height = _image_size_tuple(image)
        if width <= 0 or height <= 0:
            return None, {
                "resized": False,
                "original_size_bytes": original_size,
                "size_bytes": original_size,
                "resize_error": "Could not read screenshot dimensions",
            }
        output_path = _resized_filepath(filepath)
        current_size = original_size
        resized_info = {
            "resized": True,
            "original_path": filepath,
            "original_size_bytes": original_size,
            "original_width": width,
            "original_height": height,
        }
        for _attempt in range(MAX_RESIZE_ATTEMPTS):
            scale = math.sqrt(max(1, max_bytes) / max(1, current_size)) * 0.9
            scale = min(0.85, max(0.1, scale))
            next_width = max(MIN_RESIZED_DIMENSION, int(width * scale))
            next_height = max(MIN_RESIZED_DIMENSION, int(height * scale))
            if next_width == width and next_height == height:
                next_width = max(MIN_RESIZED_DIMENSION, width - 1)
                next_height = max(MIN_RESIZED_DIMENSION, height - 1)
            if (next_width, next_height) == (width, height):
                break
            image.scale(next_width, next_height)
            image.filepath_raw = output_path
            image.file_format = "PNG"
            image.save()
            current_size = os.path.getsize(output_path)
            width, height = next_width, next_height
            resized_info.update(
                {
                    "path": output_path,
                    "size_bytes": current_size,
                    "width": width,
                    "height": height,
                    "resize_scale": round(width / max(1, int(resized_info["original_width"])), 5),
                }
            )
            if current_size <= max_bytes:
                return output_path, resized_info
        resized_info["resize_error"] = f"Resized screenshot still exceeds {max_bytes} bytes"
        return None, resized_info
    finally:
        try:
            bpy.data.images.remove(image)
        except Exception:
            pass


def prepare_image_attachment(filepath, *, max_bytes=DEFAULT_MAX_BYTES, capture_method="file"):
    """Prepare a captured PNG as a bounded Anthropic image attachment."""

    max_bytes = int(max_bytes or DEFAULT_MAX_BYTES)
    if not os.path.exists(filepath):
        return {
            "requested": True,
            "available": False,
            "note": "Viewport screenshot operator completed but did not create a file",
        }, {}

    size_bytes = os.path.getsize(filepath)
    if size_bytes <= 0:
        return {
            "requested": True,
            "available": False,
            "note": "Viewport screenshot file was empty",
            "path": filepath,
        }, {}

    try:
        prepared_path, resize_info = _resize_png_to_fit(filepath, max_bytes)
    except Exception as exc:
        return {
            "requested": True,
            "available": False,
            "note": f"Viewport screenshot could not be prepared: {type(exc).__name__}: {exc}",
            "path": filepath,
            "size_bytes": size_bytes,
        }, {}
    if not prepared_path:
        return {
            "requested": True,
            "available": False,
            "note": resize_info.get("resize_error") or f"Viewport screenshot was larger than the {max_bytes} byte limit",
            "path": filepath,
            **resize_info,
        }, {}

    final_size = os.path.getsize(prepared_path)
    with open(prepared_path, "rb") as handle:
        data = base64.b64encode(handle.read()).decode("ascii")
    try:
        preview_image = load_preview_image(prepared_path)
        preview_image_name = preview_image.name
        width, height = _image_size_tuple(preview_image)
    except Exception:
        preview_image_name = ""
        width = int(resize_info.get("width") or 0)
        height = int(resize_info.get("height") or 0)

    note = "Viewport screenshot attached to the Claude request"
    if resize_info.get("resized"):
        note = "Viewport screenshot resized and attached to the Claude request"
    metadata = {
        "requested": True,
        "available": True,
        "media_type": "image/png",
        "capture_method": capture_method,
        "path": prepared_path,
        "preview_image": preview_image_name,
        "size_bytes": final_size,
        "width": width,
        "height": height,
        "note": note,
        **resize_info,
    }
    attachments = {
        "viewport_image": {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": data,
            },
        }
    }
    return metadata, attachments


def capture_viewport(context, *, capture_dir=None, max_bytes=DEFAULT_MAX_BYTES):
    """Capture the current Blender UI/viewport as a PNG attachment.

    This intentionally fails soft in background mode or when Blender's UI
    context cannot provide a screenshot operator.
    """

    if not _has_ui_context(context):
        return {
            "requested": True,
            "available": False,
            "note": "Viewport screenshot requires an interactive Blender window",
        }, {}

    filepath = _capture_filepath(capture_dir or default_capture_dir())
    try:
        method = _capture_with_operator(context, filepath)
    except Exception as exc:
        return {
            "requested": True,
            "available": False,
            "note": f"Viewport screenshot failed: {type(exc).__name__}: {exc}",
        }, {}

    return prepare_image_attachment(filepath, max_bytes=max_bytes, capture_method=method)


def register():
    pass


def unregister():
    pass
