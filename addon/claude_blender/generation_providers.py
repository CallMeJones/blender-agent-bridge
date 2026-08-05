"""Provider registry for image-to-3D generation backends.

Three provider kinds are supported so the same tool surface serves very
different deployments:

``hosted_api``
    A third-party service reached over the network (Tripo, Meshy). Needs a
    credential and, critically, needs egress to be permitted.
``local_http``
    An inference server the user or their studio already runs, reached at a
    configured base URL. One GPU box can serve a whole team.
``local_process``
    A model executed on this machine (TripoSR, Hunyuan3D). Needs a Python
    environment and enough VRAM.

Two rules drive the design.

First, **egress is denied by default**. A design studio frequently cannot
upload client reference art to a third-party service at all; that is a
contractual constraint rather than a preference. Providers that require
network egress stay unavailable until an operator opts in explicitly, and
the reason is always reported rather than the provider silently vanishing.

Second, **unavailability is always explained**. A provider that cannot run
reports why -- missing credential, insufficient VRAM, egress denied, no
endpoint configured -- so a planner can route rather than guess.

This module must remain importable without ``bpy`` and without torch. All
hardware facts arrive through an injected probe so the logic stays testable
headless.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess

EGRESS_ENV_VAR = "BLENDER_AGENT_BRIDGE_GENERATION_EGRESS"
PROBE_PYTHON_ENV_VAR = "BLENDER_AGENT_BRIDGE_GENERATION_PROBE_PYTHON"
PROBE_TIMEOUT_SECONDS = 60
EGRESS_DENY = "deny"
EGRESS_ALLOW = "allow"

KIND_HOSTED_API = "hosted_api"
KIND_LOCAL_HTTP = "local_http"
KIND_LOCAL_PROCESS = "local_process"
PROVIDER_KINDS = (KIND_HOSTED_API, KIND_LOCAL_HTTP, KIND_LOCAL_PROCESS)


@dataclasses.dataclass(frozen=True)
class ProviderSpec:
    """Static description of one generation backend.

    Deliberately inert: it holds requirements and never performs I/O, so the
    registry can be imported and reasoned about in any environment.
    """

    name: str
    title: str
    kind: str
    requires_egress: bool = False
    credential_env_vars: tuple = ()
    endpoint_env_vars: tuple = ()
    runtime_env_vars: tuple = ()
    min_vram_gb: float = 0.0
    min_compute_capability: float = 0.0
    requires_bfloat16: bool = False
    supports_multiview: bool = False
    max_input_images: int = 1
    license_note: str = ""
    notes: str = ""
    # False means the capability is described but no job backend exists yet.
    # Such a provider is reported for planning but never auto-selected, so a
    # caller cannot be routed to something that will refuse.
    job_implemented: bool = False

    def __post_init__(self):
        if self.kind not in PROVIDER_KINDS:
            raise ValueError("unknown provider kind: %s" % self.kind)

    def as_dict(self):
        return dataclasses.asdict(self)


# Requirements below are conservative floors used for routing, not benchmarks.
# Operators can always override with an explicit endpoint or runtime env var.
PROVIDER_SPECS = (
    ProviderSpec(
        "triposr",
        "TripoSR",
        KIND_LOCAL_PROCESS,
        runtime_env_vars=("BLENDER_AGENT_BRIDGE_TRIPOSR_PYTHON", "BLENDER_AGENT_BRIDGE_TRIPOSR_ROOT"),
        min_vram_gb=6.0,
        min_compute_capability=7.0,
        supports_multiview=False,
        max_input_images=1,
        license_note="MIT",
        notes="Fast single-image reconstruction. Lower fidelity than diffusion-based models; good for blockouts.",
    ),
    ProviderSpec(
        "hunyuan3d",
        "Hunyuan3D",
        KIND_LOCAL_PROCESS,
        runtime_env_vars=("BLENDER_AGENT_BRIDGE_HUNYUAN3D_PYTHON", "BLENDER_AGENT_BRIDGE_HUNYUAN3D_ROOT"),
        min_vram_gb=12.0,
        min_compute_capability=8.0,
        requires_bfloat16=True,
        supports_multiview=True,
        max_input_images=4,
        license_note="Tencent community licence; review territorial and scale restrictions before commercial use.",
        notes="Multi-view variants accept front/back/left/right conditioning, which suits calibrated reference sheets.",
    ),
    ProviderSpec(
        "trellis",
        "TRELLIS",
        KIND_LOCAL_PROCESS,
        runtime_env_vars=("BLENDER_AGENT_BRIDGE_TRELLIS_PYTHON", "BLENDER_AGENT_BRIDGE_TRELLIS_ROOT"),
        min_vram_gb=16.0,
        min_compute_capability=8.0,
        supports_multiview=True,
        max_input_images=4,
        license_note="MIT",
        notes="Structured-latent model; strong general quality at a high VRAM floor.",
    ),
    ProviderSpec(
        "studio_endpoint",
        "Studio inference endpoint",
        KIND_LOCAL_HTTP,
        endpoint_env_vars=("BLENDER_AGENT_BRIDGE_GENERATION_ENDPOINT",),
        credential_env_vars=("BLENDER_AGENT_BRIDGE_GENERATION_ENDPOINT_TOKEN",),
        supports_multiview=True,
        max_input_images=6,
        notes="Self-hosted server on the local network. Counts as local: no third-party egress.",
    ),
    ProviderSpec(
        "tripo",
        "Tripo AI",
        KIND_HOSTED_API,
        requires_egress=True,
        credential_env_vars=("TRIPO_API_KEY", "BLENDER_AGENT_BRIDGE_TRIPO_API_KEY"),
        supports_multiview=True,
        max_input_images=4,
        license_note="Commercial API; output rights governed by the vendor's terms.",
        job_implemented=True,
    ),
    ProviderSpec(
        "meshy",
        "Meshy AI",
        KIND_HOSTED_API,
        requires_egress=True,
        credential_env_vars=("MESHY_API_KEY", "BLENDER_AGENT_BRIDGE_MESHY_API_KEY"),
        supports_multiview=True,
        max_input_images=4,
        license_note="Commercial API; output rights governed by the vendor's terms.",
    ),
)

PROVIDERS_BY_NAME = {spec.name: spec for spec in PROVIDER_SPECS}


def egress_mode(environ=None):
    """Resolve the egress policy. Anything unrecognised denies."""

    source = environ if environ is not None else os.environ
    value = str(source.get(EGRESS_ENV_VAR, "") or "").strip().lower()
    return EGRESS_ALLOW if value == EGRESS_ALLOW else EGRESS_DENY


# Maps an add-on preference attribute to the environment name it supplies.
# Lives here rather than in preferences.py so it stays importable without bpy
# and can be tested directly instead of through a copy.
PREFERENCE_ENV_MAP = (
    ("triposr_root", "BLENDER_AGENT_BRIDGE_TRIPOSR_ROOT"),
    ("generation_endpoint", "BLENDER_AGENT_BRIDGE_GENERATION_ENDPOINT"),
    ("generation_endpoint_token", "BLENDER_AGENT_BRIDGE_GENERATION_ENDPOINT_TOKEN"),
    ("tripo_api_key", "TRIPO_API_KEY"),
    ("meshy_api_key", "MESHY_API_KEY"),
)

# One preference selects the interpreter for every local provider.
PREFERENCE_PYTHON_ATTRIBUTE = "generation_python"
PREFERENCE_PYTHON_ENV_VARS = (PROBE_PYTHON_ENV_VAR, "BLENDER_AGENT_BRIDGE_TRIPOSR_PYTHON")
PREFERENCE_EGRESS_ATTRIBUTE = "generation_egress_allowed"


def environment_overlay(prefs):
    """Map add-on preferences onto the env names this module reads.

    Only non-empty values are contributed, so layering this over ``os.environ``
    never blanks something an operator set there deliberately; preferences win
    where both are present. Duck-typed on purpose -- it takes any object with
    the attributes, so it needs no bpy import and is directly testable.
    """

    if prefs is None:
        return {}
    overlay = {}
    python_path = str(getattr(prefs, PREFERENCE_PYTHON_ATTRIBUTE, "") or "").strip()
    if python_path:
        for name in PREFERENCE_PYTHON_ENV_VARS:
            overlay[name] = python_path
    for attribute, name in PREFERENCE_ENV_MAP:
        value = str(getattr(prefs, attribute, "") or "").strip()
        if value:
            overlay[name] = value
    if bool(getattr(prefs, PREFERENCE_EGRESS_ATTRIBUTE, False)):
        overlay[EGRESS_ENV_VAR] = EGRESS_ALLOW
    return overlay


def _configured_env_names(names, environ):
    return [name for name in names if str(environ.get(name, "") or "").strip()]


def empty_hardware_probe():
    return {
        "probed": False,
        "cuda_available": False,
        "device_name": "",
        "vram_gb": 0.0,
        "compute_capability": 0.0,
        "supports_bfloat16": False,
        "message": "No hardware probe result supplied.",
    }


# Executed inside the provider's own interpreter, which is where torch lives.
# Blender's bundled Python has no torch and must never be assumed to.
_PROBE_SOURCE = """
import json
result = {"probed": True, "cuda_available": False, "device_name": "",
          "vram_gb": 0.0, "compute_capability": 0.0,
          "supports_bfloat16": False, "message": ""}
try:
    import torch
    result["torch_version"] = torch.__version__
    if torch.cuda.is_available():
        index = torch.cuda.current_device()
        props = torch.cuda.get_device_properties(index)
        major, minor = torch.cuda.get_device_capability(index)
        result.update({
            "cuda_available": True,
            "device_name": props.name,
            "vram_gb": round(props.total_memory / (1024 ** 3), 2),
            "compute_capability": float("%d.%d" % (major, minor)),
            # bfloat16 needs Ampere (SM 80) or newer in practice.
            "supports_bfloat16": bool(major >= 8),
            "message": "Probed via torch.",
        })
    else:
        result["message"] = "torch is installed but reports no CUDA device."
except Exception as error:
    result["probed"] = False
    result["message"] = "Hardware probe failed: %s" % error
print("GENERATION_PROBE " + json.dumps(result))
"""


# GPU capability cannot change within a Blender session, and the probe costs a
# full interpreter start plus a torch import -- seconds, on the main thread.
# Cache per resolved interpreter so repeated diagnostics calls are free.
_PROBE_CACHE = {}


def clear_hardware_probe_cache():
    _PROBE_CACHE.clear()


def _run_probe(argv):
    # Match the add-on's other child processes: no console window on Windows,
    # and none of the bridge's own credentials handed to third-party code.
    child_env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("BLENDER_BRIDGE_")
    }
    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=PROBE_TIMEOUT_SECONDS,
        check=False,
        env=child_env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return completed.returncode, completed.stdout, completed.stderr


def probe_hardware(python_executable="", environ=None, runner=None, use_cache=True):
    """Run the probe in an interpreter that has torch and return its findings.

    ``runner`` is injectable so tests never spawn a process. A failed probe is
    reported, never raised: routing degrades to "hardware unknown" and the
    caller still gets an actionable message.
    """

    source = environ if environ is not None else os.environ
    executable = str(
        python_executable or source.get(PROBE_PYTHON_ENV_VAR, "") or ""
    ).strip()
    if not executable:
        probe = empty_hardware_probe()
        probe["message"] = (
            "No probe interpreter configured. Set %s to a Python that has torch installed."
            % PROBE_PYTHON_ENV_VAR
        )
        return probe

    if use_cache and executable in _PROBE_CACHE:
        return dict(_PROBE_CACHE[executable])

    try:
        code, stdout, stderr = (runner or _run_probe)([executable, "-c", _PROBE_SOURCE])
    except Exception as error:  # noqa: BLE001 - probe failure must not propagate
        probe = empty_hardware_probe()
        probe["message"] = "Could not run the hardware probe: %s" % error
        return probe

    for line in str(stdout or "").splitlines():
        if line.startswith("GENERATION_PROBE "):
            try:
                probe = normalize_hardware_probe(json.loads(line[len("GENERATION_PROBE "):]))
            except ValueError:
                break
            if use_cache and probe.get("probed"):
                _PROBE_CACHE[executable] = dict(probe)
            return probe

    probe = empty_hardware_probe()
    detail = (str(stderr or "").strip() or "no probe output").splitlines()[-1:]
    probe["message"] = "Hardware probe returned no usable result (exit %s): %s" % (
        code,
        detail[0] if detail else "",
    )
    return probe


def normalize_hardware_probe(probe):
    """Coerce an arbitrary probe payload into the fields routing depends on."""

    if not isinstance(probe, dict):
        return empty_hardware_probe()
    return {
        "probed": bool(probe.get("probed", True)),
        "cuda_available": bool(probe.get("cuda_available")),
        "device_name": str(probe.get("device_name") or ""),
        "vram_gb": float(probe.get("vram_gb") or 0.0),
        "compute_capability": float(probe.get("compute_capability") or 0.0),
        "supports_bfloat16": bool(probe.get("supports_bfloat16")),
        "message": str(probe.get("message") or ""),
    }


_PROBE_KEYS = frozenset(empty_hardware_probe())


def _is_normalized(probe):
    return isinstance(probe, dict) and frozenset(probe) == _PROBE_KEYS


def _hardware_blockers(spec, hw):
    """Return (code, remedy) pairs for every capability the GPU cannot meet."""

    if not hw.get("probed"):
        return [("hardware_unknown", "Run the hardware probe so VRAM and compute capability can be checked.")]
    found = []
    if not hw.get("cuda_available"):
        found.append(("no_cuda_device", "No CUDA device was detected; local generation needs a supported GPU."))
    if spec.min_vram_gb and hw.get("vram_gb", 0.0) + 1e-6 < spec.min_vram_gb:
        found.append((
            "insufficient_vram",
            "Needs about %.0f GB VRAM; probe reported %.1f GB." % (spec.min_vram_gb, hw.get("vram_gb", 0.0)),
        ))
    if spec.min_compute_capability and hw.get("compute_capability", 0.0) + 1e-6 < spec.min_compute_capability:
        found.append((
            "compute_capability_too_low",
            "Needs compute capability %.1f or newer; probe reported %.1f."
            % (spec.min_compute_capability, hw.get("compute_capability", 0.0)),
        ))
    if spec.requires_bfloat16 and not hw.get("supports_bfloat16"):
        found.append((
            "no_bfloat16",
            "This model expects bfloat16, which this GPU architecture does not support natively.",
        ))
    return found


def provider_availability(spec, hardware=None, environ=None):
    """Decide whether one provider can run, and say why when it cannot.

    Every blocking condition is reported, not just the first, so an operator
    can fix a deployment in one pass instead of discovering issues serially.
    """

    source = environ if environ is not None else os.environ
    hw = hardware if _is_normalized(hardware) else normalize_hardware_probe(hardware)
    blockers = []
    remedies = []

    def block(code, remedy):
        """Record a blocker with its remedy so the two cannot drift apart."""

        blockers.append(code)
        remedies.append(remedy)

    if spec.requires_egress and egress_mode(source) != EGRESS_ALLOW:
        block(
            "egress_denied",
            "Network egress is denied by default. Set %s=%s to permit uploading reference "
            "images to a third-party service." % (EGRESS_ENV_VAR, EGRESS_ALLOW),
        )

    # Hosted services always need a credential. A self-hosted endpoint may sit
    # on a trusted network, so its token stays optional.
    if spec.kind == KIND_HOSTED_API and spec.credential_env_vars:
        if not _configured_env_names(spec.credential_env_vars, source):
            block("missing_credential", "Set one of: %s" % ", ".join(spec.credential_env_vars))

    if spec.kind == KIND_LOCAL_HTTP:
        if not _configured_env_names(spec.endpoint_env_vars, source):
            block("missing_endpoint", "Set one of: %s" % ", ".join(spec.endpoint_env_vars))

    if spec.kind == KIND_LOCAL_PROCESS:
        if not _configured_env_names(spec.runtime_env_vars, source):
            block(
                "missing_runtime",
                "Point at a prepared environment with one of: %s" % ", ".join(spec.runtime_env_vars),
            )
        for code, remedy in _hardware_blockers(spec, hw):
            block(code, remedy)

    return {
        "provider": spec.name,
        "title": spec.title,
        "kind": spec.kind,
        "available": not blockers,
        "blockers": blockers,
        "remedies": remedies,
        "requires_egress": spec.requires_egress,
        "supports_multiview": spec.supports_multiview,
        "max_input_images": spec.max_input_images,
        "credential_configured": bool(_configured_env_names(spec.credential_env_vars, source)),
        "configured_env_vars": _configured_env_names(
            spec.credential_env_vars + spec.endpoint_env_vars + spec.runtime_env_vars, source
        ),
        "job_implemented": spec.job_implemented,
        "license_note": spec.license_note,
        "notes": spec.notes,
    }


def generation_provider_diagnostics(environ=None, hardware=None):
    """Report every provider's availability without exposing any secret value.

    Mirrors the shape of ``external_assets.sketchfab_auth_diagnostics``: names
    of configured variables are listed, values never are.
    """

    source = environ if environ is not None else os.environ
    hw = normalize_hardware_probe(hardware)
    mode = egress_mode(source)
    reports = [provider_availability(spec, hardware=hw, environ=source) for spec in PROVIDER_SPECS]
    available = [item["provider"] for item in reports if item["available"]]
    return {
        "egress_mode": mode,
        "egress_env_var": EGRESS_ENV_VAR,
        "egress_message": (
            "Third-party generation providers are permitted to receive reference images."
            if mode == EGRESS_ALLOW
            else "Egress is denied; only local and self-hosted providers may run."
        ),
        "hardware": hw,
        "providers": reports,
        "available_providers": available,
        "available_count": len(available),
        "message": (
            "%d of %d generation provider(s) are ready." % (len(available), len(reports))
        ),
    }


def select_provider(preferred="", environ=None, hardware=None, require_multiview=False):
    """Choose a provider, preferring local ones and explaining any refusal."""

    diagnostics = generation_provider_diagnostics(environ=environ, hardware=hardware)
    by_name = {item["provider"]: item for item in diagnostics["providers"]}

    def refuse(message, **extra):
        """Every refusal carries the same keys so callers need no special cases."""

        payload = {
            "ok": False,
            "message": message,
            "selected": None,
            "report": None,
            "diagnostics": diagnostics,
        }
        payload.update(extra)
        return payload

    preferred = str(preferred or "").strip().lower()
    if preferred:
        report = by_name.get(preferred)
        if report is None:
            return refuse(
                "Unknown generation provider: %s" % preferred,
                known_providers=sorted(by_name),
            )
        if not report["available"]:
            return refuse(
                "Provider %s is not available: %s"
                % (preferred, "; ".join(report["remedies"]) or "unknown reason"),
                report=report,
            )
        if require_multiview and not report["supports_multiview"]:
            return refuse(
                "Provider %s does not accept multiple views." % preferred,
                report=report,
            )
        return {"ok": True, "selected": preferred, "report": report, "diagnostics": diagnostics}

    # Auto-selection covers local providers only. A hosted provider spends the
    # user's money and sends their reference art to a third party, so it is
    # never chosen on the user's behalf -- it must be named in the request.
    # Available hosted providers are returned as suggestions instead, so a
    # planner can offer one and let the user decide.
    order = (KIND_LOCAL_PROCESS, KIND_LOCAL_HTTP)
    skipped_unimplemented = []
    for kind in order:
        for spec in PROVIDER_SPECS:
            if spec.kind != kind:
                continue
            report = by_name[spec.name]
            if not report["available"]:
                continue
            if require_multiview and not report["supports_multiview"]:
                continue
            if not spec.job_implemented:
                skipped_unimplemented.append(spec.name)
                continue
            return {"ok": True, "selected": spec.name, "report": report, "diagnostics": diagnostics}

    suggestions = [
        spec.name
        for spec in PROVIDER_SPECS
        if spec.kind == KIND_HOSTED_API
        and spec.job_implemented
        and by_name[spec.name]["available"]
        and (not require_multiview or spec.supports_multiview)
    ]

    if suggestions:
        return refuse(
            "No local generation provider is available. %s can do this but %s a paid "
            "third-party service that uploads the reference images, so name it explicitly "
            "to use it."
            % (
                ", ".join(sorted(suggestions)),
                "is" if len(suggestions) == 1 else "are",
            ),
            suggested_providers=sorted(suggestions),
            requires_explicit_choice=True,
            unimplemented_providers=sorted(skipped_unimplemented),
        )
    if skipped_unimplemented:
        return refuse(
            "No generation provider with a job backend is available. These are configured "
            "but not yet implemented: %s" % ", ".join(sorted(skipped_unimplemented)),
            unimplemented_providers=sorted(skipped_unimplemented),
        )
    return refuse("No generation provider is currently available.")
