from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
ADDON_ROOT = ROOT / "addon"
if str(ADDON_ROOT) not in sys.path:
    sys.path.insert(0, str(ADDON_ROOT))

from claude_blender import asset_job_worker  # noqa: E402


class AssetJobWorkerTests(unittest.TestCase):
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
