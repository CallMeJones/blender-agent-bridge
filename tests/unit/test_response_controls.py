from __future__ import annotations

import copy
import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import mcp_server, response_controls, tool_registry  # noqa: E402


class _StaticBridge:
    base_url = "http://127.0.0.1:8765"

    def get(self, path, params=None):
        if path == "/tools":
            return {"ok": True, "tools": mcp_server._static_tool_definitions()}
        if path == "/resources":
            return {"ok": True, "resources": []}
        raise RuntimeError(f"Unexpected bridge path: {path}")


class ResponseControlTests(unittest.TestCase):
    def setUp(self):
        self.complete = {
            "ok": True,
            "scene": {"frame_current": 12, "frame_start": 1, "frame_end": 120},
            "objects": [
                {
                    "name": f"Cube.{index:03d}",
                    "type": "MESH",
                    "location": [float(index), 0.0, 0.0],
                    "materials": [{"name": "Material", "nodes": [{"name": "Principled BSDF"}]}],
                }
                for index in range(6)
            ],
            "warnings": ["keep this warning"],
        }

    def test_control_schema_is_optional_and_full_by_default(self):
        schema = tool_registry.REGISTRY.get("list_scene_objects").input_schema
        self.assertEqual("full", schema["properties"]["detail"]["default"])
        self.assertNotIn("detail", schema.get("required", []))
        untouched = response_controls.augment_input_schema(
            "create_primitive",
            {"type": "object", "properties": {"primitive": {"type": "string"}}},
        )
        self.assertNotIn("detail", untouched["properties"])
        discovery = response_controls.discovery_input_schema("list_scene_objects", schema)
        self.assertNotIn("detail", discovery["properties"])
        self.assertIn("max_objects", discovery["properties"])

    def test_full_default_preserves_existing_result_and_adds_digest_only(self):
        original = copy.deepcopy(self.complete)
        result = response_controls.apply_response_controls("list_scene_objects", {}, self.complete)
        digest = result.pop("response_digest")
        self.assertEqual(original, result)
        self.assertEqual(response_controls.canonical_digest(original), digest)
        self.assertEqual(original, self.complete)

    def test_summary_is_opt_in_and_keeps_identity_and_warning_data(self):
        result = response_controls.apply_response_controls(
            "list_scene_objects",
            {"detail": "summary"},
            self.complete,
        )
        self.assertEqual("summary", result["response_detail"])
        self.assertEqual(6, result["objects_count"])
        self.assertEqual("Cube.000", result["objects"][0]["name"])
        self.assertEqual(["keep this warning"], result["warnings"])
        self.assertNotIn("materials", result["objects"][0])

    def test_fields_support_dotted_projection(self):
        result = response_controls.apply_response_controls(
            "list_scene_objects",
            {"fields": ["scene.frame_current", "objects.name"]},
            self.complete,
        )
        self.assertEqual({"frame_current": 12}, result["scene"])
        self.assertEqual([{"name": f"Cube.{index:03d}"} for index in range(6)], result["objects"])
        self.assertEqual(["keep this warning"], result["warnings"])
        self.assertEqual([], result["field_selection"]["missing"])

    def test_pagination_is_opt_in_and_reports_total(self):
        result = response_controls.apply_response_controls(
            "list_scene_objects",
            {"page": 2, "page_size": 2},
            self.complete,
        )
        self.assertEqual(["Cube.002", "Cube.003"], [item["name"] for item in result["objects"]])
        self.assertEqual(
            {
                "field": "objects",
                "page": 2,
                "page_size": 2,
                "total_items": 6,
                "total_pages": 3,
                "has_previous": True,
                "has_next": True,
            },
            result["pagination"],
        )

    def test_matching_digest_returns_tiny_not_modified_response(self):
        digest = response_controls.canonical_digest(self.complete)
        result = response_controls.apply_response_controls(
            "list_scene_objects",
            {"known_digest": digest},
            self.complete,
        )
        self.assertEqual(
            {
                "ok": True,
                "not_modified": True,
                "response_digest": digest,
                "tool": "list_scene_objects",
            },
            result,
        )

    def test_digest_mismatch_ignores_reduction_and_returns_complete_result(self):
        result = response_controls.apply_response_controls(
            "list_scene_objects",
            {
                "known_digest": "0" * 64,
                "detail": "summary",
                "fields": ["objects.name"],
                "page": 2,
                "page_size": 1,
            },
            self.complete,
        )
        self.assertEqual(self.complete["objects"], result["objects"])
        self.assertEqual(self.complete["scene"], result["scene"])
        self.assertFalse(result["known_digest_match"])
        self.assertFalse(result["not_modified"])
        self.assertIn("response_digest", result)

    def test_schema_digest_supports_not_modified(self):
        server = mcp_server.BlenderMCPServer(_StaticBridge())
        complete = server._get_blender_tool_schema(
            {"name": "get_animation_details"}
        )["structuredContent"]
        self.assertFalse(complete["not_modified"])
        self.assertIn("detail", complete["tool"]["inputSchema"]["properties"])
        unchanged = server._get_blender_tool_schema(
            {
                "name": "get_animation_details",
                "known_digest": complete["schema_digest"],
            }
        )["structuredContent"]
        self.assertEqual(
            {
                "ok": True,
                "not_modified": True,
                "name": "get_animation_details",
                "schema_digest": complete["schema_digest"],
            },
            unchanged,
        )

    def test_on_demand_schema_is_canonical_for_directly_advertised_tool(self):
        server = mcp_server.BlenderMCPServer(_StaticBridge())
        complete = server._get_blender_tool_schema(
            {"name": "list_scene_objects"}
        )["structuredContent"]
        properties = complete["tool"]["inputSchema"]["properties"]
        for response_control in (
            "detail",
            "fields",
            "page",
            "page_size",
            "page_field",
            "known_digest",
        ):
            self.assertIn(response_control, properties)

    def test_payload_telemetry_has_sizes_but_no_arguments_or_content(self):
        server = mcp_server.BlenderMCPServer(_StaticBridge())
        server._record_payload_size(
            "get_blender_tool_schema",
            {"structuredContent": {"ok": True, "schema_digest": "a" * 64}},
        )
        resource = server.resources_read({"uri": "blender://mcp/payload-telemetry"})
        text = resource["contents"][0]["text"]
        telemetry = __import__("json").loads(text)
        self.assertEqual(1, telemetry["call_count"])
        self.assertEqual("get_blender_tool_schema", telemetry["tools"][0]["tool_name"])
        self.assertGreater(telemetry["tools"][0]["last_response_bytes"], 0)
        self.assertNotIn("get_animation_details", text)
        self.assertNotIn("arguments", text)

    def test_initialize_and_tool_definitions_are_byte_stable_for_prompt_caching(self):
        profiles = [
            {"name": "claude-desktop", "version": "eval"},
            {"name": "codex", "version": "eval"},
            {"name": "cursor", "version": "eval"},
        ]
        serialized = []
        for profile in profiles:
            server = mcp_server.BlenderMCPServer(_StaticBridge())
            initialized = server.initialize(
                {
                    "protocolVersion": mcp_server.PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": profile,
                }
            )
            tools = server.tools_list({})
            serialized.append(
                (
                    mcp_server._json_text(initialized),
                    mcp_server._json_text(tools),
                )
            )
            self.assertEqual(tools, server.tools_list({}))
        self.assertEqual(1, len(set(serialized)))


if __name__ == "__main__":
    unittest.main()
