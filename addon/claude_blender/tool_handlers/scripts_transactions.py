"""Blender-only handlers for the scripts_transactions domain."""

from __future__ import annotations

from .. import handler_runtime as _runtime

for _runtime_name, _runtime_value in vars(_runtime).items():
    if not _runtime_name.startswith("__"):
        globals()[_runtime_name] = _runtime_value
del _runtime_name, _runtime_value


def draft_privileged_script(context, args):
    result = draft_script(context, args)
    result["compatibility_alias"] = "draft_script"
    result["privileged_request"] = True
    return result


def draft_script(context, args):
    script_text = _extract_script_code(args)
    intent_text = "\n".join(
        str(args.get(key) or "")
        for key in ("intent", "expected_changes", "brief", "prompt")
    )
    guard_text = "\n".join([intent_text, script_text[:4000]])
    helper_advisory = None
    if _looks_like_render_job_intent(guard_text) and not helper_routing.has_explicit_animation_helper_gap(guard_text):
        helper_advisory = {
            "ok": True,
            "blocked": False,
            "code": "render_job_workflow_advised",
            "message": (
                "This looks like a long render or playblast job. Under trust the script is allowed, but "
                "start_render_job is usually more recoverable and avoids blocking the bridge."
            ),
            "recommended_tool": "start_render_job",
            "followup_tools": ["assemble_render_job_video", "validate_render_job_output"],
            "requires_user_approval": False,
        }
    if (
        _looks_like_animation_intent(guard_text)
        and not _animation_script_fallback_recently_allowed(context)
        and not helper_routing.has_explicit_animation_helper_gap(guard_text)
        and helper_advisory is None
    ):
        helper_advisory = {
            "ok": True,
            "blocked": False,
            "code": "animation_workflow_advised",
            "message": "Animation helpers may cover this; the script may still run under active trust.",
            "requires_user_approval": False,
            "animation_workflow_seen": _animation_workflow_recently_seen(context),
            "recommended_tools": [
                "plan_animation_workflow",
                "run_animation_workflow",
                "run_animation_task",
            ],
        }
    helper_first = helper_routing.helper_first_script_guard(guard_text)
    if helper_first and helper_advisory is None:
        helper_advisory = dict(helper_first)
        helper_advisory.update(
            {
                "ok": True,
                "blocked": False,
                "message": (
                    f"{helper_first.get('message', 'A structured helper is recommended')} "
                    "The script may still run under active trust."
                ),
                "requires_user_approval": False,
            }
        )
    if helper_advisory is None:
        helper_advisory = helper_routing.helper_first_script_advisory(guard_text)
    prefs = preferences.get_preferences(context)
    run_result = script_runner.run_trusted_script(
        context,
        code=script_text,
        intent=str(args.get("intent") or ""),
        expected_changes=str(args.get("expected_changes") or ""),
        risk_level=str(args.get("risk_level") or "medium"),
        target_objects=args.get("target_objects") or [],
        checkpoint_enabled=bool(getattr(prefs, "checkpoints_enabled", True)),
        checkpoint_dir=getattr(prefs, "checkpoint_dir", None),
    )
    if run_result.get("code") == "script_trust_required":
        run_result["message"] = (
            "Agent script trust is off. Start the bridge and select Trust Agent Scripts in Blender, "
            "or complete the task with bounded structured tools."
        )
    return {
        "ok": bool(run_result.get("ok")),
        "message": (
            "Script auto-ran with Blender Run Script permissions under active session trust"
            if run_result.get("ok")
            else run_result.get("message", "Trusted script did not run")
        ),
        "auto_ran": bool(run_result.get("auto_ran")),
        "auto_run_attempted": bool(run_result.get("auto_run_attempted")),
        "auto_run_reason": (
            "external_script_trust_active"
            if run_result.get("auto_run_attempted")
            else "external_script_trust_required"
        ),
        "authorization_model": "blender_run_script_equivalent",
        "blocked": bool(run_result.get("blocked")),
        "code": run_result.get("code"),
        "analysis": run_result.get("analysis"),
        "staged": run_result.get("prepared"),
        "run_result": run_result,
        "requires_user_approval": False,
        "helper_advisory": helper_advisory,
    }


def run_approved_script(context, args):
    return {
        "ok": False,
        "blocked": True,
        "code": "per_script_approval_removed",
        "message": (
            "Per-script approval was removed. Enable Trust Agent Scripts for the Blender session, "
            "then call draft_script again."
        ),
        "requires_user_approval": False,
    }


def commit_preview(context, args):
    return live_preview.commit(context)


def revert_preview(context, args):
    scope = str((args or {}).get("scope") or "all").strip().lower()
    if scope == "last_step":
        return live_preview.revert_last_created_step(context, allowed_types={"import_external_asset"})
    return live_preview.revert(context)


def register(handler_registry, specs):
    for spec in specs:
        try:
            handler = globals()[spec.handler_key]
        except KeyError as exc:
            raise KeyError(f"Missing handler {spec.handler_key} for {spec.name}") from exc
        handler_registry.register(spec.name, handler)
