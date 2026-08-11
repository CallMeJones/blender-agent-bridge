from __future__ import annotations

import importlib
import os
import sys
import types
import unittest
from unittest import mock


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))


def _load_generation_handler():
    module_name = "claude_blender.tool_handlers.generation"
    previous = sys.modules.pop(module_name, None)
    parent_package = sys.modules.get("claude_blender")
    tool_handlers_package = sys.modules.get("claude_blender.tool_handlers")
    parent_attrs = {}
    if parent_package is not None:
        for name in ("asset_jobs", "generation_providers", "preferences"):
            parent_attrs[name] = (
                True,
                getattr(parent_package, name),
            ) if hasattr(parent_package, name) else (False, None)
    tool_handler_attrs = {}
    if tool_handlers_package is not None:
        for name in ("generation", "support"):
            tool_handler_attrs[name] = (
                True,
                getattr(tool_handlers_package, name),
            ) if hasattr(tool_handlers_package, name) else (False, None)
    support = types.ModuleType("claude_blender.tool_handlers.support")
    support._bounded_int = lambda value, default, minimum=0, maximum=1000: int(default)
    support._bounded_float = lambda value, default, minimum=0.0, maximum=1000.0: float(default)

    providers = types.ModuleType("claude_blender.generation_providers")
    providers.KIND_HOSTED_API = "hosted_api"
    providers.RUN_STATUS_NO_JOB_BACKEND = "no_job_backend"
    providers._diagnostics = {"providers": []}
    providers.PROVIDER_SPECS = (
        types.SimpleNamespace(
            name="triposr",
            title="TripoSR",
            kind="local_process",
            cost_note="Free; uses local compute.",
            requires_egress=False,
            supports_multiview=False,
            license_note="MIT",
        ),
        types.SimpleNamespace(
            name="tripo",
            title="Tripo AI",
            kind="hosted_api",
            cost_note="Charged per job.",
            requires_egress=True,
            supports_multiview=True,
            license_note="Commercial API.",
        ),
        types.SimpleNamespace(
            name="meshy",
            title="Meshy AI",
            kind="hosted_api",
            cost_note="Charged per job.",
            requires_egress=True,
            supports_multiview=True,
            license_note="Commercial API.",
        ),
    )
    providers.environment_overlay = lambda _prefs: {}
    providers.probe_hardware = lambda **_kwargs: {}
    providers.generation_provider_diagnostics = lambda **_kwargs: providers._diagnostics
    providers.session_generation_policy = lambda: {"policy": "any", "reason": ""}
    providers.policy_refusal = lambda _provider: ""

    preferences = types.ModuleType("claude_blender.preferences")
    preferences.get_preferences = lambda _context: None
    stubs = {
        "claude_blender.asset_jobs": types.ModuleType("claude_blender.asset_jobs"),
        "claude_blender.generation_providers": providers,
        "claude_blender.preferences": preferences,
        "claude_blender.tool_handlers.support": support,
    }
    with mock.patch.dict(sys.modules, stubs):
        module = importlib.import_module(module_name)
    if parent_package is not None:
        for name, (existed, value) in parent_attrs.items():
            if existed:
                setattr(parent_package, name, value)
            elif hasattr(parent_package, name):
                delattr(parent_package, name)
    if tool_handlers_package is not None:
        for name, (existed, value) in tool_handler_attrs.items():
            if existed:
                setattr(tool_handlers_package, name, value)
            elif hasattr(tool_handlers_package, name):
                delattr(tool_handlers_package, name)
    # The parent package may already expose real modules when this test runs as
    # part of the full suite; pin the handler globals to these deterministic
    # stubs instead of relying on import order.
    module.asset_jobs = stubs["claude_blender.asset_jobs"]
    module.generation_providers = providers
    module.preferences = preferences
    sys.modules.pop(module_name, None)
    parent = sys.modules.get("claude_blender.tool_handlers")
    if parent is not None and getattr(parent, "generation", None) is module:
        delattr(parent, "generation")
    if previous is not None:
        sys.modules[module_name] = previous
    return module, providers


generation, providers = _load_generation_handler()


class GenerationPlanningTests(unittest.TestCase):
    def test_multiple_generation_providers_produce_an_explicit_provider_question(self):
        providers._diagnostics = {
            "providers": [
                {"provider": "triposr", "runnable": True, "run_status": "runnable"},
                {"provider": "tripo", "runnable": True, "run_status": "runnable"},
                {"provider": "meshy", "runnable": True, "run_status": "runnable"},
            ]
        }
        result = generation.plan_image_to_3d_approach(None, {})

        self.assertTrue(result["requires_user_choice"])
        self.assertTrue(result["generation_provider_selection_required"])
        self.assertEqual(["triposr", "tripo", "meshy"], result["generation_provider_choices"])
        self.assertIn("Which generation provider", result["provider_question"])

    def test_disabled_generation_routes_leave_authored_bridge_work_uninterrupted(self):
        providers._diagnostics = {
            "providers": [
                {
                    "provider": name,
                    "runnable": False,
                    "run_status": "blocked",
                    "run_blocker": "Third-party APIs disabled",
                    "blockers": ["egress_denied"],
                    "remedies": [],
                }
                for name in ("triposr", "tripo", "meshy")
            ]
        }
        result = generation.plan_image_to_3d_approach(None, {})

        self.assertFalse(result["requires_user_choice"])
        self.assertEqual(["authored"], result["ready_routes"])
        self.assertFalse(result["generation_provider_selection_required"])
        self.assertIn("scripts, bounded helpers, and the bridge tools", result["message"])

    def test_meshy_and_tripo_multiview_guidance_are_provider_specific(self):
        views = {"front": "front.png", "left": "left.png", "back": "back.png", "right": "right.png"}
        meshy = " ".join(generation._view_warnings(views, "meshy"))
        tripo = " ".join(generation._view_warnings(views, "tripo"))

        self.assertIn("primary first image", meshy)
        self.assertIn("any order", meshy)
        self.assertNotIn("positional slots", meshy)
        self.assertIn("positional slots", tripo)


if __name__ == "__main__":
    unittest.main()
