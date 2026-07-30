"""Client-neutral parsing and calibration for reference-image annotations."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path


ANNOTATION_SCHEMA_VERSION = 1
MAX_ANNOTATION_BYTES = 4 * 1024 * 1024
MAX_LANDMARKS = 128
MAX_CURVES = 64
MAX_CURVE_POINTS = 512
MAX_MASSES = 64
MAX_MEASUREMENTS = 64
MAX_NOTE_LENGTH = 512


class ReferenceAnnotationError(ValueError):
    """Raised when an annotation document cannot be calibrated safely."""


def _canonical_bytes(document):
    try:
        encoded = json.dumps(
            document,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReferenceAnnotationError(
            "annotations must contain JSON-serializable values"
        ) from exc
    if len(encoded) > MAX_ANNOTATION_BYTES:
        raise ReferenceAnnotationError(
            f"annotation document exceeds the {MAX_ANNOTATION_BYTES}-byte limit"
        )
    return encoded


def load_annotation_document(
    *,
    annotations=None,
    annotations_json="",
    annotations_path="",
):
    """Load exactly one annotation source and return document plus provenance."""

    object_supplied = annotations is not None
    json_text = str(annotations_json or "").strip()
    path_text = str(annotations_path or "").strip()
    source_count = int(object_supplied) + int(bool(json_text)) + int(bool(path_text))
    if source_count != 1:
        raise ReferenceAnnotationError(
            "supply exactly one of annotations, annotations_json, or annotations_path"
        )

    if object_supplied:
        if not isinstance(annotations, dict):
            raise ReferenceAnnotationError("annotations must be a JSON object")
        document = dict(annotations)
        source = {"kind": "object"}
    else:
        if path_text:
            path = Path(os.path.abspath(os.path.expanduser(path_text)))
            if not path.is_file():
                raise ReferenceAnnotationError(
                    f"annotation JSON path does not exist: {path}"
                )
            try:
                size = path.stat().st_size
            except OSError as exc:
                raise ReferenceAnnotationError(
                    f"could not inspect annotation JSON path: {exc}"
                ) from exc
            if size > MAX_ANNOTATION_BYTES:
                raise ReferenceAnnotationError(
                    f"annotation JSON file exceeds the {MAX_ANNOTATION_BYTES}-byte limit"
                )
            try:
                json_text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise ReferenceAnnotationError(
                    f"could not read annotation JSON as UTF-8: {exc}"
                ) from exc
            source = {"kind": "path", "path": str(path)}
        else:
            if len(json_text.encode("utf-8")) > MAX_ANNOTATION_BYTES:
                raise ReferenceAnnotationError(
                    f"annotation JSON exceeds the {MAX_ANNOTATION_BYTES}-byte limit"
                )
            source = {"kind": "json"}
        try:
            document = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise ReferenceAnnotationError(
                f"annotation JSON is invalid at line {exc.lineno}, column {exc.colno}"
            ) from exc
        if not isinstance(document, dict):
            raise ReferenceAnnotationError(
                "annotation JSON must decode to an object"
            )

    canonical = _canonical_bytes(document)
    source.update(
        {
            "sha256": hashlib.sha256(canonical).hexdigest(),
            "canonical_bytes": len(canonical),
        }
    )
    return document, source


def _finite_float(value, field):
    if isinstance(value, bool):
        raise ReferenceAnnotationError(f"{field} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ReferenceAnnotationError(f"{field} must be numeric") from exc
    if not math.isfinite(result):
        raise ReferenceAnnotationError(f"{field} must be finite")
    return result


def _pair(value, field):
    if isinstance(value, dict):
        value = [value.get("x"), value.get("y")]
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        raise ReferenceAnnotationError(f"{field} must contain [x, y]")
    return (
        _finite_float(value[0], f"{field}[0]"),
        _finite_float(value[1], f"{field}[1]"),
    )


def _positive_pair(value, field):
    x, y = _pair(value, field)
    if x <= 0.0 or y <= 0.0:
        raise ReferenceAnnotationError(f"{field} values must be greater than zero")
    return x, y


def _image_size(document, reference_image_size):
    image = document.get("image") if isinstance(document.get("image"), dict) else {}
    value = (
        document.get("image_size")
        or document.get("canvas_size")
        or image.get("size")
    )
    if value is None and image.get("width") is not None and image.get("height") is not None:
        value = [image.get("width"), image.get("height")]
    if value is None:
        value = reference_image_size
    return _positive_pair(value, "annotation image_size")


def _coordinate_space(document, fallback):
    image = document.get("image") if isinstance(document.get("image"), dict) else {}
    value = str(
        document.get("coordinate_space")
        or image.get("coordinate_space")
        or fallback
        or "pixel"
    ).strip().lower()
    aliases = {
        "pixel": "pixel",
        "pixels": "pixel",
        "px": "pixel",
        "normalized": "normalized",
        "normalised": "normalized",
        "unit": "normalized",
    }
    if value not in aliases:
        raise ReferenceAnnotationError(
            "coordinate_space must be pixel or normalized"
        )
    return aliases[value]


def _origin(document, fallback):
    image = document.get("image") if isinstance(document.get("image"), dict) else {}
    value = str(
        document.get("origin")
        or image.get("origin")
        or fallback
        or "top_left"
    ).strip().lower().replace("-", "_")
    aliases = {
        "top_left": "top_left",
        "upper_left": "top_left",
        "bottom_left": "bottom_left",
        "lower_left": "bottom_left",
    }
    if value not in aliases:
        raise ReferenceAnnotationError(
            "origin must be top_left or bottom_left"
        )
    return aliases[value]


def _image_rect(document, annotation_size, coordinate_space):
    image = document.get("image") if isinstance(document.get("image"), dict) else {}
    calibration = (
        document.get("calibration")
        if isinstance(document.get("calibration"), dict)
        else {}
    )
    value = (
        document.get("image_rect")
        or image.get("rect")
        or calibration.get("image_rect")
    )
    if value is None:
        if coordinate_space == "normalized":
            return 0.0, 0.0, 1.0, 1.0
        return 0.0, 0.0, annotation_size[0], annotation_size[1]
    if isinstance(value, dict):
        value = [
            value.get("x", 0.0),
            value.get("y", 0.0),
            value.get("width"),
            value.get("height"),
        ]
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        raise ReferenceAnnotationError(
            "image_rect must contain [x, y, width, height]"
        )
    x = _finite_float(value[0], "image_rect[0]")
    y = _finite_float(value[1], "image_rect[1]")
    width = _finite_float(value[2], "image_rect[2]")
    height = _finite_float(value[3], "image_rect[3]")
    if width <= 0.0 or height <= 0.0:
        raise ReferenceAnnotationError(
            "image_rect width and height must be greater than zero"
        )
    return x, y, width, height


def _named_items(value, field, limit, *, value_key="point"):
    if value is None:
        return []
    if isinstance(value, dict):
        if "name" in value:
            items = [dict(value)]
        else:
            items = []
            for name, item in value.items():
                if isinstance(item, dict):
                    prepared = dict(item)
                else:
                    prepared = {value_key: item}
                prepared.setdefault("name", str(name))
                items.append(prepared)
    elif isinstance(value, list):
        items = list(value)
    else:
        raise ReferenceAnnotationError(f"{field} must be an array or object map")
    if len(items) > limit:
        raise ReferenceAnnotationError(f"{field} exceeds the {limit}-item limit")
    return items


def _point_sequence(value):
    if not isinstance(value, list):
        return False
    if not value:
        return False
    first = value[0]
    if isinstance(first, dict):
        return "x" in first and "y" in first
    return isinstance(first, (list, tuple)) and len(first) >= 2


def _guide_name(value, fallback, field):
    text = str(value or fallback).strip()
    cleaned = "".join(
        char if char.isalnum() or char in {"_", "-", " "} else "_"
        for char in text
    )
    cleaned = " ".join(cleaned.split())[:80]
    if not cleaned:
        raise ReferenceAnnotationError(f"{field} must not be empty")
    return cleaned


def _guide_color(value, field):
    if not isinstance(value, (list, tuple)) or len(value) not in {3, 4}:
        raise ReferenceAnnotationError(
            f"{field} must contain three or four numeric components"
        )
    color = [
        _finite_float(component, f"{field}[{index}]")
        for index, component in enumerate(value)
    ]
    if any(component < 0.0 or component > 1.0 for component in color):
        raise ReferenceAnnotationError(
            f"{field} components must be between zero and one"
        )
    if len(color) == 3:
        color.append(1.0)
    return color


def _optional_bool(value, field, *, default=False):
    if value is None:
        return bool(default)
    if not isinstance(value, bool):
        raise ReferenceAnnotationError(f"{field} must be true or false")
    return value


def _optional_nonnegative_float(item, key, field, *, maximum):
    if key not in item:
        return None
    value = _finite_float(item[key], field)
    if value < 0.0 or value > maximum:
        raise ReferenceAnnotationError(
            f"{field} must be between zero and {maximum:g}"
        )
    return value


def _copy_guide_style(item, normalized, field):
    bevel_depth = _optional_nonnegative_float(
        item,
        "bevel_depth",
        f"{field} bevel_depth",
        maximum=1.0,
    )
    if bevel_depth is not None:
        normalized["bevel_depth"] = bevel_depth
    if "color" in item:
        normalized["color"] = _guide_color(
            item["color"], f"{field} color"
        )


def normalize_annotation_document(
    document,
    *,
    reference_image_size,
    default_coordinate_space="pixel",
    default_origin="top_left",
):
    """Convert supported annotation shapes to normalized top-left guide inputs."""

    if not isinstance(document, dict):
        raise ReferenceAnnotationError("annotation document must be an object")
    version = document.get("version", ANNOTATION_SCHEMA_VERSION)
    if isinstance(version, bool) or version != ANNOTATION_SCHEMA_VERSION:
        raise ReferenceAnnotationError(
            f"unsupported annotation schema version {version}; expected {ANNOTATION_SCHEMA_VERSION}"
        )

    reference_size = _positive_pair(reference_image_size, "reference image size")
    annotation_size = _image_size(document, reference_size)
    coordinate_space = _coordinate_space(document, default_coordinate_space)
    origin = _origin(document, default_origin)
    image_rect = _image_rect(document, annotation_size, coordinate_space)
    clamped_points = 0

    def normalize_point(value, field):
        nonlocal clamped_points
        x, y = _pair(value, field)
        x = (x - image_rect[0]) / image_rect[2]
        y = (y - image_rect[1]) / image_rect[3]
        if origin == "bottom_left":
            y = 1.0 - y
        bounded_x = max(0.0, min(1.0, x))
        bounded_y = max(0.0, min(1.0, y))
        if bounded_x != x or bounded_y != y:
            clamped_points += 1
        return [bounded_x, bounded_y]

    landmarks = []
    landmark_names = set()
    for index, item in enumerate(
        _named_items(document.get("landmarks"), "landmarks", MAX_LANDMARKS),
        start=1,
    ):
        if not isinstance(item, dict):
            raise ReferenceAnnotationError(
                f"landmarks[{index - 1}] must be an object"
            )
        name = _guide_name(
            item.get("name"),
            f"landmark_{index}",
            f"landmarks[{index - 1}].name",
        )
        if name in landmark_names:
            raise ReferenceAnnotationError(f"landmark name '{name}' is duplicated")
        point = item.get("point", item.get("center", item.get("position")))
        if point is None and item.get("x") is not None and item.get("y") is not None:
            point = [item.get("x"), item.get("y")]
        if point is None:
            raise ReferenceAnnotationError(
                f"landmark '{name}' is missing point coordinates"
            )
        normalized = {
            "name": name,
            "point": normalize_point(point, f"landmark '{name}' point"),
        }
        size = _optional_nonnegative_float(
            item,
            "size",
            f"landmark '{name}' size",
            maximum=10.0,
        )
        if size is not None:
            normalized["size"] = size
        if "note" in item:
            if not isinstance(item["note"], str):
                raise ReferenceAnnotationError(
                    f"landmark '{name}' note must be a string"
                )
            normalized["note"] = item["note"][:MAX_NOTE_LENGTH]
        landmarks.append(normalized)
        landmark_names.add(name)

    raw_curves = document.get("outlines")
    if raw_curves is None:
        raw_curves = document.get("curves")
    if _point_sequence(raw_curves):
        raw_curves = [{"name": "outline", "points": raw_curves}]
    curves = []
    curve_names = set()
    for index, item in enumerate(
        _named_items(
            raw_curves,
            "outlines",
            MAX_CURVES,
            value_key="points",
        ),
        start=1,
    ):
        if not isinstance(item, dict):
            raise ReferenceAnnotationError(
                f"outlines[{index - 1}] must be an object"
            )
        name = _guide_name(
            item.get("name"),
            f"outline_{index}",
            f"outlines[{index - 1}].name",
        )
        if name in curve_names:
            raise ReferenceAnnotationError(f"outline name '{name}' is duplicated")
        points = item.get("points", item.get("vertices"))
        if not isinstance(points, list) or len(points) < 2:
            raise ReferenceAnnotationError(
                f"outline '{name}' needs at least two points"
            )
        if len(points) > MAX_CURVE_POINTS:
            raise ReferenceAnnotationError(
                f"outline '{name}' exceeds the {MAX_CURVE_POINTS}-point limit"
            )
        closed = item.get("closed")
        if closed is None:
            closed = item.get("cyclic")
        normalized = {
            "name": name,
            "points": [
                normalize_point(point, f"outline '{name}' point {point_index}")
                for point_index, point in enumerate(points)
            ],
            "cyclic": _optional_bool(
                closed,
                f"outline '{name}' closed",
            ),
        }
        _copy_guide_style(item, normalized, f"outline '{name}'")
        curves.append(normalized)
        curve_names.add(name)

    masses = []
    mass_names = set()
    for index, item in enumerate(
        _named_items(document.get("masses"), "masses", MAX_MASSES),
        start=1,
    ):
        if not isinstance(item, dict):
            raise ReferenceAnnotationError(f"masses[{index - 1}] must be an object")
        name = _guide_name(
            item.get("name"),
            f"mass_{index}",
            f"masses[{index - 1}].name",
        )
        if name in mass_names:
            raise ReferenceAnnotationError(f"mass name '{name}' is duplicated")
        center = item.get("center")
        radius = item.get("radius", item.get("radii"))
        bounds = item.get("bounds", item.get("bbox"))
        if (center is None or radius is None) and bounds is not None:
            if isinstance(bounds, dict):
                bounds = [
                    bounds.get("x"),
                    bounds.get("y"),
                    bounds.get("width"),
                    bounds.get("height"),
                ]
            if not isinstance(bounds, (list, tuple)) or len(bounds) < 4:
                raise ReferenceAnnotationError(
                    f"mass '{name}' bounds must contain [x, y, width, height]"
                )
            bx = _finite_float(bounds[0], f"mass '{name}' bounds[0]")
            by = _finite_float(bounds[1], f"mass '{name}' bounds[1]")
            bw = _finite_float(bounds[2], f"mass '{name}' bounds[2]")
            bh = _finite_float(bounds[3], f"mass '{name}' bounds[3]")
            if bw <= 0.0 or bh <= 0.0:
                raise ReferenceAnnotationError(
                    f"mass '{name}' bounds width and height must be positive"
                )
            center = [bx + bw * 0.5, by + bh * 0.5]
            radius = [bw * 0.5, bh * 0.5]
        if center is None or radius is None:
            raise ReferenceAnnotationError(
                f"mass '{name}' requires center/radius or bounds"
            )
        rx, ry = _positive_pair(radius, f"mass '{name}' radius")
        rx /= image_rect[2]
        ry /= image_rect[3]
        normalized = {
            "name": name,
            "center": normalize_point(center, f"mass '{name}' center"),
            "radius": [min(1.0, rx), min(1.0, ry)],
        }
        _copy_guide_style(item, normalized, f"mass '{name}'")
        masses.append(normalized)
        mass_names.add(name)

    measurements = []
    measurement_names = set()
    for index, item in enumerate(
        _named_items(
            document.get("measurements"),
            "measurements",
            MAX_MEASUREMENTS,
        ),
        start=1,
    ):
        if not isinstance(item, dict):
            raise ReferenceAnnotationError(
                f"measurements[{index - 1}] must be an object"
            )
        name = _guide_name(
            item.get("name"),
            f"measurement_{index}",
            f"measurements[{index - 1}].name",
        )
        if name in measurement_names:
            raise ReferenceAnnotationError(
                f"measurement name '{name}' is duplicated"
            )
        normalized = {"name": name}
        from_name = item.get("from")
        to_name = item.get("to")
        if from_name is not None:
            normalized["from"] = _guide_name(
                from_name, "", f"measurement '{name}' from"
            )
        if to_name is not None:
            normalized["to"] = _guide_name(
                to_name, "", f"measurement '{name}' to"
            )
        from_point = item.get("from_point", item.get("start"))
        to_point = item.get("to_point", item.get("end"))
        if from_point is not None:
            normalized["from_point"] = normalize_point(
                from_point, f"measurement '{name}' from_point"
            )
        if to_point is not None:
            normalized["to_point"] = normalize_point(
                to_point, f"measurement '{name}' to_point"
            )
        if not (
            ("from" in normalized or "from_point" in normalized)
            and ("to" in normalized or "to_point" in normalized)
        ):
            raise ReferenceAnnotationError(
                f"measurement '{name}' requires landmark names or endpoint coordinates"
            )
        for endpoint in ("from", "to"):
            if (
                endpoint in normalized
                and normalized[endpoint] not in landmark_names
            ):
                raise ReferenceAnnotationError(
                    f"measurement '{name}' references unknown landmark "
                    f"'{normalized[endpoint]}'"
                )
        _copy_guide_style(item, normalized, f"measurement '{name}'")
        measurements.append(normalized)
        measurement_names.add(name)

    counts = {
        "landmarks": len(landmarks),
        "outlines": len(curves),
        "masses": len(masses),
        "measurements": len(measurements),
    }
    if sum(counts.values()) == 0:
        raise ReferenceAnnotationError(
            "annotation document contains no landmarks, outlines, masses, or measurements"
        )
    warnings = []
    if clamped_points:
        warnings.append(
            f"Clamped {clamped_points} annotation point(s) to the reference image bounds."
        )
    return {
        "schema_version": ANNOTATION_SCHEMA_VERSION,
        "subject": str(document.get("subject") or "").strip()[:MAX_NOTE_LENGTH],
        "source_coordinate_space": coordinate_space,
        "source_origin": origin,
        "reference_image_size": [reference_size[0], reference_size[1]],
        "annotation_size": [annotation_size[0], annotation_size[1]],
        "image_rect": list(image_rect),
        "landmarks": landmarks,
        "curves": curves,
        "masses": masses,
        "measurements": measurements,
        "counts": counts,
        "clamped_point_count": clamped_points,
        "warnings": warnings,
    }
