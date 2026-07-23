"""Release metadata and documentation consistency checks."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tomllib
import urllib.parse
import urllib.request


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon", "claude_blender"))

import build_info  # noqa: E402


MANIFEST_PATH = os.path.join(ROOT, "addon", "claude_blender", "blender_manifest.toml")
CHANGELOG_PATH = os.path.join(ROOT, "CHANGELOG.md")
README_PATH = os.path.join(ROOT, "README.md")
INSTALL_PATH = os.path.join(ROOT, "docs", "INSTALL_FROM_GITHUB.md")
WORKFLOW_PATH = os.path.join(ROOT, ".github", "workflows", "mcp-smoke.yml")
RECOVERY_WORKFLOW_PATH = os.path.join(ROOT, ".github", "workflows", "resume-release.yml")
PYPROJECT_PATH = os.path.join(ROOT, "pyproject.toml")
REGISTRY_SNAPSHOT_PATH = os.path.join(ROOT, "tests", "snapshots", "tool_registry.json")
CLIENT_GUIDE_DIR = os.path.join(ROOT, "docs", "clients")
PAGES_INDEX_URL = "https://callmejones.github.io/blender-agent-bridge/index.json"
LIVE_PAGES_ENV = "BLENDER_AGENT_BRIDGE_LIVE_PAGES_SMOKE"
MAX_LIVE_ARCHIVE_BYTES = 100 * 1024 * 1024


def _read_text(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _read_manifest():
    with open(MANIFEST_PATH, "rb") as handle:
        return tomllib.load(handle)


def _read_pyproject():
    with open(PYPROJECT_PATH, "rb") as handle:
        return tomllib.load(handle)


def _enabled(name):
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _download_sha256(url, *, max_bytes=MAX_LIVE_ARCHIVE_BYTES):
    digest = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(url, timeout=30) as response:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            total += len(chunk)
            assert total <= max_bytes, f"Live archive exceeds {max_bytes} bytes: {url}"
            digest.update(chunk)
    return digest.hexdigest(), total


def _assert_no_hardcoded_release_examples(version):
    docs = [
        "README.md",
        os.path.join("docs", "EXTERNAL_BRIDGE_MCP.md"),
        os.path.join("docs", "INSTALL_FROM_GITHUB.md"),
        os.path.join("docs", "RELEASE.md"),
        os.path.join("docs", "TESTING_GUIDE.md"),
    ]
    versioned_zip = re.compile(r"claude_blender-\d+\.\d+\.\d+\.zip")
    versioned_tag = re.compile(r"v\d+\.\d+\.\d+")
    offenders = []
    for relative in docs:
        text = _read_text(os.path.join(ROOT, relative))
        for pattern in (versioned_zip, versioned_tag):
            for match in pattern.finditer(text):
                value = match.group(0)
                if version in value:
                    offenders.append(f"{relative}: hard-coded current release example {value!r}; use <version> or generated $Version")
                else:
                    offenders.append(f"{relative}: stale release example {value!r}")
    assert not offenders, "\n".join(offenders)


def _assert_local_release_metadata():
    manifest = _read_manifest()
    version = str(manifest.get("version") or "")
    assert version, manifest
    assert manifest.get("id") == build_info.ADDON_ID, manifest
    assert version == build_info.ADDON_VERSION, (version, build_info.ADDON_VERSION)
    assert tuple(int(part) for part in version.split(".")) == build_info.ADDON_VERSION_TUPLE, build_info.ADDON_VERSION_TUPLE
    assert build_info.MCP_SERVER_VERSION == build_info.ADDON_VERSION, build_info.MCP_SERVER_VERSION
    pyproject = _read_pyproject()
    project = pyproject.get("project") or {}
    project_scripts = project.get("scripts") or {}
    assert project.get("name") == build_info.MCP_DISTRIBUTION_NAME, project
    assert project.get("version") == version, project
    assert project.get("dependencies") == [], project
    assert project_scripts.get(build_info.MCP_CONSOLE_COMMAND) == "claude_blender.mcp_runtime.server:main", project_scripts
    with open(REGISTRY_SNAPSHOT_PATH, "r", encoding="utf-8") as handle:
        registry_snapshot = json.load(handle)
    assert registry_snapshot.get("registry_digest") == build_info.TOOL_REGISTRY_DIGEST, registry_snapshot.get("registry_digest")
    generated_uvx = build_info.mcp_config("http://127.0.0.1:1", launch_mode="uvx", platform_name="posix")
    generated_server = generated_uvx["mcpServers"]["blender"]
    assert f"{build_info.MCP_DISTRIBUTION_NAME}=={version}" in generated_server["args"], generated_server
    assert generated_server["env"]["CLAUDE_BLENDER_TOOL_REGISTRY_DIGEST"] == build_info.TOOL_REGISTRY_DIGEST
    for filename in os.listdir(CLIENT_GUIDE_DIR):
        if filename.endswith(".md") and filename != "README.md":
            guide = _read_text(os.path.join(CLIENT_GUIDE_DIR, filename))
            assert f"blender-bridge=={version}" in guide, filename
    blender_min = str(manifest.get("blender_version_min") or "")
    assert blender_min == build_info.BLENDER_VERSION_MIN, (blender_min, build_info.BLENDER_VERSION_MIN)
    assert tuple(int(part) for part in blender_min.split(".")) == build_info.BLENDER_VERSION_MIN_TUPLE

    changelog = _read_text(CHANGELOG_PATH)
    assert "## Unreleased" in changelog, "CHANGELOG.md is missing an Unreleased section"
    assert f"## {version}" in changelog, f"CHANGELOG.md is missing ## {version}"

    readme = _read_text(README_PATH)
    install = _read_text(INSTALL_PATH)
    assert "Blender 4.2+" in readme, "README badge must match the supported Blender baseline"
    assert f"Install Blender `{blender_min}` or newer" in readme, "README Quick Start minimum drifted"
    assert f"Install Blender `{blender_min}` or newer" in install, "Install guide minimum drifted"

    workflow = _read_text(WORKFLOW_PATH)
    recovery_workflow = _read_text(RECOVERY_WORKFLOW_PATH)
    assert "needs: [mcp-smoke, blender-smoke]" in workflow, "Tag artifact preparation must wait for both test jobs"
    assert "smoke_release_artifact_identity.py" in workflow, "Tag publication must verify archive identity"
    assert "smoke_published_release_identity.py" in workflow, "Tag publication must verify both public endpoints"
    assert "if: startsWith(github.ref, 'refs/tags/v')" in workflow, "Pages and release publication must be tag-gated"
    assert "pypa/gh-action-pypi-publish" in workflow, "Tagged releases must use PyPI Trusted Publishing"
    assert re.search(r"pypa/gh-action-pypi-publish@[0-9a-f]{40}", workflow), "PyPI publishing action must be SHA-pinned"
    assert "skip-existing: true" in workflow, "PyPI partial publication recovery must skip only preflight-verified files"
    assert "--require-complete" in workflow, "PyPI publication must verify the complete artifact set"
    assert "python scripts/check_pypi_name.py" in workflow, "PyPI name ownership must be checked immediately before publish"
    assert "python -m unittest discover" in workflow, "CI must run the conventional unittest lane"
    assert "workflow_dispatch:" in recovery_workflow, "Release recovery must require an explicit manual dispatch"
    assert "source_run_id:" in recovery_workflow, "Release recovery must identify the retained artifact run"
    assert "test \"$source_sha\" = \"$expected_sha\"" in recovery_workflow, (
        "Release recovery must bind retained artifacts to the immutable tag commit"
    )
    assert "--require-complete" in recovery_workflow, "Release recovery must verify exact published PyPI hashes"
    assert "smoke_release_artifact_identity.py" in recovery_workflow, (
        "Release recovery must verify extension and Pages archive identity before deployment"
    )
    assert "run-id: ${{ inputs.source_run_id }}" in recovery_workflow, (
        "Release recovery must reuse retained tested artifacts instead of rebuilding them"
    )
    assert "uses: actions/deploy-pages@v5" in recovery_workflow, "Release recovery must deploy Pages"
    assert "uses: softprops/action-gh-release@v3" in recovery_workflow, "Release recovery must publish the GitHub Release"
    assert "smoke_published_release_identity.py" in recovery_workflow, (
        "Release recovery must verify both public extension archives"
    )

    github_ref = str(os.environ.get("GITHUB_REF") or "")
    if github_ref.startswith("refs/tags/"):
        assert github_ref == f"refs/tags/v{version}", (github_ref, version)

    _assert_no_hardcoded_release_examples(version)
    return version


def _assert_live_pages_index(version):
    with urllib.request.urlopen(PAGES_INDEX_URL, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    entries = payload.get("data") if isinstance(payload.get("data"), list) else []
    matches = [entry for entry in entries if entry.get("id") == build_info.ADDON_ID]
    assert matches, payload
    entry = matches[0]
    expected_zip = f"{build_info.ADDON_ID}-{version}.zip"
    assert entry.get("version") == version, entry
    archive_url = str(entry.get("archive_url") or "")
    assert archive_url.endswith(expected_zip), entry
    archive_hash = str(entry.get("archive_hash") or "")
    expected_hash = archive_hash.removeprefix("sha256:")
    assert archive_hash.startswith("sha256:") and re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash), entry

    resolved_archive_url = urllib.parse.urljoin(PAGES_INDEX_URL, archive_url)
    actual_hash, actual_size = _download_sha256(resolved_archive_url)
    assert actual_hash == expected_hash.lower(), (resolved_archive_url, actual_hash, archive_hash)
    if entry.get("archive_size") is not None:
        assert int(entry["archive_size"]) == actual_size, (resolved_archive_url, actual_size, entry)


def main():
    version = _assert_local_release_metadata()
    if _enabled(LIVE_PAGES_ENV):
        _assert_live_pages_index(version)
        print(f"smoke_release_consistency: live Pages index and archive verified for {version}")
    else:
        print(f"smoke_release_consistency: local metadata ok for {version}; set {LIVE_PAGES_ENV}=1 for live Pages smoke")


if __name__ == "__main__":
    main()
