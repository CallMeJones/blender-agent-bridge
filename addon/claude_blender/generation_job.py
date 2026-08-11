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
import urllib.parse
import urllib.request

from . import (
    external_assets,
    generation_clients,
    generation_meshy,
    generation_references,
    generation_tripo,
    process_utils,
)

MANIFEST_NAME = "asset_manifest.json"
POLL_INTERVAL_SECONDS = 5
# A hosted task normally lands in a minute or two; this bounds a hung provider.
MAX_POLL_SECONDS = 1800
MAX_CONSECUTIVE_POLL_FAILURES = 4
POLL_RETRY_MAX_SECONDS = 15
MAX_GENERATION_DOWNLOAD_BYTES = 8 * 1024 * 1024 * 1024


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


def _download(url, destination, timeout=300, *, max_bytes=None):
    result = external_assets.download_external_file(
        url,
        destination,
        timeout=timeout,
        max_download_bytes=max_bytes,
    )
    if not result.get("ok"):
        raise ValueError(result.get("message") or "Generated artifact download failed")
    return result


def _url_origin(url):
    parsed = urllib.parse.urlparse(str(url or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ()
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.scheme.lower(), parsed.hostname.lower(), int(port)


def _download_studio_artifact(
    url,
    destination,
    *,
    endpoint,
    api_key="",
    timeout=300,
    max_bytes=None,
):
    """Stream a local studio artifact without allowing an origin pivot."""

    if _url_origin(url) != _url_origin(endpoint):
        # A studio may hand off to a public signed CDN. That path receives the
        # same DNS, redirect, HTTPS, and size protections as hosted providers.
        return _download(url, destination, timeout=timeout, max_bytes=max_bytes)
    request = urllib.request.Request(str(url), method="GET")
    if str(api_key or "").strip():
        request.add_header("Authorization", "Bearer %s" % str(api_key).strip())
    opener = generation_clients.build_no_redirect_opener(
        urllib.request.ProxyHandler({}),
    )
    partial = "%s.part" % destination
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    requested_limit = int(max_bytes or 0)
    download_limit = min(external_assets.MAX_DOWNLOAD_BYTES, requested_limit) if requested_limit else external_assets.MAX_DOWNLOAD_BYTES
    size = 0
    content_type = ""
    try:
        with opener.open(request, timeout=timeout) as response, open(partial, "wb") as handle:
            content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            advertised = int(response.headers.get("Content-Length") or 0)
            if advertised > download_limit:
                raise ValueError("Studio artifact exceeds the download safety limit")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > download_limit:
                    raise ValueError("Studio artifact exceeded the download safety limit")
                handle.write(chunk)
        os.replace(partial, destination)
    except Exception:
        try:
            os.remove(partial)
        except OSError:
            pass
        raise
    return {
        "ok": True,
        "path": destination,
        "size": size,
        "cached": False,
        "content_type": content_type,
    }


def _download_size(result, destination=""):
    if isinstance(result, dict):
        size = int(result.get("size") or 0)
    else:
        size = int(result or 0)
    if destination and os.path.isfile(destination):
        size = max(size, os.path.getsize(destination))
    return size


def _strip_url_secret(url):
    return str(url or "").split("?", 1)[0].split("#", 1)[0]


def _generation_error_payload(error):
    if hasattr(error, "as_dict"):
        return error.as_dict()
    return {"message": str(error)}


def _task_error_category(task_error):
    error_type = str((task_error or {}).get("type") or "").strip().lower()
    if error_type == "invalid_input":
        return "invalid_input"
    if error_type in {"timeout", "service_unavailable", "server_error"}:
        return "provider_failure"
    return "provider_task_failure"


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


def _generated_mesh_content_type_error(path, content_type):
    content_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if not content_type or content_type in {"application/octet-stream", "binary/octet-stream"}:
        return ""
    rejected = {
        "application/json",
        "application/xml",
        "text/html",
        "text/json",
        "text/xml",
    }
    if content_type in rejected or content_type.startswith(("image/", "audio/", "video/")):
        return "Generated %s artifact returned a non-model content type: %s" % (
            os.path.splitext(path)[1].lower() or "model",
            content_type,
        )
    return ""


def _generated_mesh_payload_error(path):
    suffix = os.path.splitext(path)[1].lower()
    try:
        with open(path, "rb") as handle:
            header = handle.read(4 * 1024 * 1024)
    except OSError as error:
        return "Could not read generated model: %s" % error
    if not header:
        return "Generated model payload is empty"
    if suffix == ".glb" and not header.startswith(b"glTF"):
        return (
            "Generated file is named .glb but does not contain a GLB payload; "
            "the provider exporter likely wrote another format"
        )
    if suffix == ".obj":
        lines = (line.lstrip() for line in header.splitlines())
        if b"\x00" in header or not any(line.startswith(b"v ") for line in lines):
            return "Generated file is named .obj but does not contain an OBJ vertex payload"
    if suffix == ".fbx":
        stripped = header.lstrip(b"\xef\xbb\xbf\x00\t\r\n ")
        if not (
            header.startswith(b"Kaydara FBX Binary  \x00\x1a\x00")
            or stripped.startswith(b"; FBX")
        ):
            return "Generated file is named .fbx but does not contain an FBX payload"
    if suffix == ".stl":
        size = os.path.getsize(path)
        binary_size_valid = False
        if len(header) >= 84:
            triangle_count = int.from_bytes(header[80:84], "little")
            binary_size_valid = size == 84 + triangle_count * 50
        ascii_header = header.lstrip(b"\xef\xbb\xbf\t\r\n ").lower()
        ascii_valid = ascii_header.startswith(b"solid") and b"facet" in ascii_header
        if not (binary_size_valid or ascii_valid):
            return "Generated file is named .stl but does not contain an STL payload"
    return ""


def _remove_rejected_artifact(path):
    for candidate in (path, "%s.part" % path):
        try:
            os.remove(candidate)
        except OSError:
            pass


def _artifact_suffix(url, default):
    suffix = os.path.splitext(urllib.parse.urlparse(str(url or "")).path)[1].lower()
    return suffix if suffix in {".glb", ".png", ".jpg", ".jpeg"} else default


def _artifact_candidates(status):
    urls = status.get("artifact_urls") if isinstance(status.get("artifact_urls"), dict) else {}
    candidates = []
    seen = set()
    for role, url in urls.items():
        url = str(url or "")
        if not url or url in seen or role == "glb":
            continue
        seen.add(url)
        if role == "pre_remeshed_glb":
            name = "generated_pre_remeshed.glb"
        elif role == "thumbnail_url":
            name = "meshy_thumbnail%s" % _artifact_suffix(url, ".png")
        elif role == "alpha_thumbnail_url":
            name = "meshy_thumbnail_alpha%s" % _artifact_suffix(url, ".png")
        elif role.startswith("thumbnail_"):
            name = "meshy_%s%s" % (role, _artifact_suffix(url, ".png"))
        elif role.startswith("texture_"):
            name = "meshy_%s%s" % (role, _artifact_suffix(url, ".png"))
        else:
            continue
        candidates.append((str(role), url, name))
    return candidates[:32]


def _download_one(downloader, url, destination, *, provider, args, api_key="", max_bytes):
    max_bytes = int(max_bytes)
    if max_bytes <= 0:
        raise ValueError("Generation job download safety limit reached")
    if downloader is not None:
        result = downloader(url, destination, int(args.get("timeout") or 300))
    elif provider == "studio_endpoint":
        result = _download_studio_artifact(
            url,
            destination,
            endpoint=str(args.get("endpoint") or ""),
            api_key=api_key,
            timeout=int(args.get("timeout") or 300),
            max_bytes=max_bytes,
        )
    else:
        result = _download(
            url,
            destination,
            timeout=int(args.get("timeout") or 300),
            max_bytes=max_bytes,
        )
    if _download_size(result, destination) > max_bytes:
        for path in (destination, "%s.part" % destination):
            try:
                os.remove(path)
            except OSError:
                pass
        raise ValueError("Artifact exceeds the remaining generation job download limit")
    return result


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
    triposr_options = {
        "mc_resolution": _bounded_int(args.get("mc_resolution"), 256, minimum=16, maximum=512),
        "no_remove_bg": bool(args.get("no_remove_bg", False)),
        "foreground_ratio": _bounded_float(args.get("foreground_ratio"), 0.85, minimum=0.1, maximum=1.0),
        "chunk_size": _bounded_int(args.get("chunk_size"), 8192, minimum=0, maximum=262144),
        "bake_texture": bool(args.get("bake_texture", args.get("texture", False))),
        "texture_resolution": _bounded_int(args.get("texture_resolution"), 2048, minimum=256, maximum=8192),
    }
    compatibility_runner = os.path.join(os.path.dirname(__file__), "triposr_compat_runner.py")
    command = [python_executable]
    if triposr_options["bake_texture"]:
        command.append(compatibility_runner)
    command.extend(
        [
            run_py,
            image_path,
            "--output-dir",
            output_dir,
            "--model-save-format",
            "glb",
        ]
    )
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
    payload_error = _generated_mesh_payload_error(mesh_path)
    if payload_error:
        return _failure(
            cache_dir,
            payload_error,
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
            "texture_bake_compatibility": (
                "device_aligned_positions" if triposr_options["bake_texture"] else "not_requested"
            ),
            "texture_bake_export_compatibility": (
                "xatlas_obj_atlas_embedded_glb"
                if triposr_options["bake_texture"]
                else "not_requested"
            ),
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
    if provider in {"tripo", "meshy"} and not api_key:
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

    meshy_options = {}
    meshy_policy = {}
    tripo_policy = {}
    try:
        generation_references.validate_reference_images(
            views,
            provider=provider,
            expected_identities=args.get("_reference_identities"),
        )
        if provider == "meshy":
            meshy_policy = generation_meshy.resolve_job_policy(
                args,
                view_count=len(views),
            )
            meshy_options = meshy_policy["options"]
        elif provider == "tripo":
            tripo_policy = generation_tripo.resolve_job_policy(args)
    except ValueError as error:
        return _failure(cache_dir, str(error), provider=provider, uploaded=False)

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
    if provider == "meshy":
        estimated_cost = meshy_policy["estimated_credits"]
    elif provider == "tripo":
        estimated_cost = tripo_policy["estimated_credits"]
    else:
        estimated_cost = _bounded_cost(args.get("estimated_cost"), 0.0)
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
            tokens[name] = (
                client.upload_image(
                    path,
                    expected_identity=(args.get("_reference_identities") or {}).get(name),
                ),
                path,
            )
    except generation_clients.GenerationError as error:
        return _failure(
            cache_dir,
            "Upload failed: %s" % error,
            provider=provider,
            provider_error=_generation_error_payload(error),
            uploaded=False,
        )

    report(0.25, "Creating generation task", phase="submit")
    try:
        create_options = {
            "model": str(args.get("model") or ""),
            "face_limit": int(args.get("face_limit") or 0),
            "texture": args.get("texture") if "texture" in args else None,
        }
        if provider == "meshy":
            create_options["meshy_options"] = meshy_options
        elif provider == "tripo":
            create_options.update(tripo_policy["options"])
        if len(tokens) > 1:
            task_id = client.create_multiview_task(
                tokens,
                **create_options,
            )
        else:
            only_token, only_path = next(iter(tokens.values()))
            task_id = client.create_image_task(
                only_token,
                only_path,
                **create_options,
            )
    except generation_clients.GenerationError as error:
        return _failure(
            cache_dir,
            "Task creation failed: %s" % error,
            provider=provider,
            insufficient_credit=bool(getattr(error, "insufficient_credit", False)),
            provider_error=_generation_error_payload(error),
        )

    task_kind = "multiview" if len(tokens) > 1 else "image"
    report(
        0.3,
        "Task %s submitted" % task_id,
        phase="poll",
        task_id=task_id,
        task_kind=task_kind,
    )

    deadline = time.time() + MAX_POLL_SECONDS
    status = {}
    consecutive_poll_failures = 0
    recovered_poll_failures = 0
    while time.time() < deadline:
        time.sleep(poll_interval)
        try:
            status = client.task_status(task_id)
        except generation_clients.GenerationError as error:
            consecutive_poll_failures += 1
            if not error.retryable or consecutive_poll_failures > MAX_CONSECUTIVE_POLL_FAILURES:
                return _failure(
                    cache_dir,
                    "Polling failed after %d consecutive error(s): %s"
                    % (consecutive_poll_failures, error),
                    provider=provider,
                    task_id=task_id,
                    provider_error=_generation_error_payload(error),
                    poll_failures=consecutive_poll_failures,
                )
            recovered_poll_failures += 1
            retry_delay = min(
                POLL_RETRY_MAX_SECONDS,
                2 ** (consecutive_poll_failures - 1),
            )
            report(
                0.3,
                "Temporary provider polling error; retrying in %d second(s): %s"
                % (retry_delay, error),
                phase="poll_retry",
                task_id=task_id,
                task_kind=task_kind,
                poll_failure=consecutive_poll_failures,
            )
            if poll_interval:
                time.sleep(retry_delay)
            continue
        consecutive_poll_failures = 0
        remote = max(0, min(100, int(status.get("progress") or 0)))
        report(
            0.3 + 0.55 * (remote / 100.0),
            "Generating (%d%%)" % remote,
            phase="poll",
            task_id=task_id,
            task_kind=task_kind,
        )
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
        task_error = dict(status.get("task_error") or {})
        return _failure(
            cache_dir,
            "Generation ended with status %s%s"
            % (status.get("status"), ": %s" % detail if detail else ""),
            provider=provider,
            task_id=task_id,
            task_error=task_error,
            failure_category=_task_error_category(task_error),
            expires_at=status.get("expires_at"),
            preceding_tasks=status.get("preceding_tasks"),
            credits_consumed=status.get("credits_consumed"),
        )

    model_url = str(status.get("model_url") or "")
    if not model_url:
        return _failure(
            cache_dir,
            "Provider reported success but returned no model URL",
            provider=provider,
            task_id=task_id,
        )

    report(
        0.9,
        "Downloading generated model",
        phase="download",
        task_id=task_id,
        task_kind=task_kind,
    )
    suffix = os.path.splitext(urllib.parse.urlparse(model_url).path)[1].lower() or ".glb"
    if suffix not in {".glb", ".obj", ".fbx", ".stl"}:
        return _failure(
            cache_dir,
            "Provider returned an unsupported model artifact type: %s" % suffix,
            provider=provider,
            task_id=task_id,
        )
    if provider == "meshy" and suffix != ".glb":
        return _failure(
            cache_dir,
            "Meshy returned a non-GLB artifact after a GLB-only request",
            provider=provider,
            task_id=task_id,
        )
    destination = os.path.join(cache_dir, "generated%s" % suffix)
    try:
        primary_download = _download_one(
            downloader,
            model_url,
            destination,
            provider=provider,
            args=args,
            api_key=api_key,
            max_bytes=MAX_GENERATION_DOWNLOAD_BYTES,
        )
        size = _download_size(primary_download, destination)
    except Exception as error:  # noqa: BLE001 - any download failure is reportable
        return _failure(cache_dir, "Model download failed: %s" % error, provider=provider, task_id=task_id)
    payload_error = _generated_mesh_content_type_error(
        destination,
        primary_download.get("content_type", "") if isinstance(primary_download, dict) else "",
    ) or _generated_mesh_payload_error(destination)
    if payload_error:
        _remove_rejected_artifact(destination)
        return _failure(cache_dir, payload_error, provider=provider, task_id=task_id)

    downloaded_files = [
        {
            "ok": True,
            "path": destination,
            "cached": bool(primary_download.get("cached", False)) if isinstance(primary_download, dict) else False,
            "logical_path": os.path.basename(destination),
            "role": "model",
            "bytes": size,
            "sha256": primary_download.get("sha256", "") if isinstance(primary_download, dict) else "",
        }
    ]
    artifact_paths = {"model": destination}
    artifact_sources = {"model": _strip_url_secret(model_url)}
    if suffix == ".glb":
        artifact_paths["glb"] = destination
        artifact_sources["glb"] = _strip_url_secret(model_url)
    artifact_warnings = []
    total_download_bytes = size
    for role, url, filename in _artifact_candidates(status):
        remaining_bytes = MAX_GENERATION_DOWNLOAD_BYTES - total_download_bytes
        if remaining_bytes <= 0:
            artifact_warnings.append("Remaining artifacts skipped: generation job download safety limit reached")
            break
        artifact_path = os.path.join(cache_dir, filename)
        try:
            artifact_download = _download_one(
                downloader,
                url,
                artifact_path,
                provider=provider,
                args=args,
                api_key=api_key,
                max_bytes=remaining_bytes,
            )
            artifact_size = _download_size(artifact_download, artifact_path)
            if role == "pre_remeshed_glb":
                payload_error = _generated_mesh_content_type_error(
                    artifact_path,
                    artifact_download.get("content_type", "")
                    if isinstance(artifact_download, dict)
                    else "",
                ) or _generated_mesh_payload_error(artifact_path)
                if payload_error:
                    _remove_rejected_artifact(artifact_path)
                    raise ValueError(payload_error)
        except Exception as error:  # noqa: BLE001 - auxiliary artifacts are best-effort
            artifact_warnings.append("%s download failed: %s" % (role, error))
            continue
        downloaded_files.append(
            {
                "ok": True,
                "path": artifact_path,
                "cached": bool(artifact_download.get("cached", False)) if isinstance(artifact_download, dict) else False,
                "logical_path": filename,
                "role": role,
                "bytes": artifact_size,
                "sha256": artifact_download.get("sha256", "") if isinstance(artifact_download, dict) else "",
            }
        )
        artifact_paths[role] = artifact_path
        artifact_sources[role] = _strip_url_secret(url)
        total_download_bytes += artifact_size

    manifest = {
        "ok": True,
        "provider": provider,
        "asset_id": task_id,
        "cache_dir": cache_dir,
        "import_file": destination,
        "downloaded_files": downloaded_files,
        "license": str(args.get("license_note") or "Commercial API; output rights governed by the vendor's terms."),
        "source_url": _strip_url_secret(model_url),
        "generation": {
            "task_id": task_id,
            "model": (
                meshy_options.get("ai_model", "")
                if provider == "meshy"
                else str(args.get("model") or "")
            ),
            "view_names": sorted(views),
            "view_count": len(views),
            "credits_consumed": status.get("credits_consumed"),
            "estimated_credits": estimated_cost,
            "pricing_version": (
                meshy_policy.get("pricing_version", "")
                if provider == "meshy"
                else tripo_policy.get("pricing_version", "") if provider == "tripo" else ""
            ),
            "meshy_options": meshy_options if provider == "meshy" else {},
            "artifacts": artifact_paths,
            "artifact_sources": artifact_sources,
            "artifact_warnings": artifact_warnings,
            "created_at": status.get("created_at"),
            "started_at": status.get("started_at"),
            "finished_at": status.get("finished_at"),
            "expires_at": status.get("expires_at"),
            "preceding_tasks": status.get("preceding_tasks"),
            "task_error": dict(status.get("task_error") or {}),
            "recovered_poll_failures": recovered_poll_failures,
        },
        "bytes": sum(int(entry.get("bytes") or 0) for entry in downloaded_files),
        "message": "Generated model cached from %d view(s)" % len(views),
    }
    report(
        1.0,
        manifest["message"],
        phase="completed",
        task_id=task_id,
        task_kind=task_kind,
    )
    return _write_manifest(cache_dir, manifest)
