"""Local bridge transport and timeout recovery, shared by MCP and diagnostics."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
try:
    from . import bridge_protocol
except ImportError:
    import bridge_protocol

def _env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


DEFAULT_BRIDGE_URL = "http://127.0.0.1:8765"


DEFAULT_BRIDGE_MAIN_THREAD_TIMEOUT_SECONDS = max(10.0, _env_float("BLENDER_AGENT_BRIDGE_REQUEST_TIMEOUT", "90"))


BRIDGE_MAIN_THREAD_TIMEOUT_GRACE_SECONDS = 10.0


MCP_TIMEOUT_GRACE_SECONDS = 15.0


class BridgeTimeoutError(RuntimeError):
    def __init__(self, message, *, data=None):
        super().__init__(message)
        self.data = dict(data or {})


def _bridge_timeout_for_tool(name):
    try:
        contract = bridge_protocol.normalized_tool_contract(str(name or ""))
        contract_timeout = float(contract.get("timeout_seconds") or 30)
    except Exception:
        contract_timeout = 30.0
    bridge_timeout = max(
        DEFAULT_BRIDGE_MAIN_THREAD_TIMEOUT_SECONDS,
        contract_timeout + BRIDGE_MAIN_THREAD_TIMEOUT_GRACE_SECONDS,
    )
    return max(30.0, bridge_timeout + MCP_TIMEOUT_GRACE_SECONDS)


def _timeout_recovery_data(tool_name="", request_timeout=0):
    tool_name = str(tool_name or "")
    contract = bridge_protocol.normalized_tool_contract(tool_name) if tool_name else {}
    recovery = dict(contract.get("timeout_recovery") or {})
    recommended_tool = str(recovery.get("recommended_tool") or "")
    if not recommended_tool and any(term in tool_name for term in ("render", "playblast", "thumbnail")):
        recommended_tool = "start_render_job"
    return {
        "tool": tool_name,
        "recoverable": True,
        "request_may_still_be_running": True,
        "result_may_be_lost_after_client_timeout": True,
        "timeout_seconds": int(round(float(request_timeout or 0))),
        "poll_after_seconds": int(recovery.get("poll_after_seconds") or 5),
        "status_tool": str(recovery.get("status_tool") or "blender_bridge_status"),
        "resource_tool": str(recovery.get("resource_tool") or "get_visual_evidence_resources"),
        "recommended_tool": recommended_tool,
        "duration_hint": str(contract.get("duration_hint") or ""),
        "recovery_hint": str(
            recovery.get("message")
            or "Wait briefly, call blender_bridge_status, then inspect latest resources/audit logs before rerunning."
        ),
    }


class BridgeClient:
    def __init__(self, base_url, token="", timeout=30):
        self.base_url = str(base_url or DEFAULT_BRIDGE_URL).rstrip("/")
        self.token = str(token or "")
        self.timeout = float(timeout)

    def _headers(self):
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def get(self, path, params=None):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Bridge HTTP {exc.code}: {detail}") from exc
        except OSError as exc:
            raise RuntimeError(f"Bridge unavailable at {self.base_url}: {exc}") from exc

    def post(self, path, payload, *, timeout=None):
        headers = self._headers()
        headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        request_timeout = max(float(timeout if timeout is not None else self.timeout), self.timeout)
        try:
            with urllib.request.urlopen(request, timeout=request_timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 504:
                data = _timeout_recovery_data(
                    str((payload or {}).get("name") or ""),
                    request_timeout,
                )
                data["operation_id"] = str((payload or {}).get("operation_id") or "")
                try:
                    detail_payload = json.loads(detail)
                    if isinstance(detail_payload, dict):
                        result_payload = detail_payload.get("result")
                        if isinstance(result_payload, dict):
                            data.update(result_payload)
                        else:
                            data.update(detail_payload)
                except json.JSONDecodeError:
                    data["bridge_detail"] = detail[:1000]
                raise BridgeTimeoutError(
                    f"Bridge HTTP 504 after {request_timeout:.0f}s: {data.get('message') or detail}",
                    data=data,
                ) from exc
            raise RuntimeError(f"Bridge HTTP {exc.code}: {detail}") from exc
        except TimeoutError as exc:
            data = dict(_timeout_recovery_data(str((payload or {}).get("name") or ""), request_timeout), operation_id=str((payload or {}).get("operation_id") or ""))
            raise BridgeTimeoutError(
                f"Bridge request timed out after {request_timeout:.0f}s. "
                "The Blender operation may still be running; wait for Blender to become responsive. "
                "Call blender_bridge_status, then inspect latest visual evidence resources or audit logs before rerunning.",
                data=data,
            ) from exc
        except OSError as exc:
            if "timed out" in str(exc).lower():
                data = dict(_timeout_recovery_data(str((payload or {}).get("name") or ""), request_timeout), operation_id=str((payload or {}).get("operation_id") or ""))
                raise BridgeTimeoutError(
                    f"Bridge request timed out after {request_timeout:.0f}s. "
                    "The Blender operation may still be running; wait for Blender to become responsive. "
                    "Call blender_bridge_status, then inspect latest visual evidence resources or audit logs before rerunning.",
                    data=data,
                ) from exc
            raise RuntimeError(f"Bridge unavailable at {self.base_url}: {exc}") from exc
