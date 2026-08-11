"""Meshy request policy shared by UI approval, workers, and HTTP clients."""

from __future__ import annotations

import os

from . import generation_references


DEFAULT_MODEL = "latest"
STANDARD_MODELS = ("latest", "meshy-7", "meshy-6", "meshy-5")
SMART_TOPOLOGY_MODELS = ("meshy-t2",)
MODELS = STANDARD_MODELS + SMART_TOPOLOGY_MODELS

PRESET_RAW_HIGH_DETAIL = "raw_high_detail"
PRESET_BLENDER_WORKING = "blender_working"
PRESET_EDITABLE_QUAD = "editable_quad"
PRESETS = (
    PRESET_RAW_HIGH_DETAIL,
    PRESET_BLENDER_WORKING,
    PRESET_EDITABLE_QUAD,
)

MODEL_TYPES = ("standard", "smart-topology")
TOPOLOGIES = ("triangle", "quad")
TEXTURE_RESOLUTIONS = ("2k", "4k", "8k")
ORIGINS = ("bottom", "center")
DECIMATION_MODES = ("ultra", "high", "medium", "low")
DECIMATION_MODE_VALUES = {"ultra": 1, "high": 2, "medium": 3, "low": 4}

MAX_REFERENCE_IMAGE_BYTES = 20 * 1024 * 1024
MAX_REFERENCE_TOTAL_BYTES = 64 * 1024 * 1024
PRICING_VERSION = "meshy-api-2026-08"

_OPTION_KEYS = {
    "preset",
    "ai_model",
    "model_type",
    "ultra_mode",
    "should_texture",
    "enable_pbr",
    "texture_resolution",
    "should_remesh",
    "topology",
    "target_polycount",
    "decimation_mode",
    "save_pre_remeshed_model",
    "image_enhancement",
    "remove_lighting",
    "auto_size",
    "origin_at",
    "alpha_thumbnail",
    "multi_view_thumbnails",
}

_PRESET_VALUES = {
    PRESET_RAW_HIGH_DETAIL: {
        "should_texture": True,
        "enable_pbr": False,
        "texture_resolution": "2k",
        "should_remesh": False,
        "topology": "triangle",
        "save_pre_remeshed_model": False,
        "image_enhancement": True,
        "remove_lighting": True,
        "auto_size": False,
        "origin_at": "bottom",
        "alpha_thumbnail": False,
        "multi_view_thumbnails": False,
    },
    PRESET_BLENDER_WORKING: {
        "should_texture": True,
        "enable_pbr": True,
        "texture_resolution": "4k",
        "should_remesh": True,
        "topology": "triangle",
        "target_polycount": 100000,
        "save_pre_remeshed_model": True,
        "image_enhancement": True,
        "remove_lighting": True,
        "auto_size": True,
        "origin_at": "bottom",
        "alpha_thumbnail": True,
        "multi_view_thumbnails": True,
    },
    PRESET_EDITABLE_QUAD: {
        "should_texture": True,
        "enable_pbr": True,
        "texture_resolution": "4k",
        "should_remesh": True,
        "topology": "quad",
        "target_polycount": 50000,
        "save_pre_remeshed_model": True,
        "image_enhancement": True,
        "remove_lighting": True,
        "auto_size": True,
        "origin_at": "bottom",
        "alpha_thumbnail": True,
        "multi_view_thumbnails": True,
    },
}


def _strict_bool(value, name):
    if not isinstance(value, bool):
        raise ValueError("Meshy option %s must be true or false" % name)
    return value


def _strict_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Meshy option %s must be an integer" % name)
    return int(value)


def _enum(value, name, allowed):
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        raise ValueError(
            "Meshy option %s must be one of: %s" % (name, ", ".join(allowed))
        )
    return normalized


def normalize_options(
    options=None,
    *,
    model="",
    face_limit=0,
    texture=None,
    view_count=1,
):
    """Return one validated, explicit Meshy option set.

    Legacy top-level ``model``, ``face_limit``, and ``texture`` values remain
    accepted. New callers should use ``meshy_options`` so approval fingerprints
    cover every provider-specific output and cost decision.
    """

    if options is None:
        raw = {}
    elif isinstance(options, dict):
        raw = dict(options)
    else:
        raise ValueError("meshy_options must be an object")
    unknown = sorted(set(raw) - _OPTION_KEYS)
    if unknown:
        raise ValueError("Unknown Meshy option(s): %s" % ", ".join(unknown))

    explicit = set(raw)
    preset = _enum(
        raw.get("preset", PRESET_BLENDER_WORKING),
        "preset",
        PRESETS,
    )
    normalized = dict(_PRESET_VALUES[preset])
    normalized["preset"] = preset

    ai_model = str(raw.get("ai_model") or model or DEFAULT_MODEL).strip().lower()
    if model and raw.get("ai_model") and str(model).strip().lower() != ai_model:
        raise ValueError("Top-level model and meshy_options.ai_model disagree")
    if ai_model not in MODELS:
        raise ValueError("Unknown Meshy model %r; allowed values: %s" % (ai_model, ", ".join(MODELS)))
    normalized["ai_model"] = ai_model

    inferred_model_type = "smart-topology" if ai_model in SMART_TOPOLOGY_MODELS else "standard"
    model_type = _enum(raw.get("model_type", inferred_model_type), "model_type", MODEL_TYPES)
    if model_type == "smart-topology" and ai_model not in SMART_TOPOLOGY_MODELS:
        if "ai_model" in explicit or model:
            raise ValueError("Smart Topology requires ai_model meshy-t2")
        ai_model = "meshy-t2"
        normalized["ai_model"] = ai_model
    if model_type == "standard" and ai_model in SMART_TOPOLOGY_MODELS:
        raise ValueError("meshy-t2 requires model_type smart-topology")
    normalized["model_type"] = model_type

    for name in (
        "ultra_mode",
        "should_texture",
        "enable_pbr",
        "should_remesh",
        "save_pre_remeshed_model",
        "image_enhancement",
        "remove_lighting",
        "auto_size",
        "alpha_thumbnail",
        "multi_view_thumbnails",
    ):
        if name in raw:
            normalized[name] = _strict_bool(raw[name], name)

    if texture is not None:
        legacy_texture = _strict_bool(texture, "texture")
        if "should_texture" in explicit and normalized["should_texture"] != legacy_texture:
            raise ValueError("Top-level texture and meshy_options.should_texture disagree")
        normalized["should_texture"] = legacy_texture

    if "texture_resolution" in raw:
        normalized["texture_resolution"] = _enum(
            raw["texture_resolution"], "texture_resolution", TEXTURE_RESOLUTIONS
        )
    if "topology" in raw:
        normalized["topology"] = _enum(raw["topology"], "topology", TOPOLOGIES)
    if "origin_at" in raw:
        normalized["origin_at"] = _enum(raw["origin_at"], "origin_at", ORIGINS)
    if "decimation_mode" in raw:
        normalized["decimation_mode"] = _enum(
            raw["decimation_mode"], "decimation_mode", DECIMATION_MODES
        )
    if "target_polycount" in raw:
        normalized["target_polycount"] = _strict_int(
            raw["target_polycount"], "target_polycount"
        )

    legacy_face_limit = int(face_limit or 0)
    if legacy_face_limit:
        if "target_polycount" in explicit and normalized["target_polycount"] != legacy_face_limit:
            raise ValueError("Top-level face_limit and meshy_options.target_polycount disagree")
        normalized["target_polycount"] = legacy_face_limit
        normalized["should_remesh"] = True

    view_count = max(1, int(view_count or 1))
    if model_type == "smart-topology":
        if view_count > 1:
            raise ValueError("Meshy Smart Topology is available only for single-image generation")
        if normalized.get("ultra_mode"):
            raise ValueError("Meshy Ultra mode is not compatible with Smart Topology")
        if "should_remesh" in explicit and normalized.get("should_remesh"):
            raise ValueError("Smart Topology owns topology generation; should_remesh is not applicable")
        if "topology" in explicit and normalized.get("topology") != "triangle":
            raise ValueError("Meshy T2 Smart Topology outputs triangles")
        if "decimation_mode" in explicit:
            raise ValueError("decimation_mode is not compatible with Meshy T2 Smart Topology")
        if "save_pre_remeshed_model" in explicit and normalized.get("save_pre_remeshed_model"):
            raise ValueError("save_pre_remeshed_model is not available for Smart Topology")
        if "target_polycount" not in explicit and not legacy_face_limit:
            normalized["target_polycount"] = 4000
        target = int(normalized.get("target_polycount") or 4000)
        if not 100 <= target <= 15000:
            raise ValueError("Meshy T2 target_polycount must be between 100 and 15000")
        normalized["target_polycount"] = target
        normalized["should_remesh"] = False
        normalized["topology"] = "triangle"
        normalized["save_pre_remeshed_model"] = False
        normalized.pop("decimation_mode", None)
    else:
        ultra_mode = bool(normalized.get("ultra_mode", False))
        normalized["ultra_mode"] = ultra_mode
        if ultra_mode and (view_count > 1 or ai_model not in {"latest", "meshy-7"}):
            raise ValueError("Meshy Ultra requires single-image Meshy 7 or latest")

        should_remesh = bool(normalized.get("should_remesh", False))
        normalized["should_remesh"] = should_remesh
        has_decimation = bool(normalized.get("decimation_mode"))
        if has_decimation and "target_polycount" in explicit:
            raise ValueError("decimation_mode and target_polycount cannot both be set")
        if should_remesh:
            if has_decimation:
                normalized.pop("target_polycount", None)
            else:
                target = int(normalized.get("target_polycount") or 30000)
                if not 100 <= target <= 300000:
                    raise ValueError("Meshy target_polycount must be between 100 and 300000")
                normalized["target_polycount"] = target
        else:
            incompatible = {
                "target_polycount",
                "decimation_mode",
                "topology",
                "save_pre_remeshed_model",
            } & explicit
            if incompatible:
                raise ValueError(
                    "Meshy remesh option(s) require should_remesh=true: %s"
                    % ", ".join(sorted(incompatible))
                )
            normalized.pop("target_polycount", None)
            normalized.pop("decimation_mode", None)
            normalized.pop("topology", None)
            normalized.pop("save_pre_remeshed_model", None)

    if not normalized["should_texture"]:
        if raw.get("enable_pbr") is True:
            raise ValueError("enable_pbr requires should_texture=true")
        if "texture_resolution" in explicit:
            raise ValueError("texture_resolution requires should_texture=true")
        normalized["enable_pbr"] = False
        normalized.pop("texture_resolution", None)
    if (
        normalized["should_texture"]
        and normalized["ai_model"] == "meshy-5"
        and normalized["texture_resolution"] != "2k"
    ):
        if "texture_resolution" in explicit:
            raise ValueError("Meshy 5 supports only 2K textures")
        normalized["texture_resolution"] = "2k"

    enhancement_models = {"meshy-6", "meshy-7", "latest"}
    if normalized.get("image_enhancement") and normalized["ai_model"] not in enhancement_models:
        if "image_enhancement" in explicit:
            raise ValueError(
                "image_enhancement requires ai_model meshy-6, meshy-7, or latest"
            )
        normalized["image_enhancement"] = False

    lighting_models = (
        enhancement_models if view_count > 1 else {"meshy-6"}
    )
    if normalized.get("remove_lighting") and normalized["ai_model"] not in lighting_models:
        if "remove_lighting" in explicit:
            supported = "meshy-6, meshy-7, or latest" if view_count > 1 else "meshy-6"
            raise ValueError("remove_lighting requires ai_model %s" % supported)
        normalized["remove_lighting"] = False
    if normalized.get("multi_view_thumbnails") and not normalized.get("auto_size"):
        raise ValueError("multi_view_thumbnails requires auto_size=true")

    return normalized


def request_options(options, *, view_count=1):
    """Translate normalized public options into Meshy's request field names."""

    body = {
        "ai_model": options["ai_model"],
        "target_formats": ["glb"],
        "should_texture": bool(options["should_texture"]),
        "auto_size": bool(options["auto_size"]),
        "alpha_thumbnail": bool(options["alpha_thumbnail"]),
        "multi_view_thumbnails": bool(options["multi_view_thumbnails"]),
    }
    if options["auto_size"]:
        body["origin_at"] = options["origin_at"]
    if options["should_texture"]:
        body["enable_pbr"] = bool(options["enable_pbr"])
        body["texture_resolution"] = options["texture_resolution"]
    view_count = max(1, int(view_count or 1))
    if options["ai_model"] in {"meshy-6", "meshy-7", "latest"}:
        body["image_enhancement"] = bool(options["image_enhancement"])
    if options["ai_model"] == "meshy-6" or (
        view_count > 1 and options["ai_model"] in {"meshy-7", "latest"}
    ):
        body["remove_lighting"] = bool(options["remove_lighting"])
    if view_count == 1:
        body["model_type"] = options["model_type"]
    if options["model_type"] == "smart-topology":
        body["target_polycount"] = int(options["target_polycount"])
        return body

    if view_count == 1:
        body["ultra_mode"] = bool(options.get("ultra_mode", False))
    body["should_remesh"] = bool(options["should_remesh"])
    if options["should_remesh"]:
        body["topology"] = options["topology"]
        body["save_pre_remeshed_model"] = bool(options["save_pre_remeshed_model"])
        if options.get("decimation_mode"):
            body["decimation_mode"] = DECIMATION_MODE_VALUES[options["decimation_mode"]]
        else:
            body["target_polycount"] = int(options["target_polycount"])
    return body


def estimated_credits(options, *, view_count=1):
    """Calculate credits for the currently exposed Image-to-3D combinations."""

    model = options["ai_model"]
    textured = bool(options["should_texture"])
    resolution = options.get("texture_resolution", "2k")
    if model == "meshy-t2":
        credits = 5.0
    elif model == "meshy-5":
        credits = 5.0
    else:
        credits = 20.0
    if textured:
        credits += 15.0 if resolution == "8k" else 10.0
    if bool(options.get("ultra_mode")):
        credits += 5.0
    return credits


def pricing_summary(options, *, view_count=1):
    credits = estimated_credits(options, view_count=view_count)
    texture = (
        "%s textured" % options["texture_resolution"].upper()
        if options["should_texture"]
        else "untextured"
    )
    ultra = ", Ultra" if options.get("ultra_mode") else ""
    return {
        "estimated_credits": credits,
        "pricing_version": PRICING_VERSION,
        "cost_note": "%s Meshy credits: %s, %s%s, %s preset."
        % (
            int(credits) if credits == int(credits) else credits,
            options["ai_model"],
            texture,
            ultra,
            options["preset"],
        ),
    }


def _resolved_view_count(args, view_count):
    if view_count is not None:
        return max(1, int(view_count or 1))
    views = args.get("views") if isinstance(args.get("views"), dict) else {}
    return len(views) or 1


def normalize_job_options(args, *, view_count=None):
    """Resolve Meshy options from the shared generation-job argument shape."""

    args = args if isinstance(args, dict) else {}
    count = _resolved_view_count(args, view_count)
    return normalize_options(
        args.get("meshy_options"),
        model=args.get("model"),
        face_limit=args.get("face_limit"),
        texture=args.get("texture") if "texture" in args else None,
        view_count=count,
    )


def resolve_job_policy(args, *, view_count=None):
    """Return normalized options and the matching approval price facts."""

    args = args if isinstance(args, dict) else {}
    count = _resolved_view_count(args, view_count)
    options = normalize_job_options(args, view_count=count)
    return {"options": options, **pricing_summary(options, view_count=count)}


def validate_reference_image(path, *, max_bytes=MAX_REFERENCE_IMAGE_BYTES):
    """Validate a local Meshy reference before the user sees an upload approval."""

    _payload, identity = generation_references.read_reference_image(
        path,
        provider="meshy",
        max_bytes=max_bytes,
    )
    identity["suffix"] = os.path.splitext(identity["path"])[1].lower()
    return identity


def validate_reference_images(
    views,
    *,
    max_image_bytes=MAX_REFERENCE_IMAGE_BYTES,
    max_total_bytes=MAX_REFERENCE_TOTAL_BYTES,
):
    identities = generation_references.validate_reference_images(
        views,
        provider="meshy",
        max_image_bytes=max_image_bytes,
        max_total_bytes=max_total_bytes,
    )
    return [identities[str(name)] for name in (views or {}) if str(name) in identities]
