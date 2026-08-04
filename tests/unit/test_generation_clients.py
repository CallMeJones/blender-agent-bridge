from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import generation_clients as gc  # noqa: E402

KEY = "tsk_secret_value_do_not_leak"


class FakeTransport:
    """Records requests and replays queued (status, body) responses."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body})
        if not self.responses:
            raise AssertionError("unexpected extra request to %s" % url)
        return self.responses.pop(0)


def ok(payload):
    return 200, json.dumps({"code": 0, "status": "success", "data": payload})


def api_error(status, code, message):
    return status, json.dumps({"code": code, "status": "error", "message": message})


def _client(transport):
    return gc.TripoClient(KEY, transport=transport)


def _png(tmp, name="front.png"):
    path = os.path.join(tmp, name)
    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
    return path


class ConstructionTests(unittest.TestCase):
    def test_missing_key_is_rejected(self):
        with self.assertRaises(gc.GenerationError):
            gc.TripoClient("")

    def test_default_base_url_is_v3(self):
        self.assertIn("openapi.tripo3d.ai/v3", gc.TRIPO_BASE_URL)

    def test_authorization_header_is_bearer(self):
        transport = FakeTransport(ok({"status": "running"}))
        _client(transport).task_status("t")
        self.assertEqual("Bearer %s" % KEY, transport.calls[0]["headers"]["Authorization"])


class DefaultTransportTests(unittest.TestCase):
    """Covers the real transport, which the FakeTransport tests never reach."""

    def test_no_redirect_handler_is_accepted_by_build_opener(self):
        import urllib.request

        # build_opener rejects anything that is not a BaseHandler subclass.
        opener = urllib.request.build_opener(gc._NoRedirect)
        self.assertTrue(any(isinstance(h, gc._NoRedirect) for h in opener.handlers))

    def test_redirects_are_refused(self):
        self.assertIsNone(
            gc._NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://evil.test/")
        )

    def test_non_https_is_refused_before_any_request(self):
        with self.assertRaises(gc.GenerationError) as caught:
            gc._default_transport("GET", "http://insecure.test/x", {}, None, 5)
        self.assertIn("non-HTTPS", str(caught.exception))


class BalanceTests(unittest.TestCase):
    def test_balance_uses_the_v3_account_path(self):
        transport = FakeTransport(ok({"balance": 1000.0, "frozen": 0.0}))
        result = _client(transport).balance()
        self.assertEqual(1000.0, result["balance"])
        # v2 used user/balance, which 404s on v3; guard the regression.
        self.assertTrue(transport.calls[0]["url"].endswith("/account/balance"))
        self.assertNotIn("user/balance", transport.calls[0]["url"])


class UploadTests(unittest.TestCase):
    def test_upload_posts_multipart_to_files_and_returns_file_token(self):
        transport = FakeTransport(ok({"file_token": "file_abc"}))
        with tempfile.TemporaryDirectory() as tmp:
            token = _client(transport).upload_image(_png(tmp))
        self.assertEqual("file_abc", token)
        call = transport.calls[0]
        self.assertEqual("POST", call["method"])
        self.assertTrue(call["url"].endswith("/files"))
        self.assertIn("multipart/form-data; boundary=", call["headers"]["Content-Type"])
        self.assertIn(b'name="file"', call["body"])

    def test_upload_without_token_raises(self):
        transport = FakeTransport(ok({}))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(gc.GenerationError):
                _client(transport).upload_image(_png(tmp))


class ImageTaskTests(unittest.TestCase):
    def test_body_uses_file_key_and_requires_model(self):
        transport = FakeTransport(ok({"task_id": "t-1"}))
        task = _client(transport).create_image_task("file_abc", "front.png")
        self.assertEqual("t-1", task)
        call = transport.calls[0]
        self.assertTrue(call["url"].endswith("/generation/image-to-model"))
        body = json.loads(call["body"].decode())
        self.assertEqual(gc.TRIPO_DEFAULT_MODEL, body["model"])
        self.assertEqual({"type": "png", "file_token": "file_abc"}, body["file"])
        self.assertNotIn("type", {k: v for k, v in body.items() if k != "file"})

    def test_no_input_wrapper_is_sent(self):
        transport = FakeTransport(ok({"task_id": "t"}))
        _client(transport).create_image_task("file_abc", "a.png")
        body = json.loads(transport.calls[0]["body"].decode())
        self.assertNotIn("input", body)

    def test_jpeg_suffix_is_normalised(self):
        transport = FakeTransport(ok({"task_id": "t"}))
        _client(transport).create_image_task("tok", "shot.jpeg")
        body = json.loads(transport.calls[0]["body"].decode())
        self.assertEqual("jpg", body["file"]["type"])

    def test_optional_parameters_are_omitted_unless_set(self):
        transport = FakeTransport(ok({"task_id": "t"}))
        _client(transport).create_image_task("tok", "a.png")
        body = json.loads(transport.calls[0]["body"].decode())
        self.assertNotIn("face_limit", body)
        self.assertNotIn("texture", body)


class MultiviewTaskTests(unittest.TestCase):
    def test_always_sends_exactly_four_slots(self):
        transport = FakeTransport(ok({"task_id": "t-mv"}))
        _client(transport).create_multiview_task({"front": ("f", "front.png")})
        body = json.loads(transport.calls[0]["body"].decode())
        self.assertEqual(4, len(body["files"]))
        self.assertEqual("f", body["files"][0]["file_token"])
        self.assertEqual([{}, {}, {}], body["files"][1:])

    def test_slot_order_is_front_left_back_right(self):
        self.assertEqual(("front", "left", "back", "right"), gc.MULTIVIEW_SLOTS)
        transport = FakeTransport(ok({"task_id": "t"}))
        _client(transport).create_multiview_task(
            {
                "front": ("f", "front.png"),
                "left": ("l", "left.png"),
                "back": ("b", "back.png"),
            }
        )
        body = json.loads(transport.calls[0]["body"].decode())
        self.assertEqual(["f", "l", "b"], [entry["file_token"] for entry in body["files"][:3]])
        self.assertEqual({}, body["files"][3])

    def test_uses_multiview_endpoint_without_input_wrapper(self):
        transport = FakeTransport(ok({"task_id": "t"}))
        _client(transport).create_multiview_task({"front": ("f", "a.png")})
        call = transport.calls[0]
        self.assertTrue(call["url"].endswith("/generation/multiview-to-model"))
        self.assertNotIn("input", json.loads(call["body"].decode()))

    def test_no_views_raises(self):
        with self.assertRaises(gc.GenerationError):
            _client(FakeTransport()).create_multiview_task({})


class TaskStatusTests(unittest.TestCase):
    def test_success_exposes_model_url(self):
        transport = FakeTransport(ok({"status": "success", "progress": 100, "output": {"model": "https://x/m.glb"}}))
        status = _client(transport).task_status("t-1")
        self.assertTrue(status["succeeded"])
        self.assertTrue(status["terminal"])
        self.assertEqual("https://x/m.glb", status["model_url"])
        self.assertTrue(transport.calls[0]["url"].endswith("/tasks/t-1"))

    def test_pbr_model_is_preferred(self):
        transport = FakeTransport(ok({"status": "success", "output": {"model": "https://x/a.glb", "pbr_model": "https://x/b.glb"}}))
        self.assertEqual("https://x/b.glb", _client(transport).task_status("t")["model_url"])

    def test_running_task_is_not_terminal(self):
        transport = FakeTransport(ok({"status": "running", "progress": 42}))
        status = _client(transport).task_status("t")
        self.assertFalse(status["terminal"])
        self.assertEqual(42, status["progress"])

    def test_failure_states_are_terminal_but_not_successful(self):
        for state in ("failed", "cancelled", "banned"):
            transport = FakeTransport(ok({"status": state}))
            status = _client(transport).task_status("t")
            self.assertTrue(status["terminal"], state)
            self.assertFalse(status["succeeded"], state)

    def test_renamed_v3_fields_are_surfaced(self):
        transport = FakeTransport(ok({"status": "success", "credits_consumed": 20, "created_at": 1234, "output": {}}))
        status = _client(transport).task_status("t")
        self.assertEqual(20, status["credits_consumed"])
        self.assertEqual(1234, status["created_at"])


class ErrorHandlingTests(unittest.TestCase):
    def test_insufficient_credit_is_flagged_distinctly(self):
        transport = FakeTransport(api_error(403, gc.CODE_INSUFFICIENT_CREDIT, "You don't have enough credit to create this task"))
        with self.assertRaises(gc.GenerationError) as caught:
            _client(transport).create_image_task("tok", "a.png")
        self.assertTrue(caught.exception.insufficient_credit)
        self.assertEqual(gc.CODE_INSUFFICIENT_CREDIT, caught.exception.code)

    def test_validation_error_is_not_a_credit_error(self):
        transport = FakeTransport(api_error(400, gc.CODE_VALIDATION, "model is required"))
        with self.assertRaises(gc.GenerationError) as caught:
            _client(transport).create_image_task("tok", "a.png")
        self.assertFalse(caught.exception.insufficient_credit)

    def test_application_code_on_http_200_is_still_a_failure(self):
        transport = FakeTransport((200, json.dumps({"code": 2001, "message": "The task is not found"})))
        with self.assertRaises(gc.GenerationError) as caught:
            _client(transport).task_status("t")
        self.assertIn("not found", str(caught.exception))

    def test_non_json_response_is_reported_clearly(self):
        transport = FakeTransport((502, "<html>bad gateway</html>"))
        with self.assertRaises(gc.GenerationError) as caught:
            _client(transport).task_status("t")
        self.assertIn("non-JSON", str(caught.exception))

    def test_key_never_appears_in_json_error_text(self):
        transport = FakeTransport((500, json.dumps({"code": 9, "message": "token was %s" % KEY})))
        with self.assertRaises(gc.GenerationError) as caught:
            _client(transport).task_status("t")
        self.assertNotIn(KEY, str(caught.exception))

    def test_key_never_appears_in_plaintext_error_text(self):
        transport = FakeTransport((500, "plain failure %s trailing" % KEY))
        with self.assertRaises(gc.GenerationError) as caught:
            _client(transport).task_status("t")
        self.assertNotIn(KEY, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
