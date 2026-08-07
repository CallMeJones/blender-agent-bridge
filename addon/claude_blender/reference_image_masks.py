"""Pure mask and outline helpers for reference-image intake."""

from __future__ import annotations

import math


MAX_OUTLINE_POINTS = 192


def _border_flood_mask(pixels, width, height, tolerance):
    """Background is what the image border can reach; subject is what it cannot.

    Neither brightness nor a fixed background colour separates a light subject
    from a light backdrop. A white uniform is as bright as a white sweep, so
    ``luminance`` loses the character; a drop shadow is far from pure white, so
    ``background_color`` keeps the shadow and reports a subject wider than it
    is. Both failures were measured on a real reference sheet, and both produce
    a plausible-looking mask rather than an error.

    Connectivity separates them because a backdrop and its shadow touch the
    image border and the subject does not. Growth compares each candidate to
    the neighbour it came from rather than to a single seed colour, so a
    gradient or a tinted shadow is followed while the sharp step at the
    subject's edge stops it.
    """

    width = int(width)
    height = int(height)
    tolerance = max(0.0, float(tolerance))
    background = bytearray(width * height)
    stack = []

    def offset(x, y):
        return (y * width + x) * 4

    def push(x, y):
        index = y * width + x
        if not background[index]:
            background[index] = 1
            stack.append((x, y))

    for x in range(width):
        push(x, 0)
        push(x, height - 1)
    for y in range(height):
        push(0, y)
        push(width - 1, y)

    while stack:
        x, y = stack.pop()
        base = offset(x, y)
        red, green, blue = pixels[base], pixels[base + 1], pixels[base + 2]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if background[ny * width + nx]:
                continue
            near = offset(nx, ny)
            distance = math.sqrt(
                (pixels[near] - red) ** 2
                + (pixels[near + 1] - green) ** 2
                + (pixels[near + 2] - blue) ** 2
            )
            if distance <= tolerance:
                push(nx, ny)

    return bytearray(0 if value else 1 for value in background)


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
        if 0.001 < coverage < 0.995:
            mode = "alpha"
        elif len(background) >= 3:
            mode = "background_color"
        else:
            # Previously this chose background_color unconditionally and then
            # raised, because auto has no colour to supply. Border flood needs
            # none, and handles the light-on-light case that sends people here.
            mode = "border_flood"
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
    if mode == "border_flood":
        return _border_flood_mask(pixels, width, height, threshold)
    raise ValueError(
        "mask mode must be auto, alpha, luminance, background_color, or border_flood"
    )


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
