from pathlib import Path
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "addon"))
from claude_blender import asset_job_worker, asset_provider_execution, generation_job


class ProviderExecutionTests(unittest.TestCase):
    def test_worker_modes_share_provider_inputs_and_results(self):
        for provider in ("tripo", "meshy", "studio_endpoint", "triposr"):
            with self.subTest(provider=provider), mock.patch.object(generation_job, "run", return_value={"ok": True, "manifest_path": "fixture.json"}) as run:
                config = {"provider": provider, "child_status_path": "unused"}
                args = {"views": {"front": "front.png"}, "api_key": "never-read-from-config"}
                direct = asset_provider_execution.execute(config, args, credentials={"token": "explicit-token"})
                direct_args = run.call_args
                with mock.patch.dict(os.environ, {asset_job_worker.ASSET_JOB_SECRET_TOKEN_ENV: "explicit-token"}):
                    worker = asset_job_worker.WORKER_DISPATCH[provider](config, args)
                self.assertEqual(direct, worker)
                self.assertEqual(direct_args.args, run.call_args.args)
                for key in ("provider", "api_key", "poll_interval"):
                    self.assertEqual(direct_args.kwargs[key], run.call_args.kwargs[key])
                self.assertNotIn("api_key", run.call_args.args[1])

    def test_cancellation_before_execution_prevents_provider_call(self):
        with mock.patch.object(generation_job, "run") as run:
            result = asset_provider_execution.execute({"provider": "meshy"}, {}, credentials={}, is_cancelled=lambda: True)
        self.assertFalse(result["ok"])
        self.assertTrue(result["cancelled"])
        run.assert_not_called()
