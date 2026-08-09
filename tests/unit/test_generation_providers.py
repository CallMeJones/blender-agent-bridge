from __future__ import annotations

import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import generation_providers as gp  # noqa: E402


# A studio-class GPU: plenty of VRAM, Ampere or newer, bfloat16 available.
STUDIO_GPU = {
    "probed": True,
    "cuda_available": True,
    "device_name": "NVIDIA A100-SXM4-40GB",
    "vram_gb": 40.0,
    "compute_capability": 8.0,
    "supports_bfloat16": True,
}

# The machine this was developed against: Turing, 8 GB, no native bfloat16.
LAPTOP_GPU = {
    "probed": True,
    "cuda_available": True,
    "device_name": "NVIDIA GeForce RTX 2060 SUPER",
    "vram_gb": 8.0,
    "compute_capability": 7.5,
    "supports_bfloat16": False,
}


def _env(**overrides):
    env = {}
    env.update(overrides)
    return env


class EgressPolicyTests(unittest.TestCase):
    def test_egress_denied_by_default(self):
        self.assertEqual(gp.EGRESS_DENY, gp.egress_mode(_env()))

    def test_unrecognised_egress_value_denies(self):
        for value in ("", "yes", "true", "1", "ALLOWED", "maybe"):
            self.assertEqual(gp.EGRESS_DENY, gp.egress_mode(_env(**{gp.EGRESS_ENV_VAR: value})))

    def test_explicit_allow_permits_egress(self):
        self.assertEqual(gp.EGRESS_ALLOW, gp.egress_mode(_env(**{gp.EGRESS_ENV_VAR: "allow"})))

    def test_hosted_provider_blocked_by_egress_even_with_credential(self):
        report = gp.provider_availability(
            gp.PROVIDERS_BY_NAME["meshy"],
            hardware=STUDIO_GPU,
            environ=_env(MESHY_API_KEY="secret-value"),
        )
        self.assertFalse(report["available"])
        self.assertIn("egress_denied", report["blockers"])

    def test_hosted_provider_available_when_egress_allowed_and_credentialed(self):
        report = gp.provider_availability(
            gp.PROVIDERS_BY_NAME["meshy"],
            hardware=STUDIO_GPU,
            environ=_env(MESHY_API_KEY="secret-value", **{gp.EGRESS_ENV_VAR: "allow"}),
        )
        self.assertTrue(report["available"], report["remedies"])


class CredentialHandlingTests(unittest.TestCase):
    def test_credential_values_are_never_reported(self):
        secret = "sk-do-not-leak-this"
        diagnostics = gp.generation_provider_diagnostics(
            environ=_env(TRIPO_API_KEY=secret, **{gp.EGRESS_ENV_VAR: "allow"}),
            hardware=LAPTOP_GPU,
        )
        self.assertNotIn(secret, repr(diagnostics))

    def test_configured_env_var_names_are_reported(self):
        report = gp.provider_availability(
            gp.PROVIDERS_BY_NAME["tripo"],
            hardware=LAPTOP_GPU,
            environ=_env(TRIPO_API_KEY="x", **{gp.EGRESS_ENV_VAR: "allow"}),
        )
        self.assertIn("TRIPO_API_KEY", report["configured_env_vars"])
        self.assertTrue(report["credential_configured"])

    def test_missing_credential_is_reported_as_blocker(self):
        report = gp.provider_availability(
            gp.PROVIDERS_BY_NAME["tripo"],
            hardware=LAPTOP_GPU,
            environ=_env(**{gp.EGRESS_ENV_VAR: "allow"}),
        )
        self.assertIn("missing_credential", report["blockers"])


class HardwareRoutingTests(unittest.TestCase):
    def test_laptop_gpu_cannot_run_trellis(self):
        report = gp.provider_availability(
            gp.PROVIDERS_BY_NAME["trellis"],
            hardware=LAPTOP_GPU,
            environ=_env(BLENDER_AGENT_BRIDGE_TRELLIS_ROOT="/opt/trellis"),
        )
        self.assertFalse(report["available"])
        self.assertIn("insufficient_vram", report["blockers"])

    def test_turing_blocked_from_bfloat16_model(self):
        report = gp.provider_availability(
            gp.PROVIDERS_BY_NAME["hunyuan3d"],
            hardware=LAPTOP_GPU,
            environ=_env(BLENDER_AGENT_BRIDGE_HUNYUAN3D_ROOT="/opt/hunyuan"),
        )
        self.assertIn("no_bfloat16", report["blockers"])
        self.assertIn("compute_capability_too_low", report["blockers"])

    def test_laptop_gpu_can_run_triposr(self):
        report = gp.provider_availability(
            gp.PROVIDERS_BY_NAME["triposr"],
            hardware=LAPTOP_GPU,
            environ=_env(
                BLENDER_AGENT_BRIDGE_TRIPOSR_PYTHON="/opt/python",
                BLENDER_AGENT_BRIDGE_TRIPOSR_ROOT="/opt/triposr",
            ),
        )
        self.assertTrue(report["available"], report["remedies"])
        self.assertTrue(report["runnable"], report["run_blocker"])

    def test_studio_gpu_can_run_every_local_model(self):
        env = _env(
            BLENDER_AGENT_BRIDGE_GENERATION_PROBE_PYTHON="/opt/python",
            BLENDER_AGENT_BRIDGE_TRELLIS_ROOT="/opt/trellis",
            BLENDER_AGENT_BRIDGE_HUNYUAN3D_ROOT="/opt/hunyuan",
            BLENDER_AGENT_BRIDGE_TRIPOSR_ROOT="/opt/triposr",
        )
        for name in ("trellis", "hunyuan3d", "triposr"):
            report = gp.provider_availability(
                gp.PROVIDERS_BY_NAME[name], hardware=STUDIO_GPU, environ=env
            )
            self.assertTrue(report["available"], "%s: %s" % (name, report["remedies"]))

    def test_local_model_without_runtime_is_unavailable(self):
        report = gp.provider_availability(
            gp.PROVIDERS_BY_NAME["triposr"], hardware=STUDIO_GPU, environ=_env()
        )
        self.assertIn("missing_runtime", report["blockers"])

    def test_unknown_hardware_blocks_local_models(self):
        report = gp.provider_availability(
            gp.PROVIDERS_BY_NAME["triposr"],
            hardware=None,
            environ=_env(
                BLENDER_AGENT_BRIDGE_TRIPOSR_PYTHON="/opt/python",
                BLENDER_AGENT_BRIDGE_TRIPOSR_ROOT="/opt/triposr",
            ),
        )
        self.assertIn("hardware_unknown", report["blockers"])

    def test_every_blocker_is_reported_not_just_the_first(self):
        report = gp.provider_availability(
            gp.PROVIDERS_BY_NAME["hunyuan3d"], hardware=LAPTOP_GPU, environ=_env()
        )
        self.assertIn("missing_runtime", report["blockers"])
        self.assertIn("no_bfloat16", report["blockers"])
        self.assertEqual(len(report["blockers"]), len(report["remedies"]))


class SelectionTests(unittest.TestCase):
    def test_self_hosted_endpoint_counts_as_local_and_needs_no_egress(self):
        report = gp.provider_availability(
            gp.PROVIDERS_BY_NAME["studio_endpoint"],
            hardware=LAPTOP_GPU,
            environ=_env(BLENDER_AGENT_BRIDGE_GENERATION_ENDPOINT="http://gpu-box.studio.local:8080"),
        )
        self.assertTrue(report["available"], report["remedies"])

    def test_hosted_provider_is_never_auto_selected(self):
        # Hosted providers spend the user's credits and upload their reference
        # art. Auto-selection must not reach for one, even when it is ready.
        env = _env(TRIPO_API_KEY="k", MESHY_API_KEY="k", **{gp.EGRESS_ENV_VAR: "allow"})
        result = gp.select_provider(environ=env, hardware=LAPTOP_GPU)
        self.assertFalse(result["ok"])
        self.assertIsNone(result["selected"])

    def test_available_hosted_providers_are_offered_as_suggestions(self):
        env = _env(TRIPO_API_KEY="k", **{gp.EGRESS_ENV_VAR: "allow"})
        result = gp.select_provider(environ=env, hardware=LAPTOP_GPU)
        self.assertIn("tripo", result["suggested_providers"])
        self.assertTrue(result["requires_explicit_choice"])
        self.assertIn("name it explicitly", result["message"])

    def test_naming_a_hosted_provider_explicitly_is_honoured(self):
        env = _env(TRIPO_API_KEY="k", **{gp.EGRESS_ENV_VAR: "allow"})
        result = gp.select_provider(preferred="tripo", environ=env, hardware=LAPTOP_GPU)
        self.assertTrue(result["ok"], result.get("message"))
        self.assertEqual("tripo", result["selected"])

    def test_unavailable_hosted_provider_is_not_suggested(self):
        # Egress denied: offering it would suggest something that cannot run.
        env = _env(TRIPO_API_KEY="k")
        result = gp.select_provider(environ=env, hardware=LAPTOP_GPU)
        self.assertEqual([], result.get("suggested_providers", []))

    def test_unimplemented_local_provider_is_never_auto_selected(self):
        # Hunyuan3D is available on this hardware but has no job backend, so it
        # must not be selected. With no usable local provider, the hosted one is
        # suggested rather than silently used.
        env = _env(
            BLENDER_AGENT_BRIDGE_HUNYUAN3D_PYTHON="/opt/python",
            BLENDER_AGENT_BRIDGE_HUNYUAN3D_ROOT="/opt/hunyuan",
            TRIPO_API_KEY="k",
            **{gp.EGRESS_ENV_VAR: "allow"},
        )
        result = gp.select_provider(environ=env, hardware=STUDIO_GPU)
        self.assertFalse(result["ok"])
        self.assertIn("hunyuan3d", result["unimplemented_providers"])
        self.assertIn("tripo", result["suggested_providers"])

    def test_only_unimplemented_providers_refuses_and_names_them(self):
        env = _env(
            BLENDER_AGENT_BRIDGE_HUNYUAN3D_PYTHON="/opt/python",
            BLENDER_AGENT_BRIDGE_HUNYUAN3D_ROOT="/opt/hunyuan",
        )
        result = gp.select_provider(environ=env, hardware=STUDIO_GPU)
        self.assertFalse(result["ok"])
        self.assertIn("hunyuan3d", result["unimplemented_providers"])
        self.assertIn("not yet implemented", result["message"])

    def test_explicit_choice_of_an_unimplemented_provider_still_reports_availability(self):
        # Asking for it by name is a planning question, not a routing one.
        env = _env(
            BLENDER_AGENT_BRIDGE_HUNYUAN3D_PYTHON="/opt/python",
            BLENDER_AGENT_BRIDGE_HUNYUAN3D_ROOT="/opt/hunyuan",
        )
        report = gp.provider_availability(
            gp.PROVIDERS_BY_NAME["hunyuan3d"], hardware=STUDIO_GPU, environ=env
        )
        self.assertTrue(report["available"])
        self.assertFalse(report["job_implemented"])

    def test_implemented_providers_are_declared_explicitly(self):
        implemented = [s.name for s in gp.PROVIDER_SPECS if s.job_implemented]
        self.assertEqual(["triposr", "studio_endpoint", "tripo", "meshy"], implemented)

    def test_local_and_hosted_routes_require_an_explicit_choice(self):
        env = _env(
            BLENDER_AGENT_BRIDGE_TRIPOSR_PYTHON="/opt/python",
            BLENDER_AGENT_BRIDGE_TRIPOSR_ROOT="/opt/triposr",
            MESHY_API_KEY="x",
            **{gp.EGRESS_ENV_VAR: "allow"},
        )
        result = gp.select_provider(environ=env, hardware=LAPTOP_GPU)
        self.assertFalse(result["ok"])
        self.assertTrue(result["provider_selection_required"])
        self.assertEqual(["triposr", "meshy"], result["suggested_providers"])

    def test_a_sole_local_route_is_still_selected_without_a_prompt(self):
        env = _env(
            BLENDER_AGENT_BRIDGE_TRIPOSR_PYTHON="/opt/python",
            BLENDER_AGENT_BRIDGE_TRIPOSR_ROOT="/opt/triposr",
        )
        result = gp.select_provider(environ=env, hardware=LAPTOP_GPU)
        self.assertTrue(result["ok"], result.get("message"))
        self.assertEqual("triposr", result["selected"])

    def test_local_only_policy_removes_hosted_routes_before_selection(self):
        gp.set_session_generation_policy(gp.POLICY_LOCAL_ONLY)
        self.addCleanup(gp.clear_session_generation_policy)
        env = _env(
            BLENDER_AGENT_BRIDGE_TRIPOSR_PYTHON="/opt/python",
            BLENDER_AGENT_BRIDGE_TRIPOSR_ROOT="/opt/triposr",
            MESHY_API_KEY="x",
            **{gp.EGRESS_ENV_VAR: "allow"},
        )
        result = gp.select_provider(environ=env, hardware=LAPTOP_GPU)
        self.assertTrue(result["ok"], result.get("message"))
        self.assertEqual("triposr", result["selected"])

    def test_multiview_requirement_skips_single_image_provider(self):
        env = _env(
            BLENDER_AGENT_BRIDGE_TRIPOSR_PYTHON="/opt/python",
            BLENDER_AGENT_BRIDGE_TRIPOSR_ROOT="/opt/triposr",
            BLENDER_AGENT_BRIDGE_GENERATION_ENDPOINT="http://gpu-box.studio.local:8080",
        )
        result = gp.select_provider(environ=env, hardware=LAPTOP_GPU, require_multiview=True)
        self.assertTrue(result["ok"], result.get("message"))
        self.assertEqual("studio_endpoint", result["selected"])

    def test_no_provider_available_explains_itself(self):
        result = gp.select_provider(environ=_env(), hardware=LAPTOP_GPU)
        self.assertFalse(result["ok"])
        self.assertIsNone(result["selected"])
        self.assertIn("diagnostics", result)

    def test_unknown_provider_name_is_rejected(self):
        result = gp.select_provider(preferred="stable-fast-3d", environ=_env(), hardware=STUDIO_GPU)
        self.assertFalse(result["ok"])
        self.assertIn("known_providers", result)

    def test_explicit_unavailable_provider_reports_remedy(self):
        result = gp.select_provider(preferred="tripo", environ=_env(), hardware=LAPTOP_GPU)
        self.assertFalse(result["ok"])
        self.assertTrue(result["report"]["remedies"])


class HardwareProbeTests(unittest.TestCase):
    def setUp(self):
        # The probe cache is process-global by design; isolate each test.
        gp.clear_hardware_probe_cache()

    tearDown = setUp

    def test_probe_without_configured_interpreter_reports_reason(self):
        probe = gp.probe_hardware(environ=_env())
        self.assertFalse(probe["probed"])
        self.assertIn(gp.PROBE_PYTHON_ENV_VAR, probe["message"])

    def test_probe_parses_reported_payload(self):
        payload = {
            "probed": True,
            "cuda_available": True,
            "device_name": "NVIDIA A100",
            "vram_gb": 40.0,
            "compute_capability": 8.0,
            "supports_bfloat16": True,
        }

        def runner(argv):
            self.assertEqual("/opt/py", argv[0])
            return 0, "noise\nGENERATION_PROBE %s\n" % __import__("json").dumps(payload), ""

        probe = gp.probe_hardware(python_executable="/opt/py", runner=runner)
        self.assertTrue(probe["probed"])
        self.assertEqual(40.0, probe["vram_gb"])
        self.assertTrue(probe["supports_bfloat16"])

    def test_probe_failure_is_reported_not_raised(self):
        def runner(argv):
            raise OSError("interpreter missing")

        probe = gp.probe_hardware(python_executable="/opt/py", runner=runner)
        self.assertFalse(probe["probed"])
        self.assertIn("interpreter missing", probe["message"])

    def test_probe_without_marker_line_degrades_gracefully(self):
        def runner(argv):
            return 1, "", "ModuleNotFoundError: No module named 'torch'"

        probe = gp.probe_hardware(python_executable="/opt/py", runner=runner)
        self.assertFalse(probe["probed"])
        self.assertIn("torch", probe["message"])

    def test_failed_probe_blocks_local_providers_rather_than_allowing_them(self):
        def runner(argv):
            return 1, "", "boom"

        probe = gp.probe_hardware(python_executable="/opt/py", runner=runner)
        report = gp.provider_availability(
            gp.PROVIDERS_BY_NAME["triposr"],
            hardware=probe,
            environ=_env(
                BLENDER_AGENT_BRIDGE_TRIPOSR_PYTHON="/opt/python",
                BLENDER_AGENT_BRIDGE_TRIPOSR_ROOT="/opt/triposr",
            ),
        )
        self.assertFalse(report["available"])
        self.assertIn("hardware_unknown", report["blockers"])

    def test_successful_probe_is_cached_per_interpreter(self):
        payload = {"probed": True, "cuda_available": True, "vram_gb": 24.0, "compute_capability": 8.6}
        calls = []

        def runner(argv):
            calls.append(argv[0])
            return 0, "GENERATION_PROBE %s\n" % __import__("json").dumps(payload), ""

        first = gp.probe_hardware(python_executable="/opt/py", runner=runner)
        second = gp.probe_hardware(python_executable="/opt/py", runner=runner)
        self.assertEqual(first, second)
        self.assertEqual(1, len(calls), "second call should be served from cache")

        gp.probe_hardware(python_executable="/other/py", runner=runner)
        self.assertEqual(2, len(calls), "a different interpreter is probed separately")

    def test_failed_probe_is_not_cached(self):
        calls = []

        def runner(argv):
            calls.append(argv[0])
            return 1, "", "no torch"

        gp.probe_hardware(python_executable="/opt/py", runner=runner)
        gp.probe_hardware(python_executable="/opt/py", runner=runner)
        self.assertEqual(2, len(calls), "a failed probe must be retried, not cached")

    def test_cache_can_be_bypassed(self):
        payload = {"probed": True, "cuda_available": True, "vram_gb": 8.0, "compute_capability": 7.5}
        calls = []

        def runner(argv):
            calls.append(argv[0])
            return 0, "GENERATION_PROBE %s\n" % __import__("json").dumps(payload), ""

        gp.probe_hardware(python_executable="/opt/py", runner=runner)
        gp.probe_hardware(python_executable="/opt/py", runner=runner, use_cache=False)
        self.assertEqual(2, len(calls))


class RegistryIntegrityTests(unittest.TestCase):
    def test_provider_names_are_unique(self):
        names = [spec.name for spec in gp.PROVIDER_SPECS]
        self.assertEqual(len(names), len(set(names)))

    def test_every_hosted_provider_requires_egress(self):
        for spec in gp.PROVIDER_SPECS:
            if spec.kind == gp.KIND_HOSTED_API:
                self.assertTrue(spec.requires_egress, spec.name)

    def test_no_local_provider_requires_egress(self):
        for spec in gp.PROVIDER_SPECS:
            if spec.kind in (gp.KIND_LOCAL_PROCESS, gp.KIND_LOCAL_HTTP):
                self.assertFalse(spec.requires_egress, spec.name)

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            gp.ProviderSpec("bogus", "Bogus", "carrier_pigeon")

    def test_spec_round_trips_to_dict(self):
        for spec in gp.PROVIDER_SPECS:
            payload = spec.as_dict()
            self.assertEqual(spec.name, payload["name"])
            self.assertIn(payload["kind"], gp.PROVIDER_KINDS)

    def test_module_imports_without_bpy(self):
        self.assertNotIn("bpy", sys.modules)


if __name__ == "__main__":
    unittest.main()
