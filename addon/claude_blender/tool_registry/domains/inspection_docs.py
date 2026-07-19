"""Canonical tool specifications for the inspection docs domain."""

from __future__ import annotations

from ..registry import ToolSpec


SPECS = tuple(ToolSpec(**payload) for payload in [{'name': 'inspect_scene',
  'description': 'Inspect the current Blender scene and selected objects. Use before acting if context may be stale.',
  'input_schema': {'type': 'object',
                   'properties': {'include_visual': {'type': 'boolean',
                                                     'description': 'Whether viewport image context was requested'}},
                   'additionalProperties': False},
  'contract': {'description': 'Return a compact context bundle for the active Blender scene', 'mutates_scene': False},
  'handler_key': 'inspect_scene',
  'order': 0,
  'groups': (),
  'exposure': 'catalog',
  'owner': 'inspection_docs'},
 {'name': 'get_object_details',
  'description': 'Fetch deeper read-only details for named objects, selected objects, or the active object.',
  'input_schema': {'type': 'object',
                   'properties': {'object_names': {'type': 'array',
                                                   'items': {'type': 'string'},
                                                   'description': 'Optional object names to inspect'},
                                  'selected_only': {'type': 'boolean',
                                                    'description': 'Inspect current selected objects when object_names '
                                                                   'is empty'},
                                  'max_objects': {'type': 'integer', 'description': 'Maximum objects to return'}},
                   'additionalProperties': False},
  'contract': {'description': 'Return deeper details for a named Blender object', 'mutates_scene': False},
  'handler_key': 'get_object_details',
  'order': 200,
  'groups': (),
  'exposure': 'catalog',
  'owner': 'inspection_docs'},
 {'name': 'list_scene_objects',
  'description': 'List objects in the current scene with names, types, selection state, visibility, collections, and '
                 'locations.',
  'input_schema': {'type': 'object',
                   'properties': {'type_filter': {'type': 'string',
                                                  'description': 'Optional Blender object type such as MESH, CAMERA, '
                                                                 'LIGHT, EMPTY'},
                                  'max_objects': {'type': 'integer', 'description': 'Maximum objects to return'}},
                   'additionalProperties': False},
  'contract': {'description': 'Return object names, types, selection, visibility, collections, and locations',
               'mutates_scene': False},
  'handler_key': 'list_scene_objects',
  'order': 210,
  'groups': (),
  'exposure': 'compact_direct',
  'owner': 'inspection_docs'},
 {'name': 'get_collection_layer_details',
  'description': 'Fetch read-only collection tree, collection membership, visibility flags, and view-layer pass '
                 'summaries.',
  'input_schema': {'type': 'object', 'properties': {'max_depth': {'type': 'integer'}}, 'additionalProperties': False},
  'contract': {'description': 'Return collection tree, membership, visibility, and view-layer summaries',
               'mutates_scene': False},
  'handler_key': 'get_collection_layer_details',
  'order': 530,
  'groups': ('deep_inspect',),
  'exposure': 'catalog',
  'owner': 'inspection_docs'},
 {'name': 'search_blender_docs',
  'description': 'Search cached/official Blender docs. Use before unfamiliar or version-sensitive APIs.',
  'input_schema': {'type': 'object',
                   'properties': {'query': {'type': 'string'}},
                   'required': ['query'],
                   'additionalProperties': False},
  'contract': {'description': 'Search local cached official Blender docs before online docs', 'mutates_scene': False},
  'handler_key': 'search_blender_docs',
  'order': 1620,
  'groups': (),
  'exposure': 'catalog',
  'owner': 'inspection_docs'}])


def register(registry):
    registry.register_many(SPECS)


def register_handlers(handler_registry):
    from ...tool_handlers import inspection_docs

    inspection_docs.register(handler_registry, SPECS)
