"""Smoke test for the static Blender extension repository builder."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "addon", "claude_blender"))

import build_extension_repository  # noqa: E402
import build_extension_zip  # noqa: E402
import build_info  # noqa: E402


def main():
    dist_dir = tempfile.mkdtemp(prefix="agent-bridge-dist-")
    repo_dir = tempfile.mkdtemp(prefix="agent-bridge-repo-")
    try:
        package = build_extension_zip.build_extension(dist_dir=dist_dir)
        result = build_extension_repository.build_repository(
            zip_path=package["path"],
            repo_dir=repo_dir,
        )
        assert result["ok"], result
        assert os.path.exists(result["zip_path"]), result
        assert os.path.exists(result["index_path"]), result
        assert os.path.exists(result["html_path"]), result
        with open(result["index_path"], "r", encoding="utf-8") as handle:
            index = json.load(handle)
        assert index["version"] == "v1", index
        assert index["blocklist"] == [], index
        assert len(index["data"]) == 1, index
        entry = index["data"][0]
        assert entry["id"] == build_info.ADDON_ID, entry
        assert entry["version"] == build_info.ADDON_VERSION, entry
        assert entry["name"] == "Blender Agent Bridge", entry
        assert entry["archive_url"] == f"./{os.path.basename(package['path'])}", entry
        assert entry["archive_hash"] == f"sha256:{package['sha256']}", entry
        assert entry["archive_size"] == os.path.getsize(package["path"]), entry
        assert "network" in entry["permissions"], entry

        absolute = build_extension_repository.build_repository(
            zip_path=package["path"],
            repo_dir=repo_dir,
            archive_base_url="https://example.test/releases",
        )
        with open(absolute["index_path"], "r", encoding="utf-8") as handle:
            absolute_index = json.load(handle)
        assert absolute_index["data"][0]["archive_url"].startswith("https://example.test/releases/"), absolute_index
        print("smoke_extension_repository: ok")
    finally:
        shutil.rmtree(dist_dir, ignore_errors=True)
        shutil.rmtree(repo_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
