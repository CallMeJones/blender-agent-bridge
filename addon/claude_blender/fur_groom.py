"""Pure geometry helpers for deterministic directional fur grooms."""

from __future__ import annotations

import bisect
import math
import random


_EPSILON = 1.0e-9


def _vector(value, fallback=(0.0, 0.0, 0.0)):
    try:
        values = tuple(float(component) for component in value)
    except (TypeError, ValueError):
        return tuple(float(component) for component in fallback)
    if len(values) != 3 or not all(math.isfinite(component) for component in values):
        return tuple(float(component) for component in fallback)
    return values


def _add(left, right):
    return tuple(left[index] + right[index] for index in range(3))


def _subtract(left, right):
    return tuple(left[index] - right[index] for index in range(3))


def _scale(vector, amount):
    return tuple(component * amount for component in vector)


def _dot(left, right):
    return sum(left[index] * right[index] for index in range(3))


def _cross(left, right):
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _length(vector):
    return math.sqrt(max(0.0, _dot(vector, vector)))


def _normalized(vector, fallback=(0.0, 0.0, 1.0)):
    vector = _vector(vector, fallback)
    magnitude = _length(vector)
    if magnitude <= _EPSILON:
        vector = _vector(fallback, (0.0, 0.0, 1.0))
        magnitude = max(_EPSILON, _length(vector))
    return _scale(vector, 1.0 / magnitude)


def triangle_area(vertices):
    """Return the area of one 3D triangle."""
    if not isinstance(vertices, (list, tuple)) or len(vertices) != 3:
        return 0.0
    a, b, c = (_vector(vertex) for vertex in vertices)
    return 0.5 * _length(_cross(_subtract(b, a), _subtract(c, a)))


def project_to_tangent(direction, normal):
    """Project a direction onto a stable tangent plane."""
    normal = _normalized(normal)
    direction = _normalized(direction, (1.0, 0.0, 0.0))
    tangent = _subtract(direction, _scale(normal, _dot(direction, normal)))
    if _length(tangent) <= _EPSILON:
        fallback = (0.0, 1.0, 0.0) if abs(normal[1]) < 0.9 else (1.0, 0.0, 0.0)
        tangent = _subtract(fallback, _scale(normal, _dot(fallback, normal)))
    return _normalized(tangent, (1.0, 0.0, 0.0))


def blend_flow_controls(point, base_direction, controls):
    """Blend bounded world-space flow controls into a base direction."""
    point = _vector(point)
    weighted = _vector(base_direction, (1.0, 0.0, 0.0))
    total_weight = 1.0
    for control in list(controls or [])[:64]:
        if not isinstance(control, dict):
            continue
        location = _vector(control.get("location"))
        radius = _finite_float(control.get("radius"), 1.0, minimum=_EPSILON)
        strength = _finite_float(control.get("strength"), 1.0, minimum=0.0, maximum=10.0)
        distance = _length(_subtract(point, location))
        if distance >= radius or strength <= 0.0:
            continue
        weight = strength * (1.0 - distance / radius) ** 2
        direction = _normalized(control.get("direction"), base_direction)
        weighted = _add(weighted, _scale(direction, weight))
        total_weight += weight
    return _normalized(_scale(weighted, 1.0 / total_weight), base_direction)


def allocate_weighted_counts(weights, total):
    """Allocate an exact bounded integer budget using largest remainders."""
    total = max(0, int(total or 0))
    clean = [max(0.0, _finite_float(weight, 0.0)) for weight in list(weights or [])]
    if not clean or total <= 0:
        return [0 for _weight in clean]
    weight_sum = sum(clean)
    if weight_sum <= _EPSILON:
        clean = [1.0 for _weight in clean]
        weight_sum = float(len(clean))
    exact = [total * weight / weight_sum for weight in clean]
    allocated = [int(math.floor(value)) for value in exact]
    remainder = total - sum(allocated)
    order = sorted(
        range(len(clean)),
        key=lambda index: (-(exact[index] - allocated[index]), index),
    )
    for index in order[:remainder]:
        allocated[index] += 1
    return allocated


def allocate_region_counts(regions, total):
    """Allocate a total strand budget across optional explicit region counts."""
    regions = list(regions or [])
    total = max(0, int(total or 0))
    if not regions:
        return []
    explicit = []
    for region in regions:
        value = region.get("count") if isinstance(region, dict) else None
        try:
            count = int(value)
        except (TypeError, ValueError):
            count = -1
        explicit.append(count if count >= 0 else None)
    explicit_total = sum(count for count in explicit if count is not None)
    if explicit_total >= total:
        weights = [float(count or 0) for count in explicit]
        return allocate_weighted_counts(weights, total)
    remaining = total - explicit_total
    unspecified = [index for index, count in enumerate(explicit) if count is None]
    allocated = [count or 0 for count in explicit]
    if not unspecified:
        return allocated
    weights = [
        _finite_float(regions[index].get("density"), 1.0, minimum=0.0)
        for index in unspecified
    ]
    shares = allocate_weighted_counts(weights, remaining)
    for index, share in zip(unspecified, shares):
        allocated[index] = share
    return allocated


def sample_surface(triangles, count, *, seed=0, minimum_spacing=0.0, oversample=8):
    """Sample weighted triangles by world-space area with optional spatial thinning."""
    prepared = []
    cumulative = []
    total_weight = 0.0
    for triangle_index, triangle in enumerate(triangles or []):
        if not isinstance(triangle, dict):
            continue
        vertices = triangle.get("vertices")
        area = triangle_area(vertices)
        density = _finite_float(triangle.get("weight"), 1.0, minimum=0.0)
        vertex_weights = triangle.get("vertex_weights")
        if isinstance(vertex_weights, (list, tuple)) and len(vertex_weights) == 3:
            vertex_weights = tuple(
                _finite_float(value, 0.0, minimum=0.0)
                for value in vertex_weights
            )
            density *= sum(vertex_weights) / 3.0
        else:
            vertex_weights = None
        weight = area * density
        if weight <= _EPSILON:
            continue
        normal = triangle.get("normal")
        if normal is None:
            a, b, c = (_vector(vertex) for vertex in vertices)
            normal = _cross(_subtract(b, a), _subtract(c, a))
        prepared.append(
            {
                "vertices": tuple(_vector(vertex) for vertex in vertices),
                "normal": _normalized(normal),
                "triangle_index": triangle_index,
                "vertex_weights": vertex_weights,
            }
        )
        total_weight += weight
        cumulative.append(total_weight)
    count = max(0, int(count or 0))
    if not prepared or count <= 0:
        return []

    spacing = _finite_float(minimum_spacing, 0.0, minimum=0.0)
    candidate_count = count if spacing <= _EPSILON else count * max(2, min(20, int(oversample or 8)))
    rng = random.Random(int(seed or 0))
    candidates = []
    for _index in range(candidate_count):
        choice = bisect.bisect_left(cumulative, rng.random() * total_weight)
        triangle = prepared[min(choice, len(prepared) - 1)]
        a, b, c = triangle["vertices"]
        barycentric = (1.0, 0.0, 0.0)
        for _attempt in range(24):
            root = math.sqrt(rng.random())
            barycentric = (
                1.0 - root,
                root * (1.0 - rng.random()),
                0.0,
            )
            barycentric = (
                barycentric[0],
                barycentric[1],
                1.0 - barycentric[0] - barycentric[1],
            )
            vertex_weights = triangle["vertex_weights"]
            if vertex_weights is None:
                break
            interpolated = sum(
                barycentric[index] * vertex_weights[index]
                for index in range(3)
            )
            if rng.random() * max(vertex_weights) <= interpolated:
                break
        point = _add(
            _add(_scale(a, barycentric[0]), _scale(b, barycentric[1])),
            _scale(c, barycentric[2]),
        )
        candidates.append(
            {
                "point": point,
                "normal": triangle["normal"],
                "triangle_index": triangle["triangle_index"],
            }
        )
    if spacing <= _EPSILON:
        return candidates[:count]
    return _spatially_thin(candidates, count, spacing)


def _spatially_thin(candidates, count, spacing):
    cell_size = max(_EPSILON, float(spacing))
    spacing_squared = spacing * spacing
    cells = {}
    accepted = []
    for candidate in candidates:
        point = candidate["point"]
        cell = tuple(int(math.floor(component / cell_size)) for component in point)
        nearby = False
        for x_offset in (-1, 0, 1):
            for y_offset in (-1, 0, 1):
                for z_offset in (-1, 0, 1):
                    neighbor = (
                        cell[0] + x_offset,
                        cell[1] + y_offset,
                        cell[2] + z_offset,
                    )
                    for accepted_index in cells.get(neighbor, ()):
                        delta = _subtract(point, accepted[accepted_index]["point"])
                        if _dot(delta, delta) < spacing_squared:
                            nearby = True
                            break
                    if nearby:
                        break
                if nearby:
                    break
            if nearby:
                break
        if nearby:
            continue
        accepted_index = len(accepted)
        accepted.append(candidate)
        cells.setdefault(cell, []).append(accepted_index)
        if len(accepted) >= count:
            break
    return accepted


def clump_vectors(samples, clump_size):
    """Return bounded vectors toward deterministic nearby clump leaders."""
    points = [_vector(sample.get("point")) for sample in samples or []]
    size = max(1, int(clump_size or 1))
    if size <= 1 or len(points) <= 1:
        return [(0.0, 0.0, 0.0) for _point in points]
    leaders = points[::size]
    vectors = []
    for point in points:
        leader = min(leaders, key=lambda candidate: _dot(_subtract(candidate, point), _subtract(candidate, point)))
        vectors.append(_subtract(leader, point))
    return vectors


def strand_path(
    root,
    normal,
    flow_direction,
    *,
    length,
    point_count=5,
    flow_strength=0.75,
    normal_lift=0.25,
    clump_vector=(0.0, 0.0, 0.0),
    clump_strength=0.0,
    noise_strength=0.0,
    seed=0,
):
    """Create one smooth, laid-down strand path from a surface root."""
    root = _vector(root)
    normal = _normalized(normal)
    tangent = project_to_tangent(flow_direction, normal)
    flow_weight = _finite_float(flow_strength, 0.75, minimum=0.0, maximum=1.0)
    lift_weight = _finite_float(normal_lift, 0.25, minimum=0.0, maximum=1.0)
    direction = _normalized(
        _add(_scale(tangent, flow_weight), _scale(normal, lift_weight)),
        normal,
    )
    strand_length = _finite_float(length, 0.001, minimum=0.001)
    points = max(2, min(16, int(point_count or 5)))
    clump = project_to_tangent(clump_vector, normal) if _length(_vector(clump_vector)) > _EPSILON else (0.0, 0.0, 0.0)
    clump_distance = min(strand_length, _length(_vector(clump_vector)))
    clump = _scale(clump, clump_distance)
    clump_weight = _finite_float(clump_strength, 0.0, minimum=0.0, maximum=1.0)
    noise_weight = _finite_float(noise_strength, 0.0, minimum=0.0, maximum=1.0)
    rng = random.Random(int(seed or 0))
    noise = project_to_tangent(
        (
            rng.uniform(-1.0, 1.0),
            rng.uniform(-1.0, 1.0),
            rng.uniform(-1.0, 1.0),
        ),
        normal,
    )
    path = []
    for index in range(points):
        t = index / max(1, points - 1)
        bend = math.sin(math.pi * t)
        position = _add(root, _scale(direction, strand_length * t))
        position = _add(position, _scale(normal, strand_length * bend * lift_weight * 0.12))
        position = _add(position, _scale(clump, clump_weight * t * t))
        position = _add(position, _scale(noise, strand_length * noise_weight * bend * 0.2))
        path.append(position)
    return path


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
