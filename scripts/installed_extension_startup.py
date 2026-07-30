"""Blender-side fixture for the clean installed-extension live smoke."""

from __future__ import annotations

import importlib
import json
import os
import time
import traceback
from pathlib import Path

import bpy


module_name = "bl_ext.user_default.claude_blender"
status_path = Path(os.environ["INSTALLED_LIVE_SMOKE_STATUS"])
ui_status_path = Path(os.environ["INSTALLED_LIVE_SMOKE_UI_STATUS"])
port = int(os.environ.get("INSTALLED_LIVE_SMOKE_PORT", "0"))


def dismiss_startup_popups():
    try:
        for window in bpy.context.window_manager.windows:
            window.event_simulate(type="ESC", value="PRESS")
            window.event_simulate(type="ESC", value="RELEASE")
    except Exception:
        pass
    return None


def run_interactive_ui_smoke():
    test_object = None
    try:
        if bpy.app.background:
            raise AssertionError("Interactive UI smoke unexpectedly started in background mode")
        view_areas = [area for area in bpy.context.screen.areas if area.type == "VIEW_3D"]
        if not view_areas:
            raise AssertionError("No VIEW_3D area is available in the clean installed profile")

        copied = bpy.ops.claude_blender.copy_mcp_config()
        if "FINISHED" not in copied:
            raise AssertionError(f"Copy MCP Config returned {copied}")
        clipboard = bpy.context.window_manager.clipboard.strip()
        if not clipboard:
            raise AssertionError("Copy MCP Config did not write to the system clipboard")
        copied_config = json.loads(clipboard)
        server_config = copied_config["mcpServers"]["blender"]
        bundled_python = Path(str(server_config.get("command") or ""))
        if not bundled_python.is_file() or not bundled_python.name.lower().startswith("python"):
            raise AssertionError(f"Copied config does not use Blender's bundled Python: {server_config}")

        external_assets = importlib.import_module(module_name + ".external_assets")
        session_result = bpy.ops.claude_blender.set_session_sketchfab_token(
            sketchfab_api_token="interactive-smoke-token-not-a-secret"
        )
        if "FINISHED" not in session_result:
            raise AssertionError(f"Set session Sketchfab token returned {session_result}")
        if not external_assets.sketchfab_auth_diagnostics().get("session_token_configured"):
            raise AssertionError("Session Sketchfab token was not available immediately")
        clear_result = bpy.ops.claude_blender.clear_session_sketchfab_token()
        if "FINISHED" not in clear_result:
            raise AssertionError(f"Clear session Sketchfab token returned {clear_result}")
        if external_assets.sketchfab_auth_diagnostics().get("session_token_configured"):
            raise AssertionError("Session Sketchfab token remained configured after Clear")

        script_runner = importlib.import_module(module_name + ".script_runner")
        bridge_server = importlib.import_module(module_name + ".bridge_server")
        tool_dispatcher = importlib.import_module(module_name + ".tool_dispatcher")
        state = bpy.context.scene.claude_blender

        script_runner.revoke_external_script_trust_window(bpy.context)
        trusted_fs_path = status_path.parent / "blender-agent-bridge-installed-trust-smoke.txt"
        trusted_fs_path.unlink(missing_ok=True)
        trust_off = json.loads(
            tool_dispatcher.execute_tool(
                bpy.context,
                "draft_script",
                {
                    "intent": "Verify installed binary script trust",
                    "expected_changes": "Nothing runs and no file is written while trust is off",
                    "risk_level": "low",
                    "code": f"open({str(trusted_fs_path)!r}, 'w').write('unexpected')",
                },
            )
        )
        if trust_off.get("ok") or trust_off.get("code") != "script_trust_required":
            raise AssertionError(f"Installed trust-off request executed: {trust_off}")
        if trusted_fs_path.exists():
            raise AssertionError("Installed trust-off request wrote a filesystem marker")
        for removed_name in (
            "approve_pending_script_for_external_run",
            "reject_pending_script",
            "run_pending_script",
            "stage_script",
        ):
            if hasattr(script_runner, removed_name):
                raise AssertionError(f"Installed legacy per-script helper still exists: {removed_name}")
        if hasattr(state, "pending_script"):
            raise AssertionError("Installed legacy pending-script state still exists")
        session_trust = script_runner.approve_external_script_trust_window(bpy.context, session=True)
        if not session_trust.get("ok"):
            raise AssertionError(f"Installed session trust did not activate: {session_trust}")
        trusted_run = json.loads(
            tool_dispatcher.execute_tool(
                bpy.context,
                "draft_script",
                {
                    "intent": "Verify installed trusted execution",
                    "expected_changes": "Writes one temporary file and sets one scene property",
                    "risk_level": "low",
                    "code": (
                        "import os\n"
                        "import socket\n"
                        "import subprocess\n"
                        f"open({str(trusted_fs_path)!r}, 'w').write(os.path.basename({str(trusted_fs_path)!r}))\n"
                        "scene['installed_trust_smoke'] = 'ok'\n"
                    ),
                },
            )
        )
        if not trusted_run.get("ok") or not trusted_run.get("auto_ran") or bpy.context.scene.get("installed_trust_smoke") != "ok":
            raise AssertionError(f"Installed trusted script did not run immediately: {trusted_run}")
        if not trusted_fs_path.is_file() or trusted_fs_path.read_text(encoding="utf-8") != trusted_fs_path.name:
            raise AssertionError(f"Installed trusted script did not receive normal filesystem access: {trusted_run}")
        if trusted_run.get("authorization_model") != "blender_run_script_equivalent":
            raise AssertionError(f"Installed trusted script reported the wrong authorization model: {trusted_run}")
        del bpy.context.scene["installed_trust_smoke"]
        trusted_fs_path.unlink(missing_ok=True)

        expiring = script_runner.approve_external_script_trust_window(bpy.context, ttl_seconds=1)
        if not expiring.get("ok") or not script_runner.external_script_trust_active(bpy.context, state=state):
            raise AssertionError(f"Installed expiring trust did not activate: {expiring}")
        time.sleep(1.1)
        if not script_runner.expire_external_script_trust_if_needed(bpy.context, state=state):
            raise AssertionError("Installed trust did not expire after its TTL")
        expired_snapshot = script_runner.external_script_trust_snapshot(bpy.context, state=state)
        if expired_snapshot.get("active") or not expired_snapshot.get("expired"):
            raise AssertionError(f"Installed expired trust remained active: {expired_snapshot}")

        session_trust = script_runner.approve_external_script_trust_window(bpy.context, session=True)
        if not session_trust.get("ok"):
            raise AssertionError(f"Installed session trust did not activate: {session_trust}")
        revoked = script_runner.revoke_external_script_trust_window(bpy.context)
        if not revoked.get("ok") or script_runner.external_script_trust_active(bpy.context, state=state):
            raise AssertionError(f"Installed session trust did not revoke: {revoked}")

        script_runner.approve_external_script_trust_window(bpy.context, session=True)
        script_runner.unregister()
        try:
            if script_runner.external_script_trust_active(bpy.context, state=state):
                raise AssertionError("Installed script trust survived add-on reload cleanup")
        finally:
            script_runner.register()

        original_bridge_url = bridge_server.bridge_url()
        original_bridge_port = int(original_bridge_url.rsplit(":", 1)[1])
        script_runner.approve_external_script_trust_window(bpy.context, session=True)
        bridge_server.stop_bridge()
        restarted = bridge_server.start_bridge(port=original_bridge_port, auth_token="")
        if not restarted.get("ok") or restarted.get("url") != original_bridge_url:
            raise AssertionError(f"Installed bridge did not restart on the smoke URL: {restarted}")
        if not script_runner.external_script_trust_active(bpy.context, state=state):
            raise AssertionError("Installed script trust did not persist across bridge restart")
        script_runner.revoke_external_script_trust_window(bpy.context)

        mesh = bpy.data.meshes.new("Agent Bridge Interactive UI Smoke Mesh")
        test_object = bpy.data.objects.new("Agent Bridge Interactive UI Smoke Object", mesh)
        bpy.context.scene.collection.objects.link(test_object)
        presentation = external_assets._show_imported_geometry(bpy.context, [test_object.name])
        if not presentation.get("focused"):
            raise AssertionError(f"Imported geometry was not focused: {presentation}")
        if not presentation.get("material_preview"):
            raise AssertionError(f"Viewport did not enter Material Preview: {presentation}")
        if bpy.context.view_layer.objects.active != test_object or not test_object.select_get():
            raise AssertionError("Imported geometry was not left active and selected")
        shading_modes = [area.spaces.active.shading.type for area in view_areas]
        if any(mode != "MATERIAL" for mode in shading_modes):
            raise AssertionError(f"Unexpected viewport shading after import presentation: {shading_modes}")

        ui_status_path.write_text(
            json.dumps(
                {
                    "ok": True,
                    "clipboard_config": True,
                    "bundled_python": str(bundled_python),
                    "server_config": server_config,
                    "session_token_lifecycle": True,
                    "script_trust_lifecycle": True,
                    "focused": True,
                    "material_preview": True,
                    "view_areas": len(view_areas),
                    "shading_modes": shading_modes,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        ui_status_path.write_text(
            json.dumps(
                {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    finally:
        external_assets = importlib.import_module(module_name + ".external_assets")
        external_assets.clear_session_sketchfab_api_token()
        bpy.context.window_manager.clipboard = ""
        if test_object is not None and bpy.data.objects.get(test_object.name) is not None:
            mesh = test_object.data
            bpy.data.objects.remove(test_object, do_unlink=True)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        dismiss_startup_popups()
    return None


bpy.ops.preferences.addon_enable(module=module_name)
addon_module = importlib.import_module(module_name)
bridge_server = importlib.import_module(module_name + ".bridge_server")
result = bridge_server.start_bridge(port=port, auth_token="")
bpy.app.timers.register(dismiss_startup_popups, first_interval=0.5)
bpy.app.timers.register(run_interactive_ui_smoke, first_interval=1.0)
status_path.write_text(
    json.dumps({"module_file": getattr(addon_module, "__file__", ""), "result": result}, indent=2),
    encoding="utf-8",
)
print("INSTALLED_BRIDGE_START", result, flush=True)
