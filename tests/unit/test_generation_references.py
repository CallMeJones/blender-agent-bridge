from __future__ import annotations

import os
import sys
import tempfile
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import generation_references as gr  # noqa: E402


class GenerationReferenceTests(unittest.TestCase):
    def test_tripo_accepts_webp_and_records_content_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "front.webp")
            with open(path, "wb") as handle:
                handle.write(b"RIFF\x04\x00\x00\x00WEBPdata")
            identities = gr.validate_reference_images({"front": path}, provider="tripo")
        self.assertEqual("webp", identities["front"]["format"])
        self.assertEqual(64, len(identities["front"]["sha256"]))

    def test_tripo_rejects_non_image_content_before_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "front.png")
            with open(path, "wb") as handle:
                handle.write(b"not a png")
            with self.assertRaisesRegex(ValueError, "invalid file signature"):
                gr.validate_reference_images({"front": path}, provider="tripo")

    def test_reference_set_has_an_aggregate_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = {}
            for name in ("front", "left"):
                path = os.path.join(tmp, "%s.png" % name)
                with open(path, "wb") as handle:
                    handle.write(b"\x89PNG\r\n\x1a\n1234")
                paths[name] = path
            with self.assertRaisesRegex(ValueError, "job safety limit"):
                gr.validate_reference_images(
                    paths,
                    provider="tripo",
                    max_image_bytes=20,
                    max_total_bytes=20,
                )

    def test_expected_identity_rejects_replaced_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "front.png")
            with open(path, "wb") as handle:
                handle.write(b"\x89PNG\r\n\x1a\nfirst")
            expected = gr.validate_reference_images({"front": path}, provider="tripo")
            with open(path, "wb") as handle:
                handle.write(b"\x89PNG\r\n\x1a\nsecond")
            with self.assertRaisesRegex(ValueError, "changed after approval"):
                gr.validate_reference_images(
                    {"front": path},
                    provider="tripo",
                    expected_identities=expected,
                )


if __name__ == "__main__":
    unittest.main()
