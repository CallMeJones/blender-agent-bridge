from __future__ import annotations

import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import credential_store as cs  # noqa: E402
from claude_blender import session_credentials as sc  # noqa: E402

WINDOWS = sys.platform == "win32"


class BackendSelectionTests(unittest.TestCase):
    def tearDown(self):
        cs.set_backend_override(None)

    def test_backend_is_named_and_described_without_exposing_values(self):
        report = cs.describe()
        self.assertIn(report["backend"], (
            cs.BACKEND_NONE,
            cs.BACKEND_WINDOWS_DPAPI,
            cs.BACKEND_MACOS_KEYCHAIN,
            cs.BACKEND_LINUX_SECRET_SERVICE,
        ))
        self.assertEqual(report["available"], report["backend"] != cs.BACKEND_NONE)
        self.assertTrue(report["label"])

    def test_no_backend_degrades_instead_of_raising(self):
        cs.set_backend_override(cs.BACKEND_NONE)
        self.assertFalse(cs.is_available())
        self.assertFalse(cs.store_credential(sc.TRIPO_API_KEY, "tsk_live"))
        self.assertEqual("", cs.load_credential(sc.TRIPO_API_KEY))
        self.assertFalse(cs.delete_credential(sc.TRIPO_API_KEY))
        self.assertEqual([], cs.stored_credential_names())
        self.assertEqual([], cs.load_into_session())

    def test_unavailable_backend_reports_a_remedy(self):
        cs.set_backend_override(cs.BACKEND_NONE)
        self.assertTrue(cs.describe()["remedy"])

    def test_unknown_credential_names_are_refused(self):
        with self.assertRaises(sc.UnknownCredentialError):
            cs.store_credential("some_other_key", "value")
        with self.assertRaises(sc.UnknownCredentialError):
            cs.load_credential("some_other_key")


class RestrictedFileFallbackTests(unittest.TestCase):
    """The backend a headless Linux node falls back to.

    Exercised on every platform because it is the one path with no OS
    protection behind it, so its behaviour has to be pinned precisely.
    """

    def setUp(self):
        cs.set_backend_override(cs.BACKEND_RESTRICTED_FILE)
        self.addCleanup(cs.set_backend_override, None)
        self.addCleanup(cs.forget_everything)
        cs.forget_everything()

    def test_round_trip(self):
        self.assertTrue(cs.store_credential(sc.TRIPO_API_KEY, "tsk_file"))
        self.assertEqual("tsk_file", cs.load_credential(sc.TRIPO_API_KEY))

    def test_it_is_reported_as_available_but_not_encrypted(self):
        self.assertTrue(cs.is_available())
        self.assertFalse(cs.is_encrypted())
        report = cs.describe()
        self.assertFalse(report["encrypted"])
        # The label must not imply protection this backend does not provide.
        self.assertNotIn("ncrypt", report["label"])

    def test_file_is_created_owner_only(self):
        cs.store_credential(sc.TRIPO_API_KEY, "tsk_perms")
        path = cs._restricted_path(sc.TRIPO_API_KEY)
        self.assertTrue(os.path.isfile(path))
        if os.name == "posix":
            self.assertEqual(0o600, os.stat(path).st_mode & 0o777)

    @unittest.skipIf(os.name != "posix", "permission widening is a POSIX concern")
    def test_a_widened_file_is_discarded_rather_than_used(self):
        cs.store_credential(sc.TRIPO_API_KEY, "tsk_widened")
        path = cs._restricted_path(sc.TRIPO_API_KEY)
        os.chmod(path, 0o644)
        self.assertEqual("", cs.load_credential(sc.TRIPO_API_KEY))
        self.assertFalse(os.path.isfile(path))

    def test_delete_and_forget_clear_the_file(self):
        cs.store_credential(sc.TRIPO_API_KEY, "tsk_gone")
        self.assertTrue(cs.delete_credential(sc.TRIPO_API_KEY))
        self.assertEqual("", cs.load_credential(sc.TRIPO_API_KEY))

    def test_every_known_credential_can_be_stored(self):
        # Sketchfab and the generation providers share one mechanism; a
        # provider that could not be stored would need its own, again.
        for name in sc.CREDENTIAL_NAMES:
            self.assertTrue(cs.store_credential(name, "value-%s" % name), name)
            self.assertEqual("value-%s" % name, cs.load_credential(name), name)
        self.assertEqual(sorted(sc.CREDENTIAL_NAMES), sorted(cs.stored_credential_names()))


@unittest.skipUnless(WINDOWS, "DPAPI is the Windows backend")
class WindowsDpapiTests(unittest.TestCase):
    """Exercises the real OS call, not a stand-in."""

    def setUp(self):
        self.assertEqual(cs.BACKEND_WINDOWS_DPAPI, cs.backend_name())
        cs.delete_credential(sc.TRIPO_API_KEY)
        sc.clear_session_credentials()
        self.addCleanup(sc.clear_session_credentials)
        self.addCleanup(cs.delete_credential, sc.TRIPO_API_KEY)

    def test_round_trip_through_the_operating_system(self):
        self.assertTrue(cs.store_credential(sc.TRIPO_API_KEY, "tsk_round_trip"))
        self.assertEqual("tsk_round_trip", cs.load_credential(sc.TRIPO_API_KEY))

    def test_stored_file_does_not_contain_the_plaintext(self):
        # The whole point: what lands on disk must be unreadable.
        cs.store_credential(sc.TRIPO_API_KEY, "tsk_plaintext_probe")
        path = cs._credential_path(sc.TRIPO_API_KEY)
        self.assertTrue(os.path.isfile(path))
        with open(path, "rb") as handle:
            written = handle.read()
        self.assertNotIn(b"tsk_plaintext_probe", written)
        # Base64 of the ciphertext must not decode to the secret either.
        import base64

        self.assertNotIn(b"tsk_plaintext_probe", base64.b64decode(written))

    def test_missing_credential_reads_empty(self):
        self.assertEqual("", cs.load_credential(sc.MESHY_API_KEY))

    def test_delete_removes_the_file_and_the_value(self):
        cs.store_credential(sc.TRIPO_API_KEY, "tsk_delete_me")
        self.assertTrue(cs.delete_credential(sc.TRIPO_API_KEY))
        self.assertEqual("", cs.load_credential(sc.TRIPO_API_KEY))
        self.assertFalse(os.path.isfile(cs._credential_path(sc.TRIPO_API_KEY)))
        # Deleting again is not an error, it just reports nothing was there.
        self.assertFalse(cs.delete_credential(sc.TRIPO_API_KEY))

    def test_empty_value_deletes_rather_than_storing_blank(self):
        cs.store_credential(sc.TRIPO_API_KEY, "tsk_transient")
        cs.store_credential(sc.TRIPO_API_KEY, "   ")
        self.assertEqual("", cs.load_credential(sc.TRIPO_API_KEY))

    def test_entropy_binds_the_blob_to_this_application(self):
        # A blob another application produced must not decrypt as one of ours,
        # even though DPAPI would happily decrypt it for this same user.
        original = cs._DPAPI_ENTROPY
        try:
            cs._DPAPI_ENTROPY = b"someone-elses-application"
            foreign_cipher = cs._dpapi_transform("CryptProtectData", b"tsk_foreign")
        finally:
            cs._DPAPI_ENTROPY = original
        self.assertTrue(foreign_cipher)
        self.assertEqual(b"", cs._dpapi_transform("CryptUnprotectData", foreign_cipher))

    def test_load_into_session_populates_the_shared_store(self):
        cs.store_credential(sc.TRIPO_API_KEY, "tsk_seeded")
        loaded = cs.load_into_session()
        self.assertIn(sc.TRIPO_API_KEY, loaded)
        self.assertEqual("tsk_seeded", sc.session_credential(sc.TRIPO_API_KEY))

    def test_stored_names_never_include_a_value(self):
        cs.store_credential(sc.TRIPO_API_KEY, "tsk_named")
        names = cs.stored_credential_names()
        self.assertIn(sc.TRIPO_API_KEY, names)
        self.assertNotIn("tsk_named", repr(names))

    def test_forget_everything_clears_each_stored_credential(self):
        cs.store_credential(sc.TRIPO_API_KEY, "tsk_forget")
        forgotten = cs.forget_everything()
        self.assertIn(sc.TRIPO_API_KEY, forgotten)
        self.assertEqual([], cs.stored_credential_names())


if __name__ == "__main__":
    unittest.main()
