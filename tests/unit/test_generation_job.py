from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import generation_clients  # noqa: E402


API_KEY = "tsk_job_secret_must_not_reach_disk"


class _StubClient:
    """Stands in for TripoClient so no network or credits are involved."""

    def __init__(self, *, statuses=None, fail_on=""):
        self.statuses = list(statuses or [{"status": "success", "terminal": True, "succeeded": True,
                                           "progress": 100, "model_url": "https://x/model.glb",
                                           "credits_consumed": 20}])
        self.fail_on = fail_on
        self.uploaded = []
        self.created = None

    def upload_image(self, path):
        if self.fail_on == "upload":
            raise generation_clients.GenerationError("upload boom")
        self.uploaded.append(path)
        return "file_%d" % len(self.uploaded)

    def create_image_task(self, token, path="", **kwargs):
        if self.fail_on == "credit":
            raise generation_clients.GenerationError("no credit", code=2010, insufficient_credit=True)
        self.created = ("image", token, kwargs)
        return "task-img"

    def create_multiview_task(self, views, **kwargs):
        self.created = ("multiview", dict(views), kwargs)
        return "task-mv"

    def task_status(self, task_id):
        return self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]


def _views(tmp, names):
    made = {}
    for name in names:
        path = os.path.join(tmp, "%s.png" % name)
        with open(path, "wb") as handle:
            handle.write(b"\x89PNG\r\n\x1a\n")
        made[name] = path
    return made


def _fake_download(url, destination, timeout=300):
    with open(destination, "wb") as handle:
        handle.write(b"glTF-stub")
    return 9


def _run(tmp, views, *, client, collect=None, **args):
    from claude_blender import generation_job

    payload = {"views": views, "cache_dir": os.path.join(tmp, "cache")}
    payload.update(args)
    return generation_job.run(
        {"child_status_path": os.path.join(tmp, "s.json")},
        payload,
        api_key=API_KEY,
        client=client,
        downloader=_fake_download,
        poll_interval=0,
        progress_callback=collect.append if collect is not None else None,
    )


class GenerationJobTests(unittest.TestCase):
    def test_single_view_uses_image_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = _StubClient()
            manifest = _run(tmp, _views(tmp, ["front"]), client=client)
        self.assertTrue(manifest["ok"], manifest.get("message"))
        self.assertEqual("image", client.created[0])
        self.assertEqual(1, manifest["generation"]["view_count"])

    def test_multiple_views_use_multiview_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = _StubClient()
            manifest = _run(tmp, _views(tmp, ["front", "left", "back"]), client=client)
        self.assertTrue(manifest["ok"], manifest.get("message"))
        self.assertEqual("multiview", client.created[0])
        self.assertEqual(["back", "front", "left"], manifest["generation"]["view_names"])

    def test_manifest_matches_external_asset_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = _run(tmp, _views(tmp, ["front"]), client=_StubClient())
            # Assert inside the context: the temp dir holds the written files.
            self.assertTrue(os.path.isfile(manifest["manifest_path"]))
            self.assertTrue(os.path.isfile(manifest["import_file"]))
        # These keys are what the shared import/presentation tail consumes.
        for key in ("ok", "provider", "cache_dir", "manifest_path", "import_file", "downloaded_files", "license", "source_url"):
            self.assertIn(key, manifest)

    def test_missing_image_fails_before_any_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = _StubClient()
            manifest = _run(tmp, {"front": os.path.join(tmp, "nope.png")}, client=client)
        self.assertFalse(manifest["ok"])
        self.assertIn("not found", manifest["message"])
        self.assertEqual([], client.uploaded)

    def test_no_key_fails_without_contacting_provider(self):
        from claude_blender import generation_job

        with tempfile.TemporaryDirectory() as tmp:
            manifest = generation_job.run(
                {"child_status_path": os.path.join(tmp, "s.json")},
                {"views": _views(tmp, ["front"]), "cache_dir": os.path.join(tmp, "cache")},
                api_key="",
                client=_StubClient(),
            )
        self.assertFalse(manifest["ok"])
        self.assertIn("API key", manifest["message"])

    def test_insufficient_credit_is_flagged_on_the_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = _run(tmp, _views(tmp, ["front"]), client=_StubClient(fail_on="credit"))
        self.assertFalse(manifest["ok"])
        self.assertTrue(manifest.get("insufficient_credit"))

    def test_upload_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = _run(tmp, _views(tmp, ["front"]), client=_StubClient(fail_on="upload"))
        self.assertFalse(manifest["ok"])
        self.assertIn("Upload failed", manifest["message"])

    def test_failed_remote_status_does_not_claim_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = _StubClient(statuses=[{"status": "failed", "terminal": True, "succeeded": False}])
            manifest = _run(tmp, _views(tmp, ["front"]), client=client)
        self.assertFalse(manifest["ok"])
        self.assertIn("failed", manifest["message"])

    def test_progress_is_reported_through_the_callback(self):
        updates = []
        with tempfile.TemporaryDirectory() as tmp:
            _run(tmp, _views(tmp, ["front"]), client=_StubClient(), collect=updates)
        self.assertTrue(updates)
        self.assertEqual(1.0, updates[-1]["progress"])
        self.assertIn("upload", [u.get("phase") for u in updates])


if __name__ == "__main__":
    unittest.main()
