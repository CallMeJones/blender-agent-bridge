import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "addon"))
from claude_blender import generation_clients, generation_meshy, generation_spend, retopology_policy, retopology_providers


class Transport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, json.loads(body) if body else None))
        return self.responses.pop(0)


def response(data, code=200):
    return code, json.dumps(data)


class FakeClient:
    base_url = "https://api.meshy.ai/openapi/v1"
    def __init__(self, provider="meshy", missing_fbx=False):
        self.provider = provider
        self.missing_fbx = missing_fbx
        self.submitted = 0
    def create_remesh_task(self, **args):
        self.submitted += 1
        return "retopo-task"
    create_retopology_task = create_remesh_task
    def task_status(self, task_id):
        artifacts = {"glb": "https://assets.example/model.glb"}
        if self.provider == "meshy" and not self.missing_fbx:
            artifacts["fbx"] = "https://assets.example/model.fbx"
        return {"terminal": True, "succeeded": True, "progress": 100,
                "model_url": artifacts["glb"], "artifact_urls": artifacts, "credits_consumed": 5}


def downloader(url, path, **kwargs):
    data = b"Kaydara FBX Binary  \x00\x1a\x00" if path.endswith(".fbx") else b"glTF" + b"\x00" * 24
    Path(path).write_bytes(data)
    return {"ok": True, "bytes": len(data)}


class RetopologyProviderTests(unittest.TestCase):
    def test_meshy_request_status_and_cancel_use_remesh_endpoint(self):
        transport = Transport(response({"result": "remesh-task"}), response({"status": "SUCCEEDED", "progress": 100,
                              "model_urls": {"fbx": "https://example.com/model.fbx", "glb": "https://example.com/model.glb"}}), response({}))
        client = generation_clients.MeshyClient("test-secret", transport=transport)
        task_id = client.create_remesh_task(source_task_id="original-task", target_faces=5000)
        status = client.task_status(task_id)
        self.assertTrue(status["succeeded"])
        self.assertIn("fbx", status["artifact_urls"])
        self.assertEqual(transport.calls[0][2], {"input_task_id": "original-task", "target_polycount": 5000,
                                               "topology": "quad", "target_formats": ["fbx", "glb"]})
        self.assertTrue(transport.calls[1][1].endswith("/remesh/remesh-task"))
        client.cancel_task(task_id, task_kind="remesh")
        self.assertEqual(transport.calls[2][0], "DELETE")
        self.assertTrue(transport.calls[2][1].endswith("/remesh/remesh-task"))

    def test_tripo_request_uses_v3_mesh_decimate(self):
        transport = Transport(response({"code": 0, "data": {"task_id": "task-new"}}))
        client = generation_clients.TripoClient("test-secret", transport=transport)
        self.assertEqual(client.create_retopology_task(source_task_id="task-source", target_faces=5000), "task-new")
        self.assertTrue(transport.calls[0][1].endswith("/v3/mesh/decimate"))
        self.assertEqual(transport.calls[0][2], {"input": "task-source", "model": "v3.0", "face_limit": 5000,
                                               "quad": True, "smart_uv": True, "bake": True})

    def test_source_and_version_bounds(self):
        for args in ({}, {"source_task_id": "task", "model_url": "https://example.com/model.glb"},
                     {"source_task_id": "../task"}, {"model_url": "https://127.0.0.1/model.glb"},
                     {"model_url": "https://example.com/model.glb?token=secret"},
                     {"source_task_id": "task", "target_faces": 10001},
                     {"source_task_id": "task", "retopology_model": "v2.0", "smart_uv": True},
                     {"source_task_id": "task", "retopology_model": "v1.0", "bake": True}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                retopology_policy.provider_options("tripo", args)
        self.assertEqual(retopology_policy.provider_options("tripo", {"source_task_id": "task", "retopology_model": "v1.0"})["estimated_credits"], 10)

    def test_spend_fingerprint_binds_source_and_topology(self):
        args = {"job_kind": "retopology", "source_task_id": "task-original"}
        fingerprint = generation_spend.job_fingerprint("meshy", args)
        for change in ({"source_task_id": "task-other"}, {"topology": "triangle"}, {"target_faces": 6000}):
            self.assertNotEqual(fingerprint, generation_spend.job_fingerprint("meshy", dict(args, **change)))

    def test_quad_generation_requests_fbx_companion(self):
        options = generation_meshy.normalize_job_options({"meshy_options": {"preset": "editable_quad"}}, view_count=1)
        self.assertEqual(generation_meshy.request_options(options)["target_formats"], ["glb", "fbx"])

    def test_worker_downloads_fbx_for_quads_and_glb_for_tripo(self):
        for provider in ("meshy", "tripo"):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as tmp:
                manifest = retopology_providers.run({"child_status_path": os.path.join(tmp,"status.json")},
                                                    {"source_task_id": "task-source"}, provider=provider, api_key="test-secret",
                                                    client=FakeClient(provider), downloader=downloader, poll_interval=0)
                self.assertTrue(manifest["ok"], manifest)
                self.assertTrue(manifest["import_file"].endswith(".fbx" if provider == "meshy" else ".glb"))
                self.assertNotIn("test-secret", json.dumps(manifest))
                self.assertTrue(Path(manifest["manifest_path"]).is_file())

    def test_missing_fbx_does_not_silently_import_triangles(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = retopology_providers.run({"child_status_path": os.path.join(tmp,"status.json")}, {"source_task_id": "task"},
                                              provider="meshy", api_key="secret", client=FakeClient(missing_fbx=True),
                                              downloader=downloader, poll_interval=0)
            self.assertFalse(result["ok"])
            self.assertIn("FBX", result["message"])

    def test_cancel_before_submit_does_not_spend(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as tmp:
            result = retopology_providers.run({"child_status_path": os.path.join(tmp,"status.json")}, {"source_task_id": "task"},
                                              provider="meshy", api_key="secret", client=client, is_cancelled=lambda: True)
            self.assertFalse(result["ok"])
            self.assertEqual(client.submitted, 0)


if __name__ == "__main__":
    unittest.main()
