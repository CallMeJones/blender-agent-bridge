"""Provider execution shared by thread and subprocess workers.

Callers own input validation, spend approval, authorization, and job persistence.
Credentials are explicit and never copied into the durable job configuration.
"""
from . import external_assets

def _download_poly_haven(config, args, credentials, progress_callback):
    return external_assets.download_poly_haven_asset(
        asset_id=str(args.get("asset_id") or ""),
        asset_type=str(args.get("asset_type") or ""),
        resolution=str(args.get("resolution") or "2k"),
        file_format=str(args.get("file_format") or ""),
        map_types=args.get("map_types") if isinstance(args.get("map_types"), list) else None,
        include_dependencies=bool(args.get("include_dependencies", True)),
        cache_dir=str(args.get("cache_dir") or ""),
        timeout=int(args.get("timeout") or 60),
        progress_callback=progress_callback,
    )

def _download_sketchfab(config, args, credentials, progress_callback):
    return external_assets.download_sketchfab_model(
        uid=str(args.get("uid") or ""),
        api_token=credentials.get("token", ""),
        token_env_var=str(args.get("token_env_var") or external_assets.SKETCHFAB_TOKEN_ENV_VAR),
        model_password=credentials.get("password", ""),
        cache_dir=str(args.get("cache_dir") or ""),
        timeout=int(args.get("timeout") or 120),
        progress_callback=progress_callback,
        provenance=dict(args.get("provenance") or {}),
    )

def _generate_provider(provider):
    def generate(config, args, credentials, progress_callback):
        if args.get("job_kind") == "retopology":
            from . import retopology_providers
            return retopology_providers.run(config, args, provider=provider, api_key=credentials.get("token", ""),
                                            progress_callback=progress_callback,
                                            is_cancelled=config.get("_is_cancelled", lambda: False))
        from . import generation_job

        return generation_job.run(
            config,
            args,
            provider=provider,
            progress_callback=progress_callback,
            # The key never appears in the on-disk config; asset_jobs passes it
            # through the child environment for every credential-bearing
            # generation provider.
            api_key=credentials.get("token", ""),
            poll_interval=0 if provider == "triposr" else generation_job.POLL_INTERVAL_SECONDS,
        )

    return generate

WORKER_DISPATCH = {
    "poly_haven": _download_poly_haven,
    "sketchfab": _download_sketchfab,
    "tripo": _generate_provider("tripo"),
    "meshy": _generate_provider("meshy"),
    "studio_endpoint": _generate_provider("studio_endpoint"),
    "triposr": _generate_provider("triposr"),
}



def execute(config, args, *, credentials, progress_callback=None, is_cancelled=lambda: False):
    provider = str(config.get("provider") or "")
    worker = WORKER_DISPATCH.get(provider)
    if worker is None:
        return {"ok": False, "message": f"Unsupported external asset provider: {provider}"}
    if is_cancelled():
        return {"ok": False, "cancelled": True, "message": "External asset job cancelled before execution"}
    def progress(update):
        if not is_cancelled() and progress_callback:
            progress_callback(update)
    clean_args = {key: value for key, value in args.items() if key not in {"api_token", "api_key", "model_password"}}
    if provider in {"poly_haven", "sketchfab"}:
        default = 120 if provider == "sketchfab" else 60
        clean_args["timeout"] = max(1, min(300, int(clean_args.get("timeout") or default)))
    worker_config = dict(config, _is_cancelled=is_cancelled) if clean_args.get("job_kind") == "retopology" else config
    result = worker(worker_config, clean_args, dict(credentials), progress)
    if is_cancelled():
        return dict(result, ok=False, cancelled=True, message="External asset job cancelled")
    return result
