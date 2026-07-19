"""Blender smoke tests for external asset import helpers without live network."""

from __future__ import annotations

import json
import hashlib
import http.server
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.parse
import zipfile

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import asset_jobs, blender_compat, external_assets, live_preview, tool_dispatcher  # noqa: E402

observed_timeouts = []
SUBPROCESS_MODEL_BYTES = b'{"asset":{"version":"2.0"},"scene":0,"scenes":[{"nodes":[]}]}'
SUBPROCESS_MODEL_MD5 = hashlib.md5(SUBPROCESS_MODEL_BYTES).hexdigest()


def _make_png(path):
    image = bpy.data.images.new("ExternalAssetSmokePixel", width=1, height=1, alpha=True)
    image.pixels = [0.9, 0.25, 0.1, 1.0]
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def _fake_fetch_json(url, *, timeout=15):
    path = urllib.parse.urlparse(url).path
    if path == "/files/studio_hdri":
        return {
            "hdri": {
                "1k": {
                    "png": {
                        "url": "https://cdn.example.invalid/studio_hdri_1k.png",
                        "md5": "",
                        "size": 1,
                    }
                }
            }
        }
    if path == "/files/oak_floor":
        return {
            "diffuse": {
                "2k": {
                    "png": {
                        "url": "https://cdn.example.invalid/oak_floor_diff_2k.png",
                        "md5": "",
                        "size": 1,
                    }
                }
            },
            "normal": {
                "2k": {
                    "png": {
                        "url": "https://cdn.example.invalid/oak_floor_nor_2k.png",
                        "md5": "",
                        "size": 1,
                    }
                }
            },
            "arm": {
                "2k": {
                    "png": {
                        "url": "https://cdn.example.invalid/oak_floor_arm_2k.png",
                        "md5": "",
                        "size": 1,
                    }
                }
            },
        }
    if path == "/files/model_one":
        return {
            "gltf": {
                "2k": {
                    "gltf": {
                        "url": "https://cdn.example.invalid/model_one.gltf",
                        "md5": "",
                        "size": 1,
                    }
                }
            }
        }
    if path == "/files/blend_only":
        return {
            "blend": {
                "2k": {
                    "blend": {
                        "url": "https://cdn.example.invalid/blend_only.blend",
                        "md5": "",
                        "size": 1,
                    }
                }
            }
        }
    raise AssertionError(f"Unexpected URL: {url}")


def _fake_fetch_json_with_headers(url, *, headers=None, timeout=15):
    observed_timeouts.append(("fetch_json_with_headers", timeout))
    path = urllib.parse.urlparse(url).path
    if path == "/v3/models/sketchfab_one/download":
        assert headers and headers.get("Authorization") == "Token smoke-token", headers
        return {"gltf": {"url": "https://download.example.invalid/sketchfab_one.zip", "expires": 300}}
    raise AssertionError(f"Unexpected authenticated URL: {url}")


def _fake_download_file(url, destination, *, expected_md5="", expected_size=None, headers=None, timeout=60, progress_callback=None):
    observed_timeouts.append(("download_file", timeout))
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    if progress_callback:
        progress_callback(
            {
                "phase": "download",
                "url": url,
                "path": destination,
                "bytes_downloaded": int(expected_size or 0),
                "expected_size": int(expected_size or 0),
            }
        )
    if str(destination).lower().endswith(".zip"):
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("scene.gltf", "{}")
    elif str(destination).lower().endswith((".png", ".jpg", ".jpeg")):
        _make_png(destination)
    else:
        with open(destination, "w", encoding="utf-8") as handle:
            handle.write("{}")
    return {
        "ok": True,
        "url": url,
        "path": destination,
        "cached": False,
        "size": os.path.getsize(destination),
        "md5": "",
        "sha256": "smoke-sha",
    }


def _fake_import_model_file(filepath):
    mesh = bpy.data.meshes.new("SmokeImportedMesh")
    obj = bpy.data.objects.new("SmokeImportedModel", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return {"ok": True}


def _start_poly_haven_fixture_server():
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, _format, *args):
            pass

        def _send_json(self, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_bytes(self, body, content_type):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urllib.parse.urlparse(self.path).path
            base_url = f"http://{self.server.server_address[0]}:{self.server.server_address[1]}"
            if path == "/files/subprocess_model":
                self._send_json(
                    {
                        "gltf": {
                            "1k": {
                                "gltf": {
                                    "url": f"{base_url}/downloads/subprocess_model.gltf",
                                    "md5": SUBPROCESS_MODEL_MD5,
                                    "size": len(SUBPROCESS_MODEL_BYTES),
                                }
                            }
                        }
                    }
                )
                return
            if path == "/downloads/subprocess_model.gltf":
                self._send_bytes(SUBPROCESS_MODEL_BYTES, "model/gltf+json")
                return
            self.send_response(404)
            self.end_headers()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, name="PolyHavenFixtureServer", daemon=True)
    thread.start()
    return server, thread, f"http://{server.server_address[0]}:{server.server_address[1]}"


def _execute(context, name, args):
    return json.loads(tool_dispatcher.execute_tool(context, name, args))


def _wait_asset_job(context, job_id, *, timeout=5.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = _execute(context, "get_external_asset_job_status", {"job_id": job_id})
        assert last["ok"] is True, last
        status = last["asset_job"]["status"]
        if status in {"completed", "failed", "cancelled", "unknown"}:
            return last
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for external asset job {job_id}: {last}")


def _run_import_queue_once():
    result = asset_jobs._process_import_queue()
    assert result in {None, 0.1}, result


def main():
    cache_dir = tempfile.mkdtemp(prefix="bab-import-assets-")
    original_asset_job_mode = os.environ.get(asset_jobs.ASSET_JOB_MODE_ENV)
    original_poly_haven_base_url = os.environ.get("BLENDER_AGENT_BRIDGE_POLY_HAVEN_BASE_URL")
    original_fetch_json = external_assets._fetch_json
    original_fetch_json_with_headers = external_assets._fetch_json_with_headers
    original_download_file = external_assets._download_file
    original_import_model_file = external_assets._import_model_file
    fixture_server = None
    fixture_thread = None
    os.environ[asset_jobs.ASSET_JOB_MODE_ENV] = "thread"
    external_assets._fetch_json = _fake_fetch_json
    external_assets._fetch_json_with_headers = _fake_fetch_json_with_headers
    external_assets._download_file = _fake_download_file
    external_assets._import_model_file = _fake_import_model_file
    try:
        online_worker_command = asset_jobs._asset_worker_command(
            "blender",
            "asset-worker.py",
        )
        assert online_worker_command == [
            "blender",
            "--background",
            "--factory-startup",
            "--online-mode",
            "--python",
            "asset-worker.py",
        ], online_worker_command
        claude_blender.register()
        bpy.ops.mesh.primitive_cube_add()
        cube = bpy.context.object
        cube.name = "TextureTarget"

        hdri = _execute(
            bpy.context,
            "import_poly_haven_asset",
            {"asset_id": "studio_hdri", "asset_type": "hdris", "resolution": "1k", "file_format": "png", "cache_dir": cache_dir},
        )
        assert hdri["ok"] is True, hdri
        assert bpy.context.scene.world and bpy.context.scene.world.name == hdri["world"], hdri
        assert bpy.context.scene.claude_blender.pending_preview is True, hdri
        assert live_preview.revert(bpy.context)["ok"] is True

        existing_texture_material = bpy.data.materials.new("Poly Haven oak_floor")
        existing_texture_tree = blender_compat.ensure_node_tree(existing_texture_material)
        assert existing_texture_tree is not None
        existing_texture_nodes = [node.name for node in existing_texture_tree.nodes]
        texture = _execute(
            bpy.context,
            "import_poly_haven_asset",
            {
                "asset_id": "oak_floor",
                "asset_type": "textures",
                "resolution": "2k",
                "file_format": "png",
                "target_object_name": cube.name,
                "cache_dir": cache_dir,
            },
        )
        assert texture["ok"] is True, texture
        assert cube.material_slots and cube.material_slots[0].material.name == texture["material"], texture
        assert texture["material"] != existing_texture_material.name, texture
        assert texture["material"].startswith(f"{existing_texture_material.name}."), texture
        assert bpy.data.materials.get(existing_texture_material.name) == existing_texture_material, texture
        assert [node.name for node in existing_texture_material.node_tree.nodes] == existing_texture_nodes, texture
        assert {item["map_type"] for item in texture["texture_maps"]} == {"base_color", "normal", "ambient_occlusion", "roughness", "metallic"}, texture
        texture_material = bpy.data.materials[texture["material"]]
        texture_node_types = {node.type for node in texture_material.node_tree.nodes}
        assert "TEX_IMAGE" in texture_node_types, texture_node_types
        assert "NORMAL_MAP" in texture_node_types, texture_node_types
        assert "SEPARATE_COLOR" in texture_node_types, texture_node_types
        assert "MIX_RGB" in texture_node_types, texture_node_types
        assert texture["manifest"]["imported_texture_maps"] == texture["texture_maps"], texture
        assert live_preview.revert(bpy.context)["ok"] is True

        model = _execute(
            bpy.context,
            "import_poly_haven_asset",
            {"asset_id": "model_one", "asset_type": "models", "resolution": "2k", "file_format": "gltf", "cache_dir": cache_dir},
        )
        assert model["ok"] is True, model
        assert "SmokeImportedModel" in model["imported_objects"], model
        assert bpy.data.objects.get("SmokeImportedModel") is not None, model
        assert "material_preview" in model["presentation"], model
        stale_manifest = dict(model["manifest"])
        stale_manifest["import_status"] = "not_imported"
        external_assets._write_manifest(stale_manifest["cache_dir"], stale_manifest)
        live_cache_record = next(
            item for item in external_assets._cache_asset_records(os.path.abspath(cache_dir))
            if item["asset_id"] == "model_one"
        )
        assert live_cache_record["import_status"] == "imported", live_cache_record
        duplicate_blocked = _execute(
            bpy.context,
            "import_poly_haven_asset",
            {"asset_id": "model_one", "asset_type": "models", "resolution": "2k", "file_format": "gltf", "cache_dir": cache_dir},
        )
        assert duplicate_blocked["ok"] is False, duplicate_blocked
        assert duplicate_blocked["code"] == "asset_already_imported", duplicate_blocked
        assert bpy.data.objects.get("SmokeImportedModel.001") is None, duplicate_blocked
        duplicate_allowed = _execute(
            bpy.context,
            "import_poly_haven_asset",
            {
                "asset_id": "model_one",
                "asset_type": "models",
                "resolution": "2k",
                "file_format": "gltf",
                "cache_dir": cache_dir,
                "allow_duplicate": True,
            },
        )
        assert duplicate_allowed["ok"] is True, duplicate_allowed
        assert bpy.data.objects.get("SmokeImportedModel.001") is not None, duplicate_allowed
        last_step = _execute(bpy.context, "revert_preview", {"scope": "last_step"})
        assert last_step["ok"] is True, last_step
        assert last_step["remaining_step_count"] == 1, last_step
        assert bpy.data.objects.get("SmokeImportedModel.001") is None, last_step
        assert bpy.data.objects.get("SmokeImportedModel") is not None, last_step
        diagnostics = external_assets.external_asset_cache_diagnostics(cache_dir=cache_dir)
        model_diagnostics = next(item for item in diagnostics["assets"] if item["asset_id"] == "model_one")
        assert model_diagnostics["import_status"] == "imported", model_diagnostics
        assert model_diagnostics["imported_objects"] == ["SmokeImportedModel"], model_diagnostics
        assert live_preview.revert(bpy.context)["ok"] is True
        assert bpy.data.objects.get("SmokeImportedModel") is None
        diagnostics = external_assets.external_asset_cache_diagnostics(cache_dir=cache_dir)
        model_diagnostics = next(item for item in diagnostics["assets"] if item["asset_id"] == "model_one")
        assert model_diagnostics["import_status"] == "not_imported", model_diagnostics
        assert model_diagnostics["imported_objects"] == [], model_diagnostics

        previous_transaction_id = live_preview.current_transaction()["id"]
        unsupported_model = _execute(
            bpy.context,
            "import_poly_haven_asset",
            {"asset_id": "blend_only", "asset_type": "models", "resolution": "2k", "file_format": "blend", "cache_dir": cache_dir},
        )
        assert unsupported_model["ok"] is False, unsupported_model
        assert "Direct .blend append" in unsupported_model["message"], unsupported_model
        assert live_preview.current_transaction()["id"] == previous_transaction_id, unsupported_model

        sketchfab = _execute(
            bpy.context,
            "import_sketchfab_model",
            {
                "uid": "sketchfab_one",
                "api_token": "smoke-token",
                "cache_dir": cache_dir,
                "timeout": 999,
                "provenance": {
                    "model_name": "Smoke Hangar",
                    "author": "Smoke Artist",
                    "license": "CC BY 4.0",
                    "model_url": "https://sketchfab.com/3d-models/smoke-hangar-sketchfab-one",
                },
            },
        )
        assert sketchfab["ok"] is True, sketchfab
        assert "SmokeImportedModel" in sketchfab["imported_objects"], sketchfab
        assert sketchfab["manifest"]["author"] == "Smoke Artist", sketchfab
        assert sketchfab["manifest"]["license"] == "CC BY 4.0", sketchfab
        assert sketchfab["manifest"]["model_url"].endswith("smoke-hangar-sketchfab-one"), sketchfab
        assert observed_timeouts[-2:] == [("fetch_json_with_headers", 300), ("download_file", 300)], observed_timeouts
        assert live_preview.revert(bpy.context)["ok"] is True

        async_poly = _execute(
            bpy.context,
            "start_external_asset_download",
            {
                "provider": "poly_haven",
                "asset_id": "model_one",
                "asset_type": "models",
                "resolution": "2k",
                "file_format": "gltf",
                "cache_dir": cache_dir,
                "job_name": "Smoke Poly Haven model",
            },
        )
        assert async_poly["ok"] is True, async_poly
        assert async_poly["job_id"] == async_poly["asset_job"]["job_id"], async_poly
        async_poly_status = _wait_asset_job(bpy.context, async_poly["job_id"])
        assert async_poly_status["asset_job"]["status"] == "completed", async_poly_status
        assert async_poly_status["asset_job"]["manifest_path"], async_poly_status
        assert async_poly_status["asset_job"]["phase"] == "download", async_poly_status
        assert async_poly_status["asset_job"]["bytes_downloaded"] >= 1, async_poly_status
        assert async_poly_status["asset_job"]["current_file"], async_poly_status
        async_poly_import_job = _execute(
            bpy.context,
            "start_external_asset_import_job",
            {"job_id": async_poly["job_id"], "label": "Import async Poly Haven model"},
        )
        assert async_poly_import_job["ok"] is True, async_poly_import_job
        assert async_poly_import_job["asset_import_job"]["status"] == "queued", async_poly_import_job
        _run_import_queue_once()
        async_poly_import_status = _execute(
            bpy.context,
            "get_external_asset_import_job_status",
            {"job_id": async_poly_import_job["job_id"]},
        )
        assert async_poly_import_status["ok"] is True, async_poly_import_status
        assert async_poly_import_status["asset_import_job"]["status"] == "completed", async_poly_import_status
        assert async_poly_import_status["asset_import_job"]["phase"] == "import", async_poly_import_status
        assert async_poly_import_status["asset_import_job"]["import_result"]["ok"] is True, async_poly_import_status
        assert "SmokeImportedModel" in async_poly_import_status["asset_import_job"]["import_result"]["imported_objects"], async_poly_import_status
        async_poly_presentation = _execute(
            bpy.context,
            "prepare_imported_asset_presentation",
            {
                "imported_object_names": async_poly_import_status["asset_import_job"]["import_result"]["imported_objects"],
                "target_object_name": "SmokeImportedModel",
                "collection_prefix": "Smoke Imported Asset",
                "presentation_preset": "studio",
                "assign_material_if_missing": True,
                "create_stage": True,
            },
        )
        assert async_poly_presentation["target"] == "SmokeImportedModel", async_poly_presentation
        assert async_poly_presentation["selection_source"] == "explicit_names", async_poly_presentation
        assert async_poly_presentation["organization"]["ok"] is True, async_poly_presentation
        assert async_poly_presentation["stage"]["ok"] is True, async_poly_presentation
        assert "missing material fill" in async_poly_presentation["features"], async_poly_presentation
        assert live_preview.revert(bpy.context)["ok"] is True

        cancel_import_job = _execute(
            bpy.context,
            "start_external_asset_import_job",
            {"source_job_id": async_poly["job_id"], "label": "Cancel queued Poly Haven import"},
        )
        assert cancel_import_job["ok"] is True, cancel_import_job
        cancelled_import = _execute(
            bpy.context,
            "cancel_external_asset_import_job",
            {"job_id": cancel_import_job["job_id"]},
        )
        assert cancelled_import["ok"] is True, cancelled_import
        assert cancelled_import["asset_import_job"]["status"] == "cancelled", cancelled_import
        delete_dry_run = _execute(
            bpy.context,
            "delete_external_asset_job",
            {"job_id": cancel_import_job["job_id"], "dry_run": True},
        )
        assert delete_dry_run["ok"] is True, delete_dry_run
        assert delete_dry_run["deleted"] is False, delete_dry_run
        delete_actual = _execute(
            bpy.context,
            "delete_external_asset_job",
            {"job_id": cancel_import_job["job_id"], "dry_run": False},
        )
        assert delete_actual["ok"] is True, delete_actual
        assert delete_actual["deleted"] is True, delete_actual
        deleted_status = _execute(
            bpy.context,
            "get_external_asset_import_job_status",
            {"job_id": cancel_import_job["job_id"]},
        )
        assert deleted_status["ok"] is False, deleted_status

        observed_timeouts.clear()
        async_sketchfab = _execute(
            bpy.context,
            "start_external_asset_download",
            {
                "provider": "sketchfab",
                "uid": "sketchfab_one",
                "api_token": "smoke-token",
                "cache_dir": cache_dir,
                "timeout": 999,
                "job_name": "Smoke Sketchfab model",
            },
        )
        assert async_sketchfab["ok"] is True, async_sketchfab
        assert "smoke-token" not in json.dumps(async_sketchfab, sort_keys=True), async_sketchfab
        async_sketchfab_status = _wait_asset_job(bpy.context, async_sketchfab["job_id"])
        assert async_sketchfab_status["asset_job"]["status"] == "completed", async_sketchfab_status
        assert observed_timeouts == [("fetch_json_with_headers", 300), ("download_file", 300)], observed_timeouts
        status_text = json.dumps(async_sketchfab_status, sort_keys=True)
        assert "smoke-token" not in status_text, async_sketchfab_status
        assert async_sketchfab_status["asset_job"]["parameters"]["api_token_supplied"] is True, async_sketchfab_status
        async_sketchfab_import = _execute(
            bpy.context,
            "import_external_asset_job_result",
            {"job_id": async_sketchfab["job_id"], "label": "Import async Sketchfab model"},
        )
        assert async_sketchfab_import["ok"] is True, async_sketchfab_import
        assert "SmokeImportedModel" in async_sketchfab_import["import_result"]["imported_objects"], async_sketchfab_import
        assert live_preview.revert(bpy.context)["ok"] is True

        if original_asset_job_mode is None:
            os.environ.pop(asset_jobs.ASSET_JOB_MODE_ENV, None)
        else:
            os.environ[asset_jobs.ASSET_JOB_MODE_ENV] = original_asset_job_mode
        fixture_server, fixture_thread, fixture_base_url = _start_poly_haven_fixture_server()
        os.environ["BLENDER_AGENT_BRIDGE_POLY_HAVEN_BASE_URL"] = fixture_base_url
        subprocess_poly = _execute(
            bpy.context,
            "start_external_asset_download",
            {
                "provider": "poly_haven",
                "asset_id": "subprocess_model",
                "asset_type": "models",
                "resolution": "1k",
                "file_format": "gltf",
                "cache_dir": cache_dir,
                "job_name": "Smoke subprocess Poly Haven model",
            },
        )
        assert subprocess_poly["ok"] is True, subprocess_poly
        assert subprocess_poly["asset_job"]["worker_type"] == "subprocess", subprocess_poly
        subprocess_poly_status = _wait_asset_job(bpy.context, subprocess_poly["job_id"], timeout=45.0)
        assert subprocess_poly_status["asset_job"]["status"] == "completed", subprocess_poly_status
        assert subprocess_poly_status["asset_job"]["worker_type"] == "subprocess", subprocess_poly_status
        assert subprocess_poly_status["asset_job"]["pid"], subprocess_poly_status
        assert subprocess_poly_status["asset_job"]["manifest_path"], subprocess_poly_status
        assert subprocess_poly_status["asset_job"]["manifest_summary"]["ok"] is True, subprocess_poly_status
        subprocess_poly_import = _execute(
            bpy.context,
            "start_external_asset_import_job",
            {"source_job_id": subprocess_poly["job_id"], "label": "Import subprocess Poly Haven model"},
        )
        assert subprocess_poly_import["ok"] is True, subprocess_poly_import
        _run_import_queue_once()
        subprocess_poly_import_status = _execute(
            bpy.context,
            "get_external_asset_import_job_status",
            {"job_id": subprocess_poly_import["job_id"]},
        )
        assert subprocess_poly_import_status["asset_import_job"]["status"] == "completed", subprocess_poly_import_status
        assert subprocess_poly_import_status["asset_import_job"]["import_result"]["ok"] is True, subprocess_poly_import_status
        assert live_preview.revert(bpy.context)["ok"] is True

        subprocess_missing_auth = _execute(
            bpy.context,
            "start_external_asset_download",
            {"provider": "sketchfab", "uid": "subprocess_missing_auth", "cache_dir": cache_dir},
        )
        assert subprocess_missing_auth["ok"] is True, subprocess_missing_auth
        assert subprocess_missing_auth["asset_job"]["worker_type"] == "subprocess", subprocess_missing_auth
        subprocess_status = _wait_asset_job(bpy.context, subprocess_missing_auth["job_id"], timeout=15.0)
        assert subprocess_status["asset_job"]["status"] == "failed", subprocess_status
        assert subprocess_status["asset_job"]["worker_type"] == "subprocess", subprocess_status
        assert subprocess_status["asset_job"]["pid"], subprocess_status
        assert "token" in subprocess_status["asset_job"]["message"].lower(), subprocess_status

        diagnostics = _execute(bpy.context, "get_external_asset_cache_diagnostics", {"cache_dir": cache_dir})
        assert diagnostics["ok"] is True, diagnostics
        assert diagnostics["asset_count"] >= 4, diagnostics
        print("smoke_external_asset_imports: ok")
    finally:
        try:
            claude_blender.unregister()
        except Exception:
            pass
        if fixture_server is not None:
            fixture_server.shutdown()
            fixture_server.server_close()
        if fixture_thread is not None:
            fixture_thread.join(timeout=1.0)
        external_assets._fetch_json = original_fetch_json
        external_assets._fetch_json_with_headers = original_fetch_json_with_headers
        external_assets._download_file = original_download_file
        external_assets._import_model_file = original_import_model_file
        if original_poly_haven_base_url is None:
            os.environ.pop("BLENDER_AGENT_BRIDGE_POLY_HAVEN_BASE_URL", None)
        else:
            os.environ["BLENDER_AGENT_BRIDGE_POLY_HAVEN_BASE_URL"] = original_poly_haven_base_url
        if original_asset_job_mode is None:
            os.environ.pop(asset_jobs.ASSET_JOB_MODE_ENV, None)
        else:
            os.environ[asset_jobs.ASSET_JOB_MODE_ENV] = original_asset_job_mode
        shutil.rmtree(cache_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
