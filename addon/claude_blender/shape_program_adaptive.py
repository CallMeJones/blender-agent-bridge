"""Bounded adaptive octree and dual-contouring backend for shape programs."""

from __future__ import annotations

from collections import Counter, defaultdict
import math

from . import shape_program


MIN_BASE_DEPTH = 3
MAX_BASE_DEPTH = 7
MAX_ADAPTIVE_DEPTH = 9
MAX_REFINEMENT_REGIONS = 16
MAX_OCTREE_CELLS = 250_000
MAX_ADAPTIVE_SDF_SAMPLES = 1_000_000

_EPSILON = 1.0e-9
_CORNERS = (
    (0, 0, 0),
    (1, 0, 0),
    (1, 1, 0),
    (0, 1, 0),
    (0, 0, 1),
    (1, 0, 1),
    (1, 1, 1),
    (0, 1, 1),
)
_EDGES = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 0),
    (4, 5),
    (5, 6),
    (6, 7),
    (7, 4),
    (0, 4),
    (1, 5),
    (2, 6),
    (3, 7),
)
_PLANE_AXES = {
    0: (1, 2),
    1: (2, 0),
    2: (0, 1),
}
_INCIDENT_CYCLE = ((-1, -1), (1, -1), (1, 1), (-1, 1))


def _number(value, field, *, minimum=None, maximum=None):
    if isinstance(value, bool):
        raise shape_program.ShapeProgramError(f"{field} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise shape_program.ShapeProgramError(f"{field} must be a number") from exc
    if not math.isfinite(result):
        raise shape_program.ShapeProgramError(f"{field} must be finite")
    if minimum is not None and result < minimum:
        raise shape_program.ShapeProgramError(f"{field} must be at least {minimum}")
    if maximum is not None and result > maximum:
        raise shape_program.ShapeProgramError(f"{field} must be at most {maximum}")
    return result


def _integer(value, field, *, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int):
        raise shape_program.ShapeProgramError(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise shape_program.ShapeProgramError(
            f"{field} must be between {minimum} and {maximum}"
        )
    return value


def _vector(value, field):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise shape_program.ShapeProgramError(f"{field} must contain three numbers")
    return tuple(
        _number(item, f"{field}[{index}]", minimum=-1.0e6, maximum=1.0e6)
        for index, item in enumerate(value)
    )


def normalize_refinement_regions(regions, *, base_depth, max_depth):
    """Validate explicit local-depth regions used by the adaptive compiler."""

    if regions is None:
        return []
    if not isinstance(regions, list) or len(regions) > MAX_REFINEMENT_REGIONS:
        raise shape_program.ShapeProgramError(
            f"refinement_regions must contain at most {MAX_REFINEMENT_REGIONS} entries"
        )
    normalized = []
    for index, raw in enumerate(regions):
        field = f"refinement_regions[{index}]"
        if not isinstance(raw, dict):
            raise shape_program.ShapeProgramError(f"{field} must be an object")
        region_type = str(raw.get("type") or "sphere").strip().lower()
        if region_type not in {"sphere", "box"}:
            raise shape_program.ShapeProgramError(
                f"{field}.type must be sphere or box"
            )
        target_depth = _integer(
            raw.get("depth", max_depth),
            f"{field}.depth",
            minimum=base_depth,
            maximum=max_depth,
        )
        region = {
            "name": str(raw.get("name") or f"region_{index + 1}")[:120],
            "type": region_type,
            "depth": target_depth,
        }
        if region_type == "sphere":
            region["center"] = _vector(raw.get("center"), f"{field}.center")
            region["radius"] = _number(
                raw.get("radius"),
                f"{field}.radius",
                minimum=1.0e-5,
                maximum=10000.0,
            )
        else:
            minimum = _vector(raw.get("min"), f"{field}.min")
            maximum = _vector(raw.get("max"), f"{field}.max")
            if any(maximum[axis] <= minimum[axis] for axis in range(3)):
                raise shape_program.ShapeProgramError(
                    f"{field}.max components must exceed min"
                )
            region["min"] = minimum
            region["max"] = maximum
        normalized.append(region)
    return normalized


def _region_intersects_bounds(region, minimum, maximum):
    if region["type"] == "box":
        return all(
            maximum[axis] >= region["min"][axis]
            and minimum[axis] <= region["max"][axis]
            for axis in range(3)
        )
    distance_squared = 0.0
    for axis in range(3):
        coordinate = min(
            maximum[axis],
            max(minimum[axis], region["center"][axis]),
        )
        distance_squared += (coordinate - region["center"][axis]) ** 2
    return distance_squared <= region["radius"] ** 2


def _subtract(first, second):
    return tuple(first[axis] - second[axis] for axis in range(3))


def _dot(first, second):
    return sum(first[axis] * second[axis] for axis in range(3))


def _length(value):
    return math.sqrt(max(0.0, _dot(value, value)))


def _normalize(value, fallback=(0.0, 0.0, 1.0)):
    magnitude = _length(value)
    if magnitude <= _EPSILON:
        return fallback
    return tuple(component / magnitude for component in value)


def _cell_corners(origin, size):
    return tuple(
        tuple(origin[axis] + offset[axis] * size for axis in range(3))
        for offset in _CORNERS
    )


def _solve_3x3(matrix, vector):
    augmented = [list(matrix[row]) + [vector[row]] for row in range(3)]
    for column in range(3):
        pivot = max(range(column, 3), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= 1.0e-12:
            return None
        if pivot != column:
            augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        for item in range(column, 4):
            augmented[column][item] /= divisor
        for row in range(3):
            if row == column:
                continue
            factor = augmented[row][column]
            for item in range(column, 4):
                augmented[row][item] -= factor * augmented[column][item]
    return tuple(augmented[row][3] for row in range(3))


def _qef_vertex(hermite, cell_minimum, cell_maximum):
    mass_point = tuple(
        sum(point[axis] for point, _normal in hermite) / len(hermite)
        for axis in range(3)
    )
    ata = [[0.0] * 3 for _row in range(3)]
    atb = [0.0] * 3
    for point, normal in hermite:
        projection = _dot(normal, point)
        for row in range(3):
            atb[row] += normal[row] * projection
            for column in range(3):
                ata[row][column] += normal[row] * normal[column]
    regularization = max(1.0e-9, len(hermite) * 1.0e-7)
    for axis in range(3):
        ata[axis][axis] += regularization
        atb[axis] += regularization * mass_point[axis]
    solved = _solve_3x3(ata, atb) or mass_point
    vertex = tuple(
        min(cell_maximum[axis], max(cell_minimum[axis], solved[axis]))
        for axis in range(3)
    )
    residual = math.sqrt(
        sum(_dot(normal, _subtract(vertex, point)) ** 2 for point, normal in hermite)
        / len(hermite)
    )
    normal = _normalize(
        tuple(sum(item[axis] for _point, item in hermite) for axis in range(3))
    )
    normal_spread = 1.0 - min(
        1.0,
        _length(
            tuple(
                sum(item[axis] for _point, item in hermite) / len(hermite)
                for axis in range(3)
            )
        ),
    )
    return vertex, normal, residual, normal_spread


class _Sampler:
    __slots__ = (
        "prepared",
        "minimum",
        "maximum",
        "extent",
        "lattice_size",
        "iso_level",
        "lattice_cache",
        "hermite_cache",
        "sdf_evaluation_count",
        "lattice_cache_hits",
        "estimated_work_units",
    )

    def __init__(self, prepared, bounds, lattice_size, iso_level):
        self.prepared = prepared
        self.minimum = tuple(bounds["min"])
        self.maximum = tuple(bounds["max"])
        self.extent = tuple(
            self.maximum[axis] - self.minimum[axis] for axis in range(3)
        )
        self.lattice_size = lattice_size
        self.iso_level = iso_level
        self.lattice_cache = {}
        self.hermite_cache = {}
        self.sdf_evaluation_count = 0
        self.lattice_cache_hits = 0
        self.estimated_work_units = 0

    def lattice_point(self, key):
        return tuple(
            self.minimum[axis]
            + self.extent[axis] * (key[axis] / self.lattice_size)
            for axis in range(3)
        )

    def _evaluate(self, point):
        next_count = self.sdf_evaluation_count + 1
        next_work = (
            self.estimated_work_units + self.prepared.work_units_per_sample
        )
        if next_count > MAX_ADAPTIVE_SDF_SAMPLES:
            raise shape_program.ShapeProgramError(
                "Adaptive compile exceeds the "
                f"{MAX_ADAPTIVE_SDF_SAMPLES} SDF sample limit"
            )
        if next_work > shape_program.MAX_SDF_EVALUATIONS:
            raise shape_program.ShapeProgramError(
                "Adaptive compile exceeds the "
                f"{shape_program.MAX_SDF_EVALUATIONS} evaluation work-unit limit"
            )
        self.sdf_evaluation_count = next_count
        self.estimated_work_units = next_work
        return self.prepared.evaluate_unchecked(point)

    def lattice(self, key):
        cached = self.lattice_cache.get(key)
        if cached is not None:
            self.lattice_cache_hits += 1
            return cached
        value = self._evaluate(self.lattice_point(key))
        self.lattice_cache[key] = value
        return value

    def point(self, point):
        return self._evaluate(point)

    def gradient(self, point, step, fallback):
        result = []
        for axis in range(3):
            lower = list(point)
            upper = list(point)
            lower[axis] = max(self.minimum[axis], point[axis] - step)
            upper[axis] = min(self.maximum[axis], point[axis] + step)
            distance = upper[axis] - lower[axis]
            if distance <= _EPSILON:
                result.append(0.0)
                continue
            result.append((self.point(tuple(upper)) - self.point(tuple(lower))) / distance)
        return _normalize(tuple(result), fallback)

    def hermite(self, first, second, first_value, second_value, cell_extent):
        key = tuple(sorted((first, second)))
        cached = self.hermite_cache.get(key)
        if cached is not None:
            return cached
        denominator = second_value - first_value
        factor = (
            0.5
            if abs(denominator) <= _EPSILON
            else (self.iso_level - first_value) / denominator
        )
        factor = max(0.0, min(1.0, factor))
        first_point = self.lattice_point(first)
        second_point = self.lattice_point(second)
        point = tuple(
            first_point[axis]
            + (second_point[axis] - first_point[axis]) * factor
            for axis in range(3)
        )
        changed_axis = next(
            axis for axis in range(3) if first[axis] != second[axis]
        )
        fallback = [0.0, 0.0, 0.0]
        fallback[changed_axis] = 1.0 if second_value > first_value else -1.0
        step = max(1.0e-6, min(cell_extent) * 0.05)
        result = (point, self.gradient(point, step, tuple(fallback)))
        self.hermite_cache[key] = result
        return result


class _OctreeNode:
    __slots__ = (
        "origin",
        "size",
        "depth",
        "children",
        "corner_keys",
        "corner_values",
        "vertex",
        "normal",
        "residual",
        "normal_spread",
        "vertex_id",
    )

    def __init__(self, origin, size, depth):
        self.origin = origin
        self.size = size
        self.depth = depth
        self.children = None
        self.corner_keys = None
        self.corner_values = None
        self.vertex = None
        self.normal = None
        self.residual = 0.0
        self.normal_spread = 0.0
        self.vertex_id = None


class _AdaptiveBuilder:
    def __init__(
        self,
        prepared,
        *,
        base_depth,
        max_depth,
        error_threshold,
        refinement_regions,
        iso_level,
    ):
        self.prepared = prepared
        self.program = prepared.program
        self.base_depth = base_depth
        self.max_depth = max_depth
        self.error_threshold = error_threshold
        self.refinement_regions = refinement_regions
        self.iso_level = iso_level
        self.lattice_size = 1 << max_depth
        self.sampler = _Sampler(
            prepared,
            self.program["bounds"],
            self.lattice_size,
            iso_level,
        )
        self.cell_count = 0
        self.auto_refined_cells = 0
        self.region_refined_cells = 0
        self.topology_refined_cells = 0

    def cell_bounds(self, node):
        minimum = self.sampler.lattice_point(node.origin)
        maximum_key = tuple(node.origin[axis] + node.size for axis in range(3))
        return minimum, self.sampler.lattice_point(maximum_key)

    def region_depth(self, minimum, maximum):
        target = self.base_depth
        for region in self.refinement_regions:
            if _region_intersects_bounds(region, minimum, maximum):
                target = max(target, region["depth"])
        return target

    def hermite_data(self, node, cell_extent):
        result = []
        for first_index, second_index in _EDGES:
            first_value = node.corner_values[first_index]
            second_value = node.corner_values[second_index]
            if (first_value <= self.iso_level) == (second_value <= self.iso_level):
                continue
            result.append(
                self.sampler.hermite(
                    node.corner_keys[first_index],
                    node.corner_keys[second_index],
                    first_value,
                    second_value,
                    cell_extent,
                )
            )
        return result

    def _refine(self, node):
        child_size = node.size // 2
        children = [None] * 8
        for z_offset in range(2):
            for y_offset in range(2):
                for x_offset in range(2):
                    index = x_offset + 2 * y_offset + 4 * z_offset
                    origin = (
                        node.origin[0] + x_offset * child_size,
                        node.origin[1] + y_offset * child_size,
                        node.origin[2] + z_offset * child_size,
                    )
                    children[index] = self.build_node(
                        origin, child_size, node.depth + 1
                    )
        node.children = tuple(children)

    def build_node(self, origin, size, depth):
        self.cell_count += 1
        if self.cell_count > MAX_OCTREE_CELLS:
            raise shape_program.ShapeProgramError(
                f"Adaptive octree exceeds the {MAX_OCTREE_CELLS} cell limit"
            )
        node = _OctreeNode(origin, size, depth)
        node.corner_keys = _cell_corners(origin, size)
        node.corner_values = tuple(
            self.sampler.lattice(key) for key in node.corner_keys
        )
        inside = tuple(value <= self.iso_level for value in node.corner_values)
        heterogeneous = any(inside) and not all(inside)
        minimum, maximum = self.cell_bounds(node)
        cell_extent = tuple(maximum[axis] - minimum[axis] for axis in range(3))
        diagonal = _length(cell_extent)
        center = tuple((minimum[axis] + maximum[axis]) * 0.5 for axis in range(3))
        center_value = self.sampler.point(center)
        center_crosses = (center_value <= self.iso_level) != inside[0]
        corner_distance = min(abs(value - self.iso_level) for value in node.corner_values)
        potentially_contains_surface = (
            heterogeneous
            or center_crosses
            or min(corner_distance, abs(center_value - self.iso_level)) <= diagonal
        )
        if not potentially_contains_surface:
            return node

        target_depth = self.region_depth(minimum, maximum)
        if depth < self.base_depth or depth < target_depth or (
            not heterogeneous and depth < self.max_depth
        ):
            if depth >= self.base_depth and depth < target_depth:
                self.region_refined_cells += 1
            elif depth >= self.base_depth and not heterogeneous:
                self.auto_refined_cells += 1
            self._refine(node)
            return node

        if not heterogeneous:
            return node

        hermite = self.hermite_data(node, cell_extent)
        if not hermite:
            return node
        vertex, normal, residual, normal_spread = _qef_vertex(
            hermite, minimum, maximum
        )
        if depth < self.max_depth and (
            residual / max(diagonal, _EPSILON) > self.error_threshold
            or normal_spread > self.error_threshold
        ):
            self.auto_refined_cells += 1
            self._refine(node)
            return node
        node.vertex = vertex
        node.normal = normal
        node.residual = residual
        node.normal_spread = normal_spread
        return node

    def build(self):
        return self.build_node((0, 0, 0), self.lattice_size, 0)


def _leaves(root):
    stack = [root]
    result = []
    while stack:
        node = stack.pop()
        if node.children:
            stack.extend(node.children)
        else:
            result.append(node)
    return result


def _locate_leaf(root, point, lattice_size):
    if any(coordinate < 0.0 or coordinate >= lattice_size for coordinate in point):
        return None
    node = root
    while node.children:
        half = node.size * 0.5
        midpoint = tuple(node.origin[axis] + half for axis in range(3))
        x_side = 1 if point[0] >= midpoint[0] else 0
        y_side = 1 if point[1] >= midpoint[1] else 0
        z_side = 1 if point[2] >= midpoint[2] else 0
        node = node.children[x_side + 2 * y_side + 4 * z_side]
    return node


def _edge_descriptor(first, second):
    axis = next(index for index in range(3) if first[index] != second[index])
    plane = _PLANE_AXES[axis]
    line = (axis, first[plane[0]], first[plane[1]])
    return line, min(first[axis], second[axis]), max(first[axis], second[axis])


def _incident_leaves(root, line, start, end, lattice_size):
    axis, first_fixed, second_fixed = line
    plane = _PLANE_AXES[axis]
    midpoint = (start + end) * 0.5
    leaves = []
    for first_side, second_side in _INCIDENT_CYCLE:
        point = [0.0, 0.0, 0.0]
        point[axis] = midpoint
        point[plane[0]] = first_fixed + first_side * 0.25
        point[plane[1]] = second_fixed + second_side * 0.25
        leaves.append(_locate_leaf(root, point, lattice_size))
    return leaves


def _dual_faces(root, leaves, sampler, iso_level):
    lines = defaultdict(list)
    for leaf in leaves:
        if leaf.vertex_id is None:
            continue
        for first_index, second_index in _EDGES:
            line, start, end = _edge_descriptor(
                leaf.corner_keys[first_index], leaf.corner_keys[second_index]
            )
            lines[line].append((start, end))

    faces = []
    face_keys = set()
    skipped_segments = 0
    repair_candidates = set()
    for line, intervals in lines.items():
        breakpoints = sorted(
            {coordinate for interval in intervals for coordinate in interval}
        )
        for item in range(len(breakpoints) - 1):
            start, end = breakpoints[item], breakpoints[item + 1]
            midpoint = (start + end) * 0.5
            if not any(first <= midpoint <= second for first, second in intervals):
                continue
            axis, first_fixed, second_fixed = line
            plane = _PLANE_AXES[axis]
            first_key = [0, 0, 0]
            second_key = [0, 0, 0]
            first_key[axis] = start
            second_key[axis] = end
            first_key[plane[0]] = second_key[plane[0]] = first_fixed
            first_key[plane[1]] = second_key[plane[1]] = second_fixed
            first_value = sampler.lattice(tuple(first_key))
            second_value = sampler.lattice(tuple(second_key))
            if (first_value <= iso_level) == (second_value <= iso_level):
                continue
            incident = _incident_leaves(
                root, line, start, end, sampler.lattice_size
            )
            if any(node is None or node.vertex_id is None for node in incident):
                skipped_segments += 1
                repair_candidates.update(
                    node
                    for node in incident
                    if node is not None and node.vertex_id is not None
                )
                continue
            indices = []
            for node in incident:
                if node.vertex_id not in indices:
                    indices.append(node.vertex_id)
            if len(indices) < 3:
                skipped_segments += 1
                repair_candidates.update(incident)
                continue
            if len(indices) > 4:
                raise shape_program.ShapeProgramError(
                    "Adaptive dual contour produced an invalid edge neighborhood"
                )
            # _INCIDENT_CYCLE winds toward the positive edge axis. SDF growth
            # identifies the outward direction without relying on a warped QEF
            # polygon's geometric normal.
            if second_value < first_value:
                indices.reverse()
            face = tuple(indices)
            key = tuple(sorted(face))
            if key in face_keys:
                skipped_segments += 1
                repair_candidates.update(incident)
                continue
            face_keys.add(key)
            if len(faces) >= shape_program.MAX_OUTPUT_FACES:
                raise shape_program.ShapeProgramError(
                    "Adaptive mesh exceeds the "
                    f"{shape_program.MAX_OUTPUT_FACES} face limit"
                )
            faces.append(face)
    return faces, skipped_segments, repair_candidates


def _mesh_edge_usage(faces):
    counts = Counter()
    direction_balance = Counter()
    for face in faces:
        for index, first in enumerate(face):
            second = face[(index + 1) % len(face)]
            edge = tuple(sorted((first, second)))
            counts[edge] += 1
            direction_balance[edge] += 1 if (first, second) == edge else -1
    return counts, direction_balance


def _mesh_edge_status(faces):
    counts, direction_balance = _mesh_edge_usage(faces)
    invalid = [
        edge
        for edge, count in counts.items()
        if count != 2 or direction_balance[edge] != 0
    ]
    return counts, invalid


def _validate_closed(faces):
    edge_use, invalid = _mesh_edge_status(faces)
    if invalid:
        raise shape_program.ShapeProgramError(
            "Adaptive dual contour is not a consistently oriented watertight "
            f"manifold at {len(invalid)} mesh edges; increase base_depth or use "
            "uniform meshing"
        )
    return len(edge_use)


def _check_boundary(builder):
    depth = min(builder.max_depth, 7)
    segments = 1 << depth
    step = builder.lattice_size // segments
    inside_count = 0
    for axis in range(3):
        first_axis, second_axis = _PLANE_AXES[axis]
        for side in (0, builder.lattice_size):
            for first in range(0, builder.lattice_size + 1, step):
                for second in range(0, builder.lattice_size + 1, step):
                    key = [0, 0, 0]
                    key[axis] = side
                    key[first_axis] = first
                    key[second_axis] = second
                    if builder.sampler.lattice(tuple(key)) <= builder.iso_level:
                        inside_count += 1
    if inside_count:
        raise shape_program.ShapeProgramError(
            "Shape reaches or crosses the adaptive compile bounds at "
            f"{inside_count} boundary samples; expand bounds"
        )


def mesh_shape_program_adaptive(
    program,
    *,
    base_depth=5,
    max_depth=7,
    error_threshold=0.05,
    refinement_regions=None,
    iso_level=0.0,
    smooth_iterations=0,
):
    """Compile a shape program with bounded adaptive dual contouring."""

    base_depth = _integer(
        base_depth,
        "base_depth",
        minimum=MIN_BASE_DEPTH,
        maximum=MAX_BASE_DEPTH,
    )
    max_depth = _integer(
        max_depth,
        "max_depth",
        minimum=base_depth,
        maximum=MAX_ADAPTIVE_DEPTH,
    )
    error_threshold = _number(
        error_threshold,
        "error_threshold",
        minimum=0.001,
        maximum=0.5,
    )
    iso_level = _number(
        iso_level,
        "iso_level",
        minimum=-1000.0,
        maximum=1000.0,
    )
    smooth_iterations = _integer(
        smooth_iterations,
        "smooth_iterations",
        minimum=0,
        maximum=10,
    )
    prepared = shape_program.prepare_shape_program(program)
    regions = normalize_refinement_regions(
        refinement_regions,
        base_depth=base_depth,
        max_depth=max_depth,
    )
    builder = _AdaptiveBuilder(
        prepared,
        base_depth=base_depth,
        max_depth=max_depth,
        error_threshold=error_threshold,
        refinement_regions=regions,
        iso_level=iso_level,
    )
    _check_boundary(builder)
    root = builder.build()
    topology_repair_passes = 0
    while True:
        leaves = _leaves(root)
        surface_leaves = [leaf for leaf in leaves if leaf.vertex is not None]
        if not surface_leaves:
            raise shape_program.ShapeProgramError(
                "Adaptive shape program produced no surface inside its bounds"
            )
        for leaf in surface_leaves:
            leaf.vertex_id = None
        for vertex_id, leaf in enumerate(surface_leaves):
            if vertex_id >= shape_program.MAX_OUTPUT_VERTICES:
                raise shape_program.ShapeProgramError(
                    "Adaptive mesh exceeds the "
                    f"{shape_program.MAX_OUTPUT_VERTICES} vertex limit"
                )
            leaf.vertex_id = vertex_id
        vertices = [leaf.vertex for leaf in surface_leaves]
        faces, skipped_segments, repair_candidates = _dual_faces(
            root,
            leaves,
            builder.sampler,
            iso_level,
        )
        if not faces:
            raise shape_program.ShapeProgramError(
                "Adaptive dual contour produced no mesh faces"
            )
        _edge_use, invalid_edges = _mesh_edge_status(faces)
        if not invalid_edges and not skipped_segments:
            break
        repair_leaves = {
            surface_leaves[vertex_id]
            for edge in invalid_edges
            for vertex_id in edge
            if surface_leaves[vertex_id].depth < max_depth
        }
        repair_leaves.update(
            leaf for leaf in repair_candidates if leaf.depth < max_depth
        )
        if not repair_leaves or topology_repair_passes >= max_depth + 1:
            if invalid_edges:
                _validate_closed(faces)
            raise shape_program.ShapeProgramError(
                "Adaptive dual contour could not resolve "
                f"{skipped_segments} ambiguous minimal edge segments; increase "
                "base_depth or use uniform meshing"
            )
        for leaf in repair_leaves:
            builder.topology_refined_cells += 1
            builder._refine(leaf)
        topology_repair_passes += 1

    if skipped_segments:
        raise shape_program.ShapeProgramError(
            "Adaptive dual contour skipped "
            f"{skipped_segments} sign-changing minimal edge segments; "
            "increase base_depth or use uniform meshing"
        )
    mesh_edge_count = _validate_closed(faces)
    vertices = shape_program.smooth_shape_mesh(
        vertices, faces, smooth_iterations
    )
    depth_histogram = Counter(leaf.depth for leaf in surface_leaves)
    residuals = [leaf.residual for leaf in surface_leaves]
    region_stats = []
    for region in regions:
        intersecting = []
        for leaf in surface_leaves:
            minimum, maximum = builder.cell_bounds(leaf)
            if _region_intersects_bounds(region, minimum, maximum):
                intersecting.append(leaf)
        region_stats.append(
            {
                "name": region["name"],
                "type": region["type"],
                "target_depth": region["depth"],
                "surface_leaf_count": len(intersecting),
                "target_depth_leaf_count": sum(
                    leaf.depth >= region["depth"] for leaf in intersecting
                ),
            }
        )
    return {
        "vertices": vertices,
        "faces": faces,
        "stats": {
            "meshing_mode": "adaptive_dual",
            "base_depth": base_depth,
            "max_depth": max_depth,
            "error_threshold": error_threshold,
            "refinement_region_count": len(regions),
            "refinement_regions": regions,
            "refinement_region_stats": region_stats,
            "octree_cell_count": builder.cell_count,
            "leaf_count": len(leaves),
            "surface_leaf_count": len(surface_leaves),
            "surface_depth_histogram": {
                str(depth): depth_histogram[depth]
                for depth in sorted(depth_histogram)
            },
            "auto_refined_cell_count": builder.auto_refined_cells,
            "region_refined_cell_count": builder.region_refined_cells,
            "topology_refined_cell_count": builder.topology_refined_cells,
            "topology_repair_passes": topology_repair_passes,
            "sample_count": builder.sampler.sdf_evaluation_count,
            "lattice_sample_count": len(builder.sampler.lattice_cache),
            "lattice_cache_hits": builder.sampler.lattice_cache_hits,
            "estimated_work_units": builder.sampler.estimated_work_units,
            "qef_residual_mean": sum(residuals) / len(residuals),
            "qef_residual_max": max(residuals),
            "topology_skipped_segment_count": skipped_segments,
            "mesh_edge_count": mesh_edge_count,
            "vertex_count": len(vertices),
            "face_count": len(faces),
            "smooth_iterations": smooth_iterations,
            "iso_level": iso_level,
            "digest": shape_program.shape_program_digest(prepared.program),
        },
        "program": prepared.program,
    }
