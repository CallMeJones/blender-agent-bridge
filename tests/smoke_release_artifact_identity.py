"""Verify that release and Pages packaging use one byte-identical archive."""

from __future__ import annotations

import hashlib
import json
import os
import tomllib


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MANIFEST_PATH = os.path.join(ROOT, "addon", "claude_blender", "blender_manifest.toml")


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sidecar_digest(path):
    with open(path, "r", encoding="utf-8") as handle:
        value = handle.read().strip().split()[0]
    assert len(value) == 64, (path, value)
    return value.lower()


def main():
    with open(MANIFEST_PATH, "rb") as handle:
        manifest = tomllib.load(handle)
    filename = f"{manifest['id']}-{manifest['version']}.zip"
    dist_zip = os.path.join(ROOT, "dist", filename)
    pages_zip = os.path.join(ROOT, "public", filename)
    dist_sidecar = f"{dist_zip}.sha256"
    pages_sidecar = f"{pages_zip}.sha256"
    index_path = os.path.join(ROOT, "public", "index.json")

    for path in (dist_zip, pages_zip, dist_sidecar, pages_sidecar, index_path):
        assert os.path.isfile(path), path

    dist_digest = _sha256(dist_zip)
    pages_digest = _sha256(pages_zip)
    assert dist_digest == pages_digest, (dist_digest, pages_digest)
    assert _sidecar_digest(dist_sidecar) == dist_digest, dist_sidecar
    assert _sidecar_digest(pages_sidecar) == dist_digest, pages_sidecar
    assert os.path.getsize(dist_zip) == os.path.getsize(pages_zip)

    with open(index_path, "r", encoding="utf-8") as handle:
        index = json.load(handle)
    entries = [entry for entry in index.get("data", []) if entry.get("id") == manifest["id"]]
    assert len(entries) == 1, entries
    entry = entries[0]
    assert entry.get("version") == manifest["version"], entry
    assert os.path.basename(entry.get("archive_url", "")) == filename, entry
    assert entry.get("archive_hash") == f"sha256:{dist_digest}", entry
    assert entry.get("archive_size") == os.path.getsize(dist_zip), entry
    print(f"smoke_release_artifact_identity: ok {filename} sha256:{dist_digest}")


if __name__ == "__main__":
    main()
