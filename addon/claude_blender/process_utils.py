"""Cross-platform process-group lifecycle helpers for background jobs."""

from __future__ import annotations

import os
import signal
import subprocess
import time


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


def _windows_descendant_pids(root_pid):
    if os.name != "nt":
        return []
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return []

    th32cs_snapprocess = 0x00000002
    invalid_handle_value = ctypes.c_void_p(-1).value
    kernel32 = ctypes.windll.kernel32

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    snapshot = kernel32.CreateToolhelp32Snapshot(th32cs_snapprocess, 0)
    if snapshot in (0, invalid_handle_value):
        return []
    parent_by_pid = {}
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Process32First(snapshot, ctypes.byref(entry)):
            return []
        while True:
            parent_by_pid[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)

    descendants = []
    frontier = {int(root_pid)}
    seen = set(frontier)
    while frontier:
        next_frontier = {
            pid
            for pid, parent_pid in parent_by_pid.items()
            if parent_pid in frontier and pid not in seen
        }
        descendants.extend(sorted(next_frontier))
        seen.update(next_frontier)
        frontier = next_frontier
    return descendants


def _windows_terminate_pid(pid):
    if os.name != "nt":
        return False
    try:
        import ctypes
    except Exception:
        return False

    process_terminate = 0x0001
    handle = ctypes.windll.kernel32.OpenProcess(process_terminate, False, int(pid))
    if not handle:
        return False
    try:
        return bool(ctypes.windll.kernel32.TerminateProcess(handle, 1))
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _windows_pid_active(pid):
    if os.name != "nt":
        return False
    try:
        import ctypes
    except Exception:
        return False

    process_query_limited_information = 0x1000
    still_active = 259
    handle = ctypes.windll.kernel32.OpenProcess(
        process_query_limited_information,
        False,
        int(pid),
    )
    if not handle:
        return False
    exit_code = ctypes.c_ulong()
    try:
        if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _windows_wait_for_pids(pids, timeout):
    deadline = time.monotonic() + max(0, timeout)
    remaining = {int(pid) for pid in pids}
    while remaining and time.monotonic() < deadline:
        remaining = {pid for pid in remaining if _windows_pid_active(pid)}
        if remaining:
            time.sleep(0.05)
    return not remaining


def terminate_process_tree(process, timeout=5):
    """Terminate a process and all descendants started in its job group."""
    if process is None:
        return None
    if process.poll() is not None:
        return process.poll()

    if os.name == "nt":
        descendant_pids = _windows_descendant_pids(process.pid)
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
        for pid in reversed(descendant_pids):
            _windows_terminate_pid(pid)
        _windows_wait_for_pids(descendant_pids, timeout)
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
