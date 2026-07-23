"""Shared normalization for imported-asset presentation presets."""

from __future__ import annotations


def infer_presentation_preset(prompt, preset=""):
    requested = str(preset or "").strip().lower().replace("-", "_").replace(" ", "_")
    if requested in {"studio", "catalog", "turntable", "lookdev"}:
        return requested
    text = str(prompt or "").lower()
    if "turntable" in text or "spin" in text or "360" in text:
        return "turntable"
    if "catalog" in text or "dimension" in text or "callout" in text:
        return "catalog"
    if "lookdev" in text or "look dev" in text or "material preview" in text:
        return "lookdev"
    return "studio"
