"""Canonical tool specifications for the image-to-3D generation domain.

Generation synthesises a new asset from reference images. It shares the cache
and import tail with the external-assets catalog domain -- and reuses that
domain's job machinery -- but its inputs and verbs are distinct, so it owns its
own tools. See docs/adr/ADR-001-generation-provider-layer.md.
"""

from __future__ import annotations

from ..registry import ToolSpec


_VIEW_SLOTS = ("front", "left", "back", "right")

_VIEWS_SCHEMA = {
    'type': 'object',
    'description': 'Maps a canonical view name to a local image path. Tripo treats multi-view names as fixed '
                   'positional slots. Meshy uses front as the primary first image and accepts the remaining '
                   'angles in any order. Supply front alone for single-image generation.',
    'properties': {name: {'type': 'string'} for name in _VIEW_SLOTS},
    'additionalProperties': False,
}

_MESHY_OPTIONS_SCHEMA = {
    'type': 'object',
    'description': 'Meshy-only generation controls. Defaults to blender_working, which requests a remeshed '
                   'Blender-oriented GLB while preserving the raw pre-remesh model. Use raw_high_detail to '
                   'retain the previous unremeshed behavior.',
    'properties': {
        'preset': {'type': 'string',
                   'enum': ['raw_high_detail', 'blender_working', 'editable_quad'],
                   'description': 'raw_high_detail: maximum raw triangles. blender_working: 100k triangle PBR '
                                  'mesh plus raw source. editable_quad: 50k quad target plus raw source.'},
        'ai_model': {'type': 'string',
                     'enum': ['latest', 'meshy-7', 'meshy-6', 'meshy-5', 'meshy-t2']},
        'model_type': {'type': 'string', 'enum': ['standard', 'smart-topology']},
        'ultra_mode': {'type': 'boolean',
                       'description': 'Single-image Meshy 7/latest only; adds five credits.'},
        'should_texture': {'type': 'boolean'},
        'enable_pbr': {'type': 'boolean'},
        'texture_resolution': {'type': 'string', 'enum': ['2k', '4k', '8k']},
        'should_remesh': {'type': 'boolean'},
        'topology': {'type': 'string', 'enum': ['triangle', 'quad']},
        'target_polycount': {'type': 'integer', 'minimum': 100, 'maximum': 300000},
        'decimation_mode': {'type': 'string', 'enum': ['ultra', 'high', 'medium', 'low'],
                            'description': 'Adaptive provider decimation. Cannot be combined with target_polycount.'},
        'save_pre_remeshed_model': {'type': 'boolean'},
        'image_enhancement': {'type': 'boolean'},
        'remove_lighting': {'type': 'boolean',
                            'description': 'Lighting removal. Single-image Meshy currently documents this for '
                                           'meshy-6; multi-image also supports meshy-7/latest.'},
        'auto_size': {'type': 'boolean'},
        'origin_at': {'type': 'string', 'enum': ['bottom', 'center']},
        'alpha_thumbnail': {'type': 'boolean'},
        'multi_view_thumbnails': {'type': 'boolean',
                                  'description': 'Cache front/right/back/left provider thumbnails; requires auto_size.'},
    },
    'additionalProperties': False,
}


SPECS = tuple(ToolSpec(**payload) for payload in [
 {'name': 'get_generation_provider_diagnostics',
  'description': 'Report which image-to-3D generation providers are usable on this machine and, for each unusable one, '
                 'exactly why. Covers local models, a self-hosted studio endpoint, and hosted APIs. Network egress is '
                 'denied by default so reference art stays local until an operator opts in. Credential presence is '
                 'reported by environment-variable name; values are never returned.',
  'input_schema': {'type': 'object',
                   'properties': {'probe_python': {'type': 'string',
                                                   'description': 'Interpreter with torch installed, used to read GPU '
                                                                  'VRAM and compute capability.'},
                                  'refresh_hardware': {'type': 'boolean',
                                                       'description': 'Re-run the GPU probe instead of using the '
                                                                      'cached result from this session.'}},
                   'additionalProperties': False},
  'contract': {'description': 'Report generation provider availability, hardware capability, and egress policy',
               'mutates_scene': False,
               'permissions': ['process:start'],
               'supports_headless': True,
               'input_schema': {'type': 'object',
                                'properties': {'probe_python': {'type': 'string'},
                                               'refresh_hardware': {'type': 'boolean'}},
                                'additionalProperties': False}},
  'handler_key': 'get_generation_provider_diagnostics',
  'order': 1900,
  'groups': ('external_assets',),
  'exposure': 'catalog',
  'owner': 'generation'},

 {'name': 'set_generation_policy',
  'description': 'Record a STANDING instruction about how models may be built for the rest of the session. Only for '
                 'instructions the user meant to apply generally -- "never use a paid API", "nothing leaves my machine '
                 'today", "always prefer scripts". Do NOT call this for a single task: "build this one with scripts" '
                 'is a per-task choice you honour by using scripts, and recording it would wrongly refuse a later '
                 'request for generation that the user does want. When in doubt, do not record it; a missing policy '
                 'costs nothing, while a wrong one blocks work the user asked for. Once recorded the bridge enforces '
                 'it even after it leaves your context, and a later attempt is refused with the user\'s own words '
                 'quoted back. Use "no_generation" for scripts and helpers only, "local_only" to forbid anything that '
                 'uploads, and "any" to lift a policy -- lifting is allowed whenever the user asks for something the '
                 'policy forbids, since asking is how they relax it.',
  'input_schema': {'type': 'object',
                   'properties': {'policy': {'type': 'string',
                                             'enum': ['any', 'local_only', 'no_generation'],
                                             'description': 'no_generation: scripts and helpers only. local_only: no '
                                                            'third-party uploads. any: no standing restriction.'},
                                  'reason': {'type': 'string',
                                             'description': "The user's own words, quoted back to you if a later "
                                                            'attempt is refused.'}},
                   'required': ['policy'],
                   'additionalProperties': False},
  'contract': {'description': 'Record a session-scoped standing instruction about generation providers',
               'mutates_scene': False,
               'supports_headless': True,
               'input_schema': {'type': 'object',
                                'properties': {'policy': {'type': 'string',
                                                          'enum': ['any', 'local_only', 'no_generation']},
                                               'reason': {'type': 'string'}},
                                'required': ['policy'],
                                'additionalProperties': False}},
  'handler_key': 'set_generation_policy',
  'order': 1903,
  'groups': ('external_assets',),
  'exposure': 'catalog',
  'owner': 'generation'},

 {'name': 'plan_image_to_3d_approach',
  'description': 'Call this FIRST whenever the user asks for a 3D model to be built from an image or reference sheet, '
                 'before preparing references, authoring a script, or starting any generation job. Returns every '
                 'available route -- authoring it in Blender, a local model, a self-hosted endpoint, a paid hosted API '
                 '-- with its cost, whether the reference images leave the machine, and what kind of mesh it produces. '
                 'The routes differ in ways only the user can weigh, so put the choice to them in your reply and wait '
                 'for an answer rather than selecting one yourself. Read-only: costs nothing and starts nothing.',
  'input_schema': {'type': 'object',
                   'properties': {'views': _VIEWS_SCHEMA,
                                  'note': {'type': 'string',
                                           'description': 'What the user asked for, to keep with the plan.'}},
                   'additionalProperties': False},
  'contract': {'description': 'List every route from reference images to a model so the user can choose one',
               'mutates_scene': False,
               'permissions': ['process:start'],
               'supports_headless': True,
               'input_schema': {'type': 'object',
                                'properties': {'views': _VIEWS_SCHEMA,
                                               'note': {'type': 'string'}},
                                'additionalProperties': False}},
  'handler_key': 'plan_image_to_3d_approach',
  'order': 1905,
  'groups': ('external_assets',),
  'exposure': 'catalog',
  'owner': 'generation'},

 {'name': 'start_generation_job',
  'description': 'Start an asynchronous image-to-3D generation job from one or more calibrated reference images, then '
                 'poll get_generation_job_status until terminal. Generation is not the default modelling path; prefer '
                 'authored scripts and bounded helpers unless the user asks for generation. When more than one '
                 'generation provider is runnable, omitting "provider" returns the available choices and requires '
                 'the user to select one; the bridge does not prefer local, hosted, cheap, or fast on their behalf. '
                 'A sole local provider may be selected automatically. A hosted provider such as Tripo or Meshy '
                 'spends the user\'s credits and uploads their reference images to a third party, so it is never '
                 'chosen automatically: name it in "provider" only when the user asked for it. Call '
                 'get_generation_provider_diagnostics when provider readiness is unknown. Naming a paid provider is '
                 'not enough to start it: the first call returns requires_confirmation with the cost, which must be '
                 'told to the user, and the user must then click Approve in the Blender sidebar. No argument grants this: '
                 'poll get_generation_approval_status with the returned request id so the user does not have to report '
                 'their click, then call again with the exact same arguments only after approval. The finished model '
                 'is cached like any external asset, so import it with start_external_asset_import_job. TripoSR is a '
                 'single-image local blockout route: use its knobs to tune extraction, but do not treat it as final '
                 'multi-view quality.',
  'input_schema': {'type': 'object',
                   'properties': {'views': _VIEWS_SCHEMA,
                                  'provider': {'type': 'string',
                                               'description': 'Required when multiple providers are runnable. Omit only '
                                                              'to use the sole available local provider. Hosted '
                                                              'providers cost credits and upload the images, so they '
                                                              'are never auto-selected.'},
                                  'model': {'type': 'string'},
                                  'face_limit': {'type': 'integer', 'minimum': 0, 'maximum': 1000000},
                                  'texture': {'type': 'boolean'},
                                  'meshy_options': _MESHY_OPTIONS_SCHEMA,
                                  'mc_resolution': {'type': 'integer',
                                                    'minimum': 16,
                                                    'maximum': 512,
                                                    'description': 'TripoSR marching-cubes grid resolution. Higher '
                                                                   'values preserve detail but create heavier meshes.'},
                                  'no_remove_bg': {'type': 'boolean',
                                                   'description': 'TripoSR: skip automatic background removal. Use only '
                                                                  'when the input is already foreground-isolated.'},
                                  'foreground_ratio': {'type': 'number',
                                                       'minimum': 0.1,
                                                       'maximum': 1.0,
                                                       'description': 'TripoSR foreground resize ratio when background '
                                                                      'removal is enabled. Default is 0.85.'},
                                  'chunk_size': {'type': 'integer',
                                                 'minimum': 0,
                                                 'maximum': 262144,
                                                 'description': 'TripoSR evaluation chunk size. Lower values reduce '
                                                                'VRAM use but can run slower; 0 disables chunking.'},
                                  'bake_texture': {'type': 'boolean',
                                                   'description': 'TripoSR: bake a texture atlas instead of relying on '
                                                                  'vertex colors when the runtime supports it.'},
                                  'texture_resolution': {'type': 'integer',
                                                         'minimum': 256,
                                                         'maximum': 8192,
                                                         'description': 'TripoSR texture atlas resolution when '
                                                                        'bake_texture is true.'},
                                  'job_name': {'type': 'string'},
                                  'note': {'type': 'string'},
                                  'cache_dir': {'type': 'string'},
                                  'timeout': {'type': 'integer', 'minimum': 1, 'maximum': 300}},
                   'required': ['views'],
                   'additionalProperties': False},
  'contract': {'description': 'Start an asynchronous image-to-3D generation job and return a job id to poll',
               'mutates_scene': False,
               'has_side_effects': True,
               'permissions': ['files:read', 'files:write', 'network:full', 'process:start'],
               'supports_headless': True,
               'returns_background_job': True,
               'requires_user_path': True,
               'path_policy': 'Every view image path must be a local path explicitly supplied by the user, a file '
                              'picker, a prior capture, or another trusted local source.',
               'timeout_seconds': 30,
               'duration_hint': 'Returns quickly after starting the job. Generation itself typically takes one to a '
                                'few minutes; poll get_generation_job_status.',
               'timeout_recovery': {'recoverable': True,
                                    'poll_after_seconds': 5,
                                    'status_tool': 'get_generation_job_status',
                                    'bridge_status_tool': 'blender_bridge_status'},
               'input_schema': {'type': 'object',
                                'properties': {'views': _VIEWS_SCHEMA,
                                               'provider': {'type': 'string'},
                                               'model': {'type': 'string'},
                                               'face_limit': {'type': 'integer'},
                                               'texture': {'type': 'boolean'},
                                               'meshy_options': _MESHY_OPTIONS_SCHEMA,
                                               'mc_resolution': {'type': 'integer'},
                                               'no_remove_bg': {'type': 'boolean'},
                                               'foreground_ratio': {'type': 'number'},
                                               'chunk_size': {'type': 'integer'},
                                               'bake_texture': {'type': 'boolean'},
                                               'texture_resolution': {'type': 'integer'},
                                               'job_name': {'type': 'string'},
                                               'note': {'type': 'string'},
                                               'cache_dir': {'type': 'string'},
                                               'timeout': {'type': 'integer'}},
                                'required': ['views'],
                                'additionalProperties': False}},
  'handler_key': 'start_generation_job',
  'order': 1910,
  'groups': ('external_assets',),
  'exposure': 'catalog',
  'owner': 'generation'},

 {'name': 'get_generation_approval_status',
  'description': 'Poll one paid hosted-generation approval request after start_generation_job asks the user to decide '
                 'in Blender. Returns pending, approved, declined, expired, or consumed state plus the next action. Poll '
                 'the returned request id every two seconds instead of asking the user to report whether they clicked '
                 'Approve or Decline. Approval never starts a job by itself: after approved, call start_generation_job '
                 'once with the exact original arguments. TripoSR is local and never creates a spend request.',
  'input_schema': {'type': 'object',
                   'properties': {'request_id': {'type': 'string'}},
                   'required': ['request_id'],
                   'additionalProperties': False},
  'contract': {'description': 'Poll a Blender UI decision for one paid generation request',
               'mutates_scene': False,
               'supports_headless': True,
               'input_schema': {'type': 'object',
                                'properties': {'request_id': {'type': 'string'}},
                                'required': ['request_id'],
                                'additionalProperties': False}},
  'handler_key': 'get_generation_approval_status',
  'order': 1912,
  'groups': ('external_assets',),
  'exposure': 'catalog',
  'owner': 'generation'},

 {'name': 'cleanup_generated_asset',
  'description': 'Preview-safe cleanup pass for generated meshes after import. Shades the mesh smooth, can add '
                 'Weighted Normal, Decimate, and Voxel Remesh modifiers non-destructively, and preserves existing '
                 'materials unless the caller deliberately changes them later. Use for TripoSR/local blockouts before '
                 'visual review; it does not make single-view output final-quality.',
  'input_schema': {'type': 'object',
                   'properties': {'object_names': {'type': 'array', 'items': {'type': 'string'}},
                                  'target_object_name': {'type': 'string'},
                                  'selected_only': {'type': 'boolean'},
                                  'max_objects': {'type': 'integer', 'minimum': 1, 'maximum': 64},
                                  'shade_smooth': {'type': 'boolean'},
                                  'add_weighted_normals': {'type': 'boolean'},
                                  'decimate_ratio': {'type': 'number',
                                                     'minimum': 0.01,
                                                     'maximum': 1.0,
                                                     'description': 'Add a non-destructive Decimate modifier when below 1.0.'},
                                  'remesh_voxel_size': {'type': 'number',
                                                        'minimum': 0.0,
                                                        'maximum': 10.0,
                                                        'description': 'Add a non-destructive Voxel Remesh modifier when above 0.'},
                                  'preserve_materials': {'type': 'boolean'},
                                  'label': {'type': 'string'}},
                   'additionalProperties': False},
  'contract': {'description': 'Preview-safe generated mesh cleanup with optional non-destructive modifiers',
               'mutates_scene': True,
               'requires_live_preview': True,
               'permissions': ['scene:read', 'scene:mutate', 'preview:write'],
               'supports_headless': True,
               'timeout_seconds': 60,
               'input_schema': {'type': 'object',
                                'properties': {'object_names': {'type': 'array', 'items': {'type': 'string'}},
                                               'target_object_name': {'type': 'string'},
                                               'selected_only': {'type': 'boolean'},
                                               'max_objects': {'type': 'integer'},
                                               'shade_smooth': {'type': 'boolean'},
                                               'add_weighted_normals': {'type': 'boolean'},
                                               'decimate_ratio': {'type': 'number'},
                                               'remesh_voxel_size': {'type': 'number'},
                                               'preserve_materials': {'type': 'boolean'},
                                               'label': {'type': 'string'}},
                                'additionalProperties': False}},
  'handler_key': 'cleanup_generated_asset',
  'order': 1915,
  'groups': ('external_assets', 'generation_quality'),
  'exposure': 'catalog',
  'owner': 'generation'},

 {'name': 'evaluate_generated_asset',
  'description': 'Evaluate an imported generated mesh with topology/material/component/orientation checks and optional '
                 'front/side/top inspection renders. Flags single-view TripoSR relief-shell risk, vertex-color-only '
                 'materials, excessive density, fragmented components, incomplete renders, and non-Z-up orientation. Use before claiming a '
                 'generated result is more than a blockout.',
  'input_schema': {'type': 'object',
                   'properties': {'object_names': {'type': 'array', 'items': {'type': 'string'}},
                                  'target_object_name': {'type': 'string'},
                                  'selected_only': {'type': 'boolean'},
                                  'max_objects': {'type': 'integer', 'minimum': 1, 'maximum': 64},
                                  'manifest_path': {'type': 'string',
                                                    'description': 'Optional generated asset manifest; enables provider/view-count-specific findings.'},
                                  'include_renders': {'type': 'boolean'},
                                  'views': {'type': 'array',
                                            'items': {'type': 'string',
                                                      'enum': ['front_below', 'underside', 'side', 'front', 'rear', 'top']}},
                                  'resolution_x': {'type': 'integer', 'minimum': 128, 'maximum': 2048},
                                  'resolution_y': {'type': 'integer', 'minimum': 128, 'maximum': 2048},
                                  'note': {'type': 'string'}},
                   'additionalProperties': False},
  'contract': {'description': 'Evaluate imported generated mesh quality and optionally capture inspection renders',
               'mutates_scene': False,
               'has_side_effects': True,
               'permissions': ['scene:read', 'files:read', 'files:write'],
               'supports_headless': True,
               'timeout_seconds': 180,
               'duration_hint': 'Optional inspection renders can take several seconds per object/view.',
               'timeout_recovery': {'recoverable': True,
                                    'poll_after_seconds': 5,
                                    'status_tool': 'blender_bridge_status',
                                    'resource_tool': 'get_visual_evidence_resources'},
               'input_schema': {'type': 'object',
                                'properties': {'object_names': {'type': 'array', 'items': {'type': 'string'}},
                                               'target_object_name': {'type': 'string'},
                                               'selected_only': {'type': 'boolean'},
                                               'max_objects': {'type': 'integer'},
                                               'manifest_path': {'type': 'string'},
                                               'include_renders': {'type': 'boolean'},
                                               'views': {'type': 'array', 'items': {'type': 'string'}},
                                               'resolution_x': {'type': 'integer'},
                                               'resolution_y': {'type': 'integer'},
                                               'note': {'type': 'string'}},
                                'additionalProperties': False}},
  'handler_key': 'evaluate_generated_asset',
  'order': 1918,
  'groups': ('external_assets', 'generation_quality'),
  'exposure': 'catalog',
  'owner': 'generation'},

 {'name': 'get_generation_job_status',
  'description': 'Poll an asynchronous generation job for status, progress, provider task id, cached manifest path, '
                 'and import readiness. When completed, import the cached model with start_external_asset_import_job.',
  'input_schema': {'type': 'object',
                   'properties': {'job_id': {'type': 'string'}},
                   'required': ['job_id'],
                   'additionalProperties': False},
  'contract': {'description': 'Poll an asynchronous generation job for status, progress, and import readiness',
               'mutates_scene': False,
               'permissions': ['files:read'],
               'supports_headless': True,
               'input_schema': {'type': 'object',
                                'properties': {'job_id': {'type': 'string'}},
                                'required': ['job_id'],
                                'additionalProperties': False}},
  'handler_key': 'get_generation_job_status',
  'order': 1920,
  'groups': ('external_assets',),
  'exposure': 'catalog',
  'owner': 'generation'}])


def register(registry):
    registry.register_many(SPECS)


def register_handlers(handler_registry):
    from ...tool_handlers import generation

    generation.register(handler_registry, SPECS)
