"""Blender background smoke for the generation job provider dispatch.

Lives here rather than in tests/unit because ``asset_jobs`` imports bpy. The
properties asserted are the ones that matter for a paid, credential-bearing
provider: the key never reaches disk, and every registered provider has a
worker behind it.
"""

from __future__ import annotations

import json
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import asset_job_worker, asset_jobs  # noqa: E402

API_KEY = "tsk_job_secret_must_not_reach_disk"

failures = []


def check(label, condition, detail=""):
    if condition:
        print("  ok   %s" % label)
    else:
        failures.append(label)
        print("  FAIL %s %s" % (label, detail))


print("== secret handling ==")
written = asset_jobs._worker_config_args(
    "tripo", {"views": {"front": "a.png"}, "api_key": API_KEY, "model": "v3.1-20260211"}
)
check("api_key stripped from on-disk config", "api_key" not in written)
check("key value absent from serialized config", API_KEY not in json.dumps(written))
check("non-secret args survive", written.get("model") == "v3.1-20260211")

secrets = asset_jobs._provider_secrets("tripo")
check(
    "key travels only through child env",
    secrets == (("api_key", asset_jobs.ASSET_JOB_SECRET_TOKEN_ENV),),
    str(secrets),
)

env = asset_jobs._child_env({"api_key": API_KEY}, "tripo")
check("child env carries the key", env.get(asset_jobs.ASSET_JOB_SECRET_TOKEN_ENV) == API_KEY)

recorded = asset_jobs._redacted_parameters(
    "tripo", {"views": {"front": "a.png", "left": "b.png"}, "api_key": API_KEY}
)
check("metadata records presence not value", recorded.get("api_key_supplied") is True)
check("metadata has no key value", API_KEY not in json.dumps(recorded))
check("metadata classifies multiview", recorded.get("generation_kind") == "multiview")
check("metadata lists view names", recorded.get("view_names") == ["front", "left"])

print("== existing providers unchanged ==")
poly = asset_jobs._redacted_parameters("poly_haven", {"asset_id": "rock_01"})
check("poly haven redaction intact", poly.get("asset_id") == "rock_01")
sketch = asset_jobs._redacted_parameters("sketchfab", {"uid": "abc", "api_token": "secret"})
check("sketchfab redaction intact", sketch.get("api_token_supplied") is True)
check("sketchfab token value absent", "secret" not in json.dumps(sketch))
check("sketchfab secrets still declared", len(asset_jobs._provider_secrets("sketchfab")) == 2)
check("poly haven declares no secrets", asset_jobs._provider_secrets("poly_haven") == ())

print("== dispatch table ==")
check(
    "every provider has a worker",
    set(asset_jobs.JOB_PROVIDER_SPECS) == set(asset_job_worker.WORKER_DISPATCH),
    "%s vs %s" % (sorted(asset_jobs.JOB_PROVIDER_SPECS), sorted(asset_job_worker.WORKER_DISPATCH)),
)
check("tripo registered", "tripo" in asset_jobs.JOB_PROVIDER_SPECS)
check("catalog providers retained", {"poly_haven", "sketchfab"} <= set(asset_jobs.JOB_PROVIDER_SPECS))

rejected = asset_jobs.start_external_asset_download(None, provider="nope")
check("unknown provider rejected", rejected.get("ok") is False)
check(
    "rejection names the known providers",
    all(name in rejected.get("message", "") for name in asset_jobs.JOB_PROVIDER_NAMES),
    rejected.get("message", ""),
)

print("== validation ==")
check("generation needs views", "views" in asset_jobs._validate_generation({"api_key": "k"}))
check("generation needs key", "api_key" in asset_jobs._validate_generation({"views": {"front": "a.png"}}))
check("valid generation passes", asset_jobs._validate_generation({"views": {"front": "a.png"}, "api_key": "k"}) == "")
check("poly haven needs asset_id", "asset_id" in asset_jobs._validate_poly_haven({}))
check("sketchfab needs uid", "uid" in asset_jobs._validate_sketchfab({}))

if failures:
    print("\nsmoke_generation_jobs: FAILED (%d)" % len(failures))
    for item in failures:
        print("  - %s" % item)
    raise SystemExit(1)
print("\nsmoke_generation_jobs: ok")
