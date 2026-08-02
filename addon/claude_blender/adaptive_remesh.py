"""Preview-safe adaptive mesh refinement for sculpt-ready topology."""

from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import live_preview, sculpt_fields, semantic_sculpt


MAX_SELECTED_EDGES_PER_PASS = 100_000


def _edge_curvature(edge):
    if len(edge.link_faces) < 2:
        return 1.0
    normals = [face.normal.normalized() for face in list(edge.link_faces)[:2]]
    cosine = max(-1.0, min(1.0, float(normals[0].dot(normals[1]))))
    return math.acos(cosine) / math.pi


def _edge_target_length(
    base_length,
    *,
    region_weight,
    curvature,
    region_detail,
    curvature_detail,
):
    reduction = (
        max(0.0, min(1.0, float(region_detail)))
        * max(0.0, min(1.0, float(region_weight)))
        * 0.75
        + max(0.0, min(1.0, float(curvature_detail)))
        * max(0.0, min(1.0, float(curvature)))
        * 0.5
    )
    return max(float(base_length) * 0.1, float(base_length) * (1.0 - reduction))


def _source_bvh(obj):
    points = [Vector(vertex.co) for vertex in obj.data.vertices]
    faces = [tuple(int(index) for index in polygon.vertices) for polygon in obj.data.polygons]
    if not points or not faces:
        return None
    return BVHTree.FromPolygons(points, faces, all_triangles=False)


def _seed_region_layers(bm, obj, attribute_names):
    bm.verts.ensure_lookup_table()
    layers = []
    for attribute_name in attribute_names:
        values = semantic_sculpt._attribute_weights(obj.data, attribute_name)
        if values is None:
            continue
        layer = bm.verts.layers.float.get(attribute_name)
        if layer is None:
            layer = bm.verts.layers.float.new(attribute_name)
        for vertex, value in zip(bm.verts, values):
            vertex[layer] = float(value)
        layers.append(layer)
    return layers


def _vertex_weight(vertex, layers):
    return max((float(vertex[layer]) for layer in layers), default=1.0)


def _select_edges(
    bm,
    layers,
    *,
    target_edge_length,
    region_detail,
    curvature_detail,
    localized,
):
    bm.normal_update()
    bm.edges.ensure_lookup_table()
    bm.edges.index_update()
    candidates = []
    for edge in bm.edges:
        region_weight = max(_vertex_weight(vertex, layers) for vertex in edge.verts)
        if localized and region_weight <= 1.0e-6:
            continue
        if not localized:
            region_weight = 0.0
        curvature = _edge_curvature(edge)
        target = _edge_target_length(
            target_edge_length,
            region_weight=region_weight,
            curvature=curvature,
            region_detail=region_detail,
            curvature_detail=curvature_detail,
        )
        length = edge.calc_length()
        if length > target:
            candidates.append((length / target, edge.index, edge))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in candidates[:MAX_SELECTED_EDGES_PER_PASS]], len(candidates)


def _project_points_to_source(obj, source_bvh):
    if source_bvh is None:
        return 0
    projected = 0
    for vertex in obj.data.vertices:
        nearest = source_bvh.find_nearest(vertex.co)
        if nearest is None or nearest[0] is None:
            continue
        vertex.co = nearest[0]
        projected += 1
    obj.data.update()
    return projected


def adaptive_remesh(
    context,
    *,
    object_name="",
    region_names=None,
    target_edge_length=0.08,
    passes=2,
    region_detail=0.75,
    curvature_detail=0.5,
    relax_iterations=0,
    relax_factor=0.2,
    project_to_source=True,
    max_vertices=250000,
    max_result_vertices=500000,
    label="Adaptive remesh",
):
    """Refine long, weighted, or curved edges while retaining source form."""

    obj, error = semantic_sculpt._resolve_mesh_object(context, object_name)
    if error:
        return {"ok": False, "message": error}
    error = semantic_sculpt._validate_mesh_edit(
        obj,
        max_vertices=max_vertices,
    )
    if error:
        return {"ok": False, "message": error, "object": obj.name}
    if not obj.data.polygons:
        return {"ok": False, "message": f"Mesh has no faces: {obj.name}", "object": obj.name}
    names = [str(name).strip() for name in list(region_names or []) if str(name).strip()]
    attribute_names, missing = semantic_sculpt.semantic_region_attributes(obj.data, names)
    if missing:
        return {
            "ok": False,
            "message": "Semantic region(s) not found: " + ", ".join(missing),
            "object": obj.name,
            "missing_regions": missing,
        }
    target_edge_length = max(1.0e-6, float(target_edge_length))
    passes = max(1, min(6, int(passes)))
    max_result_vertices = int(max_result_vertices)
    if max_result_vertices < len(obj.data.vertices):
        return {
            "ok": False,
            "message": (
                f"max_result_vertices={max_result_vertices} is below the current "
                f"vertex count {len(obj.data.vertices)}"
            ),
            "object": obj.name,
        }
    source_bvh = _source_bvh(obj) if project_to_source or relax_iterations else None
    before = {
        "vertices": len(obj.data.vertices),
        "edges": len(obj.data.edges),
        "faces": len(obj.data.polygons),
    }

    operation = live_preview.begin_isolated(label, context)
    transaction = operation["transaction"]
    bm = bmesh.new()
    pass_reports = []
    try:
        live_preview._record_mesh_data_snapshot(obj)
        bm.from_mesh(obj.data)
        layers = _seed_region_layers(bm, obj, attribute_names)
        for pass_index in range(passes):
            selected, candidate_count = _select_edges(
                bm,
                layers,
                target_edge_length=target_edge_length,
                region_detail=region_detail,
                curvature_detail=curvature_detail,
                localized=bool(names),
            )
            if not selected:
                pass_reports.append(
                    {
                        "pass": pass_index + 1,
                        "candidate_edges": 0,
                        "subdivided_edges": 0,
                        "vertex_count": len(bm.verts),
                    }
                )
                break
            predicted = len(bm.verts) + len(selected) * 2
            if predicted > max_result_vertices:
                raise ValueError(
                    f"Adaptive remesh pass could exceed max_result_vertices={max_result_vertices}; "
                    f"predicted upper bound is {predicted}"
                )
            bmesh.ops.subdivide_edges(
                bm,
                edges=selected,
                cuts=1,
                use_grid_fill=True,
                smooth=0.0,
            )
            if len(bm.verts) > max_result_vertices:
                raise ValueError(
                    f"Adaptive remesh produced {len(bm.verts)} vertices; limit is {max_result_vertices}"
                )
            pass_reports.append(
                {
                    "pass": pass_index + 1,
                    "candidate_edges": candidate_count,
                    "subdivided_edges": len(selected),
                    "vertex_count": len(bm.verts),
                }
            )
        bm.to_mesh(obj.data)
        obj.data.update(calc_edges=True)
        projected_count = 0
        if relax_iterations:
            points = semantic_sculpt._local_points(obj)
            faces = semantic_sculpt._mesh_faces(obj)
            neighbors = semantic_sculpt._mesh_neighbors(obj)
            weights, _missing, _error = semantic_sculpt._region_weights(
                obj,
                names,
                allow_all_vertices=not names,
            )
            relaxed = sculpt_fields.tangent_relax_points(
                points,
                faces,
                neighbors,
                weights,
                factor=max(0.0, min(1.0, float(relax_factor))),
                iterations=max(1, min(20, int(relax_iterations))),
                feature_preservation=0.5,
            )
            semantic_sculpt._write_points(obj, relaxed)
        if project_to_source:
            projected_count = _project_points_to_source(obj, source_bvh)
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        after = {
            "vertices": len(obj.data.vertices),
            "edges": len(obj.data.edges),
            "faces": len(obj.data.polygons),
        }
        if after["vertices"] == before["vertices"]:
            raise ValueError(
                "No edges exceeded the adaptive target; increase target detail or use a shorter target_edge_length"
            )
        transaction["applied_steps"].append(
            {
                "type": "adaptive_remesh",
                "label": label,
                "object": obj.name,
                "regions": names,
                "before": before,
                "after": after,
            }
        )
        transaction = live_preview.finish_isolated(operation)
        live_preview.redraw(context)
        live_preview._mark_pending(context, label)
        return {
            "ok": True,
            "message": f"Adaptively refined {obj.name} from {before['vertices']} to {after['vertices']} vertices",
            "object": obj.name,
            "regions": names,
            "before": before,
            "after": after,
            "passes": pass_reports,
            "projected_vertex_count": projected_count,
            "semantic_regions_retained": sorted(semantic_sculpt._valid_metadata(obj.data)),
            "transaction_id": transaction["id"],
        }
    except Exception as exc:
        live_preview.abort_isolated(operation, context)
        return {
            "ok": False,
            "code": "adaptive_remesh_failed",
            "message": f"Adaptive remesh failed: {type(exc).__name__}: {exc}",
            "object": obj.name,
        }
    finally:
        bm.free()


def register():
    pass


def unregister():
    pass
