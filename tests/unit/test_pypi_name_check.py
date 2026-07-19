from __future__ import annotations

import io
import os
import sys
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


if __name__ == "__main__":
    unittest.main()
