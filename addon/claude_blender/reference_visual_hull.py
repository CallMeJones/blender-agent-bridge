"""Preview-safe visual-hull construction from calibrated multi-view guides."""

from __future__ import annotations

import json
import math

import bpy

from . import live_preview, reference_depth, reference_scene, visual_hull
from .advanced_support import _material_for_color


def _safe_label(value, fallback):
    text = " ".join(str(value or "").strip().split())
    return text[:120] or fallback


def _unique_material_name(base):
    base = _safe_label(base, "Reference Visual Hull Material")
    if bpy.data.materials.get(base) is None:
        return base
    index = 2
    while bpy.data.materials.get(f"{base} {index}") is not None:
        index += 1
    return f"{base} {index}"


def _multiview_collection(collection_name):
    name = str(collection_name or "").strip()
    if name:
        collection = bpy.data.collections.get(name)
        if collection is None:
            return None, f"Multi-view reference collection not found: {name}"
        if not bool(collection.get("reference_multiview_guides", False)):
            return None, f"Collection is not tagged as multi-view reference guides: {name}"
        return collection, ""
    matches = [
        collection
        for collection in bpy.data.collections
        if bool(collection.get("reference_multiview_guides", False))
    ]
    if not matches:
        return None, "No multi-view reference guide collection is available"
    if len(matches) > 1:
        return None, "Multiple multi-view reference collections are available; supply collection_name"
    return matches[0], ""


def _outline_overrides(items):
    result = {}
    for raw in list(items or [])[:6]:
        if not isinstance(raw, dict):
            continue
        view_name = str(raw.get("view_name") or "").strip()
        outline_name = str(raw.get("outline_name") or "").strip()
        if view_name and outline_name:
            result[view_name.casefold()] = outline_name
    return result


def _polygon_for_view(collection, requested_name):
    candidates = []
    for obj in reference_scene.guide_objects(collection, "curve"):
        cyclic = any(bool(spline.use_cyclic_u) for spline in obj.data.splines)
        if not cyclic:
            continue
        name = str(obj.get("reference_guide_name") or obj.name)
        metadata = reference_scene.json_prop(
            obj,
            reference_scene.REFERENCE_GUIDE_METADATA_PROP,
        )
        points = list(metadata.get("normalized_points") or [])
        if len(points) < 3:
            continue
        candidates.append(
            {
                "name": name,
                "object": obj.name,
                "points": points,
                "area": abs(visual_hull.polygon_area(points)),
            }
        )
    if requested_name:
        matches = [item for item in candidates if item["name"] == requested_name]
        if len(matches) != 1:
            raise ValueError(
                f"Expected one cyclic outline named {requested_name!r} in {collection.name}; "
                f"found {len(matches)}"
            )
        return matches[0]
    if not candidates:
        raise ValueError(f"View {collection.name} has no cyclic outline")
    return max(candidates, key=lambda item: item["area"])


def _axis_index(vector):
    absolute = [abs(float(value)) for value in vector]
    index = max(range(3), key=absolute.__getitem__)
    if absolute[index] < 1.0 - 1.0e-5 or any(
        absolute[other] > 1.0e-5 for other in range(3) if other != index
    ):
        return None
    return index, 1.0 if float(vector[index]) >= 0.0 else -1.0


def _derived_bounds(views, center, padding):
    radius = max(
        view["plane_height"]
        * math.sqrt(view["image_aspect"] ** 2 + 1.0)
        * 0.5
        for view in views
    )
    minimum = [center[index] - radius for index in range(3)]
    maximum = [center[index] + radius for index in range(3)]
    for view in views:
        xs = [point[0] for point in view["outline"]]
        ys = [point[1] for point in view["outline"]]
        for axis_vector, low, high in (
            (
                view["right"],
                (min(xs) - 0.5) * view["plane_height"] * view["image_aspect"],
                (max(xs) - 0.5) * view["plane_height"] * view["image_aspect"],
            ),
            (
                view["up"],
                (0.5 - max(ys)) * view["plane_height"],
                (0.5 - min(ys)) * view["plane_height"],
            ),
        ):
            resolved = _axis_index(axis_vector)
            if resolved is None:
                continue
            axis, sign = resolved
            values = [center[axis] + sign * low, center[axis] + sign * high]
            minimum[axis] = max(minimum[axis], min(values))
            maximum[axis] = min(maximum[axis], max(values))
    size = [maximum[index] - minimum[index] for index in range(3)]
    if any(component <= 1.0e-6 for component in size):
        raise ValueError("Derived silhouette bounds are empty")
    padding = max(0.0, min(0.5, float(padding)))
    padded_size = [component * (1.0 + padding * 2.0) for component in size]
    bounded_center = [
        (minimum[index] + maximum[index]) * 0.5 for index in range(3)
    ]
    return bounded_center, padded_size


def _source_views(master, view_names, outline_overrides):
    requested = {str(name).strip().casefold() for name in view_names or [] if str(name).strip()}
    overrides = _outline_overrides(outline_overrides)
    views = []
    skipped = []
    found = set()
    for child in master.children:
        metadata = reference_scene.json_prop(
            child,
            "reference_multiview_calibration_json",
        )
        view_name = str(metadata.get("name") or child.get("reference_view_name") or "").strip()
        if not view_name or (requested and view_name.casefold() not in requested):
            continue
        basis = metadata.get("basis") if isinstance(metadata.get("basis"), dict) else {}
        try:
            outline = _polygon_for_view(
                child,
                overrides.get(view_name.casefold(), ""),
            )
        except ValueError:
            if requested or view_name.casefold() in overrides:
                raise
            skipped.append(view_name)
            continue
        views.append(
            {
                "name": view_name,
                "right": basis.get("right"),
                "forward": basis.get("forward"),
                "up": basis.get("up"),
                "center": metadata.get("center"),
                "plane_height": metadata.get("plane_height"),
                "image_aspect": metadata.get("image_aspect"),
                "outline": outline["points"],
                "outline_name": outline["name"],
                "outline_object": outline["object"],
                "collection": child.name,
                "camera": str(metadata.get("camera") or ""),
            }
        )
        found.add(view_name.casefold())
    missing = sorted(requested - found)
    if missing:
        raise ValueError("Multi-view reference view(s) not found: " + ", ".join(missing))
    if len(views) < 2:
        raise ValueError("At least two calibrated views with cyclic outlines are required")
    return views, skipped


def _cleanup_created(obj, mesh, material):
    try:
        if obj is not None and bpy.data.objects.get(obj.name) is obj:
            bpy.data.objects.remove(obj, do_unlink=True)
    except Exception:
        pass
    try:
        if mesh is not None and bpy.data.meshes.get(mesh.name) is mesh and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    except Exception:
        pass
    try:
        if material is not None and bpy.data.materials.get(material.name) is material and material.users == 0:
            bpy.data.materials.remove(material)
    except Exception:
        pass


def _create_multiview_surface(
    context,
    *,
    collection_name="",
    view_names=None,
    outline_overrides=None,
    object_name="Reference Visual Hull",
    bounds_center=None,
    bounds_size=None,
    bounds_padding=0.05,
    resolution=48,
    component_mode="largest",
    minimum_component_voxels=8,
    smooth_iterations=2,
    minimum_view_angle_degrees=1.0,
    color=(0.52, 0.58, 0.68, 1.0),
    depth_sources=None,
    max_depth_axis=256,
    require_depth=False,
    surface_kind="visual_hull",
    label="Create multi-view visual hull",
):
    """Create a watertight mesh from calibrated silhouette and depth fields."""

    master, error = _multiview_collection(collection_name)
    if error:
        return {"ok": False, "message": error}
    try:
        views, skipped_views = _source_views(
            master,
            view_names,
            outline_overrides,
        )
        views, depth_summary = reference_depth.attach_depth_sources(
            views,
            depth_sources,
            max_axis=max_depth_axis,
            require_depth=require_depth,
        )
        metadata = reference_scene.json_prop(
            master,
            reference_scene.REFERENCE_GUIDE_METADATA_PROP,
        )
        master_center = metadata.get("center") or views[0]["center"]
        if (bounds_center is None) != (bounds_size is None):
            raise ValueError("bounds_center and bounds_size must be supplied together")
        if bounds_center is None:
            derived_center, derived_size = _derived_bounds(
                views,
                [float(value) for value in master_center],
                bounds_padding,
            )
        else:
            derived_center, derived_size = bounds_center, bounds_size
        result = visual_hull.carve_visual_hull(
            views,
            bounds_center=derived_center,
            bounds_size=derived_size,
            resolution=resolution,
            component_mode=component_mode,
            minimum_component_voxels=minimum_component_voxels,
            smooth_iterations=smooth_iterations,
            minimum_view_angle_degrees=minimum_view_angle_degrees,
        )
        unused_depth_layers = [
            item
            for item in result["stats"]["depth_layer_evaluations"]
            if item["evaluation_count"] == 0
        ]
        if require_depth and unused_depth_layers:
            raise ValueError(
                "Calibrated depth source(s) did not overlap occupied silhouette samples: "
                + ", ".join(
                    f"{item['view_name']}:{item['mode']} ({item['name']})"
                    for item in unused_depth_layers
                )
            )
    except (TypeError, ValueError, OverflowError) as exc:
        return {
            "ok": False,
            "code": "invalid_visual_hull",
            "message": str(exc),
            "guide_collection": master.name,
        }

    operation = live_preview.begin_isolated(label, context)
    transaction = operation["transaction"]
    mesh = None
    obj = None
    material = None
    stage = "mesh"
    try:
        mesh = bpy.data.meshes.new(f"{_safe_label(object_name, 'Reference Visual Hull')} Mesh")
        live_preview._record_created_id("mesh", mesh.name)
        mesh.from_pydata(result["vertices"], [], result["faces"])
        mesh.validate(verbose=False)
        mesh.update(calc_edges=True)
        result["stats"]["vertex_count"] = len(mesh.vertices)
        result["stats"]["face_count"] = len(mesh.polygons)
        for polygon in mesh.polygons:
            polygon.use_smooth = True
        obj = bpy.data.objects.new(_safe_label(object_name, "Reference Visual Hull"), mesh)
        live_preview._record_created_id("object", obj.name)
        context.scene.collection.objects.link(obj)
        stage = "material"
        material = _material_for_color(
            _unique_material_name(f"{obj.name} Material"),
            color,
        )
        obj.data.materials.append(material)
        obj["reference_visual_hull"] = True
        obj["reference_depth_surface"] = surface_kind == "depth_surface"
        obj["reference_visual_hull_guide_collection"] = master.name
        obj["reference_visual_hull_metadata_json"] = json.dumps(
            {
                "guide_collection": master.name,
                "views": [
                    {
                        "name": view["name"],
                        "outline_name": view["outline_name"],
                        "outline_object": view["outline_object"],
                    }
                    for view in views
                ],
                "depth_sources": depth_summary,
                **result["stats"],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
        stage = "selection"
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        context.view_layer.objects.active = obj
        transaction["applied_steps"].append(
            {
                "type": (
                    "create_multiview_depth_surface"
                    if surface_kind == "depth_surface"
                    else "create_multiview_visual_hull"
                ),
                "label": label,
                "guide_collection": master.name,
                "object": obj.name,
                "views": [view["name"] for view in views],
            }
        )
        transaction = live_preview.finish_isolated(operation)
        live_preview.redraw(context)
        live_preview._mark_pending(context, label)
        return {
            "ok": True,
            "message": (
                f"Created {'depth-constrained surface' if depth_summary else 'visual hull'} "
                f"{obj.name} from {len(views)} calibrated views"
            ),
            "object": obj.name,
            "guide_collection": master.name,
            "views": [
                {
                    "name": view["name"],
                    "outline_name": view["outline_name"],
                    "outline_object": view["outline_object"],
                }
                for view in views
            ],
            "warnings": [
                "Skipped calibrated view(s) without a cyclic outline: "
                + ", ".join(skipped_views)
            ] if skipped_views else [],
            "depth_sources": depth_summary,
            "stats": result["stats"],
            "transaction_id": transaction["id"],
        }
    except Exception as exc:
        live_preview.abort_isolated(operation, context)
        _cleanup_created(obj, mesh, material)
        return {
            "ok": False,
            "code": "visual_hull_creation_failed",
            "message": f"Visual hull failed during {stage}: {type(exc).__name__}: {exc}",
            "guide_collection": master.name,
        }


def register():
    pass


def unregister():
    pass


def create_multiview_visual_hull(
    context,
    *,
    collection_name="",
    view_names=None,
    outline_overrides=None,
    object_name="Reference Visual Hull",
    bounds_center=None,
    bounds_size=None,
    bounds_padding=0.05,
    resolution=48,
    component_mode="largest",
    minimum_component_voxels=8,
    smooth_iterations=2,
    minimum_view_angle_degrees=1.0,
    color=(0.52, 0.58, 0.68, 1.0),
    label="Create multi-view visual hull",
):
    """Create a watertight mesh by intersecting calibrated silhouettes."""

    return _create_multiview_surface(
        context,
        collection_name=collection_name,
        view_names=view_names,
        outline_overrides=outline_overrides,
        object_name=object_name,
        bounds_center=bounds_center,
        bounds_size=bounds_size,
        bounds_padding=bounds_padding,
        resolution=resolution,
        component_mode=component_mode,
        minimum_component_voxels=minimum_component_voxels,
        smooth_iterations=smooth_iterations,
        minimum_view_angle_degrees=minimum_view_angle_degrees,
        color=color,
        label=label,
    )


def create_multiview_depth_surface(
    context,
    *,
    collection_name="",
    view_names=None,
    outline_overrides=None,
    depth_sources=None,
    object_name="Reference Depth Surface",
    bounds_center=None,
    bounds_size=None,
    bounds_padding=0.05,
    resolution=48,
    component_mode="largest",
    minimum_component_voxels=8,
    smooth_iterations=2,
    minimum_view_angle_degrees=1.0,
    max_depth_axis=256,
    color=(0.48, 0.62, 0.7, 1.0),
    label="Create multi-view depth surface",
):
    """Fuse signed calibrated depth fields with the multi-view visual hull."""

    return _create_multiview_surface(
        context,
        collection_name=collection_name,
        view_names=view_names,
        outline_overrides=outline_overrides,
        depth_sources=depth_sources,
        object_name=object_name,
        bounds_center=bounds_center,
        bounds_size=bounds_size,
        bounds_padding=bounds_padding,
        resolution=resolution,
        component_mode=component_mode,
        minimum_component_voxels=minimum_component_voxels,
        smooth_iterations=smooth_iterations,
        minimum_view_angle_degrees=minimum_view_angle_degrees,
        max_depth_axis=max_depth_axis,
        require_depth=True,
        surface_kind="depth_surface",
        color=color,
        label=label,
    )


resolve_multiview_collection = _multiview_collection
source_silhouette_views = _source_views
