"""Advanced Blender helpers for workflows refinement."""



from __future__ import annotations

import math

import bpy

from . import live_preview, presentation_support

from .advanced_support import (
    _bounds_world,
    _coerce_vector,
    _create_curve_line,
    _material_for_color,
    _preserve_selection,
)

from .advanced_camera_render import (
    create_product_turntable_setup,
    create_studio_product_stage,
)

from .advanced_materials import (
    create_material_palette,
)



def _record_mesh_smoothing(mesh):
    transaction = live_preview.begin()
    key = f"mesh:{mesh.name}:smoothing"
    if key in transaction["before_state"]:
        return
    transaction["before_state"][key] = {
        "kind": "mesh_smoothing",
        "mesh_name": mesh.name,
        "polygon_smooth": [bool(poly.use_smooth) for poly in mesh.polygons],
    }
    transaction["changed_data_blocks"].append(mesh.name)

def _axis_rotation(axis):
    axis = str(axis or "Y").upper()
    if axis == "X":
        return (0.0, math.radians(90.0), 0.0)
    if axis == "Y":
        return (math.radians(90.0), 0.0, 0.0)
    return (0.0, 0.0, 0.0)

def _create_text_label(context, name, text, location, *, size=0.2, rotation=(0.0, 0.0, 0.0), material=None):
    curve = bpy.data.curves.new(f"{name} Data", "FONT")
    curve.body = str(text)
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = max(0.01, float(size))
    obj = bpy.data.objects.new(name, curve)
    obj.location = _coerce_vector(location, (0.0, 0.0, 0.0))
    obj.rotation_euler = _coerce_vector(rotation, (0.0, 0.0, 0.0))
    context.scene.collection.objects.link(obj)
    if material:
        curve.materials.append(material)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("curve", curve.name)
    return obj

def _create_wheel_parts(context, *, name, location, radius, thickness, axis, tire_material, rim_material):
    rotation = _axis_rotation(axis)
    bpy.ops.mesh.primitive_torus_add(
        major_radius=max(0.01, float(radius)),
        minor_radius=max(0.005, float(thickness)),
        major_segments=64,
        minor_segments=16,
        location=location,
        rotation=rotation,
    )
    tire = context.object
    tire.name = f"{name} Tire"
    tire.data.name = f"{tire.name} Mesh"
    tire.data.materials.append(tire_material)
    live_preview._record_created_id("object", tire.name)
    live_preview._record_created_id("mesh", tire.data.name)

    bpy.ops.mesh.primitive_cylinder_add(
        vertices=48,
        radius=max(0.01, float(radius) * 0.62),
        depth=max(0.01, float(thickness) * 2.2),
        location=location,
        rotation=rotation,
    )
    rim = context.object
    rim.name = f"{name} Rim"
    rim.data.name = f"{rim.name} Mesh"
    rim.data.materials.append(rim_material)
    live_preview._record_created_id("object", rim.name)
    live_preview._record_created_id("mesh", rim.data.name)

    return [tire, rim]

def shade_smooth_selected(context, *, add_weighted_normals=True, label="Shade smooth selected"):
    selected = [obj for obj in context.selected_objects if obj.type == "MESH" and obj.data]
    if not selected:
        return {"ok": False, "message": "No selected mesh objects to shade smooth"}
    transaction = live_preview.begin(label)
    changed = []
    for obj in selected:
        _record_mesh_smoothing(obj.data)
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        if add_weighted_normals and obj.modifiers.get("Agent Bridge Weighted Normals") is None:
            modifier = obj.modifiers.new("Agent Bridge Weighted Normals", "WEIGHTED_NORMAL")
            live_preview._record_created_modifier(obj, modifier)
        changed.append(obj.name)
    transaction["applied_steps"].append({"type": "shade_smooth_selected", "label": label, "objects": changed})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Smoothed {len(changed)} mesh object(s)", "objects": changed, "transaction_id": transaction["id"]}

def add_bevel_and_subsurf(
    context,
    *,
    bevel_width=0.06,
    bevel_segments=3,
    subsurf_levels=1,
    weighted_normals=True,
    label="Add bevel and subdivision",
):
    selected = [obj for obj in context.selected_objects if obj.type == "MESH" and obj.data]
    if not selected:
        return {"ok": False, "message": "No selected mesh objects for bevel/subdivision"}
    transaction = live_preview.begin(label)
    changed = []
    for obj in selected:
        bevel = obj.modifiers.new("Agent Bridge Detail Bevel", "BEVEL")
        bevel.width = max(0.0, min(10.0, float(bevel_width)))
        bevel.segments = max(1, min(16, int(bevel_segments)))
        live_preview._record_created_modifier(obj, bevel)
        if int(subsurf_levels) > 0:
            subsurf = obj.modifiers.new("Agent Bridge Detail Subdivision", "SUBSURF")
            subsurf.levels = max(0, min(3, int(subsurf_levels)))
            subsurf.render_levels = max(0, min(3, int(subsurf_levels)))
            live_preview._record_created_modifier(obj, subsurf)
        if weighted_normals:
            normals = obj.modifiers.new("Agent Bridge Weighted Normals", "WEIGHTED_NORMAL")
            live_preview._record_created_modifier(obj, normals)
        changed.append(obj.name)
    transaction["applied_steps"].append({"type": "add_bevel_and_subsurf", "label": label, "objects": changed})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Added bevel/detail modifiers to {len(changed)} mesh object(s)", "objects": changed, "transaction_id": transaction["id"]}

def create_wheel_assembly(
    context,
    *,
    name,
    location,
    radius=0.45,
    tire_thickness=0.12,
    axis="Y",
    tire_material_name="Agent Bridge Tire Rubber",
    rim_material_name="Agent Bridge Wheel Rim",
    label="Create wheel assembly",
):
    transaction = live_preview.begin(label)
    tire_material = _material_for_color(tire_material_name, (0.005, 0.005, 0.006, 1.0))
    rim_material = _material_for_color(rim_material_name, (0.72, 0.72, 0.68, 1.0))
    objects = _create_wheel_parts(
        context,
        name=name or "Agent Bridge Wheel",
        location=_coerce_vector(location, (0.0, 0.0, 0.0)),
        radius=radius,
        thickness=tire_thickness,
        axis=axis,
        tire_material=tire_material,
        rim_material=rim_material,
    )
    transaction["applied_steps"].append(
        {"type": "create_wheel_assembly", "label": label, "objects": [obj.name for obj in objects]}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Created wheel assembly {name}", "objects": [obj.name for obj in objects], "transaction_id": transaction["id"]}

def add_panel_seams(
    context,
    *,
    target_name="",
    seam_material_name="Agent Bridge Panel Seams",
    bevel_depth=0.015,
    label="Add panel seams",
):
    target = bpy.data.objects.get(target_name) if target_name else context.active_object
    if target is None or target.type != "MESH":
        return {"ok": False, "message": "A mesh target object is required for panel seams"}
    transaction = live_preview.begin(label)
    bounds = _bounds_world(target)
    min_x, min_y, min_z = bounds["min"]
    max_x, max_y, max_z = bounds["max"]
    sx, sy, sz = bounds["size"]
    seam_material = _material_for_color(seam_material_name, (0.01, 0.008, 0.006, 1.0))
    z_top = max_z + max(0.01, sz * 0.01)
    y_left = min_y - max(0.01, sy * 0.01)
    y_right = max_y + max(0.01, sy * 0.01)
    x_front = min_x + sx * 0.28
    x_mid = min_x + sx * 0.52
    x_rear = min_x + sx * 0.76
    created = []
    for index, x in enumerate((x_front, x_mid, x_rear), start=1):
        created.append(
            _create_curve_line(
                context,
                f"{target.name} Panel Seam Top {index}",
                [(x, min_y, z_top), (x, max_y, z_top)],
                bevel_depth,
                seam_material,
            ).name
        )
    for side_name, y in (("L", y_left), ("R", y_right)):
        z_side = min_z + sz * 0.48
        created.append(
            _create_curve_line(
                context,
                f"{target.name} Door Seam {side_name}",
                [(x_mid, y, min_z + sz * 0.12), (x_mid, y, z_side)],
                bevel_depth,
                seam_material,
            ).name
        )
        created.append(
            _create_curve_line(
                context,
                f"{target.name} Belt Line {side_name}",
                [(min_x + sx * 0.18, y, z_side), (max_x - sx * 0.12, y, z_side)],
                bevel_depth,
                seam_material,
            ).name
        )
    transaction["applied_steps"].append({"type": "add_panel_seams", "label": label, "target": target.name, "objects": created})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Added panel seams around {target.name}", "objects": created, "transaction_id": transaction["id"]}

def add_dimension_callouts(
    context,
    *,
    target_name="",
    unit_label="bu",
    include_width=True,
    include_depth=True,
    include_height=True,
    label="Add dimension callouts",
):
    target = bpy.data.objects.get(target_name) if target_name else context.active_object
    if target is None or not hasattr(target, "bound_box"):
        return {"ok": False, "message": "A target object with bounds is required for dimension callouts"}
    if not any((include_width, include_depth, include_height)):
        return {"ok": False, "message": "Enable at least one dimension callout"}
    transaction = live_preview.begin(label, context)
    bounds = _bounds_world(target)
    min_x, min_y, min_z = bounds["min"]
    max_x, max_y, max_z = bounds["max"]
    center_x, center_y, center_z = bounds["center"]
    sx, sy, sz = bounds["size"]
    max_dim = max(1.0, sx, sy, sz)
    offset = max_dim * 0.18
    line_material = _material_for_color(f"{target.name} Dimension Lines", (0.02, 0.02, 0.02, 1.0))
    text_material = _material_for_color(f"{target.name} Dimension Text", (0.95, 0.95, 0.88, 1.0))
    bevel = max(0.004, max_dim * 0.006)
    text_size = max(0.08, max_dim * 0.075)
    unit_label = str(unit_label or "bu")
    created = []
    measurements = {}

    def add_line(name, points, text, text_location, rotation=(math.radians(60.0), 0.0, 0.0)):
        line = _create_curve_line(context, name, points, bevel, line_material)
        label_obj = _create_text_label(
            context,
            f"{name} Label",
            text,
            text_location,
            size=text_size,
            rotation=rotation,
            material=text_material,
        )
        created.extend([line.name, label_obj.name])

    if include_width:
        y = min_y - offset
        z = min_z + offset * 0.35
        value = float(sx)
        measurements["width"] = value
        add_line(
            f"{target.name} Width Callout",
            [(min_x, y, z), (max_x, y, z)],
            f"W {value:.2f} {unit_label}",
            (center_x, y, z + offset * 0.22),
        )
    if include_depth:
        x = max_x + offset
        z = min_z + offset * 0.35
        value = float(sy)
        measurements["depth"] = value
        add_line(
            f"{target.name} Depth Callout",
            [(x, min_y, z), (x, max_y, z)],
            f"D {value:.2f} {unit_label}",
            (x, center_y, z + offset * 0.22),
            rotation=(math.radians(60.0), 0.0, math.radians(90.0)),
        )
    if include_height:
        x = max_x + offset
        y = max_y + offset
        value = float(sz)
        measurements["height"] = value
        add_line(
            f"{target.name} Height Callout",
            [(x, y, min_z), (x, y, max_z)],
            f"H {value:.2f} {unit_label}",
            (x, y, center_z),
            rotation=(math.radians(70.0), 0.0, math.radians(90.0)),
        )

    transaction["applied_steps"].append(
        {
            "type": "add_dimension_callouts",
            "label": label,
            "target": target.name,
            "created_objects": created,
            "measurements": measurements,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Added dimension callouts for {target.name}",
        "target": target.name,
        "created_objects": created,
        "measurements": measurements,
        "transaction_id": transaction["id"],
    }

def _asset_presentation_objects(
    context,
    *,
    imported_object_names=None,
    target_object_name="",
    selected_only=False,
    use_active_fallback=True,
):
    names = []
    target_object_name = str(target_object_name or "").strip()
    if target_object_name and not target_object_name.startswith("<"):
        names.append(target_object_name)
    for name in imported_object_names or []:
        text = str(name or "").strip()
        if text and not text.startswith("<") and text not in names:
            names.append(text)
    objects = []
    missing = []
    seen = set()
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None:
            missing.append(name)
            continue
        if not hasattr(obj, "bound_box"):
            continue
        if obj.name not in seen:
            objects.append(obj)
            seen.add(obj.name)
    if objects:
        return objects, missing, "explicit_names"

    if selected_only:
        for obj in context.selected_objects:
            if obj and hasattr(obj, "bound_box") and obj.name not in seen:
                objects.append(obj)
                seen.add(obj.name)
        if objects:
            return objects, missing, "selected_objects"

    active = context.active_object if use_active_fallback else None
    if active and hasattr(active, "bound_box"):
        return [active], missing, "active_object"
    return [], missing, "none"

def _largest_bounds_object(objects):
    best = None
    best_volume = -1.0
    for obj in objects or []:
        try:
            sx, sy, sz = _bounds_world(obj)["size"]
            volume = max(0.0, float(sx)) * max(0.0, float(sy)) * max(0.0, float(sz))
        except Exception:
            volume = 0.0
        if best is None or volume > best_volume:
            best = obj
            best_volume = volume
    return best

def prepare_imported_asset_presentation(
    context,
    *,
    imported_object_names=None,
    target_object_name="",
    selected_only=False,
    use_active_fallback=True,
    collection_prefix="Agent Bridge Imported Asset",
    presentation_preset="studio",
    assign_material_if_missing=True,
    create_stage=True,
    create_turntable=False,
    label="Prepare imported asset presentation",
):
    """Organize imported scene objects and build a bounded presentation setup."""

    objects, missing, source = _asset_presentation_objects(
        context,
        imported_object_names=imported_object_names,
        target_object_name=target_object_name,
        selected_only=selected_only,
        use_active_fallback=use_active_fallback,
    )
    if not objects:
        return {
            "ok": False,
            "message": "Imported object names, selected objects, or an active object with bounds are required",
            "missing_object_names": missing,
            "selection_source": source,
        }

    target = bpy.data.objects.get(target_object_name) if target_object_name and not str(target_object_name).startswith("<") else None
    if target not in objects or not hasattr(target, "bound_box"):
        target = _largest_bounds_object(objects)
    if target is None:
        return {"ok": False, "message": "A bounded target object is required for imported asset presentation"}

    preset_key = presentation_support.infer_presentation_preset("", presentation_preset)
    collection_prefix = str(collection_prefix or "Agent Bridge Imported Asset")
    transaction = live_preview.begin(label, context)
    assigned = []
    material_name = ""
    with _preserve_selection(context):
        bpy.ops.object.select_all(action="DESELECT")
        for obj in objects:
            obj.select_set(True)
        context.view_layer.objects.active = target

        organization_result = organize_scene_for_production(
            context,
            collection_prefix=collection_prefix,
            selected_only=True,
            label=label,
        )

        if assign_material_if_missing:
            material = _material_for_color(f"{collection_prefix} Neutral Material", (0.64, 0.63, 0.59, 1.0))
            material_name = material.name
            for obj in objects:
                if obj.type != "MESH" or not obj.data:
                    continue
                if obj.material_slots:
                    continue
                live_preview._record_object_materials(obj)
                obj.data.materials.append(material)
                assigned.append({"object": obj.name, "material": material.name})

        palette_result = create_material_palette(
            context,
            palette_name=f"{collection_prefix} Palette",
            palette="product_neutral" if preset_key != "lookdev" else "cinematic",
            create_swatches=False,
            assign_to_selected=False,
            label=label,
        )

        stage_result = {}
        if create_stage:
            stage_result = create_studio_product_stage(
                context,
                target_name=target.name,
                stage_name=f"{collection_prefix} Stage",
                floor=True,
                backdrop=preset_key != "lookdev",
                lighting=True,
                camera=True,
                label=label,
            )

        turntable_result = {}
        if create_turntable or preset_key == "turntable":
            turntable_result = create_product_turntable_setup(
                context,
                target_name=target.name,
                frame_start=context.scene.frame_start,
                frame_end=max(context.scene.frame_end, context.scene.frame_start + 96),
                revolutions=1.0,
                setup_name=f"{collection_prefix} Turntable",
                create_stage=False,
                label=label,
            )

    created = []
    created.extend(stage_result.get("created_objects") or [])
    if turntable_result.get("camera_orbit", {}).get("camera"):
        created.append(turntable_result["camera_orbit"]["camera"])
    features = ["production collections"]
    if assigned:
        features.append("missing material fill")
    if palette_result.get("ok"):
        features.append("material palette")
    if stage_result.get("ok"):
        features.append("studio stage")
    if turntable_result.get("ok"):
        features.append("turntable review")
    transaction["applied_steps"].append(
        {
            "type": "prepare_imported_asset_presentation",
            "label": label,
            "target": target.name,
            "objects": [obj.name for obj in objects],
            "selection_source": source,
            "collection_prefix": collection_prefix,
            "presentation_preset": preset_key,
            "assigned_materials": assigned,
            "created_objects": created,
            "features": features,
            "expected_changes": (
                f"Prepares imported asset objects around {target.name}: "
                f"{', '.join(features)}."
            ),
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    warnings = list(stage_result.get("warnings") or [])
    return {
        "ok": True,
        "message": f"Prepared imported asset presentation for {target.name}",
        "target": target.name,
        "objects": [obj.name for obj in objects],
        "missing_object_names": missing,
        "selection_source": source,
        "collection_prefix": collection_prefix,
        "presentation_preset": preset_key,
        "organization": organization_result,
        "material": material_name,
        "assigned_materials": assigned,
        "palette": palette_result,
        "stage": stage_result,
        "turntable": turntable_result,
        "created_objects": created,
        "features": features,
        "warnings": warnings,
        "transaction_id": transaction["id"],
    }

def organize_scene_for_production(
    context,
    *,
    collection_prefix="Agent Bridge Production",
    selected_only=False,
    label="Organize scene for production",
):
    collection_prefix = str(collection_prefix or "Agent Bridge Production")
    objects = list(context.selected_objects) if selected_only else list(context.scene.objects)
    objects = [obj for obj in objects if obj and not obj.name.startswith(collection_prefix)]
    if not objects:
        return {"ok": False, "message": "No objects available to organize"}
    transaction = live_preview.begin(label, context)
    buckets = {
        "Meshes": {"MESH"},
        "Cameras": {"CAMERA"},
        "Lights": {"LIGHT"},
        "Curves Text": {"CURVE", "FONT"},
        "Helpers": {"EMPTY", "ARMATURE"},
    }
    collections = {}
    linked = []
    for obj in objects:
        bucket_name = "Other"
        for name, types in buckets.items():
            if obj.type in types:
                bucket_name = name
                break
        collection_name = f"{collection_prefix} - {bucket_name}"
        collection = collections.get(collection_name) or bpy.data.collections.get(collection_name)
        if collection is None:
            collection = bpy.data.collections.new(collection_name)
            context.scene.collection.children.link(collection)
            live_preview._record_created_id("collection", collection.name)
        collections[collection_name] = collection
        live_preview._record_object_collections(obj)
        if collection.objects.get(obj.name) is None:
            collection.objects.link(obj)
        linked.append({"object": obj.name, "collection": collection.name})
    transaction["applied_steps"].append(
        {
            "type": "organize_scene_for_production",
            "label": label,
            "collections": sorted(collections),
            "linked": linked,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Linked {len(linked)} object(s) into production collections",
        "collections": sorted(collections),
        "linked": linked,
        "transaction_id": transaction["id"],
    }





def register():

    pass





def unregister():

    pass

