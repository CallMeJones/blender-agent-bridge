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
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DEFAULT_GATEWAY_TOOLS = (
    "blender_bridge_status",
    "blender_tool_catalog",
    "search_blender_tools",
    "get_blender_tool_schema",
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


def _post_tool(base_url: str, name: str, arguments: dict, *, timeout: float) -> dict:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/tool",
        data=json.dumps({"name": name, "arguments": arguments}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = payload.get("result")
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(f"{name} failed: {result or payload}")
    return result


def _scene_object_signature(bridge_url: str, *, timeout: float) -> str:
    result = _post_tool(bridge_url, "list_scene_objects", {}, timeout=timeout)
    return json.dumps(result.get("objects") or [], sort_keys=True, separators=(",", ":"))


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


def _wait_for_interactive_ui_smoke(status_path: Path, process: subprocess.Popen[str], *, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Blender exited before interactive UI smoke completed with code {process.returncode}")
        if status_path.exists():
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
                if not status.get("ok"):
                    raise RuntimeError(
                        "Interactive UI smoke failed: "
                        f"{status.get('error') or status}; traceback={status.get('traceback') or ''}"
                    )
                return status
            except (OSError, json.JSONDecodeError) as exc:
                last_error = str(exc)
        time.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for interactive UI smoke. Last error: {last_error}")


def _start_blender(
    blender: str,
    *,
    env: dict[str, str],
    profile_dir: Path,
    port: int,
    timeout: float,
) -> tuple[subprocess.Popen[str], str, dict, dict]:
    status_path = profile_dir / "installed-bridge-status.json"
    ui_status_path = profile_dir / "installed-interactive-ui-status.json"
    startup_path = SCRIPTS / "installed_extension_startup.py"
    env = dict(env)
    env["INSTALLED_LIVE_SMOKE_STATUS"] = str(status_path)
    env["INSTALLED_LIVE_SMOKE_UI_STATUS"] = str(ui_status_path)
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
        ui_status = _wait_for_interactive_ui_smoke(ui_status_path, process, timeout=timeout)
        print(
            "interactive UI smoke ok:",
            "clipboard config,",
            "session token lifecycle,",
            "script trust lifecycle,",
            "viewport focus,",
            f"Material Preview in {ui_status.get('view_areas')} VIEW_3D area(s)",
            flush=True,
        )
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
    return process, bridge_url, health, ui_status


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


def _mcp_stdio_smoke(
    python_command: str,
    mcp_path: Path,
    *,
    env: dict[str, str],
    bridge_url: str,
    timeout: float,
) -> None:
    _mcp_stdio_smoke_command(
        [python_command, str(mcp_path), "--bridge-url", bridge_url],
        env=env,
        timeout=timeout,
    )


def _mcp_stdio_smoke_command(
    command: list[str],
    *,
    env: dict[str, str],
    timeout: float,
) -> None:
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
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "search_blender_tools",
                "arguments": {
                    "query": "inspect scene list objects blend file diagnostics",
                    "limit": 5,
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "get_blender_tool_schema",
                "arguments": {"name": "list_scene_objects"},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "invoke_blender_tool",
                "arguments": {"name": "list_scene_objects", "arguments": {}},
            },
        },
    ]
    result = _run(
        [*command, "--timeout", str(int(timeout))],
        env=env,
        input_text=json.dumps(request),
        timeout=max(timeout, 60),
        show_output=False,
    )
    responses = json.loads(result.stdout)
    if len(responses) != 6:
        raise RuntimeError(f"Expected 6 MCP responses, got {len(responses)}")
    errors = [response for response in responses if "error" in response]
    if errors:
        raise RuntimeError(f"MCP responses contained errors: {errors}")
    tool_names = [tool["name"] for tool in responses[1]["result"]["tools"]]
    if set(tool_names) != set(DEFAULT_GATEWAY_TOOLS) or len(tool_names) != len(DEFAULT_GATEWAY_TOOLS):
        raise RuntimeError(f"Unexpected default MCP gateway tools: {tool_names}")
    status = responses[2]["result"]["structuredContent"]
    if not status.get("ok"):
        raise RuntimeError("blender_bridge_status did not return ok")
    if status.get("addon_runtime_source_status") != "current":
        raise RuntimeError(f"Unexpected MCP source status: {status.get('addon_runtime_source_status')}")
    if status.get("mcp_tool_surface") != "gateway":
        raise RuntimeError(f"Unexpected installed MCP tool surface: {status.get('mcp_tool_surface')}")
    search = responses[3]["result"]["structuredContent"]
    search_names = [tool["name"] for tool in search.get("tools") or []]
    for required in ("get_blend_file_diagnostics", "list_scene_objects"):
        if required not in search_names:
            raise RuntimeError(f"Installed gateway search could not find {required}: {search_names}")
    schema = responses[4]["result"]["structuredContent"]
    if not schema.get("ok") or (schema.get("tool") or {}).get("name") != "list_scene_objects":
        raise RuntimeError(f"Installed gateway schema lookup failed: {schema}")
    invoked = responses[5]["result"]["structuredContent"]
    if not invoked.get("ok") or invoked.get("invoked_tool") != "list_scene_objects":
        raise RuntimeError(f"Installed gateway invocation failed: {invoked}")
    print(
        "mcp installed smoke ok:",
        f"{len(tool_names)} gateway tools,",
        "search/schema/invoke reachable,",
        f"addon {status.get('addon_version')},",
        f"source {status.get('addon_runtime_source_status')}",
    )


def _doctor_smoke(
    python_executable: str,
    server_path: Path,
    *,
    env: dict[str, str],
    bridge_url: str,
    timeout: float,
    label: str,
) -> None:
    _doctor_smoke_command(
        [
            python_executable,
            str(server_path),
            "doctor",
            "--bridge-url",
            bridge_url,
        ],
        env=env,
        bridge_url=bridge_url,
        timeout=timeout,
        label=label,
    )


def _doctor_smoke_command(
    command: list[str],
    *,
    env: dict[str, str],
    bridge_url: str,
    timeout: float,
    label: str,
) -> None:
    before = _scene_object_signature(bridge_url, timeout=timeout)
    result = _run(
        [
            *command,
            "--timeout",
            str(min(timeout, 10.0)),
        ],
        env=env,
        timeout=max(timeout, 60.0),
    )
    if "Overall: PASS" not in result.stdout:
        raise RuntimeError(f"{label} doctor did not report PASS: {result.stdout}")
    after = _scene_object_signature(bridge_url, timeout=timeout)
    if after != before:
        raise RuntimeError(f"{label} doctor changed the scene object inventory")
    print(f"{label} doctor smoke ok: PASS with unchanged scene inventory")


def _mcpb_smoke(
    *,
    env: dict[str, str],
    profile_dir: Path,
    bridge_url: str,
    timeout: float,
) -> None:
    output_dir = profile_dir / "mcpb-dist"
    stage_dir = profile_dir / "mcpb-stage"
    _run(
        [
            sys.executable,
            str(SCRIPTS / "build_mcpb.py"),
            "--output-dir",
            str(output_dir),
            "--stage-dir",
            str(stage_dir),
        ],
        env=env,
        timeout=max(timeout, 120.0),
    )
    bundles = sorted(output_dir.glob("*.mcpb"))
    if len(bundles) != 1:
        raise RuntimeError(f"Expected one MCPB archive, found: {bundles}")
    extracted = profile_dir / "mcpb-extracted"
    with zipfile.ZipFile(bundles[0]) as archive:
        archive.extractall(extracted)
        manifest = json.loads(archive.read("manifest.json"))
    server_path = extracted / "src" / "main.py"
    package_root = extracted / "src" / "claude_blender"
    project_path = extracted / "pyproject.toml"
    if not server_path.is_file() or not package_root.is_dir() or not project_path.is_file():
        raise RuntimeError("MCPB archive is missing its host-managed uv source layout")

    config = manifest["server"]["mcp_config"]
    replacements = {
        "${__dirname}": str(extracted),
        "${user_config.bridge_url}": bridge_url,
        "${user_config.bridge_token}": env.get("BLENDER_BRIDGE_TOKEN", ""),
    }

    def expand(value: str) -> str:
        for placeholder, replacement in replacements.items():
            value = value.replace(placeholder, replacement)
        return value

    command = shutil.which(config["command"])
    if not command:
        raise RuntimeError(f"MCPB runtime command is unavailable: {config['command']}")
    launch_command = [command, *[expand(value) for value in config.get("args", [])]]
    mcpb_env = env.copy()
    mcpb_env.update({key: expand(value) for key, value in config.get("env", {}).items()})
    mcpb_env["UV_NO_PROGRESS"] = "1"
    mcpb_env["UV_CACHE_DIR"] = str(profile_dir / "uv-cache")
    mcpb_env["UV_PROJECT_ENVIRONMENT"] = str(profile_dir / "uv-environment")
    mcpb_env["UV_PYTHON_INSTALL_DIR"] = str(profile_dir / "uv-python")
    _doctor_smoke_command(
        [*launch_command, "doctor"],
        env=mcpb_env,
        bridge_url=bridge_url,
        timeout=timeout,
        label="MCPB",
    )
    _mcp_stdio_smoke_command(
        launch_command,
        env=mcpb_env,
        timeout=timeout,
    )
    print(f"mcpb installed smoke ok: {bundles[0].name}")


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
        process, bridge_url, health, ui_status = _start_blender(
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
        _mcp_stdio_smoke(
            str(ui_status["bundled_python"]),
            mcp_path,
            env=env,
            bridge_url=bridge_url,
            timeout=args.timeout,
        )
        _doctor_smoke(
            str(ui_status["bundled_python"]),
            mcp_path,
            env=env,
            bridge_url=bridge_url,
            timeout=args.timeout,
            label="Bundled",
        )
        _mcpb_smoke(
            env=env,
            profile_dir=profile_dir,
            bridge_url=bridge_url,
            timeout=args.timeout,
        )
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
