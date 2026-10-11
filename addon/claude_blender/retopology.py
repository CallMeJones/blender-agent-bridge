"""Bounded mesh inspection, working-copy cleanup and sampled form comparison."""
from __future__ import annotations

import math
import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from . import live_preview

MAX_VERTICES = 1_000_000
MAX_FACES = 2_000_000
MAX_OBJECTS = 8


def resolve_objects(context, object_names=None):
    names = list(dict.fromkeys(object_names or []))
    objects = [context.scene.objects.get(name) for name in names] if names else list(context.selected_objects)
    if not objects or len(objects) > MAX_OBJECTS:
        raise ValueError(f"Select or name between one and {MAX_OBJECTS} mesh objects")
    for obj in objects:
        if obj is None or obj.type != "MESH":
            raise ValueError("Every source must be a mesh in the current scene")
        if obj.mode != "OBJECT":
            raise ValueError(f"Leave Edit/Sculpt mode before processing {obj.name}")
        if any(not math.isfinite(float(value)) for row in obj.matrix_world for value in row):
            raise ValueError(f"Object has a non-finite transform: {obj.name}")
        validate_mesh(obj.data)
    return objects


def validate_mesh(mesh):
    if not mesh.vertices or not mesh.polygons:
        raise ValueError("A nonempty surface mesh is required")
    if len(mesh.vertices) > MAX_VERTICES or len(mesh.polygons) > MAX_FACES:
        raise ValueError(f"Mesh exceeds {MAX_VERTICES} vertices or {MAX_FACES} faces")
    if any(not math.isfinite(float(c)) for vertex in mesh.vertices for c in vertex.co):
        raise ValueError("Mesh contains non-finite coordinates")


def face_components(bm):
    """Face islands, including islands touching only at a single vertex."""
    remaining = set(bm.faces)
    components = []
    while remaining:
        seed = remaining.pop()
        component, frontier = [seed], [seed]
        while frontier:
            face = frontier.pop()
            for edge in face.edges:
                for neighbor in edge.link_faces:
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        component.append(neighbor)
                        frontier.append(neighbor)
        components.append(component)
    return components


def mesh_report(obj):
    validate_mesh(obj.data)
    mesh = obj.data
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        components = sorted((len(c) for c in face_components(bm)), reverse=True)
        counts = {"triangles": 0, "quads": 0, "ngons": 0}
        for face in bm.faces:
            counts["triangles" if len(face.verts) == 3 else "quads" if len(face.verts) == 4 else "ngons"] += 1
        geometry = {
            "vertices": len(bm.verts), "faces": len(bm.faces), "edges": len(bm.edges),
            **counts, "triangle_equivalent": sum(max(0, len(f.verts) - 2) for f in bm.faces),
            "quad_fraction": counts["quads"] / len(bm.faces),
            "boundary_edges": sum(len(e.link_faces) == 1 for e in bm.edges),
            "nonmanifold_edges": sum(len(e.link_faces) > 2 for e in bm.edges),
            "wire_edges": sum(not e.link_faces for e in bm.edges),
            "loose_vertices": sum(not v.link_edges for v in bm.verts),
            "degenerate_faces": sum(f.calc_area() <= 1e-14 for f in bm.faces),
            "component_count": len(components), "largest_component_faces": components[0],
            "component_sizes": components[:32],
        }
    finally:
        bm.free()
    materials = []
    for slot in obj.material_slots:
        mat = slot.material
        if not mat:
            continue
        images = [n.image for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image] if mat.node_tree else []
        materials.append({"name": mat.name, "image_count": len(images),
                          "missing_images": [im.name for im in images if not im.has_data and not im.packed_file]})
    warnings = []
    if geometry["boundary_edges"] or geometry["nonmanifold_edges"]:
        warnings.append("Open or nonmanifold geometry may need repair before quad remeshing")
    if geometry["component_count"] > 1:
        warnings.append("Disconnected surface parts are preserved unless removal is explicitly requested")
    if obj.data.shape_keys or any(m.type == "ARMATURE" for m in obj.modifiers):
        warnings.append("Working copies capture the evaluated current pose; existing rig and shape keys are not transferred")
    if not mesh.uv_layers:
        warnings.append("No UV map; texture baking needs an unwrap on the target")
    return {"object": obj.name, "geometry": geometry, "uv_maps": [uv.name for uv in mesh.uv_layers],
            "materials": materials, "modifiers": [m.type for m in obj.modifiers],
            "has_shape_keys": bool(mesh.shape_keys), "warnings": warnings,
            "animation_ready": False, "topology_basis": "base_mesh"}


def inspect_source(context, *, object_names=None):
    objects = resolve_objects(context, object_names)
    return {"ok": True, "message": "Retopology sources inspected", "sources": [mesh_report(o) for o in objects],
            "next_tool": "prepare_retopology_copy", "animation_ready": False}


def clean_mesh(mesh, *, merge_distance_ratio=0.000001, min_component_faces=0):
    """Conservative cleanup. No hole filling or removal of surface islands by default."""
    validate_mesh(mesh)
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        before = {"vertices": len(bm.verts), "faces": len(bm.faces)}
        points = [v.co for v in bm.verts]
        diagonal = (Vector([max(v[i] for v in points) for i in range(3)]) -
                    Vector([min(v[i] for v in points) for i in range(3)])).length
        distance = diagonal * float(merge_distance_ratio)
        if distance > 0:
            bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=distance)
        bad = [f for f in bm.faces if f.calc_area() <= max(1e-20, diagonal * diagonal * 1e-14)]
        if bad:
            bmesh.ops.delete(bm, geom=bad, context="FACES_ONLY")
        removed_components = 0
        if min_component_faces:
            parts = face_components(bm)
            largest = max(parts, key=len, default=[])
            small = [c for c in parts if c is not largest and len(c) < min_component_faces]
            removed_components = len(small)
            if small:
                bmesh.ops.delete(bm, geom=[f for c in small for f in c], context="FACES_ONLY")
        wires = [e for e in bm.edges if not e.link_faces]
        if wires:
            bmesh.ops.delete(bm, geom=wires, context="EDGES")
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
        if not bm.faces:
            raise ValueError("Cleanup would remove the entire surface")
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
        mesh.update()
        return {"before": before, "after": {"vertices": len(bm.verts), "faces": len(bm.faces)},
                "merge_distance": distance, "removed_components": removed_components}
    finally:
        bm.free()


def static_copy(context, source, name, *, link=True, independent_materials=True, track_preview=False):
    # Direct mesh edits (including UV removal) must reach the evaluated graph.
    source.data.update()
    context.view_layer.update()
    graph = context.evaluated_depsgraph_get()
    evaluated = source.evaluated_get(graph)
    # Check evaluated counts before allocating a persistent copy.
    validate_mesh(evaluated.data)
    mesh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=graph)
    obj, materials = None, []
    try:
        mesh.name = name + " Mesh"
        if track_preview:
            live_preview.record_created_id("mesh", mesh.name)
        obj = bpy.data.objects.new(name, mesh)
        if track_preview:
            live_preview.record_created_id("object", obj.name)
        obj.matrix_world = evaluated.matrix_world.copy()
        for index, slot in enumerate(evaluated.material_slots):
            # Resolve object-linked overrides into the standalone mesh snapshot.
            mesh.materials[index] = slot.material
        if independent_materials:
            for i, material in enumerate(list(mesh.materials)):
                if material:
                    copied = material.copy()
                    materials.append(copied)
                    if track_preview:
                        live_preview.record_created_id("material", copied.name)
                    mesh.materials[i] = copied
        if link:
            context.scene.collection.objects.link(obj)
        return obj
    except Exception:
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)
        for material in materials:
            if material.users == 0:
                bpy.data.materials.remove(material)
        raise


def prepare_copy(context, *, object_names=None, name_suffix="_retopo_work", merge_distance_ratio=0.000001,
                 min_component_faces=0, shade_smooth=True, label="Prepare retopology working copy"):
    objects = resolve_objects(context, object_names)
    transaction = live_preview.begin(label, context)
    results = []
    for source in objects:
        copy = static_copy(context, source, source.name + name_suffix, track_preview=True)
        cleanup = clean_mesh(copy.data, merge_distance_ratio=merge_distance_ratio,
                             min_component_faces=min_component_faces)
        for face in copy.data.polygons:
            face.use_smooth = bool(shade_smooth)
        copy["agent_bridge_retopology_source"] = source.name
        results.append({"source": source.name, "working_copy": copy.name,
                        "cleanup": cleanup, "report": mesh_report(copy)})
    transaction["applied_steps"].append({"type": "retopology_working_copy", "objects": [r["working_copy"] for r in results]})
    live_preview.mark_pending(context, label)
    live_preview.redraw(context)
    return {"ok": True, "message": "Independent retopology working copies prepared", "copies": results,
            "transaction_id": transaction["id"], "next_tool": "start_retopology_job"}


def _world_surface(obj, graph):
    evaluated = obj.evaluated_get(graph)
    validate_mesh(evaluated.data)
    mesh = evaluated.data
    points = [evaluated.matrix_world @ v.co for v in mesh.vertices]
    faces = [tuple(f.vertices) for f in mesh.polygons]
    bvh = BVHTree.FromPolygons(points, faces, all_triangles=False)
    return points, faces, bvh


def _samples(points, faces, budget):
    half = max(1, budget // 2)
    vertices = [points[(i * len(points)) // min(half, len(points))] for i in range(min(half, len(points)))]
    indices = [(i * len(faces)) // min(half, len(faces)) for i in range(min(half, len(faces)))]
    return vertices + [sum((points[j] for j in faces[i]), Vector()) / len(faces[i]) for i in indices]


def evaluate_result(context, *, source_object_name, target_object_name, sample_count=2048,
                    max_deviation_ratio=0.02, intended_use="prop", include_renders=False):
    objects = resolve_objects(context, [source_object_name, target_object_name])
    if len(objects) != 2:
        raise ValueError("Source and target must be distinct objects")
    source, target = objects
    graph = context.evaluated_depsgraph_get()
    a, af, abvh = _world_surface(source, graph)
    b, bf, bbvh = _world_surface(target, graph)
    budget = max(32, min(8192, int(sample_count)))
    distances = []
    for points, faces, bvh in ((a, af, bbvh), (b, bf, abvh)):
        distances.extend(bvh.find_nearest(p)[3] for p in _samples(points, faces, budget))
    distances.sort()
    diagonal = (Vector([max(v[i] for v in a) for i in range(3)]) -
                Vector([min(v[i] for v in a) for i in range(3)])).length
    denominator = max(diagonal, 1e-12)
    report = mesh_report(target)
    findings = list(report["warnings"])
    maximum = max(distances, default=0.0)
    shape_passed = maximum / denominator <= max_deviation_ratio
    if not shape_passed:
        findings.append("Sampled surface deviation exceeds the requested tolerance")
    if intended_use == "character":
        findings.append("Review joint and facial edge loops and test poses before rigging; automatic quads do not prove deformation readiness")
    result = {"ok": True, "message": "Retopology result compared", "source": mesh_report(source), "target": report,
              "comparison": {"sample_count": len(distances), "method": "bidirectional_vertices_and_face_centers",
                             "max_distance": maximum, "mean_distance": sum(distances) / len(distances),
                             "p95_distance": distances[min(len(distances) - 1, int(len(distances) * .95))],
                             "source_diagonal": diagonal, "max_deviation_ratio": maximum / denominator,
                             "tolerance_ratio": max_deviation_ratio, "shape_passed": shape_passed,
                             "face_reduction_ratio": 1 - len(bf) / len(af), "face_count_basis": "evaluated_mesh"},
              "findings": findings, "animation_ready": False,
              "limitations": ["Sampled distances are not an exhaustive Hausdorff distance or self-intersection test"]}
    if include_renders:
        from . import inspection_render, preferences
        capture_dir = getattr(preferences.get_preferences(context), "capture_cache_dir", None)
        result["previews"] = [inspection_render.capture_object_inspection_renders(
            context, object_names=[obj.name], views=["front", "side", "top"], resolution_x=512, resolution_y=512,
            isolate_targets=True, create_contact_sheet=True, capture_dir=capture_dir)
            for obj in (source, target)]
    return result
