"""Deterministic, read-only connection diagnostics for the external MCP runtime."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
import urllib.parse

try:
    import tomllib
except ImportError:  # pragma: no cover - Python 3.10 fallback
    tomllib = None

from . import bridge_protocol, build_info


PASS = "pass"
WARN = "warn"
FAIL = "fail"
SKIP = "skip"
DEFAULT_PROBE_TOOL = "list_scene_objects"
DEFAULT_BRIDGE_URL = "http://127.0.0.1:8765"
CLIENT_CONFIG_CONTAINERS = (
    "mcpServers",
    "mcp_servers",
    "servers",
    "mcp",
)
BLENDER_SERVER_IDS = {
    "blender",
    "blender-agent-bridge",
    "blender_agent_bridge",
}


def _check(check_id, title, status, summary, *, recovery="", details=None):
    item = {
        "id": str(check_id),
        "title": str(title),
        "status": str(status),
        "summary": str(summary),
    }
    if recovery:
        item["recovery"] = str(recovery)
    if details:
        item["details"] = dict(details)
    return item


def _structured_content(result):
    if not isinstance(result, dict):
        return {}
    content = result.get("structuredContent")
    return content if isinstance(content, dict) else {}


def _parse_bridge_url(bridge_url):
    parsed = urllib.parse.urlparse(str(bridge_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Bridge URL must be an absolute http:// or https:// URL")
    if parsed.username or parsed.password:
        raise ValueError("Bridge URL must not contain credentials; use BLENDER_BRIDGE_TOKEN")
    if parsed.query or parsed.fragment:
        raise ValueError("Bridge URL must not contain a query string or fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("Bridge URL must not contain a path")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("Bridge URL contains an invalid port") from exc
    return parsed, port


def _loopback_host(hostname):
    return str(hostname or "").strip().lower() in {"127.0.0.1", "::1", "localhost"}


def _safe_bridge_url(bridge_url):
    try:
        parsed = urllib.parse.urlparse(str(bridge_url or "").strip())
        if not parsed.hostname:
            return "<invalid>"
        port = f":{parsed.port}" if parsed.port else ""
        hostname = (
            f"[{parsed.hostname}]"
            if ":" in parsed.hostname
            else parsed.hostname
        )
        return urllib.parse.urlunparse(
            (parsed.scheme, f"{hostname}{port}", parsed.path, "", "", "")
        )
    except (TypeError, ValueError):
        return "<invalid>"


def _check_runtime():
    executable = os.path.abspath(sys.executable) if sys.executable else ""
    if executable and os.path.isfile(executable):
        return _check(
            "mcp_process",
            "MCP process",
            PASS,
            f"Running Blender Agent Bridge MCP {build_info.MCP_SERVER_VERSION} with Python "
            f"{sys.version_info.major}.{sys.version_info.minor}.",
            details={
                "executable": executable,
                "runtime_mode": build_info.mcp_runtime_mode_from_env(),
                "server_version": build_info.MCP_SERVER_VERSION,
            },
        )
    return _check(
        "mcp_process",
        "MCP process",
        FAIL,
        "The current Python executable cannot be resolved on disk.",
        recovery="Replace the client MCP entry with a freshly copied Blender config or reinstall the connector.",
    )


def _normalize_client_entry(entry):
    if not isinstance(entry, dict):
        raise ValueError("The Blender MCP server entry must be an object")
    normalized = dict(entry)
    command = entry.get("command")
    explicit_args = entry.get("args")
    args = (
        [str(value) for value in explicit_args]
        if isinstance(explicit_args, (list, tuple))
        else []
    )
    if isinstance(command, (list, tuple)):
        command_parts = [str(value) for value in command]
        normalized["command"] = command_parts[0] if command_parts else ""
        normalized["args"] = command_parts[1:] + args
    elif command is None or isinstance(command, str):
        normalized["command"] = str(command or "")
        normalized["args"] = args
    else:
        raise ValueError(
            "The Blender MCP command must be a string or command array"
        )

    env = entry.get("env")
    environment = entry.get("environment")
    if (
        isinstance(env, dict)
        and isinstance(environment, dict)
        and env != environment
    ):
        raise ValueError(
            "The Blender MCP entry defines conflicting env and environment values"
        )
    normalized["env"] = dict(
        env
        if isinstance(env, dict)
        else environment
        if isinstance(environment, dict)
        else {}
    )
    return normalized


def _client_entry_score(server_id, entry):
    try:
        normalized = _normalize_client_entry(entry)
    except ValueError:
        return -1
    score = (
        1000
        if str(server_id or "").strip().lower() in BLENDER_SERVER_IDS
        else 0
    )
    env = normalized["env"]
    if any(
        key in env
        for key in (
            "BLENDER_BRIDGE_URL",
            "BLENDER_BRIDGE_TOKEN",
            "CLAUDE_BLENDER_ADDON_ID",
            "CLAUDE_BLENDER_MCP_SERVER_VERSION",
            "CLAUDE_BLENDER_TOOL_REGISTRY_DIGEST",
        )
    ):
        score += 500
    launch_text = " ".join(
        [normalized["command"], *normalized["args"]]
    ).lower()
    if any(
        marker in launch_text
        for marker in (
            "blender-bridge",
            "blender_agent_bridge",
            "claude_blender",
            "mcp_server.py",
        )
    ):
        score += 250
    return score


def _load_client_entry(path):
    with open(path, "rb") as handle:
        raw = handle.read()
    suffix = os.path.splitext(path)[1].lower()
    if suffix == ".toml":
        if tomllib is None:
            raise ValueError(
                "TOML client config inspection requires Python 3.11 or newer"
            )
        payload = tomllib.loads(raw.decode("utf-8"))
    else:
        payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("The MCP client config must decode to an object")
    if "command" in payload:
        return _normalize_client_entry(payload)

    candidates = []
    for container_name in CLIENT_CONFIG_CONTAINERS:
        container = payload.get(container_name)
        if not isinstance(container, dict):
            continue
        for server_id, entry in container.items():
            if not isinstance(entry, dict):
                continue
            score = _client_entry_score(server_id, entry)
            if score > 0:
                candidates.append(
                    (score, str(server_id), entry)
                )
    if not candidates:
        raise ValueError("No Blender MCP server entry was found")
    candidates.sort(key=lambda item: (-item[0], item[1]))
    best_score = candidates[0][0]
    best = [item for item in candidates if item[0] == best_score]
    if len(best) > 1:
        raise ValueError(
            "Multiple Blender MCP server entries were found; keep one active entry"
        )
    return _normalize_client_entry(best[0][2])


def _resolved_command(entry):
    command = str(entry.get("command") or "").strip()
    if not command:
        return "", ""
    if os.path.isabs(command):
        return command, command if os.path.isfile(command) else ""
    return command, str(shutil.which(command) or "")


def _client_connection_settings(entry):
    args = [str(value) for value in (entry.get("args") or [])]
    env = entry.get("env") if isinstance(entry.get("env"), dict) else {}
    argument_urls = []
    for index, value in enumerate(args):
        if value == "--bridge-url":
            if index + 1 >= len(args):
                raise ValueError(
                    "The client entry has --bridge-url without a value"
                )
            argument_urls.append(args[index + 1])
        elif value.startswith("--bridge-url="):
            argument_urls.append(value.partition("=")[2])
    argument_urls = [str(value).strip() for value in argument_urls]
    if any(not value for value in argument_urls):
        raise ValueError("The client entry has an empty bridge URL")
    if len(set(argument_urls)) > 1:
        raise ValueError(
            "The client entry defines multiple conflicting bridge URLs"
        )
    argument_url = str(argument_urls[-1] if argument_urls else "").strip()
    environment_url = str(env.get("BLENDER_BRIDGE_URL") or "").strip()
    if (
        argument_url
        and environment_url
        and argument_url != environment_url
    ):
        raise ValueError(
            "The client entry defines conflicting bridge URLs in args and env"
        )
    return {
        "bridge_url": argument_url or environment_url,
        "token": str(env.get("BLENDER_BRIDGE_TOKEN") or ""),
    }


def _client_entry_check(absolute_path, entry):
    if entry.get("enabled") is False or entry.get("disabled") is True:
        return _check(
            "client_configuration",
            "Client configuration",
            FAIL,
            "The configured Blender MCP server entry is disabled.",
            recovery="Enable the Blender MCP server entry and restart or refresh the client.",
        )
    command, resolved = _resolved_command(entry)
    if not resolved:
        return _check(
            "client_configuration",
            "Client configuration",
            FAIL,
            f"The configured MCP command cannot be found: {command or '<empty>'}",
            recovery="Copy a fresh MCP config from Blender or reinstall the MCPB connector.",
        )

    args = [str(value) for value in (entry.get("args") or [])]
    if os.path.basename(command).lower() in {"cmd", "cmd.exe"} and any(
        value.lower() == "uvx" for value in args
    ):
        if not shutil.which("uvx"):
            return _check(
                "client_configuration",
                "Client configuration",
                FAIL,
                "The Windows wrapper resolves, but its nested uvx command is unavailable.",
                recovery="Install uv, switch Blender to Bundled mode, or install the MCPB connector.",
            )
    missing_paths = [
        value
        for value in args
        if os.path.isabs(value) and value.lower().endswith(".py") and not os.path.isfile(value)
    ]
    if missing_paths:
        return _check(
            "client_configuration",
            "Client configuration",
            FAIL,
            "The configured bundled MCP server path no longer exists.",
            recovery="The add-on location changed. Copy a fresh MCP config from Blender and restart the client.",
            details={"missing_server_path": missing_paths[0]},
        )

    expected_pin = f"{build_info.MCP_DISTRIBUTION_NAME}=={build_info.MCP_SERVER_VERSION}"
    configured_pins = [value for value in args if value.startswith(f"{build_info.MCP_DISTRIBUTION_NAME}==")]
    if configured_pins and expected_pin not in configured_pins:
        return _check(
            "client_configuration",
            "Client configuration",
            FAIL,
            f"The client pins {configured_pins[0]}, but this source expects {expected_pin}.",
            recovery="Copy a fresh MCP config from the matching Blender add-on and restart the client.",
        )

    env = entry.get("env") if isinstance(entry.get("env"), dict) else {}
    configured_surface = str(env.get("BLENDER_MCP_TOOL_SURFACE") or "").strip().lower()
    if configured_surface and configured_surface != "gateway":
        return _check(
            "client_configuration",
            "Client configuration",
            FAIL,
            f"The client forces the non-default '{configured_surface}' tool surface.",
            recovery=(
                "Remove BLENDER_MCP_TOOL_SURFACE, replace the complete Blender entry, "
                "and restart the client to clear its manifest."
            ),
        )
    configured_version = str(env.get("CLAUDE_BLENDER_MCP_SERVER_VERSION") or "").strip()
    configured_digest = str(env.get("CLAUDE_BLENDER_TOOL_REGISTRY_DIGEST") or "").strip()
    if configured_version and configured_version != build_info.MCP_SERVER_VERSION:
        return _check(
            "client_configuration",
            "Client configuration",
            FAIL,
            f"The client config expects MCP {configured_version}, not {build_info.MCP_SERVER_VERSION}.",
            recovery="Replace the complete Blender MCP entry and fully restart or refresh the client.",
        )
    if configured_digest and configured_digest != build_info.TOOL_REGISTRY_DIGEST:
        return _check(
            "client_configuration",
            "Client configuration",
            FAIL,
            "The client config contains a stale tool-registry digest.",
            recovery="Replace the complete Blender MCP entry and fully restart or refresh the client.",
        )
    try:
        settings = _client_connection_settings(entry)
    except ValueError as exc:
        return _check(
            "client_configuration",
            "Client configuration",
            FAIL,
            str(exc),
            recovery="Replace the complete Blender MCP entry with one copied from Blender.",
        )
    details = {
        "config_path": absolute_path,
        "command": command,
        "resolved_command": resolved,
    }
    if settings["bridge_url"]:
        details["bridge_url"] = _safe_bridge_url(settings["bridge_url"])
    return _check(
        "client_configuration",
        "Client configuration",
        PASS,
        "The Blender client entry resolves to an available MCP command with current version metadata.",
        details=details,
    )


def _inspect_client_config(path):
    if not path:
        return (
            _check(
                "client_configuration",
                "Client configuration",
                SKIP,
                "No client config path was supplied; runtime and bridge checks will still run.",
                recovery="Pass --client-config with the active JSON or TOML MCP config to inspect its Blender entry.",
            ),
            {},
        )
    absolute_path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(absolute_path):
        return (
            _check(
                "client_configuration",
                "Client configuration",
                FAIL,
                f"Client config does not exist: {absolute_path}",
                recovery="Select the active client config or install the MCPB connector, then rerun doctor.",
            ),
            {},
        )
    try:
        entry = _load_client_entry(absolute_path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        return (
            _check(
                "client_configuration",
                "Client configuration",
                FAIL,
                f"Client config could not be inspected: {exc}",
                recovery="Repair the config syntax or copy a fresh complete Blender MCP entry.",
            ),
            {},
        )
    check = _client_entry_check(absolute_path, entry)
    settings = (
        _client_connection_settings(entry)
        if check["status"] == PASS
        else {}
    )
    return check, settings


def _client_config_check(path):
    return _inspect_client_config(path)[0]


def _socket_check(parsed, port, timeout, connector):
    try:
        connection = connector((parsed.hostname, port), timeout=min(max(float(timeout), 0.1), 3.0))
        close = getattr(connection, "close", None)
        if callable(close):
            close()
    except OSError as exc:
        return _check(
            "tcp_bridge",
            "TCP bridge",
            FAIL,
            f"Nothing accepted a TCP connection at {parsed.hostname}:{port}: {exc}",
            recovery="Open Blender, enable the extension, press Start, and verify the configured bridge port.",
        )
    return _check(
        "tcp_bridge",
        "TCP bridge",
        PASS,
        f"A process accepted a TCP connection at {parsed.hostname}:{port}.",
    )


def _gateway_manifest_check(server):
    from .mcp_server import GATEWAY_TOOL_NAMES

    listed = server.tools_list()
    names = tuple(tool.get("name") for tool in listed.get("tools") or [])
    if names != tuple(GATEWAY_TOOL_NAMES):
        return _check(
            "gateway_manifest",
            "Five-tool manifest",
            FAIL,
            f"The runtime advertised {len(names)} tools instead of the canonical five-tool gateway.",
            recovery=(
                "Unset BLENDER_MCP_TOOL_SURFACE, replace the client config, and restart the MCP client "
                "to clear its cached manifest."
            ),
            details={"advertised_tools": list(names), "expected_tools": list(GATEWAY_TOOL_NAMES)},
        )
    return _check(
        "gateway_manifest",
        "Five-tool manifest",
        PASS,
        "The MCP runtime advertises exactly the five canonical gateway tools.",
        details={"advertised_tools": list(names)},
    )


def _bridge_status_check(server):
    result = server.tools_call({"name": "blender_bridge_status", "arguments": {}})
    status = _structured_content(result)
    if not status.get("ok"):
        message = str(status.get("message") or "Bridge health request failed")
        lowered = message.lower()
        if "401" in lowered or "unauthorized" in lowered:
            recovery = "The bridge token is wrong or missing. Replace the complete client entry from Blender."
        elif any(marker in lowered for marker in ("404", "json", "decode", "expecting value")):
            recovery = (
                "Another process may occupy this port. Stop it or change Blender's bridge port, "
                "then copy a fresh client config."
            )
        else:
            recovery = "Start the bridge in Blender and confirm the URL, port, and local firewall settings."
        return (
            _check("blender_health", "Blender health", FAIL, message, recovery=recovery),
            status,
        )
    blender_version = str(status.get("blender_version") or "unknown")
    addon_version = str(status.get("addon_version") or "unknown")
    return (
        _check(
            "blender_health",
            "Blender health",
            PASS,
            f"Blender {blender_version} answered through add-on {addon_version}.",
            details={
                "blender_version": blender_version,
                "addon_version": addon_version,
                "bridge_busy": bool(status.get("bridge_busy")),
            },
        ),
        status,
    )


def _compatibility_check(status):
    if not status or not status.get("ok"):
        return _check(
            "runtime_compatibility",
            "Runtime compatibility",
            SKIP,
            "Compatibility could not be checked until Blender health succeeds.",
        )
    if status.get("addon_runtime_source_stale"):
        return _check(
            "runtime_compatibility",
            "Runtime compatibility",
            FAIL,
            "The add-on files changed after Blender loaded them.",
            recovery=str(status.get("addon_reload_guidance") or "Reload scripts or restart Blender."),
        )
    if status.get("addon_mcp_version_match") is False:
        return _check(
            "runtime_compatibility",
            "Runtime compatibility",
            FAIL,
            (
                f"Blender add-on {status.get('addon_version') or 'unknown'} and MCP runtime "
                f"{build_info.MCP_SERVER_VERSION} differ."
            ),
            recovery="Install matching add-on and connector versions, copy fresh config, and restart the client.",
        )
    source_status = str(status.get("source_hash_status") or "").strip()
    if source_status in {"mismatch", "mcp_config_mismatch"}:
        return _check(
            "runtime_compatibility",
            "Runtime compatibility",
            FAIL,
            str(status.get("source_hash_message") or "Bundled MCP source identity differs."),
            recovery="Copy a fresh bundled config from Blender and fully restart the MCP client.",
        )
    if status.get("compatible") is False:
        return _check(
            "runtime_compatibility",
            "Runtime compatibility",
            FAIL,
            str(status.get("compatibility_message") or "Add-on and MCP runtime are incompatible."),
            recovery="Install matching add-on and connector versions, copy fresh config, and restart the client.",
        )
    if status.get("compatible") is not True:
        return _check(
            "runtime_compatibility",
            "Runtime compatibility",
            WARN,
            str(status.get("compatibility_message") or "Compatibility metadata is incomplete."),
            recovery="Update the Blender extension and connector together.",
        )
    return _check(
        "runtime_compatibility",
        "Runtime compatibility",
        PASS,
        str(status.get("compatibility_message") or "Bridge protocol and tool registry match."),
        details={
            "bridge_protocol": str(status.get("bridge_version") or bridge_protocol.BRIDGE_VERSION),
            "tool_registry_digest": str(status.get("tool_registry_digest") or ""),
        },
    )


def _schema_lookup_check(server):
    result = server.tools_call(
        {
            "name": "get_blender_tool_schema",
            "arguments": {"name": DEFAULT_PROBE_TOOL},
        }
    )
    content = _structured_content(result)
    tool = content.get("tool") if isinstance(content.get("tool"), dict) else {}
    if not content.get("ok") or tool.get("name") != DEFAULT_PROBE_TOOL:
        return _check(
            "schema_lookup",
            "Gateway schema lookup",
            FAIL,
            str(content.get("message") or f"Could not resolve {DEFAULT_PROBE_TOOL}."),
            recovery="Update the extension and MCP connector together, then rerun doctor.",
        )
    return _check(
        "schema_lookup",
        "Gateway schema lookup",
        PASS,
        f"The canonical schema for {DEFAULT_PROBE_TOOL} is reachable through the gateway.",
        details={"schema_digest": str(content.get("schema_digest") or "")},
    )


def _read_only_gateway_check(server, bridge_ready):
    if not bridge_ready:
        return _check(
            "read_only_gateway",
            "Read-only gateway invocation",
            SKIP,
            "The scene probe was skipped because Blender health failed.",
        )
    result = server.tools_call(
        {
            "name": "blender_tool_catalog",
            "arguments": {
                "action": "invoke",
                "name": DEFAULT_PROBE_TOOL,
                "arguments": {},
            },
        }
    )
    content = _structured_content(result)
    if not content.get("ok", not result.get("isError")) or content.get("invoked_tool") != DEFAULT_PROBE_TOOL:
        return _check(
            "read_only_gateway",
            "Read-only gateway invocation",
            FAIL,
            str(content.get("message") or f"The {DEFAULT_PROBE_TOOL} probe failed."),
            recovery="Resolve the reported compatibility or bridge error, then rerun doctor.",
        )
    objects = content.get("objects")
    object_count = len(objects) if isinstance(objects, list) else content.get("object_count")
    return _check(
        "read_only_gateway",
        "Read-only gateway invocation",
        PASS,
        f"The gateway invoked {DEFAULT_PROBE_TOOL} without mutating the scene.",
        details={"object_count": object_count},
    )


def run_connection_diagnostics(
    *,
    bridge_url=None,
    token=None,
    timeout=5.0,
    client_config="",
    bridge_client=None,
    bridge_client_factory=None,
    server=None,
    socket_connector=socket.create_connection,
):
    """Run the complete non-mutating connection probe and return a safe report."""

    config_check, configured = _inspect_client_config(client_config)
    checks = [_check_runtime(), config_check]
    fallback_url = (
        str(bridge_url or "").strip()
        or str(os.environ.get("BLENDER_BRIDGE_URL") or "").strip()
        or DEFAULT_BRIDGE_URL
    )
    if config_check["status"] == FAIL:
        return _report(fallback_url, checks)
    configured_url = str(configured.get("bridge_url") or "").strip()
    explicit_url = str(bridge_url or "").strip()
    if explicit_url and configured_url and explicit_url != configured_url:
        checks.append(
            _check(
                "connection_target",
                "Connection target",
                FAIL,
                "The explicit bridge URL does not match the selected client config.",
                recovery="Remove the override or update the selected client config, then rerun doctor.",
            )
        )
        return _report(explicit_url, checks)
    configured_token = str(configured.get("token") or "")
    if token is not None and configured_token and str(token) != configured_token:
        checks.append(
            _check(
                "connection_target",
                "Connection target",
                FAIL,
                "The explicit bridge token does not match the selected client config.",
                recovery="Remove the override or copy a fresh complete client config from Blender.",
            )
        )
        return _report(explicit_url or configured_url or fallback_url, checks)
    resolved_url = explicit_url or configured_url or fallback_url
    resolved_token = (
        str(token)
        if token is not None
        else configured_token or str(os.environ.get("BLENDER_BRIDGE_TOKEN") or "")
    )
    try:
        parsed, port = _parse_bridge_url(resolved_url)
    except ValueError as exc:
        checks.append(
            _check(
                "bridge_url",
                "Bridge URL",
                FAIL,
                str(exc),
                recovery="Use the URL shown in Blender's Agent Bridge panel or copy a fresh MCP config.",
            )
        )
        return _report(resolved_url, checks)

    if _loopback_host(parsed.hostname):
        checks.append(
            _check("bridge_url", "Bridge URL", PASS, f"Using loopback bridge URL {parsed.scheme}://{parsed.hostname}:{port}.")
        )
    else:
        if parsed.scheme == "http":
            checks.append(
                _check(
                    "bridge_url",
                    "Bridge URL",
                    FAIL,
                    "Remote bridge connections require HTTPS; plaintext HTTP could expose the bearer token.",
                    recovery="Use a loopback URL or configure an authenticated HTTPS endpoint.",
                )
            )
            return _report(resolved_url, checks)
        checks.append(
            _check(
                "bridge_url",
                "Bridge URL",
                WARN,
                f"The bridge host is not loopback: {parsed.hostname}",
                recovery="Use 127.0.0.1 unless remote HTTPS access is an explicit, secured deployment.",
            )
        )
    checks.append(_socket_check(parsed, port, timeout, socket_connector))

    if server is None:
        from .mcp_server import BlenderMCPServer, BridgeClient

        client_factory = bridge_client_factory or BridgeClient
        bridge_client = bridge_client or client_factory(
            resolved_url,
            token=resolved_token,
            timeout=timeout,
        )
        server = BlenderMCPServer(bridge_client)
    checks.append(_gateway_manifest_check(server))
    health_check, health_status = _bridge_status_check(server)
    checks.append(health_check)
    checks.append(_compatibility_check(health_status))
    checks.append(_schema_lookup_check(server))
    checks.append(_read_only_gateway_check(server, health_check["status"] == PASS))
    return _report(resolved_url, checks)


def _report(bridge_url, checks):
    failures = sum(check["status"] == FAIL for check in checks)
    warnings = sum(check["status"] == WARN for check in checks)
    return {
        "ok": failures == 0,
        "status": FAIL if failures else (WARN if warnings else PASS),
        "bridge_url": _safe_bridge_url(bridge_url),
        "mcp_server_version": build_info.MCP_SERVER_VERSION,
        "checks": checks,
        "summary": {
            "passed": sum(check["status"] == PASS for check in checks),
            "warnings": warnings,
            "failed": failures,
            "skipped": sum(check["status"] == SKIP for check in checks),
        },
        "client_refresh_required_after_config_change": True,
        "client_refresh_guidance": (
            "After replacing a config or connector, fully restart or refresh the MCP client. "
            "Its visible tool list must contain exactly the five names reported by the manifest check."
        ),
    }


def format_report(report):
    lines = [
        f"Blender Agent Bridge doctor {report['mcp_server_version']}",
        f"Overall: {str(report['status']).upper()}",
        "",
    ]
    symbols = {PASS: "PASS", WARN: "WARN", FAIL: "FAIL", SKIP: "SKIP"}
    for check in report["checks"]:
        lines.append(f"[{symbols[check['status']]}] {check['title']}: {check['summary']}")
        if check.get("recovery") and check["status"] != PASS:
            lines.append(f"       Recovery: {check['recovery']}")
    lines.extend(["", report["client_refresh_guidance"]])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="blender-bridge doctor",
        description="Run a deterministic, read-only Blender Agent Bridge connection diagnostic.",
    )
    parser.add_argument("--bridge-url", default=None)
    parser.add_argument("--token", default=None)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--client-config", default="")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = run_connection_diagnostics(
        bridge_url=args.bridge_url,
        token=args.token,
        timeout=args.timeout,
        client_config=args.client_config,
    )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


__all__ = ["format_report", "main", "run_connection_diagnostics"]
