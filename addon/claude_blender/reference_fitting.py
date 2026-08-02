"""Pure bounded multi-view silhouette, landmark, and depth surface fitting."""

from __future__ import annotations

import math

from . import depth_fields, sculpt_fields, visual_hull


MAX_FIT_VERTICES = 100_000
MAX_FIT_FACES = 250_000
MAX_FIT_ITERATIONS = 12
MAX_STEP_CANDIDATES = 5
MAX_SILHOUETTE_EDGES_PER_VIEW = 1024
MAX_OUTLINE_SAMPLES_PER_VIEW = 512
MAX_DEPTH_VERTICES_PER_LAYER = 12_000
MAX_FIT_DEPTH_SAMPLE_EVALUATIONS = 100_000_000
MAX_LANDMARKS = 128
_EPSILON = 1.0e-9
MINIMUM_FACE_AREA_RATIO = 0.02


class ReferenceFitError(ValueError):
    """Raised when a bounded reference fit cannot be evaluated."""


def _vector(value, length, field):
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise ReferenceFitError(f"{field} must contain {length} numbers")
    try:
        result = tuple(float(value[index]) for index in range(length))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReferenceFitError(f"{field} must contain {length} numbers") from exc
    if not all(math.isfinite(component) for component in result):
        raise ReferenceFitError(f"{field} must contain finite numbers")
    return result


def _add(left, right):
    return tuple(left[index] + right[index] for index in range(3))


def _subtract(left, right):
    return tuple(left[index] - right[index] for index in range(3))


def _scale(vector, factor):
    return tuple(component * factor for component in vector)


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


def _clamp_length(vector, maximum):
    magnitude = _length(vector)
    if maximum <= 0.0 or magnitude <= maximum or magnitude <= _EPSILON:
        return vector
    return _scale(vector, maximum / magnitude)


def _prepare_mesh(points, faces):
    prepared_points = [
        _vector(point, 3, f"points[{index}]")
        for index, point in enumerate(points or [])
    ]
    if len(prepared_points) < 4:
        raise ReferenceFitError("A fitted surface needs at least four vertices")
    if len(prepared_points) > MAX_FIT_VERTICES:
        raise ReferenceFitError(
            f"Surface contains {len(prepared_points)} vertices; limit is {MAX_FIT_VERTICES}"
        )
    prepared_faces = []
    for face_index, face in enumerate(faces or []):
        if not isinstance(face, (list, tuple)) or len(face) < 3:
            raise ReferenceFitError(f"faces[{face_index}] must contain at least three indices")
        try:
            indices = tuple(int(value) for value in face)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ReferenceFitError(f"faces[{face_index}] must contain integer indices") from exc
        if any(index < 0 or index >= len(prepared_points) for index in indices):
            raise ReferenceFitError(f"faces[{face_index}] contains an out-of-range index")
        if len(set(indices)) < 3:
            raise ReferenceFitError(f"faces[{face_index}] is degenerate")
        prepared_faces.append(indices)
    if not prepared_faces:
        raise ReferenceFitError("A fitted surface needs at least one face")
    if len(prepared_faces) > MAX_FIT_FACES:
        raise ReferenceFitError(
            f"Surface contains {len(prepared_faces)} faces; limit is {MAX_FIT_FACES}"
        )
    return prepared_points, prepared_faces


def _topology(vertex_count, faces):
    neighbors = [set() for _index in range(vertex_count)]
    edge_faces = {}
    for face_index, face in enumerate(faces):
        for index, first in enumerate(face):
            second = face[(index + 1) % len(face)]
            neighbors[first].add(second)
            neighbors[second].add(first)
            edge = (min(first, second), max(first, second))
            edge_faces.setdefault(edge, []).append(face_index)
    return [tuple(sorted(items)) for items in neighbors], edge_faces


def _face_normal(points, face):
    origin = points[face[0]]
    for index in range(1, len(face) - 1):
        first = _subtract(points[face[index]], origin)
        second = _subtract(points[face[index + 1]], origin)
        normal = _cross(first, second)
        magnitude = _length(normal)
        if magnitude > _EPSILON:
            return _scale(normal, 1.0 / magnitude)
    return (0.0, 0.0, 0.0)


def _face_area(points, face):
    origin = points[face[0]]
    area = 0.0
    for index in range(1, len(face) - 1):
        area += _length(
            _cross(
                _subtract(points[face[index]], origin),
                _subtract(points[face[index + 1]], origin),
            )
        ) * 0.5
    return area


def _measure_surface_integrity_prepared(points, faces, reference):
    degenerate = []
    inverted = []
    minimum_ratio = MINIMUM_FACE_AREA_RATIO
    for index, face in enumerate(faces):
        reference_area = _face_area(reference, face)
        candidate_area = _face_area(points, face)
        if reference_area <= _EPSILON:
            degenerate.append(index)
            continue
        if candidate_area <= max(_EPSILON, reference_area * minimum_ratio):
            degenerate.append(index)
            continue
        reference_normal = _face_normal(reference, face)
        candidate_normal = _face_normal(points, face)
        if _dot(reference_normal, candidate_normal) <= 0.0:
            inverted.append(index)
    return {
        "ok": not degenerate and not inverted,
        "degenerate_face_count": len(degenerate),
        "inverted_face_count": len(inverted),
        "degenerate_faces": degenerate[:32],
        "inverted_faces": inverted[:32],
        "minimum_face_area_ratio": minimum_ratio,
    }


def measure_surface_integrity(points, faces, *, reference_points=None):
    """Report geometric face collapse and orientation changes."""

    points, faces = _prepare_mesh(points, faces)
    reference = (
        [
            _vector(point, 3, f"reference_points[{index}]")
            for index, point in enumerate(reference_points)
        ]
        if reference_points is not None
        else points
    )
    if len(reference) != len(points):
        raise ReferenceFitError("reference_points must match the fitted vertex count")
    return _measure_surface_integrity_prepared(points, faces, reference)


def _sample_evenly(items, maximum):
    if len(items) <= maximum:
        return list(items)
    return [items[index * len(items) // maximum] for index in range(maximum)]


def _silhouette_edges(points, faces, edge_faces, view):
    signs = [_dot(_face_normal(points, face), view["forward"]) for face in faces]
    edges = []
    for edge, adjacent_faces in edge_faces.items():
        if len(adjacent_faces) == 1:
            edges.append(edge)
            continue
        facing = [signs[index] < -1.0e-7 for index in adjacent_faces]
        if any(facing) and not all(facing):
            edges.append(edge)
    edges.sort()
    return _sample_evenly(edges, MAX_SILHOUETTE_EDGES_PER_VIEW)


def _nearest_segment_point_2d(point, start, end):
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    denominator = dx * dx + dy * dy
    if denominator <= _EPSILON:
        target = start
    else:
        factor = max(
            0.0,
            min(
                1.0,
                ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
                / denominator,
            ),
        )
        target = (start[0] + dx * factor, start[1] + dy * factor)
    return target, math.hypot(point[0] - target[0], point[1] - target[1])


def _nearest_polyline_point(point, polygon):
    best = None
    for index, end in enumerate(polygon):
        target, distance = _nearest_segment_point_2d(point, polygon[index - 1], end)
        candidate = (distance, target)
        if best is None or candidate < best:
            best = candidate
    return best[1], best[0]


def _outline_samples(polygon):
    samples = []
    for index, end in enumerate(polygon):
        start = polygon[index - 1]
        samples.append(end)
        samples.append(((start[0] + end[0]) * 0.5, (start[1] + end[1]) * 0.5))
    return _sample_evenly(samples, MAX_OUTLINE_SAMPLES_PER_VIEW)


def _nearest_model_edge_distance(point, projected, edges):
    best = float("inf")
    for first, second in edges:
        _target, distance = _nearest_segment_point_2d(
            point,
            projected[first],
            projected[second],
        )
        best = min(best, distance)
    return best


def _silhouette_measurement(points, faces, edge_faces, view):
    edges = _silhouette_edges(points, faces, edge_faces, view)
    if not edges:
        raise ReferenceFitError(f"View {view['name']} produced no measurable silhouette edges")
    projected = [visual_hull.project_point(point, view) for point in points]
    vertex_indices = sorted({index for edge in edges for index in edge})
    model_distances = []
    corrections = []
    for vertex_index in vertex_indices:
        target, distance = _nearest_polyline_point(
            projected[vertex_index],
            view["outline"],
        )
        model_distances.append(distance)
        corrections.append((vertex_index, target, distance))
    target_distances = [
        _nearest_model_edge_distance(point, projected, edges)
        for point in _outline_samples(view["outline"])
    ]
    distances = model_distances + target_distances
    return {
        "error": sum(distances) / max(1, len(distances)),
        "maximum_error": max(distances, default=0.0),
        "edge_count": len(edges),
        "vertex_count": len(vertex_indices),
        "projected": projected,
        "corrections": corrections,
    }


def _depth_measurements(points, normals, view):
    layers = view.get("depth_layers") or ()
    if not layers:
        return [], []
    stride = max(1, int(math.ceil(len(points) / MAX_DEPTH_VERTICES_PER_LAYER)))
    measurements = []
    summaries = []
    for layer in layers:
        layer_measurements = []
        for vertex_index in range(0, len(points), stride):
            facing = _dot(normals[vertex_index], view["forward"])
            if layer["mode"] == "front" and facing > -1.0e-5:
                continue
            if layer["mode"] == "back" and facing < 1.0e-5:
                continue
            projected = visual_hull.project_point(points[vertex_index], view)
            if not 0.0 <= projected[0] <= 1.0 or not 0.0 <= projected[1] <= 1.0:
                continue
            target = depth_fields.sample_depth(layer, projected)
            if target is None:
                continue
            current = _dot(_subtract(points[vertex_index], view["center"]), view["forward"])
            item = {
                "vertex_index": vertex_index,
                "target": target,
                "current": current,
                "residual": current - target,
                "view": view["name"],
                "layer": layer["name"],
                "mode": layer["mode"],
            }
            measurements.append(item)
            layer_measurements.append(item)
        errors = [abs(item["residual"]) / view["plane_height"] for item in layer_measurements]
        summaries.append(
            {
                "name": layer["name"],
                "mode": layer["mode"],
                "sample_count": len(layer_measurements),
                "mean_error": sum(errors) / max(1, len(errors)),
                "maximum_error": max(errors, default=0.0),
            }
        )
    return measurements, summaries


def _prepare_landmarks(raw_constraints, points):
    constraints = []
    for index, raw in enumerate(list(raw_constraints or [])[:MAX_LANDMARKS]):
        if not isinstance(raw, dict):
            raise ReferenceFitError(f"landmarks[{index}] must be an object")
        target = _vector(raw.get("target"), 3, f"landmarks[{index}].target")
        vertex_index = raw.get("vertex_index")
        if vertex_index is None:
            vertex_index = min(
                range(len(points)),
                key=lambda point_index: _length(_subtract(points[point_index], target)),
            )
        else:
            try:
                vertex_index = int(vertex_index)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ReferenceFitError(
                    f"landmarks[{index}].vertex_index must be an integer"
                ) from exc
            if not 0 <= vertex_index < len(points):
                raise ReferenceFitError(
                    f"landmarks[{index}].vertex_index is out of range"
                )
        try:
            weight = float(raw.get("weight", 1.0))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ReferenceFitError(f"landmarks[{index}].weight must be numeric") from exc
        if not math.isfinite(weight) or weight <= 0.0:
            raise ReferenceFitError(f"landmarks[{index}].weight must be greater than zero")
        constraints.append(
            {
                "name": str(raw.get("name") or f"landmark_{index + 1}"),
                "target": target,
                "vertex_index": vertex_index,
                "weight": min(100.0, weight),
            }
        )
    return constraints


def _landmark_measurement(points, constraints, scale):
    items = []
    for constraint in constraints:
        current = points[constraint["vertex_index"]]
        distance = _length(_subtract(current, constraint["target"]))
        items.append(
            {
                "name": constraint["name"],
                "vertex_index": constraint["vertex_index"],
                "distance": distance,
                "normalized_error": distance / scale,
            }
        )
    return items


def _surface_scale(points):
    minimum = [min(point[axis] for point in points) for axis in range(3)]
    maximum = [max(point[axis] for point in points) for axis in range(3)]
    return max(_EPSILON, _length(_subtract(maximum, minimum)))


def _evaluate_surface_fit_prepared(
    points,
    faces,
    views,
    landmarks,
    edge_faces,
    *,
    silhouette_weight=1.0,
    depth_weight=0.5,
    landmark_weight=0.5,
    worst_view_weight=0.25,
):
    normals = sculpt_fields.vertex_normals(points, faces)
    scale = _surface_scale(points)
    per_view = []
    silhouette_errors = []
    depth_errors = []
    for view in views:
        silhouette = _silhouette_measurement(points, faces, edge_faces, view)
        _depth_items, depth_layers = _depth_measurements(points, normals, view)
        layer_errors = [item["mean_error"] for item in depth_layers if item["sample_count"]]
        depth_error = sum(layer_errors) / len(layer_errors) if layer_errors else 0.0
        combined = float(silhouette_weight) * silhouette["error"]
        if layer_errors:
            combined += float(depth_weight) * depth_error
            depth_errors.append(depth_error)
        silhouette_errors.append(silhouette["error"])
        per_view.append(
            {
                "name": view["name"],
                "silhouette_error": silhouette["error"],
                "silhouette_maximum_error": silhouette["maximum_error"],
                "silhouette_edge_count": silhouette["edge_count"],
                "depth_error": depth_error,
                "depth_layers": depth_layers,
                "combined_error": combined,
            }
        )
    landmark_items = _landmark_measurement(points, landmarks, scale)
    landmark_error = (
        sum(item["normalized_error"] for item in landmark_items) / len(landmark_items)
        if landmark_items
        else 0.0
    )
    silhouette_error = sum(silhouette_errors) / len(silhouette_errors)
    depth_error = sum(depth_errors) / len(depth_errors) if depth_errors else 0.0
    objective = (
        float(silhouette_weight) * silhouette_error
        + float(depth_weight) * depth_error
        + float(landmark_weight) * landmark_error
        + float(worst_view_weight) * max(item["combined_error"] for item in per_view)
    )
    values = (objective, silhouette_error, depth_error, landmark_error)
    if not all(math.isfinite(value) for value in values):
        raise ReferenceFitError("Reference fit produced a non-finite objective")
    return {
        "objective": objective,
        "quality_score": 1.0 / (1.0 + objective),
        "silhouette_error": silhouette_error,
        "depth_error": depth_error,
        "landmark_error": landmark_error,
        "per_view": per_view,
        "landmarks": landmark_items,
    }


def evaluate_surface_fit(
    points,
    faces,
    views,
    *,
    landmarks=None,
    silhouette_weight=1.0,
    depth_weight=0.5,
    landmark_weight=0.5,
    worst_view_weight=0.25,
    _topology_cache=None,
):
    """Measure a mesh against all calibrated reference constraints."""

    points, faces = _prepare_mesh(points, faces)
    prepared_views = visual_hull.prepare_calibrated_views(views, minimum_count=2)
    _neighbors, edge_faces = _topology_cache or _topology(len(points), faces)
    prepared_landmarks = _prepare_landmarks(landmarks, points)
    return _evaluate_surface_fit_prepared(
        points,
        faces,
        prepared_views,
        prepared_landmarks,
        edge_faces,
        silhouette_weight=silhouette_weight,
        depth_weight=depth_weight,
        landmark_weight=landmark_weight,
        worst_view_weight=worst_view_weight,
    )


def _add_correction(accumulated, weights, index, delta, weight):
    if weight <= 0.0:
        return
    accumulated[index] = _add(accumulated[index], _scale(delta, weight))
    weights[index] += weight


def _correction_field(
    points,
    faces,
    neighbors,
    edge_faces,
    views,
    landmarks,
    *,
    silhouette_weight,
    depth_weight,
    landmark_weight,
    regularization,
    propagation_steps,
    propagation_decay,
    feature_preservation,
    maximum_step,
    pinned_vertices,
):
    accumulated = [(0.0, 0.0, 0.0) for _point in points]
    source_weights = [0.0] * len(points)
    normals = sculpt_fields.vertex_normals(points, faces)
    for view in views:
        silhouette = _silhouette_measurement(points, faces, edge_faces, view)
        plane_width = view["plane_height"] * view["image_aspect"]
        for vertex_index, target, _distance in silhouette["corrections"]:
            projected = silhouette["projected"][vertex_index]
            world_delta = _add(
                _scale(view["right"], (target[0] - projected[0]) * plane_width),
                _scale(view["up"], -(target[1] - projected[1]) * view["plane_height"]),
            )
            _add_correction(
                accumulated,
                source_weights,
                vertex_index,
                world_delta,
                silhouette_weight,
            )
        depth_items, _summaries = _depth_measurements(points, normals, view)
        for item in depth_items:
            _add_correction(
                accumulated,
                source_weights,
                item["vertex_index"],
                _scale(view["forward"], -item["residual"]),
                depth_weight,
            )
    for constraint in landmarks:
        vertex_index = constraint["vertex_index"]
        _add_correction(
            accumulated,
            source_weights,
            vertex_index,
            _subtract(constraint["target"], points[vertex_index]),
            landmark_weight * constraint["weight"],
        )
    source = [
        _scale(accumulated[index], 1.0 / source_weights[index])
        if source_weights[index] > _EPSILON
        else (0.0, 0.0, 0.0)
        for index in range(len(points))
    ]
    current = list(source)
    influence = [1.0 if weight > _EPSILON else 0.0 for weight in source_weights]
    blend = max(0.0, min(1.0, float(regularization)))
    decay = max(0.0, min(1.0, float(propagation_decay)))
    for _iteration in range(max(0, min(12, int(propagation_steps)))):
        following = list(current)
        following_influence = list(influence)
        for index, adjacent in enumerate(neighbors):
            if index in pinned_vertices or not adjacent:
                continue
            total = sum(influence[neighbor] for neighbor in adjacent)
            if total <= _EPSILON:
                continue
            average = tuple(
                sum(current[neighbor][axis] * influence[neighbor] for neighbor in adjacent)
                / total
                for axis in range(3)
            )
            if source_weights[index] > _EPSILON:
                following[index] = _add(
                    _scale(source[index], 1.0 - blend),
                    _scale(average, blend),
                )
                following_influence[index] = 1.0
            else:
                following[index] = _scale(average, decay)
                following_influence[index] = min(1.0, total / len(adjacent) * decay)
        current = following
        influence = following_influence
    curvature = sculpt_fields.curvature_values(normals, neighbors)
    preservation = max(0.0, min(1.0, float(feature_preservation)))
    for index in range(len(current)):
        if index in pinned_vertices:
            current[index] = (0.0, 0.0, 0.0)
            influence[index] = 0.0
            continue
        current[index] = _clamp_length(
            _scale(current[index], max(0.0, 1.0 - preservation * curvature[index])),
            maximum_step,
        )
    return current, influence


def _candidate_points(current, original, deltas, factor, maximum_total):
    candidate = []
    for point, baseline, delta in zip(current, original, deltas):
        proposed = _add(point, _scale(delta, factor))
        total_delta = _clamp_length(_subtract(proposed, baseline), maximum_total)
        candidate.append(_add(baseline, total_delta))
    return candidate


def _view_regression(current, candidate, tolerance):
    baseline = {item["name"]: item["combined_error"] for item in current["per_view"]}
    return [
        item["name"]
        for item in candidate["per_view"]
        if item["combined_error"] > baseline[item["name"]] + tolerance
    ]


def fit_surface_to_references(
    points,
    faces,
    views,
    *,
    landmarks=None,
    iterations=6,
    step_candidates=(0.25, 0.5, 1.0),
    minimum_improvement=1.0e-5,
    silhouette_weight=1.0,
    depth_weight=0.5,
    landmark_weight=0.5,
    worst_view_weight=0.25,
    per_view_regression_tolerance=0.002,
    regularization=0.35,
    propagation_steps=4,
    propagation_decay=0.8,
    feature_preservation=0.25,
    maximum_step=0.0,
    maximum_total_displacement=0.0,
    preserve_volume=0.0,
    pinned_vertex_indices=None,
):
    """Fit a surface coarse-to-fine and retain only cross-view improvements."""

    original, prepared_faces = _prepare_mesh(points, faces)
    baseline_integrity = _measure_surface_integrity_prepared(
        original,
        prepared_faces,
        original,
    )
    if not baseline_integrity["ok"]:
        raise ReferenceFitError(
            "Input surface contains degenerate faces and is not safe for measured fitting"
        )
    prepared_views = visual_hull.prepare_calibrated_views(views, minimum_count=2)
    neighbors, edge_faces = _topology(len(original), prepared_faces)
    prepared_landmarks = _prepare_landmarks(landmarks, original)
    iteration_count = max(1, min(MAX_FIT_ITERATIONS, int(iterations)))
    candidates = []
    for raw in list(step_candidates or [])[:MAX_STEP_CANDIDATES]:
        try:
            value = float(raw)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ReferenceFitError("step_candidates must contain finite numbers") from exc
        if not math.isfinite(value) or value <= 0.0 or value > 2.0:
            raise ReferenceFitError("step_candidates must be greater than zero and at most 2")
        if value not in candidates:
            candidates.append(value)
    if not candidates:
        raise ReferenceFitError("At least one positive step candidate is required")
    depth_evaluation_passes = 1 + iteration_count * (1 + len(candidates))
    estimated_depth_sample_evaluations = depth_evaluation_passes * sum(
        min(len(original), MAX_DEPTH_VERTICES_PER_LAYER)
        * int(layer.get("maximum_query_samples", 4))
        for view in prepared_views
        for layer in view["depth_layers"]
    )
    if estimated_depth_sample_evaluations > MAX_FIT_DEPTH_SAMPLE_EVALUATIONS:
        raise ReferenceFitError(
            "Reference fit depth workload requires up to "
            f"{estimated_depth_sample_evaluations} sample evaluations; limit is "
            f"{MAX_FIT_DEPTH_SAMPLE_EVALUATIONS}. Use fewer iterations or candidates, "
            "fewer depth sources, or less-overlapping sparse samples."
        )
    weight_values = (
        float(silhouette_weight),
        float(depth_weight),
        float(landmark_weight),
        float(worst_view_weight),
    )
    if not all(math.isfinite(value) and value >= 0.0 for value in weight_values):
        raise ReferenceFitError("Fit objective weights must be finite and non-negative")
    if weight_values[0] <= 0.0:
        raise ReferenceFitError("silhouette_weight must be greater than zero")
    pinned = set()
    for raw in list(pinned_vertex_indices or []):
        index = int(raw)
        if not 0 <= index < len(original):
            raise ReferenceFitError(f"Pinned vertex index is out of range: {index}")
        pinned.add(index)
    scale = _surface_scale(original)
    step_limit = float(maximum_step) if float(maximum_step) > 0.0 else scale * 0.05
    total_limit = (
        float(maximum_total_displacement)
        if float(maximum_total_displacement) > 0.0
        else scale * 0.25
    )
    score_arguments = {
        "silhouette_weight": weight_values[0],
        "depth_weight": weight_values[1],
        "landmark_weight": weight_values[2],
        "worst_view_weight": weight_values[3],
    }
    baseline = _evaluate_surface_fit_prepared(
        original,
        prepared_faces,
        prepared_views,
        prepared_landmarks,
        edge_faces,
        **score_arguments,
    )
    current = list(original)
    current_score = baseline
    history = []
    volume_strength = max(0.0, min(1.0, float(preserve_volume)))
    minimum = max(0.0, float(minimum_improvement))
    tolerance = max(0.0, float(per_view_regression_tolerance))
    stop_reason = "iteration limit reached"
    for iteration in range(iteration_count):
        deltas, influences = _correction_field(
            current,
            prepared_faces,
            neighbors,
            edge_faces,
            prepared_views,
            prepared_landmarks,
            silhouette_weight=weight_values[0],
            depth_weight=weight_values[1],
            landmark_weight=weight_values[2],
            regularization=regularization,
            propagation_steps=propagation_steps,
            propagation_decay=propagation_decay,
            feature_preservation=feature_preservation,
            maximum_step=step_limit,
            pinned_vertices=pinned,
        )
        if max((_length(delta) for delta in deltas), default=0.0) <= _EPSILON:
            stop_reason = "constraint field produced no movement"
            break
        trials = []
        best = None
        for factor in candidates:
            candidate_points = _candidate_points(
                current,
                original,
                deltas,
                factor,
                total_limit,
            )
            if volume_strength > 0.0 and sculpt_fields.is_closed_surface(prepared_faces):
                candidate_points, _volume = sculpt_fields.compensate_volume(
                    current,
                    candidate_points,
                    prepared_faces,
                    influences,
                    strength=volume_strength,
                )
                candidate_points = _candidate_points(
                    candidate_points,
                    original,
                    [(0.0, 0.0, 0.0)] * len(candidate_points),
                    0.0,
                    total_limit,
                )
            integrity = _measure_surface_integrity_prepared(
                candidate_points,
                prepared_faces,
                original,
            )
            if not integrity["ok"]:
                trials.append(
                    {
                        "step": factor,
                        "objective": None,
                        "improvement": None,
                        "view_regressions": [],
                        "integrity": integrity,
                        "rejected": "candidate introduced collapsed or inverted faces",
                    }
                )
                continue
            score = _evaluate_surface_fit_prepared(
                candidate_points,
                prepared_faces,
                prepared_views,
                prepared_landmarks,
                edge_faces,
                **score_arguments,
            )
            regressions = _view_regression(baseline, score, tolerance)
            improvement = current_score["objective"] - score["objective"]
            trial = {
                "step": factor,
                "objective": score["objective"],
                "improvement": improvement,
                "view_regressions": regressions,
                "integrity": integrity,
            }
            trials.append(trial)
            if regressions or improvement < minimum:
                continue
            if best is None or score["objective"] < best["score"]["objective"]:
                best = {"points": candidate_points, "score": score, "step": factor}
        history.append(
            {
                "iteration": iteration + 1,
                "objective_before": current_score["objective"],
                "trials": trials,
                "accepted_step": best["step"] if best else None,
            }
        )
        if best is None:
            stop_reason = "no candidate improved the bounded cross-view objective"
            break
        current = best["points"]
        current_score = best["score"]
    final = current_score
    changed = final["objective"] <= baseline["objective"] - minimum
    if not changed:
        current = list(original)
        final = baseline
    moved = [
        _length(_subtract(after, before))
        for before, after in zip(original, current)
    ]
    return {
        "points": current,
        "changed": changed,
        "baseline": baseline,
        "final": final,
        "objective_improvement": baseline["objective"] - final["objective"],
        "history": history,
        "stop_reason": stop_reason,
        "landmark_bindings": [
            {
                "name": item["name"],
                "vertex_index": item["vertex_index"],
                "target": list(item["target"]),
                "weight": item["weight"],
            }
            for item in prepared_landmarks
        ],
        "deformation": {
            "moved_vertex_count": sum(distance > 1.0e-9 for distance in moved),
            "mean_displacement": sum(moved) / len(moved),
            "maximum_displacement": max(moved, default=0.0),
            "maximum_step": step_limit,
            "maximum_total_displacement": total_limit,
        },
        "integrity": _measure_surface_integrity_prepared(
            current,
            prepared_faces,
            original,
        ),
        "workload": {
            "depth_evaluation_passes": depth_evaluation_passes,
            "estimated_depth_sample_evaluations": estimated_depth_sample_evaluations,
            "maximum_depth_sample_evaluations": MAX_FIT_DEPTH_SAMPLE_EVALUATIONS,
        },
    }
