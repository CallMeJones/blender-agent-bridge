"""Provider-neutral generated-mesh retopology tools."""
from ..registry import ToolSpec


def _spec(name, description, properties, *, required=(), preview=False, order=1930, permissions=None, contract=None):
    schema = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = list(required)
    permissions = permissions or (["scene:read", "scene:mutate", "preview:write"] if preview else ["scene:read"])
    return ToolSpec(name=name, description=description, input_schema=schema,
                    contract={"mutates_scene": preview, "requires_live_preview": preview,
                              "permissions": permissions, "has_side_effects": preview or any(p.endswith(":write") or p.startswith("process:") for p in permissions),
                              "supports_headless": True, **(contract or {})}, handler_key=name, order=order,
                    groups=("retopology", "model_quality", "external_assets"), owner="retopology")


OBJECTS = {"object_names": {"type": "array", "items": {"type": "string"}, "maxItems": 8}}
BAKING = {
    "resolution": {"type": "integer", "minimum": 16, "maximum": 4096},
    "map_types": {"type": "array", "items": {"type": "string", "enum": ["base_color", "normal", "roughness", "metallic", "emission"]}, "minItems": 1, "maxItems": 5},
    "samples": {"type": "integer", "minimum": 1, "maximum": 256},
    "margin": {"type": "integer", "minimum": 0, "maximum": 64},
    "uv_mode": {"type": "string", "enum": ["smart_project", "existing"]},
    "ray_distance_ratio": {"type": "number", "minimum": .00001, "maximum": 1},
    "cage_extrusion_ratio": {"type": "number", "minimum": 0, "maximum": .2},
    "max_deviation_ratio": {"type": "number", "minimum": 0, "maximum": 1},
    "intended_use": {"type": "string", "enum": ["prop", "character"]},
    "timeout_seconds": {"type": "integer", "minimum": 30, "maximum": 7200},
}
JOB = {"job_id": {"type": "string"}}
SPECS = (
    _spec("inspect_retopology_source", "Inspect mesh density, actual triangle/quad counts, surface islands, open/nonmanifold edges, UVs, textures and rig risks before retopology. Read-only; works for Meshy, Tripo and other meshes.", OBJECTS),
    _spec("prepare_retopology_copy", "Create independent static working meshes and material copies while preserving the originals. Captures the evaluated current pose, removes loose/degenerate geometry, merges near-coincident vertices and recalculates normals. Surface islands are kept by default. Preview-safe; rig and shape keys are not transferred.",
          {**OBJECTS, "name_suffix": {"type": "string", "maxLength": 80},
           "merge_distance_ratio": {"type": "number", "minimum": 0, "maximum": 0.01},
           "min_component_faces": {"type": "integer", "minimum": 0, "maximum": 10000},
           "shade_smooth": {"type": "boolean"}, "label": {"type": "string"}}, preview=True, order=1931),
    _spec("evaluate_retopology_result", "Compare an original and retopology result using bounded bidirectional world-space surface samples, topology/material reports and optional front/side/top previews. Reports sampling limits and character edge-loop review requirements; never certifies automatic output as animation-ready.",
          {"source_object_name": {"type": "string"}, "target_object_name": {"type": "string"},
           "sample_count": {"type": "integer", "minimum": 32, "maximum": 8192},
           "max_deviation_ratio": {"type": "number", "minimum": 0, "maximum": 1},
           "intended_use": {"type": "string", "enum": ["prop", "character"]}, "include_renders": {"type": "boolean"}},
          required=("source_object_name", "target_object_name"), order=1932, permissions=["scene:read", "files:write"],
          contract={"long_running": True, "timeout_seconds": 180,
                    "timeout_recovery": {"recoverable": True, "status_tool": "blender_bridge_status", "poll_after_seconds": 5,
                                         "message": "If inspection renders time out, check bridge status and visual evidence resources before retrying."}}),
    _spec("start_retopology_job", "Snapshot one to eight source meshes without changing the scene, then run cleanup, QuadriFlow quad remeshing or triangle-budget decimation, optional surface projection and PBR rebaking in a supervised background Blender process. target_faces is per object and approximate. Defaults to baked 1024px PBR maps; no cloud API required. Poll status and explicitly import the result for preview. Does not transfer rigs or shape keys.",
          {**OBJECTS, **BAKING, "method": {"type": "string", "enum": ["quadriflow", "decimate"]},
           "target_faces": {"type": "integer", "minimum": 50, "maximum": 100000},
           "bake_textures": {"type": "boolean"}, "project_to_source": {"type": "boolean"},
           "use_symmetry": {"type": "boolean"}, "preserve_sharp": {"type": "boolean"}, "preserve_boundary": {"type": "boolean"},
           "seed": {"type": "integer", "minimum": 0, "maximum": 1000000},
           "merge_distance_ratio": {"type": "number", "minimum": 0, "maximum": .01}},
          order=1933, permissions=["scene:read", "files:write", "process:spawn"]),
    _spec("start_retopology_bake_job", "Rebake a source mesh's base color, tangent normal, roughness, metallic and HDR emission onto a separate target mesh in background Blender. Outputs a new target copy with packed textures, a UV atlas and measured projection coverage. Original source and target remain untouched. Supports a Principled BSDF connected directly to the material output, including ordinary Meshy/Tripo GLB imports. Shader groups/mixes are rejected; opacity, transmission and coat need manual review.",
          {"source_object_name": {"type": "string"}, "target_object_name": {"type": "string"}, **BAKING},
          required=("source_object_name", "target_object_name"), order=1934,
          permissions=["scene:read", "files:write", "process:spawn"]),
    _spec("get_retopology_job_status", "Poll local retopology job phase/progress, terminal outcome and topology, shape-deviation and texture-coverage reports. A timed-out client request does not stop the worker; keep polling the returned job_id.", JOB,
          required=("job_id",), order=1935, permissions=["files:read", "files:write", "process:terminate"]),
    _spec("cancel_retopology_job", "Stop a local retopology worker and its process tree. Preserves source meshes and prevents incomplete results from being imported.", JOB,
          required=("job_id",), order=1936, permissions=["files:write", "process:terminate"]),
    _spec("import_retopology_job_result", "Append a completed local remesh/bake result as new objects and materials with packed textures through live preview. Repeated imports reuse the current scene's existing result. Never replaces the source; review the result, then commit or revert preview.",
          {**JOB, "label": {"type": "string"}}, required=("job_id",), preview=True, order=1937),
    _spec("start_provider_retopology_job", "Request Meshy Remesh or Tripo v3 retopology for an existing provider task or public HTTPS model URL. Runs through the same exact-job Blender UI spend approval and background asset workers as generation. Meshy quad output uses FBX plus a GLB companion; Tripo GLB output stores triangles. No agent flag grants paid approval. Poll get_generation_approval_status, then repeat this exact call once approved; poll the returned asset job and import a new candidate.",
          {"provider": {"type": "string", "enum": ["meshy", "tripo"]},
           "source_task_id": {"type": "string"}, "model_url": {"type": "string"},
           "target_faces": {"type": "integer", "minimum": 1, "maximum": 2000000},
           "topology": {"type": "string", "enum": ["quad", "triangle"]},
           "retopology_model": {"type": "string", "enum": ["v3.0", "v2.0", "v1.0"]},
           "smart_uv": {"type": "boolean"}, "bake": {"type": "boolean"},
           "timeout": {"type": "integer", "minimum": 1, "maximum": 300},
           "poll_timeout_seconds": {"type": "integer", "minimum": 30, "maximum": 7200}},
          required=("provider",), order=1938, permissions=["network:read", "network:write", "files:write"]),
    _spec("get_provider_retopology_job_status", "Poll a Meshy/Tripo retopology asset job and recover its task ID and cached manifest. Use cancel_external_asset_job to stop local work and request provider cancellation where supported. Do not resubmit an already-running paid request.",
          JOB, required=("job_id",), order=1939, permissions=["files:read"]),
    _spec("import_provider_retopology_job_result", "Import a completed provider retopology candidate or cached Meshy generation format variant into live preview. preferred_format=fbx imports Meshy quad faces instead of the triangulated GLB when a cached FBX exists. Missing requested formats fail explicitly. Original scene models stay intact; compare before committing preview.",
          {**JOB, "preferred_format": {"type": "string", "enum": ["auto", "fbx", "glb"]}, "label": {"type": "string"}},
          required=("job_id",), preview=True, order=1940),
)


def register(registry):
    registry.register_many(SPECS)


def register_handlers(handler_registry):
    from ...tool_handlers import retopology
    retopology.register(handler_registry, SPECS)
