from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "addon" / "claude_blender" / "reference_annotations.py"
SPEC = importlib.util.spec_from_file_location("reference_annotations", MODULE_PATH)
reference_annotations = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(reference_annotations)


class ReferenceAnnotationTests(unittest.TestCase):
    def test_pixel_canvas_rect_maps_to_normalized_reference_space(self):
        normalized = reference_annotations.normalize_annotation_document(
            {
                "version": 1,
                "subject": "test subject",
                "coordinate_space": "pixel",
                "origin": "top_left",
                "image_size": [1200, 700],
                "image_rect": [100, 100, 1000, 500],
                "landmarks": {"center": [600, 350]},
                "outlines": [
                    {
                        "name": "silhouette",
                        "points": [[100, 100], [1100, 600]],
                        "closed": True,
                    }
                ],
                "masses": [
                    {"name": "body", "bbox": [400, 200, 400, 200]}
                ],
                "measurements": [
                    {"name": "span", "from": "center", "to": "center"}
                ],
            },
            reference_image_size=[1000, 500],
        )

        self.assertEqual([0.5, 0.5], normalized["landmarks"][0]["point"])
        self.assertEqual(
            [[0.0, 0.0], [1.0, 1.0]],
            normalized["curves"][0]["points"],
        )
        self.assertTrue(normalized["curves"][0]["cyclic"])
        self.assertEqual([0.5, 0.4], normalized["masses"][0]["center"])
        self.assertEqual([0.2, 0.2], normalized["masses"][0]["radius"])
        self.assertEqual(
            {"landmarks": 1, "outlines": 1, "masses": 1, "measurements": 1},
            normalized["counts"],
        )

    def test_bottom_left_normalized_coordinates_are_flipped(self):
        normalized = reference_annotations.normalize_annotation_document(
            {
                "coordinate_space": "normalized",
                "origin": "bottom_left",
                "landmarks": [
                    {"name": "feature", "point": {"x": 0.25, "y": 0.2}}
                ],
            },
            reference_image_size=[800, 600],
        )

        self.assertEqual([0.25, 0.8], normalized["landmarks"][0]["point"])
        self.assertEqual("bottom_left", normalized["source_origin"])

    def test_normalized_image_rect_and_named_outline_map_are_calibrated(self):
        normalized = reference_annotations.normalize_annotation_document(
            {
                "coordinate_space": "normalized",
                "image_rect": [0.1, 0.2, 0.8, 0.6],
                "landmarks": {"center": [0.5, 0.5]},
                "outlines": {
                    "silhouette": [[0.1, 0.2], [0.9, 0.8]]
                },
                "masses": [
                    {
                        "name": "body",
                        "center": [0.5, 0.5],
                        "radius": [0.2, 0.15],
                    }
                ],
            },
            reference_image_size=[800, 600],
        )

        self.assertEqual([0.5, 0.5], normalized["landmarks"][0]["point"])
        self.assertEqual(
            [[0.0, 0.0], [1.0, 1.0]],
            normalized["curves"][0]["points"],
        )
        self.assertEqual([0.25, 0.25], normalized["masses"][0]["radius"])

    def test_out_of_bounds_points_are_clamped_and_reported(self):
        normalized = reference_annotations.normalize_annotation_document(
            {
                "coordinate_space": "pixel",
                "landmarks": [{"name": "edge", "point": [-2, 120]}],
            },
            reference_image_size=[100, 100],
        )

        self.assertEqual([0.0, 1.0], normalized["landmarks"][0]["point"])
        self.assertEqual(1, normalized["clamped_point_count"])
        self.assertTrue(normalized["warnings"])

    def test_measurement_landmark_names_are_canonicalized_and_checked(self):
        normalized = reference_annotations.normalize_annotation_document(
            {
                "coordinate_space": "normalized",
                "landmarks": {
                    "feature.left": [0.25, 0.5],
                    "feature/right": [0.75, 0.5],
                },
                "measurements": [
                    {
                        "name": "feature span",
                        "from": "feature.left",
                        "to": "feature/right",
                    }
                ],
            },
            reference_image_size=[100, 100],
        )

        self.assertEqual(
            ["feature_left", "feature_right"],
            [item["name"] for item in normalized["landmarks"]],
        )
        self.assertEqual("feature_left", normalized["measurements"][0]["from"])
        self.assertEqual("feature_right", normalized["measurements"][0]["to"])
        with self.assertRaisesRegex(
            reference_annotations.ReferenceAnnotationError,
            "unknown landmark",
        ):
            reference_annotations.normalize_annotation_document(
                {
                    "coordinate_space": "normalized",
                    "landmarks": {"feature": [0.5, 0.5]},
                    "measurements": [
                        {"name": "bad", "from": "feature", "to": "missing"}
                    ],
                },
                reference_image_size=[100, 100],
            )

    def test_json_path_loads_with_digest_and_sources_are_exclusive(self):
        document = {
            "coordinate_space": "normalized",
            "landmarks": [{"name": "feature", "point": [0.5, 0.5]}],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "annotations.json"
            path.write_text(json.dumps(document), encoding="utf-8")

            loaded, source = reference_annotations.load_annotation_document(
                annotations_path=str(path)
            )

        self.assertEqual(document, loaded)
        self.assertEqual("path", source["kind"])
        self.assertEqual(64, len(source["sha256"]))
        with self.assertRaisesRegex(
            reference_annotations.ReferenceAnnotationError,
            "exactly one",
        ):
            reference_annotations.load_annotation_document(
                annotations=document,
                annotations_json=json.dumps(document),
            )

    def test_invalid_optional_style_values_are_rejected_before_blender(self):
        with self.assertRaisesRegex(
            reference_annotations.ReferenceAnnotationError,
            "bevel_depth must be numeric",
        ):
            reference_annotations.normalize_annotation_document(
                {
                    "coordinate_space": "normalized",
                    "outlines": [
                        {
                            "name": "bad",
                            "points": [[0.0, 0.0], [1.0, 1.0]],
                            "bevel_depth": "wide",
                        }
                    ],
                },
                reference_image_size=[100, 100],
            )
        with self.assertRaisesRegex(
            reference_annotations.ReferenceAnnotationError,
            "closed must be true or false",
        ):
            reference_annotations.normalize_annotation_document(
                {
                    "coordinate_space": "normalized",
                    "outlines": [
                        {
                            "name": "bad",
                            "points": [[0.0, 0.0], [1.0, 1.0]],
                            "closed": "false",
                        }
                    ],
                },
                reference_image_size=[100, 100],
            )
        with self.assertRaisesRegex(
            reference_annotations.ReferenceAnnotationError,
            "unsupported annotation schema version",
        ):
            reference_annotations.normalize_annotation_document(
                {
                    "version": True,
                    "landmarks": {"center": [0.5, 0.5]},
                },
                reference_image_size=[100, 100],
            )
        with self.assertRaisesRegex(
            reference_annotations.ReferenceAnnotationError,
            "components must be between zero and one",
        ):
            reference_annotations.normalize_annotation_document(
                {
                    "coordinate_space": "normalized",
                    "masses": [
                        {
                            "name": "bad",
                            "center": [0.5, 0.5],
                            "radius": [0.1, 0.1],
                            "color": [2.0, 0.0, 0.0],
                        }
                    ],
                },
                reference_image_size=[100, 100],
            )


if __name__ == "__main__":
    unittest.main()
