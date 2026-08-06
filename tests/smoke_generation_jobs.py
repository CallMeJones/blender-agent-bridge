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

print("== every provider declares whether it spends money ==")
# The point of declaring it per provider rather than checking a provider name
# is that adding a new one forces the decision. A provider that forgets is the
# one that quietly charges someone.
for name, spec in sorted(asset_jobs.JOB_PROVIDER_SPECS.items()):
    check("%s declares a spend policy" % name, "spends_money" in spec)
    check("%s spend policy is a bool" % name, isinstance(spec.get("spends_money"), bool))
check("tripo is declared paid", asset_jobs.JOB_PROVIDER_SPECS["tripo"]["spends_money"] is True)
check(
    "poly haven is declared free",
    asset_jobs.JOB_PROVIDER_SPECS["poly_haven"]["spends_money"] is False,
)
# Sketchfab authenticates but does not purchase on this path; if that ever
# changes, flipping the flag gates it with no other edit.
check(
    "sketchfab is declared free",
    asset_jobs.JOB_PROVIDER_SPECS["sketchfab"]["spends_money"] is False,
)

print("== only a human at the keyboard can spend money ==")
# The property under test is that no sequence of tool calls starts a paid job.
# An argument cannot carry consent: the bridge never sees the conversation, so
# a flag saying "the user agreed" is only the caller asserting it asked.
import bpy  # noqa: E402
from claude_blender import generation_spend  # noqa: E402
from claude_blender.tool_handlers import generation as generation_handler  # noqa: E402

image = os.path.join(bpy.app.tempdir, "smoke_reference.png")
with open(image, "wb") as handle:
    handle.write(b"\x89PNG\r\n\x1a\n")

# This smoke imports the package without registering it, so there is no
# preferences instance; the environment is the only configuration source and
# environment_overlay(None) contributes nothing over it.
os.environ["TRIPO_API_KEY"] = "tsk_smoke_key"
os.environ["BLENDER_AGENT_BRIDGE_GENERATION_EGRESS"] = "allow"
generation_spend.clear_requests()
JOB = {"provider": "tripo", "views": {"front": image}}

try:
    first = generation_handler.start_generation_job(bpy.context, dict(JOB))
    check("naming a paid provider does not start it", first.get("ok") is False, str(first)[:90])
    check("refusal waits on the user", first.get("awaiting_user_approval") is True)
    check("refusal states the cost", "30" in (first.get("cost") or {}).get("cost_note", ""))
    check("refusal names the upload", (first.get("cost") or {}).get("uploads_reference_images") is True)
    check("refusal points at a free path", bool(first.get("free_alternative")))

    # The bypass that made the previous gate ornamental: refuse, then retry.
    check(
        "retrying does not approve it",
        generation_handler.start_generation_job(bpy.context, dict(JOB)).get("ok") is False,
    )
    check(
        "no argument approves it",
        generation_handler.start_generation_job(
            bpy.context, dict(JOB, confirm_paid=True)
        ).get("ok") is False,
    )

    pending = generation_spend.pending_requests()
    check("exactly one request is pending", len(pending) == 1, str(len(pending)))

    # A different job must not ride on this request.
    other = generation_handler.start_generation_job(
        bpy.context, {"provider": "tripo", "views": {"front": image}, "model": "other"}
    )
    check("a different job raises its own request", other.get("ok") is False)
    check("requests are per job", len(generation_spend.pending_requests()) == 2)

    # The operator wiring is covered by smoke_ui_layout, which registers the
    # add-on; this smoke drives the store the operator writes to.
    generation_spend.set_status(pending[0]["request_id"], generation_spend.STATUS_APPROVED)
    check(
        "the job runs once the user approves in Blender",
        generation_handler.start_generation_job(bpy.context, dict(JOB)).get("ok") is True,
    )
    check(
        "the approval is single use",
        generation_handler.start_generation_job(bpy.context, dict(JOB)).get("ok") is False,
    )

    generation_spend.clear_requests()
    denied = generation_handler.start_generation_job(bpy.context, dict(JOB))
    generation_spend.set_status(
        denied["spend_approval"]["request_id"], generation_spend.STATUS_DENIED
    )
    after_denial = generation_handler.start_generation_job(bpy.context, dict(JOB))
    check("a declined job stays declined", after_denial.get("ok") is False)
    check("declining is not a retry prompt", not after_denial.get("awaiting_user_approval"))

    auto = generation_handler.start_generation_job(bpy.context, {"views": {"front": image}})
    check("omitting the provider never picks a paid one", auto.get("ok") is False, str(auto)[:90])

    missing = generation_handler.start_generation_job(
        bpy.context, {"provider": "tripo", "views": {"front": image + ".absent"}}
    )
    check("a missing reference image is refused first", missing.get("ok") is False)
finally:
    generation_spend.clear_requests()
    os.environ.pop("TRIPO_API_KEY", None)
    os.environ.pop("BLENDER_AGENT_BRIDGE_GENERATION_EGRESS", None)

if failures:
    print("\nsmoke_generation_jobs: FAILED (%d)" % len(failures))
    for item in failures:
        print("  - %s" % item)
    raise SystemExit(1)
print("\nsmoke_generation_jobs: ok")
