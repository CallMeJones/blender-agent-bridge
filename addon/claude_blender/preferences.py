"""Add-on preferences for Blender Agent Bridge."""

from __future__ import annotations

import bpy

from . import credential_store, session_credentials, user_paths

# Preference field -> the session credential it feeds. Every provider that
# needs a secret goes through this one table, so Sketchfab and the generation
# providers cannot drift back into separate handling. Poly Haven is absent
# because its API is open and every asset is CC0 -- there is no key to hold.
CREDENTIAL_FIELDS = (
    ("sketchfab_api_token", session_credentials.SKETCHFAB_API_TOKEN, "Sketchfab"),
    ("tripo_api_key", session_credentials.TRIPO_API_KEY, "Tripo"),
    ("meshy_api_key", session_credentials.MESHY_API_KEY, "Meshy"),
    ("generation_endpoint_token", session_credentials.GENERATION_ENDPOINT_TOKEN, "Studio endpoint"),
)
REMEMBER_CREDENTIALS_ATTRIBUTE = "remember_api_keys"

# Assigning to a property from inside its own update callback re-enters that
# callback. Track which fields we are mid-scrub on rather than recursing.
_SCRUBBING = set()


def _blank_field(prefs, attribute):
    """Clear an entry field without re-entering its own update callback."""

    if not str(getattr(prefs, attribute, "") or ""):
        return
    _SCRUBBING.add(attribute)
    try:
        setattr(prefs, attribute, "")
    finally:
        _SCRUBBING.discard(attribute)


def _make_credential_update(attribute, credential):
    """Route a typed credential to memory, and to the OS store when asked.

    The preference field is only ever an entry box. Its value is moved out and
    the box blanked, so no credential is written to ``userpref.blend`` on any
    path -- "remember" means the operating system's credential store, never a
    plain-text preference.
    """

    def update(self, _context):
        if attribute in _SCRUBBING:
            return
        value = str(getattr(self, attribute, "") or "").strip()
        if not value:
            return
        session_credentials.set_session_credential(credential, value)
        if getattr(self, REMEMBER_CREDENTIALS_ATTRIBUTE, False):
            credential_store.store_credential(credential, value)
        _blank_field(self, attribute)

    return update


def _remember_credentials_update(self, _context):
    """Push held credentials into the OS store, or forget them there."""

    if REMEMBER_CREDENTIALS_ATTRIBUTE in _SCRUBBING:
        return
    if getattr(self, REMEMBER_CREDENTIALS_ATTRIBUTE, False):
        if not credential_store.is_available():
            # Nothing to fall back to that would still be safe, so the toggle
            # snaps back rather than quietly doing nothing.
            _SCRUBBING.add(REMEMBER_CREDENTIALS_ATTRIBUTE)
            try:
                setattr(self, REMEMBER_CREDENTIALS_ATTRIBUTE, False)
            finally:
                _SCRUBBING.discard(REMEMBER_CREDENTIALS_ATTRIBUTE)
            return
        for _attribute, credential, _label in CREDENTIAL_FIELDS:
            value = session_credentials.session_credential(credential)
            if value:
                credential_store.store_credential(credential, value)
        return
    # Switching off forgets what is on disk but leaves this session working.
    credential_store.forget_everything()


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
    triposr_mc_resolution: bpy.props.IntProperty(
        name="Marching Cubes Resolution",
        description="Default TripoSR extraction resolution; individual jobs may override it",
        default=256,
        min=16,
        max=512,
    )
    triposr_no_remove_bg: bpy.props.BoolProperty(
        name="Keep Input Background",
        description="Skip TripoSR background removal by default",
        default=False,
    )
    triposr_foreground_ratio: bpy.props.FloatProperty(
        name="Foreground Ratio",
        description="Default TripoSR foreground resize ratio after background removal",
        default=0.85,
        min=0.1,
        max=1.0,
    )
    triposr_chunk_size: bpy.props.IntProperty(
        name="Chunk Size",
        description="Default TripoSR evaluation chunk size; use 0 to disable chunking",
        default=8192,
        min=0,
        max=262144,
    )
    triposr_bake_texture: bpy.props.BoolProperty(
        name="Bake Texture",
        description="Bake a texture atlas by default when the TripoSR runtime supports it",
        default=False,
    )
    triposr_texture_resolution: bpy.props.IntProperty(
        name="Texture Resolution",
        description="Default TripoSR texture atlas resolution",
        default=2048,
        min=256,
        max=8192,
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
    # Credentials. Every one of these is held in memory for this Blender
    # session and the field blanks itself once entered, unless persistence is
    # switched on below. See CREDENTIAL_FIELDS for the single routing table.
    remember_api_keys: bpy.props.BoolProperty(
        name="Remember Keys On This Machine",
        description=(
            "Keep third-party provider keys in this computer's own credential store so "
            "they survive a restart. Encrypted by the OS against your user account where "
            "one is available, and never written to Blender preferences or .blend files. "
            "Switching it off erases them"
        ),
        default=True,
        update=_remember_credentials_update,
    )
    generation_endpoint_token: bpy.props.StringProperty(
        name="Endpoint Token",
        description="Optional bearer token for your self-hosted endpoint. Not a vendor key",
        subtype="PASSWORD",
        default="",
        update=_make_credential_update(
            "generation_endpoint_token", session_credentials.GENERATION_ENDPOINT_TOKEN
        ),
    )
    sketchfab_api_token: bpy.props.StringProperty(
        name="Sketchfab API Token",
        description="Token for downloading Sketchfab models. Held in memory unless you opt into saving",
        subtype="PASSWORD",
        default="",
        update=_make_credential_update("sketchfab_api_token", session_credentials.SKETCHFAB_API_TOKEN),
    )
    tripo_api_key: bpy.props.StringProperty(
        name="Tripo API Key",
        description="Key for Tripo image-to-3D. Held in memory unless you opt into saving",
        subtype="PASSWORD",
        default="",
        update=_make_credential_update("tripo_api_key", session_credentials.TRIPO_API_KEY),
    )
    meshy_api_key: bpy.props.StringProperty(
        name="Meshy API Key",
        description="Key for Meshy image-to-3D. Held in memory unless you opt into saving",
        subtype="PASSWORD",
        default="",
        update=_make_credential_update("meshy_api_key", session_credentials.MESHY_API_KEY),
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

        draw_generation_settings(layout.box(), self, title="Providers And Credentials")


def _draw_credential(layout, prefs, attribute, credential, label):
    """Draw one credential field and always say whether a key is set.

    The status line is not decoration. The entry field blanks itself the
    moment a key is accepted, so a set key and an unset one look identical --
    this line is the only thing that distinguishes them.
    """

    layout.prop(prefs, attribute)
    row = layout.row(align=True)
    if not session_credentials.session_credential(credential):
        row.label(text="%s: not set" % label, icon="RADIOBUT_OFF")
        return
    if getattr(prefs, REMEMBER_CREDENTIALS_ATTRIBUTE, False):
        row.label(text="%s: set, remembered on this machine" % label, icon="FILE_TICK")
    else:
        row.label(text="%s: set for this session" % label, icon="LOCKED")
    row.operator(
        "claude_blender.clear_session_credential", text="", icon="X"
    ).credential = credential


def draw_generation_settings(layout, prefs, *, title=""):
    """Lay out the generation and provider credential settings.

    Shared by the add-on preferences and the viewport sidebar so the two views
    cannot drift as providers are added. Grouped by what each field is *for*:
    as a flat list there was nothing to tell a user that the interpreter and
    endpoint fields have no bearing on the hosted providers below them.
    """

    if title:
        layout.label(text=title)

    local = layout.box()
    local.label(text="Run On Your Own Hardware", icon="DESKTOP")
    local.label(text="Optional. Leave blank to use hosted providers only.")
    local.prop(prefs, "generation_python")
    local.prop(prefs, "triposr_root")
    local.label(text="TripoSR Defaults")
    local.prop(prefs, "triposr_mc_resolution")
    local.prop(prefs, "triposr_no_remove_bg")
    local.prop(prefs, "triposr_foreground_ratio")
    local.prop(prefs, "triposr_chunk_size")
    local.prop(prefs, "triposr_bake_texture")
    local.prop(prefs, "triposr_texture_resolution")
    local.separator()
    local.prop(prefs, "generation_endpoint")
    _draw_credential(
        local,
        prefs,
        "generation_endpoint_token",
        session_credentials.GENERATION_ENDPOINT_TOKEN,
        "Endpoint token",
    )

    draw_credential_settings(layout.box(), prefs)


def draw_credential_settings(layout, prefs, *, title="Provider Credentials"):
    """One panel for every provider key, so no provider gets weaker handling."""

    if title:
        layout.label(text=title, icon="LOCKED")

    store = credential_store.describe()
    remember = layout.row()
    remember.enabled = bool(store["available"])
    remember.prop(prefs, REMEMBER_CREDENTIALS_ATTRIBUTE)
    if not store["available"]:
        layout.label(text="Nowhere safe to remember keys here; memory only.", icon="INFO")
    elif getattr(prefs, REMEMBER_CREDENTIALS_ATTRIBUTE, False):
        # Never call the permissions-only fallback encrypted.
        layout.label(
            text=store["label"], icon="CHECKMARK" if store["encrypted"] else "INFO"
        )
    else:
        layout.label(text="Keys stay in memory and clear when Blender closes.", icon="INFO")
    if store["remedy"]:
        layout.label(text=store["remedy"], icon="INFO")

    # Every key below is entered and stored the same way. They are split by
    # which direction data travels, because only one direction needs the
    # upload consent -- without the headings that split reads as arbitrary.
    layout.separator()
    layout.label(text="Download assets from", icon="IMPORT")
    _draw_credential(
        layout, prefs, "sketchfab_api_token", session_credentials.SKETCHFAB_API_TOKEN, "Sketchfab"
    )
    layout.label(text="Poly Haven needs no key: open API, every asset CC0.", icon="CHECKMARK")

    layout.separator()
    layout.label(text="Generate from your images with", icon="EXPORT")
    layout.label(text="These send your reference images to the vendor.")
    layout.prop(prefs, "generation_egress_allowed")
    hosted = layout.column()
    hosted.enabled = bool(prefs.generation_egress_allowed)
    _draw_credential(hosted, prefs, "tripo_api_key", session_credentials.TRIPO_API_KEY, "Tripo")
    _draw_credential(hosted, prefs, "meshy_api_key", session_credentials.MESHY_API_KEY, "Meshy")
    if not prefs.generation_egress_allowed:
        layout.label(text="Hosted generation stays disabled until uploads are allowed.", icon="INFO")


def draw_generation_summary(layout, prefs):
    """Read-only readiness for the viewport sidebar.

    Setup lives in Preferences, not here. Entering a key is a once-ever task
    now that it is remembered, while this panel is on screen for the whole
    session -- including during screen shares, tutorials, and streams. A
    credential field in the viewport is an exposure waiting to happen, and it
    buys nothing a status line and a button do not.
    """

    held = [
        label
        for _attribute, credential, label in CREDENTIAL_FIELDS
        if session_credentials.session_credential(credential)
    ]
    if held:
        layout.label(text="Keys: %s" % ", ".join(held), icon="LOCKED")
    else:
        layout.label(text="No provider keys entered yet.", icon="INFO")

    if str(getattr(prefs, "generation_endpoint", "") or "").strip():
        layout.label(text="Studio endpoint configured.", icon="CHECKMARK")
    elif str(getattr(prefs, "generation_python", "") or "").strip():
        layout.label(text="Local generation interpreter set.", icon="CHECKMARK")
    else:
        layout.label(text="No local generation configured.", icon="INFO")

    if not getattr(prefs, "generation_egress_allowed", False):
        layout.label(text="Third-party uploads are off.", icon="INFO")

    layout.operator("claude_blender.open_generation_preferences", icon="PREFERENCES")


def seed_session_credentials(prefs):
    """Populate the session store at startup, and migrate off plain text.

    Earlier builds wrote generation keys straight into ``userpref.blend``. Any
    such value is moved into memory (and into the OS store when the user has
    asked to be remembered) and the preference blanked, so upgrading clears
    the plain-text copy rather than leaving it behind.
    """

    seeded = list(credential_store.load_into_session())
    if prefs is None:
        return seeded
    remember = bool(getattr(prefs, REMEMBER_CREDENTIALS_ATTRIBUTE, False))
    for attribute, credential, _label in CREDENTIAL_FIELDS:
        value = str(getattr(prefs, attribute, "") or "").strip()
        if not value:
            continue
        session_credentials.set_session_credential(credential, value)
        if remember:
            credential_store.store_credential(credential, value)
        _blank_field(prefs, attribute)
        if credential not in seeded:
            seeded.append(credential)
    return seeded


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
    try:
        seed_session_credentials(get_preferences(bpy.context))
    except (AttributeError, KeyError, RuntimeError):
        # Preferences are not always reachable this early during startup. The
        # store simply stays empty and the preference fallback still applies.
        pass


def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
