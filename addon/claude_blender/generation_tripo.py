"""Tripo request and pricing policy shared by approval, workers, and clients."""

from __future__ import annotations


DEFAULT_MODEL = "v3.1-20260211"
MODELS = ("P1-20260311", "v3.1-20260211", "v3.0-20250812", "v2.5-20250123")
PRICING_VERSION = "tripo-api-2026-06-03"


def normalize_job_options(args):
    args = args if isinstance(args, dict) else {}
    model = str(args.get("model") or DEFAULT_MODEL).strip()
    if model not in MODELS:
        raise ValueError("Unknown Tripo model %r; allowed values: %s" % (model, ", ".join(MODELS)))
    try:
        face_limit = int(args.get("face_limit") or 0)
    except (TypeError, ValueError):
        raise ValueError("Tripo face_limit must be an integer") from None
    if face_limit < 0 or face_limit > 1000000:
        raise ValueError("Tripo face_limit must be between 0 and 1000000")
    if model == "P1-20260311" and face_limit and not 48 <= face_limit <= 20000:
        raise ValueError("Tripo P1 face_limit must be between 48 and 20000")
    texture = bool(args.get("texture")) if "texture" in args else True
    return {"model": model, "face_limit": face_limit, "texture": texture}


def estimated_credits(options):
    p1 = options["model"] == "P1-20260311"
    if p1:
        return 50.0 if options["texture"] else 40.0
    return 30.0 if options["texture"] else 20.0


def resolve_job_policy(args):
    options = normalize_job_options(args)
    credits = estimated_credits(options)
    texture = "standard texture" if options["texture"] else "untextured"
    return {
        "options": options,
        "estimated_credits": credits,
        "pricing_version": PRICING_VERSION,
        "cost_note": "%d Tripo credits: %s, %s."
        % (int(credits), options["model"], texture),
    }
