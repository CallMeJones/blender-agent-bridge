"""Run one hosted generation job to completion inside the asset job worker.

Executes in the subprocess started by ``asset_jobs``, so the long poll against
a remote provider never touches Blender's main thread.

Produces the same manifest shape the catalog providers produce -- ``ok``,
``provider``, ``cache_dir``, ``manifest_path``, ``import_file``,
``downloaded_files`` -- so every downstream tool (import, presentation, cache
diagnostics, pruning) works on a generated asset with no special casing.

The API key arrives through the child environment, never through the job config
that ``asset_jobs`` writes to disk.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request

from . import generation_clients

MANIFEST_NAME = "asset_manifest.json"
POLL_INTERVAL_SECONDS = 5
# A hosted task normally lands in a minute or two; this bounds a hung provider.
MAX_POLL_SECONDS = 1800


def _write_manifest(cache_dir, manifest):
    os.makedirs(cache_dir, exist_ok=True)
    manifest_path = os.path.join(cache_dir, MANIFEST_NAME)
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    manifest["manifest_path"] = manifest_path
    return manifest


def _failure(cache_dir, message, **extra):
    manifest = {"ok": False, "provider": "tripo", "cache_dir": cache_dir, "message": message}
    manifest.update(extra)
    try:
        _write_manifest(cache_dir, manifest)
    except OSError:
        pass
    return manifest


def _download(url, destination, timeout=300):
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    with open(destination, "wb") as handle:
        handle.write(payload)
    return len(payload)


def run(
    config,
    args,
    *,
    progress_callback=None,
    api_key="",
    client=None,
    downloader=None,
    poll_interval=POLL_INTERVAL_SECONDS,
):
    """Upload, submit, poll, download. Returns an external-asset manifest.

    ``client``, ``downloader`` and ``poll_interval`` are injectable so the whole
    flow can be exercised without network access, credits, or real waiting.
    """

    def report(fraction, message, **extra):
        if progress_callback:
            update = {"progress": max(0.0, min(1.0, fraction)), "message": message}
            update.update(extra)
            progress_callback(update)

    cache_dir = str(args.get("cache_dir") or "") or os.path.join(
        os.path.dirname(str(config.get("child_status_path") or "")), "generated"
    )
    os.makedirs(cache_dir, exist_ok=True)

    api_key = str(api_key or "").strip()
    if not api_key:
        return _failure(cache_dir, "No generation API key was supplied to the worker")

    views = {
        str(name): str(path)
        for name, path in (args.get("views") or {}).items()
        if str(path or "").strip()
    }
    if not views:
        return _failure(cache_dir, "No reference images were supplied")

    missing = [path for path in views.values() if not os.path.isfile(path)]
    if missing:
        return _failure(cache_dir, "Reference image not found: %s" % missing[0])

    if client is None:
        try:
            client = generation_clients.TripoClient(api_key, timeout=int(args.get("timeout") or 120))
        except generation_clients.GenerationError as error:
            return _failure(cache_dir, str(error))

    # Upload every view first; uploads are not billed, so a failure here costs
    # nothing and is worth surfacing before a task is created.
    tokens = {}
    try:
        for index, (name, path) in enumerate(sorted(views.items())):
            report(0.05 + 0.15 * (index / max(1, len(views))), "Uploading %s" % name, phase="upload")
            tokens[name] = (client.upload_image(path), path)
    except generation_clients.GenerationError as error:
        return _failure(cache_dir, "Upload failed: %s" % error)

    report(0.25, "Creating generation task", phase="submit")
    try:
        if len(tokens) > 1:
            task_id = client.create_multiview_task(
                tokens,
                model=str(args.get("model") or ""),
                face_limit=int(args.get("face_limit") or 0),
            )
        else:
            only_token, only_path = next(iter(tokens.values()))
            task_id = client.create_image_task(
                only_token,
                only_path,
                model=str(args.get("model") or ""),
                face_limit=int(args.get("face_limit") or 0),
            )
    except generation_clients.GenerationError as error:
        return _failure(
            cache_dir,
            "Task creation failed: %s" % error,
            insufficient_credit=bool(getattr(error, "insufficient_credit", False)),
        )

    report(0.3, "Task %s submitted" % task_id, phase="poll", task_id=task_id)

    deadline = time.time() + MAX_POLL_SECONDS
    status = {}
    while time.time() < deadline:
        time.sleep(poll_interval)
        try:
            status = client.task_status(task_id)
        except generation_clients.GenerationError as error:
            return _failure(cache_dir, "Polling failed: %s" % error, task_id=task_id)
        remote = max(0, min(100, int(status.get("progress") or 0)))
        report(0.3 + 0.55 * (remote / 100.0), "Generating (%d%%)" % remote, phase="poll", task_id=task_id)
        if status.get("terminal"):
            break
    else:
        return _failure(cache_dir, "Generation timed out after %d seconds" % MAX_POLL_SECONDS, task_id=task_id)

    if not status.get("succeeded"):
        return _failure(
            cache_dir,
            "Generation ended with status %s" % status.get("status"),
            task_id=task_id,
        )

    model_url = str(status.get("model_url") or "")
    if not model_url:
        return _failure(cache_dir, "Provider reported success but returned no model URL", task_id=task_id)

    report(0.9, "Downloading generated model", phase="download", task_id=task_id)
    suffix = os.path.splitext(model_url.split("?", 1)[0])[1].lower() or ".glb"
    destination = os.path.join(cache_dir, "generated%s" % suffix)
    try:
        size = (downloader or _download)(model_url, destination)
    except Exception as error:  # noqa: BLE001 - any download failure is reportable
        return _failure(cache_dir, "Model download failed: %s" % error, task_id=task_id)

    manifest = {
        "ok": True,
        "provider": "tripo",
        "asset_id": task_id,
        "cache_dir": cache_dir,
        "import_file": destination,
        "downloaded_files": [{"ok": True, "path": destination, "cached": False, "logical_path": os.path.basename(destination)}],
        "license": str(args.get("license_note") or "Commercial API; output rights governed by the vendor's terms."),
        "source_url": model_url,
        "generation": {
            "task_id": task_id,
            "model": str(args.get("model") or generation_clients.TRIPO_DEFAULT_MODEL),
            "view_names": sorted(views),
            "view_count": len(views),
            "credits_consumed": status.get("credits_consumed"),
        },
        "bytes": size,
        "message": "Generated model cached from %d view(s)" % len(views),
    }
    report(1.0, manifest["message"], phase="completed", task_id=task_id)
    return _write_manifest(cache_dir, manifest)
