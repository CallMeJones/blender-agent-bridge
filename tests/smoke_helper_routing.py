"""Smoke tests for script-first authoring and bounded operational routing."""

from __future__ import annotations

import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import agent_tools, bridge_protocol, helper_routing  # noqa: E402


def _known_tool_names():
    return {tool["name"] for tool in agent_tools.blender_tool_definitions()} | set(bridge_protocol.TOOL_CONTRACTS)


def main():
    known_tools = _known_tool_names()
    missing_groups = helper_routing.HELPER_FIRST_SCRIPT_GROUPS - set(agent_tools._TOOL_GROUPS)
    assert not missing_groups, missing_groups
    for group in helper_routing.HELPER_FIRST_SCRIPT_GROUPS:
        assert agent_tools._TOOL_GROUPS[group], group

    rules = list(helper_routing.iter_helper_first_script_rules())
    assert rules, "expected bounded-helper advisory rules"

    for prompt in (
        "Match the reference image while modeling this character's silhouette and proportions.",
        "Review this mesh against the attached photo and repair its form continuity.",
        "Improve the model quality and landmark placement of this prop.",
        "Build a 3D model from image and run a quality pass.",
    ):
        assert helper_routing.is_reference_model_quality_request(prompt), prompt
    for prompt in (
        "Animate this character waving.",
        "Create a product reference sheet.",
        "Use this character as a reference for the story.",
        "Add fur to the selected object.",
    ):
        assert not helper_routing.is_reference_model_quality_request(prompt), prompt

    codes = set()
    for rule in rules:
        code = str(rule.get("code") or "")
        assert code and code not in codes, rule
        codes.add(code)
        assert rule.get("message"), rule
        assert rule.get("terms"), rule
        recommended_tools = list(rule.get("recommended_tools") or [])
        assert recommended_tools, rule
        for tool_name in recommended_tools:
            assert tool_name not in {"draft_script", "run_approved_script"}, (code, tool_name)
            assert tool_name in known_tools, (code, tool_name)

    helper_prompt = "Write a Python script to move the selected cube up and make it red."
    assert helper_routing.should_include_draft_script(helper_prompt, ["basic_edit", "materials"])

    for authored_prompt in (
        "Create a realistic cartoon cat from the supplied brief.",
        "Animate this character waving with secondary motion.",
        "Create a procedural marble material and custom shader nodes.",
        "Rig this character with custom controls and drivers.",
        "Build a product scene, animate a reveal, render frames, and capture viewport evidence.",
        "Import a Poly Haven asset, build a robot, animate it, and render frames.",
        "Create a new project, build a robot, and save the blend.",
    ):
        assert helper_routing.is_script_first_authored_request(authored_prompt), authored_prompt
        assert helper_routing.should_include_draft_script(
            authored_prompt,
            ["advanced_create", "animation", "materials", "rigging"],
        ), authored_prompt

    for helper_override in (
        "Use helpers only to create a procedural material for the selected object.",
        "Create a procedural material with helpers.",
        "Use the helper path to build a robot.",
        "Use helper-based tools to animate the selected object.",
    ):
        assert helper_routing.prefers_bounded_helpers(helper_override), helper_override
        assert not helper_routing.is_script_first_authored_request(helper_override), helper_override
        assert not helper_routing.should_include_draft_script(
            helper_override,
            ["materials", "animation", "advanced_workflow"],
        ), helper_override
    helper_override = "Use helpers only to create a procedural material for the selected object."
    for script_preference in (
        "Do not use helpers; build the robot with a cohesive script.",
        "Use a script, not the helper path, to animate the character.",
    ):
        assert not helper_routing.prefers_bounded_helpers(
            script_preference
        ), script_preference
        assert helper_routing.is_script_first_authored_request(
            script_preference
        ), script_preference

    for operational_prompt in (
        "Create a new Blender project.",
        "Render the final animation.",
        "Find a Poly Haven model, download it, import it, and make a studio presentation.",
    ):
        assert not helper_routing.is_script_first_authored_request(
            operational_prompt
        ), operational_prompt
    assert helper_routing.project_file_operation_kinds(
        "Create a new Blender project."
    ) == {"create"}
    assert helper_routing.is_render_job_request("Render the final animation.")
    assert helper_routing.is_authored_animation_request(
        "Animate this character waving and repair the timing."
    )
    assert not helper_routing.is_authored_animation_request(
        "Render the final animation."
    )
    assert helper_routing.is_animation_workflow_request(
        "Review the playblast timing and spacing."
    )
    assert helper_routing.is_animation_workflow_request(
        "Inspect the current animation state."
    )
    for static_motion_prompt in (
        "Build a wave machine.",
        "Create an orbit sculpture.",
        "Build a reveal mechanism.",
    ):
        assert not helper_routing.is_authored_animation_request(
            static_motion_prompt
        ), static_motion_prompt
        selected_tools, metadata = agent_tools.select_blender_tool_definitions(
            static_motion_prompt
        )
        selected_names = {tool["name"] for tool in selected_tools}
        assert "draft_script" in selected_names, (static_motion_prompt, metadata)
        assert "run_animation_task" not in selected_names, (
            static_motion_prompt,
            metadata,
        )
    assert helper_routing.is_authored_animation_request(
        "Make the character wave."
    )
    assert helper_routing.is_authored_animation_request(
        "Render frames after animating the character."
    )
    wave_tools, wave_metadata = agent_tools.select_blender_tool_definitions(
        "Make the character wave."
    )
    wave_names = {tool["name"] for tool in wave_tools}
    assert "draft_script" in wave_names, wave_metadata
    assert "run_animation_task" in wave_names, wave_metadata
    assert helper_routing.is_script_first_authored_request(
        "Save the blend after creating a material."
    )
    assert helper_routing.project_file_operation_kinds(
        "Open this blend and animate the character."
    ) == {"open"}
    assert helper_routing.is_lookdev_review_request(
        "Create a lookdev turntable review."
    )
    lookdev_tools, lookdev_metadata = agent_tools.select_blender_tool_definitions(
        "Create a lookdev turntable review."
    )
    assert "create_lookdev_turntable_review" in {
        tool["name"] for tool in lookdev_tools
    }, lookdev_metadata
    script_preflight = helper_routing.script_authoring_preflight()
    assert "bpy.app.version" in script_preflight["version_check"], script_preflight
    assert "enum_items" in script_preflight["enum_check"], script_preflight

    custom_prompt = "Draft a custom procedural material node network that helpers cannot express."
    assert helper_routing.should_include_draft_script(custom_prompt, ["materials"])
    assert not helper_routing.should_include_draft_script(
        "Draft a custom Python script to download and import a Poly Haven sunset HDRI.",
        ["external_assets"],
    )
    assert helper_routing.should_include_privileged_script(
        "Draft a custom Python script to download and import a Poly Haven sunset HDRI.",
        ["external_assets"],
    )
    assert not helper_routing.should_include_draft_script(
        "Draft a custom Python script to save this blend file.",
        ["project_files"],
    )
    assert helper_routing.should_include_privileged_script(
        "Draft a custom Python script to save this blend file.",
        ["project_files"],
    )
    assert not helper_routing.should_include_privileged_script(custom_prompt, ["materials"])

    material_guard = helper_routing.helper_first_script_advisory(
        "Make the selected cube red with bpy.data.materials and a material script."
    )
    assert material_guard is None, material_guard
    explicit_material_helper = helper_routing.helper_first_script_advisory(helper_override)
    assert explicit_material_helper["code"] == "material_helper_required", explicit_material_helper
    assert "create_shader_material" in explicit_material_helper["recommended_tools"], explicit_material_helper
    texture_guard = helper_routing.helper_first_script_advisory(
        "Apply a local base color image texture and normal map to the selected cube with a material script."
    )
    assert texture_guard is None, texture_guard
    map_bake_guard = helper_routing.helper_first_script_advisory(
        "Write Python to run bpy.ops.object.bake for AO, normal, and diffuse maps."
    )
    assert map_bake_guard and "bake_maps" in map_bake_guard["recommended_tools"], map_bake_guard
    assert helper_routing.helper_first_script_guard(
        "Make the selected cube red with bpy.data.materials and a material script."
    ) is None

    advanced_guard = helper_routing.helper_first_script_advisory(
        "Write a Python script for a director workflow plan across asset import, animation, evidence, and preview commit."
    )
    assert advanced_guard["code"] == "advanced_workflow_helper_required", advanced_guard
    assert "plan_director_workflow" in advanced_guard["recommended_tools"], advanced_guard

    storyboard_guard = helper_routing.helper_first_script_advisory(
        "Write a Python script to create a storyboard animatic with 2D panels."
    )
    assert storyboard_guard is None, storyboard_guard

    procedural_guard = helper_routing.helper_first_script_advisory(
        "Write Python for a non-destructive procedural array stack with bevels."
    )
    assert procedural_guard is None, procedural_guard

    modeling_guard = helper_routing.helper_first_script_advisory(
        "Write Python for a boolean cutter, mirror modifier, symmetry pass, solidify thickness, and screw thread."
    )
    assert modeling_guard is None, modeling_guard

    edit_mesh_guard = helper_routing.helper_first_script_advisory(
        "Write Python to extrude faces, inset panels, loop cut, knife cut, proportional edit, bridge edge loops, merge by distance, and convert curve to mesh."
    )
    assert edit_mesh_guard is None, edit_mesh_guard

    quality_guard = helper_routing.helper_first_script_advisory(
        "Write Python to validate model mesh quality, non-manifold edges, loose geometry, and missing materials."
    )
    assert quality_guard["code"] == "procedural_3d_helper_required", quality_guard
    assert "inspect_modeling_quality" in quality_guard["recommended_tools"], quality_guard

    modular_guard = helper_routing.helper_first_script_advisory(
        "Write Python for a modular wall panel object kit with pipe run details."
    )
    assert modular_guard is None, modular_guard

    cloth_guard = helper_routing.helper_first_script_advisory(
        "Draft a script to add cloth simulation setup to the selected mesh."
    )
    assert cloth_guard["code"] == "simulation_setup_helper_required", cloth_guard
    assert not cloth_guard["blocked"], cloth_guard
    assert "add_cloth_simulation_to_selected" in cloth_guard["recommended_tools"], cloth_guard

    asset_guard = helper_routing.helper_first_script_guard(
        "Write a Python script to download and import a Poly Haven sunset HDRI."
    )
    assert asset_guard["blocked"], asset_guard
    assert asset_guard["code"] == "external_asset_workflow_required", asset_guard
    assert "plan_asset_import_workflow" in asset_guard["recommended_tools"], asset_guard
    assert "prepare_imported_asset_presentation" in asset_guard["recommended_tools"], asset_guard

    custom_asset_guard = helper_routing.helper_first_script_guard(
        "Write a custom Python script to download and import a Poly Haven sunset HDRI."
    )
    assert custom_asset_guard["blocked"], custom_asset_guard
    assert custom_asset_guard["code"] == "external_asset_workflow_required", custom_asset_guard

    bake_guard = helper_routing.helper_first_script_guard(
        "Draft Python to run bpy.ops.ptcache.bake_all and free_bake_all."
    )
    assert bake_guard["blocked"], bake_guard
    assert bake_guard["code"] == "simulation_helper_required", bake_guard

    assert helper_routing.helper_first_script_guard(custom_prompt) is None
    print("smoke_helper_routing: ok")


if __name__ == "__main__":
    main()
