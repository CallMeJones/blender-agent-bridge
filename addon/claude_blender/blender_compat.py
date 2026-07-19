"""Version and capability policy shared by Blender and pure-Python diagnostics."""

from __future__ import annotations

import re


MINIMUM_VERSION = (4, 2, 0)
MINIMUM_VERSION_TEXT = "4.2.0"
TESTED_RELEASE_LINES = ((4, 2), (4, 5), (5, 1))


def version_tuple(value):
    """Return a comparable three-part tuple without importing ``bpy``."""

    if isinstance(value, (tuple, list)):
        parts = list(value[:3])
    else:
        parts = [int(part) for part in re.findall(r"\d+", str(value or ""))[:3]]
    parts.extend([0] * (3 - len(parts)))
    return tuple(int(part) for part in parts[:3])


def compatibility_report(value):
    current = version_tuple(value)
    release_line = current[:2]
    supported = current >= MINIMUM_VERSION
    tested = release_line in TESTED_RELEASE_LINES
    if not supported:
        status = "unsupported"
        message = f"Blender {current[0]}.{current[1]}.{current[2]} is below the supported minimum {MINIMUM_VERSION_TEXT}."
    elif tested:
        status = "tested"
        message = f"Blender {current[0]}.{current[1]} is in the continuously tested compatibility matrix."
    else:
        status = "compatible_untested"
        message = (
            f"Blender {current[0]}.{current[1]} is allowed but not in the current test matrix; "
            "capability checks are used and unsupported features should return explicit warnings."
        )
    return {
        "version": ".".join(str(part) for part in current),
        "minimum_version": MINIMUM_VERSION_TEXT,
        "supported": supported,
        "tested": tested,
        "status": status,
        "message": message,
        "tested_release_lines": [f"{major}.{minor}" for major, minor in TESTED_RELEASE_LINES],
    }


def node_tree(owner):
    """Return an enabled node tree across legacy and node-only Blender APIs."""

    if owner is None:
        return None
    compositor_tree = getattr(owner, "compositing_node_group", None)
    if compositor_tree is not None:
        return compositor_tree
    return getattr(owner, "node_tree", None)


def _has_property(owner, name):
    """Check RNA capabilities without evaluating deprecated property getters."""

    rna = getattr(owner, "bl_rna", None)
    properties = getattr(rna, "properties", None)
    if properties is not None:
        try:
            return properties.get(name) is not None
        except (AttributeError, TypeError):
            pass
    return hasattr(owner, name)


def _new_compositor_tree(owner):
    """Create Blender's node-group based compositor tree when that API exists."""

    try:
        import bpy
    except ImportError:
        return None
    tree = bpy.data.node_groups.new(
        name=f"{getattr(owner, 'name', 'Scene')} Compositor",
        type="CompositorNodeTree",
    )
    owner.compositing_node_group = tree
    return tree


def ensure_node_tree(owner):
    """Enable legacy node owners only when they do not already expose a tree."""

    if owner is None:
        return None
    tree = node_tree(owner)
    if tree is not None:
        return tree
    if _has_property(owner, "compositing_node_group"):
        return _new_compositor_tree(owner)
    if _has_property(owner, "use_nodes"):
        owner.use_nodes = True
        tree = getattr(owner, "node_tree", None)
    return tree


def node_tree_enabled(owner):
    return node_tree(owner) is not None


def restore_node_tree_enabled(owner, enabled):
    """Restore legacy enable state; node-only future APIs remain enabled."""

    if owner is None:
        return
    desired = bool(enabled)
    tree = node_tree(owner)
    if _has_property(owner, "compositing_node_group"):
        if desired and tree is None:
            ensure_node_tree(owner)
        elif not desired and tree is not None:
            owner.compositing_node_group = None
            try:
                import bpy
            except ImportError:
                return
            if getattr(tree, "users", 1) == 0:
                bpy.data.node_groups.remove(tree)
        return
    if bool(tree) == desired:
        return
    if _has_property(owner, "use_nodes"):
        owner.use_nodes = desired
    elif desired:
        ensure_node_tree(owner)
