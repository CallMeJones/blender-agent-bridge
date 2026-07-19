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
DEFAULT_REPOSITORY_URL = "https://callmejones.github.io/blender-agent-bridge/index.json"
DEFAULT_RELEASE_URL = "https://github.com/CallMeJones/blender-agent-bridge/releases/latest"
PROJECT_URL = "https://github.com/CallMeJones/blender-agent-bridge"
SHOWCASE_ASSETS = (
    "egypt-dogfight-hero.jpg",
    "egypt-dogfight-preview.gif",
    "egypt-workflow-strip.jpg",
)


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


def _is_same_file(left, right):
    try:
        return os.path.exists(left) and os.path.exists(right) and os.path.samefile(left, right)
    except OSError:
        return False


def _remove_stale_packages(repo_dir, *, extension_id, keep_names):
    prefix = f"{extension_id}-"
    for filename in os.listdir(repo_dir):
        if filename in keep_names:
            continue
        is_package = filename.startswith(prefix) and (
            filename.endswith(".zip") or filename.endswith(".zip.sha256")
        )
        if is_package:
            os.remove(os.path.join(repo_dir, filename))


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


def _copy_showcase_assets(repo_dir):
    source_dir = os.path.join(ROOT, "docs", "assets")
    target_dir = os.path.join(repo_dir, "assets")
    copied = []
    for filename in SHOWCASE_ASSETS:
        source = os.path.join(source_dir, filename)
        if not os.path.isfile(source):
            continue
        os.makedirs(target_dir, exist_ok=True)
        target = os.path.join(target_dir, filename)
        shutil.copy2(source, target)
        copied.append(target)
    return copied


def _write_html(repo_dir, entry, zip_name, *, repository_url=DEFAULT_REPOSITORY_URL, release_url=DEFAULT_RELEASE_URL):
    title = html.escape(entry["name"])
    version = html.escape(entry["version"])
    tagline = html.escape(entry.get("tagline") or "")
    archive_hash = html.escape(entry["archive_hash"])
    repository_url = html.escape(str(repository_url or DEFAULT_REPOSITORY_URL))
    release_url = html.escape(str(release_url or DEFAULT_RELEASE_URL))
    min_blender = html.escape(str(entry.get("blender_version_min") or "4.2.0"))
    website = html.escape(str(entry.get("website") or "https://github.com/CallMeJones/blender-agent-bridge"))
    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} Extension Repository</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem auto; padding: 0 1rem; max-width: 72rem; line-height: 1.5; color: #111827; }}
    h1, h2 {{ line-height: 1.15; }}
    .panel {{ border: 1px solid #d1d5db; border-radius: 0.5rem; padding: 1rem; margin: 1rem 0; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(17rem, 1fr)); gap: 1rem; }}
    .meta {{ color: #4b5563; }}
    .hero {{ width: 100%; max-height: 28rem; object-fit: cover; border-radius: 0.75rem; }}
    .clients a {{ display: inline-block; margin: 0.2rem 0.5rem 0.2rem 0; }}
    code {{ background: #f2f2f2; padding: 0.15rem 0.3rem; border-radius: 0.25rem; }}
    pre {{ background: #111827; color: #f9fafb; padding: 1rem; border-radius: 0.5rem; overflow-x: auto; }}
    a {{ color: #1d4ed8; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="meta">{tagline}</p>
  <p>{title} is a safe, provider-neutral bridge between Blender and external AI agents. Blender executes bounded helper tools, visual evidence capture, previews, approvals, checkpoints, and the local MCP bridge; external clients host the model and conversation.</p>

  <img class="hero" src="./assets/egypt-dogfight-hero.jpg" alt="Two aircraft in a Blender dogfight test scene with smoke and motion blur">

  <div class="panel">
    <h2>1. Install the Blender extension</h2>
    <ol>
      <li>Open Blender {min_blender} or newer.</li>
      <li>Open <strong>Edit &gt; Preferences &gt; Get Extensions</strong>.</li>
      <li>Add a remote extension repository with this URL:</li>
    </ol>
    <pre>{repository_url}</pre>
    <ol start="4">
      <li>Sync the repository, search for <strong>{title}</strong>, then install and enable it.</li>
      <li>Open the 3D View sidebar, start the bridge, and copy the MCP config for your external client.</li>
    </ol>
  </div>

  <h2>2. Choose the MCP runtime</h2>
  <div class="grid">
    <div class="panel">
      <h3>Bundled (default)</h3>
      <p>Press <strong>Copy MCP Config</strong> and paste it into your MCP client. The server is shipped with the extension, requires no extra installation, and retains source-tree diagnostics.</p>
    </div>
    <div class="panel">
      <h3>uvx / PyPI (optional)</h3>
      <p>Install <a href="https://docs.astral.sh/uv/getting-started/installation/">uv</a>, select <strong>uvx / PyPI</strong> in Blender preferences, then copy the config. It pins the matching release:</p>
      <pre>uvx --from blender-bridge=={version} blender-bridge</pre>
      <p>Windows configs use <code>cmd /c uvx</code>. Blender never installs software automatically.</p>
    </div>
  </div>

  <p><strong>Run only one MCP server instance against a Blender bridge.</strong> Both modes use the same protocol, canonical registry digest, tool contracts, and safety gates. Incompatible protocol or digest combinations fail closed.</p>

  <h2>Safety by design</h2>
  <div class="grid">
    <div class="panel"><h3>Bounded tools first</h3><p>Structured helpers cover routine scene work. Generated Python remains staged and approval-gated.</p></div>
    <div class="panel"><h3>Reversible editing</h3><p>Mutating helpers use visible preview transactions with commit, revert, and Blender undo paths.</p></div>
    <div class="panel"><h3>Local and inspectable</h3><p>The bridge binds to loopback, redacts audit data, exposes status and evidence resources, and stores no model-provider keys.</p></div>
  </div>

  <div class="panel clients">
    <h2>Client guides</h2>
    <p>
      <a href="{PROJECT_URL}/blob/main/docs/clients/CODEX.md">Codex</a>
      <a href="{PROJECT_URL}/blob/main/docs/clients/CLAUDE.md">Claude</a>
      <a href="{PROJECT_URL}/blob/main/docs/clients/CURSOR.md">Cursor</a>
      <a href="{PROJECT_URL}/blob/main/docs/clients/VSCODE.md">VS Code / Cline / Roo</a>
      <a href="{PROJECT_URL}/blob/main/docs/clients/CHATGPT.md">ChatGPT</a>
      <a href="{PROJECT_URL}/blob/main/docs/clients/GEMINI.md">Gemini CLI</a>
      <a href="{PROJECT_URL}/blob/main/docs/clients/OPENCODE.md">OpenCode</a>
      <a href="{PROJECT_URL}/blob/main/docs/clients/OLLAMA.md">Ollama hosts</a>
    </p>
  </div>

  <h2>Showcase</h2>
  <img class="hero" src="./assets/egypt-workflow-strip.jpg" alt="Three frames showing planning, visual evidence, and repair in the Egypt dogfight workflow">
  <p>This documented test workflow used scene inspection, helper previews, playblast/render evidence, repairs, and background rendering. Media is documentation-only; read its <a href="{PROJECT_URL}/blob/main/docs/assets/PROVENANCE.md">provenance and licensing boundary</a>.</p>
  <p><a href="{PROJECT_URL}/blob/main/docs/SHOWCASE.md">Curated showcase and submission guide</a></p>

  <div class="panel">
    <h2>Manual install fallback</h2>
    <p>Download the packaged extension ZIP from the <a href="{release_url}">latest GitHub release</a>, then use Blender's <strong>Install from Disk</strong>. Do not install GitHub's generated source-code ZIP.</p>
  </div>

  <h2>Current package</h2>
  <p>Latest package: <a href="./{html.escape(zip_name)}">{html.escape(zip_name)}</a> ({version})</p>
  <p>Archive hash: <code>{archive_hash}</code></p>
  <p>Project: <a href="{website}">{website}</a></p>
  <p><a href="{PROJECT_URL}/discussions">Discussions</a> · <a href="{PROJECT_URL}/issues">Issues</a> · <a href="{PROJECT_URL}/blob/main/CONTRIBUTING.md">Contributing</a> · <a href="{PROJECT_URL}/blob/main/SUPPORT.md">Support</a></p>
</body>
</html>
"""
    path = os.path.join(repo_dir, "index.html")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return path


def build_repository(
    *,
    zip_path="",
    repo_dir=DEFAULT_REPO_DIR,
    archive_base_url="",
    build_zip=False,
    blender="",
    repository_url=DEFAULT_REPOSITORY_URL,
    release_url=DEFAULT_RELEASE_URL,
):
    repo_dir = os.path.abspath(repo_dir)
    if build_zip or not zip_path:
        result = build_extension_zip.build_extension(blender=blender)
        zip_path = result["path"]
    zip_path = os.path.abspath(zip_path)
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"Extension zip not found: {zip_path}")

    zip_name = os.path.basename(zip_path)
    manifest = _read_zip_manifest(zip_path)
    extension_id = str(manifest["id"])

    os.makedirs(repo_dir, exist_ok=True)
    _remove_stale_packages(
        repo_dir,
        extension_id=extension_id,
        keep_names={zip_name, f"{zip_name}.sha256"},
    )

    repo_zip_path = os.path.join(repo_dir, zip_name)
    if not _is_same_file(zip_path, repo_zip_path):
        shutil.copy2(zip_path, repo_zip_path)

    sha_path = f"{zip_path}.sha256"
    repo_sha_path = os.path.join(repo_dir, os.path.basename(sha_path))
    if os.path.exists(sha_path):
        if not _is_same_file(sha_path, repo_sha_path):
            shutil.copy2(sha_path, repo_sha_path)
    else:
        digest = _sha256_file(zip_path)
        with open(os.path.join(repo_dir, f"{zip_name}.sha256"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{digest}  {zip_name}\n")

    entry = _manifest_entry(
        manifest,
        zip_name=zip_name,
        zip_path=repo_zip_path,
        archive_base_url=archive_base_url,
    )
    index_path = _write_index(repo_dir, entry)
    showcase_assets = _copy_showcase_assets(repo_dir)
    html_path = _write_html(repo_dir, entry, zip_name, repository_url=repository_url, release_url=release_url)
    return {
        "ok": True,
        "repo_dir": repo_dir,
        "index_path": index_path,
        "html_path": html_path,
        "zip_path": repo_zip_path,
        "archive_hash": entry["archive_hash"],
        "archive_url": entry["archive_url"],
        "repository_url": repository_url,
        "release_url": release_url,
        "showcase_assets": showcase_assets,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build a static Blender extension repository")
    parser.add_argument("--zip-path", default="", help="Packaged extension zip. Defaults to building the current extension.")
    parser.add_argument("--repo-dir", default=DEFAULT_REPO_DIR)
    parser.add_argument("--archive-base-url", default="", help="Optional absolute URL prefix for archive_url.")
    parser.add_argument("--build-zip", action="store_true", help="Build the extension zip before generating the repository.")
    parser.add_argument("--blender", default="", help="Optional Blender executable for official extension zip builds.")
    parser.add_argument("--repository-url", default=DEFAULT_REPOSITORY_URL, help="Blender remote repository URL shown on index.html.")
    parser.add_argument("--release-url", default=DEFAULT_RELEASE_URL, help="GitHub release URL shown on index.html.")
    args = parser.parse_args(argv)
    result = build_repository(
        zip_path=args.zip_path,
        repo_dir=args.repo_dir,
        archive_base_url=args.archive_base_url,
        build_zip=args.build_zip,
        blender=args.blender,
        repository_url=args.repository_url,
        release_url=args.release_url,
    )
    print(f"Built extension repository: {result['repo_dir']}")
    print(f"Index: {result['index_path']}")
    print(f"Archive: {result['zip_path']}")
    print(f"Hash: {result['archive_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
