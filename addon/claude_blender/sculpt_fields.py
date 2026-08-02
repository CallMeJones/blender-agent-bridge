"""Pure weighted-field geometry helpers for semantic sculpt operations."""

from __future__ import annotations

import math


_EPSILON = 1e-9


def _vector(value, length, default):
    if not isinstance(value, (list, tuple)) or len(value) < length:
        return tuple(float(item) for item in default)
    try:
        result = tuple(float(value[index]) for index in range(length))
    except (TypeError, ValueError, OverflowError):
        return tuple(float(item) for item in default)
    if not all(math.isfinite(item) for item in result):
        return tuple(float(item) for item in default)
    return result


def _clamp(value, minimum=0.0, maximum=1.0):
    return max(float(minimum), min(float(maximum), float(value)))


def _smoothstep(value):
    value = _clamp(value)
    return value * value * (3.0 - 2.0 * value)


def _distance(a, b):
    return math.sqrt(sum((a[index] - b[index]) ** 2 for index in range(len(a))))


def _point_segment_distance_2d(point, start, end):
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared <= _EPSILON:
        return _distance(point, start)
    factor = _clamp(
        ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
        / length_squared
    )
    closest = (start[0] + dx * factor, start[1] + dy * factor)
    return _distance(point, closest)


def _point_in_polygon(point, polygon):
    inside = False
    previous = polygon[-1]
    for current in polygon:
        if (current[1] > point[1]) != (previous[1] > point[1]):
            denominator = previous[1] - current[1]
            if abs(denominator) <= _EPSILON:
                previous = current
                continue
            intersection = (
                (previous[0] - current[0])
                * (point[1] - current[1])
                / denominator
                + current[0]
            )
            if point[0] < intersection:
                inside = not inside
        previous = current
    return inside


def sphere_weights(points, *, center, radius, feather=0.0):
    """Return a full-weight sphere with an optional soft exterior band."""

    center = _vector(center, 3, (0.0, 0.0, 0.0))
    radius = max(_EPSILON, float(radius))
    feather = max(0.0, float(feather))
    weights = []
    for raw_point in points:
        point = _vector(raw_point, 3, (0.0, 0.0, 0.0))
        distance = _distance(point, center)
        if distance <= radius:
            weights.append(1.0)
        elif feather > _EPSILON and distance < radius + feather:
            weights.append(_smoothstep(1.0 - (distance - radius) / feather))
        else:
            weights.append(0.0)
    return weights


def box_weights(points, *, minimum, maximum, feather=0.0):
    """Return weights inside an axis-aligned box with exterior feathering."""

    minimum = _vector(minimum, 3, (-1.0, -1.0, -1.0))
    maximum = _vector(maximum, 3, (1.0, 1.0, 1.0))
    lower = tuple(min(minimum[index], maximum[index]) for index in range(3))
    upper = tuple(max(minimum[index], maximum[index]) for index in range(3))
    feather = max(0.0, float(feather))
    weights = []
    for raw_point in points:
        point = _vector(raw_point, 3, (0.0, 0.0, 0.0))
        offsets = [
            max(lower[index] - point[index], 0.0, point[index] - upper[index])
            for index in range(3)
        ]
        outside_distance = math.sqrt(sum(value * value for value in offsets))
        if outside_distance <= _EPSILON:
            weights.append(1.0)
        elif feather > _EPSILON and outside_distance < feather:
            weights.append(_smoothstep(1.0 - outside_distance / feather))
        else:
            weights.append(0.0)
    return weights


def polygon_weights(points, *, polygon, feather=0.0):
    """Return weights for 2D points inside or near a closed polygon."""

    polygon = [_vector(point, 2, (0.0, 0.0)) for point in list(polygon or [])]
    if len(polygon) < 3:
        raise ValueError("A screen polygon needs at least three points")
    feather = max(0.0, float(feather))
    weights = []
    for raw_point in points:
        point = _vector(raw_point, 2, (0.0, 0.0))
        if _point_in_polygon(point, polygon):
            weights.append(1.0)
            continue
        if feather <= _EPSILON:
            weights.append(0.0)
            continue
        distance = min(
            _point_segment_distance_2d(
                point,
                polygon[index - 1],
                polygon[index],
            )
            for index in range(len(polygon))
        )
        weights.append(
            _smoothstep(1.0 - distance / feather)
            if distance < feather
            else 0.0
        )
    return weights


def polygon_evaluation_count(point_count, *, edge_count, feather=0.0):
    """Return the maximum edge checks performed by ``polygon_weights``."""

    point_count = max(0, int(point_count))
    edge_count = max(0, int(edge_count))
    edge_passes = 2 if float(feather) > _EPSILON else 1
    return point_count * edge_count * edge_passes


def index_weights(point_count, indices):
    weights = [0.0] * max(0, int(point_count))
    for raw_index in list(indices or []):
        try:
            index = int(raw_index)
        except (TypeError, ValueError, OverflowError):
            continue
        if 0 <= index < len(weights):
            weights[index] = 1.0
    return weights


def merge_weights(existing, incoming, mode="replace"):
    if len(existing) != len(incoming):
        raise ValueError("Weight arrays must have the same length")
    mode = str(mode or "replace").strip().lower()
    if mode not in {"replace", "add", "subtract", "intersect"}:
        raise ValueError(f"Unsupported region write mode: {mode}")
    result = []
    for left, right in zip(existing, incoming):
        left = _clamp(left)
        right = _clamp(right)
        if mode == "replace":
            value = right
        elif mode == "add":
            value = max(left, right)
        elif mode == "subtract":
            value = left * (1.0 - right)
        else:
            value = min(left, right)
        result.append(_clamp(value))
    return result


def combine_regions(region_weights):
    arrays = [list(values) for values in region_weights]
    if not arrays:
        return []
    length = len(arrays[0])
    if any(len(values) != length for values in arrays):
        raise ValueError("Region weight arrays must have the same length")
    return [max(values[index] for values in arrays) for index in range(length)]


def translate_points(points, weights, vector):
    vector = _vector(vector, 3, (0.0, 0.0, 0.0))
    return [
        tuple(point[axis] + vector[axis] * _clamp(weight) for axis in range(3))
        for point, weight in zip(points, weights)
    ]


def inflate_points(points, normals, weights, amount):
    amount = float(amount)
    return [
        tuple(
            point[axis] + normal[axis] * amount * _clamp(weight)
            for axis in range(3)
        )
        for point, normal, weight in zip(points, normals, weights)
    ]


def smooth_points(points, neighbors, weights, *, factor=0.5, iterations=1):
    factor = _clamp(factor)
    current = [tuple(point) for point in points]
    for _iteration in range(max(1, min(50, int(iterations)))):
        following = list(current)
        for index, adjacent in enumerate(neighbors):
            weight = _clamp(weights[index])
            valid = [neighbor for neighbor in adjacent if 0 <= neighbor < len(current)]
            if weight <= _EPSILON or not valid:
                continue
            average = tuple(
                sum(current[neighbor][axis] for neighbor in valid) / len(valid)
                for axis in range(3)
            )
            following[index] = tuple(
                current[index][axis]
                + (average[axis] - current[index][axis]) * factor * weight
                for axis in range(3)
            )
        current = following
    return current


def diffuse_weights(weights, neighbors, *, steps=0, decay=0.75):
    """Expand weighted regions through mesh adjacency with bounded decay."""

    current = [_clamp(weight) for weight in weights]
    decay = _clamp(decay)
    for _step in range(max(0, min(64, int(steps)))):
        following = list(current)
        for index, adjacent in enumerate(neighbors):
            valid = [neighbor for neighbor in adjacent if 0 <= neighbor < len(current)]
            if valid:
                following[index] = max(
                    current[index],
                    max(current[neighbor] * decay for neighbor in valid),
                )
        current = following
    return current


def vertex_normals(points, faces):
    """Return area-weighted vertex normals for polygonal mesh data."""

    accumulated = [[0.0, 0.0, 0.0] for _point in points]
    for face in faces:
        indices = [int(index) for index in face]
        if len(indices) < 3 or any(index < 0 or index >= len(points) for index in indices):
            continue
        origin = points[indices[0]]
        for offset in range(1, len(indices) - 1):
            first = points[indices[offset]]
            second = points[indices[offset + 1]]
            left = tuple(first[axis] - origin[axis] for axis in range(3))
            right = tuple(second[axis] - origin[axis] for axis in range(3))
            normal = (
                left[1] * right[2] - left[2] * right[1],
                left[2] * right[0] - left[0] * right[2],
                left[0] * right[1] - left[1] * right[0],
            )
            for index in (indices[0], indices[offset], indices[offset + 1]):
                for axis in range(3):
                    accumulated[index][axis] += normal[axis]
    result = []
    for normal in accumulated:
        magnitude = math.sqrt(sum(component * component for component in normal))
        result.append(
            tuple(component / magnitude for component in normal)
            if magnitude > _EPSILON
            else (0.0, 0.0, 1.0)
        )
    return result


def curvature_values(normals, neighbors):
    """Estimate normalized local curvature from adjacent normal disagreement."""

    result = []
    for index, adjacent in enumerate(neighbors):
        valid = [neighbor for neighbor in adjacent if 0 <= neighbor < len(normals)]
        if not valid:
            result.append(0.0)
            continue
        disagreement = sum(
            (1.0 - _clamp(sum(normals[index][axis] * normals[neighbor][axis] for axis in range(3)), -1.0, 1.0))
            * 0.5
            for neighbor in valid
        ) / len(valid)
        result.append(_clamp(disagreement))
    return result


def _tangent(vector, normal):
    along = sum(vector[axis] * normal[axis] for axis in range(3))
    return tuple(vector[axis] - normal[axis] * along for axis in range(3))


def tangent_relax_points(
    points,
    faces,
    neighbors,
    weights,
    *,
    factor=0.25,
    iterations=1,
    feature_preservation=0.5,
):
    """Relax spacing in each tangent plane while protecting curved features."""

    factor = _clamp(factor)
    feature_preservation = _clamp(feature_preservation)
    current = [tuple(point) for point in points]
    for _iteration in range(max(1, min(50, int(iterations)))):
        normals = vertex_normals(current, faces)
        curvature = curvature_values(normals, neighbors)
        following = list(current)
        for index, adjacent in enumerate(neighbors):
            valid = [neighbor for neighbor in adjacent if 0 <= neighbor < len(current)]
            influence = _clamp(weights[index]) * (
                1.0 - feature_preservation * curvature[index]
            )
            if not valid or influence <= _EPSILON:
                continue
            average = tuple(
                sum(current[neighbor][axis] for neighbor in valid) / len(valid)
                for axis in range(3)
            )
            delta = _tangent(
                tuple(average[axis] - current[index][axis] for axis in range(3)),
                normals[index],
            )
            following[index] = tuple(
                current[index][axis] + delta[axis] * factor * influence
                for axis in range(3)
            )
        current = following
    return current


def pinch_points(
    points,
    faces,
    neighbors,
    weights,
    *,
    strength=0.25,
    depth=0.0,
    center=None,
    iterations=1,
    feature_preservation=0.5,
):
    """Pull a weighted region tangentially toward a center with optional crease depth."""

    current = [tuple(point) for point in points]
    iterations = max(1, min(50, int(iterations)))
    strength = max(-1.0, min(1.0, float(strength))) / iterations
    depth = float(depth) / iterations
    feature_preservation = _clamp(feature_preservation)
    if center is None:
        total_weight = sum(_clamp(weight) for weight in weights)
        if total_weight <= _EPSILON:
            raise ValueError("Pinch field requires at least one weighted point")
        center = tuple(
            sum(point[axis] * _clamp(weight) for point, weight in zip(points, weights))
            / total_weight
            for axis in range(3)
        )
    else:
        center = _vector(center, 3, (0.0, 0.0, 0.0))
    for _iteration in range(iterations):
        normals = vertex_normals(current, faces)
        curvature = curvature_values(normals, neighbors)
        following = list(current)
        for index, point in enumerate(current):
            influence = _clamp(weights[index]) * (
                1.0 - feature_preservation * curvature[index]
            )
            if influence <= _EPSILON:
                continue
            toward_center = tuple(center[axis] - point[axis] for axis in range(3))
            tangent = _tangent(toward_center, normals[index])
            following[index] = tuple(
                point[axis]
                + tangent[axis] * strength * influence
                + normals[index][axis] * depth * influence
                for axis in range(3)
            )
        current = following
    return current


def flatten_points(points, weights, *, plane_point, plane_normal, factor=1.0):
    plane_point = _vector(plane_point, 3, (0.0, 0.0, 0.0))
    plane_normal = _vector(plane_normal, 3, (0.0, 0.0, 1.0))
    length = math.sqrt(sum(value * value for value in plane_normal))
    if length <= _EPSILON:
        raise ValueError("Flatten plane normal must be non-zero")
    normal = tuple(value / length for value in plane_normal)
    factor = _clamp(factor)
    result = []
    for point, weight in zip(points, weights):
        distance = sum(
            (point[axis] - plane_point[axis]) * normal[axis]
            for axis in range(3)
        )
        influence = factor * _clamp(weight)
        result.append(
            tuple(
                point[axis] - normal[axis] * distance * influence
                for axis in range(3)
            )
        )
    return result


def signed_volume(points, faces):
    volume = 0.0
    for face in faces:
        indices = list(face)
        if len(indices) < 3:
            continue
        origin = points[indices[0]]
        for offset in range(1, len(indices) - 1):
            first = points[indices[offset]]
            second = points[indices[offset + 1]]
            cross = (
                first[1] * second[2] - first[2] * second[1],
                first[2] * second[0] - first[0] * second[2],
                first[0] * second[1] - first[1] * second[0],
            )
            volume += sum(origin[axis] * cross[axis] for axis in range(3)) / 6.0
    return volume


def is_closed_surface(faces):
    edge_counts = {}
    edge_directions = {}
    for face in faces:
        indices = list(face)
        if len(indices) < 3:
            return False
        for index, first in enumerate(indices):
            second = indices[(index + 1) % len(indices)]
            edge = tuple(sorted((int(first), int(second))))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
            direction = 1 if (int(first), int(second)) == edge else -1
            edge_directions[edge] = edge_directions.get(edge, 0) + direction
    return bool(edge_counts) and all(
        count == 2 and edge_directions[edge] == 0
        for edge, count in edge_counts.items()
    )


def compensate_volume(original, deformed, faces, weights, *, strength=1.0):
    """Apply a bounded weighted scale that moves volume toward its original value."""

    if not is_closed_surface(faces):
        return list(deformed), {
            "applied": False,
            "reason": "mesh surface is open, non-manifold, or inconsistently wound",
            "before": abs(signed_volume(original, faces)),
            "after": abs(signed_volume(deformed, faces)),
            "corrected": abs(signed_volume(deformed, faces)),
        }
    before = abs(signed_volume(original, faces))
    after = abs(signed_volume(deformed, faces))
    strength = _clamp(strength)
    if before <= _EPSILON or after <= _EPSILON or strength <= _EPSILON:
        return list(deformed), {
            "applied": False,
            "before": before,
            "after": after,
            "corrected": after,
        }
    uncorrected_error = abs(after - before)
    if uncorrected_error <= _EPSILON:
        return list(deformed), {
            "applied": False,
            "reason": "mesh volume is already preserved",
            "before": before,
            "after": after,
            "corrected": after,
        }
    total_weight = sum(_clamp(weight) for weight in weights)
    if total_weight <= _EPSILON:
        return list(deformed), {
            "applied": False,
            "before": before,
            "after": after,
            "corrected": after,
        }
    center = tuple(
        sum(point[axis] for point in deformed) / len(deformed)
        for axis in range(3)
    )
    target_scale = (before / after) ** (1.0 / 3.0)
    target_scale = max(0.5, min(2.0, target_scale))
    scale = 1.0 + (target_scale - 1.0) * strength
    corrected = []
    for point, weight in zip(deformed, weights):
        influence = _clamp(weight)
        corrected.append(
            tuple(
                point[axis]
                + (point[axis] - center[axis]) * (scale - 1.0) * influence
                for axis in range(3)
            )
        )
    corrected_volume = abs(signed_volume(corrected, faces))
    if abs(corrected_volume - before) >= uncorrected_error - _EPSILON:
        return list(deformed), {
            "applied": False,
            "reason": "bounded correction did not improve volume error",
            "before": before,
            "after": after,
            "corrected": after,
            "scale": scale,
        }
    return corrected, {
        "applied": True,
        "before": before,
        "after": after,
        "corrected": corrected_volume,
        "scale": scale,
    }


def mirror_deltas(points, deltas, weights, *, axis=0, tolerance=1e-4):
    """Reflect weighted deformation deltas onto matching mirrored vertices."""

    axis = max(0, min(2, int(axis)))
    tolerance = max(_EPSILON, float(tolerance))

    def key(point):
        return tuple(int(round(float(value) / tolerance)) for value in point)

    lookup = {}
    for index, point in enumerate(points):
        lookup.setdefault(key(point), []).append(index)
    result = [tuple(delta) for delta in deltas]
    result_weights = [_clamp(weight) for weight in weights]
    for index, point in enumerate(points):
        source_weight = _clamp(weights[index])
        if source_weight <= _EPSILON:
            continue
        mirrored_point = list(point)
        mirrored_point[axis] *= -1.0
        mirrored_indices = lookup.get(key(mirrored_point), ())
        if not mirrored_indices:
            continue
        mirrored_delta = list(deltas[index])
        mirrored_delta[axis] *= -1.0
        for mirrored_index in mirrored_indices:
            if source_weight > result_weights[mirrored_index] + _EPSILON:
                result[mirrored_index] = tuple(mirrored_delta)
                result_weights[mirrored_index] = source_weight
            elif abs(source_weight - result_weights[mirrored_index]) <= _EPSILON:
                result[mirrored_index] = tuple(
                    (result[mirrored_index][component] + mirrored_delta[component])
                    * 0.5
                    for component in range(3)
                )
    return result, result_weights
