"""Blend-file save/open/new-project helpers for external tools."""

from __future__ import annotations

import base64
import binascii
import hashlib
import itertools
import os
import re
import tempfile
import time

import bpy

from . import lab_parity, script_runner


DEFAULT_PROJECT_DIRS = ("assets", "refs", "renders", "exports")
MAX_PROJECT_FILE_BYTES = 4 * 1024 * 1024
MAX_PROJECT_FILE_BASE64_CHARS = ((MAX_PROJECT_FILE_BYTES + 2) // 3) * 4
PROJECT_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")
WINDOWS_RESERVED_FILE_NAMES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
BLOCKED_PROJECT_WRITE_SUFFIXES = {
    ".bat",
    ".blend",
    ".cmd",
    ".com",
    ".dll",
    ".dylib",
    ".exe",
    ".hta",
    ".jar",
    ".js",
    ".jse",
    ".lnk",
    ".msi",
    ".ps1",
    ".py",
    ".pyd",
    ".pyw",
    ".scr",
    ".sh",
    ".so",
    ".url",
    ".vbe",
    ".vbs",
    ".wsf",
    ".wsh",
}
USER_PATH_REQUIRED_MESSAGE = (
    "This operation needs a human-confirmed path. Ask the user for the .blend path or project folder, "
    "then retry with user_confirmed_path=true."
)


def _project_filesystem_unavailable(message):
    return {
        "ok": False,
        "blocked": True,
        "code": "project_filesystem_unavailable",
        "message": str(message),
        "project_root": "",
    }


def _project_root():
    filepath = getattr(bpy.data, "filepath", "") or ""
    if not filepath:
        return _project_filesystem_unavailable(
            "Project filesystem access requires a saved .blend file. Save the project to a user-confirmed path first."
        )
    absolute_file = os.path.abspath(filepath)
    root = os.path.realpath(os.path.dirname(absolute_file))
    if not os.path.isdir(root):
        return _project_filesystem_unavailable("The saved .blend project directory does not exist.")
    return {
        "ok": True,
        "project_root": root,
        "blend_path": absolute_file,
    }


def _normalized_project_relative_path(value, *, allow_root=False):
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return "" if allow_root else None
    if len(raw) > 1024:
        return None
    drive, _tail = os.path.splitdrive(raw)
    if drive or raw.startswith("/"):
        return None
    parts = [part for part in raw.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        return None
    if any(part.startswith(".") for part in parts):
        return None
    for part in parts:
        trimmed = part.rstrip(" .")
        device_stem = trimmed.split(".", 1)[0].upper()
        if (
            not trimmed
            or trimmed != part
            or ":" in part
            or any(ord(character) < 32 for character in part)
            or device_stem in WINDOWS_RESERVED_FILE_NAMES
            or re.fullmatch(r"(?:COM|LPT)[1-9]", device_stem)
        ):
            return None
    return os.path.join(*parts)


def _is_reparse_path(path):
    if os.path.islink(path):
        return True
    try:
        stat_result = os.lstat(path)
    except OSError:
        return False
    file_attributes = getattr(stat_result, "st_file_attributes", 0)
    reparse_flag = getattr(stat_result, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(file_attributes & reparse_flag)


def _is_hidden_path(path):
    if os.path.basename(path).startswith("."):
        return True
    if os.name != "nt":
        return False
    try:
        stat_result = os.lstat(path)
    except OSError:
        return False
    file_attributes = getattr(stat_result, "st_file_attributes", 0)
    hidden_flag = getattr(stat_result, "FILE_ATTRIBUTE_HIDDEN", 0x2)
    return bool(file_attributes & hidden_flag)


def _path_is_within(root, path):
    try:
        return os.path.normcase(os.path.commonpath([root, path])) == os.path.normcase(root)
    except ValueError:
        return False


def _existing_path_components_are_safe(root, path):
    relative = os.path.relpath(path, root)
    if relative == ".":
        return True, "", ""
    current = root
    for part in relative.split(os.sep):
        current = os.path.join(current, part)
        if not os.path.lexists(current):
            continue
        if _is_reparse_path(current):
            return False, current, "link"
        if _is_hidden_path(current):
            return False, current, "hidden"
    return True, "", ""


def _resolve_project_path(relative_path, *, allow_root=False, for_write=False):
    scope = _project_root()
    if not scope.get("ok"):
        return scope
    normalized = _normalized_project_relative_path(relative_path, allow_root=allow_root)
    if normalized is None:
        return {
            "ok": False,
            "blocked": True,
            "code": "project_path_outside_scope",
            "message": "Use a relative path inside the current saved .blend project directory; absolute, parent, and hidden paths are blocked.",
            "project_root": scope["project_root"],
            "relative_path": str(relative_path or ""),
        }
    candidate = os.path.abspath(os.path.join(scope["project_root"], normalized))
    resolved_candidate = os.path.realpath(candidate)
    if not _path_is_within(scope["project_root"], resolved_candidate):
        return {
            "ok": False,
            "blocked": True,
            "code": "project_path_outside_scope",
            "message": "The resolved path escapes the current project directory.",
            "project_root": scope["project_root"],
            "relative_path": str(relative_path or ""),
        }
    safe_components, unsafe_component, unsafe_kind = _existing_path_components_are_safe(
        scope["project_root"],
        candidate,
    )
    if not safe_components:
        return {
            "ok": False,
            "blocked": True,
            "code": (
                "project_path_hidden_blocked"
                if unsafe_kind == "hidden"
                else "project_path_link_blocked"
            ),
            "message": (
                "Hidden filesystem paths are not exposed by project-file tools."
                if unsafe_kind == "hidden"
                else "Symbolic links and filesystem reparse points are not followed by project-file tools."
            ),
            "project_root": scope["project_root"],
            "relative_path": normalized,
            "blocked_component": unsafe_component,
        }
    if for_write and os.path.splitext(candidate)[1].lower() in BLOCKED_PROJECT_WRITE_SUFFIXES:
        return {
            "ok": False,
            "blocked": True,
            "code": "project_file_type_blocked",
            "message": "Executable, script, library, and .blend files cannot be written through the generic project-file tool.",
            "project_root": scope["project_root"],
            "relative_path": normalized,
        }
    return {
        "ok": True,
        "project_root": scope["project_root"],
        "blend_path": scope["blend_path"],
        "relative_path": normalized,
        "path": candidate,
    }


def _ensure_project_parent(root, path):
    parent = os.path.dirname(path)
    if not _path_is_within(root, parent):
        return False, "Target parent escapes the current project directory"
    relative = os.path.relpath(parent, root)
    current = root
    if relative == ".":
        return True, ""
    for part in relative.split(os.sep):
        current = os.path.join(current, part)
        if os.path.lexists(current):
            if _is_reparse_path(current):
                return False, f"Project path component is a link or reparse point: {current}"
            if not os.path.isdir(current):
                return False, f"Project path component is not a directory: {current}"
        else:
            try:
                os.mkdir(current)
            except OSError as exc:
                return False, f"Could not create project directory: {type(exc).__name__}: {exc}"
    return True, ""


def list_project_files(*, relative_path="", recursive=False, max_entries=200):
    resolved = _resolve_project_path(relative_path, allow_root=True)
    if not resolved.get("ok"):
        return resolved
    directory = resolved["path"]
    if not os.path.isdir(directory):
        return {**resolved, "ok": False, "message": "Project directory not found"}
    limit = max(1, min(int(max_entries or 200), 1000))
    entries = []
    truncated = False

    def visit(current):
        nonlocal truncated
        remaining = limit - len(entries)
        if remaining <= 0:
            truncated = True
            return
        try:
            with os.scandir(current) as iterator:
                children = list(itertools.islice(iterator, remaining + 1))
        except OSError as exc:
            raise RuntimeError(f"Could not list project directory: {type(exc).__name__}: {exc}") from exc
        if len(children) > remaining:
            truncated = True
            children = children[:remaining]
        children.sort(key=lambda item: item.name.lower())
        for entry in children:
            if _is_hidden_path(entry.path):
                continue
            if len(entries) >= limit:
                return
            relative = os.path.relpath(entry.path, resolved["project_root"])
            is_link = _is_reparse_path(entry.path)
            is_dir = entry.is_dir(follow_symlinks=False)
            item = {
                "relative_path": relative,
                "name": entry.name,
                "type": "link" if is_link else ("directory" if is_dir else "file"),
            }
            if not is_dir and not is_link:
                try:
                    item["size_bytes"] = entry.stat(follow_symlinks=False).st_size
                except OSError:
                    item["size_bytes"] = None
            entries.append(item)
            if recursive and is_dir and not is_link:
                visit(entry.path)
                if len(entries) >= limit:
                    return

    try:
        visit(directory)
    except RuntimeError as exc:
        return {**resolved, "ok": False, "message": str(exc)}
    return {
        **resolved,
        "message": "Project files listed",
        "entries": entries,
        "entry_count": len(entries),
        "truncated": truncated,
        "recursive": bool(recursive),
    }


def read_project_file(*, relative_path, encoding="utf-8", max_bytes=1_048_576):
    resolved = _resolve_project_path(relative_path)
    if not resolved.get("ok"):
        return resolved
    path = resolved["path"]
    if not os.path.isfile(path):
        return {**resolved, "ok": False, "message": "Project file not found"}
    try:
        link_count = os.stat(path, follow_symlinks=False).st_nlink
    except OSError as exc:
        return {**resolved, "ok": False, "message": f"Could not inspect project file: {type(exc).__name__}: {exc}"}
    if link_count > 1:
        return {
            **resolved,
            "ok": False,
            "blocked": True,
            "code": "project_path_link_blocked",
            "message": "Files with multiple hard links are not read by project-file tools.",
            "link_count": link_count,
        }
    limit = max(1, min(int(max_bytes or 1_048_576), MAX_PROJECT_FILE_BYTES))
    size = os.path.getsize(path)
    if size > limit:
        return {
            **resolved,
            "ok": False,
            "code": "project_file_too_large",
            "message": f"Project file is {size} bytes; the requested read limit is {limit} bytes.",
            "size_bytes": size,
            "max_bytes": limit,
        }
    with open(path, "rb") as handle:
        payload = handle.read(limit + 1)
    if len(payload) > limit:
        return {**resolved, "ok": False, "code": "project_file_too_large", "message": "Project file exceeded the read limit."}
    normalized_encoding = str(encoding or "utf-8").strip().lower()
    if normalized_encoding == "base64":
        content = base64.b64encode(payload).decode("ascii")
    elif normalized_encoding == "utf-8":
        try:
            content = payload.decode("utf-8")
        except UnicodeDecodeError:
            return {
                **resolved,
                "ok": False,
                "code": "project_file_not_utf8",
                "message": "Project file is not valid UTF-8; retry with encoding=base64.",
                "size_bytes": len(payload),
            }
    else:
        return {**resolved, "ok": False, "message": "encoding must be utf-8 or base64"}
    return {
        **resolved,
        "message": "Project file read",
        "encoding": normalized_encoding,
        "content": content,
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def write_project_file(*, relative_path, content, encoding="utf-8", overwrite=False, create_dirs=True):
    resolved = _resolve_project_path(relative_path, for_write=True)
    if not resolved.get("ok"):
        return resolved
    normalized_encoding = str(encoding or "utf-8").strip().lower()
    content_text = str(content or "")
    try:
        if normalized_encoding == "base64":
            if len(content_text) > MAX_PROJECT_FILE_BASE64_CHARS:
                return {
                    **resolved,
                    "ok": False,
                    "code": "project_file_too_large",
                    "message": f"Base64 project-file writes are limited to {MAX_PROJECT_FILE_BASE64_CHARS} encoded characters.",
                }
            payload = base64.b64decode(content_text, validate=True)
        elif normalized_encoding == "utf-8":
            if len(content_text) > MAX_PROJECT_FILE_BYTES:
                return {
                    **resolved,
                    "ok": False,
                    "code": "project_file_too_large",
                    "message": f"Project-file writes are limited to {MAX_PROJECT_FILE_BYTES} bytes.",
                }
            payload = content_text.encode("utf-8")
        else:
            return {**resolved, "ok": False, "message": "encoding must be utf-8 or base64"}
    except (binascii.Error, ValueError) as exc:
        return {**resolved, "ok": False, "message": f"Invalid base64 content: {exc}"}
    if len(payload) > MAX_PROJECT_FILE_BYTES:
        return {
            **resolved,
            "ok": False,
            "code": "project_file_too_large",
            "message": f"Project-file writes are limited to {MAX_PROJECT_FILE_BYTES} bytes.",
            "size_bytes": len(payload),
            "max_bytes": MAX_PROJECT_FILE_BYTES,
        }
    path = resolved["path"]
    if os.path.isdir(path):
        return {**resolved, "ok": False, "message": "Target path is a directory"}
    if os.path.exists(path) and not bool(overwrite):
        return {
            **resolved,
            "ok": False,
            "code": "project_file_exists",
            "message": "Project file already exists; pass overwrite=true to replace it.",
            "exists": True,
        }
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        if not bool(create_dirs):
            return {**resolved, "ok": False, "message": "Target project directory does not exist"}
        created, error = _ensure_project_parent(resolved["project_root"], path)
        if not created:
            return {**resolved, "ok": False, "message": error}
    safe_components, unsafe_component, unsafe_kind = _existing_path_components_are_safe(
        resolved["project_root"],
        path,
    )
    if not safe_components:
        return {
            **resolved,
            "ok": False,
            "blocked": True,
            "code": (
                "project_path_hidden_blocked"
                if unsafe_kind == "hidden"
                else "project_path_link_blocked"
            ),
            "message": (
                "A project path component became hidden before the write."
                if unsafe_kind == "hidden"
                else "A project path component became a link or reparse point before the write."
            ),
            "blocked_component": unsafe_component,
        }
    temp_path = ""
    try:
        descriptor, temp_path = tempfile.mkstemp(prefix=".agent-bridge-write-", dir=parent)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if bool(overwrite):
            os.replace(temp_path, path)
            temp_path = ""
        else:
            try:
                os.link(temp_path, path)
            except FileExistsError:
                return {
                    **resolved,
                    "ok": False,
                    "code": "project_file_exists",
                    "message": "Project file already exists; pass overwrite=true to replace it.",
                    "exists": True,
                }
            except OSError:
                with open(path, "xb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
            os.unlink(temp_path)
            temp_path = ""
    except Exception as exc:
        return {**resolved, "ok": False, "message": f"Project-file write failed: {type(exc).__name__}: {exc}"}
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
    return {
        **resolved,
        "message": "Project file written",
        "encoding": normalized_encoding,
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "overwrote": bool(overwrite),
    }


def _abspath(path):
    raw = str(path or "").strip()
    if not raw:
        return ""
    expanded = os.path.expanduser(bpy.path.abspath(raw))
    return os.path.abspath(expanded)


def _is_blend_path(path):
    return bool(str(path or "").lower().endswith(".blend"))


def _safe_project_name(value):
    name = PROJECT_NAME_RE.sub("_", str(value or "").strip())
    name = name.strip(" ._")
    return name[:80] or "untitled-project"


def _safe_project_subdir(value):
    raw = str(value or "").strip().replace("\\", "/").strip("/")
    if not raw or os.path.isabs(raw) or ":" in raw:
        return ""
    parts = [part.strip() for part in raw.split("/") if part.strip()]
    if not parts or any(part in {".", ".."} for part in parts):
        return ""
    return os.path.join(*parts)


def _current_state():
    filepath = getattr(bpy.data, "filepath", "") or ""
    absolute = os.path.abspath(filepath) if filepath else ""
    return {
        "filepath": filepath,
        "absolute_path": absolute,
        "is_saved": bool(filepath),
        "exists": bool(absolute and os.path.isfile(absolute)),
        "is_dirty": bool(getattr(bpy.data, "is_dirty", False)),
    }


def _ensure_parent_dir(path, *, create_dirs):
    directory = os.path.dirname(path)
    if not directory:
        return {"ok": False, "message": "Target path must include a directory", "directory": directory}
    if os.path.isdir(directory):
        return {"ok": True, "directory": directory}
    if not create_dirs:
        return {"ok": False, "message": f"Target directory does not exist: {directory}", "directory": directory}
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "message": f"Could not create target directory: {type(exc).__name__}: {exc}", "directory": directory}
    return {"ok": True, "directory": directory}


def _user_path_required_payload(*, path="", before=None):
    return {
        "ok": False,
        "code": "user_path_required",
        "message": USER_PATH_REQUIRED_MESSAGE,
        "path": path,
        "human_in_loop_required": True,
        "requires_user_confirmed_path": True,
        "before": before or _current_state(),
    }


def _checkpoint_before_replace(context, *, create_checkpoint=True, require_checkpoint=True, checkpoint_dir=None):
    if not bool(create_checkpoint):
        return {"ok": False, "requested": False, "message": "Checkpoint disabled", "path": ""}
    checkpoint = script_runner.create_checkpoint(context, checkpoint_dir=checkpoint_dir)
    checkpoint["requested"] = True
    if not checkpoint.get("ok") and bool(require_checkpoint):
        checkpoint["blocking"] = True
    return checkpoint


def _clear_scene_runtime_state(message):
    script_runner.clear_external_script_trust_for_all_scenes(
        status=script_runner.NO_EXTERNAL_TRUST_STATUS,
        audit_action="clear_on_project_file_change",
    )
    state = getattr(getattr(bpy.context, "scene", None), "claude_blender", None)
    if not state:
        return
    state.pending_preview = False
    state.pending_preview_label = ""
    state.pending_preview_summary = ""
    state.pending_preview_warnings = ""
    state.status = str(message or "Project file operation finished")


def _run_open_mainfile(path, *, load_ui=False):
    try:
        return bpy.ops.wm.open_mainfile(filepath=path, load_ui=bool(load_ui))
    except TypeError:
        return bpy.ops.wm.open_mainfile(filepath=path)


def _run_read_homefile(*, template="default"):
    normalized = str(template or "default").strip().lower().replace("-", "_")
    kwargs = {}
    if normalized == "empty":
        kwargs["use_empty"] = True
    elif normalized in {"factory", "factory_startup", "factory-startup"}:
        kwargs["use_factory_startup"] = True
    try:
        return bpy.ops.wm.read_homefile(**kwargs)
    except TypeError:
        return bpy.ops.wm.read_homefile()


def _save_result_payload(path, *, operation, operator_result, before, copy, path_source):
    exists = os.path.isfile(path)
    diagnostics = lab_parity.get_blend_file_diagnostics(bpy.context)
    return {
        "ok": bool(exists),
        "message": f"Blend file {operation} complete" if exists else f"Blend file {operation} did not create a file",
        "operation": operation,
        "path": path,
        "path_source": path_source,
        "copy": bool(copy),
        "operator_result": sorted(str(item) for item in operator_result),
        "size_bytes": os.path.getsize(path) if exists else 0,
        "before": before,
        "after": _current_state(),
        "diagnostics": diagnostics,
    }


def save_blend_file(context, *, filepath="", copy=False, overwrite=False, create_dirs=True, user_confirmed_path=False):
    before = _current_state()
    target = _abspath(filepath) if str(filepath or "").strip() else before["absolute_path"]
    requested_path = bool(str(filepath or "").strip())
    copy = bool(copy)
    if not target:
        return _user_path_required_payload(before=before)
    if not _is_blend_path(target):
        return {"ok": False, "message": "Blend file path must end with .blend", "path": target, "before": before}
    if copy and not requested_path:
        return {"ok": False, "message": "Saving a copy requires an explicit filepath", "path": target, "before": before}
    current = before["absolute_path"]
    same_current = bool(current and os.path.normcase(current) == os.path.normcase(target))
    path_changes_binding = bool(requested_path and not same_current)
    if path_changes_binding and not bool(user_confirmed_path):
        return _user_path_required_payload(path=target, before=before)
    if copy and same_current:
        return {"ok": False, "message": "Save-copy target must differ from the active blend file", "path": target, "before": before}
    parent = _ensure_parent_dir(target, create_dirs=bool(create_dirs))
    if not parent.get("ok"):
        return {"ok": False, **parent, "path": target, "before": before}
    exists = os.path.isfile(target)
    if exists and not bool(overwrite) and requested_path and not same_current:
        return {
            "ok": False,
            "message": "Target blend file already exists; pass overwrite=true to replace it",
            "path": target,
            "exists": True,
            "before": before,
        }
    try:
        operator_result = bpy.ops.wm.save_as_mainfile(filepath=target, check_existing=False, copy=copy)
    except Exception as exc:
        return {
            "ok": False,
            "message": f"Blend file save failed: {type(exc).__name__}: {exc}",
            "path": target,
            "before": before,
        }
    return _save_result_payload(
        target,
        operation="copy save" if copy else ("save-as" if requested_path and not same_current else "save"),
        operator_result=operator_result,
        before=before,
        copy=copy,
        path_source="user_confirmed" if path_changes_binding else "active_blend_binding",
    )


def open_blend_file(
    context,
    *,
    filepath,
    confirm_discard_current=False,
    create_checkpoint=True,
    require_checkpoint=True,
    checkpoint_dir=None,
    load_ui=False,
    user_confirmed_path=False,
):
    before = _current_state()
    path = _abspath(filepath)
    if not bool(confirm_discard_current):
        return {
            "ok": False,
            "message": "Opening a blend file replaces the active Blender session; pass confirm_discard_current=true",
            "path": path,
            "before": before,
        }
    if not path:
        return {"ok": False, "message": "A filepath is required", "before": before}
    if not bool(user_confirmed_path):
        return _user_path_required_payload(path=path, before=before)
    if not _is_blend_path(path):
        return {"ok": False, "message": "Blend file path must end with .blend", "path": path, "before": before}
    if not os.path.isfile(path):
        return {"ok": False, "message": f"Blend file not found: {path}", "path": path, "before": before}
    checkpoint = _checkpoint_before_replace(
        context,
        create_checkpoint=create_checkpoint,
        require_checkpoint=require_checkpoint,
        checkpoint_dir=checkpoint_dir,
    )
    if checkpoint.get("blocking"):
        return {
            "ok": False,
            "message": checkpoint.get("message", "Checkpoint failed; open was not attempted"),
            "path": path,
            "checkpoint": checkpoint,
            "before": before,
        }
    started_at = time.time()
    try:
        operator_result = _run_open_mainfile(path, load_ui=bool(load_ui))
    except Exception as exc:
        return {
            "ok": False,
            "message": f"Blend file open failed: {type(exc).__name__}: {exc}",
            "path": path,
            "checkpoint": checkpoint,
            "before": before,
        }
    _clear_scene_runtime_state(f"Opened blend file: {path}")
    diagnostics = lab_parity.get_blend_file_diagnostics(bpy.context)
    return {
        "ok": True,
        "message": "Blend file opened",
        "path": path,
        "path_source": "user_confirmed",
        "operator_result": sorted(str(item) for item in operator_result),
        "elapsed_seconds": round(time.time() - started_at, 3),
        "checkpoint": checkpoint,
        "before": before,
        "after": _current_state(),
        "diagnostics": diagnostics,
    }


def create_new_blender_project(
    context,
    *,
    project_dir="",
    project_name="",
    filepath="",
    template="default",
    create_standard_dirs=True,
    standard_dirs=None,
    overwrite=False,
    create_dirs=True,
    confirm_discard_current=False,
    create_checkpoint=True,
    require_checkpoint=True,
    checkpoint_dir=None,
    user_confirmed_path=False,
):
    before = _current_state()
    requested_project_name = str(project_name or "").strip()
    safe_name = _safe_project_name(requested_project_name)
    target = _abspath(filepath)
    if target:
        project_root = os.path.dirname(target)
        safe_name = _safe_project_name(project_name or os.path.splitext(os.path.basename(target))[0])
    else:
        root = _abspath(project_dir)
        if not root:
            return {"ok": False, "message": "project_dir or filepath is required", "before": before}
        if not requested_project_name:
            safe_name = _safe_project_name(os.path.basename(os.path.normpath(root)))
            project_root = root
        else:
            project_root = os.path.join(root, safe_name) if os.path.basename(root).lower() != safe_name.lower() else root
        target = os.path.join(project_root, f"{safe_name}.blend")
    if not bool(confirm_discard_current):
        return {
            "ok": False,
            "message": "Creating a new project replaces the active Blender session; pass confirm_discard_current=true",
            "path": target,
            "before": before,
        }
    if not bool(user_confirmed_path):
        return _user_path_required_payload(path=target, before=before)
    if not _is_blend_path(target):
        return {"ok": False, "message": "Blend file path must end with .blend", "path": target, "before": before}
    parent = _ensure_parent_dir(target, create_dirs=bool(create_dirs))
    if not parent.get("ok"):
        return {"ok": False, **parent, "path": target, "before": before}
    if os.path.isfile(target) and not bool(overwrite):
        return {
            "ok": False,
            "message": "Project blend file already exists; pass overwrite=true to replace it",
            "path": target,
            "exists": True,
            "before": before,
        }
    checkpoint = _checkpoint_before_replace(
        context,
        create_checkpoint=create_checkpoint,
        require_checkpoint=require_checkpoint,
        checkpoint_dir=checkpoint_dir,
    )
    if checkpoint.get("blocking"):
        return {
            "ok": False,
            "message": checkpoint.get("message", "Checkpoint failed; new project was not created"),
            "path": target,
            "checkpoint": checkpoint,
            "before": before,
        }
    created_dirs = []
    started_at = time.time()
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if bool(create_standard_dirs):
            requested_dirs = standard_dirs if isinstance(standard_dirs, (list, tuple)) else DEFAULT_PROJECT_DIRS
            for item in requested_dirs:
                name = _safe_project_subdir(item)
                if not name:
                    continue
                path = os.path.join(os.path.dirname(target), name)
                os.makedirs(path, exist_ok=True)
                created_dirs.append(path)
        read_result = _run_read_homefile(template=template)
        if safe_name and getattr(bpy.context, "scene", None):
            bpy.context.scene.name = safe_name[:63]
        save_result = bpy.ops.wm.save_as_mainfile(filepath=target, check_existing=False)
    except Exception as exc:
        return {
            "ok": False,
            "message": f"New project creation failed: {type(exc).__name__}: {exc}",
            "path": target,
            "checkpoint": checkpoint,
            "created_dirs": created_dirs,
            "before": before,
        }
    _clear_scene_runtime_state(f"Created new Blender project: {target}")
    diagnostics = lab_parity.get_blend_file_diagnostics(bpy.context)
    return {
        "ok": bool(os.path.isfile(target)),
        "message": "New Blender project created" if os.path.isfile(target) else "New project save did not create a blend file",
        "project_name": safe_name,
        "project_dir": os.path.dirname(target),
        "path": target,
        "path_source": "user_confirmed",
        "template": str(template or "default"),
        "created_dirs": created_dirs,
        "operator_result": {
            "read_homefile": sorted(str(item) for item in read_result),
            "save_as_mainfile": sorted(str(item) for item in save_result),
        },
        "elapsed_seconds": round(time.time() - started_at, 3),
        "checkpoint": checkpoint,
        "before": before,
        "after": _current_state(),
        "diagnostics": diagnostics,
    }


def register():
    pass


def unregister():
    pass
