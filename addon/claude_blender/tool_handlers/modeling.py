"""Blender-only handlers for the modeling domain."""

from __future__ import annotations

from .. import (
    adaptive_remesh as adaptive_remesh_tool,
    advanced_modeling as advanced_helpers,
    preferences,
    reference_blockout,
    reference_comparison,
    reference_feature_stacks,
    reference_guides,
    reference_fur_flow,
    reference_image_intake,
    reference_multiview_scene,
    reference_part_scene,
    reference_surface_fitting,
    reference_visual_hull,
    semantic_sculpt,
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


def prepare_reference_images(context, args):
    return reference_image_intake.prepare_reference_images(
        context,
        references=args.get("references") if isinstance(args.get("references"), list) else [],
        subject=str(args.get("subject") or "reference model"),
        collection_name=str(
            args.get("collection_name") or "Reference Image Intake Guides"
        ),
        subject_center=_float_list(
            args.get("subject_center"), 3, (0.0, 0.0, 1.5)
        ),
        active_view=str(args.get("active_view") or ""),
        create_guides=bool(args.get("create_guides", True)),
        require_annotations=bool(args.get("require_annotations", False)),
        max_mask_axis=_bounded_int(
            args.get("max_mask_axis"), 256, minimum=16, maximum=512
        ),
        label=str(args.get("label") or "Prepare reference images"),
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


def create_multiview_visual_hull(context, args):
    overrides = args.get("outline_overrides")
    return reference_visual_hull.create_multiview_visual_hull(
        context,
        collection_name=str(args.get("collection_name") or ""),
        view_names=_name_list(args.get("view_names")),
        outline_overrides=overrides if isinstance(overrides, list) else [],
        object_name=str(args.get("object_name") or "Reference Visual Hull"),
        bounds_center=_optional_float_list(
            args.get("bounds_center"), 3, (0.0, 0.0, 0.0)
        ),
        bounds_size=_optional_float_list(
            args.get("bounds_size"), 3, (1.0, 1.0, 1.0)
        ),
        bounds_padding=_bounded_float(
            args.get("bounds_padding"), 0.05, minimum=0.0, maximum=0.5
        ),
        resolution=_bounded_int(
            args.get("resolution"), 48, minimum=8, maximum=80
        ),
        component_mode=str(args.get("component_mode") or "largest"),
        minimum_component_voxels=_bounded_int(
            args.get("minimum_component_voxels"), 8, minimum=1, maximum=100000
        ),
        smooth_iterations=_bounded_int(
            args.get("smooth_iterations"), 2, minimum=0, maximum=10
        ),
        minimum_view_angle_degrees=_bounded_float(
            args.get("minimum_view_angle_degrees"),
            1.0,
            minimum=0.1,
            maximum=90.0,
        ),
        color=_float_list(args.get("color"), 4, (0.52, 0.58, 0.68, 1.0)),
        label=str(args.get("label") or "Create multi-view visual hull"),
    )


def create_multiview_depth_surface(context, args):
    overrides = args.get("outline_overrides")
    depth_sources = args.get("depth_sources")
    return reference_visual_hull.create_multiview_depth_surface(
        context,
        collection_name=str(args.get("collection_name") or ""),
        view_names=_name_list(args.get("view_names")),
        outline_overrides=overrides if isinstance(overrides, list) else [],
        depth_sources=depth_sources if isinstance(depth_sources, list) else [],
        object_name=str(args.get("object_name") or "Reference Depth Surface"),
        bounds_center=_optional_float_list(
            args.get("bounds_center"), 3, (0.0, 0.0, 0.0)
        ),
        bounds_size=_optional_float_list(
            args.get("bounds_size"), 3, (1.0, 1.0, 1.0)
        ),
        bounds_padding=_bounded_float(
            args.get("bounds_padding"), 0.05, minimum=0.0, maximum=0.5
        ),
        resolution=_bounded_int(
            args.get("resolution"), 48, minimum=8, maximum=80
        ),
        component_mode=str(args.get("component_mode") or "largest"),
        minimum_component_voxels=_bounded_int(
            args.get("minimum_component_voxels"), 8, minimum=1, maximum=100000
        ),
        smooth_iterations=_bounded_int(
            args.get("smooth_iterations"), 2, minimum=0, maximum=10
        ),
        minimum_view_angle_degrees=_bounded_float(
            args.get("minimum_view_angle_degrees"),
            1.0,
            minimum=0.1,
            maximum=90.0,
        ),
        max_depth_axis=_bounded_int(
            args.get("max_depth_axis"), 256, minimum=16, maximum=1024
        ),
        color=_float_list(args.get("color"), 4, (0.48, 0.62, 0.7, 1.0)),
        label=str(args.get("label") or "Create multi-view depth surface"),
    )


def fit_surface_to_multiview_references(context, args):
    prefs = preferences.get_preferences(context)
    overrides = args.get("outline_overrides")
    depth_sources = args.get("depth_sources")
    step_candidates = args.get("step_candidates")
    pinned = args.get("pinned_vertex_indices")
    return reference_surface_fitting.fit_surface_to_multiview_references(
        context,
        object_name=str(args.get("object_name") or ""),
        collection_name=str(args.get("collection_name") or ""),
        view_names=_name_list(args.get("view_names")),
        outline_overrides=overrides if isinstance(overrides, list) else [],
        depth_sources=depth_sources if isinstance(depth_sources, list) else [],
        landmark_names=_name_list(args.get("landmark_names")),
        iterations=_bounded_int(args.get("iterations"), 6, minimum=1, maximum=12),
        step_candidates=(
            step_candidates if isinstance(step_candidates, list) else [0.25, 0.5, 1.0]
        ),
        minimum_improvement=_bounded_float(
            args.get("minimum_improvement"), 0.00001, minimum=0.0, maximum=1.0
        ),
        silhouette_weight=_bounded_float(
            args.get("silhouette_weight"), 1.0, minimum=0.000001, maximum=100.0
        ),
        depth_weight=_bounded_float(
            args.get("depth_weight"), 0.5, minimum=0.0, maximum=100.0
        ),
        landmark_weight=_bounded_float(
            args.get("landmark_weight"), 0.5, minimum=0.0, maximum=100.0
        ),
        worst_view_weight=_bounded_float(
            args.get("worst_view_weight"), 0.25, minimum=0.0, maximum=100.0
        ),
        per_view_regression_tolerance=_bounded_float(
            args.get("per_view_regression_tolerance"),
            0.002,
            minimum=0.0,
            maximum=1.0,
        ),
        regularization=_bounded_float(
            args.get("regularization"), 0.35, minimum=0.0, maximum=1.0
        ),
        propagation_steps=_bounded_int(
            args.get("propagation_steps"), 4, minimum=0, maximum=12
        ),
        propagation_decay=_bounded_float(
            args.get("propagation_decay"), 0.8, minimum=0.0, maximum=1.0
        ),
        feature_preservation=_bounded_float(
            args.get("feature_preservation"), 0.25, minimum=0.0, maximum=1.0
        ),
        maximum_step=_bounded_float(
            args.get("maximum_step"), 0.0, minimum=0.0, maximum=1000.0
        ),
        maximum_total_displacement=_bounded_float(
            args.get("maximum_total_displacement"),
            0.0,
            minimum=0.0,
            maximum=1000.0,
        ),
        preserve_volume=_bounded_float(
            args.get("preserve_volume"), 0.0, minimum=0.0, maximum=1.0
        ),
        pinned_vertex_indices=pinned if isinstance(pinned, list) else [],
        max_depth_axis=_bounded_int(
            args.get("max_depth_axis"), 256, minimum=16, maximum=1024
        ),
        capture_evidence=bool(args.get("capture_evidence", False)),
        evidence_max_axis=_bounded_int(
            args.get("evidence_max_axis"), 256, minimum=64, maximum=1024
        ),
        evidence_mask_threshold=_bounded_float(
            args.get("evidence_mask_threshold"), 0.5, minimum=0.01, maximum=0.99
        ),
        evidence_regression_tolerance=_bounded_float(
            args.get("evidence_regression_tolerance"),
            0.002,
            minimum=0.0,
            maximum=1.0,
        ),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
        max_vertices=_bounded_int(
            args.get("max_vertices"), 100000, minimum=1, maximum=100000
        ),
        label=str(args.get("label") or "Fit surface to multi-view references"),
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


def evaluate_multiview_reference_match(context, args):
    prefs = preferences.get_preferences(context)
    return reference_image_intake.evaluate_multiview_reference_match(
        context,
        collection_name=str(args.get("collection_name") or ""),
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        view_names=_name_list(args.get("view_names")),
        outline_name=str(args.get("outline_name") or ""),
        reference_mask_source=str(args.get("reference_mask_source") or "auto"),
        landmark_targets=(
            args.get("landmark_targets")
            if isinstance(args.get("landmark_targets"), list)
            else []
        ),
        benchmark_profile=str(args.get("benchmark_profile") or "refined"),
        threshold_overrides=(
            args.get("threshold_overrides")
            if isinstance(args.get("threshold_overrides"), dict)
            else {}
        ),
        max_axis=_bounded_int(args.get("max_axis"), 384, minimum=64, maximum=1024),
        mask_threshold=_bounded_float(
            args.get("mask_threshold"), 0.5, minimum=0.01, maximum=0.99
        ),
        edge_weight=_bounded_float(
            args.get("edge_weight"), 0.25, minimum=0.0, maximum=10.0
        ),
        landmark_weight=_bounded_float(
            args.get("landmark_weight"), 0.1, minimum=0.0, maximum=10.0
        ),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
    )


def auto_reference_sculpt_repair(context, args):
    prefs = preferences.get_preferences(context)
    return reference_image_intake.auto_reference_sculpt_repair(
        context,
        object_name=str(args.get("object_name") or ""),
        collection_name=str(args.get("collection_name") or ""),
        view_names=_name_list(args.get("view_names")),
        region_names=_name_list(args.get("region_names")),
        allow_all_vertices=bool(args.get("allow_all_vertices", False)),
        outline_name=str(args.get("outline_name") or ""),
        reference_mask_source=str(args.get("reference_mask_source") or "auto"),
        strength_candidates=(
            args.get("strength_candidates")
            if isinstance(args.get("strength_candidates"), list)
            else []
        ),
        minimum_improvement=_bounded_float(
            args.get("minimum_improvement"), 0.0005, minimum=0.0, maximum=1.0
        ),
        max_controls=_bounded_int(args.get("max_controls"), 4, minimum=1, maximum=8),
        control_step=_bounded_float(
            args.get("control_step"), 0.045, minimum=0.001, maximum=0.2
        ),
        maximum_world_displacement=_bounded_float(
            args.get("maximum_world_displacement"), 0.05, minimum=0.0, maximum=10.0
        ),
        max_axis=_bounded_int(args.get("max_axis"), 256, minimum=64, maximum=1024),
        mask_threshold=_bounded_float(
            args.get("mask_threshold"), 0.5, minimum=0.01, maximum=0.99
        ),
        edge_weight=_bounded_float(
            args.get("edge_weight"), 0.25, minimum=0.0, maximum=10.0
        ),
        landmark_weight=_bounded_float(
            args.get("landmark_weight"), 0.1, minimum=0.0, maximum=10.0
        ),
        landmark_targets=(
            args.get("landmark_targets")
            if isinstance(args.get("landmark_targets"), list)
            else []
        ),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
        label=str(args.get("label") or "Auto reference sculpt repair"),
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


def create_reference_part_graph(context, args):
    return reference_part_scene.create_reference_part_graph(
        context,
        collection_name=str(args.get("collection_name") or ""),
        camera_name=str(args.get("camera_name") or ""),
        active_view=str(args.get("active_view") or ""),
        subject_profile=str(args.get("subject_profile") or "auto"),
        part_hints=(
            args.get("part_hints")
            if isinstance(args.get("part_hints"), list)
            else []
        ),
        mass_names=_name_list(args.get("mass_names")),
        mass_settings=(
            args.get("mass_settings")
            if isinstance(args.get("mass_settings"), list)
            else []
        ),
        name=str(args.get("name") or "Reference Part Graph"),
        depth_ratio=_bounded_float(
            args.get("depth_ratio"), 0.7, minimum=0.05, maximum=3.0
        ),
        max_parts=_bounded_int(
            args.get("max_parts"), 32, minimum=1, maximum=64
        ),
        create_markers=bool(args.get("create_markers", True)),
        label=str(args.get("label") or "Create reference part graph"),
    )


def build_part_aware_base_mesh(context, args):
    return reference_part_scene.build_part_aware_base_mesh(
        context,
        part_graph_collection_name=str(
            args.get("part_graph_collection_name") or ""
        ),
        part_names=_name_list(args.get("part_names")),
        name_prefix=str(args.get("name_prefix") or "Reference Part Base"),
        include_feature_parts=bool(args.get("include_feature_parts", True)),
        blend_organic_parts=bool(args.get("blend_organic_parts", True)),
        voxel_size=_bounded_float(
            args.get("voxel_size"), 0.06, minimum=0.001, maximum=10.0
        ),
        smooth_iterations=_bounded_int(
            args.get("smooth_iterations"), 3, minimum=0, maximum=20
        ),
        segments=_bounded_int(
            args.get("segments"), 32, minimum=8, maximum=128
        ),
        rings=_bounded_int(
            args.get("rings"), 16, minimum=4, maximum=64
        ),
        show_components=bool(args.get("show_components", False)),
        label=str(args.get("label") or "Build part-aware base mesh"),
    )


def create_eye_stack(context, args):
    return reference_feature_stacks.create_eye_stack(
        context,
        part_graph_collection_name=str(
            args.get("part_graph_collection_name") or ""
        ),
        part_names=_name_list(args.get("part_names")),
        name_prefix=str(args.get("name_prefix") or "Reference Eye Stack"),
        iris_color=_float_list(args.get("iris_color"), 4, (0.22, 0.55, 0.78, 1.0)),
        sclera_color=_float_list(args.get("sclera_color"), 4, (0.96, 0.97, 0.95, 1.0)),
        pupil_color=_float_list(args.get("pupil_color"), 4, (0.01, 0.01, 0.012, 1.0)),
        highlight_color=_float_list(args.get("highlight_color"), 4, (1.0, 1.0, 1.0, 1.0)),
        scale=_bounded_float(args.get("scale"), 1.0, minimum=0.05, maximum=10.0),
        protrusion=_bounded_float(
            args.get("protrusion"), 0.0, minimum=-2.0, maximum=2.0
        ),
        create_highlight=bool(args.get("create_highlight", True)),
        segments=_bounded_int(args.get("segments"), 32, minimum=8, maximum=128),
        rings=_bounded_int(args.get("rings"), 16, minimum=4, maximum=64),
        max_parts=_bounded_int(args.get("max_parts"), 8, minimum=1, maximum=32),
        label=str(args.get("label") or "Create eye stack"),
    )


def create_muzzle_stack(context, args):
    return reference_feature_stacks.create_muzzle_stack(
        context,
        part_graph_collection_name=str(
            args.get("part_graph_collection_name") or ""
        ),
        part_names=_name_list(args.get("part_names")),
        name_prefix=str(args.get("name_prefix") or "Reference Muzzle Stack"),
        muzzle_color=_float_list(args.get("muzzle_color"), 4, (0.9, 0.84, 0.78, 1.0)),
        nose_color=_float_list(args.get("nose_color"), 4, (0.86, 0.42, 0.48, 1.0)),
        mouth_color=_float_list(args.get("mouth_color"), 4, (0.08, 0.035, 0.03, 1.0)),
        tongue_color=_float_list(args.get("tongue_color"), 4, (0.9, 0.35, 0.42, 1.0)),
        scale=_bounded_float(args.get("scale"), 1.0, minimum=0.05, maximum=10.0),
        create_nose=bool(args.get("create_nose", True)),
        create_mouth=bool(args.get("create_mouth", True)),
        create_tongue=bool(args.get("create_tongue", False)),
        segments=_bounded_int(args.get("segments"), 32, minimum=8, maximum=128),
        rings=_bounded_int(args.get("rings"), 16, minimum=4, maximum=64),
        max_parts=_bounded_int(args.get("max_parts"), 8, minimum=1, maximum=32),
        label=str(args.get("label") or "Create muzzle stack"),
    )


def create_ear_stack(context, args):
    return reference_feature_stacks.create_ear_stack(
        context,
        part_graph_collection_name=str(
            args.get("part_graph_collection_name") or ""
        ),
        part_names=_name_list(args.get("part_names")),
        name_prefix=str(args.get("name_prefix") or "Reference Ear Stack"),
        outer_color=_float_list(args.get("outer_color"), 4, (0.7, 0.72, 0.74, 1.0)),
        inner_color=_float_list(args.get("inner_color"), 4, (0.86, 0.68, 0.68, 1.0)),
        scale=_bounded_float(args.get("scale"), 1.0, minimum=0.05, maximum=10.0),
        inner_scale=_bounded_float(
            args.get("inner_scale"), 0.62, minimum=0.05, maximum=1.0
        ),
        create_outer_shell=bool(args.get("create_outer_shell", True)),
        create_inner_patch=bool(args.get("create_inner_patch", True)),
        segments=_bounded_int(args.get("segments"), 32, minimum=8, maximum=128),
        rings=_bounded_int(args.get("rings"), 16, minimum=4, maximum=64),
        max_parts=_bounded_int(args.get("max_parts"), 8, minimum=1, maximum=32),
        label=str(args.get("label") or "Create ear stack"),
    )


def create_fur_flow_field_from_parts(context, args):
    return reference_fur_flow.create_fur_flow_field_from_parts(
        context,
        part_graph_collection_name=str(
            args.get("part_graph_collection_name") or ""
        ),
        part_names=_name_list(args.get("part_names")),
        include_roles=_name_list(args.get("include_roles")),
        preset=str(args.get("preset") or "kitten_soft"),
        count=_bounded_int(args.get("count"), 600, minimum=1, maximum=5000),
        max_regions=_bounded_int(args.get("max_regions"), 16, minimum=1, maximum=16),
        apply_groom=bool(args.get("apply_groom", False)),
        use_part_vertex_groups=bool(args.get("use_part_vertex_groups", True)),
        vertex_group_name_prefix=str(
            args.get("vertex_group_name_prefix") or "Reference Part"
        ),
        vertex_group_radius_scale=_bounded_float(
            args.get("vertex_group_radius_scale"), 1.35, minimum=0.05, maximum=100.0
        ),
        vertex_group_falloff_power=_bounded_float(
            args.get("vertex_group_falloff_power"), 2.0, minimum=0.05, maximum=16.0
        ),
        vertex_group_minimum_weight=_bounded_float(
            args.get("vertex_group_minimum_weight"), 0.001, minimum=0.0, maximum=1.0
        ),
        replace_existing_vertex_groups=bool(
            args.get("replace_existing_vertex_groups", True)
        ),
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        name_prefix=str(args.get("name_prefix") or "Reference Fur Flow"),
        material_name=str(args.get("material_name") or ""),
        color=_float_list(args.get("color"), 4, (0.82, 0.82, 0.78, 1.0)),
        seed=_bounded_int(args.get("seed"), 17, minimum=0, maximum=1000000),
        label=str(args.get("label") or "Create fur flow field from parts"),
    )


def create_part_weight_vertex_groups(context, args):
    return reference_fur_flow.create_part_weight_vertex_groups(
        context,
        part_graph_collection_name=str(
            args.get("part_graph_collection_name") or ""
        ),
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        part_names=_name_list(args.get("part_names")),
        include_roles=_name_list(args.get("include_roles")),
        name_prefix=str(args.get("name_prefix") or "Reference Part"),
        radius_scale=_bounded_float(
            args.get("radius_scale"), 1.35, minimum=0.05, maximum=100.0
        ),
        falloff_power=_bounded_float(
            args.get("falloff_power"), 2.0, minimum=0.05, maximum=16.0
        ),
        minimum_weight=_bounded_float(
            args.get("minimum_weight"), 0.001, minimum=0.0, maximum=1.0
        ),
        replace_existing=bool(args.get("replace_existing", True)),
        max_parts=_bounded_int(args.get("max_parts"), 16, minimum=1, maximum=32),
        label=str(args.get("label") or "Create part weight vertex groups"),
    )


def adaptive_remesh(context, args):
    return adaptive_remesh_tool.adaptive_remesh(
        context,
        object_name=str(args.get("object_name") or ""),
        region_names=_name_list(args.get("region_names")),
        target_edge_length=_bounded_float(
            args.get("target_edge_length"), 0.08, minimum=0.000001, maximum=1000.0
        ),
        passes=_bounded_int(args.get("passes"), 2, minimum=1, maximum=6),
        region_detail=_bounded_float(
            args.get("region_detail"), 0.75, minimum=0.0, maximum=1.0
        ),
        curvature_detail=_bounded_float(
            args.get("curvature_detail"), 0.5, minimum=0.0, maximum=1.0
        ),
        relax_iterations=_bounded_int(
            args.get("relax_iterations"), 0, minimum=0, maximum=20
        ),
        relax_factor=_bounded_float(
            args.get("relax_factor"), 0.2, minimum=0.0, maximum=1.0
        ),
        project_to_source=bool(args.get("project_to_source", True)),
        max_vertices=_bounded_int(
            args.get("max_vertices"), 250000, minimum=1, maximum=250000
        ),
        max_result_vertices=_bounded_int(
            args.get("max_result_vertices"), 500000, minimum=1, maximum=500000
        ),
        label=str(args.get("label") or "Adaptive remesh"),
    )


def define_semantic_sculpt_regions(context, args):
    return semantic_sculpt.define_semantic_sculpt_regions(
        context,
        object_name=str(args.get("object_name") or ""),
        regions=args.get("regions") if isinstance(args.get("regions"), list) else [],
        max_vertices=_bounded_int(
            args.get("max_vertices"), 250000, minimum=1, maximum=250000
        ),
        label=str(args.get("label") or "Define semantic sculpt regions"),
    )


def inspect_semantic_sculpt_regions(context, args):
    return semantic_sculpt.inspect_semantic_sculpt_regions(
        context,
        object_name=str(args.get("object_name") or ""),
        include_weights=bool(args.get("include_weights", False)),
        max_weights=_bounded_int(
            args.get("max_weights"), 256, minimum=1, maximum=4096
        ),
    )


def _screen_sculpt_options(args, *, default_max_vertices):
    return {
        "object_name": str(args.get("object_name") or ""),
        "collection_name": str(args.get("collection_name") or ""),
        "camera_name": str(args.get("camera_name") or ""),
        "region_names": _name_list(args.get("region_names")),
        "controls": (
            args.get("controls") if isinstance(args.get("controls"), list) else []
        ),
        "origin": str(args.get("origin") or "top_left"),
        "allow_all_vertices": bool(args.get("allow_all_vertices", False)),
        "front_faces_only": bool(args.get("front_faces_only", True)),
        "front_face_threshold": _bounded_float(
            args.get("front_face_threshold"), -0.25, minimum=-1.0, maximum=1.0
        ),
        "maximum_world_displacement": _bounded_float(
            args.get("maximum_world_displacement"),
            0.0,
            minimum=0.0,
            maximum=1000.0,
        ),
        "symmetry_axis": str(args.get("symmetry_axis") or "NONE"),
        "symmetry_tolerance": _bounded_float(
            args.get("symmetry_tolerance"), 1e-4, minimum=1e-8, maximum=1.0
        ),
        "preserve_volume": _bounded_float(
            args.get("preserve_volume"), 0.0, minimum=0.0, maximum=1.0
        ),
        "max_vertices": _bounded_int(
            args.get("max_vertices"),
            default_max_vertices,
            minimum=1,
            maximum=250000,
        ),
    }


def apply_semantic_sculpt(context, args):
    arguments = args.get("arguments")
    return semantic_sculpt.apply_semantic_sculpt(
        context,
        object_name=str(args.get("object_name") or ""),
        region_names=_name_list(args.get("region_names")),
        operation=str(args.get("operation") or "translate"),
        arguments=arguments if isinstance(arguments, dict) else {},
        allow_all_vertices=bool(args.get("allow_all_vertices", False)),
        max_vertices=_bounded_int(
            args.get("max_vertices"), 250000, minimum=1, maximum=250000
        ),
        label=str(args.get("label") or "Apply semantic sculpt"),
    )


def apply_form_aware_sculpt(context, args):
    return semantic_sculpt.apply_form_aware_sculpt(
        context,
        object_name=str(args.get("object_name") or ""),
        region_names=_name_list(args.get("region_names")),
        operation=str(args.get("operation") or "tangent_relax"),
        strength=_bounded_float(
            args.get("strength"), 0.25, minimum=-1.0, maximum=1.0
        ),
        crease_depth=_bounded_float(
            args.get("crease_depth"), 0.0, minimum=-1000.0, maximum=1000.0
        ),
        center=_optional_float_list(args.get("center"), 3, (0.0, 0.0, 0.0)),
        coordinate_space=str(args.get("coordinate_space") or "local"),
        iterations=_bounded_int(args.get("iterations"), 1, minimum=1, maximum=50),
        falloff_steps=_bounded_int(
            args.get("falloff_steps"), 0, minimum=0, maximum=64
        ),
        falloff_decay=_bounded_float(
            args.get("falloff_decay"), 0.75, minimum=0.0, maximum=1.0
        ),
        feature_preservation=_bounded_float(
            args.get("feature_preservation"), 0.5, minimum=0.0, maximum=1.0
        ),
        maximum_world_displacement=_bounded_float(
            args.get("maximum_world_displacement"),
            0.0,
            minimum=0.0,
            maximum=1000.0,
        ),
        symmetry_axis=str(args.get("symmetry_axis") or "NONE"),
        symmetry_tolerance=_bounded_float(
            args.get("symmetry_tolerance"), 1e-4, minimum=1e-8, maximum=1.0
        ),
        preserve_volume=_bounded_float(
            args.get("preserve_volume"), 0.0, minimum=0.0, maximum=1.0
        ),
        allow_all_vertices=bool(args.get("allow_all_vertices", False)),
        max_vertices=_bounded_int(
            args.get("max_vertices"), 250000, minimum=1, maximum=250000
        ),
        label=str(args.get("label") or "Apply form-aware sculpt"),
    )


def apply_screen_space_sculpt(context, args):
    return semantic_sculpt.apply_screen_space_sculpt(
        context,
        strength=_bounded_float(
            args.get("strength"), 1.0, minimum=-4.0, maximum=4.0
        ),
        label=str(args.get("label") or "Apply screen-space sculpt"),
        **_screen_sculpt_options(args, default_max_vertices=250000),
    )


def optimize_screen_space_sculpt(context, args):
    prefs = preferences.get_preferences(context)
    return semantic_sculpt.optimize_screen_space_sculpt(
        context,
        outline_name=str(args.get("outline_name") or ""),
        reference_mask_source=str(args.get("reference_mask_source") or "auto"),
        strength_candidates=(
            args.get("strength_candidates")
            if isinstance(args.get("strength_candidates"), list)
            else []
        ),
        minimum_improvement=_bounded_float(
            args.get("minimum_improvement"), 0.0005, minimum=0.0, maximum=1.0
        ),
        edge_weight=_bounded_float(
            args.get("edge_weight"), 0.25, minimum=0.0, maximum=10.0
        ),
        landmark_weight=_bounded_float(
            args.get("landmark_weight"), 0.1, minimum=0.0, maximum=10.0
        ),
        landmark_targets=(
            args.get("landmark_targets")
            if isinstance(args.get("landmark_targets"), list)
            else []
        ),
        max_axis=_bounded_int(
            args.get("max_axis"), 256, minimum=64, maximum=1024
        ),
        mask_threshold=_bounded_float(
            args.get("mask_threshold"), 0.5, minimum=0.01, maximum=0.99
        ),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
        label=str(args.get("label") or "Optimize screen-space sculpt"),
        **_screen_sculpt_options(args, default_max_vertices=100000),
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
