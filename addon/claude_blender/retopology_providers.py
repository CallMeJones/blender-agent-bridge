"""Hosted retopology execution through the shared approved asset-job seam."""
from __future__ import annotations

import hashlib
import os
import time
import urllib.parse
from . import external_assets, generation_clients, generation_job, job_runtime, retopology_policy

MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
POLL_INTERVAL_SECONDS = 3


def run(config, args, *, provider, api_key, progress_callback=None, is_cancelled=lambda: False,
        client=None, downloader=None, poll_interval=POLL_INTERVAL_SECONDS):
    policy = retopology_policy.provider_options(provider, args)
    cache = os.path.join(os.path.dirname(config["child_status_path"]), "retopology")
    os.makedirs(cache, exist_ok=True)
    task_id = ""

    def report(progress, message, **extra):
        if is_cancelled():
            raise generation_clients.GenerationError("Retopology job cancelled")
        if progress_callback:
            progress_callback({"progress": progress, "message": message, "task_id": task_id,
                               "task_kind": "remesh" if provider == "meshy" else "retopology", **extra})

    def finish(ok, message, **extra):
        manifest = {"ok": ok, "provider": provider, "cache_dir": cache, "message": message,
                    "asset_id": task_id, "generation": {"kind": "retopology", "task_id": task_id}, **extra}
        path = os.path.join(cache, "asset_manifest.json")
        manifest["manifest_path"] = path
        job_runtime.write_json(path, manifest)
        return manifest

    try:
        client = client or (generation_clients.MeshyClient(api_key, timeout=int(args.get("timeout", 60))) if provider == "meshy"
                            else generation_clients.TripoClient(api_key, timeout=int(args.get("timeout", 60))))
        report(.05, "Submitting approved retopology request", phase="submit")
        task_id = client.create_remesh_task(**args) if provider == "meshy" else client.create_retopology_task(**args)
        report(.1, "Retopology task submitted", phase="poll")
        deadline = time.monotonic() + int(args.get("poll_timeout_seconds", 1800))
        errors = 0
        while time.monotonic() < deadline:
            if is_cancelled():
                return finish(False, "Local retopology job cancelled; provider task may still be running", cancelled=True,
                              provider_task_id=task_id)
            try:
                status = client.task_status(task_id)
                errors = 0
            except generation_clients.GenerationError as error:
                errors += 1
                if not error.retryable or errors > 3:
                    raise
                report(.1, "Temporary provider polling error; retrying", phase="poll_retry")
                time.sleep(min(8, 2 ** errors) if poll_interval else 0)
                continue
            report(.1 + .7 * max(0, min(100, status.get("progress", 0))) / 100, "Retopology in progress", phase="poll")
            if status.get("terminal"):
                break
            time.sleep(poll_interval)
        else:
            return finish(False, "Provider retopology polling timed out; do not resubmit blindly", provider_task_id=task_id)
        if not status.get("succeeded"):
            return finish(False, f"Provider retopology ended with status {status.get('status')}", provider_task_id=task_id,
                          provider_error=status.get("task_error", {}))
        urls = dict(status.get("artifact_urls") or {})
        if status.get("model_url"):
            urls.setdefault("glb", status["model_url"])
        primary_role = policy["output_format"]
        primary_url = urls.get(primary_role)
        if not primary_url:
            return finish(False, f"Provider did not return the requested {primary_role.upper()} model; refusing a silent format fallback",
                          provider_task_id=task_id)
        downloaded, artifacts, total = [], {}, 0
        downloader = downloader or external_assets.download_external_file
        candidates = [(primary_role, primary_url)] + [(key, url) for key, url in urls.items()
                      if key != primary_role and (key in {"glb", "fbx"} or key.startswith("texture_"))]
        for role, url in candidates:
            report(.85, f"Downloading {role}", phase="download")
            suffix = os.path.splitext(urllib.parse.urlsplit(url).path)[1].lower()
            if role in {"glb", "fbx"}:
                if suffix != "." + role:
                    raise ValueError(f"Provider returned a mismatched {role} model URL")
                filename = "model." + role
            else:
                if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
                    continue
                # Preserve texture basenames used by the provider's FBX references.
                filename = os.path.basename(urllib.parse.urlsplit(url).path)
                if filename in {"model.glb", "model.fbx"} or any(os.path.basename(f["path"]) == filename for f in downloaded):
                    filename = role + suffix
            destination = os.path.join(cache, filename)
            remaining = MAX_DOWNLOAD_BYTES - total
            if remaining <= 0:
                raise ValueError("Retopology artifacts exceed the aggregate 512 MiB download limit")
            result = downloader(url, destination, timeout=int(args.get("timeout", 60)), max_download_bytes=remaining)
            if not result.get("ok"):
                raise ValueError(result.get("message") or "Retopology artifact download failed")
            size = os.path.getsize(destination)
            if size > remaining:
                raise ValueError("Retopology artifact exceeds the remaining download limit")
            if role in {"glb", "fbx"}:
                error = generation_job.validate_generated_model_file(destination, content_type=result.get("content_type", ""))
                if error:
                    raise ValueError(error)
            digest = hashlib.sha256()
            with open(destination, "rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            total += size
            artifacts[role] = destination
            downloaded.append({"ok": True, "path": destination, "logical_path": filename,
                               "role": role, "bytes": size, "sha256": digest.hexdigest()})
        return finish(True, "Provider retopology cached; import a new candidate for review",
                      import_file=artifacts[primary_role], downloaded_files=downloaded, asset_type="models",
                      source_url=f"{client.base_url}/{'remesh' if provider == 'meshy' else 'tasks'}/{task_id}",
                      license=str(args.get("license_note") or "Provider asset license applies"),
                      retopology={"source_task_id": policy["source_task_id"], "topology_requested": policy["topology"],
                                  "target_faces": policy["target_faces"], "format_note": policy["format_note"],
                                  "artifacts": artifacts, "credits_consumed": status.get("credits_consumed"),
                                  "animation_ready": False})
    except Exception as error:
        # Transport clients scrub their keys. This also protects injected transports
        # and errors from the artifact downloader before status/log persistence.
        message = str(error).replace(api_key, "<redacted>") if api_key else str(error)
        return finish(False, f"Provider retopology failed: {message}", provider_task_id=task_id)
