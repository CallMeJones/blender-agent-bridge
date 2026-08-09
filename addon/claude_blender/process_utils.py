"""Cross-platform process-group lifecycle helpers for background jobs."""

from __future__ import annotations

import os
import signal
import subprocess


def process_group_kwargs():
    """Return ``Popen`` options that isolate a job and its descendants."""
    if os.name == "nt":
        return {
            "creationflags": (
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
        }
    return {"start_new_session": True}


def _wait_for_exit(process, timeout):
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return None


def terminate_process_tree(process, timeout=5):
    """Terminate a process and all descendants started in its job group."""
    if process is None:
        return None
    if process.poll() is not None:
        return process.poll()

    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", "")
        taskkill = os.path.join(system_root, "System32", "taskkill.exe") if system_root else "taskkill.exe"
        try:
            subprocess.run(
                [taskkill, "/PID", str(int(process.pid)), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=max(1, timeout),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:  # noqa: BLE001 - direct-process fallback follows
            pass
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass

    result = _wait_for_exit(process, timeout)
    if result is not None:
        return result

    if os.name != "nt":
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    try:
        process.kill()
    except OSError:
        pass
    return _wait_for_exit(process, timeout)
