"""User-point-of-view functionality smoke for common client routes.

This deliberately mixes routing checks and actual scene execution:

- helper-only scene inspection;
- script-only authoring with trust off and on;
- mixed helper plus script workflow;
- paid generation provider-choice/approval behavior;
- no-third-party fallback still allowing ordinary bridge work.
"""

from __future__ import annotations

import json
import os
import random
import sys
import tempfile

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import (  # noqa: E402
    agent_tools,
    context_bundle,
    generation_providers,
    generation_spend,
    preferences,
    script_runner,
    tool_dispatcher,
)
from claude_blender.tool_handlers import generation as generation_handler  # noqa: E402


PREFIX = "User POV Smoke"


def _execute(context, name, args=None):
    return json.loads(tool_dispatcher.execute_tool(context, name, args or {}))


def _require_ok(label, result):
    assert result.get("ok"), "%s failed: %s" % (label, result)
    return result


def _tool_names(tools):
    return {tool["name"] for tool in tools}


def _cleanup():
    for obj in list(bpy.data.objects):
        if obj.name.startswith(PREFIX):
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh is not None and getattr(mesh, "users", 0) == 0:
                try:
                    bpy.data.meshes.remove(mesh)
                except Exception:
                    pass
    for material in list(bpy.data.materials):
        if material.name.startswith(PREFIX):
            bpy.data.materials.remove(material)


def _write_tiny_png(path):
    # 1x1 transparent PNG.
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    with open(path, "wb") as handle:
        handle.write(png)


def _check_prompt_routing(context):
    bundle = context_bundle.build_context_bundle(context)
    cases = [
        (
            "helper_only",
            "What objects are in my current scene?",
            {"list_scene_objects"},
            {"draft_script"},
        ),
        (
            "script_only",
            "Draft a Blender Python script to build a custom procedural signal tower.",
            {"draft_script"},
            set(),
        ),
        (
            "mixed_helper_script",
            "Write a Python script to move the selected cube up and make it red.",
            {"draft_script", "set_selected_location_delta", "assign_material_to_selected"},
            set(),
        ),
        (
            "asset_safety_route",
            "Write a Python script to download and import a Poly Haven sunset HDRI.",
            {"plan_asset_import_workflow", "start_external_asset_download"},
            {"draft_script", "draft_privileged_script"},
        ),
        (
            "file_safety_route",
            "Write a custom Python script to save this project as a new .blend file.",
            {"save_blend_file"},
            {"draft_script", "draft_privileged_script"},
        ),
    ]
    rng = random.Random(5606)
    rng.shuffle(cases)
    observed = {}
    for label, prompt, must_include, must_exclude in cases:
        tools, meta = agent_tools.select_blender_tool_definitions(prompt, bundle)
        names = _tool_names(tools)
        assert must_include.issubset(names), (label, must_include, names, meta)
        assert not (must_exclude & names), (label, must_exclude & names, meta)
        observed[label] = sorted(names & (must_include | must_exclude | {"draft_script"}))
    return observed


def _check_script_only(context):
    trust_off = _execute(
        context,
        "draft_script",
        {
            "intent": "User POV script-only trust-off refusal",
            "expected_changes": "No object is created",
            "risk_level": "low",
            "code": (
                "import bpy\n"
                "bpy.ops.mesh.primitive_cube_add(size=1.0)\n"
                "bpy.context.object.name = 'User POV Smoke Trust Leak'\n"
            ),
        },
    )
    assert not trust_off.get("ok"), trust_off
    assert trust_off.get("code") == "script_trust_required", trust_off
    assert "User POV Smoke Trust Leak" not in bpy.data.objects

    trusted = script_runner.approve_external_script_trust_window(context, session=True)
    assert trusted.get("ok"), trusted
    authored = _require_ok(
        "trusted script-only run",
        _execute(
            context,
            "draft_script",
            {
                "intent": "User POV script-only creates one simple prop",
                "expected_changes": "Creates one torus prop and tags it",
                "risk_level": "low",
                "code": (
                    "import bpy\n"
                    "bpy.ops.mesh.primitive_torus_add(major_radius=0.8, minor_radius=0.18, location=(-2, 0, 1))\n"
                    "obj = bpy.context.object\n"
                    "obj.name = 'User POV Smoke Script Only Torus'\n"
                    "obj['user_pov_route'] = 'script_only'\n"
                    "scene['user_pov_script_only'] = obj.name\n"
                ),
            },
        ),
    )
    assert authored.get("auto_ran"), authored
    obj = bpy.data.objects.get("User POV Smoke Script Only Torus")
    assert obj is not None and obj.get("user_pov_route") == "script_only", authored


def _check_mixed_helper_script(context):
    created = _require_ok(
        "helper primitive",
        _execute(
            context,
            "create_primitive",
            {
                "primitive_type": "CUBE",
                "name": "User POV Smoke Mixed Cube",
                "location": [1.5, 0.0, 0.5],
                "rotation": [0.0, 0.0, 0.0],
                "scale": [1.0, 1.0, 1.0],
                "label": "User POV mixed helper/script cube",
            },
        ),
    )
    assert created.get("object") == "User POV Smoke Mixed Cube", created
    select = _require_ok(
        "select helper object",
        _execute(
            context,
            "select_objects",
            {"object_names": ["User POV Smoke Mixed Cube"], "active_object_name": "User POV Smoke Mixed Cube"},
        ),
    )
    assert select.get("active_object") == "User POV Smoke Mixed Cube", select
    material = _require_ok(
        "helper material",
        _execute(
            context,
            "create_shader_material",
            {"name": "User POV Smoke Material", "preset": "screen_glow", "assign_to_selected": True},
        ),
    )
    assert material.get("material"), material
    script = _require_ok(
        "mixed follow-up script",
        _execute(
            context,
            "draft_script",
            {
                "intent": "User POV mixed helper/script follow-up",
                "expected_changes": "Adds a bevel modifier to the helper-created cube",
                "risk_level": "low",
                "code": (
                    "import bpy\n"
                    "obj = bpy.data.objects['User POV Smoke Mixed Cube']\n"
                    "mod = obj.modifiers.new('User POV Smoke Bevel', 'BEVEL')\n"
                    "mod.width = 0.05\n"
                    "obj['user_pov_route'] = 'mixed_helper_script'\n"
                ),
            },
        ),
    )
    assert script.get("auto_ran"), script
    obj = bpy.data.objects["User POV Smoke Mixed Cube"]
    assert obj.get("user_pov_route") == "mixed_helper_script"
    assert "User POV Smoke Bevel" in obj.modifiers
    listed = _require_ok("post-mixed scene listing", _execute(context, "list_scene_objects", {"max_objects": 50}))
    names = {item["name"] for item in listed.get("objects", [])}
    assert {"User POV Smoke Mixed Cube", "User POV Smoke Script Only Torus"}.issubset(names), listed


def _check_generation_user_choices(context):
    old_env = {name: os.environ.get(name) for name in (
        "TRIPO_API_KEY",
        "MESHY_API_KEY",
        "BLENDER_AGENT_BRIDGE_GENERATION_EGRESS",
        "BLENDER_AGENT_BRIDGE_TRIPOSR_PYTHON",
        "BLENDER_AGENT_BRIDGE_TRIPOSR_ROOT",
    )}
    original_probe_hardware = generation_providers.probe_hardware
    original_redraw = generation_handler._redraw_sidebar
    redraws = []
    try:
        image = os.path.join(tempfile.mkdtemp(prefix="user-pov-generation-"), "front.png")
        _write_tiny_png(image)
        os.environ["TRIPO_API_KEY"] = "tsk_user_pov_fake"
        os.environ["MESHY_API_KEY"] = "msy_user_pov_fake"
        os.environ["BLENDER_AGENT_BRIDGE_GENERATION_EGRESS"] = "allow"
        os.environ["BLENDER_AGENT_BRIDGE_TRIPOSR_PYTHON"] = "C:/smoke/python.exe"
        os.environ["BLENDER_AGENT_BRIDGE_TRIPOSR_ROOT"] = "C:/smoke/TripoSR"
        generation_providers.probe_hardware = lambda **_kwargs: {
            "probed": True,
            "cuda_available": True,
            "device_name": "User POV Smoke GPU",
            "vram_gb": 8.0,
            "compute_capability": 7.5,
            "supports_bfloat16": False,
        }
        generation_handler._redraw_sidebar = lambda _context: redraws.append(True)
        generation_spend.clear_requests()

        ambiguous = _execute(context, "start_generation_job", {"views": {"front": image}})
        assert not ambiguous.get("ok"), ambiguous
        assert ambiguous.get("provider_selection_required") is True, ambiguous
        assert ambiguous.get("requires_explicit_choice") is True, ambiguous
        assert ambiguous.get("suggested_providers") == ["triposr", "tripo", "meshy"], ambiguous

        paid = _execute(
            context,
            "start_generation_job",
            {
                "provider": "meshy",
                "views": {"front": image},
                "meshy_options": {"should_texture": False},
            },
        )
        assert not paid.get("ok"), paid
        assert paid.get("awaiting_user_approval") is True, paid
        assert (paid.get("spend_approval") or {}).get("estimated_credits") == 20, paid
        assert redraws, paid
    finally:
        generation_handler._redraw_sidebar = original_redraw
        generation_providers.probe_hardware = original_probe_hardware
        generation_spend.clear_requests()
        generation_providers.set_session_generation_policy(generation_providers.POLICY_ANY)
        for name, value in old_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _check_no_third_party_fallback(context):
    generation_providers.set_session_generation_policy(
        generation_providers.POLICY_NO_GENERATION,
        reason="user POV smoke: disable all third-party generation",
    )
    plan = _require_ok("authored-only generation plan", _execute(context, "plan_image_to_3d_approach", {}))
    assert plan.get("ready_routes") == ["authored"], plan
    read = _require_ok("bridge still reads scene", _execute(context, "list_scene_objects", {"max_objects": 20}))
    assert read.get("objects"), read
    script = _require_ok(
        "script still runs with providers disabled",
        _execute(
            context,
            "draft_script",
            {
                "intent": "User POV no-provider script path still works",
                "expected_changes": "Sets one scene flag",
                "risk_level": "low",
                "code": "scene['user_pov_no_provider_script_ok'] = True",
            },
        ),
    )
    assert script.get("auto_ran") and context.scene.get("user_pov_no_provider_script_ok"), script
    generation_providers.set_session_generation_policy(generation_providers.POLICY_ANY)


def main():
    audit_dir = tempfile.mkdtemp(prefix="user-pov-audit-")
    previous_audit = os.environ.get("CLAUDE_BLENDER_AUDIT_LOG")
    os.environ["CLAUDE_BLENDER_AUDIT_LOG"] = os.path.join(audit_dir, "audit.jsonl")
    original_get_preferences = preferences.get_preferences
    prefs = type(
        "_UserPovPrefs",
        (),
        {
            "checkpoint_dir": tempfile.mkdtemp(prefix="user-pov-checkpoints-"),
            "checkpoints_enabled": True,
            "capture_cache_dir": "",
            "generation_egress_allowed": True,
            "generation_python": "C:/smoke/python.exe",
            "triposr_root": "C:/smoke/TripoSR",
            "tripo_api_key": "tsk_user_pov_fake",
            "meshy_api_key": "msy_user_pov_fake",
        },
    )()
    try:
        claude_blender.register()
        preferences.get_preferences = lambda _context: prefs
        context = bpy.context
        _cleanup()
        script_runner.revoke_external_script_trust_window(context)

        observed_routes = _check_prompt_routing(context)
        _require_ok("helper-only scene listing", _execute(context, "list_scene_objects", {"max_objects": 10}))
        _check_script_only(context)
        _check_mixed_helper_script(context)
        _check_generation_user_choices(context)
        _check_no_third_party_fallback(context)

        print("user POV route matrix:", json.dumps(observed_routes, sort_keys=True))
        print("smoke_user_functionality_pov: ok")
    finally:
        preferences.get_preferences = original_get_preferences
        generation_providers.set_session_generation_policy(generation_providers.POLICY_ANY)
        script_runner.revoke_external_script_trust_window(bpy.context)
        _cleanup()
        if "user_pov_script_only" in bpy.context.scene:
            del bpy.context.scene["user_pov_script_only"]
        if "user_pov_no_provider_script_ok" in bpy.context.scene:
            del bpy.context.scene["user_pov_no_provider_script_ok"]
        if previous_audit is None:
            os.environ.pop("CLAUDE_BLENDER_AUDIT_LOG", None)
        else:
            os.environ["CLAUDE_BLENDER_AUDIT_LOG"] = previous_audit
        claude_blender.unregister()


if __name__ == "__main__":
    main()
