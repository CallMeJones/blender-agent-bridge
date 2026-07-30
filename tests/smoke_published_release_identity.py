"""Verify the public Pages and GitHub Release archives are byte-identical."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MANIFEST_PATH = os.path.join(ROOT, "addon", "claude_blender", "blender_manifest.toml")
PAGES_INDEX_URL = "https://callmejones.github.io/blender-agent-bridge/index.json"
RELEASE_BASE_URL = "https://github.com/CallMeJones/blender-agent-bridge/releases/download"
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024


def _download(url, *, max_bytes):
    request = urllib.request.Request(url, headers={"User-Agent": "blender-agent-bridge-release-smoke"})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read(max_bytes + 1)
    assert len(body) <= max_bytes, (url, len(body), max_bytes)
    return body


def _sidecar_digest(body, url, *, expected_filename):
    parts = body.decode("utf-8").strip().split()
    assert len(parts) >= 2, (url, parts)
    value = parts[0].lower()
    assert len(value) == 64, (url, value)
    sidecar_filename = os.path.basename(parts[1].lstrip("*"))
    assert sidecar_filename == expected_filename, (url, sidecar_filename, expected_filename)
    return value


def _verify_mcpb_archive(body, *, version):
    build_mcpb = _load_mcpb_builder()
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
        project = tomllib.loads(archive.read("pyproject.toml").decode("utf-8"))

    server = manifest["server"]
    assert manifest["manifest_version"] == "0.4", manifest
    assert manifest["name"] == build_mcpb.MCPB_NAME, manifest
    assert manifest["version"] == version, manifest
    assert server["type"] == "uv", server
    assert server["mcp_config"]["command"] == "uv", server
    assert server["entry_point"] in names, (server["entry_point"], names)
    assert project["project"]["version"] == version, project
    assert project["project"]["dependencies"] == [], project
    assert not any(name.startswith("server/lib/") for name in names), names


def _load_mcpb_builder():
    scripts_dir = os.path.join(ROOT, "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import build_mcpb

    return build_mcpb


def _expected_mcpb_digest(version):
    build_mcpb = _load_mcpb_builder()
    assert build_mcpb.build_info.MCP_SERVER_VERSION == version
    with tempfile.TemporaryDirectory(prefix="bab-publication-mcpb-") as temporary:
        output_path, _ = build_mcpb.build_mcpb(temporary)
        with open(output_path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()


def _verify_once(*, expected_mcpb_digest=None):
    with open(MANIFEST_PATH, "rb") as handle:
        manifest = tomllib.load(handle)
    version = manifest["version"]
    filename = f"{manifest['id']}-{version}.zip"

    index = json.loads(_download(PAGES_INDEX_URL, max_bytes=2 * 1024 * 1024))
    entries = [entry for entry in index.get("data", []) if entry.get("id") == manifest["id"]]
    assert len(entries) == 1, entries
    entry = entries[0]
    assert entry.get("version") == version, entry
    assert os.path.basename(entry.get("archive_url", "")) == filename, entry
    advertised_digest = str(entry.get("archive_hash") or "").removeprefix("sha256:").lower()
    assert len(advertised_digest) == 64, entry

    pages_zip_url = urllib.parse.urljoin(PAGES_INDEX_URL, entry["archive_url"])
    pages_sidecar_url = f"{pages_zip_url}.sha256"
    release_zip_url = f"{RELEASE_BASE_URL}/v{version}/{filename}"
    release_sidecar_url = f"{release_zip_url}.sha256"

    pages_zip = _download(pages_zip_url, max_bytes=MAX_ARCHIVE_BYTES)
    release_zip = _download(release_zip_url, max_bytes=MAX_ARCHIVE_BYTES)
    pages_digest = hashlib.sha256(pages_zip).hexdigest()
    release_digest = hashlib.sha256(release_zip).hexdigest()
    assert pages_digest == advertised_digest, (pages_digest, advertised_digest)
    assert release_digest == advertised_digest, (release_digest, advertised_digest)
    assert (
        _sidecar_digest(
            _download(pages_sidecar_url, max_bytes=4096),
            pages_sidecar_url,
            expected_filename=filename,
        )
        == advertised_digest
    )
    assert (
        _sidecar_digest(
            _download(release_sidecar_url, max_bytes=4096),
            release_sidecar_url,
            expected_filename=filename,
        )
        == advertised_digest
    )
    assert len(pages_zip) == entry.get("archive_size"), (len(pages_zip), entry.get("archive_size"))
    assert pages_zip == release_zip, "Pages and GitHub Release archives differ"

    mcpb_filename = _load_mcpb_builder().mcpb_filename(version)
    mcpb_url = f"{RELEASE_BASE_URL}/v{version}/{mcpb_filename}"
    mcpb_sidecar_url = f"{mcpb_url}.sha256"
    mcpb_body = _download(mcpb_url, max_bytes=MAX_ARCHIVE_BYTES)
    mcpb_digest = hashlib.sha256(mcpb_body).hexdigest()
    expected_mcpb_digest = expected_mcpb_digest or _expected_mcpb_digest(version)
    assert mcpb_digest == expected_mcpb_digest, (mcpb_digest, expected_mcpb_digest)
    assert (
        _sidecar_digest(
            _download(mcpb_sidecar_url, max_bytes=4096),
            mcpb_sidecar_url,
            expected_filename=mcpb_filename,
        )
        == mcpb_digest
    )
    _verify_mcpb_archive(mcpb_body, version=version)
    print(
        "smoke_published_release_identity: ok",
        f"{filename} sha256:{advertised_digest};",
        f"{mcpb_filename} sha256:{mcpb_digest}",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--delay", type=float, default=0)
    args = parser.parse_args()
    assert args.attempts >= 1
    assert args.delay >= 0

    with open(MANIFEST_PATH, "rb") as handle:
        expected_version = tomllib.load(handle)["version"]
    expected_mcpb_digest = _expected_mcpb_digest(expected_version)
    last_error = None
    for attempt in range(1, args.attempts + 1):
        try:
            _verify_once(expected_mcpb_digest=expected_mcpb_digest)
            return
        except (
            AssertionError,
            OSError,
            UnicodeError,
            urllib.error.URLError,
            json.JSONDecodeError,
            tomllib.TOMLDecodeError,
            zipfile.BadZipFile,
        ) as exc:
            last_error = exc
            if attempt == args.attempts:
                raise
            print(f"publication not ready ({attempt}/{args.attempts}): {exc}")
            time.sleep(args.delay)
    raise AssertionError(last_error)


if __name__ == "__main__":
    main()
