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
from sos.errors import InvalidStatus
from sos.http import INFO_PAYLOAD, SosApp, parse_job_status_filter
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
        self.assertEqual(body["jobs"]["statuses"], ["queued", "running", "paused", "succeeded", "failed", "canceled"])
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
        self.assertIn("PANORAMIX_CTL_HTTP", ctl["note"])
        self.assertIn("PANORAMIX_RUNTIME_ROOT", ctl["note"])
        self.assertIn("lab_compose_reserve_temporal", ctl["note"])
        self.assertIn("ctl_http_unreachable", ctl["note"])
        self.assertIn("lab-serve down", ctl["note"])
        self.assertIn("ctl_http_unreachable", body["jobs"]["ctl_http_unreachable"])
        self.assertIn("lab-serve down", body["jobs"]["ctl_http_unreachable"])
        self.assertIn("Not a hung poll", body["jobs"]["ctl_http_unreachable"])
        self.assertNotIn("never calls", ctl["note"])
        hook = body["jobs"]["durable_hook"]
        self.assertEqual(hook["kind"], "inert")
        self.assertIs(hook["durable_path"], False)
        self.assertIs(hook["north_star_done"], False)
        self.assertIs(hook["guest_to_mesh_ctl"], False)
        self.assertIn("No pretend", hook["note"])
        self.assertEqual(body["jobs"]["list"], "GET /v0/jobs")
        self.assertEqual(
            body["jobs"]["list_status"],
            "GET /v0/jobs?status=queued|running|paused|succeeded|failed|canceled",
        )
        self.assertIn("real job.status", body["jobs"]["list_status_honesty"])
        self.assertIn("invalid_status", body["jobs"]["list_status_honesty"])
        self.assertIn("cancelled", body["jobs"]["list_status_honesty"])
        self.assertIn("Stops when the selected job is terminal", body["jobs"]["auto_refresh_honesty"])
        self.assertIn("Does not invent progress", body["jobs"]["auto_refresh_honesty"])
        self.assertIn("durable_hook", body["jobs"]["auto_refresh_honesty"])
        self.assertIn("Not a SPA framework", body["jobs"]["auto_refresh_honesty"])
        self.assertEqual(body["jobs"]["progress"], "GET /v0/jobs/{id}/progress")
        self.assertEqual(body["jobs"]["events"], "GET /v0/jobs/{id}/events")
        self.assertIn("?kind=", body["jobs"]["events_filter"])
        self.assertIn("format=jsonl", body["jobs"]["events_export"])
        self.assertIn("not regulatory defensibility", body["jobs"]["events_export_honesty"])
        self.assertEqual(body["jobs"]["compare"], "GET /v0/jobs/{id}/compare")
        self.assertEqual(body["jobs"]["pause"], "POST /v0/jobs/{id}/pause")
        self.assertEqual(body["jobs"]["resume"], "POST /v0/jobs/{id}/resume")
        self.assertIs(body["jobs"]["pause_resume"], True)
        self.assertIn("durable path only", body["jobs"]["pause_resume_honesty"])
        self.assertIn("stub_only", body["jobs"]["pause_resume_honesty"])
        self.assertIn(
            "python3 -m runtime.apply reserve-temporal pause|resume",
            body["jobs"]["pause_resume_honesty"],
        )
        self.assertIn("not iec chunk progress", body["jobs"]["progress_honesty"])
        self.assertIn("durable", body["jobs"]["progress_honesty"])
        self.assertIn("path-slices", body["jobs"]["progress_honesty"])
        self.assertIn("not iec planner", body["jobs"]["progress_honesty"])
        self.assertIn("named stages", body["jobs"]["progress_honesty"])
        self.assertIn("completed vs current vs pending", body["jobs"]["progress_honesty"])
        self.assertIn("without fake names", body["jobs"]["progress_honesty"])
        self.assertIn("stage i of n", body["jobs"]["progress_honesty"])
        self.assertIn(
            "python3 -m runtime.apply reserve-temporal progress",
            body["jobs"]["progress_honesty"],
        )
        self.assertIn("not a regulatory audit", body["jobs"]["events_honesty"])
        self.assertIn("not regulatory defensibility", body["jobs"]["events_honesty"])
        self.assertIn("durable", body["jobs"]["events_honesty"])
        self.assertIn("jsonl", body["jobs"]["events_honesty"].lower())
        self.assertIn("not a siem", body["jobs"]["events_honesty"].lower())
        self.assertIn("/v1/audit/events", body["jobs"]["events_honesty"])
        self.assertIn("filter by kind", body["jobs"]["events_honesty"])
        self.assertIn(
            "python3 -m runtime.apply reserve-temporal events",
            body["jobs"]["events_honesty"],
        )
        self.assertIn("not a data-catalog product", body["jobs"]["investigate_honesty"])
        self.assertIn("not Slack", body["jobs"]["investigate_honesty"])
        self.assertIn("admit / project / fold / complete", body["jobs"]["investigate_honesty"])
        self.assertIn("same panel", body["jobs"]["investigate_honesty"])
        self.assertIn("not a SIEM", body["jobs"]["investigate_honesty"])
        self.assertIn("not a forecast", body["jobs"]["compare_honesty"])
        self.assertIn("not IFRS17", body["jobs"]["compare_honesty"])
        self.assertIn("not iec SPA historical widget", body["jobs"]["compare_honesty"])
        self.assertIn("guest process history", body["jobs"]["compare_honesty"])
        self.assertIn("PANORAMIX_SOS_JOBS_DIR", body["jobs"]["compare_honesty"])
        self.assertIn("Fail-closed", body["jobs"]["compare_honesty"])
        self.assertIn("No guest→ctl HTTP", body["jobs"]["compare_honesty"])
        persist = body["jobs"]["history_persist"]
        self.assertEqual(persist["env"], "PANORAMIX_SOS_JOBS_DIR")
        self.assertEqual(persist["default"], ".sos/jobs")
        self.assertEqual(persist["disable"], "off")
        self.assertIs(persist["enabled"], False)
        self.assertIn("Fail-closed", persist["note"])
        self.assertIn("Not a SIEM", persist["note"])
        self.assertIn("Not #70 Done", persist["note"])
        self.assertIn("Cancel is not pause", body["jobs"]["cancel_note"])
        self.assertIn("does not auto-retry", body["jobs"]["cancel_note"])
        self.assertIn("ctl-mediated", body["jobs"]["cancel_note"])
        self.assertIn("Fail-closed without hook", body["jobs"]["cancel_note"])
        self.assertIn("PANORAMIX_CTL_HTTP", body["jobs"]["cancel_note"])
        self.assertIn(
            "python3 -m runtime.apply reserve-temporal cancel",
            body["jobs"]["cancel_note"],
        )
        self.assertIn("SIEM", body["jobs"]["terminal"])
        self.assertIn("/v1/audit/events", body["jobs"]["terminal"])
        self.assertIn("does not auto-retry", body["jobs"]["recoverability"])
        self.assertIn(
            "python3 -m runtime.apply reserve-temporal admit --handoff JSON",
            body["jobs"]["recoverability"],
        )
        self.assertIn("stub_only", body["jobs"]["recoverability"])
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
            self.assertIn("Event trail", html)
            self.assertIn("View/copy handoff", html)
            self.assertIn("Fetch payload", html)
            self.assertNotIn("no pause / resume", html)
            self.assertIn("not iec chunk progress", html)
            self.assertIn("stages_completed", html)
            self.assertIn("fraction", html)
            self.assertIn("/progress", html)
            self.assertIn("path-slices", html)
            self.assertIn("Path-slice timeline (thinner)", html)
            self.assertIn("progressTimeline", html)
            self.assertIn("without fake names", html)
            self.assertIn('"Stage " + index + " of "', html)
            self.assertIn("step.pending", html)
            self.assertIn("completed vs current vs pending", html)
            self.assertIn("not a regulatory audit", html)
            self.assertIn("not a SIEM", html)
            self.assertIn("not regulatory defensibility", html)
            self.assertIn("Download JSON", html)
            self.assertIn("Download JSONL", html)
            self.assertIn("StageCompleted", html)
            self.assertIn("event-kind-filters", html)
            self.assertIn("format=jsonl", html)
            self.assertIn("reserve-temporal events --id", html)
            self.assertIn("/events", html)
            self.assertIn("docs/ux-side-by-side.md", html)
            self.assertIn("End run (canceled)", html)
            self.assertIn("Stub-backed jobs cancel locally", html)
            self.assertIn("Durable cancel is ctl-mediated", html)
            self.assertIn("Fail-closed without hook", html)
            self.assertIn("id=\"pause-btn\"", html)
            self.assertIn("id=\"resume-btn\"", html)
            self.assertIn("durable path", html)
            self.assertIn("409 stub_only", html)
            self.assertIn("python3 -m runtime.apply reserve-temporal pause|resume", html)
            self.assertIn("PANORAMIX_CTL_HTTP", html)
            self.assertIn("/reserve-temporal/", html)
            self.assertIn("durable-badge", html)
            self.assertIn("No pretend durable path", html)
            self.assertIn("Durable path active — loopback ctl HTTP", html)
            self.assertIn("ctl_http_unreachable", html)
            self.assertIn("lab serve down", html.lower())
            self.assertIn("badge-down", html)
            self.assertIn("Lab serve down (thinner)", html)
            self.assertIn("durable_hook", html)
            self.assertIn("Cancel is not pause", html)
            self.assertIn("Investigate (thinner)", html)
            self.assertIn("Catalog cross-check", html)
            self.assertIn("not a data-catalog product", html)
            self.assertIn("Not a data-catalog product", html)
            self.assertIn("Path-slice ownership tags", html)
            self.assertIn("admit / project / fold / complete", html)
            self.assertIn("Not Slack", html)
            self.assertIn("Event trail is on this panel", html)
            self.assertIn("not a SIEM", html)
            self.assertIn("Failure / terminal (thinner)", html)
            self.assertIn("Recoverability (thinner)", html)
            self.assertIn("does not auto-retry", html)
            self.assertIn("Export handoff for re-admit", html)
            self.assertIn("Export payload for re-admit", html)
            self.assertIn("reserve-temporal admit --handoff JSON", html)
            self.assertIn("not iec /v1/audit/events", html)
            self.assertIn("No resume-from-failed", html)
            self.assertIn("Vs recent guest jobs", html)
            self.assertIn("/compare", html)
            self.assertIn("Not a forecast", html)
            self.assertIn("Not IFRS17", html)
            self.assertIn("Not iec SPA historical widget", html)
            self.assertIn("No prior jobs in guest history to compare", html)
            self.assertIn("PANORAMIX_SOS_JOBS_DIR", html)
            self.assertIn("typical_elapsed_s", html)
            self.assertIn("eta_elapsed_s", html)
            self.assertIn('id="status-filter"', html)
            self.assertIn('id="auto-refresh"', html)
            self.assertIn('id="refresh-btn"', html)
            self.assertIn('value="queued"', html)
            self.assertIn('value="paused"', html)
            self.assertIn('value="canceled"', html)
            self.assertNotIn('value="cancelled"', html)
            self.assertIn("/v0/jobs?status=", html)
            self.assertIn("Does not invent progress", html)
            self.assertIn("Stops when the selected job is terminal", html)
            self.assertIn("durable_path", html)
            self.assertIn("No jobs with status", html)
            self.assertNotIn("setInterval(refresh, 1000)", html)
            self.assertIn("REFRESH_MS = 2000", html)
            self.assertIn("Not a SPA framework", html)

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
        canceled_job = _json(canceled)
        self.assertEqual(canceled_job["status"], "canceled")
        self.assertEqual(canceled_job["terminal"]["status"], "canceled")
        self.assertEqual(canceled_job["terminal"]["message"], "canceled by operator")
        self.assertIn("not a SIEM", canceled_job["terminal"]["note"])
        self.assertIn("/v1/audit/events", canceled_job["terminal"]["note"])
        self.assertEqual(canceled_job["recoverability"]["auto_retry"], False)
        self.assertEqual(canceled_job["recoverability"]["resume_from_failed"], False)
        self.assertIs(canceled_job["recoverability"]["payload_known"], True)
        self.assertIn("does not auto-retry", canceled_job["recoverability"]["note"])
        self.assertIn(
            "reserve-temporal admit --handoff JSON",
            canceled_job["recoverability"]["re_admit"],
        )

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
        self.assertEqual(body["source"], "stub")
        self.assertEqual(body["stages_total"], 3)
        self.assertIs(body["pause_resume"], False)
        self.assertIn("not iec chunk progress", body["note"])
        self.assertNotIn("chunks_done", body)
        self.assertNotIn("parallelism", body)
        self.assertNotIn("stages_completed", body)
        self.assertNotIn("fraction", body)
        self.assertNotIn("timeline", body)
        self.assertEqual(body["investigate"]["catalog"]["name"], "recorded")
        self.assertEqual(body["investigate"]["catalog"]["digest_short"], "sha256:77e9299f…")
        self.assertIn("not a data-catalog product", body["investigate"]["catalog"]["note"])
        self.assertNotIn("ownership", body["investigate"])

        events = self.app.handle("GET", f"/v0/jobs/{job_id}/events")
        self.assertEqual(events.status, 200)
        trail = _json(events)
        self.assertEqual(trail["id"], job_id)
        self.assertEqual(trail["source"], "memory")
        self.assertIn("not a regulatory audit", trail["note"])
        names = [item["event"] for item in trail["events"]]
        self.assertIn("submitted", names)
        self.assertIn("backed", names)

        canceled = self.app.handle("POST", f"/v0/jobs/{job_id}/cancel")
        self.assertEqual(canceled.status, 200)
        job = _json(canceled)
        self.assertEqual(job["status"], "canceled")
        self.assertIn("canceled", [item["event"] for item in job["events"]])
        self.assertEqual(job["terminal"]["status"], "canceled")
        self.assertEqual(job["terminal"]["last_events"][-1]["event"], "canceled")
        self.assertIs(job["recoverability"]["auto_retry"], False)

        compare = self.app.handle("GET", f"/v0/jobs/{job_id}/compare")
        self.assertEqual(compare.status, 200)
        vs = _json(compare)
        self.assertEqual(vs["id"], job_id)
        self.assertEqual(vs["source"], "guest_history")
        self.assertEqual(vs["priors_n"], 0)
        self.assertNotIn("typical_elapsed_s", vs)
        self.assertNotIn("eta_elapsed_s", vs)
        self.assertIn("No prior jobs", vs["note"])
        self.assertIn("Not a forecast", vs["note"])
        self.assertIn("Not IFRS17", vs["note"])
        self.assertIn("Not iec SPA historical widget", vs["note"])

        missing_p = self.app.handle("GET", "/v0/jobs/nope/progress")
        self.assertEqual(missing_p.status, 404)
        missing_e = self.app.handle("GET", "/v0/jobs/nope/events")
        self.assertEqual(missing_e.status, 404)
        missing_c = self.app.handle("GET", "/v0/jobs/nope/compare")
        self.assertEqual(missing_c.status, 404)
        self.assertEqual(
            self.app.handle("POST", f"/v0/jobs/{job_id}/progress").status, 405
        )
        self.assertEqual(
            self.app.handle("POST", f"/v0/jobs/{job_id}/events").status, 405
        )
        self.assertEqual(
            self.app.handle("POST", f"/v0/jobs/{job_id}/compare").status, 405
        )

    def test_compare_http_empty_single_multi(self) -> None:
        first = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "seconds": 0, "stages": 2}).encode(),
        )
        first_id = _json(first)["id"]
        wait_http_status(self.app, first_id, {"succeeded"})
        empty = _json(self.app.handle("GET", f"/v0/jobs/{first_id}/compare"))
        self.assertEqual(empty["priors_n"], 0)
        self.assertNotIn("typical_elapsed_s", empty)
        self.assertNotIn("eta_elapsed_s", empty)

        second = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "seconds": 0, "stages": 2}).encode(),
        )
        second_id = _json(second)["id"]
        wait_http_status(self.app, second_id, {"succeeded"})
        single = _json(self.app.handle("GET", f"/v0/jobs/{second_id}/compare"))
        self.assertEqual(single["priors_n"], 1)
        self.assertEqual(single["priors"][0]["id"], first_id)
        self.assertIn("elapsed_s", single["priors"][0])
        self.assertNotIn("typical_elapsed_s", single)
        self.assertNotIn("eta_elapsed_s", single)

        third = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "seconds": 0, "stages": 2}).encode(),
        )
        third_id = _json(third)["id"]
        wait_http_status(self.app, third_id, {"succeeded"})
        multi = _json(self.app.handle("GET", f"/v0/jobs/{third_id}/compare"))
        self.assertEqual(multi["priors_n"], 2)
        self.assertIn("typical_elapsed_s", multi)
        self.assertNotIn("eta_elapsed_s", multi)
        self.assertIn("Not a forecast", multi["note"])
        handoff = _json(self.app.handle("GET", f"/v0/jobs/{third_id}/handoff"))
        self.assertNotIn("typical_elapsed_s", handoff)
        self.assertNotIn("compare", handoff)

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
        self.assertIn("not pause", body["note"].lower())
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
        body = _json(canceled)
        self.assertEqual(body["status"], "canceled")
        self.assertNotEqual(body["status"], "cancelled")
        self.assertEqual(body["terminal"]["status"], "canceled")
        self.assertIs(body["recoverability"]["auto_retry"], False)
        self.assertNotIn("terminal", _json(created))
        self.assertNotIn("recoverability", _json(created))

    def test_failed_and_canceled_terminal_http(self) -> None:
        class FailHook:
            def admit(self, handoff, payload_bytes):
                return {"accepted": True}

            def cancel(self, job_id, runtime_ref) -> bool:
                return True

            def status(self, job_id, runtime_ref):
                return "failed"

            def pause(self, job_id, runtime_ref) -> bool:
                return False

            def resume(self, job_id, runtime_ref) -> bool:
                return False

            def events(self, job_id, runtime_ref):
                return {
                    "events": [
                        {
                            "ts": "2026-09-11T16:00:00Z",
                            "event": "admit",
                            "type": "WorkflowExecutionStarted",
                        },
                        {
                            "ts": "2026-09-11T16:00:01Z",
                            "event": "fail",
                            "type": "WorkflowExecutionFailed",
                        },
                    ],
                    "events_durable": True,
                    "events_n": 2,
                }

        app = SosApp(JobStore(step_seconds=0.02, runtime_hook=FailHook()))
        created = app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "seconds": 8}).encode(),
        )
        self.assertEqual(created.status, 201)
        job = _json(created)
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["terminal"]["status"], "failed")
        self.assertEqual(job["terminal"]["message"], "status via runtime hook")
        self.assertEqual(job["terminal"]["events_source"], "durable")
        self.assertEqual(job["terminal"]["last_events"][-1]["event"], "fail")
        self.assertIn("not a SIEM", job["terminal"]["note"])
        self.assertIs(job["recoverability"]["auto_retry"], False)
        self.assertIs(job["recoverability"]["resume_from_failed"], False)
        self.assertIs(job["recoverability"]["payload_known"], True)
        self.assertIn(job["id"], job["recoverability"]["handoff"])
        handoff = _json(app.handle("GET", f"/v0/jobs/{job['id']}/handoff"))
        self.assertNotIn("terminal", handoff)
        self.assertNotIn("recoverability", handoff)
        self.assertEqual(handoff["status"], "failed")

        opaque = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps(
                {"kind": "job", "class": "cpu", "payload_digest": _digest()}
            ).encode(),
        )
        oid = _json(opaque)["id"]
        canceled = self.app.handle("POST", f"/v0/jobs/{oid}/cancel")
        body = _json(canceled)
        self.assertEqual(body["status"], "canceled")
        self.assertEqual(body["terminal"]["status"], "canceled")
        self.assertIs(body["recoverability"]["payload_known"], False)

        done = wait_http_status(self.app, _json(self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "echo", "message": "ok"}).encode(),
        ))["id"], {"succeeded"})
        self.assertNotIn("terminal", done)
        self.assertNotIn("recoverability", done)

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

    def test_pause_resume_stub_only_refused(self) -> None:
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "sleep", "seconds": 8}).encode(),
        )
        job_id = _json(created)["id"]
        self.assertEqual(_json(created)["local"]["backed"], "stub")
        self.assertIs(_json(created)["pause_resume"], False)

        pause = self.app.handle("POST", f"/v0/jobs/{job_id}/pause")
        self.assertEqual(pause.status, 409)
        body = _json(pause)
        self.assertEqual(body["error"], "stub_only")
        self.assertEqual(body["action"], "pause")
        self.assertIn("durable path", body["detail"])
        self.assertIn("python3 -m runtime.apply reserve-temporal pause|resume", body["detail"])

        resume = self.app.handle("POST", f"/v0/jobs/{job_id}/resume")
        self.assertEqual(resume.status, 409)
        self.assertEqual(_json(resume)["error"], "stub_only")
        self.assertEqual(_json(resume)["action"], "resume")

        missing = self.app.handle("POST", "/v0/jobs/nope/pause")
        self.assertEqual(missing.status, 404)
        self.assertEqual(_json(missing)["error"], "not_found")
        missing_r = self.app.handle("POST", "/v0/jobs/nope/resume")
        self.assertEqual(missing_r.status, 404)
        self.assertEqual(
            self.app.handle("GET", f"/v0/jobs/{job_id}/pause").status, 405
        )
        self.assertEqual(
            self.app.handle("GET", f"/v0/jobs/{job_id}/resume").status, 405
        )
        self.app.handle("POST", f"/v0/jobs/{job_id}/cancel")

    def test_pause_resume_durable_http(self) -> None:
        class FakeHook:
            def __init__(self) -> None:
                self.reported = "running"
                self.pauses: list[str] = []
                self.resumes: list[str] = []

            def admit(self, handoff, payload_bytes):
                return {"accepted": True}

            def cancel(self, job_id, runtime_ref) -> bool:
                return True

            def status(self, job_id, runtime_ref):
                return self.reported

            def pause(self, job_id, runtime_ref) -> bool:
                self.pauses.append(job_id)
                self.reported = "paused"
                return True

            def resume(self, job_id, runtime_ref) -> bool:
                self.resumes.append(job_id)
                self.reported = "running"
                return True

        hook = FakeHook()
        app = SosApp(JobStore(step_seconds=0.02, runtime_hook=hook))
        created = app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "seconds": 8}).encode(),
        )
        self.assertEqual(created.status, 201)
        job = _json(created)
        job_id = job["id"]
        self.assertEqual(job["local"]["backed"], "runtime")
        self.assertEqual(job["status"], "running")
        self.assertIs(job["pause_resume"], True)

        paused = app.handle("POST", f"/v0/jobs/{job_id}/pause")
        self.assertEqual(paused.status, 200)
        body = _json(paused)
        self.assertEqual(body["status"], "paused")
        self.assertIs(body["pause_resume"], True)
        self.assertIn("paused", [item["event"] for item in body["events"]])
        self.assertEqual(hook.pauses, [job_id])

        handoff = _json(app.handle("GET", f"/v0/jobs/{job_id}/handoff"))
        self.assertEqual(handoff["status"], "paused")
        self.assertEqual(
            set(handoff),
            {"id", "kind", "class", "payload_digest", "status"},
        )

        again = app.handle("POST", f"/v0/jobs/{job_id}/pause")
        self.assertEqual(again.status, 409)
        self.assertEqual(_json(again)["error"], "illegal_transition")

        resumed = app.handle("POST", f"/v0/jobs/{job_id}/resume")
        self.assertEqual(resumed.status, 200)
        self.assertEqual(_json(resumed)["status"], "running")
        self.assertEqual(hook.resumes, [job_id])

        queued_hook = FakeHook()
        queued_hook.reported = None  # type: ignore[assignment]
        queued_app = SosApp(JobStore(step_seconds=0.02, runtime_hook=queued_hook))
        queued = queued_app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "seconds": 8}).encode(),
        )
        qid = _json(queued)["id"]
        self.assertEqual(_json(queued)["status"], "queued")
        bad_pause = queued_app.handle("POST", f"/v0/jobs/{qid}/pause")
        self.assertEqual(bad_pause.status, 409)
        self.assertEqual(_json(bad_pause)["error"], "illegal_transition")
        bad_resume = queued_app.handle("POST", f"/v0/jobs/{qid}/resume")
        self.assertEqual(bad_resume.status, 409)
        self.assertEqual(_json(bad_resume)["error"], "illegal_transition")

        done_hook = FakeHook()
        done_hook.reported = "succeeded"
        done_app = SosApp(JobStore(step_seconds=0.02, runtime_hook=done_hook))
        done = done_app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "seconds": 8}).encode(),
        )
        did = _json(done)["id"]
        self.assertEqual(_json(done)["status"], "succeeded")
        term_pause = done_app.handle("POST", f"/v0/jobs/{did}/pause")
        self.assertEqual(term_pause.status, 409)
        self.assertEqual(_json(term_pause)["error"], "already_terminal")
        term_resume = done_app.handle("POST", f"/v0/jobs/{did}/resume")
        self.assertEqual(term_resume.status, 409)
        self.assertEqual(_json(term_resume)["error"], "already_terminal")

    def test_hooked_cancel_and_status_follow_http(self) -> None:
        class FollowHook:
            def __init__(self) -> None:
                self.reported = "running"
                self.cancels: list[str] = []

            def admit(self, handoff, payload_bytes):
                return {"id": "cw_deadbeefdeadbeef"}

            def cancel(self, job_id, runtime_ref) -> bool:
                self.cancels.append(job_id)
                self.reported = "canceled"
                return True

            def status(self, job_id, runtime_ref):
                return self.reported

            def pause(self, job_id, runtime_ref) -> bool:
                return False

            def resume(self, job_id, runtime_ref) -> bool:
                return False

        hook = FollowHook()
        app = SosApp(JobStore(step_seconds=0.02, runtime_hook=hook))
        created = app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "seconds": 8}).encode(),
        )
        job = _json(created)
        job_id = job["id"]
        self.assertEqual(job["status"], "running")
        self.assertEqual(job["local"]["backed"], "runtime")

        hook.reported = "paused"
        listed = _json(app.handle("GET", "/v0/jobs"))
        self.assertEqual(listed["jobs"][0]["id"], job_id)
        self.assertEqual(listed["jobs"][0]["status"], "paused")
        got = _json(app.handle("GET", f"/v0/jobs/{job_id}"))
        self.assertEqual(got["status"], "paused")
        self.assertEqual(got["message"], "status via runtime hook")

        hook.reported = "running"
        self.assertEqual(_json(app.handle("GET", f"/v0/jobs/{job_id}"))["status"], "running")

        canceled = app.handle("POST", f"/v0/jobs/{job_id}/cancel")
        self.assertEqual(canceled.status, 200)
        body = _json(canceled)
        self.assertEqual(body["status"], "canceled")
        self.assertEqual(body["message"], "status via runtime hook")
        self.assertEqual(hook.cancels, [job_id])
        self.assertIs(body["recoverability"]["auto_retry"], False)
        conflict = app.handle("POST", f"/v0/jobs/{job_id}/cancel")
        self.assertEqual(conflict.status, 409)
        self.assertEqual(_json(conflict)["error"], "already_terminal")
        self.assertIn("ctl-mediated", _json(conflict)["note"])

    def test_progress_durable_http(self) -> None:
        class FakeHook:
            def admit(self, handoff, payload_bytes):
                return {"accepted": True}

            def cancel(self, job_id, runtime_ref) -> bool:
                return True

            def status(self, job_id, runtime_ref):
                return "running"

            def pause(self, job_id, runtime_ref) -> bool:
                return False

            def resume(self, job_id, runtime_ref) -> bool:
                return False

            def progress(self, job_id, runtime_ref):
                return {
                    "stage": 3,
                    "stages_total": 4,
                    "stages_completed": 3,
                    "fraction": 0.75,
                    "progress": {
                        "stage": 3,
                        "stages_total": 4,
                        "stages_completed": 3,
                        "fraction": 0.75,
                    },
                }

        app = SosApp(JobStore(step_seconds=0.02, runtime_hook=FakeHook()))
        created = app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "seconds": 8}).encode(),
        )
        job_id = _json(created)["id"]
        progress = app.handle("GET", f"/v0/jobs/{job_id}/progress")
        self.assertEqual(progress.status, 200)
        body = _json(progress)
        self.assertEqual(body["source"], "durable")
        self.assertEqual(body["stages_completed"], 3)
        self.assertEqual(body["stages_total"], 4)
        self.assertEqual(body["fraction"], 0.75)
        self.assertEqual(body["progress"]["stages_completed"], 3)
        self.assertEqual(body["fraction"], 0.75)
        self.assertEqual(
            [(item["name"], item["state"], item["owner"]) for item in body["timeline"]],
            [
                ("admit", "completed", "ctl / admit"),
                ("project", "completed", "kernel / project"),
                ("fold", "completed", "kernel / fold"),
                ("complete", "pending", "ctl / complete"),
            ],
        )
        self.assertIn("path-slices", body["note"].lower())
        self.assertIn("not iec planner", body["note"].lower())
        self.assertNotIn("temporal_product", body)
        self.assertNotIn("workflow_id", body)
        self.assertEqual(body["investigate"]["catalog"]["name"], "recorded")
        self.assertEqual(
            [item["slice"] for item in body["investigate"]["ownership"]["tags"]],
            ["admit", "project", "fold", "complete"],
        )
        self.assertIn("not Slack", body["investigate"]["ownership"]["note"])
        job = _json(app.handle("GET", f"/v0/jobs/{job_id}"))
        self.assertEqual(
            [item["owner"] for item in job["investigate"]["ownership"]["tags"]],
            ["ctl / admit", "kernel / project", "kernel / fold", "ctl / complete"],
        )
        handoff = _json(app.handle("GET", f"/v0/jobs/{job_id}/handoff"))
        self.assertNotIn("investigate", handoff)
        app.handle("POST", f"/v0/jobs/{job_id}/cancel")

    def test_events_durable_http(self) -> None:
        class FakeHook:
            def admit(self, handoff, payload_bytes):
                return {"accepted": True}

            def cancel(self, job_id, runtime_ref) -> bool:
                return True

            def status(self, job_id, runtime_ref):
                return "running"

            def pause(self, job_id, runtime_ref) -> bool:
                return False

            def resume(self, job_id, runtime_ref) -> bool:
                return False

            def events(self, job_id, runtime_ref):
                return {
                    "events": [
                        {
                            "ts": "2026-09-11T16:00:00Z",
                            "event": "admit",
                            "type": "WorkflowExecutionStarted",
                            "seq": 1,
                        },
                        {
                            "ts": "2026-09-11T16:00:01Z",
                            "event": "fail",
                            "type": "WorkflowExecutionFailed",
                            "seq": 2,
                        },
                    ],
                    "events_durable": True,
                    "events_n": 2,
                }

        app = SosApp(JobStore(step_seconds=0.02, runtime_hook=FakeHook()))
        created = app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "seconds": 8}).encode(),
        )
        job_id = _json(created)["id"]
        events = app.handle("GET", f"/v0/jobs/{job_id}/events")
        self.assertEqual(events.status, 200)
        body = _json(events)
        self.assertEqual(body["source"], "durable")
        self.assertIs(body["events_durable"], True)
        self.assertEqual(body["events_n"], 2)
        self.assertEqual([item["event"] for item in body["events"]], ["admit", "fail"])
        self.assertEqual(body["events"][0]["type"], "WorkflowExecutionStarted")
        self.assertIn("jsonl", body["note"].lower())
        self.assertIn("not a siem", body["note"].lower())
        self.assertIn("/v1/audit/events", body["note"])
        job = _json(app.handle("GET", f"/v0/jobs/{job_id}"))
        self.assertEqual(job["events_source"], "durable")
        self.assertIs(job["events_durable"], True)
        self.assertEqual(job["events_n"], 2)
        handoff = _json(app.handle("GET", f"/v0/jobs/{job_id}/handoff"))
        self.assertNotIn("events", handoff)
        self.assertNotIn("events_durable", handoff)
        self.assertNotIn("temporal_product", body)
        self.assertNotIn("workflow_id", body)
        app.handle("POST", f"/v0/jobs/{job_id}/cancel")

    def test_invalid_json(self) -> None:
        resp = self.app.handle("POST", "/v0/jobs", b"{")
        self.assertEqual(resp.status, 400)
        self.assertEqual(_json(resp)["error"], "invalid_json")

    def test_parse_job_status_filter(self) -> None:
        self.assertIsNone(parse_job_status_filter({}))
        self.assertIsNone(parse_job_status_filter({"status": [""]}))
        self.assertEqual(parse_job_status_filter({"status": ["running"]}), frozenset({"running"}))
        self.assertEqual(
            parse_job_status_filter({"status": ["running,paused"]}),
            frozenset({"running", "paused"}),
        )
        self.assertEqual(
            parse_job_status_filter({"status": ["running", "paused"]}),
            frozenset({"running", "paused"}),
        )
        with self.assertRaises(InvalidStatus) as ctx:
            parse_job_status_filter({"status": ["cancelled"]})
        body = ctx.exception.to_dict()
        self.assertEqual(body["error"], "invalid_status")
        self.assertEqual(body["status"], "cancelled")
        self.assertIn("canceled", body["allowed"])
        self.assertNotIn("cancelled", body["allowed"])
        with self.assertRaises(InvalidStatus):
            parse_job_status_filter({"status": ["accepted"]})
        with self.assertRaises(InvalidStatus):
            parse_job_status_filter({"status": ["RUNNING"]})

    def test_list_status_filter_http(self) -> None:
        sleep = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "sleep", "seconds": 8}).encode(),
        )
        sleep_id = _json(sleep)["id"]
        echo = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "echo", "message": "hi"}).encode(),
        )
        echo_id = _json(echo)["id"]
        wait_http_status(self.app, echo_id, {"succeeded"})

        all_jobs = _json(self.app.handle("GET", "/v0/jobs"))
        self.assertNotIn("status", all_jobs)
        all_ids = {job["id"] for job in all_jobs["jobs"]}
        self.assertEqual(all_ids, {sleep_id, echo_id})

        succeeded = _json(self.app.handle("GET", "/v0/jobs?status=succeeded"))
        self.assertEqual(succeeded["status"], ["succeeded"])
        self.assertEqual([job["id"] for job in succeeded["jobs"]], [echo_id])
        self.assertTrue(all(job["status"] == "succeeded" for job in succeeded["jobs"]))

        live = _json(self.app.handle("GET", "/v0/jobs?status=queued,running,paused"))
        self.assertEqual(live["status"], ["queued", "running", "paused"])
        live_ids = {job["id"] for job in live["jobs"]}
        self.assertIn(sleep_id, live_ids)
        self.assertNotIn(echo_id, live_ids)
        self.assertTrue(all(job["status"] in {"queued", "running", "paused"} for job in live["jobs"]))

        canceled = self.app.handle("POST", f"/v0/jobs/{sleep_id}/cancel")
        self.assertEqual(_json(canceled)["status"], "canceled")
        filtered = _json(self.app.handle("GET", "/v0/jobs?status=canceled"))
        self.assertEqual([job["id"] for job in filtered["jobs"]], [sleep_id])

        bad = self.app.handle("GET", "/v0/jobs?status=cancelled")
        self.assertEqual(bad.status, 400)
        self.assertEqual(_json(bad)["error"], "invalid_status")
        accepted = self.app.handle("GET", "/v0/jobs?status=accepted")
        self.assertEqual(accepted.status, 400)
        self.assertEqual(_json(accepted)["error"], "invalid_status")

    def test_unit_yaml_has_no_engine_fields(self) -> None:
        text = Path(__file__).resolve().parents[1].joinpath(".platform/contract.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn('contract_version: "0.5"', text)
        for needle in ("image:", "ray:", "temporal:", "aws:"):
            self.assertNotIn(needle, text)


if __name__ == "__main__":
    unittest.main()
