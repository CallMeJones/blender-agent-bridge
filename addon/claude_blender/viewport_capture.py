"""Viewport screenshot capture and API image attachment helpers."""

from __future__ import annotations

import base64
import os
import time

import bpy


DEFAULT_MAX_BYTES = 5 * 1024 * 1024
PREVIEW_IMAGE_NAME = "Claude Viewport Preview"


def default_capture_dir():
    return os.path.join(os.path.expanduser("~"), ".claude_blender", "captures")


def _capture_filepath(capture_dir):
    os.makedirs(capture_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return os.path.join(capture_dir, f"viewport-{timestamp}.png")


def _has_ui_context(context):
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
    if size_bytes > int(max_bytes):
        return {
            "requested": True,
            "available": False,
            "note": f"Viewport screenshot was larger than the {int(max_bytes)} byte limit",
            "path": filepath,
            "size_bytes": size_bytes,
        }, {}

    with open(filepath, "rb") as handle:
        data = base64.b64encode(handle.read()).decode("ascii")
    try:
        preview_image = load_preview_image(filepath)
        preview_image_name = preview_image.name
    except Exception:
        preview_image_name = ""

    metadata = {
        "requested": True,
        "available": True,
        "media_type": "image/png",
        "capture_method": method,
        "path": filepath,
        "preview_image": preview_image_name,
        "size_bytes": size_bytes,
        "note": "Viewport screenshot attached to the Claude request",
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


def register():
    pass


def unregister():
    pass
