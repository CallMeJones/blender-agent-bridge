from __future__ import annotations

import io
import hashlib
import json
import os
import sys
import tempfile
import unittest
import urllib.error


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import check_pypi_name  # noqa: E402


class _Response:
    def __init__(self, body):
        self._body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._body


class PyPINameCheckTests(unittest.TestCase):
    def test_unregistered_name_is_available(self):
        def opener(url, timeout):
            raise urllib.error.HTTPError(url, 404, "missing", {}, io.BytesIO())

        result = check_pypi_name.check_name(opener=opener)
        self.assertEqual("unregistered", result["status"])

    def test_existing_matching_project_is_allowed(self):
        def opener(_url, timeout):
            return _Response(
                '{"info":{"version":"0.3.0","project_urls":{"Repository":"https://github.com/CallMeJones/blender-agent-bridge"}}}'
            )

        result = check_pypi_name.check_name(opener=opener)
        self.assertEqual("existing_project", result["status"])

    def test_existing_other_project_stops_release(self):
        def opener(_url, timeout):
            return _Response('{"info":{"project_urls":{"Repository":"https://example.test/other"}}}')

        with self.assertRaisesRegex(RuntimeError, "naming decision"):
            check_pypi_name.check_name(opener=opener)

    def _release_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        files = {
            "blender_bridge-0.3.0-py3-none-any.whl": b"wheel",
            "blender_bridge-0.3.0.tar.gz": b"sdist",
        }
        for filename, body in files.items():
            with open(os.path.join(temporary.name, filename), "wb") as handle:
                handle.write(body)
        digests = {filename: hashlib.sha256(body).hexdigest() for filename, body in files.items()}
        return temporary, digests

    @staticmethod
    def _release_response(digests):
        urls = [
            {"filename": filename, "digests": {"sha256": digest}}
            for filename, digest in sorted(digests.items())
        ]
        return _Response(json.dumps({"urls": urls}))

    def test_unpublished_release_requires_publication(self):
        temporary, _digests = self._release_fixture()
        self.addCleanup(temporary.cleanup)

        def opener(url, timeout):
            raise urllib.error.HTTPError(url, 404, "missing", {}, io.BytesIO())

        result = check_pypi_name.check_release_artifacts(temporary.name, "v0.3.0", opener=opener)
        self.assertEqual("unpublished", result["status"])
        self.assertTrue(result["publish_required"])

    def test_other_release_artifacts_are_rejected(self):
        temporary, _digests = self._release_fixture()
        self.addCleanup(temporary.cleanup)
        with open(os.path.join(temporary.name, "blender_bridge-0.2.0.tar.gz"), "wb") as handle:
            handle.write(b"old release")

        with self.assertRaisesRegex(RuntimeError, "outside blender-bridge 0.3.0"):
            check_pypi_name.check_release_artifacts(
                temporary.name,
                "0.3.0",
                opener=lambda _url, timeout: self._release_response({}),
            )

    def test_complete_matching_release_is_idempotent(self):
        temporary, digests = self._release_fixture()
        self.addCleanup(temporary.cleanup)
        result = check_pypi_name.check_release_artifacts(
            temporary.name,
            "0.3.0",
            opener=lambda _url, timeout: self._release_response(digests),
        )
        self.assertEqual("complete", result["status"])
        self.assertFalse(result["publish_required"])

    def test_github_output_drives_the_publish_condition(self):
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            output_path = handle.name
        self.addCleanup(lambda: os.path.exists(output_path) and os.remove(output_path))

        check_pypi_name._write_github_output(
            output_path,
            {"publish_required": True, "status": "partially_published"},
        )

        with open(output_path, "r", encoding="utf-8") as handle:
            self.assertEqual(
                "publish_required=true\npublication_status=partially_published\n",
                handle.read(),
            )

    def test_identical_partial_release_can_resume(self):
        temporary, digests = self._release_fixture()
        self.addCleanup(temporary.cleanup)
        first_filename = sorted(digests)[0]
        result = check_pypi_name.check_release_artifacts(
            temporary.name,
            "0.3.0",
            opener=lambda _url, timeout: self._release_response({first_filename: digests[first_filename]}),
        )
        self.assertEqual("partially_published", result["status"])
        self.assertTrue(result["publish_required"])
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            check_pypi_name.check_release_artifacts(
                temporary.name,
                "0.3.0",
                require_complete=True,
                opener=lambda _url, timeout: self._release_response({first_filename: digests[first_filename]}),
            )

    def test_complete_check_retries_only_incomplete_publication_state(self):
        temporary, digests = self._release_fixture()
        self.addCleanup(temporary.cleanup)
        calls = []

        def opener(url, timeout):
            calls.append(url)
            if len(calls) == 1:
                raise urllib.error.HTTPError(url, 404, "not propagated", {}, io.BytesIO())
            return self._release_response(digests)

        result = check_pypi_name.check_release_artifacts_with_retry(
            temporary.name,
            "0.3.0",
            require_complete=True,
            attempts=2,
            delay=0,
            opener=opener,
        )
        self.assertEqual("complete", result["status"])
        self.assertEqual(2, len(calls))

    def test_mismatched_or_unexpected_release_artifacts_stop_publication(self):
        temporary, digests = self._release_fixture()
        self.addCleanup(temporary.cleanup)
        first_filename = sorted(digests)[0]
        bad_remote = {
            first_filename: "0" * 64,
            "unexpected.whl": "1" * 64,
        }
        with self.assertRaisesRegex(RuntimeError, "hash_mismatches"):
            check_pypi_name.check_release_artifacts(
                temporary.name,
                "0.3.0",
                opener=lambda _url, timeout: self._release_response(bad_remote),
            )


if __name__ == "__main__":
    unittest.main()
