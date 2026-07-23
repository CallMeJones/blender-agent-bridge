"""Blender-only handlers for the project_workspace domain."""

from __future__ import annotations

from .. import autosave, lab_parity, project_files
from ..handler_runtime import _bounded_int


def get_blend_file_diagnostics(context, args):
    return lab_parity.get_blend_file_diagnostics(
        context,
        max_items=_bounded_int(args.get("max_items"), 50, minimum=1, maximum=200),
    )


def save_blend_file(context, args):
    return project_files.save_blend_file(
        context,
        filepath=str(args.get("filepath") or ""),
        copy=bool(args.get("copy", False)),
        overwrite=bool(args.get("overwrite", False)),
        create_dirs=bool(args.get("create_dirs", True)),
        user_confirmed_path=bool(args.get("user_confirmed_path", False)),
    )


def open_blend_file(context, args):
    return project_files.open_blend_file(
        context,
        filepath=str(args.get("filepath") or ""),
        confirm_discard_current=bool(args.get("confirm_discard_current", False)),
        create_checkpoint=bool(args.get("create_checkpoint", True)),
        require_checkpoint=bool(args.get("require_checkpoint", True)),
        checkpoint_dir=str(args.get("checkpoint_dir") or ""),
        load_ui=bool(args.get("load_ui", False)),
        user_confirmed_path=bool(args.get("user_confirmed_path", False)),
    )


def create_new_blender_project(context, args):
    standard_dirs = args.get("standard_dirs")
    return project_files.create_new_blender_project(
        context,
        project_dir=str(args.get("project_dir") or ""),
        project_name=str(args.get("project_name") or ""),
        filepath=str(args.get("filepath") or ""),
        template=str(args.get("template") or "default"),
        create_standard_dirs=bool(args.get("create_standard_dirs", True)),
        standard_dirs=standard_dirs if isinstance(standard_dirs, list) else None,
        overwrite=bool(args.get("overwrite", False)),
        create_dirs=bool(args.get("create_dirs", True)),
        confirm_discard_current=bool(args.get("confirm_discard_current", False)),
        create_checkpoint=bool(args.get("create_checkpoint", True)),
        require_checkpoint=bool(args.get("require_checkpoint", True)),
        checkpoint_dir=str(args.get("checkpoint_dir") or ""),
        user_confirmed_path=bool(args.get("user_confirmed_path", False)),
    )


def autosave_current_blend_file(context, args):
    return autosave.autosave_current_blend_file(
        context,
        force=bool(args.get("force", False)),
        reason=str(args.get("reason") or "manual"),
        respect_enabled=bool(args.get("respect_enabled", False)),
    )


def list_project_files(context, args):
    return project_files.list_project_files(
        relative_path=str(args.get("relative_path") or ""),
        recursive=bool(args.get("recursive", False)),
        max_entries=_bounded_int(args.get("max_entries"), 200, minimum=1, maximum=1000),
    )


def read_project_file(context, args):
    return project_files.read_project_file(
        relative_path=str(args.get("relative_path") or ""),
        encoding=str(args.get("encoding") or "utf-8"),
        max_bytes=_bounded_int(args.get("max_bytes"), 1_048_576, minimum=1, maximum=project_files.MAX_PROJECT_FILE_BYTES),
    )


def write_project_file(context, args):
    return project_files.write_project_file(
        relative_path=str(args.get("relative_path") or ""),
        content=args.get("content") or "",
        encoding=str(args.get("encoding") or "utf-8"),
        overwrite=bool(args.get("overwrite", False)),
        create_dirs=bool(args.get("create_dirs", True)),
    )


def get_workspace_layout(context, args):
    return lab_parity.get_workspace_layout(
        context,
        max_workspaces=_bounded_int(args.get("max_workspaces"), 20, minimum=1, maximum=100),
        max_areas=_bounded_int(args.get("max_areas"), 80, minimum=1, maximum=300),
    )


def jump_to_workspace(context, args):
    return lab_parity.jump_to_workspace(
        context,
        workspace_name=str(args.get("workspace_name") or args.get("name") or ""),
    )


def set_viewport_view(context, args):
    return lab_parity.set_viewport_view(
        context,
        view=str(args.get("view") or "front"),
        frame_object_name=str(args.get("frame_object_name") or args.get("object_name") or ""),
        use_orthographic=bool(args.get("use_orthographic", True)),
    )


def focus_object_in_viewport(context, args):
    return lab_parity.focus_object_in_viewport(
        context,
        object_name=str(args.get("object_name") or ""),
        select=bool(args.get("select", True)),
    )


def register(handler_registry, specs):
    for spec in specs:
        try:
            handler = globals()[spec.handler_key]
        except KeyError as exc:
            raise KeyError(f"Missing handler {spec.handler_key} for {spec.name}") from exc
        handler_registry.register(spec.name, handler)
