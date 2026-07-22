"""Blender-only handlers for the scripts_transactions domain."""

from __future__ import annotations

from .. import handler_runtime as _runtime

for _runtime_name, _runtime_value in vars(_runtime).items():
    if not _runtime_name.startswith("__"):
        globals()[_runtime_name] = _runtime_value
del _runtime_name, _runtime_value


def draft_privileged_script(context, args):
    return {
        "ok": False,
        "blocked": True,
        "code": "privileged_scripts_disabled",
        "message": (
            "Privileged generated Python is disabled. Use the bounded external-asset, project-file, "
            "project-directory filesystem, render, capture, save, or project-output tools instead."
        ),
        "requires_user_approval": False,
        "requires_explicit_one_time_approval": False,
        "trust_window_auto_run_allowed": False,
        "auto_run_attempted": False,
        "auto_ran": False,
        "recommended_tools": [
            "search_poly_haven_assets",
            "search_sketchfab_models",
            "start_external_asset_download",
            "get_external_asset_job_status",
            "start_external_asset_import_job",
            "list_project_files",
            "read_project_file",
            "write_project_file",
            "save_blend_file",
            "start_render_job",
        ],
    }


def draft_script(context, args):
    script_text = _extract_script_code(args)
    intent_text = "\n".join(
        str(args.get(key) or "")
        for key in ("intent", "expected_changes", "brief", "prompt")
    )
    guard_text = "\n".join([intent_text, script_text[:4000]])
    if _looks_like_render_job_intent(guard_text) and not helper_routing.has_explicit_animation_helper_gap(guard_text):
        return {
            "ok": False,
            "blocked": True,
            "message": (
                "This looks like a long render or playblast job. Use start_render_job first, then poll "
                "get_render_job_status. Use assemble_render_job_video and validate_render_job_output for "
                "PNG sequences unless the render helpers cannot express the request."
            ),
            "recommended_tool": "start_render_job",
            "followup_tools": ["assemble_render_job_video", "validate_render_job_output"],
            "requires_user_approval": False,
        }
    helper_advisory = None
    if (
        _looks_like_animation_intent(guard_text)
        and not _animation_script_fallback_recently_allowed(context)
        and not helper_routing.has_explicit_animation_helper_gap(guard_text)
    ):
        helper_advisory = {
            "ok": True,
            "blocked": False,
            "code": "animation_workflow_advised",
            "message": "Animation helpers may cover this, but advanced approved scripts are allowed when static checks pass.",
            "requires_user_approval": False,
            "animation_workflow_seen": _animation_workflow_recently_seen(context),
            "recommended_tools": [
                "plan_animation_workflow",
                "run_animation_workflow",
                "run_animation_task",
            ],
        }
    helper_first = helper_routing.helper_first_script_guard(guard_text)
    if helper_first:
        return helper_first
    if helper_advisory is None:
        helper_advisory = helper_routing.helper_first_script_advisory(guard_text)
    analysis = script_runner.analyze_script(script_text)
    if not analysis.get("ok"):
        return {
            "ok": False,
            "blocked": True,
            "code": "script_blocked_by_static_checks",
            "message": "Script blocked by static checks",
            "analysis": analysis,
            "requires_user_approval": False,
            "auto_run_attempted": False,
            "auto_ran": False,
            "helper_advisory": helper_advisory,
        }
    if analysis.get("explicit_approval_required") or not analysis.get("trust_window_allowed", True):
        return {
            "ok": False,
            "blocked": True,
            "code": "privileged_script_operation_disabled",
            "message": (
                "This script requires a privileged or one-time-approved operation. Generated Python cannot "
                "perform it; use the corresponding bounded structured tool instead."
            ),
            "analysis": analysis,
            "requires_user_approval": False,
            "auto_run_attempted": False,
            "auto_ran": False,
            "helper_advisory": helper_advisory,
        }
    if not script_runner.external_script_trust_active(context):
        return {
            "ok": False,
            "blocked": True,
            "code": "script_trust_required",
            "message": (
                "Agent script trust is off. Start the bridge and select Trust Agent Scripts in Blender, "
                "or complete the task with bounded structured tools."
            ),
            "analysis": analysis,
            "requires_user_approval": False,
            "auto_run_attempted": False,
            "auto_ran": False,
            "helper_advisory": helper_advisory,
        }
    staged = script_runner.stage_script(
        context,
        code=script_text,
        intent=str(args.get("intent") or ""),
        expected_changes=str(args.get("expected_changes") or ""),
        risk_level=str(args.get("risk_level") or "medium"),
        target_objects=args.get("target_objects") or [],
    )
    if helper_advisory:
        staged["helper_advisory"] = helper_advisory
    if not staged.get("ok") or staged.get("analysis", {}).get("blocked"):
        return staged
    prefs = preferences.get_preferences(context)
    run_result = script_runner.run_externally_approved_script(
        context,
        "",
        checkpoint_enabled=bool(getattr(prefs, "checkpoints_enabled", True)),
        checkpoint_dir=getattr(prefs, "checkpoint_dir", None),
    )
    if not run_result.get("ok"):
        script_runner.discard_pending_script(
            context,
            status=run_result.get("message", "Trusted script did not run"),
        )
    return {
        "ok": bool(run_result.get("ok")),
        "message": (
            "Script staged and auto-ran under active external script trust"
            if run_result.get("ok")
            else "Script staged but auto-run failed under active external script trust"
        ),
        "auto_ran": bool(run_result.get("ok")),
        "auto_run_attempted": True,
        "auto_run_reason": "external_script_trust_active",
        "staged": staged,
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
