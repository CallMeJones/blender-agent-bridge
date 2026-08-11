"""Handlers for the image-to-3D generation domain.

Credentials and machine paths come from add-on preferences because these
handlers run inside Blender and never see the MCP server process environment.
Generation jobs reuse the external-asset job machinery so they inherit the
subprocess worker, cancel, restart recovery, and the whole cache/import tail.
"""

from __future__ import annotations

import json
import os

from .. import (
    asset_jobs,
    generation_clients,
    generation_meshy,
    generation_providers,
    generation_tripo,
    generation_spend,
    preferences,
)
from .support import _bounded_float, _bounded_int


def _generation_environ(context):
    prefs = preferences.get_preferences(context)
    environ = dict(os.environ)
    environ.update(generation_providers.environment_overlay(prefs))
    return environ


def get_generation_provider_diagnostics(context, args):
    environ = _generation_environ(context)
    # The probe result is cached per interpreter, so the default path costs
    # nothing after the first call; refresh_hardware forces a re-probe when a
    # user has just installed torch or switched interpreters.
    hardware = generation_providers.probe_hardware(
        python_executable=str(args.get("probe_python") or ""),
        environ=environ,
        use_cache=not bool(args.get("refresh_hardware", False)),
    )
    report = generation_providers.generation_provider_diagnostics(
        environ=environ, hardware=hardware
    )
    report["credential_source"] = "addon_preferences_over_environment"
    report["ok"] = True
    return report


_VIEW_SLOTS = ("front", "left", "back", "right")


def _first_configured(environ, names):
    for name in names:
        value = str(environ.get(name, "") or "").strip()
        if value:
            return value
    return ""


def _runtime_requirement_value(spec, environ, label):
    for requirement_label, names in getattr(spec, "runtime_requirements", ()) or ():
        if str(requirement_label or "").strip().lower() == label:
            return _first_configured(environ, names)
    return ""


def _triposr_job_options(args, prefs):
    """Resolve saved TripoSR defaults with per-job arguments taking precedence."""

    def value(argument, preference, default):
        if argument in args:
            return args.get(argument)
        return getattr(prefs, preference, default)

    return {
        "mc_resolution": _bounded_int(
            value("mc_resolution", "triposr_mc_resolution", 256), 256, minimum=16, maximum=512
        ),
        "no_remove_bg": bool(value("no_remove_bg", "triposr_no_remove_bg", False)),
        "foreground_ratio": _bounded_float(
            value("foreground_ratio", "triposr_foreground_ratio", 0.85),
            0.85,
            minimum=0.1,
            maximum=1.0,
        ),
        "chunk_size": _bounded_int(
            value("chunk_size", "triposr_chunk_size", 8192), 8192, minimum=0, maximum=262144
        ),
        "bake_texture": bool(value("bake_texture", "triposr_bake_texture", False)),
        "texture_resolution": _bounded_int(
            value("texture_resolution", "triposr_texture_resolution", 2048),
            2048,
            minimum=256,
            maximum=8192,
        ),
    }


def _view_warnings(views, provider=""):
    """Say what a partial or uncalibrated view set will cost the result.

    Tripo uses fixed positional slots. Meshy 7 uses the front image as primary
    conditioning and treats the remaining images as unordered supporting
    angles. Both still need honest image labels for provenance and evaluation.
    """

    warnings = []
    supplied = [name for name in _VIEW_SLOTS if name in views]
    missing = [name for name in _VIEW_SLOTS if name not in views]
    if missing:
        warnings.append(
            "Only %s supplied. The provider invents everything the %s view%s would have "
            "shown; on a character that is typically the back of the hair, clothing "
            "fastenings, and anything the front hides."
            % (
                ", ".join(supplied) or "one view",
                ", ".join(missing),
                "" if len(missing) == 1 else "s",
            )
        )
    provider = str(provider or "").strip().lower()
    if len(supplied) > 1 and provider == "meshy":
        warnings.append(
            "Meshy uses 'front' as the primary first image. Remaining images may be "
            "different supporting angles in any order; their names are retained for "
            "provenance and evaluation rather than sent as positional API slots."
        )
    elif len(supplied) > 1:
        warnings.append(
            "Views are positional slots, not labels: each image must be the orthographic "
            "view its slot names. A three-quarter image placed in 'left' degrades the "
            "model silently rather than failing."
        )
    return warnings


def plan_image_to_3d_approach(context, args):
    """List every route from a reference image to a model, for the user to pick.

    Exists because the alternative is an agent quietly choosing on the user's
    behalf. The routes differ in ways only the user can weigh -- money, whether
    their artwork leaves the machine, how long it takes, and how editable the
    result is -- so this returns the options and refuses to rank them.
    """

    environ = _generation_environ(context)
    hardware = generation_providers.probe_hardware(environ=environ)
    diagnostics = generation_providers.generation_provider_diagnostics(
        environ=environ, hardware=hardware
    )
    by_name = {item["provider"]: item for item in diagnostics["providers"]}

    routes = [
        {
            "id": "authored",
            "title": "Author it in Blender",
            "how": "Bounded helpers and trusted scripts build the mesh from reference guides.",
            "cost": "Free.",
            "data_leaves_machine": False,
            "ready": True,
            "produces": "Clean, editable topology you own from the first vertex.",
            "effort": "Slowest. Best when the model must be rigged, edited, or matched precisely.",
        }
    ]
    for spec in generation_providers.PROVIDER_SPECS:
        report = by_name.get(spec.name) or {}
        hosted = spec.kind == generation_providers.KIND_HOSTED_API
        no_backend = (
            report.get("run_status") == generation_providers.RUN_STATUS_NO_JOB_BACKEND
        )
        # Config blockers are dropped for a provider with no backend. They are
        # accurate but unactionable, and offering them beside the real reason
        # invites the reader to act on the fixable-looking one: a planner
        # offered "install TripoSR first, then generate locally at no cost",
        # which no amount of installing could deliver.
        routes.append(
            {
                "id": spec.name,
                "title": spec.title,
                "how": (
                    "Uploads the reference images to a third-party service."
                    if hosted
                    else "Runs the model on hardware you control."
                ),
                "cost": spec.cost_note or "Free; uses your own compute.",
                "data_leaves_machine": bool(spec.requires_egress),
                "ready": bool(report.get("runnable")),
                "why_not_ready": str(report.get("run_blocker") or ""),
                "produces": (
                    "A fast local blockout mesh. Single-view TripoSR cannot know the back or side structure."
                    if spec.name == "triposr"
                    else "A generated mesh, typically dense and not rig-ready."
                ),
                "blockers": [] if no_backend else (report.get("blockers") or []),
                "remedies": [] if no_backend else (report.get("remedies") or []),
                "actionable": not no_backend,
                "license_note": spec.license_note,
                "quality_route": (
                    "blockout"
                    if spec.name == "triposr"
                    else ("multi_view_final_candidate" if spec.supports_multiview else "generated")
                ),
                "quality_note": (
                    "Prefer hosted Tripo multi-view or a studio endpoint when the final asset needs plausible "
                    "side/back structure."
                    if spec.name == "triposr"
                    else ""
                ),
            }
        )

    policy = generation_providers.session_generation_policy()
    for route in routes:
        if route["id"] == "authored":
            continue
        forbidden = generation_providers.policy_refusal(route["id"])
        if forbidden:
            route["ready"] = False
            route["why_not_ready"] = forbidden

    ready = [route for route in routes if route["ready"]]
    ready_generation_routes = [route for route in ready if route["id"] != "authored"]
    paid_ready = [route for route in ready if route["id"] != "authored" and route["data_leaves_machine"]]
    provider_choice_needed = len(ready_generation_routes) > 1

    # With no key configured, uploads switched off, or no local runtime, the
    # authored route is the only one left -- and a question with one answer is
    # not a choice, it is an interruption. Asking anyway trains people to click
    # through the prompt, which blunts it for the times it does matter.
    choice_needed = len(ready) > 1
    if choice_needed:
        message = (
            "Several routes can build this. They differ in cost and in whether the "
            "reference images leave the machine, so the user chooses -- do not pick one "
            "for them, and do not start work on any route before they answer."
        )
        question = "How would you like this built? %s" % " | ".join(
            "%s (%s)" % (route["title"], route["cost"]) for route in ready
        )
    else:
        message = (
            "Only the authored route is available, so there is nothing to choose. "
            "Do not ask the user and do not raise provider setup unless they bring it "
            "up: proceed with scripts, bounded helpers, and the bridge tools."
        )
        question = ""

    return {
        "ok": True,
        "requires_user_choice": choice_needed,
        "message": message,
        "question": question,
        "routes": routes,
        "ready_routes": [route["id"] for route in ready],
        "generation_provider_selection_required": provider_choice_needed,
        "generation_provider_choices": [route["id"] for route in ready_generation_routes],
        "provider_question": (
            "Which generation provider do you want to use? %s"
            % " | ".join(route["title"] for route in ready_generation_routes)
            if provider_choice_needed
            else ""
        ),
        "paid_routes": [route["id"] for route in paid_ready],
        "generation_policy": policy,
        "note": (
            "A paid route additionally needs the user to click Approve in the Blender "
            "sidebar before it starts, so asking here does not replace that."
        ),
    }


def set_generation_policy(context, args):
    """Record a standing instruction about how work may be done this session."""

    policy = str(args.get("policy") or "").strip().lower()
    try:
        recorded = generation_providers.set_session_generation_policy(
            policy, reason=str(args.get("reason") or "")
        )
    except ValueError as error:
        return {
            "ok": False,
            "message": str(error),
            "known_policies": list(generation_providers.GENERATION_POLICIES),
        }
    return {
        "ok": True,
        "message": "Standing instruction recorded for this Blender session. %s"
        % generation_providers.POLICY_LABELS[recorded["policy"]],
        "generation_policy": recorded,
        "note": (
            "Enforced in the bridge, so it holds for the rest of the session even after "
            "it leaves your context. Only the user can relax it."
        ),
    }


def start_generation_job(context, args):
    environ = _generation_environ(context)

    views = {
        str(name): str(path)
        for name, path in (args.get("views") or {}).items()
        if str(path or "").strip()
    }
    if not views:
        return {"ok": False, "message": "views must map at least one view name to an image path"}

    missing = [path for path in views.values() if not os.path.isfile(path)]
    if missing:
        return {
            "ok": False,
            "message": "Reference image not found: %s" % missing[0],
            "hint": "Supply local paths the user confirmed; the bridge does not invent paths.",
        }

    selection = generation_providers.select_provider(
        preferred=str(args.get("provider") or ""),
        environ=environ,
        hardware=generation_providers.probe_hardware(environ=environ),
        require_multiview=len(views) > 1,
    )
    if not selection.get("ok"):
        # Hand back the full diagnostics so the caller can fix the deployment
        # rather than guess which of several conditions failed.
        result = {
            "ok": False,
            "message": selection.get("message") or "No generation provider is available",
            "diagnostics": selection.get("diagnostics"),
        }
        for key in (
            "requires_explicit_choice",
            "provider_selection_required",
            "suggested_providers",
            "provider_choices",
            "unimplemented_providers",
            "generation_policy",
            "policy_blocked",
        ):
            if key in selection:
                result[key] = selection[key]
        return result

    provider = selection["selected"]
    provider_spec = generation_providers.PROVIDERS_BY_NAME[provider]

    if provider == "meshy" and len(views) > 1 and "front" not in views:
        return {
            "ok": False,
            "message": "Meshy multi-image generation requires a primary 'front' image",
            "hint": "Put the primary/front reference in views.front; remaining angles may use the other view names in any order.",
        }

    # A standing instruction outranks everything below it, including an
    # explicit confirm_paid. If the user said "no APIs, just scripts" an hour
    # ago, that is still true now whether or not it is still in context.
    refusal = generation_providers.policy_refusal(provider)
    if refusal:
        return {
            "ok": False,
            "message": "Refused by the user's standing instruction for this session. %s" % refusal,
            "provider": provider,
            "generation_policy": generation_providers.session_generation_policy(),
            "hint": "Build it with authored scripts and bounded helpers instead.",
        }

    # The spend gate lives in asset_jobs.start_external_asset_download, the
    # single seam every job of every kind passes through. Duplicating it here
    # would create a second thing to keep in step with the first.

    if provider not in asset_jobs.JOB_PROVIDER_SPECS:
        return {
            "ok": False,
            "message": "Provider %s is available but has no job implementation yet" % provider,
            "implemented_providers": [
                name for name in asset_jobs.JOB_PROVIDER_NAMES if name not in ("poly_haven", "sketchfab")
            ],
        }

    api_key = ""
    for name in provider_spec.credential_env_vars:
        api_key = str(environ.get(name, "") or "").strip()
        if api_key:
            break

    prefs = preferences.get_preferences(context)
    job_args = {
        "views": views,
        "api_key": api_key,
        "model": str(args.get("model") or ""),
        "face_limit": _bounded_int(args.get("face_limit"), 0, minimum=0, maximum=1000000),
        "cache_dir": str(args.get("cache_dir") or ""),
        "timeout": _bounded_int(args.get("timeout"), 120, minimum=1, maximum=300),
        "license_note": provider_spec.license_note,
    }
    if "texture" in args:
        job_args["texture"] = bool(args.get("texture"))
    if provider == "meshy":
        job_args["meshy_options"] = args.get("meshy_options")
        try:
            resolved = generation_meshy.resolve_job_policy(
                job_args,
                view_count=len(views),
            )
        except ValueError as error:
            return {"ok": False, "message": str(error), "provider": provider}
        job_args["meshy_options"] = resolved["options"]
        job_args["estimated_cost"] = resolved["estimated_credits"]
    if provider == "tripo":
        try:
            resolved = generation_tripo.resolve_job_policy(job_args)
        except ValueError as error:
            return {"ok": False, "message": str(error), "provider": provider}
        job_args.update(resolved["options"])
        job_args["estimated_cost"] = resolved["estimated_credits"]
    if provider == "triposr":
        job_args.update(_triposr_job_options(args, prefs))
    endpoint = _first_configured(environ, provider_spec.endpoint_env_vars)
    if endpoint:
        job_args["endpoint"] = endpoint
    runtime_python = _runtime_requirement_value(provider_spec, environ, "python")
    if runtime_python:
        job_args["runtime_python"] = runtime_python
    runtime_root = _runtime_requirement_value(provider_spec, environ, "root")
    if runtime_root:
        job_args["runtime_root"] = runtime_root

    started = asset_jobs.start_external_asset_download(
        context,
        provider=provider,
        job_name=str(args.get("job_name") or "generation"),
        note=str(args.get("note") or ""),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
        **job_args,
    )
    # Carried on both the approval request and the started job: the cost of a
    # partial view set is worth stating before the user approves it, and worth
    # repeating once the mesh exists and looks wrong on the unseen side.
    warnings = _view_warnings(views, provider)
    if warnings and isinstance(started, dict):
        started["view_warnings"] = warnings
    return started


def get_generation_job_status(context, args):
    prefs = preferences.get_preferences(context)
    job = asset_jobs.external_asset_job_status(
        str(args.get("job_id") or ""),
        context=context,
        preferred_dir=getattr(prefs, "capture_cache_dir", None),
    )
    return {
        "ok": bool(job.get("available", False)),
        "message": "Generation job status collected" if job.get("available") else job.get("message", "Generation job was not found"),
        "asset_job": job,
    }


def get_generation_approval_status(_context, args):
    request_id = str(args.get("request_id") or "").strip()
    record = generation_spend.request_state(request_id)
    if record is None:
        return {
            "ok": False,
            "available": False,
            "request_id": request_id,
            "message": "Generation approval request was not found in this Blender session",
        }

    status = str(record.get("status") or "")
    if status == generation_spend.STATUS_PENDING:
        message = "Waiting for the user to approve or decline this paid generation request in Blender"
        next_action = "wait_for_user"
    elif status == generation_spend.STATUS_APPROVED:
        message = "The user approved this paid generation request in Blender"
        next_action = "start_exact_job"
    elif status == generation_spend.STATUS_DENIED:
        message = "The user declined this paid generation request in Blender"
        next_action = "stop"
    elif status == generation_spend.STATUS_EXPIRED:
        message = "This generation approval expired before the paid job started"
        next_action = "request_new_approval"
    else:
        message = "This single-use generation approval has already been consumed"
        next_action = "approval_consumed"

    return {
        "ok": True,
        "available": True,
        "request_id": request_id,
        "provider": str(record.get("provider") or ""),
        "title": str(record.get("title") or ""),
        "status": status,
        "decision_received": status in {generation_spend.STATUS_APPROVED, generation_spend.STATUS_DENIED},
        "approved": status == generation_spend.STATUS_APPROVED,
        "declined": status == generation_spend.STATUS_DENIED,
        "ready_to_start": status == generation_spend.STATUS_APPROVED,
        "terminal": status != generation_spend.STATUS_PENDING,
        "poll_after_seconds": 2 if status == generation_spend.STATUS_PENDING else 0,
        "next_action": next_action,
        "message": message,
        "spend_approval": record,
    }


def cancel_provider_generation_task(context, asset_job):
    """Cancel supported hosted tasks without persisting provider credentials."""

    asset_job = asset_job if isinstance(asset_job, dict) else {}
    provider = str(asset_job.get("provider") or "").strip().lower()
    task_id = str(asset_job.get("provider_task_id") or "").strip()
    if provider != "meshy" or not task_id:
        return {}

    spec = generation_providers.PROVIDERS_BY_NAME.get(provider)
    environ = _generation_environ(context)
    api_key = _first_configured(environ, getattr(spec, "credential_env_vars", ()) or ())
    if not api_key:
        return {
            "ok": False,
            "provider": provider,
            "task_id": task_id,
            "message": "Meshy task ID was recovered, but no Meshy credential is configured",
        }
    try:
        return generation_clients.MeshyClient(api_key, timeout=15).cancel_task(
            task_id,
            task_kind=str(asset_job.get("provider_task_kind") or ""),
        )
    except generation_clients.GenerationError as error:
        return {
            "ok": False,
            "provider": provider,
            "task_id": task_id,
            "message": "Meshy provider cancellation failed: %s" % error,
        }


def _resolve_scene_objects(context, args, *, default_active=True):
    import bpy

    names = []
    object_names = args.get("object_names")
    if isinstance(object_names, str):
        names.append(object_names)
    elif isinstance(object_names, (list, tuple)):
        names.extend(str(name) for name in object_names)
    target_name = str(args.get("target_object_name") or "").strip()
    if target_name:
        names.insert(0, target_name)

    seen = set()
    objects = []
    missing = []
    for name in names:
        name = str(name or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        obj = bpy.data.objects.get(name)
        if obj is None:
            missing.append(name)
        else:
            objects.append(obj)

    if not objects and bool(args.get("selected_only", False)):
        objects = list(getattr(context, "selected_objects", []) or [])
    if not objects and default_active and getattr(context, "active_object", None):
        objects = [context.active_object]

    max_objects = _bounded_int(args.get("max_objects"), 12, minimum=1, maximum=64)
    return objects[:max_objects], missing


def _mesh_objects(objects):
    return [obj for obj in objects or [] if getattr(obj, "type", "") == "MESH" and getattr(obj, "data", None)]


def cleanup_generated_asset(context, args):
    from .. import live_preview

    objects, missing = _resolve_scene_objects(context, args)
    meshes = _mesh_objects(objects)
    if not meshes:
        return {
            "ok": False,
            "message": "A generated mesh object is required for cleanup",
            "missing_object_names": missing,
        }

    shade_smooth = bool(args.get("shade_smooth", True))
    add_weighted_normals = bool(args.get("add_weighted_normals", True))
    decimate_ratio = _bounded_float(args.get("decimate_ratio"), 1.0, minimum=0.01, maximum=1.0)
    remesh_voxel_size = _bounded_float(args.get("remesh_voxel_size"), 0.0, minimum=0.0, maximum=10.0)
    preserve_materials = bool(args.get("preserve_materials", True))
    label = str(args.get("label") or "Clean up generated asset")

    transaction = live_preview.begin(label, context)
    changed = []
    for obj in meshes:
        entry = {
            "object": obj.name,
            "materials_before": [
                slot.material.name if slot.material else "" for slot in getattr(obj, "material_slots", [])
            ],
            "shade_smooth": False,
            "modifiers": [],
        }
        if shade_smooth:
            live_preview._record_mesh_data_snapshot(obj)
            for polygon in obj.data.polygons:
                polygon.use_smooth = True
            entry["shade_smooth"] = True

        if add_weighted_normals:
            modifier = obj.modifiers.new("Agent Bridge Generated Weighted Normals", "WEIGHTED_NORMAL")
            live_preview._record_created_modifier(obj, modifier)
            if hasattr(modifier, "keep_sharp"):
                modifier.keep_sharp = True
            entry["modifiers"].append({"name": modifier.name, "type": modifier.type})

        if decimate_ratio < 0.999:
            modifier = obj.modifiers.new("Agent Bridge Generated Decimate", "DECIMATE")
            live_preview._record_created_modifier(obj, modifier)
            modifier.ratio = decimate_ratio
            entry["modifiers"].append({"name": modifier.name, "type": modifier.type, "ratio": decimate_ratio})

        if remesh_voxel_size > 0:
            modifier = obj.modifiers.new("Agent Bridge Generated Voxel Remesh", "REMESH")
            live_preview._record_created_modifier(obj, modifier)
            if hasattr(modifier, "mode"):
                modifier.mode = "VOXEL"
            if hasattr(modifier, "voxel_size"):
                modifier.voxel_size = remesh_voxel_size
            if hasattr(modifier, "use_remove_disconnected"):
                modifier.use_remove_disconnected = False
            entry["modifiers"].append(
                {"name": modifier.name, "type": modifier.type, "voxel_size": remesh_voxel_size}
            )

        if preserve_materials:
            after = [slot.material.name if slot.material else "" for slot in getattr(obj, "material_slots", [])]
            entry["materials_preserved"] = after == entry["materials_before"]
        changed.append(entry)

    transaction["applied_steps"].append(
        {
            "type": "cleanup_generated_asset",
            "label": label,
            "objects": [obj.name for obj in meshes],
            "shade_smooth": shade_smooth,
            "add_weighted_normals": add_weighted_normals,
            "decimate_ratio": decimate_ratio,
            "remesh_voxel_size": remesh_voxel_size,
            "expected_changes": "Cleaned generated mesh shading and added optional non-destructive cleanup modifiers.",
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": "Prepared generated asset cleanup for %d mesh object(s)" % len(meshes),
        "objects": [obj.name for obj in meshes],
        "changed": changed,
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }


def _mesh_component_stats(obj):
    mesh = getattr(obj, "data", None)
    if mesh is None:
        return {"component_count": 0, "largest_component_vertices": 0, "isolated_vertices": 0}
    vertex_count = len(mesh.vertices)
    adjacency = [[] for _ in range(vertex_count)]
    for edge in mesh.edges:
        a, b = int(edge.vertices[0]), int(edge.vertices[1])
        if 0 <= a < vertex_count and 0 <= b < vertex_count:
            adjacency[a].append(b)
            adjacency[b].append(a)
    seen = [False] * vertex_count
    component_sizes = []
    isolated = 0
    for index in range(vertex_count):
        if seen[index]:
            continue
        stack = [index]
        seen[index] = True
        size = 0
        has_edge = False
        while stack:
            current = stack.pop()
            size += 1
            if adjacency[current]:
                has_edge = True
            for nxt in adjacency[current]:
                if not seen[nxt]:
                    seen[nxt] = True
                    stack.append(nxt)
        if not has_edge:
            isolated += size
        component_sizes.append(size)
    component_sizes.sort(reverse=True)
    return {
        "component_count": len(component_sizes),
        "largest_component_vertices": component_sizes[0] if component_sizes else 0,
        "isolated_vertices": isolated,
        "component_sizes": component_sizes[:12],
    }


def _material_profile(obj):
    mesh = getattr(obj, "data", None)
    materials = [slot.material for slot in getattr(obj, "material_slots", []) if slot.material]
    node_types = []
    image_texture_count = 0
    vertex_color_node_count = 0
    for material in materials:
        if not getattr(material, "use_nodes", False) or not getattr(material, "node_tree", None):
            continue
        for node in material.node_tree.nodes:
            node_types.append(getattr(node, "bl_idname", ""))
            if getattr(node, "bl_idname", "") == "ShaderNodeTexImage":
                image_texture_count += 1
            if getattr(node, "bl_idname", "") in {"ShaderNodeVertexColor", "ShaderNodeAttribute"}:
                vertex_color_node_count += 1
    color_attributes = []
    if mesh is not None and hasattr(mesh, "color_attributes"):
        color_attributes = [
            {"name": attr.name, "domain": attr.domain, "data_type": attr.data_type}
            for attr in mesh.color_attributes
        ]
    uv_layers = [layer.name for layer in getattr(mesh, "uv_layers", [])] if mesh is not None else []
    return {
        "material_count": len(materials),
        "materials": [material.name for material in materials],
        "uv_layer_count": len(uv_layers),
        "uv_layers": uv_layers,
        "color_attributes": color_attributes,
        "image_texture_count": image_texture_count,
        "vertex_color_node_count": vertex_color_node_count,
        "node_types": sorted(set(item for item in node_types if item)),
        "material_type": (
            "texture_atlas"
            if image_texture_count
            else ("vertex_color" if color_attributes or vertex_color_node_count else "plain_material")
        ),
    }


def _manifest_for_evaluation(args):
    manifest_path = str(args.get("manifest_path") or "").strip()
    if not manifest_path:
        return {}, ""
    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        if not isinstance(manifest, dict):
            return {"ok": False, "message": "Manifest root must be a JSON object"}, manifest_path
        return manifest, manifest_path
    except Exception as error:  # noqa: BLE001 - reported in evaluation output
        return {"ok": False, "message": "Could not read manifest: %s" % error}, manifest_path


def _manifest_orientation_normalization(manifest):
    if not isinstance(manifest, dict):
        return {}
    normalization = manifest.get("import_orientation_normalization")
    return normalization if isinstance(normalization, dict) else {}


def _orientation_profile(obj, manifest=None):
    dims = tuple(float(component) for component in getattr(obj, "dimensions", (0.0, 0.0, 0.0)))
    axes = {"x": dims[0], "y": dims[1], "z": dims[2]}
    dominant = max(axes, key=lambda key: axes[key]) if axes else "z"
    normalization = _manifest_orientation_normalization(manifest)
    object_orientation = ""
    try:
        object_orientation = str(obj.get("blender_agent_bridge_import_orientation", "") or "")
    except AttributeError:
        object_orientation = ""
    provider_normalized = bool(normalization.get("applied") or object_orientation)
    provider = str((manifest or {}).get("provider") or "").strip().lower()
    axis_dominance_warning = dominant != "z"
    missing_required_normalization = provider == "triposr" and not provider_normalized
    upright_likely = not missing_required_normalization
    return {
        "dimensions": [round(value, 6) for value in dims],
        "dominant_axis": dominant,
        "upright_likely": upright_likely,
        "provider_normalized": provider_normalized,
        "provider_requires_normalization": provider == "triposr",
        "object_orientation": object_orientation,
        "import_orientation_normalization": normalization,
        "axis_dominance_warning": axis_dominance_warning,
        "warning": (
            "TripoSR orientation normalization is not recorded; raw output is expected to require Y-up to Z-up conversion."
            if missing_required_normalization
            else ""
        ),
        "note": (
            "Bounding-box dominance cannot determine orientation for wide or elongated subjects; inspect the rendered views."
            if axis_dominance_warning and not missing_required_normalization
            else ""
        ),
    }


def _generation_source(obj, manifest):
    manifest = manifest if isinstance(manifest, dict) else {}
    provider = str((manifest or {}).get("provider") or "").strip().lower()
    if not provider:
        provider = str(obj.get("blender_agent_bridge_asset_provider", "") or "").strip().lower()
    generation = manifest.get("generation") if isinstance(manifest.get("generation"), dict) else {}
    return provider, generation


VERY_DENSE_FACE_THRESHOLD = 500_000
FRAGMENTED_COMPONENT_THRESHOLD = 32


def _topology_findings(face_count, components):
    component_count = int((components or {}).get("component_count") or 0)
    findings = []
    if face_count > VERY_DENSE_FACE_THRESHOLD:
        findings.append(
            {
                "code": "very_dense_mesh",
                "severity": "warning",
                "message": "Mesh has %d faces, which is heavy for routine viewport editing." % face_count,
                "recommendation": "Preserve the source asset, then create a decimated or remeshed working copy.",
            }
        )
    elif component_count <= 1 and face_count > 20000:
        findings.append(
            {
                "code": "dense_single_component",
                "severity": "info",
                "message": "Mesh is a dense single component; it may be hard to edit as separate parts.",
                "recommendation": "Use cleanup/decimation for blockout review, or part-aware reconstruction for editable assets.",
            }
        )
    if component_count > FRAGMENTED_COMPONENT_THRESHOLD:
        findings.append(
            {
                "code": "fragmented_mesh_components",
                "severity": "warning",
                "message": "Mesh contains %d disconnected components, which can complicate cleanup and editing."
                % component_count,
                "recommendation": "Inspect for floating fragments, then join or remove components on a working copy.",
            }
        )
    return findings


def _quality_findings(obj, manifest):
    provider, generation = _generation_source(obj, manifest)
    material = _material_profile(obj)
    components = _mesh_component_stats(obj)
    orientation = _orientation_profile(obj, manifest)
    mesh = getattr(obj, "data", None)
    face_count = len(mesh.polygons) if mesh is not None else 0
    vertex_count = len(mesh.vertices) if mesh is not None else 0
    try:
        view_count = int(generation.get("view_count") or 0)
    except (TypeError, ValueError):
        view_count = 0
    findings = []
    if not orientation["upright_likely"]:
        findings.append(
            {
                "code": "orientation_not_z_up",
                "severity": "warning",
                "message": orientation["warning"],
                "recommendation": "Use provider import normalization or rotate Y-up output to Blender Z-up.",
            }
        )
    elif orientation["axis_dominance_warning"]:
        findings.append(
            {
                "code": "orientation_axis_dominance_ambiguous",
                "severity": "info",
                "message": orientation["note"],
                "recommendation": "Inspect the front/side/top renders before treating bounding-box dominance as orientation failure.",
            }
        )
    if provider == "triposr" and view_count <= 1:
        findings.append(
            {
                "code": "single_view_relief_shell_risk",
                "severity": "warning",
                "message": "Single-view TripoSR cannot observe side/back structure and often produces a relief-shell blockout.",
                "recommendation": "Use hosted Tripo multi-view or a studio endpoint for final-quality side/back structure.",
            }
        )
    if material["material_type"] == "vertex_color":
        findings.append(
            {
                "code": "vertex_color_only_material",
                "severity": "info",
                "message": "Imported material uses vertex colors and has no texture atlas.",
                "recommendation": "Use bake_texture/texture_resolution when supported, or keep materials during cleanup.",
            }
        )
    findings.extend(_topology_findings(face_count, components))
    return {
        "provider": provider,
        "generation": generation,
        "orientation": orientation,
        "material": material,
        "components": components,
        "topology": {"vertices": vertex_count, "faces": face_count},
        "findings": findings,
        "relief_shell_risk": any(item["code"] == "single_view_relief_shell_risk" for item in findings),
    }


def evaluate_generated_asset(context, args):
    from .. import advanced_modeling, inspection_render

    objects, missing = _resolve_scene_objects(context, args)
    meshes = _mesh_objects(objects)
    if not meshes:
        return {
            "ok": False,
            "message": "A generated mesh object is required for evaluation",
            "missing_object_names": missing,
        }
    manifest, manifest_path = _manifest_for_evaluation(args)
    include_renders = bool(args.get("include_renders", True))
    views = args.get("views") if isinstance(args.get("views"), list) else ["front", "side", "top"]
    views = [str(view) for view in views if str(view) in {"front_below", "underside", "side", "front", "rear", "top"}]
    if not views:
        views = ["front", "side", "top"]

    evaluations = []
    for obj in meshes:
        quality = advanced_modeling.inspect_modeling_quality(
            context,
            object_names=[obj.name],
            selected_only=False,
            include_children=False,
            max_objects=1,
            require_materials=True,
        )
        profile = _quality_findings(obj, manifest if len(meshes) == 1 else {})
        evaluations.append(
            {
                "object": obj.name,
                "quality": quality,
                **profile,
            }
        )

    render_result = {}
    if include_renders:
        render_result = inspection_render.capture_object_inspection_renders(
            context,
            object_names=[obj.name for obj in meshes],
            views=views,
            resolution_x=_bounded_int(args.get("resolution_x"), 800, minimum=128, maximum=2048),
            resolution_y=_bounded_int(args.get("resolution_y"), 600, minimum=128, maximum=2048),
            note=str(args.get("note") or "Generated asset evaluation"),
            isolate_targets=True,
            create_contact_sheet=True,
        )

    inspection_renders = render_result.get("inspection_render") if render_result else {}
    render_findings = []
    if include_renders and inspection_renders:
        failed_images = [
            image
            for image in inspection_renders.get("images", [])
            if image.get("view") != "contact_sheet" and not image.get("available")
        ]
        if failed_images:
            render_findings.append(
                {
                    "code": "inspection_render_incomplete",
                    "severity": "warning",
                    "message": "%d requested inspection view(s) did not render." % len(failed_images),
                    "views": [image.get("view", "") for image in failed_images],
                    "recommendation": "Retry the failed views or capture viewport evidence before judging orientation and shape.",
                }
            )
    finding_count = sum(len(item.get("findings") or []) for item in evaluations) + len(render_findings)
    return {
        "ok": True,
        "message": "Generated asset evaluation completed",
        "objects": [obj.name for obj in meshes],
        "missing_object_names": missing,
        "manifest_path": manifest_path,
        "manifest": manifest if manifest_path else {},
        "evaluations": evaluations,
        "finding_count": finding_count,
        "render_findings": render_findings,
        "render_complete": bool(not include_renders or inspection_renders.get("render_complete", False)),
        "inspection_renders": inspection_renders,
        "contact_sheet": (
            (render_result.get("inspection_render") or {}).get("contact_sheet", {})
            if render_result
            else {}
        ),
        "render_result": render_result,
    }


def register(handler_registry, specs):
    for spec in specs:
        try:
            handler = globals()[spec.handler_key]
        except KeyError as exc:
            raise KeyError(f"Missing handler {spec.handler_key} for {spec.name}") from exc
        handler_registry.register(spec.name, handler)
