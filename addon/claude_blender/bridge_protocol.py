"""Semantic bridge contract for JSON bridge and MCP access.

The Blender extension owns real scene reads/writes through bpy. A local
companion process exposes these tool names over MCP without changing the core
tool semantics.
"""

from __future__ import annotations


BRIDGE_VERSION = "0.2"


TOOL_CONTRACTS = {
    "inspect_scene": {
        "description": "Return a compact context bundle for the active Blender scene",
        "mutates_scene": False,
    },
    "list_scene_objects": {
        "description": "Return object names, types, selection, visibility, collections, and locations",
        "mutates_scene": False,
    },
    "get_object_details": {
        "description": "Return deeper details for a named Blender object",
        "mutates_scene": False,
    },
    "get_animation_details": {
        "description": "Return scene timeline, action, f-curve, and keyframe details",
        "mutates_scene": False,
    },
    "get_material_node_details": {
        "description": "Return material node, socket, and link details",
        "mutates_scene": False,
    },
    "get_geometry_nodes_details": {
        "description": "Return Geometry Nodes modifier and node-group summaries",
        "mutates_scene": False,
    },
    "get_shader_nodes_details": {
        "description": "Return shader node tree, node, link, and driver summaries",
        "mutates_scene": False,
    },
    "get_rigging_details": {
        "description": "Return armature, bone, pose, constraint, and driver summaries",
        "mutates_scene": False,
    },
    "get_shape_key_details": {
        "description": "Return mesh shape key block, value, range, and driver summaries",
        "mutates_scene": False,
    },
    "get_curve_text_details": {
        "description": "Return curve spline and text object summaries",
        "mutates_scene": False,
    },
    "get_simulation_details": {
        "description": "Return particle system and simulation modifier summaries",
        "mutates_scene": False,
    },
    "get_collection_layer_details": {
        "description": "Return collection tree, membership, visibility, and view-layer summaries",
        "mutates_scene": False,
    },
    "get_render_camera_compositor_details": {
        "description": "Return render, camera, world, and compositor summaries",
        "mutates_scene": False,
    },
    "search_blender_docs": {
        "description": "Search local cached official Blender docs before online docs",
        "mutates_scene": False,
    },
    "set_selected_location_delta": {
        "description": "Move selected Blender objects by a delta with rollback state",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "set_selected_transform": {
        "description": "Set absolute location, rotation, and/or scale for selected objects",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "select_objects": {
        "description": "Select named objects and optionally set the active object",
        "mutates_scene": True,
    },
    "set_current_frame": {
        "description": "Set the current scene frame/playhead",
        "mutates_scene": True,
    },
    "create_primitive": {
        "description": "Create a mesh primitive with transform values",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "assign_material_to_selected": {
        "description": "Create or update a material and assign it to selected mesh objects",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "assign_emission_material_to_selected": {
        "description": "Create a new emission material node setup and assign it to selected mesh objects",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_collection": {
        "description": "Create or find a collection in the current scene",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "link_selected_to_collection": {
        "description": "Link selected objects to a named collection without deleting existing links",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_modifier_to_selected": {
        "description": "Add a bounded common modifier to selected mesh objects",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_shader_material": {
        "description": "Create or update a Principled BSDF material and optionally assign it",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_geometry_nodes_modifier": {
        "description": "Add a valid passthrough Geometry Nodes modifier and node group",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_shape_key": {
        "description": "Create or update a mesh shape key value",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "animate_shape_key": {
        "description": "Keyframe a mesh shape key value over a frame range",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_text_object": {
        "description": "Create a text object with transform and optional material",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_curve_path": {
        "description": "Create a 3D curve path from points",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_particle_system_to_selected": {
        "description": "Add a bounded particle system to selected mesh objects",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_basic_armature": {
        "description": "Create a simple one-bone armature object",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_copy_transform_constraint": {
        "description": "Add a copy transform-style constraint to selected objects",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "set_render_settings": {
        "description": "Set render engine, resolution, FPS, frame range, and transparency",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "set_camera_settings": {
        "description": "Set active or named camera lens and depth-of-field settings",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "set_world_background": {
        "description": "Set scene world background color",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "shade_smooth_selected": {
        "description": "Shade selected mesh polygons smooth and optionally add weighted normals",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_bevel_and_subsurf": {
        "description": "Add a bounded bevel/subdivision/weighted-normal refinement stack",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_wheel_assembly": {
        "description": "Create a tire/rim wheel assembly from primitives",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_panel_seams": {
        "description": "Add simple curve panel seams around a mesh object's bounds",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_window_materials": {
        "description": "Create glass material and optional window panels for a mesh object's bounds",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "apply_vehicle_refinement_template": {
        "description": "Apply a bounded vehicle detail kit with wheels, windows, seams, lights, and smoothing",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_track_to_constraint": {
        "description": "Add a Track To constraint from selected object(s) to a target object",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_light": {
        "description": "Add a light object to the live scene",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_camera": {
        "description": "Add a camera object and set it as active",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "set_scene_frame_range": {
        "description": "Set timeline frame range, current frame, and FPS",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "set_active_camera": {
        "description": "Set an existing camera object as the active scene camera",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "animate_selected_transform": {
        "description": "Create simple transform keyframes for selected objects",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_camera_orbit": {
        "description": "Create a keyframed camera orbit rig around a target object",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "commit_preview": {
        "description": "Commit the current live preview transaction",
        "mutates_scene": True,
    },
    "revert_preview": {
        "description": "Revert the current live preview transaction",
        "mutates_scene": True,
    },
    "draft_script": {
        "description": "Stage generated Blender Python in a Text datablock for explicit user approval",
        "mutates_scene": False,
        "requires_approval": True,
    },
    "run_approved_script": {
        "description": "Run generated Blender Python after explicit user approval",
        "mutates_scene": True,
        "requires_approval": True,
    },
}


def list_tool_contracts():
    return {
        "bridge_version": BRIDGE_VERSION,
        "tools": TOOL_CONTRACTS,
    }


def register():
    pass


def unregister():
    pass
