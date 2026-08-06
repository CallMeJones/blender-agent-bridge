from __future__ import annotations

import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import external_assets, generation_providers as gp  # noqa: E402
from claude_blender import session_credentials as sc  # noqa: E402


class StoreTests(unittest.TestCase):
    def setUp(self):
        sc.clear_session_credentials()
        self.addCleanup(sc.clear_session_credentials)

    def test_round_trip(self):
        self.assertTrue(sc.set_session_credential(sc.TRIPO_API_KEY, "tsk_live"))
        self.assertEqual("tsk_live", sc.session_credential(sc.TRIPO_API_KEY))

    def test_unset_credential_reads_empty_not_none(self):
        self.assertEqual("", sc.session_credential(sc.MESHY_API_KEY))

    def test_values_are_stripped(self):
        sc.set_session_credential(sc.MESHY_API_KEY, "  msy_live \n")
        self.assertEqual("msy_live", sc.session_credential(sc.MESHY_API_KEY))

    def test_empty_value_clears_rather_than_storing_blank(self):
        sc.set_session_credential(sc.TRIPO_API_KEY, "tsk_live")
        self.assertFalse(sc.set_session_credential(sc.TRIPO_API_KEY, "   "))
        self.assertEqual([], sc.configured_session_credentials())

    def test_unknown_name_is_refused(self):
        # A typo must not park a live secret under a name nothing reads back.
        with self.assertRaises(sc.UnknownCredentialError):
            sc.set_session_credential("tripo_api_kye", "tsk_live")
        with self.assertRaises(sc.UnknownCredentialError):
            sc.session_credential("openai_api_key")

    def test_credentials_are_independent(self):
        sc.set_session_credential(sc.TRIPO_API_KEY, "tripo")
        sc.set_session_credential(sc.MESHY_API_KEY, "meshy")
        sc.clear_session_credential(sc.TRIPO_API_KEY)
        self.assertEqual("", sc.session_credential(sc.TRIPO_API_KEY))
        self.assertEqual("meshy", sc.session_credential(sc.MESHY_API_KEY))

    def test_clear_all_reports_how_many_were_held(self):
        sc.set_session_credential(sc.TRIPO_API_KEY, "tripo")
        sc.set_session_credential(sc.SKETCHFAB_API_TOKEN, "sketch")
        self.assertEqual(2, sc.clear_session_credentials())
        self.assertEqual([], sc.configured_session_credentials())

    def test_status_names_every_credential_and_leaks_no_value(self):
        sc.set_session_credential(sc.TRIPO_API_KEY, "tsk_live_secret")
        status = sc.session_credential_status()
        self.assertEqual(set(sc.CREDENTIAL_NAMES), set(status))
        self.assertTrue(status[sc.TRIPO_API_KEY])
        self.assertFalse(status[sc.MESHY_API_KEY])
        self.assertNotIn("tsk_live_secret", repr(status))


class SketchfabParityTests(unittest.TestCase):
    """Sketchfab and the generation providers must share one store."""

    def setUp(self):
        sc.clear_session_credentials()
        self.addCleanup(sc.clear_session_credentials)

    def test_sketchfab_helpers_delegate_to_the_shared_store(self):
        external_assets.set_session_sketchfab_api_token("sfab_token")
        self.assertEqual("sfab_token", sc.session_credential(sc.SKETCHFAB_API_TOKEN))
        self.assertEqual("sfab_token", external_assets.session_sketchfab_api_token())

    def test_clearing_through_either_surface_agrees(self):
        sc.set_session_credential(sc.SKETCHFAB_API_TOKEN, "sfab_token")
        external_assets.clear_session_sketchfab_api_token()
        self.assertEqual("", external_assets.session_sketchfab_api_token())
        self.assertEqual([], sc.configured_session_credentials())

    def test_diagnostics_see_a_store_written_credential(self):
        sc.set_session_credential(sc.SKETCHFAB_API_TOKEN, "sfab_token")
        report = external_assets.sketchfab_auth_diagnostics(environ={})
        self.assertTrue(report["ready"])
        self.assertTrue(report["session_token_configured"])
        self.assertNotIn("sfab_token", repr(report))


class OverlayCredentialTests(unittest.TestCase):
    """The store is the first place the environment overlay looks."""

    def setUp(self):
        sc.clear_session_credentials()
        self.addCleanup(sc.clear_session_credentials)

    def test_session_credential_reaches_the_environment_without_preferences(self):
        sc.set_session_credential(sc.TRIPO_API_KEY, "from-session")
        overlay = gp.environment_overlay(None)
        self.assertEqual("from-session", overlay["TRIPO_API_KEY"])

    def test_session_credential_beats_a_persisted_preference(self):
        sc.set_session_credential(sc.TRIPO_API_KEY, "from-session")
        overlay = gp.environment_overlay(_FakePreferences(tripo_api_key="from-preferences"))
        self.assertEqual("from-session", overlay["TRIPO_API_KEY"])

    def test_persisted_preference_still_works_when_nothing_is_held(self):
        overlay = gp.environment_overlay(_FakePreferences(tripo_api_key="from-preferences"))
        self.assertEqual("from-preferences", overlay["TRIPO_API_KEY"])

    def test_injected_credentials_override_the_live_store(self):
        sc.set_session_credential(sc.MESHY_API_KEY, "live-store")
        overlay = gp.environment_overlay(None, credentials={sc.MESHY_API_KEY: "injected"})
        self.assertEqual("injected", overlay["MESHY_API_KEY"])

    def test_every_secret_preference_is_backed_by_a_credential(self):
        # Guards the pairing: a new secret field that forgets its credential
        # would silently go back to disk-only storage.
        secret_attributes = {attribute for attribute, _ in gp.PREFERENCE_CREDENTIAL_MAP}
        for attribute in ("tripo_api_key", "meshy_api_key", "generation_endpoint_token"):
            self.assertIn(attribute, secret_attributes)
        for _attribute, credential in gp.PREFERENCE_CREDENTIAL_MAP:
            self.assertIn(credential, sc.CREDENTIAL_NAMES)


class _FakePreferences:
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


if __name__ == "__main__":
    unittest.main()
