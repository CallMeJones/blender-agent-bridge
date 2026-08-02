"""Pure mask and outline helpers for reference-image intake."""

from __future__ import annotations

import math


MAX_OUTLINE_POINTS = 192


def mask_from_pixels(sample, *, mode, threshold, background_color=None):
    width, height = sample["sampled_size"]
    pixels = sample["pixels"]
    threshold = max(0.0, min(1.0, float(threshold)))
    mode = str(mode or "alpha").strip().lower()
    background = list(background_color or [])
    if mode == "auto":
        alpha_pixels = sum(
            1
            for offset in range(3, len(pixels), 4)
            if pixels[offset] >= threshold
        )
        coverage = alpha_pixels / max(1, int(width) * int(height))
        mode = "alpha" if 0.001 < coverage < 0.995 else "background_color"
    if mode == "alpha":
        return bytearray(
            1 if pixels[offset + 3] >= threshold else 0
            for offset in range(0, len(pixels), 4)
        )
    if mode == "luminance":
        return bytearray(
            1
            if (
                pixels[offset] * 0.2126
                + pixels[offset + 1] * 0.7152
                + pixels[offset + 2] * 0.0722
            )
            >= threshold
            else 0
            for offset in range(0, len(pixels), 4)
        )
    if mode == "background_color":
        if len(background) < 3:
            raise ValueError(
                "background_color mask mode requires background_color [r,g,b]"
            )
        br, bg, bb = [float(value) for value in background[:3]]
        return bytearray(
            1
            if math.sqrt(
                (pixels[offset] - br) ** 2
                + (pixels[offset + 1] - bg) ** 2
                + (pixels[offset + 2] - bb) ** 2
            )
            >= threshold
            else 0
            for offset in range(0, len(pixels), 4)
        )
    raise ValueError("mask mode must be auto, alpha, luminance, or background_color")


def _mask_bounds(mask, width, height):
    xs = []
    ys = []
    for index, value in enumerate(mask):
        if not value:
            continue
        y, x = divmod(index, width)
        xs.append(x)
        ys.append(y)
    if not xs:
        raise ValueError("foreground mask contains no pixels")
    return min(xs), min(ys), max(xs), max(ys), len(xs)


def _edge_pixels(mask, width, height):
    edges = []
    for y in range(height):
        row = y * width
        for x in range(width):
            index = row + x
            if not mask[index]:
                continue
            if (
                x == 0
                or y == 0
                or x == width - 1
                or y == height - 1
                or not mask[index - 1]
                or not mask[index + 1]
                or not mask[index - width]
                or not mask[index + width]
            ):
                edges.append((x, y))
    if len(edges) < 3:
        raise ValueError("foreground mask has too few edge pixels")
    return edges


def outline_from_mask(mask, width, height, *, max_points=MAX_OUTLINE_POINTS):
    """Return a cyclic normalized top-left outline sampled by polar angle."""

    width = int(width)
    height = int(height)
    bounds = _mask_bounds(mask, width, height)
    edges = _edge_pixels(mask, width, height)
    cx = sum(x for x, _y in edges) / len(edges)
    cy = sum(y for _x, y in edges) / len(edges)
    buckets = {}
    bucket_count = max(12, min(MAX_OUTLINE_POINTS, int(max_points or 96)))
    for x, y in edges:
        angle = math.atan2(y - cy, x - cx)
        bucket = int(((angle + math.pi) / (2.0 * math.pi)) * bucket_count)
        bucket = max(0, min(bucket_count - 1, bucket))
        distance = (x - cx) ** 2 + (y - cy) ** 2
        previous = buckets.get(bucket)
        if previous is None or distance > previous[0]:
            buckets[bucket] = (distance, x, y)
    points = [
        [
            round((buckets[index][1] + 0.5) / width, 6),
            round((buckets[index][2] + 0.5) / height, 6),
        ]
        for index in sorted(buckets)
    ]
    if len(points) < 3:
        raise ValueError("could not derive a usable outline from the foreground mask")
    min_x, min_y, max_x, max_y, foreground_count = bounds
    return {
        "points": points,
        "bounds": {
            "x": round(min_x / width, 6),
            "y": round(min_y / height, 6),
            "width": round((max_x - min_x + 1) / width, 6),
            "height": round((max_y - min_y + 1) / height, 6),
        },
        "foreground_coverage": round(foreground_count / (width * height), 6),
        "edge_pixel_count": len(edges),
    }
