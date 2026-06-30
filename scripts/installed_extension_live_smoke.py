"""Clean installed-extension smoke for the live bridge and MCP stdio path.

The smoke builds a package ZIP, installs it into a throwaway Blender profile,
starts the bridge from the installed extension, runs the live workflow and
visual evidence smokes, verifies the installed MCP server over stdio, and then
stops Blender.

Example:
    python scripts/installed_extension_live_smoke.py --blender "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe"
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DEFAULT_REQUIRED_TOOLS = (
    "blender_bridge_status",
    "plan_director_workflow",
    "plan_asset_import_workflow",
    "plan_advanced_scene_workflow",
    "run_animation_workflow",
    "invoke_blender_tool",
)


def _common_blender_paths() -> list[Path]:
    if os.name != "nt":
        return []
    base = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Blender Foundation"
    if not base.exists():
        return []
    return sorted(base.glob(r"Blender *\blender.exe"), reverse=True)


def _find_blender(explicit: str) -> str:
    if explicit:
        path = shutil.which(explicit) if os.sep not in explicit and "/" not in explicit else explicit
        if path and Path(path).exists():
            return str(Path(path).resolve())
        raise FileNotFoundError(f"Blender executable not found: {explicit}")
    env_path = os.environ.get("BLENDER_PATH", "")
    if env_path:
        return _find_blender(env_path)
    which = shutil.which("blender")
    if which:
        return str(Path(which).resolve())
    for path in _common_blender_paths():
        return str(path.resolve())
    raise FileNotFoundError("Blender executable not found. Pass --blender or set BLENDER_PATH.")


def _tail(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _run(
    command: list[str],
    *,
    env: dict[str, str],
    timeout: float,
    input_text: str | None = None,
    show_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    printable = " ".join(f'"{part}"' if " " in part else part for part in command)
    print(f"$ {printable}", flush=True)
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        if result.stdout:
            print(_tail(result.stdout), file=sys.stderr)
        if result.stderr:
            print(_tail(result.stderr), file=sys.stderr)
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {printable}")
    if show_output and result.stdout.strip():
        print(_tail(result.stdout.strip(), 2000), flush=True)
    if show_output and result.stderr.strip():
        print(_tail(result.stderr.strip(), 2000), file=sys.stderr, flush=True)
    return result


def _prepare_profile(profile_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["BLENDER_USER_CONFIG"] = str(profile_dir / "config")
    env["BLENDER_USER_SCRIPTS"] = str(profile_dir / "scripts")
    env["BLENDER_USER_CACHE"] = str(profile_dir / "cache")
    env["BLENDER_USER_EXTENSIONS"] = str(profile_dir / "extensions")
    for key in ("BLENDER_USER_CONFIG", "BLENDER_USER_SCRIPTS", "BLENDER_USER_CACHE", "BLENDER_USER_EXTENSIONS"):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    return env


def _disable_startup_splash(blender: str, *, env: dict[str, str], timeout: float) -> None:
    expression = "import bpy; bpy.context.preferences.view.show_splash = False; bpy.ops.wm.save_userpref()"
    _run(
        [blender, "--background", "--factory-startup", "--python-expr", expression],
        env=env,
        timeout=timeout,
        show_output=False,
    )


def _read_json(url: str, *, timeout: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _wait_for_bridge(status_path: Path, process: subprocess.Popen[str], *, timeout: float) -> tuple[str, dict]:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Blender exited before bridge startup completed with code {process.returncode}")
        if status_path.exists():
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
                result = status.get("result") or {}
                if not result.get("ok"):
                    raise RuntimeError(f"Bridge startup failed: {result}")
                bridge_url = str(result.get("url") or "").rstrip("/")
                if not bridge_url:
                    raise RuntimeError(f"Bridge startup did not report a URL: {status}")
                health = _read_json(f"{bridge_url}/health", timeout=5)
                if not health.get("ok"):
                    raise RuntimeError(f"Bridge health failed: {health}")
                return bridge_url, health
            except (OSError, json.JSONDecodeError, urllib.error.URLError, TimeoutError) as exc:
                last_error = str(exc)
        time.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for installed bridge startup. Last error: {last_error}")


def _start_blender(
    blender: str,
    *,
    env: dict[str, str],
    profile_dir: Path,
    port: int,
    timeout: float,
) -> tuple[subprocess.Popen[str], str, dict]:
    status_path = profile_dir / "installed-bridge-status.json"
    startup_path = profile_dir / "start_installed_bridge.py"
    startup_path.write_text(
        """
import importlib
import json
import os
from pathlib import Path

import bpy

module_name = "bl_ext.user_default.claude_blender"
status_path = Path(os.environ["INSTALLED_LIVE_SMOKE_STATUS"])
port = int(os.environ.get("INSTALLED_LIVE_SMOKE_PORT", "0"))

def dismiss_startup_popups():
    try:
        for window in bpy.context.window_manager.windows:
            window.event_simulate(type="ESC", value="PRESS")
            window.event_simulate(type="ESC", value="RELEASE")
    except Exception:
        pass
    return None

bpy.ops.preferences.addon_enable(module=module_name)
addon_module = importlib.import_module(module_name)
bridge_server = importlib.import_module(module_name + ".bridge_server")
result = bridge_server.start_bridge(port=port, auth_token="")
bpy.app.timers.register(dismiss_startup_popups, first_interval=0.5)
status_path.write_text(
    json.dumps({"module_file": getattr(addon_module, "__file__", ""), "result": result}, indent=2),
    encoding="utf-8",
)
print("INSTALLED_BRIDGE_START", result, flush=True)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    env = dict(env)
    env["INSTALLED_LIVE_SMOKE_STATUS"] = str(status_path)
    env["INSTALLED_LIVE_SMOKE_PORT"] = str(port)
    stdout_path = profile_dir / "blender-live-smoke.stdout.log"
    stderr_path = profile_dir / "blender-live-smoke.stderr.log"
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [blender, "--factory-startup", "--enable-event-simulate", "--python", str(startup_path)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=stdout_handle,
        stderr=stderr_handle,
        creationflags=creationflags,
    )
    process._bab_log_handles = (stdout_handle, stderr_handle)  # type: ignore[attr-defined]
    try:
        bridge_url, health = _wait_for_bridge(status_path, process, timeout=timeout)
    except Exception:
        try:
            for handle in (stdout_handle, stderr_handle):
                handle.flush()
            for log_path in (stdout_path, stderr_path):
                if log_path.exists():
                    print(f"{log_path}:\n{_tail(log_path.read_text(encoding='utf-8', errors='replace'))}", file=sys.stderr)
        finally:
            _stop_blender(process)
        raise
    return process, bridge_url, health


def _stop_blender(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    for handle in getattr(process, "_bab_log_handles", ()):
        try:
            handle.close()
        except Exception:
            pass


def _verify_installed_health(health: dict, profile_dir: Path) -> None:
    addon_path = str(health.get("addon_path") or "")
    expected = str(profile_dir / "extensions" / "user_default" / "claude_blender")
    if not addon_path.startswith(expected):
        raise RuntimeError(f"Bridge is not using the temp installed extension: {addon_path}")
    if health.get("addon_runtime_source_status") != "current":
        raise RuntimeError(f"Installed source is not current: {health.get('addon_runtime_source_status')}")
    if health.get("addon_loaded_source_hash") != health.get("addon_source_hash"):
        raise RuntimeError("Installed source hash and loaded source hash do not match")


def _mcp_stdio_smoke(mcp_path: Path, *, env: dict[str, str], bridge_url: str, timeout: float) -> None:
    request = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "installed-live-smoke", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "blender_bridge_status", "arguments": {}},
        },
    ]
    result = _run(
        [sys.executable, str(mcp_path), "--bridge-url", bridge_url, "--timeout", str(int(timeout))],
        env=env,
        input_text=json.dumps(request),
        timeout=max(timeout, 60),
        show_output=False,
    )
    responses = json.loads(result.stdout)
    if len(responses) != 3:
        raise RuntimeError(f"Expected 3 MCP responses, got {len(responses)}")
    errors = [response for response in responses if "error" in response]
    if errors:
        raise RuntimeError(f"MCP responses contained errors: {errors}")
    tool_names = [tool["name"] for tool in responses[1]["result"]["tools"]]
    missing = [name for name in DEFAULT_REQUIRED_TOOLS if name not in tool_names]
    if missing:
        raise RuntimeError(f"Missing compact MCP tools: {', '.join(missing)}")
    status_text = "\n".join(part.get("text", "") for part in responses[2]["result"]["content"])
    status = json.loads(status_text)
    if not status.get("ok"):
        raise RuntimeError("blender_bridge_status did not return ok")
    if status.get("addon_runtime_source_status") != "current":
        raise RuntimeError(f"Unexpected MCP source status: {status.get('addon_runtime_source_status')}")
    print(
        "mcp installed smoke ok:",
        f"{len(tool_names)} compact tools,",
        f"addon {status.get('addon_version')},",
        f"source {status.get('addon_runtime_source_status')}",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test an installed Blender Agent Bridge extension.")
    parser.add_argument("--blender", default="", help="Path to blender executable. Defaults to BLENDER_PATH, PATH, or common Windows installs.")
    parser.add_argument("--profile-dir", default="", help="Optional temp Blender profile directory to reuse/create.")
    parser.add_argument("--keep-profile", action="store_true", help="Keep the temporary profile and captured artifacts.")
    parser.add_argument("--port", type=int, default=0, help="Bridge port. Defaults to 0 for an unused local port.")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--skip-playblast", action="store_true")
    args = parser.parse_args(argv)

    blender = _find_blender(args.blender)
    profile_dir = Path(args.profile_dir).resolve() if args.profile_dir else Path(tempfile.mkdtemp(prefix="bab-installed-live-profile-"))
    zip_path = profile_dir / "claude_blender-installed-live-smoke.zip"
    process: subprocess.Popen[str] | None = None

    try:
        if profile_dir.exists() and not args.profile_dir:
            shutil.rmtree(profile_dir, ignore_errors=True)
        profile_dir.mkdir(parents=True, exist_ok=True)
        env = _prepare_profile(profile_dir)

        print(f"blender: {blender}")
        print(f"profile: {profile_dir}")

        _run(
            [sys.executable, str(SCRIPTS / "build_extension_zip.py"), "--output", str(zip_path), "--blender", blender],
            env=env,
            timeout=max(args.timeout, 120),
        )
        _run(
            [blender, "--command", "extension", "install-file", "-r", "user_default", "-e", str(zip_path)],
            env=env,
            timeout=max(args.timeout, 120),
        )
        extension_list = _run(
            [blender, "--command", "extension", "list"],
            env=env,
            timeout=args.timeout,
        )
        if "claude_blender [installed]" not in extension_list.stdout:
            raise RuntimeError("Installed extension was not listed by Blender")

        _disable_startup_splash(blender, env=env, timeout=args.timeout)
        process, bridge_url, health = _start_blender(
            blender,
            env=env,
            profile_dir=profile_dir,
            port=args.port,
            timeout=args.timeout,
        )
        _verify_installed_health(health, profile_dir)
        print(
            "installed bridge ok:",
            f"Blender {health.get('blender_version')}",
            f"addon {health.get('addon_version')}",
            f"source {health.get('addon_runtime_source_status')}",
            bridge_url,
        )

        _run(
            [sys.executable, str(SCRIPTS / "live_workflow_sweep.py"), "--bridge-url", bridge_url, "--skip-viewport", "--timeout", str(int(args.timeout))],
            env=env,
            timeout=max(args.timeout, 120),
        )
        bridge_smoke = [sys.executable, str(SCRIPTS / "live_bridge_smoke.py"), "--bridge-url", bridge_url, "--timeout", str(int(args.timeout))]
        if args.skip_playblast:
            bridge_smoke.append("--skip-playblast")
        _run(bridge_smoke, env=env, timeout=max(args.timeout, 120))

        mcp_path = profile_dir / "extensions" / "user_default" / "claude_blender" / "mcp_server.py"
        _mcp_stdio_smoke(mcp_path, env=env, bridge_url=bridge_url, timeout=args.timeout)
        print("installed extension live smoke passed")
        if args.keep_profile:
            print(f"kept profile: {profile_dir}")
        return 0
    finally:
        if process is not None:
            _stop_blender(process)
        if not args.keep_profile and not args.profile_dir:
            shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
