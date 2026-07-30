"""Pure reusable geometry generation for soft reference-derived forms."""

from __future__ import annotations

import math


def _vector3(value, default):
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return tuple(float(item) for item in default)
    try:
        return tuple(float(value[index]) for index in range(3))
    except (TypeError, ValueError):
        return tuple(float(item) for item in default)


def _length(vector):
    return math.sqrt(sum(component * component for component in vector))


def _normalized(vector, default):
    length = _length(vector)
    if length <= 1e-9:
        return tuple(float(item) for item in default)
    return tuple(component / length for component in vector)


def _smoothstep(value):
    value = max(0.0, min(1.0, float(value)))
    return value * value * (3.0 - 2.0 * value)


def _control_displacement(unit_direction, controls, average_radius):
    displacement = [0.0, 0.0, 0.0]
    for raw in list(controls or [])[:32]:
        if not isinstance(raw, dict):
            continue
        direction = _normalized(
            _vector3(raw.get("direction"), (0.0, 0.0, 1.0)),
            (0.0, 0.0, 1.0),
        )
        try:
            offset = max(-2.0, min(2.0, float(raw.get("offset") or 0.0)))
            falloff = max(
                0.01, min(2.0, float(raw.get("falloff") or 0.75))
            )
        except (TypeError, ValueError):
            continue
        distance = _length(
            tuple(
                unit_direction[index] - direction[index]
                for index in range(3)
            )
        )
        influence = _smoothstep(1.0 - distance / falloff)
        amount = offset * average_radius * influence
        for index in range(3):
            displacement[index] += direction[index] * amount
    return tuple(displacement)


def deformed_ellipsoid_mesh(
    *,
    center=(0.0, 0.0, 0.0),
    radii=(1.0, 1.0, 1.0),
    basis=None,
    controls=None,
    segments=32,
    rings=16,
):
    """Return vertices/faces for a smooth camera-basis ellipsoid."""

    center = _vector3(center, (0.0, 0.0, 0.0))
    radii = tuple(
        max(1e-5, abs(value))
        for value in _vector3(radii, (1.0, 1.0, 1.0))
    )
    if not isinstance(basis, (list, tuple)) or len(basis) < 3:
        basis = (
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        )
    basis = tuple(
        _normalized(_vector3(axis, default), default)
        for axis, default in zip(
            basis,
            (
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
            ),
        )
    )
    segments = max(8, min(128, int(segments)))
    rings = max(4, min(64, int(rings)))
    average_radius = sum(radii) / 3.0

    def point(unit):
        local = [
            unit[index] * radii[index] for index in range(3)
        ]
        deformation = _control_displacement(
            unit, controls, average_radius
        )
        local = [
            local[index] + deformation[index] for index in range(3)
        ]
        return tuple(
            center[world_axis]
            + sum(
                basis[local_axis][world_axis] * local[local_axis]
                for local_axis in range(3)
            )
            for world_axis in range(3)
        )

    vertices = [point((0.0, 0.0, 1.0))]
    for ring in range(1, rings):
        theta = math.pi * ring / rings
        sin_theta = math.sin(theta)
        cos_theta = math.cos(theta)
        for segment in range(segments):
            phi = math.tau * segment / segments
            vertices.append(
                point(
                    (
                        sin_theta * math.cos(phi),
                        sin_theta * math.sin(phi),
                        cos_theta,
                    )
                )
            )
    bottom_index = len(vertices)
    vertices.append(point((0.0, 0.0, -1.0)))

    faces = []
    first_ring = 1
    for segment in range(segments):
        next_segment = (segment + 1) % segments
        faces.append((0, first_ring + segment, first_ring + next_segment))
    for ring in range(rings - 2):
        current = 1 + ring * segments
        following = current + segments
        for segment in range(segments):
            next_segment = (segment + 1) % segments
            faces.append(
                (
                    current + segment,
                    following + segment,
                    following + next_segment,
                    current + next_segment,
                )
            )
    last_ring = 1 + (rings - 2) * segments
    for segment in range(segments):
        next_segment = (segment + 1) % segments
        faces.append(
            (
                last_ring + segment,
                bottom_index,
                last_ring + next_segment,
            )
        )
    return vertices, faces
