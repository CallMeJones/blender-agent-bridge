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
    'description': 'Maps a view name to a local image path. Multi-view providers treat the '
                   'names as positional slots, so a mislabelled view produces a worse model '
                   'rather than an error. Supply "front" alone for single-image generation.',
    'properties': {name: {'type': 'string'} for name in _VIEW_SLOTS},
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
                 'authored scripts and bounded helpers unless the user asks for generation. Only local providers are '
                 'selected automatically. A hosted provider such as Tripo or Meshy spends the user\'s credits and '
                 'uploads their reference images to a third party, so it is never chosen automatically: name it in '
                 '"provider" only when the user asked for it, or suggest it and let them decide. Call '
                 'get_generation_provider_diagnostics when provider readiness is unknown. Naming a paid provider is '
                 'not enough to start it: the first call returns requires_confirmation with the cost, which must be '
                 'told to the user, and only a second call with confirm_paid=true spends anything. The finished model '
                 'is cached like any external asset, so import it with start_external_asset_import_job.',
  'input_schema': {'type': 'object',
                   'properties': {'views': _VIEWS_SCHEMA,
                                  'provider': {'type': 'string',
                                               'description': 'Omit to auto-select a local provider. Hosted providers '
                                                              '(tripo, meshy) cost credits and upload the images, so '
                                                              'they are never auto-selected and must be named here.'},
                                  'confirm_paid': {'type': 'boolean',
                                                   'description': 'Set only after telling the user the cost and '
                                                                  'getting their agreement. Required before any '
                                                                  'hosted provider will start. Never set it in the '
                                                                  'same turn the cost was discovered.'},
                                  'model': {'type': 'string'},
                                  'face_limit': {'type': 'integer', 'minimum': 0, 'maximum': 1000000},
                                  'job_name': {'type': 'string'},
                                  'note': {'type': 'string'},
                                  'cache_dir': {'type': 'string'},
                                  'timeout': {'type': 'integer', 'minimum': 1, 'maximum': 300}},
                   'required': ['views'],
                   'additionalProperties': False},
  'contract': {'description': 'Start an asynchronous paid image-to-3D generation job and return a job id to poll',
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
                                               'confirm_paid': {'type': 'boolean'},
                                               'model': {'type': 'string'},
                                               'face_limit': {'type': 'integer'},
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
