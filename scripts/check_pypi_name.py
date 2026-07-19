"""Fail a release if the blender-bridge PyPI name belongs to another project."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


DEFAULT_NAME = "blender-bridge"
DEFAULT_PROJECT_URL = "https://github.com/CallMeJones/blender-agent-bridge"


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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument("--expected-project-url", default=DEFAULT_PROJECT_URL)
    args = parser.parse_args(argv)
    result = check_name(args.name, args.expected_project_url)
    print(result["message"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

