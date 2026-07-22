"""Validate blender-bridge PyPI ownership and idempotent release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request


DEFAULT_NAME = "blender-bridge"
DEFAULT_PROJECT_URL = "https://github.com/CallMeJones/blender-agent-bridge"


class IncompleteReleaseError(RuntimeError):
    pass


def _normalized_url(value):
    return str(value or "").strip().lower().rstrip("/")


def project_matches(payload, expected_project_url):
    info = payload.get("info") if isinstance(payload, dict) else {}
    info = info if isinstance(info, dict) else {}
    candidates = [info.get("home_page"), info.get("project_url")]
    project_urls = info.get("project_urls")
    if isinstance(project_urls, dict):
        candidates.extend(project_urls.values())
    expected = _normalized_url(expected_project_url)
    return bool(expected and expected in {_normalized_url(value) for value in candidates})


def check_name(name=DEFAULT_NAME, expected_project_url=DEFAULT_PROJECT_URL, *, opener=urllib.request.urlopen):
    url = f"https://pypi.org/pypi/{name}/json"
    try:
        with opener(url, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"ok": True, "status": "unregistered", "message": f"PyPI name {name!r} is unregistered."}
        raise RuntimeError(f"PyPI availability check failed with HTTP {exc.code}") from exc
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"PyPI availability check failed: {exc}") from exc
    if not project_matches(payload, expected_project_url):
        raise RuntimeError(
            f"PyPI name {name!r} is already registered to a different project; stop for a naming decision."
        )
    version = str((payload.get("info") or {}).get("version") or "unknown")
    return {
        "ok": True,
        "status": "existing_project",
        "message": f"PyPI name {name!r} already identifies this project (latest {version}).",
    }


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _distribution_digests(dist_dir, name, version):
    normalized_name = re.sub(r"[-_.]+", "_", str(name or "").strip()).lower()
    normalized_version = str(version or "").strip().lower()
    wheel_prefix = f"{normalized_name}-{normalized_version}-"
    sdist_name = f"{normalized_name}-{normalized_version}.tar.gz"
    distributions = []
    for filename in sorted(os.listdir(dist_dir)):
        path = os.path.join(dist_dir, filename)
        if os.path.isfile(path) and (filename.endswith(".whl") or filename.endswith(".tar.gz")):
            distributions.append(filename)
    candidates = {
        filename: _sha256_file(os.path.join(dist_dir, filename))
        for filename in distributions
        if (filename.lower().startswith(wheel_prefix) and filename.lower().endswith(".whl"))
        or filename.lower() == sdist_name
    }
    unexpected = sorted(set(distributions) - set(candidates))
    if unexpected:
        raise RuntimeError(
            f"Distribution directory contains artifacts outside {name} {version}; unexpected={unexpected}"
        )
    if not candidates:
        raise RuntimeError(f"No {name} {version} wheel or source distribution found in {dist_dir!r}")
    if not any(filename.endswith(".whl") for filename in candidates):
        raise RuntimeError(f"No wheel found in {dist_dir!r}")
    if not any(filename.endswith(".tar.gz") for filename in candidates):
        raise RuntimeError(f"No source distribution found in {dist_dir!r}")
    return candidates


def check_release_artifacts(
    dist_dir,
    version,
    name=DEFAULT_NAME,
    *,
    require_complete=False,
    opener=urllib.request.urlopen,
):
    version = str(version or "").strip().removeprefix("v")
    if not version:
        raise RuntimeError("A release version is required for the PyPI artifact check")
    local = _distribution_digests(dist_dir, name, version)
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    try:
        with opener(url, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            if require_complete:
                raise IncompleteReleaseError(f"PyPI release {name} {version} is still unpublished") from exc
            return {
                "ok": True,
                "status": "unpublished",
                "publish_required": True,
                "local_files": sorted(local),
                "published_files": [],
                "message": f"PyPI release {name} {version} is unpublished; all artifacts must be uploaded.",
            }
        raise RuntimeError(f"PyPI release artifact check failed with HTTP {exc.code}") from exc
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"PyPI release artifact check failed: {exc}") from exc

    remote = {}
    for item in payload.get("urls") or []:
        filename = str(item.get("filename") or "")
        sha256 = str((item.get("digests") or {}).get("sha256") or "").lower()
        if not filename or not sha256:
            raise RuntimeError(f"PyPI release {name} {version} contains an artifact without a SHA-256 digest")
        if filename in remote:
            raise RuntimeError(f"PyPI release {name} {version} contains duplicate metadata for {filename}")
        remote[filename] = sha256

    unexpected = sorted(set(remote) - set(local))
    mismatched = sorted(filename for filename in set(remote) & set(local) if remote[filename] != local[filename])
    if unexpected or mismatched:
        raise RuntimeError(
            f"PyPI release {name} {version} does not match the tested artifact set; "
            f"unexpected={unexpected}, hash_mismatches={mismatched}"
        )

    missing = sorted(set(local) - set(remote))
    if missing:
        if require_complete:
            raise IncompleteReleaseError(f"PyPI release {name} {version} is incomplete; missing={missing}")
        status = "partially_published" if remote else "unpublished"
        return {
            "ok": True,
            "status": status,
            "publish_required": True,
            "local_files": sorted(local),
            "published_files": sorted(remote),
            "missing_files": missing,
            "message": (
                f"PyPI release {name} {version} has an identical published subset; "
                f"upload the missing artifacts: {', '.join(missing)}."
            ),
        }

    return {
        "ok": True,
        "status": "complete",
        "publish_required": False,
        "local_files": sorted(local),
        "published_files": sorted(remote),
        "missing_files": [],
        "message": f"PyPI release {name} {version} already contains the complete tested artifact set.",
    }


def check_release_artifacts_with_retry(
    dist_dir,
    version,
    name=DEFAULT_NAME,
    *,
    attempts=1,
    delay=0,
    sleep=time.sleep,
    **check_options,
):
    attempts = max(1, int(attempts or 1))
    for attempt in range(1, attempts + 1):
        try:
            return check_release_artifacts(dist_dir, version, name, **check_options)
        except IncompleteReleaseError:
            if attempt >= attempts:
                raise
            sleep(max(0, float(delay or 0)))
    raise AssertionError("unreachable")


def _write_github_output(path, result):
    if not path:
        return
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"publish_required={str(bool(result['publish_required'])).lower()}\n")
        handle.write(f"publication_status={result['status']}\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument("--expected-project-url", default=DEFAULT_PROJECT_URL)
    parser.add_argument("--dist-dir", default="")
    parser.add_argument("--version", default="")
    parser.add_argument("--github-output", default="")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--delay", type=float, default=0)
    args = parser.parse_args(argv)
    result = check_name(args.name, args.expected_project_url)
    print(result["message"])
    if bool(args.dist_dir) != bool(args.version):
        parser.error("--dist-dir and --version must be supplied together")
    if args.dist_dir:
        result = check_release_artifacts_with_retry(
            args.dist_dir,
            args.version,
            args.name,
            require_complete=args.require_complete,
            attempts=args.attempts,
            delay=args.delay,
        )
        _write_github_output(args.github_output, result)
        print(result["message"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
