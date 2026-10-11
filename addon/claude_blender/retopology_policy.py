"""Retopology job bounds and provider requests, independent of Blender."""
from __future__ import annotations

import math
import ipaddress
import re
import urllib.parse

MAP_CHANNELS = {"base_color": ("Base Color", "sRGB"), "roughness": ("Roughness", "Non-Color"),
                "metallic": ("Metallic", "Non-Color"), "emission": ("Emission Color", "Non-Color"),
                "normal": ("Normal", "Non-Color")}
DEFAULT_MAPS = ("base_color", "normal", "roughness", "metallic", "emission")
MAX_ATLAS_PIXELS = 32 * 1024 * 1024
PRICING_VERSION = "retopology-api-2026-10-11"


def _integer(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer between {low} and {high}")
    return value


def _number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be a finite number between {low} and {high}")
    return float(value)


def _boolean(value, name):
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false")
    return value


def validate_atlas(resolution, map_types=None):
    _integer(resolution, "resolution", 16, 4096)
    if map_types is not None and not isinstance(map_types, (list, tuple)):
        raise ValueError("map_types must be a list")
    maps = list(dict.fromkeys(map_types if map_types is not None else DEFAULT_MAPS))
    if not maps or any(m not in MAP_CHANNELS for m in maps):
        raise ValueError("Choose base_color, normal, roughness, metallic or emission maps")
    if resolution * resolution * (len(maps) + 2) > MAX_ATLAS_PIXELS:
        raise ValueError("Atlas maps plus coverage checks exceed the 32-megapixel job budget; lower resolution or request fewer maps")
    return maps


def local_options(args, *, kind="remesh"):
    args = args or {}
    defaults = {"method": "quadriflow", "target_faces": 5000, "bake_textures": True,
                "resolution": 1024, "samples": 16, "margin": 8, "map_types": list(DEFAULT_MAPS),
                "use_symmetry": False, "preserve_sharp": True, "preserve_boundary": True,
                "seed": 0, "project_to_source": True, "merge_distance_ratio": .000001,
                "ray_distance_ratio": .05, "cage_extrusion_ratio": .01, "uv_mode": "smart_project",
                "max_deviation_ratio": .02, "intended_use": "prop", "timeout_seconds": 1800}
    result = {key: args.get(key, value) for key, value in defaults.items()}
    if kind == "bake":
        result["bake_textures"] = True
    for key, low, high in (("target_faces", 50, 100000), ("resolution", 16, 4096), ("samples", 1, 256),
                          ("margin", 0, 64), ("seed", 0, 1000000), ("timeout_seconds", 30, 7200)):
        result[key] = _integer(result[key], key, low, high)
    for key in ("bake_textures", "use_symmetry", "preserve_sharp", "preserve_boundary", "project_to_source"):
        result[key] = _boolean(result[key], key)
    for key, low, high in (("merge_distance_ratio", 0, .01), ("ray_distance_ratio", .00001, 1),
                          ("cage_extrusion_ratio", 0, .2), ("max_deviation_ratio", 0, 1)):
        result[key] = _number(result[key], key, low, high)
    for key, choices in (("method", ("quadriflow", "decimate")), ("uv_mode", ("smart_project", "existing")),
                         ("intended_use", ("prop", "character"))):
        if result[key] not in choices:
            raise ValueError(f"{key} must be one of {', '.join(choices)}")
    result["map_types"] = validate_atlas(result["resolution"], result["map_types"])
    return result


def provider_options(provider, args):
    if provider not in {"meshy", "tripo"}:
        raise ValueError("Retopology provider must be meshy or tripo")
    source_task = str(args.get("source_task_id") or "").strip()
    model_url = str(args.get("model_url") or "").strip()
    if bool(source_task) == bool(model_url):
        raise ValueError("Provide exactly one source_task_id or model_url")
    if source_task and not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", source_task):
        raise ValueError("Invalid provider source task ID")
    if model_url:
        parsed = urllib.parse.urlsplit(model_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.query:
            raise ValueError("model_url must be a public HTTPS model URL without credentials, query tokens or fragments")
        host = parsed.hostname.lower()
        if host == "localhost" or host.endswith((".local", ".localhost")) or "." not in host:
            raise ValueError("model_url must use a public host")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address and not address.is_global:
            raise ValueError("model_url must not address a private/local network")
        if not parsed.path.lower().endswith((".glb", ".gltf", ".fbx", ".obj", ".stl")):
            raise ValueError("model_url must point directly to a supported model file")
    _integer(args.get("timeout", 60), "timeout", 1, 300)
    _integer(args.get("poll_timeout_seconds", 1800), "poll_timeout_seconds", 30, 7200)
    topology = args.get("topology", "quad")
    if topology not in {"quad", "triangle"}:
        raise ValueError("topology must be quad or triangle")
    target = args.get("target_faces", 5000)
    payload = {}
    if provider == "meshy":
        _integer(target, "target_faces", 100, 300000)
        payload = {"input_task_id" if source_task else "model_url": source_task or model_url,
                   "target_polycount": target, "topology": topology, "target_formats": ["fbx", "glb"]}
        cost = 5
        output = "fbx" if topology == "quad" else "glb"
    else:
        model = args.get("retopology_model", "v3.0")
        if model not in {"v3.0", "v2.0", "v1.0"}:
            raise ValueError("retopology_model must be v3.0, v2.0 or v1.0")
        maximum = (150000 if topology == "quad" else 2000000) if model == "v1.0" else (10000 if topology == "quad" else 20000)
        _integer(target, "target_faces", 1 if model == "v1.0" else 500, maximum)
        smart_uv = _boolean(args.get("smart_uv", model == "v3.0"), "smart_uv")
        bake = _boolean(args.get("bake", model != "v1.0"), "bake")
        if smart_uv and model != "v3.0":
            raise ValueError("smart_uv is supported only by Tripo retopology v3.0")
        if bake and model == "v1.0":
            raise ValueError("Tripo retopology v1.0 does not support texture baking")
        payload = {"input": source_task or model_url, "model": model, "face_limit": target, "quad": topology == "quad"}
        if model == "v3.0":
            payload["smart_uv"] = smart_uv
        if model != "v1.0":
            payload["bake"] = bake
        cost = (40 if topology == "quad" else 35) if model == "v3.0" else 30 if model == "v2.0" else 10
        output = "glb"
    return {"payload": payload, "estimated_credits": cost, "pricing_version": PRICING_VERSION,
            "output_format": output, "source_task_id": source_task, "model_url": model_url,
            "cost_note": f"Estimated {cost} {provider.title()} credits for retopology; provider pricing may change.",
            "topology": topology, "target_faces": target,
            "format_note": "FBX preserves Meshy quad faces; GLB stores triangles. Inspect actual imported topology."}
