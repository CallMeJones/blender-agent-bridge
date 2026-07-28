"""Blender smoke test for isolated background trusted-script jobs."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import (  # noqa: E402
    bridge_server,
    preferences,
    script_runner,
    tool_dispatcher,
    trusted_script_jobs,
)


OBJECT_NAME = "Trusted Script Job Smoke Object"
TIMEOUT_SECONDS = int(os.environ.get("BAB_TRUSTED_SCRIPT_JOB_SMOKE_TIMEOUT_SECONDS", "90"))


def _execute(name, args=None):
    return json.loads(tool_dispatcher.execute_tool(bpy.context, name, args or {}))


def _wait(job_id):
    deadline = time.time() + TIMEOUT_SECONDS
    status = {}
    while time.time() < deadline:
        payload = _execute("get_trusted_script_job_status", {"job_id": job_id})
        assert payload["ok"] is True, payload
        status = payload["trusted_script_job"]
        if status["status"] in {"completed", "failed", "cancelled"}:
            return status
        time.sleep(0.5)
    raise AssertionError(f"Trusted script job timed out: {status}")


def main():
    root = tempfile.mkdtemp(prefix="blender-agent-trusted-script-jobs-")
    jobs_root = os.path.join(root, "jobs")
    checkpoint_root = os.path.join(root, "checkpoints")
    original_job_root = trusted_script_jobs._root
    original_get_preferences = preferences.get_preferences
    old_bridge_token = os.environ.get("BLENDER_BRIDGE_TOKEN")
    old_bridge_url = os.environ.get("BLENDER_BRIDGE_URL")
    registered = False
    try:
        preferences.get_preferences = lambda _context: type(
            "_SmokePreferences",
            (),
            {"checkpoint_dir": checkpoint_root, "checkpoints_enabled": True},
        )()
        claude_blender.register()
        registered = True
        trusted_script_jobs._root = lambda create=False: jobs_root
        script_runner.approve_external_script_trust_window(bpy.context, session=True)
        assert script_runner.external_script_trust_snapshot(bpy.context)["active"]

        os.environ["BLENDER_BRIDGE_TOKEN"] = "must-not-reach-child"
        os.environ["BLENDER_BRIDGE_URL"] = "http://127.0.0.1:9999"
        child_env = trusted_script_jobs._child_env()
        assert "BLENDER_BRIDGE_TOKEN" not in child_env, child_env
        assert "BLENDER_BRIDGE_URL" not in child_env, child_env

        cancel_started = _execute(
            "start_trusted_script_job",
            {
                "intent": "Exercise cancellation",
                "expected_changes": "No live-scene changes",
                "risk_level": "low",
                "code": (
                    "import time\n"
                    "for index in range(60):\n"
                    "    agent_job_report_progress(index / 60.0, 'waiting')\n"
                    "    time.sleep(0.25)\n"
                ),
            },
        )
        assert cancel_started["ok"] is True, cancel_started
        cancel_id = cancel_started["trusted_script_job"]["job_id"]
        tracked_process = trusted_script_jobs._PROCESSES.pop(cancel_id)
        cancelled = _execute("cancel_trusted_script_job", {"job_id": cancel_id})
        assert cancelled["ok"] is True, cancelled
        assert cancelled["trusted_script_job"]["status"] == "cancel_requested", cancelled
        assert cancelled["trusted_script_job"]["poll_after_seconds"] > 0, cancelled
        trusted_script_jobs._PROCESSES[cancel_id] = tracked_process
        cancelled_status = _wait(cancel_id)
        assert cancelled_status["status"] == "cancelled", cancelled_status
        assert bpy.data.objects.get(OBJECT_NAME) is None

        started = _execute(
            "start_trusted_script_job",
            {
                "intent": "Create smoke object in copied blend",
                "expected_changes": f"Create {OBJECT_NAME}",
                "risk_level": "medium",
                "target_objects": [OBJECT_NAME],
                "code": (
                    "import bpy\n"
                    "mesh = bpy.data.meshes.new('Trusted Script Job Smoke Mesh')\n"
                    f"obj = bpy.data.objects.new({OBJECT_NAME!r}, mesh)\n"
                    "bpy.context.scene.collection.objects.link(obj)\n"
                    "agent_job_report_progress(0.8, 'object created')\n"
                ),
            },
        )
        assert started["ok"] is True, started
        job_id = started["trusted_script_job"]["job_id"]
        assert bpy.data.objects.get(OBJECT_NAME) is None
        status = _wait(job_id)
        assert status["status"] == "completed", status
        assert status["result_available"] is True, status
        assert bpy.data.objects.get(OBJECT_NAME) is None

        blocked_apply = _execute(
            "apply_trusted_script_job_result",
            {"job_id": job_id, "confirm_replace_current_scene": False},
        )
        assert blocked_apply["ok"] is False, blocked_apply
        assert blocked_apply["code"] == "trusted_script_job_apply_confirmation_required", blocked_apply

        applied = _execute(
            "apply_trusted_script_job_result",
            {"job_id": job_id, "confirm_replace_current_scene": True},
        )
        assert applied["ok"] is True, applied
        assert applied["trust_preserved"] is True, applied
        assert applied["external_script_trust"]["active"] is True, applied
        assert bpy.data.objects.get(OBJECT_NAME) is not None
        assert os.path.isfile(applied["checkpoint"]["path"]), applied
        assert trusted_script_jobs.parse_job_resource_uri(status["metadata_uri"]) == (job_id, "metadata")
        latest_resource = bridge_server._read_resource(
            trusted_script_jobs.LATEST_JOB_RESOURCE_URI
        )
        assert latest_resource and latest_resource["mimeType"] == "application/json", latest_resource
        print("smoke_trusted_script_jobs: ok")
    finally:
        if registered:
            claude_blender.unregister()
        trusted_script_jobs._root = original_job_root
        preferences.get_preferences = original_get_preferences
        if old_bridge_token is None:
            os.environ.pop("BLENDER_BRIDGE_TOKEN", None)
        else:
            os.environ["BLENDER_BRIDGE_TOKEN"] = old_bridge_token
        if old_bridge_url is None:
            os.environ.pop("BLENDER_BRIDGE_URL", None)
        else:
            os.environ["BLENDER_BRIDGE_URL"] = old_bridge_url
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
