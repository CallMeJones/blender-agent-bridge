"""Blender-only handlers for the inspection_docs domain."""

from __future__ import annotations

from .. import context_bundle, docs_index, preferences, world_model
from ..handler_runtime import _idprops_summary, _mesh_data_layers
from .support import _bounded_int, _resolve_objects


def inspect_scene(context, args):
    bundle = context_bundle.build_context_bundle(
        context,
        include_visual=bool(args.get("include_visual", False)),
    )
    return context_bundle.public_bundle(bundle)


def list_scene_objects(context, args):
    type_filter = str(args.get("type_filter") or "").upper()
    max_objects = _bounded_int(args.get("max_objects"), 80, maximum=250)
    objects = []
    for obj in context.scene.objects:
        if type_filter and obj.type != type_filter:
            continue
        objects.append(
            {
                "name": obj.name,
                "type": obj.type,
                "selected": bool(obj.select_get()),
                "active": context.active_object == obj,
                "hidden_viewport": bool(obj.hide_viewport),
                "hidden_render": bool(obj.hide_render),
                "location": context_bundle._xyz(obj.location),
                "collection_names": [collection.name for collection in obj.users_collection],
            }
        )
        if len(objects) >= max_objects:
            break
    return {
        "ok": True,
        "objects": objects,
        "total_scene_objects": len(context.scene.objects),
        "truncated": len(objects) < len(context.scene.objects) and not type_filter,
    }


def get_object_details(context, args):
    objects, missing = _resolve_objects(context, args, default_to_scene=True)
    details = []
    for obj in objects:
        item = context_bundle._object_summary(obj)
        item.update(
            {
                "parent": obj.parent.name if obj.parent else None,
                "children": [child.name for child in list(obj.children)[:25]],
                "custom_properties": _idprops_summary(obj),
            }
        )
        if obj.type == "MESH" and obj.data:
            item["mesh_data_layers"] = _mesh_data_layers(obj.data)
            item["mesh_custom_properties"] = _idprops_summary(obj.data)
        details.append(item)
    return {
        "ok": True,
        "objects": details,
        "missing_object_names": missing,
        "note": "Raw mesh vertex/edge/polygon arrays are omitted; summaries and layer names are returned.",
    }


def get_collection_layer_details(context, args):
    return world_model.collection_layer_details(
        context,
        max_depth=_bounded_int(args.get("max_depth"), 4, maximum=8),
    )


def search_blender_docs(context, args):
    prefs = preferences.get_preferences(context)
    return docs_index.search_blender_docs(
        str(args.get("query") or ""),
        cache_dir=getattr(prefs, "docs_cache_dir", None),
        local_first=bool(getattr(prefs, "local_docs_first", True)),
    )


def register(handler_registry, specs):
    for spec in specs:
        try:
            handler = globals()[spec.handler_key]
        except KeyError as exc:
            raise KeyError(f"Missing handler {spec.handler_key} for {spec.name}") from exc
        handler_registry.register(spec.name, handler)
