"""Add-on preferences for Blender Agent Bridge."""

from __future__ import annotations

import bpy

from . import user_paths


def _default_cache_dir():
    return user_paths.user_data_path("docs_cache")


def _default_capture_dir():
    return user_paths.user_data_path("captures")


def _default_checkpoint_dir():
    return user_paths.user_data_path("checkpoints")


class CLAUDEBLENDER_AP_preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    screenshot_default: bpy.props.BoolProperty(
        name="Screenshot Toggle Default",
        description="Default state for viewport screenshot inclusion",
        default=False,
    )
    local_docs_first: bpy.props.BoolProperty(
        name="Local Docs First",
        description="Use cached/local Blender docs before online lookup",
        default=True,
    )
    docs_cache_dir: bpy.props.StringProperty(
        name="Docs Cache",
        description="Directory for cached Blender documentation snippets",
        subtype="DIR_PATH",
        default=_default_cache_dir(),
    )
    capture_cache_dir: bpy.props.StringProperty(
        name="Capture Cache",
        description="Optional custom base directory for viewport screenshots. Blank or default uses project-local captures when possible.",
        subtype="DIR_PATH",
        default=_default_capture_dir(),
    )
    checkpoint_dir: bpy.props.StringProperty(
        name="Checkpoint Directory",
        description="Directory for timestamped blend backups before trusted scripts run",
        subtype="DIR_PATH",
        default=_default_checkpoint_dir(),
    )
    max_screenshot_bytes: bpy.props.IntProperty(
        name="Max Screenshot Bytes",
        description="Maximum PNG screenshot size to attach to an API request",
        default=5 * 1024 * 1024,
        min=256 * 1024,
        soft_max=10 * 1024 * 1024,
    )
    checkpoints_enabled: bpy.props.BoolProperty(
        name="Checkpoints",
        description="Save blend checkpoints before risky changes",
        default=True,
    )
    autosave_enabled: bpy.props.BoolProperty(
        name="Autosave",
        description="Automatically save the active blend file in place after it has a user-confirmed path",
        default=True,
    )
    autosave_interval_seconds: bpy.props.IntProperty(
        name="Autosave Interval Seconds",
        description="Minimum seconds between in-place autosaves of the active blend file",
        default=300,
        min=30,
        soft_max=1800,
    )
    bridge_port: bpy.props.IntProperty(
        name="Bridge Port",
        description="Localhost HTTP bridge port for external MCP access",
        default=8765,
        min=1024,
        max=65535,
    )
    bridge_auth_token: bpy.props.StringProperty(
        name="Bridge Token",
        description="Optional bearer token required by the localhost bridge. Leave empty for no token.",
        subtype="PASSWORD",
        default="",
    )
    mcp_launch_mode: bpy.props.EnumProperty(
        name="MCP Runtime",
        description="Choose the external MCP server launched by copied client configurations",
        items=(
            ("BUNDLED", "Bundled", "Use the MCP server included in this Blender extension; works offline"),
            ("UVX", "uvx / PyPI", "Use the matching blender-bridge package from PyPI through uvx"),
        ),
        default="BUNDLED",
    )

    # Image-to-3D generation providers. These live in add-on preferences rather
    # than the MCP client config because the tool handler runs inside Blender
    # and never sees the MCP server process environment.
    generation_egress_allowed: bpy.props.BoolProperty(
        name="Allow Third-Party Uploads",
        description=(
            "Permit hosted providers to receive reference images. Off by default: many studios "
            "may not send client artwork to a third party. Local models and a self-hosted "
            "endpoint work with this off"
        ),
        default=False,
    )
    triposr_root: bpy.props.StringProperty(
        name="TripoSR Folder",
        description="Checkout containing run.py for local TripoSR generation",
        subtype="DIR_PATH",
        default="",
    )
    generation_python: bpy.props.StringProperty(
        name="Generation Python",
        description=(
            "Interpreter with torch installed, used to probe GPU capability and run local "
            "models. Blender's bundled Python is not used"
        ),
        subtype="FILE_PATH",
        default="",
    )
    generation_endpoint: bpy.props.StringProperty(
        name="Studio Endpoint",
        description="Base URL of a self-hosted inference server; counts as local, needs no egress",
        default="",
    )
    generation_endpoint_token: bpy.props.StringProperty(
        name="Endpoint Token",
        description="Optional bearer token for the self-hosted endpoint",
        subtype="PASSWORD",
        default="",
    )
    tripo_api_key: bpy.props.StringProperty(
        name="Tripo API Key",
        description=(
            "Stored in Blender preferences on disk, masked in this panel but not encrypted. "
            "Leave empty and use an environment variable if that is unacceptable"
        ),
        subtype="PASSWORD",
        default="",
    )
    meshy_api_key: bpy.props.StringProperty(
        name="Meshy API Key",
        description=(
            "Stored in Blender preferences on disk, masked in this panel but not encrypted. "
            "Leave empty and use an environment variable if that is unacceptable"
        ),
        subtype="PASSWORD",
        default="",
    )

    def draw(self, context):
        layout = self.layout
        safety = layout.box()
        safety.label(text="Safety")
        safety.prop(self, "checkpoints_enabled")
        safety.prop(self, "autosave_enabled")

        connection = layout.box()
        connection.label(text="Connection")
        connection.prop(self, "bridge_port")
        connection.prop(self, "bridge_auth_token")
        connection.prop(self, "mcp_launch_mode")

        draw_generation_settings(layout.box(), self, title="Image-To-3D Generation")


def draw_generation_settings(layout, prefs, *, title=""):
    """Lay out the generation settings.

    Shared by the add-on preferences and the viewport sidebar so the two views
    cannot drift as providers are added.
    """

    if title:
        layout.label(text=title)
    layout.prop(prefs, "generation_python")
    layout.prop(prefs, "triposr_root")
    layout.separator()
    layout.prop(prefs, "generation_endpoint")
    layout.prop(prefs, "generation_endpoint_token")
    layout.separator()
    layout.prop(prefs, "generation_egress_allowed")
    hosted = layout.column()
    hosted.enabled = bool(prefs.generation_egress_allowed)
    hosted.prop(prefs, "tripo_api_key")
    hosted.prop(prefs, "meshy_api_key")
    if not prefs.generation_egress_allowed:
        layout.label(text="Hosted providers stay disabled until uploads are allowed.", icon="INFO")


def generation_environment_overlay(prefs):
    """Map generation preferences onto the env names the provider layer reads.

    The mapping itself lives in ``generation_providers`` so it stays importable
    without bpy and is covered by tests directly rather than through a copy.
    """

    from . import generation_providers

    return generation_providers.environment_overlay(prefs)


def get_preferences(context):
    addon = context.preferences.addons.get(__package__)
    if addon is None:
        return None
    return addon.preferences


classes = (
    CLAUDEBLENDER_AP_preferences,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
