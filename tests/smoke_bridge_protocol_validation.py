"""Pure-Python smoke tests for the shared tool-argument validator (plain python).

Covers bridge_protocol.validate_arguments, which the in-Blender HTTP /tool path now
uses for defense-in-depth (matching the stdio MCP server's schema enforcement).
"""

from __future__ import annotations

import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon", "claude_blender"))

import bridge_protocol  # noqa: E402


SCHEMA = {
    "type": "object",
    "properties": {
        "job_id": {"type": "string"},
        "count": {"type": "integer"},
        "mode": {"type": "string", "enum": ["fast", "slow"]},
        "names": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    },
    "required": ["job_id"],
    "additionalProperties": False,
}


def test_valid_passes():
    assert bridge_protocol.validate_arguments({"job_id": "a", "count": 2, "mode": "fast"}, SCHEMA) == []


def test_missing_required():
    errors = bridge_protocol.validate_arguments({"count": 1}, SCHEMA)
    assert any("job_id" in e and "required" in e for e in errors), errors


def test_type_mismatch():
    errors = bridge_protocol.validate_arguments({"job_id": "a", "count": "two"}, SCHEMA)
    assert any("count" in e for e in errors), errors


def test_additional_property_rejected():
    errors = bridge_protocol.validate_arguments({"job_id": "a", "extra": 1}, SCHEMA)
    assert any("extra" in e for e in errors), errors


def test_enum_rejected():
    errors = bridge_protocol.validate_arguments({"job_id": "a", "mode": "warp"}, SCHEMA)
    assert any("mode" in e for e in errors), errors


def test_maxitems_rejected():
    errors = bridge_protocol.validate_arguments({"job_id": "a", "names": ["a", "b", "c", "d"]}, SCHEMA)
    assert any("at most" in e for e in errors), errors


def test_bool_not_accepted_as_integer():
    errors = bridge_protocol.validate_arguments({"job_id": "a", "count": True}, SCHEMA)
    assert any("count" in e for e in errors), errors


def test_real_contract_schema_smoke():
    # A real contract that ships an input_schema should accept a minimal valid call.
    contract = bridge_protocol.normalized_tool_contract("validate_render_job_output")
    schema = contract.get("input_schema")
    assert isinstance(schema, dict), contract
    assert bridge_protocol.validate_arguments({"job_id": "job-1"}, schema) == []
    assert bridge_protocol.validate_arguments({}, schema), "missing job_id should fail"


def main():
    test_valid_passes()
    test_missing_required()
    test_type_mismatch()
    test_additional_property_rejected()
    test_enum_rejected()
    test_maxitems_rejected()
    test_bool_not_accepted_as_integer()
    test_real_contract_schema_smoke()
    print("smoke_bridge_protocol_validation: ok")


if __name__ == "__main__":
    main()
