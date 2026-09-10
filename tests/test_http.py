"""HTTP dispatcher tests — SosApp.handle, no listening sockets."""

from __future__ import annotations

import json
import time
import unittest

from pathlib import Path

from platform_run import parse_listen
from sos.handoff import digest_canonical
from sos.http import INFO_PAYLOAD, SosApp
from sos.jobs import JobStore


def _json(resp) -> dict:
    return json.loads(resp.body.decode("utf-8"))


def _digest(hex_byte: str = "ab") -> str:
    return "sha256:" + hex_byte * 32


def wait_http_status(app: SosApp, job_id: str, wanted: set[str], timeout: float = 2.0) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        resp = app.handle("GET", f"/v0/jobs/{job_id}")
        last = _json(resp)
        if last.get("status") in wanted:
            return last
        time.sleep(0.02)
    raise AssertionError(f"job stayed {last!r}, wanted {wanted}")


class ParseListenTests(unittest.TestCase):
    def test_shapes(self) -> None:
        self.assertEqual(parse_listen("18280"), ("127.0.0.1", 18280))
        self.assertEqual(parse_listen(":18280"), ("0.0.0.0", 18280))
        self.assertEqual(parse_listen("0.0.0.0:18280"), ("0.0.0.0", 18280))


class HttpAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = SosApp(JobStore(step_seconds=0.02))

    def test_health_and_info(self) -> None:
        health = self.app.handle("GET", "/health")
        self.assertEqual(health.status, 200)
        self.assertEqual(_json(health), {"status": "ok"})

        info = self.app.handle("GET", "/v0/info")
        self.assertEqual(info.status, 200)
        body = _json(info)
        self.assertEqual(body["status"], "day-one")
        self.assertNotEqual(body["status"], "skeleton")
        self.assertIs(body["iec_equivalent"], False)
        self.assertEqual(body["engines"], "runtime-bindings-only")
        self.assertEqual(body["kind"], INFO_PAYLOAD["kind"])
        self.assertEqual(body["jobs"]["kinds"], ["chunk", "job", "stage"])
        self.assertEqual(body["jobs"]["classes"], ["cpu", "gpu"])
        self.assertEqual(body["jobs"]["statuses"], ["queued", "running", "succeeded", "failed", "canceled"])
        self.assertNotIn("accepted", body["jobs"]["statuses"])
        self.assertNotIn("cancelled", body["jobs"]["statuses"])
        blob = json.dumps(body)
        self.assertNotIn("ray://", blob)
        self.assertNotIn("temporal://", blob)
        self.assertNotIn("sos.demo.echo", blob)

    def test_ui_pages(self) -> None:
        for path in ("/", "/ui"):
            resp = self.app.handle("GET", path)
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.content_type)
            html = resp.body.decode("utf-8")
            self.assertIn("SoS operator", html)
            self.assertIn("/v0/jobs", html)
            self.assertIn("Cancel", html)
            self.assertIn('value="echo"', html)
            self.assertIn('value="sleep"', html)
            self.assertIn("payload_digest", html)
            self.assertIn("canceled", html)
            self.assertNotIn("cancelled", html)
            self.assertNotIn("sos.demo.echo", html)
            self.assertNotIn("ray://", html)
            self.assertNotIn("temporal://", html)

    def test_submit_list_get_opaque(self) -> None:
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps(
                {"kind": "job", "class": "cpu", "payload_digest": _digest()}
            ).encode(),
        )
        self.assertEqual(created.status, 201)
        job = _json(created)
        self.assertEqual(job["kind"], "job")
        self.assertEqual(job["class"], "cpu")
        self.assertEqual(job["payload_digest"], _digest())
        self.assertEqual(job["status"], "queued")
        self.assertIn("Location", created.headers or {})
        self.assertTrue(created.headers["Location"].endswith(job["id"]))

        listed = _json(self.app.handle("GET", "/v0/jobs"))
        self.assertEqual(listed["jobs"][0]["id"], job["id"])

        got = self.app.handle("GET", f"/v0/jobs/{job['id']}")
        self.assertEqual(got.status, 200)
        self.assertEqual(_json(got)["id"], job["id"])

        done = wait_http_status(self.app, job["id"], {"succeeded"})
        self.assertIn("opaque", done["message"])
        self.assertNotIn("engine", done)
        self.assertNotIn("ray", done)

    def test_submit_demo_echo(self) -> None:
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "echo", "message": "hi"}).encode(),
        )
        self.assertEqual(created.status, 201)
        job = _json(created)
        self.assertEqual(job["kind"], "job")
        self.assertEqual(job["class"], "cpu")
        self.assertEqual(job["payload_digest"], digest_canonical({"demo": "echo", "message": "hi"}))
        self.assertEqual(job["local"]["demo"], "echo")
        done = wait_http_status(self.app, job["id"], {"succeeded"})
        self.assertEqual(done["message"], "hi")

    def test_bad_kind(self) -> None:
        resp = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps(
                {"kind": "sos.demo.unknown", "class": "cpu", "payload_digest": _digest()}
            ).encode(),
        )
        self.assertEqual(resp.status, 400)
        body = _json(resp)
        self.assertEqual(body["error"], "invalid_kind")
        self.assertIn("error", body)

    def test_bad_class_and_digest(self) -> None:
        bad_class = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps(
                {"kind": "job", "class": "tpu", "payload_digest": _digest()}
            ).encode(),
        )
        self.assertEqual(bad_class.status, 400)
        self.assertEqual(_json(bad_class)["error"], "invalid_class")

        bad_digest = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps(
                {"kind": "job", "class": "cpu", "payload_digest": "not-a-digest"}
            ).encode(),
        )
        self.assertEqual(bad_digest.status, 400)
        self.assertEqual(_json(bad_digest)["error"], "invalid_digest")

    def test_engine_smuggle_rejected(self) -> None:
        probes = [
            {"kind": "job", "class": "cpu", "payload_digest": _digest(), "engine_kind": "x"},
            {"kind": "job", "class": "cpu", "payload_digest": _digest(), "payload": {}},
            {"kind": "job", "class": "cpu", "payload_digest": "s3://bucket/key"},
            {"kind": "job", "class": "cpu", "payload_digest": _digest(), "url": "cluster"},
            {"kind": "ray://127.0.0.1:10001", "class": "cpu", "payload_digest": _digest()},
        ]
        for raw in probes:
            with self.subTest(raw=raw):
                resp = self.app.handle("POST", "/v0/jobs", json.dumps(raw).encode())
                self.assertEqual(resp.status, 400)
                self.assertEqual(_json(resp)["error"], "engine_smuggle")

    def test_missing_job(self) -> None:
        resp = self.app.handle("GET", "/v0/jobs/not-a-job")
        self.assertEqual(resp.status, 404)
        self.assertEqual(_json(resp)["error"], "not_found")

    def test_cancel_sleep(self) -> None:
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "sleep", "seconds": 8}).encode(),
        )
        job_id = _json(created)["id"]
        canceled = self.app.handle("POST", f"/v0/jobs/{job_id}/cancel")
        self.assertEqual(canceled.status, 200)
        self.assertEqual(_json(canceled)["status"], "canceled")
        self.assertNotEqual(_json(canceled)["status"], "cancelled")

    def test_cancel_terminal_conflict(self) -> None:
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "echo", "message": "x"}).encode(),
        )
        job_id = _json(created)["id"]
        wait_http_status(self.app, job_id, {"succeeded"})
        conflict = self.app.handle("POST", f"/v0/jobs/{job_id}/cancel")
        self.assertEqual(conflict.status, 409)
        self.assertEqual(_json(conflict)["error"], "already_terminal")

    def test_cancel_missing(self) -> None:
        resp = self.app.handle("POST", "/v0/jobs/missing/cancel")
        self.assertEqual(resp.status, 404)

    def test_invalid_json(self) -> None:
        resp = self.app.handle("POST", "/v0/jobs", b"{")
        self.assertEqual(resp.status, 400)
        self.assertEqual(_json(resp)["error"], "invalid_json")

    def test_unit_yaml_has_no_engine_fields(self) -> None:
        text = Path(__file__).resolve().parents[1].joinpath(".platform/contract.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn('contract_version: "0.5"', text)
        for needle in ("image:", "ray:", "temporal:", "aws:"):
            self.assertNotIn(needle, text)


if __name__ == "__main__":
    unittest.main()
