"""Blender adapters for persistent, preview-safe implicit shape programs."""

from __future__ import annotations

import json

import bpy

from . import live_preview, shape_program, shape_program_adaptive
from .advanced_support import _material_for_color


PROGRAM_FLAG_PROP = "agent_shape_program"
PROGRAM_JSON_PROP = "agent_shape_program_json"
PROGRAM_DIGEST_PROP = "agent_shape_program_digest"
PROGRAM_COMPILE_PROP = "agent_shape_program_compile_json"
_PROGRAM_PROPERTIES = (
    PROGRAM_FLAG_PROP,
    PROGRAM_JSON_PROP,
    PROGRAM_DIGEST_PROP,
    PROGRAM_COMPILE_PROP,
)


def _safe_label(value, fallback):
    result = " ".join(str(value or "").strip().split())
    return result[:120] or fallback


def _unique_material_name(base):
    base = _safe_label(base, "Implicit Shape Material")
    if bpy.data.materials.get(base) is None:
        return base
    index = 2
    while bpy.data.materials.get(f"{base} {index}") is not None:
        index += 1
    return f"{base} {index}"


def _set_program_metadata(obj, result):
    obj[PROGRAM_FLAG_PROP] = True
    obj[PROGRAM_JSON_PROP] = shape_program.canonical_program_json(result["program"])
    obj[PROGRAM_DIGEST_PROP] = result["stats"]["digest"]
    obj[PROGRAM_COMPILE_PROP] = json.dumps(
        result["stats"], sort_keys=True, ensure_ascii=True, separators=(",", ":")
    )


def _record_program_metadata(obj):
    for property_name in _PROGRAM_PROPERTIES:
        live_preview._record_id_property("object", obj.name, property_name)


def _write_mesh(mesh, result):
    mesh.clear_geometry()
    mesh.from_pydata(result["vertices"], [], result["faces"])
    corrected = mesh.validate(verbose=False)
    if corrected and result["stats"].get("meshing_mode") == "adaptive_dual":
        raise shape_program.ShapeProgramError(
            "Blender found invalid adaptive mesh geometry; increase base depth "
            "or use uniform meshing"
        )
    mesh.update(calc_edges=True)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    result["stats"]["vertex_count"] = len(mesh.vertices)
    result["stats"]["face_count"] = len(mesh.polygons)


def _select_object(context, obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj


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


def _mesh_program(
    program,
    *,
    meshing_mode,
    resolution,
    iso_level,
    smooth_iterations,
    adaptive_base_depth,
    adaptive_max_depth,
    adaptive_error_threshold,
    refinement_regions,
):
    mode = str(meshing_mode or "uniform").strip().lower()
    if mode == "uniform":
        if refinement_regions:
            raise shape_program.ShapeProgramError(
                "refinement_regions require meshing_mode='adaptive_dual'"
            )
        return shape_program.mesh_shape_program(
            program,
            resolution=resolution,
            iso_level=iso_level,
            smooth_iterations=smooth_iterations,
        )
    if mode == "adaptive_dual":
        return shape_program_adaptive.mesh_shape_program_adaptive(
            program,
            base_depth=adaptive_base_depth,
            max_depth=adaptive_max_depth,
            error_threshold=adaptive_error_threshold,
            refinement_regions=refinement_regions,
            iso_level=iso_level,
            smooth_iterations=smooth_iterations,
        )
    raise shape_program.ShapeProgramError(
        "meshing_mode must be 'uniform' or 'adaptive_dual'"
    )


def compile_shape_program(
    context,
    *,
    program,
    object_name="Implicit Shape",
    meshing_mode="uniform",
    resolution=48,
    iso_level=0.0,
    smooth_iterations=1,
    adaptive_base_depth=5,
    adaptive_max_depth=7,
    adaptive_error_threshold=0.05,
    refinement_regions=None,
    material_name="",
    color=(0.56, 0.62, 0.72, 1.0),
    label="Compile shape program",
):
    """Compile a new persistent shape-program object as a live preview."""

    try:
        result = _mesh_program(
            program,
            meshing_mode=meshing_mode,
            resolution=resolution,
            iso_level=iso_level,
            smooth_iterations=smooth_iterations,
            adaptive_base_depth=adaptive_base_depth,
            adaptive_max_depth=adaptive_max_depth,
            adaptive_error_threshold=adaptive_error_threshold,
            refinement_regions=refinement_regions,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        return {
            "ok": False,
            "code": "invalid_shape_program",
            "message": str(exc),
        }

    operation = live_preview.begin_isolated(label, context)
    transaction = operation["transaction"]
    mesh = None
    obj = None
    material = None
    material_was_created = False
    try:
        name = _safe_label(object_name, result["program"]["name"])
        mesh = bpy.data.meshes.new(f"{name} Mesh")
        live_preview._record_created_id("mesh", mesh.name)
        _write_mesh(mesh, result)
        obj = bpy.data.objects.new(name, mesh)
        live_preview._record_created_id("object", obj.name)
        (context.collection or context.scene.collection).objects.link(obj)
        resolved_material_name = (
            _safe_label(material_name, "")
            or _unique_material_name(f"{obj.name} Material")
        )
        material = bpy.data.materials.get(resolved_material_name)
        material_was_created = material is None
        if material is None:
            material = _material_for_color(resolved_material_name, color)
        obj.data.materials.append(material)
        _set_program_metadata(obj, result)
        _select_object(context, obj)
        created_data = [
            {"kind": "object", "name": obj.name},
            {"kind": "mesh", "name": mesh.name},
        ]
        if material_was_created:
            created_data.append({"kind": "material", "name": material.name})
        transaction["applied_steps"].append(
            {
                "type": "compile_shape_program",
                "label": label,
                "object": obj.name,
                "digest": result["stats"]["digest"],
                "created_data": created_data,
            }
        )
        transaction = live_preview.finish_isolated(operation)
        live_preview.redraw(context)
        live_preview._mark_pending(context, label)
        return {
            "ok": True,
            "message": (
                f"Compiled {result['program']['name']} as {obj.name} with "
                f"{result['stats']['vertex_count']} vertices"
            ),
            "object": obj.name,
            "program": shape_program.shape_program_summary(result["program"]),
            "stats": result["stats"],
            "transaction_id": transaction["id"],
        }
    except Exception as exc:
        live_preview.abort_isolated(operation, context)
        _cleanup_created(
            obj,
            mesh,
            material if material_was_created else None,
        )
        return {
            "ok": False,
            "code": "shape_program_compile_failed",
            "message": f"Shape-program compile failed: {type(exc).__name__}: {exc}",
        }


def inspect_shape_program(context, *, object_name, include_program=True):
    """Read and validate the persistent program attached to one mesh object."""

    obj = bpy.data.objects.get(str(object_name or ""))
    if obj is None:
        return {"ok": False, "message": f"Object not found: {object_name}"}
    if obj.type != "MESH" or not bool(obj.get(PROGRAM_FLAG_PROP)):
        return {
            "ok": False,
            "message": f"Object is not a compiled shape-program mesh: {obj.name}",
            "object": obj.name,
        }
    try:
        program = json.loads(str(obj.get(PROGRAM_JSON_PROP) or ""))
        summary = shape_program.shape_program_summary(program)
        compile_stats = json.loads(str(obj.get(PROGRAM_COMPILE_PROP) or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "code": "shape_program_metadata_invalid",
            "message": f"Stored shape program is invalid: {exc}",
            "object": obj.name,
        }
    stored_digest = str(obj.get(PROGRAM_DIGEST_PROP) or "")
    warnings = []
    if stored_digest != summary["digest"]:
        warnings.append(
            "Stored shape-program digest does not match its canonical program"
        )
    response = {
        "ok": True,
        "message": f"Inspected shape program on {obj.name}",
        "object": obj.name,
        "mesh": {
            "vertices": len(obj.data.vertices),
            "edges": len(obj.data.edges),
            "faces": len(obj.data.polygons),
        },
        "program_summary": summary,
        "compile_stats": compile_stats,
        "warnings": warnings,
    }
    if include_program:
        response["program"] = shape_program.normalize_shape_program(program)
    return response


def update_shape_program(
    context,
    *,
    object_name,
    program,
    meshing_mode="uniform",
    resolution=48,
    iso_level=0.0,
    smooth_iterations=1,
    adaptive_base_depth=5,
    adaptive_max_depth=7,
    adaptive_error_threshold=0.05,
    refinement_regions=None,
    label="Update shape program",
):
    """Recompile an existing shape-program mesh with full preview rollback."""

    obj = bpy.data.objects.get(str(object_name or ""))
    if obj is None:
        return {"ok": False, "message": f"Object not found: {object_name}"}
    if obj.type != "MESH" or not bool(obj.get(PROGRAM_FLAG_PROP)):
        return {
            "ok": False,
            "message": f"Object is not a compiled shape-program mesh: {obj.name}",
            "object": obj.name,
        }
    if obj.mode != "OBJECT":
        return {
            "ok": False,
            "message": f"Shape-program updates require Object Mode: {obj.name} is in {obj.mode} mode",
            "object": obj.name,
        }
    linked_objects = [
        candidate.name
        for candidate in bpy.data.objects
        if candidate.type == "MESH" and candidate.data is obj.data
    ]
    if len(linked_objects) > 1:
        return {
            "ok": False,
            "message": (
                f"Mesh data is shared by {len(linked_objects)} objects: {obj.data.name}. "
                "Make the shape-program mesh single-user before updating it."
            ),
            "object": obj.name,
        }
    if getattr(obj.data, "shape_keys", None) is not None:
        return {
            "ok": False,
            "message": "Shape-program updates require a mesh without shape keys",
            "object": obj.name,
        }
    try:
        result = _mesh_program(
            program,
            meshing_mode=meshing_mode,
            resolution=resolution,
            iso_level=iso_level,
            smooth_iterations=smooth_iterations,
            adaptive_base_depth=adaptive_base_depth,
            adaptive_max_depth=adaptive_max_depth,
            adaptive_error_threshold=adaptive_error_threshold,
            refinement_regions=refinement_regions,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        return {
            "ok": False,
            "code": "invalid_shape_program",
            "message": str(exc),
            "object": obj.name,
        }

    previous_digest = str(obj.get(PROGRAM_DIGEST_PROP) or "")
    cleared_groups = [group.name for group in obj.vertex_groups]
    operation = live_preview.begin_isolated(label, context)
    transaction = operation["transaction"]
    try:
        live_preview._record_mesh_data_snapshot(obj)
        live_preview._record_object_vertex_groups(obj)
        _record_program_metadata(obj)
        for group in list(obj.vertex_groups):
            obj.vertex_groups.remove(group)
        _write_mesh(obj.data, result)
        _set_program_metadata(obj, result)
        _select_object(context, obj)
        transaction["applied_steps"].append(
            {
                "type": "update_shape_program",
                "label": label,
                "object": obj.name,
                "previous_digest": previous_digest,
                "digest": result["stats"]["digest"],
            }
        )
        transaction = live_preview.finish_isolated(operation)
        live_preview.redraw(context)
        live_preview._mark_pending(context, label)
        warnings = []
        if cleared_groups:
            warnings.append(
                "Cleared topology-dependent vertex groups: "
                + ", ".join(cleared_groups[:16])
            )
        return {
            "ok": True,
            "message": (
                f"Updated shape program on {obj.name} to "
                f"{result['stats']['vertex_count']} vertices"
            ),
            "object": obj.name,
            "previous_digest": previous_digest,
            "program": shape_program.shape_program_summary(result["program"]),
            "stats": result["stats"],
            "warnings": warnings,
            "transaction_id": transaction["id"],
        }
    except Exception as exc:
        live_preview.abort_isolated(operation, context)
        return {
            "ok": False,
            "code": "shape_program_update_failed",
            "message": f"Shape-program update failed: {type(exc).__name__}: {exc}",
            "object": obj.name,
        }
