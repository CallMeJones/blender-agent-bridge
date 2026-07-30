"""Preview-safe soft blockouts derived from calibrated reference guides."""

from __future__ import annotations

import json
import math

import bpy
from mathutils import Vector

from . import live_preview, reference_forms, reference_scene
from .advanced_support import _material_for_color


def _safe_label(value, fallback):
    text = " ".join(str(value or "").strip().split())
    return text[:120] or fallback


def _unique_material_name(base):
    base = _safe_label(base, "Reference Blockout Material")
    if bpy.data.materials.get(base) is None:
        return base
    index = 2
    while bpy.data.materials.get(f"{base} {index}") is not None:
        index += 1
    return f"{base} {index}"


def _vector3(value, default):
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return Vector(default)
    try:
        return Vector(
            (float(value[0]), float(value[1]), float(value[2]))
        )
    except (TypeError, ValueError):
        return Vector(default)


def _basis_values(camera):
    return tuple(tuple(float(value) for value in axis) for axis in reference_scene.camera_basis(camera))


def _form_bounds(points, basis):
    if len(points) < 3:
        raise ValueError("A soft form guide needs at least three world points")
    axes = [Vector(axis) for axis in basis]
    projected = [
        [Vector(point).dot(axis) for point in points] for axis in axes
    ]
    minimum = [min(values) for values in projected]
    maximum = [max(values) for values in projected]
    midpoint = [
        (minimum[index] + maximum[index]) * 0.5 for index in range(3)
    ]
    center = sum(
        (axes[index] * midpoint[index] for index in range(3)),
        Vector((0.0, 0.0, 0.0)),
    )
    return center, [
        max(1e-4, (maximum[0] - minimum[0]) * 0.5),
        max(1e-4, (maximum[2] - minimum[2]) * 0.5),
    ]


def _setting_map(mass_settings):
    result = {}
    for raw in list(mass_settings or [])[:64]:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if name:
            result[name] = raw
    return result


def _source_forms(
    collection,
    *,
    camera,
    mass_names,
    mass_settings,
    depth_ratio,
    max_forms,
):
    requested = {
        str(name).strip() for name in mass_names or [] if str(name).strip()
    }
    settings = _setting_map(mass_settings)
    mass_objects = reference_scene.guide_objects(collection, "mass")
    if requested:
        available = {
            str(obj.get("reference_guide_name") or obj.name)
            for obj in mass_objects
        }
        missing = sorted(requested - available)
        if missing:
            raise ValueError(
                "Reference mass guide(s) not found: "
                + ", ".join(missing[:16])
            )
        mass_objects = [
            obj
            for obj in mass_objects
            if str(obj.get("reference_guide_name") or obj.name) in requested
        ]
    source_kind = "mass"
    if not mass_objects and not requested:
        curves = reference_scene.guide_objects(collection, "curve")
        cyclic = [
            obj
            for obj in curves
            if any(bool(spline.use_cyclic_u) for spline in obj.data.splines)
        ]
        mass_objects = (cyclic or curves)[:1]
        source_kind = "outline_fallback"
    if not mass_objects:
        message = "No reference mass guides were resolved"
        raise ValueError(message)

    basis = _basis_values(camera)
    warnings = []
    unused_settings = sorted(
        set(settings)
        - {
            str(obj.get("reference_guide_name") or obj.name)
            for obj in mass_objects
        }
    )
    if unused_settings:
        warnings.append(
            "Ignored mass_settings for unresolved guide name(s): "
            + ", ".join(unused_settings[:16])
        )
    if len(mass_objects) > max_forms:
        warnings.append(
            f"Limited {len(mass_objects)} resolved forms to max_forms={max_forms}"
        )
    forms = []
    for obj in mass_objects[: max(1, min(32, int(max_forms or 1)))]:
        name = str(obj.get("reference_guide_name") or obj.name)
        points = reference_scene.curve_world_points(obj, max_points=512)
        center, (width_radius, height_radius) = _form_bounds(points, basis)
        setting = settings.get(name, {})
        try:
            local_depth_ratio = max(
                0.05,
                min(
                    3.0,
                    float(setting.get("depth_ratio", depth_ratio)),
                ),
            )
        except (TypeError, ValueError):
            local_depth_ratio = depth_ratio
        depth_radius = (
            math.sqrt(width_radius * height_radius) * local_depth_ratio
        )
        scale = _vector3(setting.get("scale"), (1.0, 1.0, 1.0))
        scale = Vector(
            (
                max(0.05, min(10.0, abs(scale.x))),
                max(0.05, min(10.0, abs(scale.y))),
                max(0.05, min(10.0, abs(scale.z))),
            )
        )
        offset = _vector3(setting.get("offset"), (0.0, 0.0, 0.0))
        axes = [Vector(axis) for axis in basis]
        center += sum(
            (axes[index] * offset[index] for index in range(3)),
            Vector((0.0, 0.0, 0.0)),
        )
        forms.append(
            {
                "name": name,
                "source_object": obj.name,
                "source_kind": source_kind,
                "center": tuple(center),
                "radii": (
                    width_radius * scale.x,
                    depth_radius * scale.y,
                    height_radius * scale.z,
                ),
                "basis": basis,
                "controls": (
                    setting.get("controls")
                    if isinstance(setting.get("controls"), list)
                    else []
                ),
            }
        )
    return forms, warnings


def make_deformed_ellipsoid(
    context,
    *,
    name,
    center,
    radii,
    basis,
    controls=None,
    segments=32,
    rings=16,
    collection=None,
    material=None,
):
    """Create one editable mesh ellipsoid from a reference-derived form spec."""

    vertices, faces = reference_forms.deformed_ellipsoid_mesh(
        center=center,
        radii=radii,
        basis=basis,
        controls=controls,
        segments=segments,
        rings=rings,
    )
    mesh = bpy.data.meshes.new(f"{name} Mesh")
    live_preview._record_created_id("mesh", mesh.name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    live_preview._record_created_id("object", obj.name)
    (collection or context.collection or context.scene.collection).objects.link(
        obj
    )
    if material is not None:
        obj.data.materials.append(material)
    return obj


def blend_soft_forms(
    context,
    *,
    objects,
    name,
    collection=None,
    material=None,
    voxel_size=0.08,
    smooth_iterations=2,
    show_components=False,
):
    """Combine component meshes and add a non-destructive voxel-remesh stack."""

    vertices = []
    faces = []
    for source in objects:
        if source.type != "MESH":
            continue
        offset = len(vertices)
        vertices.extend(
            tuple(source.matrix_world @ vertex.co)
            for vertex in source.data.vertices
        )
        faces.extend(
            tuple(offset + index for index in polygon.vertices)
            for polygon in source.data.polygons
        )
    if not vertices or not faces:
        raise ValueError("Soft-form blending requires at least one mesh")

    mesh = None
    obj = None
    try:
        mesh = bpy.data.meshes.new(f"{name} Mesh")
        live_preview._record_created_id("mesh", mesh.name)
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        for polygon in mesh.polygons:
            polygon.use_smooth = True
        obj = bpy.data.objects.new(name, mesh)
        live_preview._record_created_id("object", obj.name)
        (
            collection or context.collection or context.scene.collection
        ).objects.link(obj)
        if material is not None:
            obj.data.materials.append(material)

        minimum = [
            min(vertex[axis] for vertex in vertices) for axis in range(3)
        ]
        maximum = [
            max(vertex[axis] for vertex in vertices) for axis in range(3)
        ]
        max_extent = max(
            maximum[axis] - minimum[axis] for axis in range(3)
        )
        requested_voxel_size = max(
            0.001, min(10.0, float(voxel_size))
        )
        effective_voxel_size = max(
            requested_voxel_size, max_extent / 128.0
        )
        remesh = obj.modifiers.new("Reference Soft Union", "REMESH")
        remesh.mode = "VOXEL"
        remesh.voxel_size = effective_voxel_size
        remesh.use_smooth_shade = True
        obj["reference_blockout_requested_voxel_size"] = (
            requested_voxel_size
        )
        obj["reference_blockout_effective_voxel_size"] = (
            effective_voxel_size
        )
        iterations = max(0, min(20, int(smooth_iterations or 0)))
        if iterations:
            smooth = obj.modifiers.new(
                "Reference Surface Relax", "SMOOTH"
            )
            smooth.factor = 0.5
            smooth.iterations = iterations

        for component in objects:
            component.hide_render = True
            component.hide_set(not bool(show_components))
        return obj
    except Exception:
        if obj is not None and bpy.data.objects.get(obj.name) is obj:
            bpy.data.objects.remove(obj, do_unlink=True)
        if (
            mesh is not None
            and bpy.data.meshes.get(mesh.name) is mesh
            and mesh.users == 0
        ):
            bpy.data.meshes.remove(mesh)
        raise


def _cleanup_created(objects, meshes, material):
    for obj in reversed(objects):
        try:
            if bpy.data.objects.get(obj.name) is obj:
                bpy.data.objects.remove(obj, do_unlink=True)
        except Exception:
            pass
    for mesh in reversed(meshes):
        try:
            if bpy.data.meshes.get(mesh.name) is mesh and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        except Exception:
            pass
    try:
        if (
            material is not None
            and bpy.data.materials.get(material.name) is material
            and material.users == 0
        ):
            bpy.data.materials.remove(material)
    except Exception:
        pass


def create_reference_blockout(
    context,
    *,
    collection_name="",
    camera_name="",
    mass_names=None,
    mass_settings=None,
    name_prefix="Reference Blockout",
    depth_ratio=0.7,
    segments=32,
    rings=16,
    max_forms=16,
    blend_mode="voxel",
    voxel_size=0.08,
    smooth_iterations=2,
    show_components=False,
    color=(0.55, 0.6, 0.68, 1.0),
    label="Create reference blockout",
):
    """Create editable primary masses from calibrated guide ellipses."""

    collection, error = reference_scene.guide_collection(collection_name)
    if error:
        return {"ok": False, "message": error}
    camera, error = reference_scene.comparison_camera(
        collection, camera_name
    )
    if error:
        return {"ok": False, "message": error}
    try:
        forms, warnings = _source_forms(
            collection,
            camera=camera,
            mass_names=mass_names,
            mass_settings=mass_settings,
            depth_ratio=max(0.05, min(3.0, float(depth_ratio or 0.7))),
            max_forms=max_forms,
        )
    except (TypeError, ValueError) as exc:
        return {"ok": False, "message": str(exc)}

    operation = live_preview.begin_isolated(label, context)
    transaction = operation["transaction"]
    created_objects = []
    created_meshes = []
    material = None
    material_name = _unique_material_name(f"{name_prefix} Material")
    stage = "material"
    try:
        try:
            material = _material_for_color(material_name, color)
        except Exception:
            material = bpy.data.materials.get(material_name)
            raise
        components = []
        stage = "components"
        for index, form in enumerate(forms, 1):
            obj = make_deformed_ellipsoid(
                context,
                name=_safe_label(
                    f"{name_prefix} {index:02d} {form['name']}",
                    f"Reference Blockout {index:02d}",
                ),
                center=form["center"],
                radii=form["radii"],
                basis=form["basis"],
                controls=form["controls"],
                segments=segments,
                rings=rings,
                collection=context.scene.collection,
                material=material,
            )
            obj["reference_blockout_component"] = True
            obj["reference_blockout_mass_name"] = form["name"]
            obj["reference_blockout_source_object"] = form["source_object"]
            obj["reference_blockout_form_json"] = json.dumps(
                {
                    "center": list(form["center"]),
                    "radii": list(form["radii"]),
                    "source_kind": form["source_kind"],
                },
                sort_keys=True,
            )
            components.append(obj)
            created_objects.append(obj)
            created_meshes.append(obj.data)

        mode = str(blend_mode or "voxel").strip().lower()
        result_objects = list(components)
        blended = None
        stage = "blend"
        if mode == "voxel":
            blended = blend_soft_forms(
                context,
                objects=components,
                name=_safe_label(
                    f"{name_prefix} Soft Union",
                    "Reference Blockout Soft Union",
                ),
                collection=context.scene.collection,
                material=material,
                voxel_size=voxel_size,
                smooth_iterations=smooth_iterations,
                show_components=show_components,
            )
            blended["reference_blockout"] = True
            blended["reference_blockout_guide_collection"] = collection.name
            created_objects.append(blended)
            created_meshes.append(blended.data)
            result_objects = [blended]
        elif mode != "separate":
            raise ValueError("blend_mode must be voxel or separate")

        stage = "selection"
        bpy.ops.object.select_all(action="DESELECT")
        for obj in result_objects:
            obj.hide_set(False)
            obj.select_set(True)
        context.view_layer.objects.active = result_objects[0]
        transaction["applied_steps"].append(
            {
                "type": "create_reference_blockout",
                "label": label,
                "guide_collection": collection.name,
                "camera": camera.name,
                "mass_names": [form["name"] for form in forms],
                "components": [obj.name for obj in components],
                "result_objects": [obj.name for obj in result_objects],
                "blend_mode": mode,
            }
        )
        transaction = live_preview.finish_isolated(operation)
        live_preview.redraw(context)
        live_preview._mark_pending(context, label)
        return {
            "ok": True,
            "message": (
                f"Created {len(forms)} reference-derived soft form(s)"
            ),
            "guide_collection": collection.name,
            "camera": camera.name,
            "blend_mode": mode,
            "components": [
                {
                    "name": form["name"],
                    "object": obj.name,
                    "source_object": form["source_object"],
                    "source_kind": form["source_kind"],
                    "center": list(form["center"]),
                    "radii": list(form["radii"]),
                }
                for form, obj in zip(forms, components)
            ],
            "result_objects": [obj.name for obj in result_objects],
            "blended_object": blended.name if blended else "",
            "effective_voxel_size": (
                float(
                    blended.get(
                        "reference_blockout_effective_voxel_size",
                        voxel_size,
                    )
                )
                if blended
                else None
            ),
            "warnings": warnings,
            "transaction_id": transaction["id"],
        }
    except Exception as exc:
        live_preview.abort_isolated(operation, context)
        _cleanup_created(created_objects, created_meshes, material)
        return {
            "ok": False,
            "message": (
                f"Reference blockout failed during {stage}: "
                f"{type(exc).__name__}: {exc}"
            ),
            "guide_collection": collection.name,
            "camera": camera.name,
        }


def register():
    pass


def unregister():
    pass
