"""Pure bounded visual-hull construction from calibrated silhouettes."""

from __future__ import annotations

from collections import deque
import math

from . import depth_fields


MAX_GRID_CELLS = 512_000
MAX_SILHOUETTE_EDGE_EVALUATIONS = 100_000_000
MAX_DEPTH_SAMPLE_EVALUATIONS = 100_000_000
MAX_SURFACE_FACES = 1_000_000
_EPSILON = 1.0e-9


class VisualHullError(ValueError):
    """Raised when calibrated silhouettes cannot produce a bounded hull."""


def _vector(value, length, field):
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise VisualHullError(f"{field} must contain {length} numbers")
    try:
        result = tuple(float(value[index]) for index in range(length))
    except (TypeError, ValueError, OverflowError) as exc:
        raise VisualHullError(f"{field} must contain {length} numbers") from exc
    if not all(math.isfinite(component) for component in result):
        raise VisualHullError(f"{field} must contain finite numbers")
    return result


def _dot(left, right):
    return sum(left[index] * right[index] for index in range(3))


def _length(vector):
    return math.sqrt(max(0.0, _dot(vector, vector)))


def _normalized(vector, field):
    result = _vector(vector, 3, field)
    magnitude = _length(result)
    if magnitude <= _EPSILON:
        raise VisualHullError(f"{field} must not be zero length")
    return tuple(component / magnitude for component in result)


def polygon_area(points):
    """Return the signed area of a 2D polygon."""

    polygon = [_vector(point, 2, "polygon point") for point in points or []]
    if len(polygon) < 3:
        return 0.0
    return 0.5 * sum(
        polygon[index - 1][0] * polygon[index][1]
        - polygon[index][0] * polygon[index - 1][1]
        for index in range(len(polygon))
    )


def _point_in_polygon(point, polygon):
    inside = False
    previous = polygon[-1]
    for current in polygon:
        if (current[1] > point[1]) != (previous[1] > point[1]):
            denominator = previous[1] - current[1]
            if abs(denominator) > _EPSILON:
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


def _prepare_view(raw, index):
    if not isinstance(raw, dict):
        raise VisualHullError(f"views[{index}] must be an object")
    polygon = [
        _vector(point, 2, f"views[{index}].outline point")
        for point in list(raw.get("outline") or [])
    ]
    if len(polygon) < 3 or abs(polygon_area(polygon)) <= _EPSILON:
        raise VisualHullError(
            f"views[{index}].outline must be a non-degenerate polygon"
        )
    right = _normalized(raw.get("right"), f"views[{index}].right")
    forward = _normalized(raw.get("forward"), f"views[{index}].forward")
    up = _normalized(raw.get("up"), f"views[{index}].up")
    if max(abs(_dot(right, forward)), abs(_dot(right, up)), abs(_dot(forward, up))) > 1.0e-4:
        raise VisualHullError(f"views[{index}] basis must be orthogonal")
    center = _vector(raw.get("center"), 3, f"views[{index}].center")
    try:
        height = float(raw.get("plane_height"))
        aspect = float(raw.get("image_aspect"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise VisualHullError(
            f"views[{index}] plane_height and image_aspect must be numeric"
        ) from exc
    if not math.isfinite(height) or not math.isfinite(aspect) or height <= 0.0 or aspect <= 0.0:
        raise VisualHullError(
            f"views[{index}] plane_height and image_aspect must be greater than zero"
        )
    return {
        "name": str(raw.get("name") or f"view_{index + 1}"),
        "right": right,
        "forward": forward,
        "up": up,
        "center": center,
        "plane_height": height,
        "image_aspect": aspect,
        "outline": polygon,
        "outline_bounds": (
            min(point[0] for point in polygon),
            min(point[1] for point in polygon),
            max(point[0] for point in polygon),
            max(point[1] for point in polygon),
        ),
        "depth_layers": depth_fields.prepare_depth_layers(
            raw.get("depth_layers") or []
        ),
    }


def prepare_calibrated_views(views, *, minimum_count=1):
    """Validate calibrated orthographic views for reconstruction or fitting."""

    prepared = [_prepare_view(view, index) for index, view in enumerate(views or [])]
    if len(prepared) < int(minimum_count):
        raise VisualHullError(
            f"At least {int(minimum_count)} calibrated view(s) are required"
        )
    return prepared


def project_point(point, view):
    """Project a world point into normalized top-left image coordinates."""

    offset = tuple(point[index] - view["center"][index] for index in range(3))
    return (
        0.5
        + _dot(offset, view["right"])
        / (view["plane_height"] * view["image_aspect"]),
        0.5 - _dot(offset, view["up"]) / view["plane_height"],
    )


def _has_nonparallel_views(views, minimum_angle_degrees):
    minimum_angle = max(0.0, min(90.0, float(minimum_angle_degrees)))
    for index, view in enumerate(views):
        for other in views[index + 1 :]:
            cosine = max(-1.0, min(1.0, abs(_dot(view["forward"], other["forward"]))))
            if math.degrees(math.acos(cosine)) >= minimum_angle:
                return True
    return False


def _grid(bounds_center, bounds_size, resolution, cell_size=None):
    center = _vector(bounds_center, 3, "bounds_center")
    size = _vector(bounds_size, 3, "bounds_size")
    if any(component <= 0.0 for component in size):
        raise VisualHullError("bounds_size components must be greater than zero")
    if cell_size is None:
        resolution = max(8, min(80, int(resolution)))
        cell_size = max(size) / resolution
        resolution_mode = "resolution"
    else:
        try:
            cell_size = float(cell_size)
        except (TypeError, ValueError, OverflowError) as exc:
            raise VisualHullError("cell_size must be a finite number") from exc
        if not math.isfinite(cell_size) or cell_size <= 0.0:
            raise VisualHullError("cell_size must be greater than zero")
        resolution_mode = "cell_size"
    dimensions = tuple(max(1, int(math.ceil(component / cell_size))) for component in size)
    cell_count = dimensions[0] * dimensions[1] * dimensions[2]
    if cell_count > MAX_GRID_CELLS:
        raise VisualHullError(
            f"Visual hull grid requires {cell_count} cells; limit is {MAX_GRID_CELLS}"
        )
    actual_size = tuple(dimension * cell_size for dimension in dimensions)
    minimum = tuple(center[index] - actual_size[index] * 0.5 for index in range(3))
    return minimum, actual_size, dimensions, cell_size, cell_count, resolution_mode


def _occupied_cells(views, minimum, dimensions, cell_size):
    occupied = set()
    depth_evaluations = 0
    layer_evaluations = [
        [0 for _layer in view["depth_layers"]]
        for view in views
    ]
    for z_index in range(dimensions[2]):
        z = minimum[2] + (z_index + 0.5) * cell_size
        for y_index in range(dimensions[1]):
            y = minimum[1] + (y_index + 0.5) * cell_size
            for x_index in range(dimensions[0]):
                point = (
                    minimum[0] + (x_index + 0.5) * cell_size,
                    y,
                    z,
                )
                inside = True
                for view_index, view in enumerate(views):
                    projected = project_point(point, view)
                    left, top, right, bottom = view["outline_bounds"]
                    if (
                        projected[0] < left
                        or projected[0] > right
                        or projected[1] < top
                        or projected[1] > bottom
                        or not _point_in_polygon(projected, view["outline"])
                    ):
                        inside = False
                        break
                    if view["depth_layers"]:
                        point_depth = _dot(
                            tuple(point[index] - view["center"][index] for index in range(3)),
                            view["forward"],
                        )
                        for layer_index, layer in enumerate(view["depth_layers"]):
                            target_depth = depth_fields.sample_depth(layer, projected)
                            if target_depth is None:
                                continue
                            depth_evaluations += 1
                            layer_evaluations[view_index][layer_index] += 1
                            if not depth_fields.allows_depth(
                                point_depth,
                                target_depth,
                                mode=layer["mode"],
                                tolerance=layer["tolerance"],
                            ):
                                inside = False
                                break
                        if not inside:
                            break
                if inside:
                    occupied.add((x_index, y_index, z_index))
    return occupied, depth_evaluations, [
        {
            "view_name": view["name"],
            "name": layer["name"],
            "mode": layer["mode"],
            "evaluation_count": layer_evaluations[view_index][layer_index],
        }
        for view_index, view in enumerate(views)
        for layer_index, layer in enumerate(view["depth_layers"])
    ]


_NEIGHBOR_OFFSETS = (
    (-1, 0, 0),
    (1, 0, 0),
    (0, -1, 0),
    (0, 1, 0),
    (0, 0, -1),
    (0, 0, 1),
)


def _filter_components(occupied, mode, minimum_voxels):
    mode = str(mode or "largest").strip().lower()
    if mode not in {"largest", "all"}:
        raise VisualHullError("component_mode must be largest or all")
    remaining = set(occupied)
    components = []
    while remaining:
        start = remaining.pop()
        component = {start}
        queue = deque([start])
        while queue:
            cell = queue.popleft()
            for offset in _NEIGHBOR_OFFSETS:
                adjacent = tuple(cell[index] + offset[index] for index in range(3))
                if adjacent in remaining:
                    remaining.remove(adjacent)
                    component.add(adjacent)
                    queue.append(adjacent)
        components.append(component)
    components.sort(key=len, reverse=True)
    threshold = max(1, int(minimum_voxels))
    if mode == "largest":
        kept = components[:1] if components and len(components[0]) >= threshold else []
    else:
        kept = [component for component in components if len(component) >= threshold]
    return set().union(*kept) if kept else set(), [len(item) for item in components]


_FACE_CORNERS = (
    ((-1, 0, 0), ((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0))),
    ((1, 0, 0), ((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1))),
    ((0, -1, 0), ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1))),
    ((0, 1, 0), ((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0))),
    ((0, 0, -1), ((0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0))),
    ((0, 0, 1), ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))),
)


def _surface_mesh(occupied, minimum, cell_size):
    vertex_indices = {}
    vertices = []
    faces = []

    def vertex_index(lattice_point):
        index = vertex_indices.get(lattice_point)
        if index is not None:
            return index
        index = len(vertices)
        vertex_indices[lattice_point] = index
        vertices.append(
            tuple(
                minimum[axis] + lattice_point[axis] * cell_size
                for axis in range(3)
            )
        )
        return index

    for cell in sorted(occupied):
        for neighbor_offset, corners in _FACE_CORNERS:
            neighbor = tuple(cell[index] + neighbor_offset[index] for index in range(3))
            if neighbor in occupied:
                continue
            faces.append(
                tuple(
                    vertex_index(
                        tuple(cell[axis] + corner[axis] for axis in range(3))
                    )
                    for corner in corners
                )
            )
    return vertices, faces


def _neighbors(vertex_count, faces):
    result = [set() for _index in range(vertex_count)]
    for face in faces:
        for index, first in enumerate(face):
            second = face[(index + 1) % len(face)]
            result[first].add(second)
            result[second].add(first)
    return [tuple(items) for items in result]


def _smooth(vertices, faces, iterations):
    iterations = max(0, min(10, int(iterations)))
    if not iterations:
        return list(vertices)
    adjacent = _neighbors(len(vertices), faces)
    current = [tuple(vertex) for vertex in vertices]
    for _iteration in range(iterations):
        for factor in (0.45, -0.47):
            following = list(current)
            for index, neighbors in enumerate(adjacent):
                if not neighbors:
                    continue
                average = tuple(
                    sum(current[neighbor][axis] for neighbor in neighbors)
                    / len(neighbors)
                    for axis in range(3)
                )
                following[index] = tuple(
                    current[index][axis]
                    + (average[axis] - current[index][axis]) * factor
                    for axis in range(3)
                )
            current = following
    return current


def carve_visual_hull(
    views,
    *,
    bounds_center,
    bounds_size,
    resolution=48,
    cell_size=None,
    component_mode="largest",
    minimum_component_voxels=8,
    smooth_iterations=2,
    minimum_view_angle_degrees=1.0,
):
    """Intersect calibrated silhouette volumes and return a closed boundary mesh."""

    prepared = prepare_calibrated_views(views, minimum_count=2)
    if not _has_nonparallel_views(prepared, minimum_view_angle_degrees):
        raise VisualHullError("Visual hull views are too parallel to bound depth")
    minimum, actual_size, dimensions, cell_size, cell_count, resolution_mode = _grid(
        bounds_center,
        bounds_size,
        resolution,
        cell_size,
    )
    edge_evaluations = cell_count * sum(len(view["outline"]) for view in prepared)
    if edge_evaluations > MAX_SILHOUETTE_EDGE_EVALUATIONS:
        raise VisualHullError(
            "Visual hull silhouette workload requires "
            f"{edge_evaluations} edge evaluations; limit is "
            f"{MAX_SILHOUETTE_EDGE_EVALUATIONS}. Use a lower resolution or simpler outlines."
        )
    estimated_depth_sample_evaluations = cell_count * sum(
        int(layer.get("maximum_query_samples", 4))
        for view in prepared
        for layer in view["depth_layers"]
    )
    if estimated_depth_sample_evaluations > MAX_DEPTH_SAMPLE_EVALUATIONS:
        raise VisualHullError(
            "Visual hull depth workload requires up to "
            f"{estimated_depth_sample_evaluations} sample evaluations; limit is "
            f"{MAX_DEPTH_SAMPLE_EVALUATIONS}. Use a lower resolution, fewer depth "
            "sources, or less-overlapping sparse samples."
        )
    occupied, depth_evaluations, depth_layer_evaluations = _occupied_cells(
        prepared,
        minimum,
        dimensions,
        cell_size,
    )
    if not occupied:
        raise VisualHullError(
            "Calibrated silhouettes do not overlap inside the requested bounds"
        )
    occupied_before_filter = len(occupied)
    occupied, component_sizes = _filter_components(
        occupied,
        component_mode,
        minimum_component_voxels,
    )
    if not occupied:
        raise VisualHullError("No visual-hull component survived component filtering")
    vertices, faces = _surface_mesh(occupied, minimum, cell_size)
    if len(faces) > MAX_SURFACE_FACES:
        raise VisualHullError(
            f"Visual hull surface requires {len(faces)} faces; limit is {MAX_SURFACE_FACES}"
        )
    vertices = _smooth(vertices, faces, smooth_iterations)
    return {
        "vertices": vertices,
        "faces": faces,
        "stats": {
            "view_count": len(prepared),
            "view_names": [view["name"] for view in prepared],
            "grid_dimensions": list(dimensions),
            "grid_cell_count": cell_count,
            "resolution_mode": resolution_mode,
            "silhouette_edge_evaluations": edge_evaluations,
            "depth_layer_count": sum(len(view["depth_layers"]) for view in prepared),
            "depth_evaluations": depth_evaluations,
            "depth_layer_evaluations": depth_layer_evaluations,
            "estimated_depth_sample_evaluations": estimated_depth_sample_evaluations,
            "cell_size": cell_size,
            "bounds_minimum": list(minimum),
            "bounds_size": list(actual_size),
            "occupied_voxels_before_filter": occupied_before_filter,
            "occupied_voxels": len(occupied),
            "component_sizes": component_sizes,
            "vertex_count": len(vertices),
            "face_count": len(faces),
            "smooth_iterations": max(0, min(10, int(smooth_iterations))),
        },
    }
