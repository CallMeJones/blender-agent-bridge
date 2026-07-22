"""Canonical tool specifications for the scripts transactions domain."""

from __future__ import annotations

from ..registry import ToolSpec


SPECS = tuple(ToolSpec(**payload) for payload in [{'name': 'draft_script',
  'description': 'Run Blender Python immediately after static checks when Blender-side session script trust is active. '
                 'When trust is off the request is refused without staging a pending script. Use only when bounded '
                 'helper tools cannot express the requested scene, animation, material, or rig change.',
  'input_schema': {'type': 'object',
                   'properties': {'intent': {'type': 'string', 'description': 'Plain-language reason for the script'},
                                  'expected_changes': {'type': 'string',
                                                       'description': 'Visible scene/data changes the user should '
                                                                      'expect if they approve it'},
                                  'risk_level': {'type': 'string',
                                                 'enum': ['low', 'medium', 'high'],
                                                 'description': 'Risk estimate based on scope, destructiveness, and '
                                                                'API uncertainty'},
                                  'target_objects': {'type': 'array',
                                                     'items': {'type': 'string'},
                                                     'description': 'Object or datablock names the script intends to '
                                                                    'touch'},
                                  'code': {'type': 'string',
                                           'maxLength': 500000,
                                           'description': 'Complete Blender Python script to stage for approval'}},
                   'required': ['intent', 'expected_changes', 'risk_level', 'code'],
                   'additionalProperties': False},
  'contract': {'description': 'Run generated Blender Python after static checks only while Blender-side session script '
                              'trust is active',
               'mutates_scene': True,
               'has_side_effects': True,
               'requires_approval': False},
  'handler_key': 'draft_script',
  'order': 1810,
  'groups': (),
  'exposure': 'catalog',
  'owner': 'scripts_transactions'},
 {'name': 'draft_privileged_script',
  'description': 'Compatibility endpoint that refuses privileged generated Python. Use bounded external-asset, '
                 'project-file, render, capture, save, or project-output tools instead.',
  'input_schema': {'type': 'object',
                   'properties': {'script_kind': {'type': 'string',
                                                  'enum': ['external_asset', 'project_file', 'asset_project_file'],
                                                  'description': 'Privileged workflow class that determines default '
                                                                 'capabilities and approval checks.'},
                                  'intent': {'type': 'string',
                                             'description': 'Plain-language reason for the privileged script'},
                                  'expected_changes': {'type': 'string',
                                                       'description': 'Visible scene, file, asset-cache, or '
                                                                      'project-file changes the user should expect'},
                                  'approval_summary': {'type': 'string',
                                                       'description': 'Concise approval manifest explaining why helper '
                                                                      'tools are insufficient and what the script may '
                                                                      'touch'},
                                  'capabilities': {'type': 'array',
                                                   'items': {'type': 'string',
                                                             'enum': ['filesystem',
                                                                      'network',
                                                                      'asset_import',
                                                                      'project_file']},
                                                   'description': 'Requested elevated capabilities. Defaults are '
                                                                  'inferred from script_kind and merged with this '
                                                                  'list.'},
                                  'declared_paths': {'type': 'array',
                                                     'items': {'type': 'string'},
                                                     'description': 'Files, directories, cache locations, or .blend '
                                                                    'paths the script may read/write/open/save'},
                                  'declared_urls': {'type': 'array',
                                                    'items': {'type': 'string'},
                                                    'description': 'Network URLs, API endpoints, providers, or asset '
                                                                   'sources the script may contact'},
                                  'destructive_actions': {'type': 'array',
                                                          'items': {'type': 'string'},
                                                          'description': 'Expected overwrite, open, delete, import, '
                                                                         'save, or discard operations. Use an empty '
                                                                         'list only when none are expected.'},
                                  'risk_level': {'type': 'string',
                                                 'enum': ['low', 'medium', 'high'],
                                                 'description': 'Risk estimate based on file/network/project impact. '
                                                                'Defaults to high.'},
                                  'target_objects': {'type': 'array',
                                                     'items': {'type': 'string'},
                                                     'description': 'Object or datablock names the script intends to '
                                                                    'touch'},
                                  'code': {'type': 'string',
                                           'maxLength': 500000,
                                           'description': 'Complete privileged Blender Python script to stage for '
                                                          'approval'}},
                   'additionalProperties': False},
  'contract': {'description': 'Refuse privileged generated Python and direct clients to bounded structured tools',
               'mutates_scene': False,
               'has_side_effects': False,
               'requires_approval': False,
               'explicit_approval_required': False,
               'trust_window_auto_run_allowed': False,
               'approval_policy': 'Privileged generated scripts are disabled.',
               'recovery_hint': 'Use the corresponding bounded structured tool.',
               'permissions': ['scene:read'],
               'output_schema': {'type': 'object',
                                 'properties': {'ok': {'type': 'boolean'},
                                                'message': {'type': 'string'},
                                                'requires_user_approval': {'type': 'boolean'},
                                                'requires_explicit_one_time_approval': {'type': 'boolean'},
                                                'trust_window_auto_run_allowed': {'type': 'boolean'},
                                                'auto_run_attempted': {'type': 'boolean'},
                                                'auto_ran': {'type': 'boolean'},
                                                'auto_run_skipped_reason': {'type': 'string'},
                                                'approval_policy': {'type': 'string'},
                                                'approval_summary': {'type': 'string'},
                                                'declared_paths': {'type': 'array', 'items': {'type': 'string'}},
                                                'declared_urls': {'type': 'array', 'items': {'type': 'string'}},
                                                'destructive_actions': {'type': 'array', 'items': {'type': 'string'}},
                                                'analysis': {'type': 'object',
                                                             'properties': {'ok': {'type': 'boolean',
                                                                                   'description': 'Whether the tool '
                                                                                                  'completed '
                                                                                                  'successfully'},
                                                                            'message': {'type': 'string',
                                                                                        'description': 'Human-readable '
                                                                                                       'status or '
                                                                                                       'error '
                                                                                                       'message'}},
                                                             'additionalProperties': True}},
                                 'required': ['ok'],
                                 'additionalProperties': True}},
  'handler_key': 'draft_privileged_script',
  'order': 1820,
  'groups': (),
  'exposure': 'catalog',
  'owner': 'scripts_transactions'},
 {'name': 'commit_preview',
  'description': 'Commit the current live preview transaction.',
  'input_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
  'contract': {'description': 'Commit the current live preview transaction', 'mutates_scene': True},
  'handler_key': 'commit_preview',
  'order': 1830,
  'groups': ('preview_control',),
  'exposure': 'catalog',
  'owner': 'scripts_transactions'},
 {'name': 'revert_preview',
  'description': 'Revert the full live preview transaction, or remove only the latest isolated imported-asset step.',
  'input_schema': {'type': 'object',
                   'properties': {'scope': {'type': 'string',
                                            'enum': ['all', 'last_step'],
                                            'description': 'Defaults to all. last_step is accepted only for an isolated creation step such as an asset import.'}},
                   'additionalProperties': False},
  'contract': {'description': 'Revert the current live preview transaction', 'mutates_scene': True},
  'handler_key': 'revert_preview',
  'order': 1840,
  'groups': ('preview_control',),
  'exposure': 'catalog',
  'owner': 'scripts_transactions'},
 {'name': 'run_approved_script',
  'description': 'Compatibility endpoint that refuses removed per-script approval flows.',
  'input_schema': {'type': 'object',
                   'properties': {'approval_token': {'type': 'string',
                                                     'description': 'Optional one-time token copied from Blender after '
                                                                    'the user approves external execution. Omit this, '
                                                                    'or pass an empty string, only while a '
                                                                    'Blender-side external script trust grant is '
                                                                    'active.'}},
                   'additionalProperties': False},
  'contract': {'description': 'Refuse removed per-script approval flows',
               'mutates_scene': False,
               'has_side_effects': False,
               'requires_approval': False,
               'external_only': True,
               'supports_headless': False,
               'timeout_seconds': 120,
               'permissions': ['scene:read'],
               'input_schema': {'type': 'object',
                                'properties': {'approval_token': {'type': 'string',
                                                                  'description': 'Optional one-time token copied from '
                                                                                 'Blender after the user approves '
                                                                                 'external execution. Omit this, or '
                                                                                 'pass an empty string, only while a '
                                                                                 'Blender-side external script trust '
                                                                                 'grant is active.'}},
                                'additionalProperties': False},
               'output_schema': {'type': 'object',
                                 'properties': {'ok': {'type': 'boolean'},
                                                'message': {'type': 'string'},
                                                'stdout': {'type': 'string'},
                                                'log_datablock': {'type': 'string'},
                                                'checkpoint': {'type': 'object',
                                                               'properties': {'ok': {'type': 'boolean',
                                                                                     'description': 'Whether the tool '
                                                                                                    'completed '
                                                                                                    'successfully'},
                                                                              'message': {'type': 'string',
                                                                                          'description': 'Human-readable '
                                                                                                         'status or '
                                                                                                         'error '
                                                                                                         'message'}},
                                                               'additionalProperties': True}},
                                 'required': ['ok'],
                                 'additionalProperties': True}},
  'handler_key': 'run_approved_script',
  'order': 1850,
  'groups': (),
  'exposure': 'internal',
  'owner': 'scripts_transactions'}])


def register(registry):
    registry.register_many(SPECS)


def register_handlers(handler_registry):
    from ...tool_handlers import scripts_transactions

    scripts_transactions.register(handler_registry, SPECS)
