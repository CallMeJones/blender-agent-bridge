from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ADDON_ROOT = ROOT / "addon"
if str(ADDON_ROOT) not in sys.path:
    sys.path.insert(0, str(ADDON_ROOT))

from claude_blender import process_utils  # noqa: E402


def _pid_exists(pid):
    if os.name == "nt":
        import ctypes

        process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not process:
            return False
        exit_code = ctypes.c_ulong()
        try:
            if not ctypes.windll.kernel32.GetExitCodeProcess(process, ctypes.byref(exit_code)):
                return False
            return exit_code.value == 259  # STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(process)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class ProcessUtilsTests(unittest.TestCase):
    def test_terminate_process_tree_stops_descendant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            child_pid_path = os.path.join(temp_dir, "child.pid")
            child_code = "import time; time.sleep(60)"
            parent_code = (
                "import subprocess, sys, time\n"
                "child = subprocess.Popen([sys.executable, '-c', %r])\n"
                "open(sys.argv[1], 'w').write(str(child.pid))\n"
                "time.sleep(60)\n"
            ) % child_code
            process = subprocess.Popen(
                [sys.executable, "-c", parent_code, child_pid_path],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **process_utils.process_group_kwargs(),
            )
            deadline = time.monotonic() + 5
            while not os.path.isfile(child_pid_path) and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(os.path.isfile(child_pid_path), "parent did not report its child PID")
            with open(child_pid_path, "r", encoding="utf-8") as handle:
                child_pid = int(handle.read())

            result = process_utils.terminate_process_tree(process)

            self.assertIsNotNone(result)
            self.assertFalse(_pid_exists(process.pid))
            deadline = time.monotonic() + 5
            while _pid_exists(child_pid) and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertFalse(_pid_exists(child_pid))


if __name__ == "__main__":
    unittest.main()
