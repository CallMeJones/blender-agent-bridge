"""Pure-Python smoke test for tool catalog and bridge contract consistency."""

from __future__ import annotations

import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import agent_tools, bridge_protocol, script_analysis  # noqa: E402


EXTERNAL_ONLY_TOOLS = {"run_approved_script"}


def main():
    catalog_names = {tool["name"] for tool in agent_tools.blender_tool_definitions()}
    contract_names = set(bridge_protocol.TOOL_CONTRACTS)
    missing_contracts = catalog_names - contract_names
    assert not missing_contracts, sorted(missing_contracts)
    for tool_name in EXTERNAL_ONLY_TOOLS:
        assert tool_name in contract_names, tool_name
        assert tool_name not in catalog_names, tool_name
    for tool_name in ("create_procedural_object_kit", "create_directed_animation_shot"):
        assert tool_name in catalog_names, tool_name
        contract = bridge_protocol.normalized_tool_contract(tool_name)
        assert contract["mutates_scene"] is True, contract
        assert contract["requires_live_preview"] is True, contract
        assert contract["input_schema"].get("additionalProperties") is False, contract
    kit_templates = bridge_protocol.normalized_tool_contract("create_procedural_object_kit")["input_schema"]["properties"]["template"]["enum"]
    assert "desk_lamp" in kit_templates, kit_templates
    kit_props = bridge_protocol.normalized_tool_contract("create_procedural_object_kit")["input_schema"]["properties"]
    assert {"style", "variant", "detail_level", "features"}.issubset(kit_props), kit_props
    assert "architect" in kit_props["style"]["enum"], kit_props["style"]
    assert "spring_arms" in kit_props["features"]["items"]["enum"], kit_props["features"]
    parent_contract = bridge_protocol.normalized_tool_contract("parent_selected_to_empty")
    assert parent_contract["requires_selection"] is False, parent_contract
    assert {"object_names", "selected_only"}.issubset(parent_contract["input_schema"]["properties"]), parent_contract
    catalog_by_name = {tool["name"]: tool for tool in agent_tools.blender_tool_definitions()}
    for tool_name in ("draft_script", "draft_privileged_script"):
        code_schema = catalog_by_name[tool_name]["input_schema"]["properties"]["code"]
        assert code_schema["maxLength"] == script_analysis.MAX_SCRIPT_CHARS, code_schema

    # Input-schema parity: when a tool declares an input schema in both the external catalog
    # (agent_tools) and the bridge contract (bridge_protocol), their property names must match.
    # This catches a field added to one schema but not the other (e.g. a new playblast option).
    for tool_name, tool in catalog_by_name.items():
        catalog_schema = tool.get("input_schema")
        if not isinstance(catalog_schema, dict) or "properties" not in catalog_schema:
            continue
        contract_schema = bridge_protocol.TOOL_CONTRACTS.get(tool_name, {}).get("input_schema")
        if not isinstance(contract_schema, dict) or "properties" not in contract_schema:
            continue
        catalog_props = set(catalog_schema["properties"])
        contract_props = set(contract_schema["properties"])
        assert catalog_props == contract_props, (
            tool_name,
            {"only_in_catalog": sorted(catalog_props - contract_props),
             "only_in_contract": sorted(contract_props - catalog_props)},
        )
    print("smoke_tool_contract_inventory: ok")


if __name__ == "__main__":
    main()
