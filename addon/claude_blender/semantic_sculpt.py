"""Preview-safe semantic region and deterministic sculpt operations."""

from __future__ import annotations

import hashlib
import json
import math
import re

import bpy
from mathutils import Vector

from . import (
    live_preview,
    reference_comparison,
    reference_scene,
    sculpt_fields,
)


REGION_ATTRIBUTE_PREFIX = "semantic_region::"
REGION_METADATA_PROP = "semantic_sculpt_regions_json"
MAX_REGIONS_PER_MESH = 256
MAX_SELECTOR_POINT_EVALUATIONS = 2_000_000
MAX_SCREEN_POLYGON_EDGE_EVALUATIONS = 2_000_000
MAX_SMOOTH_POINT_ITERATIONS = 2_000_000
_SAFE_NAME_RE = re.compile(r"[^a-z0-9]+")


def _safe_region_name(value):
    return " ".join(str(value or "").strip().split())[:120]


def _attribute_name(region_name):
    label = _safe_region_name(region_name)
    slug = _SAFE_NAME_RE.sub("_", label.lower()).strip("_")[:28] or "region"
    digest = hashlib.sha1(label.encode("utf-8")).hexdigest()[:8]
    return f"{REGION_ATTRIBUTE_PREFIX}{slug}:{digest}"


def _metadata(mesh):
    raw = mesh.get(REGION_METADATA_PROP)
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _store_metadata(mesh, metadata):
    if metadata:
        mesh[REGION_METADATA_PROP] = json.dumps(metadata, sort_keys=True)
    elif REGION_METADATA_PROP in mesh:
        del mesh[REGION_METADATA_PROP]


def _resolve_mesh_object(context, object_name):
    name = str(object_name or "").strip()
    obj = bpy.data.objects.get(name) if name else context.active_object
    if obj is None:
        return None, f"Mesh object not found: {name}" if name else "No active mesh object"
    if obj.type != "MESH" or obj.data is None:
        return None, f"Object is not an editable mesh: {obj.name}"
    return obj, ""


def _validate_mesh_edit(obj, *, max_vertices):
    if obj.mode != "OBJECT":
        return f"Semantic sculpt requires Object Mode: {obj.name} is in {obj.mode} mode"
    if not getattr(obj, "is_editable", True) or not getattr(
        obj.data,
        "is_editable",
        True,
    ):
        return f"Linked mesh data is not editable: {obj.name}"
    linked_objects = [
        candidate.name
        for candidate in bpy.data.objects
        if candidate.type == "MESH" and candidate.data is obj.data
    ]
    if len(linked_objects) > 1:
        return (
            f"Mesh data is shared by {len(linked_objects)} objects: {obj.data.name}. "
            "Make the target mesh single-user before semantic sculpting."
        )
    count = len(obj.data.vertices)
    if count == 0:
        return f"Mesh has no vertices: {obj.name}"
    if count > max_vertices:
        return (
            f"Mesh has {count} vertices; semantic sculpt is limited to "
            f"{max_vertices} vertices per synchronous operation"
        )
    if obj.data.shape_keys:
        return (
            f"Mesh has shape keys and direct sculpt edits are unsupported: {obj.name}. "
            "Use a mesh without shape keys until key-block editing and rollback are supported."
        )
    return ""


def _local_points(obj):
    return [tuple(float(value) for value in vertex.co) for vertex in obj.data.vertices]


def _world_points(obj, local_points=None):
    points = local_points if local_points is not None else _local_points(obj)
    return [tuple(obj.matrix_world @ Vector(point)) for point in points]


def _attribute_weights(mesh, attribute_name):
    attribute = mesh.attributes.get(attribute_name)
    if attribute is None or attribute.domain != "POINT" or attribute.data_type != "FLOAT":
        return None
    return [max(0.0, min(1.0, float(item.value))) for item in attribute.data]


def _valid_region_attribute(mesh, attribute_name):
    attribute = mesh.attributes.get(str(attribute_name or ""))
    return bool(
        attribute is not None
        and attribute.domain == "POINT"
        and attribute.data_type == "FLOAT"
    )


def _valid_metadata(mesh):
    metadata = {}
    for raw_name, raw_attribute_name in _metadata(mesh).items():
        name = _safe_region_name(raw_name)
        attribute_name = str(raw_attribute_name or "")
        if (
            name
            and attribute_name.startswith(REGION_ATTRIBUTE_PREFIX)
            and _valid_region_attribute(mesh, attribute_name)
        ):
            metadata[name] = attribute_name
    return metadata


def semantic_region_attributes(mesh, region_names):
    """Resolve named semantic regions to validated point-float attributes."""

    metadata = _valid_metadata(mesh)
    names = [_safe_region_name(name) for name in list(region_names or [])]
    names = [name for name in names if name]
    missing = [name for name in names if name not in metadata]
    return [metadata[name] for name in names if name in metadata], missing


def _write_attribute(mesh, attribute_name, weights):
    attribute = mesh.attributes.get(attribute_name)
    if attribute is not None and (
        attribute.domain != "POINT" or attribute.data_type != "FLOAT"
    ):
        raise ValueError(
            f"Existing mesh attribute has incompatible type: {attribute_name}"
        )
    if attribute is None:
        attribute = mesh.attributes.new(attribute_name, "FLOAT", "POINT")
    if len(attribute.data) != len(weights):
        raise ValueError("Semantic region weight count does not match mesh vertices")
    for item, weight in zip(attribute.data, weights):
        item.value = max(0.0, min(1.0, float(weight)))


def _region_weights(obj, region_names, *, allow_all_vertices=False):
    names = [_safe_region_name(name) for name in list(region_names or [])]
    names = [name for name in names if name]
    if not names:
        if allow_all_vertices:
            return [1.0] * len(obj.data.vertices), [], ""
        return [], [], "At least one semantic region is required"
    metadata = _valid_metadata(obj.data)
    arrays = []
    missing = []
    for name in names:
        attribute_name = str(metadata.get(name) or _attribute_name(name))
        weights = _attribute_weights(obj.data, attribute_name)
        if weights is None:
            missing.append(name)
        else:
            arrays.append(weights)
    if missing:
        return [], missing, "Semantic region(s) not found: " + ", ".join(missing)
    return sculpt_fields.combine_regions(arrays), [], ""


def _camera_for_selector(selector):
    collection, error = reference_scene.guide_collection(
        str(selector.get("collection_name") or "")
    )
    if error:
        return None, None, error
    camera, error = reference_scene.comparison_camera(
        collection,
        str(selector.get("camera_name") or ""),
    )
    return collection, camera, error


def _landmark_center(selector):
    collection, error = reference_scene.guide_collection(
        str(selector.get("collection_name") or "")
    )
    if error:
        return None, error
    name = str(selector.get("landmark_name") or "").strip()
    matches = [
        obj
        for obj in reference_scene.guide_objects(collection, "landmark")
        if str(obj.get("reference_guide_name") or obj.name) == name
    ]
    if len(matches) != 1:
        return None, (
            f"Expected one reference landmark named {name!r}; found {len(matches)}"
        )
    return tuple(matches[0].matrix_world.translation), ""


def _selector_weights(context, obj, selector, local_points, world_points):
    selector_type = str(selector.get("type") or "sphere").strip().lower()
    coordinate_space = str(
        selector.get("coordinate_space") or "world"
    ).strip().lower()
    points = local_points if coordinate_space == "local" else world_points
    feather = max(0.0, float(selector.get("feather") or 0.0))
    if selector_type == "sphere":
        return sculpt_fields.sphere_weights(
            points,
            center=selector.get("center") or (0.0, 0.0, 0.0),
            radius=max(1e-6, float(selector.get("radius") or 0.1)),
            feather=feather,
        )
    if selector_type == "box":
        return sculpt_fields.box_weights(
            points,
            minimum=selector.get("minimum") or (-1.0, -1.0, -1.0),
            maximum=selector.get("maximum") or (1.0, 1.0, 1.0),
            feather=feather,
        )
    if selector_type == "vertex_indices":
        return sculpt_fields.index_weights(
            len(local_points), selector.get("vertex_indices") or []
        )
    if selector_type == "landmark_sphere":
        center, error = _landmark_center(selector)
        if error:
            raise ValueError(error)
        return sculpt_fields.sphere_weights(
            world_points,
            center=center,
            radius=max(1e-6, float(selector.get("radius") or 0.1)),
            feather=feather,
        )
    if selector_type == "screen_polygon":
        _collection, camera, error = _camera_for_selector(selector)
        if error:
            raise ValueError(error)
        projected = [
            reference_scene.project_point(context.scene, camera, point)
            for point in world_points
        ]
        polygon = list(selector.get("points") or [])
        if str(selector.get("origin") or "top_left").lower() == "bottom_left":
            polygon = [[point[0], 1.0 - point[1]] for point in polygon]
        return sculpt_fields.polygon_weights(
            projected,
            polygon=polygon,
            feather=feather,
        )
    raise ValueError(f"Unsupported semantic region selector: {selector_type}")


def _region_summary(name, attribute_name, weights):
    nonzero = [value for value in weights if value > 1e-6]
    return {
        "name": name,
        "attribute": attribute_name,
        "vertex_count": len(nonzero),
        "maximum_weight": max(nonzero) if nonzero else 0.0,
        "mean_nonzero_weight": (
            sum(nonzero) / len(nonzero) if nonzero else 0.0
        ),
    }


def define_semantic_sculpt_regions(
    context,
    *,
    object_name="",
    regions=None,
    max_vertices=250000,
    label="Define semantic sculpt regions",
):
    """Create, update, or delete persistent weighted semantic mesh regions."""

    obj, error = _resolve_mesh_object(context, object_name)
    if error:
        return {"ok": False, "message": error}
    error = _validate_mesh_edit(
        obj,
        max_vertices=max_vertices,
    )
    if error:
        return {"ok": False, "message": error, "object": obj.name}
    definitions = [item for item in list(regions or [])[:64] if isinstance(item, dict)]
    if not definitions:
        return {"ok": False, "message": "No semantic region definitions were supplied"}

    raw_metadata = _metadata(obj.data)
    metadata = _valid_metadata(obj.data)
    stored_metadata_present = REGION_METADATA_PROP in obj.data
    try:
        normalized_definitions = []
        delete_names = set()
        names_in_call = set()
        selector_count = 0
        for definition in definitions:
            name = _safe_region_name(definition.get("name"))
            if not name:
                raise ValueError("Every semantic region needs a non-empty name")
            if name in names_in_call:
                raise ValueError(
                    f"Semantic region {name!r} is defined more than once in one call"
                )
            names_in_call.add(name)
            write_mode = str(definition.get("write_mode") or "replace").lower()
            if write_mode == "delete":
                delete_names.add(name)
                continue
            selectors = definition.get("selectors")
            if not isinstance(selectors, list):
                selector = definition.get("selector")
                selectors = [selector] if isinstance(selector, dict) else []
            selectors = [item for item in selectors[:16] if isinstance(item, dict)]
            if not selectors:
                raise ValueError(f"Semantic region {name!r} has no selectors")
            selector_count += len(selectors)
            normalized_definitions.append((name, selectors, write_mode))
        replacement_names = {
            name for name, _selectors, _write_mode in normalized_definitions
        }
        if len((set(metadata) - delete_names) | replacement_names) > MAX_REGIONS_PER_MESH:
            raise ValueError(
                f"A mesh may store at most {MAX_REGIONS_PER_MESH} semantic regions"
            )

        prepared = []
        if normalized_definitions:
            local_points = _local_points(obj)
            if len(local_points) * selector_count > MAX_SELECTOR_POINT_EVALUATIONS:
                raise ValueError(
                    "Semantic region selectors exceed the synchronous evaluation limit; "
                    "use fewer selectors or a lower-resolution mesh"
                )
            polygon_evaluations = sum(
                sculpt_fields.polygon_evaluation_count(
                    len(local_points),
                    edge_count=len(list(selector.get("points") or [])),
                    feather=selector.get("feather") or 0.0,
                )
                for _name, selectors, _write_mode in normalized_definitions
                for selector in selectors
                if str(selector.get("type") or "sphere").lower()
                == "screen_polygon"
            )
            if polygon_evaluations > MAX_SCREEN_POLYGON_EDGE_EVALUATIONS:
                raise ValueError(
                    "Screen polygon selectors exceed the synchronous edge-evaluation "
                    "limit; use fewer polygon points or a lower-resolution mesh"
                )
            world_points = _world_points(obj, local_points)
            for name, selectors, write_mode in normalized_definitions:
                selector_arrays = [
                    _selector_weights(
                        context,
                        obj,
                        selector,
                        local_points,
                        world_points,
                    )
                    for selector in selectors
                ]
                incoming = sculpt_fields.combine_regions(selector_arrays)
                attribute_name = str(metadata.get(name) or _attribute_name(name))
                existing = _attribute_weights(obj.data, attribute_name)
                if existing is None:
                    existing = [0.0] * len(local_points)
                weights = sculpt_fields.merge_weights(existing, incoming, write_mode)
                prepared.append((name, attribute_name, weights))
    except (TypeError, ValueError, OverflowError) as exc:
        return {"ok": False, "message": str(exc), "object": obj.name}

    deleted_regions = []
    for name in sorted(delete_names):
        attribute_name = metadata.pop(name, None)
        if attribute_name:
            deleted_regions.append({"name": name, "attribute": attribute_name})
    attributes_to_delete = {
        item["attribute"]
        for item in deleted_regions
        if item["attribute"] not in metadata.values()
    }
    metadata_changed = metadata != raw_metadata or (
        stored_metadata_present and not metadata
    )
    if not prepared and not attributes_to_delete and not metadata_changed:
        return {
            "ok": True,
            "message": "No matching semantic sculpt regions needed deletion",
            "object": obj.name,
            "regions": [],
            "deleted_regions": [],
        }

    operation = live_preview.begin_isolated(label, context)
    transaction = operation["transaction"]
    try:
        live_preview._record_mesh_data_snapshot(obj)
        summaries = []
        for attribute_name in sorted(attributes_to_delete):
            attribute = obj.data.attributes.get(attribute_name)
            if attribute is not None:
                obj.data.attributes.remove(attribute)
        for name, attribute_name, weights in prepared:
            _write_attribute(obj.data, attribute_name, weights)
            metadata[name] = attribute_name
            summaries.append(_region_summary(name, attribute_name, weights))
        _store_metadata(obj.data, metadata)
        obj.data.update()
        transaction["applied_steps"].append(
            {
                "type": "define_semantic_sculpt_regions",
                "label": label,
                "object": obj.name,
                "regions": [item["name"] for item in summaries],
                "deleted_regions": [item["name"] for item in deleted_regions],
            }
        )
        transaction = live_preview.finish_isolated(operation)
        live_preview.redraw(context)
        live_preview._mark_pending(context, label)
        return {
            "ok": True,
            "message": (
                f"Updated {len(summaries)} and deleted {len(deleted_regions)} "
                f"semantic sculpt region(s) on {obj.name}"
            ),
            "object": obj.name,
            "regions": summaries,
            "deleted_regions": deleted_regions,
            "transaction_id": transaction["id"],
        }
    except Exception as exc:
        live_preview.abort_isolated(operation, context)
        return {
            "ok": False,
            "message": f"Could not define semantic regions: {type(exc).__name__}: {exc}",
            "object": obj.name,
        }


def inspect_semantic_sculpt_regions(
    _context,
    *,
    object_name="",
    include_weights=False,
    max_weights=256,
):
    obj = bpy.data.objects.get(str(object_name or "").strip())
    if obj is None or obj.type != "MESH" or obj.data is None:
        return {"ok": False, "message": f"Mesh object not found: {object_name}"}
    metadata = _valid_metadata(obj.data)
    regions = []
    for name, attribute_name in sorted(metadata.items()):
        weights = _attribute_weights(obj.data, str(attribute_name))
        if weights is None:
            continue
        summary = _region_summary(name, str(attribute_name), weights)
        if include_weights:
            summary["weights"] = [
                {"vertex_index": index, "weight": weight}
                for index, weight in enumerate(weights)
                if weight > 1e-6
            ][: max(1, min(4096, int(max_weights)))]
            summary["weights_truncated"] = summary["vertex_count"] > len(
                summary["weights"]
            )
        regions.append(summary)
    return {
        "ok": True,
        "message": f"Inspected {len(regions)} semantic sculpt region(s)",
        "object": obj.name,
        "vertex_count": len(obj.data.vertices),
        "regions": regions,
    }


def _mesh_faces(obj):
    return [tuple(int(index) for index in polygon.vertices) for polygon in obj.data.polygons]


def _mesh_neighbors(obj):
    neighbors = [set() for _vertex in obj.data.vertices]
    for edge in obj.data.edges:
        first, second = (int(index) for index in edge.vertices)
        neighbors[first].add(second)
        neighbors[second].add(first)
    return [tuple(sorted(items)) for items in neighbors]


def _local_vector(obj, vector, coordinate_space):
    value = Vector(tuple(float(item) for item in vector[:3]))
    if str(coordinate_space or "local").lower() == "world":
        value = obj.matrix_world.inverted().to_3x3() @ value
    return tuple(value)


def _local_plane(obj, point, normal, coordinate_space):
    point_value = Vector(tuple(float(item) for item in point[:3]))
    normal_value = Vector(tuple(float(item) for item in normal[:3]))
    if str(coordinate_space or "local").lower() == "world":
        point_value = obj.matrix_world.inverted() @ point_value
        normal_value = obj.matrix_world.to_3x3().transposed() @ normal_value
    return tuple(point_value), tuple(normal_value)


def _apply_symmetry(original, deformed, weights, axis_name, tolerance):
    axis_name = str(axis_name or "NONE").upper()
    if axis_name not in {"X", "Y", "Z"}:
        return deformed, weights
    deltas = [
        tuple(deformed[index][axis] - original[index][axis] for axis in range(3))
        for index in range(len(original))
    ]
    deltas, mirrored_weights = sculpt_fields.mirror_deltas(
        original,
        deltas,
        weights,
        axis={"X": 0, "Y": 1, "Z": 2}[axis_name],
        tolerance=tolerance,
    )
    return [
        tuple(original[index][axis] + deltas[index][axis] for axis in range(3))
        for index in range(len(original))
    ], mirrored_weights


def _apply_operation(obj, original, weights, *, operation, arguments):
    operation = str(operation or "translate").strip().lower()
    coordinate_space = str(arguments.get("coordinate_space") or "local")
    if operation == "translate":
        vector = _local_vector(
            obj,
            list(arguments.get("vector") or (0.0, 0.0, 0.0)),
            coordinate_space,
        )
        deformed = sculpt_fields.translate_points(original, weights, vector)
    elif operation == "inflate":
        normals = [tuple(float(value) for value in vertex.normal) for vertex in obj.data.vertices]
        deformed = sculpt_fields.inflate_points(
            original,
            normals,
            weights,
            float(arguments.get("amount") or 0.0),
        )
    elif operation == "smooth":
        deformed = sculpt_fields.smooth_points(
            original,
            _mesh_neighbors(obj),
            weights,
            factor=float(arguments.get("factor", 0.5)),
            iterations=int(arguments.get("iterations", 1)),
        )
    elif operation == "flatten":
        point, normal = _local_plane(
            obj,
            list(arguments.get("plane_point") or (0.0, 0.0, 0.0)),
            list(arguments.get("plane_normal") or (0.0, 0.0, 1.0)),
            coordinate_space,
        )
        deformed = sculpt_fields.flatten_points(
            original,
            weights,
            plane_point=point,
            plane_normal=normal,
            factor=float(arguments.get("factor", 1.0)),
        )
    else:
        raise ValueError(f"Unsupported semantic sculpt operation: {operation}")
    deformed, effective_weights = _apply_symmetry(
        original,
        deformed,
        weights,
        arguments.get("symmetry_axis") or "NONE",
        max(1e-8, float(arguments.get("symmetry_tolerance") or 1e-4)),
    )
    faces = _mesh_faces(obj)
    volume = {
        "applied": False,
        "before": abs(sculpt_fields.signed_volume(original, faces)),
        "after": abs(sculpt_fields.signed_volume(deformed, faces)),
    }
    volume_strength = max(
        0.0, min(1.0, float(arguments.get("preserve_volume") or 0.0))
    )
    if volume_strength > 0.0:
        deformed, volume = sculpt_fields.compensate_volume(
            original,
            deformed,
            faces,
            effective_weights,
            strength=volume_strength,
        )
    return deformed, effective_weights, volume


def _write_points(obj, points):
    if len(points) != len(obj.data.vertices):
        raise ValueError("Deformed point count does not match mesh vertices")
    for vertex, point in zip(obj.data.vertices, points):
        vertex.co = point
    obj.data.update()


def _deformation_summary(original, deformed, weights):
    distances = [
        math.sqrt(
            sum(
                (deformed[index][axis] - original[index][axis]) ** 2
                for axis in range(3)
            )
        )
        for index in range(len(original))
    ]
    moved = [distance for distance in distances if distance > 1e-8]
    return {
        "affected_vertex_count": sum(1 for weight in weights if weight > 1e-6),
        "moved_vertex_count": len(moved),
        "maximum_local_displacement": max(moved) if moved else 0.0,
        "mean_local_displacement": sum(moved) / len(moved) if moved else 0.0,
    }


def apply_semantic_sculpt(
    context,
    *,
    object_name="",
    region_names=None,
    operation="translate",
    arguments=None,
    allow_all_vertices=False,
    max_vertices=250000,
    label="Apply semantic sculpt",
):
    """Apply one deterministic weighted sculpt field to persistent regions."""

    obj, error = _resolve_mesh_object(context, object_name)
    if error:
        return {"ok": False, "message": error}
    error = _validate_mesh_edit(
        obj,
        max_vertices=max_vertices,
    )
    if error:
        return {"ok": False, "message": error, "object": obj.name}
    weights, missing, error = _region_weights(
        obj,
        region_names,
        allow_all_vertices=allow_all_vertices,
    )
    if error:
        return {
            "ok": False,
            "message": error,
            "object": obj.name,
            "missing_regions": missing,
        }
    if not any(weight > 1e-6 for weight in weights):
        return {"ok": False, "message": "Semantic regions contain no weighted vertices", "object": obj.name}
    arguments = dict(arguments or {})
    original = _local_points(obj)
    if str(operation or "").strip().lower() == "smooth":
        try:
            iterations = max(1, min(50, int(arguments.get("iterations", 1))))
        except (TypeError, ValueError, OverflowError):
            return {
                "ok": False,
                "message": "Smooth iterations must be an integer",
                "object": obj.name,
            }
        if len(original) * iterations > MAX_SMOOTH_POINT_ITERATIONS:
            return {
                "ok": False,
                "message": (
                    "Smooth iterations exceed the synchronous evaluation limit; "
                    "use fewer iterations or a lower-resolution mesh"
                ),
                "object": obj.name,
            }
    try:
        deformed, effective_weights, volume = _apply_operation(
            obj,
            original,
            weights,
            operation=operation,
            arguments=arguments,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        return {"ok": False, "message": str(exc), "object": obj.name}
    summary = _deformation_summary(original, deformed, effective_weights)
    if summary["moved_vertex_count"] == 0:
        return {"ok": False, "message": "Sculpt operation produced no vertex movement", "object": obj.name}

    isolated = live_preview.begin_isolated(label, context)
    transaction = isolated["transaction"]
    try:
        live_preview._record_mesh_data_snapshot(obj)
        _write_points(obj, deformed)
        transaction["applied_steps"].append(
            {
                "type": "apply_semantic_sculpt",
                "label": label,
                "object": obj.name,
                "operation": str(operation),
                "regions": list(region_names or []),
            }
        )
        transaction = live_preview.finish_isolated(isolated)
        live_preview.redraw(context)
        live_preview._mark_pending(context, label)
        return {
            "ok": True,
            "message": f"Applied {operation} sculpt field to {obj.name}",
            "object": obj.name,
            "operation": str(operation),
            "regions": list(region_names or []),
            "deformation": summary,
            "volume": volume,
            "transaction_id": transaction["id"],
        }
    except Exception as exc:
        live_preview.abort_isolated(isolated, context)
        return {
            "ok": False,
            "message": f"Semantic sculpt failed: {type(exc).__name__}: {exc}",
            "object": obj.name,
        }


def _projection_matrices(context, camera):
    scene = context.scene
    render = scene.render
    scale = max(0.01, float(render.resolution_percentage) / 100.0)
    width = max(1, int(render.resolution_x * scale))
    height = max(1, int(render.resolution_y * scale))
    projection = camera.calc_matrix_camera(
        context.evaluated_depsgraph_get(),
        x=width,
        y=height,
        scale_x=float(render.pixel_aspect_x),
        scale_y=float(render.pixel_aspect_y),
    )
    world_to_clip = projection @ camera.matrix_world.inverted()
    return world_to_clip, world_to_clip.inverted()


def _screen_shift_world(world_point, delta, world_to_clip, clip_to_world):
    clip = world_to_clip @ Vector((*world_point, 1.0))
    if abs(clip.w) <= 1e-9:
        return Vector((0.0, 0.0, 0.0))
    ndc = Vector((clip.x / clip.w, clip.y / clip.w, clip.z / clip.w, 1.0))
    ndc.x += 2.0 * float(delta[0])
    ndc.y -= 2.0 * float(delta[1])
    target = clip_to_world @ ndc
    if abs(target.w) <= 1e-9:
        return Vector((0.0, 0.0, 0.0))
    target = Vector((target.x / target.w, target.y / target.w, target.z / target.w))
    return target - Vector(world_point)


def _limit_world_displacement(obj, original, deformed, maximum):
    maximum = max(0.0, float(maximum or 0.0))
    if maximum <= 0.0:
        return list(deformed), 0
    basis = obj.matrix_world.to_3x3()
    limited = []
    limited_count = 0
    for source, target in zip(original, deformed):
        delta = Vector(target) - Vector(source)
        world_length = (basis @ delta).length
        if world_length > maximum:
            delta *= maximum / world_length
            limited_count += 1
        limited.append(tuple(Vector(source) + delta))
    return limited, limited_count


def _optional_local_point(obj, point, coordinate_space):
    if point is None:
        return None
    if not isinstance(point, (list, tuple)) or len(point) < 3:
        raise ValueError("Brush center must contain three numbers")
    value = Vector(tuple(float(item) for item in point[:3]))
    if str(coordinate_space or "local").lower() == "world":
        value = obj.matrix_world.inverted() @ value
    return tuple(value)


def apply_form_aware_sculpt(
    context,
    *,
    object_name="",
    region_names=None,
    operation="tangent_relax",
    strength=0.25,
    crease_depth=0.0,
    center=None,
    coordinate_space="local",
    iterations=1,
    falloff_steps=0,
    falloff_decay=0.75,
    feature_preservation=0.5,
    maximum_world_displacement=0.0,
    symmetry_axis="NONE",
    symmetry_tolerance=1.0e-4,
    preserve_volume=0.0,
    allow_all_vertices=False,
    max_vertices=250000,
    label="Apply form-aware sculpt",
):
    """Apply topology-aware tangent relax, pinch, or crease fields."""

    obj, error = _resolve_mesh_object(context, object_name)
    if error:
        return {"ok": False, "message": error}
    error = _validate_mesh_edit(
        obj,
        max_vertices=max_vertices,
    )
    if error:
        return {"ok": False, "message": error, "object": obj.name}
    weights, missing, error = _region_weights(
        obj,
        region_names,
        allow_all_vertices=allow_all_vertices,
    )
    if error:
        return {
            "ok": False,
            "message": error,
            "object": obj.name,
            "missing_regions": missing,
        }
    operation = str(operation or "tangent_relax").strip().lower()
    if operation not in {"tangent_relax", "pinch", "crease"}:
        return {
            "ok": False,
            "message": f"Unsupported form-aware sculpt operation: {operation}",
            "object": obj.name,
        }
    if operation == "tangent_relax" and float(strength) < 0.0:
        return {
            "ok": False,
            "message": "tangent_relax strength must be non-negative",
            "object": obj.name,
        }
    try:
        iterations = max(1, min(50, int(iterations)))
        falloff_steps = max(0, min(64, int(falloff_steps)))
    except (TypeError, ValueError, OverflowError):
        return {
            "ok": False,
            "message": "iterations and falloff_steps must be integers",
            "object": obj.name,
        }
    if len(obj.data.vertices) * (iterations + falloff_steps) > MAX_SMOOTH_POINT_ITERATIONS:
        return {
            "ok": False,
            "message": (
                "Form-aware brush iterations exceed the synchronous evaluation limit; "
                "use fewer iterations or a lower-resolution mesh"
            ),
            "object": obj.name,
        }
    original = _local_points(obj)
    faces = _mesh_faces(obj)
    neighbors = _mesh_neighbors(obj)
    try:
        effective_weights = sculpt_fields.diffuse_weights(
            weights,
            neighbors,
            steps=falloff_steps,
            decay=falloff_decay,
        )
        if not any(weight > 1.0e-6 for weight in effective_weights):
            raise ValueError("Semantic regions contain no weighted vertices")
        if operation == "tangent_relax":
            deformed = sculpt_fields.tangent_relax_points(
                original,
                faces,
                neighbors,
                effective_weights,
                factor=strength,
                iterations=iterations,
                feature_preservation=feature_preservation,
            )
        else:
            local_center = _optional_local_point(obj, center, coordinate_space)
            deformed = sculpt_fields.pinch_points(
                original,
                faces,
                neighbors,
                effective_weights,
                strength=strength,
                depth=float(crease_depth) if operation == "crease" else 0.0,
                center=local_center,
                iterations=iterations,
                feature_preservation=feature_preservation,
            )
        deformed, effective_weights = _apply_symmetry(
            original,
            deformed,
            effective_weights,
            symmetry_axis,
            max(1.0e-8, float(symmetry_tolerance)),
        )
        volume = {
            "applied": False,
            "before": abs(sculpt_fields.signed_volume(original, faces)),
            "after": abs(sculpt_fields.signed_volume(deformed, faces)),
        }
        volume_strength = max(0.0, min(1.0, float(preserve_volume)))
        if volume_strength > 0.0:
            deformed, volume = sculpt_fields.compensate_volume(
                original,
                deformed,
                faces,
                effective_weights,
                strength=volume_strength,
            )
        deformed, limited_count = _limit_world_displacement(
            obj,
            original,
            deformed,
            maximum_world_displacement,
        )
        volume["final"] = abs(sculpt_fields.signed_volume(deformed, faces))
    except (TypeError, ValueError, OverflowError) as exc:
        return {"ok": False, "message": str(exc), "object": obj.name}
    summary = _deformation_summary(original, deformed, effective_weights)
    summary["limited_vertex_count"] = limited_count
    summary["falloff_steps"] = falloff_steps
    if summary["moved_vertex_count"] == 0:
        return {
            "ok": False,
            "message": "Form-aware sculpt operation produced no vertex movement",
            "object": obj.name,
        }

    isolated = live_preview.begin_isolated(label, context)
    transaction = isolated["transaction"]
    try:
        live_preview._record_mesh_data_snapshot(obj)
        _write_points(obj, deformed)
        transaction["applied_steps"].append(
            {
                "type": "apply_form_aware_sculpt",
                "label": label,
                "object": obj.name,
                "operation": operation,
                "regions": list(region_names or []),
            }
        )
        transaction = live_preview.finish_isolated(isolated)
        live_preview.redraw(context)
        live_preview._mark_pending(context, label)
        return {
            "ok": True,
            "message": f"Applied {operation} form-aware sculpt field to {obj.name}",
            "object": obj.name,
            "operation": operation,
            "regions": list(region_names or []),
            "deformation": summary,
            "volume": volume,
            "transaction_id": transaction["id"],
        }
    except Exception as exc:
        live_preview.abort_isolated(isolated, context)
        return {
            "ok": False,
            "message": f"Form-aware sculpt failed: {type(exc).__name__}: {exc}",
            "object": obj.name,
        }


def _front_facing_weights(obj, camera, weights, threshold):
    normal_matrix = obj.matrix_world.to_3x3().inverted().transposed()
    _right, camera_depth, _up = reference_scene.camera_basis(camera)
    view_direction = -camera_depth
    result = []
    for vertex, weight in zip(obj.data.vertices, weights):
        normal = normal_matrix @ vertex.normal
        if normal.length <= 1e-9:
            result.append(0.0)
            continue
        result.append(
            weight
            if normal.normalized().dot(view_direction) >= threshold
            else 0.0
        )
    return result


def _normalize_controls(controls, origin):
    normalized = []
    bottom_left = str(origin or "top_left").strip().lower() == "bottom_left"
    for raw in list(controls or [])[:32]:
        if not isinstance(raw, dict):
            continue
        source = list(raw.get("source") or [])
        target = list(raw.get("target") or [])
        if len(source) < 2 or len(target) < 2:
            continue
        source = [float(source[0]), float(source[1])]
        target = [float(target[0]), float(target[1])]
        if bottom_left:
            source[1] = 1.0 - source[1]
            target[1] = 1.0 - target[1]
        normalized.append(
            {
                "source": source,
                "target": target,
                "radius": max(0.001, min(2.0, float(raw.get("radius") or 0.08))),
                "strength": max(-4.0, min(4.0, float(raw.get("strength", 1.0)))),
            }
        )
    if not normalized:
        raise ValueError("At least one valid screen-space sculpt control is required")
    return normalized


def _screen_deformation(
    context,
    obj,
    camera,
    original,
    region_weights,
    controls,
    *,
    strength,
    front_faces_only,
    front_face_threshold,
    maximum_world_displacement,
    symmetry_axis,
    symmetry_tolerance,
    preserve_volume,
):
    world_points = _world_points(obj, original)
    projected = [
        reference_scene.project_point(context.scene, camera, point)
        for point in world_points
    ]
    effective_weights = list(region_weights)
    if front_faces_only:
        effective_weights = _front_facing_weights(
            obj,
            camera,
            effective_weights,
            front_face_threshold,
        )
    world_to_clip, clip_to_world = _projection_matrices(context, camera)
    inverse_basis = obj.matrix_world.inverted().to_3x3()
    deltas = [Vector((0.0, 0.0, 0.0)) for _point in original]
    control_weights = [0.0] * len(original)
    for control in controls:
        source = control["source"]
        delta = (
            control["target"][0] - source[0],
            control["target"][1] - source[1],
        )
        radius = control["radius"]
        control_strength = control["strength"] * float(strength)
        for index, screen_point in enumerate(projected):
            semantic_weight = effective_weights[index]
            if semantic_weight <= 1e-9:
                continue
            distance = math.hypot(
                screen_point[0] - source[0],
                screen_point[1] - source[1],
            )
            if distance >= radius:
                continue
            unit = 1.0 - distance / radius
            falloff = unit * unit * (3.0 - 2.0 * unit)
            influence = semantic_weight * falloff * control_strength
            world_delta = _screen_shift_world(
                world_points[index],
                delta,
                world_to_clip,
                clip_to_world,
            )
            local_delta = inverse_basis @ world_delta
            deltas[index] += local_delta * influence
            control_weights[index] = max(
                control_weights[index],
                min(1.0, abs(influence)),
            )
    deformed = [
        tuple(Vector(original[index]) + deltas[index])
        for index in range(len(original))
    ]
    deformed, _ = _limit_world_displacement(
        obj,
        original,
        deformed,
        maximum_world_displacement,
    )
    deformed, effective_weights = _apply_symmetry(
        original,
        deformed,
        control_weights,
        symmetry_axis,
        symmetry_tolerance,
    )
    faces = _mesh_faces(obj)
    volume = {
        "applied": False,
        "before": abs(sculpt_fields.signed_volume(original, faces)),
        "after": abs(sculpt_fields.signed_volume(deformed, faces)),
    }
    if preserve_volume > 0.0:
        deformed, volume = sculpt_fields.compensate_volume(
            original,
            deformed,
            faces,
            effective_weights,
            strength=preserve_volume,
        )
    deformed, post_compensation_limited = _limit_world_displacement(
        obj,
        original,
        deformed,
        maximum_world_displacement,
    )
    if volume.get("applied"):
        volume["corrected"] = abs(sculpt_fields.signed_volume(deformed, faces))
    volume["post_compensation_limited_vertex_count"] = post_compensation_limited
    return deformed, effective_weights, volume


def _resolve_reference_camera(collection_name, camera_name):
    collection, error = reference_scene.guide_collection(collection_name)
    if error:
        return None, None, error
    camera, error = reference_scene.comparison_camera(collection, camera_name)
    return collection, camera, error


def apply_screen_space_sculpt(
    context,
    *,
    object_name="",
    collection_name="",
    camera_name="",
    region_names=None,
    controls=None,
    origin="top_left",
    strength=1.0,
    allow_all_vertices=False,
    front_faces_only=True,
    front_face_threshold=-0.25,
    maximum_world_displacement=0.0,
    symmetry_axis="NONE",
    symmetry_tolerance=1e-4,
    preserve_volume=0.0,
    max_vertices=250000,
    label="Apply screen-space sculpt",
):
    """Project bounded reference-space pulls onto a weighted mesh region."""

    obj, error = _resolve_mesh_object(context, object_name)
    if error:
        return {"ok": False, "message": error}
    error = _validate_mesh_edit(
        obj,
        max_vertices=max_vertices,
    )
    if error:
        return {"ok": False, "message": error, "object": obj.name}
    collection, camera, error = _resolve_reference_camera(
        collection_name, camera_name
    )
    if error:
        return {"ok": False, "message": error, "object": obj.name}
    weights, missing, error = _region_weights(
        obj,
        region_names,
        allow_all_vertices=allow_all_vertices,
    )
    if error:
        return {
            "ok": False,
            "message": error,
            "object": obj.name,
            "missing_regions": missing,
        }
    try:
        normalized_controls = _normalize_controls(controls, origin)
        original = _local_points(obj)
        deformed, effective_weights, volume = _screen_deformation(
            context,
            obj,
            camera,
            original,
            weights,
            normalized_controls,
            strength=float(strength),
            front_faces_only=bool(front_faces_only),
            front_face_threshold=max(-1.0, min(1.0, float(front_face_threshold))),
            maximum_world_displacement=max(0.0, float(maximum_world_displacement)),
            symmetry_axis=symmetry_axis,
            symmetry_tolerance=max(1e-8, float(symmetry_tolerance)),
            preserve_volume=max(0.0, min(1.0, float(preserve_volume))),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        return {"ok": False, "message": str(exc), "object": obj.name}
    summary = _deformation_summary(original, deformed, effective_weights)
    if summary["moved_vertex_count"] == 0:
        return {
            "ok": False,
            "message": "Screen-space controls did not affect any eligible vertices",
            "object": obj.name,
        }

    isolated = live_preview.begin_isolated(label, context)
    transaction = isolated["transaction"]
    try:
        live_preview._record_mesh_data_snapshot(obj)
        _write_points(obj, deformed)
        transaction["applied_steps"].append(
            {
                "type": "apply_screen_space_sculpt",
                "label": label,
                "object": obj.name,
                "camera": camera.name,
                "regions": list(region_names or []),
                "control_count": len(normalized_controls),
            }
        )
        transaction = live_preview.finish_isolated(isolated)
        live_preview.redraw(context)
        live_preview._mark_pending(context, label)
        return {
            "ok": True,
            "message": f"Applied {len(normalized_controls)} screen-space sculpt control(s) to {obj.name}",
            "object": obj.name,
            "guide_collection": collection.name,
            "camera": camera.name,
            "regions": list(region_names or []),
            "controls": normalized_controls,
            "deformation": summary,
            "volume": volume,
            "transaction_id": transaction["id"],
        }
    except Exception as exc:
        live_preview.abort_isolated(isolated, context)
        return {
            "ok": False,
            "message": f"Screen-space sculpt failed: {type(exc).__name__}: {exc}",
            "object": obj.name,
        }


def _comparison_score(result, *, edge_weight, landmark_weight):
    if not result.get("ok"):
        raise ValueError(result.get("message") or "Reference comparison failed")
    metrics = result.get("metrics") or {}
    resolution = result.get("resolution") or [1, 1]
    diagonal = max(1.0, math.hypot(float(resolution[0]), float(resolution[1])))
    iou = float(metrics.get("silhouette_iou") or 0.0)
    edge = float(metrics.get("mean_edge_distance_pixels") or 0.0) / diagonal
    landmark_errors = list(result.get("landmark_errors") or [])
    landmark = (
        sum(float(item.get("distance_pixels") or 0.0) for item in landmark_errors)
        / len(landmark_errors)
        / diagonal
        if landmark_errors
        else 0.0
    )
    score_values = (iou, edge, landmark, float(edge_weight), float(landmark_weight))
    if not all(math.isfinite(value) for value in score_values):
        raise ValueError("Reference comparison produced a non-finite score component")
    score = iou - score_values[3] * edge - score_values[4] * landmark
    return {
        "score": score,
        "silhouette_iou": iou,
        "normalized_edge_error": edge,
        "normalized_landmark_error": landmark,
        "comparison_id": result.get("comparison_id", ""),
    }


def optimize_screen_space_sculpt(
    context,
    *,
    object_name="",
    collection_name="",
    camera_name="",
    outline_name="",
    reference_mask_source="auto",
    region_names=None,
    controls=None,
    origin="top_left",
    strength_candidates=None,
    minimum_improvement=0.0005,
    edge_weight=0.25,
    landmark_weight=0.1,
    landmark_targets=None,
    max_axis=256,
    mask_threshold=0.5,
    allow_all_vertices=False,
    front_faces_only=True,
    front_face_threshold=-0.25,
    maximum_world_displacement=0.0,
    symmetry_axis="NONE",
    symmetry_tolerance=1e-4,
    preserve_volume=0.0,
    max_vertices=100000,
    capture_dir=None,
    label="Optimize screen-space sculpt",
):
    """Try bounded sculpt strengths and retain only a measured improvement."""

    obj, error = _resolve_mesh_object(context, object_name)
    if error:
        return {"ok": False, "message": error}
    error = _validate_mesh_edit(
        obj,
        max_vertices=max_vertices,
    )
    if error:
        return {"ok": False, "message": error, "object": obj.name}
    collection, camera, error = _resolve_reference_camera(
        collection_name, camera_name
    )
    if error:
        return {"ok": False, "message": error, "object": obj.name}
    weights, missing, error = _region_weights(
        obj,
        region_names,
        allow_all_vertices=allow_all_vertices,
    )
    if error:
        return {
            "ok": False,
            "message": error,
            "object": obj.name,
            "missing_regions": missing,
        }
    try:
        normalized_controls = _normalize_controls(controls, origin)
        candidates = []
        for raw in list(strength_candidates or [0.5, 1.0, 1.5])[:7]:
            value = max(-4.0, min(4.0, float(raw)))
            if abs(value) > 1e-9 and value not in candidates:
                candidates.append(value)
        if not candidates:
            raise ValueError("At least one non-zero strength candidate is required")
    except (TypeError, ValueError, OverflowError) as exc:
        return {"ok": False, "message": str(exc), "object": obj.name}

    comparison_arguments = {
        "collection_name": collection.name,
        "camera_name": camera.name,
        "object_names": [obj.name],
        "selected_only": False,
        "outline_name": outline_name,
        "reference_mask_source": reference_mask_source,
        "landmark_targets": landmark_targets or [],
        "max_axis": max_axis,
        "mask_threshold": mask_threshold,
        "capture_dir": capture_dir,
    }
    baseline_result = reference_comparison.compare_model_to_reference(
        context, **comparison_arguments
    )
    try:
        baseline = _comparison_score(
            baseline_result,
            edge_weight=edge_weight,
            landmark_weight=landmark_weight,
        )
    except ValueError as exc:
        return {"ok": False, "message": str(exc), "object": obj.name}

    original = _local_points(obj)
    isolated = live_preview.begin_isolated(label, context)
    transaction = isolated["transaction"]
    trials = []
    best = None
    try:
        live_preview._record_mesh_data_snapshot(obj)
        for strength in candidates:
            _write_points(obj, original)
            deformed, effective_weights, volume = _screen_deformation(
                context,
                obj,
                camera,
                original,
                weights,
                normalized_controls,
                strength=strength,
                front_faces_only=bool(front_faces_only),
                front_face_threshold=max(-1.0, min(1.0, float(front_face_threshold))),
                maximum_world_displacement=max(0.0, float(maximum_world_displacement)),
                symmetry_axis=symmetry_axis,
                symmetry_tolerance=max(1e-8, float(symmetry_tolerance)),
                preserve_volume=max(0.0, min(1.0, float(preserve_volume))),
            )
            _write_points(obj, deformed)
            deformation = _deformation_summary(
                original,
                deformed,
                effective_weights,
            )
            if deformation["moved_vertex_count"] == 0:
                trials.append(
                    {
                        "strength": strength,
                        **baseline,
                        "deformation": deformation,
                        "volume": volume,
                        "skipped": "controls produced no vertex movement",
                    }
                )
                continue
            comparison = reference_comparison.compare_model_to_reference(
                context, **comparison_arguments
            )
            scored = _comparison_score(
                comparison,
                edge_weight=edge_weight,
                landmark_weight=landmark_weight,
            )
            trial = {
                "strength": strength,
                **scored,
                "deformation": deformation,
                "volume": volume,
            }
            trials.append(trial)
            if best is None or trial["score"] > best["score"]:
                best = {**trial, "points": deformed}

        improvement = (best["score"] - baseline["score"]) if best else 0.0
        if best is None or improvement < max(0.0, float(minimum_improvement)):
            _write_points(obj, original)
            live_preview.abort_isolated(isolated, context)
            return {
                "ok": True,
                "message": "No candidate improved the reference score; mesh restored",
                "changed": False,
                "object": obj.name,
                "guide_collection": collection.name,
                "camera": camera.name,
                "baseline": baseline,
                "trials": trials,
                "minimum_improvement": max(0.0, float(minimum_improvement)),
            }

        _write_points(obj, best["points"])
        final_result = reference_comparison.compare_model_to_reference(
            context, **comparison_arguments
        )
        final_score = _comparison_score(
            final_result,
            edge_weight=edge_weight,
            landmark_weight=landmark_weight,
        )
        final_improvement = final_score["score"] - baseline["score"]
        if final_improvement < max(0.0, float(minimum_improvement)):
            _write_points(obj, original)
            live_preview.abort_isolated(isolated, context)
            return {
                "ok": True,
                "message": (
                    "Final verification did not preserve the measured improvement; "
                    "mesh restored"
                ),
                "changed": False,
                "object": obj.name,
                "guide_collection": collection.name,
                "camera": camera.name,
                "baseline": baseline,
                "trials": trials,
                "selected_strength": best["strength"],
                "final": final_score,
                "minimum_improvement": max(
                    0.0,
                    float(minimum_improvement),
                ),
            }
        transaction["applied_steps"].append(
            {
                "type": "optimize_screen_space_sculpt",
                "label": label,
                "object": obj.name,
                "camera": camera.name,
                "regions": list(region_names or []),
                "selected_strength": best["strength"],
                "score_improvement": final_improvement,
            }
        )
        transaction = live_preview.finish_isolated(isolated)
        live_preview.redraw(context)
        live_preview._mark_pending(context, label)
        return {
            "ok": True,
            "message": f"Selected strength {best['strength']:.4g} from {len(trials)} measured sculpt trial(s)",
            "changed": True,
            "object": obj.name,
            "guide_collection": collection.name,
            "camera": camera.name,
            "baseline": baseline,
            "trials": trials,
            "selected_strength": best["strength"],
            "final": final_score,
            "score_improvement": final_improvement,
            "metrics": final_result.get("metrics") or {},
            "landmark_errors": final_result.get("landmark_errors") or [],
            "images": final_result.get("images") or [],
            "transaction_id": transaction["id"],
        }
    except Exception as exc:
        try:
            _write_points(obj, original)
        except Exception:
            pass
        live_preview.abort_isolated(isolated, context)
        return {
            "ok": False,
            "message": f"Screen-space sculpt optimization failed: {type(exc).__name__}: {exc}",
            "object": obj.name,
            "baseline": baseline,
            "trials": trials,
        }


def register():
    pass


def unregister():
    pass
