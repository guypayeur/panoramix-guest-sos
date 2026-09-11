"""HTTP dispatcher tests — SosApp.handle, no listening sockets."""

from __future__ import annotations

import json
import time
import unittest

from pathlib import Path

from platform_run import parse_listen
from sos.handoff import digest_canonical, digest_bytes
from sos.handoff_vocab import (
    PARITY_PAYLOAD_DIGEST,
    RECORDED_CANONICAL_JSON,
    RECORDED_PAYLOAD_DIGEST,
)
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
        self.assertEqual(body["jobs"]["local_demo"], ["echo", "reserve", "sleep"])
        self.assertIn("stub", body["jobs"]["ux_seed"])
        self.assertEqual(body["jobs"]["iec_named_baseline"], "grammar/examples/reserve_ifrs17")
        self.assertEqual(body["jobs"]["reserve_digest_recorded"], RECORDED_PAYLOAD_DIGEST)
        self.assertEqual(
            body["jobs"]["reserve_digest_recorded"],
            "sha256:77e9299f4b8ea4aeed46f71b91cc947d56e9bd169d795e70845123fef53d7e4e",
        )
        self.assertEqual(body["jobs"]["runtime_reserve"], "docs/reserve.md")
        self.assertEqual(
            body["jobs"]["runtime_reserve_helpers"],
            [
                "runtime.reserve.digest_for",
                "runtime.reserve.recorded_params",
                "runtime.reserve.live_params",
                "runtime.reserve.parity_params",
            ],
        )
        self.assertEqual(body["jobs"]["reserve_catalogs"], ["recorded", "live", "parity"])
        self.assertEqual(
            body["jobs"]["reserve_digest_parity"],
            "sha256:e180d2c2e3589b8762f92efa1bedb3d53ffeeb16648581ba13d537bcd3311102",
        )
        self.assertEqual(body["jobs"]["runtime_reserve_parity"], "runtime.reserve.parity_params")
        self.assertIn("workload", body["jobs"]["reserve_payload_keys"])
        ctl = body["jobs"]["ctl_handoff"]
        self.assertEqual(ctl["mode"], "operator-ctl")
        self.assertIs(ctl["guest_to_ctl_http"], False)
        self.assertIs(ctl["guest_callable_submit"], False)
        self.assertNotIn("awaiting_runtime_stamp", ctl)
        self.assertIn("handoff", ctl["handoff"])
        self.assertIn("payload", ctl["payload"])
        self.assertEqual(ctl["mesh"], "compute-job -> sos")
        self.assertNotIn("PLATFORM_COMPUTE", json.dumps(ctl))
        self.assertNotIn("PLATFORM_RAY", json.dumps(ctl))
        self.assertNotIn("PLATFORM_MESH", json.dumps(ctl))
        self.assertIn("runtime.apply compute-work", ctl["note"])
        self.assertIn("guest→ctl HTTP", ctl["note"])
        self.assertIn("operator/ctl", ctl["note"])
        self.assertIn("Stub is the fallback", ctl["note"])
        self.assertIn("not a perf baseline until runtime #83", ctl["note"].lower())
        self.assertIn("Not #70 Done", ctl["note"])
        self.assertNotIn("never calls", ctl["note"])
        self.assertEqual(body["jobs"]["progress"], "GET /v0/jobs/{id}/progress")
        self.assertEqual(body["jobs"]["events"], "GET /v0/jobs/{id}/events")
        self.assertIs(body["jobs"]["pause_resume"], False)
        self.assertIn("not iec chunk progress", body["jobs"]["progress_honesty"])
        self.assertIn("not a regulatory audit", body["jobs"]["events_honesty"])
        self.assertIn("No pause/resume", body["jobs"]["cancel_note"])
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
            self.assertIn('value="reserve"', html)
            self.assertIn("Reserve (shaped)", html)
            self.assertIn("Stub / UX seed only", html)
            self.assertIn("reserve_ifrs17", html)
            self.assertIn("not</strong> a performance baseline", html)
            self.assertIn("payload_digest", html)
            self.assertIn("compute_work.py", html)
            self.assertNotIn("runtime#73", html)
            self.assertIn("canceled", html)
            self.assertNotIn("cancelled", html)
            self.assertNotIn("sos.demo.echo", html)
            self.assertNotIn("ray://", html)
            self.assertNotIn("temporal://", html)
            self.assertIn("/v0/jobs/{id}/handoff", html)
            self.assertIn("/payload", html)
            self.assertIn("compute-job", html)
            self.assertIn("Stub fallback", html)
            self.assertIn("operator binding path", html)
            self.assertIn("operator/ctl-mediated", html)
            self.assertIn("runtime.apply compute-work", html)
            self.assertIn("guest→ctl HTTP", html)
            self.assertIn("#83 + remeasure", html)
            self.assertIn("runtime #70 Done", html)
            self.assertIn("not</strong> runtime #70 Done", html)
            self.assertNotIn("awaiting a platform-stamped", html)
            self.assertIn("docs/reserve.md", html)
            self.assertIn("digest_for", html)
            self.assertIn("recorded_params", html)
            self.assertIn('value="recorded"', html)
            self.assertIn('value="parity"', html)
            self.assertIn("parity-scale", html)
            self.assertNotIn("north-star Done", html)
            self.assertIn("Job detail", html)
            self.assertIn("Local event trail", html)
            self.assertIn("View/copy handoff", html)
            self.assertIn("Fetch payload", html)
            self.assertIn("no pause / resume", html)
            self.assertIn("not iec chunk progress", html)
            self.assertIn("not a regulatory audit", html)
            self.assertIn("docs/ux-side-by-side.md", html)
            self.assertIn("End run (canceled)", html)
            self.assertIn("Stub-backed jobs cancel locally", html)

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

    def test_submit_demo_reserve_and_cancel(self) -> None:
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "stages": 3, "seconds": 8}).encode(),
        )
        self.assertEqual(created.status, 201)
        job = _json(created)
        self.assertEqual(job["kind"], "job")
        self.assertEqual(job["class"], "cpu")
        self.assertEqual(job["local"]["demo"], "reserve")
        self.assertEqual(job["local"]["catalog"], "recorded")
        self.assertEqual(job["payload_digest"], RECORDED_PAYLOAD_DIGEST)
        self.assertEqual(
            job["payload_digest"],
            "sha256:77e9299f4b8ea4aeed46f71b91cc947d56e9bd169d795e70845123fef53d7e4e",
        )
        handoff = self.app.handle("GET", f"/v0/jobs/{job['id']}/handoff")
        self.assertEqual(handoff.status, 200)
        exported = _json(handoff)
        self.assertEqual(
            set(exported),
            {"id", "kind", "class", "payload_digest", "status"},
        )
        self.assertEqual(exported["id"], job["id"])
        self.assertEqual(exported["payload_digest"], job["payload_digest"])
        self.assertNotIn("payload", exported)
        self.assertNotIn("local", exported)

        payload = self.app.handle("GET", f"/v0/jobs/{job['id']}/payload")
        self.assertEqual(payload.status, 200)
        body = _json(payload)
        self.assertEqual(body["payload_digest"], job["payload_digest"])
        self.assertEqual(digest_bytes(bytes.fromhex(body["hex"])), job["payload_digest"])
        self.assertEqual(body["utf8"].encode("utf-8"), bytes.fromhex(body["hex"]))
        self.assertNotIn("payload", body)
        self.assertEqual(body["utf8"], RECORDED_CANONICAL_JSON)
        self.assertEqual(
            body["utf8"],
            '{"accounts":48,"discount_bps":300,"horizon":12,"lapse_bps":80,'
            '"paths":96,"seed":17070,"workload":"reserve"}',
        )
        self.assertIn('"workload":"reserve"', body["utf8"])
        self.assertNotIn("reserve_ifrs17", body["utf8"])
        self.assertNotIn('"work":', body["utf8"])
        canceled = self.app.handle("POST", f"/v0/jobs/{job['id']}/cancel")
        self.assertEqual(canceled.status, 200)
        self.assertEqual(_json(canceled)["status"], "canceled")

        smuggle = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "engine": "local"}).encode(),
        )
        self.assertEqual(smuggle.status, 400)
        self.assertEqual(_json(smuggle)["error"], "engine_smuggle")

        parity = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "catalog": "parity", "seconds": 0}).encode(),
        )
        self.assertEqual(parity.status, 201)
        body = _json(parity)
        self.assertEqual(body["local"]["catalog"], "parity")
        self.assertEqual(body["payload_digest"], PARITY_PAYLOAD_DIGEST)
        self.assertEqual(
            body["payload_digest"],
            "sha256:e180d2c2e3589b8762f92efa1bedb3d53ffeeb16648581ba13d537bcd3311102",
        )
        alias = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "catalog": "parity-scale", "seconds": 0}).encode(),
        )
        self.assertEqual(alias.status, 201)
        self.assertEqual(_json(alias)["local"]["catalog"], "parity")
        self.assertEqual(_json(alias)["payload_digest"], PARITY_PAYLOAD_DIGEST)

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

    def test_payload_unknown_for_opaque_digest_only(self) -> None:
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps(
                {"kind": "job", "class": "cpu", "payload_digest": _digest()}
            ).encode(),
        )
        job_id = _json(created)["id"]
        missing = self.app.handle("GET", f"/v0/jobs/{job_id}/payload")
        self.assertEqual(missing.status, 404)
        self.assertEqual(_json(missing)["error"], "payload_unknown")
        handoff = _json(self.app.handle("GET", f"/v0/jobs/{job_id}/handoff"))
        self.assertEqual(handoff["kind"], "job")
        self.assertNotIn("payload", handoff)

    def test_handoff_and_payload_missing(self) -> None:
        self.assertEqual(self.app.handle("GET", "/v0/jobs/nope/handoff").status, 404)
        self.assertEqual(self.app.handle("GET", "/v0/jobs/nope/payload").status, 404)
        self.assertEqual(
            self.app.handle("POST", "/v0/jobs/nope/handoff").status, 405
        )

    def test_progress_and_events_http(self) -> None:
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "stages": 3, "seconds": 8}).encode(),
        )
        job_id = _json(created)["id"]
        progress = self.app.handle("GET", f"/v0/jobs/{job_id}/progress")
        self.assertEqual(progress.status, 200)
        body = _json(progress)
        self.assertEqual(body["id"], job_id)
        self.assertEqual(body["backed"], "stub")
        self.assertEqual(body["stages_total"], 3)
        self.assertIn("not iec chunk progress", body["note"])
        self.assertNotIn("chunks_done", body)
        self.assertNotIn("parallelism", body)

        events = self.app.handle("GET", f"/v0/jobs/{job_id}/events")
        self.assertEqual(events.status, 200)
        trail = _json(events)
        self.assertEqual(trail["id"], job_id)
        self.assertIn("not a regulatory audit", trail["note"])
        names = [item["event"] for item in trail["events"]]
        self.assertIn("submitted", names)
        self.assertIn("backed", names)

        canceled = self.app.handle("POST", f"/v0/jobs/{job_id}/cancel")
        self.assertEqual(canceled.status, 200)
        job = _json(canceled)
        self.assertEqual(job["status"], "canceled")
        self.assertIn("canceled", [item["event"] for item in job["events"]])

        missing_p = self.app.handle("GET", "/v0/jobs/nope/progress")
        self.assertEqual(missing_p.status, 404)
        missing_e = self.app.handle("GET", "/v0/jobs/nope/events")
        self.assertEqual(missing_e.status, 404)
        self.assertEqual(
            self.app.handle("POST", f"/v0/jobs/{job_id}/progress").status, 405
        )
        self.assertEqual(
            self.app.handle("POST", f"/v0/jobs/{job_id}/events").status, 405
        )

    def test_cancel_terminal_includes_pause_note(self) -> None:
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "echo", "message": "x"}).encode(),
        )
        job_id = _json(created)["id"]
        wait_http_status(self.app, job_id, {"succeeded"})
        conflict = self.app.handle("POST", f"/v0/jobs/{job_id}/cancel")
        self.assertEqual(conflict.status, 409)
        body = _json(conflict)
        self.assertEqual(body["error"], "already_terminal")
        self.assertIn("no pause/resume", body["note"])
        self.assertIn("canceled", body["note"])

    def test_missing_job(self) -> None:
        resp = self.app.handle("GET", "/v0/jobs/not-a-job")
        self.assertEqual(resp.status, 404)
        self.assertEqual(_json(resp)["error"], "not_found")
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
