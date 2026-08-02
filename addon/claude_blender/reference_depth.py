"""Blender image loading for calibrated reference depth fields."""

from __future__ import annotations

import math
import os

import bpy

from . import depth_fields


MAX_DEPTH_SOURCES = 12
MAX_TOTAL_DEPTH_PIXELS = 4_194_304
MAX_TOTAL_SPARSE_BUCKET_REFERENCES = 1_048_576


def _finite(value, field, default=None):
    if value is None and default is not None:
        value = default
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a finite number")
    return result


def _channel_value(pixels, offset, channel):
    if channel == "red":
        return pixels[offset]
    if channel == "green":
        return pixels[offset + 1]
    if channel == "blue":
        return pixels[offset + 2]
    if channel == "alpha":
        return pixels[offset + 3]
    return (
        pixels[offset] * 0.2126
        + pixels[offset + 1] * 0.7152
        + pixels[offset + 2] * 0.0722
    )


def _image_layer(raw, source_index, max_axis):
    field = f"depth_sources[{source_index}]"
    path = os.path.abspath(
        bpy.path.abspath(os.path.expanduser(str(raw.get("image_path") or "").strip()))
    )
    if not path or not os.path.isfile(path):
        raise ValueError(f"{field}.image_path does not exist: {path}")
    near_depth = _finite(raw.get("near_depth"), f"{field}.near_depth")
    far_depth = _finite(raw.get("far_depth"), f"{field}.far_depth")
    channel = str(raw.get("channel") or "luminance").strip().lower()
    if channel not in {"luminance", "red", "green", "blue", "alpha"}:
        raise ValueError(
            f"{field}.channel must be luminance, red, green, blue, or alpha"
        )
    invalid_below = _finite(raw.get("invalid_below"), f"{field}.invalid_below", -1.0)
    invalid_above = _finite(raw.get("invalid_above"), f"{field}.invalid_above", 2.0)
    if invalid_below > invalid_above:
        raise ValueError(f"{field}.invalid_below must not exceed invalid_above")
    alpha_threshold = _finite(
        raw.get("alpha_threshold"),
        f"{field}.alpha_threshold",
        0.0,
    )
    alpha_threshold = max(0.0, min(1.0, alpha_threshold))
    image = None
    try:
        image = bpy.data.images.load(path, check_existing=False)
        source_width = int(image.size[0])
        source_height = int(image.size[1])
        if source_width < 1 or source_height < 1:
            raise ValueError(f"{field}.image_path has no readable pixels")
        bounded_axis = max(16, min(1024, int(max_axis)))
        scale = min(1.0, bounded_axis / max(source_width, source_height))
        width = max(1, int(round(source_width * scale)))
        height = max(1, int(round(source_height * scale)))
        if (width, height) != (source_width, source_height):
            image.scale(width, height)
            image.update()
        pixels = list(image.pixels[:])
        values = []
        invert = bool(raw.get("invert", False))
        for top_y in range(height):
            source_y = height - 1 - top_y
            for x in range(width):
                offset = (source_y * width + x) * 4
                alpha = float(pixels[offset + 3])
                raw_value = float(_channel_value(pixels, offset, channel))
                if (
                    alpha < alpha_threshold
                    or raw_value < invalid_below
                    or raw_value > invalid_above
                ):
                    values.append(None)
                    continue
                normalized = max(0.0, min(1.0, raw_value))
                if invert:
                    normalized = 1.0 - normalized
                values.append(near_depth + (far_depth - near_depth) * normalized)
        layer = depth_fields.prepare_depth_layer(
            {
                "name": str(raw.get("name") or os.path.basename(path)),
                "mode": raw.get("mode") or "front",
                "tolerance": raw.get("tolerance", 0.0),
                "width": width,
                "height": height,
                "values": values,
            }
        )
        return layer, {
            "kind": "image",
            "path": path,
            "source_size": [source_width, source_height],
            "sampled_size": [width, height],
            "valid_depth_count": layer["valid_count"],
            "mode": layer["mode"],
            "near_depth": near_depth,
            "far_depth": far_depth,
        }
    finally:
        if image is not None and bpy.data.images.get(image.name) is image:
            bpy.data.images.remove(image)


def _sample_layer(raw, source_index):
    layer = depth_fields.prepare_depth_layer(
        {
            "name": str(raw.get("name") or f"samples_{source_index + 1}"),
            "mode": raw.get("mode") or "front",
            "tolerance": raw.get("tolerance", 0.0),
            "samples": raw.get("samples"),
        }
    )
    return layer, {
        "kind": "samples",
        "sample_count": layer["valid_count"],
        "mode": layer["mode"],
    }


def attach_depth_sources(views, sources, *, max_axis=256, require_depth=False):
    """Attach user-supplied image or sparse depth sources to calibrated views."""

    prepared_views = [{**view, "depth_layers": []} for view in views]
    by_name = {view["name"].casefold(): view for view in prepared_views}
    summaries = []
    sources = list(sources or [])
    total_depth_pixels = 0
    total_bucket_references = 0
    if len(sources) > MAX_DEPTH_SOURCES:
        raise ValueError(f"depth_sources supports at most {MAX_DEPTH_SOURCES} entries")
    for index, raw in enumerate(sources):
        if not isinstance(raw, dict):
            raise ValueError(f"depth_sources[{index}] must be an object")
        view_name = str(raw.get("view_name") or "").strip()
        view = by_name.get(view_name.casefold())
        if view is None:
            raise ValueError(f"depth_sources[{index}].view_name is not calibrated: {view_name}")
        has_image = bool(str(raw.get("image_path") or "").strip())
        has_samples = raw.get("samples") is not None
        if has_image == has_samples:
            raise ValueError(
                f"depth_sources[{index}] must contain exactly one of image_path or samples"
            )
        layer, summary = (
            _image_layer(raw, index, max_axis)
            if has_image
            else _sample_layer(raw, index)
        )
        if layer["kind"] == "grid":
            total_depth_pixels += layer["width"] * layer["height"]
            if total_depth_pixels > MAX_TOTAL_DEPTH_PIXELS:
                raise ValueError(
                    "depth_sources exceed the aggregate sampled-image limit of "
                    f"{MAX_TOTAL_DEPTH_PIXELS} pixels"
                )
        else:
            total_bucket_references += layer["bucket_reference_count"]
            if total_bucket_references > MAX_TOTAL_SPARSE_BUCKET_REFERENCES:
                raise ValueError(
                    "depth_sources exceed the aggregate sparse-index limit of "
                    f"{MAX_TOTAL_SPARSE_BUCKET_REFERENCES} references"
                )
        view["depth_layers"].append(layer)
        view["depth_layers"] = list(
            depth_fields.prepare_depth_layers(view["depth_layers"])
        )
        summaries.append(
            {
                "view_name": view["name"],
                "name": layer["name"],
                **summary,
            }
        )
    if require_depth and not summaries:
        raise ValueError("At least one calibrated depth source is required")
    return prepared_views, summaries


def register():
    pass


def unregister():
    pass
