"""Blender background smoke test for the compact sidebar layout."""

from __future__ import annotations

import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import (  # noqa: E402
    bridge_server,
    credential_store,
    external_assets,
    live_preview,
    preferences,
    script_runner,
    session_credentials,
    ui,
)


class _FakeOperator:
    pass


class _PreferencesProxy:
    """Real preference values behind a fake layout.

    ``AddonPreferences.draw`` reads ``self.layout`` and then hands ``self`` on
    as the preferences object, so a stub with only a layout cannot exercise
    anything that reads an actual setting.
    """

    def __init__(self, prefs, layout):
        object.__setattr__(self, "_prefs", prefs)
        object.__setattr__(self, "layout", layout)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_prefs"), name)


class _FakeLayout:
    def __init__(self, *, shared=None, enabled=True):
        self.alert = False
        self.enabled = enabled
        shared = shared or {
            "labels": [],
            "operators": [],
            "operator_enabled": [],
            "properties": [],
        }
        self._shared = shared
        self.labels = shared["labels"]
        self.operators = shared["operators"]
        self.operator_enabled = shared["operator_enabled"]
        self.properties = shared["properties"]

    def row(self, **_kwargs):
        return _FakeLayout(shared=self._shared, enabled=self.enabled)

    def column(self, **_kwargs):
        return _FakeLayout(shared=self._shared, enabled=self.enabled)

    def box(self):
        return _FakeLayout(shared=self._shared, enabled=self.enabled)

    def label(self, *, text="", **_kwargs):
        self.labels.append(text)

    def operator(self, operator_id, **_kwargs):
        self.operators.append(operator_id)
        self.operator_enabled.append((operator_id, self.enabled))
        return _FakeOperator()

    def prop(self, _owner, property_name, **_kwargs):
        self.properties.append(property_name)

    def separator(self):
        return None


def main():
    claude_blender.register()
    original_is_running = bridge_server.is_running
    try:
        context = bpy.context
        state = context.scene.claude_blender
        state.bridge_source_status = ""
        state.pending_preview = False
        state.last_script_error_summary = ""
        state.last_checkpoint_path = ""
        state.last_checkpoint_status = "No script checkpoint yet"
        script_runner.revoke_external_script_trust_window(context)

        panels = [cls for cls in ui.classes if issubclass(cls, bpy.types.Panel)]
        assert panels == [
            ui.CLAUDEBLENDER_PT_sidebar,
            ui.CLAUDEBLENDER_PT_generation,
        ], panels
        # The generation panel is a closed-by-default child, so it cannot
        # crowd the sidebar it hangs off.
        assert ui.CLAUDEBLENDER_PT_generation.bl_parent_id == "CLAUDEBLENDER_PT_sidebar"
        assert "DEFAULT_CLOSED" in ui.CLAUDEBLENDER_PT_generation.bl_options
        assert not hasattr(ui, "CLAUDEBLENDER_PT_advanced")
        for removed_operator in (
            "CLAUDEBLENDER_OT_run_approved_script",
            "CLAUDEBLENDER_OT_approve_external_script_run",
            "CLAUDEBLENDER_OT_reject_script",
        ):
            assert not hasattr(ui, removed_operator), removed_operator
        assert not hasattr(ui, "_draw_pending_script_review")
        globally_discoverable = {
            ui.CLAUDEBLENDER_OT_commit_preview,
            ui.CLAUDEBLENDER_OT_revert_preview,
            ui.CLAUDEBLENDER_OT_revert_last_preview_step,
            ui.CLAUDEBLENDER_OT_revoke_external_script_trust,
            ui.CLAUDEBLENDER_OT_start_bridge,
            ui.CLAUDEBLENDER_OT_stop_bridge,
            ui.CLAUDEBLENDER_OT_copy_mcp_config,
        }
        for cls in (candidate for candidate in ui.classes if issubclass(candidate, bpy.types.Operator)):
            options = getattr(cls, "bl_options", set())
            if cls in globally_discoverable:
                assert "INTERNAL" not in options, cls
            else:
                assert "INTERNAL" in options, cls
        for removed_renderer in (
            "_draw_advanced_controls",
            "_draw_preview_manifest_section",
            "_draw_audit_section",
            "_draw_visual_evidence_section",
            "_draw_status_section",
        ):
            assert not hasattr(ui, removed_renderer), removed_renderer

        trust_dialog_layout = _FakeLayout()
        trust_dialog = type("_TrustDialog", (), {"layout": trust_dialog_layout})()
        ui.CLAUDEBLENDER_OT_approve_external_script_trust.draw(trust_dialog, context)
        assert trust_dialog_layout.labels == [
            "Trust agent-generated Python for this Blender session?",
            "Equivalent to Blender Run Script: files, network, and processes are allowed.",
            "Any client connected to this local bridge can use these permissions.",
            "Runs with Blender's OS permissions until Revoke, add-on reload, or exit.",
        ], trust_dialog_layout.labels

        # The exact operator sets are a product boundary: adding setup or
        # diagnostics to the default panel must require an intentional test change.
        for running, expected_status, expected_operators in (
            (
                False,
                "Bridge is offline",
                [
                    "claude_blender.start_bridge",
                    "claude_blender.copy_mcp_config",
                    "claude_blender.approve_external_script_trust",
                ],
            ),
            (
                True,
                "Bridge is ready",
                [
                    "claude_blender.stop_bridge",
                    "claude_blender.copy_mcp_config",
                    "claude_blender.approve_external_script_trust",
                ],
            ),
        ):
            bridge_server.is_running = lambda running=running: running
            layout = _FakeLayout()
            panel = type("_Sidebar", (), {"layout": layout})()
            ui.CLAUDEBLENDER_PT_sidebar.draw(panel, context)
            assert layout.labels == [expected_status], layout.labels
            assert layout.operators == expected_operators, layout.operators

        ready_layout = _FakeLayout()
        ready_panel = type("_Sidebar", (), {"layout": ready_layout})()
        ui.CLAUDEBLENDER_PT_sidebar.draw(ready_panel, context)
        trust_operator = ready_layout.operators.index("claude_blender.approve_external_script_trust")
        assert ready_layout.operator_enabled[trust_operator] == (
            "claude_blender.approve_external_script_trust",
            True,
        )

        trusted = script_runner.approve_external_script_trust_window(context, session=True)
        assert trusted["ok"] and trusted["session"], trusted
        bridge_server.is_running = lambda: False
        trusted_layout = _FakeLayout()
        trusted_panel = type("_Sidebar", (), {"layout": trusted_layout})()
        ui.CLAUDEBLENDER_PT_sidebar.draw(trusted_panel, context)
        assert trusted_layout.labels == ["Bridge is offline", "Script trust active"], trusted_layout.labels
        assert trusted_layout.operators == [
            "claude_blender.start_bridge",
            "claude_blender.copy_mcp_config",
            "claude_blender.revoke_external_script_trust",
        ], trusted_layout.operators
        assert script_runner.revoke_external_script_trust_window(context)["ok"]

        state.last_script_error_summary = "Old script failure"
        state.last_checkpoint_status = "Checkpoint disabled"
        history_layout = _FakeLayout()
        history_panel = type("_Sidebar", (), {"layout": history_layout})()
        ui.CLAUDEBLENDER_PT_sidebar.draw(history_panel, context)
        assert history_layout.labels == ["Bridge is offline"], history_layout.labels
        assert history_layout.operators == [
            "claude_blender.start_bridge",
            "claude_blender.copy_mcp_config",
            "claude_blender.approve_external_script_trust",
        ], history_layout.operators

        state.last_script_error_summary = ""
        state.last_checkpoint_status = "No script checkpoint yet"

        # The removed per-script workflow has no state properties or execution
        # helpers left that a later panel edit could accidentally expose.
        for removed_property in (
            "pending_script",
            "pending_script_blocked",
            "pending_script_text_name",
            "pending_script_external_approval_hash",
        ):
            assert not hasattr(state, removed_property), removed_property
        for removed_helper in (
            "approve_pending_script_for_external_run",
            "reject_pending_script",
            "run_pending_script",
            "stage_script",
        ):
            assert not hasattr(script_runner, removed_helper), removed_helper
        script_layout = _FakeLayout()
        script_panel = type("_Sidebar", (), {"layout": script_layout})()
        ui.CLAUDEBLENDER_PT_sidebar.draw(script_panel, context)
        assert script_layout.labels == ["Bridge is offline"], script_layout.labels
        assert script_layout.operators == [
            "claude_blender.start_bridge",
            "claude_blender.copy_mcp_config",
            "claude_blender.approve_external_script_trust",
        ], script_layout.operators

        bridge_server.is_running = lambda: False
        state.pending_preview = True
        state.pending_preview_label = "Preview changes"
        state.pending_preview_summary = ""
        state.pending_preview_warnings = ""
        preview_layout = _FakeLayout()
        preview_panel = type("_Sidebar", (), {"layout": preview_layout})()
        ui.CLAUDEBLENDER_PT_sidebar.draw(preview_panel, context)
        assert preview_layout.labels == [
            "Bridge is offline",
            "Pending",
            "Live Preview:",
            "Preview changes",
        ], preview_layout.labels
        assert preview_layout.operators == [
            "claude_blender.start_bridge",
            "claude_blender.copy_mcp_config",
            "claude_blender.approve_external_script_trust",
            "claude_blender.commit_preview",
            "claude_blender.revert_preview",
        ], preview_layout.operators
        state.pending_preview = False

        transaction = live_preview.begin("Imported asset", context)
        transaction["applied_steps"].append(
            {
                "type": "import_external_asset",
                "created_data": [{"kind": "object", "name": "Synthetic Imported Object"}],
            }
        )
        state.pending_preview = True
        state.pending_preview_label = "Imported asset"
        imported_layout = _FakeLayout()
        imported_panel = type("_Sidebar", (), {"layout": imported_layout})()
        ui.CLAUDEBLENDER_PT_sidebar.draw(imported_panel, context)
        assert "claude_blender.revert_last_preview_step" in imported_layout.operators, imported_layout.operators
        transaction["status"] = "reverted"
        state.pending_preview = False

        cube = bpy.data.objects["Cube"]
        start_location = tuple(cube.location)
        moved = live_preview.apply_location_delta(context, (1, 0, 0), label="UI revert smoke")
        assert moved["ok"] and state.pending_preview, moved
        assert "FINISHED" in bpy.ops.claude_blender.revert_preview()
        assert tuple(cube.location) == start_location
        assert not state.pending_preview

        # This smoke registers the package directly rather than through
        # addon_enable, so there is no Addons entry and therefore no
        # preferences instance until one is made.
        if context.preferences.addons.get("claude_blender") is None:
            context.preferences.addons.new().module = "claude_blender"
        addon_prefs = preferences.get_preferences(context)
        assert addon_prefs is not None
        session_credentials.clear_session_credentials()

        prefs_layout = _FakeLayout()
        preferences.CLAUDEBLENDER_AP_preferences.draw(
            _PreferencesProxy(addon_prefs, prefs_layout), context
        )
        assert prefs_layout.properties == [
            "checkpoints_enabled",
            "autosave_enabled",
            "bridge_port",
            "bridge_auth_token",
            "mcp_launch_mode",
            "generation_python",
            "triposr_root",
            "generation_endpoint",
            "generation_endpoint_token",
            "remember_api_keys",
            "sketchfab_api_token",
            "generation_egress_allowed",
            "tripo_api_key",
            "meshy_api_key",
        ], prefs_layout.properties
        # Every provider that takes a key is offered one in the same panel, and
        # Poly Haven says why it has no field rather than leaving a gap.
        assert "Provider Credentials" in prefs_layout.labels, prefs_layout.labels
        assert "Poly Haven needs no key: open API, every asset CC0." in prefs_layout.labels
        # The split between the two credential groups is about data direction,
        # not about how a key is stored, and has to say so on screen.
        assert "Download assets from" in prefs_layout.labels, prefs_layout.labels
        assert "Generate from your images with" in prefs_layout.labels
        assert "These send your reference images to the vendor." in prefs_layout.labels
        assert not hasattr(preferences.CLAUDEBLENDER_AP_preferences, "execution_mode")

        # Nothing is held yet, so no credential offers to be cleared.
        assert "claude_blender.clear_session_credential" not in prefs_layout.operators

        print("== every provider key takes the same route ==")
        # Remembering is the default, and it is the OS store that remembers.
        assert addon_prefs.remember_api_keys is True
        assert credential_store.is_available(), credential_store.describe()
        credential_store.forget_everything()

        for attribute, credential, secret in (
            ("tripo_api_key", session_credentials.TRIPO_API_KEY, "tsk_smoke_secret"),
            ("sketchfab_api_token", session_credentials.SKETCHFAB_API_TOKEN, "sfab_smoke_secret"),
        ):
            setattr(addon_prefs, attribute, secret)
            # The field blanks itself: no key reaches userpref.blend, ever.
            assert getattr(addon_prefs, attribute) == "", attribute
            assert session_credentials.session_credential(credential) == secret, attribute
            assert credential_store.load_credential(credential) == secret, attribute

        assert external_assets.session_sketchfab_api_token() == "sfab_smoke_secret"

        held_layout = _FakeLayout()
        preferences.CLAUDEBLENDER_AP_preferences.draw(
            _PreferencesProxy(addon_prefs, held_layout), context
        )
        assert "Tripo: remembered on this machine" in held_layout.labels, held_layout.labels
        assert "Sketchfab: remembered on this machine" in held_layout.labels
        clears = [
            enabled
            for operator_id, enabled in held_layout.operator_enabled
            if operator_id == "claude_blender.clear_session_credential"
        ]
        # Two offers, and the hosted one is gated by the upload toggle.
        assert clears == [True, False], clears

        print("== clearing reaches memory and disk together ==")
        assert "FINISHED" in bpy.ops.claude_blender.clear_session_credential(
            credential=session_credentials.TRIPO_API_KEY
        )
        assert session_credentials.session_credential(session_credentials.TRIPO_API_KEY) == ""
        # A key that came back on the next restart would not really be cleared.
        assert credential_store.load_credential(session_credentials.TRIPO_API_KEY) == ""
        # An unknown name is refused loudly rather than silently doing nothing.
        try:
            bpy.ops.claude_blender.clear_session_credential(credential="nope")
        except RuntimeError as error:
            assert "Unknown credential" in str(error), error
        else:
            raise AssertionError("clearing an unknown credential should fail")

        print("== turning remembering off erases what was stored ==")
        addon_prefs.remember_api_keys = False
        assert credential_store.load_credential(session_credentials.SKETCHFAB_API_TOKEN) == ""
        # ...but the running session keeps working.
        assert external_assets.session_sketchfab_api_token() == "sfab_smoke_secret"

        addon_prefs.meshy_api_key = "msy_smoke_secret"
        assert addon_prefs.meshy_api_key == ""
        assert credential_store.load_credential(session_credentials.MESHY_API_KEY) == ""
        assert session_credentials.session_credential(
            session_credentials.MESHY_API_KEY
        ) == "msy_smoke_secret"

        print("== a stale plain-text preference is migrated away ==")
        # Earlier builds wrote the key straight into userpref.blend.
        addon_prefs.remember_api_keys = True
        session_credentials.clear_session_credentials()
        # Suppressing the scrub reproduces exactly what an older build left
        # behind: a live key sitting in the preference field.
        preferences._SCRUBBING.add("tripo_api_key")
        try:
            addon_prefs.tripo_api_key = "tsk_legacy_plaintext"
        finally:
            preferences._SCRUBBING.discard("tripo_api_key")
        assert addon_prefs.tripo_api_key == "tsk_legacy_plaintext"
        seeded = preferences.seed_session_credentials(addon_prefs)
        assert session_credentials.TRIPO_API_KEY in seeded, seeded
        assert addon_prefs.tripo_api_key == "", addon_prefs.tripo_api_key
        assert session_credentials.session_credential(
            session_credentials.TRIPO_API_KEY
        ) == "tsk_legacy_plaintext"

        credential_store.forget_everything()
        session_credentials.clear_session_credentials()
        addon_prefs.remember_api_keys = False

        print("smoke_ui_layout: ok")
    finally:
        bridge_server.is_running = original_is_running
        claude_blender.unregister()


if __name__ == "__main__":
    main()
