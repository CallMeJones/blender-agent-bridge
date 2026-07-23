"""Blender-only handlers for the modeling domain."""

from __future__ import annotations

from .. import advanced_modeling as advanced_helpers
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
