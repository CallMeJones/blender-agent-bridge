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
        stale_zip = os.path.join(repo_dir, f"{build_info.ADDON_ID}-0.0.0.zip")
        stale_sha = f"{stale_zip}.sha256"
        unrelated_zip = os.path.join(repo_dir, "other_extension-0.0.0.zip")
        with open(stale_zip, "wb") as handle:
            handle.write(b"stale")
        with open(stale_sha, "w", encoding="utf-8") as handle:
            handle.write("stale\n")
        with open(unrelated_zip, "wb") as handle:
            handle.write(b"unrelated")
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
        assert entry["website"] == "https://github.com/CallMeJones/blender-agent-bridge", entry
        assert "network" in entry["permissions"], entry
        assert not os.path.exists(stale_zip), result
        assert not os.path.exists(stale_sha), result
        assert os.path.exists(unrelated_zip), result
        with open(result["html_path"], "r", encoding="utf-8") as handle:
            html = handle.read()
        assert "https://callmejones.github.io/blender-agent-bridge/index.json" in html, html
        assert "https://github.com/CallMeJones/blender-agent-bridge/releases/latest" in html, html
        assert "Install from Disk" in html, html

        same_file = build_extension_repository.build_repository(
            zip_path=result["zip_path"],
            repo_dir=repo_dir,
        )
        assert same_file["ok"], same_file
        assert same_file["zip_path"] == result["zip_path"], same_file

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
