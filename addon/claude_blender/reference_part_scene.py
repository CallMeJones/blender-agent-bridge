"""Blender scene tools for reference-derived editable part graphs."""

from __future__ import annotations

import json

import bpy

from . import live_preview, reference_blockout, reference_parts, reference_scene
from .advanced_support import _material_for_color


PART_GRAPH_METADATA_PROP = "reference_part_graph_json"


def _safe_label(value, fallback):
    text = " ".join(str(value or "").strip().split())
    keep = [char if char.isalnum() or char in {"_", "-", " "} else "_" for char in text]
    return " ".join("".join(keep).split())[:100] or fallback


def _set_json_prop(data_block, key, value):
    data_block[key] = json.dumps(value, sort_keys=True)


def _get_json_prop(data_block, key, fallback=None):
    try:
        value = data_block.get(key)
        if not value:
            return fallback
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else fallback
    except Exception:
        return fallback


def _guide_collection(collection_name, active_view=""):
    collection, error = reference_scene.guide_collection(collection_name)
    if not error:
        return collection, "", []
    name = str(collection_name or "").strip()
    master = bpy.data.collections.get(name) if name else None
    if master is None or not bool(master.get("reference_multiview_guides", False)):
        return None, error, []
    child_guides = [
        child for child in master.children if bool(child.get("reference_modeling_guides", False))
    ]
    if not child_guides:
        return None, f"Multi-view collection has no child reference guide views: {master.name}", []
    requested = str(active_view or "").strip()
    if requested:
        for child in child_guides:
            view_name = str(child.get("reference_multiview_view") or child.name)
            if requested in {view_name, child.name}:
                return child, "", [f"Used multi-view child guide {child.name} from {master.name}."]
        return None, f"Multi-view view not found for part graph: {requested}", []
    return child_guides[0], "", [f"Used first multi-view child guide {child_guides[0].name} from {master.name}."]


def _graph_collection(collection_name):
    name = str(collection_name or "").strip()
    if name:
        collection = bpy.data.collections.get(name)
        if collection is None:
            return None, f"Reference part graph collection not found: {name}"
        if not bool(collection.get("reference_part_graph", False)):
            return None, f"Collection is not tagged as a reference part graph: {name}"
        return collection, ""
    collections = [
        collection
        for collection in bpy.data.collections
        if bool(collection.get("reference_part_graph", False))
    ]
    if not collections:
        return None, "No reference part graph collection is available"
    if len(collections) > 1:
        return None, "Multiple reference part graphs are available; supply part_graph_collection_name"
    return collections[0], ""


def _landmark_summaries(collection):
    result = []
    for obj in reference_scene.guide_objects(collection, "landmark"):
        meta = reference_scene.json_prop(obj, reference_scene.REFERENCE_GUIDE_METADATA_PROP)
        result.append(
            {
                "name": str(obj.get("reference_guide_name") or meta.get("name") or obj.name),
                "object": obj.name,
                "location": [float(obj.location[0]), float(obj.location[1]), float(obj.location[2])],
            }
        )
    for obj in reference_scene.guide_objects(collection, "landmark_3d"):
        result.append(
            {
                "name": str(obj.get("reference_guide_name") or obj.name),
                "object": obj.name,
                "location": [float(obj.location[0]), float(obj.location[1]), float(obj.location[2])],
            }
        )
    return result


def _role_color(role):
    return {
        "body": (0.62, 0.66, 0.7, 1.0),
        "head": (0.72, 0.75, 0.78, 1.0),
        "muzzle": (0.9, 0.86, 0.8, 1.0),
        "ear": (0.76, 0.69, 0.68, 1.0),
        "eye": (0.05, 0.08, 0.1, 1.0),
        "nose": (0.86, 0.42, 0.48, 1.0),
        "paw": (0.6, 0.62, 0.66, 1.0),
        "tail": (0.58, 0.62, 0.67, 1.0),
    }.get(str(role or "generic"), (0.58, 0.62, 0.68, 1.0))


def _material(role, prefix):
    return _material_for_color(
        _safe_label(f"{prefix} {role} Material", "Reference Part Material"),
        _role_color(role),
    )


def create_reference_part_graph(
    context,
    *,
    collection_name="",
    camera_name="",
    active_view="",
    subject_profile="auto",
    part_hints=None,
    mass_names=None,
    mass_settings=None,
    name="Reference Part Graph",
    depth_ratio=0.7,
    max_parts=32,
    create_markers=True,
    label="Create reference part graph",
):
    """Infer named editable parts from calibrated reference guides."""

    source_collection, error, source_warnings = _guide_collection(collection_name, active_view)
    if error:
        return {"ok": False, "message": error}
    camera, error = reference_scene.comparison_camera(source_collection, camera_name)
    if error:
        return {"ok": False, "message": error}
    try:
        forms, form_warnings = reference_blockout.source_reference_forms(
            source_collection,
            camera=camera,
            mass_names=mass_names or [],
            mass_settings=mass_settings or [],
            depth_ratio=depth_ratio,
            max_forms=max_parts,
        )
    except (TypeError, ValueError) as exc:
        return {"ok": False, "message": str(exc)}
    subject = str(source_collection.get("reference_guide_subject") or "")
    graph = reference_parts.infer_part_graph(
        subject=subject,
        subject_profile=subject_profile,
        forms=forms,
        landmarks=_landmark_summaries(source_collection),
        part_hints=part_hints or [],
        max_parts=max_parts,
    )
    graph["source_guide_collection"] = source_collection.name
    graph["camera"] = camera.name
    graph["form_count"] = len(forms)
    graph["warnings"] = list(source_warnings) + list(form_warnings) + list(graph.get("warnings") or [])
    if not graph["parts"]:
        return {"ok": False, "message": "No reference parts could be inferred from the guide collection"}

    operation = live_preview.begin_isolated(label, context)
    transaction = operation["transaction"]
    try:
        part_collection = bpy.data.collections.new(_safe_label(name, "Reference Part Graph"))
        context.scene.collection.children.link(part_collection)
        live_preview._record_created_id("collection", part_collection.name)
        part_collection["reference_part_graph"] = True
        part_collection["reference_source_guide_collection"] = source_collection.name
        _set_json_prop(part_collection, PART_GRAPH_METADATA_PROP, graph)

        markers = []
        if create_markers:
            for part in graph["parts"]:
                empty = bpy.data.objects.new(
                    _safe_label(f"{part_collection.name} {part['name']}", "Reference Part"),
                    None,
                )
                empty.empty_display_type = "SPHERE"
                empty.empty_display_size = max(0.025, min(part["radii"]) * 0.75)
                empty.location = part["center"]
                part_collection.objects.link(empty)
                live_preview._record_created_id("object", empty.name)
                empty["reference_part_marker"] = True
                empty["reference_part_name"] = part["name"]
                empty["reference_part_role"] = part["role"]
                _set_json_prop(empty, PART_GRAPH_METADATA_PROP, part)
                markers.append(empty.name)

        transaction["applied_steps"].append(
            {
                "type": "create_reference_part_graph",
                "label": label,
                "source_guide_collection": source_collection.name,
                "part_graph_collection": part_collection.name,
                "part_count": len(graph["parts"]),
            }
        )
        transaction = live_preview.finish_isolated(operation)
        live_preview.redraw(context)
        live_preview._mark_pending(context, label)
        return {
            "ok": True,
            "message": f"Created reference part graph with {len(graph['parts'])} part(s)",
            "collection": part_collection.name,
            "source_guide_collection": source_collection.name,
            "camera": camera.name,
            "part_count": len(graph["parts"]),
            "parts": graph["parts"],
            "role_counts": graph["role_counts"],
            "warnings": graph["warnings"],
            "markers": markers,
            "transaction_id": transaction["id"],
        }
    except Exception as exc:
        live_preview.abort_isolated(operation, context)
        return {
            "ok": False,
            "message": f"Reference part graph failed: {type(exc).__name__}: {exc}",
            "source_guide_collection": source_collection.name,
        }


def build_part_aware_base_mesh(
    context,
    *,
    part_graph_collection_name="",
    part_names=None,
    name_prefix="Reference Part Base",
    include_feature_parts=True,
    blend_organic_parts=True,
    voxel_size=0.06,
    smooth_iterations=3,
    segments=32,
    rings=16,
    show_components=False,
    label="Build part-aware base mesh",
):
    """Build sculptable base geometry from a stored reference part graph."""

    graph_collection, error = _graph_collection(part_graph_collection_name)
    if error:
        return {"ok": False, "message": error}
    graph = _get_json_prop(graph_collection, PART_GRAPH_METADATA_PROP, {}) or {}
    parts = list(graph.get("parts") or [])
    requested = {str(name).strip() for name in part_names or [] if str(name).strip()}
    if requested:
        available = {part.get("name") for part in parts}
        missing = sorted(requested - available)
        if missing:
            return {"ok": False, "message": "Reference part(s) not found: " + ", ".join(missing[:16])}
        parts = [part for part in parts if part.get("name") in requested]
    if not parts:
        return {"ok": False, "message": "Reference part graph contains no usable parts"}

    operation = live_preview.begin_isolated(label, context)
    transaction = operation["transaction"]
    created_objects = []
    created_meshes = []
    created_materials = {}
    stage = "components"
    try:
        components = []
        organic_components = []
        feature_objects = []
        for part in parts:
            role = str(part.get("role") or "generic")
            if role in reference_parts.FEATURE_ROLES and not include_feature_parts:
                continue
            material = created_materials.get(role)
            if material is None:
                material = _material(role, name_prefix)
                created_materials[role] = material
            obj = reference_blockout.make_deformed_ellipsoid(
                context,
                name=_safe_label(f"{name_prefix} {part.get('name')}", "Reference Part Component"),
                center=part.get("center"),
                radii=part.get("radii"),
                basis=part.get("basis"),
                controls=part.get("controls") if isinstance(part.get("controls"), list) else [],
                segments=segments,
                rings=rings,
                collection=context.scene.collection,
                material=material,
            )
            obj["reference_part_component"] = True
            obj["reference_part_name"] = str(part.get("name") or "")
            obj["reference_part_role"] = role
            obj["reference_part_graph_collection"] = graph_collection.name
            _set_json_prop(obj, PART_GRAPH_METADATA_PROP, part)
            components.append(obj)
            created_objects.append(obj)
            created_meshes.append(obj.data)
            if role in reference_parts.FEATURE_ROLES and include_feature_parts:
                feature_objects.append(obj)
            elif role in reference_parts.ORGANIC_ROLES:
                organic_components.append(obj)
            elif include_feature_parts:
                feature_objects.append(obj)
        if not components:
            raise ValueError("No part components remained after filtering")

        result_objects = []
        blended = None
        stage = "blend"
        if blend_organic_parts and organic_components:
            material = created_materials.get("body") or next(iter(created_materials.values()))
            blended = reference_blockout.blend_soft_forms(
                context,
                objects=organic_components,
                name=_safe_label(f"{name_prefix} Organic Union", "Reference Part Organic Union"),
                collection=context.scene.collection,
                material=material,
                voxel_size=voxel_size,
                smooth_iterations=smooth_iterations,
                show_components=show_components,
            )
            blended["reference_part_base_mesh"] = True
            blended["reference_part_graph_collection"] = graph_collection.name
            created_objects.append(blended)
            created_meshes.append(blended.data)
            result_objects.append(blended)
        else:
            result_objects.extend(organic_components)
        result_objects.extend(feature_objects)

        if not result_objects:
            result_objects = list(components)
        stage = "selection"
        bpy.ops.object.select_all(action="DESELECT")
        for obj in result_objects:
            obj.hide_set(False)
            obj.select_set(True)
        context.view_layer.objects.active = result_objects[0]
        transaction["applied_steps"].append(
            {
                "type": "build_part_aware_base_mesh",
                "label": label,
                "part_graph_collection": graph_collection.name,
                "parts": [part.get("name") for part in parts],
                "result_objects": [obj.name for obj in result_objects],
            }
        )
        transaction = live_preview.finish_isolated(operation)
        live_preview.redraw(context)
        live_preview._mark_pending(context, label)
        return {
            "ok": True,
            "message": f"Built part-aware base mesh from {len(parts)} part(s)",
            "part_graph_collection": graph_collection.name,
            "components": [obj.name for obj in components],
            "organic_components": [obj.name for obj in organic_components],
            "feature_objects": [obj.name for obj in feature_objects],
            "result_objects": [obj.name for obj in result_objects],
            "blended_object": blended.name if blended else "",
            "transaction_id": transaction["id"],
        }
    except Exception as exc:
        live_preview.abort_isolated(operation, context)
        for obj in reversed(created_objects):
            try:
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
        for material in created_materials.values():
            try:
                if bpy.data.materials.get(material.name) is material and material.users == 0:
                    bpy.data.materials.remove(material)
            except Exception:
                pass
        return {
            "ok": False,
            "message": f"Part-aware base mesh failed during {stage}: {type(exc).__name__}: {exc}",
            "part_graph_collection": graph_collection.name,
        }


def register():
    pass


def unregister():
    pass
