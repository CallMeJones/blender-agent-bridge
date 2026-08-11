"""Reference-image validation and content identity for generation providers."""

from __future__ import annotations

import hashlib
import os


MIB = 1024 * 1024
DEFAULT_MAX_IMAGE_BYTES = 20 * MIB
DEFAULT_MAX_TOTAL_BYTES = 64 * MIB

_POLICIES = {
    "meshy": {"suffixes": (".jpg", ".jpeg", ".png"), "max_images": 4},
    "tripo": {"suffixes": (".jpg", ".jpeg", ".png", ".webp"), "max_images": 4},
    "studio_endpoint": {"suffixes": (".jpg", ".jpeg", ".png", ".webp"), "max_images": 6},
    "triposr": {"suffixes": (".jpg", ".jpeg", ".png", ".webp"), "max_images": 1},
}


def _policy(provider):
    return _POLICIES.get(
        str(provider or "").strip().lower(),
        {"suffixes": (".jpg", ".jpeg", ".png", ".webp"), "max_images": 4},
    )


def _signature_valid(suffix, header):
    if suffix == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if suffix == ".webp":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    return False


def _format_name(suffix):
    return "jpeg" if suffix in {".jpg", ".jpeg"} else suffix.lstrip(".")


def read_reference_image(
    path,
    *,
    provider="",
    expected_identity=None,
    max_bytes=DEFAULT_MAX_IMAGE_BYTES,
):
    """Read one bounded image and verify that it is the approved content."""

    original_path = str(path or "")
    normalized_path = os.path.normpath(os.path.abspath(original_path))
    suffix = os.path.splitext(normalized_path)[1].lower()
    policy = _policy(provider)
    if suffix not in policy["suffixes"]:
        if str(provider or "").strip().lower() == "meshy":
            raise ValueError("Meshy reference images must be JPEG or PNG: %s" % normalized_path)
        raise ValueError(
            "%s reference images must use one of: %s"
            % (str(provider or "Generation").replace("_", " ").title(), ", ".join(policy["suffixes"]))
        )
    try:
        with open(normalized_path, "rb") as handle:
            payload = handle.read(int(max_bytes) + 1)
    except OSError as error:
        raise ValueError("Could not read generation reference image: %s" % error) from None
    if not payload:
        raise ValueError("Generation reference image is empty: %s" % normalized_path)
    if len(payload) > int(max_bytes):
        raise ValueError(
            "Generation reference image exceeds the %d-byte safety limit: %s"
            % (int(max_bytes), normalized_path)
        )
    if not _signature_valid(suffix, payload[:12]):
        raise ValueError(
            "Generation reference image has an invalid file signature for %s: %s"
            % (_format_name(suffix), normalized_path)
        )

    identity = {
        "path": normalized_path,
        "name": os.path.basename(normalized_path),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "format": _format_name(suffix),
    }
    expected = expected_identity if isinstance(expected_identity, dict) else {}
    if expected and (
        int(expected.get("bytes") or -1) != identity["bytes"]
        or str(expected.get("sha256") or "") != identity["sha256"]
    ):
        raise ValueError(
            "Generation reference changed after approval; review and approve the updated image: %s"
            % normalized_path
        )
    return payload, identity


def validate_reference_images(
    views,
    *,
    provider="",
    expected_identities=None,
    max_image_bytes=DEFAULT_MAX_IMAGE_BYTES,
    max_total_bytes=DEFAULT_MAX_TOTAL_BYTES,
):
    """Validate a provider's complete reference set and return content identities."""

    views = views if isinstance(views, dict) else {}
    supplied = [(str(name), str(path)) for name, path in views.items() if str(path or "").strip()]
    policy = _policy(provider)
    if not supplied:
        raise ValueError("Generation requires at least one reference image")
    if len(supplied) > int(policy["max_images"]):
        raise ValueError(
            "%s accepts at most %d reference image(s)"
            % (str(provider or "Generation").replace("_", " ").title(), int(policy["max_images"]))
        )

    identities = {}
    expected_identities = expected_identities if isinstance(expected_identities, dict) else {}
    total_bytes = 0
    for name, path in supplied:
        _payload, identity = read_reference_image(
            path,
            provider=provider,
            expected_identity=expected_identities.get(name),
            max_bytes=max_image_bytes,
        )
        identities[name] = identity
        total_bytes += identity["bytes"]
        if total_bytes > int(max_total_bytes):
            raise ValueError(
                "Generation reference images total %d bytes, above the %d-byte job safety limit"
                % (total_bytes, int(max_total_bytes))
            )
    return identities


def fingerprint_identities(provider, views, supplied=None):
    """Return stable identity facts, tolerating missing paths for pure unit callers."""

    supplied = supplied if isinstance(supplied, dict) else {}
    result = {}
    for name, path in sorted((views or {}).items()):
        identity = supplied.get(str(name)) if isinstance(supplied.get(str(name)), dict) else None
        if identity is None and os.path.isfile(str(path or "")):
            try:
                _payload, identity = read_reference_image(path, provider=provider)
            except ValueError:
                identity = None
        result[str(name)] = {
            "path": os.path.normpath(os.path.abspath(str(path))),
            "bytes": int((identity or {}).get("bytes") or 0),
            "sha256": str((identity or {}).get("sha256") or ""),
        }
    return result
