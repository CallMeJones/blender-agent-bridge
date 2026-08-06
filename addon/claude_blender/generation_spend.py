"""Human approval for generation jobs that cost money.

An agent argument is not consent. The previous gate asked the caller to pass
``confirm_paid`` after telling the user the cost, and that was bypassable in
the most ordinary way possible: call, read the refusal, call again with the
flag set, never showing the user anything. The bridge cannot see the
conversation, so no argument it receives can prove a human agreed.

What it can require is an action only a human at the keyboard can perform.
This module holds spend requests that must be approved in Blender's own UI
before a paid job starts -- the same shape as the existing script-trust
window, which is already the project's answer to "an agent cannot grant
itself a permission".

Approvals are single-use and bound to the exact job. Approving a Tripo job
for one image does not authorise a second job, a different image, or a
different provider.

Free routes never reach this module. Nothing here can be set by a tool call.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid

# Long enough to walk to Blender and read the request, short enough that an
# approval cannot sit around authorising a job the user has forgotten about.
APPROVAL_TTL_SECONDS = 600

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_DENIED = "denied"
STATUS_EXPIRED = "expired"
STATUS_SPENT = "spent"

_LOCK = threading.RLock()
_REQUESTS = {}


def job_fingerprint(provider, args):
    """Identify one specific job, so approval cannot be reused for another."""

    views = (args or {}).get("views") or {}
    payload = {
        "provider": str(provider or "").strip().lower(),
        "views": {str(name): str(path) for name, path in sorted(views.items())},
        "model": str((args or {}).get("model") or ""),
        "face_limit": int((args or {}).get("face_limit") or 0),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _expire_locked(now):
    for record in _REQUESTS.values():
        if record["status"] == STATUS_PENDING and now > record["expires_at"]:
            record["status"] = STATUS_EXPIRED


def request_approval(provider, fingerprint, *, cost_note="", view_count=1, title=""):
    """Record a pending request, or return the live one for this same job."""

    now = time.time()
    with _LOCK:
        _expire_locked(now)
        for record in _REQUESTS.values():
            if record["fingerprint"] == fingerprint and record["status"] in (
                STATUS_PENDING,
                STATUS_APPROVED,
            ):
                return dict(record)
        request_id = uuid.uuid4().hex[:12]
        record = {
            "request_id": request_id,
            "provider": str(provider or ""),
            "title": str(title or provider or ""),
            "fingerprint": fingerprint,
            "cost_note": str(cost_note or ""),
            "view_count": int(view_count),
            "status": STATUS_PENDING,
            "created_at": now,
            "expires_at": now + APPROVAL_TTL_SECONDS,
        }
        _REQUESTS[request_id] = record
        return dict(record)


def approval_state(fingerprint):
    """Where this exact job stands. Returns None when never requested."""

    now = time.time()
    with _LOCK:
        _expire_locked(now)
        matches = [r for r in _REQUESTS.values() if r["fingerprint"] == fingerprint]
        if not matches:
            return None
        for status in (STATUS_APPROVED, STATUS_PENDING, STATUS_DENIED, STATUS_SPENT):
            for record in matches:
                if record["status"] == status:
                    return dict(record)
        return dict(matches[-1])


def consume_approval(fingerprint):
    """Spend an approval. Returns True only if one was live and unused."""

    now = time.time()
    with _LOCK:
        _expire_locked(now)
        for record in _REQUESTS.values():
            if record["fingerprint"] == fingerprint and record["status"] == STATUS_APPROVED:
                record["status"] = STATUS_SPENT
                record["spent_at"] = now
                return True
        return False


def set_status(request_id, status):
    """Approve or deny. Called only from the Blender UI operators."""

    if status not in (STATUS_APPROVED, STATUS_DENIED):
        raise ValueError("Spend requests may only be approved or denied")
    with _LOCK:
        record = _REQUESTS.get(str(request_id or ""))
        if record is None:
            return None
        if record["status"] != STATUS_PENDING:
            return dict(record)
        record["status"] = status
        record["decided_at"] = time.time()
        return dict(record)


def pending_requests():
    """Live requests awaiting a decision, oldest first."""

    now = time.time()
    with _LOCK:
        _expire_locked(now)
        return sorted(
            (dict(r) for r in _REQUESTS.values() if r["status"] == STATUS_PENDING),
            key=lambda record: record["created_at"],
        )


def clear_requests():
    with _LOCK:
        _REQUESTS.clear()
