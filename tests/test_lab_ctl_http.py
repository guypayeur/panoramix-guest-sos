"""Opt-in lab reserve-temporal ctl HTTP loopback — recorded/fake HTTP only.

No live Temporal. Default (env unset) stays inert. Does not close
runtime #70 / #78. Does not unlock cloud. Does not stamp north_star_done.
Not guest→mesh ctl.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from sos.errors import StubOnly
from sos.http import SosApp
from sos.jobs import EVENTS_SOURCE_DURABLE, PROGRESS_SOURCE_DURABLE, JobStore
from sos.lab_ctl import (
    APPLY_REL,
    ENV_RUNTIME_ROOT,
    LabReserveTemporalHook,
    lab_hook_from_env,
)
from sos.lab_ctl_http import (
    ENV_CTL_BEARER,
    ENV_CTL_HTTP,
    LabReserveTemporalHttpHook,
    ctl_http_base_from_env,
    http_hook_from_env,
    normalize_ctl_http_base,
)
from sos.runtime_hook import InertRuntimeHandoffHook, resolve_runtime_hook


CTL_ID = "cw_deadbeefdeadbeef"
LOOPBACK = "http://127.0.0.1:19215"


class _FakeHttp:
    """Recorded HTTP fixture — method/url/headers/body in, JSON out."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, str], bytes | None]] = []
        self.status = "running"
        self.paused = False
        self.canceled = False
        self.admitted: list[dict[str, str]] = []
        self.require_bearer = False
        self.fail_next = False

    def __call__(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> tuple[int, str]:
        self.calls.append((method, url, dict(headers), body))
        if self.require_bearer:
            auth = headers.get("Authorization") or ""
            if not auth.startswith("Bearer "):
                return 401, json.dumps({"ok": False, "error": "unauthorized"})
        if self.fail_next:
            self.fail_next = False
            return 500, json.dumps({"ok": False, "error": "boom"})
        parsed = urlsplit(url)
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            return 403, json.dumps({"ok": False, "error": "off loopback"})
        path = parsed.path
        query = parse_qs(parsed.query)
        payload = json.loads(body.decode("utf-8")) if body else {}
        if path == "/reserve-temporal/admit" and method == "POST":
            self.admitted.append(payload)
            self.status = "running"
            return 200, json.dumps(
                {
                    "ok": True,
                    "id": CTL_ID,
                    "handoff": {
                        "id": CTL_ID,
                        "kind": payload.get("kind", "job"),
                        "class": payload.get("class", "cpu"),
                        "payload_digest": payload.get("payload_digest", ""),
                        "status": "running",
                    },
                    "north_star_done": False,
                }
            )
        work_id = (query.get("id") or [""])[0]
        if work_id != CTL_ID:
            return 400, json.dumps({"ok": False, "error": "unknown id"})
        if path == "/reserve-temporal/status" and method == "GET":
            return 200, json.dumps(
                {
                    "ok": True,
                    "id": CTL_ID,
                    "handoff": {"id": CTL_ID, "status": self.status},
                    "ctl": "status",
                }
            )
        if path == "/reserve-temporal/progress" and method == "GET":
            return 200, json.dumps(
                {
                    "ok": True,
                    "id": CTL_ID,
                    "ctl": "progress",
                    "stage": 2,
                    "stages_total": 4,
                    "stages_completed": 2,
                    "fraction": 0.5,
                    "progress": {
                        "stage": 2,
                        "stages_total": 4,
                        "stages_completed": 2,
                        "fraction": 0.5,
                    },
                    "north_star_done": False,
                }
            )
        if path == "/reserve-temporal/events" and method == "GET":
            return 200, json.dumps(
                {
                    "ok": True,
                    "id": CTL_ID,
                    "ctl": "events",
                    "events": [
                        {
                            "ts": "2026-09-11T22:00:00Z",
                            "event": "admit",
                            "type": "WorkflowExecutionStarted",
                        },
                        {
                            "ts": "2026-09-11T22:00:01Z",
                            "event": "stage_completed",
                            "type": "StageCompleted",
                        },
                    ],
                    "n": 2,
                    "durable": True,
                    "siem": False,
                    "north_star_done": False,
                }
            )
        if path == "/reserve-temporal/pause" and method == "POST":
            if self.status != "running":
                return 400, json.dumps({"ok": False, "error": "not running"})
            self.status = "paused"
            self.paused = True
            return 200, json.dumps({"ok": True, "id": CTL_ID, "ctl": "pause"})
        if path == "/reserve-temporal/resume" and method == "POST":
            if self.status != "paused":
                return 400, json.dumps({"ok": False, "error": "not paused"})
            self.status = "running"
            return 200, json.dumps({"ok": True, "id": CTL_ID, "ctl": "resume"})
        if path == "/reserve-temporal/cancel" and method == "POST":
            self.status = "canceled"
            self.canceled = True
            return 200, json.dumps({"ok": True, "id": CTL_ID, "ctl": "cancel"})
        return 404, json.dumps({"ok": False, "error": path})


def _fake_root() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="sos-lab-http-"))
    apply_py = tmp / APPLY_REL
    apply_py.parent.mkdir(parents=True)
    apply_py.write_text("# fake runtime.apply for opt-in probe\n", encoding="utf-8")
    return tmp


class FailClosedTests(unittest.TestCase):
    def test_resolve_without_env_is_inert(self) -> None:
        self.assertIsNone(ctl_http_base_from_env({}))
        self.assertIsNone(http_hook_from_env({}))
        hook = resolve_runtime_hook({})
        self.assertIsInstance(hook, InertRuntimeHandoffHook)
        self.assertIsNone(hook.admit({"kind": "job"}, None))
        self.assertIs(hook.pause("id", None), False)
        self.assertIsNone(hook.progress("id", None))
        self.assertIsNone(hook.events("id", None))

    def test_non_loopback_fails_closed(self) -> None:
        for raw in (
            "http://8.8.8.8:19215",
            "http://0.0.0.0:19215",
            "http://192.168.1.9:19215",
            "https://127.0.0.1:19215",
            "http://example.com:19215",
            "http://127.0.0.1:19215/reserve-temporal",
            "http://127.0.0.1:19215?x=1",
            "not-a-url",
            "",
        ):
            self.assertIsNone(normalize_ctl_http_base(raw), raw)
            self.assertIsNone(http_hook_from_env({ENV_CTL_HTTP: raw}), raw)
            self.assertIsInstance(resolve_runtime_hook({ENV_CTL_HTTP: raw}), InertRuntimeHandoffHook)

    def test_loopback_origins_normalize(self) -> None:
        self.assertEqual(normalize_ctl_http_base(LOOPBACK), LOOPBACK)
        self.assertEqual(
            normalize_ctl_http_base("http://127.0.0.1:19215/"),
            LOOPBACK,
        )
        self.assertEqual(
            normalize_ctl_http_base("http://localhost:19215"),
            "http://localhost:19215",
        )
        self.assertEqual(normalize_ctl_http_base("http://[::1]:19215"), "http://[::1]:19215")

    def test_default_store_and_http_stay_stub(self) -> None:
        store = JobStore(step_seconds=0.02)
        self.assertIsInstance(store.runtime_hook, InertRuntimeHandoffHook)
        job = store.submit({"demo": "sleep", "seconds": 8})
        self.assertEqual(job.local["backed"], "stub")
        with self.assertRaises(StubOnly):
            store.pause(job.id)
        store.cancel(job.id)

        app = SosApp(JobStore(step_seconds=0.02))
        created = app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "sleep", "seconds": 8}).encode(),
        )
        body = json.loads(created.body.decode("utf-8"))
        self.assertEqual(body["local"]["backed"], "stub")
        pause = app.handle("POST", f"/v0/jobs/{body['id']}/pause")
        self.assertEqual(pause.status, 409)
        self.assertEqual(json.loads(pause.body.decode("utf-8"))["error"], "stub_only")
        app.handle("POST", f"/v0/jobs/{body['id']}/cancel")


class OptInFakeHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.http = _FakeHttp()
        self.hook = LabReserveTemporalHttpHook(LOOPBACK, transport=self.http)
        self.store = JobStore(step_seconds=0.02, runtime_hook=self.hook)

    def test_http_hook_from_env_when_loopback(self) -> None:
        env = {ENV_CTL_HTTP: LOOPBACK}
        self.assertEqual(ctl_http_base_from_env(env), LOOPBACK)
        hook = http_hook_from_env(env, transport=self.http)
        self.assertIsInstance(hook, LabReserveTemporalHttpHook)
        resolved = resolve_runtime_hook(env)
        self.assertIsInstance(resolved, LabReserveTemporalHttpHook)
        self.assertFalse(resolved.live)
        self.assertIsNone(resolved.bearer)

    def test_http_preferred_over_subprocess_root(self) -> None:
        root = _fake_root()
        env = {ENV_CTL_HTTP: LOOPBACK, ENV_RUNTIME_ROOT: str(root)}
        self.assertIsInstance(resolve_runtime_hook(env), LabReserveTemporalHttpHook)
        self.assertIsInstance(lab_hook_from_env(env), LabReserveTemporalHook)

    def test_bearer_and_live_are_opt_in(self) -> None:
        env = {
            ENV_CTL_HTTP: LOOPBACK,
            ENV_CTL_BEARER: "lab-token",
            "PANORAMIX_RESERVE_TEMPORAL_LIVE": "1",
        }
        hook = http_hook_from_env(env, transport=self.http)
        self.assertEqual(hook.bearer, "lab-token")
        self.assertTrue(hook.live)

    def test_admit_status_pause_resume_progress_events_cancel(self) -> None:
        job = self.store.submit({"demo": "reserve", "seconds": 8})
        self.assertEqual(job.local["backed"], "runtime")
        self.assertEqual(job.status, "running")
        self.assertIs(job.to_dict()["pause_resume"], True)
        self.assertEqual(job.runtime_ref["id"], CTL_ID)
        self.assertEqual(job.runtime_ref["ctl"], "reserve-temporal")
        self.assertNotIn("workflow_id", job.runtime_ref)
        self.assertNotIn("task_queue", job.runtime_ref)
        self.assertEqual(len(self.http.admitted), 1)
        self.assertEqual(self.http.admitted[0]["kind"], "job")
        self.assertNotIn("payload", self.http.admitted[0])
        method, url, headers, body = self.http.calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(url.startswith("http://127.0.0.1:19215/reserve-temporal/admit"))
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertNotIn("Authorization", headers)
        self.assertIn(b'"kind":"job"', body or b"")

        progress = self.store.progress(job.id)
        self.assertEqual(progress["source"], PROGRESS_SOURCE_DURABLE)
        self.assertEqual(progress["stages_completed"], 2)
        self.assertEqual(progress["fraction"], 0.5)
        self.assertIn("path-slices", progress["note"].lower())

        events = self.store.events(job.id)
        self.assertEqual(events["source"], EVENTS_SOURCE_DURABLE)
        self.assertIs(events["events_durable"], True)
        self.assertEqual(events["events_n"], 2)
        self.assertEqual(
            [item["event"] for item in events["events"]],
            ["admit", "stage_completed"],
        )
        self.assertIn("not a siem", events["note"].lower())

        paused = self.store.pause(job.id)
        self.assertEqual(paused.status, "paused")
        self.assertTrue(self.http.paused)

        resumed = self.store.resume(job.id)
        self.assertEqual(resumed.status, "running")

        canceled = self.store.cancel(job.id)
        self.assertEqual(canceled.status, "canceled")
        self.assertTrue(self.http.canceled)
        paths = [urlsplit(call[1]).path for call in self.http.calls]
        self.assertIn("/reserve-temporal/pause", paths)
        self.assertIn("/reserve-temporal/resume", paths)
        self.assertIn("/reserve-temporal/cancel", paths)
        self.assertIn("/reserve-temporal/progress", paths)
        self.assertIn("/reserve-temporal/events", paths)
        self.assertIn("/reserve-temporal/status", paths)

    def test_http_opt_in_fake_ctl(self) -> None:
        app = SosApp(self.store)
        created = app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "seconds": 8}).encode(),
        )
        self.assertEqual(created.status, 201)
        job = json.loads(created.body.decode("utf-8"))
        self.assertEqual(job["local"]["backed"], "runtime")
        self.assertIs(job["pause_resume"], True)
        job_id = job["id"]

        paused = app.handle("POST", f"/v0/jobs/{job_id}/pause")
        self.assertEqual(paused.status, 200)
        self.assertEqual(json.loads(paused.body.decode("utf-8"))["status"], "paused")

        progress = json.loads(
            app.handle("GET", f"/v0/jobs/{job_id}/progress").body.decode("utf-8")
        )
        self.assertEqual(progress["source"], "durable")
        self.assertEqual(progress["stages_total"], 4)

        trail = json.loads(
            app.handle("GET", f"/v0/jobs/{job_id}/events").body.decode("utf-8")
        )
        self.assertEqual(trail["source"], "durable")
        self.assertIn("not a siem", trail["note"].lower())

        resumed = app.handle("POST", f"/v0/jobs/{job_id}/resume")
        self.assertEqual(json.loads(resumed.body.decode("utf-8"))["status"], "running")
        canceled = app.handle("POST", f"/v0/jobs/{job_id}/cancel")
        self.assertEqual(json.loads(canceled.body.decode("utf-8"))["status"], "canceled")

    def test_bearer_sent_when_configured(self) -> None:
        self.http.require_bearer = True
        hook = LabReserveTemporalHttpHook(
            LOOPBACK, transport=self.http, bearer="secret"
        )
        store = JobStore(step_seconds=0.02, runtime_hook=hook)
        job = store.submit({"demo": "reserve", "seconds": 8})
        self.assertEqual(job.local["backed"], "runtime")
        self.assertEqual(self.http.calls[0][2]["Authorization"], "Bearer secret")

    def test_missing_bearer_fails_closed_to_stub(self) -> None:
        self.http.require_bearer = True
        hook = LabReserveTemporalHttpHook(LOOPBACK, transport=self.http)
        store = JobStore(step_seconds=0.02, runtime_hook=hook)
        job = store.submit({"demo": "echo", "message": "fallback"})
        self.assertEqual(job.local["backed"], "stub")
        with self.assertRaises(StubOnly):
            store.pause(job.id)

    def test_ctl_failure_fails_closed_to_stub(self) -> None:
        self.http.fail_next = True
        hook = LabReserveTemporalHttpHook(LOOPBACK, transport=self.http)
        store = JobStore(step_seconds=0.02, runtime_hook=hook)
        job = store.submit({"demo": "echo", "message": "fallback"})
        self.assertEqual(job.local["backed"], "stub")
        with self.assertRaises(StubOnly):
            store.pause(job.id)

    def test_constructor_rejects_non_loopback(self) -> None:
        with self.assertRaises(ValueError):
            LabReserveTemporalHttpHook("http://10.0.0.2:19215")


class LoopbackServerTests(unittest.TestCase):
    """One real stdlib loopback listen — still recorded, no Temporal."""

    def test_urllib_talks_loopback_shape(self) -> None:
        state = {"status": "running", "admitted": 0}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: object) -> None:
                return

            def do_POST(self) -> None:
                parsed = urlsplit(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                if parsed.path != "/reserve-temporal/admit":
                    self._json(404, {"ok": False, "error": "not found"})
                    return
                payload = json.loads(raw.decode("utf-8")) if raw else {}
                state["admitted"] += 1
                self._json(
                    200,
                    {
                        "ok": True,
                        "id": CTL_ID,
                        "handoff": {
                            "id": CTL_ID,
                            "kind": payload.get("kind", "job"),
                            "class": payload.get("class", "cpu"),
                            "payload_digest": payload.get("payload_digest", ""),
                            "status": "running",
                        },
                        "north_star_done": False,
                    },
                )

            def do_GET(self) -> None:
                parsed = urlsplit(self.path)
                query = parse_qs(parsed.query)
                if parsed.path != "/reserve-temporal/status":
                    self._json(404, {"ok": False, "error": "not found"})
                    return
                if (query.get("id") or [""])[0] != CTL_ID:
                    self._json(400, {"ok": False, "error": "unknown id"})
                    return
                self._json(
                    200,
                    {
                        "ok": True,
                        "id": CTL_ID,
                        "handoff": {"id": CTL_ID, "status": state["status"]},
                    },
                )

            def _json(self, code: int, obj: dict) -> None:
                body = json.dumps(obj).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            hook = LabReserveTemporalHttpHook(f"http://{host}:{port}")
            admitted = hook.admit(
                {
                    "kind": "job",
                    "class": "cpu",
                    "payload_digest": "sha256:" + "ab" * 32,
                    "status": "queued",
                },
                None,
            )
            self.assertEqual(admitted, {"id": CTL_ID, "ctl": "reserve-temporal"})
            self.assertEqual(state["admitted"], 1)
            self.assertEqual(hook.status(CTL_ID, admitted), "running")
        finally:
            server.shutdown()
            server.server_close()


class HonestyTests(unittest.TestCase):
    def test_honesty_comments(self) -> None:
        text = Path(__file__).resolve().parents[1].joinpath(
            "sos/lab_ctl_http.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Does not close runtime #70", text)
        self.assertIn("Does not close #78", text)
        self.assertIn("Does not unlock", text)
        self.assertIn("north_star_done", text)
        self.assertIn("Cloud stays locked", text)
        self.assertIn("fail closed", text)
        self.assertIn("Not guest→mesh ctl", text)
        self.assertIn("PANORAMIX_CTL_HTTP", text)
        self.assertIn("fb901542", text)
        self.assertNotIn("Fixes #70", text)
        self.assertNotIn("Fixes #78", text)
        imports = [
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        blob = "\n".join(imports)
        self.assertNotIn("from runtime", blob)
        self.assertNotIn("import runtime", blob)
        self.assertNotIn("subprocess", blob)
        self.assertIn("urllib", blob)


if __name__ == "__main__":
    unittest.main()
