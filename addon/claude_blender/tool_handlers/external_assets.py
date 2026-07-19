"""Blender-only handlers for the external_assets domain."""

from __future__ import annotations

from .. import handler_runtime as _runtime

for _runtime_name, _runtime_value in vars(_runtime).items():
    if not _runtime_name.startswith("__"):
        globals()[_runtime_name] = _runtime_value
del _runtime_name, _runtime_value


def list_poly_haven_categories(context, args):
    return external_assets.list_poly_haven_categories(
        asset_type=str(args.get("asset_type") or "all"),
        timeout=_bounded_int(args.get("timeout"), 15, minimum=1, maximum=60),
    )


def search_poly_haven_assets(context, args):
    return external_assets.search_poly_haven_assets(
        query=str(args.get("query") or ""),
        asset_type=str(args.get("asset_type") or "all"),
        category=str(args.get("category") or ""),
        limit=_bounded_int(args.get("limit"), 20, minimum=1, maximum=50),
        timeout=_bounded_int(args.get("timeout"), 15, minimum=1, maximum=60),
    )


def inspect_poly_haven_asset_files(context, args):
    return external_assets.inspect_poly_haven_asset_files(
        asset_id=str(args.get("asset_id") or args.get("id") or ""),
        timeout=_bounded_int(args.get("timeout"), 15, minimum=1, maximum=60),
    )


def download_poly_haven_asset(context, args):
    return external_assets.download_poly_haven_asset(
        asset_id=str(args.get("asset_id") or args.get("id") or ""),
        asset_type=str(args.get("asset_type") or ""),
        resolution=str(args.get("resolution") or "2k"),
        file_format=str(args.get("file_format") or args.get("format") or ""),
        map_types=_name_list(args.get("map_types")),
        include_dependencies=bool(args.get("include_dependencies", True)),
        cache_dir=str(args.get("cache_dir") or ""),
        timeout=_bounded_int(args.get("timeout"), 60, minimum=1, maximum=300),
    )


def import_poly_haven_asset(context, args):
    return external_assets.import_poly_haven_asset(
        context,
        asset_id=str(args.get("asset_id") or args.get("id") or ""),
        asset_type=str(args.get("asset_type") or ""),
        resolution=str(args.get("resolution") or "2k"),
        file_format=str(args.get("file_format") or args.get("format") or ""),
        map_types=_name_list(args.get("map_types")),
        target_object_name=str(args.get("target_object_name") or args.get("object_name") or ""),
        cache_dir=str(args.get("cache_dir") or ""),
        timeout=_bounded_int(args.get("timeout"), 60, minimum=1, maximum=300),
        label=args.get("label", "Import Poly Haven asset"),
        allow_duplicate=bool(args.get("allow_duplicate", False)),
    )


def search_sketchfab_models(context, args):
    return external_assets.search_sketchfab_models(
        query=str(args.get("query") or ""),
        downloadable=bool(args.get("downloadable", True)),
        staffpicked=args.get("staffpicked") if args.get("staffpicked") is not None else None,
        animated=args.get("animated") if args.get("animated") is not None else None,
        limit=_bounded_int(args.get("limit"), 20, minimum=1, maximum=50),
        timeout=_bounded_int(args.get("timeout"), 15, minimum=1, maximum=60),
    )


def download_sketchfab_model(context, args):
    return external_assets.download_sketchfab_model(
        uid=str(args.get("uid") or ""),
        api_token=str(args.get("api_token") or ""),
        token_env_var=str(args.get("token_env_var") or external_assets.SKETCHFAB_TOKEN_ENV_VAR),
        model_password=str(args.get("model_password") or ""),
        cache_dir=str(args.get("cache_dir") or ""),
        timeout=_bounded_int(args.get("timeout"), 120, minimum=1, maximum=300),
        provenance=dict(args.get("provenance") or {}),
    )


def import_sketchfab_model(context, args):
    return external_assets.import_sketchfab_model(
        context,
        uid=str(args.get("uid") or ""),
        api_token=str(args.get("api_token") or ""),
        token_env_var=str(args.get("token_env_var") or external_assets.SKETCHFAB_TOKEN_ENV_VAR),
        model_password=str(args.get("model_password") or ""),
        cache_dir=str(args.get("cache_dir") or ""),
        timeout=_bounded_int(args.get("timeout"), 120, minimum=1, maximum=300),
        label=args.get("label", "Import Sketchfab model"),
        provenance=dict(args.get("provenance") or {}),
        allow_duplicate=bool(args.get("allow_duplicate", False)),
    )


def start_external_asset_download(context, args):
    prefs = preferences.get_preferences(context)
    provider = str(args.get("provider") or "").strip().lower()
    return asset_jobs.start_external_asset_download(
        context,
        provider=provider,
        asset_id=str(args.get("asset_id") or args.get("id") or ""),
        uid=str(args.get("uid") or ""),
        asset_type=str(args.get("asset_type") or ""),
        resolution=str(args.get("resolution") or "2k"),
        file_format=str(args.get("file_format") or args.get("format") or ""),
        map_types=_name_list(args.get("map_types")),
        include_dependencies=bool(args.get("include_dependencies", True)),
        api_token=str(args.get("api_token") or ""),
        token_env_var=str(args.get("token_env_var") or external_assets.SKETCHFAB_TOKEN_ENV_VAR),
        model_password=str(args.get("model_password") or ""),
        provenance=dict(args.get("provenance") or {}),
        cache_dir=str(args.get("cache_dir") or ""),
        timeout=_bounded_int(args.get("timeout"), 120 if provider == "sketchfab" else 60, minimum=1, maximum=300),
        job_name=str(args.get("job_name") or ""),
        note=str(args.get("note") or ""),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
    )


def get_external_asset_job_status(context, args):
    prefs = preferences.get_preferences(context)
    job = asset_jobs.external_asset_job_status(
        str(args.get("job_id") or ""),
        context=context,
        preferred_dir=getattr(prefs, "capture_cache_dir", None),
    )
    return {
        "ok": bool(job.get("available", False)),
        "message": "External asset job status collected" if job.get("available") else job.get("message", "External asset job was not found"),
        "asset_job": job,
    }


def cancel_external_asset_job(context, args):
    prefs = preferences.get_preferences(context)
    return asset_jobs.cancel_external_asset_job(
        str(args.get("job_id") or ""),
        context=context,
        preferred_dir=getattr(prefs, "capture_cache_dir", None),
    )


def import_external_asset_job_result(context, args):
    prefs = preferences.get_preferences(context)
    return asset_jobs.import_external_asset_job_result(
        context,
        job_id=str(args.get("job_id") or ""),
        target_object_name=str(args.get("target_object_name") or args.get("object_name") or ""),
        label=str(args.get("label") or "Import external asset job result"),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
        allow_duplicate=bool(args.get("allow_duplicate", False)),
    )


def start_external_asset_import_job(context, args):
    prefs = preferences.get_preferences(context)
    return asset_jobs.start_external_asset_import_job(
        context,
        source_job_id=str(args.get("source_job_id") or args.get("asset_job_id") or args.get("job_id") or ""),
        manifest_path=str(args.get("manifest_path") or ""),
        target_object_name=str(args.get("target_object_name") or args.get("object_name") or ""),
        label=str(args.get("label") or "Import external asset job result"),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
        allow_duplicate=bool(args.get("allow_duplicate", False)),
    )


def get_external_asset_import_job_status(context, args):
    prefs = preferences.get_preferences(context)
    job = asset_jobs.external_asset_import_job_status(
        str(args.get("job_id") or ""),
        context=context,
        preferred_dir=getattr(prefs, "capture_cache_dir", None),
    )
    return {
        "ok": bool(job.get("available", False)),
        "message": "External asset import job status collected" if job.get("available") else job.get("message", "External asset import job was not found"),
        "asset_import_job": job,
    }


def cancel_external_asset_import_job(context, args):
    prefs = preferences.get_preferences(context)
    return asset_jobs.cancel_external_asset_import_job(
        str(args.get("job_id") or ""),
        context=context,
        preferred_dir=getattr(prefs, "capture_cache_dir", None),
    )


def delete_external_asset_job(context, args):
    prefs = preferences.get_preferences(context)
    return asset_jobs.delete_external_asset_job(
        str(args.get("job_id") or ""),
        context=context,
        preferred_dir=getattr(prefs, "capture_cache_dir", None),
        dry_run=bool(args.get("dry_run", True)),
    )


def get_external_asset_cache_diagnostics(context, args):
    return external_assets.external_asset_cache_diagnostics(
        cache_dir=str(args.get("cache_dir") or ""),
        max_assets=_bounded_int(args.get("max_assets"), 50, minimum=1, maximum=500),
    )


def prune_external_asset_cache(context, args):
    return external_assets.prune_external_asset_cache(
        cache_dir=str(args.get("cache_dir") or ""),
        max_age_days=_bounded_int(args.get("max_age_days"), 0, minimum=0, maximum=36500),
        max_total_bytes=_bounded_int(args.get("max_total_bytes"), 0, minimum=0, maximum=10 * 1024 * 1024 * 1024 * 1024),
        dry_run=bool(args.get("dry_run", True)),
        include_imported=bool(args.get("include_imported", False)),
    )


def register(handler_registry, specs):
    for spec in specs:
        try:
            handler = globals()[spec.handler_key]
        except KeyError as exc:
            raise KeyError(f"Missing handler {spec.handler_key} for {spec.name}") from exc
        handler_registry.register(spec.name, handler)
