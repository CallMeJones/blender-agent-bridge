"""Thin bridge adapters for the retopology pipeline."""
import json
import os
import bpy
from .. import asset_jobs, external_assets, generation_providers, preferences, retopology, retopology_jobs, retopology_policy


def inspect_retopology_source(context, args):
    return retopology.inspect_source(context, object_names=args.get("object_names"))


def prepare_retopology_copy(context, args):
    return retopology.prepare_copy(context, **args)


def evaluate_retopology_result(context, args):
    return retopology.evaluate_result(context, **args)


def start_retopology_job(context, args):
    return retopology_jobs.start(context, args)


def start_retopology_bake_job(context, args):
    return retopology_jobs.start(context, args, kind="bake")


def get_retopology_job_status(context, args):
    return retopology_jobs.status(context, args["job_id"])


def cancel_retopology_job(context, args):
    return retopology_jobs.cancel(context, args["job_id"])


def import_retopology_job_result(context, args):
    return retopology_jobs.import_result(context, **args)


def start_provider_retopology_job(context, args):
    provider = args["provider"]
    policy = retopology_policy.provider_options(provider, args)
    prefs = preferences.get_preferences(context)
    environ = dict(os.environ)
    environ.update(generation_providers.environment_overlay(prefs))
    spec = generation_providers.PROVIDERS_BY_NAME[provider]
    availability = generation_providers.provider_availability(spec, environ=environ)
    if not availability["available"]:
        return {"ok": False, "message": "Provider retopology is unavailable; review provider credentials and third-party access",
                "provider_availability": availability}
    api_key = next((environ[key] for key in spec.credential_env_vars if environ.get(key)), "")
    result = asset_jobs.start_external_asset_download(
        context, provider=provider, job_name="retopology", capture_dir=getattr(prefs, "capture_cache_dir", None),
        **dict({key: value for key, value in args.items() if key != "provider"}, job_kind="retopology",
               api_key=api_key, estimated_cost=policy["estimated_credits"], license_note=spec.license_note))
    if result.get("awaiting_user_approval"):
        from .. import live_preview
        live_preview.redraw(context)
    result["format_note"] = policy["format_note"]
    return result


def get_provider_retopology_job_status(context, args):
    prefs = preferences.get_preferences(context)
    job = asset_jobs.external_asset_job_status(args["job_id"], context=context,
                                              preferred_dir=getattr(prefs, "capture_cache_dir", None))
    return {"ok": bool(job.get("available")), "asset_job": job,
            "next_tool": "import_provider_retopology_job_result" if job.get("status") == "completed" else "get_provider_retopology_job_status"}


def import_provider_retopology_job_result(context, args):
    prefs = preferences.get_preferences(context)
    job = asset_jobs.external_asset_job_status(args["job_id"], context=context,
                                              preferred_dir=getattr(prefs, "capture_cache_dir", None))
    if job.get("status") != "completed" or job.get("provider") not in {"meshy", "tripo"}:
        return {"ok": False, "message": "A completed Meshy/Tripo job is required", "asset_job": job}
    with open(job["manifest_path"], encoding="utf-8") as handle:
        manifest = json.load(handle)
    selected = args.get("preferred_format", "auto")
    if selected != "auto":
        artifacts = (manifest.get("retopology") or manifest.get("generation") or {}).get("artifacts") or {}
        path = artifacts.get(selected)
        if not path or not os.path.isfile(path):
            return {"ok": False, "message": f"No cached {selected.upper()} variant is available", "available_formats": sorted(artifacts)}
        manifest = dict(manifest, import_file=path, asset_id=str(manifest.get("asset_id") or args["job_id"]) + ":" + selected)
        # Keep format variants independent of the primary cache and import identity.
        variant_dir = os.path.join(manifest["cache_dir"], "variants", selected)
        os.makedirs(variant_dir, exist_ok=True)
        manifest.update(cache_dir=variant_dir, manifest_path=os.path.join(variant_dir, "asset_manifest.json"))
        for key in list(manifest):
            if key.startswith("imported_") or key == "transaction_id":
                manifest.pop(key)
        files = list(manifest.get("downloaded_files") or [])
        manifest["downloaded_files"] = sorted(files, key=lambda f: str(f.get("path") or "") != path)
    from .. import live_preview
    label = args.get("label") or "Import provider retopology candidate"
    live_preview.begin(label, context)
    collections = {"object": "objects", "mesh": "meshes", "material": "materials", "image": "images",
                   "node_group": "node_groups", "action": "actions", "armature": "armatures",
                   "collection": "collections", "camera": "cameras", "light": "lights", "curve": "curves"}
    before = {kind: set(getattr(bpy.data, collection).keys()) for kind, collection in collections.items()}
    try:
        result = external_assets.import_cached_asset(context, manifest=manifest, label=label)
    finally:
        # Importers can allocate partial datablocks before returning an error.
        for kind, collection in collections.items():
            for name in set(getattr(bpy.data, collection).keys()) - before[kind]:
                live_preview.record_created_id(kind, name)
    if result.get("ok"):
        result["animation_ready"] = False
        result["next_tool"] = "evaluate_retopology_result"
        result["topology_note"] = "Inspect actual imported quads/triangles; provider quad labels do not establish animation readiness."
    return result


def register(handler_registry, specs):
    for spec in specs:
        handler_registry.register(spec.name, globals()[spec.handler_key])
