"""Verify the public Pages and GitHub Release archives are byte-identical."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request


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


def _sidecar_digest(body, url):
    value = body.decode("utf-8").strip().split()[0].lower()
    assert len(value) == 64, (url, value)
    return value


def _verify_once():
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
    assert _sidecar_digest(_download(pages_sidecar_url, max_bytes=4096), pages_sidecar_url) == advertised_digest
    assert _sidecar_digest(_download(release_sidecar_url, max_bytes=4096), release_sidecar_url) == advertised_digest
    assert len(pages_zip) == entry.get("archive_size"), (len(pages_zip), entry.get("archive_size"))
    assert pages_zip == release_zip, "Pages and GitHub Release archives differ"
    print(f"smoke_published_release_identity: ok {filename} sha256:{advertised_digest}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--delay", type=float, default=0)
    args = parser.parse_args()
    assert args.attempts >= 1
    assert args.delay >= 0

    last_error = None
    for attempt in range(1, args.attempts + 1):
        try:
            _verify_once()
            return
        except (AssertionError, OSError, UnicodeError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == args.attempts:
                raise
            print(f"publication not ready ({attempt}/{args.attempts}): {exc}")
            time.sleep(args.delay)
    raise AssertionError(last_error)


if __name__ == "__main__":
    main()
