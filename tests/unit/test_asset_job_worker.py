from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
ADDON_ROOT = ROOT / "addon"
if str(ADDON_ROOT) not in sys.path:
    sys.path.insert(0, str(ADDON_ROOT))

from claude_blender import asset_job_worker  # noqa: E402


class AssetJobWorkerTests(unittest.TestCase):
    def test_status_write_retries_transient_windows_replace_contention(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "child-status.json")
            real_replace = os.replace
            replace_calls = 0

            def contend_once(source, destination):
                nonlocal replace_calls
                replace_calls += 1
                if replace_calls == 1:
                    raise PermissionError(13, "status file is temporarily in use", destination)
                return real_replace(source, destination)

            with mock.patch.object(asset_job_worker.os, "replace", side_effect=contend_once), mock.patch.object(
                asset_job_worker.time,
                "sleep",
            ) as sleep:
                asset_job_worker._write_json(path, {"status": "running"})

            self.assertEqual(replace_calls, 2)
            sleep.assert_called_once_with(asset_job_worker.STATUS_REPLACE_INITIAL_DELAY_SECONDS)
            self.assertEqual(asset_job_worker._read_json(path), {"status": "running"})

    def test_status_write_stops_after_bounded_replace_retries(self):
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            asset_job_worker.os,
            "replace",
            side_effect=PermissionError(13, "status file remains in use"),
        ) as replace, mock.patch.object(asset_job_worker.time, "sleep") as sleep:
            path = os.path.join(temp_dir, "child-status.json")

            with self.assertRaises(PermissionError):
                asset_job_worker._write_json(path, {"status": "running"})

            self.assertEqual(replace.call_count, asset_job_worker.STATUS_REPLACE_ATTEMPTS)
            self.assertEqual(sleep.call_count, asset_job_worker.STATUS_REPLACE_ATTEMPTS - 1)

    def test_background_sketchfab_worker_forwards_provenance_but_reads_secrets_from_env(self):
        provenance = {
            "model_name": "Worker Fixture",
            "author": "Fixture Artist",
            "license": "CC BY 4.0",
            "model_url": "https://sketchfab.com/3d-models/worker-fixture-abc123",
        }
        args = {
            "uid": "abc123",
            "api_token": "must-not-be-read-from-config",
            "model_password": "must-not-be-read-from-config",
            "provenance": provenance,
        }
        secrets = {
            asset_job_worker.ASSET_JOB_SECRET_TOKEN_ENV: "worker-token",
            asset_job_worker.ASSET_JOB_SECRET_PASSWORD_ENV: "worker-password",
        }
        with mock.patch.dict(os.environ, secrets, clear=False), mock.patch.object(
            asset_job_worker.external_assets,
            "download_sketchfab_model",
            return_value={"ok": True},
        ) as download:
            result = asset_job_worker._download_sketchfab({"child_status_path": "unused"}, args)

        self.assertTrue(result["ok"])
        kwargs = download.call_args.kwargs
        self.assertEqual(kwargs["api_token"], "worker-token")
        self.assertEqual(kwargs["model_password"], "worker-password")
        self.assertEqual(kwargs["provenance"], provenance)


if __name__ == "__main__":
    unittest.main()
