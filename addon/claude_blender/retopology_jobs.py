"""Supervised background Blender jobs with explicit, preview-safe result import."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid
import bpy
from . import job_runtime, live_preview, preferences, process_utils, retopology, retopology_policy, viewport_capture

_PROCESSES = {}
_JOB_DIRS = {}
TERMINAL = {"completed", "failed", "cancelled", "timed_out"}
MAX_ACTIVE_JOBS = 2


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _root(context, *, create=False):
    preferred = getattr(preferences.get_preferences(context), "capture_cache_dir", None)
    info = viewport_capture.resolve_capture_dir(context, preferred_dir=preferred, create=create)
    root = os.path.join(info["capture_dir"], "retopology-jobs")
    if create:
        os.makedirs(root, exist_ok=True)
    return root


def _locate(context, job_id):
    if not re.fullmatch(r"[a-f0-9]{32}", str(job_id)):
        raise ValueError("Invalid retopology job ID")
    preferred = getattr(preferences.get_preferences(context), "capture_cache_dir", None)
    # Never rely on a remembered directory from another open project.
    roots = [os.path.join(info["capture_dir"], "retopology-jobs")
             for info in viewport_capture.capture_dir_candidates(context=context, preferred_dir=preferred)]
    for root in roots:
        directory = os.path.join(root, job_id)
        if os.path.isfile(os.path.join(directory, "metadata.json")):
            return directory
    raise ValueError("Retopology job not found in this project/session")


def _refresh(directory):
    metadata_path = os.path.join(directory, "metadata.json")
    metadata = _read(metadata_path)
    job_id = metadata["job_id"]
    process = _PROCESSES.get(job_id)
    if metadata["status"] not in TERMINAL:
        try:
            child = _read(os.path.join(directory, "status.json"))
        except (OSError, ValueError):
            child = {}
        if process and process.poll() is None and time.time() - metadata["created_at"] > metadata["timeout_seconds"]:
            process_utils.terminate_process_tree(process)
            if process.poll() is None:
                metadata["message"] = "Worker exceeded its time limit but could not be stopped; retrying termination"
            else:
                metadata.update(status="timed_out", message="Retopology worker exceeded its time limit")
                _PROCESSES.pop(job_id, None)
        elif process and process.poll() is not None:
            if process.returncode == 0 and child.get("status") == "completed" and os.path.isfile(metadata["result_path"]):
                metadata.update(child)
                metadata["result_sha256"] = _sha256(metadata["result_path"])
            else:
                metadata.update(status="failed", message=child.get("message") or f"Worker exited with code {process.returncode}")
            _PROCESSES.pop(job_id, None)
        elif process:
            metadata.update({key: child[key] for key in ("phase", "progress", "message") if key in child})
        else:
            metadata.update(status="failed", message="Worker handle is unavailable; start a new job from the preserved sources")
        job_runtime.write_json(metadata_path, metadata)
    if metadata["status"] == "completed":
        try:
            report = _read(os.path.join(directory, "result.json"))
            if not report.get("ok") or not report.get("object_names") or len(report["object_names"]) > retopology.MAX_OBJECTS:
                raise ValueError("Missing or invalid object inventory")
            metadata["report"] = report
        except (OSError, ValueError, TypeError, AttributeError) as error:
            metadata.update(status="failed", message=f"Worker result report is invalid: {error}")
            job_runtime.write_json(metadata_path, metadata)
    metadata["poll_after_seconds"] = 0 if metadata["status"] in TERMINAL else 2
    metadata["timeout_safe"] = True
    return metadata


def _poll():
    for job_id, directory in list(_JOB_DIRS.items()):
        if job_id in _PROCESSES:
            _refresh(directory)
    return 1.0 if _PROCESSES else None


def start(context, args, *, kind="remesh"):
    options = retopology_policy.local_options(args, kind=kind)
    names = [args["source_object_name"], args["target_object_name"]] if kind == "bake" else args.get("object_names")
    objects = retopology.resolve_objects(context, names)
    if kind == "bake" and len(objects) != 2:
        raise ValueError("Baking needs distinct source and target objects")
    atlas_count = 1 if kind == "bake" else len(objects)
    if options["bake_textures"] and atlas_count * options["resolution"] ** 2 * (len(options["map_types"]) + 2) > retopology_policy.MAX_ATLAS_PIXELS:
        raise ValueError("Combined texture atlases exceed the 32-megapixel job budget; process fewer objects or lower resolution")
    if sum(len(o.data.vertices) for o in objects) > 2_000_000:
        raise ValueError("Combined source meshes exceed the two-million-vertex job budget")
    _poll()
    if len(_PROCESSES) >= MAX_ACTIVE_JOBS:
        return {"ok": False, "message": "Two retopology jobs are already active; wait or cancel one"}
    job_id = uuid.uuid4().hex
    directory = os.path.join(_root(context, create=True), job_id)
    os.makedirs(directory)
    snapshots = []
    try:
        evaluated_vertices = 0
        for index, obj in enumerate(objects):
            snapshots.append(retopology.static_copy(context, obj, f"retopo_snapshot_{index}", link=False, independent_materials=False))
            evaluated_vertices += len(snapshots[-1].data.vertices)
            if evaluated_vertices > 2_000_000:
                raise ValueError("Combined evaluated meshes exceed the two-million-vertex job budget")
        input_path = os.path.join(directory, "input.blend")
        bpy.data.libraries.write(input_path, set(snapshots), path_remap="ABSOLUTE", fake_user=False, compress=True)
        config = {"job_id": job_id, "kind": kind, "options": options, "job_dir": directory,
                  "snapshot_names": [o.name for o in snapshots],
                  "source_snapshots": [o.name for o in snapshots[:1]] if kind == "bake" else [o.name for o in snapshots],
                  "source_names": [objects[0].name] if kind == "bake" else [o.name for o in objects],
                  "target_snapshot": snapshots[1].name if kind == "bake" else "",
                  "input_path": input_path, "result_path": os.path.join(directory, "result.blend"),
                  "result_report_path": os.path.join(directory, "result.json"),
                  "status_path": os.path.join(directory, "status.json"), "cancel_path": os.path.join(directory, "cancel")}
    finally:
        for obj in snapshots:
            mesh = obj.data
            bpy.data.objects.remove(obj)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
    config_path = os.path.join(directory, "config.json")
    job_runtime.write_json(config_path, config)
    script_path = os.path.join(directory, "worker.py")
    with open(script_path, "w", encoding="utf-8") as handle:
        handle.write(f"import sys\nsys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r})\n"
                     f"from claude_blender.retopology_worker import main\nraise SystemExit(main({config_path!r}))\n")
    metadata = {"job_id": job_id, "kind": kind, "status": "running", "created_at": time.time(),
                "timeout_seconds": options["timeout_seconds"], "source_names": config["source_names"],
                "result_path": config["result_path"], "job_dir": directory,
                "operation_id": job_runtime.current_operation_id(), "message": "Background retopology job started"}
    job_runtime.write_json(os.path.join(directory, "metadata.json"), metadata)
    try:
        with open(os.path.join(directory, "worker.log"), "wb") as log:
            process = subprocess.Popen([bpy.app.binary_path, "--background", "--factory-startup", "--disable-autoexec",
                                        "--threads", "2", "--python-exit-code", "1", "--python", script_path],
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                       env=job_runtime.child_environment(), **process_utils.process_group_kwargs())
        _PROCESSES[job_id] = process
        _JOB_DIRS[job_id] = directory
        if not bpy.app.timers.is_registered(_poll):
            bpy.app.timers.register(_poll, first_interval=1.0)
    except Exception as error:
        process = _PROCESSES.pop(job_id, None)
        if process and process.poll() is None:
            process_utils.terminate_process_tree(process)
        _JOB_DIRS.pop(job_id, None)
        metadata.update(status="failed", message=f"Could not launch retopology worker: {error}")
        job_runtime.write_json(os.path.join(directory, "metadata.json"), metadata)
        return {"ok": False, "message": metadata["message"], "job_id": job_id}
    return {"ok": True, "message": metadata["message"], "job_id": job_id,
            "retopology_job": _refresh(directory), "next_tool": "get_retopology_job_status"}


def status(context, job_id):
    return {"ok": True, "retopology_job": _refresh(_locate(context, job_id))}


def cancel(context, job_id):
    directory = _locate(context, job_id)
    metadata = _refresh(directory)
    if metadata["status"] in TERMINAL:
        return {"ok": True, "retopology_job": metadata, "message": "Job is already terminal"}
    Path(directory, "cancel").touch()
    process = _PROCESSES.get(job_id)
    if process:
        process_utils.terminate_process_tree(process)
        if process.poll() is None:
            return {"ok": False, "message": "Worker could not be stopped; poll before restarting"}
    _PROCESSES.pop(job_id, None)
    metadata.update(status="cancelled", message="Retopology worker and descendants stopped; source meshes preserved")
    job_runtime.write_json(os.path.join(directory, "metadata.json"), metadata)
    return {"ok": True, "message": metadata["message"], "retopology_job": metadata}


def import_result(context, job_id, *, label="Import retopology result"):
    directory = _locate(context, job_id)
    metadata = _refresh(directory)
    if metadata["status"] != "completed":
        return {"ok": False, "message": "Retopology result is not completed", "retopology_job": metadata}
    existing = [o.name for o in context.scene.objects if o.get("agent_bridge_retopology_import_job") == job_id]
    if existing:
        return {"ok": True, "message": "This job is already imported in the current scene", "objects": existing}
    if _sha256(metadata["result_path"]) != metadata["result_sha256"]:
        return {"ok": False, "message": "Result file changed after worker completion; refusing stale import"}
    transaction = live_preview.begin(label, context)
    collections = {"object": "objects", "mesh": "meshes", "material": "materials", "image": "images",
                   "node_group": "node_groups", "action": "actions", "armature": "armatures"}
    before = {kind: set(getattr(bpy.data, collection).keys()) for kind, collection in collections.items()}
    try:
        with bpy.data.libraries.load(metadata["result_path"], link=False) as (available, loaded):
            # Blender replaces this list's names with IDs when the context exits.
            loaded.objects = list(metadata["report"]["object_names"])
    finally:
        for kind, collection in collections.items():
            for name in set(getattr(bpy.data, collection).keys()) - before[kind]:
                live_preview.record_created_id(kind, name)
    for obj in loaded.objects:
        if obj is None or obj.type != "MESH":
            raise ValueError("Worker result contains a missing/non-mesh object")
        retopology.validate_mesh(obj.data)
        context.scene.collection.objects.link(obj)
        obj["agent_bridge_retopology_import_job"] = job_id
    names = [o.name for o in loaded.objects]
    transaction["applied_steps"].append({"type": "retopology_import", "job_id": job_id, "objects": names})
    live_preview.mark_pending(context, label)
    live_preview.redraw(context)
    return {"ok": True, "message": "Retopology result imported for review", "objects": names,
            "transaction_id": transaction["id"], "report": metadata["report"], "animation_ready": False}


def unregister():
    if bpy.app.timers.is_registered(_poll):
        bpy.app.timers.unregister(_poll)
    for job_id, process in list(_PROCESSES.items()):
        if process.poll() is None:
            process_utils.terminate_process_tree(process)
            path = os.path.join(_JOB_DIRS[job_id], "metadata.json")
            metadata = _read(path)
            metadata.update(status="cancelled", message="Retopology job stopped during add-on shutdown/reload")
            job_runtime.write_json(path, metadata)
    _PROCESSES.clear()
    _JOB_DIRS.clear()
