"""Pure bounded implicit shape programs for LLM-authored modeling."""

from __future__ import annotations

import hashlib
import json
import math


SCHEMA_VERSION = 1
SUPPORTED_NODE_TYPES = (
    "sphere",
    "ellipsoid",
    "box",
    "capsule",
    "cylinder",
    "torus",
    "superquadric",
    "sweep",
)
SUPPORTED_OPERATIONS = ("union", "subtract", "intersect")
MAX_NODES = 64
MAX_SWEEP_POINTS = 64
MAX_GRID_SAMPLES = 950_000
MAX_SDF_EVALUATIONS = 64_000_000
MAX_OUTPUT_VERTICES = 750_000
MAX_OUTPUT_FACES = 1_500_000
MIN_RESOLUTION = 8
MAX_RESOLUTION = 96
_EPSILON = 1.0e-9
_MAX_COORDINATE = 1_000_000.0
_MIN_SCALE = 1.0e-4
_MAX_SCALE = 10_000.0
_MAX_DISTANCE = 1.0e12


class ShapeProgramError(ValueError):
    """Raised when a shape program is invalid or unsafe to compile."""


def _number(value, field, *, minimum=None, maximum=None):
    if isinstance(value, bool):
        raise ShapeProgramError(f"{field} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ShapeProgramError(f"{field} must be a number") from exc
    if not math.isfinite(result):
        raise ShapeProgramError(f"{field} must be finite")
    if minimum is not None and result < minimum:
        raise ShapeProgramError(f"{field} must be at least {minimum}")
    if maximum is not None and result > maximum:
        raise ShapeProgramError(f"{field} must be at most {maximum}")
    return result


def _vector(
    value,
    field,
    *,
    positive=False,
    minimum_value=None,
    maximum_absolute=None,
):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ShapeProgramError(f"{field} must contain three numbers")
    result = tuple(_number(item, f"{field}[{index}]") for index, item in enumerate(value))
    if positive and any(item <= 0.0 for item in result):
        raise ShapeProgramError(f"{field} components must be greater than zero")
    if minimum_value is not None and any(item < minimum_value for item in result):
        raise ShapeProgramError(
            f"{field} components must be at least {minimum_value}"
        )
    if maximum_absolute is not None and any(
        abs(item) > maximum_absolute for item in result
    ):
        raise ShapeProgramError(
            f"{field} components must not exceed {maximum_absolute} in magnitude"
        )
    return result


def _identifier(value, field):
    result = str(value or "").strip()
    if not result:
        raise ShapeProgramError(f"{field} must not be empty")
    if len(result) > 64:
        raise ShapeProgramError(f"{field} must be 64 characters or fewer")
    return result


def _normalize_transform(raw, field):
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ShapeProgramError(f"{field} must be an object")
    return {
        "location": _vector(
            raw.get("location", (0.0, 0.0, 0.0)),
            f"{field}.location",
            maximum_absolute=_MAX_COORDINATE,
        ),
        "rotation": _vector(
            raw.get("rotation", (0.0, 0.0, 0.0)),
            f"{field}.rotation",
            maximum_absolute=_MAX_COORDINATE,
        ),
        "scale": _vector(
            raw.get("scale", (1.0, 1.0, 1.0)),
            f"{field}.scale",
            positive=True,
            maximum_absolute=_MAX_SCALE,
        ),
    }


def _normalize_points(raw, field):
    if not isinstance(raw, list) or not 2 <= len(raw) <= MAX_SWEEP_POINTS:
        raise ShapeProgramError(
            f"{field} must contain between 2 and {MAX_SWEEP_POINTS} points"
        )
    return [
        _vector(
            point,
            f"{field}[{index}]",
            maximum_absolute=_MAX_COORDINATE,
        )
        for index, point in enumerate(raw)
    ]


def _positive_vector2(raw, field):
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ShapeProgramError(f"{field} must contain two numbers")
    return tuple(
        _number(
            value,
            f"{field}[{index}]",
            minimum=1.0e-5,
            maximum=10000.0,
        )
        for index, value in enumerate(raw)
    )


def _normalize_node(raw, index):
    field = f"nodes[{index}]"
    if not isinstance(raw, dict):
        raise ShapeProgramError(f"{field} must be an object")
    node_type = str(raw.get("type") or "").strip().lower()
    if node_type not in SUPPORTED_NODE_TYPES:
        raise ShapeProgramError(
            f"{field}.type must be one of {', '.join(SUPPORTED_NODE_TYPES)}"
        )
    operation = str(raw.get("operation") or "union").strip().lower()
    if operation not in SUPPORTED_OPERATIONS:
        raise ShapeProgramError(
            f"{field}.operation must be one of {', '.join(SUPPORTED_OPERATIONS)}"
        )
    node = {
        "id": _identifier(raw.get("id"), f"{field}.id"),
        "type": node_type,
        "operation": operation,
        "blend": _number(raw.get("blend", 0.0), f"{field}.blend", minimum=0.0, maximum=1000.0),
        "enabled": raw.get("enabled", True),
        "transform": _normalize_transform(raw.get("transform"), f"{field}.transform"),
    }
    if not isinstance(node["enabled"], bool):
        raise ShapeProgramError(f"{field}.enabled must be a boolean")
    if any(value < _MIN_SCALE for value in node["transform"]["scale"]):
        raise ShapeProgramError(
            f"{field}.transform.scale components must be at least {_MIN_SCALE}"
        )
    parent_id = str(raw.get("parent_id") or "").strip()
    if parent_id:
        node["parent_id"] = _identifier(parent_id, f"{field}.parent_id")
    semantic_role = str(raw.get("semantic_role") or "").strip()
    if semantic_role:
        node["semantic_role"] = semantic_role[:120]
    raw_target_ids = raw.get("target_ids")
    if raw_target_ids is not None:
        if operation not in {"subtract", "intersect"}:
            raise ShapeProgramError(
                f"{field}.target_ids requires subtract or intersect"
            )
        if not isinstance(raw_target_ids, (list, tuple)) or not raw_target_ids:
            raise ShapeProgramError(f"{field}.target_ids must contain node ids")
        target_ids = [
            _identifier(value, f"{field}.target_ids[{item_index}]")
            for item_index, value in enumerate(raw_target_ids)
        ]
        if len(target_ids) > MAX_NODES or len(set(target_ids)) != len(target_ids):
            raise ShapeProgramError(
                f"{field}.target_ids must contain unique node ids"
            )
        node["target_ids"] = target_ids

    if node_type == "sphere":
        node["radius"] = _number(raw.get("radius", 1.0), f"{field}.radius", minimum=1.0e-5, maximum=10000.0)
    elif node_type == "ellipsoid":
        node["radii"] = _vector(
            raw.get("radii", (1.0, 1.0, 1.0)),
            f"{field}.radii",
            positive=True,
            minimum_value=1.0e-5,
            maximum_absolute=10000.0,
        )
    elif node_type == "box":
        node["size"] = _vector(
            raw.get("size", (1.0, 1.0, 1.0)),
            f"{field}.size",
            positive=True,
            minimum_value=1.0e-5,
            maximum_absolute=10000.0,
        )
        node["rounding"] = _number(raw.get("rounding", 0.0), f"{field}.rounding", minimum=0.0, maximum=1000.0)
        if node["rounding"] > min(node["size"]) * 0.5:
            raise ShapeProgramError(
                f"{field}.rounding may not exceed half the shortest box size"
            )
    elif node_type == "capsule":
        node["point_a"] = _vector(
            raw.get("point_a", (0.0, 0.0, -0.5)),
            f"{field}.point_a",
            maximum_absolute=_MAX_COORDINATE,
        )
        node["point_b"] = _vector(
            raw.get("point_b", (0.0, 0.0, 0.5)),
            f"{field}.point_b",
            maximum_absolute=_MAX_COORDINATE,
        )
        node["radius"] = _number(raw.get("radius", 0.25), f"{field}.radius", minimum=1.0e-5, maximum=10000.0)
        if raw.get("cross_section") is not None:
            node["cross_section"] = _positive_vector2(
                raw.get("cross_section"), f"{field}.cross_section"
            )
        if raw.get("cross_section_rotation") is not None:
            node["cross_section_rotation"] = _number(
                raw.get("cross_section_rotation"),
                f"{field}.cross_section_rotation",
                minimum=-math.tau * 100.0,
                maximum=math.tau * 100.0,
            )
    elif node_type == "cylinder":
        node["radius"] = _number(raw.get("radius", 0.5), f"{field}.radius", minimum=1.0e-5, maximum=10000.0)
        node["depth"] = _number(raw.get("depth", 1.0), f"{field}.depth", minimum=1.0e-5, maximum=10000.0)
        node["rounding"] = _number(raw.get("rounding", 0.0), f"{field}.rounding", minimum=0.0, maximum=1000.0)
        if node["rounding"] > min(node["radius"], node["depth"] * 0.5):
            raise ShapeProgramError(
                f"{field}.rounding exceeds the cylinder radius or half-depth"
            )
    elif node_type == "torus":
        node["major_radius"] = _number(raw.get("major_radius", 0.75), f"{field}.major_radius", minimum=1.0e-5, maximum=10000.0)
        node["minor_radius"] = _number(raw.get("minor_radius", 0.25), f"{field}.minor_radius", minimum=1.0e-5, maximum=10000.0)
    elif node_type == "superquadric":
        node["radii"] = _vector(
            raw.get("radii", (1.0, 1.0, 1.0)),
            f"{field}.radii",
            positive=True,
            minimum_value=1.0e-5,
            maximum_absolute=10000.0,
        )
        exponents = raw.get("exponents", (1.0, 1.0))
        if not isinstance(exponents, (list, tuple)) or len(exponents) != 2:
            raise ShapeProgramError(f"{field}.exponents must contain two numbers")
        node["exponents"] = tuple(
            _number(value, f"{field}.exponents[{item_index}]", minimum=0.1, maximum=4.0)
            for item_index, value in enumerate(exponents)
        )
    elif node_type == "sweep":
        points = _normalize_points(raw.get("points"), f"{field}.points")
        radii = raw.get("radii", [0.25] * len(points))
        if not isinstance(radii, (list, tuple)) or len(radii) != len(points):
            raise ShapeProgramError(
                f"{field}.radii must contain one radius per sweep point"
            )
        node["points"] = points
        node["radii"] = [
            _number(value, f"{field}.radii[{item_index}]", minimum=1.0e-5, maximum=10000.0)
            for item_index, value in enumerate(radii)
        ]
        raw_cross_sections = raw.get("cross_sections")
        if raw_cross_sections is not None:
            if (
                not isinstance(raw_cross_sections, (list, tuple))
                or len(raw_cross_sections) != len(points)
            ):
                raise ShapeProgramError(
                    f"{field}.cross_sections must contain one [width, depth] pair per sweep point"
                )
            node["cross_sections"] = [
                _positive_vector2(value, f"{field}.cross_sections[{item_index}]")
                for item_index, value in enumerate(raw_cross_sections)
            ]
        raw_rotations = raw.get("cross_section_rotations")
        if raw_rotations is not None:
            if (
                not isinstance(raw_rotations, (list, tuple))
                or len(raw_rotations) != len(points)
            ):
                raise ShapeProgramError(
                    f"{field}.cross_section_rotations must contain one angle per sweep point"
                )
            node["cross_section_rotations"] = [
                _number(
                    value,
                    f"{field}.cross_section_rotations[{item_index}]",
                    minimum=-math.tau * 100.0,
                    maximum=math.tau * 100.0,
                )
                for item_index, value in enumerate(raw_rotations)
            ]
    return node


def _validate_parent_graph(nodes):
    by_id = {node["id"]: node for node in nodes}
    for node in nodes:
        parent_id = node.get("parent_id")
        if parent_id and parent_id not in by_id:
            raise ShapeProgramError(
                f"Node {node['id']!r} references missing parent {parent_id!r}"
            )
        if parent_id == node["id"]:
            raise ShapeProgramError(f"Node {node['id']!r} cannot parent itself")
    for node in nodes:
        seen = set()
        current = node
        minimum_scale = 1.0
        maximum_scale = 1.0
        while current.get("parent_id"):
            if current["id"] in seen:
                raise ShapeProgramError(
                    f"Parent cycle detected at node {current['id']!r}"
                )
            seen.add(current["id"])
            minimum_scale *= min(current["transform"]["scale"])
            maximum_scale *= max(current["transform"]["scale"])
            current = by_id[current["parent_id"]]
        minimum_scale *= min(current["transform"]["scale"])
        maximum_scale *= max(current["transform"]["scale"])
        if minimum_scale < _MIN_SCALE or maximum_scale > _MAX_SCALE:
            raise ShapeProgramError(
                f"Node {node['id']!r} has a cumulative transform scale outside "
                f"the supported {_MIN_SCALE} to {_MAX_SCALE} range"
            )
    return by_id


def _validate_boolean_targets(nodes, by_id):
    positions = {node["id"]: index for index, node in enumerate(nodes)}
    for node in nodes:
        for target_id in node.get("target_ids", ()):
            target = by_id.get(target_id)
            if target is None:
                raise ShapeProgramError(
                    f"Node {node['id']!r} references missing boolean target {target_id!r}"
                )
            if positions[target_id] >= positions[node["id"]]:
                raise ShapeProgramError(
                    f"Node {node['id']!r} must target an earlier node"
                )
            if node["enabled"] and not target["enabled"]:
                raise ShapeProgramError(
                    f"Enabled node {node['id']!r} cannot target disabled node {target_id!r}"
                )
            if target["operation"] != "union":
                raise ShapeProgramError(
                    f"Boolean target {target_id!r} must use the union operation"
                )


def normalize_shape_program(program):
    """Validate and return the canonical shape-program representation."""

    if not isinstance(program, dict):
        raise ShapeProgramError("program must be an object")
    version = program.get("schema_version", SCHEMA_VERSION)
    if isinstance(version, bool) or not isinstance(version, int):
        raise ShapeProgramError("schema_version must be an integer")
    if version != SCHEMA_VERSION:
        raise ShapeProgramError(
            f"schema_version must be {SCHEMA_VERSION}; received {version}"
        )
    raw_bounds = program.get("bounds")
    if not isinstance(raw_bounds, dict):
        raise ShapeProgramError("bounds must be an object with min and max vectors")
    minimum = _vector(
        raw_bounds.get("min"),
        "bounds.min",
        maximum_absolute=_MAX_COORDINATE,
    )
    maximum = _vector(
        raw_bounds.get("max"),
        "bounds.max",
        maximum_absolute=_MAX_COORDINATE,
    )
    if any(maximum[index] <= minimum[index] for index in range(3)):
        raise ShapeProgramError("Each bounds.max component must exceed bounds.min")
    if any(maximum[index] - minimum[index] > 10000.0 for index in range(3)):
        raise ShapeProgramError("Shape-program bounds may not exceed 10000 units per axis")

    raw_nodes = program.get("nodes")
    if not isinstance(raw_nodes, list) or not 1 <= len(raw_nodes) <= MAX_NODES:
        raise ShapeProgramError(f"nodes must contain between 1 and {MAX_NODES} entries")
    nodes = [_normalize_node(raw, index) for index, raw in enumerate(raw_nodes)]
    identifiers = [node["id"] for node in nodes]
    if len(set(identifiers)) != len(identifiers):
        duplicate = next(item for item in identifiers if identifiers.count(item) > 1)
        raise ShapeProgramError(f"Duplicate node id {duplicate!r}")
    by_id = _validate_parent_graph(nodes)
    _validate_boolean_targets(nodes, by_id)
    enabled = [node for node in nodes if node["enabled"]]
    if not enabled:
        raise ShapeProgramError("At least one node must be enabled")
    if enabled[0]["operation"] != "union":
        raise ShapeProgramError("The first enabled node must use the union operation")

    normalized = {
        "schema_version": SCHEMA_VERSION,
        "name": str(program.get("name") or "Implicit Shape")[:120],
        "bounds": {"min": minimum, "max": maximum},
        "nodes": nodes,
    }
    metadata = program.get("metadata")
    if isinstance(metadata, dict):
        safe_metadata = {}
        for key, value in list(metadata.items())[:32]:
            if not (isinstance(value, (str, int, float, bool)) or value is None):
                continue
            if isinstance(value, float) and not math.isfinite(value):
                continue
            safe_metadata[str(key)[:64]] = value[:1024] if isinstance(value, str) else value
        normalized["metadata"] = safe_metadata
    return normalized


def canonical_program_json(program):
    """Return stable compact JSON after validating a shape program."""

    return json.dumps(
        normalize_shape_program(program),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def shape_program_digest(program):
    """Return a stable SHA-256 identity for a validated shape program."""

    return hashlib.sha256(canonical_program_json(program).encode("utf-8")).hexdigest()


def shape_program_summary(program):
    """Return compact semantic and operation counts for a shape program."""

    normalized = normalize_shape_program(program)
    type_counts = {}
    operation_counts = {}
    roles = []
    for node in normalized["nodes"]:
        type_counts[node["type"]] = type_counts.get(node["type"], 0) + 1
        operation_counts[node["operation"]] = operation_counts.get(node["operation"], 0) + 1
        if node.get("semantic_role") and node["semantic_role"] not in roles:
            roles.append(node["semantic_role"])
    return {
        "schema_version": normalized["schema_version"],
        "name": normalized["name"],
        "node_count": len(normalized["nodes"]),
        "enabled_node_count": sum(node["enabled"] for node in normalized["nodes"]),
        "type_counts": type_counts,
        "operation_counts": operation_counts,
        "semantic_roles": roles,
        "bounds": normalized["bounds"],
        "digest": shape_program_digest(normalized),
    }


def _subtract(left, right):
    return tuple(left[index] - right[index] for index in range(3))


def _add(left, right):
    return tuple(left[index] + right[index] for index in range(3))


def _scale(vector, amount):
    return tuple(component * amount for component in vector)


def _dot(left, right):
    return sum(left[index] * right[index] for index in range(3))


def _length(value):
    return math.sqrt(max(0.0, _dot(value, value)))


def _rotate_x(point, angle):
    cosine, sine = math.cos(angle), math.sin(angle)
    return (point[0], cosine * point[1] - sine * point[2], sine * point[1] + cosine * point[2])


def _rotate_y(point, angle):
    cosine, sine = math.cos(angle), math.sin(angle)
    return (cosine * point[0] + sine * point[2], point[1], -sine * point[0] + cosine * point[2])


def _rotate_z(point, angle):
    cosine, sine = math.cos(angle), math.sin(angle)
    return (cosine * point[0] - sine * point[1], sine * point[0] + cosine * point[1], point[2])


def _inverse_transform(point, transform):
    local = _subtract(point, transform["location"])
    rotation = transform["rotation"]
    local = _rotate_z(local, -rotation[2])
    local = _rotate_y(local, -rotation[1])
    local = _rotate_x(local, -rotation[0])
    return tuple(local[index] / transform["scale"][index] for index in range(3))


def _transform_chains(nodes, by_id):
    chains = {}
    for node in nodes:
        chain = []
        current = node
        while current is not None:
            chain.append(current["transform"])
            current = by_id.get(current.get("parent_id"))
        chains[node["id"]] = tuple(reversed(chain))
    return chains


def _local_point_and_scale(point, node, transform_chains):
    local = point
    distance_scale = 1.0
    for transform in transform_chains[node["id"]]:
        local = _inverse_transform(local, transform)
        distance_scale *= min(transform["scale"])
    return local, distance_scale


def _ellipsoid_distance(point, radii):
    scaled = tuple(point[index] / radii[index] for index in range(3))
    squared_scaled = tuple(point[index] / (radii[index] * radii[index]) for index in range(3))
    k0 = _length(scaled)
    k1 = _length(squared_scaled)
    if k1 <= _EPSILON:
        return -min(radii)
    return k0 * (k0 - 1.0) / k1


def _box_distance(point, size, rounding):
    half = tuple(max(_EPSILON, size[index] * 0.5 - rounding) for index in range(3))
    q = tuple(abs(point[index]) - half[index] for index in range(3))
    outside = _length(tuple(max(value, 0.0) for value in q))
    return outside + min(max(q), 0.0) - rounding


def _segment_distance(point, first, second, first_radius, second_radius):
    segment = _subtract(second, first)
    length_squared = _dot(segment, segment)
    if length_squared <= _EPSILON:
        return _length(_subtract(point, first)) - max(first_radius, second_radius)
    factor = max(0.0, min(1.0, _dot(_subtract(point, first), segment) / length_squared))
    nearest = tuple(first[index] + segment[index] * factor for index in range(3))
    radius = first_radius + (second_radius - first_radius) * factor
    return _length(_subtract(point, nearest)) - radius


def _ellipse_distance(point, radii):
    scaled = (point[0] / radii[0], point[1] / radii[1])
    squared_scaled = (
        point[0] / (radii[0] * radii[0]),
        point[1] / (radii[1] * radii[1]),
    )
    k0 = math.hypot(*scaled)
    k1 = math.hypot(*squared_scaled)
    if k1 <= _EPSILON:
        return -min(radii)
    return k0 * (k0 - 1.0) / k1


def _segment_cross_section_distance(
    point,
    first,
    second,
    first_cross_section,
    second_cross_section,
    first_rotation=0.0,
    second_rotation=0.0,
):
    segment = _subtract(second, first)
    length_squared = _dot(segment, segment)
    if length_squared <= _EPSILON:
        return _ellipsoid_distance(
            _subtract(point, first),
            (first_cross_section[0], first_cross_section[1], min(first_cross_section)),
        )
    projected_factor = _dot(_subtract(point, first), segment) / length_squared
    factor = max(0.0, min(1.0, projected_factor))
    nearest = tuple(
        first[index] + segment[index] * factor for index in range(3)
    )
    tangent = _scale(segment, 1.0 / math.sqrt(length_squared))
    reference = (0.0, 0.0, 1.0)
    if abs(_dot(tangent, reference)) > 0.9:
        reference = (0.0, 1.0, 0.0)
    first_axis_raw = _cross(tangent, reference)
    first_axis = _scale(first_axis_raw, 1.0 / _length(first_axis_raw))
    second_axis = _cross(tangent, first_axis)
    rotation = first_rotation + (second_rotation - first_rotation) * factor
    cosine, sine = math.cos(rotation), math.sin(rotation)
    rotated_first = _add(_scale(first_axis, cosine), _scale(second_axis, sine))
    rotated_second = _add(_scale(first_axis, -sine), _scale(second_axis, cosine))
    offset = _subtract(point, nearest)
    radii = tuple(
        first_cross_section[index]
        + (second_cross_section[index] - first_cross_section[index]) * factor
        for index in range(2)
    )
    local_first = _dot(offset, rotated_first)
    local_second = _dot(offset, rotated_second)
    if projected_factor < 0.0 or projected_factor > 1.0:
        return _ellipsoid_distance(
            (local_first, local_second, _dot(offset, tangent)),
            (radii[0], radii[1], min(radii)),
        )
    return _ellipse_distance((local_first, local_second), radii)


def _bounded_power(value, exponent):
    if value <= 0.0:
        return 0.0
    logarithm = exponent * math.log(value)
    if logarithm >= math.log(_MAX_DISTANCE):
        return _MAX_DISTANCE
    return math.exp(logarithm)


def _primitive_distance(point, node):
    node_type = node["type"]
    if node_type == "sphere":
        return _length(point) - node["radius"]
    if node_type == "ellipsoid":
        return _ellipsoid_distance(point, node["radii"])
    if node_type == "box":
        return _box_distance(point, node["size"], node["rounding"])
    if node_type == "capsule":
        cross_section = node.get("cross_section")
        if cross_section is not None:
            rotation = node.get("cross_section_rotation", 0.0)
            return _segment_cross_section_distance(
                point,
                node["point_a"],
                node["point_b"],
                cross_section,
                cross_section,
                rotation,
                rotation,
            )
        return _segment_distance(
            point, node["point_a"], node["point_b"], node["radius"], node["radius"]
        )
    if node_type == "cylinder":
        rounding = node["rounding"]
        radial = math.hypot(point[0], point[1]) - (node["radius"] - rounding)
        axial = abs(point[2]) - (node["depth"] * 0.5 - rounding)
        outside = math.hypot(max(radial, 0.0), max(axial, 0.0))
        return outside + min(max(radial, axial), 0.0) - rounding
    if node_type == "torus":
        return math.hypot(math.hypot(point[0], point[1]) - node["major_radius"], point[2]) - node["minor_radius"]
    if node_type == "superquadric":
        radii = node["radii"]
        vertical, horizontal = node["exponents"]
        x = abs(point[0] / radii[0])
        y = abs(point[1] / radii[1])
        z = abs(point[2] / radii[2])
        radial_base = min(
            _MAX_DISTANCE,
            _bounded_power(x, 2.0 / horizontal)
            + _bounded_power(y, 2.0 / horizontal),
        )
        radial = _bounded_power(radial_base, horizontal / vertical)
        field_base = min(
            _MAX_DISTANCE,
            radial + _bounded_power(z, 2.0 / vertical),
        )
        field = _bounded_power(field_base, vertical * 0.5)
        return min(_MAX_DISTANCE, (field - 1.0) * min(radii))
    if node_type == "sweep":
        cross_sections = node.get("cross_sections")
        rotations = node.get("cross_section_rotations") or [0.0] * len(node["points"])
        if cross_sections is not None:
            return min(
                _segment_cross_section_distance(
                    point,
                    node["points"][index],
                    node["points"][index + 1],
                    cross_sections[index],
                    cross_sections[index + 1],
                    rotations[index],
                    rotations[index + 1],
                )
                for index in range(len(node["points"]) - 1)
            )
        return min(
            _segment_distance(
                point,
                node["points"][index],
                node["points"][index + 1],
                node["radii"][index],
                node["radii"][index + 1],
            )
            for index in range(len(node["points"]) - 1)
        )
    raise ShapeProgramError(f"Unsupported node type {node_type!r}")


def _smooth_min(first, second, blend):
    if blend <= _EPSILON:
        return min(first, second)
    influence = max(blend - abs(first - second), 0.0) / blend
    return min(first, second) - influence * influence * blend * 0.25


def _smooth_max(first, second, blend):
    return -_smooth_min(-first, -second, blend)


def _is_identity_transform(transform):
    return (
        transform["location"] == (0.0, 0.0, 0.0)
        and transform["rotation"] == (0.0, 0.0, 0.0)
        and transform["scale"] == (1.0, 1.0, 1.0)
    )


def _cached_local_point_and_scale(point, node, by_id, cache):
    cached = cache.get(node["id"])
    if cached is not None:
        return cached
    parent_id = node.get("parent_id")
    if parent_id:
        local, distance_scale = _cached_local_point_and_scale(
            point, by_id[parent_id], by_id, cache
        )
    else:
        local, distance_scale = point, 1.0
    transform = node["transform"]
    if not _is_identity_transform(transform):
        local = _inverse_transform(local, transform)
        distance_scale *= min(transform["scale"])
    cache[node["id"]] = (local, distance_scale)
    return cache[node["id"]]


def _evaluate_prepared(program, point, by_id=None, transform_chains=None):
    by_id = by_id or {node["id"]: node for node in program["nodes"]}
    local_cache = {}
    distances = {}
    for node in program["nodes"]:
        if not node["enabled"]:
            continue
        local, distance_scale = _cached_local_point_and_scale(
            point, node, by_id, local_cache
        )
        distances[node["id"]] = _primitive_distance(local, node) * distance_scale

    targeted_values = {
        node["id"]: distances[node["id"]]
        for node in program["nodes"]
        if node["enabled"] and node["operation"] == "union"
    }
    for node in program["nodes"]:
        if not node["enabled"] or not node.get("target_ids"):
            continue
        distance = distances[node["id"]]
        for target_id in node["target_ids"]:
            if node["operation"] == "subtract":
                targeted_values[target_id] = _smooth_max(
                    targeted_values[target_id], -distance, node["blend"]
                )
            else:
                targeted_values[target_id] = _smooth_max(
                    targeted_values[target_id], distance, node["blend"]
                )

    result = None
    for node in program["nodes"]:
        if not node["enabled"] or node.get("target_ids"):
            continue
        distance = targeted_values.get(node["id"], distances[node["id"]])
        if result is None:
            result = distance
        elif node["operation"] == "union":
            result = _smooth_min(result, distance, node["blend"])
        elif node["operation"] == "subtract":
            result = _smooth_max(result, -distance, node["blend"])
        else:
            result = _smooth_max(result, distance, node["blend"])
    return result


class PreparedShapeProgram:
    """Validated shape program with cached transforms and workload metadata."""

    __slots__ = (
        "program",
        "by_id",
        "transform_chains",
        "enabled_nodes",
        "node_units",
        "primitive_units",
        "transform_units",
        "work_units_per_sample",
    )

    def __init__(self, program):
        self.program = normalize_shape_program(program)
        self.by_id = {node["id"]: node for node in self.program["nodes"]}
        self.transform_chains = _transform_chains(
            self.program["nodes"], self.by_id
        )
        self.enabled_nodes = tuple(
            node for node in self.program["nodes"] if node["enabled"]
        )
        self.node_units = len(self.enabled_nodes)
        self.primitive_units = sum(
            len(node["points"]) - 1 if node["type"] == "sweep" else 1
            for node in self.enabled_nodes
        )
        required_transform_nodes = set()
        for enabled in self.enabled_nodes:
            current = enabled
            while current is not None and current["id"] not in required_transform_nodes:
                required_transform_nodes.add(current["id"])
                current = self.by_id.get(current.get("parent_id"))
        self.transform_units = sum(
            not _is_identity_transform(self.by_id[node_id]["transform"])
            for node_id in required_transform_nodes
        )
        self.work_units_per_sample = self.primitive_units + self.transform_units

    def evaluate_unchecked(self, point):
        """Evaluate a known finite program-space point without revalidation."""

        return _evaluate_prepared(
            self.program,
            point,
            self.by_id,
            self.transform_chains,
        )

    def evaluate(self, point, *, field="point"):
        """Validate and evaluate one object-local program-space point."""

        return self.evaluate_unchecked(
            _vector(point, field, maximum_absolute=_MAX_COORDINATE)
        )


def prepare_shape_program(program):
    """Return a reusable evaluator for repeated sampling or mesh extraction."""

    return PreparedShapeProgram(program)


def evaluate_shape_program(program, point):
    """Return signed distance at one program-space point; negative is inside."""

    return prepare_shape_program(program).evaluate(point)


def sample_shape_program(program, points):
    """Return signed distances for a bounded list of program-space points."""

    if not isinstance(points, list) or len(points) > 512:
        raise ShapeProgramError("points must be a list containing at most 512 entries")
    prepared = prepare_shape_program(program)
    return [
        prepared.evaluate(
            point,
            field=f"points[{index}]",
        )
        for index, point in enumerate(points)
    ]


def _grid_spec(bounds, resolution):
    try:
        resolution = int(resolution)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ShapeProgramError("resolution must be an integer") from exc
    if not MIN_RESOLUTION <= resolution <= MAX_RESOLUTION:
        raise ShapeProgramError(
            f"resolution must be between {MIN_RESOLUTION} and {MAX_RESOLUTION}"
        )
    minimum = bounds["min"]
    maximum = bounds["max"]
    extent = tuple(maximum[index] - minimum[index] for index in range(3))
    longest = max(extent)
    dimensions = tuple(max(2, int(math.ceil(resolution * value / longest))) for value in extent)
    sample_dimensions = tuple(value + 1 for value in dimensions)
    sample_count = math.prod(sample_dimensions)
    if sample_count > MAX_GRID_SAMPLES:
        raise ShapeProgramError(
            f"Shape grid requires {sample_count} samples; limit is {MAX_GRID_SAMPLES}"
        )
    steps = tuple(extent[index] / dimensions[index] for index in range(3))
    return minimum, dimensions, sample_dimensions, steps, sample_count


_CUBE_CORNERS = (
    (0, 0, 0),
    (1, 0, 0),
    (1, 1, 0),
    (0, 1, 0),
    (0, 0, 1),
    (1, 0, 1),
    (1, 1, 1),
    (0, 1, 1),
)
_CUBE_TETRAHEDRA = (
    (0, 5, 1, 6),
    (0, 1, 2, 6),
    (0, 2, 3, 6),
    (0, 3, 7, 6),
    (0, 7, 4, 6),
    (0, 4, 5, 6),
)


def _cross(first, second):
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _mesh_neighbors(vertex_count, faces):
    neighbors = [set() for _index in range(vertex_count)]
    for face in faces:
        for index, first in enumerate(face):
            second = face[(index + 1) % len(face)]
            neighbors[first].add(second)
            neighbors[second].add(first)
    return [tuple(items) for items in neighbors]


def smooth_shape_mesh(vertices, faces, iterations):
    """Apply bounded topology-preserving smoothing to one shape mesh."""

    iterations = max(0, min(10, int(iterations)))
    if not iterations:
        return list(vertices)
    neighbors = _mesh_neighbors(len(vertices), faces)
    current = [tuple(vertex) for vertex in vertices]
    for _iteration in range(iterations):
        for factor in (0.45, -0.47):
            following = list(current)
            for index, adjacent in enumerate(neighbors):
                if not adjacent:
                    continue
                average = tuple(
                    sum(current[other][axis] for other in adjacent) / len(adjacent)
                    for axis in range(3)
                )
                following[index] = tuple(
                    current[index][axis] + (average[axis] - current[index][axis]) * factor
                    for axis in range(3)
                )
            current = following
    return current


def mesh_component_summary(faces):
    """Return connected face-component counts for a bounded compiled mesh."""

    if not faces:
        return {"component_count": 0, "component_face_counts": []}
    parent = list(range(len(faces)))
    rank = [0] * len(faces)
    vertex_owner = {}

    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(first, second):
        first_root, second_root = find(first), find(second)
        if first_root == second_root:
            return
        if rank[first_root] < rank[second_root]:
            first_root, second_root = second_root, first_root
        parent[second_root] = first_root
        if rank[first_root] == rank[second_root]:
            rank[first_root] += 1

    for face_index, face in enumerate(faces):
        for vertex_id in face:
            owner = vertex_owner.setdefault(vertex_id, face_index)
            union(face_index, owner)
    counts = {}
    for face_index in range(len(faces)):
        root = find(face_index)
        counts[root] = counts.get(root, 0) + 1
    face_counts = sorted(counts.values(), reverse=True)
    return {
        "component_count": len(face_counts),
        "component_face_counts": face_counts,
    }


def mesh_shape_program(program, *, resolution=48, iso_level=0.0, smooth_iterations=1):
    """Compile a validated shape program into a closed triangle mesh."""

    prepared = prepare_shape_program(program)
    normalized = prepared.program
    iso_level = _number(iso_level, "iso_level", minimum=-1000.0, maximum=1000.0)
    minimum, dimensions, sample_dimensions, steps, sample_count = _grid_spec(
        normalized["bounds"], resolution
    )
    node_evaluation_count = sample_count * prepared.node_units
    primitive_evaluation_count = sample_count * prepared.primitive_units
    transform_evaluation_count = sample_count * prepared.transform_units
    estimated_work_units = sample_count * prepared.work_units_per_sample
    if estimated_work_units > MAX_SDF_EVALUATIONS:
        raise ShapeProgramError(
            "Shape compile requires approximately "
            f"{estimated_work_units} evaluation work units; "
            f"limit is {MAX_SDF_EVALUATIONS}"
        )
    x_samples, y_samples, z_samples = sample_dimensions

    def sample_index(x_index, y_index, z_index):
        return (z_index * y_samples + y_index) * x_samples + x_index

    values = [0.0] * sample_count
    boundary_inside_count = 0
    for z_index in range(z_samples):
        z = minimum[2] + z_index * steps[2]
        for y_index in range(y_samples):
            y = minimum[1] + y_index * steps[1]
            for x_index in range(x_samples):
                point = (minimum[0] + x_index * steps[0], y, z)
                value = prepared.evaluate_unchecked(point)
                values[sample_index(x_index, y_index, z_index)] = value
                if (
                    x_index in (0, x_samples - 1)
                    or y_index in (0, y_samples - 1)
                    or z_index in (0, z_samples - 1)
                ) and value <= iso_level:
                    boundary_inside_count += 1
    if boundary_inside_count:
        raise ShapeProgramError(
            "Shape reaches or crosses the compile bounds at "
            f"{boundary_inside_count} boundary samples; expand bounds"
        )

    vertices = []
    faces = []
    edge_vertices = {}
    lattice_vertices = {}

    def grid_point(x_index, y_index, z_index):
        return (
            minimum[0] + x_index * steps[0],
            minimum[1] + y_index * steps[1],
            minimum[2] + z_index * steps[2],
        )

    def interpolated_vertex(first_id, second_id, first_point, second_point, first_value, second_value):
        key = (min(first_id, second_id), max(first_id, second_id))
        cached = edge_vertices.get(key)
        if cached is not None:
            return cached
        exact_id = None
        exact_point = None
        if abs(first_value - iso_level) <= 1.0e-12:
            exact_id, exact_point = first_id, first_point
        elif abs(second_value - iso_level) <= 1.0e-12:
            exact_id, exact_point = second_id, second_point
        if exact_id is not None:
            cached = lattice_vertices.get(exact_id)
            if cached is None:
                cached = len(vertices)
                vertices.append(exact_point)
                lattice_vertices[exact_id] = cached
            edge_vertices[key] = cached
            return cached
        denominator = second_value - first_value
        factor = 0.5 if abs(denominator) <= _EPSILON else (iso_level - first_value) / denominator
        factor = max(0.0, min(1.0, factor))
        vertex = tuple(
            first_point[index] + (second_point[index] - first_point[index]) * factor
            for index in range(3)
        )
        result = len(vertices)
        if result >= MAX_OUTPUT_VERTICES:
            raise ShapeProgramError(
                f"Compiled mesh exceeds the {MAX_OUTPUT_VERTICES} vertex limit"
            )
        vertices.append(vertex)
        edge_vertices[key] = result
        return result

    def add_face(indices, outward):
        if len(set(indices)) != 3:
            return
        first, second, third = (vertices[index] for index in indices)
        normal = _cross(_subtract(second, first), _subtract(third, first))
        if _dot(normal, normal) <= 1.0e-24:
            return
        face = tuple(indices)
        if _dot(normal, outward) < 0.0:
            face = (face[0], face[2], face[1])
        if len(faces) >= MAX_OUTPUT_FACES:
            raise ShapeProgramError(
                f"Compiled mesh exceeds the {MAX_OUTPUT_FACES} face limit"
            )
        faces.append(face)

    for z_index in range(dimensions[2]):
        for y_index in range(dimensions[1]):
            for x_index in range(dimensions[0]):
                corner_coords = [
                    (x_index + offset[0], y_index + offset[1], z_index + offset[2])
                    for offset in _CUBE_CORNERS
                ]
                corner_ids = [sample_index(*coord) for coord in corner_coords]
                corner_points = [grid_point(*coord) for coord in corner_coords]
                corner_values = [values[item] for item in corner_ids]
                if all(value > iso_level for value in corner_values) or all(
                    value <= iso_level for value in corner_values
                ):
                    continue
                for tetra in _CUBE_TETRAHEDRA:
                    inside = [item for item in tetra if corner_values[item] <= iso_level]
                    outside = [item for item in tetra if corner_values[item] > iso_level]
                    if not inside or not outside:
                        continue
                    inside_center = tuple(
                        sum(corner_points[item][axis] for item in inside) / len(inside)
                        for axis in range(3)
                    )
                    outside_center = tuple(
                        sum(corner_points[item][axis] for item in outside) / len(outside)
                        for axis in range(3)
                    )
                    outward = _subtract(outside_center, inside_center)

                    def crossing(first, second):
                        return interpolated_vertex(
                            corner_ids[first],
                            corner_ids[second],
                            corner_points[first],
                            corner_points[second],
                            corner_values[first],
                            corner_values[second],
                        )

                    if len(inside) == 1:
                        add_face([crossing(inside[0], item) for item in outside], outward)
                    elif len(outside) == 1:
                        add_face([crossing(outside[0], item) for item in inside], outward)
                    else:
                        first_inside, second_inside = inside
                        first_outside, second_outside = outside
                        a = crossing(first_inside, first_outside)
                        b = crossing(first_inside, second_outside)
                        c = crossing(second_inside, first_outside)
                        d = crossing(second_inside, second_outside)
                        add_face((a, b, d), outward)
                        add_face((a, d, c), outward)

    if not vertices or not faces:
        raise ShapeProgramError(
            "Shape program produced no surface inside the requested bounds"
        )
    vertices = smooth_shape_mesh(vertices, faces, smooth_iterations)
    component_summary = mesh_component_summary(faces)
    return {
        "vertices": vertices,
        "faces": faces,
        "stats": {
            "meshing_mode": "uniform_tetrahedra",
            "resolution": int(resolution),
            "grid_dimensions": dimensions,
            "sample_count": sample_count,
            "node_evaluation_count": node_evaluation_count,
            "primitive_evaluation_count": primitive_evaluation_count,
            "transform_evaluation_count": transform_evaluation_count,
            "estimated_work_units": estimated_work_units,
            "vertex_count": len(vertices),
            "face_count": len(faces),
            **component_summary,
            "disconnected_component_count": max(
                0, component_summary["component_count"] - 1
            ),
            "smooth_iterations": max(0, min(10, int(smooth_iterations))),
            "iso_level": iso_level,
            "digest": shape_program_digest(normalized),
        },
        "program": normalized,
    }
