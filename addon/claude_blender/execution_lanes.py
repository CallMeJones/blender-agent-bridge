"""Explicit I/O plans. Preparation is main-thread only; workers receive no bpy objects."""
from copy import deepcopy
import json
import bpy

from . import asset_jobs, external_assets, preferences, tool_executor
from .operation_queue import DeferredCall
from .tool_handlers import external_assets as assets_handler, generation


NETWORK_TOOLS = frozenset({
    "list_poly_haven_categories", "search_poly_haven_assets",
    "inspect_poly_haven_asset_files", "search_sketchfab_models",
    "download_poly_haven_asset", "download_sketchfab_model",
})
IMPORT_TOOLS = frozenset({"import_poly_haven_asset", "import_sketchfab_model"})
WORKER_TOOLS = NETWORK_TOOLS | IMPORT_TOOLS | {"get_generation_provider_diagnostics", "cancel_external_asset_job"}


def prepare(context, name, arguments):
    if name not in WORKER_TOOLS:
        return None
    args = deepcopy(arguments)
    policy = external_assets.capture_network_policy()
    finish = lambda result: result
    if name in NETWORK_TOOLS | IMPORT_TOOLS:
        handler = getattr(assets_handler, name.replace("import_", "download_", 1) if name in IMPORT_TOOLS else name)
        captured_auth = None
        if name.startswith(("download_", "import_")):
            args["cache_dir"] = str(args.get("cache_dir") or external_assets._default_cache_dir())
            if "sketchfab" in name:
                captured_auth = external_assets._auth_header_from_token(
                    str(args.get("api_token") or ""),
                    token_env_var=str(args.get("token_env_var") or external_assets.SKETCHFAB_TOKEN_ENV_VAR))
        def work():
            with external_assets.network_access_scope(policy, sketchfab_auth=captured_auth):
                return handler(None, args)
        if name in IMPORT_TOOLS:
            scene_identity = context.scene.as_pointer()
            def finish(manifest):
                if not manifest.get("ok"):
                    return manifest
                if bpy.context.scene is None or bpy.context.scene.as_pointer() != scene_identity:
                    return {"ok": False, "code": "scene_changed_during_download",
                            "message": "Scene changed while downloading; import the cached manifest explicitly",
                            "manifest": manifest}
                def apply(context, _args):
                    return external_assets.import_cached_asset(
                        context, manifest=manifest,
                        target_object_name=str(args.get("target_object_name") or args.get("object_name") or ""),
                        label=str(args.get("label") or ("Import Poly Haven asset" if "poly_haven" in name else "Import Sketchfab model")),
                        allow_duplicate=bool(args.get("allow_duplicate", False)))
                return json.loads(tool_executor.execute_tool(bpy.context, name, args, handler=apply))
    elif name == "get_generation_provider_diagnostics":
        environ = generation._generation_environ(context)
        def work():
            return generation.diagnostics_from_environment(args, environ)
    else:
        prefs = preferences.get_preferences(context)
        job = deepcopy(asset_jobs.external_asset_job_status(
            str(args.get("job_id") or ""), context=context,
            preferred_dir=getattr(prefs, "capture_cache_dir", None)))
        environ = generation._generation_environ(context)
        def work():
            # Stop local work before a slow remote provider request.
            result = asset_jobs.cancel_prepared_asset_job(job)
            with external_assets.network_access_scope(policy):
                remote = generation.cancel_provider_task(job, environ) if job.get("available") else {}
            if remote and job.get("metadata_path"):
                result["asset_job"] = asset_jobs._update_metadata(
                    job["metadata_path"], remote_cancellation=remote)
            return result
    return DeferredCall(work, finish)
