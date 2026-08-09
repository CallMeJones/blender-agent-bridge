from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import smoke_published_release_identity as publication_smoke  # noqa: E402


def _mcpb_bytes(version):
    manifest = {
        "manifest_version": "0.4",
        "name": "blender-agent-bridge",
        "version": version,
        "server": {
            "type": "uv",
            "entry_point": "src/main.py",
            "mcp_config": {"command": "uv"},
        },
    }
    project = "\n".join(
        (
            "[project]",
            'name = "blender-agent-bridge-mcpb"',
            f'version = "{version}"',
            "dependencies = []",
            "",
        )
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("pyproject.toml", project)
        archive.writestr("src/main.py", "print('ok')\n")
    return output.getvalue()


class PublishedReleaseIdentityTests(unittest.TestCase):
    def test_candidate_mcpb_digest_reads_the_retained_sidecar(self):
        version = "1.2.3"
        filename = f"blender-agent-bridge-{version}.mcpb"
        digest = "a" * 64
        with tempfile.TemporaryDirectory() as temporary:
            sidecar_path = os.path.join(temporary, f"{filename}.sha256")
            with open(sidecar_path, "w", encoding="utf-8") as handle:
                handle.write(f"{digest}  {filename}\n")

            self.assertEqual(
                digest,
                publication_smoke._candidate_mcpb_digest(sidecar_path, version=version),
            )

    def test_mcpb_archive_contract_requires_uv_source_layout(self):
        publication_smoke._verify_mcpb_archive(_mcpb_bytes("1.2.3"), version="1.2.3")

        with self.assertRaises(AssertionError):
            publication_smoke._verify_mcpb_archive(_mcpb_bytes("1.2.2"), version="1.2.3")

    def test_sidecar_must_name_the_verified_asset(self):
        digest = "a" * 64
        self.assertEqual(
            digest,
            publication_smoke._sidecar_digest(
                f"{digest}  expected.mcpb\n".encode(),
                "https://example.invalid/expected.mcpb.sha256",
                expected_filename="expected.mcpb",
            ),
        )
        with self.assertRaises(AssertionError):
            publication_smoke._sidecar_digest(
                f"{digest}  other.mcpb\n".encode(),
                "https://example.invalid/expected.mcpb.sha256",
                expected_filename="expected.mcpb",
            )

    def test_publication_verifier_downloads_and_checks_mcpb(self):
        version = "1.2.3"
        extension_filename = f"claude_blender-{version}.zip"
        extension_body = b"extension archive fixture"
        extension_digest = hashlib.sha256(extension_body).hexdigest()
        mcpb_filename = f"blender-agent-bridge-{version}.mcpb"
        mcpb_body = _mcpb_bytes(version)
        mcpb_digest = hashlib.sha256(mcpb_body).hexdigest()
        index = {
            "data": [
                {
                    "id": "claude_blender",
                    "version": version,
                    "archive_url": extension_filename,
                    "archive_hash": f"sha256:{extension_digest}",
                    "archive_size": len(extension_body),
                }
            ]
        }
        pages_zip_url = f"https://callmejones.github.io/blender-agent-bridge/{extension_filename}"
        release_zip_url = (
            f"{publication_smoke.RELEASE_BASE_URL}/v{version}/{extension_filename}"
        )
        mcpb_url = f"{publication_smoke.RELEASE_BASE_URL}/v{version}/{mcpb_filename}"
        responses = {
            publication_smoke.PAGES_INDEX_URL: json.dumps(index).encode(),
            pages_zip_url: extension_body,
            f"{pages_zip_url}.sha256": (
                f"{extension_digest}  {extension_filename}\n".encode()
            ),
            release_zip_url: extension_body,
            f"{release_zip_url}.sha256": (
                f"{extension_digest}  {extension_filename}\n".encode()
            ),
            mcpb_url: mcpb_body,
            f"{mcpb_url}.sha256": f"{mcpb_digest}  {mcpb_filename}\n".encode(),
        }

        def download(url, *, max_bytes):
            body = responses[url]
            self.assertLessEqual(len(body), max_bytes)
            return body

        with tempfile.TemporaryDirectory() as temporary:
            manifest_path = os.path.join(temporary, "blender_manifest.toml")
            with open(manifest_path, "w", encoding="utf-8") as handle:
                handle.write(f'id = "claude_blender"\nversion = "{version}"\n')
            with (
                mock.patch.object(publication_smoke, "MANIFEST_PATH", manifest_path),
                mock.patch.object(publication_smoke, "_download", side_effect=download) as mocked,
            ):
                publication_smoke._verify_once(expected_mcpb_digest=mcpb_digest)

        requested_urls = [call.args[0] for call in mocked.call_args_list]
        self.assertIn(mcpb_url, requested_urls)
        self.assertIn(f"{mcpb_url}.sha256", requested_urls)


if __name__ == "__main__":
    unittest.main()
