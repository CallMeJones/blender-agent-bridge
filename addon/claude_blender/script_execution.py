"""Pure policy for reporting trusted Blender Python execution outcomes."""

from __future__ import annotations


AUTHORIZATION_MODEL = "blender_run_script_equivalent"
ACTIVE_TRUST_REASON = "external_script_trust_active"
TRUST_REQUIRED_REASON = "external_script_trust_required"
NOT_ATTEMPTED_REASON = "not_attempted"


def status_fields(run_result):
    """Return the canonical public status fields for a trusted-script result."""

    result = run_result if isinstance(run_result, dict) else {}
    attempted = bool(result.get("auto_run_attempted"))
    code = str(result.get("code") or "")
    if attempted:
        reason = ACTIVE_TRUST_REASON
    elif code == "script_trust_required":
        reason = TRUST_REQUIRED_REASON
    elif code:
        reason = code
    else:
        reason = NOT_ATTEMPTED_REASON
    return {
        "auto_ran": bool(result.get("auto_ran")),
        "auto_run_attempted": attempted,
        "auto_run_reason": reason,
        "auto_run_skipped_reason": "" if attempted else (code or NOT_ATTEMPTED_REASON),
        "authorization_model": AUTHORIZATION_MODEL,
    }
