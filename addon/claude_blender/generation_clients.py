"""HTTP clients for hosted image-to-3D generation providers.

Tripo v3. Every shape below was verified against the live API rather than taken
from documentation, which disagreed with itself across three sources:

    POST /v3/files                        multipart, form field "file"
        -> {"code":0,"status":"success","data":{"file_token":"file_..."}}
    POST /v3/generation/image-to-model    {"model": M, "file": {"type","file_token"}}
    POST /v3/generation/multiview-to-model {"model": M, "files": [f, l, b, r]}
        -> exactly four slots, front/left/back/right; {} skips a view
    GET  /v3/tasks/{task_id}
        -> {"code":0,"data":{"status":..,"output":{..}}}

Both generation bodies were confirmed by submitting them against a zero-credit
account: the API rejected them with code 2010 ("not enough credit") rather than
1004 ("validation"), which proves the structure was accepted.

v2 (``api.tripo3d.ai/v2/openapi``) is retired on 1 November 2026 and is not
implemented here. API keys are shared between the two versions.

Transport is injected so the client is testable without network access, and
every error path scrubs the credential before it can reach a log or a tool
result.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import generation_meshy, generation_references, generation_tripo

TRIPO_BASE_URL = "https://openapi.tripo3d.ai/v3"
TRIPO_DEFAULT_MODEL = generation_tripo.DEFAULT_MODEL
TRIPO_MODELS = generation_tripo.MODELS

MESHY_BASE_URL = "https://api.meshy.ai/openapi/v1"
MESHY_DEFAULT_MODEL = generation_meshy.DEFAULT_MODEL
MESHY_MODELS = generation_meshy.MODELS

STUDIO_DEFAULT_PATH = "image-to-3d"
STUDIO_STATUS_PATH = "tasks"

# Multiview is positional and fixed-length.
MULTIVIEW_SLOTS = ("front", "left", "back", "right")

CODE_INSUFFICIENT_CREDIT = 2010
CODE_VALIDATION = 1004

TERMINAL_SUCCESS = "success"
TERMINAL_FAILURES = ("failed", "cancelled", "banned", "unknown")
TERMINAL_STATUSES = (TERMINAL_SUCCESS,) + TERMINAL_FAILURES

MESHY_TERMINAL_SUCCESS = "succeeded"
MESHY_TERMINAL_FAILURES = ("failed", "canceled", "cancelled", "expired")
MESHY_TERMINAL_STATUSES = (MESHY_TERMINAL_SUCCESS,) + MESHY_TERMINAL_FAILURES


class GenerationError(Exception):
    """Provider error with the credential already removed from its message."""

    def __init__(
        self,
        message,
        *,
        code=0,
        insufficient_credit=False,
        retryable=False,
        error_type="",
        doc_url="",
        details=None,
    ):
        super().__init__(message)
        self.code = code
        self.insufficient_credit = insufficient_credit
        self.retryable = bool(retryable)
        self.error_type = str(error_type or "")
        self.doc_url = str(doc_url or "")
        self.details = dict(details or {})

    def as_dict(self):
        return {
            "message": str(self),
            "code": self.code,
            "insufficient_credit": bool(self.insufficient_credit),
            "retryable": bool(self.retryable),
            "type": self.error_type,
            "doc_url": self.doc_url,
        }


def _redact(text, secret):
    out = str(text)
    return out.replace(secret, "<redacted>") if secret else out


def _encode_multipart_file(
    field,
    file_path,
    content_type="",
    *,
    provider="tripo",
    expected_identity=None,
):
    """Build a multipart body, reading the file straight into the payload.

    Reads once into the assembled body rather than holding the file bytes and
    the encoded body simultaneously.
    """

    boundary = "----blenderagentbridge%s" % uuid.uuid4().hex
    try:
        payload, identity = generation_references.read_reference_image(
            file_path,
            provider=provider,
            expected_identity=expected_identity,
        )
    except ValueError as error:
        raise GenerationError(str(error), error_type="invalid_local_input") from None
    content_type = content_type or "image/%s" % identity["format"]
    body = b"".join(
        [
            ("--%s\r\n" % boundary).encode(),
            (
                'Content-Disposition: form-data; name="%s"; filename="%s"\r\n'
                % (field, os.path.basename(file_path))
            ).encode(),
            ("Content-Type: %s\r\n\r\n" % content_type).encode(),
            payload,
            ("\r\n--%s--\r\n" % boundary).encode(),
        ]
    )
    return body, "multipart/form-data; boundary=%s" % boundary


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so a Bearer token is never replayed to another host.

    urllib's default handler follows redirects and re-sends every header,
    including Authorization. For a credential-bearing client that is a token
    leak to whatever host the redirect names, so redirects surface to the
    caller as an ordinary response instead.

    Must subclass HTTPRedirectHandler: build_opener rejects anything that is
    not a BaseHandler.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def build_no_redirect_opener(*handlers):
    """Build an opener that never replays request headers across redirects."""

    return urllib.request.build_opener(*handlers, _NoRedirect)


def _default_transport(method, url, headers, body, timeout):
    if not str(url).lower().startswith("https://"):
        raise GenerationError(
            "Refusing to send credentials over a non-HTTPS URL: %s" % url
        )

    request = urllib.request.Request(url, data=body, method=method)
    for name, value in headers.items():
        request.add_header(name, value)
    opener = build_no_redirect_opener()
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        try:
            detail = error.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - error body is best-effort
            detail = ""
        return error.code, detail
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise GenerationError(
            "Provider transport failed: %s" % error,
            retryable=True,
            error_type=type(error).__name__,
        ) from None


def _default_local_transport(method, url, headers, body, timeout):
    """HTTP transport for studio-owned endpoints.

    Studio endpoints are explicitly local/self-hosted. They may run on plain
    HTTP inside a controlled network, so unlike hosted-provider transport this
    function does not force HTTPS. Redirects are still refused so a token is
    never replayed to another host.
    """

    request = urllib.request.Request(url, data=body, method=method)
    for name, value in headers.items():
        request.add_header(name, value)
    opener = build_no_redirect_opener()
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        try:
            detail = error.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - error body is best-effort
            detail = ""
        return error.code, detail
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise GenerationError(
            "Studio endpoint transport failed: %s" % error,
            retryable=True,
            error_type=type(error).__name__,
        ) from None


def image_entry(file_token, image_path=""):
    """Build one file descriptor for a generation request."""

    suffix = os.path.splitext(image_path or "")[1].lstrip(".").lower() or "png"
    if suffix == "jpeg":
        suffix = "jpg"
    return {"type": suffix, "file_token": file_token}


def image_data_uri(image_path, *, provider="studio_endpoint", expected_identity=None):
    """Encode a local PNG/JPEG as a data URI for providers without upload APIs."""

    payload_bytes, identity = generation_references.read_reference_image(
        image_path,
        provider=provider,
        expected_identity=expected_identity,
    )
    content_type = "image/%s" % identity["format"]
    payload = base64.b64encode(payload_bytes).decode("ascii")
    return "data:%s;base64,%s" % (content_type, payload)


def _json_response(text, *, label, status, secret=""):
    safe = _redact(text, secret)
    try:
        payload = json.loads(text) if text else {}
    except ValueError:
        status_code = int(status or 0)
        raise GenerationError(
            "%s returned a non-JSON response (HTTP %s): %s"
            % (label, status, safe[:200]),
            code=status_code,
            retryable=(status_code == 429 or status_code >= 500),
            error_type="invalid_provider_response",
        ) from None
    if not isinstance(payload, dict):
        raise GenerationError(
            "%s returned a JSON value that was not an object" % label,
            code=int(status or 0),
            retryable=True,
            error_type="invalid_provider_response",
        )
    return payload


def _provider_mapping(value, *, label):
    if isinstance(value, dict):
        return value
    raise GenerationError(
        "%s returned an invalid object" % label,
        retryable=True,
        error_type="invalid_provider_response",
    )


def _provider_number(value, *, label, default=0.0):
    if value in (None, ""):
        return float(default)
    if isinstance(value, bool):
        raise GenerationError(
            "%s returned an invalid numeric value" % label,
            retryable=True,
            error_type="invalid_provider_response",
        )
    try:
        return float(value)
    except (TypeError, ValueError):
        raise GenerationError(
            "%s returned an invalid numeric value" % label,
            retryable=True,
            error_type="invalid_provider_response",
        ) from None


def _provider_progress(value, *, label, default=0):
    number = _provider_number(value, label=label, default=default)
    if number != number or number in (float("inf"), float("-inf")):
        raise GenerationError(
            "%s returned a non-finite progress value" % label,
            retryable=True,
            error_type="invalid_provider_response",
        )
    return int(number)


def _error_message(payload, fallback=""):
    if isinstance(payload, dict):
        for key in ("message", "error", "detail", "suggestion"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        task_error = payload.get("task_error")
        if isinstance(task_error, dict):
            value = task_error.get("message")
            if isinstance(value, str) and value:
                return value
    return str(fallback or "unknown error")


def _task_error(payload):
    value = payload.get("task_error") if isinstance(payload, dict) else None
    if not isinstance(value, dict):
        return {}
    return {
        "type": str(value.get("type") or ""),
        "message": str(value.get("message") or ""),
        "code": value.get("code"),
        "doc_url": str(value.get("doc_url") or ""),
    }


def _meshy_artifact_urls(payload):
    """Extract the documented downloadable Meshy task artifacts."""

    if not isinstance(payload, dict):
        return {}
    artifacts = {}
    model_urls = payload.get("model_urls")
    if isinstance(model_urls, dict):
        for key in ("glb", "pre_remeshed_glb"):
            value = model_urls.get(key)
            if isinstance(value, str) and value:
                artifacts[key] = value
    for key in ("thumbnail_url", "alpha_thumbnail_url"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            artifacts[key] = value
    thumbnail_urls = payload.get("thumbnail_urls")
    if isinstance(thumbnail_urls, dict):
        for view in ("front", "right", "back", "left"):
            value = thumbnail_urls.get(view)
            if isinstance(value, str) and value:
                artifacts["thumbnail_%s" % view] = value
    texture_urls = payload.get("texture_urls")
    if isinstance(texture_urls, list):
        for index, texture_set in enumerate(texture_urls[:16]):
            if not isinstance(texture_set, dict):
                continue
            for map_name in ("base_color", "metallic", "roughness", "normal", "emission"):
                value = texture_set.get(map_name)
                if isinstance(value, str) and value:
                    artifacts["texture_%d_%s" % (index, map_name)] = value
    return artifacts


def _model_url_from_payload(payload):
    urls = payload.get("model_urls") if isinstance(payload, dict) else None
    if isinstance(urls, dict):
        for key in ("glb", "pbr_model", "model", "fbx", "obj", "usdz", "stl"):
            value = urls.get(key)
            if isinstance(value, str) and value:
                return value
    output = payload.get("output") if isinstance(payload, dict) else None
    if isinstance(output, dict):
        for key in ("pbr_model", "model", "model_url", "glb"):
            value = output.get(key)
            if isinstance(value, str) and value:
                return value
    for key in ("model_url", "model", "glb"):
        value = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(value, str) and value:
            return value
    return ""


def _local_http_host(host):
    host = str(host or "").strip().strip("[]").lower()
    if host in {"localhost"} or not host:
        return True
    if "." not in host:
        return True
    if host.endswith(".local") or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(address.is_private or address.is_loopback or address.is_link_local)


class TripoClient:
    """Client for the Tripo v3 generation API."""

    def __init__(self, api_key, *, base_url=TRIPO_BASE_URL, transport=None, timeout=60):
        self._key = str(api_key or "").strip()
        if not self._key:
            raise GenerationError("Tripo API key is not configured")
        self.base_url = str(base_url or TRIPO_BASE_URL).rstrip("/")
        self._transport = transport or _default_transport
        self.timeout = timeout

    def _request(self, method, path, *, body=None, content_type="", label=""):
        url = "%s/%s" % (self.base_url, str(path).lstrip("/"))
        headers = {"Authorization": "Bearer %s" % self._key, "Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        status, text = self._transport(method, url, headers, body, self.timeout)
        safe = _redact(text, self._key)
        payload = _json_response(
            text,
            label=label or path,
            status=status,
            secret=self._key,
        )
        code_raw = payload.get("code")
        code = int(_provider_number(code_raw, label="%s code" % (label or path))) if code_raw is not None else 0
        if status >= 400 or code:
            # Redact again here: this message comes from the parsed payload, not
            # from `safe`, so a provider that echoes the key in a JSON field
            # would otherwise leak it into logs and tool results.
            message = _redact(
                payload.get("message") or payload.get("suggestion") or safe[:200],
                self._key,
            )
            raise GenerationError(
                "%s failed (HTTP %s, code %s): %s" % (label or path, status, code, message),
                code=int(code or 0),
                insufficient_credit=(code == CODE_INSUFFICIENT_CREDIT),
                retryable=(status == 429 or status >= 500),
                error_type="http_error" if status >= 400 else "provider_error",
            )
        return _provider_mapping(payload.get("data", {}) or {}, label="%s data" % (label or path))

    def balance(self):
        """Read the credit meter.

        The v3 path is ``account/balance``; ``user/balance`` is the v2 name and
        404s here. Reported for pre-flight so a job can fail before uploading
        rather than after.
        """

        data = self._request("GET", "account/balance", label="balance")
        return {
            "balance": _provider_number(data.get("balance"), label="Tripo balance"),
            "frozen": _provider_number(data.get("frozen"), label="Tripo frozen balance"),
        }

    def upload_image(self, image_path, *, expected_identity=None):
        """Upload one image and return its ``file_token``. Uploads are not billed."""

        body, content_type = _encode_multipart_file(
            "file",
            image_path,
            provider="tripo",
            expected_identity=expected_identity,
        )
        data = self._request("POST", "files", body=body, content_type=content_type, label="upload")
        token = str(data.get("file_token") or "")
        if not token:
            raise GenerationError("upload returned no file_token")
        return token

    def create_image_task(self, file_token, image_path="", *, model="", face_limit=0, texture=None):
        """Create a single-image task. This spends credits."""

        return self._create(
            "generation/image-to-model",
            {"file": image_entry(file_token, image_path)},
            model=model,
            face_limit=face_limit,
            texture=texture,
        )

    def create_multiview_task(self, views, *, model="", face_limit=0, texture=None):
        """Create a multi-view task. This spends credits.

        ``views`` maps slot name to ``(file_token, image_path)``. The API
        requires exactly four positional slots -- front, left, back, right --
        so any slot not supplied is sent as an empty object.
        """

        files = []
        for slot in MULTIVIEW_SLOTS:
            entry = views.get(slot)
            if entry and entry[0]:
                files.append(image_entry(entry[0], entry[1] if len(entry) > 1 else ""))
            else:
                files.append({})
        if not any(files):
            raise GenerationError("multiview task needs at least one view")
        return self._create(
            "generation/multiview-to-model",
            {"files": files},
            model=model,
            face_limit=face_limit,
            texture=texture,
        )

    def _create(self, path, payload, *, model="", face_limit=0, texture=None):
        """Apply the parameters every generation endpoint shares, then submit."""

        raw_options = {"model": model, "face_limit": face_limit}
        if texture is not None:
            raw_options["texture"] = texture
        try:
            options = generation_tripo.normalize_job_options(raw_options)
        except ValueError as error:
            raise GenerationError(str(error), error_type="validation_error") from None
        body = {"model": options["model"]}
        body.update(payload)
        if options["face_limit"]:
            body["face_limit"] = options["face_limit"]
        if texture is not None:
            body["texture"] = options["texture"]
        data = self._request(
            "POST", path, body=json.dumps(body).encode("utf-8"),
            content_type="application/json", label=path,
        )
        task_id = str(data.get("task_id") or data.get("id") or "")
        if not task_id:
            raise GenerationError("%s returned no task_id" % path)
        return task_id

    def task_status(self, task_id):
        data = self._request("GET", "tasks/%s" % task_id, label="task status")
        status = str(data.get("status") or "unknown").lower()
        output = _provider_mapping(data.get("output") or {}, label="Tripo task output")
        model_url = ""
        for key in ("pbr_model", "model", "model_url"):
            candidate = output.get(key)
            if isinstance(candidate, str) and candidate:
                model_url = candidate
                break
        return {
            "task_id": task_id,
            "status": status,
            "terminal": status in TERMINAL_STATUSES,
            "succeeded": status == TERMINAL_SUCCESS,
            "progress": _provider_progress(data.get("progress"), label="Tripo task progress"),
            "model_url": model_url,
            "credits_consumed": data.get("credits_consumed"),
            "created_at": data.get("created_at"),
            "output": output,
        }


class MeshyClient:
    """Client for Meshy's v1 image-to-3D and multi-image-to-3D APIs."""

    def __init__(self, api_key, *, base_url=MESHY_BASE_URL, transport=None, timeout=60):
        self._key = str(api_key or "").strip()
        if not self._key:
            raise GenerationError("Meshy API key is not configured")
        self.base_url = str(base_url or MESHY_BASE_URL).rstrip("/")
        self._transport = transport or _default_transport
        self.timeout = timeout
        self._task_paths = {}

    def _request(self, method, path, *, body=None, content_type="", label=""):
        url = "%s/%s" % (self.base_url, str(path).lstrip("/"))
        headers = {"Authorization": "Bearer %s" % self._key, "Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        status, text = self._transport(method, url, headers, body, self.timeout)
        payload = _json_response(
            text,
            label=label or path,
            status=status,
            secret=self._key,
        )
        if status >= 400:
            task_error = _task_error(payload)
            raise GenerationError(
                "%s failed (HTTP %s): %s"
                % (
                    label or path,
                    status,
                    _redact(_error_message(payload, text[:200]), self._key),
                ),
                code=int(status),
                insufficient_credit=(status == 402),
                retryable=(status == 429 or status >= 500),
                error_type=task_error.get("type") or "http_error",
                doc_url=task_error.get("doc_url") or "",
                details=task_error,
            )
        return payload

    def balance(self):
        data = self._request("GET", "balance", label="balance")
        try:
            return float(data.get("balance") or 0.0)
        except (TypeError, ValueError):
            raise GenerationError(
                "Meshy balance returned an invalid credit value",
                error_type="invalid_provider_response",
            ) from None

    def upload_image(self, image_path, *, expected_identity=None):
        """Return a data URI; Meshy accepts these directly as image URLs."""

        try:
            return image_data_uri(
                image_path,
                provider="meshy",
                expected_identity=expected_identity,
            )
        except (OSError, ValueError) as error:
            raise GenerationError(
                str(error),
                error_type="invalid_local_input",
            ) from None

    def _options(
        self,
        *,
        model="",
        face_limit=0,
        texture=None,
        meshy_options=None,
        view_count=1,
    ):
        try:
            normalized = generation_meshy.normalize_job_options(
                {
                    "meshy_options": meshy_options,
                    "model": model,
                    "face_limit": face_limit,
                    "texture": texture,
                },
                view_count=view_count,
            )
        except ValueError as error:
            raise GenerationError(str(error), error_type="validation_error") from None
        return generation_meshy.request_options(normalized, view_count=view_count)

    def create_image_task(
        self,
        file_token,
        image_path="",
        *,
        model="",
        face_limit=0,
        texture=None,
        meshy_options=None,
    ):
        body = {"image_url": file_token}
        body.update(
            self._options(
                model=model,
                face_limit=face_limit,
                texture=texture,
                meshy_options=meshy_options,
                view_count=1,
            )
        )
        data = self._request(
            "POST",
            "image-to-3d",
            body=json.dumps(body).encode("utf-8"),
            content_type="application/json",
            label="image-to-3d",
        )
        task_id = str(data.get("task_id") or data.get("id") or data.get("result") or "")
        if not task_id:
            raise GenerationError("image-to-3d returned no task_id")
        self._task_paths[task_id] = "image-to-3d"
        return task_id

    def create_multiview_task(
        self,
        views,
        *,
        model="",
        face_limit=0,
        texture=None,
        meshy_options=None,
    ):
        image_urls = []
        for slot in MULTIVIEW_SLOTS:
            entry = views.get(slot)
            if entry and entry[0]:
                image_urls.append(entry[0])
        for name in sorted(set(views) - set(MULTIVIEW_SLOTS)):
            entry = views.get(name)
            if entry and entry[0]:
                image_urls.append(entry[0])
        image_urls = image_urls[:4]
        if not image_urls:
            raise GenerationError("multi-image task needs at least one view")
        body = {"image_urls": image_urls}
        body.update(
            self._options(
                model=model,
                face_limit=face_limit,
                texture=texture,
                meshy_options=meshy_options,
                view_count=len(image_urls),
            )
        )
        data = self._request(
            "POST",
            "multi-image-to-3d",
            body=json.dumps(body).encode("utf-8"),
            content_type="application/json",
            label="multi-image-to-3d",
        )
        task_id = str(data.get("result") or data.get("task_id") or data.get("id") or "")
        if not task_id:
            raise GenerationError("multi-image-to-3d returned no task_id")
        self._task_paths[task_id] = "multi-image-to-3d"
        return task_id

    def task_status(self, task_id):
        path = self._task_path(task_id)
        data = self._request("GET", "%s/%s" % (path, task_id), label="task status")
        status = str(data.get("status") or "unknown").lower()
        message = _error_message(data, "")
        task_error = _task_error(data)
        return {
            "task_id": task_id,
            "status": status,
            "terminal": status in MESHY_TERMINAL_STATUSES,
            "succeeded": status == MESHY_TERMINAL_SUCCESS,
            "progress": _provider_progress(data.get("progress"), label="Meshy task progress"),
            "model_url": _model_url_from_payload(data),
            "credits_consumed": data.get("consumed_credits"),
            "created_at": data.get("created_at"),
            "started_at": data.get("started_at"),
            "finished_at": data.get("finished_at"),
            "expires_at": data.get("expires_at"),
            "preceding_tasks": data.get("preceding_tasks"),
            "error_message": message,
            "task_error": task_error,
            "artifact_urls": _meshy_artifact_urls(data),
            "output": data,
        }

    def _task_path(self, task_id, task_kind=""):
        kind = str(task_kind or "").strip().lower().replace("-", "_")
        if kind in {"multiview", "multi_image", "multiimage"}:
            return "multi-image-to-3d"
        if kind in {"image", "single_image", "single"}:
            return "image-to-3d"
        return self._task_paths.get(str(task_id), "image-to-3d")

    def cancel_task(self, task_id, *, task_kind=""):
        """Delete a pending or in-progress Meshy task at the provider."""

        task_id = str(task_id or "").strip()
        if not task_id:
            raise GenerationError("Meshy task cancellation requires a task_id")
        path = self._task_path(task_id, task_kind)
        self._request("DELETE", "%s/%s" % (path, task_id), label="task cancellation")
        return {
            "ok": True,
            "provider": "meshy",
            "task_id": task_id,
            "task_kind": "multiview" if path == "multi-image-to-3d" else "image",
            "message": "Meshy task cancelled at the provider",
        }


class StudioEndpointClient:
    """Client for a bridge-compatible self-hosted image-to-3D endpoint.

    The intentionally small contract is:

    - ``POST /image-to-3d`` with ``{"views": [{"name", "image_url"}], ...}``
      returns ``task_id``, ``id`` or ``result``.
    - ``GET /tasks/{task_id}`` returns a provider-neutral task object with
      ``status``, ``progress`` and either ``model_url`` or ``model_urls.glb``.
    - ``GET /balance`` is optional; if absent the worker continues.
    """

    def __init__(self, endpoint, *, api_key="", transport=None, timeout=60):
        self.base_url = str(endpoint or "").strip().rstrip("/")
        if not self.base_url:
            raise GenerationError("Studio generation endpoint is not configured")
        parsed = urllib.parse.urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise GenerationError("Studio generation endpoint must be an http(s) URL")
        if parsed.scheme == "http" and not _local_http_host(parsed.hostname):
            raise GenerationError(
                "Plain HTTP studio endpoints must use a local or private-network host"
            )
        self._key = str(api_key or "").strip()
        self._transport = transport or _default_local_transport
        self.timeout = timeout

    def _request(self, method, path, *, body=None, content_type="", label=""):
        url = "%s/%s" % (self.base_url, str(path).lstrip("/"))
        headers = {"Accept": "application/json"}
        if self._key:
            headers["Authorization"] = "Bearer %s" % self._key
        if content_type:
            headers["Content-Type"] = content_type
        status, text = self._transport(method, url, headers, body, self.timeout)
        payload = _json_response(
            text,
            label=label or path,
            status=status,
            secret=self._key,
        )
        if status >= 400:
            task_error = _task_error(payload)
            raise GenerationError(
                "%s failed (HTTP %s): %s"
                % (
                    label or path,
                    status,
                    _redact(_error_message(payload, text[:200]), self._key),
                ),
                code=int(status),
                insufficient_credit=(status == 402),
                retryable=(status == 429 or status >= 500),
                error_type=task_error.get("type") or "http_error",
                doc_url=task_error.get("doc_url") or "",
                details=task_error,
            )
        return payload

    def balance(self):
        data = self._request("GET", "balance", label="balance")
        return _provider_number(
            data.get("balance") if data.get("balance") is not None else data.get("credits"),
            label="Studio balance",
        )

    def upload_image(self, image_path, *, expected_identity=None):
        try:
            return image_data_uri(
                image_path,
                provider="studio_endpoint",
                expected_identity=expected_identity,
            )
        except (OSError, ValueError) as error:
            raise GenerationError(str(error), error_type="invalid_local_input") from None

    def _create_task(self, views, *, model="", face_limit=0, texture=None):
        ordered = []
        for slot in MULTIVIEW_SLOTS:
            entry = views.get(slot)
            if entry and entry[0]:
                ordered.append({"name": slot, "image_url": entry[0]})
        for name in sorted(set(views) - set(MULTIVIEW_SLOTS)):
            entry = views.get(name)
            if entry and entry[0]:
                ordered.append({"name": name, "image_url": entry[0]})
        if not ordered:
            raise GenerationError("studio generation needs at least one view")
        body = {"views": ordered}
        if model:
            body["model"] = str(model)
        if face_limit:
            body["face_limit"] = int(face_limit)
        if texture is not None:
            body["texture"] = bool(texture)
        data = self._request(
            "POST",
            STUDIO_DEFAULT_PATH,
            body=json.dumps(body).encode("utf-8"),
            content_type="application/json",
            label=STUDIO_DEFAULT_PATH,
        )
        task_id = str(data.get("task_id") or data.get("id") or data.get("result") or "")
        if not task_id:
            raise GenerationError("studio endpoint returned no task_id")
        return task_id

    def create_image_task(self, file_token, image_path="", *, model="", face_limit=0, texture=None):
        return self._create_task(
            {"front": (file_token, image_path)},
            model=model,
            face_limit=face_limit,
            texture=texture,
        )

    def create_multiview_task(self, views, *, model="", face_limit=0, texture=None):
        return self._create_task(
            views,
            model=model,
            face_limit=face_limit,
            texture=texture,
        )

    def task_status(self, task_id):
        data = self._request(
            "GET",
            "%s/%s" % (STUDIO_STATUS_PATH, task_id),
            label="task status",
        )
        status = str(data.get("status") or "unknown").lower()
        succeeded = status in {"success", "succeeded", "completed", "complete"}
        failed = status in {"failed", "canceled", "cancelled", "error"}
        progress = _provider_progress(
            data.get("progress"),
            label="Studio task progress",
            default=100 if succeeded else 0,
        )
        return {
            "task_id": task_id,
            "status": status,
            "terminal": succeeded or failed,
            "succeeded": succeeded,
            "progress": progress,
            "model_url": _model_url_from_payload(data),
            "credits_consumed": data.get("credits_consumed") or data.get("consumed_credits"),
            "created_at": data.get("created_at"),
            "error_message": _error_message(data, ""),
            "output": data,
        }
