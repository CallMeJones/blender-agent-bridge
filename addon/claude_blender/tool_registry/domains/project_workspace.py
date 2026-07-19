"""Canonical tool specifications for the project workspace domain."""

from __future__ import annotations

from ..registry import ToolSpec


SPECS = tuple(ToolSpec(**payload) for payload in [{'name': 'get_blend_file_diagnostics',
  'description': 'Inspect blend-file health: saved path, dirty state, backups, missing external files, linked '
                 'libraries, and data-block usage summaries.',
  'input_schema': {'type': 'object',
                   'properties': {'max_items': {'type': 'integer',
                                                'description': 'Maximum external file/library entries to return.'}},
                   'additionalProperties': False},
  'contract': {'description': 'Return blend-file diagnostics for save path, dirty state, backups, missing external '
                              'files, linked libraries, and data-block usage summaries',
               'mutates_scene': False,
               'input_schema': {'type': 'object',
                                'properties': {'max_items': {'type': 'integer',
                                                             'description': 'Maximum external file/library entries to '
                                                                            'return'}},
                                'additionalProperties': False}},
  'handler_key': 'get_blend_file_diagnostics',
  'order': 40,
  'groups': ('project_files', 'deep_inspect'),
  'exposure': 'catalog',
  'owner': 'project_workspace'},
 {'name': 'save_blend_file',
  'description': 'Save the current .blend, save-as to a human-confirmed .blend path, or save a copy without changing '
                 'the active file. Refuses accidental overwrite unless overwrite=true.',
  'input_schema': {'type': 'object',
                   'properties': {'filepath': {'type': 'string',
                                               'description': 'Optional .blend path. Omit to save the active file.'},
                                  'copy': {'type': 'boolean',
                                           'description': 'Save a copy without changing the active filepath. Requires '
                                                          'filepath.'},
                                  'overwrite': {'type': 'boolean',
                                                'description': 'Allow replacing an existing target .blend file.'},
                                  'create_dirs': {'type': 'boolean',
                                                  'description': 'Create the target directory if missing. Defaults to '
                                                                 'true.'},
                                  'user_confirmed_path': {'type': 'boolean',
                                                          'description': 'Required true for save-as/save-copy. Set '
                                                                         'only after the user provides the filepath.'}},
                   'additionalProperties': False},
  'contract': {'description': 'Save the current .blend file, save-as to a new .blend path, or save a copy without '
                              'changing the active file',
               'mutates_scene': False,
               'has_side_effects': True,
               'human_in_loop_required': True,
               'requires_user_path': True,
               'path_policy': 'Saving the active bound .blend may omit filepath. Any save-as or save-copy filepath '
                              'must come from the user and set user_confirmed_path=true.',
               'permissions': ['scene:read', 'files:write'],
               'long_running': True,
               'duration_hint': 'Usually seconds, but large .blend files or network paths can take longer. The current '
                                'file path changes only when copy=false and filepath targets a different .blend.',
               'timeout_recovery': {'recoverable': True,
                                    'poll_after_seconds': 5,
                                    'status_tool': 'blender_bridge_status',
                                    'resource_tool': 'get_blend_file_diagnostics',
                                    'message': 'If saving times out, wait, call blender_bridge_status, then check '
                                               'get_blend_file_diagnostics and the target file before retrying.'},
               'timeout_seconds': 180,
               'input_schema': {'type': 'object',
                                'properties': {'filepath': {'type': 'string',
                                                            'description': 'Optional .blend path. Omit to save the '
                                                                           'active file.'},
                                               'copy': {'type': 'boolean',
                                                        'description': 'Save a copy without changing the active blend '
                                                                       'filepath. Requires filepath.'},
                                               'overwrite': {'type': 'boolean',
                                                             'description': 'Allow replacing an existing target .blend '
                                                                            'file.'},
                                               'create_dirs': {'type': 'boolean',
                                                               'description': 'Create the target directory if missing. '
                                                                              'Defaults to true.'},
                                               'user_confirmed_path': {'type': 'boolean',
                                                                       'description': 'Required true when filepath is '
                                                                                      'supplied for save-as/save-copy. '
                                                                                      'Set only when the path came '
                                                                                      'from the user or a file '
                                                                                      'picker.'}},
                                'additionalProperties': False}},
  'handler_key': 'save_blend_file',
  'order': 50,
  'groups': ('project_files',),
  'exposure': 'catalog',
  'owner': 'project_workspace'},
 {'name': 'open_blend_file',
  'description': 'Open an existing user-confirmed .blend file. This replaces the active Blender session, so '
                 'confirm_discard_current and user_confirmed_path must be true; creates a checkpoint first by default.',
  'input_schema': {'type': 'object',
                   'properties': {'filepath': {'type': 'string', 'description': 'Existing .blend file path to open.'},
                                  'confirm_discard_current': {'type': 'boolean',
                                                              'description': 'Required true; opening replaces the '
                                                                             'active session.'},
                                  'create_checkpoint': {'type': 'boolean',
                                                        'description': 'Save a checkpoint before opening. Defaults to '
                                                                       'true.'},
                                  'require_checkpoint': {'type': 'boolean',
                                                         'description': 'Abort if checkpoint creation fails. Defaults '
                                                                        'to true.'},
                                  'checkpoint_dir': {'type': 'string'},
                                  'load_ui': {'type': 'boolean',
                                              'description': 'Load UI layout from the opened file when supported. '
                                                             'Defaults to false.'},
                                  'user_confirmed_path': {'type': 'boolean',
                                                          'description': 'Required true. Set only after the user '
                                                                         'provides the filepath.'}},
                   'required': ['filepath', 'confirm_discard_current', 'user_confirmed_path'],
                   'additionalProperties': False},
  'contract': {'description': 'Open an existing .blend file after explicit discard confirmation, creating a checkpoint '
                              'first by default',
               'mutates_scene': True,
               'has_side_effects': True,
               'destructive': True,
               'risk_level': 'destructive',
               'human_in_loop_required': True,
               'requires_user_path': True,
               'path_policy': 'The filepath must come from the user or a file picker, and user_confirmed_path plus '
                              'confirm_discard_current must both be true.',
               'permissions': ['scene:read', 'scene:mutate', 'files:read', 'files:write'],
               'long_running': True,
               'duration_hint': 'Usually seconds, but large .blend files can take longer. The active Blender session '
                                'is replaced.',
               'timeout_recovery': {'recoverable': True,
                                    'poll_after_seconds': 5,
                                    'status_tool': 'blender_bridge_status',
                                    'resource_tool': 'get_blend_file_diagnostics',
                                    'message': 'If opening times out, wait, call blender_bridge_status, then check '
                                               'get_blend_file_diagnostics before opening another file.'},
               'timeout_seconds': 300,
               'input_schema': {'type': 'object',
                                'properties': {'filepath': {'type': 'string',
                                                            'description': 'Existing .blend file path to open.'},
                                               'confirm_discard_current': {'type': 'boolean',
                                                                           'description': 'Required true; opening '
                                                                                          'replaces the active '
                                                                                          'session.'},
                                               'create_checkpoint': {'type': 'boolean',
                                                                     'description': 'Save a checkpoint of the current '
                                                                                    'file before opening. Defaults to '
                                                                                    'true.'},
                                               'require_checkpoint': {'type': 'boolean',
                                                                      'description': 'Abort if checkpoint creation '
                                                                                     'fails. Defaults to true.'},
                                               'checkpoint_dir': {'type': 'string',
                                                                  'description': 'Optional checkpoint output '
                                                                                 'directory.'},
                                               'load_ui': {'type': 'boolean',
                                                           'description': 'Load UI layout from the opened .blend when '
                                                                          'supported. Defaults to false.'},
                                               'user_confirmed_path': {'type': 'boolean',
                                                                       'description': 'Required true. Set only when '
                                                                                      'filepath came from the user or '
                                                                                      'a file picker.'}},
                                'required': ['filepath', 'confirm_discard_current', 'user_confirmed_path'],
                                'additionalProperties': False}},
  'handler_key': 'open_blend_file',
  'order': 60,
  'groups': ('project_files',),
  'exposure': 'catalog',
  'owner': 'project_workspace'},
 {'name': 'create_new_blender_project',
  'description': 'Create a new Blender project folder and .blend file at a user-confirmed path. This replaces the '
                 'active Blender session, so confirm_discard_current and user_confirmed_path must be true; creates a '
                 'checkpoint first by default.',
  'input_schema': {'type': 'object',
                   'properties': {'project_dir': {'type': 'string',
                                                  'description': 'Parent or final project directory. Required unless '
                                                                 'filepath is supplied.'},
                                  'project_name': {'type': 'string',
                                                   'description': 'Project name used for folder/filename when filepath '
                                                                  'is omitted.'},
                                  'filepath': {'type': 'string',
                                               'description': 'Optional explicit target .blend path.'},
                                  'template': {'type': 'string', 'enum': ['default', 'empty', 'factory_startup']},
                                  'create_standard_dirs': {'type': 'boolean',
                                                           'description': 'Create assets, refs, renders, and exports '
                                                                          'folders. Defaults to true.'},
                                  'standard_dirs': {'type': 'array', 'items': {'type': 'string'}},
                                  'overwrite': {'type': 'boolean',
                                                'description': 'Allow replacing an existing target .blend file.'},
                                  'create_dirs': {'type': 'boolean',
                                                  'description': 'Create the project directory if missing. Defaults to '
                                                                 'true.'},
                                  'confirm_discard_current': {'type': 'boolean',
                                                              'description': 'Required true; new project replaces the '
                                                                             'active session.'},
                                  'create_checkpoint': {'type': 'boolean',
                                                        'description': 'Save a checkpoint before creating the new '
                                                                       'project. Defaults to true.'},
                                  'require_checkpoint': {'type': 'boolean',
                                                         'description': 'Abort if checkpoint creation fails. Defaults '
                                                                        'to true.'},
                                  'checkpoint_dir': {'type': 'string'},
                                  'user_confirmed_path': {'type': 'boolean',
                                                          'description': 'Required true. Set only after the user '
                                                                         'provides the project_dir or filepath.'}},
                   'required': ['confirm_discard_current', 'user_confirmed_path'],
                   'additionalProperties': False},
  'contract': {'description': 'Create a new Blender project folder and .blend file after explicit discard '
                              'confirmation, with optional standard subfolders',
               'mutates_scene': True,
               'has_side_effects': True,
               'destructive': True,
               'risk_level': 'destructive',
               'human_in_loop_required': True,
               'requires_user_path': True,
               'path_policy': 'The project_dir or filepath must come from the user or a file picker, and '
                              'user_confirmed_path plus confirm_discard_current must both be true.',
               'permissions': ['scene:read', 'scene:mutate', 'files:write'],
               'long_running': True,
               'duration_hint': 'Usually seconds. The active Blender session is replaced by a fresh startup scene and '
                                'immediately saved.',
               'timeout_recovery': {'recoverable': True,
                                    'poll_after_seconds': 5,
                                    'status_tool': 'blender_bridge_status',
                                    'resource_tool': 'get_blend_file_diagnostics',
                                    'message': 'If new-project creation times out, wait, call blender_bridge_status, '
                                               'then check get_blend_file_diagnostics and the target project folder '
                                               'before retrying.'},
               'timeout_seconds': 300,
               'input_schema': {'type': 'object',
                                'properties': {'project_dir': {'type': 'string',
                                                               'description': 'Parent or final project directory. '
                                                                              'Required unless filepath is supplied.'},
                                               'project_name': {'type': 'string',
                                                                'description': 'Project name used for folder/filename '
                                                                               'when filepath is omitted.'},
                                               'filepath': {'type': 'string',
                                                            'description': 'Optional explicit target .blend path.'},
                                               'template': {'type': 'string',
                                                            'enum': ['default', 'empty', 'factory_startup'],
                                                            'description': 'Startup scene template. Defaults to '
                                                                           'default.'},
                                               'create_standard_dirs': {'type': 'boolean',
                                                                        'description': 'Create assets, refs, renders, '
                                                                                       'and exports folders. Defaults '
                                                                                       'to true.'},
                                               'standard_dirs': {'type': 'array',
                                                                 'items': {'type': 'string'},
                                                                 'description': 'Optional custom project subfolders.'},
                                               'overwrite': {'type': 'boolean',
                                                             'description': 'Allow replacing an existing target .blend '
                                                                            'file.'},
                                               'create_dirs': {'type': 'boolean',
                                                               'description': 'Create the project directory if '
                                                                              'missing. Defaults to true.'},
                                               'confirm_discard_current': {'type': 'boolean',
                                                                           'description': 'Required true; new project '
                                                                                          'replaces the active '
                                                                                          'session.'},
                                               'create_checkpoint': {'type': 'boolean',
                                                                     'description': 'Save a checkpoint of the current '
                                                                                    'file before creating the new '
                                                                                    'project. Defaults to true.'},
                                               'require_checkpoint': {'type': 'boolean',
                                                                      'description': 'Abort if checkpoint creation '
                                                                                     'fails. Defaults to true.'},
                                               'checkpoint_dir': {'type': 'string',
                                                                  'description': 'Optional checkpoint output '
                                                                                 'directory.'},
                                               'user_confirmed_path': {'type': 'boolean',
                                                                       'description': 'Required true. Set only when '
                                                                                      'project_dir or filepath came '
                                                                                      'from the user or a file '
                                                                                      'picker.'}},
                                'required': ['confirm_discard_current', 'user_confirmed_path'],
                                'additionalProperties': False}},
  'handler_key': 'create_new_blender_project',
  'order': 70,
  'groups': ('project_files',),
  'exposure': 'catalog',
  'owner': 'project_workspace'},
 {'name': 'autosave_current_blend_file',
  'description': 'Autosave the current open .blend in place. It has no filepath argument and refuses unsaved scenes.',
  'input_schema': {'type': 'object',
                   'properties': {'force': {'type': 'boolean',
                                            'description': 'Save even when the file is not dirty, the interval has not '
                                                           'elapsed, or live preview changes are pending. Defaults to '
                                                           'false.'},
                                  'reason': {'type': 'string', 'description': 'Short reason for the autosave.'},
                                  'respect_enabled': {'type': 'boolean',
                                                      'description': 'Skip if the autosave preference is disabled. '
                                                                     'Defaults to false.'}},
                   'additionalProperties': False},
  'contract': {'description': 'Autosave the current open .blend in place after Blender is already bound to a '
                              'user-confirmed path',
               'mutates_scene': False,
               'has_side_effects': True,
               'permissions': ['scene:read', 'files:write'],
               'long_running': True,
               'duration_hint': 'Usually seconds. Autosave only saves when the current Blender session is already '
                                'bound to a saved .blend path.',
               'path_policy': 'No filepath is accepted. Autosave saves the active .blend in place and refuses unsaved '
                              'scenes until the user provides a path through save/open/new.',
               'timeout_recovery': {'recoverable': True,
                                    'poll_after_seconds': 5,
                                    'status_tool': 'blender_bridge_status',
                                    'resource_tool': 'get_blend_file_diagnostics',
                                    'message': 'If autosave times out, wait, call blender_bridge_status, then check '
                                               'get_blend_file_diagnostics and the active .blend file before '
                                               'retrying.'},
               'timeout_seconds': 180,
               'input_schema': {'type': 'object',
                                'properties': {'force': {'type': 'boolean',
                                                         'description': 'Save even if the interval has not elapsed, '
                                                                        'the file is not dirty, or live preview '
                                                                        'changes are pending. Defaults to false.'},
                                               'reason': {'type': 'string',
                                                          'description': 'Short reason stored in the result.'},
                                               'respect_enabled': {'type': 'boolean',
                                                                   'description': 'When true, skip if the autosave '
                                                                                  'preference is disabled. Defaults to '
                                                                                  'false for manual calls.'}},
                                'additionalProperties': False}},
  'handler_key': 'autosave_current_blend_file',
  'order': 80,
  'groups': ('project_files',),
  'exposure': 'catalog',
  'owner': 'project_workspace'},
 {'name': 'get_workspace_layout',
  'description': 'Return JSON for Blender workspaces, windows, screens, and UI areas. Use before workspace/view '
                 'navigation or UI diagnostics.',
  'input_schema': {'type': 'object',
                   'properties': {'max_workspaces': {'type': 'integer'}, 'max_areas': {'type': 'integer'}},
                   'additionalProperties': False},
  'contract': {'description': 'Return workspace, window, screen, and area layout JSON for the current Blender UI',
               'mutates_scene': False,
               'input_schema': {'type': 'object',
                                'properties': {'max_workspaces': {'type': 'integer'}, 'max_areas': {'type': 'integer'}},
                                'additionalProperties': False}},
  'handler_key': 'get_workspace_layout',
  'order': 90,
  'groups': ('selection', 'deep_inspect'),
  'exposure': 'catalog',
  'owner': 'project_workspace'},
 {'name': 'jump_to_workspace',
  'description': 'Switch the active Blender window to a named workspace/tab. Requires an interactive Blender UI and '
                 'fails soft in background mode.',
  'input_schema': {'type': 'object',
                   'properties': {'workspace_name': {'type': 'string'}},
                   'required': ['workspace_name'],
                   'additionalProperties': False},
  'contract': {'description': 'Switch the active interactive Blender window to a named workspace',
               'mutates_scene': False,
               'has_side_effects': True,
               'permissions': ['ui:navigate'],
               'supports_headless': False,
               'input_schema': {'type': 'object',
                                'properties': {'workspace_name': {'type': 'string'}},
                                'required': ['workspace_name'],
                                'additionalProperties': False}},
  'handler_key': 'jump_to_workspace',
  'order': 110,
  'groups': ('selection',),
  'exposure': 'catalog',
  'owner': 'project_workspace'},
 {'name': 'set_viewport_view',
  'description': 'Set the first 3D viewport to an axis, camera, or user view and optionally frame an object. Requires '
                 'an interactive Blender UI and fails soft in background mode.',
  'input_schema': {'type': 'object',
                   'properties': {'view': {'type': 'string',
                                           'enum': ['front',
                                                    'back',
                                                    'left',
                                                    'right',
                                                    'top',
                                                    'bottom',
                                                    'camera',
                                                    'user']},
                                  'frame_object_name': {'type': 'string',
                                                        'description': 'Optional object to frame after changing view.'},
                                  'use_orthographic': {'type': 'boolean',
                                                       'description': 'Use orthographic axis views when possible. '
                                                                      'Defaults to true.'}},
                   'additionalProperties': False},
  'contract': {'description': 'Set the first interactive 3D viewport to an axis, camera, or user view and optionally '
                              'frame an object without changing scene data',
               'mutates_scene': False,
               'has_side_effects': True,
               'permissions': ['ui:navigate'],
               'supports_headless': False,
               'input_schema': {'type': 'object',
                                'properties': {'view': {'type': 'string',
                                                        'enum': ['front',
                                                                 'back',
                                                                 'left',
                                                                 'right',
                                                                 'top',
                                                                 'bottom',
                                                                 'camera',
                                                                 'user']},
                                               'frame_object_name': {'type': 'string',
                                                                     'description': 'Optional object to frame after '
                                                                                    'changing view.'},
                                               'use_orthographic': {'type': 'boolean',
                                                                    'description': 'Use orthographic axis views when '
                                                                                   'possible. Defaults to true.'}},
                                'additionalProperties': False}},
  'handler_key': 'set_viewport_view',
  'order': 120,
  'groups': ('selection',),
  'exposure': 'catalog',
  'owner': 'project_workspace'},
 {'name': 'focus_object_in_viewport',
  'description': 'Frame a named object in the first 3D viewport and optionally select it. Requires an interactive '
                 'Blender UI and fails soft in background mode.',
  'input_schema': {'type': 'object',
                   'properties': {'object_name': {'type': 'string'},
                                  'select': {'type': 'boolean',
                                             'description': 'Select and activate the object before focusing. Defaults '
                                                            'to true.'}},
                   'required': ['object_name'],
                   'additionalProperties': False},
  'contract': {'description': 'Frame a named object in the first 3D viewport and optionally select it',
               'mutates_scene': True,
               'has_side_effects': True,
               'permissions': ['ui:navigate', 'scene:mutate'],
               'supports_headless': False,
               'input_schema': {'type': 'object',
                                'properties': {'object_name': {'type': 'string'},
                                               'select': {'type': 'boolean',
                                                          'description': 'Select and activate the object before '
                                                                         'focusing. Defaults to true.'}},
                                'required': ['object_name'],
                                'additionalProperties': False}},
  'handler_key': 'focus_object_in_viewport',
  'order': 130,
  'groups': ('selection',),
  'exposure': 'catalog',
  'owner': 'project_workspace'}])


def register(registry):
    registry.register_many(SPECS)


def register_handlers(handler_registry):
    from ...tool_handlers import project_workspace

    project_workspace.register(handler_registry, SPECS)
