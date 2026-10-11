"""Reload actual implementation bodies while preserving only declared session state."""
from pathlib import Path
import importlib
import sys
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))
import claude_blender
from claude_blender import external_assets, generation_clients, response_controls, session_credentials

claude_blender.register()
try:
    credential_name = session_credentials.TRIPO_API_KEY
    session_credentials.set_session_credential(credential_name, "reload-fixture")
    sentinel = lambda *_args, **_kwargs: "stale implementation"
    external_assets.search_poly_haven_assets = sentinel
    generation_clients.MeshyClient = sentinel
    response_controls.apply_response_controls = sentinel
    old_queue = sys.modules["claude_blender.bridge_server"]._requests
    queued = old_queue.submit(lambda: (_ for _ in ()).throw(AssertionError("stale work executed")), 30)
    claude_blender.unregister()
    importlib.reload(claude_blender)
    claude_blender.register()
    assert external_assets.search_poly_haven_assets is not sentinel
    assert generation_clients.MeshyClient is not sentinel
    assert response_controls.apply_response_controls is not sentinel
    assert session_credentials.session_credential(credential_name) == "reload-fixture"
    assert old_queue.status(queued.operation_id)["state"] == "cancelled"
    old_queue.pump()
    from claude_blender import script_runner
    assert not script_runner.external_script_trust_active(bpy.context)
    print("smoke_reload_lifecycle: ok")
finally:
    session_credentials.clear_session_credentials()
    claude_blender.unregister()
