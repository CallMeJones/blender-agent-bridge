"""Handlers for the image-to-3D generation domain.

Credentials and machine paths come from add-on preferences because these
handlers run inside Blender and never see the MCP server process environment.
Generation jobs reuse the external-asset job machinery so they inherit the
subprocess worker, cancel, restart recovery, and the whole cache/import tail.
"""

from __future__ import annotations

import os

from .. import asset_jobs, generation_providers, generation_spend, preferences
from .support import _bounded_int


def _generation_environ(context):
    prefs = preferences.get_preferences(context)
    environ = dict(os.environ)
    environ.update(generation_providers.environment_overlay(prefs))
    return environ


def get_generation_provider_diagnostics(context, args):
    environ = _generation_environ(context)
    # The probe result is cached per interpreter, so the default path costs
    # nothing after the first call; refresh_hardware forces a re-probe when a
    # user has just installed torch or switched interpreters.
    hardware = generation_providers.probe_hardware(
        python_executable=str(args.get("probe_python") or ""),
        environ=environ,
        use_cache=not bool(args.get("refresh_hardware", False)),
    )
    report = generation_providers.generation_provider_diagnostics(
        environ=environ, hardware=hardware
    )
    report["credential_source"] = "addon_preferences_over_environment"
    report["ok"] = True
    return report


def plan_image_to_3d_approach(context, args):
    """List every route from a reference image to a model, for the user to pick.

    Exists because the alternative is an agent quietly choosing on the user's
    behalf. The routes differ in ways only the user can weigh -- money, whether
    their artwork leaves the machine, how long it takes, and how editable the
    result is -- so this returns the options and refuses to rank them.
    """

    environ = _generation_environ(context)
    hardware = generation_providers.probe_hardware(environ=environ)
    diagnostics = generation_providers.generation_provider_diagnostics(
        environ=environ, hardware=hardware
    )
    by_name = {item["provider"]: item for item in diagnostics["providers"]}

    routes = [
        {
            "id": "authored",
            "title": "Author it in Blender",
            "how": "Bounded helpers and trusted scripts build the mesh from reference guides.",
            "cost": "Free.",
            "data_leaves_machine": False,
            "ready": True,
            "produces": "Clean, editable topology you own from the first vertex.",
            "effort": "Slowest. Best when the model must be rigged, edited, or matched precisely.",
        }
    ]
    for spec in generation_providers.PROVIDER_SPECS:
        report = by_name.get(spec.name) or {}
        hosted = spec.kind == generation_providers.KIND_HOSTED_API
        routes.append(
            {
                "id": spec.name,
                "title": spec.title,
                "how": (
                    "Uploads the reference images to a third-party service."
                    if hosted
                    else "Runs the model on hardware you control."
                ),
                "cost": spec.cost_note or "Free; uses your own compute.",
                "data_leaves_machine": bool(spec.requires_egress),
                "ready": bool(report.get("runnable")),
                "why_not_ready": str(report.get("run_blocker") or ""),
                "produces": "A generated mesh, typically dense and not rig-ready.",
                "blockers": report.get("blockers") or [],
                "remedies": report.get("remedies") or [],
                "license_note": spec.license_note,
            }
        )

    policy = generation_providers.session_generation_policy()
    for route in routes:
        if route["id"] == "authored":
            continue
        forbidden = generation_providers.policy_refusal(route["id"])
        if forbidden:
            route["ready"] = False
            route["why_not_ready"] = forbidden

    ready = [route for route in routes if route["ready"]]
    paid_ready = [route for route in ready if route["id"] != "authored" and route["data_leaves_machine"]]
    return {
        "ok": True,
        "requires_user_choice": True,
        "message": (
            "Several routes can build this. They differ in cost and in whether the "
            "reference images leave the machine, so the user chooses -- do not pick one "
            "for them, and do not start work on any route before they answer."
        ),
        "question": (
            "How would you like this built? %s"
            % " | ".join("%s (%s)" % (route["title"], route["cost"]) for route in ready)
        ),
        "routes": routes,
        "ready_routes": [route["id"] for route in ready],
        "paid_routes": [route["id"] for route in paid_ready],
        "generation_policy": policy,
        "note": (
            "Starting a paid route still needs confirm_paid on start_generation_job, so "
            "asking here is the first of two checks, not a replacement for it."
        ),
    }


def set_generation_policy(context, args):
    """Record a standing instruction about how work may be done this session."""

    policy = str(args.get("policy") or "").strip().lower()
    try:
        recorded = generation_providers.set_session_generation_policy(
            policy, reason=str(args.get("reason") or "")
        )
    except ValueError as error:
        return {
            "ok": False,
            "message": str(error),
            "known_policies": list(generation_providers.GENERATION_POLICIES),
        }
    return {
        "ok": True,
        "message": "Standing instruction recorded for this Blender session. %s"
        % generation_providers.POLICY_LABELS[recorded["policy"]],
        "generation_policy": recorded,
        "note": (
            "Enforced in the bridge, so it holds for the rest of the session even after "
            "it leaves your context. Only the user can relax it."
        ),
    }


def start_generation_job(context, args):
    environ = _generation_environ(context)

    views = {
        str(name): str(path)
        for name, path in (args.get("views") or {}).items()
        if str(path or "").strip()
    }
    if not views:
        return {"ok": False, "message": "views must map at least one view name to an image path"}

    missing = [path for path in views.values() if not os.path.isfile(path)]
    if missing:
        return {
            "ok": False,
            "message": "Reference image not found: %s" % missing[0],
            "hint": "Supply local paths the user confirmed; the bridge does not invent paths.",
        }

    selection = generation_providers.select_provider(
        preferred=str(args.get("provider") or ""),
        environ=environ,
        hardware=generation_providers.probe_hardware(environ=environ),
        require_multiview=len(views) > 1,
    )
    if not selection.get("ok"):
        # Hand back the full diagnostics so the caller can fix the deployment
        # rather than guess which of several conditions failed.
        return {
            "ok": False,
            "message": selection.get("message") or "No generation provider is available",
            "diagnostics": selection.get("diagnostics"),
        }

    provider = selection["selected"]

    # A standing instruction outranks everything below it, including an
    # explicit confirm_paid. If the user said "no APIs, just scripts" an hour
    # ago, that is still true now whether or not it is still in context.
    refusal = generation_providers.policy_refusal(provider)
    if refusal:
        return {
            "ok": False,
            "message": "Refused by the user's standing instruction for this session. %s" % refusal,
            "provider": provider,
            "generation_policy": generation_providers.session_generation_policy(),
            "hint": "Build it with authored scripts and bounded helpers instead.",
        }

    # Spending the user's money requires the user. An argument cannot carry
    # consent: the bridge never sees the conversation, so any flag a caller
    # passes is just the caller asserting it asked. The approval below has to
    # be given in Blender's own UI, which no tool call can reach -- the same
    # reasoning as the script-trust window.
    if generation_providers.is_paid_provider(provider):
        notice = generation_providers.paid_provider_notice(provider)
        fingerprint = generation_spend.job_fingerprint(provider, args)
        state = generation_spend.approval_state(fingerprint)
        status = (state or {}).get("status")

        if status != generation_spend.STATUS_APPROVED:
            if status == generation_spend.STATUS_DENIED:
                return {
                    "ok": False,
                    "spend_approval": state,
                    "message": (
                        "The user declined this paid job in Blender. Do not ask again for "
                        "the same job; offer a free route or a different approach."
                    ),
                }
            request = generation_spend.request_approval(
                provider,
                fingerprint,
                cost_note=notice.get("cost_note") or "",
                view_count=len(views),
                title=notice.get("title") or provider,
            )
            expired = status == generation_spend.STATUS_EXPIRED
            return {
                "ok": False,
                "awaiting_user_approval": True,
                "spend_approval": request,
                "message": (
                    "%s costs money and cannot start until the user approves it in Blender. "
                    "%s Tell them the cost, then ask them to click Approve on the pending "
                    "request in the Agent Bridge sidebar. Call this tool again with the same "
                    "arguments once they have; there is no argument that skips this."
                    % (
                        notice.get("title") or provider,
                        ("The earlier request expired. " if expired else "")
                        + (notice.get("cost_note") or ""),
                    )
                ).strip(),
                "cost": notice,
                "free_alternative": (
                    "Authoring the model in Blender costs nothing and uploads nothing."
                ),
            }

        if not generation_spend.consume_approval(fingerprint):
            return {
                "ok": False,
                "message": "That spend approval was already used. Ask the user to approve again.",
                "spend_approval": generation_spend.approval_state(fingerprint),
            }

    if provider not in asset_jobs.JOB_PROVIDER_SPECS:
        return {
            "ok": False,
            "message": "Provider %s is available but has no job implementation yet" % provider,
            "implemented_providers": [
                name for name in asset_jobs.JOB_PROVIDER_NAMES if name not in ("poly_haven", "sketchfab")
            ],
        }

    api_key = ""
    for name in generation_providers.PROVIDERS_BY_NAME[provider].credential_env_vars:
        api_key = str(environ.get(name, "") or "").strip()
        if api_key:
            break

    prefs = preferences.get_preferences(context)
    return asset_jobs.start_external_asset_download(
        context,
        provider=provider,
        job_name=str(args.get("job_name") or "generation"),
        note=str(args.get("note") or ""),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
        views=views,
        api_key=api_key,
        model=str(args.get("model") or ""),
        face_limit=_bounded_int(args.get("face_limit"), 0, minimum=0, maximum=1000000),
        cache_dir=str(args.get("cache_dir") or ""),
        timeout=_bounded_int(args.get("timeout"), 120, minimum=1, maximum=300),
    )


def get_generation_job_status(context, args):
    prefs = preferences.get_preferences(context)
    job = asset_jobs.external_asset_job_status(
        str(args.get("job_id") or ""),
        context=context,
        preferred_dir=getattr(prefs, "capture_cache_dir", None),
    )
    return {
        "ok": bool(job.get("available", False)),
        "message": "Generation job status collected" if job.get("available") else job.get("message", "Generation job was not found"),
        "asset_job": job,
    }


def register(handler_registry, specs):
    for spec in specs:
        try:
            handler = globals()[spec.handler_key]
        except KeyError as exc:
            raise KeyError(f"Missing handler {spec.handler_key} for {spec.name}") from exc
        handler_registry.register(spec.name, handler)
