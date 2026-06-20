"""Opt-in live-network smoke tests for external asset providers.

This test is skipped unless BLENDER_AGENT_BRIDGE_LIVE_EXTERNAL_ASSET_SMOKE=1.
Downloads are skipped unless BLENDER_AGENT_BRIDGE_LIVE_EXTERNAL_ASSET_DOWNLOAD=1.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import external_assets  # noqa: E402


LIVE_ENV = "BLENDER_AGENT_BRIDGE_LIVE_EXTERNAL_ASSET_SMOKE"
DOWNLOAD_ENV = "BLENDER_AGENT_BRIDGE_LIVE_EXTERNAL_ASSET_DOWNLOAD"


def _enabled(name):
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def main():
    if not _enabled(LIVE_ENV):
        print(f"smoke_external_assets_live: skipped; set {LIVE_ENV}=1 to run")
        return

    cache_dir = tempfile.mkdtemp(prefix="bab-live-assets-")
    try:
        categories = external_assets.list_poly_haven_categories(asset_type="hdris", timeout=30)
        assert categories["ok"] is True, categories
        assert categories["groups"], categories

        poly = external_assets.search_poly_haven_assets(query="studio", asset_type="hdris", limit=3, timeout=30)
        assert poly["ok"] is True, poly
        assert poly["assets"], poly
        first_asset_id = poly["assets"][0]["id"]
        files = external_assets.inspect_poly_haven_asset_files(asset_id=first_asset_id, timeout=30)
        assert files["ok"] is True, files
        assert files["files"], files

        if _enabled(DOWNLOAD_ENV):
            cached = external_assets.download_poly_haven_asset(
                asset_id=first_asset_id,
                asset_type="hdris",
                resolution="1k",
                cache_dir=cache_dir,
                timeout=60,
            )
            assert cached["ok"] is True, cached
            assert cached["downloaded_files"], cached

        sketchfab = external_assets.search_sketchfab_models(query="repair drone", limit=3, timeout=30)
        assert sketchfab["ok"] is True, sketchfab
        assert "models" in sketchfab, sketchfab

        sketchfab_uid = str(os.environ.get("BLENDER_AGENT_BRIDGE_LIVE_SKETCHFAB_UID") or "").strip()
        has_sketchfab_token = bool(
            str(os.environ.get(external_assets.SKETCHFAB_TOKEN_ENV_VAR) or "").strip()
            or str(os.environ.get(external_assets.SKETCHFAB_BRIDGE_TOKEN_ENV_VAR) or "").strip()
        )
        if _enabled(DOWNLOAD_ENV) and sketchfab_uid and has_sketchfab_token:
            cached = external_assets.download_sketchfab_model(uid=sketchfab_uid, cache_dir=cache_dir, timeout=120)
            assert cached["ok"] is True, cached
            assert cached["import_file"], cached

        print("smoke_external_assets_live: ok")
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
