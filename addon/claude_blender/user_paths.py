"""User-data paths for Blender extension runtime artifacts."""

from __future__ import annotations

import os
import tempfile

try:
    import bpy
except ImportError:  # Allows MCP/server-side imports outside Blender.
    bpy = None


LEGACY_BASE_DIR = os.path.join(os.path.expanduser("~"), ".claude_blender")
TEMP_BASE_DIR = os.path.join(tempfile.gettempdir(), "claude_blender")
WINDOWS_SAFE_PATH_LIMIT = 248
WINDOWS_USER_DATA_RESERVE = 128


def path_budget_exceeded(path, *, reserve=0, platform=None):
    platform = os.name if platform is None else str(platform)
    if platform != "nt":
        return False
    normalized = os.path.abspath(os.path.expanduser(str(path or "")))
    return len(normalized) + max(0, int(reserve)) >= WINDOWS_SAFE_PATH_LIMIT


def safe_path(path, *, fallback_parts=(), reserve=0, platform=None):
    normalized = os.path.abspath(os.path.expanduser(str(path or "")))
    if path_budget_exceeded(normalized, reserve=reserve, platform=platform):
        return legacy_user_data_path(*fallback_parts)
    return normalized


def temp_user_data_path(*parts):
    return os.path.join(TEMP_BASE_DIR, *[str(part) for part in parts if str(part)])


def _assert_writable_dir(path):
    probe = os.path.join(path, ".write-test-%s" % os.getpid())
    descriptor = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, b"ok")
    finally:
        os.close(descriptor)
    try:
        os.remove(probe)
    except OSError:
        pass


def ensure_dir(path, *, fallback_parts=()):
    normalized = os.path.abspath(os.path.expanduser(str(path or "")))
    try:
        os.makedirs(normalized, exist_ok=True)
        _assert_writable_dir(normalized)
        return normalized
    except OSError:
        fallback = temp_user_data_path(*fallback_parts)
        os.makedirs(fallback, exist_ok=True)
        _assert_writable_dir(fallback)
        return fallback


def _extension_user_root():
    if bpy is None:
        return ""
    extension_path_user = getattr(getattr(bpy, "utils", None), "extension_path_user", None)
    if not extension_path_user:
        return ""
    try:
        return extension_path_user(__package__, path="", create=True)
    except Exception:
        return ""


def user_data_dir(*parts, create=True):
    root = _extension_user_root() or LEGACY_BASE_DIR
    path_parts = [str(part) for part in parts if str(part)]
    path = safe_path(
        os.path.join(root, *path_parts),
        fallback_parts=path_parts,
        reserve=WINDOWS_USER_DATA_RESERVE,
    )
    if create:
        path = ensure_dir(path, fallback_parts=path_parts)
    return path


def user_data_path(*parts):
    return user_data_dir(*parts, create=False)


def legacy_user_data_path(*parts):
    return os.path.join(LEGACY_BASE_DIR, *[str(part) for part in parts if str(part)])


def register():
    pass


def unregister():
    pass
