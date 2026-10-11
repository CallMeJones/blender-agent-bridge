"""Shared job persistence and process observation, independent of Blender."""
import json
import os
import uuid
import time
from .operation_queue import current_operation_id

STATUS_REPLACE_ATTEMPTS = 6
STATUS_REPLACE_INITIAL_DELAY_SECONDS = 0.01


def replace_status_file(temp_path, path):
    delay = STATUS_REPLACE_INITIAL_DELAY_SECONDS
    for attempt in range(STATUS_REPLACE_ATTEMPTS):
        try:
            os.replace(temp_path, path)
            return
        except PermissionError:
            if attempt + 1 == STATUS_REPLACE_ATTEMPTS:
                raise
            time.sleep(delay)
            delay *= 2

def child_environment():
    """Environment for background Blender child processes with bridge secrets removed."""
    env = dict(os.environ)
    for key in ("BLENDER_BRIDGE_TOKEN", "BLENDER_BRIDGE_URL"):
        env.pop(key, None)
    return env

def pid_alive(pid):
    """Best-effort cross-platform check that a process id is still running."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not handle:
                return False
            try:
                exit_code = wintypes.DWORD()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return False
                return exit_code.value == STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def write_json(path, payload):
    """Atomically publish a complete status file, including concurrent writers."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    temp_path = f"{path}.{uuid.uuid4().hex}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        replace_status_file(temp_path, path)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass
    return path
