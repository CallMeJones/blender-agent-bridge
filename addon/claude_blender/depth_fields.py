"""Pure calibrated depth-field validation and sampling."""

from __future__ import annotations

import math


MAX_DEPTH_LAYERS_PER_VIEW = 2
MAX_DEPTH_PIXELS_PER_LAYER = 1_048_576
MAX_DEPTH_SAMPLES_PER_LAYER = 4096
SPARSE_BUCKET_AXIS = 64
MAX_SPARSE_SAMPLES_PER_BUCKET = 128
MAX_SPARSE_BUCKET_REFERENCES = 524_288
_EPSILON = 1.0e-9


class DepthFieldError(ValueError):
    """Raised when a calibrated depth field is invalid or unsafe."""


def _finite(value, field):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise DepthFieldError(f"{field} must be a finite number") from exc
    if not math.isfinite(result):
        raise DepthFieldError(f"{field} must be a finite number")
    return result


def _point(value, field):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise DepthFieldError(f"{field} must contain two numbers")
    return (_finite(value[0], field), _finite(value[1], field))


def _mode(value, field):
    result = str(value or "front").strip().lower()
    if result not in {"front", "back"}:
        raise DepthFieldError(f"{field} must be front or back")
    return result


def _prepare_grid(raw, field):
    try:
        width = int(raw.get("width"))
        height = int(raw.get("height"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise DepthFieldError(f"{field} width and height must be integers") from exc
    if width < 1 or height < 1:
        raise DepthFieldError(f"{field} width and height must be positive")
    pixel_count = width * height
    if pixel_count > MAX_DEPTH_PIXELS_PER_LAYER:
        raise DepthFieldError(
            f"{field} contains {pixel_count} pixels; limit is "
            f"{MAX_DEPTH_PIXELS_PER_LAYER}"
        )
    raw_values = raw.get("values")
    if not isinstance(raw_values, (list, tuple)) or len(raw_values) != pixel_count:
        actual = len(raw_values) if isinstance(raw_values, (list, tuple)) else 0
        raise DepthFieldError(
            f"{field}.values contains {actual} values; expected {pixel_count}"
        )
    values = []
    valid_count = 0
    for index, value in enumerate(raw_values):
        if value is None:
            values.append(None)
            continue
        depth = _finite(value, f"{field}.values[{index}]")
        values.append(depth)
        valid_count += 1
    if not valid_count:
        raise DepthFieldError(f"{field} contains no valid depth values")
    return {
        "kind": "grid",
        "width": width,
        "height": height,
        "values": tuple(values),
        "valid_count": valid_count,
        "maximum_query_samples": 4,
    }


def _prepare_samples(raw, field):
    source = raw.get("samples")
    if not isinstance(source, (list, tuple)) or not source:
        raise DepthFieldError(f"{field}.samples must contain at least one sample")
    if len(source) > MAX_DEPTH_SAMPLES_PER_LAYER:
        raise DepthFieldError(
            f"{field}.samples contains {len(source)} samples; limit is "
            f"{MAX_DEPTH_SAMPLES_PER_LAYER}"
        )
    samples = []
    for index, item in enumerate(source):
        if not isinstance(item, dict):
            raise DepthFieldError(f"{field}.samples[{index}] must be an object")
        point = _point(item.get("point"), f"{field}.samples[{index}].point")
        if not 0.0 <= point[0] <= 1.0 or not 0.0 <= point[1] <= 1.0:
            raise DepthFieldError(
                f"{field}.samples[{index}].point must use normalized coordinates"
            )
        radius = _finite(
            item.get("radius", 0.03),
            f"{field}.samples[{index}].radius",
        )
        if radius <= 0.0 or radius > 2.0:
            raise DepthFieldError(
                f"{field}.samples[{index}].radius must be greater than zero and at most 2"
            )
        samples.append(
            {
                "point": point,
                "depth": _finite(
                    item.get("depth"),
                    f"{field}.samples[{index}].depth",
                ),
                "radius": radius,
            }
        )
    buckets = {}
    reference_count = 0
    for sample_index, sample in enumerate(samples):
        center_x, center_y = sample["point"]
        radius = sample["radius"]
        minimum_x = _bucket_coordinate(center_x - radius)
        maximum_x = _bucket_coordinate(center_x + radius)
        minimum_y = _bucket_coordinate(center_y - radius)
        maximum_y = _bucket_coordinate(center_y + radius)
        for bucket_y in range(minimum_y, maximum_y + 1):
            for bucket_x in range(minimum_x, maximum_x + 1):
                key = bucket_y * SPARSE_BUCKET_AXIS + bucket_x
                bucket = buckets.setdefault(key, [])
                bucket.append(sample_index)
                reference_count += 1
                if len(bucket) > MAX_SPARSE_SAMPLES_PER_BUCKET:
                    raise DepthFieldError(
                        f"{field}.samples overlap too densely; a lookup bucket exceeds "
                        f"{MAX_SPARSE_SAMPLES_PER_BUCKET} candidate samples"
                    )
                if reference_count > MAX_SPARSE_BUCKET_REFERENCES:
                    raise DepthFieldError(
                        f"{field}.samples require too many spatial-index references"
                    )
    maximum_query_samples = max((len(bucket) for bucket in buckets.values()), default=0)
    return {
        "kind": "samples",
        "samples": tuple(samples),
        "sample_buckets": {
            key: tuple(indices)
            for key, indices in buckets.items()
        },
        "bucket_axis": SPARSE_BUCKET_AXIS,
        "bucket_reference_count": reference_count,
        "maximum_query_samples": maximum_query_samples,
        "valid_count": len(samples),
    }


def _bucket_coordinate(value):
    scaled = int(math.floor(max(0.0, min(1.0, float(value))) * SPARSE_BUCKET_AXIS))
    return min(SPARSE_BUCKET_AXIS - 1, scaled)


def prepare_depth_layer(raw, index=0):
    """Validate one signed orthographic depth layer.

    Depth is measured in world units from the calibrated view center along the
    view's forward vector. Front layers bound occupied volume from the camera
    side; back layers bound it from the far side.
    """

    field = f"depth_layers[{index}]"
    if not isinstance(raw, dict):
        raise DepthFieldError(f"{field} must be an object")
    if raw.get("_prepared_depth_layer") is True:
        return raw
    has_grid = any(key in raw for key in ("width", "height", "values"))
    has_samples = raw.get("samples") is not None
    if has_grid == has_samples:
        raise DepthFieldError(
            f"{field} must contain exactly one of a depth grid or samples"
        )
    prepared = _prepare_grid(raw, field) if has_grid else _prepare_samples(raw, field)
    tolerance = _finite(raw.get("tolerance", 0.0), f"{field}.tolerance")
    if tolerance < 0.0:
        raise DepthFieldError(f"{field}.tolerance must not be negative")
    return {
        **prepared,
        "_prepared_depth_layer": True,
        "name": str(raw.get("name") or f"depth_{index + 1}"),
        "mode": _mode(raw.get("mode"), f"{field}.mode"),
        "tolerance": tolerance,
    }


def prepare_depth_layers(raw_layers):
    """Validate the bounded depth-layer set attached to one view."""

    layers = list(raw_layers or [])
    if len(layers) > MAX_DEPTH_LAYERS_PER_VIEW:
        raise DepthFieldError(
            f"A view supports at most {MAX_DEPTH_LAYERS_PER_VIEW} depth layers"
        )
    prepared = [prepare_depth_layer(raw, index) for index, raw in enumerate(layers)]
    modes = [layer["mode"] for layer in prepared]
    if len(modes) != len(set(modes)):
        raise DepthFieldError("A view may contain at most one front and one back depth layer")
    return tuple(prepared)


def _sample_grid(layer, point):
    x = max(0.0, min(1.0, float(point[0]))) * (layer["width"] - 1)
    y = max(0.0, min(1.0, float(point[1]))) * (layer["height"] - 1)
    x0 = int(math.floor(x))
    y0 = int(math.floor(y))
    x1 = min(layer["width"] - 1, x0 + 1)
    y1 = min(layer["height"] - 1, y0 + 1)
    weighted = 0.0
    total = 0.0
    for sample_x, sample_y, weight in (
        (x0, y0, (x1 - x if x1 != x0 else 1.0) * (y1 - y if y1 != y0 else 1.0)),
        (x1, y0, (x - x0 if x1 != x0 else 0.0) * (y1 - y if y1 != y0 else 1.0)),
        (x0, y1, (x1 - x if x1 != x0 else 1.0) * (y - y0 if y1 != y0 else 0.0)),
        (x1, y1, (x - x0 if x1 != x0 else 0.0) * (y - y0 if y1 != y0 else 0.0)),
    ):
        if weight <= 0.0:
            continue
        value = layer["values"][sample_y * layer["width"] + sample_x]
        if value is None:
            continue
        weighted += value * weight
        total += weight
    return weighted / total if total > _EPSILON else None


def _sample_sparse(layer, point):
    best = None
    bucket_x = _bucket_coordinate(point[0])
    bucket_y = _bucket_coordinate(point[1])
    key = bucket_y * int(layer["bucket_axis"]) + bucket_x
    for sample_index in layer["sample_buckets"].get(key, ()):
        sample = layer["samples"][sample_index]
        distance = math.hypot(
            float(point[0]) - sample["point"][0],
            float(point[1]) - sample["point"][1],
        )
        if distance > sample["radius"]:
            continue
        candidate = (distance / sample["radius"], distance, sample["depth"])
        if best is None or candidate < best:
            best = candidate
    return best[2] if best is not None else None


def sample_depth(layer, point):
    """Sample signed world depth at a normalized top-left image coordinate."""

    if layer["kind"] == "grid":
        return _sample_grid(layer, point)
    return _sample_sparse(layer, point)


def allows_depth(point_depth, target_depth, *, mode, tolerance=0.0):
    """Return whether a point lies inside one front/back depth half-space."""

    if mode == "front":
        return point_depth >= target_depth - tolerance
    return point_depth <= target_depth + tolerance
