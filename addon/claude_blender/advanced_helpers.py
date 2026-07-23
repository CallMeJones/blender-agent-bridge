"""Compatibility facade for domain-owned advanced Blender helpers."""

# Re-exports are the purpose of this module.
# ruff: noqa: F401

from __future__ import annotations

from .advanced_animation import (
    add_action_cycles,
    add_breakdown_pose,
    animate_light_property,
    animate_material_property,
    animate_object_bounce,
    animate_shape_key,
    block_key_poses,
    clear_animation,
    create_camera_dolly_animation,
    create_follow_path_animation,
    create_motion_arc,
    create_progressive_bounce_animation,
    create_pulse_animation,
    create_reveal_animation,
    create_shape_key,
    create_staggered_motion,
    create_turntable_animation,
    retime_actions,
    set_action_interpolation,
    set_animation_preview_range,
    set_pose_hold,
)
from .advanced_camera_render import (
    apply_lighting_preset,
    configure_render_outputs,
    create_lookdev_turntable_review,
    create_product_turntable_setup,
    create_studio_product_stage,
    set_camera_settings,
    set_render_engine,
    set_render_settings,
    set_world_background,
)
from .advanced_materials import (
    add_geometry_nodes_modifier,
    add_window_materials,
    bake_maps,
    create_image_texture_material,
    create_material_palette,
    create_procedural_texture_material,
    create_shader_material,
    inspect_material_setup,
    inspect_uv_layout,
    mark_uv_seams,
    repair_material_setup,
    uv_unwrap,
)
from .advanced_modeling import (
    apply_procedural_array_stack,
    boolean_op,
    create_curve_path,
    create_text_object,
    curve_to_mesh,
    edit_mesh,
    inspect_modeling_quality,
    mirror_model,
    screw_model,
    solidify_model,
    symmetrize_model,
)
from .advanced_rigging import (
    add_cloth_simulation_to_selected,
    add_copy_transform_constraint,
    add_particle_system_to_selected,
    apply_rig_action_clip,
    apply_rig_pose_from_action,
    apply_rig_pose_marker,
    create_basic_armature,
    get_rig_pose_library_details,
    offset_rig_limb_controls,
    set_rig_custom_property_keyframes,
    set_rig_pose_hold,
)
from .advanced_scene_editing import (
    align_selected_objects,
    create_empty,
    distribute_selected_objects,
    duplicate_selected_objects,
    parent_selected_to_empty,
    set_object_display,
    set_object_visibility,
)
from .advanced_presentation import (
    add_bevel_and_subsurf,
    add_dimension_callouts,
    add_panel_seams,
    create_wheel_assembly,
    organize_scene_for_production,
    prepare_imported_asset_presentation,
    shade_smooth_selected,
)
from .advanced_support import _link_object_like_source, _restore_selection_snapshot, _selection_snapshot
from .two_d_inspection import get_2d_animation_details
from .workflow_planning import plan_advanced_scene_workflow, plan_asset_import_workflow, plan_director_workflow


def register():
    pass


def unregister():
    pass
