from __future__ import annotations

import unittest

from tests import smoke_release_consistency


class ReleaseConsistencyPolicyTests(unittest.TestCase):
    def test_unreleased_changes_cannot_reuse_published_version(self):
        with self.assertRaisesRegex(AssertionError, "newer than the published artifact"):
            smoke_release_consistency._assert_release_state(
                "0.4.0",
                "0.4.0",
                "- changed behavior",
            )

    def test_unreleased_changes_use_next_working_version(self):
        smoke_release_consistency._assert_release_state(
            "0.4.1",
            "0.4.0",
            "- changed behavior",
        )

    def test_tag_requires_publication_version_and_empty_unreleased_section(self):
        with self.assertRaisesRegex(AssertionError, "release_state.toml"):
            smoke_release_consistency._assert_release_state(
                "0.4.1",
                "0.4.0",
                "",
                "refs/tags/v0.4.1",
            )
        with self.assertRaisesRegex(AssertionError, "Move Unreleased entries"):
            smoke_release_consistency._assert_release_state(
                "0.4.1",
                "0.4.1",
                "- not finalized",
                "refs/tags/v0.4.1",
            )


if __name__ == "__main__":
    unittest.main()
