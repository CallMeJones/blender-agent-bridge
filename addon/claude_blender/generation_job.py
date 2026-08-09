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
import shutil
import subprocess
import time
import urllib.request

from . import generation_clients, process_utils

MANIFEST_NAME = "asset_manifest.json"
POLL_INTERVAL_SECONDS = 5
# A hosted task normally lands in a minute or two; this bounds a hung provider.
MAX_POLL_SECONDS = 1800
# Measured on a live v3 image-to-model job. Used only to refuse a job the
# account plainly cannot afford, so erring high would block affordable work
# and erring low would let it fail after upload; this is the observed figure.
ESTIMATED_JOB_COST = 30.0
ESTIMATED_PROVIDER_COSTS = {
    "tripo": 30.0,
    "meshy": 30.0,
}


def _bounded_int(value, default, *, minimum, maximum):
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = int(default)
    return max(int(minimum), min(int(maximum), result))


def _bounded_float(value, default, *, minimum, maximum):
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = float(default)
    return max(float(minimum), min(float(maximum), result))


def _bounded_cost(value, default):
    try:
        cost = float(value)
    except (TypeError, ValueError):
        return float(default)
    return cost if cost > 0 else float(default)


def _format_credits(value):
    number = float(value)
    return str(int(number)) if number == int(number) else "%.2f" % number


def _write_manifest(cache_dir, manifest):
    os.makedirs(cache_dir, exist_ok=True)
    manifest_path = os.path.join(cache_dir, MANIFEST_NAME)
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    manifest["manifest_path"] = manifest_path
    return manifest


def _failure(cache_dir, message, *, provider="tripo", **extra):
    manifest = {"ok": False, "provider": provider, "cache_dir": cache_dir, "message": message}
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


def _tail(value, limit=4000):
    text = str(value or "")
    return text[-limit:] if len(text) > limit else text


def _balance_amount(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("balance", "credits", "available", "available_credits"):
            candidate = value.get(key)
            if isinstance(candidate, (int, float)):
                return float(candidate)
    return None


def _client_for_provider(provider, args, *, api_key=""):
    provider = str(provider or "tripo").strip().lower()
    timeout = int(args.get("timeout") or 120)
    if provider == "tripo":
        return generation_clients.TripoClient(api_key, timeout=timeout)
    if provider == "meshy":
        return generation_clients.MeshyClient(api_key, timeout=timeout)
    if provider == "studio_endpoint":
        return generation_clients.StudioEndpointClient(
            str(args.get("endpoint") or ""),
            api_key=api_key,
            timeout=timeout,
        )
    raise generation_clients.GenerationError(
        "Unsupported hosted generation provider: %s" % provider
    )


def _find_generated_mesh(output_dir):
    preferred = []
    fallback = []
    for root, _dirs, files in os.walk(output_dir):
        for name in files:
            path = os.path.join(root, name)
            suffix = os.path.splitext(name)[1].lower()
            if name.lower() in {"mesh.glb", "mesh.obj"}:
                preferred.append(path)
            elif suffix in {".glb", ".obj", ".fbx", ".stl"}:
                fallback.append(path)
    candidates = sorted(preferred) or sorted(fallback)
    return candidates[0] if candidates else ""


def _run_triposr(config, args, *, progress_callback=None):
    def report(fraction, message, **extra):
        if progress_callback:
            update = {"progress": max(0.0, min(1.0, fraction)), "message": message}
            update.update(extra)
            progress_callback(update)

    cache_dir = str(args.get("cache_dir") or "") or os.path.join(
        os.path.dirname(str(config.get("child_status_path") or "")), "generated"
    )
    os.makedirs(cache_dir, exist_ok=True)
    views = {
        str(name): str(path)
        for name, path in (args.get("views") or {}).items()
        if str(path or "").strip()
    }
    if len(views) != 1:
        return _failure(
            cache_dir,
            "TripoSR accepts exactly one reference image; supply one view or choose a multi-view provider",
            provider="triposr",
        )
    image_path = next(iter(views.values()))
    if not os.path.isfile(image_path):
        return _failure(cache_dir, "Reference image not found: %s" % image_path, provider="triposr")

    python_executable = str(args.get("runtime_python") or "").strip()
    root = str(args.get("runtime_root") or "").strip()
    if not python_executable:
        return _failure(cache_dir, "TripoSR runtime_python is required", provider="triposr")
    if not os.path.isfile(python_executable):
        return _failure(
            cache_dir,
            "TripoSR runtime_python does not exist: %s" % python_executable,
            provider="triposr",
        )
    run_py = os.path.join(root, "run.py")
    if not os.path.isfile(run_py):
        return _failure(
            cache_dir,
            "TripoSR root must contain run.py: %s" % root,
            provider="triposr",
        )

    output_dir = os.path.join(cache_dir, "triposr-output")
    os.makedirs(output_dir, exist_ok=True)
    # TripoSR writes each input to output_dir/<index>/mesh.*, but the script
    # does not create that indexed folder before export.
    os.makedirs(os.path.join(output_dir, "0"), exist_ok=True)
    command = [
        python_executable,
        run_py,
        image_path,
        "--output-dir",
        output_dir,
        "--model-save-format",
        "glb",
    ]
    triposr_options = {
        "mc_resolution": _bounded_int(args.get("mc_resolution"), 256, minimum=16, maximum=512),
        "no_remove_bg": bool(args.get("no_remove_bg", False)),
        "foreground_ratio": _bounded_float(args.get("foreground_ratio"), 0.85, minimum=0.1, maximum=1.0),
        "chunk_size": _bounded_int(args.get("chunk_size"), 8192, minimum=0, maximum=262144),
        "bake_texture": bool(args.get("bake_texture", args.get("texture", False))),
        "texture_resolution": _bounded_int(args.get("texture_resolution"), 2048, minimum=256, maximum=8192),
    }
    if triposr_options["no_remove_bg"]:
        command.append("--no-remove-bg")
    else:
        command.extend(["--foreground-ratio", str(triposr_options["foreground_ratio"])])
    command.extend(["--mc-resolution", str(triposr_options["mc_resolution"])])
    command.extend(["--chunk-size", str(triposr_options["chunk_size"])])
    if triposr_options["bake_texture"]:
        command.append("--bake-texture")
        command.extend(["--texture-resolution", str(triposr_options["texture_resolution"])])

    report(0.1, "Starting TripoSR local process", phase="local_process")
    timeout = int(args.get("timeout") or 300)
    try:
        process = subprocess.Popen(
            command,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            stdin=subprocess.DEVNULL,
            **process_utils.process_group_kwargs(),
        )
    except Exception as error:  # noqa: BLE001 - process startup failure is reportable
        return _failure(cache_dir, "TripoSR process failed to start: %s" % error, provider="triposr")

    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process_utils.terminate_process_tree(process)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
        completed_returncode = process.returncode
        timed_out = True
    else:
        completed_returncode = process.returncode
        timed_out = False

    stdout_path = os.path.join(cache_dir, "triposr.stdout.log")
    stderr_path = os.path.join(cache_dir, "triposr.stderr.log")
    with open(stdout_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(stdout or "")
    with open(stderr_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(stderr or "")

    if timed_out:
        return _failure(
            cache_dir,
            "TripoSR timed out after %d seconds" % timeout,
            provider="triposr",
            returncode=completed_returncode,
            stdout_log=stdout_path,
            stderr_log=stderr_path,
        )

    if completed_returncode != 0:
        return _failure(
            cache_dir,
            "TripoSR exited with code %s: %s"
            % (completed_returncode, _tail(stderr or stdout)),
            provider="triposr",
            stdout_log=stdout_path,
            stderr_log=stderr_path,
        )

    mesh_path = _find_generated_mesh(output_dir)
    if not mesh_path:
        return _failure(
            cache_dir,
            "TripoSR completed but no generated mesh was found",
            provider="triposr",
            stdout_log=stdout_path,
            stderr_log=stderr_path,
        )
    destination = os.path.join(cache_dir, "generated%s" % os.path.splitext(mesh_path)[1].lower())
    if os.path.abspath(mesh_path) != os.path.abspath(destination):
        shutil.copy2(mesh_path, destination)
    size = os.path.getsize(destination)
    manifest = {
        "ok": True,
        "provider": "triposr",
        "asset_id": os.path.basename(output_dir),
        "cache_dir": cache_dir,
        "import_file": destination,
        "downloaded_files": [
            {
                "ok": True,
                "path": destination,
                "cached": False,
                "logical_path": os.path.basename(destination),
            }
        ],
        "license": "MIT",
        "source_url": "local://triposr/%s" % os.path.basename(destination),
        "generation": {
            "task_id": "",
            "model": "TripoSR",
            "view_names": sorted(views),
            "view_count": len(views),
            "credits_consumed": 0,
            "local_process": True,
            "runtime_root": root,
            "intended_use": "local_blockout",
            "quality_note": (
                "TripoSR is a fast single-view local blockout route. It cannot observe "
                "occluded side/back structure and should not be treated as final asset quality."
            ),
            "triposr_options": triposr_options,
        },
        "bytes": size,
        "stdout_log": stdout_path,
        "stderr_log": stderr_path,
        "message": "Generated local TripoSR model cached from one view",
    }
    report(1.0, manifest["message"], phase="completed")
    return _write_manifest(cache_dir, manifest)


def run(
    config,
    args,
    *,
    progress_callback=None,
    provider="",
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

    provider = str(provider or config.get("provider") or args.get("provider") or "tripo").strip().lower()
    if provider == "triposr":
        return _run_triposr(
            config,
            args,
            progress_callback=progress_callback,
        )

    cache_dir = str(args.get("cache_dir") or "") or os.path.join(
        os.path.dirname(str(config.get("child_status_path") or "")), "generated"
    )
    os.makedirs(cache_dir, exist_ok=True)

    api_key = str(api_key or "").strip()
    if provider in ESTIMATED_PROVIDER_COSTS and not api_key:
        return _failure(
            cache_dir,
            "No generation API key was supplied to the worker",
            provider=provider,
        )

    views = {
        str(name): str(path)
        for name, path in (args.get("views") or {}).items()
        if str(path or "").strip()
    }
    if not views:
        return _failure(cache_dir, "No reference images were supplied", provider=provider)

    missing = [path for path in views.values() if not os.path.isfile(path)]
    if missing:
        return _failure(cache_dir, "Reference image not found: %s" % missing[0], provider=provider)

    if client is None:
        try:
            client = _client_for_provider(provider, args, api_key=api_key)
        except generation_clients.GenerationError as error:
            return _failure(cache_dir, str(error), provider=provider)

    # Check funds before anything leaves the machine. An account short of
    # credits fails at task creation -- after the user has approved the spend
    # and after their reference art has already been uploaded, which is the
    # worst order to discover it in. This runs in the worker subprocess, so
    # the request never touches Blender's main thread.
    estimated_cost = _bounded_cost(
        args.get("estimated_cost"),
        ESTIMATED_PROVIDER_COSTS.get(provider, ESTIMATED_JOB_COST),
    )
    read_balance = getattr(client, "balance", None)
    try:
        available = read_balance() if callable(read_balance) else None
    except generation_clients.GenerationError as error:
        # A balance endpoint that is unreachable or unrecognised must not block
        # a job the user has already approved; the vendor rejects it later if
        # funds really are short.
        report(0.02, "Could not read the account balance: %s" % error, phase="balance")
        available = None
    balance = _balance_amount(available)
    if balance is not None and balance < estimated_cost:
        return _failure(
            cache_dir,
            "Not enough credits: the account holds %s and this job needs about %s. "
            "Nothing was uploaded and nothing was charged."
            % (_format_credits(balance), _format_credits(estimated_cost)),
            provider=provider,
            credits_available=balance,
            credits_required=estimated_cost,
            uploaded=False,
        )

    # Upload every view first; uploads are not billed, so a failure here costs
    # nothing and is worth surfacing before a task is created.
    tokens = {}
    try:
        for index, (name, path) in enumerate(sorted(views.items())):
            report(0.05 + 0.15 * (index / max(1, len(views))), "Uploading %s" % name, phase="upload")
            tokens[name] = (client.upload_image(path), path)
    except generation_clients.GenerationError as error:
        return _failure(cache_dir, "Upload failed: %s" % error, provider=provider)

    report(0.25, "Creating generation task", phase="submit")
    try:
        if len(tokens) > 1:
            task_id = client.create_multiview_task(
                tokens,
                model=str(args.get("model") or ""),
                face_limit=int(args.get("face_limit") or 0),
                texture=args.get("texture") if "texture" in args else None,
            )
        else:
            only_token, only_path = next(iter(tokens.values()))
            task_id = client.create_image_task(
                only_token,
                only_path,
                model=str(args.get("model") or ""),
                face_limit=int(args.get("face_limit") or 0),
                texture=args.get("texture") if "texture" in args else None,
            )
    except generation_clients.GenerationError as error:
        return _failure(
            cache_dir,
            "Task creation failed: %s" % error,
            provider=provider,
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
            return _failure(cache_dir, "Polling failed: %s" % error, provider=provider, task_id=task_id)
        remote = max(0, min(100, int(status.get("progress") or 0)))
        report(0.3 + 0.55 * (remote / 100.0), "Generating (%d%%)" % remote, phase="poll", task_id=task_id)
        if status.get("terminal"):
            break
    else:
        return _failure(
            cache_dir,
            "Generation timed out after %d seconds" % MAX_POLL_SECONDS,
            provider=provider,
            task_id=task_id,
        )

    if not status.get("succeeded"):
        detail = str(status.get("error_message") or "").strip()
        return _failure(
            cache_dir,
            "Generation ended with status %s%s"
            % (status.get("status"), ": %s" % detail if detail else ""),
            provider=provider,
            task_id=task_id,
        )

    model_url = str(status.get("model_url") or "")
    if not model_url:
        return _failure(
            cache_dir,
            "Provider reported success but returned no model URL",
            provider=provider,
            task_id=task_id,
        )

    report(0.9, "Downloading generated model", phase="download", task_id=task_id)
    suffix = os.path.splitext(model_url.split("?", 1)[0])[1].lower() or ".glb"
    destination = os.path.join(cache_dir, "generated%s" % suffix)
    try:
        size = (downloader or _download)(model_url, destination)
    except Exception as error:  # noqa: BLE001 - any download failure is reportable
        return _failure(cache_dir, "Model download failed: %s" % error, provider=provider, task_id=task_id)

    manifest = {
        "ok": True,
        "provider": provider,
        "asset_id": task_id,
        "cache_dir": cache_dir,
        "import_file": destination,
        "downloaded_files": [{"ok": True, "path": destination, "cached": False, "logical_path": os.path.basename(destination)}],
        "license": str(args.get("license_note") or "Commercial API; output rights governed by the vendor's terms."),
        "source_url": model_url.split("?", 1)[0],
        "generation": {
            "task_id": task_id,
            "model": str(args.get("model") or ""),
            "view_names": sorted(views),
            "view_count": len(views),
            "credits_consumed": status.get("credits_consumed"),
        },
        "bytes": size,
        "message": "Generated model cached from %d view(s)" % len(views),
    }
    report(1.0, manifest["message"], phase="completed", task_id=task_id)
    return _write_manifest(cache_dir, manifest)
