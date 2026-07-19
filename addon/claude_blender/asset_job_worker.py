"""Background process entry point for external asset download/cache jobs."""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
import uuid

from . import external_assets


ASSET_JOB_SECRET_TOKEN_ENV = "BLENDER_AGENT_BRIDGE_ASSET_JOB_API_TOKEN"
ASSET_JOB_SECRET_PASSWORD_ENV = "BLENDER_AGENT_BRIDGE_ASSET_JOB_MODEL_PASSWORD"


def _write_json(path, payload):
    temp_path = f"{path}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _manifest_summary(manifest):
    manifest = manifest if isinstance(manifest, dict) else {}
    downloaded = [item for item in manifest.get("downloaded_files") or [] if isinstance(item, dict)]
    extracted = manifest.get("extracted_files") if isinstance(manifest.get("extracted_files"), list) else []
    return {
        "ok": bool(manifest.get("ok")),
        "provider": str(manifest.get("provider") or ""),
        "asset_id": str(manifest.get("asset_id") or ""),
        "uid": str(manifest.get("uid") or ""),
        "asset_type": str(manifest.get("asset_type") or ""),
        "cache_dir": str(manifest.get("cache_dir") or ""),
        "manifest_path": str(manifest.get("manifest_path") or ""),
        "import_file": str(manifest.get("import_file") or ""),
        "downloaded_file_count": len(downloaded),
        "extracted_file_count": len(extracted),
        "import_status": str(manifest.get("import_status") or ""),
        "message": str(manifest.get("message") or ""),
    }


def _write_status(config, status, **updates):
    path = config["child_status_path"]
    try:
        payload = _read_json(path) if os.path.isfile(path) else {}
    except Exception:
        payload = {}
    payload.update(updates)
    payload["status"] = status
    payload["updated_at"] = time.time()
    _write_json(path, payload)


def _progress_callback(config, update):
    update = update if isinstance(update, dict) else {}
    expected = int(update.get("expected_size") or 0)
    downloaded = int(update.get("bytes_downloaded") or 0)
    progress = round(min(0.99, max(0.0, downloaded / expected)), 4) if expected else 0.0
    _write_status(
        config,
        "running",
        phase=str(update.get("phase") or "download"),
        current_url=str(update.get("url") or ""),
        current_file=str(update.get("path") or ""),
        partial_path=str(update.get("partial_path") or ""),
        bytes_downloaded=downloaded,
        expected_size_bytes=expected,
        current_file_progress=progress,
        progress=progress,
        attempt=int(update.get("attempt") or 0),
        resumed=bool(update.get("resumed", False)),
        message="External asset download/cache in progress",
    )


def _download_poly_haven(config, args):
    return external_assets.download_poly_haven_asset(
        asset_id=str(args.get("asset_id") or ""),
        asset_type=str(args.get("asset_type") or ""),
        resolution=str(args.get("resolution") or "2k"),
        file_format=str(args.get("file_format") or ""),
        map_types=args.get("map_types") if isinstance(args.get("map_types"), list) else None,
        include_dependencies=bool(args.get("include_dependencies", True)),
        cache_dir=str(args.get("cache_dir") or ""),
        timeout=int(args.get("timeout") or 60),
        progress_callback=lambda update: _progress_callback(config, update),
    )


def _download_sketchfab(config, args):
    return external_assets.download_sketchfab_model(
        uid=str(args.get("uid") or ""),
        api_token=os.environ.get(ASSET_JOB_SECRET_TOKEN_ENV, ""),
        token_env_var=str(args.get("token_env_var") or external_assets.SKETCHFAB_TOKEN_ENV_VAR),
        model_password=os.environ.get(ASSET_JOB_SECRET_PASSWORD_ENV, ""),
        cache_dir=str(args.get("cache_dir") or ""),
        timeout=int(args.get("timeout") or 120),
        progress_callback=lambda update: _progress_callback(config, update),
        provenance=dict(args.get("provenance") or {}),
    )


def run(config):
    provider = str(config.get("provider") or "")
    args = dict(config.get("args") or {})
    _write_status(config, "running", message=f"{provider.replace('_', ' ').title()} asset download/cache started")
    if provider == "poly_haven":
        manifest = _download_poly_haven(config, args)
    elif provider == "sketchfab":
        manifest = _download_sketchfab(config, args)
    else:
        manifest = {"ok": False, "message": f"Unsupported external asset provider: {provider}"}
    status = "completed" if manifest.get("ok") else "failed"
    _write_status(
        config,
        status,
        ok=bool(manifest.get("ok")),
        completed_at=time.time(),
        progress=1.0 if manifest.get("ok") else 0.0,
        poll_after_seconds=0,
        manifest_path=str(manifest.get("manifest_path") or ""),
        manifest_summary=_manifest_summary(manifest),
        message=str(manifest.get("message") or ("External asset cached" if manifest.get("ok") else "External asset job failed")),
    )
    return 0 if manifest.get("ok") else 1


def main(config_path=None):
    config_path = config_path or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not config_path:
        raise RuntimeError("asset job worker config path is required")
    config = _read_json(config_path)
    try:
        return run(config)
    except Exception as exc:
        _write_status(
            config,
            "failed",
            ok=False,
            completed_at=time.time(),
            progress=0.0,
            poll_after_seconds=0,
            message=f"External asset worker failed: {type(exc).__name__}: {exc}",
            traceback=traceback.format_exc(),
        )
        raise
