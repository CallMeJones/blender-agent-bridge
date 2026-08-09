from __future__ import annotations

import json
import os
import sys
import tempfile
import time
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


if __name__ == "__main__":
    unittest.main()


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
