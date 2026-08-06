from __future__ import annotations

import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import generation_providers as gp  # noqa: E402
from claude_blender import session_credentials  # noqa: E402


class _StoreIsolation(unittest.TestCase):
    """The overlay now consults the session store, which is process-global."""

    def setUp(self):
        session_credentials.clear_session_credentials()
        self.addCleanup(session_credentials.clear_session_credentials)


class _FakePreferences:
    """Stands in for the Blender AddonPreferences instance.

    ``environment_overlay`` is duck-typed precisely so it can be exercised
    without importing bpy -- this is the real function under test, not a copy.
    """

    def __init__(self, **values):
        defaults = {
            "generation_python": "",
            "triposr_root": "",
            "generation_endpoint": "",
            "generation_endpoint_token": "",
            "tripo_api_key": "",
            "meshy_api_key": "",
            "generation_egress_allowed": False,
        }
        defaults.update(values)
        for key, value in defaults.items():
            setattr(self, key, value)


LAPTOP_GPU = {
    "probed": True,
    "cuda_available": True,
    "device_name": "NVIDIA GeForce RTX 2060 SUPER",
    "vram_gb": 8.0,
    "compute_capability": 7.5,
    "supports_bfloat16": False,
}


class PreferenceOverlayTests(_StoreIsolation):
    def test_empty_preferences_produce_no_overlay(self):
        self.assertEqual({}, gp.environment_overlay(_FakePreferences()))

    def test_missing_preferences_object_is_tolerated(self):
        self.assertEqual({}, gp.environment_overlay(None))

    def test_generation_python_populates_every_interpreter_variable(self):
        overlay = gp.environment_overlay(_FakePreferences(generation_python="C:/venv/python.exe"))
        for name in gp.PREFERENCE_PYTHON_ENV_VARS:
            self.assertEqual("C:/venv/python.exe", overlay[name])

    def test_whitespace_only_values_are_ignored(self):
        overlay = gp.environment_overlay(_FakePreferences(tripo_api_key="   ", triposr_root="\t"))
        self.assertEqual({}, overlay)

    def test_egress_toggle_only_appears_when_enabled(self):
        self.assertNotIn(gp.EGRESS_ENV_VAR, gp.environment_overlay(_FakePreferences()))
        enabled = gp.environment_overlay(_FakePreferences(generation_egress_allowed=True))
        self.assertEqual(gp.EGRESS_ALLOW, enabled[gp.EGRESS_ENV_VAR])

    def test_overlay_does_not_blank_operator_environment(self):
        environ = {"TRIPO_API_KEY": "from-environment"}
        environ.update(gp.environment_overlay(_FakePreferences()))
        self.assertEqual("from-environment", environ["TRIPO_API_KEY"])

    def test_preferences_win_over_environment_when_set(self):
        environ = {"TRIPO_API_KEY": "from-environment"}
        environ.update(gp.environment_overlay(_FakePreferences(tripo_api_key="from-preferences")))
        self.assertEqual("from-preferences", environ["TRIPO_API_KEY"])

    def test_every_mapped_preference_reaches_the_environment(self):
        prefs = _FakePreferences(
            triposr_root="root",
            generation_endpoint="endpoint",
            generation_endpoint_token="token",
            tripo_api_key="tripo",
            meshy_api_key="meshy",
        )
        overlay = gp.environment_overlay(prefs)
        for attribute, name in gp.PREFERENCE_ENV_MAP:
            self.assertIn(name, overlay, attribute)


class PreferenceDrivenAvailabilityTests(_StoreIsolation):
    def test_configuring_triposr_in_preferences_makes_it_available(self):
        environ = gp.environment_overlay(
            _FakePreferences(generation_python="C:/venv/python.exe", triposr_root="C:/blend/TripoSR")
        )
        report = gp.provider_availability(
            gp.PROVIDERS_BY_NAME["triposr"], hardware=LAPTOP_GPU, environ=environ
        )
        self.assertTrue(report["available"], report["remedies"])

    def test_hosted_needs_both_toggle_and_key(self):
        key_only = gp.environment_overlay(_FakePreferences(tripo_api_key="k"))
        report = gp.provider_availability(
            gp.PROVIDERS_BY_NAME["tripo"], hardware=LAPTOP_GPU, environ=key_only
        )
        self.assertIn("egress_denied", report["blockers"])

        both = gp.environment_overlay(
            _FakePreferences(tripo_api_key="k", generation_egress_allowed=True)
        )
        report = gp.provider_availability(
            gp.PROVIDERS_BY_NAME["tripo"], hardware=LAPTOP_GPU, environ=both
        )
        self.assertTrue(report["available"], report["remedies"])

    def test_studio_endpoint_available_without_enabling_egress(self):
        environ = gp.environment_overlay(_FakePreferences(generation_endpoint="http://gpu-box:8080"))
        report = gp.provider_availability(
            gp.PROVIDERS_BY_NAME["studio_endpoint"], hardware=LAPTOP_GPU, environ=environ
        )
        self.assertTrue(report["available"], report["remedies"])
        self.assertEqual(gp.EGRESS_DENY, gp.egress_mode(environ))


class PaidProviderTests(_StoreIsolation):
    """Spending the user's money must never be automatic."""

    def test_only_hosted_providers_are_paid(self):
        self.assertTrue(gp.is_paid_provider("tripo"))
        self.assertTrue(gp.is_paid_provider("meshy"))
        self.assertFalse(gp.is_paid_provider("triposr"))
        self.assertFalse(gp.is_paid_provider("studio_endpoint"))
        self.assertFalse(gp.is_paid_provider(""))
        self.assertFalse(gp.is_paid_provider("not_a_provider"))

    def test_every_paid_provider_states_its_cost(self):
        # A confirmation prompt with no number in it is not informed consent.
        for spec in gp.PROVIDER_SPECS:
            if spec.kind == gp.KIND_HOSTED_API:
                self.assertTrue(spec.cost_note, spec.name)

    def test_notice_carries_what_a_user_needs_to_decide(self):
        notice = gp.paid_provider_notice("tripo")
        self.assertTrue(notice["paid"])
        self.assertTrue(notice["uploads_reference_images"])
        self.assertIn("credits", notice["cost_note"])
        self.assertTrue(notice["license_note"])

    def test_notice_for_a_local_provider_is_not_marked_paid(self):
        notice = gp.paid_provider_notice("triposr")
        self.assertFalse(notice["paid"])
        self.assertFalse(notice["uploads_reference_images"])

    def test_auto_selection_never_returns_a_paid_provider(self):
        # Both hosted providers fully configured and permitted; a request that
        # names nothing must still refuse rather than pick one.
        environ = {
            "TRIPO_API_KEY": "k",
            "MESHY_API_KEY": "k",
            gp.EGRESS_ENV_VAR: gp.EGRESS_ALLOW,
        }
        selection = gp.select_provider(environ=environ, hardware=LAPTOP_GPU)
        self.assertFalse(selection["ok"])
        self.assertIsNone(selection["selected"])
        self.assertTrue(selection["requires_explicit_choice"])
        self.assertIn("tripo", selection["suggested_providers"])

    def test_a_configured_local_provider_is_chosen_over_a_paid_one(self):
        environ = gp.environment_overlay(
            _FakePreferences(
                generation_python="C:/venv/python.exe",
                triposr_root="C:/blend/TripoSR",
                tripo_api_key="k",
                generation_egress_allowed=True,
            )
        )
        selection = gp.select_provider(environ=environ, hardware=LAPTOP_GPU)
        # TripoSR has no job backend yet, so this still refuses -- but the
        # refusal must not quietly fall through to the paid provider.
        self.assertFalse(gp.is_paid_provider(selection.get("selected") or ""))


if __name__ == "__main__":
    unittest.main()
