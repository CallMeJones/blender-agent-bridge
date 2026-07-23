from __future__ import annotations

import json
import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import agent_tools, bridge_protocol, mcp_server, tool_registry  # noqa: E402
from claude_blender.tool_registry.registry import ToolRegistry, ToolSpec  # noqa: E402


SNAPSHOT_PATH = os.path.join(ROOT, "tests", "snapshots", "tool_registry.json")


class ToolRegistryTests(unittest.TestCase):
    def test_inventory_is_complete_and_domain_owned(self):
        specs = tool_registry.REGISTRY.specs()
        self.assertEqual(181, len(specs))
        self.assertEqual(180, len(tool_registry.definitions()))
        self.assertEqual(11, len(tool_registry.DOMAIN_MODULES))
        self.assertEqual({spec.name for spec in specs}, set(bridge_protocol.TOOL_CONTRACTS))
        self.assertEqual(
            {spec.name for spec in specs if spec.exposure != "internal"},
            {definition["name"] for definition in agent_tools.blender_tool_definitions()},
        )
        self.assertTrue(all(spec.owner for spec in specs))
        self.assertEqual(
            tuple(spec.name for spec in specs if spec.exposure == "compact_direct"),
            mcp_server.COMPACT_DIRECT_TOOL_NAMES,
        )
        self.assertEqual(
            28,
            len(mcp_server.WRAPPER_TOOL_NAMES) + len(mcp_server.COMPACT_DIRECT_TOOL_NAMES),
        )
        for module in tool_registry.DOMAIN_MODULES:
            owner = module.__name__.rsplit(".", 1)[-1]
            self.assertTrue(module.SPECS)
            self.assertTrue(all(spec.owner == owner for spec in module.SPECS))

    def test_registry_rejects_duplicate_names(self):
        registry = ToolRegistry()
        spec = tool_registry.REGISTRY.get("inspect_scene")
        registry.register(spec)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            registry.register(spec)

    def test_explicit_empty_output_schema_is_preserved(self):
        spec = ToolSpec(
            name="empty_output",
            description="Test",
            input_schema={},
            contract={},
            handler_key="empty_output",
            order=1,
            output_schema={},
        )
        self.assertEqual({}, spec.output_schema)

    def test_registry_outputs_are_json_serializable(self):
        json.dumps(tool_registry.definitions(), sort_keys=True)
        json.dumps(tool_registry.contracts(), sort_keys=True)

    def test_registry_state_isolated_from_nested_metadata_mutation(self):
        original_digest = tool_registry.REGISTRY.digest()
        original_definitions = tool_registry.definitions()
        returned_spec = tool_registry.REGISTRY.get("inspect_scene")

        returned_spec.input_schema["properties"]["include_visual"]["type"] = "mutated"
        inspect_definition = next(item for item in original_definitions if item["name"] == "inspect_scene")
        inspect_definition["input_schema"]["properties"]["include_visual"]["type"] = "mutated"

        self.assertEqual(original_digest, tool_registry.REGISTRY.digest())
        self.assertEqual(tool_registry.TOOL_REGISTRY_DIGEST, tool_registry.REGISTRY.digest())
        self.assertEqual(
            "boolean",
            tool_registry.REGISTRY.get("inspect_scene").input_schema["properties"]["include_visual"]["type"],
        )

    def test_contracts_take_canonical_description_and_schemas_from_tool_specs(self):
        for spec in tool_registry.REGISTRY.specs():
            with self.subTest(tool=spec.name):
                contract = tool_registry.contracts()[spec.name]
                self.assertEqual(spec.description, contract["description"])
                self.assertEqual(dict(spec.input_schema), contract["input_schema"])
                self.assertEqual(dict(spec.output_schema), contract["output_schema"])

    def test_handler_parity_requires_every_handler(self):
        handlers = {spec.name: (lambda _context, _args: None) for spec in tool_registry.REGISTRY.specs()}
        tool_registry.REGISTRY.validate_handlers(handlers)
        handlers.pop("inspect_scene")
        with self.assertRaisesRegex(ValueError, "inspect_scene"):
            tool_registry.REGISTRY.validate_handlers(handlers)

    def test_checked_in_snapshot_matches_registry(self):
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as handle:
            snapshot = json.load(handle)
        self.assertEqual(tool_registry.TOOL_REGISTRY_DIGEST, snapshot["registry_digest"])
        self.assertEqual(tool_registry.definitions(), snapshot["definitions"])
        self.assertEqual(tool_registry.contracts(), snapshot["contracts"])
        self.assertEqual(
            [
                {
                    "name": spec.name,
                    "description": spec.description,
                    "input_schema": dict(spec.input_schema),
                    "output_schema": dict(spec.output_schema),
                    "contract": dict(spec.contract),
                    "handler_key": spec.handler_key,
                    "order": spec.order,
                    "groups": list(spec.groups),
                    "exposure": spec.exposure,
                    "owner": spec.owner,
                }
                for spec in tool_registry.REGISTRY.specs()
            ],
            snapshot["specs"],
        )


if __name__ == "__main__":
    unittest.main()
