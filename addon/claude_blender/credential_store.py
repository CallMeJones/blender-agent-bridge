"""Durable credential storage backed by the operating system.

The problem this solves: a user should not re-paste an API key every time
Blender starts, and the key must not sit in ``userpref.blend``, which is
unencrypted and travels with a copied configuration.

Encrypting the value with a key kept beside it would be obfuscation rather
than security -- whoever can read one can read the other. So the secret is
handed to the facility the operating system already provides for exactly this,
the same one the AWS and GitHub CLIs use:

Windows
    DPAPI (``CryptProtectData``). The ciphertext is bound to the Windows user
    account, so a copied file is useless on another machine or under another
    account. Reached through ``ctypes``; nothing to install.
macOS
    The login keychain, through the bundled ``security`` tool.
Linux
    The Secret Service API, through ``secret-tool`` when libsecret is present.

Where no backend is available the store reports itself unavailable and the
caller falls back to memory-only credentials. Nothing is ever written in the
clear, on any platform, including as a fallback.

Only Windows is exercised by the test suite on this project; the other two
backends are guarded so an absent tool degrades to unavailable rather than
raising.
"""

from __future__ import annotations

import base64
import os
import platform
import subprocess
import sys

try:
    from . import session_credentials, user_paths
except ImportError:  # Direct-script compatibility inside Blender.
    import session_credentials
    import user_paths

SERVICE_NAME = "blender-agent-bridge"

# Mixed into the DPAPI ciphertext so a blob produced by another application
# cannot be dropped in and decrypted as one of ours.
_DPAPI_ENTROPY = b"blender-agent-bridge/credential-store/v1"

BACKEND_NONE = "none"
BACKEND_WINDOWS_DPAPI = "windows_dpapi"
BACKEND_MACOS_KEYCHAIN = "macos_keychain"
BACKEND_LINUX_SECRET_SERVICE = "linux_secret_service"
BACKEND_RESTRICTED_FILE = "restricted_file"

BACKEND_LABELS = {
    BACKEND_NONE: "No credential store available",
    BACKEND_WINDOWS_DPAPI: "Encrypted by Windows (DPAPI)",
    BACKEND_MACOS_KEYCHAIN: "macOS login keychain",
    BACKEND_LINUX_SECRET_SERVICE: "Linux Secret Service (libsecret)",
    BACKEND_RESTRICTED_FILE: "File readable only by your user account",
}

# Whether the stored bytes are meaningless to anyone who reads them. The
# restricted-file backend is the honest exception and must never be described
# as encrypted -- it relies on file permissions alone.
BACKEND_ENCRYPTED = {
    BACKEND_WINDOWS_DPAPI: True,
    BACKEND_MACOS_KEYCHAIN: True,
    BACKEND_LINUX_SECRET_SERVICE: True,
    BACKEND_RESTRICTED_FILE: False,
    BACKEND_NONE: False,
}

# Used to prove a backend actually works before it is selected. A tool that is
# installed but cannot reach its daemon -- the normal case on a headless Linux
# render node -- must not be chosen and then fail on first use.
_PROBE_ACCOUNT = "blender-agent-bridge-probe"
_PROBE_VALUE = "probe"

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _validated(name):
    """Reject any name outside the known credential set."""

    return session_credentials.canonical_name(name)


# --------------------------------------------------------------------------
# Windows: DPAPI
# --------------------------------------------------------------------------


def _dpapi():
    """Return the crypt32 handle, or None when unusable."""

    if sys.platform != "win32":
        return None
    try:
        import ctypes
        import ctypes.wintypes
    except ImportError:
        return None
    try:
        return ctypes.WinDLL("crypt32")
    except (OSError, AttributeError):
        return None


def _dpapi_blob_types():
    import ctypes
    import ctypes.wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", ctypes.wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    return ctypes, DATA_BLOB


def _dpapi_in_blob(ctypes_module, blob_type, payload):
    buffer = ctypes_module.create_string_buffer(payload, len(payload))
    return blob_type(
        len(payload), ctypes_module.cast(buffer, ctypes_module.POINTER(ctypes_module.c_char))
    ), buffer


def _dpapi_transform(function_name, payload):
    crypt32 = _dpapi()
    if crypt32 is None or not payload:
        return b""
    ctypes_module, blob_type = _dpapi_blob_types()
    source, _keepalive = _dpapi_in_blob(ctypes_module, blob_type, payload)
    entropy, _entropy_keepalive = _dpapi_in_blob(ctypes_module, blob_type, _DPAPI_ENTROPY)
    result = blob_type()
    function = getattr(crypt32, function_name)
    ok = function(
        ctypes_module.byref(source),
        None,
        ctypes_module.byref(entropy),
        None,
        None,
        0,
        ctypes_module.byref(result),
    )
    if not ok:
        return b""
    try:
        return ctypes_module.string_at(result.pbData, result.cbData)
    finally:
        # The blob is allocated by the API; failing to free it leaks the
        # decrypted secret into the process heap for the session.
        try:
            ctypes_module.WinDLL("kernel32").LocalFree(result.pbData)
        except (OSError, AttributeError):
            pass


def _credential_path(name):
    return os.path.join(user_paths.user_data_dir("credentials"), "%s.dpapi" % name)


def _windows_store(name, value):
    ciphertext = _dpapi_transform("CryptProtectData", value.encode("utf-8"))
    if not ciphertext:
        return False
    path = _credential_path(name)
    with open(path, "wb") as handle:
        handle.write(base64.b64encode(ciphertext))
    return True


def _windows_load(name):
    path = _credential_path(name)
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "rb") as handle:
            ciphertext = base64.b64decode(handle.read())
    except (OSError, ValueError):
        return ""
    plaintext = _dpapi_transform("CryptUnprotectData", ciphertext)
    return plaintext.decode("utf-8", "replace") if plaintext else ""


def _windows_delete(name):
    path = _credential_path(name)
    if not os.path.isfile(path):
        return False
    try:
        os.remove(path)
    except OSError:
        return False
    return True


# --------------------------------------------------------------------------
# macOS and Linux: the platform's own secret tooling
# --------------------------------------------------------------------------


def _run(command, *, stdin_text=None):
    try:
        completed = subprocess.run(
            command,
            input=stdin_text.encode("utf-8") if stdin_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=None if stdin_text is not None else subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed


def _tool_present(executable):
    completed = _run([executable, "--version"])
    if completed is None:
        return False
    # `security` has no --version and exits non-zero; reaching the process at
    # all is what matters.
    return True


def _macos_store(name, value):
    # The value appears in this process's argv, which is briefly visible to
    # other processes owned by the same user. `security` offers no stdin path
    # for a non-interactive write; the exposure is local and momentary.
    completed = _run(
        [
            "security", "add-generic-password", "-U",
            "-s", SERVICE_NAME, "-a", name, "-w", value,
        ]
    )
    return bool(completed and completed.returncode == 0)


def _macos_load(name):
    completed = _run(
        ["security", "find-generic-password", "-s", SERVICE_NAME, "-a", name, "-w"]
    )
    if not completed or completed.returncode != 0:
        return ""
    return completed.stdout.decode("utf-8", "replace").strip()


def _macos_delete(name):
    completed = _run(
        ["security", "delete-generic-password", "-s", SERVICE_NAME, "-a", name]
    )
    return bool(completed and completed.returncode == 0)


def _linux_store(name, value):
    completed = _run(
        [
            "secret-tool", "store", "--label=Blender Agent Bridge",
            "service", SERVICE_NAME, "account", name,
        ],
        stdin_text=value,
    )
    return bool(completed and completed.returncode == 0)


def _linux_load(name):
    completed = _run(["secret-tool", "lookup", "service", SERVICE_NAME, "account", name])
    if not completed or completed.returncode != 0:
        return ""
    return completed.stdout.decode("utf-8", "replace").strip()


def _linux_delete(name):
    completed = _run(["secret-tool", "clear", "service", SERVICE_NAME, "account", name])
    return bool(completed and completed.returncode == 0)


# --------------------------------------------------------------------------
# Last resort: a file only the owning user account can read
# --------------------------------------------------------------------------
#
# Blender runs on machines with no keychain daemon at all -- headless Linux
# render nodes are the common case. Refusing to remember anything there would
# mean re-pasting a key on every start, so the credential falls back to the
# same mechanism ``~/.aws/credentials`` and ``~/.netrc`` use: an ordinary file
# with owner-only permissions. This is weaker, it is not encryption, and the
# panel says so in those words rather than implying protection it lacks.


def _restricted_path(name):
    return os.path.join(user_paths.user_data_dir("credentials"), "%s.key" % name)


def _restricted_store(name, value):
    path = _restricted_path(name)
    try:
        # Created with 0600 from the outset; writing first and chmod-ing after
        # would leave a readable window.
        descriptor = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        try:
            os.write(descriptor, value.encode("utf-8"))
        finally:
            os.close(descriptor)
        os.chmod(path, 0o600)
    except OSError:
        return False
    return True


def _restricted_load(name):
    path = _restricted_path(name)
    if not os.path.isfile(path):
        return ""
    try:
        # A file that became group or world readable is treated as spent: the
        # value may already have been seen, so it is removed rather than used.
        if os.name == "posix" and (os.stat(path).st_mode & 0o077):
            os.remove(path)
            return ""
        with open(path, "rb") as handle:
            return handle.read().decode("utf-8", "replace").strip()
    except OSError:
        return ""


def _restricted_delete(name):
    path = _restricted_path(name)
    if not os.path.isfile(path):
        return False
    try:
        os.remove(path)
    except OSError:
        return False
    return True


# --------------------------------------------------------------------------
# Backend selection
# --------------------------------------------------------------------------

_BACKENDS = {
    BACKEND_WINDOWS_DPAPI: (_windows_store, _windows_load, _windows_delete),
    BACKEND_MACOS_KEYCHAIN: (_macos_store, _macos_load, _macos_delete),
    BACKEND_LINUX_SECRET_SERVICE: (_linux_store, _linux_load, _linux_delete),
    BACKEND_RESTRICTED_FILE: (_restricted_store, _restricted_load, _restricted_delete),
}

_BACKEND_OVERRIDE = None
_DETECTED = None


def set_backend_override(backend):
    """Pin the backend. For tests only; None restores detection."""

    global _BACKEND_OVERRIDE
    _BACKEND_OVERRIDE = backend
    clear_backend_cache()


def clear_backend_cache():
    """Force the next call to re-detect. Detection probes the OS, so it is cached."""

    global _DETECTED
    _DETECTED = None


def _probe(backend):
    """Prove a backend round-trips before trusting it with a real credential."""

    store, load, delete = _BACKENDS[backend]
    try:
        if not store(_PROBE_ACCOUNT, _PROBE_VALUE):
            return False
        ok = load(_PROBE_ACCOUNT) == _PROBE_VALUE
    except Exception:  # noqa: BLE001 - a broken backend must not break startup
        return False
    finally:
        try:
            delete(_PROBE_ACCOUNT)
        except Exception:  # noqa: BLE001
            pass
    return ok


def _detect_backend():
    if sys.platform == "win32":
        # Probed in memory: a DPAPI round-trip needs no file and no daemon.
        if _dpapi() is not None and _dpapi_transform(
            "CryptUnprotectData", _dpapi_transform("CryptProtectData", b"probe")
        ) == b"probe":
            return BACKEND_WINDOWS_DPAPI
    elif sys.platform == "darwin":
        if _tool_present("security") and _probe(BACKEND_MACOS_KEYCHAIN):
            return BACKEND_MACOS_KEYCHAIN
    elif _tool_present("secret-tool") and _probe(BACKEND_LINUX_SECRET_SERVICE):
        return BACKEND_LINUX_SECRET_SERVICE
    # Every remaining platform Blender supports still gets persistence, just
    # with permissions instead of encryption.
    if _probe(BACKEND_RESTRICTED_FILE):
        return BACKEND_RESTRICTED_FILE
    return BACKEND_NONE


def backend_name():
    """Which storage facility will be used, or ``none``."""

    global _DETECTED
    if _BACKEND_OVERRIDE is not None:
        return _BACKEND_OVERRIDE
    if _DETECTED is None:
        _DETECTED = _detect_backend()
    return _DETECTED


def is_available():
    return backend_name() != BACKEND_NONE


def is_encrypted():
    """Whether the stored bytes are useless to whoever reads them."""

    return bool(BACKEND_ENCRYPTED.get(backend_name(), False))


def describe():
    """Report the backend without exposing any stored value."""

    name = backend_name()
    if name == BACKEND_NONE:
        remedy = "Keys stay in memory only; set an environment variable to avoid re-entry."
    elif name == BACKEND_RESTRICTED_FILE:
        remedy = (
            "Install libsecret (secret-tool) for an encrypted store."
            if sys.platform not in ("win32", "darwin")
            else ""
        )
    else:
        remedy = ""
    return {
        "backend": name,
        "available": name != BACKEND_NONE,
        "encrypted": is_encrypted(),
        "label": BACKEND_LABELS.get(name, name),
        "platform": platform.system(),
        "stored_credentials": stored_credential_names(),
        "remedy": remedy,
    }


def store_credential(name, value):
    """Persist a credential in the OS store. Empty value deletes it."""

    name = _validated(name)
    value = str(value or "").strip()
    if not value:
        return delete_credential(name)
    backend = _BACKENDS.get(backend_name())
    if backend is None:
        return False
    return bool(backend[0](name, value))


def load_credential(name):
    name = _validated(name)
    backend = _BACKENDS.get(backend_name())
    if backend is None:
        return ""
    return str(backend[1](name) or "")


def delete_credential(name):
    name = _validated(name)
    backend = _BACKENDS.get(backend_name())
    if backend is None:
        return False
    return bool(backend[2](name))


def stored_credential_names():
    """Names with a value in the OS store. Never returns a value."""

    if not is_available():
        return []
    return [name for name in session_credentials.CREDENTIAL_NAMES if load_credential(name)]


def load_into_session():
    """Seed the in-memory store from the OS store at startup.

    The session store stays the single read path for every provider, so
    remembered credentials are pulled through it rather than adding a second
    lookup everywhere.
    """

    loaded = []
    if not is_available():
        return loaded
    for name in session_credentials.CREDENTIAL_NAMES:
        value = load_credential(name)
        if value:
            session_credentials.set_session_credential(name, value)
            loaded.append(name)
    return loaded


def forget_everything():
    """Remove every stored credential from the OS store."""

    return [name for name in session_credentials.CREDENTIAL_NAMES if delete_credential(name)]
