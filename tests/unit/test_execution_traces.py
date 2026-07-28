from __future__ import annotations

import os
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
os.sys.path.insert(0, str(ROOT / "addon"))

from claude_blender import execution_traces  # noqa: E402


class ExecutionTraceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(
            os.environ,
            {execution_traces.TRACE_ROOT_ENV: self.temp_dir.name},
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp_dir.cleanup()

    def test_trace_redacts_credentials_and_stores_script_as_local_artifact(self):
        started = execution_traces.start_trace(
            name="Trace test",
            prompt="Build a test object",
            metadata={"client": "unit", "api_token": "metadata-secret"},
        )
        trace_id = started["trace"]["trace_id"]
        self.assertEqual("", started["trace"]["prompt"])
        self.assertFalse(started["trace"]["prompt_stored"])
        self.assertEqual(len("Build a test object"), started["trace"]["prompt_chars"])
        self.assertEqual("[redacted]", started["trace"]["metadata"]["api_token"])
        execution_traces.record_tool_call(
            layer="bridge",
            tool_name="draft_script",
            arguments={
                "code": "import bpy\nbpy.ops.mesh.primitive_cube_add()\n",
                "api_token": "do-not-store",
                "intent": "Create cube",
            },
            result={"ok": True, "auto_ran": True, "image_base64": "large-secret-result"},
            duration_ms=12.5,
            contract={"mutates_scene": True},
        )

        trace = execution_traces.trace_status(trace_id, include_events=True)
        event = next(item for item in trace["events"] if item["event"] == "tool_call")
        arguments = event["data"]["arguments"]
        self.assertEqual("[redacted]", arguments["api_token"])
        self.assertIn("$artifact", arguments["code"])
        artifact_path = pathlib.Path(self.temp_dir.name, trace_id, arguments["code"]["$artifact"])
        self.assertEqual(
            "import bpy\nbpy.ops.mesh.primitive_cube_add()\n",
            artifact_path.read_text(encoding="utf-8"),
        )
        self.assertEqual("[redacted]", event["data"]["result"]["image_base64"])

        default_replay = execution_traces.prepare_replay(trace_id)
        self.assertFalse(default_replay["ready"])
        self.assertEqual(
            "<stored_script_artifact; request include_script_code to resolve>",
            default_replay["calls"][0]["gateway_call"]["arguments"]["arguments"]["code"],
        )
        self.assertTrue(default_replay["dry_run_only"])

        code_replay = execution_traces.prepare_replay(trace_id, include_script_code=True)
        self.assertEqual(
            "import bpy\nbpy.ops.mesh.primitive_cube_add()\n",
            code_replay["calls"][0]["gateway_call"]["arguments"]["arguments"]["code"],
        )
        self.assertIn("redacted", " ".join(code_replay["blockers"]).lower())

    def test_finalize_records_reported_tokens_and_clears_active_trace(self):
        started = execution_traces.start_trace(name="Tokens")
        trace_id = started["trace"]["trace_id"]
        finished = execution_traces.finalize_trace(
            trace_id,
            outcome="completed",
            token_usage={
                "input_tokens": 120,
                "output_tokens": 34,
                "cache_creation_input_tokens": 20,
            },
        )
        self.assertTrue(finished["ok"])
        self.assertEqual("completed", finished["trace"]["status"])
        self.assertEqual(
            {
                "input_tokens": 120,
                "output_tokens": 34,
                "cache_creation_input_tokens": 20,
            },
            finished["trace"]["provided_token_usage"],
        )
        self.assertEqual("", execution_traces.active_trace_id())


if __name__ == "__main__":
    unittest.main()
