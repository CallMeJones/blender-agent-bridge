"""Regression: a failed operation must not contaminate an earlier preview."""
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))
import claude_blender
from claude_blender import blender_compat, live_preview, tool_dispatcher, tool_executor


def call(name, args=None):
    return json.loads(tool_dispatcher.execute_tool(bpy.context, name, args or {}))


claude_blender.register()
try:
    cube = bpy.data.objects["Cube"]
    bpy.ops.object.select_all(action="DESELECT")
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    meshes = set(bpy.data.meshes.keys())
    for with_parent in (False, True):
        if with_parent:
            assert call("set_selected_location_delta", {"delta": [1, 0, 0]})["ok"]
        before = tuple(cube.location)
        parent = live_preview.current_transaction()
        redraw = live_preview.redraw
        def fail_once(*_args, **_kwargs):
            live_preview.redraw = redraw
            raise RuntimeError("injected after mutation")
        live_preview.redraw = fail_once
        try:
            failed = call("set_selected_location_delta", {"delta": [2, 0, 0]})
        finally:
            live_preview.redraw = redraw
        assert not failed["ok"], failed
        assert failed["auto_reverted_preview"], failed
        assert tuple(cube.location) == before, (before, tuple(cube.location))
        if with_parent:
            assert live_preview.current_transaction() is parent
            assert call("revert_preview")["ok"]
        assert tuple(cube.location) == (0, 0, 0)
        assert set(bpy.data.meshes.keys()) == meshes
    # Shader records include diffuse_color as well as their own kind. The
    # kind-specific codec must restore sockets, not stop at diffuse color.
    material = bpy.data.materials.new("Atomic shader fixture")
    tree = blender_compat.ensure_node_tree(material)
    principled = next(node for node in tree.nodes if node.type == "BSDF_PRINCIPLED")
    roughness = principled.inputs["Roughness"]
    original_roughness = roughness.default_value
    def shader_edit(_context, args):
        live_preview.record_shader_material(material)
        roughness.default_value = args["value"]
        if args.get("fail"):
            raise RuntimeError("after shader mutation")
        return {"ok": True}
    def shader_call(value, fail=False):
        return json.loads(tool_executor.execute_tool(bpy.context, "set_selected_location_delta",
                          {"value": value, "fail": fail}, handler=shader_edit))
    assert shader_call(0.2)["ok"]
    assert not shader_call(0.9, True)["ok"]
    assert abs(roughness.default_value - 0.2) < 1e-6
    assert call("revert_preview")["ok"]
    assert abs(roughness.default_value - original_roughness) < 1e-6
    bpy.data.materials.remove(material)
    print("smoke_preview_atomicity: ok")
finally:
    claude_blender.unregister()
