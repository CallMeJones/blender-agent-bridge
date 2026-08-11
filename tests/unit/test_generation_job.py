from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock


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

    def upload_image(self, path, *, expected_identity=None):
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


def _run(tmp, views, *, client, collect=None, downloader=_fake_download, **args):
    from claude_blender import generation_job

    payload = {"views": views, "cache_dir": os.path.join(tmp, "cache")}
    payload.update(args)
    return generation_job.run(
        {"child_status_path": os.path.join(tmp, "s.json")},
        payload,
        api_key=API_KEY,
        client=client,
        downloader=downloader,
        poll_interval=0,
        progress_callback=collect.append if collect is not None else None,
    )


class GenerationJobTests(unittest.TestCase):
    def test_hosted_generation_download_rejects_file_and_private_urls(self):
        from claude_blender import external_assets, generation_job

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            external_assets,
            "DOWNLOAD_RETRY_COUNT",
            0,
        ), mock.patch.object(
            external_assets,
            "_online_access_error",
            return_value=None,
        ):
            for index, url in enumerate(
                (
                    "file:///etc/passwd",
                    "https://127.0.0.1/private.glb",
                    "https://10.1.2.3/private.glb",
                )
            ):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    generation_job._download(
                        url,
                        os.path.join(tmp, "rejected-%d.glb" % index),
                        max_bytes=1024,
                    )

    def test_generation_download_surfaces_hardened_size_limit_failure(self):
        from claude_blender import external_assets, generation_job

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            external_assets,
            "download_external_file",
            return_value={
                "ok": False,
                "message": "Download exceeded the 4-byte limit while streaming",
                "error_type": "download_size_limit_exceeded",
            },
        ) as download:
            with self.assertRaisesRegex(ValueError, "4-byte limit"):
                generation_job._download(
                    "https://cdn.example.test/model.glb",
                    os.path.join(tmp, "model.glb"),
                    max_bytes=4,
                )
        self.assertEqual(4, download.call_args.kwargs["max_download_bytes"])

    def test_generated_payload_checks_supported_model_formats(self):
        from claude_blender import generation_job

        invalid = {
            ".obj": b"<html>not an obj</html>",
            ".fbx": b"not an fbx",
            ".stl": b"not an stl",
        }
        with tempfile.TemporaryDirectory() as tmp:
            for suffix, payload in invalid.items():
                path = os.path.join(tmp, "model%s" % suffix)
                with open(path, "wb") as handle:
                    handle.write(payload)
                with self.subTest(suffix=suffix):
                    self.assertTrue(generation_job._generated_mesh_payload_error(path))

    def test_html_masquerading_as_glb_is_rejected_and_removed(self):
        def html_download(_url, destination, _timeout=300):
            with open(destination, "wb") as handle:
                handle.write(b"<html>provider error</html>")
            return {
                "ok": True,
                "size": os.path.getsize(destination),
                "content_type": "text/html; charset=utf-8",
            }

        with tempfile.TemporaryDirectory() as tmp:
            manifest = _run(
                tmp,
                _views(tmp, ["front"]),
                client=_StubClient(),
                downloader=html_download,
            )
            rejected_path = os.path.join(tmp, "cache", "generated.glb")
            self.assertFalse(manifest["ok"])
            self.assertIn("non-model content type", manifest["message"])
            self.assertFalse(os.path.exists(rejected_path))

    def test_same_origin_studio_artifact_receives_bearer_token(self):
        from claude_blender import generation_job

        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.headers = {"Content-Length": "9"}
        response.read.side_effect = [b"glTF-stub", b""]
        opener = mock.MagicMock()
        opener.open.return_value = response
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            generation_clients,
            "build_no_redirect_opener",
            return_value=opener,
        ):
            destination = os.path.join(tmp, "model.glb")
            generation_job._download_studio_artifact(
                "http://studio.local/api/files/model.glb",
                destination,
                endpoint="http://studio.local/api",
                api_key="studio-secret",
            )
            request = opener.open.call_args.args[0]
            self.assertEqual("Bearer studio-secret", request.get_header("Authorization"))
            self.assertTrue(os.path.isfile(destination))

    def test_cross_origin_studio_artifact_uses_unauthenticated_hosted_download(self):
        from claude_blender import generation_job

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            generation_job,
            "_download",
            return_value={"ok": True, "path": "model.glb", "size": 9},
        ) as download, mock.patch.object(
            generation_clients,
            "build_no_redirect_opener",
        ) as opener:
            generation_job._download_studio_artifact(
                "https://cdn.example.test/model.glb?signature=one-time",
                os.path.join(tmp, "model.glb"),
                endpoint="http://studio.local/api",
                api_key="studio-secret",
            )
        opener.assert_not_called()
        download.assert_called_once()

    def test_retryable_poll_failure_recovers_without_losing_task(self):
        class RetryClient(_StubClient):
            def __init__(self):
                super().__init__()
                self.polls = 0

            def task_status(self, task_id):
                self.polls += 1
                if self.polls == 1:
                    raise generation_clients.GenerationError(
                        "rate limited",
                        code=429,
                        retryable=True,
                        error_type="RateLimitExceeded",
                    )
                return super().task_status(task_id)

        updates = []
        with tempfile.TemporaryDirectory() as tmp:
            client = RetryClient()
            manifest = _run(
                tmp,
                _views(tmp, ["front"]),
                client=client,
                collect=updates,
            )
        self.assertTrue(manifest["ok"], manifest.get("message"))
        self.assertEqual(2, client.polls)
        self.assertEqual(1, manifest["generation"]["recovered_poll_failures"])
        self.assertIn("poll_retry", [update.get("phase") for update in updates])

    def test_non_retryable_poll_failure_preserves_structured_error(self):
        class FailedClient(_StubClient):
            def task_status(self, task_id):
                raise generation_clients.GenerationError(
                    "invalid input",
                    code=400,
                    retryable=False,
                    error_type="InvalidImageError",
                    doc_url="https://docs.meshy.ai/errors/input",
                )

        with tempfile.TemporaryDirectory() as tmp:
            manifest = _run(tmp, _views(tmp, ["front"]), client=FailedClient())
        self.assertFalse(manifest["ok"])
        self.assertEqual("InvalidImageError", manifest["provider_error"]["type"])
        self.assertEqual("https://docs.meshy.ai/errors/input", manifest["provider_error"]["doc_url"])

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

    def test_manifest_does_not_persist_signed_download_query(self):
        signed_url = "https://cdn.example/model.glb?Policy=secret&Signature=temporary"
        client = _StubClient(
            statuses=[
                {
                    "status": "success",
                    "terminal": True,
                    "succeeded": True,
                    "progress": 100,
                    "model_url": signed_url,
                }
            ]
        )
        downloaded = []

        def download(url, destination, timeout=300):
            downloaded.append(url)
            return _fake_download(url, destination, timeout)

        with tempfile.TemporaryDirectory() as tmp:
            from claude_blender import generation_job

            manifest = generation_job.run(
                {"child_status_path": os.path.join(tmp, "s.json")},
                {"views": _views(tmp, ["front"]), "cache_dir": os.path.join(tmp, "cache")},
                api_key=API_KEY,
                client=client,
                downloader=download,
                poll_interval=0,
            )
        self.assertEqual([signed_url], downloaded)
        self.assertEqual("https://cdn.example/model.glb", manifest["source_url"])

    def test_meshy_manifest_caches_provider_artifacts_without_signed_queries(self):
        client = _StubClient(
            statuses=[
                {
                    "status": "succeeded",
                    "terminal": True,
                    "succeeded": True,
                    "progress": 100,
                    "model_url": "https://cdn.example/model.glb?Signature=final",
                    "artifact_urls": {
                        "glb": "https://cdn.example/model.glb?Signature=final",
                        "pre_remeshed_glb": "https://cdn.example/raw.glb?Signature=raw",
                        "thumbnail_front": "https://cdn.example/front.png?Signature=front",
                        "texture_0_base_color": "https://cdn.example/base.png?Signature=base",
                    },
                    "credits_consumed": 30,
                    "expires_at": 123456,
                    "preceding_tasks": 2,
                }
            ]
        )

        def download(url, destination, timeout=300):
            with open(destination, "wb") as handle:
                handle.write(b"\x89PNG\r\n\x1a\n" if destination.endswith(".png") else b"glTF-stub")
            return {"ok": True, "size": os.path.getsize(destination), "sha256": "digest"}

        with tempfile.TemporaryDirectory() as tmp:
            from claude_blender import generation_job

            manifest = generation_job.run(
                {"child_status_path": os.path.join(tmp, "s.json")},
                {
                    "views": _views(tmp, ["front"]),
                    "cache_dir": os.path.join(tmp, "cache"),
                    "provider": "meshy",
                },
                provider="meshy",
                api_key=API_KEY,
                client=client,
                downloader=download,
                poll_interval=0,
            )
            self.assertTrue(manifest["ok"], manifest.get("message"))
            self.assertEqual(
                {"model", "pre_remeshed_glb", "thumbnail_front", "texture_0_base_color"},
                {entry["role"] for entry in manifest["downloaded_files"]},
            )
            self.assertEqual("https://cdn.example/raw.glb", manifest["generation"]["artifact_sources"]["pre_remeshed_glb"])
            self.assertEqual(123456, manifest["generation"]["expires_at"])
            self.assertEqual(2, manifest["generation"]["preceding_tasks"])
            with open(manifest["manifest_path"], "r", encoding="utf-8") as handle:
                persisted = handle.read()
        self.assertNotIn("Signature=", persisted)

    def test_auxiliary_artifacts_stop_at_the_aggregate_download_limit(self):
        from claude_blender import generation_job

        client = _StubClient(
            statuses=[
                {
                    "status": "succeeded",
                    "terminal": True,
                    "succeeded": True,
                    "progress": 100,
                    "model_url": "https://cdn.example/model.glb",
                    "artifact_urls": {
                        "thumbnail_front": "https://cdn.example/front.png",
                        "thumbnail_left": "https://cdn.example/left.png",
                    },
                }
            ]
        )

        def download(_url, destination, _timeout=300):
            with open(destination, "wb") as handle:
                handle.write(b"glTF-stub")
            return 9

        original_limit = generation_job.MAX_GENERATION_DOWNLOAD_BYTES
        try:
            generation_job.MAX_GENERATION_DOWNLOAD_BYTES = 20
            with tempfile.TemporaryDirectory() as tmp:
                manifest = generation_job.run(
                    {"child_status_path": os.path.join(tmp, "s.json")},
                    {
                        "views": _views(tmp, ["front"]),
                        "cache_dir": os.path.join(tmp, "cache"),
                        "provider": "meshy",
                    },
                    provider="meshy",
                    api_key=API_KEY,
                    client=client,
                    downloader=download,
                    poll_interval=0,
                )
                self.assertEqual(18, manifest["bytes"])
                self.assertEqual(
                    {"model", "thumbnail_front"},
                    {entry["role"] for entry in manifest["downloaded_files"]},
                )
                self.assertFalse(os.path.exists(os.path.join(tmp, "cache", "meshy_thumbnail_left.png")))
        finally:
            generation_job.MAX_GENERATION_DOWNLOAD_BYTES = original_limit

        self.assertTrue(manifest["ok"], manifest.get("message"))
        self.assertIn("remaining generation job download limit", " ".join(manifest["generation"]["artifact_warnings"]))

    def test_meshy_file_removed_after_balance_is_a_structured_upload_failure(self):
        from claude_blender import generation_job

        with tempfile.TemporaryDirectory() as tmp:
            views = _views(tmp, ["front"])
            image_path = views["front"]

            def transport(_method, url, _headers, _body, _timeout):
                self.assertTrue(url.endswith("/balance"))
                os.remove(image_path)
                return 200, json.dumps({"balance": 1000})

            manifest = generation_job.run(
                {"child_status_path": os.path.join(tmp, "s.json")},
                {
                    "views": views,
                    "cache_dir": os.path.join(tmp, "cache"),
                    "provider": "meshy",
                },
                provider="meshy",
                api_key=API_KEY,
                client=generation_clients.MeshyClient(API_KEY, transport=transport),
                downloader=_fake_download,
                poll_interval=0,
            )

        self.assertFalse(manifest["ok"])
        self.assertFalse(manifest["uploaded"])
        self.assertIn("Upload failed", manifest["message"])
        self.assertEqual("invalid_local_input", manifest["provider_error"]["type"])

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

    def test_failed_remote_status_distinguishes_invalid_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = _StubClient(
                statuses=[
                    {
                        "status": "failed",
                        "terminal": True,
                        "succeeded": False,
                        "error_message": "reference was rejected",
                        "task_error": {
                            "type": "invalid_input",
                            "code": "image_too_complex",
                            "message": "reference was rejected",
                            "doc_url": "https://docs.meshy.ai/en/api/errors#image-too-complex",
                        },
                    }
                ]
            )
            manifest = _run(tmp, _views(tmp, ["front"]), client=client)
        self.assertEqual("invalid_input", manifest["failure_category"])
        self.assertEqual("image_too_complex", manifest["task_error"]["code"])

    def test_progress_is_reported_through_the_callback(self):
        updates = []
        with tempfile.TemporaryDirectory() as tmp:
            _run(tmp, _views(tmp, ["front"]), client=_StubClient(), collect=updates)
        self.assertTrue(updates)
        self.assertEqual(1.0, updates[-1]["progress"])
        self.assertIn("upload", [u.get("phase") for u in updates])
        submitted = next(update for update in updates if update.get("task_id") == "task-img")
        self.assertEqual("image", submitted["task_kind"])
        task_updates = [update for update in updates if update.get("task_id") == "task-img"]
        self.assertTrue(task_updates)
        self.assertTrue(all(update.get("task_kind") == "image" for update in task_updates))

    def test_multiview_progress_keeps_task_kind_after_submit(self):
        updates = []
        with tempfile.TemporaryDirectory() as tmp:
            client = _StubClient(
                statuses=[
                    {"status": "running", "terminal": False, "succeeded": False, "progress": 25},
                    {
                        "status": "success",
                        "terminal": True,
                        "succeeded": True,
                        "progress": 100,
                        "model_url": "https://x/model.glb",
                    },
                ]
            )
            _run(tmp, _views(tmp, ["front", "left"]), client=client, collect=updates)
        task_updates = [update for update in updates if update.get("task_id") == "task-mv"]

        self.assertTrue(task_updates)
        self.assertTrue(all(update.get("task_kind") == "multiview" for update in task_updates))

    def test_provider_name_is_preserved_for_meshy_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = _StubClient()
            manifest = _run(tmp, _views(tmp, ["front"]), client=client, provider="meshy")
        self.assertTrue(manifest["ok"], manifest.get("message"))
        self.assertEqual("meshy", manifest["provider"])
        self.assertEqual("image", client.created[0])

    def test_studio_endpoint_can_run_without_a_token(self):
        from claude_blender import generation_job

        with tempfile.TemporaryDirectory() as tmp:
            manifest = generation_job.run(
                {"child_status_path": os.path.join(tmp, "s.json")},
                {
                    "views": _views(tmp, ["front"]),
                    "cache_dir": os.path.join(tmp, "cache"),
                    "provider": "studio_endpoint",
                },
                provider="studio_endpoint",
                api_key="",
                client=_StubClient(),
                downloader=_fake_download,
                poll_interval=0,
            )
        self.assertTrue(manifest["ok"], manifest.get("message"))
        self.assertEqual("studio_endpoint", manifest["provider"])

    def test_triposr_missing_runtime_fails_before_local_process(self):
        from claude_blender import generation_job

        with tempfile.TemporaryDirectory() as tmp:
            manifest = generation_job.run(
                {"child_status_path": os.path.join(tmp, "s.json")},
                {
                    "views": _views(tmp, ["front"]),
                    "cache_dir": os.path.join(tmp, "cache"),
                    "provider": "triposr",
                },
                provider="triposr",
                poll_interval=0,
            )
        self.assertFalse(manifest["ok"])
        self.assertEqual("triposr", manifest["provider"])
        self.assertIn("runtime_python", manifest["message"])

    def test_triposr_precreates_indexed_output_folder(self):
        from claude_blender import generation_job

        with tempfile.TemporaryDirectory() as tmp:
            runtime_root = os.path.join(tmp, "triposr")
            os.makedirs(runtime_root)
            run_py = os.path.join(runtime_root, "run.py")
            with open(run_py, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(
                    "import argparse, os\n"
                    "parser = argparse.ArgumentParser()\n"
                    "parser.add_argument('image')\n"
                    "parser.add_argument('--output-dir', required=True)\n"
                    "parser.add_argument('--model-save-format', default='glb')\n"
                    "args, _ = parser.parse_known_args()\n"
                    "target = os.path.join(args.output_dir, '0')\n"
                    "if not os.path.isdir(target):\n"
                    "    raise SystemExit('missing indexed output folder')\n"
                    "with open(os.path.join(target, 'mesh.' + args.model_save_format), 'wb') as out:\n"
                    "    out.write(b'glTF-stub')\n"
                )
            manifest = generation_job.run(
                {"child_status_path": os.path.join(tmp, "s.json")},
                {
                    "views": _views(tmp, ["front"]),
                    "cache_dir": os.path.join(tmp, "cache"),
                    "provider": "triposr",
                    "runtime_python": sys.executable,
                    "runtime_root": runtime_root,
                    "timeout": 30,
                },
                provider="triposr",
                poll_interval=0,
            )
        self.assertTrue(manifest["ok"], manifest.get("message"))
        self.assertEqual("triposr", manifest["provider"])
        self.assertEqual("generated.glb", os.path.basename(manifest["import_file"]))

    def test_triposr_timeout_is_reported_distinctly(self):
        from claude_blender import generation_job

        with tempfile.TemporaryDirectory() as tmp:
            runtime_root = os.path.join(tmp, "triposr")
            os.makedirs(runtime_root)
            with open(os.path.join(runtime_root, "run.py"), "w", encoding="utf-8", newline="\n") as handle:
                handle.write("import time\ntime.sleep(30)\n")
            started = time.monotonic()
            manifest = generation_job.run(
                {"child_status_path": os.path.join(tmp, "s.json")},
                {
                    "views": _views(tmp, ["front"]),
                    "cache_dir": os.path.join(tmp, "cache"),
                    "provider": "triposr",
                    "runtime_python": sys.executable,
                    "runtime_root": runtime_root,
                    "timeout": 1,
                },
                provider="triposr",
                poll_interval=0,
            )
            elapsed = time.monotonic() - started
        self.assertFalse(manifest["ok"])
        self.assertIn("timed out after 1 seconds", manifest["message"])
        self.assertLess(elapsed, 10)

    def test_triposr_passes_tunable_runtime_flags(self):
        from claude_blender import generation_job

        with tempfile.TemporaryDirectory() as tmp:
            runtime_root = os.path.join(tmp, "triposr")
            os.makedirs(runtime_root)
            run_py = os.path.join(runtime_root, "run.py")
            with open(run_py, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(
                    "import argparse, json, os\n"
                    "parser = argparse.ArgumentParser()\n"
                    "parser.add_argument('image')\n"
                    "parser.add_argument('--output-dir', required=True)\n"
                    "parser.add_argument('--model-save-format', default='glb')\n"
                    "parser.add_argument('--mc-resolution', type=int)\n"
                    "parser.add_argument('--foreground-ratio', type=float)\n"
                    "parser.add_argument('--chunk-size', type=int)\n"
                    "parser.add_argument('--no-remove-bg', action='store_true')\n"
                    "parser.add_argument('--bake-texture', action='store_true')\n"
                    "parser.add_argument('--texture-resolution', type=int)\n"
                    "args, _ = parser.parse_known_args()\n"
                    "target = os.path.join(args.output_dir, '0')\n"
                    "os.makedirs(target, exist_ok=True)\n"
                    "with open(os.path.join(args.output_dir, 'flags.json'), 'w', encoding='utf-8') as out:\n"
                    "    json.dump(vars(args), out, sort_keys=True)\n"
                    "with open(os.path.join(target, 'mesh.' + args.model_save_format), 'wb') as out:\n"
                    "    out.write(b'glTF-stub')\n"
                )
            cache_dir = os.path.join(tmp, "cache")
            manifest = generation_job.run(
                {"child_status_path": os.path.join(tmp, "s.json")},
                {
                    "views": _views(tmp, ["front"]),
                    "cache_dir": cache_dir,
                    "provider": "triposr",
                    "runtime_python": sys.executable,
                    "runtime_root": runtime_root,
                    "timeout": 30,
                    "mc_resolution": 64,
                    "foreground_ratio": 0.7,
                    "chunk_size": 4096,
                    "bake_texture": True,
                    "texture_resolution": 1024,
                },
                provider="triposr",
                poll_interval=0,
            )
            with open(
                os.path.join(cache_dir, "triposr-output", "flags.json"),
                "r",
                encoding="utf-8",
            ) as handle:
                flags = json.load(handle)
        self.assertTrue(manifest["ok"], manifest.get("message"))
        self.assertEqual(64, flags["mc_resolution"])
        self.assertEqual(0.7, flags["foreground_ratio"])
        self.assertEqual(4096, flags["chunk_size"])
        self.assertTrue(flags["bake_texture"])
        self.assertEqual(1024, flags["texture_resolution"])
        self.assertEqual("local_blockout", manifest["generation"]["intended_use"])
        self.assertEqual(64, manifest["generation"]["triposr_options"]["mc_resolution"])
        self.assertEqual(
            "device_aligned_positions",
            manifest["generation"]["texture_bake_compatibility"],
        )
        self.assertEqual(
            "xatlas_obj_atlas_embedded_glb",
            manifest["generation"]["texture_bake_export_compatibility"],
        )

    def test_triposr_rejects_obj_payload_mislabeled_as_glb(self):
        from claude_blender import generation_job

        with tempfile.TemporaryDirectory() as tmp:
            runtime_root = os.path.join(tmp, "triposr")
            os.makedirs(runtime_root)
            with open(
                os.path.join(runtime_root, "run.py"),
                "w",
                encoding="utf-8",
                newline="\n",
            ) as handle:
                handle.write(
                    "import argparse, os\n"
                    "parser = argparse.ArgumentParser()\n"
                    "parser.add_argument('image')\n"
                    "parser.add_argument('--output-dir', required=True)\n"
                    "args, _ = parser.parse_known_args()\n"
                    "target = os.path.join(args.output_dir, '0')\n"
                    "os.makedirs(target, exist_ok=True)\n"
                    "with open(os.path.join(target, 'mesh.glb'), 'wb') as out:\n"
                    "    out.write(b'v 0 0 0\\n')\n"
                )
            manifest = generation_job.run(
                {"child_status_path": os.path.join(tmp, "s.json")},
                {
                    "views": _views(tmp, ["front"]),
                    "cache_dir": os.path.join(tmp, "cache"),
                    "provider": "triposr",
                    "runtime_python": sys.executable,
                    "runtime_root": runtime_root,
                    "timeout": 30,
                },
                provider="triposr",
                poll_interval=0,
            )
        self.assertFalse(manifest["ok"])
        self.assertIn("does not contain a GLB payload", manifest["message"])

class _BalanceClient(_StubClient):
    """A stub that can report an account balance, like the real client."""

    def __init__(self, credits, **kwargs):
        super().__init__(**kwargs)
        self._credits = credits
        self.balance_calls = 0

    def balance(self):
        self.balance_calls += 1
        if isinstance(self._credits, Exception):
            raise self._credits
        return self._credits


class BalanceGateTests(unittest.TestCase):
    """Funds are checked before anything leaves the machine."""

    def test_a_short_account_fails_before_upload(self):
        # The bad order is: approve, upload the user's art, then discover the
        # account cannot pay. Nothing should leave the machine first.
        with tempfile.TemporaryDirectory() as tmp:
            client = _BalanceClient(10.0)
            manifest = _run(tmp, _views(tmp, ["front"]), client=client)
        self.assertFalse(manifest["ok"])
        self.assertIn("Not enough credits", manifest["message"])
        self.assertIn("nothing was charged", manifest["message"])
        self.assertEqual(10.0, manifest["credits_available"])
        self.assertEqual(30.0, manifest["credits_required"])
        self.assertFalse(manifest["uploaded"])
        self.assertEqual([], client.uploaded)
        self.assertIsNone(client.created)

    def test_a_short_account_with_real_balance_payload_fails_before_upload(self):
        # Real Tripo balance responses are dictionaries, not bare numbers.
        with tempfile.TemporaryDirectory() as tmp:
            client = _BalanceClient({"balance": 10.0, "frozen": 0.0})
            manifest = _run(tmp, _views(tmp, ["front"]), client=client)
        self.assertFalse(manifest["ok"])
        self.assertIn("Not enough credits", manifest["message"])
        self.assertEqual([], client.uploaded)
        self.assertIsNone(client.created)

    def test_a_funded_account_proceeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = _BalanceClient(1000.0)
            manifest = _run(tmp, _views(tmp, ["front"]), client=client)
        self.assertTrue(manifest["ok"], manifest.get("message"))
        self.assertEqual(1, client.balance_calls)
        self.assertEqual("image", client.created[0])

    def test_exactly_enough_credit_proceeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = _run(tmp, _views(tmp, ["front"]), client=_BalanceClient(30.0))
        self.assertTrue(manifest["ok"], manifest.get("message"))

    def test_an_unreadable_balance_does_not_block_an_approved_job(self):
        # The user already approved the spend. A balance endpoint that is
        # unreachable or unrecognised must not veto that; the vendor rejects
        # the task later if funds really are short.
        error = generation_clients.GenerationError("balance endpoint unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            manifest = _run(tmp, _views(tmp, ["front"]), client=_BalanceClient(error))
        self.assertTrue(manifest["ok"], manifest.get("message"))

    def test_a_client_without_a_balance_method_still_runs(self):
        # Injected clients in other suites do not implement balance().
        with tempfile.TemporaryDirectory() as tmp:
            manifest = _run(tmp, _views(tmp, ["front"]), client=_StubClient())
        self.assertTrue(manifest["ok"], manifest.get("message"))

    def test_meshy_uses_the_configured_exact_cost_before_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = _BalanceClient(19.0)
            manifest = _run(
                tmp,
                _views(tmp, ["front"]),
                client=client,
                provider="meshy",
                meshy_options={"should_texture": False},
            )
        self.assertFalse(manifest["ok"])
        self.assertEqual(20.0, manifest["credits_required"])
        self.assertEqual([], client.uploaded)

    def test_meshy_ultra_8k_requires_forty_credits(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = _BalanceClient(39.0)
            manifest = _run(
                tmp,
                _views(tmp, ["front"]),
                client=client,
                provider="meshy",
                meshy_options={"texture_resolution": "8k", "ultra_mode": True},
            )
        self.assertFalse(manifest["ok"])
        self.assertEqual(40.0, manifest["credits_required"])
        self.assertEqual([], client.uploaded)

    def test_tripo_p1_texture_requires_fifty_credits_before_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = _BalanceClient(49.0)
            manifest = _run(
                tmp,
                _views(tmp, ["front"]),
                client=client,
                model="P1-20260311",
                texture=True,
            )
        self.assertFalse(manifest["ok"])
        self.assertEqual(50.0, manifest["credits_required"])
        self.assertEqual([], client.uploaded)

    def test_tripo_manifest_records_resolved_pricing_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = _run(
                tmp,
                _views(tmp, ["front"]),
                client=_BalanceClient(50.0),
                model="P1-20260311",
                texture=True,
            )
        self.assertTrue(manifest["ok"], manifest.get("message"))
        self.assertEqual(50.0, manifest["generation"]["estimated_credits"])
        self.assertEqual("tripo-api-2026-06-03", manifest["generation"]["pricing_version"])


if __name__ == "__main__":
    unittest.main()
