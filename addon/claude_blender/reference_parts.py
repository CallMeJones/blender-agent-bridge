"""Pure reference-derived part graph inference."""

from __future__ import annotations

import math


ROLE_ALIASES = {
    "body": ("body", "torso", "chest", "belly", "trunk"),
    "head": ("head", "face", "skull", "cranium"),
    "muzzle": ("muzzle", "snout", "mouth", "cheek", "cheeks"),
    "ear": ("ear", "ears"),
    "eye": ("eye", "eyes"),
    "nose": ("nose",),
    "paw": ("paw", "paws", "foot", "feet"),
    "leg": ("leg", "legs", "limb", "limbs"),
    "tail": ("tail",),
}

FEATURE_ROLES = {"eye", "nose"}
ORGANIC_ROLES = {"body", "head", "muzzle", "ear", "paw", "leg", "tail", "generic"}


def _vector3(value, default=(0.0, 0.0, 0.0)):
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return tuple(float(item) for item in default)
    try:
        result = tuple(float(value[index]) for index in range(3))
    except (TypeError, ValueError, OverflowError):
        return tuple(float(item) for item in default)
    if not all(math.isfinite(item) for item in result):
        return tuple(float(item) for item in default)
    return result


def _add(a, b):
    return tuple(float(a[index]) + float(b[index]) for index in range(3))


def _scale(vector, amount):
    return tuple(float(component) * float(amount) for component in vector)


def _axis(basis, index, fallback):
    if isinstance(basis, (list, tuple)) and len(basis) > index:
        return _vector3(basis[index], fallback)
    return tuple(float(item) for item in fallback)


def _basis(value):
    return (
        _axis(value, 0, (1.0, 0.0, 0.0)),
        _axis(value, 1, (0.0, 1.0, 0.0)),
        _axis(value, 2, (0.0, 0.0, 1.0)),
    )


def _safe_name(value, fallback):
    text = " ".join(str(value or "").replace("_", " ").replace("-", " ").split())
    keep = [char for char in text if char.isalnum() or char == " "]
    return " ".join("".join(keep).split())[:80] or fallback


def _role_for_name(name, fallback="generic"):
    lowered = str(name or "").lower()
    for role, aliases in ROLE_ALIASES.items():
        if any(alias in lowered for alias in aliases):
            return role
    return fallback


def _profile_for_subject(subject, subject_profile):
    requested = str(subject_profile or "auto").strip().lower()
    if requested != "auto":
        return requested
    lowered = str(subject or "").lower()
    if any(term in lowered for term in ("kitten", "cat", "puppy", "dog", "cute", "plush")):
        return "cute_quadruped"
    if any(term in lowered for term in ("character", "creature", "animal", "mascot")):
        return "generic_character"
    return "generic_object"


def _part(
    *,
    name,
    role,
    center,
    radii,
    basis,
    source,
    parent="",
    symmetry_key="",
    material_role="",
    confidence="inferred",
    controls=None,
):
    return {
        "name": _safe_name(name, "part").replace(" ", "_").lower(),
        "label": _safe_name(name, "part"),
        "role": str(role or "generic"),
        "center": list(_vector3(center)),
        "radii": [max(0.0001, abs(value)) for value in _vector3(radii, (0.25, 0.25, 0.25))],
        "basis": [list(axis) for axis in _basis(basis)],
        "source": dict(source or {}),
        "parent": str(parent or ""),
        "symmetry_key": str(symmetry_key or ""),
        "material_role": str(material_role or role or "generic"),
        "confidence": str(confidence or "inferred"),
        "controls": list(controls or [])[:16],
    }


def _largest_form(forms):
    candidates = []
    for form in forms:
        radii = _vector3(form.get("radii"), (0.0, 0.0, 0.0))
        volume_proxy = radii[0] * radii[1] * radii[2]
        candidates.append((volume_proxy, form))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _parts_from_forms(forms):
    parts = []
    for index, form in enumerate(forms[:32], 1):
        name = _safe_name(form.get("name"), f"part {index}")
        role = _role_for_name(name)
        parts.append(
            _part(
                name=name,
                role=role,
                center=form.get("center"),
                radii=form.get("radii"),
                basis=form.get("basis"),
                source={
                    "kind": "guide_mass",
                    "object": str(form.get("source_object") or ""),
                    "guide_name": str(form.get("name") or ""),
                },
                parent="body" if role not in {"body", "generic"} else "",
                material_role=role,
                confidence="named_guide" if role != "generic" else "guide_mass",
                controls=form.get("controls") if isinstance(form.get("controls"), list) else [],
            )
        )
    return parts


def _cute_quadruped_defaults(primary):
    center = _vector3(primary.get("center"))
    radii = _vector3(primary.get("radii"), (1.0, 0.6, 1.0))
    basis = _basis(primary.get("basis"))
    right, depth, up = basis
    head_center = _add(center, _scale(up, radii[2] * 0.32))
    body_center = _add(center, _scale(up, -radii[2] * 0.38))
    head_radii = (radii[0] * 0.82, radii[1] * 0.95, radii[2] * 0.42)
    body_radii = (radii[0] * 0.62, radii[1] * 0.95, radii[2] * 0.48)
    source = {
        "kind": "profile_default",
        "profile": "cute_quadruped",
        "source_object": str(primary.get("source_object") or ""),
    }
    parts = [
        _part(
            name="body",
            role="body",
            center=body_center,
            radii=body_radii,
            basis=basis,
            source=source,
            confidence="profile_default",
        ),
        _part(
            name="head",
            role="head",
            center=head_center,
            radii=head_radii,
            basis=basis,
            source=source,
            parent="body",
            confidence="profile_default",
            controls=[
                {"direction": [0.0, 0.0, 1.0], "offset": 0.08, "falloff": 1.1},
            ],
        ),
        _part(
            name="left_ear",
            role="ear",
            center=_add(_add(head_center, _scale(right, -head_radii[0] * 0.52)), _scale(up, head_radii[2] * 0.65)),
            radii=(head_radii[0] * 0.18, head_radii[1] * 0.55, head_radii[2] * 0.34),
            basis=basis,
            source=source,
            parent="head",
            symmetry_key="ear",
            confidence="profile_default",
            controls=[
                {"direction": [0.0, 0.0, 1.0], "offset": 0.45, "falloff": 0.9},
            ],
        ),
        _part(
            name="right_ear",
            role="ear",
            center=_add(_add(head_center, _scale(right, head_radii[0] * 0.52)), _scale(up, head_radii[2] * 0.65)),
            radii=(head_radii[0] * 0.18, head_radii[1] * 0.55, head_radii[2] * 0.34),
            basis=basis,
            source=source,
            parent="head",
            symmetry_key="ear",
            confidence="profile_default",
            controls=[
                {"direction": [0.0, 0.0, 1.0], "offset": 0.45, "falloff": 0.9},
            ],
        ),
        _part(
            name="muzzle",
            role="muzzle",
            center=_add(_add(head_center, _scale(up, -head_radii[2] * 0.22)), _scale(depth, -head_radii[1] * 0.72)),
            radii=(head_radii[0] * 0.36, head_radii[1] * 0.34, head_radii[2] * 0.18),
            basis=basis,
            source=source,
            parent="head",
            confidence="profile_default",
        ),
        _part(
            name="left_eye",
            role="eye",
            center=_add(_add(head_center, _scale(right, -head_radii[0] * 0.32)), _scale(depth, -head_radii[1] * 0.86)),
            radii=(head_radii[0] * 0.12, head_radii[1] * 0.06, head_radii[2] * 0.16),
            basis=basis,
            source=source,
            parent="head",
            symmetry_key="eye",
            material_role="eye",
            confidence="profile_default",
        ),
        _part(
            name="right_eye",
            role="eye",
            center=_add(_add(head_center, _scale(right, head_radii[0] * 0.32)), _scale(depth, -head_radii[1] * 0.86)),
            radii=(head_radii[0] * 0.12, head_radii[1] * 0.06, head_radii[2] * 0.16),
            basis=basis,
            source=source,
            parent="head",
            symmetry_key="eye",
            material_role="eye",
            confidence="profile_default",
        ),
    ]
    return parts


def _landmark_parts(landmarks, fallback_form, existing_names):
    if fallback_form is None:
        return []
    basis = _basis(fallback_form.get("basis"))
    base_radii = _vector3(fallback_form.get("radii"), (1.0, 0.6, 1.0))
    default_radius = max(0.015, min(base_radii) * 0.18)
    parts = []
    for index, landmark in enumerate(list(landmarks or [])[:64], 1):
        name = _safe_name(landmark.get("name"), f"landmark part {index}")
        role = _role_for_name(name, "")
        if role not in FEATURE_ROLES | {"ear", "muzzle", "paw"}:
            continue
        part_name = name.replace(" ", "_").lower()
        if part_name in existing_names:
            continue
        scale = {
            "eye": (1.0, 0.35, 1.25),
            "nose": (0.8, 0.4, 0.6),
            "ear": (1.0, 0.75, 1.5),
            "muzzle": (2.4, 1.0, 1.2),
            "paw": (1.4, 1.0, 0.8),
        }.get(role, (1.0, 1.0, 1.0))
        parts.append(
            _part(
                name=part_name,
                role=role,
                center=landmark.get("location"),
                radii=tuple(default_radius * item for item in scale),
                basis=basis,
                source={
                    "kind": "landmark",
                    "object": str(landmark.get("object") or ""),
                    "landmark_name": str(landmark.get("name") or ""),
                },
                parent="head" if role in {"eye", "nose", "ear", "muzzle"} else "body",
                symmetry_key=role if any(side in part_name for side in ("left", "right")) else "",
                material_role=role,
                confidence="landmark_name",
            )
        )
    return parts


def _apply_hints(parts, part_hints):
    by_name = {part["name"]: dict(part) for part in parts}
    for index, hint in enumerate(list(part_hints or [])[:32], 1):
        if not isinstance(hint, dict):
            continue
        name = _safe_name(hint.get("name"), f"hint_part_{index}").replace(" ", "_").lower()
        current = by_name.get(name, {})
        role = str(hint.get("role") or current.get("role") or _role_for_name(name))
        center = hint.get("center", current.get("center", (0.0, 0.0, 0.0)))
        radii = hint.get("radii", current.get("radii", (0.25, 0.25, 0.25)))
        basis = hint.get("basis", current.get("basis", ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))))
        by_name[name] = _part(
            name=name,
            role=role,
            center=center,
            radii=radii,
            basis=basis,
            source={"kind": "hint", "overrode": bool(current)},
            parent=str(hint.get("parent", current.get("parent", "")) or ""),
            symmetry_key=str(hint.get("symmetry_key", current.get("symmetry_key", "")) or ""),
            material_role=str(hint.get("material_role", current.get("material_role", role)) or role),
            confidence="hint",
            controls=hint.get("controls") if isinstance(hint.get("controls"), list) else current.get("controls", []),
        )
    return list(by_name.values())


def infer_part_graph(
    *,
    subject="",
    subject_profile="auto",
    forms=None,
    landmarks=None,
    part_hints=None,
    max_parts=32,
):
    """Infer a bounded, JSON-safe editable part graph from guide forms."""

    forms = list(forms or [])[:64]
    landmarks = list(landmarks or [])[:128]
    profile = _profile_for_subject(subject, subject_profile)
    warnings = []
    parts = _parts_from_forms(forms)
    primary = _largest_form(forms)
    explicit_roles = {part["role"] for part in parts}
    if profile == "cute_quadruped" and primary is not None and not {"head", "body"}.issubset(explicit_roles):
        if parts:
            warnings.append(
                "Generated cute_quadruped default parts because guide masses did not explicitly label head/body."
            )
        parts = _cute_quadruped_defaults(primary) + [
            part for part in parts if part["role"] not in {"generic", "body", "head"}
        ]
    elif primary is not None and not parts:
        parts = [
            _part(
                name="primary",
                role="generic",
                center=primary.get("center"),
                radii=primary.get("radii"),
                basis=primary.get("basis"),
                source={"kind": "primary_form", "source_object": str(primary.get("source_object") or "")},
                confidence="fallback",
            )
        ]
    existing_names = {part["name"] for part in parts}
    parts.extend(_landmark_parts(landmarks, primary, existing_names))
    parts = _apply_hints(parts, part_hints)
    parts = sorted(parts, key=lambda part: (part.get("parent") != "", part["name"]))
    limit = max(1, min(64, int(max_parts or 32)))
    if len(parts) > limit:
        warnings.append(f"Limited inferred parts from {len(parts)} to max_parts={limit}.")
        parts = parts[:limit]
    names = {part["name"] for part in parts}
    for part in parts:
        if part.get("parent") and part["parent"] not in names:
            part["parent"] = ""
    role_counts = {}
    for part in parts:
        role_counts[part["role"]] = role_counts.get(part["role"], 0) + 1
    return {
        "schema_version": 1,
        "subject": str(subject or "reference model"),
        "subject_profile": profile,
        "parts": parts,
        "role_counts": role_counts,
        "warnings": warnings,
    }
