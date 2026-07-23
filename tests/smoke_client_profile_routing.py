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
    def get(self, path, params=None):
        if path == "/tools":
            return {"ok": True, "tools": mcp_server._static_tool_definitions()}
        raise RuntimeError("offline routing smoke uses static tool contracts")


CLIENT_PROFILES = [
    {"id": "claude", "clientInfo": {"name": "claude-desktop", "version": "routing-eval"}},
    {"id": "codex", "clientInfo": {"name": "codex", "version": "routing-eval"}},
    {"id": "cursor", "clientInfo": {"name": "cursor", "version": "routing-eval"}},
]


ROUTING_FIXTURES = [
    {
        "id": "animation_helper_first",
        "prompt": "Make the selected cube bounce twice, get smaller each bounce, capture a playblast, review it, repair issues, and leave it as a preview.",
        "must_select": ["plan_animation_workflow", "run_animation_workflow", "capture_animation_playblast", "review_playblast_against_brief", "run_animation_repair_loop"],
        "must_not_select": ["draft_script"],
        "search": "bounce twice get smaller playblast review repair",
        "search_before": [("run_animation_workflow", "draft_script"), ("plan_animation_workflow", "draft_script")],
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
        "search": "hard surface modular wall panel geometry nodes material preset object kit",
        "search_before": [("plan_advanced_scene_workflow", "draft_script"), ("add_geometry_nodes_modifier", "draft_script")],
    },
    {
        "id": "object_design_composable_or_script",
        "prompt": "Design a futuristic wall-mounted coffee machine with chrome pipes, a small display, buttons, and beveled body.",
        "must_select": ["plan_advanced_scene_workflow", "edit_mesh", "create_shader_material", "inspect_modeling_quality", "draft_script"],
        "must_not_select": [],
        "search": "object design coffee machine chrome pipes display buttons beveled body helper path",
        "search_before": [("plan_advanced_scene_workflow", "draft_script"), ("create_shader_material", "draft_script")],
    },
    {
        "id": "desk_lamp_prop_composable_or_script",
        "prompt": "Create a believable architect desk lamp product prop with spring arms, counterweight, open wide shade, bulb, cable, and capture inspection renders.",
        "must_select": ["plan_advanced_scene_workflow", "inspect_modeling_quality", "capture_object_inspection_renders", "draft_script"],
        "must_not_select": [],
        "search": "architect desk lamp product prop spring arms counterweight wide shade bulb cable object kit inspection renders",
        "search_before": [("plan_advanced_scene_workflow", "draft_script"), ("capture_object_inspection_renders", "draft_script")],
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
        "must_select": ["plan_director_workflow", "plan_asset_import_workflow", "plan_advanced_scene_workflow", "prepare_imported_asset_presentation", "run_animation_workflow", "capture_viewport"],
        "must_not_select": ["draft_script"],
        "search": "director workflow import asset product scene animate reveal evidence commit revert",
        "search_before": [("plan_director_workflow", "draft_script"), ("plan_asset_import_workflow", "draft_script")],
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
        "id": "material_inspection_and_repair",
        "prompt": "Inspect the selected object's material, repair missing shader nodes, assign a PBR material, and leave the changes in preview.",
        "must_select": ["inspect_material_setup", "repair_material_setup", "create_shader_material"],
        "must_not_select": ["draft_script"],
        "search": "material shader repair",
        "search_contains": ["inspect_material_setup", "repair_material_setup", "create_shader_material"],
        "search_before": [("inspect_material_setup", "draft_script"), ("repair_material_setup", "draft_script")],
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
    expected_names = set(mcp_server.WRAPPER_TOOL_NAMES) | set(mcp_server.COMPACT_DIRECT_TOOL_NAMES)
    assert {tool["name"] for tool in tools} == expected_names, profile
    assert all(str(tool.get("description") or "").strip() for tool in tools), profile
    assert all((tool.get("inputSchema") or {}).get("type") == "object" for tool in tools), profile
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
            search_names, search = _search_names(servers[profile["id"]], fixture["search"])
            for name in fixture.get("search_contains", []):
                assert name in search_names, (profile["id"], fixture["id"], name, search_names)
            for earlier, later in fixture["search_before"]:
                _assert_before(search_names, earlier, later, f"{profile['id']}:{fixture['id']}")
            assert search["count"] > 0, (profile["id"], fixture["id"], search)
    print("smoke_client_profile_routing: ok")


if __name__ == "__main__":
    main()
