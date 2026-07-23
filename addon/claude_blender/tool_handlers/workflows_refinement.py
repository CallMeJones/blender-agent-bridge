"""Blender-only handlers for the workflows_refinement domain."""

from __future__ import annotations

from .. import advanced_helpers
from ..handler_runtime import _bounded_int, _float_list, _name_list, _optional_float_list


def plan_advanced_scene_workflow(context, args):
    return advanced_helpers.plan_advanced_scene_workflow(
        context,
        prompt=str(args.get("prompt") or ""),
        domains=_name_list(args.get("domains")),
        target_objects=_name_list(args.get("target_objects")),
        label=args.get("label", "Plan advanced scene workflow"),
    )


def plan_object_design(context, args):
    return advanced_helpers.plan_object_design(
        context,
        prompt=str(args.get("prompt") or ""),
        object_family=str(args.get("object_family") or ""),
        target_objects=_name_list(args.get("target_objects")),
        label=args.get("label", "Plan object design"),
    )


def plan_asset_import_workflow(context, args):
    return advanced_helpers.plan_asset_import_workflow(
        context,
        prompt=str(args.get("prompt") or ""),
        provider=str(args.get("provider") or ""),
        asset_id=str(args.get("asset_id") or ""),
        uid=str(args.get("uid") or ""),
        target_object_name=str(args.get("target_object_name") or args.get("object_name") or ""),
        presentation_preset=str(args.get("presentation_preset") or "studio"),
        label=args.get("label", "Plan asset import workflow"),
    )


def plan_director_workflow(context, args):
    return advanced_helpers.plan_director_workflow(
        context,
        prompt=str(args.get("prompt") or ""),
        target_objects=_name_list(args.get("target_objects")),
        deliverables=_name_list(args.get("deliverables")),
        label=args.get("label", "Plan director workflow"),
    )


def get_2d_animation_details(context, args):
    return advanced_helpers.get_2d_animation_details(
        context,
        max_items=_bounded_int(args.get("max_items"), 32, minimum=1, maximum=128),
    )


def create_storyboard_panels(context, args):
    return advanced_helpers.create_storyboard_panels(
        context,
        panel_count=_bounded_int(args.get("panel_count"), 4, minimum=1, maximum=24),
        columns=_bounded_int(args.get("columns"), 2, minimum=1, maximum=24),
        panel_width=float(args.get("panel_width", 3.2)),
        panel_height=float(args.get("panel_height", 1.8)),
        gap=float(args.get("gap", 0.35)),
        name_prefix=str(args.get("name_prefix") or "Agent Bridge Storyboard"),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_step=_bounded_int(args.get("frame_step"), 24, minimum=1, maximum=10000),
        background_color=_float_list(args.get("background_color"), 4, (0.08, 0.08, 0.09, 1.0)),
        border_color=_float_list(args.get("border_color"), 4, (0.9, 0.9, 0.86, 1.0)),
        text_color=_float_list(args.get("text_color"), 4, (0.95, 0.95, 0.9, 1.0)),
        create_camera=bool(args.get("create_camera", True)),
        label=args.get("label", "Create storyboard panels"),
    )


def create_2d_cutout_layer(context, args):
    return advanced_helpers.create_2d_cutout_layer(
        context,
        name=str(args.get("name") or "Agent Bridge 2D Cutout"),
        location=_float_list(args.get("location"), 3, (0.0, 0.0, 0.0)),
        size=args.get("size") or [1.0, 1.0],
        color=_float_list(args.get("color"), 4, (0.2, 0.55, 1.0, 1.0)),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        location_end=_optional_float_list(args.get("location_end"), 3, (0.0, 0.0, 0.0)),
        rotation_end=_optional_float_list(args.get("rotation_end"), 3, (0.0, 0.0, 0.0)),
        scale_end=_optional_float_list(args.get("scale_end"), 3, (1.0, 1.0, 1.0)),
        text=str(args.get("text") or ""),
        label=args.get("label", "Create 2D cutout layer"),
    )


def shade_smooth_selected(context, args):
    return advanced_helpers.shade_smooth_selected(
        context,
        add_weighted_normals=bool(args.get("add_weighted_normals", True)),
        label=args.get("label", "Shade smooth selected"),
    )


def add_bevel_and_subsurf(context, args):
    return advanced_helpers.add_bevel_and_subsurf(
        context,
        bevel_width=float(args.get("bevel_width", 0.06)),
        bevel_segments=_bounded_int(args.get("bevel_segments"), 3, maximum=16),
        subsurf_levels=_bounded_int(args.get("subsurf_levels"), 1, minimum=0, maximum=3),
        weighted_normals=bool(args.get("weighted_normals", True)),
        label=args.get("label", "Add bevel and subdivision"),
    )


def create_wheel_assembly(context, args):
    return advanced_helpers.create_wheel_assembly(
        context,
        name=str(args.get("name") or "Agent Bridge Wheel"),
        location=_float_list(args.get("location"), 3, (0.0, 0.0, 0.0)),
        radius=float(args.get("radius", 0.45)),
        tire_thickness=float(args.get("tire_thickness", 0.12)),
        axis=str(args.get("axis") or "Y"),
        tire_material_name=str(args.get("tire_material_name") or "Agent Bridge Tire Rubber"),
        rim_material_name=str(args.get("rim_material_name") or "Agent Bridge Wheel Rim"),
        label=args.get("label", "Create wheel assembly"),
    )


def add_panel_seams(context, args):
    return advanced_helpers.add_panel_seams(
        context,
        target_name=str(args.get("target_name") or ""),
        seam_material_name=str(args.get("seam_material_name") or "Agent Bridge Panel Seams"),
        bevel_depth=float(args.get("bevel_depth", 0.015)),
        label=args.get("label", "Add panel seams"),
    )


def apply_vehicle_refinement_template(context, args):
    return advanced_helpers.apply_vehicle_refinement_template(
        context,
        target_name=str(args.get("target_name") or ""),
        detail_level=str(args.get("detail_level") or "medium"),
        label=args.get("label", "Apply vehicle refinement template"),
    )


def apply_product_refinement_template(context, args):
    return advanced_helpers.apply_product_refinement_template(
        context,
        target_name=str(args.get("target_name") or ""),
        style=str(args.get("style") or "studio"),
        include_stage=bool(args.get("include_stage", True)),
        include_callouts=bool(args.get("include_callouts", True)),
        include_turntable=bool(args.get("include_turntable", False)),
        label=args.get("label", "Apply product refinement template"),
    )


def apply_character_refinement_template(context, args):
    return advanced_helpers.apply_character_refinement_template(
        context,
        target_name=str(args.get("target_name") or ""),
        character_style=str(args.get("character_style") or "neutral"),
        detail_level=str(args.get("detail_level") or "medium"),
        create_guides=bool(args.get("create_guides", True)),
        label=args.get("label", "Apply character refinement template"),
    )


def add_dimension_callouts(context, args):
    return advanced_helpers.add_dimension_callouts(
        context,
        target_name=str(args.get("target_name") or ""),
        unit_label=str(args.get("unit_label") or "bu"),
        include_width=bool(args.get("include_width", True)),
        include_depth=bool(args.get("include_depth", True)),
        include_height=bool(args.get("include_height", True)),
        label=args.get("label", "Add dimension callouts"),
    )


def prepare_imported_asset_presentation(context, args):
    return advanced_helpers.prepare_imported_asset_presentation(
        context,
        imported_object_names=_name_list(args.get("imported_object_names") or args.get("object_names")),
        target_object_name=str(args.get("target_object_name") or args.get("target_name") or ""),
        selected_only=bool(args.get("selected_only", False)),
        use_active_fallback=bool(args.get("use_active_fallback", True)),
        collection_prefix=str(args.get("collection_prefix") or "Agent Bridge Imported Asset"),
        presentation_preset=str(args.get("presentation_preset") or "studio"),
        assign_material_if_missing=bool(args.get("assign_material_if_missing", True)),
        create_stage=bool(args.get("create_stage", True)),
        create_turntable=bool(args.get("create_turntable", False)),
        label=args.get("label", "Prepare imported asset presentation"),
    )


def organize_scene_for_production(context, args):
    return advanced_helpers.organize_scene_for_production(
        context,
        collection_prefix=str(args.get("collection_prefix") or "Agent Bridge Production"),
        selected_only=bool(args.get("selected_only", False)),
        label=args.get("label", "Organize scene for production"),
    )


def register(handler_registry, specs):
    for spec in specs:
        try:
            handler = globals()[spec.handler_key]
        except KeyError as exc:
            raise KeyError(f"Missing handler {spec.handler_key} for {spec.name}") from exc
        handler_registry.register(spec.name, handler)
