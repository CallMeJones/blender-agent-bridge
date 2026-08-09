from __future__ import annotations

import os
import sys
import types
import unittest
from unittest import mock


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))


def _load_generation_handler():
    import importlib

    module_name = "claude_blender.tool_handlers.generation"
    previous = sys.modules.pop(module_name, None)
    support = types.ModuleType("claude_blender.tool_handlers.support")
    support._bounded_int = lambda value, default, minimum=0, maximum=1000: max(minimum, min(maximum, int(default if value is None else value)))
    support._bounded_float = lambda value, default, minimum=0.0, maximum=1000.0: max(
        minimum,
        min(maximum, float(default if value is None else value)),
    )
    stubs = {
        "claude_blender.asset_jobs": types.ModuleType("claude_blender.asset_jobs"),
        "claude_blender.generation_providers": types.ModuleType("claude_blender.generation_providers"),
        "claude_blender.preferences": types.ModuleType("claude_blender.preferences"),
        "claude_blender.tool_handlers.support": support,
    }
    with mock.patch.dict(sys.modules, stubs):
        module = importlib.import_module(module_name)
    sys.modules.pop(module_name, None)
    parent = sys.modules.get("claude_blender.tool_handlers")
    if parent is not None and getattr(parent, "generation", None) is module:
        delattr(parent, "generation")
    if previous is not None:
        sys.modules[module_name] = previous
    return module


generation = _load_generation_handler()


class _FakeMesh:
    vertices = [object(), object(), object()]
    edges = []
    polygons = []
    color_attributes = []
    uv_layers = []


class _FakeObject(dict):
    name = "Generated"
    data = _FakeMesh()
    dimensions = (0.6, 1.0, 0.5)
    material_slots = []


class GeneratedAssetQualityTests(unittest.TestCase):
    def test_provider_normalization_downgrades_axis_dominance_to_info(self):
        obj = _FakeObject()
        obj["blender_agent_bridge_import_orientation"] = "triposr_image_plane_to_blender_z_up"
        findings = generation._quality_findings(
            obj,
            {
                "provider": "triposr",
                "generation": {"view_count": 1},
                "import_orientation_normalization": {
                    "applied": True,
                    "axis_transform": "triposr_image_plane_to_blender_z_up",
                    "rotation_applied": True,
                },
            },
        )

        codes = {item["code"]: item["severity"] for item in findings["findings"]}
        self.assertNotIn("orientation_not_z_up", codes)
        self.assertEqual("info", codes["orientation_axis_dominance_ambiguous"])
        self.assertTrue(findings["orientation"]["provider_normalized"])

    def test_missing_normalization_keeps_orientation_warning(self):
        findings = generation._quality_findings(_FakeObject(), {"provider": "triposr", "generation": {"view_count": 1}})

        codes = {item["code"]: item["severity"] for item in findings["findings"]}
        self.assertEqual("warning", codes["orientation_not_z_up"])

    def test_wide_hosted_subject_does_not_imply_wrong_orientation(self):
        findings = generation._quality_findings(_FakeObject(), {"provider": "meshy", "generation": {"view_count": 1}})

        codes = {item["code"]: item["severity"] for item in findings["findings"]}
        self.assertNotIn("orientation_not_z_up", codes)
        self.assertEqual("info", codes["orientation_axis_dominance_ambiguous"])
        self.assertTrue(findings["orientation"]["upright_likely"])


if __name__ == "__main__":
    unittest.main()
