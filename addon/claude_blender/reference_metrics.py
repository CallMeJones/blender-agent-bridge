"""Pure image-space metrics for calibrated reference-model comparison."""

from __future__ import annotations

import math


def _dimensions(width, height):
    width = int(width)
    height = int(height)
    if width < 1 or height < 1:
        raise ValueError("Mask dimensions must be positive")
    return width, height


def _mask(mask, width, height, label):
    result = bytearray(1 if value else 0 for value in mask)
    if len(result) != width * height:
        raise ValueError(
            f"{label} mask has {len(result)} pixels; expected {width * height}"
        )
    return result


def rasterize_polygon(points, width, height):
    """Rasterize normalized top-left polygon coordinates into a binary mask."""

    width, height = _dimensions(width, height)
    vertices = []
    for point in points or []:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            x = max(0.0, min(1.0, float(point[0])))
            y = max(0.0, min(1.0, float(point[1])))
        except (TypeError, ValueError):
            continue
        vertices.append((x, y))
    if len(vertices) < 3:
        raise ValueError("A reference outline needs at least three valid points")

    result = bytearray(width * height)
    for row in range(height):
        scan_y = (row + 0.5) / height
        intersections = []
        previous = vertices[-1]
        for current in vertices:
            x1, y1 = previous
            x2, y2 = current
            if (y1 <= scan_y < y2) or (y2 <= scan_y < y1):
                ratio = (scan_y - y1) / (y2 - y1)
                intersections.append(x1 + ratio * (x2 - x1))
            previous = current
        intersections.sort()
        for index in range(0, len(intersections) - 1, 2):
            left = max(0, int(math.ceil(intersections[index] * width - 0.5)))
            right = min(
                width - 1,
                int(math.floor(intersections[index + 1] * width - 0.5)),
            )
            if right >= left:
                start = row * width + left
                result[start : start + right - left + 1] = b"\x01" * (
                    right - left + 1
                )
    return result


def mask_edges(mask, width, height):
    width, height = _dimensions(width, height)
    source = _mask(mask, width, height, "Input")
    edges = bytearray(width * height)
    for y in range(height):
        row = y * width
        for x in range(width):
            index = row + x
            if not source[index]:
                continue
            if (
                x == 0
                or x == width - 1
                or y == 0
                or y == height - 1
                or not source[index - 1]
                or not source[index + 1]
                or not source[index - width]
                or not source[index + width]
            ):
                edges[index] = 1
    return edges


def _distance_transform(edges, width, height):
    diagonal = math.sqrt(2.0)
    infinity = float(width + height + 1)
    distances = [0.0 if value else infinity for value in edges]
    for y in range(height):
        row = y * width
        for x in range(width):
            index = row + x
            value = distances[index]
            if x:
                value = min(value, distances[index - 1] + 1.0)
            if y:
                value = min(value, distances[index - width] + 1.0)
                if x:
                    value = min(value, distances[index - width - 1] + diagonal)
                if x + 1 < width:
                    value = min(
                        value, distances[index - width + 1] + diagonal
                    )
            distances[index] = value
    for y in range(height - 1, -1, -1):
        row = y * width
        for x in range(width - 1, -1, -1):
            index = row + x
            value = distances[index]
            if x + 1 < width:
                value = min(value, distances[index + 1] + 1.0)
            if y + 1 < height:
                value = min(value, distances[index + width] + 1.0)
                if x:
                    value = min(
                        value, distances[index + width - 1] + diagonal
                    )
                if x + 1 < width:
                    value = min(
                        value, distances[index + width + 1] + diagonal
                    )
            distances[index] = value
    return distances


def _percentile(values, fraction):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(
        0,
        min(len(ordered) - 1, int(math.ceil(fraction * len(ordered)) - 1)),
    )
    return float(ordered[index])


def _centroid(mask, width, height):
    count = 0
    x_total = 0.0
    y_total = 0.0
    for index, value in enumerate(mask):
        if not value:
            continue
        y, x = divmod(index, width)
        count += 1
        x_total += (x + 0.5) / width
        y_total += (y + 0.5) / height
    if not count:
        return None
    return [x_total / count, y_total / count]


def _error_regions(reference, model, width, height):
    regions = []
    row_names = ("upper", "middle", "lower")
    column_names = ("left", "center", "right")
    reference_total = max(1, sum(reference))
    for row_index, row_name in enumerate(row_names):
        y0 = row_index * height // 3
        y1 = (row_index + 1) * height // 3
        for column_index, column_name in enumerate(column_names):
            x0 = column_index * width // 3
            x1 = (column_index + 1) * width // 3
            missing = 0
            excess = 0
            for y in range(y0, y1):
                start = y * width
                for x in range(x0, x1):
                    index = start + x
                    if reference[index] and not model[index]:
                        missing += 1
                    elif model[index] and not reference[index]:
                        excess += 1
            difference = missing + excess
            if not difference:
                continue
            if excess > missing * 1.25:
                problem = "model_excess"
                action = "Reduce or move the model silhouette inward in this region."
            elif missing > excess * 1.25:
                problem = "model_missing"
                action = "Expand or move the model silhouette outward in this region."
            else:
                problem = "mixed_alignment"
                action = "Reposition the local form before changing its overall size."
            regions.append(
                {
                    "name": f"{row_name}_{column_name}",
                    "problem": problem,
                    "missing_pixels": missing,
                    "excess_pixels": excess,
                    "magnitude": round(difference / reference_total, 6),
                    "suggested_action": action,
                }
            )
    return sorted(
        regions,
        key=lambda item: (
            -item["magnitude"],
            item["name"],
        ),
    )


def compare_masks(reference_mask, model_mask, width, height):
    """Compare two binary masks and return bounded, reproducible metrics."""

    width, height = _dimensions(width, height)
    reference = _mask(reference_mask, width, height, "Reference")
    model = _mask(model_mask, width, height, "Model")
    reference_pixels = sum(reference)
    model_pixels = sum(model)
    if not reference_pixels:
        raise ValueError("Reference mask contains no foreground pixels")
    if not model_pixels:
        raise ValueError("Model mask contains no foreground pixels")

    intersection = 0
    union = 0
    for reference_value, model_value in zip(reference, model):
        intersection += int(reference_value and model_value)
        union += int(reference_value or model_value)

    reference_edges = mask_edges(reference, width, height)
    model_edges = mask_edges(model, width, height)
    reference_distances = _distance_transform(reference_edges, width, height)
    model_distances = _distance_transform(model_edges, width, height)
    reference_to_model = [
        model_distances[index]
        for index, value in enumerate(reference_edges)
        if value
    ]
    model_to_reference = [
        reference_distances[index]
        for index, value in enumerate(model_edges)
        if value
    ]
    symmetric_distances = reference_to_model + model_to_reference
    diagonal = math.hypot(width, height)
    reference_centroid = _centroid(reference, width, height)
    model_centroid = _centroid(model, width, height)
    centroid_dx = model_centroid[0] - reference_centroid[0]
    centroid_dy = model_centroid[1] - reference_centroid[1]

    return {
        "width": width,
        "height": height,
        "reference_pixels": reference_pixels,
        "model_pixels": model_pixels,
        "intersection_pixels": intersection,
        "union_pixels": union,
        "silhouette_iou": round(intersection / union, 6),
        "silhouette_dice": round(
            (2.0 * intersection) / (reference_pixels + model_pixels), 6
        ),
        "reference_coverage": round(reference_pixels / (width * height), 6),
        "model_coverage": round(model_pixels / (width * height), 6),
        "mean_edge_distance_pixels": round(
            sum(symmetric_distances) / max(1, len(symmetric_distances)), 4
        ),
        "p95_edge_distance_pixels": round(
            _percentile(symmetric_distances, 0.95), 4
        ),
        "mean_edge_distance_normalized": round(
            (
                sum(symmetric_distances)
                / max(1, len(symmetric_distances))
                / diagonal
            ),
            6,
        ),
        "reference_centroid": [
            round(reference_centroid[0], 6),
            round(reference_centroid[1], 6),
        ],
        "model_centroid": [
            round(model_centroid[0], 6),
            round(model_centroid[1], 6),
        ],
        "centroid_offset": {
            "dx_normalized": round(centroid_dx, 6),
            "dy_normalized": round(centroid_dy, 6),
            "dx_pixels": round(centroid_dx * width, 3),
            "dy_pixels": round(centroid_dy * height, 3),
        },
        "error_regions": _error_regions(
            reference, model, width, height
        )[:9],
    }


def compare_landmarks(reference_points, target_points, width, height):
    """Compare matching normalized top-left landmarks."""

    width, height = _dimensions(width, height)
    reference_points = (
        reference_points if isinstance(reference_points, dict) else {}
    )
    target_points = target_points if isinstance(target_points, dict) else {}
    errors = []
    for name in sorted(set(reference_points) & set(target_points)):
        reference = reference_points[name]
        target = target_points[name]
        if (
            not isinstance(reference, (list, tuple))
            or len(reference) < 2
            or not isinstance(target, (list, tuple))
            or len(target) < 2
        ):
            continue
        try:
            reference_x = float(reference[0])
            reference_y = float(reference[1])
            target_x = float(target[0])
            target_y = float(target[1])
        except (TypeError, ValueError):
            continue
        dx = target_x - reference_x
        dy = target_y - reference_y
        dx_pixels = dx * width
        dy_pixels = dy * height
        errors.append(
            {
                "name": str(name),
                "reference": [
                    round(reference_x, 6),
                    round(reference_y, 6),
                ],
                "target": [round(target_x, 6), round(target_y, 6)],
                "dx_pixels": round(dx_pixels, 3),
                "dy_pixels": round(dy_pixels, 3),
                "distance_pixels": round(
                    math.hypot(dx_pixels, dy_pixels), 3
                ),
                "correction_normalized": [
                    round(-dx, 6),
                    round(-dy, 6),
                ],
            }
        )
    errors.sort(key=lambda item: (-item["distance_pixels"], item["name"]))
    return errors
