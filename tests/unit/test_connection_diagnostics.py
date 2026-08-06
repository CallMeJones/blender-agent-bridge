from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import bridge_protocol, build_info, connection_diagnostics, mcp_server  # noqa: E402


class _Connection:
    def close(self):
        return None


class _Bridge:
    def __init__(self, *, health=None, health_error=None):
        self.base_url = "http://127.0.0.1:8765"
        self.health = health or {
            "ok": True,
            "bridge_url": "http://127.0.0.1:8765",
            "bridge_version": bridge_protocol.BRIDGE_VERSION,
            "blender_version": "5.1.2",
            "addon_version": build_info.ADDON_VERSION,
            "addon_source_hash": build_info.source_tree_hash(),
            "addon_loaded_source_hash": build_info.source_tree_hash(),
            "addon_runtime_source_stale": False,
            "tool_registry_digest": build_info.TOOL_REGISTRY_DIGEST,
        }
        self.health_error = health_error
        self.invocations = []

    def get(self, path, params=None):
        if path == "/health":
            if self.health_error:
                raise RuntimeError(self.health_error)
            return dict(self.health)
        if path == "/tools":
            return {"ok": True, "tools": []}
        raise AssertionError(path)

    def post(self, path, payload, timeout=None):
        self.invocations.append((path, payload))
        return {
            "ok": True,
            "result": {
                "ok": True,
                "objects": [{"name": "Cube"}],
            },
        }


def _socket_connector(address, timeout):
    return _Connection()


class ConnectionDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.environment = mock.patch.dict(
            os.environ,
            {
                "BLENDER_MCP_TOOL_SURFACE": "gateway",
                "CLAUDE_BLENDER_TOOL_REGISTRY_DIGEST": build_info.TOOL_REGISTRY_DIGEST,
            },
            clear=False,
        )
        self.environment.start()
        self.audit_patch = mock.patch.object(mcp_server.audit_log, "append_event")
        self.audit_patch.start()

    def tearDown(self):
        self.audit_patch.stop()
        self.environment.stop()

    def _run(self, bridge):
        server = mcp_server.BlenderMCPServer(bridge)
        return connection_diagnostics.run_connection_diagnostics(
            bridge_url="http://127.0.0.1:8765",
            server=server,
            socket_connector=_socket_connector,
        )

    def test_healthy_probe_exercises_schema_and_read_only_gateway(self):
        bridge = _Bridge()
        report = self._run(bridge)
        checks = {item["id"]: item for item in report["checks"]}

        self.assertTrue(report["ok"], report)
        self.assertEqual("pass", checks["gateway_manifest"]["status"])
        self.assertEqual(5, len(checks["gateway_manifest"]["details"]["advertised_tools"]))
        self.assertEqual("pass", checks["schema_lookup"]["status"])
        self.assertEqual("pass", checks["read_only_gateway"]["status"])
        self.assertEqual("list_scene_objects", bridge.invocations[0][1]["name"])

    def test_unauthorized_health_reports_token_recovery_and_skips_scene_probe(self):
        report = self._run(_Bridge(health_error="Bridge HTTP 401: Unauthorized"))
        checks = {item["id"]: item for item in report["checks"]}

        self.assertFalse(report["ok"])
        self.assertEqual("fail", checks["blender_health"]["status"])
        self.assertIn("token", checks["blender_health"]["recovery"].lower())
        self.assertEqual("skip", checks["read_only_gateway"]["status"])

    def test_non_bridge_http_service_reports_occupied_port_recovery(self):
        report = self._run(_Bridge(health_error="Expecting value: line 1 column 1"))
        checks = {item["id"]: item for item in report["checks"]}

        self.assertEqual("fail", checks["blender_health"]["status"])
        self.assertIn("another process", checks["blender_health"]["recovery"].lower())

    def test_registry_mismatch_does_not_fail_the_connection(self):
        # Helpers resolve against the live registry in Blender, so a digest
        # that has moved on is a note, not a fault. Reporting it as a failure
        # sent users through a copy-config-and-restart cycle for nothing.
        health = dict(_Bridge().health)
        health["tool_registry_digest"] = "0" * 64
        report = self._run(_Bridge(health=health))
        checks = {item["id"]: item for item in report["checks"]}

        self.assertNotEqual("fail", checks["runtime_compatibility"]["status"])

    def test_stale_loaded_addon_requires_reload(self):
        health = dict(_Bridge().health)
        health["addon_runtime_source_stale"] = True
        health["addon_reload_guidance"] = "Restart Blender."
        report = self._run(_Bridge(health=health))
        checks = {item["id"]: item for item in report["checks"]}

        self.assertEqual("fail", checks["runtime_compatibility"]["status"])
        self.assertEqual("Restart Blender.", checks["runtime_compatibility"]["recovery"])

    def test_addon_and_mcp_patch_versions_must_match(self):
        health = dict(_Bridge().health)
        health["addon_version"] = "0.4.0"
        health["mcp_server_version"] = "0.4.0"
        report = self._run(_Bridge(health=health))
        checks = {item["id"]: item for item in report["checks"]}

        self.assertEqual("fail", checks["runtime_compatibility"]["status"])
        self.assertIn("0.4.0", checks["runtime_compatibility"]["summary"])
        self.assertIn(build_info.MCP_SERVER_VERSION, checks["runtime_compatibility"]["summary"])

    def test_bundled_source_mismatch_requires_fresh_config(self):
        health = dict(_Bridge().health)
        health["addon_source_hash"] = "1" * 64
        report = self._run(_Bridge(health=health))
        checks = {item["id"]: item for item in report["checks"]}

        self.assertEqual("fail", checks["runtime_compatibility"]["status"])
        self.assertIn("source hash", checks["runtime_compatibility"]["summary"].lower())

    def test_client_config_detects_missing_bundled_server_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_path = os.path.join(temporary, "client.json")
            payload = {
                "mcpServers": {
                    "blender": {
                        "command": sys.executable,
                        "args": [os.path.join(temporary, "missing", "mcp_server.py")],
                        "env": {},
                    }
                }
            }
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)

            check = connection_diagnostics._client_config_check(config_path)

        self.assertEqual("fail", check["status"])
        self.assertIn("no longer exists", check["summary"])
        self.assertIn("fresh", check["recovery"].lower())

    def test_client_config_accepts_current_resolvable_entry_without_exposing_env(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_path = os.path.join(temporary, "client.json")
            payload = {
                "mcpServers": {
                    "blender": {
                        "command": sys.executable,
                        "args": [],
                        "env": {
                            "BLENDER_BRIDGE_TOKEN": "do-not-report",
                            "CLAUDE_BLENDER_MCP_SERVER_VERSION": build_info.MCP_SERVER_VERSION,
                            "CLAUDE_BLENDER_TOOL_REGISTRY_DIGEST": build_info.TOOL_REGISTRY_DIGEST,
                        },
                    }
                }
            }
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)

            check = connection_diagnostics._client_config_check(config_path)

        self.assertEqual("pass", check["status"])
        self.assertNotIn("do-not-report", json.dumps(check))

    def test_documented_client_config_shapes_normalize_to_one_entry(self):
        server_path = os.path.join(
            ROOT,
            "addon",
            "claude_blender",
            "mcp_server.py",
        )
        bridge_url = "http://127.0.0.1:9999"
        fixtures = {
            "gemini": {
                "mcpServers": {
                    "blender-agent-bridge": {
                        "command": sys.executable,
                        "args": ["--bridge-url", bridge_url],
                        "env": {"BLENDER_BRIDGE_TOKEN": "gemini-secret"},
                        "trust": False,
                    }
                }
            },
            "vscode": {
                "servers": {
                    "blender_agent_bridge": {
                        "type": "stdio",
                        "command": sys.executable,
                        "args": ["--bridge-url", bridge_url],
                        "env": {"BLENDER_BRIDGE_TOKEN": "vscode-secret"},
                    }
                }
            },
            "opencode": {
                "mcp": {
                    "blender_agent_bridge": {
                        "type": "local",
                        "command": [
                            sys.executable,
                            server_path,
                            "--bridge-url",
                            bridge_url,
                        ],
                        "environment": {
                            "BLENDER_BRIDGE_TOKEN": "opencode-secret"
                        },
                        "enabled": True,
                    }
                }
            },
            "custom_id": {
                "mcpServers": {
                    "my-3d-tools": {
                        "command": sys.executable,
                        "args": ["--bridge-url", bridge_url],
                        "env": {
                            "CLAUDE_BLENDER_MCP_SERVER_VERSION": (
                                build_info.MCP_SERVER_VERSION
                            ),
                            "BLENDER_BRIDGE_TOKEN": "custom-secret",
                        },
                    }
                }
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            for client, payload in fixtures.items():
                with self.subTest(client=client):
                    config_path = os.path.join(
                        temporary,
                        f"{client}.json",
                    )
                    with open(
                        config_path,
                        "w",
                        encoding="utf-8",
                    ) as handle:
                        json.dump(payload, handle)
                    check, settings = (
                        connection_diagnostics._inspect_client_config(
                            config_path
                        )
                    )
                    self.assertEqual("pass", check["status"], check)
                    self.assertEqual(bridge_url, settings["bridge_url"])
                    self.assertNotIn(
                        settings["token"],
                        json.dumps(check),
                    )

    def test_client_config_rejects_multiple_equally_ranked_blender_entries(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_path = os.path.join(temporary, "client.json")
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "mcpServers": {
                            "blender": {
                                "command": sys.executable,
                            },
                            "blender-agent-bridge": {
                                "command": sys.executable,
                            },
                        }
                    },
                    handle,
                )
            check = connection_diagnostics._client_config_check(
                config_path
            )

        self.assertEqual("fail", check["status"])
        self.assertIn("multiple", check["summary"].lower())

    def test_client_config_rejects_non_gateway_surface(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_path = os.path.join(temporary, "client.json")
            payload = {
                "mcpServers": {
                    "blender": {
                        "command": sys.executable,
                        "args": [],
                        "env": {"BLENDER_MCP_TOOL_SURFACE": "direct"},
                    }
                }
            }
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)

            check = connection_diagnostics._client_config_check(config_path)

        self.assertEqual("fail", check["status"])
        self.assertIn("non-default", check["summary"])

    def test_client_config_connection_values_drive_the_probe_without_leaking_token(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_path = os.path.join(temporary, "client.json")
            payload = {
                "mcpServers": {
                    "blender": {
                        "command": sys.executable,
                        "args": [],
                        "env": {
                            "BLENDER_BRIDGE_URL": "http://127.0.0.1:9999",
                            "BLENDER_BRIDGE_TOKEN": "configured-secret",
                        },
                    }
                }
            }
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            connections = []
            clients = []

            def connector(address, timeout):
                connections.append(address)
                return _Connection()

            def client_factory(url, *, token, timeout):
                clients.append((url, token))
                return _Bridge()

            report = connection_diagnostics.run_connection_diagnostics(
                client_config=config_path,
                socket_connector=connector,
                bridge_client_factory=client_factory,
            )

        self.assertTrue(report["ok"], report)
        self.assertEqual([("127.0.0.1", 9999)], connections)
        self.assertEqual(
            [("http://127.0.0.1:9999", "configured-secret")],
            clients,
        )
        self.assertNotIn("configured-secret", json.dumps(report))

    def test_client_config_and_explicit_target_mismatch_stops_before_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_path = os.path.join(temporary, "client.json")
            payload = {
                "mcpServers": {
                    "blender": {
                        "command": sys.executable,
                        "args": ["--bridge-url", "http://127.0.0.1:9999"],
                        "env": {},
                    }
                }
            }
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            report = connection_diagnostics.run_connection_diagnostics(
                bridge_url="http://127.0.0.1:8765",
                client_config=config_path,
                socket_connector=lambda *args, **kwargs: self.fail(
                    "socket should not be called"
                ),
            )

        checks = {item["id"]: item for item in report["checks"]}
        self.assertFalse(report["ok"])
        self.assertEqual("fail", checks["connection_target"]["status"])

    def test_remote_plaintext_bridge_stops_before_network(self):
        report = connection_diagnostics.run_connection_diagnostics(
            bridge_url="http://192.0.2.1:8765",
            token="do-not-send",
            socket_connector=lambda *args, **kwargs: self.fail(
                "socket should not be called"
            ),
        )

        checks = {item["id"]: item for item in report["checks"]}
        self.assertFalse(report["ok"])
        self.assertEqual("fail", checks["bridge_url"]["status"])
        self.assertIn("HTTPS", checks["bridge_url"]["summary"])
        self.assertNotIn("do-not-send", json.dumps(report))

    def test_invalid_url_stops_before_network_checks(self):
        report = connection_diagnostics.run_connection_diagnostics(
            bridge_url="not-a-url",
            socket_connector=lambda *args, **kwargs: self.fail("socket should not be called"),
        )
        checks = {item["id"]: item for item in report["checks"]}
        self.assertFalse(report["ok"])
        self.assertEqual("fail", checks["bridge_url"]["status"])

    def test_url_credentials_are_rejected_and_redacted(self):
        report = connection_diagnostics.run_connection_diagnostics(
            bridge_url="http://secret@127.0.0.1:8765",
            socket_connector=lambda *args, **kwargs: self.fail("socket should not be called"),
        )
        self.assertFalse(report["ok"])
        self.assertNotIn("secret", json.dumps(report))

    def test_bridge_url_rejects_paths_and_queries_before_network_access(self):
        for bridge_url in (
            "http://127.0.0.1:8765/not-the-bridge",
            "http://127.0.0.1:8765?token=secret",
        ):
            with self.subTest(bridge_url=bridge_url):
                report = connection_diagnostics.run_connection_diagnostics(
                    bridge_url=bridge_url,
                    socket_connector=lambda *args, **kwargs: self.fail("socket should not be called"),
                )
                self.assertFalse(report["ok"])
                self.assertNotIn("secret", json.dumps(report))

    def test_text_report_contains_recovery_without_tokens(self):
        report = self._run(_Bridge(health_error="Bridge HTTP 401: Unauthorized"))
        text = connection_diagnostics.format_report(report)
        self.assertIn("Overall: FAIL", text)
        self.assertIn("Recovery:", text)
        self.assertNotIn("do-not-report", text)

    def test_bundled_script_propagates_failed_doctor_exit_code(self):
        completed = subprocess.run(
            [
                sys.executable,
                os.path.join(ROOT, "addon", "claude_blender", "mcp_server.py"),
                "doctor",
                "--bridge-url",
                "invalid",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(1, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("Overall: FAIL", completed.stdout)


if __name__ == "__main__":
    unittest.main()
