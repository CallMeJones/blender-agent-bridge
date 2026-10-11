import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("smoke_runner", ROOT / "scripts/run_smoke_suite.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class SmokeManifestTests(unittest.TestCase):
    def test_manifest_covers_every_smoke_with_environment_and_lane(self):
        rows = runner.load_manifest()
        for row in rows:
            if "core" in row["lanes"]:
                self.assertIn("release", row["lanes"])
            self.assertGreater(row["timeout_seconds"], 0)
            self.assertTrue(row["success"])

    def test_previously_omitted_deterministic_tests_run_in_ci(self):
        rows = {row["name"]: row for row in runner.load_manifest()}
        for name in ("adaptive_manifold", "generated_manifest_evaluation", "modeling_quality_gate",
                     "reference_image_intake", "reference_part_graph", "shape_program", "user_functionality_pov"):
            self.assertIn("core", rows["smoke_" + name]["lanes"])


if __name__ == "__main__":
    unittest.main()
