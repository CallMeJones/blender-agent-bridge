"""Blender-only handlers for the modeling domain."""

from __future__ import annotations

from .. import (
    advanced_modeling as advanced_helpers,
    preferences,
    reference_blockout,
    reference_comparison,
    reference_guides,
    reference_multiview_scene,
)
from .support import _bounded_float, _bounded_int, _float_list, _name_list, _optional_float_list


def create_text_object(context, args):
    return advanced_helpers.create_text_object(
        context,
        name=str(args.get("name") or "Agent Bridge Text"),
        body=str(args.get("body") or "Text"),
        location=_float_list(args.get("location"), 3, (0.0, 0.0, 0.0)),
        rotation=_float_list(args.get("rotation"), 3, (0.0, 0.0, 0.0)),
        scale=_float_list(args.get("scale"), 3, (1.0, 1.0, 1.0)),
        size=float(args.get("size", 1.0)),
        align_x=str(args.get("align_x") or "CENTER"),
        align_y=str(args.get("align_y") or "CENTER"),
        material_name=str(args.get("material_name") or ""),
        color=_optional_float_list(args.get("color"), 4, (1.0, 1.0, 1.0, 1.0)),
        label=args.get("label", "Create text object"),
    )


def create_curve_path(context, args):
    points = args.get("points") or []
    return advanced_helpers.create_curve_path(
        context,
        name=str(args.get("name") or "Agent Bridge Curve"),
        points=points,
        bevel_depth=float(args.get("bevel_depth", 0.02)),
        cyclic=bool(args.get("cyclic", False)),
        material_name=str(args.get("material_name") or ""),
        color=_optional_float_list(args.get("color"), 4, (1.0, 1.0, 1.0, 1.0)),
        label=args.get("label", "Create curve path"),
    )


def create_reference_modeling_guides(context, args):
    return reference_guides.create_reference_modeling_guides(
        context,
        image_path=str(args.get("image_path") or ""),
        image_size=args.get("image_size") or [],
        coordinate_space=str(args.get("coordinate_space") or "normalized"),
        subject=str(args.get("subject") or "reference model"),
        collection_name=str(args.get("collection_name") or "Reference Modeling Guides"),
        plane_height=_bounded_float(args.get("plane_height"), 3.0, minimum=0.01, maximum=100.0),
        plane_location=_float_list(args.get("plane_location"), 3, (0.0, 0.0, 1.5)),
        guide_offset_y=_bounded_float(args.get("guide_offset_y"), -0.02, minimum=-10.0, maximum=10.0),
        include_image_plane=bool(args.get("include_image_plane", True)),
        image_alpha=_bounded_float(args.get("image_alpha"), 0.35, minimum=0.0, maximum=1.0),
        landmarks=args.get("landmarks") if isinstance(args.get("landmarks"), list) else [],
        curves=args.get("curves") if isinstance(args.get("curves"), list) else [],
        masses=args.get("masses") if isinstance(args.get("masses"), list) else [],
        measurements=args.get("measurements") if isinstance(args.get("measurements"), list) else [],
        label=args.get("label", "Create reference modeling guides"),
    )


def create_reference_guides_from_annotations(context, args):
    annotations = args.get("annotations")
    return reference_guides.create_reference_guides_from_annotations(
        context,
        image_path=str(args.get("image_path") or ""),
        annotations=annotations if isinstance(annotations, dict) else None,
        annotations_json=str(args.get("annotations_json") or ""),
        annotations_path=str(args.get("annotations_path") or ""),
        default_coordinate_space=str(
            args.get("default_coordinate_space") or "pixel"
        ),
        default_origin=str(args.get("default_origin") or "top_left"),
        subject=str(args.get("subject") or ""),
        collection_name=str(
            args.get("collection_name") or "Reference Annotation Guides"
        ),
        plane_height=_bounded_float(
            args.get("plane_height"), 3.0, minimum=0.01, maximum=100.0
        ),
        plane_location=_float_list(
            args.get("plane_location"), 3, (0.0, 0.0, 1.5)
        ),
        guide_offset_y=_bounded_float(
            args.get("guide_offset_y"), -0.02, minimum=-10.0, maximum=10.0
        ),
        include_image_plane=bool(args.get("include_image_plane", True)),
        image_alpha=_bounded_float(
            args.get("image_alpha"), 0.35, minimum=0.0, maximum=1.0
        ),
        create_camera=bool(args.get("create_camera", True)),
        camera_name=str(
            args.get("camera_name") or "Reference Annotation Camera"
        ),
        camera_margin=_bounded_float(
            args.get("camera_margin"), 0.05, minimum=0.0, maximum=1.0
        ),
        activate_camera=bool(args.get("activate_camera", True)),
        match_render_aspect=bool(args.get("match_render_aspect", True)),
        label=args.get(
            "label", "Create reference guides from annotations"
        ),
    )


def create_multiview_reference_guides(context, args):
    return reference_multiview_scene.create_multiview_reference_guides(
        context,
        views=args.get("views") if isinstance(args.get("views"), list) else [],
        subject=str(args.get("subject") or "reference model"),
        collection_name=str(
            args.get("collection_name") or "Multi-View Reference Guides"
        ),
        subject_center=_float_list(
            args.get("subject_center"),
            3,
            (0.0, 0.0, 1.5),
        ),
        active_view=str(args.get("active_view") or ""),
        include_image_planes=bool(args.get("include_image_planes", True)),
        image_alpha=_bounded_float(
            args.get("image_alpha"),
            0.35,
            minimum=0.0,
            maximum=1.0,
        ),
        guide_offset=_bounded_float(
            args.get("guide_offset"),
            -0.02,
            minimum=-10.0,
            maximum=10.0,
        ),
        create_connectors=bool(args.get("create_connectors", True)),
        require_reconstruction=bool(args.get("require_reconstruction", True)),
        minimum_views_per_landmark=_bounded_int(
            args.get("minimum_views_per_landmark"),
            2,
            minimum=2,
            maximum=6,
        ),
        minimum_ray_angle_degrees=_bounded_float(
            args.get("minimum_ray_angle_degrees"),
            1.0,
            minimum=0.0,
            maximum=90.0,
        ),
        max_landmark_residual=_bounded_float(
            args.get("max_landmark_residual"),
            0.1,
            minimum=0.0,
            maximum=1000.0,
        ),
        match_render_aspect=bool(args.get("match_render_aspect", True)),
        label=str(args.get("label") or "Create multi-view reference guides"),
    )


def inspect_reference_modeling_guides(context, args):
    return reference_guides.inspect_reference_modeling_guides(
        context,
        collection_name=str(args.get("collection_name") or ""),
        include_points=bool(args.get("include_points", False)),
        max_points_per_curve=_bounded_int(args.get("max_points_per_curve"), 32, minimum=2, maximum=512),
        max_collections=_bounded_int(args.get("max_collections"), 8, minimum=1, maximum=64),
    )


def compare_model_to_reference(context, args):
    landmark_targets = args.get("landmark_targets")
    prefs = preferences.get_preferences(context)
    return reference_comparison.compare_model_to_reference(
        context,
        collection_name=str(args.get("collection_name") or ""),
        camera_name=str(args.get("camera_name") or ""),
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        outline_name=str(args.get("outline_name") or ""),
        reference_mask_source=str(
            args.get("reference_mask_source") or "auto"
        ),
        landmark_targets=(
            landmark_targets if isinstance(landmark_targets, list) else []
        ),
        max_axis=_bounded_int(
            args.get("max_axis"), 512, minimum=64, maximum=1024
        ),
        mask_threshold=_bounded_float(
            args.get("mask_threshold"), 0.5, minimum=0.01, maximum=0.99
        ),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
    )


def create_reference_blockout(context, args):
    mass_settings = args.get("mass_settings")
    return reference_blockout.create_reference_blockout(
        context,
        collection_name=str(args.get("collection_name") or ""),
        camera_name=str(args.get("camera_name") or ""),
        mass_names=_name_list(args.get("mass_names")),
        mass_settings=mass_settings if isinstance(mass_settings, list) else [],
        name_prefix=str(args.get("name_prefix") or "Reference Blockout"),
        depth_ratio=_bounded_float(
            args.get("depth_ratio"), 0.7, minimum=0.05, maximum=3.0
        ),
        segments=_bounded_int(
            args.get("segments"), 32, minimum=8, maximum=128
        ),
        rings=_bounded_int(
            args.get("rings"), 16, minimum=4, maximum=64
        ),
        max_forms=_bounded_int(
            args.get("max_forms"), 16, minimum=1, maximum=32
        ),
        blend_mode=str(args.get("blend_mode") or "voxel"),
        voxel_size=_bounded_float(
            args.get("voxel_size"), 0.08, minimum=0.001, maximum=10.0
        ),
        smooth_iterations=_bounded_int(
            args.get("smooth_iterations"), 2, minimum=0, maximum=20
        ),
        show_components=bool(args.get("show_components", False)),
        color=_float_list(
            args.get("color"), 4, (0.55, 0.6, 0.68, 1.0)
        ),
        label=str(args.get("label") or "Create reference blockout"),
    )


def apply_procedural_array_stack(context, args):
    return advanced_helpers.apply_procedural_array_stack(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        count=_bounded_int(args.get("count"), 5, minimum=1, maximum=1000),
        relative_offset=_float_list(args.get("relative_offset"), 3, (1.25, 0.0, 0.0)),
        bevel_width=float(args.get("bevel_width", 0.025)),
        bevel_segments=_bounded_int(args.get("bevel_segments"), 2, minimum=1, maximum=32),
        add_weighted_normals=bool(args.get("add_weighted_normals", True)),
        name_prefix=str(args.get("name_prefix") or "Agent Bridge Procedural"),
        label=args.get("label", "Apply procedural array stack"),
    )


def edit_mesh(context, args):
    return advanced_helpers.edit_mesh(
        context,
        operation=str(args.get("operation") or "extrude_faces"),
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        face_scope=str(args.get("face_scope") or "ALL"),
        direction=str(args.get("direction") or "NORMAL"),
        axis=str(args.get("axis") or "Z"),
        distance=_bounded_float(args.get("distance"), 0.25, minimum=-100.0, maximum=100.0),
        inset_thickness=_bounded_float(args.get("inset_thickness"), 0.05, minimum=0.0, maximum=100.0),
        inset_depth=_bounded_float(args.get("inset_depth"), 0.0, minimum=-100.0, maximum=100.0),
        merge_distance=_bounded_float(args.get("merge_distance"), 0.0001, minimum=0.0, maximum=10.0),
        loop_cuts=_bounded_int(args.get("loop_cuts"), 1, minimum=1, maximum=32),
        cut_axis=str(args.get("cut_axis") or "Z"),
        cut_position=_bounded_float(args.get("cut_position"), 0.0, minimum=-1000.0, maximum=1000.0),
        proportional_center=_float_list(args.get("proportional_center"), 3, (0.0, 0.0, 0.0)),
        proportional_radius=_bounded_float(args.get("proportional_radius"), 1.0, minimum=0.0001, maximum=1000.0),
        proportional_falloff=str(args.get("proportional_falloff") or "SMOOTH"),
        allow_shape_keys=bool(args.get("allow_shape_keys", False)),
        label=args.get("label", "Edit mesh"),
    )


def inspect_modeling_quality(context, args):
    return advanced_helpers.inspect_modeling_quality(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        include_children=bool(args.get("include_children", True)),
        require_materials=bool(args.get("require_materials", True)),
        allow_modifier_seed_boundaries=bool(args.get("allow_modifier_seed_boundaries", True)),
        scale_tolerance=_bounded_float(args.get("scale_tolerance"), 0.001, minimum=0.0, maximum=1.0),
        max_objects=_bounded_int(args.get("max_objects"), 64, minimum=1, maximum=256),
    )


def curve_to_mesh(context, args):
    return advanced_helpers.curve_to_mesh(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        name_prefix=str(args.get("name_prefix") or "Agent Bridge Mesh "),
        hide_original=bool(args.get("hide_original", False)),
        label=args.get("label", "Convert curve to mesh"),
    )


def boolean_op(context, args):
    return advanced_helpers.boolean_op(
        context,
        target_object_name=str(args.get("target_object_name") or ""),
        cutter_object_names=_name_list(args.get("cutter_object_names")),
        operation=str(args.get("operation") or "DIFFERENCE"),
        solver=str(args.get("solver") or "FAST"),
        name_prefix=str(args.get("name_prefix") or "Agent Bridge Boolean"),
        label=args.get("label", "Apply boolean operation"),
    )


def mirror_model(context, args):
    return advanced_helpers.mirror_model(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        use_axis=args.get("use_axis"),
        mirror_object_name=str(args.get("mirror_object_name") or ""),
        bisect_axis=args.get("bisect_axis"),
        flip_axis=args.get("flip_axis"),
        use_clip=bool(args.get("use_clip", False)),
        use_mirror_merge=bool(args.get("use_mirror_merge", True)),
        merge_threshold=_bounded_float(args.get("merge_threshold"), 0.001, minimum=0.0, maximum=10.0),
        name=str(args.get("name") or "Agent Bridge Mirror"),
        label=args.get("label", "Mirror model"),
    )


def symmetrize_model(context, args):
    return advanced_helpers.symmetrize_model(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        axis=str(args.get("axis") or "X"),
        direction=str(args.get("direction") or "POSITIVE_TO_NEGATIVE"),
        merge_threshold=_bounded_float(args.get("merge_threshold"), 0.001, minimum=0.0, maximum=10.0),
        name=str(args.get("name") or "Agent Bridge Symmetry"),
        label=args.get("label", "Symmetrize model"),
    )


def solidify_model(context, args):
    return advanced_helpers.solidify_model(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        thickness=_bounded_float(args.get("thickness"), 0.1, minimum=-10.0, maximum=10.0),
        offset=_bounded_float(args.get("offset"), 0.0, minimum=-1.0, maximum=1.0),
        use_even_offset=bool(args.get("use_even_offset", True)),
        name=str(args.get("name") or "Agent Bridge Solidify"),
        label=args.get("label", "Solidify model"),
    )


def screw_model(context, args):
    return advanced_helpers.screw_model(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        axis=str(args.get("axis") or "Z"),
        angle=_bounded_float(args.get("angle"), 6.283185307179586, minimum=-201.06192982974676, maximum=201.06192982974676),
        screw_offset=_bounded_float(args.get("screw_offset"), 0.0, minimum=-1000.0, maximum=1000.0),
        iterations=_bounded_int(args.get("iterations"), 1, minimum=1, maximum=256),
        steps=_bounded_int(args.get("steps"), 16, minimum=1, maximum=512),
        render_steps=_bounded_int(args.get("render_steps"), 32, minimum=1, maximum=1024),
        use_merge_vertices=bool(args.get("use_merge_vertices", False)),
        merge_threshold=_bounded_float(args.get("merge_threshold"), 0.001, minimum=0.0, maximum=10.0),
        use_smooth_shade=bool(args.get("use_smooth_shade", True)),
        name=str(args.get("name") or "Agent Bridge Screw"),
        label=args.get("label", "Screw model"),
    )




def register(handler_registry, specs):
    for spec in specs:
        try:
            handler = globals()[spec.handler_key]
        except KeyError as exc:
            raise KeyError(f"Missing handler {spec.handler_key} for {spec.name}") from exc
        handler_registry.register(spec.name, handler)
