"""Public HTTP surface for the SoS guest (health, jobs API, operator UI).

Served on the Unit public port. JSON errors are `{"error": ..., ...}`.
No engine URL schemes in request or response bodies. Ctl exports
``GET /v0/jobs/{id}/handoff`` (WorkHandoff projection, no nested payload)
and ``GET /v0/jobs/{id}/payload`` (canonical JSON bytes as hex/utf8).
Transport is operator/ctl-mediated: no guest→ctl HTTP, no
``runtime.apply compute-work`` from this guest.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from sos.errors import SosError
from sos.handoff_vocab import (
    LOCAL_DEMOS,
    PARITY_PAYLOAD_DIGEST,
    RECORDED_PAYLOAD_DIGEST,
    RESOURCE_CLASSES,
    WORK_KINDS,
    WORK_STATUSES,
)
from sos.jobs import JobStore
from sos.ui import OPERATOR_HTML

MAX_BODY = 64 * 1024
HEALTH_PAYLOAD = {"status": "ok"}
INFO_PAYLOAD = {
    "name": "sos",
    "product": "panoramix-guest-sos",
    "kind": "actuarial-guest",
    "contract_version": "0.5",
    "status": "day-one",
    "iec_equivalent": False,
    "engines": "runtime-bindings-only",
    "jobs": {
        "kinds": sorted(WORK_KINDS),
        "classes": sorted(RESOURCE_CLASSES),
        "statuses": list(WORK_STATUSES),
        "handoff": ["kind", "class", "payload_digest"],
        "local_demo": sorted(LOCAL_DEMOS),
        "ux_seed": (
            "reserve is a stub lifecycle for operator UX; "
            "not a perf baseline until runtime #83 + remeasure"
        ),
        "iec_named_baseline": "grammar/examples/reserve_ifrs17",
        "reserve_payload_keys": [
            "accounts",
            "discount_bps",
            "horizon",
            "lapse_bps",
            "paths",
            "seed",
            "workload",
        ],
        "reserve_catalogs": ["recorded", "live", "parity"],
        "reserve_digest_recorded": RECORDED_PAYLOAD_DIGEST,
        "reserve_digest_parity": PARITY_PAYLOAD_DIGEST,
        "runtime_reserve": "docs/reserve.md",
        "runtime_reserve_helpers": [
            "runtime.reserve.digest_for",
            "runtime.reserve.recorded_params",
            "runtime.reserve.live_params",
            "runtime.reserve.parity_params",
        ],
        "runtime_reserve_parity": "runtime.reserve.parity_params",
        "ctl_handoff": {
            "mode": "operator-ctl",
            "guest_to_ctl_http": False,
            "guest_callable_submit": False,
            "handoff": "GET /v0/jobs/{id}/handoff",
            "payload": "GET /v0/jobs/{id}/payload",
            "mesh": "compute-job -> sos",
            "note": (
                "Transport is operator/ctl-mediated. Guest UX is "
                "submit/status/cancel. Emit WorkHandoff JSON only — no "
                "guest→ctl HTTP, no runtime.apply compute-work, no env "
                "that adds mesh destinations. Stub is the fallback; "
                "operator/ctl admits via the binding. "
                "Not a perf baseline until runtime #83 + remeasure. Not #70 Done."
            ),
        },
        "progress": "GET /v0/jobs/{id}/progress",
        "events": "GET /v0/jobs/{id}/events",
        "progress_honesty": "stub stage metadata; not iec chunk progress",
        "events_honesty": "local event trail; not a regulatory audit",
        "pause_resume": False,
        "cancel_note": (
            "No pause/resume. Cancel ends a live run (canceled). "
            "Stub-backed cancel is local; runtime-backed cancel signals "
            "the injected hook, then marks the guest job canceled if still live."
        ),
    },
    "ui": "/",
}

_JOB_RE = re.compile(r"^/v0/jobs/([^/]+)$")
_CANCEL_RE = re.compile(r"^/v0/jobs/([^/]+)/cancel$")
_HANDOFF_RE = re.compile(r"^/v0/jobs/([^/]+)/handoff$")
_PAYLOAD_RE = re.compile(r"^/v0/jobs/([^/]+)/payload$")
_PROGRESS_RE = re.compile(r"^/v0/jobs/([^/]+)/progress$")
_EVENTS_RE = re.compile(r"^/v0/jobs/([^/]+)/events$")


@dataclass
class HttpResponse:
    status: int
    body: bytes
    content_type: str = "application/json"
    headers: dict[str, str] | None = None


def _json_response(status: int, payload: Any, extra_headers: dict[str, str] | None = None) -> HttpResponse:
    body = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    return HttpResponse(status=status, body=body, content_type="application/json", headers=extra_headers)


def _html_response(html: str) -> HttpResponse:
    body = html.encode("utf-8")
    return HttpResponse(status=200, body=body, content_type="text/html; charset=utf-8")


def _read_json_object(body: bytes) -> dict[str, Any]:
    if not body or not body.strip():
        raise SosError("invalid_json", detail="request body is required")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SosError("invalid_json", detail=str(exc)) from exc
    if not isinstance(payload, dict):
        raise SosError("invalid_json", detail="body must be a JSON object")
    return payload


class SosApp:
    """Dispatch table used by the HTTP handler and by tests (no sockets)."""

    def __init__(self, store: JobStore | None = None) -> None:
        self.store = store or JobStore()

    def handle(self, method: str, path: str, body: bytes = b"") -> HttpResponse:
        method = method.upper()
        path = urlsplit(path).path or "/"
        try:
            return self._route(method, path, body)
        except SosError as err:
            return _json_response(err.http_status, err.to_dict())

    def _route(self, method: str, path: str, body: bytes) -> HttpResponse:
        if path == "/health":
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, HEALTH_PAYLOAD)
        if path == "/v0/info":
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, INFO_PAYLOAD)
        if path in ("/", "/ui"):
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _html_response(OPERATOR_HTML)
        if path == "/v0/jobs":
            if method == "GET":
                return _json_response(200, {"jobs": [j.to_dict() for j in self.store.list()]})
            if method == "POST":
                return self._create_job(body)
            return _json_response(405, {"error": "method_not_allowed", "path": path})
        cancel = _CANCEL_RE.match(path)
        if cancel:
            if method != "POST":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            job = self.store.cancel(cancel.group(1))
            return _json_response(200, job.to_dict())
        handoff = _HANDOFF_RE.match(path)
        if handoff:
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, self.store.handoff(handoff.group(1)))
        payload = _PAYLOAD_RE.match(path)
        if payload:
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, self.store.payload(payload.group(1)))
        progress = _PROGRESS_RE.match(path)
        if progress:
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, self.store.progress(progress.group(1)))
        events = _EVENTS_RE.match(path)
        if events:
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, self.store.events(events.group(1)))
        job_match = _JOB_RE.match(path)
        if job_match:
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            job = self.store.get(job_match.group(1))
            return _json_response(200, job.to_dict())
        return _json_response(404, {"error": "not_found", "path": path})

    def _create_job(self, body: bytes) -> HttpResponse:
        payload = _read_json_object(body)
        job = self.store.submit(payload)
        return _json_response(
            201,
            job.to_dict(),
            extra_headers={"Location": f"/v0/jobs/{job.id}"},
        )


class SosServer(ThreadingHTTPServer):
    allow_reuse_address = True


def bind_handler(app: SosApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: object) -> None:
            print("%s - %s" % (self.address_string(), fmt % args), flush=True)

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

        def _dispatch(self, method: str) -> None:
            length_raw = self.headers.get("Content-Length") or "0"
            try:
                length = int(length_raw)
            except ValueError:
                self._write(_json_response(400, {"error": "invalid_json", "detail": "bad Content-Length"}))
                return
            if length < 0 or length > MAX_BODY:
                self._write(_json_response(413, {"error": "payload_too_large"}))
                return
            body = self.rfile.read(length) if length else b""
            path = self.path.split("?", 1)[0]
            self._write(app.handle(method, path, body))

        def _write(self, resp: HttpResponse) -> None:
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.content_type)
            self.send_header("Content-Length", str(len(resp.body)))
            self.send_header("Connection", "close")
            if resp.headers:
                for key, value in resp.headers.items():
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(resp.body)

    return Handler
