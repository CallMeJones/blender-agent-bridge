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
import tempfile


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import asset_job_worker, asset_jobs, generation_providers  # noqa: E402

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
implemented_generation = {
    spec.name for spec in generation_providers.PROVIDER_SPECS if spec.job_implemented
}
registered_generation = set(asset_jobs.JOB_PROVIDER_SPECS) - {"poly_haven", "sketchfab"}
check(
    "planned executable generation providers match the job registry",
    implemented_generation == registered_generation,
    "%s vs %s" % (sorted(implemented_generation), sorted(registered_generation)),
)
check(
    "generation spend policy comes from provider planning specs",
    all(
        asset_jobs.JOB_PROVIDER_SPECS[name]["spends_money"]
        == generation_providers.is_paid_provider(name)
        for name in registered_generation
    ),
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
check("generation needs views", "views" in asset_jobs._validate_generation("tripo", {"api_key": "k"}))
check(
    "generation needs key",
    "api_key" in asset_jobs._validate_generation("tripo", {"views": {"front": "a.png"}}),
)
check(
    "valid generation passes",
    asset_jobs._validate_generation("tripo", {"views": {"front": "a.png"}, "api_key": "k"}) == "",
)
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
check("meshy is declared paid", asset_jobs.JOB_PROVIDER_SPECS["meshy"]["spends_money"] is True)
check("local TripoSR is declared free", asset_jobs.JOB_PROVIDER_SPECS["triposr"]["spends_money"] is False)
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
from claude_blender import generation_providers, generation_spend  # noqa: E402
from claude_blender.tool_handlers import generation as generation_handler  # noqa: E402

print("== saved TripoSR defaults with per-job overrides ==")
triposr_preferences = type(
    "_TripoSRPreferences",
    (),
    {
        "triposr_mc_resolution": 192,
        "triposr_no_remove_bg": True,
        "triposr_foreground_ratio": 0.7,
        "triposr_chunk_size": 4096,
        "triposr_bake_texture": True,
        "triposr_texture_resolution": 1024,
    },
)()
saved_options = generation_handler._triposr_job_options({}, triposr_preferences)
check("saved resolution is used", saved_options["mc_resolution"] == 192, str(saved_options))
check("saved background mode is used", saved_options["no_remove_bg"] is True, str(saved_options))
check("saved foreground ratio is used", saved_options["foreground_ratio"] == 0.7, str(saved_options))
check("saved chunk size is used", saved_options["chunk_size"] == 4096, str(saved_options))
check("saved bake mode is used", saved_options["bake_texture"] is True, str(saved_options))
check("saved texture size is used", saved_options["texture_resolution"] == 1024, str(saved_options))
override_options = generation_handler._triposr_job_options(
    {"mc_resolution": 64, "no_remove_bg": False, "bake_texture": False},
    triposr_preferences,
)
check("per-job resolution wins", override_options["mc_resolution"] == 64, str(override_options))
check("per-job background mode wins", override_options["no_remove_bg"] is False, str(override_options))
check("per-job bake mode wins", override_options["bake_texture"] is False, str(override_options))

print("== historical job recovery preserves provider cancellation ==")
with tempfile.TemporaryDirectory(prefix="bab-generation-recovery-") as temp_dir:
    project_root = os.path.join(temp_dir, "capture-root", "project")
    current_capture_dir = os.path.join(project_root, "current-session")
    previous_capture_dir = os.path.join(project_root, "previous-session")
    recovered_job_id = "recovered-cancelled-job"
    recovered_job_dir = os.path.join(previous_capture_dir, "asset-jobs", recovered_job_id)
    os.makedirs(recovered_job_dir)
    metadata_path = os.path.join(recovered_job_dir, asset_jobs.METADATA_FILENAME)
    child_status_path = os.path.join(recovered_job_dir, asset_jobs.CHILD_STATUS_FILENAME)
    remote_cancellation = {
        "ok": True,
        "provider": "meshy",
        "task_id": "mesh-task",
        "task_kind": "image",
        "message": "Meshy task cancelled at the provider",
    }
    asset_jobs._write_json(
        metadata_path,
        {
            "available": True,
            "job_id": recovered_job_id,
            "metadata_path": metadata_path,
            "child_status_path": child_status_path,
            "status": "cancelled",
            "ok": False,
            "message": "Generating (1%)",
            "cancel_requested": False,
            "completed_at": 2.0,
            "started_at": 1.0,
            "provider_task_id": "mesh-task",
            "provider_task_kind": "image",
            "remote_cancellation": remote_cancellation,
        },
    )
    asset_jobs._write_json(
        child_status_path,
        {
            "status": "running",
            "message": "Generating (1%)",
            "progress": 0.3,
            "provider_task_id": "mesh-task",
            "provider_task_kind": "image",
        },
    )
    original_capture_dir_candidates = asset_jobs.viewport_capture.capture_dir_candidates
    asset_jobs.viewport_capture.capture_dir_candidates = lambda **_kwargs: [
        {
            "capture_dir": current_capture_dir,
            "storage_scope": "global",
            "project_id": "project",
            "session_id": "current-session",
            "base_dir": os.path.dirname(project_root),
            "fallback_reason": "",
        }
    ]
    try:
        recovered = asset_jobs.external_asset_job_status(recovered_job_id)
    finally:
        asset_jobs.viewport_capture.capture_dir_candidates = original_capture_dir_candidates
    check("historical job is discovered", recovered.get("available") is True, str(recovered))
    check("terminal cancellation wins over stale child state", recovered.get("status") == "cancelled", str(recovered))
    check("recovered cancellation remains requested", recovered.get("cancel_requested") is True, str(recovered))
    check("stale child message is healed", recovered.get("message") == "External asset job cancelled", str(recovered))
    check("provider cancellation receipt survives recovery", recovered.get("remote_cancellation") == remote_cancellation, str(recovered))

image = os.path.join(bpy.app.tempdir, "smoke_reference.png")
with open(image, "wb") as handle:
    handle.write(b"\x89PNG\r\n\x1a\n")

# This smoke imports the package without registering it, so there is no
# preferences instance; the environment is the only configuration source and
# environment_overlay(None) contributes nothing over it.
os.environ["TRIPO_API_KEY"] = "tsk_smoke_key"
os.environ["MESHY_API_KEY"] = "msy_smoke_key"
os.environ["BLENDER_AGENT_BRIDGE_GENERATION_EGRESS"] = "allow"
os.environ["BLENDER_AGENT_BRIDGE_TRIPOSR_PYTHON"] = "C:/smoke/python.exe"
os.environ["BLENDER_AGENT_BRIDGE_TRIPOSR_ROOT"] = "C:/smoke/TripoSR"
generation_spend.clear_requests()
JOB = {"provider": "tripo", "views": {"front": image}}
original_probe_hardware = generation_providers.probe_hardware
original_redraw = generation_handler._redraw_sidebar
redraw_calls = []
generation_providers.probe_hardware = lambda **_kwargs: {
    "probed": True,
    "cuda_available": True,
    "device_name": "Smoke GPU",
    "vram_gb": 8.0,
    "compute_capability": 7.5,
    "supports_bfloat16": False,
}
generation_handler._redraw_sidebar = lambda context: redraw_calls.append(context)

try:
    meshy_untextured = generation_handler.start_generation_job(
        bpy.context,
        {
            "provider": "meshy",
            "views": {"front": image},
            "meshy_options": {"should_texture": False},
        },
    )
    check(
        "Meshy untextured approval estimates 20 credits",
        (meshy_untextured.get("spend_approval") or {}).get("estimated_credits") == 20,
        str(meshy_untextured)[:180],
    )
    check(
        "Meshy approval names the reference and preset",
        (meshy_untextured.get("spend_approval") or {}).get("reference_files")
        == [os.path.normpath(os.path.abspath(image))]
        and (meshy_untextured.get("spend_approval") or {}).get("options_summary")
        == "blender_working",
        str(meshy_untextured.get("spend_approval")),
    )
    check("paid approval redraws the sidebar immediately", bool(redraw_calls))
    meshy_ultra = generation_handler.start_generation_job(
        bpy.context,
        {
            "provider": "meshy",
            "views": {"front": image},
            "meshy_options": {"texture_resolution": "8k", "ultra_mode": True},
        },
    )
    check(
        "Meshy 8K Ultra approval estimates 40 credits",
        (meshy_ultra.get("spend_approval") or {}).get("estimated_credits") == 40,
        str(meshy_ultra)[:180],
    )
    generation_spend.clear_requests()

    first = generation_handler.start_generation_job(bpy.context, dict(JOB))
    check("naming a paid provider does not start it", first.get("ok") is False, str(first)[:90])
    check("refusal waits on the user", first.get("awaiting_user_approval") is True)
    check("refusal states the cost", "30" in (first.get("cost") or {}).get("cost_note", ""))
    check("refusal names the upload", (first.get("cost") or {}).get("uploads_reference_images") is True)
    check("refusal points at a free path", bool(first.get("free_alternative")))
    check("refusal supplies an approval status tool", first.get("approval_status_tool") == "get_generation_approval_status")
    approval_args = first.get("approval_status_arguments") or {}
    pending_status = generation_handler.get_generation_approval_status(bpy.context, approval_args)
    check("agent can observe a pending click", pending_status.get("status") == generation_spend.STATUS_PENDING)
    check("pending click tells the agent to keep polling", pending_status.get("poll_after_seconds") == 2)

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
        bpy.context,
        {"provider": "tripo", "views": {"front": image}, "model": "P1-20260311"},
    )
    check("a different job raises its own request", other.get("ok") is False)
    check(
        "Tripo P1 textured approval estimates 50 credits",
        (other.get("spend_approval") or {}).get("estimated_credits") == 50,
        str(other.get("spend_approval")),
    )
    check("requests are per job", len(generation_spend.pending_requests()) == 2)

    # The operator wiring is covered by smoke_ui_layout, which registers the
    # add-on; this smoke drives the store the operator writes to.
    generation_spend.set_status(pending[0]["request_id"], generation_spend.STATUS_APPROVED)
    approved_status = generation_handler.get_generation_approval_status(
        bpy.context, {"request_id": pending[0]["request_id"]}
    )
    check("agent observes approval", approved_status.get("ready_to_start") is True, str(approved_status))
    check(
        "the job runs once the user approves in Blender",
        generation_handler.start_generation_job(bpy.context, dict(JOB)).get("ok") is True,
    )
    check(
        "the approval is single use",
        generation_handler.start_generation_job(bpy.context, dict(JOB)).get("ok") is False,
    )
    same_path_retry = generation_spend.pending_requests()[0]
    with open(image, "ab") as handle:
        handle.write(b"replacement")
    replaced = generation_handler.start_generation_job(bpy.context, dict(JOB))
    replaced_approval = replaced.get("spend_approval") or {}
    check(
        "replacing approved bytes at the same path requires a distinct approval",
        replaced.get("awaiting_user_approval") is True
        and replaced_approval.get("request_id") != same_path_retry.get("request_id")
        and replaced_approval.get("fingerprint") != same_path_retry.get("fingerprint"),
        str(replaced_approval),
    )

    generation_spend.clear_requests()
    denied = generation_handler.start_generation_job(bpy.context, dict(JOB))
    generation_spend.set_status(
        denied["spend_approval"]["request_id"], generation_spend.STATUS_DENIED
    )
    denied_status = generation_handler.get_generation_approval_status(
        bpy.context, {"request_id": denied["spend_approval"]["request_id"]}
    )
    check("agent observes decline", denied_status.get("declined") is True, str(denied_status))
    after_denial = generation_handler.start_generation_job(bpy.context, dict(JOB))
    check("a declined job stays declined", after_denial.get("ok") is False)
    check("declining is not a retry prompt", not after_denial.get("awaiting_user_approval"))

    auto = generation_handler.start_generation_job(bpy.context, {"views": {"front": image}})
    check("omitting an ambiguous provider starts nothing", auto.get("ok") is False, str(auto)[:90])
    check("ambiguous provider requires a user choice", auto.get("provider_selection_required") is True, str(auto)[:160])
    check(
        "all runnable providers are offered",
        auto.get("suggested_providers") == ["triposr", "tripo", "meshy"],
        str(auto.get("suggested_providers")),
    )

    missing = generation_handler.start_generation_job(
        bpy.context, {"provider": "tripo", "views": {"front": image + ".absent"}}
    )
    check("a missing reference image is refused first", missing.get("ok") is False)
finally:
    generation_handler._redraw_sidebar = original_redraw
    generation_providers.probe_hardware = original_probe_hardware
    generation_spend.clear_requests()
    for name in (
        "TRIPO_API_KEY",
        "MESHY_API_KEY",
        "BLENDER_AGENT_BRIDGE_GENERATION_EGRESS",
        "BLENDER_AGENT_BRIDGE_TRIPOSR_PYTHON",
        "BLENDER_AGENT_BRIDGE_TRIPOSR_ROOT",
    ):
        os.environ.pop(name, None)

if failures:
    print("\nsmoke_generation_jobs: FAILED (%d)" % len(failures))
    for item in failures:
        print("  - %s" % item)
    raise SystemExit(1)
print("\nsmoke_generation_jobs: ok")
