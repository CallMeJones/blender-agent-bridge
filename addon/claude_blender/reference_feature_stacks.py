"""Reusable feature stack builders for reference part graphs."""

from __future__ import annotations

import json
import math

import bpy
from mathutils import Vector

from . import live_preview, reference_blockout, reference_part_scene
from .advanced_support import _material_for_color


FEATURE_STACK_METADATA_PROP = "reference_feature_stack_json"


def _safe_label(value, fallback):
    text = " ".join(str(value or "").strip().split())
    keep = [char if char.isalnum() or char in {"_", "-", " "} else "_" for char in text]
    return " ".join("".join(keep).split())[:100] or fallback


def _set_json_prop(data_block, key, value):
    data_block[key] = json.dumps(value, sort_keys=True)


def _as_color(value, fallback):
    try:
        values = list(value or [])[:4]
    except TypeError:
        values = []
    while len(values) < 4:
        values.append(fallback[len(values)])
    try:
        return tuple(max(0.0, min(1.0, float(item))) for item in values[:4])
    except (TypeError, ValueError, OverflowError):
        return tuple(fallback)


def _material(name, color):
    return _material_for_color(_safe_label(name, "Reference Feature Material"), color)


def _vector(value, default=(0.0, 0.0, 0.0)):
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return Vector(default)
    try:
        result = Vector((float(value[0]), float(value[1]), float(value[2])))
    except (TypeError, ValueError, OverflowError):
        return Vector(default)
    if not all(math.isfinite(component) for component in result):
        return Vector(default)
    return result


def _basis(part):
    raw = part.get("basis") if isinstance(part, dict) else None
    defaults = (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )
    axes = []
    for index, default in enumerate(defaults):
        axis = _vector(raw[index], default) if isinstance(raw, list) and len(raw) > index else Vector(default)
        if axis.length <= 1e-9:
            axis = Vector(default)
        axes.append(axis.normalized())
    return tuple(axes)


def _radii(part, fallback=(0.2, 0.12, 0.2)):
    values = _vector(part.get("radii"), fallback)
    return Vector((max(0.0001, abs(values.x)), max(0.0001, abs(values.y)), max(0.0001, abs(values.z))))


def _basis_lists(axes):
    return [list(axis) for axis in axes]


def _part_center(part):
    return _vector(part.get("center"), (0.0, 0.0, 0.0))


def _graph_parts(part_graph_collection_name, *, roles, part_names, max_parts):
    collection, error = reference_part_scene.resolve_part_graph_collection(part_graph_collection_name)
    if error:
        return None, [], error
    graph = reference_part_scene.load_part_graph(collection)
    parts = [part for part in list(graph.get("parts") or []) if isinstance(part, dict)]
    requested = {str(name).strip() for name in part_names or [] if str(name).strip()}
    if requested:
        available = {str(part.get("name") or "") for part in parts}
        missing = sorted(requested - available)
        if missing:
            return collection, [], "Reference part(s) not found: " + ", ".join(missing[:16])
        parts = [part for part in parts if str(part.get("name") or "") in requested]
    role_set = {str(role) for role in roles}
    parts = [part for part in parts if str(part.get("role") or "") in role_set]
    limit = max(1, min(32, int(max_parts or 8)))
    if len(parts) > limit:
        parts = parts[:limit]
    if not parts:
        return collection, [], "No matching reference part(s) found for roles: " + ", ".join(sorted(role_set))
    return collection, parts, ""


def _create_ellipsoid(
    context,
    *,
    name,
    center,
    radii,
    basis,
    material,
    segments,
    rings,
    metadata,
    created_objects,
    created_meshes,
):
    obj = reference_blockout.make_deformed_ellipsoid(
        context,
        name=_safe_label(name, "Reference Feature"),
        center=tuple(center),
        radii=tuple(radii),
        basis=_basis_lists(basis),
        controls=[],
        segments=segments,
        rings=rings,
        collection=context.scene.collection,
        material=material,
    )
    obj["reference_feature_stack"] = True
    obj["reference_feature_role"] = str(metadata.get("feature_role") or "")
    obj["reference_part_name"] = str(metadata.get("part_name") or "")
    _set_json_prop(obj, FEATURE_STACK_METADATA_PROP, metadata)
    created_objects.append(obj)
    created_meshes.append(obj.data)
    return obj


def _create_curve(
    context,
    *,
    name,
    points,
    material,
    bevel_depth,
    metadata,
    created_objects,
):
    curve = bpy.data.curves.new(f"{_safe_label(name, 'Reference Feature Curve')} Data", "CURVE")
    live_preview._record_created_id("curve", curve.name)
    curve.dimensions = "3D"
    curve.bevel_depth = max(0.0, float(bevel_depth))
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, values in zip(spline.points, points):
        point.co = (float(values[0]), float(values[1]), float(values[2]), 1.0)
    if material is not None:
        curve.materials.append(material)
    obj = bpy.data.objects.new(_safe_label(name, "Reference Feature Curve"), curve)
    context.scene.collection.objects.link(obj)
    live_preview._record_created_id("object", obj.name)
    obj["reference_feature_stack"] = True
    obj["reference_feature_role"] = str(metadata.get("feature_role") or "")
    obj["reference_part_name"] = str(metadata.get("part_name") or "")
    _set_json_prop(obj, FEATURE_STACK_METADATA_PROP, metadata)
    created_objects.append(obj)
    return obj


def _finish_stack(context, operation, *, label, stack_kind, graph_collection, parts, result_objects):
    transaction = operation["transaction"]
    bpy.ops.object.select_all(action="DESELECT")
    for obj in result_objects:
        obj.hide_set(False)
        obj.select_set(True)
    context.view_layer.objects.active = result_objects[0]
    transaction["applied_steps"].append(
        {
            "type": stack_kind,
            "label": label,
            "part_graph_collection": graph_collection.name,
            "parts": [str(part.get("name") or "") for part in parts],
            "result_objects": [obj.name for obj in result_objects],
        }
    )
    transaction = live_preview.finish_isolated(operation)
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return transaction


def _cleanup(created_objects, created_meshes):
    created_curves = []
    for obj in reversed(created_objects):
        try:
            if getattr(obj, "type", "") == "CURVE":
                created_curves.append(obj.data)
            if bpy.data.objects.get(obj.name) is obj:
                bpy.data.objects.remove(obj, do_unlink=True)
        except Exception:
            pass
    for mesh in reversed(created_meshes):
        try:
            if bpy.data.meshes.get(mesh.name) is mesh and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        except Exception:
            pass
    for curve in reversed(created_curves):
        try:
            if bpy.data.curves.get(curve.name) is curve and curve.users == 0:
                bpy.data.curves.remove(curve)
        except Exception:
            pass


def create_eye_stack(
    context,
    *,
    part_graph_collection_name="",
    part_names=None,
    name_prefix="Reference Eye Stack",
    iris_color=(0.22, 0.55, 0.78, 1.0),
    sclera_color=(0.96, 0.97, 0.95, 1.0),
    pupil_color=(0.01, 0.01, 0.012, 1.0),
    highlight_color=(1.0, 1.0, 1.0, 1.0),
    scale=1.0,
    protrusion=0.0,
    create_highlight=True,
    segments=32,
    rings=16,
    max_parts=8,
    label="Create eye stack",
):
    graph_collection, parts, error = _graph_parts(
        part_graph_collection_name,
        roles={"eye"},
        part_names=part_names or [],
        max_parts=max_parts,
    )
    if error:
        return {"ok": False, "message": error}
    scale = max(0.05, min(10.0, float(scale or 1.0)))
    protrusion = max(-2.0, min(2.0, float(protrusion or 0.0)))
    operation = live_preview.begin_isolated(label, context)
    created_objects = []
    created_meshes = []
    result_objects = []
    try:
        mats = {
            "sclera": _material(f"{name_prefix} Sclera", _as_color(sclera_color, (0.96, 0.97, 0.95, 1.0))),
            "iris": _material(f"{name_prefix} Iris", _as_color(iris_color, (0.22, 0.55, 0.78, 1.0))),
            "pupil": _material(f"{name_prefix} Pupil", _as_color(pupil_color, (0.01, 0.01, 0.012, 1.0))),
            "highlight": _material(f"{name_prefix} Highlight", _as_color(highlight_color, (1.0, 1.0, 1.0, 1.0))),
        }
        for part in parts:
            center = _part_center(part)
            axes = _basis(part)
            right, depth, up = axes
            front = -depth
            radii = _radii(part, (0.12, 0.06, 0.16)) * scale
            part_name = str(part.get("name") or "eye")
            center = center + front * radii.y * protrusion
            eyeball = _create_ellipsoid(
                context,
                name=f"{name_prefix} {part_name} eyeball",
                center=center,
                radii=radii,
                basis=axes,
                material=mats["sclera"],
                segments=segments,
                rings=rings,
                metadata={"feature_role": "eye_sclera", "part_name": part_name},
                created_objects=created_objects,
                created_meshes=created_meshes,
            )
            iris_center = center + front * (radii.y * 0.96)
            iris = _create_ellipsoid(
                context,
                name=f"{name_prefix} {part_name} iris",
                center=iris_center,
                radii=(radii.x * 0.58, max(0.002, radii.y * 0.08), radii.z * 0.58),
                basis=axes,
                material=mats["iris"],
                segments=segments,
                rings=max(4, rings // 2),
                metadata={"feature_role": "eye_iris", "part_name": part_name},
                created_objects=created_objects,
                created_meshes=created_meshes,
            )
            pupil = _create_ellipsoid(
                context,
                name=f"{name_prefix} {part_name} pupil",
                center=iris_center + front * max(0.002, radii.y * 0.05),
                radii=(radii.x * 0.28, max(0.0015, radii.y * 0.04), radii.z * 0.34),
                basis=axes,
                material=mats["pupil"],
                segments=segments,
                rings=max(4, rings // 2),
                metadata={"feature_role": "eye_pupil", "part_name": part_name},
                created_objects=created_objects,
                created_meshes=created_meshes,
            )
            result_objects.extend([eyeball, iris, pupil])
            if create_highlight:
                highlight = _create_ellipsoid(
                    context,
                    name=f"{name_prefix} {part_name} highlight",
                    center=iris_center + right * radii.x * 0.18 + up * radii.z * 0.22 + front * max(0.003, radii.y * 0.08),
                    radii=(radii.x * 0.12, max(0.0015, radii.y * 0.035), radii.z * 0.14),
                    basis=axes,
                    material=mats["highlight"],
                    segments=max(8, segments // 2),
                    rings=max(4, rings // 2),
                    metadata={"feature_role": "eye_highlight", "part_name": part_name},
                    created_objects=created_objects,
                    created_meshes=created_meshes,
                )
                result_objects.append(highlight)
        transaction = _finish_stack(
            context,
            operation,
            label=label,
            stack_kind="create_eye_stack",
            graph_collection=graph_collection,
            parts=parts,
            result_objects=result_objects,
        )
        return {
            "ok": True,
            "message": f"Created eye stack for {len(parts)} part(s)",
            "part_graph_collection": graph_collection.name,
            "parts": [str(part.get("name") or "") for part in parts],
            "objects": [obj.name for obj in result_objects],
            "transaction_id": transaction["id"],
        }
    except Exception as exc:
        live_preview.abort_isolated(operation, context)
        _cleanup(created_objects, created_meshes)
        return {"ok": False, "message": f"Eye stack failed: {type(exc).__name__}: {exc}"}


def create_muzzle_stack(
    context,
    *,
    part_graph_collection_name="",
    part_names=None,
    name_prefix="Reference Muzzle Stack",
    muzzle_color=(0.9, 0.84, 0.78, 1.0),
    nose_color=(0.86, 0.42, 0.48, 1.0),
    mouth_color=(0.08, 0.035, 0.03, 1.0),
    tongue_color=(0.9, 0.35, 0.42, 1.0),
    scale=1.0,
    create_nose=True,
    create_mouth=True,
    create_tongue=False,
    segments=32,
    rings=16,
    max_parts=8,
    label="Create muzzle stack",
):
    graph_collection, parts, error = _graph_parts(
        part_graph_collection_name,
        roles={"muzzle"},
        part_names=part_names or [],
        max_parts=max_parts,
    )
    if error:
        return {"ok": False, "message": error}
    scale = max(0.05, min(10.0, float(scale or 1.0)))
    operation = live_preview.begin_isolated(label, context)
    created_objects = []
    created_meshes = []
    result_objects = []
    try:
        mats = {
            "muzzle": _material(f"{name_prefix} Muzzle", _as_color(muzzle_color, (0.9, 0.84, 0.78, 1.0))),
            "nose": _material(f"{name_prefix} Nose", _as_color(nose_color, (0.86, 0.42, 0.48, 1.0))),
            "mouth": _material(f"{name_prefix} Mouth", _as_color(mouth_color, (0.08, 0.035, 0.03, 1.0))),
            "tongue": _material(f"{name_prefix} Tongue", _as_color(tongue_color, (0.9, 0.35, 0.42, 1.0))),
        }
        for part in parts:
            center = _part_center(part)
            axes = _basis(part)
            right, depth, up = axes
            front = -depth
            radii = _radii(part, (0.32, 0.16, 0.16)) * scale
            part_name = str(part.get("name") or "muzzle")
            for side, amount in (("left", -0.42), ("right", 0.42)):
                cheek = _create_ellipsoid(
                    context,
                    name=f"{name_prefix} {part_name} {side} cheek",
                    center=center + right * (radii.x * amount),
                    radii=(radii.x * 0.58, radii.y * 0.9, radii.z * 0.92),
                    basis=axes,
                    material=mats["muzzle"],
                    segments=segments,
                    rings=rings,
                    metadata={"feature_role": "muzzle_cheek", "part_name": part_name, "side": side},
                    created_objects=created_objects,
                    created_meshes=created_meshes,
                )
                result_objects.append(cheek)
            if create_nose:
                nose = _create_ellipsoid(
                    context,
                    name=f"{name_prefix} {part_name} nose",
                    center=center + up * radii.z * 0.58 + front * radii.y * 0.72,
                    radii=(radii.x * 0.28, radii.y * 0.26, radii.z * 0.25),
                    basis=axes,
                    material=mats["nose"],
                    segments=segments,
                    rings=max(4, rings // 2),
                    metadata={"feature_role": "muzzle_nose", "part_name": part_name},
                    created_objects=created_objects,
                    created_meshes=created_meshes,
                )
                result_objects.append(nose)
            if create_mouth:
                mouth_points = [
                    center + front * radii.y * 0.78 + up * radii.z * 0.1,
                    center + front * radii.y * 0.82 + up * -radii.z * 0.35,
                    center + front * radii.y * 0.78 + up * radii.z * 0.1 + right * radii.x * 0.42,
                ]
                left_points = [
                    mouth_points[0],
                    mouth_points[1],
                    center + front * radii.y * 0.78 + up * radii.z * 0.1 + right * -radii.x * 0.42,
                ]
                for side, points in (("right", mouth_points), ("left", left_points)):
                    curve = _create_curve(
                        context,
                        name=f"{name_prefix} {part_name} {side} mouth curve",
                        points=[tuple(point) for point in points],
                        material=mats["mouth"],
                        bevel_depth=max(0.002, min(radii) * 0.035),
                        metadata={"feature_role": "muzzle_mouth_curve", "part_name": part_name, "side": side},
                        created_objects=created_objects,
                    )
                    result_objects.append(curve)
            if create_tongue:
                tongue = _create_ellipsoid(
                    context,
                    name=f"{name_prefix} {part_name} tongue",
                    center=center + front * radii.y * 0.86 + up * -radii.z * 0.42,
                    radii=(radii.x * 0.22, radii.y * 0.18, radii.z * 0.22),
                    basis=axes,
                    material=mats["tongue"],
                    segments=segments,
                    rings=max(4, rings // 2),
                    metadata={"feature_role": "muzzle_tongue", "part_name": part_name},
                    created_objects=created_objects,
                    created_meshes=created_meshes,
                )
                result_objects.append(tongue)
        transaction = _finish_stack(
            context,
            operation,
            label=label,
            stack_kind="create_muzzle_stack",
            graph_collection=graph_collection,
            parts=parts,
            result_objects=result_objects,
        )
        return {
            "ok": True,
            "message": f"Created muzzle stack for {len(parts)} part(s)",
            "part_graph_collection": graph_collection.name,
            "parts": [str(part.get("name") or "") for part in parts],
            "objects": [obj.name for obj in result_objects],
            "transaction_id": transaction["id"],
        }
    except Exception as exc:
        live_preview.abort_isolated(operation, context)
        _cleanup(created_objects, created_meshes)
        return {"ok": False, "message": f"Muzzle stack failed: {type(exc).__name__}: {exc}"}


def create_ear_stack(
    context,
    *,
    part_graph_collection_name="",
    part_names=None,
    name_prefix="Reference Ear Stack",
    outer_color=(0.7, 0.72, 0.74, 1.0),
    inner_color=(0.86, 0.68, 0.68, 1.0),
    scale=1.0,
    inner_scale=0.62,
    create_outer_shell=True,
    create_inner_patch=True,
    segments=32,
    rings=16,
    max_parts=8,
    label="Create ear stack",
):
    graph_collection, parts, error = _graph_parts(
        part_graph_collection_name,
        roles={"ear"},
        part_names=part_names or [],
        max_parts=max_parts,
    )
    if error:
        return {"ok": False, "message": error}
    scale = max(0.05, min(10.0, float(scale or 1.0)))
    inner_scale = max(0.05, min(1.0, float(inner_scale or 0.62)))
    operation = live_preview.begin_isolated(label, context)
    created_objects = []
    created_meshes = []
    result_objects = []
    try:
        mats = {
            "outer": _material(f"{name_prefix} Outer", _as_color(outer_color, (0.7, 0.72, 0.74, 1.0))),
            "inner": _material(f"{name_prefix} Inner", _as_color(inner_color, (0.86, 0.68, 0.68, 1.0))),
        }
        for part in parts:
            center = _part_center(part)
            axes = _basis(part)
            right, depth, up = axes
            front = -depth
            radii = _radii(part, (0.12, 0.28, 0.22)) * scale
            part_name = str(part.get("name") or "ear")
            if create_outer_shell:
                outer = _create_ellipsoid(
                    context,
                    name=f"{name_prefix} {part_name} outer shell",
                    center=center,
                    radii=radii,
                    basis=axes,
                    material=mats["outer"],
                    segments=segments,
                    rings=rings,
                    metadata={"feature_role": "ear_outer_shell", "part_name": part_name},
                    created_objects=created_objects,
                    created_meshes=created_meshes,
                )
                result_objects.append(outer)
            if create_inner_patch:
                inner = _create_ellipsoid(
                    context,
                    name=f"{name_prefix} {part_name} inner patch",
                    center=center + front * radii.y * 0.45 + up * -radii.z * 0.05,
                    radii=(radii.x * inner_scale, max(0.002, radii.y * 0.14), radii.z * inner_scale),
                    basis=axes,
                    material=mats["inner"],
                    segments=segments,
                    rings=max(4, rings // 2),
                    metadata={"feature_role": "ear_inner_patch", "part_name": part_name},
                    created_objects=created_objects,
                    created_meshes=created_meshes,
                )
                result_objects.append(inner)
        if not result_objects:
            raise ValueError("No ear stack components were requested")
        transaction = _finish_stack(
            context,
            operation,
            label=label,
            stack_kind="create_ear_stack",
            graph_collection=graph_collection,
            parts=parts,
            result_objects=result_objects,
        )
        return {
            "ok": True,
            "message": f"Created ear stack for {len(parts)} part(s)",
            "part_graph_collection": graph_collection.name,
            "parts": [str(part.get("name") or "") for part in parts],
            "objects": [obj.name for obj in result_objects],
            "transaction_id": transaction["id"],
        }
    except Exception as exc:
        live_preview.abort_isolated(operation, context)
        _cleanup(created_objects, created_meshes)
        return {"ok": False, "message": f"Ear stack failed: {type(exc).__name__}: {exc}"}


def register():
    pass


def unregister():
    pass
