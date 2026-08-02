"""Pure calibration and ray-intersection helpers for multi-view references."""

from __future__ import annotations

import math


_EPSILON = 1.0e-9
_AXIS_BASES = {
    "FRONT": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "BACK": ((-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    "LEFT": ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "RIGHT": ((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "TOP": ((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
    "BOTTOM": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)),
}


class MultiViewCalibrationError(ValueError):
    """Raised when a view calibration cannot reconstruct stable 3D points."""


def _vector(value, field):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise MultiViewCalibrationError(f"{field} must contain three numbers")
    try:
        result = tuple(float(component) for component in value)
    except (TypeError, ValueError) as exc:
        raise MultiViewCalibrationError(f"{field} must contain three numbers") from exc
    if not all(math.isfinite(component) for component in result):
        raise MultiViewCalibrationError(f"{field} must contain finite numbers")
    return result


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


def _normalized(vector, field):
    vector = _vector(vector, field)
    magnitude = _length(vector)
    if magnitude <= _EPSILON:
        raise MultiViewCalibrationError(f"{field} must not be zero length")
    return _scale(vector, 1.0 / magnitude)


def view_basis(axis, *, view_direction=None, up_direction=None):
    """Return image-right, camera-forward, and image-up basis vectors."""
    axis = str(axis or "").strip().upper()
    if axis in _AXIS_BASES:
        return _AXIS_BASES[axis]
    if axis != "CUSTOM":
        raise MultiViewCalibrationError(
            "axis must be FRONT, BACK, LEFT, RIGHT, TOP, BOTTOM, or CUSTOM"
        )
    forward = _normalized(view_direction, "view_direction")
    requested_up = _normalized(up_direction, "up_direction")
    right = _cross(forward, requested_up)
    if _length(right) <= 1.0e-6:
        raise MultiViewCalibrationError(
            "view_direction and up_direction must not be parallel"
        )
    right = _scale(right, 1.0 / _length(right))
    up = _cross(right, forward)
    up = _scale(up, 1.0 / _length(up))
    return right, forward, up


def image_point_to_ray(
    point,
    *,
    image_aspect,
    plane_height,
    center=(0.0, 0.0, 0.0),
    basis,
):
    """Map a top-left normalized image point to an orthographic world ray."""
    if not isinstance(point, (list, tuple)) or len(point) < 2:
        raise MultiViewCalibrationError("point must contain normalized [x, y]")
    try:
        u, v = float(point[0]), float(point[1])
        aspect = float(image_aspect)
        height = float(plane_height)
    except (TypeError, ValueError) as exc:
        raise MultiViewCalibrationError(
            "point, image_aspect, and plane_height must be numeric"
        ) from exc
    if not all(math.isfinite(value) for value in (u, v, aspect, height)):
        raise MultiViewCalibrationError("ray calibration values must be finite")
    if aspect <= 0.0 or height <= 0.0:
        raise MultiViewCalibrationError(
            "image_aspect and plane_height must be greater than zero"
        )
    right, forward, up = basis
    center = _vector(center, "center")
    origin = _add(
        center,
        _add(
            _scale(right, (u - 0.5) * height * aspect),
            _scale(up, (0.5 - v) * height),
        ),
    )
    return {
        "origin": origin,
        "direction": _normalized(forward, "basis forward"),
    }


def triangulate_rays(rays, *, minimum_angle_degrees=1.0):
    """Return the least-squares point nearest two or more orthographic rays."""
    prepared = []
    for index, ray in enumerate(rays or []):
        if not isinstance(ray, dict):
            continue
        prepared.append(
            {
                "origin": _vector(ray.get("origin"), f"rays[{index}].origin"),
                "direction": _normalized(
                    ray.get("direction"),
                    f"rays[{index}].direction",
                ),
                "view": str(ray.get("view") or ""),
            }
        )
    if len(prepared) < 2:
        raise MultiViewCalibrationError(
            "at least two calibrated rays are required"
        )

    largest_angle = 0.0
    for index, ray in enumerate(prepared):
        for other in prepared[index + 1 :]:
            cosine = max(
                -1.0,
                min(1.0, abs(_dot(ray["direction"], other["direction"]))),
            )
            largest_angle = max(
                largest_angle,
                math.degrees(math.acos(cosine)),
            )
    minimum_angle = max(0.0, float(minimum_angle_degrees))
    if largest_angle < minimum_angle:
        raise MultiViewCalibrationError(
            f"view rays are too parallel for stable reconstruction "
            f"({largest_angle:.3f} degrees)"
        )

    matrix = [[0.0 for _column in range(3)] for _row in range(3)]
    vector = [0.0, 0.0, 0.0]
    for ray in prepared:
        direction = ray["direction"]
        projector = [
            [
                (1.0 if row == column else 0.0)
                - direction[row] * direction[column]
                for column in range(3)
            ]
            for row in range(3)
        ]
        for row in range(3):
            vector[row] += sum(
                projector[row][column] * ray["origin"][column]
                for column in range(3)
            )
            for column in range(3):
                matrix[row][column] += projector[row][column]
    point, pivot_ratio = _solve_3x3(matrix, vector)
    residuals = []
    for ray in prepared:
        offset = _subtract(point, ray["origin"])
        along = _scale(ray["direction"], _dot(offset, ray["direction"]))
        residuals.append(_length(_subtract(offset, along)))
    rms = math.sqrt(sum(value * value for value in residuals) / len(residuals))
    return {
        "point": point,
        "rms_residual": rms,
        "max_residual": max(residuals),
        "residuals": residuals,
        "view_count": len(prepared),
        "views": [ray["view"] for ray in prepared],
        "largest_ray_angle_degrees": largest_angle,
        "pivot_ratio": pivot_ratio,
    }


def _solve_3x3(matrix, vector):
    augmented = [
        [float(matrix[row][column]) for column in range(3)]
        + [float(vector[row])]
        for row in range(3)
    ]
    pivots = []
    for column in range(3):
        pivot_row = max(
            range(column, 3),
            key=lambda row: abs(augmented[row][column]),
        )
        pivot = abs(augmented[pivot_row][column])
        if pivot <= _EPSILON:
            raise MultiViewCalibrationError(
                "view calibration is singular; add a non-parallel view"
            )
        augmented[column], augmented[pivot_row] = (
            augmented[pivot_row],
            augmented[column],
        )
        divisor = augmented[column][column]
        pivots.append(abs(divisor))
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(3):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                augmented[row][index] - factor * augmented[column][index]
                for index in range(4)
            ]
    return (
        tuple(augmented[row][3] for row in range(3)),
        min(pivots) / max(pivots),
    )
