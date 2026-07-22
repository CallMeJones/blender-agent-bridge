import os
import sys
import unittest
from unittest import mock


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import blender_compat, build_info  # noqa: E402


class BlenderCompatibilityTests(unittest.TestCase):
    def test_node_only_owner_does_not_read_deprecated_use_nodes(self):
        tree = object()

        class NodeOnlyOwner:
            node_tree = tree

            @property
            def use_nodes(self):
                raise AssertionError("deprecated use_nodes getter was evaluated")

        owner = NodeOnlyOwner()
        self.assertIs(tree, blender_compat.node_tree(owner))
        self.assertTrue(blender_compat.node_tree_enabled(owner))
        self.assertIs(tree, blender_compat.ensure_node_tree(owner))
        blender_compat.restore_node_tree_enabled(owner, True)

    def test_compositor_group_is_the_canonical_scene_tree(self):
        tree = object()
        owner = type("SceneOwner", (), {"compositing_node_group": tree, "node_tree": None})()
        self.assertIs(tree, blender_compat.node_tree(owner))
        self.assertTrue(blender_compat.node_tree_enabled(owner))

    def test_minimum_and_tested_release_lines(self):
        minimum = blender_compat.compatibility_report("4.2.0")
        self.assertTrue(minimum["supported"])
        self.assertTrue(minimum["tested"])
        self.assertEqual("tested", minimum["status"])
        self.assertEqual((4, 2, 0), build_info.BLENDER_VERSION_MIN_TUPLE)

    def test_below_minimum_is_unsupported(self):
        report = blender_compat.compatibility_report((4, 1, 9))
        self.assertFalse(report["supported"])
        self.assertEqual("unsupported", report["status"])

    def test_future_versions_are_allowed_with_warning(self):
        report = blender_compat.compatibility_report("7.0.0 Alpha")
        self.assertTrue(report["supported"])
        self.assertFalse(report["tested"])
        self.assertEqual("compatible_untested", report["status"])

    def test_stale_runtime_diagnostics_include_reload_guidance(self):
        with mock.patch.object(build_info, "source_tree_hash", return_value="changed"):
            with mock.patch.object(build_info, "LOADED_SOURCE_HASH", "loaded"):
                diagnostics = build_info.diagnostics_dict(blender_version="4.5.1")
        self.assertTrue(diagnostics["addon_reload_required"])
        self.assertIn("Reload Scripts", diagnostics["addon_reload_guidance"])
        self.assertEqual("tested", diagnostics["blender_compatibility"]["status"])

    def test_diagnostics_summary_hashes_source_once(self):
        with mock.patch.object(build_info, "source_tree_hash", return_value="current") as source_hash:
            with mock.patch.object(build_info, "LOADED_SOURCE_HASH", "loaded"):
                summary = build_info.diagnostics_summary()

        self.assertEqual(1, source_hash.call_count)
        self.assertIn("Source current", summary)
        self.assertIn("Runtime stale", summary)

    def test_diagnostics_summary_reuses_existing_diagnostics(self):
        diagnostics = {
            "addon_source_hash": "existing",
            "addon_runtime_source_stale": False,
        }
        with mock.patch.object(build_info, "source_tree_hash") as source_hash:
            summary = build_info.diagnostics_summary(diagnostics)

        source_hash.assert_not_called()
        self.assertIn("Source existing", summary)


if __name__ == "__main__":
    unittest.main()
