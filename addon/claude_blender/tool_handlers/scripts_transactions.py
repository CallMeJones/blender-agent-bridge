"""Blender-only handlers for the scripts_transactions domain."""

from __future__ import annotations

from .. import handler_runtime as _runtime

for _runtime_name, _runtime_value in vars(_runtime).items():
    if not _runtime_name.startswith("__"):
        globals()[_runtime_name] = _runtime_value
del _runtime_name, _runtime_value


def draft_privileged_script(context, args):
    script_text = _extract_script_code(args)
    kind = str(args.get("script_kind") or "").strip().lower()
    if kind not in PRIVILEGED_SCRIPT_KINDS:
        return {
            "ok": False,
            "blocked": True,
            "code": "invalid_privileged_script_kind",
            "message": "script_kind must be external_asset, project_file, or asset_project_file.",
            "requires_user_approval": False,
        }
    capabilities = _privileged_script_capabilities(kind, args)
    approval_summary = str(args.get("approval_summary") or "").strip()
    declared_paths = _string_list_arg(args.get("declared_paths"))
    declared_urls = _string_list_arg(args.get("declared_urls"))
    destructive_actions = _string_list_arg(args.get("destructive_actions"))
    manifest_issues = []
    if not approval_summary:
        manifest_issues.append("approval_summary is required")
    if "project_file" in capabilities and not declared_paths:
        manifest_issues.append("declared_paths must include the project file path(s) to save/open/create")
    if "network" in capabilities and not declared_urls:
        manifest_issues.append("declared_urls must include the external URL(s), API endpoints, or asset sources")
    if manifest_issues:
        return {
            "ok": False,
            "blocked": True,
            "code": "privileged_manifest_required",
            "message": "Privileged scripts require an explicit approval manifest.",
            "issues": manifest_issues,
            "requires_user_approval": False,
        }
    intent_text = "\n".join(
        str(args.get(key) or "")
        for key in ("intent", "expected_changes", "approval_summary", "brief", "prompt")
    )
    guard_text = "\n".join([intent_text, script_text[:4000]])
    staged = script_runner.stage_script(
        context,
        code=script_text,
        intent=str(args.get("intent") or ""),
        expected_changes=str(args.get("expected_changes") or ""),
        risk_level=str(args.get("risk_level") or "high"),
        target_objects=args.get("target_objects") or [],
        privileged=True,
        privileged_kind=kind,
        privileged_capabilities=capabilities,
        approval_summary=approval_summary,
        declared_paths=declared_paths,
        declared_urls=declared_urls,
        destructive_actions=destructive_actions,
    )
    advisory = _privileged_helper_advisory(guard_text)
    if advisory:
        staged["helper_advisory"] = advisory
    staged.update(
        {
            "requires_explicit_one_time_approval": True,
            "trust_window_auto_run_allowed": False,
            "auto_run_attempted": False,
            "auto_ran": False,
            "auto_run_skipped_reason": "privileged_scripts_require_explicit_one_time_approval",
            "manifest_enforcement": "review_context_only",
            "manifest_notice": (
                "Declared paths, URLs, and destructive actions are shown for user review and audit. "
                "They are not a filesystem or network sandbox; inspect the script before approval."
            ),
            "approval_policy": (
                "Privileged asset/project-file scripts never auto-run under normal external script trust. "
                "Review the manifest in Blender, then run manually or issue a one-time external approval token."
            ),
        }
    )
    return staged


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
    if not script_runner.external_script_trust_active(context):
        return staged
    prefs = preferences.get_preferences(context)
    run_result = script_runner.run_externally_approved_script(
        context,
        "",
        checkpoint_enabled=bool(getattr(prefs, "checkpoints_enabled", True)),
        checkpoint_dir=getattr(prefs, "checkpoint_dir", None),
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
    prefs = preferences.get_preferences(context)
    return script_runner.run_externally_approved_script(
        context,
        str(args.get("approval_token") or ""),
        checkpoint_enabled=bool(getattr(prefs, "checkpoints_enabled", True)),
        checkpoint_dir=getattr(prefs, "checkpoint_dir", None),
    )


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
