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


def _normalized_bounds(points, source, *, reliable):
    prepared = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            x, y = float(point[0]), float(point[1])
        except (TypeError, ValueError):
            continue
        if math.isfinite(x) and math.isfinite(y):
            prepared.append((max(0.0, min(1.0, x)), max(0.0, min(1.0, y))))
    if not prepared:
        return {}
    minimum_x = min(point[0] for point in prepared)
    maximum_x = max(point[0] for point in prepared)
    minimum_y = min(point[1] for point in prepared)
    maximum_y = max(point[1] for point in prepared)
    width = maximum_x - minimum_x
    height = maximum_y - minimum_y
    if width <= _EPSILON or height <= _EPSILON:
        return {}
    return {
        "bounds": [minimum_x, minimum_y, width, height],
        "source": source,
        "reliable": bool(reliable),
        "point_count": len(prepared),
    }


def subject_bounds_from_annotations(normalized, explicit_bounds=None):
    """Estimate normalized subject bounds, preferring an explicit box or outline."""
    if explicit_bounds is not None:
        if not isinstance(explicit_bounds, (list, tuple)) or len(explicit_bounds) != 4:
            raise MultiViewCalibrationError(
                "subject_bounds must be normalized [x, y, width, height]"
            )
        try:
            x, y, width, height = (float(value) for value in explicit_bounds)
        except (TypeError, ValueError) as exc:
            raise MultiViewCalibrationError("subject_bounds must contain four numbers") from exc
        if not all(math.isfinite(value) for value in (x, y, width, height)):
            raise MultiViewCalibrationError("subject_bounds must contain finite numbers")
        if width <= 0.0 or height <= 0.0 or x < 0.0 or y < 0.0 or x + width > 1.0 or y + height > 1.0:
            raise MultiViewCalibrationError("subject_bounds must stay inside normalized image coordinates")
        return {
            "bounds": [x, y, width, height],
            "source": "explicit",
            "reliable": True,
            "point_count": 4,
        }

    normalized = normalized if isinstance(normalized, dict) else {}
    curves = [curve for curve in normalized.get("curves") or [] if isinstance(curve, dict)]
    named = [
        curve
        for curve in curves
        if any(token in str(curve.get("name") or "").casefold() for token in ("silhouette", "outline", "contour"))
    ]
    candidates = named or [curve for curve in curves if bool(curve.get("cyclic"))]
    outline = _normalized_bounds(
        [point for curve in candidates for point in (curve.get("points") or [])],
        "named_outline" if named else "cyclic_outlines",
        reliable=True,
    )
    if outline:
        return outline

    mass_points = []
    for mass in normalized.get("masses") or []:
        if not isinstance(mass, dict):
            continue
        center = mass.get("center") or []
        radius = mass.get("radius") or []
        if len(center) < 2 or len(radius) < 2:
            continue
        mass_points.extend(
            [
                (float(center[0]) - float(radius[0]), float(center[1]) - float(radius[1])),
                (float(center[0]) + float(radius[0]), float(center[1]) + float(radius[1])),
            ]
        )
    masses = _normalized_bounds(mass_points, "mass_bounds", reliable=False)
    if masses:
        return masses

    landmarks = [
        landmark.get("point")
        for landmark in normalized.get("landmarks") or []
        if isinstance(landmark, dict) and landmark.get("point") is not None
    ]
    return _normalized_bounds(landmarks, "landmark_extent", reliable=False)


def subject_scale_calibration(
    normalized,
    *,
    plane_height,
    subject_height=0.0,
    subject_bounds=None,
):
    """Resolve frame-scale or silhouette-derived subject-scale calibration."""
    try:
        frame_height = float(plane_height)
        requested_height = float(subject_height or 0.0)
    except (TypeError, ValueError) as exc:
        raise MultiViewCalibrationError("plane_height and subject_height must be numeric") from exc
    if not math.isfinite(frame_height) or frame_height <= 0.0:
        raise MultiViewCalibrationError("plane_height must be greater than zero")
    if not math.isfinite(requested_height) or requested_height < 0.0:
        raise MultiViewCalibrationError("subject_height must be zero or greater")

    detected = subject_bounds_from_annotations(normalized, subject_bounds)
    fraction = float((detected.get("bounds") or [0.0, 0.0, 0.0, 0.0])[3])
    applied = bool(requested_height > 0.0 and fraction > _EPSILON)
    resolved_height = requested_height / fraction if applied else frame_height
    estimated_subject_height = resolved_height * fraction if fraction > 0.0 else 0.0
    warnings = []
    if requested_height > 0.0 and not detected:
        warnings.append(
            "subject_height was requested but no usable silhouette, mass, landmark extent, or subject_bounds was available"
        )
    elif applied and not detected.get("reliable"):
        warnings.append(
            "subject_height used estimated bounds; provide subject_bounds or a cyclic silhouette for reliable cross-view scale"
        )
    elif not applied and fraction > 0.0 and abs(1.0 - fraction) > 0.01:
        warnings.append(
            "plane_height maps the image frame; the detected subject occupies %.2f%% of frame height and may scale differently across views"
            % (fraction * 100.0)
        )
    return {
        "mode": "subject_height" if applied else "frame_height",
        "applied": applied,
        "requested_subject_height": requested_height,
        "input_plane_height": frame_height,
        "resolved_plane_height": resolved_height,
        "detected_subject_bounds": list(detected.get("bounds") or []),
        "bounds_source": str(detected.get("source") or ""),
        "bounds_reliable": bool(detected.get("reliable")),
        "subject_height_fraction": fraction,
        "estimated_world_subject_height": estimated_subject_height,
        "warnings": warnings,
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
