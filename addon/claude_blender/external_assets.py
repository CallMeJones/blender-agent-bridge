"""External asset catalog, cache, and preview import helpers."""

from __future__ import annotations

import json
import hashlib
import calendar
import os
import re
import shutil
import time
import urllib.parse
import urllib.request
import zipfile

try:
    import bpy
except ImportError:  # Allows pure-Python smoke tests outside Blender.
    bpy = None

try:
    from . import blender_compat
except ImportError:  # Direct-script compatibility inside Blender.
    import blender_compat

try:
    from . import live_preview
except ImportError:  # Pure-Python registry/runtime imports must never require bpy.
    live_preview = None

try:
    from . import user_paths
except ImportError:
    user_paths = None


def _env_url(name, default):
    return str(os.environ.get(name) or default).rstrip("/")


POLY_HAVEN_BASE_URL = _env_url("BLENDER_AGENT_BRIDGE_POLY_HAVEN_BASE_URL", "https://api.polyhaven.com")
POLY_HAVEN_SITE_URL = _env_url("BLENDER_AGENT_BRIDGE_POLY_HAVEN_SITE_URL", "https://polyhaven.com")
SKETCHFAB_BASE_URL = _env_url("BLENDER_AGENT_BRIDGE_SKETCHFAB_BASE_URL", "https://api.sketchfab.com/v3")
USER_AGENT = "BlenderAgentBridge/0.1 (+https://github.com/CallMeJones/blender-agent-bridge)"
DOWNLOAD_RETRY_COUNT = 2
DOWNLOAD_RETRY_BACKOFF_SECONDS = 0.5
MAX_ZIP_MEMBER_COUNT = 20_000
MAX_ZIP_EXTRACTED_BYTES = 4 * 1024 * 1024 * 1024
MAX_ZIP_MEMBER_BYTES = 2 * 1024 * 1024 * 1024
MAX_ZIP_PATH_DEPTH = 32
MAX_ZIP_COMPRESSION_RATIO = 200
MIN_ZIP_RATIO_CHECK_BYTES = 10 * 1024 * 1024
POLY_HAVEN_LICENSE = "CC0"
SKETCHFAB_TOKEN_ENV_VAR = "SKETCHFAB_API_TOKEN"
SKETCHFAB_BRIDGE_TOKEN_ENV_VAR = "BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN"
SKETCHFAB_API_TOKEN_ENV_VARS = (SKETCHFAB_TOKEN_ENV_VAR, SKETCHFAB_BRIDGE_TOKEN_ENV_VAR)
SKETCHFAB_ALLOWED_TOKEN_ENV_VARS = frozenset(SKETCHFAB_API_TOKEN_ENV_VARS)
ASSET_KEY_PROPERTY = "blender_agent_bridge_asset_key"
ASSET_PROVIDER_PROPERTY = "blender_agent_bridge_asset_provider"
ASSET_SOURCE_URL_PROPERTY = "blender_agent_bridge_asset_source_url"
_SESSION_SKETCHFAB_API_TOKEN = ""


def set_session_sketchfab_api_token(value):
    """Keep Sketchfab auth in this Blender process only."""

    global _SESSION_SKETCHFAB_API_TOKEN
    _SESSION_SKETCHFAB_API_TOKEN = str(value or "").strip()
    return bool(_SESSION_SKETCHFAB_API_TOKEN)


def clear_session_sketchfab_api_token():
    global _SESSION_SKETCHFAB_API_TOKEN
    _SESSION_SKETCHFAB_API_TOKEN = ""


def session_sketchfab_api_token():
    return _SESSION_SKETCHFAB_API_TOKEN


def _bounded_limit(value, default=20, *, maximum=50):
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = int(default)
    return max(1, min(int(maximum), result))


def _auth_env_candidates(preferred, *, defaults, allowed):
    preferred = str(preferred or "").strip()
    if preferred:
        if preferred not in allowed:
            return [], preferred
        candidates = [preferred]
        if preferred == defaults[0]:
            candidates.extend(name for name in defaults[1:] if name not in candidates)
        return candidates, ""
    return list(defaults), ""


def _first_env_token(preferred, *, defaults, allowed, environ=None):
    candidates, blocked = _auth_env_candidates(preferred, defaults=defaults, allowed=allowed)
    if blocked:
        return "", "", blocked, candidates
    source = environ if environ is not None else os.environ
    for name in candidates:
        value = str(source.get(name, "") or "").strip()
        if value:
            return value, name, "", candidates
    return "", "", "", candidates


def _present_auth_env_names(environ=None):
    source = environ if environ is not None else os.environ
    return [
        name
        for name in SKETCHFAB_API_TOKEN_ENV_VARS
        if str(source.get(name, "") or "").strip()
    ]


def sketchfab_auth_diagnostics(environ=None):
    """Report Sketchfab auth availability without exposing credential values."""

    configured = _present_auth_env_names(environ=environ)
    session_configured = bool(session_sketchfab_api_token())
    api_token_configured = session_configured or any(name in configured for name in SKETCHFAB_API_TOKEN_ENV_VARS)
    return {
        "provider": "sketchfab",
        "auth_method": "api_token",
        "ready": bool(api_token_configured),
        "api_token_configured": bool(api_token_configured),
        "session_token_configured": session_configured,
        "configured_env_vars": configured,
        "api_token_env_vars": list(SKETCHFAB_API_TOKEN_ENV_VARS),
        "message": (
            "Sketchfab API token is configured for this Blender session."
            if session_configured
            else "Sketchfab API token is configured."
            if api_token_configured
            else "No Sketchfab API token env var is configured."
        ),
    }


def sketchfab_auth_arguments_from_env(arguments, *, environ=None):
    """Copy arguments and inject MCP-process env credentials for bridge calls."""

    result = dict(arguments or {})
    if str(result.get("api_token") or "").strip():
        return result
    api_token, _api_env, blocked, _candidates = _first_env_token(
        result.get("token_env_var") or SKETCHFAB_TOKEN_ENV_VAR,
        defaults=SKETCHFAB_API_TOKEN_ENV_VARS,
        allowed=SKETCHFAB_ALLOWED_TOKEN_ENV_VARS,
        environ=environ,
    )
    if blocked:
        return result
    if api_token:
        result["api_token"] = api_token
    return result


def _default_cache_dir():
    if user_paths is not None:
        return user_paths.user_data_path("assets")
    return os.path.join(os.path.expanduser("~"), ".claude_blender", "assets")


def _is_loopback_url(url):
    try:
        host = (urllib.parse.urlparse(str(url or "")).hostname or "").lower()
    except Exception:
        return False
    return host in {"localhost", "::1"} or host.startswith("127.")


def _online_access_error(provider="external asset", url=""):
    if _is_loopback_url(url):
        return None
    if bpy is None or bool(getattr(bpy.app, "online_access", True)):
        return None
    overridden = bool(getattr(bpy.app, "online_access_overriden", False))
    if overridden:
        message = f"{provider} download requires online access, but Blender was started in offline mode."
    else:
        message = f"{provider} download requires online access; enable Allow Online Access in Blender preferences."
    return {
        "ok": False,
        "message": message,
        "error_type": "online_access_disabled",
        "online_access": False,
        "online_access_overridden": overridden,
    }


def _fetch_json(url, *, timeout=15):
    offline_error = _online_access_error("External asset metadata", url=url)
    if offline_error:
        raise RuntimeError(offline_error["message"])
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=max(1, int(timeout or 15))) as response:
        data = response.read()
    return json.loads(data.decode("utf-8"))


def _fetch_json_with_headers(url, *, headers=None, timeout=15):
    offline_error = _online_access_error("External asset metadata", url=url)
    if offline_error:
        raise RuntimeError(offline_error["message"])
    merged = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    merged.update(headers or {})
    request = urllib.request.Request(url, headers=merged)
    with urllib.request.urlopen(request, timeout=max(1, int(timeout or 15))) as response:
        data = response.read()
    return json.loads(data.decode("utf-8"))


def _fetch_json_result(provider, url, *, timeout=15):
    try:
        return _fetch_json(url, timeout=timeout), None
    except Exception as exc:
        return None, {
            "ok": False,
            "message": f"{provider} request failed: {type(exc).__name__}: {exc}",
            "provider": provider,
            "source_url": url,
            "error_type": type(exc).__name__,
        }


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sanitize_slug(value, fallback="asset"):
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()).strip("._-")
    return text[:120] or fallback


def _cache_root(cache_dir=""):
    root = os.path.abspath(os.path.expanduser(str(cache_dir or _default_cache_dir())))
    os.makedirs(root, exist_ok=True)
    return root


def _asset_cache_dir(provider, asset_id, cache_dir=""):
    root = _cache_root(cache_dir)
    directory = os.path.join(root, _sanitize_slug(provider, "provider"), _sanitize_slug(asset_id))
    os.makedirs(directory, exist_ok=True)
    return directory


def _manifest_path(asset_dir):
    return os.path.join(asset_dir, "asset_manifest.json")


def _write_manifest(asset_dir, manifest):
    manifest = dict(manifest)
    manifest.setdefault("created_at", _now())
    manifest["updated_at"] = _now()
    manifest["cache_dir"] = asset_dir
    path = _manifest_path(asset_dir)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    manifest["manifest_path"] = path
    return manifest


def _read_manifest(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        data["manifest_path"] = path
        return data
    except Exception as exc:
        return {"ok": False, "manifest_path": path, "message": f"Manifest read failed: {type(exc).__name__}: {exc}"}


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _md5_file(path):
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _filename_from_url(url, fallback):
    parsed = urllib.parse.urlparse(str(url or ""))
    name = os.path.basename(parsed.path)
    return _sanitize_slug(urllib.parse.unquote(name), fallback=fallback)


def _expected_size_int(expected_size):
    try:
        return int(expected_size) if expected_size is not None else 0
    except (TypeError, ValueError):
        return 0


def _cached_file_valid(path, *, expected_md5="", expected_size=None):
    if not os.path.exists(path):
        return False
    size = os.path.getsize(path)
    expected_size_value = _expected_size_int(expected_size)
    if expected_size_value and size != expected_size_value:
        return False
    if expected_md5 and _md5_file(path).lower() != str(expected_md5).lower():
        return False
    return True


def _emit_download_progress(progress_callback, payload):
    if not progress_callback:
        return
    try:
        progress_callback(payload)
    except Exception:
        pass


def _download_file(url, destination, *, expected_md5="", expected_size=None, headers=None, timeout=60, progress_callback=None):
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    expected_size_value = _expected_size_int(expected_size)
    partial_path = f"{destination}.part"
    cached = _cached_file_valid(destination, expected_md5=expected_md5, expected_size=expected_size_value or None)
    if cached:
        size = os.path.getsize(destination)
        md5 = _md5_file(destination) if os.path.exists(destination) else ""
        return {
            "ok": True,
            "url": str(url),
            "path": destination,
            "cached": True,
            "resumed": False,
            "attempts": 0,
            "partial_path": partial_path,
            "size": size,
            "md5": md5,
            "sha256": _sha256_file(destination),
        }

    if os.path.exists(destination):
        try:
            os.remove(destination)
        except OSError:
            pass
    if os.path.exists(partial_path) and expected_size_value and os.path.getsize(partial_path) > expected_size_value:
        try:
            os.remove(partial_path)
        except OSError:
            pass

    resumed = False
    attempts = 0
    http_status = 0
    max_attempts = max(1, DOWNLOAD_RETRY_COUNT + 1)
    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        offline_error = _online_access_error("External asset file", url=url)
        if offline_error:
            offline_error["url"] = str(url)
            offline_error["path"] = destination
            offline_error["partial_path"] = partial_path
            return offline_error
        partial_size = os.path.getsize(partial_path) if os.path.exists(partial_path) else 0
        request_headers = {"User-Agent": USER_AGENT, **(headers or {})}
        if partial_size and not any(str(key).lower() == "range" for key in request_headers):
            request_headers["Range"] = f"bytes={partial_size}-"
        try:
            request = urllib.request.Request(str(url), headers=request_headers)
            with urllib.request.urlopen(request, timeout=max(1, int(timeout or 60))) as response:
                http_status = int(getattr(response, "status", 0) or response.getcode() or 0)
                if partial_size and http_status == 206:
                    mode = "ab"
                    resumed = True
                else:
                    mode = "wb"
                    if partial_size and http_status == 200:
                        resumed = False
                with open(partial_path, mode) as handle:
                    bytes_downloaded = partial_size if mode == "ab" else 0
                    _emit_download_progress(
                        progress_callback,
                        {
                            "phase": "download",
                            "url": str(url),
                            "path": destination,
                            "partial_path": partial_path,
                            "bytes_downloaded": bytes_downloaded,
                            "expected_size": expected_size_value,
                            "attempt": attempts,
                            "resumed": bool(mode == "ab"),
                        },
                    )
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        bytes_downloaded += len(chunk)
                        _emit_download_progress(
                            progress_callback,
                            {
                                "phase": "download",
                                "url": str(url),
                                "path": destination,
                                "partial_path": partial_path,
                                "bytes_downloaded": bytes_downloaded,
                                "expected_size": expected_size_value,
                                "attempt": attempts,
                                "resumed": bool(mode == "ab"),
                            },
                        )
            os.replace(partial_path, destination)
            break
        except Exception as exc:
            if attempt >= max_attempts:
                return {
                    "ok": False,
                    "message": f"Download failed for {destination}: {type(exc).__name__}: {exc}",
                    "url": str(url),
                    "path": destination,
                    "partial_path": partial_path,
                    "partial_size": os.path.getsize(partial_path) if os.path.exists(partial_path) else 0,
                    "attempts": attempts,
                    "resumed": resumed,
                    "http_status": http_status,
                    "error_type": type(exc).__name__,
                }
            time.sleep(DOWNLOAD_RETRY_BACKOFF_SECONDS * attempt)

    size = os.path.getsize(destination)
    md5 = _md5_file(destination) if os.path.exists(destination) else ""
    if expected_size_value and size != expected_size_value:
        return {
            "ok": False,
            "message": f"Downloaded size mismatch for {destination}",
            "path": destination,
            "expected_size": expected_size_value,
            "size": size,
            "partial_path": partial_path,
            "attempts": attempts,
            "resumed": resumed,
            "http_status": http_status,
        }
    if expected_md5 and md5.lower() != str(expected_md5).lower():
        return {
            "ok": False,
            "message": f"Downloaded MD5 mismatch for {destination}",
            "path": destination,
            "expected_md5": str(expected_md5),
            "md5": md5,
            "partial_path": partial_path,
            "attempts": attempts,
            "resumed": resumed,
            "http_status": http_status,
        }
    return {
        "ok": True,
        "url": str(url),
        "path": destination,
        "cached": False,
        "resumed": resumed,
        "attempts": attempts,
        "partial_path": partial_path,
        "http_status": http_status,
        "size": size,
        "md5": md5,
        "sha256": _sha256_file(destination),
    }


def _poly_haven_type(asset_type):
    value = str(asset_type or "all").strip().lower()
    aliases = {
        "all": "all",
        "hdri": "hdris",
        "hdris": "hdris",
        "texture": "textures",
        "textures": "textures",
        "model": "models",
        "models": "models",
    }
    return aliases.get(value, "all")


def _poly_haven_category_items(payload):
    if isinstance(payload, dict):
        return [
            {
                "slug": str(key),
                "name": str(key).replace("_", " ").title(),
                "count": int(value or 0) if isinstance(value, int) else None,
            }
            for key, value in sorted(payload.items())
        ]
    if isinstance(payload, list):
        items = []
        for item in payload:
            if isinstance(item, dict):
                slug = str(item.get("slug") or item.get("name") or "")
                items.append({"slug": slug, "name": str(item.get("name") or slug), "count": item.get("count")})
            else:
                slug = str(item)
                items.append({"slug": slug, "name": slug.replace("_", " ").title(), "count": None})
        return items
    return []


def _string_list(value):
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def list_poly_haven_categories(*, asset_type="all", timeout=15):
    asset_type = _poly_haven_type(asset_type)
    asset_types = ["hdris", "textures", "models"] if asset_type == "all" else [asset_type]
    groups = []
    for current_type in asset_types:
        url = f"{POLY_HAVEN_BASE_URL}/categories/{urllib.parse.quote(current_type)}"
        payload, error = _fetch_json_result("poly_haven", url, timeout=timeout)
        if error:
            error["groups"] = groups
            error["failed_asset_type"] = current_type
            return error
        groups.append({"asset_type": current_type, "categories": _poly_haven_category_items(payload)})
    return {
        "ok": True,
        "message": "Poly Haven categories fetched",
        "provider": "poly_haven",
        "source_url": POLY_HAVEN_BASE_URL,
        "groups": groups,
    }


def _poly_haven_assets(payload):
    if isinstance(payload, dict):
        iterable = payload.items()
    elif isinstance(payload, list):
        iterable = (
            ((item.get("id") or item.get("slug") or item.get("name") or ""), item)
            for item in payload
            if isinstance(item, dict)
        )
    else:
        iterable = []
    assets = []
    for asset_id, item in iterable:
        info = item if isinstance(item, dict) else {}
        asset_id = str(asset_id or info.get("id") or info.get("slug") or "").strip()
        if not asset_id:
            continue
        title = str(info.get("name") or info.get("title") or asset_id).strip()
        asset_type = _poly_haven_type(info.get("type") or info.get("asset_type") or "")
        categories = info.get("categories") if isinstance(info.get("categories"), list) else []
        assets.append(
            {
                "id": asset_id,
                "name": title,
                "asset_type": "" if asset_type == "all" else asset_type,
                "categories": [str(item) for item in categories],
                "authors": _string_list(info.get("authors") or info.get("author")),
                "license": info.get("license") or "CC0",
                "page_url": f"{POLY_HAVEN_SITE_URL}/a/{urllib.parse.quote(asset_id)}",
                "api_files_url": f"{POLY_HAVEN_BASE_URL}/files/{urllib.parse.quote(asset_id)}",
                "thumbnail_url": info.get("thumbnail_url") or info.get("thumb") or "",
            }
        )
    return assets


def search_poly_haven_assets(*, query="", asset_type="all", category="", limit=20, timeout=15):
    asset_type = _poly_haven_type(asset_type)
    params = {}
    if asset_type != "all":
        params["t"] = asset_type
    category = str(category or "").strip()
    if category and category.lower() != "all":
        params["c"] = category
    url = f"{POLY_HAVEN_BASE_URL}/assets"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    payload, error = _fetch_json_result("poly_haven", url, timeout=timeout)
    if error:
        error.update(
            {
                "query": query,
                "asset_type": asset_type,
                "category": category,
                "assets": [],
                "count": 0,
                "download_import_status": "not_attempted",
            }
        )
        return error
    assets = _poly_haven_assets(payload)
    if asset_type != "all":
        for asset in assets:
            if not asset.get("asset_type"):
                asset["asset_type"] = asset_type
    query_text = str(query or "").strip().lower()
    if query_text:
        assets = [
            asset
            for asset in assets
            if query_text in " ".join([asset["id"], asset["name"], " ".join(asset["categories"])]).lower()
        ]
    limit = _bounded_limit(limit)
    return {
        "ok": True,
        "message": "Poly Haven assets searched",
        "provider": "poly_haven",
        "source_url": url,
        "query": query,
        "asset_type": asset_type,
        "category": category,
        "count": min(len(assets), limit),
        "total_considered": len(assets),
        "assets": assets[:limit],
        "download_import_status": "download_or_import_tools_available",
    }


def _poly_haven_files_url(asset_id):
    return f"{POLY_HAVEN_BASE_URL}/files/{urllib.parse.quote(str(asset_id or '').strip())}"


def _flatten_poly_haven_files(payload, prefix=()):
    entries = []
    if not isinstance(payload, dict):
        return entries
    if isinstance(payload.get("url"), str):
        include = payload.get("include") if isinstance(payload.get("include"), dict) else {}
        entries.append(
            {
                "logical_path": "/".join(str(item) for item in prefix),
                "path_parts": [str(item) for item in prefix],
                "url": str(payload.get("url") or ""),
                "md5": str(payload.get("md5") or ""),
                "size": int(payload.get("size") or 0),
                "include": include,
            }
        )
        return entries
    for key, value in payload.items():
        if key == "include":
            continue
        if value is None:
            continue
        entries.extend(_flatten_poly_haven_files(value, (*prefix, key)))
    return entries


def _infer_poly_haven_asset_type(payload):
    keys = set(payload.keys()) if isinstance(payload, dict) else set()
    if "hdri" in keys:
        return "hdris"
    texture_roots = {
        "ao",
        "arm",
        "bump",
        "diff",
        "diffuse",
        "disp",
        "displacement",
        "metal",
        "metallic",
        "nor",
        "normal",
        "rough",
        "roughness",
    }
    if texture_roots & keys or "mtlx" in keys:
        return "textures"
    if {"blend", "gltf", "fbx", "usd"} & keys:
        return "models"
    return ""


def inspect_poly_haven_asset_files(*, asset_id, timeout=15):
    asset_id = str(asset_id or "").strip()
    if not asset_id:
        return {"ok": False, "message": "asset_id is required"}
    url = _poly_haven_files_url(asset_id)
    payload, error = _fetch_json_result("poly_haven", url, timeout=timeout)
    if error:
        error["asset_id"] = asset_id
        return error
    entries = _flatten_poly_haven_files(payload)
    return {
        "ok": True,
        "message": "Poly Haven file tree fetched",
        "provider": "poly_haven",
        "asset_id": asset_id,
        "asset_type": _infer_poly_haven_asset_type(payload),
        "source_url": url,
        "file_count": len(entries),
        "files": entries,
        "raw_file_tree": payload,
    }


def _path_score(entry, resolution, preferred_formats):
    parts = [part.lower() for part in entry.get("path_parts", [])]
    resolution = str(resolution or "").lower()
    score = 0
    if resolution and resolution in parts:
        score += 100
    for index, file_format in enumerate(preferred_formats):
        if str(file_format).lower() in parts:
            score += max(1, 50 - index)
            break
    return score


def _select_poly_haven_hdri(entries, *, resolution, file_format):
    preferred = [file_format] if file_format else ["hdr", "exr", "jpg", "png"]
    candidates = [entry for entry in entries if (entry.get("path_parts") or [""])[0].lower() == "hdri"]
    candidates.sort(key=lambda item: _path_score(item, resolution, preferred), reverse=True)
    return candidates[:1]


def _select_poly_haven_model(entries, *, resolution, file_format):
    preferred = [file_format] if file_format else ["gltf", "glb", "fbx", "usd", "blend"]
    candidates = []
    for entry in entries:
        parts = [part.lower() for part in entry.get("path_parts", [])]
        if parts and parts[0] in {"gltf", "glb", "fbx", "usd", "blend"}:
            candidates.append(entry)
    candidates.sort(key=lambda item: _path_score(item, resolution, preferred), reverse=True)
    return candidates[:1]


def _select_poly_haven_texture_maps(entries, *, resolution, file_format, map_types=None):
    preferred = [file_format] if file_format else ["jpg", "png", "exr", "tif"]
    requested_maps = {str(item).strip().lower() for item in map_types or [] if str(item).strip()}
    excluded_roots = {"blend", "gltf", "fbx", "usd", "mtlx", "hdri", "backplates", "tonemapped", "colorchart"}
    grouped = {}
    for entry in entries:
        parts = [part.lower() for part in entry.get("path_parts", [])]
        if not parts or parts[0] in excluded_roots:
            continue
        if requested_maps and parts[0] not in requested_maps:
            continue
        grouped.setdefault(parts[0], []).append(entry)
    selected = []
    for items in grouped.values():
        items.sort(key=lambda item: _path_score(item, resolution, preferred), reverse=True)
        if items:
            selected.append(items[0])
    selected.sort(key=lambda item: item.get("logical_path", ""))
    return selected


def _included_poly_haven_entries(entry):
    include = entry.get("include") if isinstance(entry.get("include"), dict) else {}
    parent_parts = [str(part) for part in (entry.get("path_parts") or [])[:-1] if str(part)]
    entries = []
    for include_path, file_info in include.items():
        if not isinstance(file_info, dict) or not file_info.get("url"):
            continue
        include_logical_path = str(include_path).replace("\\", "/").strip("/")
        entries.append(
            {
                "logical_path": include_logical_path,
                # Poly Haven model include paths are relative to the model file.
                # Keep the provider path for diagnostics, but cache the file beside
                # the model so Blender's FBX/glTF texture references resolve.
                "local_logical_path": "/".join([*parent_parts, include_logical_path]),
                "path_parts": [part for part in include_logical_path.split("/") if part],
                "url": str(file_info.get("url") or ""),
                "md5": str(file_info.get("md5") or ""),
                "size": int(file_info.get("size") or 0),
                "include": {},
                "dependency": True,
            }
        )
    return entries


def _local_poly_haven_path(asset_dir, entry):
    logical = entry.get("local_logical_path") or entry.get("logical_path") or _filename_from_url(entry.get("url"), "asset-file")
    logical = logical.replace("\\", "/").strip("/")
    if "." not in os.path.basename(logical):
        logical = os.path.join(logical, _filename_from_url(entry.get("url"), "asset-file"))
    parts = [_sanitize_slug(part, "part") for part in logical.split("/") if part]
    return os.path.join(asset_dir, "files", *parts)


def download_poly_haven_asset(
    *,
    asset_id,
    asset_type="",
    resolution="2k",
    file_format="",
    map_types=None,
    include_dependencies=True,
    cache_dir="",
    timeout=60,
    progress_callback=None,
):
    files = inspect_poly_haven_asset_files(asset_id=asset_id, timeout=timeout)
    if not files.get("ok"):
        return files
    asset_type = _poly_haven_type(asset_type or files.get("asset_type") or "all")
    entries = files.get("files") or []
    if asset_type == "hdris":
        selected = _select_poly_haven_hdri(entries, resolution=resolution, file_format=file_format)
    elif asset_type == "textures":
        selected = _select_poly_haven_texture_maps(entries, resolution=resolution, file_format=file_format, map_types=map_types)
    elif asset_type == "models":
        selected = _select_poly_haven_model(entries, resolution=resolution, file_format=file_format)
    else:
        selected = _select_poly_haven_model(entries, resolution=resolution, file_format=file_format) or _select_poly_haven_hdri(
            entries,
            resolution=resolution,
            file_format=file_format,
        )
    if not selected:
        return {
            "ok": False,
            "message": "No matching Poly Haven files found for the requested type/resolution/format",
            "provider": "poly_haven",
            "asset_id": asset_id,
            "asset_type": asset_type,
            "available_files": entries[:50],
        }
    if include_dependencies:
        for entry in list(selected):
            selected.extend(_included_poly_haven_entries(entry))
    asset_dir = _asset_cache_dir("poly_haven", asset_id, cache_dir)
    downloads = []
    for entry in selected:
        destination = _local_poly_haven_path(asset_dir, entry)
        result = _download_file(
            entry["url"],
            destination,
            expected_md5=entry.get("md5", ""),
            expected_size=entry.get("size") or None,
            timeout=timeout,
            progress_callback=progress_callback,
        )
        result["logical_path"] = entry.get("logical_path", "")
        result["local_logical_path"] = entry.get("local_logical_path", entry.get("logical_path", ""))
        result["dependency"] = bool(entry.get("dependency", False))
        downloads.append(result)
        if not result.get("ok"):
            manifest = _write_manifest(
                asset_dir,
                {
                    "ok": False,
                    "provider": "poly_haven",
                    "asset_id": asset_id,
                    "asset_type": asset_type,
                    "license": POLY_HAVEN_LICENSE,
                    "source_url": _poly_haven_files_url(asset_id),
                    "downloaded_files": downloads,
                    "message": result.get("message", "Download failed"),
                },
            )
            return manifest
    manifest = _write_manifest(
        asset_dir,
        {
            "ok": True,
            "message": "Poly Haven asset cached",
            "provider": "poly_haven",
            "asset_id": asset_id,
            "asset_type": asset_type,
            "license": POLY_HAVEN_LICENSE,
            "source_url": _poly_haven_files_url(asset_id),
            "resolution": resolution,
            "file_format": file_format,
            "downloaded_files": downloads,
            "import_status": "not_imported",
        },
    )
    return manifest


def _thumbnail_url(result):
    thumbnails = result.get("thumbnails") if isinstance(result.get("thumbnails"), dict) else {}
    images = thumbnails.get("images") if isinstance(thumbnails.get("images"), list) else []
    if not images:
        return ""
    images = sorted(images, key=lambda item: int(item.get("width", 0) or 0), reverse=True)
    return str(images[0].get("url") or "")


def search_sketchfab_models(*, query, downloadable=True, staffpicked=None, animated=None, limit=20, timeout=15):
    query = str(query or "").strip()
    if not query:
        return {"ok": False, "message": "query is required for Sketchfab model search"}
    limit = _bounded_limit(limit)
    params = {
        "type": "models",
        "q": query,
        "count": limit,
        "downloadable": "true" if bool(downloadable) else "false",
    }
    if staffpicked is not None:
        params["staffpicked"] = "true" if bool(staffpicked) else "false"
    if animated is not None:
        params["animated"] = "true" if bool(animated) else "false"
    url = f"{SKETCHFAB_BASE_URL}/search?{urllib.parse.urlencode(params)}"
    payload, error = _fetch_json_result("sketchfab", url, timeout=timeout)
    if error:
        error.update(
            {
                "query": query,
                "models": [],
                "count": 0,
                "download_import_status": "not_attempted",
            }
        )
        return error
    results = payload.get("results") if isinstance(payload, dict) else []
    models = []
    for result in results or []:
        if not isinstance(result, dict):
            continue
        user = result.get("user") if isinstance(result.get("user"), dict) else {}
        license_info = result.get("license") if isinstance(result.get("license"), dict) else {}
        model = {
                "uid": str(result.get("uid") or ""),
                "name": str(result.get("name") or ""),
                "viewer_url": str(result.get("viewerUrl") or result.get("viewer_url") or ""),
                "is_downloadable": bool(result.get("isDownloadable", result.get("downloadable", False))),
                "user": str(user.get("displayName") or user.get("username") or ""),
                "license": str(license_info.get("label") or license_info.get("name") or ""),
                "thumbnail_url": _thumbnail_url(result),
                "like_count": int(result.get("likeCount") or 0),
                "view_count": int(result.get("viewCount") or 0),
            }
        model["provenance"] = {
            "uid": model["uid"],
            "model_name": model["name"],
            "author": model["user"],
            "license": model["license"],
            "model_url": model["viewer_url"],
        }
        models.append(model)
    return {
        "ok": True,
        "message": "Sketchfab models searched",
        "provider": "sketchfab",
        "source_url": url,
        "query": query,
        "count": len(models),
        "models": models,
        "download_import_status": "download_or_import_requires_auth",
    }


def _require_blender():
    if bpy is None or live_preview is None:
        return {"ok": False, "message": "This import helper requires Blender runtime"}
    return None


def _record_created_image(image):
    if live_preview is None or image is None:
        return
    live_preview._record_created_id("image", image.name)


def _record_created_data_for_object(obj):
    if live_preview is None or obj is None:
        return
    live_preview._record_created_id("object", obj.name)
    data = getattr(obj, "data", None)
    if data is None:
        return
    if obj.type == "MESH":
        live_preview._record_created_id("mesh", data.name)
    elif obj.type in {"CURVE", "FONT"}:
        live_preview._record_created_id("curve", data.name)
    elif obj.type == "CAMERA":
        live_preview._record_created_id("camera", data.name)
    elif obj.type == "LIGHT":
        live_preview._record_created_id("light", data.name)
    elif obj.type == "ARMATURE":
        live_preview._record_created_id("armature", data.name)


def _existing_names(collection):
    return {item.name for item in collection} if collection is not None else set()


def _new_names(collection, before):
    return sorted(item.name for item in collection if item.name not in before) if collection is not None else []


def _first_downloaded_file(manifest, *, extensions=()):
    lowered = tuple(ext.lower() for ext in extensions)
    for item in manifest.get("downloaded_files") or []:
        path = item.get("path", "")
        if path and (not lowered or path.lower().endswith(lowered)):
            return path
    return ""


def _texture_map_files(manifest):
    result = {}
    for item in manifest.get("downloaded_files") or []:
        if item.get("dependency"):
            continue
        path = item.get("path", "")
        if not path:
            continue
        logical = str(item.get("logical_path") or path).replace("\\", "/").lower()
        key = logical.split("/", 1)[0]
        result[key] = path
    return result


def _texture_map_helper_args(maps):
    args = {}
    ignored = {}
    for key, path in sorted((maps or {}).items()):
        lowered = str(key or "").lower()
        target = ""
        if any(term in lowered for term in ("diff", "albedo", "color", "base")):
            target = "base_color_path"
        elif any(term in lowered for term in ("normal", "nor")):
            target = "normal_path"
        elif lowered in {"arm", "ao_rough_metal", "ambient_rough_metal"} or "arm" in lowered:
            target = "arm_path"
        elif lowered in {"orm", "occlusion_rough_metal"} or "orm" in lowered:
            target = "orm_path"
        elif lowered in {"ao", "ambient", "ambient_occlusion"} or "ambient" in lowered:
            target = "ambient_occlusion_path"
        elif "bump" in lowered:
            target = "bump_path"
        elif any(term in lowered for term in ("disp", "displacement", "height")):
            target = "displacement_path"
        elif "rough" in lowered:
            target = "roughness_path"
        elif "metal" in lowered:
            target = "metallic_path"
        elif any(term in lowered for term in ("alpha", "opacity")):
            target = "alpha_path"
        elif any(term in lowered for term in ("emission", "emissive")):
            target = "emission_path"
        if target and target not in args:
            args[target] = path
        else:
            ignored[key] = path
    return args, ignored


def _unique_data_block_name(data_blocks, base_name):
    base = str(base_name or "").strip() or "Imported Asset"
    if data_blocks.get(base) is None:
        return base
    index = 1
    while True:
        candidate = f"{base}.{index:03d}"
        if data_blocks.get(candidate) is None:
            return candidate
        index += 1


def _load_image(path, *, colorspace="sRGB"):
    image = bpy.data.images.load(path, check_existing=True)
    _record_created_image(image)
    try:
        image.colorspace_settings.name = colorspace
    except Exception:
        pass
    return image


def _apply_hdri_world(context, manifest, *, label="Import Poly Haven HDRI"):
    error = _require_blender()
    if error:
        return error
    path = _first_downloaded_file(manifest, extensions=(".hdr", ".exr", ".jpg", ".jpeg", ".png"))
    if not path:
        return {"ok": False, "message": "No HDRI/image file was cached", "manifest": manifest}
    transaction = live_preview.begin(label, context)
    scene = context.scene
    key = f"scene:{scene.name}:world"
    if key not in transaction["before_state"]:
        transaction["before_state"][key] = {
            "kind": "scene_world",
            "scene_name": scene.name,
            "world_name": scene.world.name if scene.world else None,
        }
    world = bpy.data.worlds.new(f"Poly Haven {manifest.get('asset_id', 'HDRI')} World")
    live_preview._record_created_id("world", world.name)
    scene.world = world
    node_tree = blender_compat.ensure_node_tree(world)
    if node_tree is None:
        return {"ok": False, "message": "This Blender version did not provide a world shader node tree", "manifest": manifest}
    nodes = node_tree.nodes
    links = node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputWorld")
    background = nodes.new("ShaderNodeBackground")
    environment = nodes.new("ShaderNodeTexEnvironment")
    image = _load_image(path, colorspace="Linear")
    environment.image = image
    links.new(environment.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])
    transaction["applied_steps"].append(
        {
            "type": "import_external_asset",
            "label": label,
            "provider": manifest.get("provider"),
            "asset_id": manifest.get("asset_id"),
            "world": world.name,
            "image": image.name,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    manifest["import_status"] = "imported"
    manifest["imported_world"] = world.name
    manifest["imported_images"] = [image.name]
    manifest["transaction_id"] = transaction["id"]
    _write_manifest(manifest["cache_dir"], manifest)
    return {
        "ok": True,
        "message": f"Imported HDRI world from {manifest.get('asset_id')}",
        "world": world.name,
        "image": image.name,
        "manifest": manifest,
        "transaction_id": transaction["id"],
    }


def _apply_texture_material(context, manifest, *, target_object_name="", label="Import Poly Haven texture material"):
    error = _require_blender()
    if error:
        return error
    maps = _texture_map_files(manifest)
    if not maps:
        return {"ok": False, "message": "No texture map files were cached", "manifest": manifest}
    target = bpy.data.objects.get(target_object_name) if target_object_name else context.active_object
    object_names = [target.name] if target and getattr(target, "type", "") == "MESH" else None
    helper_args, ignored_maps = _texture_map_helper_args(maps)
    if not helper_args:
        return {
            "ok": False,
            "message": "No supported texture map files were cached for material import",
            "map_files": maps,
            "manifest": manifest,
        }
    try:
        from . import advanced_helpers
    except ImportError:
        import advanced_helpers
    material_name = _unique_data_block_name(bpy.data.materials, f"Poly Haven {manifest.get('asset_id', 'Texture')}")
    helper_result = advanced_helpers.create_image_texture_material(
        context,
        name=material_name,
        assign_to_objects=bool(object_names),
        object_names=object_names,
        selected_only=False,
        label=label,
        **helper_args,
    )
    if not helper_result.get("ok"):
        helper_result["manifest"] = manifest
        helper_result["map_files"] = maps
        return helper_result
    transaction = live_preview.current_transaction() or live_preview.begin(label, context)
    assigned_object = (helper_result.get("assigned_objects") or [""])[0]
    imported_images = [item.get("image") for item in helper_result.get("maps") or [] if item.get("image")]
    transaction["applied_steps"].append(
        {
            "type": "import_external_asset",
            "label": label,
            "provider": manifest.get("provider"),
            "asset_id": manifest.get("asset_id"),
            "material": helper_result["material"],
            "assigned_object": assigned_object,
            "maps": [item.get("map_type") for item in helper_result.get("maps") or []],
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    manifest["import_status"] = "imported"
    manifest["imported_materials"] = [helper_result["material"]]
    manifest["imported_images"] = imported_images
    manifest["imported_texture_maps"] = helper_result.get("maps") or []
    manifest["ignored_texture_maps"] = sorted(ignored_maps)
    manifest["assigned_object"] = assigned_object
    manifest["transaction_id"] = transaction["id"]
    _write_manifest(manifest["cache_dir"], manifest)
    return {
        "ok": True,
        "message": f"Created texture material from {manifest.get('asset_id')}",
        "material": helper_result["material"],
        "assigned_object": assigned_object,
        "images": imported_images,
        "texture_maps": helper_result.get("maps") or [],
        "ignored_texture_maps": sorted(ignored_maps),
        "manifest": manifest,
        "transaction_id": transaction["id"],
    }


def _operator_available(path):
    current = bpy.ops
    for part in str(path or "").split("."):
        current = getattr(current, part, None)
        if current is None:
            return None
    return current


def _call_first_import_operator(candidates, filepath):
    for path in candidates:
        operator = _operator_available(path)
        if operator is None:
            continue
        try:
            operator(filepath=filepath)
            return {"ok": True, "operator": path}
        except Exception as exc:
            last_error = f"{path}: {type(exc).__name__}: {exc}"
    return {"ok": False, "message": locals().get("last_error", "No compatible Blender import operator is available")}


def _import_model_file(filepath):
    format_error = _unsupported_model_import_error(filepath)
    if format_error:
        return format_error
    lower = str(filepath).lower()
    if lower.endswith((".gltf", ".glb")):
        return _call_first_import_operator(("import_scene.gltf", "wm.gltf_import"), filepath)
    elif lower.endswith(".fbx"):
        return _call_first_import_operator(("import_scene.fbx", "wm.fbx_import"), filepath)
    elif lower.endswith((".usd", ".usda", ".usdc")):
        return _call_first_import_operator(("wm.usd_import",), filepath)
    return {"ok": True, "operator": ""}


def _unsupported_model_import_error(filepath):
    lower = str(filepath).lower()
    if lower.endswith((".gltf", ".glb", ".fbx", ".usd", ".usda", ".usdc")):
        return None
    if lower.endswith(".blend"):
        return {"ok": False, "message": "Direct .blend append is not implemented for external asset imports yet"}
    return {"ok": False, "message": f"Unsupported model import format: {os.path.basename(filepath)}"}


def _asset_key(manifest):
    provider = str(manifest.get("provider") or "unknown").strip().lower()
    asset_id = str(manifest.get("asset_id") or manifest.get("uid") or "").strip()
    return f"{provider}:{asset_id}" if asset_id else ""


def _existing_asset_objects(manifest):
    key = _asset_key(manifest)
    result = []
    for obj in bpy.data.objects:
        if key and str(obj.get(ASSET_KEY_PROPERTY, "") or "") == key:
            result.append(obj.name)
    for name in manifest.get("imported_objects") or []:
        if bpy.data.objects.get(str(name)) is not None and str(name) not in result:
            result.append(str(name))
    return result


def _show_imported_geometry(context, imported_objects):
    objects = [bpy.data.objects.get(name) for name in imported_objects]
    objects = [obj for obj in objects if obj is not None]
    if not objects:
        return {"focused": False, "material_preview": False, "message": "No imported geometry was available to focus"}
    try:
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in objects:
            obj.select_set(True)
        context.view_layer.objects.active = objects[0]
    except Exception:
        pass
    focused = False
    material_preview = False
    screen = getattr(context, "screen", None)
    for area in list(getattr(screen, "areas", ()) or ()):
        if getattr(area, "type", "") != "VIEW_3D":
            continue
        space = getattr(area.spaces, "active", None)
        shading = getattr(space, "shading", None)
        if shading is not None and hasattr(shading, "type"):
            try:
                shading.type = "MATERIAL"
                material_preview = True
            except Exception:
                pass
        if hasattr(context, "temp_override"):
            try:
                region = next((item for item in area.regions if item.type == "WINDOW"), None)
                with context.temp_override(area=area, region=region, space_data=space):
                    bpy.ops.view3d.view_selected(use_all_regions=False)
                focused = True
            except Exception:
                pass
    return {
        "focused": focused,
        "material_preview": material_preview,
        "message": (
            "Imported geometry focused in Material Preview"
            if material_preview
            else "Imported geometry selected; switch the viewport to Material Preview to inspect textures"
        ),
    }


def _apply_model_import(context, manifest, *, label="Import external model", allow_duplicate=False):
    error = _require_blender()
    if error:
        return error
    path = _first_downloaded_file(manifest, extensions=(".gltf", ".glb", ".fbx", ".usd", ".usda", ".usdc", ".blend"))
    if not path:
        return {"ok": False, "message": "No importable model file was cached", "manifest": manifest}
    format_error = _unsupported_model_import_error(path)
    if format_error:
        format_error["manifest"] = manifest
        return format_error
    existing_objects = _existing_asset_objects(manifest)
    if existing_objects and not bool(allow_duplicate):
        return {
            "ok": False,
            "code": "asset_already_imported",
            "message": "This cached asset is already present in the scene; set allow_duplicate=true to import another copy",
            "existing_asset_warning": True,
            "existing_objects": existing_objects,
            "asset_key": _asset_key(manifest),
            "manifest": manifest,
        }
    before_objects = _existing_names(bpy.data.objects)
    before_meshes = _existing_names(bpy.data.meshes)
    before_curves = _existing_names(bpy.data.curves)
    before_armatures = _existing_names(bpy.data.armatures)
    before_cameras = _existing_names(bpy.data.cameras)
    before_lights = _existing_names(bpy.data.lights)
    before_collections = _existing_names(bpy.data.collections)
    before_actions = _existing_names(bpy.data.actions)
    before_node_groups = _existing_names(bpy.data.node_groups)
    before_materials = _existing_names(bpy.data.materials)
    before_images = _existing_names(bpy.data.images)
    import_result = _import_model_file(path)
    if not import_result.get("ok"):
        return import_result
    context.view_layer.update()
    transaction = live_preview.begin(label, context)
    imported_objects = _new_names(bpy.data.objects, before_objects)
    imported_meshes = _new_names(bpy.data.meshes, before_meshes)
    imported_curves = _new_names(bpy.data.curves, before_curves)
    imported_armatures = _new_names(bpy.data.armatures, before_armatures)
    imported_cameras = _new_names(bpy.data.cameras, before_cameras)
    imported_lights = _new_names(bpy.data.lights, before_lights)
    imported_collections = _new_names(bpy.data.collections, before_collections)
    imported_actions = _new_names(bpy.data.actions, before_actions)
    imported_node_groups = _new_names(bpy.data.node_groups, before_node_groups)
    imported_materials = _new_names(bpy.data.materials, before_materials)
    imported_images = _new_names(bpy.data.images, before_images)
    asset_key = _asset_key(manifest)
    for name in imported_objects:
        obj = bpy.data.objects.get(name)
        _record_created_data_for_object(obj)
        if obj is not None:
            obj[ASSET_KEY_PROPERTY] = asset_key
            obj[ASSET_PROVIDER_PROPERTY] = str(manifest.get("provider") or "")
            obj[ASSET_SOURCE_URL_PROPERTY] = str(manifest.get("source_url") or "")
    for name in imported_meshes:
        live_preview._record_created_id("mesh", name)
    for kind, names in (
        ("curve", imported_curves),
        ("armature", imported_armatures),
        ("camera", imported_cameras),
        ("light", imported_lights),
        ("collection", imported_collections),
        ("action", imported_actions),
        ("node_group", imported_node_groups),
    ):
        for name in names:
            live_preview._record_created_id(kind, name)
    for name in imported_materials:
        live_preview._record_created_id("material", name)
    for name in imported_images:
        live_preview._record_created_id("image", name)
    transaction["applied_steps"].append(
        {
            "type": "import_external_asset",
            "label": label,
            "provider": manifest.get("provider"),
            "asset_id": manifest.get("asset_id") or manifest.get("uid"),
            "source_file": path,
            "created_objects": imported_objects,
            "created_data": [
                *[{"kind": "object", "name": name} for name in imported_objects],
                *[{"kind": "collection", "name": name} for name in imported_collections],
                *[{"kind": "mesh", "name": name} for name in imported_meshes],
                *[{"kind": "curve", "name": name} for name in imported_curves],
                *[{"kind": "armature", "name": name} for name in imported_armatures],
                *[{"kind": "camera", "name": name} for name in imported_cameras],
                *[{"kind": "light", "name": name} for name in imported_lights],
                *[{"kind": "action", "name": name} for name in imported_actions],
                *[{"kind": "node_group", "name": name} for name in imported_node_groups],
                *[{"kind": "material", "name": name} for name in imported_materials],
                *[{"kind": "image", "name": name} for name in imported_images],
            ],
            "manifest_path": manifest.get("manifest_path", ""),
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    manifest["import_status"] = "imported"
    manifest["imported_objects"] = imported_objects
    manifest["imported_meshes"] = imported_meshes
    manifest["imported_curves"] = imported_curves
    manifest["imported_armatures"] = imported_armatures
    manifest["imported_cameras"] = imported_cameras
    manifest["imported_lights"] = imported_lights
    manifest["imported_collections"] = imported_collections
    manifest["imported_actions"] = imported_actions
    manifest["imported_node_groups"] = imported_node_groups
    manifest["imported_materials"] = imported_materials
    manifest["imported_images"] = imported_images
    manifest["transaction_id"] = transaction["id"]
    _write_manifest(manifest["cache_dir"], manifest)
    presentation = _show_imported_geometry(context, imported_objects)
    return {
        "ok": True,
        "message": f"Imported model from {os.path.basename(path)}",
        "source_file": path,
        "imported_objects": imported_objects,
        "manifest": manifest,
        "transaction_id": transaction["id"],
        "asset_key": asset_key,
        "presentation": presentation,
        "revert_guidance": "Use revert_preview with scope=last_step to remove only this import, or scope=all to revert the full pending preview.",
    }


def import_poly_haven_asset(
    context,
    *,
    asset_id,
    asset_type="",
    resolution="2k",
    file_format="",
    map_types=None,
    target_object_name="",
    cache_dir="",
    timeout=60,
    label="Import Poly Haven asset",
    allow_duplicate=False,
):
    manifest = download_poly_haven_asset(
        asset_id=asset_id,
        asset_type=asset_type,
        resolution=resolution,
        file_format=file_format,
        map_types=map_types,
        include_dependencies=True,
        cache_dir=cache_dir,
        timeout=timeout,
    )
    if not manifest.get("ok"):
        return manifest
    resolved_type = manifest.get("asset_type") or _poly_haven_type(asset_type)
    if resolved_type == "hdris":
        return _apply_hdri_world(context, manifest, label=label)
    if resolved_type == "textures":
        return _apply_texture_material(context, manifest, target_object_name=target_object_name, label=label)
    if resolved_type == "models":
        return _apply_model_import(context, manifest, label=label, allow_duplicate=allow_duplicate)
    return {"ok": False, "message": f"Unsupported Poly Haven import type: {resolved_type}", "manifest": manifest}


def import_cached_asset(
    context,
    *,
    manifest=None,
    manifest_path="",
    target_object_name="",
    label="Import external asset",
    allow_duplicate=False,
):
    if manifest is None:
        manifest_path = str(manifest_path or "").strip()
        if not manifest_path:
            return {"ok": False, "message": "manifest_path is required"}
        manifest = _read_manifest(manifest_path)
    if not isinstance(manifest, dict) or not manifest.get("ok"):
        return {
            "ok": False,
            "message": "Cached asset manifest is unavailable or not successful",
            "manifest": manifest or {},
        }
    provider = str(manifest.get("provider") or "").strip().lower()
    if provider == "poly_haven":
        resolved_type = manifest.get("asset_type") or "all"
        if resolved_type == "hdris":
            return _apply_hdri_world(context, manifest, label=label)
        if resolved_type == "textures":
            return _apply_texture_material(context, manifest, target_object_name=target_object_name, label=label)
        if resolved_type == "models":
            return _apply_model_import(context, manifest, label=label, allow_duplicate=allow_duplicate)
        return {"ok": False, "message": f"Unsupported Poly Haven import type: {resolved_type}", "manifest": manifest}
    if provider == "sketchfab":
        import_file = manifest.get("import_file", "")
        if import_file:
            downloaded_files = manifest.setdefault("downloaded_files", [])
            if not any(str(item.get("path") or "") == str(import_file) for item in downloaded_files if isinstance(item, dict)):
                downloaded_files.insert(
                    0,
                    {
                        "ok": True,
                        "path": import_file,
                        "cached": True,
                        "logical_path": os.path.relpath(import_file, manifest.get("cache_dir", os.path.dirname(import_file))),
                    },
                )
        return _apply_model_import(context, manifest, label=label, allow_duplicate=allow_duplicate)
    return {"ok": False, "message": f"Unsupported cached asset provider: {provider}", "manifest": manifest}


def _api_token_authorization_header(token):
    token = str(token or "").strip()
    lowered = token.lower()
    if lowered.startswith("token ") or lowered.startswith("bearer "):
        return token
    return f"Token {token}"


def _auth_header_from_token(
    api_token="",
    *,
    token_env_var=SKETCHFAB_TOKEN_ENV_VAR,
):
    token = str(api_token or "").strip()
    if token:
        return _api_token_authorization_header(token), "argument"

    token, env_name, blocked, _candidates = _first_env_token(
        token_env_var,
        defaults=SKETCHFAB_API_TOKEN_ENV_VARS,
        allowed=SKETCHFAB_ALLOWED_TOKEN_ENV_VARS,
    )
    if blocked:
        return "", f"blocked_env:{blocked}"
    if token:
        return _api_token_authorization_header(token), f"env:{env_name}"
    token = session_sketchfab_api_token()
    if token:
        return _api_token_authorization_header(token), "blender_session"
    return "", ""


def get_sketchfab_model_download_info(
    *,
    uid,
    api_token="",
    token_env_var=SKETCHFAB_TOKEN_ENV_VAR,
    model_password="",
    timeout=15,
):
    uid = str(uid or "").strip()
    if not uid:
        return {"ok": False, "message": "uid is required"}
    authorization, auth_source = _auth_header_from_token(
        api_token,
        token_env_var=token_env_var,
    )
    if auth_source.startswith("blocked_env:"):
        return {
            "ok": False,
            "message": "Sketchfab token_env_var must be a Sketchfab-specific environment variable",
            "provider": "sketchfab",
            "uid": uid,
            "auth_required": True,
            "blocked_token_env_var": auth_source.replace("blocked_env:", "", 1),
            "allowed_token_env_vars": sorted(SKETCHFAB_ALLOWED_TOKEN_ENV_VARS),
            "allowed_api_token_env_vars": sorted(SKETCHFAB_ALLOWED_TOKEN_ENV_VARS),
            "auth_method": "api_token",
            "configured_auth_env_vars": _present_auth_env_names(),
        }
    if not authorization:
        return {
            "ok": False,
            "message": (
                "Sketchfab download requires an API token via api_token, SKETCHFAB_API_TOKEN, "
                "or BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN."
            ),
            "provider": "sketchfab",
            "uid": uid,
            "auth_required": True,
            "auth_method": "api_token",
            "allowed_api_token_env_vars": sorted(SKETCHFAB_ALLOWED_TOKEN_ENV_VARS),
            "allowed_token_env_vars": sorted(SKETCHFAB_ALLOWED_TOKEN_ENV_VARS),
            "configured_auth_env_vars": _present_auth_env_names(),
        }
    headers = {"Authorization": authorization}
    if model_password:
        headers["x-skfb-model-pwd"] = str(model_password)
    url = f"{SKETCHFAB_BASE_URL}/models/{urllib.parse.quote(uid)}/download"
    try:
        payload = _fetch_json_with_headers(url, headers=headers, timeout=timeout)
    except Exception as exc:
        return {
            "ok": False,
            "message": f"Sketchfab download info failed: {type(exc).__name__}: {exc}",
            "provider": "sketchfab",
            "uid": uid,
            "source_url": url,
            "error_type": type(exc).__name__,
            "auth_source": auth_source,
            "auth_method": "api_token",
        }
    gltf = payload.get("gltf") if isinstance(payload, dict) else {}
    download_url = str((gltf or {}).get("url") or "")
    if not download_url:
        return {
            "ok": False,
            "message": "Sketchfab download response did not include a gltf.url",
            "provider": "sketchfab",
            "uid": uid,
            "source_url": url,
            "auth_source": auth_source,
            "auth_method": "api_token",
            "raw_response_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
        }
    return {
        "ok": True,
        "message": "Sketchfab download info fetched",
        "provider": "sketchfab",
        "uid": uid,
        "source_url": url,
        "download_url": download_url,
        "expires": int((gltf or {}).get("expires") or 0),
        "auth_source": auth_source,
        "auth_method": "api_token",
    }


def _zip_member_is_symlink(member):
    mode = (int(getattr(member, "external_attr", 0) or 0) >> 16) & 0o170000
    return mode == 0o120000


def _zip_member_depth(filename):
    return len([part for part in str(filename or "").replace("\\", "/").split("/") if part and part != "."])


def _safe_extract_zip(zip_path, destination):
    os.makedirs(destination, exist_ok=True)
    extracted = []
    destination_abs = os.path.abspath(destination)
    with zipfile.ZipFile(zip_path, "r") as archive:
        members = archive.infolist()
        if len(members) > MAX_ZIP_MEMBER_COUNT:
            return {
                "ok": False,
                "message": "Archive has too many members",
                "member_count": len(members),
                "max_member_count": MAX_ZIP_MEMBER_COUNT,
            }
        total_uncompressed = 0
        for member in members:
            if _zip_member_is_symlink(member):
                return {"ok": False, "message": f"Archive member is a symlink: {member.filename}"}
            if _zip_member_depth(member.filename) > MAX_ZIP_PATH_DEPTH:
                return {
                    "ok": False,
                    "message": f"Archive member path is too deep: {member.filename}",
                    "max_path_depth": MAX_ZIP_PATH_DEPTH,
                }
            if int(member.file_size or 0) > MAX_ZIP_MEMBER_BYTES:
                return {
                    "ok": False,
                    "message": f"Archive member is too large: {member.filename}",
                    "member_size": int(member.file_size or 0),
                    "max_member_size": MAX_ZIP_MEMBER_BYTES,
                }
            total_uncompressed += int(member.file_size or 0)
            if total_uncompressed > MAX_ZIP_EXTRACTED_BYTES:
                return {
                    "ok": False,
                    "message": "Archive uncompressed size is too large",
                    "total_uncompressed_size": total_uncompressed,
                    "max_total_uncompressed_size": MAX_ZIP_EXTRACTED_BYTES,
                }
            compressed_size = int(member.compress_size or 0)
            if compressed_size <= 0 and int(member.file_size or 0) > 0:
                return {
                    "ok": False,
                    "message": f"Archive member has invalid compressed size: {member.filename}",
                    "member_size": int(member.file_size or 0),
                    "compressed_size": compressed_size,
                }
            if (
                compressed_size > 0
                and int(member.file_size or 0) >= MIN_ZIP_RATIO_CHECK_BYTES
                and (int(member.file_size or 0) / compressed_size) > MAX_ZIP_COMPRESSION_RATIO
            ):
                return {
                    "ok": False,
                    "message": f"Archive member compression ratio is too high: {member.filename}",
                    "member_size": int(member.file_size or 0),
                    "compressed_size": compressed_size,
                    "max_compression_ratio": MAX_ZIP_COMPRESSION_RATIO,
                }
            target = os.path.abspath(os.path.join(destination_abs, member.filename))
            if not (target == destination_abs or target.startswith(destination_abs + os.sep)):
                return {"ok": False, "message": f"Unsafe archive member path: {member.filename}"}
            archive.extract(member, destination_abs)
            if not member.is_dir():
                extracted.append(target)
    return {"ok": True, "extracted_files": extracted, "total_uncompressed_size": total_uncompressed}


def _find_importable_model_file(directory):
    preferred = (".gltf", ".glb", ".fbx", ".usd", ".usda", ".usdc")
    candidates = []
    for root, _dirs, files in os.walk(directory):
        for filename in files:
            path = os.path.join(root, filename)
            if filename.lower().endswith(preferred):
                candidates.append(path)
    candidates.sort(key=lambda path: (0 if path.lower().endswith((".gltf", ".glb")) else 1, len(path), path.lower()))
    return candidates[0] if candidates else ""


def download_sketchfab_model(
    *,
    uid,
    api_token="",
    token_env_var=SKETCHFAB_TOKEN_ENV_VAR,
    model_password="",
    cache_dir="",
    timeout=120,
    progress_callback=None,
    provenance=None,
):
    provenance = dict(provenance or {})
    info = get_sketchfab_model_download_info(
        uid=uid,
        api_token=api_token,
        token_env_var=token_env_var,
        model_password=model_password,
        timeout=timeout,
    )
    if not info.get("ok"):
        return info
    model_url = str(provenance.get("model_url") or provenance.get("viewer_url") or "").strip()
    author = str(provenance.get("author") or provenance.get("user") or "").strip()
    license_name = str(provenance.get("license") or "").strip()
    model_name = str(provenance.get("model_name") or provenance.get("name") or "").strip()
    asset_dir = _asset_cache_dir("sketchfab", uid, cache_dir)
    archive_path = os.path.join(asset_dir, "download", "gltf.zip")
    download = _download_file(info["download_url"], archive_path, timeout=timeout, progress_callback=progress_callback)
    if not download.get("ok"):
        manifest = _write_manifest(
            asset_dir,
            {
                "ok": False,
                "provider": "sketchfab",
                "uid": uid,
                "source_url": model_url or info.get("source_url", ""),
                "download_api_url": info.get("source_url", ""),
                "author": author,
                "license": license_name,
                "model_name": model_name,
                "downloaded_files": [download],
                "message": download.get("message", "Sketchfab archive download failed"),
                "auth_source": info.get("auth_source", ""),
                "auth_method": info.get("auth_method", ""),
            },
        )
        return manifest
    extract_dir = os.path.join(asset_dir, "extracted")
    extract = _safe_extract_zip(archive_path, extract_dir)
    if not extract.get("ok"):
        manifest = _write_manifest(
            asset_dir,
            {
                "ok": False,
                "provider": "sketchfab",
                "uid": uid,
                "source_url": model_url or info.get("source_url", ""),
                "download_api_url": info.get("source_url", ""),
                "author": author,
                "license": license_name,
                "model_name": model_name,
                "downloaded_files": [download],
                "message": extract.get("message", "Sketchfab archive extraction failed"),
                "auth_source": info.get("auth_source", ""),
                "auth_method": info.get("auth_method", ""),
            },
        )
        return manifest
    import_file = _find_importable_model_file(extract_dir)
    manifest = _write_manifest(
        asset_dir,
        {
            "ok": bool(import_file),
            "message": "Sketchfab model cached" if import_file else "Sketchfab archive did not contain an importable model file",
            "provider": "sketchfab",
            "uid": uid,
            "source_url": model_url or info.get("source_url", ""),
            "model_url": model_url,
            "download_api_url": info.get("source_url", ""),
            "author": author,
            "model_name": model_name,
            "downloaded_files": [download],
            "extracted_files": extract.get("extracted_files", []),
            "import_file": import_file,
            "license": license_name,
            "provenance_complete": bool(model_url and author and license_name),
            "provenance": {
                "uid": uid,
                "model_name": model_name,
                "author": author,
                "license": license_name,
                "model_url": model_url,
            },
            "auth_source": info.get("auth_source", ""),
            "auth_method": info.get("auth_method", ""),
            "import_status": "not_imported",
        },
    )
    return manifest


def import_sketchfab_model(
    context,
    *,
    uid,
    api_token="",
    token_env_var=SKETCHFAB_TOKEN_ENV_VAR,
    model_password="",
    cache_dir="",
    timeout=120,
    label="Import Sketchfab model",
    provenance=None,
    allow_duplicate=False,
):
    manifest = download_sketchfab_model(
        uid=uid,
        api_token=api_token,
        token_env_var=token_env_var,
        model_password=model_password,
        cache_dir=cache_dir,
        timeout=timeout,
        provenance=provenance,
    )
    if not manifest.get("ok"):
        return manifest
    import_file = manifest.get("import_file", "")
    if import_file:
        manifest.setdefault("downloaded_files", []).insert(
            0,
            {
                "ok": True,
                "path": import_file,
                "cached": True,
                "logical_path": os.path.relpath(import_file, manifest.get("cache_dir", os.path.dirname(import_file))),
            },
        )
    return _apply_model_import(context, manifest, label=label, allow_duplicate=allow_duplicate)


def external_asset_cache_diagnostics(*, cache_dir="", max_assets=50):
    root = _cache_root(cache_dir)
    manifests = []
    for current_root, _dirs, files in os.walk(root):
        if "asset_manifest.json" not in files:
            continue
        manifests.append(_read_manifest(os.path.join(current_root, "asset_manifest.json")))
    manifests.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    max_assets = _bounded_limit(max_assets, default=50, maximum=500)
    assets = []
    provider_counts = {}
    total_bytes = 0
    imported_count = 0
    for manifest in manifests[:max_assets]:
        provider = str(manifest.get("provider") or "unknown")
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
        files = manifest.get("downloaded_files") or []
        size = sum(int(item.get("size") or 0) for item in files if isinstance(item, dict))
        total_bytes += size
        if manifest.get("import_status") == "imported":
            imported_count += 1
        assets.append(
            {
                "provider": provider,
                "asset_id": manifest.get("asset_id") or manifest.get("uid") or "",
                "asset_type": manifest.get("asset_type", ""),
                "license": manifest.get("license", ""),
                "author": manifest.get("author", ""),
                "model_name": manifest.get("model_name", ""),
                "model_url": manifest.get("model_url", ""),
                "source_url": manifest.get("source_url", ""),
                "cache_dir": manifest.get("cache_dir", ""),
                "manifest_path": manifest.get("manifest_path", ""),
                "file_count": len(files),
                "total_bytes": size,
                "import_status": manifest.get("import_status", ""),
                "imported_objects": manifest.get("imported_objects", []),
                "imported_materials": manifest.get("imported_materials", []),
                "imported_image_datablocks": manifest.get("imported_images", []),
                "source_files": [
                    {
                        "source_filename": os.path.basename(str(item.get("path") or item.get("logical_path") or "")),
                        "cached_filepath": str(item.get("path") or ""),
                        "logical_path": str(item.get("logical_path") or ""),
                        "size": int(item.get("size") or 0),
                    }
                    for item in files
                    if isinstance(item, dict)
                ],
                "imported_world": manifest.get("imported_world", ""),
                "updated_at": manifest.get("updated_at", ""),
            }
        )
    return {
        "ok": True,
        "message": "External asset cache diagnostics collected",
        "cache_dir": root,
        "auth": {
            "sketchfab": sketchfab_auth_diagnostics(),
        },
        "asset_count": len(manifests),
        "returned_asset_count": len(assets),
        "imported_asset_count": imported_count,
        "provider_counts": provider_counts,
        "total_cached_bytes": total_bytes,
        "assets": assets,
    }


def _directory_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for filename in files:
            full_path = os.path.join(root, filename)
            try:
                total += os.path.getsize(full_path)
            except OSError:
                pass
    return total


def _manifest_epoch(manifest, fallback_path=""):
    value = str(manifest.get("updated_at") or manifest.get("created_at") or "")
    try:
        parsed = time.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        return calendar.timegm(parsed)
    except Exception:
        try:
            return os.path.getmtime(fallback_path)
        except OSError:
            return 0.0


def _cache_asset_records(root):
    records = []
    for current_root, _dirs, files in os.walk(root):
        if "asset_manifest.json" not in files:
            continue
        manifest_path = os.path.join(current_root, "asset_manifest.json")
        manifest = _read_manifest(manifest_path)
        size = _directory_size(current_root)
        records.append(
            {
                "provider": str(manifest.get("provider") or "unknown"),
                "asset_id": str(manifest.get("asset_id") or manifest.get("uid") or ""),
                "asset_type": str(manifest.get("asset_type") or ""),
                "cache_dir": current_root,
                "manifest_path": manifest_path,
                "import_status": str(manifest.get("import_status") or ""),
                "size": size,
                "updated_epoch": _manifest_epoch(manifest, manifest_path),
            }
        )
    return records


def prune_external_asset_cache(*, cache_dir="", max_age_days=0, max_total_bytes=0, dry_run=True, include_imported=False):
    root = _cache_root(cache_dir)
    records = _cache_asset_records(root)
    total_bytes = sum(int(item.get("size") or 0) for item in records)
    now = time.time()
    candidates_by_path = {}
    max_age_seconds = max(0, int(float(max_age_days or 0) * 86400))
    for record in records:
        if not include_imported and record.get("import_status") == "imported":
            continue
        if max_age_seconds and record.get("updated_epoch") and now - float(record["updated_epoch"]) >= max_age_seconds:
            candidates_by_path[record["cache_dir"]] = {**record, "reason": "older_than_max_age"}

    max_total_bytes = max(0, int(max_total_bytes or 0))
    projected_total = total_bytes
    if max_total_bytes and projected_total > max_total_bytes:
        for record in sorted(records, key=lambda item: float(item.get("updated_epoch") or 0.0)):
            if projected_total <= max_total_bytes:
                break
            if not include_imported and record.get("import_status") == "imported":
                continue
            existing = candidates_by_path.get(record["cache_dir"])
            reason = "over_max_total_bytes" if existing is None else f"{existing['reason']},over_max_total_bytes"
            candidates_by_path[record["cache_dir"]] = {**record, "reason": reason}
            projected_total -= int(record.get("size") or 0)

    candidates = sorted(candidates_by_path.values(), key=lambda item: (float(item.get("updated_epoch") or 0.0), item.get("cache_dir", "")))
    deleted = []
    errors = []
    reclaimed = 0
    root_abs = os.path.abspath(root)
    for record in candidates:
        path = os.path.abspath(record["cache_dir"])
        if not (path == root_abs or path.startswith(root_abs + os.sep)):
            errors.append({"path": path, "message": "Refusing to delete path outside asset cache root"})
            continue
        if dry_run:
            continue
        try:
            shutil.rmtree(path)
            deleted.append(record)
            reclaimed += int(record.get("size") or 0)
        except Exception as exc:
            errors.append({"path": path, "message": f"{type(exc).__name__}: {exc}"})

    return {
        "ok": not errors,
        "message": "External asset cache prune dry run complete" if dry_run else "External asset cache prune complete",
        "dry_run": bool(dry_run),
        "cache_dir": root,
        "asset_count": len(records),
        "total_bytes": total_bytes,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "deleted_count": len(deleted),
        "deleted": deleted,
        "reclaimed_bytes": reclaimed,
        "errors": errors,
    }
