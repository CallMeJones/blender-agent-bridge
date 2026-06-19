"""Build a static Blender extension repository from a packaged extension zip."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import shutil
import tomllib
import zipfile

import build_extension_zip


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_REPO_DIR = os.path.join(ROOT, "public")


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_zip_manifest(zip_path):
    with zipfile.ZipFile(zip_path, "r") as archive:
        with archive.open("blender_manifest.toml", "r") as handle:
            return tomllib.loads(handle.read().decode("utf-8"))


def _manifest_entry(manifest, *, zip_name, zip_path, archive_base_url=""):
    archive_size = os.path.getsize(zip_path)
    archive_hash = _sha256_file(zip_path)
    archive_url = f"./{zip_name}"
    archive_base_url = str(archive_base_url or "").strip()
    if archive_base_url:
        archive_url = f"{archive_base_url.rstrip('/')}/{zip_name}"

    entry = {
        "schema_version": str(manifest.get("schema_version") or "1.0.0"),
        "id": str(manifest["id"]),
        "name": str(manifest["name"]),
        "tagline": str(manifest.get("tagline") or ""),
        "version": str(manifest["version"]),
        "type": str(manifest.get("type") or "add-on"),
        "maintainer": str(manifest.get("maintainer") or ""),
        "license": list(manifest.get("license") or []),
        "blender_version_min": str(manifest.get("blender_version_min") or ""),
        "archive_url": archive_url,
        "archive_size": int(archive_size),
        "archive_hash": f"sha256:{archive_hash}",
    }
    if manifest.get("permissions"):
        entry["permissions"] = dict(manifest["permissions"])
    if manifest.get("website"):
        entry["website"] = str(manifest["website"])
    if manifest.get("tags"):
        entry["tags"] = list(manifest["tags"])
    return entry


def _write_index(repo_dir, entry):
    index = {
        "version": "v1",
        "blocklist": [],
        "data": [entry],
    }
    path = os.path.join(repo_dir, "index.json")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(index, handle, indent=2)
        handle.write("\n")
    return path


def _write_html(repo_dir, entry, zip_name):
    title = html.escape(entry["name"])
    version = html.escape(entry["version"])
    tagline = html.escape(entry.get("tagline") or "")
    archive_hash = html.escape(entry["archive_hash"])
    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} Extension Repository</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; max-width: 56rem; line-height: 1.5; }}
    code {{ background: #f2f2f2; padding: 0.15rem 0.3rem; border-radius: 0.25rem; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p>{tagline}</p>
  <p>Latest package: <a href="./{html.escape(zip_name)}">{html.escape(zip_name)}</a> ({version})</p>
  <p>Repository URL for Blender:</p>
  <p><code>https://callmejones.github.io/blender-agent-bridge/index.json</code></p>
  <p>Archive hash: <code>{archive_hash}</code></p>
</body>
</html>
"""
    path = os.path.join(repo_dir, "index.html")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return path


def build_repository(*, zip_path="", repo_dir=DEFAULT_REPO_DIR, archive_base_url="", build_zip=False):
    repo_dir = os.path.abspath(repo_dir)
    if build_zip or not zip_path:
        result = build_extension_zip.build_extension()
        zip_path = result["path"]
    zip_path = os.path.abspath(zip_path)
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"Extension zip not found: {zip_path}")

    os.makedirs(repo_dir, exist_ok=True)
    zip_name = os.path.basename(zip_path)
    repo_zip_path = os.path.join(repo_dir, zip_name)
    shutil.copy2(zip_path, repo_zip_path)

    sha_path = f"{zip_path}.sha256"
    if os.path.exists(sha_path):
        shutil.copy2(sha_path, os.path.join(repo_dir, os.path.basename(sha_path)))
    else:
        digest = _sha256_file(zip_path)
        with open(os.path.join(repo_dir, f"{zip_name}.sha256"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{digest}  {zip_name}\n")

    manifest = _read_zip_manifest(repo_zip_path)
    entry = _manifest_entry(
        manifest,
        zip_name=zip_name,
        zip_path=repo_zip_path,
        archive_base_url=archive_base_url,
    )
    index_path = _write_index(repo_dir, entry)
    html_path = _write_html(repo_dir, entry, zip_name)
    return {
        "ok": True,
        "repo_dir": repo_dir,
        "index_path": index_path,
        "html_path": html_path,
        "zip_path": repo_zip_path,
        "archive_hash": entry["archive_hash"],
        "archive_url": entry["archive_url"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build a static Blender extension repository")
    parser.add_argument("--zip-path", default="", help="Packaged extension zip. Defaults to building the current extension.")
    parser.add_argument("--repo-dir", default=DEFAULT_REPO_DIR)
    parser.add_argument("--archive-base-url", default="", help="Optional absolute URL prefix for archive_url.")
    parser.add_argument("--build-zip", action="store_true", help="Build the extension zip before generating the repository.")
    args = parser.parse_args(argv)
    result = build_repository(
        zip_path=args.zip_path,
        repo_dir=args.repo_dir,
        archive_base_url=args.archive_base_url,
        build_zip=args.build_zip,
    )
    print(f"Built extension repository: {result['repo_dir']}")
    print(f"Index: {result['index_path']}")
    print(f"Archive: {result['zip_path']}")
    print(f"Hash: {result['archive_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
