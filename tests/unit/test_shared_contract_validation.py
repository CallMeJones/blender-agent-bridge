from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "addon"))
from claude_blender import bridge_protocol, mcp_server, tool_catalog


class SharedValidationTests(unittest.TestCase):
    def test_transports_share_full_validation_corpus(self):
        schema = {"type": "object", "properties": {
            "page": {"type": "integer", "minimum": 1, "maximum": 100},
            "weight": {"type": "number"},
            "samples": {"type": "array", "minItems": 1, "maxItems": 2,
                        "items": {"anyOf": [{"type": "string"}, {"type": "integer"}]}},
            "choice": {"oneOf": [{"type": "integer"}, {"type": "number"}]},
        }, "required": ["page"], "additionalProperties": False}
        valid = [{"page": 1}, {"page": 100, "samples": ["a", 3], "weight": 1.5}]
        invalid = [{"page": 0}, {"page": 101}, {"page": True}, {},
                   {"page": 1, "weight": float("nan")}, {"page": 1, "weight": float("inf")},
                   {"page": 1, "samples": []}, {"page": 1, "samples": [None]},
                   {"page": 1, "choice": 2}, {"page": 1, "extra": 2}]
        for value, rejected in [(value, False) for value in valid] + [(value, True) for value in invalid]:
            with self.subTest(value=value):
                bridge = bridge_protocol.validate_arguments(value, schema)
                self.assertEqual(bridge, mcp_server._validate_schema(value, schema))
                self.assertEqual(bool(bridge), rejected)

    def test_generation_categories_follow_registry_groups(self):
        for name in ("plan_image_to_3d_approach", "cleanup_generated_asset", "evaluate_generated_asset"):
            self.assertEqual(tool_catalog._tool_category({"name": name}), "external_assets")


if __name__ == "__main__":
    unittest.main()
