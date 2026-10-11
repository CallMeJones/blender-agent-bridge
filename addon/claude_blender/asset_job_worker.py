"""Background process entry point for external asset download/cache jobs."""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
import uuid

from . import asset_provider_execution, external_assets, job_runtime


ASSET_JOB_SECRET_TOKEN_ENV = "BLENDER_AGENT_BRIDGE_ASSET_JOB_API_TOKEN"
ASSET_JOB_SECRET_PASSWORD_ENV = "BLENDER_AGENT_BRIDGE_ASSET_JOB_MODEL_PASSWORD"
STATUS_REPLACE_ATTEMPTS = job_runtime.STATUS_REPLACE_ATTEMPTS
STATUS_REPLACE_INITIAL_DELAY_SECONDS = job_runtime.STATUS_REPLACE_INITIAL_DELAY_SECONDS


_replace_status_file = job_runtime.replace_status_file


_write_json = job_runtime.write_json


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
    if expected:
        progress = round(min(0.99, max(0.0, downloaded / expected)), 4)
    else:
        try:
            progress = round(min(0.99, max(0.0, float(update.get("progress")))), 4)
        except (TypeError, ValueError):
            progress = 0.0
    status_update = {
        "phase": str(update.get("phase") or "download"),
        "current_url": str(update.get("url") or ""),
        "current_file": str(update.get("path") or ""),
        "partial_path": str(update.get("partial_path") or ""),
        "bytes_downloaded": downloaded,
        "expected_size_bytes": expected,
        "current_file_progress": progress,
        "progress": progress,
        "attempt": int(update.get("attempt") or 0),
        "resumed": bool(update.get("resumed", False)),
        "message": str(update.get("message") or "External asset download/cache in progress"),
    }
    task_id = str(update.get("task_id") or "").strip()
    if task_id:
        status_update["provider_task_id"] = task_id
    task_kind = str(update.get("task_kind") or "").strip()
    if task_kind:
        status_update["provider_task_kind"] = task_kind
    _write_status(config, "running", **status_update)


def _provider_adapter(provider):
    def execute(config, args):
        return asset_provider_execution.execute(
            dict(config, provider=provider), args,
            credentials={"token": os.environ.get(ASSET_JOB_SECRET_TOKEN_ENV, ""),
                         "password": os.environ.get(ASSET_JOB_SECRET_PASSWORD_ENV, "")},
            progress_callback=lambda update: _progress_callback(config, update),
        )
    return execute


WORKER_DISPATCH = {name: _provider_adapter(name) for name in asset_provider_execution.WORKER_DISPATCH}
_download_poly_haven = WORKER_DISPATCH["poly_haven"]
_download_sketchfab = WORKER_DISPATCH["sketchfab"]


def run(config):
    provider = str(config.get("provider") or "")
    args = dict(config.get("args") or {})
    _write_status(config, "running", message=f"{provider.replace('_', ' ').title()} asset download/cache started")
    worker = WORKER_DISPATCH.get(provider)
    if worker is None:
        manifest = {"ok": False, "message": f"Unsupported external asset provider: {provider}"}
    else:
        manifest = worker(config, args)
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
