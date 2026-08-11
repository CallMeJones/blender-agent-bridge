from __future__ import annotations

import os
import sys
import tempfile
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import generation_meshy as gm  # noqa: E402


class MeshyOptionTests(unittest.TestCase):
    def test_blender_working_is_the_default_and_preserves_raw_source(self):
        options = gm.normalize_options(view_count=4)
        body = gm.request_options(options, view_count=4)

        self.assertEqual("blender_working", options["preset"])
        self.assertTrue(body["should_remesh"])
        self.assertEqual("triangle", body["topology"])
        self.assertEqual(100000, body["target_polycount"])
        self.assertTrue(body["save_pre_remeshed_model"])
        self.assertTrue(body["enable_pbr"])
        self.assertEqual("4k", body["texture_resolution"])
        self.assertTrue(body["multi_view_thumbnails"])
        self.assertNotIn("model_type", body)
        self.assertNotIn("ultra_mode", body)
        self.assertTrue(body["remove_lighting"])

    def test_raw_high_detail_retains_previous_unremeshed_behavior(self):
        options = gm.normalize_options({"preset": "raw_high_detail"})
        body = gm.request_options(options)

        self.assertFalse(body["should_remesh"])
        self.assertNotIn("target_polycount", body)
        self.assertNotIn("save_pre_remeshed_model", body)

    def test_editable_quad_preset_requests_quad_remesh(self):
        body = gm.request_options(gm.normalize_options({"preset": "editable_quad"}))
        self.assertEqual("quad", body["topology"])
        self.assertEqual(50000, body["target_polycount"])

    def test_adaptive_decimation_replaces_preset_polycount(self):
        options = gm.normalize_options({"decimation_mode": "medium"})
        body = gm.request_options(options)
        self.assertEqual(3, body["decimation_mode"])
        self.assertNotIn("target_polycount", body)

    def test_explicit_decimation_and_polycount_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "cannot both"):
            gm.normalize_options({"decimation_mode": "low", "target_polycount": 12000})

    def test_meshy_t2_is_single_image_triangle_smart_topology(self):
        options = gm.normalize_options(
            {"ai_model": "meshy-t2", "model_type": "smart-topology"},
            view_count=1,
        )
        body = gm.request_options(options)
        self.assertEqual("smart-topology", body["model_type"])
        self.assertEqual("meshy-t2", body["ai_model"])
        self.assertEqual(4000, body["target_polycount"])
        self.assertNotIn("should_remesh", body)
        with self.assertRaisesRegex(ValueError, "single-image"):
            gm.normalize_options(
                {"ai_model": "meshy-t2", "model_type": "smart-topology"},
                view_count=2,
            )

    def test_ultra_is_limited_to_single_image_meshy_7(self):
        options = gm.normalize_options(
            {"ai_model": "meshy-7", "ultra_mode": True},
            view_count=1,
        )
        self.assertTrue(gm.request_options(options)["ultra_mode"])
        with self.assertRaisesRegex(ValueError, "Ultra"):
            gm.normalize_options({"ultra_mode": True}, view_count=4)

    def test_legacy_fields_remain_compatible(self):
        options = gm.normalize_options(
            model="meshy-6",
            face_limit=12000,
            texture=False,
        )
        self.assertEqual("meshy-6", options["ai_model"])
        self.assertEqual(12000, options["target_polycount"])
        self.assertFalse(options["should_texture"])

    def test_normalized_inactive_options_can_cross_multiple_layers(self):
        untextured = gm.normalize_options({"should_texture": False})
        raw = gm.normalize_options({"preset": "raw_high_detail"})

        self.assertEqual(untextured, gm.normalize_options(untextured))
        self.assertEqual(raw, gm.normalize_options(raw))
        self.assertNotIn("texture_resolution", untextured)
        self.assertNotIn("topology", raw)

    def test_job_policy_owns_legacy_argument_translation_and_pricing(self):
        resolved = gm.resolve_job_policy(
            {
                "views": {"front": "front.png"},
                "model": "meshy-6",
                "face_limit": 12000,
                "texture": False,
                "meshy_options": {"preset": "blender_working"},
            }
        )

        self.assertEqual("meshy-6", resolved["options"]["ai_model"])
        self.assertEqual(12000, resolved["options"]["target_polycount"])
        self.assertFalse(resolved["options"]["should_texture"])
        self.assertEqual(20.0, resolved["estimated_credits"])
        self.assertEqual(gm.PRICING_VERSION, resolved["pricing_version"])

    def test_job_policy_accepts_options_already_normalized_by_an_outer_boundary(self):
        options = gm.normalize_options({"should_texture": False})
        resolved = gm.resolve_job_policy(
            {"views": {"front": "front.png"}, "meshy_options": options}
        )

        self.assertEqual(options, resolved["options"])

    def test_meshy_5_uses_supported_defaults_and_omits_enhancement_fields(self):
        options = gm.normalize_options({"ai_model": "meshy-5"})
        body = gm.request_options(options)

        self.assertEqual("2k", options["texture_resolution"])
        self.assertNotIn("image_enhancement", body)
        self.assertNotIn("remove_lighting", body)

    def test_single_image_meshy_7_omits_unsupported_lighting_removal(self):
        options = gm.normalize_options({"ai_model": "meshy-7"}, view_count=1)
        body = gm.request_options(options, view_count=1)

        self.assertTrue(body["image_enhancement"])
        self.assertNotIn("remove_lighting", body)
        with self.assertRaisesRegex(ValueError, "remove_lighting"):
            gm.normalize_options(
                {"ai_model": "meshy-7", "remove_lighting": True},
                view_count=1,
            )


class MeshyPricingTests(unittest.TestCase):
    def test_meshy_7_cost_matrix(self):
        self.assertEqual(30.0, gm.estimated_credits(gm.normalize_options()))
        self.assertEqual(
            20.0,
            gm.estimated_credits(gm.normalize_options({"should_texture": False})),
        )
        self.assertEqual(
            40.0,
            gm.estimated_credits(
                gm.normalize_options(
                    {"texture_resolution": "8k", "ultra_mode": True},
                    view_count=1,
                )
            ),
        )

    def test_meshy_t2_cost_matrix(self):
        base = {"ai_model": "meshy-t2", "model_type": "smart-topology"}
        self.assertEqual(15.0, gm.estimated_credits(gm.normalize_options(base)))
        self.assertEqual(
            5.0,
            gm.estimated_credits(gm.normalize_options({**base, "should_texture": False})),
        )
        self.assertEqual(
            20.0,
            gm.estimated_credits(
                gm.normalize_options({**base, "texture_resolution": "8k"})
            ),
        )


class MeshyInputValidationTests(unittest.TestCase):
    def test_accepts_png_and_jpeg_signatures(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = os.path.join(tmp, "front.png")
            jpg = os.path.join(tmp, "side.jpg")
            with open(png, "wb") as handle:
                handle.write(b"\x89PNG\r\n\x1a\nrest")
            with open(jpg, "wb") as handle:
                handle.write(b"\xff\xd8\xffrest")
            self.assertEqual("front.png", gm.validate_reference_image(png)["name"])
            self.assertEqual("side.jpg", gm.validate_reference_image(jpg)["name"])

    def test_rejects_wrong_extension_and_spoofed_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = os.path.join(tmp, "secret.txt")
            spoof = os.path.join(tmp, "spoof.png")
            with open(text, "wb") as handle:
                handle.write(b"secret")
            with open(spoof, "wb") as handle:
                handle.write(b"not a png")
            with self.assertRaisesRegex(ValueError, "JPEG or PNG"):
                gm.validate_reference_image(text)
            with self.assertRaisesRegex(ValueError, "invalid file signature"):
                gm.validate_reference_image(spoof)

    def test_rejects_an_image_above_the_upload_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = os.path.join(tmp, "front.png")
            with open(image, "wb") as handle:
                handle.write(b"\x89PNG\r\n\x1a\nrest")
            with self.assertRaisesRegex(ValueError, "safety limit"):
                gm.validate_reference_image(image, max_bytes=8)

    def test_rejects_reference_set_above_the_aggregate_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            views = {}
            for name in ("front", "left"):
                path = os.path.join(tmp, "%s.png" % name)
                with open(path, "wb") as handle:
                    handle.write(b"\x89PNG\r\n\x1a\n1234")
                views[name] = path

            with self.assertRaisesRegex(ValueError, "job safety limit"):
                gm.validate_reference_images(
                    views,
                    max_image_bytes=32,
                    max_total_bytes=20,
                )


if __name__ == "__main__":
    unittest.main()
