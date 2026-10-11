"""Real descendants stop through render/trusted cancellation and unregister APIs."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))
import claude_blender
from claude_blender import job_runtime, process_utils, render_jobs, trusted_script_jobs


def active(pid):
    status = Path(f"/proc/{pid}/stat")
    if status.exists() and status.read_text().split()[2] == "Z":
        return False
    return job_runtime.pid_alive(pid)


claude_blender.register()
try:
    python = shutil.which("python") or shutil.which("python3")
    assert python, "Python fixture executable is required"
    for module in (render_jobs, trusted_script_jobs):
        for action in ("cancel", "unregister"):
            with tempfile.TemporaryDirectory(prefix="bridge-process-regression-") as root:
                pid_path = Path(root) / "child.pid"
                child = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"
                parent = "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c',sys.argv[2]]); open(sys.argv[1],'w').write(str(p.pid)); time.sleep(60)"
                process = subprocess.Popen([python, "-c", parent, str(pid_path), child],
                                           **process_utils.process_group_kwargs())
                module._PROCESSES["fixture"] = process
                try:
                    deadline = time.monotonic() + 5
                    while (not pid_path.exists() or not pid_path.read_text()) and time.monotonic() < deadline:
                        time.sleep(0.02)
                    child_pid = int(pid_path.read_text())
                    metadata = {"ok": True, "available": True, "job_id": "fixture", "pid": process.pid,
                                "status": "running", "cancel_path": str(Path(root) / "cancel"),
                                "metadata_path": str(Path(root) / "metadata.json")}
                    job_runtime.write_json(metadata["metadata_path"], metadata)
                    if action == "unregister":
                        module.unregister()
                    elif module is render_jobs:
                        with mock.patch.object(module, "render_job_status", return_value=metadata):
                            result = module.cancel_render_job("fixture")
                            assert result["ok"], result
                    else:
                        with mock.patch.object(module, "_metadata_path", return_value=metadata["metadata_path"]), mock.patch.object(module, "job_status", return_value=metadata):
                            result = module.cancel_job("fixture")
                            assert result["ok"], result
                    assert process.poll() is not None
                    deadline = time.monotonic() + 5
                    while active(child_pid) and time.monotonic() < deadline:
                        time.sleep(0.02)
                    assert not active(child_pid), (module.__name__, action, child_pid)
                    saved = json.loads(Path(metadata["metadata_path"]).read_text())
                    if action == "cancel":
                        assert saved["status"] == "cancelled", saved
                        if module is render_jobs:
                            stale_path = str(Path(root) / "child-status.json")
                            job_runtime.write_json(stale_path, {"status": "running"})
                            saved["child_status_path"] = stale_path
                            with mock.patch.object(module, "_metadata_for_id", return_value=saved), mock.patch.object(module, "_frame_files", return_value=[]):
                                assert module.render_job_status("fixture")["status"] == "cancelled"
                finally:
                    process_utils.terminate_process_tree(process)
                    module._PROCESSES.pop("fixture", None)
    # A recovered PID alone does not authorize killing a process.
    unrelated = {"ok": True, "available": True, "job_id": "untracked", "pid": os.getpid(), "status": "running"}
    with mock.patch.object(render_jobs, "render_job_status", return_value=unrelated):
        assert not render_jobs.cancel_render_job("untracked")["ok"]
    print("smoke_job_supervision: ok")
finally:
    claude_blender.unregister()
