"""Fixture-driven offline routing checks for MCP client-shaped profiles."""

from __future__ import annotations

import json
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import agent_tools  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "addon", "claude_blender"))
import mcp_server  # noqa: E402


class OfflineBridge:
    base_url = "http://127.0.0.1:8765"

    def get(self, path, params=None):
        if path == "/tools":
            return {"ok": True, "tools": mcp_server._static_tool_definitions()}
        if path == "/health":
            return {
                "ok": True,
                "bridge_version": mcp_server.bridge_protocol.BRIDGE_VERSION,
                "addon_version": mcp_server.build_info.ADDON_VERSION,
                "tool_registry_digest": mcp_server.build_info.TOOL_REGISTRY_DIGEST,
            }
        raise RuntimeError("offline routing smoke uses static tool contracts")

    def post(self, path, payload, timeout=None):
        assert path == "/tool", (path, payload)
        return {
            "ok": True,
            "result": {
                "ok": True,
                "executed_tool": payload["name"],
                "arguments": payload["arguments"],
            },
        }


CLIENT_PROFILES = [
    {"id": "claude", "clientInfo": {"name": "claude-desktop", "version": "routing-eval"}},
    {"id": "codex", "clientInfo": {"name": "codex", "version": "routing-eval"}},
    {"id": "cursor", "clientInfo": {"name": "cursor", "version": "routing-eval"}},
]


ROUTING_FIXTURES = [
    {
        "id": "animation_script_first",
        "prompt": "Make the selected cube bounce twice, get smaller each bounce, capture a playblast, review it, repair issues, and leave it as a preview.",
        "must_select": ["draft_script", "plan_animation_workflow", "run_animation_workflow", "capture_animation_playblast", "review_playblast_against_brief", "run_animation_repair_loop"],
        "must_not_select": [],
        "search": "Make the selected cube bounce twice, get smaller each bounce, capture a playblast, review it, repair issues, and leave it as a preview.",
        "search_before": [("draft_script", "run_animation_workflow")],
    },
    {
        "id": "visual_inspection_helper_first",
        "prompt": "Inspect underside close-up renders of the aircraft landing gear and repair visual-detail issues.",
        "must_select": ["capture_object_inspection_renders", "review_inspection_renders_against_brief", "repair_animation_from_findings"],
        "must_not_select": ["draft_script"],
        "search": "underside close-up inspection renders landing gear visual detail repair",
        "search_before": [("capture_object_inspection_renders", "draft_script")],
    },
    {
        "id": "procedural_creation_composable_or_script",
        "prompt": "Create a hard-surface modular wall panel kit with geometry node starters, bevels, material presets, and production organization.",
        "must_select": ["plan_advanced_scene_workflow", "apply_procedural_array_stack", "add_geometry_nodes_modifier", "create_shader_material", "organize_scene_for_production", "draft_script"],
        "must_not_select": [],
        "search": "create hard surface modular wall panel geometry nodes material preset object kit",
        "search_before": [("draft_script", "add_geometry_nodes_modifier")],
    },
    {
        "id": "object_design_composable_or_script",
        "prompt": "Design a futuristic wall-mounted coffee machine with chrome pipes, a small display, buttons, and beveled body.",
        "must_select": ["plan_advanced_scene_workflow", "edit_mesh", "create_shader_material", "inspect_modeling_quality", "draft_script"],
        "must_not_select": [],
        "search": "object design coffee machine chrome pipes display buttons beveled body",
        "search_before": [("draft_script", "create_shader_material")],
    },
    {
        "id": "desk_lamp_prop_composable_or_script",
        "prompt": "Create a believable architect desk lamp product prop with spring arms, counterweight, open wide shade, bulb, cable, and capture inspection renders.",
        "must_select": ["plan_advanced_scene_workflow", "inspect_modeling_quality", "capture_object_inspection_renders", "draft_script"],
        "must_not_select": [],
        "search": "create architect desk lamp product prop spring arms counterweight wide shade bulb cable object kit inspection renders",
        "search_before": [("draft_script", "capture_object_inspection_renders")],
    },
    {
        "id": "reference_model_quality_loop",
        "prompt": "Match the reference image of a plush cartoon cat: preserve silhouette, proportions, face placement, fur direction, paws, tail, capture evidence, score it, repair issues, and leave preview pending.",
        "must_select": ["plan_model_quality_workflow", "plan_advanced_scene_workflow", "inspect_modeling_quality", "capture_viewport", "capture_object_inspection_renders", "draft_script"],
        "must_not_select": [],
        "search": "match reference cartoon cat silhouette proportions fur quality evidence repair",
        "search_contains": ["plan_model_quality_workflow", "capture_viewport", "inspect_modeling_quality"],
        "search_before": [("plan_model_quality_workflow", "plan_advanced_scene_workflow"), ("plan_model_quality_workflow", "draft_script")],
    },
    {
        "id": "human_reference_model_quality_loop",
        "prompt": "Model a human figure from the attached reference image, matching its silhouette, measured proportions, landmark placement, and form continuity before surface detail.",
        "must_select": ["plan_model_quality_workflow", "plan_advanced_scene_workflow", "inspect_modeling_quality", "capture_viewport", "capture_object_inspection_renders", "draft_script"],
        "must_not_select": [],
        "search": "model human figure from attached reference image silhouette proportions landmark placement form continuity",
        "search_contains": ["plan_model_quality_workflow", "capture_viewport", "inspect_modeling_quality"],
        "search_before": [("plan_model_quality_workflow", "plan_advanced_scene_workflow")],
    },
    {
        "id": "hard_surface_reference_model_quality_loop",
        "prompt": "Rebuild this hard-surface product from the reference photo and score silhouette, proportions, feature placement, edge treatment, and surface match before preview approval.",
        "must_select": ["plan_model_quality_workflow", "plan_advanced_scene_workflow", "inspect_modeling_quality", "capture_viewport", "capture_object_inspection_renders", "draft_script"],
        "must_not_select": [],
        "search": "rebuild hard surface product from reference photo silhouette proportions feature placement surface match",
        "search_contains": ["plan_model_quality_workflow", "capture_viewport", "inspect_modeling_quality"],
        "search_before": [("plan_model_quality_workflow", "plan_advanced_scene_workflow")],
    },
    {
        "id": "character_animation_not_model_quality",
        "prompt": "Animate this character waving, capture a playblast, and repair the timing.",
        "must_select": ["draft_script", "run_animation_task", "plan_animation_workflow", "capture_animation_playblast"],
        "must_not_select": ["plan_model_quality_workflow"],
        "search": "animate character waving playblast timing repair",
        "search_contains": ["draft_script", "run_animation_task", "plan_animation_workflow"],
        "search_not_contains": ["plan_model_quality_workflow"],
        "search_before": [("draft_script", "run_animation_task"), ("run_animation_task", "plan_advanced_scene_workflow")],
    },
    {
        "id": "asset_import_async_path",
        "prompt": "Find a Poly Haven model, download it, import it, organize it, make a studio presentation, and capture viewport evidence.",
        "must_select": ["plan_asset_import_workflow", "start_external_asset_download", "get_external_asset_job_status", "start_external_asset_import_job", "get_external_asset_import_job_status", "prepare_imported_asset_presentation"],
        "must_not_select": ["draft_script"],
        "search": "poly haven asset import organize studio presentation workflow",
        "search_before": [("plan_asset_import_workflow", "download_poly_haven_asset"), ("start_external_asset_download", "download_poly_haven_asset")],
    },
    {
        "id": "director_orchestration",
        "prompt": "Director workflow: import an asset, build a product scene, animate a reveal, review evidence, repair, and ask me to commit or revert.",
        "must_select": ["plan_director_workflow", "plan_asset_import_workflow", "plan_advanced_scene_workflow", "prepare_imported_asset_presentation", "run_animation_workflow", "capture_viewport", "draft_script"],
        "must_not_select": [],
        "search": "director workflow import asset product scene animate reveal evidence commit revert",
        "search_before": [("plan_director_workflow", "draft_script"), ("draft_script", "run_animation_workflow")],
    },
    {
        "id": "explicit_custom_script_allowed_after_gap",
        "prompt": "Draft a custom Python script for a bespoke geometry-node network that helper tools cannot express.",
        "must_select": ["draft_script", "get_geometry_nodes_details", "plan_advanced_scene_workflow"],
        "must_not_select": [],
        "search": "custom python geometry node network helpers cannot express",
        "search_before": [("plan_advanced_scene_workflow", "draft_script")],
    },
    {
        "id": "client_neutral_annotation_guides",
        "prompt": "Create calibrated Blender guides from a reference image and landmark outline JSON.",
        "must_select": ["create_reference_guides_from_annotations", "inspect_reference_modeling_guides"],
        "must_not_select": [],
        "search": "calibrated reference image landmark outline JSON guide scene",
        "search_contains": ["create_reference_guides_from_annotations", "inspect_reference_modeling_guides"],
        "search_before": [("create_reference_guides_from_annotations", "create_reference_modeling_guides")],
    },
    {
        "id": "client_neutral_depth_fusion",
        "prompt": "Fuse calibrated front and side depth maps into a depth-constrained surface.",
        "must_select": ["create_multiview_depth_surface"],
        "must_not_select": [],
        "search": "calibrated multi-view depth map fusion depth surface",
        "search_contains": ["create_multiview_depth_surface"],
        "search_before": [("create_multiview_depth_surface", "create_multiview_visual_hull")],
    },
    {
        "id": "client_neutral_multiview_fitting",
        "prompt": "Fit the surface to the calibrated multi-view references with a joint silhouette objective.",
        "must_select": ["fit_surface_to_multiview_references"],
        "must_not_select": [],
        "search": "fit surface calibrated multi-view references joint silhouette",
        "search_contains": ["fit_surface_to_multiview_references"],
        "search_before": [("fit_surface_to_multiview_references", "optimize_screen_space_sculpt")],
    },
    {
        "id": "reference_render_redline_comparison",
        "prompt": "Render the model through the calibrated reference camera, compare its silhouette and landmarks, and generate a redline overlay for the next repair.",
        "must_select": ["compare_model_to_reference", "plan_model_quality_workflow"],
        "must_not_select": [],
        "search": "calibrated reference render silhouette landmark redline compare repair",
        "search_contains": ["compare_model_to_reference"],
        "search_before": [("compare_model_to_reference", "capture_object_inspection_renders")],
    },
    {
        "id": "reference_soft_form_blockout",
        "prompt": "Create a soft organic primary-mass blockout from the calibrated reference guide ellipses before detail.",
        "must_select": ["create_reference_blockout", "plan_model_quality_workflow"],
        "must_not_select": [],
        "search": "reference soft organic primary mass blockout guide ellipses",
        "search_contains": ["create_reference_blockout"],
        "search_before": [("create_reference_blockout", "apply_procedural_array_stack")],
    },
    {
        "id": "material_inspection_and_repair",
        "prompt": "Inspect the selected object's material, repair missing shader nodes, assign a PBR material, and leave the changes in preview.",
        "must_select": ["inspect_material_setup", "repair_material_setup", "create_shader_material"],
        "must_not_select": ["draft_script"],
        "search": "inspect material shader repair",
        "search_contains": ["inspect_material_setup", "repair_material_setup", "create_shader_material"],
        "search_before": [("inspect_material_setup", "draft_script"), ("repair_material_setup", "draft_script")],
    },
    {
        "id": "material_generation_script_first",
        "prompt": "Create a custom procedural marble material with layered noise, color ramps, and bump for the selected object.",
        "must_select": ["draft_script", "create_procedural_texture_material", "inspect_material_setup"],
        "must_not_select": [],
        "search": "create custom procedural marble material layered noise color ramps bump",
        "search_contains": ["draft_script", "create_procedural_texture_material"],
        "search_before": [("draft_script", "create_procedural_texture_material")],
    },
    {
        "id": "explicit_material_helper_override",
        "prompt": "Create a procedural marble material with helpers for the selected object.",
        "must_select": ["create_procedural_texture_material"],
        "must_not_select": ["draft_script"],
        "search": "create procedural marble material with helpers",
        "search_contains": ["create_procedural_texture_material"],
        "search_before": [("create_procedural_texture_material", "draft_script")],
    },
    {
        "id": "project_creation_helper_only",
        "prompt": "Create a new Blender project.",
        "must_select": ["create_new_blender_project", "get_blend_file_diagnostics"],
        "must_not_select": ["draft_script"],
        "search": "Create a new Blender project.",
        "search_contains": ["create_new_blender_project", "get_blend_file_diagnostics"],
        "search_before": [("create_new_blender_project", "draft_script")],
    },
    {
        "id": "final_animation_render_helper_only",
        "prompt": "Render the final animation.",
        "must_select": ["start_render_job", "get_render_job_status"],
        "must_not_select": ["draft_script"],
        "search": "Render the final animation.",
        "search_contains": ["start_render_job", "get_render_job_status"],
        "search_before": [("start_render_job", "run_animation_task"), ("start_render_job", "draft_script")],
    },
    {
        "id": "project_file_diagnostics_and_save",
        "prompt": "Inspect blend file diagnostics before saving the current project to a user-confirmed path.",
        "must_select": ["get_blend_file_diagnostics"],
        "must_not_select": ["draft_script"],
        "search": "blend file save diagnostics",
        "search_contains": ["get_blend_file_diagnostics", "save_blend_file"],
        "search_before": [("get_blend_file_diagnostics", "draft_script"), ("save_blend_file", "draft_script")],
    },
    {
        "id": "mixed_project_save_and_material_authoring",
        "prompt": "Save the blend after creating a material.",
        "must_select": ["save_blend_file", "draft_script"],
        "must_not_select": ["run_animation_task"],
        "search": "Save the blend after creating a material.",
        "search_contains": ["save_blend_file", "draft_script"],
        "search_before": [("save_blend_file", "draft_script")],
    },
    {
        "id": "static_motion_noun_not_animation",
        "prompt": "Create an orbit sculpture.",
        "must_select": ["draft_script"],
        "must_not_select": ["run_animation_task", "plan_animation_workflow"],
        "search": "Create an orbit sculpture.",
        "search_not_contains": ["run_animation_task", "plan_animation_workflow", "create_camera_orbit"],
        "search_before": [],
    },
    {
        "id": "render_setup_helper_route",
        "prompt": "Create a render setup.",
        "must_select": ["configure_render_outputs", "set_render_settings"],
        "must_not_select": ["draft_script", "run_animation_task"],
        "search": "Create a render setup.",
        "search_contains": ["configure_render_outputs", "set_render_settings"],
        "search_before": [("configure_render_outputs", "create_lookdev_turntable_review")],
    },
    {
        "id": "lookdev_review_exact_helper_route",
        "prompt": "Create a lookdev turntable review.",
        "must_select": ["create_lookdev_turntable_review"],
        "must_not_select": ["draft_script", "run_animation_task"],
        "search": "Create a lookdev turntable review.",
        "search_contains": ["create_lookdev_turntable_review"],
        "search_before": [("create_lookdev_turntable_review", "plan_advanced_scene_workflow")],
    },
    {
        "id": "preview_commit_or_revert",
        "prompt": "Inspect pending preview changes and let the user choose whether to commit or revert them.",
        "must_select": ["commit_preview", "revert_preview"],
        "must_not_select": ["draft_script"],
        "search": "pending live preview commit revert",
        "search_contains": ["commit_preview", "revert_preview"],
        "search_before": [],
    },
    {
        "id": "binary_session_script_trust",
        "prompt": "Use custom Blender Python only after the user enables session script trust.",
        "must_select": ["draft_script"],
        "must_not_select": [],
        "search": "trusted script python",
        "search_contains": ["draft_script", "run_approved_script"],
        "search_before": [],
    },
    {
        "id": "gateway_inspection_reachability",
        "prompt": "Inspect the scene, list its objects, and check blend-file diagnostics before changing anything.",
        "must_select": ["list_scene_objects", "get_blend_file_diagnostics"],
        "must_not_select": [],
        "search": "inspect scene list objects blend file diagnostics",
        "search_limit": 5,
        "search_contains": ["get_blend_file_diagnostics", "list_scene_objects"],
        "search_not_contains": ["stage_persistent_simulation_bake"],
        "search_before": [],
    },
    {
        "id": "gateway_broad_workflow_reachability",
        "prompt": "Build a named-part robot with materials, wave animation, lights, an orbit camera, screenshots, and preview commit or revert.",
        "must_select": [],
        "must_not_select": [],
        "search": "build named primitives materials wave animation three-point lights platform orbit camera screenshots preview commit revert",
        "search_limit": 5,
        "search_contains": ["plan_director_workflow", "plan_advanced_scene_workflow"],
        "search_before": [("plan_director_workflow", "run_animation_workflow")],
    },
]


def _selected_names(prompt):
    tools, meta = agent_tools.select_blender_tool_definitions(prompt, context_bundle=None)
    return {tool["name"] for tool in tools}, meta


def _search_names(server, query, limit=12):
    result = server._search_blender_tools({"query": query, "limit": limit})
    structured = result["structuredContent"]
    return [tool["name"] for tool in structured["tools"]], structured


def _assert_before(names, earlier, later, fixture_id):
    assert earlier in names, (fixture_id, earlier, names)
    if later in names:
        assert names.index(earlier) < names.index(later), (fixture_id, earlier, later, names)


def _client_discovery_contract(server, profile):
    initialized = server.initialize(
        {
            "protocolVersion": mcp_server.PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": profile["clientInfo"],
        }
    )
    assert initialized["protocolVersion"] == mcp_server.PROTOCOL_VERSION, (profile, initialized)
    instructions = initialized["instructions"]
    for required_guidance in (
        "search_blender_tools",
        "get_blender_tool_schema",
        "invoke_blender_tool",
        "session script trust",
        "external asset",
        "bridge_timeout",
    ):
        assert required_guidance in instructions, (profile["id"], required_guidance, instructions)

    tools = server.tools_list({})["tools"]
    expected_names = set(mcp_server.GATEWAY_TOOL_NAMES)
    assert {tool["name"] for tool in tools} == expected_names, profile
    assert len(tools) == 5, profile
    assert all(str(tool.get("description") or "").strip() for tool in tools), profile
    assert all((tool.get("inputSchema") or {}).get("type") == "object" for tool in tools), profile
    descriptions = " ".join(str(tool.get("description") or "").lower() for tool in tools)
    for workflow_term in (
        "scene inspection",
        "modeling",
        "materials",
        "rigging",
        "animation",
        "rendering",
        "trusted scripts",
        "commit/revert",
    ):
        assert workflow_term in descriptions, (profile["id"], workflow_term, descriptions)
    for helper_name in (
        "list_scene_objects",
        "get_blend_file_diagnostics",
        "run_animation_workflow",
        "plan_model_quality_workflow",
        "capture_viewport",
        "draft_script",
        "commit_preview",
        "revert_preview",
    ):
        schema = server._get_blender_tool_schema({"name": helper_name})["structuredContent"]
        assert schema["ok"] is True and schema["tool"]["name"] == helper_name, (profile["id"], helper_name, schema)
    invoked = server._invoke_blender_tool(
        {"name": "list_scene_objects", "arguments": {}}
    )["structuredContent"]
    assert invoked["ok"] is True and invoked["invoked_tool"] == "list_scene_objects", (profile["id"], invoked)
    quality_invoked = server._invoke_blender_tool(
        {
            "name": "plan_model_quality_workflow",
            "arguments": {
                "prompt": "Match the attached reference image.",
                "reference_brief": {
                    "subject": "test model",
                    "silhouette": ["wide upper form over a narrow base"],
                    "primary_masses": ["upper form", "base"],
                    "proportion_checks": ["upper form is twice the base width"],
                },
            },
        }
    )["structuredContent"]
    assert quality_invoked["ok"] is True, (profile["id"], quality_invoked)
    assert quality_invoked["invoked_tool"] == "plan_model_quality_workflow", (profile["id"], quality_invoked)
    return json.dumps(tools, separators=(",", ":"), sort_keys=True)


def main():
    servers = {
        profile["id"]: mcp_server.BlenderMCPServer(OfflineBridge())
        for profile in CLIENT_PROFILES
    }
    discovery_contracts = {
        profile["id"]: _client_discovery_contract(servers[profile["id"]], profile)
        for profile in CLIENT_PROFILES
    }
    assert len(set(discovery_contracts.values())) == 1, discovery_contracts

    for fixture in ROUTING_FIXTURES:
        selected, meta = _selected_names(fixture["prompt"])
        for name in fixture["must_select"]:
            assert name in selected, (fixture["id"], name, meta)
        for name in fixture["must_not_select"]:
            assert name not in selected, (fixture["id"], name, meta)

        for profile in CLIENT_PROFILES:
            search_names, search = _search_names(
                servers[profile["id"]],
                fixture["search"],
                limit=fixture.get("search_limit", 12),
            )
            for name in fixture.get("search_contains", []):
                assert name in search_names, (profile["id"], fixture["id"], name, search_names)
            for name in fixture.get("search_not_contains", []):
                assert name not in search_names, (profile["id"], fixture["id"], name, search_names)
            for earlier, later in fixture["search_before"]:
                _assert_before(search_names, earlier, later, f"{profile['id']}:{fixture['id']}")
            assert search["count"] > 0, (profile["id"], fixture["id"], search)
    print("smoke_client_profile_routing: ok")


if __name__ == "__main__":
    main()
