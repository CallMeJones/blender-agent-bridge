"""Advanced Blender helpers for modeling."""



from __future__ import annotations

import bmesh
import math
import os

import bpy
from mathutils import Vector

from . import live_preview

from .advanced_support import (
    _axis_index,
    _clamped_float,
    _coerce_vector,
    _link_object_like_source,
    _material_for_color,
    _mesh_edit_blockers,
    _resolve_edit_objects,
)



EDIT_MESH_OPERATIONS = {
    "extrude_faces",
    "inset_faces",
    "merge_by_distance",
    "dissolve_degenerate",
    "bridge_boundary_loops",
    "loop_cut",
    "knife_cut",
    "proportional_edit",
}

def create_text_object(
    context,
    *,
    name,
    body,
    location,
    rotation,
    scale,
    size=1.0,
    align_x="CENTER",
    align_y="CENTER",
    material_name="",
    color=None,
    label="Create text object",
):
    transaction = live_preview.begin(label)
    curve = bpy.data.curves.new(f"{name} Data", "FONT")
    curve.body = str(body)
    curve.size = max(0.01, float(size))
    curve.align_x = align_x if align_x in {"LEFT", "CENTER", "RIGHT", "JUSTIFY", "FLUSH"} else "CENTER"
    curve.align_y = align_y if align_y in {"CENTER", "TOP", "BOTTOM"} else "CENTER"
    obj = bpy.data.objects.new(name or "Agent Bridge Text", curve)
    obj.location = _coerce_vector(location, (0.0, 0.0, 0.0))
    obj.rotation_euler = _coerce_vector(rotation, (0.0, 0.0, 0.0))
    obj.scale = _coerce_vector(scale, (1.0, 1.0, 1.0))
    context.scene.collection.objects.link(obj)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("curve", curve.name)
    if color is not None:
        material = _material_for_color(material_name or f"{obj.name} Material", color)
        curve.materials.append(material)
    transaction["applied_steps"].append({"type": "create_text_object", "label": label, "object": obj.name})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Created text object {obj.name}", "object": obj.name, "transaction_id": transaction["id"]}

def create_curve_path(
    context,
    *,
    name,
    points,
    bevel_depth=0.02,
    cyclic=False,
    material_name="",
    color=None,
    label="Create curve path",
):
    if len(points or []) < 2:
        return {"ok": False, "message": "Curve path needs at least two points"}
    transaction = live_preview.begin(label)
    curve = bpy.data.curves.new(f"{name} Data", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = max(0.0, float(bevel_depth))
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, values in zip(spline.points, points):
        xyz = _coerce_vector(values, (0.0, 0.0, 0.0))
        point.co = (xyz[0], xyz[1], xyz[2], 1.0)
    spline.use_cyclic_u = bool(cyclic)
    obj = bpy.data.objects.new(name or "Agent Bridge Curve", curve)
    context.scene.collection.objects.link(obj)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("curve", curve.name)
    if color is not None:
        material = _material_for_color(material_name or f"{obj.name} Material", color)
        curve.materials.append(material)
    transaction["applied_steps"].append({"type": "create_curve_path", "label": label, "object": obj.name})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Created curve path {obj.name}", "object": obj.name, "transaction_id": transaction["id"]}

REFERENCE_GUIDE_COORDINATE_SPACES = {"normalized", "pixel"}

def _has_reference_guide_inputs(*, include_image_plane, landmarks, curves, masses, measurements):
    if include_image_plane:
        return True
    for item in landmarks[:128]:
        if isinstance(item, dict) and item.get("point", item.get("center", item.get("position"))) is not None:
            return True
    for item in curves[:64]:
        if isinstance(item, dict) and len(list(item.get("points") or [])) >= 2:
            return True
    for item in masses[:64]:
        if isinstance(item, dict) and item.get("center") is not None and item.get("radius", item.get("radii")) is not None:
            return True
    for item in measurements[:64]:
        if not isinstance(item, dict):
            continue
        if item.get("from_point") is not None and item.get("to_point") is not None:
            return True
        if item.get("from") and item.get("to"):
            return True
    return False

def _as_float_pair(value, fallback=(0.5, 0.5)):
    if isinstance(value, dict):
        value = (value.get("x", fallback[0]), value.get("y", fallback[1]))
    try:
        values = list(value or [])[:2]
    except TypeError:
        values = []
    while len(values) < 2:
        values.append(fallback[len(values)])
    return float(values[0]), float(values[1])

def _as_color(value, fallback):
    try:
        values = list(value or [])[:4]
    except TypeError:
        values = []
    while len(values) < 4:
        values.append(fallback[len(values)])
    return tuple(float(component) for component in values[:4])

def _safe_label(value, fallback):
    text = str(value or fallback).strip() or str(fallback)
    keep = []
    for char in text:
        keep.append(char if char.isalnum() or char in {"_", "-", " "} else "_")
    return " ".join("".join(keep).split())[:80] or str(fallback)

def _reference_mapper(*, coordinate_space, image_size, plane_width, plane_height, plane_location, guide_offset_y):
    width = max(1.0, float((image_size or [1.0, 1.0])[0] or 1.0))
    height = max(1.0, float((image_size or [1.0, 1.0])[1] or 1.0))
    loc = _coerce_vector(plane_location, (0.0, 0.0, 1.5))
    coordinate_space = str(coordinate_space or "normalized").strip().lower()
    if coordinate_space not in REFERENCE_GUIDE_COORDINATE_SPACES:
        coordinate_space = "normalized"

    def normalize(point):
        x, y = _as_float_pair(point)
        if coordinate_space == "pixel":
            x = x / width
            y = y / height
        return max(0.0, min(1.0, x)), max(0.0, min(1.0, y))

    def map_point(point, *, y_offset=0.0):
        x, y = normalize(point)
        return (
            loc[0] + (x - 0.5) * float(plane_width),
            loc[1] + float(guide_offset_y) + float(y_offset),
            loc[2] + (0.5 - y) * float(plane_height),
        )

    return normalize, map_point

def _create_reference_plane(context, *, name, image_path, plane_width, plane_height, plane_location, alpha):
    mesh = bpy.data.meshes.new(f"{name} Mesh")
    x = float(plane_width) / 2.0
    z = float(plane_height) / 2.0
    loc = _coerce_vector(plane_location, (0.0, 0.0, 1.5))
    verts = [
        (loc[0] - x, loc[1], loc[2] - z),
        (loc[0] + x, loc[1], loc[2] - z),
        (loc[0] + x, loc[1], loc[2] + z),
        (loc[0] - x, loc[1], loc[2] + z),
    ]
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    context.scene.collection.objects.link(obj)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("mesh", mesh.name)
    material = bpy.data.materials.new(f"{name} Material")
    live_preview._record_created_id("material", material.name)
    material.diffuse_color = (1.0, 1.0, 1.0, max(0.0, min(1.0, float(alpha))))
    material.use_nodes = True
    material.blend_method = "BLEND"
    material.show_transparent_back = False
    nodes = material.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = material.diffuse_color[3]
        if image_path:
            try:
                image = bpy.data.images.load(image_path, check_existing=True)
                if image.users == 0:
                    live_preview._record_created_id("image", image.name)
                tex = nodes.new(type="ShaderNodeTexImage")
                tex.image = image
                material.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
            except Exception as exc:
                obj["reference_image_error"] = f"{type(exc).__name__}: {exc}"
    obj.data.materials.append(material)
    return obj

def _create_poly_curve_object(context, *, name, points, material, bevel_depth, cyclic=False):
    curve = bpy.data.curves.new(f"{name} Data", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = max(0.0, float(bevel_depth))
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, values in zip(spline.points, points):
        point.co = (float(values[0]), float(values[1]), float(values[2]), 1.0)
    spline.use_cyclic_u = bool(cyclic)
    obj = bpy.data.objects.new(name, curve)
    context.scene.collection.objects.link(obj)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("curve", curve.name)
    if material:
        curve.materials.append(material)
    return obj

def create_reference_modeling_guides(
    context,
    *,
    image_path="",
    image_size=None,
    coordinate_space="normalized",
    subject="reference model",
    collection_name="Reference Modeling Guides",
    plane_height=3.0,
    plane_location=(0.0, 0.0, 1.5),
    guide_offset_y=-0.02,
    include_image_plane=True,
    image_alpha=0.35,
    landmarks=None,
    curves=None,
    masses=None,
    measurements=None,
    label="Create reference modeling guides",
):
    """Create reference-image guide geometry from image-space landmarks and outlines."""

    landmarks = list(landmarks or [])
    curves = list(curves or [])
    masses = list(masses or [])
    measurements = list(measurements or [])
    if not _has_reference_guide_inputs(
        include_image_plane=include_image_plane,
        landmarks=landmarks,
        curves=curves,
        masses=masses,
        measurements=measurements,
    ):
        return {"ok": False, "message": "No reference guides were created; supply an image path, landmarks, curves, masses, or measurements"}
    image_size = list(image_size or [])
    loaded_image = None
    if image_path:
        expanded = os.path.abspath(os.path.expanduser(str(image_path)))
        if os.path.exists(expanded):
            image_path = expanded
            try:
                loaded_image = bpy.data.images.load(image_path, check_existing=True)
                if not image_size:
                    image_size = [float(loaded_image.size[0]), float(loaded_image.size[1])]
                if not include_image_plane and loaded_image.users == 0:
                    bpy.data.images.remove(loaded_image)
                    loaded_image = None
            except Exception:
                loaded_image = None
        elif include_image_plane:
            return {"ok": False, "message": f"Reference image path does not exist: {image_path}"}
    if len(image_size) < 2:
        image_size = [1.0, 1.0]
    image_width = max(1.0, float(image_size[0] or 1.0))
    image_height = max(1.0, float(image_size[1] or 1.0))
    plane_height = max(0.01, float(plane_height or 3.0))
    plane_width = plane_height * (image_width / image_height)
    normalize, map_point = _reference_mapper(
        coordinate_space=coordinate_space,
        image_size=(image_width, image_height),
        plane_width=plane_width,
        plane_height=plane_height,
        plane_location=plane_location,
        guide_offset_y=guide_offset_y,
    )

    had_pending_transaction = bool(
        live_preview.current_transaction() and live_preview.current_transaction().get("status") == "pending"
    )
    transaction = live_preview.begin(label, context)
    collection = bpy.data.collections.new(_safe_label(collection_name, "Reference Modeling Guides"))
    context.scene.collection.children.link(collection)
    live_preview._record_created_id("collection", collection.name)

    def move_to_collection(obj):
        if collection.objects.get(obj.name) is None:
            collection.objects.link(obj)
        for source in list(obj.users_collection):
            if source != collection:
                source.objects.unlink(obj)
        return obj

    created_curves = []
    created_landmarks = []
    created_masses = []
    created_measurements = []
    image_plane = None

    if include_image_plane:
        image_plane = _create_reference_plane(
            context,
            name=f"{collection.name} Image Plane",
            image_path=image_path,
            plane_width=plane_width,
            plane_height=plane_height,
            plane_location=plane_location,
            alpha=image_alpha,
        )
        move_to_collection(image_plane)

    landmark_positions = {}
    landmark_brief = []
    default_landmark_color = (1.0, 0.72, 0.16, 1.0)
    for index, item in enumerate(landmarks[:128], 1):
        if not isinstance(item, dict):
            continue
        name = _safe_label(item.get("name"), f"landmark_{index}")
        point = item.get("point", item.get("center", item.get("position")))
        if point is None:
            continue
        location = map_point(point)
        empty = bpy.data.objects.new(f"{collection.name} Landmark {name}", None)
        empty.empty_display_type = "SPHERE"
        empty.empty_display_size = max(0.01, float(item.get("size", 0.045) or 0.045))
        empty.location = location
        context.scene.collection.objects.link(empty)
        live_preview._record_created_id("object", empty.name)
        move_to_collection(empty)
        normalized = normalize(point)
        empty["reference_landmark_name"] = name
        empty["reference_landmark_normalized"] = normalized
        empty["reference_landmark_note"] = str(item.get("note") or "")
        landmark_positions[name] = location
        created_landmarks.append({"name": name, "object": empty.name, "location": location, "normalized": normalized})
        landmark_brief.append(f"{name} at normalized image coordinate ({normalized[0]:.3f}, {normalized[1]:.3f})")

    curve_brief = []
    for index, item in enumerate(curves[:64], 1):
        if not isinstance(item, dict):
            continue
        raw_points = list(item.get("points") or [])
        if len(raw_points) < 2:
            continue
        name = _safe_label(item.get("name"), f"curve_{index}")
        color = _as_color(item.get("color"), (0.1, 0.55, 1.0, 1.0))
        material = _material_for_color(f"{collection.name} {name} Material", color)
        points = [map_point(point, y_offset=-0.004 * index) for point in raw_points[:512]]
        obj = _create_poly_curve_object(
            context,
            name=f"{collection.name} Curve {name}",
            points=points,
            material=material,
            bevel_depth=float(item.get("bevel_depth", 0.006) or 0.006),
            cyclic=bool(item.get("cyclic", False)),
        )
        move_to_collection(obj)
        created_curves.append({"name": name, "object": obj.name, "point_count": len(points), "cyclic": bool(item.get("cyclic", False))})
        curve_brief.append(f"{name} guide with {len(points)} point(s)" + (" closed" if item.get("cyclic") else ""))

    mass_brief = []
    for index, item in enumerate(masses[:64], 1):
        if not isinstance(item, dict):
            continue
        center = item.get("center")
        radius = item.get("radius", item.get("radii"))
        if center is None or radius is None:
            continue
        rx, ry = _as_float_pair(radius, (0.1, 0.1))
        if str(coordinate_space or "normalized").strip().lower() == "pixel":
            rx = rx / image_width
            ry = ry / image_height
        rx = max(0.001, min(1.0, float(rx)))
        ry = max(0.001, min(1.0, float(ry)))
        name = _safe_label(item.get("name"), f"mass_{index}")
        color = _as_color(item.get("color"), (0.1, 0.9, 0.45, 1.0))
        material = _material_for_color(f"{collection.name} {name} Mass Material", color)
        cx, cy = normalize(center)
        ellipse = [
            map_point((cx + math.cos(step / 64.0 * math.tau) * rx, cy + math.sin(step / 64.0 * math.tau) * ry))
            for step in range(64)
        ]
        obj = _create_poly_curve_object(
            context,
            name=f"{collection.name} Mass {name}",
            points=ellipse,
            material=material,
            bevel_depth=float(item.get("bevel_depth", 0.005) or 0.005),
            cyclic=True,
        )
        move_to_collection(obj)
        created_masses.append({"name": name, "object": obj.name, "center": (cx, cy), "radius": (rx, ry)})
        mass_brief.append(f"{name} mass centered at ({cx:.3f}, {cy:.3f}) with normalized radius ({rx:.3f}, {ry:.3f})")

    measurement_brief = []
    for index, item in enumerate(measurements[:64], 1):
        if not isinstance(item, dict):
            continue
        name = _safe_label(item.get("name"), f"measurement_{index}")
        start = None
        end = None
        if item.get("from") in landmark_positions:
            start = landmark_positions[item.get("from")]
        if item.get("to") in landmark_positions:
            end = landmark_positions[item.get("to")]
        if start is None and item.get("from_point") is not None:
            start = map_point(item.get("from_point"))
        if end is None and item.get("to_point") is not None:
            end = map_point(item.get("to_point"))
        if start is None or end is None:
            continue
        color = _as_color(item.get("color"), (1.0, 0.25, 0.25, 1.0))
        material = _material_for_color(f"{collection.name} {name} Measurement Material", color)
        obj = _create_poly_curve_object(
            context,
            name=f"{collection.name} Measurement {name}",
            points=[start, end],
            material=material,
            bevel_depth=float(item.get("bevel_depth", 0.004) or 0.004),
            cyclic=False,
        )
        move_to_collection(obj)
        distance = (Vector(end) - Vector(start)).length
        created_measurements.append({"name": name, "object": obj.name, "distance": distance})
        measurement_brief.append(f"{name} guide distance {distance:.3f} Blender units")

    if not any([image_plane, created_landmarks, created_curves, created_masses, created_measurements]):
        created_collection_name = collection.name
        bpy.data.collections.remove(collection)
        transaction["before_state"].pop(f"created:collection:{created_collection_name}", None)
        if created_collection_name in transaction.get("changed_data_blocks", []):
            transaction["changed_data_blocks"].remove(created_collection_name)
        if not had_pending_transaction:
            live_preview.revert(context)
        return {"ok": False, "message": "No reference guides were created; supply an image path, landmarks, curves, masses, or measurements"}

    reference_brief_seed = {
        "subject": str(subject or "reference model"),
        "source_notes": [f"Guide collection {collection.name} generated from {coordinate_space} image coordinates."],
        "silhouette": curve_brief,
        "primary_masses": mass_brief,
        "secondary_forms": [],
        "landmarks": landmark_brief,
        "proportion_checks": measurement_brief,
        "surface_cues": [],
        "negative_constraints": ["Sculpt/model against guide curves and landmarks before adding surface detail."],
        "inspection_views": ["front", "side"],
    }
    transaction["applied_steps"].append(
        {
            "type": "create_reference_modeling_guides",
            "label": label,
            "collection": collection.name,
            "image_plane": image_plane.name if image_plane else "",
            "landmarks": [item["name"] for item in created_landmarks],
            "curves": [item["name"] for item in created_curves],
            "masses": [item["name"] for item in created_masses],
            "measurements": [item["name"] for item in created_measurements],
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Created reference modeling guides in {collection.name}",
        "collection": collection.name,
        "image_plane": image_plane.name if image_plane else "",
        "coordinate_space": str(coordinate_space or "normalized").strip().lower(),
        "image_size": [image_width, image_height],
        "plane": {"width": plane_width, "height": plane_height, "location": list(_coerce_vector(plane_location, (0.0, 0.0, 1.5)))},
        "landmarks": created_landmarks,
        "curves": created_curves,
        "masses": created_masses,
        "measurements": created_measurements,
        "reference_brief_seed": reference_brief_seed,
        "transaction_id": transaction["id"],
    }

MODELING_SEED_MODIFIER_TYPES = {"ARRAY", "BOOLEAN", "MIRROR", "NODES", "SCREW", "SOLIDIFY"}

def _material_assignment_quality(obj):
    slots = list(getattr(obj, "material_slots", []) or [])
    materials = [slot.material.name for slot in slots if getattr(slot, "material", None)]
    empty_slots = [index for index, slot in enumerate(slots) if getattr(slot, "material", None) is None]
    unassigned_polygons = 0
    mesh = obj.data if obj and obj.type == "MESH" else None
    if mesh is not None:
        for poly in mesh.polygons:
            index = int(getattr(poly, "material_index", 0) or 0)
            if index >= len(slots) or slots[index].material is None:
                unassigned_polygons += 1
    return {
        "slot_count": len(slots),
        "materials": materials,
        "empty_slots": empty_slots,
        "unassigned_polygons": unassigned_polygons,
    }

def _mesh_modeling_quality(obj, *, require_materials, allow_modifier_seed_boundaries, scale_tolerance):
    mesh = obj.data if obj and obj.type == "MESH" else None
    modifiers = [{"name": modifier.name, "type": modifier.type} for modifier in getattr(obj, "modifiers", [])]
    seed_modifier = any(item["type"] in MODELING_SEED_MODIFIER_TYPES for item in modifiers)
    materials = _material_assignment_quality(obj)
    issues = []
    warnings = []
    topology = {
        "vertices": len(mesh.vertices) if mesh else 0,
        "edges": len(mesh.edges) if mesh else 0,
        "faces": len(mesh.polygons) if mesh else 0,
        "loose_vertices": 0,
        "loose_edges": 0,
        "boundary_edges": 0,
        "non_manifold_edges": 0,
        "ngons": 0,
        "triangles": 0,
    }
    if mesh is None:
        issues.append("not a mesh")
    else:
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            topology.update(
                {
                    "loose_vertices": sum(1 for vert in bm.verts if not vert.link_edges),
                    "loose_edges": sum(1 for edge in bm.edges if edge.is_wire),
                    "boundary_edges": sum(1 for edge in bm.edges if edge.is_boundary),
                    "non_manifold_edges": sum(1 for edge in bm.edges if not edge.is_manifold),
                }
            )
        finally:
            bm.free()
        topology["ngons"] = sum(1 for poly in mesh.polygons if len(poly.vertices) > 4)
        topology["triangles"] = sum(1 for poly in mesh.polygons if len(poly.vertices) == 3)
        if topology["vertices"] <= 0:
            issues.append("mesh has no vertices")
        if topology["faces"] <= 0 and not seed_modifier:
            issues.append("mesh has no faces")
        if topology["loose_vertices"]:
            issues.append(f"{topology['loose_vertices']} loose vertex/vertices")
        if topology["loose_edges"]:
            issues.append(f"{topology['loose_edges']} loose edge(s)")
        if topology["non_manifold_edges"]:
            message = f"{topology['non_manifold_edges']} non-manifold/boundary edge(s)"
            if allow_modifier_seed_boundaries and seed_modifier:
                warnings.append(f"{message}; accepted as modifier seed geometry")
            else:
                issues.append(message)
        if topology["ngons"]:
            warnings.append(f"{topology['ngons']} n-gon face(s)")

    if require_materials:
        if not materials["materials"]:
            issues.append("no assigned material")
        if materials["empty_slots"]:
            issues.append("empty material slot(s)")
        if materials["unassigned_polygons"]:
            issues.append(f"{materials['unassigned_polygons']} polygon(s) without material assignment")

    scale = tuple(float(component) for component in getattr(obj, "scale", (1.0, 1.0, 1.0)))
    if any(abs(abs(component) - 1.0) > scale_tolerance for component in scale):
        warnings.append("object has unapplied scale")

    dimensions = tuple(float(component) for component in getattr(obj, "dimensions", (0.0, 0.0, 0.0)))
    if any(component <= 1e-6 for component in dimensions):
        warnings.append("object has near-zero dimension")

    return {
        "object": obj.name,
        "type": obj.type,
        "mesh": mesh.name if mesh else "",
        "topology": topology,
        "materials": materials,
        "modifiers": modifiers,
        "scale": [round(value, 6) for value in scale],
        "dimensions": [round(value, 6) for value in dimensions],
        "issues": issues,
        "warnings": warnings,
        "passed": not issues,
    }

def inspect_modeling_quality(
    context,
    *,
    object_names=None,
    selected_only=True,
    include_children=True,
    require_materials=True,
    allow_modifier_seed_boundaries=True,
    scale_tolerance=0.001,
    max_objects=64,
):
    roots, missing = _resolve_edit_objects(context, object_names=object_names, selected_only=selected_only, max_objects=max_objects)
    seen = set()
    objects = []
    for root in roots:
        candidates = [root]
        if include_children:
            candidates.extend(list(getattr(root, "children_recursive", []) or []))
        for obj in candidates:
            if obj.name in seen:
                continue
            seen.add(obj.name)
            objects.append(obj)
            if len(objects) >= max(1, int(max_objects or 1)):
                break
    mesh_objects = [obj for obj in objects if obj.type == "MESH"]
    if not mesh_objects:
        return {
            "ok": False,
            "passed": False,
            "message": "No mesh objects found for modeling quality inspection",
            "objects": [],
            "missing_object_names": missing,
        }

    tolerance = _clamped_float(scale_tolerance, 0.001, 0.0, 1.0)
    results = [
        _mesh_modeling_quality(
            obj,
            require_materials=bool(require_materials),
            allow_modifier_seed_boundaries=bool(allow_modifier_seed_boundaries),
            scale_tolerance=tolerance,
        )
        for obj in mesh_objects
    ]
    issue_count = sum(len(item["issues"]) for item in results)
    warning_count = sum(len(item["warnings"]) for item in results)
    return {
        "ok": True,
        "passed": issue_count == 0,
        "message": "Modeling quality inspection passed" if issue_count == 0 else "Modeling quality inspection found issues",
        "objects": results,
        "object_count": len(results),
        "issue_count": issue_count,
        "warning_count": warning_count,
        "missing_object_names": missing,
        "policy": {
            "require_materials": bool(require_materials),
            "include_children": bool(include_children),
            "allow_modifier_seed_boundaries": bool(allow_modifier_seed_boundaries),
            "scale_tolerance": tolerance,
        },
    }

def apply_procedural_array_stack(
    context,
    *,
    object_names=None,
    selected_only=True,
    count=5,
    relative_offset=(1.25, 0.0, 0.0),
    bevel_width=0.025,
    bevel_segments=2,
    add_weighted_normals=True,
    name_prefix="Agent Bridge Procedural",
    label="Apply procedural array stack",
):
    objects, missing = _resolve_edit_objects(context, object_names=object_names, selected_only=selected_only)
    meshes = [obj for obj in objects if obj.type == "MESH"]
    if not meshes:
        return {"ok": False, "message": "No mesh objects found for procedural array stack", "missing_object_names": missing}
    transaction = live_preview.begin(label, context)
    changed = []
    for obj in meshes:
        array = obj.modifiers.new(f"{name_prefix} Array", "ARRAY")
        live_preview._record_created_modifier(obj, array)
        array.count = max(1, min(1000, int(count or 1)))
        array.relative_offset_displace = _coerce_vector(relative_offset, (1.25, 0.0, 0.0))
        bevel = obj.modifiers.new(f"{name_prefix} Bevel", "BEVEL")
        live_preview._record_created_modifier(obj, bevel)
        bevel.width = max(0.0, min(10.0, float(bevel_width or 0.0)))
        bevel.segments = max(1, min(32, int(bevel_segments or 1)))
        modifiers = [array.name, bevel.name]
        if add_weighted_normals:
            weighted = obj.modifiers.new(f"{name_prefix} Weighted Normals", "WEIGHTED_NORMAL")
            live_preview._record_created_modifier(obj, weighted)
            modifiers.append(weighted.name)
        changed.append({"object": obj.name, "modifiers": modifiers})
    transaction["applied_steps"].append({"type": "apply_procedural_array_stack", "label": label, "objects": changed})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Applied procedural array stack to {len(changed)} mesh object(s)",
        "objects": changed,
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }

def _clamped_int(value, default, minimum, maximum):
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = int(default)
    return max(int(minimum), min(int(maximum), result))

def _coerce_bool_triplet(value, fallback):
    if value is None:
        values = list(fallback)
    elif isinstance(value, str):
        text = value.strip().upper()
        values = [axis in text for axis in ("X", "Y", "Z")]
    else:
        values = list(value)[:3]
    while len(values) < 3:
        values.append(bool(fallback[len(values)]))
    return tuple(bool(item) for item in values[:3])

def _axis_names_from_triplet(values):
    return [axis for axis, enabled in zip(("X", "Y", "Z"), values) if enabled]

def _mesh_topology_counts(mesh):
    return {
        "vertices": len(mesh.vertices),
        "edges": len(mesh.edges),
        "faces": len(mesh.polygons),
    }

def _bm_topology_counts(bm):
    return {
        "vertices": len(bm.verts),
        "edges": len(bm.edges),
        "faces": len(bm.faces),
    }

def _normalize_edit_mesh_operation(operation):
    normalized = str(operation or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "extrude": "extrude_faces",
        "extrude_face": "extrude_faces",
        "inset": "inset_faces",
        "inset_region": "inset_faces",
        "merge": "merge_by_distance",
        "remove_doubles": "merge_by_distance",
        "dissolve": "dissolve_degenerate",
        "bridge": "bridge_boundary_loops",
        "bridge_loops": "bridge_boundary_loops",
        "bridge_edge_loops": "bridge_boundary_loops",
        "loop": "loop_cut",
        "loopcut": "loop_cut",
        "loop_cuts": "loop_cut",
        "subdivide": "loop_cut",
        "knife": "knife_cut",
        "bisect": "knife_cut",
        "plane_cut": "knife_cut",
        "proportional": "proportional_edit",
        "proportional_move": "proportional_edit",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in EDIT_MESH_OPERATIONS else ""

def _face_scope_axis(scope):
    normalized = str(scope or "ALL").strip().upper().replace("-", "_").replace(" ", "_")
    return {
        "TOP": ("Z", 1.0),
        "UP": ("Z", 1.0),
        "BOTTOM": ("Z", -1.0),
        "DOWN": ("Z", -1.0),
        "RIGHT": ("X", 1.0),
        "LEFT": ("X", -1.0),
        "BACK": ("Y", 1.0),
        "FRONT": ("Y", -1.0),
    }.get(normalized)

def _scoped_bmesh_faces(bm, scope):
    faces = list(bm.faces)
    if not faces:
        return []
    axis_spec = _face_scope_axis(scope)
    if axis_spec is None:
        return faces
    axis_name, sign = axis_spec
    axis_index, _axis_name = _axis_index(axis_name)
    centers = [(face, face.calc_center_median()[axis_index]) for face in faces]
    values = [value for _face, value in centers]
    target = max(values) if sign > 0.0 else min(values)
    span = max(values) - min(values)
    tolerance = max(1e-6, abs(span) * 0.02)
    return [face for face, value in centers if abs(value - target) <= tolerance]

def _mesh_edit_axis_vector(axis):
    axis_index, axis_name = _axis_index(axis)
    components = [0.0, 0.0, 0.0]
    components[axis_index] = 1.0
    return Vector(components), axis_index, axis_name

def _edit_mesh_vector(bm, faces, direction, axis, distance):
    distance = _clamped_float(distance, 0.25, -100.0, 100.0)
    normalized = str(direction or "NORMAL").strip().upper()
    axis_index, axis_name = _axis_index(axis)
    if normalized == "AXIS":
        components = [0.0, 0.0, 0.0]
        components[axis_index] = 1.0
        return Vector(components) * distance, axis_name
    if normalized in {"X", "Y", "Z"}:
        axis_index, axis_name = _axis_index(normalized)
        components = [0.0, 0.0, 0.0]
        components[axis_index] = 1.0
        return Vector(components) * distance, axis_name
    normal = Vector((0.0, 0.0, 0.0))
    for face in faces:
        normal += face.normal
    if normal.length < 1e-8:
        normal = Vector((0.0, 0.0, 1.0))
    else:
        normal.normalize()
    return normal * distance, "NORMAL"

def _proportional_falloff_weight(distance, radius, falloff):
    if radius <= 0.0:
        return 1.0 if distance <= 1e-8 else 0.0
    t = max(0.0, min(1.0, float(distance) / float(radius)))
    if t >= 1.0:
        return 0.0
    falloff = str(falloff or "SMOOTH").strip().upper()
    if falloff == "CONSTANT":
        return 1.0
    if falloff == "LINEAR":
        return 1.0 - t
    if falloff == "SHARP":
        return (1.0 - t) * (1.0 - t)
    if falloff == "ROOT":
        return math.sqrt(1.0 - t)
    if falloff == "SPHERE":
        return math.sqrt(max(0.0, 1.0 - (t * t)))
    smooth = t * t * (3.0 - (2.0 * t))
    return 1.0 - smooth

def _apply_bmesh_edit_operation(
    bm,
    operation,
    *,
    face_scope,
    direction,
    axis,
    distance,
    inset_thickness,
    inset_depth,
    merge_distance,
    loop_cuts,
    cut_axis,
    cut_position,
    proportional_center,
    proportional_radius,
    proportional_falloff,
):
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.normal_update()
    before_counts = _bm_topology_counts(bm)
    details = {}

    if operation == "extrude_faces":
        faces = _scoped_bmesh_faces(bm, face_scope)
        if not faces:
            return before_counts, before_counts, {"skipped": "no scoped faces"}
        vec, used_direction = _edit_mesh_vector(bm, faces, direction, axis, distance)
        result = bmesh.ops.extrude_face_region(bm, geom=faces)
        verts = [item for item in result.get("geom", []) if isinstance(item, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=verts, vec=vec)
        details = {"face_scope": str(face_scope or "ALL").upper(), "direction": used_direction, "distance": float(distance), "faces": len(faces)}

    elif operation == "inset_faces":
        faces = _scoped_bmesh_faces(bm, face_scope)
        if not faces:
            return before_counts, before_counts, {"skipped": "no scoped faces"}
        thickness = _clamped_float(inset_thickness, 0.05, 0.0, 100.0)
        depth = _clamped_float(inset_depth, 0.0, -100.0, 100.0)
        bmesh.ops.inset_region(
            bm,
            faces=faces,
            thickness=thickness,
            depth=depth,
            use_even_offset=True,
            use_interpolate=True,
        )
        details = {"face_scope": str(face_scope or "ALL").upper(), "thickness": thickness, "depth": depth, "faces": len(faces)}

    elif operation == "merge_by_distance":
        distance = _clamped_float(merge_distance, 0.0001, 0.0, 10.0)
        result = bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=distance)
        result = result or {}
        details = {"distance": distance, "merged": len(result.get("targetmap", {}) or {})}

    elif operation == "dissolve_degenerate":
        distance = _clamped_float(merge_distance, 0.0001, 0.0, 10.0)
        bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=distance)
        details = {"distance": distance}

    elif operation == "bridge_boundary_loops":
        boundary_edges = [edge for edge in bm.edges if edge.is_boundary or edge.is_wire]
        if len(boundary_edges) < 4:
            return before_counts, before_counts, {"skipped": "not enough boundary edges"}
        if len(boundary_edges) > 512:
            return before_counts, before_counts, {"skipped": "too many boundary edges"}
        bmesh.ops.bridge_loops(bm, edges=boundary_edges)
        details = {"boundary_edges": len(boundary_edges)}

    elif operation == "loop_cut":
        cuts = _clamped_int(loop_cuts, 1, 1, 32)
        normal, axis_index, axis_name = _mesh_edit_axis_vector(cut_axis or axis)
        geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
        if not geom:
            return before_counts, before_counts, {"skipped": "empty mesh"}
        if len(geom) > 12288:
            return before_counts, before_counts, {"skipped": "too many elements for bounded loop cut"}
        values = [vert.co[axis_index] for vert in bm.verts]
        lower = min(values)
        upper = max(values)
        span = upper - lower
        if span <= 1e-8:
            return before_counts, before_counts, {"skipped": f"mesh has no span on {axis_name} axis"}
        positions = [lower + (span * (index + 1) / float(cuts + 1)) for index in range(cuts)]
        cut_elements = 0
        for position in positions:
            plane_co = Vector((0.0, 0.0, 0.0))
            plane_co[axis_index] = position
            geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
            result = bmesh.ops.bisect_plane(
                bm,
                geom=geom,
                plane_co=plane_co,
                plane_no=normal,
                clear_inner=False,
                clear_outer=False,
            )
            cut_elements += len(result.get("geom_cut", []) if result else [])
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
        if cut_elements <= 0:
            return before_counts, before_counts, {"skipped": "loop planes did not intersect mesh"}
        details = {
            "mode": "bounded_planar_loop",
            "axis": axis_name,
            "cuts": cuts,
            "positions": [round(float(position), 6) for position in positions],
            "cut_elements": cut_elements,
        }

    elif operation == "knife_cut":
        plane_axis = cut_axis or axis
        normal, axis_index, axis_name = _mesh_edit_axis_vector(plane_axis)
        position = _clamped_float(cut_position, 0.0, -1000.0, 1000.0)
        plane_co = Vector((0.0, 0.0, 0.0))
        plane_co[axis_index] = position
        geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
        if not geom:
            return before_counts, before_counts, {"skipped": "empty mesh"}
        result = bmesh.ops.bisect_plane(
            bm,
            geom=geom,
            plane_co=plane_co,
            plane_no=normal,
            clear_inner=False,
            clear_outer=False,
        )
        cut_geom = result.get("geom_cut", []) if result else []
        if not cut_geom:
            return before_counts, before_counts, {"skipped": "plane did not intersect mesh"}
        details = {"axis": axis_name, "position": position, "cut_elements": len(cut_geom)}

    elif operation == "proportional_edit":
        move_axis, _axis_index_value, axis_name = _mesh_edit_axis_vector(axis)
        amount = _clamped_float(distance, 0.25, -100.0, 100.0)
        radius = _clamped_float(proportional_radius, 1.0, 0.0001, 1000.0)
        center = Vector(_coerce_vector(proportional_center, (0.0, 0.0, 0.0)))
        moved = 0
        max_weight = 0.0
        for vert in bm.verts:
            weight = _proportional_falloff_weight((vert.co - center).length, radius, proportional_falloff)
            if weight <= 1e-6:
                continue
            vert.co += move_axis * (amount * weight)
            moved += 1
            max_weight = max(max_weight, weight)
        if moved == 0 or abs(amount) <= 1e-8:
            return before_counts, before_counts, {"skipped": "no vertices inside proportional radius"}
        details = {
            "axis": axis_name,
            "distance": amount,
            "center": [float(component) for component in center],
            "radius": radius,
            "falloff": str(proportional_falloff or "SMOOTH").strip().upper(),
            "moved_vertices": moved,
            "max_weight": round(float(max_weight), 6),
        }

    bm.normal_update()
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    after_counts = _bm_topology_counts(bm)
    return before_counts, after_counts, details

def _selected_meshes_except(context, excluded):
    return [obj for obj in getattr(context, "selected_objects", []) if obj.type == "MESH" and obj != excluded]

def _forget_recorded_created_id(transaction, kind, name):
    if not transaction or not name:
        return
    key = f"created:{kind}:{name}"
    if key not in transaction.get("before_state", {}):
        return
    transaction["before_state"].pop(key, None)
    try:
        transaction.get("changed_data_blocks", []).remove(name)
    except ValueError:
        pass

def edit_mesh(
    context,
    *,
    operation="extrude_faces",
    object_names=None,
    selected_only=True,
    face_scope="ALL",
    direction="NORMAL",
    axis="Z",
    distance=0.25,
    inset_thickness=0.05,
    inset_depth=0.0,
    merge_distance=0.0001,
    loop_cuts=1,
    cut_axis="Z",
    cut_position=0.0,
    proportional_center=None,
    proportional_radius=1.0,
    proportional_falloff="SMOOTH",
    allow_shape_keys=False,
    label="Edit mesh",
):
    operation = _normalize_edit_mesh_operation(operation)
    if not operation:
        return {"ok": False, "message": f"operation must be one of {', '.join(sorted(EDIT_MESH_OPERATIONS))}"}
    objects, missing = _resolve_edit_objects(context, object_names=object_names, selected_only=selected_only, max_objects=16)
    meshes = [obj for obj in objects if obj.type == "MESH"]
    if not meshes:
        return {"ok": False, "message": "No mesh objects found for edit_mesh", "missing_object_names": missing}

    changed = []
    skipped = []
    transaction = None
    opened_transaction = False
    for obj in meshes:
        blockers = _mesh_edit_blockers(obj, allow_shape_keys=allow_shape_keys)
        if blockers:
            skipped.append({"object": obj.name, "reason": "; ".join(blockers)})
            continue
        mesh = obj.data
        before_mesh_counts = _mesh_topology_counts(mesh)
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            before_counts, after_counts, details = _apply_bmesh_edit_operation(
                bm,
                operation,
                face_scope=face_scope,
                direction=direction,
                axis=axis,
                distance=distance,
                inset_thickness=inset_thickness,
                inset_depth=inset_depth,
                merge_distance=merge_distance,
                loop_cuts=loop_cuts,
                cut_axis=cut_axis,
                cut_position=cut_position,
                proportional_center=proportional_center,
                proportional_radius=proportional_radius,
                proportional_falloff=proportional_falloff,
            )
            if before_counts == after_counts and details.get("skipped"):
                skipped.append({"object": obj.name, "reason": details["skipped"]})
                continue
            if before_counts == after_counts and operation in {"merge_by_distance", "dissolve_degenerate"}:
                skipped.append({"object": obj.name, "reason": "no topology changed"})
                continue
            if transaction is None:
                pending = live_preview.current_transaction()
                had_pending = bool(pending and pending.get("status") == "pending")
                transaction = live_preview.begin(label, context)
                opened_transaction = not had_pending
            live_preview._record_mesh_data_snapshot(obj)
            bm.to_mesh(mesh)
            mesh.update()
            changed.append(
                {
                    "object": obj.name,
                    "operation": operation,
                    "before": before_mesh_counts,
                    "after": _mesh_topology_counts(mesh),
                    "details": details,
                }
            )
        except Exception as exc:
            skipped.append({"object": obj.name, "reason": f"{type(exc).__name__}: {exc}"})
        finally:
            bm.free()

    if not changed:
        if opened_transaction and transaction and transaction.get("status") == "pending":
            live_preview.revert(context)
        return {
            "ok": False,
            "message": f"No mesh topology changed for {operation}",
            "operation": operation,
            "objects": [],
            "skipped": skipped,
            "missing_object_names": missing,
        }

    transaction["applied_steps"].append({"type": "edit_mesh", "label": label, "operation": operation, "objects": changed})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Applied {operation} to {len(changed)} mesh object(s)",
        "operation": operation,
        "objects": changed,
        "skipped": skipped,
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }

def curve_to_mesh(
    context,
    *,
    object_names=None,
    selected_only=True,
    name_prefix="Agent Bridge Mesh ",
    hide_original=False,
    label="Convert curve to mesh",
):
    objects, missing = _resolve_edit_objects(context, object_names=object_names, selected_only=selected_only, max_objects=32)
    curves = [obj for obj in objects if obj.type in {"CURVE", "FONT"}]
    if not curves:
        return {"ok": False, "message": "No curve or text objects found for curve_to_mesh", "missing_object_names": missing}

    depsgraph = context.evaluated_depsgraph_get()
    transaction = None
    opened_transaction = False
    created = []
    skipped = []
    prefix = str(name_prefix or "Agent Bridge Mesh ")
    for obj in curves:
        mesh = None
        mesh_obj = None
        recorded_ids = []
        try:
            if transaction is None:
                pending = live_preview.current_transaction()
                had_pending = bool(pending and pending.get("status") == "pending")
                transaction = live_preview.begin(label, context)
                opened_transaction = not had_pending
            evaluated = obj.evaluated_get(depsgraph)
            mesh = bpy.data.meshes.new_from_object(evaluated, depsgraph=depsgraph)
            mesh.name = f"{prefix}{obj.name} Mesh"
            mesh_obj = bpy.data.objects.new(f"{prefix}{obj.name}", mesh)
            mesh_obj.matrix_world = obj.matrix_world.copy()
            live_preview._record_created_id("object", mesh_obj.name)
            recorded_ids.append(("object", mesh_obj.name))
            live_preview._record_created_id("mesh", mesh.name)
            recorded_ids.append(("mesh", mesh.name))
            _link_object_like_source(context, obj, mesh_obj)
            if hide_original:
                live_preview._record_object_visibility(obj)
                obj.hide_set(True)
                obj.hide_viewport = True
                obj.hide_render = True
            created.append({"source": obj.name, "object": mesh_obj.name, "mesh": mesh.name})
        except Exception as exc:
            if mesh_obj and bpy.data.objects.get(mesh_obj.name):
                bpy.data.objects.remove(mesh_obj, do_unlink=True)
            if mesh and bpy.data.meshes.get(mesh.name) and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
            for kind, name in recorded_ids:
                _forget_recorded_created_id(transaction, kind, name)
            skipped.append({"object": obj.name, "reason": f"{type(exc).__name__}: {exc}"})

    if not created:
        if opened_transaction and transaction and transaction.get("status") == "pending":
            live_preview.revert(context)
        return {
            "ok": False,
            "message": "No mesh objects were created from curves",
            "created": [],
            "skipped": skipped,
            "missing_object_names": missing,
        }

    transaction["applied_steps"].append({"type": "curve_to_mesh", "label": label, "created": created})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Converted {len(created)} curve/text object(s) to mesh copies",
        "created": created,
        "skipped": skipped,
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }

def _normalize_boolean_operation(operation):
    normalized = str(operation or "DIFFERENCE").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "SUBTRACT": "DIFFERENCE",
        "CUT": "DIFFERENCE",
        "JOIN": "UNION",
        "ADD": "UNION",
        "COMMON": "INTERSECT",
        "INTERSECTION": "INTERSECT",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in {"DIFFERENCE", "UNION", "INTERSECT"} else "DIFFERENCE"

def _normalize_boolean_solver(solver):
    normalized = str(solver or "FAST").strip().upper()
    return normalized if normalized in {"FAST", "FLOAT", "EXACT", "MANIFOLD"} else "FAST"

def _set_boolean_solver(modifier, solver):
    if not hasattr(modifier, "solver"):
        return ""
    solver = _normalize_boolean_solver(solver)
    candidates = [solver]
    if solver == "FAST":
        candidates.extend(["FLOAT", "EXACT"])
    elif solver == "FLOAT":
        candidates.extend(["FAST", "EXACT"])
    elif solver == "MANIFOLD":
        candidates.append("EXACT")
    for candidate in dict.fromkeys(candidates):
        try:
            modifier.solver = candidate
            return str(modifier.solver)
        except (TypeError, ValueError):
            continue
    return str(getattr(modifier, "solver", ""))

def boolean_op(
    context,
    *,
    target_object_name="",
    cutter_object_names=None,
    operation="DIFFERENCE",
    solver="FAST",
    name_prefix="Agent Bridge Boolean",
    label="Apply boolean operation",
):
    """Add non-destructive Boolean modifiers to a target mesh."""

    target_name = str(target_object_name or "").strip()
    target = bpy.data.objects.get(target_name) if target_name else getattr(context, "active_object", None)
    if not target or target.type != "MESH":
        return {"ok": False, "message": "Boolean operation needs a mesh target object", "target_object_name": target_name}

    missing = []
    cutters = []
    for name in [str(item).strip() for item in cutter_object_names or [] if str(item).strip()]:
        cutter = bpy.data.objects.get(name)
        if not cutter:
            missing.append(name)
        elif cutter.type == "MESH" and cutter != target:
            cutters.append(cutter)
    if not cutters and not cutter_object_names:
        cutters = _selected_meshes_except(context, target)
    cutters = cutters[:32]
    if not cutters:
        return {
            "ok": False,
            "message": "Boolean operation needs at least one mesh cutter object",
            "target": target.name,
            "missing_object_names": missing,
        }

    operation = _normalize_boolean_operation(operation)
    solver = _normalize_boolean_solver(solver)
    prefix = str(name_prefix or "Agent Bridge Boolean")
    transaction = live_preview.begin(label, context)
    modifiers = []
    applied_solver = solver
    for cutter in cutters:
        modifier = target.modifiers.new(f"{prefix} {operation.title()} {cutter.name}", "BOOLEAN")
        live_preview._record_created_modifier(target, modifier)
        if hasattr(modifier, "operand_type"):
            modifier.operand_type = "OBJECT"
        modifier.operation = operation
        modifier.object = cutter
        applied_solver = _set_boolean_solver(modifier, solver) or solver
        modifiers.append({"name": modifier.name, "cutter": cutter.name})

    transaction["applied_steps"].append(
        {
            "type": "boolean_op",
            "label": label,
            "target": target.name,
            "cutters": [cutter.name for cutter in cutters],
            "operation": operation,
            "solver": applied_solver,
            "modifiers": [item["name"] for item in modifiers],
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Added {len(modifiers)} {operation.lower()} Boolean modifier(s) to {target.name}",
        "target": target.name,
        "cutters": [cutter.name for cutter in cutters],
        "operation": operation,
        "solver": applied_solver,
        "modifiers": modifiers,
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }

def mirror_model(
    context,
    *,
    object_names=None,
    selected_only=True,
    use_axis=(True, False, False),
    mirror_object_name="",
    bisect_axis=(False, False, False),
    flip_axis=(False, False, False),
    use_clip=False,
    use_mirror_merge=True,
    merge_threshold=0.001,
    name="Agent Bridge Mirror",
    label="Mirror model",
):
    objects, missing = _resolve_edit_objects(context, object_names=object_names, selected_only=selected_only)
    meshes = [obj for obj in objects if obj.type == "MESH"]
    if not meshes:
        return {"ok": False, "message": "No mesh objects found for mirror model", "missing_object_names": missing}

    axis = _coerce_bool_triplet(use_axis, (True, False, False))
    if not any(axis):
        axis = (True, False, False)
    bisect = _coerce_bool_triplet(bisect_axis, (False, False, False))
    flip = _coerce_bool_triplet(flip_axis, (False, False, False))
    mirror_object = None
    mirror_object_name = str(mirror_object_name or "").strip()
    if mirror_object_name:
        mirror_object = bpy.data.objects.get(mirror_object_name)
        if mirror_object is None:
            return {"ok": False, "message": f"Mirror object not found: {mirror_object_name}", "missing_object_names": missing + [mirror_object_name]}

    transaction = live_preview.begin(label, context)
    changed = []
    for obj in meshes:
        modifier = obj.modifiers.new(str(name or "Agent Bridge Mirror"), "MIRROR")
        live_preview._record_created_modifier(obj, modifier)
        modifier.use_axis = axis
        modifier.use_bisect_axis = bisect
        modifier.use_bisect_flip_axis = flip
        modifier.use_clip = bool(use_clip)
        modifier.use_mirror_merge = bool(use_mirror_merge)
        modifier.merge_threshold = _clamped_float(merge_threshold, 0.001, 0.0, 10.0)
        if mirror_object is not None:
            modifier.mirror_object = mirror_object
        changed.append({"object": obj.name, "modifier": modifier.name})

    transaction["applied_steps"].append(
        {
            "type": "mirror_model",
            "label": label,
            "objects": changed,
            "axis": _axis_names_from_triplet(axis),
            "mirror_object": mirror_object.name if mirror_object else "",
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Added Mirror modifier to {len(changed)} mesh object(s)",
        "objects": changed,
        "axis": _axis_names_from_triplet(axis),
        "mirror_object": mirror_object.name if mirror_object else "",
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }

def symmetrize_model(
    context,
    *,
    object_names=None,
    selected_only=True,
    axis="X",
    direction="POSITIVE_TO_NEGATIVE",
    merge_threshold=0.001,
    name="Agent Bridge Symmetry",
    label="Symmetrize model",
):
    objects, missing = _resolve_edit_objects(context, object_names=object_names, selected_only=selected_only)
    meshes = [obj for obj in objects if obj.type == "MESH"]
    if not meshes:
        return {"ok": False, "message": "No mesh objects found for symmetrize model", "missing_object_names": missing}

    axis_index, axis_name = _axis_index(axis)
    normalized_direction = str(direction or "POSITIVE_TO_NEGATIVE").strip().upper().replace("-", "_").replace(" ", "_")
    direction_aliases = {
        "+TO-": "POSITIVE_TO_NEGATIVE",
        "POSITIVE_TO_NEGATIVE": "POSITIVE_TO_NEGATIVE",
        "POSITIVE_TO_NEG": "POSITIVE_TO_NEGATIVE",
        "POS_TO_NEG": "POSITIVE_TO_NEGATIVE",
        "-TO+": "NEGATIVE_TO_POSITIVE",
        "NEGATIVE_TO_POSITIVE": "NEGATIVE_TO_POSITIVE",
        "NEGATIVE_TO_POS": "NEGATIVE_TO_POSITIVE",
        "NEG_TO_POS": "NEGATIVE_TO_POSITIVE",
    }
    normalized_direction = direction_aliases.get(normalized_direction, normalized_direction)
    if normalized_direction not in {"POSITIVE_TO_NEGATIVE", "NEGATIVE_TO_POSITIVE"}:
        normalized_direction = "POSITIVE_TO_NEGATIVE"

    use_axis = [False, False, False]
    use_axis[axis_index] = True
    bisect_axis = [False, False, False]
    bisect_axis[axis_index] = True
    flip_axis = [False, False, False]
    flip_axis[axis_index] = normalized_direction == "NEGATIVE_TO_POSITIVE"
    threshold = _clamped_float(merge_threshold, 0.001, 0.0, 10.0)

    transaction = live_preview.begin(label, context)
    changed = []
    for obj in meshes:
        modifier = obj.modifiers.new(str(name or "Agent Bridge Symmetry"), "MIRROR")
        live_preview._record_created_modifier(obj, modifier)
        modifier.use_axis = tuple(use_axis)
        modifier.use_bisect_axis = tuple(bisect_axis)
        modifier.use_bisect_flip_axis = tuple(flip_axis)
        modifier.use_clip = True
        modifier.use_mirror_merge = True
        modifier.merge_threshold = threshold
        changed.append({"object": obj.name, "modifier": modifier.name})

    transaction["applied_steps"].append(
        {
            "type": "symmetrize_model",
            "label": label,
            "objects": changed,
            "axis": axis_name,
            "direction": normalized_direction,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Added symmetry Mirror modifier to {len(changed)} mesh object(s)",
        "objects": changed,
        "axis": axis_name,
        "direction": normalized_direction,
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }

def solidify_model(
    context,
    *,
    object_names=None,
    selected_only=True,
    thickness=0.1,
    offset=0.0,
    use_even_offset=True,
    name="Agent Bridge Solidify",
    label="Solidify model",
):
    objects, missing = _resolve_edit_objects(context, object_names=object_names, selected_only=selected_only)
    meshes = [obj for obj in objects if obj.type == "MESH"]
    if not meshes:
        return {"ok": False, "message": "No mesh objects found for solidify model", "missing_object_names": missing}

    thickness = _clamped_float(thickness, 0.1, -10.0, 10.0)
    offset = _clamped_float(offset, 0.0, -1.0, 1.0)
    transaction = live_preview.begin(label, context)
    changed = []
    for obj in meshes:
        modifier = obj.modifiers.new(str(name or "Agent Bridge Solidify"), "SOLIDIFY")
        live_preview._record_created_modifier(obj, modifier)
        modifier.thickness = thickness
        modifier.offset = offset
        if hasattr(modifier, "use_even_offset"):
            modifier.use_even_offset = bool(use_even_offset)
        changed.append({"object": obj.name, "modifier": modifier.name})

    transaction["applied_steps"].append(
        {
            "type": "solidify_model",
            "label": label,
            "objects": changed,
            "thickness": thickness,
            "offset": offset,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Added Solidify modifier to {len(changed)} mesh object(s)",
        "objects": changed,
        "thickness": thickness,
        "offset": offset,
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }

def screw_model(
    context,
    *,
    object_names=None,
    selected_only=True,
    axis="Z",
    angle=math.tau,
    screw_offset=0.0,
    iterations=1,
    steps=16,
    render_steps=32,
    use_merge_vertices=False,
    merge_threshold=0.001,
    use_smooth_shade=True,
    name="Agent Bridge Screw",
    label="Screw model",
):
    objects, missing = _resolve_edit_objects(context, object_names=object_names, selected_only=selected_only)
    meshes = [obj for obj in objects if obj.type == "MESH"]
    if not meshes:
        return {"ok": False, "message": "No mesh objects found for screw model", "missing_object_names": missing}

    _axis_index_value, axis_name = _axis_index(axis)
    angle = _clamped_float(angle, math.tau, -math.tau * 32.0, math.tau * 32.0)
    screw_offset = _clamped_float(screw_offset, 0.0, -1000.0, 1000.0)
    iterations = _clamped_int(iterations, 1, 1, 256)
    steps = _clamped_int(steps, 16, 1, 512)
    render_steps = _clamped_int(render_steps, max(steps, 16), 1, 1024)
    merge_threshold = _clamped_float(merge_threshold, 0.001, 0.0, 10.0)
    transaction = live_preview.begin(label, context)
    changed = []
    for obj in meshes:
        modifier = obj.modifiers.new(str(name or "Agent Bridge Screw"), "SCREW")
        live_preview._record_created_modifier(obj, modifier)
        modifier.axis = axis_name
        modifier.angle = angle
        modifier.screw_offset = screw_offset
        modifier.iterations = iterations
        modifier.steps = steps
        modifier.render_steps = render_steps
        if hasattr(modifier, "use_merge_vertices"):
            modifier.use_merge_vertices = bool(use_merge_vertices)
        if hasattr(modifier, "merge_threshold"):
            modifier.merge_threshold = merge_threshold
        if hasattr(modifier, "use_smooth_shade"):
            modifier.use_smooth_shade = bool(use_smooth_shade)
        changed.append({"object": obj.name, "modifier": modifier.name})

    transaction["applied_steps"].append(
        {
            "type": "screw_model",
            "label": label,
            "objects": changed,
            "axis": axis_name,
            "angle": angle,
            "screw_offset": screw_offset,
            "iterations": iterations,
            "steps": steps,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Added Screw modifier to {len(changed)} mesh object(s)",
        "objects": changed,
        "axis": axis_name,
        "angle": angle,
        "screw_offset": screw_offset,
        "iterations": iterations,
        "steps": steps,
        "render_steps": render_steps,
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }





def register():

    pass





def unregister():

    pass
