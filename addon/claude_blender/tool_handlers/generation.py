"""Handlers for the image-to-3D generation domain.

Credentials and machine paths come from add-on preferences because these
handlers run inside Blender and never see the MCP server process environment.
Generation jobs reuse the external-asset job machinery so they inherit the
subprocess worker, cancel, restart recovery, and the whole cache/import tail.
"""

from __future__ import annotations

import os

from .. import asset_jobs, generation_providers, preferences
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
        "note": (
            "Starting a paid route still needs confirm_paid on start_generation_job, so "
            "asking here is the first of two checks, not a replacement for it."
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

    # Naming a paid provider is not the same as agreeing to be charged. An
    # agent can decide to call Tripo on its own; the user cannot un-spend the
    # credits afterwards. So the first attempt reports the cost and refuses,
    # and only a second call carrying confirm_paid actually starts the job --
    # which forces the number into the conversation before the money moves.
    if generation_providers.is_paid_provider(provider) and not bool(args.get("confirm_paid")):
        notice = generation_providers.paid_provider_notice(provider)
        return {
            "ok": False,
            "requires_confirmation": True,
            "message": (
                "%s is a paid service and would be charged for this job. %s Tell the user "
                "the cost and that their reference images are uploaded, then call again "
                "with confirm_paid=true if they agree."
                % (notice.get("title") or provider, notice.get("cost_note") or "")
            ).strip(),
            "provider": provider,
            "cost": notice,
            "free_alternative": (
                "Local providers cost nothing and upload nothing; run "
                "get_generation_provider_diagnostics to see whether one is configured."
            ),
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
