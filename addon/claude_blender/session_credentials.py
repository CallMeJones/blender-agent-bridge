"""Process-scoped credential store.

Credentials the bridge needs live here by default: in this Blender process, in
memory, gone when Blender closes. Writing one to ``userpref.blend`` is an
explicit opt-in, because that file is unencrypted, travels between machines
with a user's configuration, and outlives the work that needed the credential.

Sketchfab already worked this way. Generation providers arrived later and wrote
their keys straight to preferences, which left two policies for one class of
secret with the newer one weaker. This module is the single policy both use.

Deliberately free of ``bpy`` so the policy is testable directly rather than
through a copy, and so the job worker can import it.
"""

from __future__ import annotations

import threading

SKETCHFAB_API_TOKEN = "sketchfab_api_token"
TRIPO_API_KEY = "tripo_api_key"
MESHY_API_KEY = "meshy_api_key"
GENERATION_ENDPOINT_TOKEN = "generation_endpoint_token"

# Every credential the store will hold. Unknown names raise rather than being
# stored, so a typo cannot leave a live secret sitting under a name nothing
# ever reads back.
CREDENTIAL_NAMES = (
    SKETCHFAB_API_TOKEN,
    TRIPO_API_KEY,
    MESHY_API_KEY,
    GENERATION_ENDPOINT_TOKEN,
)

_LOCK = threading.RLock()
_STORE = {}


class UnknownCredentialError(KeyError):
    """Raised for a credential name outside :data:`CREDENTIAL_NAMES`."""


def canonical_name(name):
    """Normalise a credential name, refusing anything outside the known set."""

    key = str(name or "").strip().lower()
    if key not in CREDENTIAL_NAMES:
        raise UnknownCredentialError(
            "Unknown credential %r; known names are %s" % (name, ", ".join(CREDENTIAL_NAMES))
        )
    return key


_canonical = canonical_name


def set_session_credential(name, value):
    """Hold ``value`` for this process only. An empty value clears the slot."""

    key = _canonical(name)
    value = str(value or "").strip()
    with _LOCK:
        if value:
            _STORE[key] = value
        else:
            _STORE.pop(key, None)
    return bool(value)


def session_credential(name):
    """Return the held value, or an empty string when nothing is held."""

    with _LOCK:
        return _STORE.get(_canonical(name), "")


def clear_session_credential(name):
    """Forget one credential. Returns whether anything was held."""

    with _LOCK:
        return bool(_STORE.pop(_canonical(name), ""))


def clear_session_credentials():
    """Forget every credential. Returns how many were held."""

    with _LOCK:
        count = len(_STORE)
        _STORE.clear()
        return count


def configured_session_credentials():
    """Names currently held, sorted. Never returns a value."""

    with _LOCK:
        return sorted(_STORE)


def session_credential_status():
    """Report which credentials are held without exposing any value.

    Safe to put in diagnostics, manifests, and audit logs.
    """

    held = set(configured_session_credentials())
    return {name: (name in held) for name in CREDENTIAL_NAMES}
