"""Job store, handoff parse, and stub runner — no sockets."""

from __future__ import annotations

import hashlib
import time
import unittest

from sos.errors import (
    AlreadyTerminal,
    EngineSmuggle,
    IllegalTransition,
    InvalidClass,
    InvalidDemo,
    InvalidDigest,
    InvalidHandoff,
    InvalidKind,
    JobNotFound,
    PayloadUnknown,
    StubOnly,
)
from sos.handoff import digest_canonical, digest_for, parse_submit, payload_for, recorded_params
from sos.handoff_vocab import (
    BACKED_STUB,
    LIVE_PAYLOAD_DIGEST,
    PARITY_CANONICAL_JSON,
    PARITY_PAYLOAD_DIGEST,
    RECORDED_CANONICAL_JSON,
    RECORDED_PAYLOAD_DIGEST,
    STATUS_CANCELED,
    STATUS_QUEUED,
)
from sos.jobs import (
    JobStore,
    EVENTS_SOURCE_DURABLE,
    EVENTS_SOURCE_MEMORY,
    PROGRESS_SOURCE_DURABLE,
    PROGRESS_SOURCE_STUB,
)


def wait_status(store: JobStore, job_id: str, wanted: set[str], timeout: float = 2.0) -> str:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        last = store.get(job_id).status
        if last in wanted:
            return last
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} stayed {last!r}, wanted {wanted}")


def _digest(hex_byte: str = "ab") -> str:
    return "sha256:" + hex_byte * 32


class HandoffParseTests(unittest.TestCase):
    def test_valid_opaque_handoff(self) -> None:
        parsed = parse_submit(
            {"kind": "job", "class": "cpu", "payload_digest": _digest()}
        )
        self.assertEqual(parsed.kind, "job")
        self.assertEqual(parsed.resource_class, "cpu")
        self.assertEqual(parsed.payload_digest, _digest())
        self.assertIsNone(parsed.local)
        self.assertIsNone(parsed.payload_bytes)

    def test_stage_gpu_handoff(self) -> None:
        parsed = parse_submit(
            {"kind": "stage", "class": "gpu", "payload_digest": _digest("cd")}
        )
        self.assertEqual(parsed.kind, "stage")
        self.assertEqual(parsed.resource_class, "gpu")
        self.assertEqual(parsed.payload_digest, _digest("cd"))
        self.assertIsNone(parsed.local)

    def test_bad_kind(self) -> None:
        with self.assertRaises(InvalidKind) as ctx:
            parse_submit(
                {"kind": "sos.demo.echo", "class": "cpu", "payload_digest": _digest()}
            )
        body = ctx.exception.to_dict()
        self.assertEqual(body["error"], "invalid_kind")
        self.assertIn("job", body["allowed"])
        self.assertNotIn("sos.demo.echo", body["allowed"])

    def test_bad_class(self) -> None:
        with self.assertRaises(InvalidClass) as ctx:
            parse_submit(
                {"kind": "job", "class": "tpu", "payload_digest": _digest()}
            )
        self.assertEqual(ctx.exception.to_dict()["error"], "invalid_class")

    def test_bad_digest(self) -> None:
        with self.assertRaises(InvalidDigest):
            parse_submit({"kind": "job", "class": "cpu", "payload_digest": "sha256:dead"})
        with self.assertRaises(InvalidDigest):
            parse_submit({"kind": "job", "class": "cpu", "payload_digest": "md5:" + "ab" * 16})

    def test_demo_synthesizes_job_cpu_digest(self) -> None:
        parsed = parse_submit({"demo": "echo", "message": "ping"})
        self.assertEqual(parsed.kind, "job")
        self.assertEqual(parsed.resource_class, "cpu")
        self.assertEqual(parsed.payload_digest, digest_canonical({"demo": "echo", "message": "ping"}))
        self.assertRegex(parsed.payload_digest, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(parsed.local, {"demo": "echo", "message": "ping"})
        self.assertEqual(
            parsed.payload_bytes,
            b'{"demo":"echo","message":"ping"}',
        )

    def test_reserve_synthesizes_opaque_job(self) -> None:
        parsed = parse_submit(
            {"demo": "reserve", "label": "ux-seed", "stages": 3, "seconds": 6}
        )
        self.assertEqual(parsed.kind, "job")
        self.assertEqual(parsed.resource_class, "cpu")
        expected = payload_for(recorded_params())
        self.assertEqual(parsed.payload_digest, digest_for(expected))
        self.assertEqual(parsed.payload_digest, RECORDED_PAYLOAD_DIGEST)
        self.assertEqual(parsed.local["demo"], "reserve")
        self.assertEqual(parsed.local["catalog"], "recorded")
        self.assertEqual(parsed.local["label"], "ux-seed")
        self.assertNotEqual(parsed.local["demo"], "reserve_ifrs17")
        self.assertEqual(expected["workload"], "reserve")
        self.assertNotIn("demo", expected)
        self.assertNotIn("label", expected)
        self.assertNotIn("stages", expected)
        self.assertNotIn("seconds", expected)

    def test_reserve_defaults_and_gpu_label(self) -> None:
        parsed = parse_submit({"demo": "reserve"})
        self.assertEqual((parsed.kind, parsed.resource_class), ("job", "cpu"))
        self.assertEqual(parsed.local["catalog"], "recorded")
        self.assertEqual(parsed.local["label"], "reserve-shaped")
        self.assertEqual(parsed.local["stages"], 3)
        self.assertEqual(parsed.local["seconds"], 6)
        self.assertEqual(parsed.payload_digest, RECORDED_PAYLOAD_DIGEST)
        self.assertEqual(parsed.payload_bytes.decode("utf-8"), RECORDED_CANONICAL_JSON)

        parsed = parse_submit({"demo": "reserve", "class": "gpu"})
        self.assertEqual((parsed.kind, parsed.resource_class), ("job", "gpu"))
        self.assertEqual(parsed.local["class"], "gpu")
        self.assertEqual(parsed.payload_digest, RECORDED_PAYLOAD_DIGEST)

    def test_known_recorded_catalog_digest(self) -> None:
        """Golden digest: independent of handoff_vocab constants.

        Canonical JSON bytes:
        {"accounts":48,"discount_bps":300,"horizon":12,"lapse_bps":80,
         "paths":96,"seed":17070,"workload":"reserve"}
        payload_digest =
        sha256:77e9299f4b8ea4aeed46f71b91cc947d56e9bd169d795e70845123fef53d7e4e
        """
        canonical = (
            '{"accounts":48,"discount_bps":300,"horizon":12,"lapse_bps":80,'
            '"paths":96,"seed":17070,"workload":"reserve"}'
        )
        digest = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.assertEqual(
            digest,
            "sha256:77e9299f4b8ea4aeed46f71b91cc947d56e9bd169d795e70845123fef53d7e4e",
        )
        self.assertEqual(RECORDED_CANONICAL_JSON, canonical)
        self.assertEqual(RECORDED_PAYLOAD_DIGEST, digest)
        self.assertEqual(
            digest_canonical(
                {
                    "accounts": 48,
                    "discount_bps": 300,
                    "horizon": 12,
                    "lapse_bps": 80,
                    "paths": 96,
                    "seed": 17070,
                    "workload": "reserve",
                }
            ),
            digest,
        )

        parsed = parse_submit({"demo": "reserve"})
        self.assertEqual(parsed.kind, "job")
        self.assertEqual(parsed.resource_class, "cpu")
        self.assertEqual(parsed.local["catalog"], "recorded")
        self.assertEqual(parsed.payload_digest, digest)
        self.assertEqual(parsed.payload_bytes.decode("utf-8"), canonical)

        live_canonical = (
            '{"accounts":640,"discount_bps":300,"horizon":40,"lapse_bps":80,'
            '"paths":2048,"seed":17070,"workload":"reserve"}'
        )
        live_digest = "sha256:" + hashlib.sha256(
            live_canonical.encode("utf-8")
        ).hexdigest()
        self.assertEqual(
            live_digest,
            "sha256:9207915bfa0c563ccc6d167ef79db47c5318219bd0269aae5c4b8313d2fceea6",
        )
        live = parse_submit({"demo": "reserve", "catalog": "live"})
        self.assertEqual(live.kind, "job")
        self.assertEqual(live.resource_class, "cpu")
        self.assertEqual(live.local["catalog"], "live")
        self.assertEqual(live.local["accounts"], 640)
        self.assertEqual(live.local["horizon"], 40)
        self.assertEqual(live.local["paths"], 2048)
        self.assertEqual(live.local["seed"], 17070)
        self.assertEqual(live.local["lapse_bps"], 80)
        self.assertEqual(live.local["discount_bps"], 300)
        self.assertEqual(live.payload_digest, live_digest)
        self.assertEqual(live.payload_bytes.decode("utf-8"), live_canonical)
        self.assertEqual(LIVE_PAYLOAD_DIGEST, live_digest)
        self.assertNotEqual(live_digest, digest)

        parity_canonical = (
            '{"accounts":2048,"discount_bps":300,"horizon":64,"lapse_bps":80,'
            '"paths":4096,"seed":17070,"workload":"reserve"}'
        )
        parity_digest = "sha256:" + hashlib.sha256(
            parity_canonical.encode("utf-8")
        ).hexdigest()
        self.assertEqual(
            parity_digest,
            "sha256:e180d2c2e3589b8762f92efa1bedb3d53ffeeb16648581ba13d537bcd3311102",
        )
        self.assertEqual(PARITY_CANONICAL_JSON, parity_canonical)
        self.assertEqual(PARITY_PAYLOAD_DIGEST, parity_digest)
        parity = parse_submit({"demo": "reserve", "catalog": "parity"})
        self.assertEqual(parity.kind, "job")
        self.assertEqual(parity.resource_class, "cpu")
        self.assertEqual(parity.local["catalog"], "parity")
        self.assertEqual(parity.local["accounts"], 2048)
        self.assertEqual(parity.local["horizon"], 64)
        self.assertEqual(parity.local["paths"], 4096)
        self.assertEqual(parity.local["seed"], 17070)
        self.assertEqual(parity.local["lapse_bps"], 80)
        self.assertEqual(parity.local["discount_bps"], 300)
        self.assertEqual(parity.payload_digest, parity_digest)
        self.assertEqual(parity.payload_bytes.decode("utf-8"), parity_canonical)
        alias = parse_submit({"demo": "reserve", "catalog": "parity-scale"})
        self.assertEqual(alias.local["catalog"], "parity")
        self.assertEqual(alias.payload_digest, parity_digest)
        self.assertNotEqual(parity_digest, digest)
        self.assertNotEqual(parity_digest, live_digest)

    def test_reserve_payload_digest_is_stable(self) -> None:
        a = parse_submit({"demo": "reserve", "stages": 3, "label": "ux-seed", "seconds": 6})
        b = parse_submit({"seconds": 6, "demo": "reserve", "label": "ux-seed", "stages": 3})
        c = parse_submit({"demo": "reserve"})
        self.assertEqual(a.payload_digest, b.payload_digest)
        self.assertEqual(a.payload_digest, c.payload_digest)
        self.assertEqual(a.payload_bytes, b.payload_bytes)
        self.assertEqual(a.payload_bytes.decode("utf-8"), RECORDED_CANONICAL_JSON)
        self.assertEqual(a.payload_digest, digest_for(recorded_params()))
        self.assertEqual(a.payload_digest, RECORDED_PAYLOAD_DIGEST)
        shuffled = {
            "seed": 17070,
            "workload": "reserve",
            "paths": 96,
            "lapse_bps": 80,
            "accounts": 48,
            "discount_bps": 300,
            "horizon": 12,
        }
        self.assertEqual(digest_canonical(shuffled), RECORDED_PAYLOAD_DIGEST)
        live = parse_submit({"demo": "reserve", "catalog": "live"})
        self.assertEqual(live.payload_digest, LIVE_PAYLOAD_DIGEST)
        self.assertNotEqual(live.payload_digest, RECORDED_PAYLOAD_DIGEST)
        parity = parse_submit({"demo": "reserve", "catalog": "parity"})
        self.assertEqual(parity.payload_digest, PARITY_PAYLOAD_DIGEST)
        self.assertNotEqual(parity.payload_digest, RECORDED_PAYLOAD_DIGEST)
        self.assertNotEqual(parity.payload_digest, LIVE_PAYLOAD_DIGEST)
        custom = parse_submit({"demo": "reserve", "accounts": 49})
        self.assertNotEqual(custom.payload_digest, RECORDED_PAYLOAD_DIGEST)
        self.assertEqual(custom.local["accounts"], 49)

    def test_reserve_rejects_bad_params_and_alias(self) -> None:
        with self.assertRaises(InvalidDemo):
            parse_submit({"demo": "reserve_ifrs17"})
        with self.assertRaises(InvalidDemo):
            parse_submit({"demo": "reserve", "stages": 1})
        with self.assertRaises(InvalidDemo):
            parse_submit({"demo": "reserve", "stages": True})
        with self.assertRaises(InvalidDemo):
            parse_submit({"demo": "reserve", "seconds": -1})
        with self.assertRaises(InvalidDemo):
            parse_submit({"demo": "reserve", "label": ""})
        with self.assertRaises(InvalidClass):
            parse_submit({"demo": "reserve", "class": "tpu"})
        with self.assertRaises(InvalidHandoff):
            parse_submit({"demo": "echo", "label": "nope"})
        with self.assertRaises(InvalidDemo):
            parse_submit({"demo": "reserve", "catalog": "ifrs17"})
        with self.assertRaises(InvalidDemo):
            parse_submit({"demo": "reserve", "accounts": True})
        with self.assertRaises(InvalidDemo):
            parse_submit({"demo": "reserve", "accounts": 0})
        with self.assertRaises(InvalidHandoff):
            parse_submit({"demo": "reserve", "message": "nope"})

    def test_engine_smuggle_keys_and_schemes(self) -> None:
        digest = _digest()
        probes = [
            {"kind": "ray://127.0.0.1:10001", "class": "cpu", "payload_digest": digest},
            {
                "kind": "job",
                "class": "cpu",
                "payload_digest": digest,
                "engine": "local",
            },
            {
                "kind": "job",
                "class": "cpu",
                "payload_digest": digest,
                "engine_kind": "compute-local",
            },
            {
                "kind": "job",
                "class": "cpu",
                "payload_digest": digest,
                "engine_url": "http://cluster",
            },
            {
                "kind": "job",
                "class": "cpu",
                "payload_digest": digest,
                "ray_address": "127.0.0.1:10001",
            },
            {
                "kind": "job",
                "class": "cpu",
                "payload_digest": digest,
                "temporal_host": "localhost:7233",
            },
            {
                "kind": "job",
                "class": "cpu",
                "payload_digest": digest,
                "workflow_id": "wf-1",
            },
            {
                "kind": "job",
                "class": "cpu",
                "payload_digest": digest,
                "task_queue": "sos",
            },
            {
                "kind": "job",
                "class": "cpu",
                "payload_digest": digest,
                "payload": {"code": "x"},
            },
            {"kind": "job", "class": "cpu", "payload_digest": digest, "url": "x"},
            {"kind": "job", "class": "cpu", "payload_digest": digest, "uri": "x"},
            {"kind": "job", "class": "cpu", "payload_digest": digest, "endpoint": "x"},
            {"kind": "job", "class": "cpu", "payload_digest": digest, "address": "x"},
            {"kind": "job", "class": "cpu", "payload_digest": "s3://bucket/key"},
            {"kind": "job", "class": "cpu", "payload_digest": digest, "image": "busybox"},
            {"demo": "reserve", "engine": "local"},
            {"demo": "reserve", "seconds": 8, "ray": "cluster"},
        ]
        for raw in probes:
            with self.subTest(raw=raw):
                with self.assertRaises(EngineSmuggle) as ctx:
                    parse_submit(raw)
                self.assertEqual(ctx.exception.to_dict()["error"], "engine_smuggle")


class JobStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = JobStore(step_seconds=0.02)

    def test_echo_submit_get_list_succeeds(self) -> None:
        job = self.store.submit({"demo": "echo", "message": "ping"})
        self.assertEqual(job.kind, "job")
        self.assertEqual(job.resource_class, "cpu")
        self.assertEqual(job.status, STATUS_QUEUED)
        self.assertNotEqual(job.status, "accepted")
        self.assertEqual(job.payload_digest, digest_canonical({"demo": "echo", "message": "ping"}))
        self.assertEqual(job.local["demo"], "echo")
        self.assertEqual(job.local["message"], "ping")
        self.assertEqual(job.local["backed"], BACKED_STUB)
        self.assertIsNone(job.error)
        seam = job.to_seam()
        for key in ("id", "kind", "class", "payload_digest", "status"):
            self.assertIn(key, seam)
        blob = str(job.to_dict())
        self.assertNotIn("sos.demo.echo", blob)
        for key in job.to_dict():
            self.assertNotIn(key, ("engine", "ray", "temporal", "aws", "image", "spec"))

        fetched = self.store.get(job.id)
        self.assertEqual(fetched.id, job.id)

        wait_status(self.store, job.id, {"succeeded"})
        done = self.store.get(job.id)
        self.assertEqual(done.status, "succeeded")
        self.assertEqual(done.message, "ping")

        listed = self.store.list()
        self.assertEqual([j.id for j in listed], [job.id])

    def test_opaque_handoff_stub_succeeds(self) -> None:
        job = self.store.submit(
            {"kind": "chunk", "class": "gpu", "payload_digest": _digest()}
        )
        self.assertEqual(job.kind, "chunk")
        self.assertEqual(job.resource_class, "gpu")
        self.assertEqual(job.status, STATUS_QUEUED)
        self.assertEqual(job.local, {"backed": BACKED_STUB})
        wait_status(self.store, job.id, {"succeeded"})
        done = self.store.get(job.id)
        self.assertIn("opaque", done.message or "")

    def test_list_newest_first(self) -> None:
        a = self.store.submit({"demo": "echo", "message": "a"})
        b = self.store.submit({"demo": "echo", "message": "b"})
        ids = [j.id for j in self.store.list()]
        self.assertEqual(ids[0], b.id)
        self.assertEqual(ids[1], a.id)

    def test_unknown_kind(self) -> None:
        with self.assertRaises(InvalidKind) as ctx:
            self.store.submit(
                {"kind": "sos.demo.nope", "class": "cpu", "payload_digest": _digest()}
            )
        body = ctx.exception.to_dict()
        self.assertEqual(body["error"], "invalid_kind")
        self.assertIn("job", body["allowed"])

    def test_invalid_sleep_demo(self) -> None:
        with self.assertRaises(InvalidDemo):
            self.store.submit({"demo": "sleep", "seconds": -1})
        with self.assertRaises(InvalidDemo):
            self.store.submit({"demo": "sleep", "seconds": True})
        with self.assertRaises(InvalidDemo):
            self.store.submit({"demo": "sleep", "seconds": 99})

    def test_extra_seam_field(self) -> None:
        with self.assertRaises(InvalidHandoff):
            self.store.submit(
                {
                    "kind": "job",
                    "class": "cpu",
                    "payload_digest": _digest(),
                    "spec": {"message": "x"},
                }
            )

    def test_get_missing(self) -> None:
        with self.assertRaises(JobNotFound) as ctx:
            self.store.get("missing")
        self.assertEqual(ctx.exception.http_status, 404)

    def test_cancel_sleep_before_terminal(self) -> None:
        job = self.store.submit({"demo": "sleep", "seconds": 8})
        canceled = self.store.cancel(job.id)
        self.assertEqual(canceled.status, STATUS_CANCELED)
        self.assertEqual(canceled.status, "canceled")
        self.assertNotEqual(canceled.status, "cancelled")
        time.sleep(0.08)
        again = self.store.get(job.id)
        self.assertEqual(again.status, "canceled")
        self.assertIsNone(again.error)

    def test_reserve_lifecycle_named_stages(self) -> None:
        job = self.store.submit(
            {"demo": "reserve", "label": "ux-seed", "stages": 3, "seconds": 0.3}
        )
        self.assertEqual(job.kind, "job")
        self.assertEqual(job.resource_class, "cpu")
        self.assertEqual(job.status, STATUS_QUEUED)
        self.assertEqual(job.local["demo"], "reserve")
        self.assertEqual(job.local["backed"], BACKED_STUB)
        self.assertEqual(job.payload_digest, RECORDED_PAYLOAD_DIGEST)
        seen = set()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            snap = self.store.get(job.id)
            if snap.local and snap.local.get("stage"):
                seen.add(snap.local["stage"])
            if snap.status == "succeeded":
                break
            time.sleep(0.01)
        done = self.store.get(job.id)
        self.assertEqual(done.status, "succeeded")
        self.assertIn("UX seed", done.message or "")
        self.assertIn("no IFRS17 math", done.message or "")
        self.assertNotIn("engine", done.to_dict())
        self.assertIn("admit", seen)
        self.assertIn("project", seen)
        self.assertIn("fold", seen)
        self.assertEqual(done.local["stage"], "fold")
        self.assertEqual(done.local["stage_index"], 3)

    def test_reserve_cancel_mid_flight(self) -> None:
        job = self.store.submit({"demo": "reserve", "stages": 3, "seconds": 8})
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            snap = self.store.get(job.id)
            if snap.status == "running" and (snap.local or {}).get("stage"):
                break
            time.sleep(0.01)
        else:
            self.fail("reserve job never reached a named running stage")
        canceled = self.store.cancel(job.id)
        self.assertEqual(canceled.status, "canceled")
        self.assertNotEqual(canceled.status, "cancelled")
        self.assertEqual(canceled.message, "canceled by operator")
        time.sleep(0.08)
        again = self.store.get(job.id)
        self.assertEqual(again.status, "canceled")
        self.assertIsNone(again.error)
        self.assertIn(again.local.get("stage"), {"admit", "project", "fold"})

    def test_reserve_gpu_class_is_label_only(self) -> None:
        job = self.store.submit({"demo": "reserve", "class": "gpu", "seconds": 0})
        wait_status(self.store, job.id, {"succeeded"})
        done = self.store.get(job.id)
        self.assertEqual(done.resource_class, "gpu")
        self.assertIn("label only", done.message or "")
        self.assertIn("no GPU kernels", done.message or "")
        blob = str(done.to_dict())
        self.assertNotIn("ray://", blob)
        self.assertNotIn("temporal://", blob)

    def test_cancel_missing(self) -> None:
        with self.assertRaises(JobNotFound):
            self.store.cancel("nope")

    def test_cancel_terminal_conflict(self) -> None:
        job = self.store.submit({"demo": "echo", "message": "x"})
        wait_status(self.store, job.id, {"succeeded"})
        with self.assertRaises(AlreadyTerminal) as ctx:
            self.store.cancel(job.id)
        self.assertEqual(ctx.exception.http_status, 409)
        body = ctx.exception.to_dict()
        self.assertEqual(body["status"], "succeeded")
        self.assertIn("not pause", body["note"].lower())

    def test_progress_and_events_reserve(self) -> None:
        job = self.store.submit(
            {"demo": "reserve", "label": "ux-seed", "stages": 3, "seconds": 8}
        )
        progress = self.store.progress(job.id)
        self.assertEqual(progress["id"], job.id)
        self.assertEqual(progress["status"], STATUS_QUEUED)
        self.assertIsNone(progress["stage"])
        self.assertEqual(progress["backed"], BACKED_STUB)
        self.assertEqual(progress["source"], PROGRESS_SOURCE_STUB)
        self.assertEqual(progress["stages_total"], 3)
        self.assertIs(progress["pause_resume"], False)
        self.assertIn("not iec chunk progress", progress["note"])
        self.assertNotIn("parallelism claimed", progress["note"])
        self.assertNotIn("stages_completed", progress)
        self.assertNotIn("fraction", progress)

        events = self.store.events(job.id)
        self.assertEqual(events["id"], job.id)
        self.assertEqual(events["source"], EVENTS_SOURCE_MEMORY)
        self.assertIn("not a regulatory audit", events["note"])
        self.assertNotIn("events_durable", events)
        names = [item["event"] for item in events["events"]]
        self.assertIn("submitted", names)
        self.assertIn("backed", names)
        self.assertTrue(any(item["detail"] == BACKED_STUB for item in events["events"]))

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            snap = self.store.get(job.id)
            if snap.status == "running" and (snap.local or {}).get("stage"):
                break
            time.sleep(0.01)
        else:
            self.fail("reserve job never reached a named running stage")

        mid = self.store.progress(job.id)
        self.assertEqual(mid["status"], "running")
        self.assertIn(mid["stage"], {"admit", "project", "fold"})
        self.assertEqual(mid["stages_total"], 3)
        self.assertIn(mid["stage_index"], {1, 2, 3})
        self.assertEqual(mid["source"], PROGRESS_SOURCE_STUB)
        self.assertIn("stub stage metadata", mid["note"].lower())

        canceled = self.store.cancel(job.id)
        self.assertEqual(canceled.status, "canceled")
        trail = [item["event"] for item in canceled.events]
        self.assertIn("canceled", trail)
        self.assertIn("stage", trail)
        body = self.store.events(job.id)
        self.assertEqual(body["source"], EVENTS_SOURCE_MEMORY)
        self.assertEqual(body["events"][-1]["event"], "canceled")
        self.assertEqual(body["events"][-1]["detail"], "canceled by operator")
        handoff = self.store.handoff(job.id)
        self.assertNotIn("events", handoff)
        self.assertNotIn("progress", handoff)

    def test_progress_echo_has_no_fake_chunks(self) -> None:
        job = self.store.submit({"demo": "echo", "message": "hi"})
        wait_status(self.store, job.id, {"succeeded"})
        progress = self.store.progress(job.id)
        self.assertEqual(progress["status"], "succeeded")
        self.assertIsNone(progress["stage"])
        self.assertNotIn("stages_total", progress)
        self.assertNotIn("stage_index", progress)
        self.assertNotIn("stages_completed", progress)
        self.assertNotIn("fraction", progress)
        self.assertEqual(progress["source"], PROGRESS_SOURCE_STUB)
        self.assertIn("not iec chunk progress", progress["note"])
        events = [item["event"] for item in self.store.events(job.id)["events"]]
        self.assertEqual(self.store.events(job.id)["source"], EVENTS_SOURCE_MEMORY)
        self.assertIn("submitted", events)
        self.assertIn("succeeded", events)
        self.assertNotIn("pause", events)
        self.assertNotIn("resume", events)

    def test_handoff_export_and_payload_bytes(self) -> None:
        job = self.store.submit({"demo": "reserve", "label": "ux-seed", "stages": 3, "seconds": 0})
        handoff = self.store.handoff(job.id)
        self.assertEqual(
            list(handoff.keys()),
            ["id", "kind", "class", "payload_digest", "status"],
        )
        self.assertEqual(handoff["id"], job.id)
        self.assertEqual(handoff["kind"], "job")
        self.assertEqual(handoff["class"], "cpu")
        self.assertEqual(handoff["payload_digest"], job.payload_digest)
        self.assertNotIn("payload", handoff)
        self.assertNotIn("local", handoff)
        blob = str(handoff)
        self.assertNotIn("ray", blob)
        self.assertNotIn("temporal", blob)
        self.assertNotIn("aws", blob)

        record = self.store.payload(job.id)
        self.assertEqual(record["payload_digest"], job.payload_digest)
        self.assertEqual(record["encoding"], "canonical-json")
        self.assertNotIn("payload", record)
        self.assertEqual(record["utf8"], RECORDED_CANONICAL_JSON)
        self.assertEqual(bytes.fromhex(record["hex"]).decode("utf-8"), record["utf8"])
        self.assertEqual(record["payload_digest"], RECORDED_PAYLOAD_DIGEST)
        wait_status(self.store, job.id, {"succeeded"})

    def test_opaque_submit_has_no_stored_payload(self) -> None:
        job = self.store.submit(
            {"kind": "job", "class": "cpu", "payload_digest": _digest()}
        )
        with self.assertRaises(PayloadUnknown) as ctx:
            self.store.payload(job.id)
        self.assertEqual(ctx.exception.http_status, 404)
        self.assertEqual(ctx.exception.to_dict()["error"], "payload_unknown")
        handoff = self.store.handoff(job.id)
        self.assertEqual(handoff["payload_digest"], _digest())
        self.assertNotIn("payload", handoff)

    def test_runtime_hook_admit_then_cancel_fallback(self) -> None:
        class RecordingHook:
            def __init__(self) -> None:
                self.admits: list[tuple[dict[str, str], bytes | None]] = []
                self.cancels: list[tuple[str, dict | None]] = []
                self.admit_ok = True
                self.cancel_ok = True

            def admit(self, handoff: dict[str, str], payload_bytes: bytes | None):
                self.admits.append((handoff, payload_bytes))
                if not self.admit_ok:
                    return None
                return {"accepted": True}

            def cancel(self, job_id: str, runtime_ref: dict | None) -> bool:
                self.cancels.append((job_id, runtime_ref))
                if not self.cancel_ok:
                    raise RuntimeError("hook boom")
                return True

            def status(self, job_id: str, runtime_ref: dict | None):
                return None

        hook = RecordingHook()
        store = JobStore(step_seconds=0.02, runtime_hook=hook)
        job = store.submit({"demo": "reserve", "seconds": 8})
        self.assertEqual(job.local["backed"], "runtime")
        self.assertEqual(len(hook.admits), 1)
        self.assertEqual(hook.admits[0][0]["kind"], "job")
        self.assertNotIn("payload", hook.admits[0][0])
        time.sleep(0.15)
        still = store.get(job.id)
        self.assertEqual(still.status, STATUS_QUEUED)
        canceled = store.cancel(job.id)
        self.assertEqual(canceled.status, STATUS_CANCELED)
        self.assertEqual(len(hook.cancels), 1)
        self.assertEqual(hook.cancels[0][0], job.id)

        hook.admit_ok = False
        stub = store.submit({"demo": "echo", "message": "fallback"})
        self.assertEqual(stub.local["backed"], BACKED_STUB)
        wait_status(store, stub.id, {"succeeded"})

        hook.admit_ok = True
        hook.cancel_ok = False
        live = store.submit({"demo": "reserve", "seconds": 8})
        canceled = store.cancel(live.id)
        self.assertEqual(canceled.status, "canceled")
        self.assertEqual(canceled.message, "canceled by operator")

    def test_pause_resume_stub_only_refused(self) -> None:
        job = self.store.submit({"demo": "sleep", "seconds": 8})
        self.assertEqual(job.local["backed"], BACKED_STUB)
        self.assertIs(job.to_dict()["pause_resume"], False)
        with self.assertRaises(StubOnly) as ctx:
            self.store.pause(job.id)
        self.assertEqual(ctx.exception.http_status, 409)
        body = ctx.exception.to_dict()
        self.assertEqual(body["error"], "stub_only")
        self.assertEqual(body["action"], "pause")
        self.assertIn("durable path", body["detail"])
        self.assertIn(
            "python3 -m runtime.apply reserve-temporal pause|resume",
            body["detail"],
        )
        with self.assertRaises(StubOnly) as ctx:
            self.store.resume(job.id)
        self.assertEqual(ctx.exception.to_dict()["action"], "resume")
        self.store.cancel(job.id)

    def test_pause_resume_durable_hook(self) -> None:
        class TinyHook:
            def __init__(self) -> None:
                self.reported: str | None = "running"
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

        hook = TinyHook()
        store = JobStore(step_seconds=0.02, runtime_hook=hook)
        job = store.submit({"demo": "reserve", "seconds": 8})
        self.assertEqual(job.local["backed"], "runtime")
        self.assertEqual(job.status, "running")
        self.assertIs(job.to_dict()["pause_resume"], True)
        self.assertIs(job.to_progress()["pause_resume"], True)

        paused = store.pause(job.id)
        self.assertEqual(paused.status, "paused")
        self.assertEqual(paused.message, "paused via runtime hook")
        self.assertEqual(hook.pauses, [job.id])
        self.assertIn("paused", [item["event"] for item in paused.events])
        self.assertEqual(store.handoff(job.id)["status"], "paused")
        self.assertNotIn("pause_resume", store.handoff(job.id))

        with self.assertRaises(IllegalTransition) as ctx:
            store.pause(job.id)
        self.assertEqual(ctx.exception.http_status, 409)
        self.assertEqual(ctx.exception.to_dict()["error"], "illegal_transition")
        self.assertEqual(ctx.exception.to_dict()["status"], "paused")

        resumed = store.resume(job.id)
        self.assertEqual(resumed.status, "running")
        self.assertEqual(hook.resumes, [job.id])
        self.assertIn("running", [item["event"] for item in resumed.events])

        with self.assertRaises(IllegalTransition):
            store.resume(job.id)

        canceled = store.cancel(job.id)
        self.assertEqual(canceled.status, "canceled")

        hook.reported = None
        queued = store.submit({"demo": "reserve", "seconds": 8})
        self.assertEqual(queued.status, STATUS_QUEUED)
        with self.assertRaises(IllegalTransition) as ctx:
            store.pause(queued.id)
        self.assertEqual(ctx.exception.to_dict()["status"], "queued")
        with self.assertRaises(IllegalTransition):
            store.resume(queued.id)

        hook.reported = "succeeded"
        done = store.submit({"demo": "echo", "message": "x"})
        self.assertEqual(done.status, "succeeded")
        with self.assertRaises(AlreadyTerminal):
            store.pause(done.id)
        with self.assertRaises(AlreadyTerminal):
            store.resume(done.id)

        paused_hook = TinyHook()
        paused_store = JobStore(step_seconds=0.02, runtime_hook=paused_hook)
        live = paused_store.submit({"demo": "reserve", "seconds": 8})
        paused_store.pause(live.id)
        canceled_paused = paused_store.cancel(live.id)
        self.assertEqual(canceled_paused.status, "canceled")

    def test_inert_hook_has_noop_pause_resume(self) -> None:
        from sos.runtime_hook import InertRuntimeHandoffHook

        hook = InertRuntimeHandoffHook()
        self.assertIs(hook.pause("id", None), False)
        self.assertIs(hook.resume("id", None), False)
        self.assertIs(hook.cancel("id", None), False)
        self.assertIsNone(hook.admit({}, None))
        self.assertIsNone(hook.status("id", None))
        self.assertIsNone(hook.progress("id", None))
        self.assertIsNone(hook.events("id", None))

    def test_progress_durable_hook_counters(self) -> None:
        class DurableProgressHook:
            def __init__(self) -> None:
                self.reported = "running"
                self.calls: list[tuple[str, dict | None]] = []

            def admit(self, handoff, payload_bytes):
                return {"accepted": True}

            def cancel(self, job_id, runtime_ref) -> bool:
                return True

            def status(self, job_id, runtime_ref):
                return self.reported

            def pause(self, job_id, runtime_ref) -> bool:
                return False

            def resume(self, job_id, runtime_ref) -> bool:
                return False

            def progress(self, job_id, runtime_ref):
                self.calls.append((job_id, runtime_ref))
                return {
                    "stage": 2,
                    "stages_total": 4,
                    "stages_completed": 2,
                    "fraction": 0.5,
                    "inner_steps": 96,
                    "progress": {
                        "stage": 2,
                        "stages_total": 4,
                        "stages_completed": 2,
                        "fraction": 0.5,
                        "inner_steps": 96,
                    },
                }

        hook = DurableProgressHook()
        store = JobStore(step_seconds=0.02, runtime_hook=hook)
        job = store.submit({"demo": "reserve", "seconds": 8})
        self.assertEqual(job.local["backed"], "runtime")
        body = store.progress(job.id)
        self.assertEqual(body["id"], job.id)
        self.assertEqual(body["status"], "running")
        self.assertEqual(body["source"], PROGRESS_SOURCE_DURABLE)
        self.assertEqual(body["backed"], "runtime")
        self.assertEqual(body["stage"], 2)
        self.assertEqual(body["stages_total"], 4)
        self.assertEqual(body["stages_completed"], 2)
        self.assertEqual(body["fraction"], 0.5)
        self.assertEqual(body["inner_steps"], 96)
        self.assertEqual(body["progress"]["stages_completed"], 2)
        self.assertIn("path-slices", body["note"].lower())
        self.assertIn("not iec planner", body["note"].lower())
        self.assertIn("not iec chunk progress", body["note"])
        self.assertNotIn("parallelism claimed", body["note"])
        self.assertEqual(len(hook.calls), 1)
        self.assertEqual(hook.calls[0][0], job.id)
        handoff = store.handoff(job.id)
        self.assertNotIn("progress", handoff)
        self.assertNotIn("source", handoff)
        store.cancel(job.id)

        class SilentDurableHook(DurableProgressHook):
            def progress(self, job_id, runtime_ref):
                return None

        silent = SilentDurableHook()
        fallback = JobStore(step_seconds=0.02, runtime_hook=silent)
        backed = fallback.submit({"demo": "reserve", "seconds": 8})
        stubby = fallback.progress(backed.id)
        self.assertEqual(stubby["source"], PROGRESS_SOURCE_STUB)
        self.assertNotIn("stages_completed", stubby)
        fallback.cancel(backed.id)

    def test_events_durable_hook_jsonl(self) -> None:
        class DurableEventsHook:
            def __init__(self) -> None:
                self.reported = "running"
                self.calls: list[tuple[str, dict | None]] = []
                self.payload: dict | list | None = {
                    "events": [
                        {
                            "ts": "2026-09-11T16:00:00Z",
                            "event": "admit",
                            "type": "WorkflowExecutionStarted",
                            "seq": 1,
                            "id": "cw_deadbeefdeadbeef",
                        },
                        {
                            "ts": "2026-09-11T16:00:01Z",
                            "event": "stage_completed",
                            "type": "StageCompleted",
                            "seq": 2,
                            "stages_completed": 1,
                        },
                        {
                            "ts": "2026-09-11T16:00:02Z",
                            "event": "pause",
                            "type": "WorkflowExecutionSignaled",
                            "signal": "pause",
                            "seq": 3,
                        },
                    ],
                    "events_durable": True,
                    "events_n": 3,
                }

            def admit(self, handoff, payload_bytes):
                return {"accepted": True}

            def cancel(self, job_id, runtime_ref) -> bool:
                return True

            def status(self, job_id, runtime_ref):
                return self.reported

            def pause(self, job_id, runtime_ref) -> bool:
                return False

            def resume(self, job_id, runtime_ref) -> bool:
                return False

            def events(self, job_id, runtime_ref):
                self.calls.append((job_id, runtime_ref))
                return self.payload

        hook = DurableEventsHook()
        store = JobStore(step_seconds=0.02, runtime_hook=hook)
        job = store.submit({"demo": "reserve", "seconds": 8})
        self.assertEqual(job.local["backed"], "runtime")
        body = store.events(job.id)
        self.assertEqual(body["id"], job.id)
        self.assertEqual(body["source"], EVENTS_SOURCE_DURABLE)
        self.assertIs(body["events_durable"], True)
        self.assertEqual(body["events_n"], 3)
        names = [item["event"] for item in body["events"]]
        self.assertEqual(names, ["admit", "stage_completed", "pause"])
        self.assertEqual(body["events"][0]["type"], "WorkflowExecutionStarted")
        self.assertEqual(body["events"][1]["type"], "StageCompleted")
        self.assertEqual(body["events"][2]["signal"], "pause")
        self.assertIn("jsonl", body["note"].lower())
        self.assertIn("not a siem", body["note"].lower())
        self.assertIn("/v1/audit/events", body["note"])
        self.assertNotIn("submitted", names)
        self.assertEqual(hook.calls[-1][0], job.id)
        resource = store.get(job.id).to_dict()
        self.assertEqual(resource["events_source"], EVENTS_SOURCE_DURABLE)
        self.assertIs(resource["events_durable"], True)
        self.assertEqual(resource["events_n"], 3)
        self.assertEqual([item["event"] for item in resource["events"]], names)
        handoff = store.handoff(job.id)
        self.assertNotIn("events", handoff)
        self.assertNotIn("events_source", handoff)
        self.assertNotIn("events_durable", handoff)
        store.cancel(job.id)

        hook.payload = [
            {
                "ts": "2026-09-11T16:10:00Z",
                "event": "succeed",
                "type": "WorkflowExecutionCompleted",
                "seq": 4,
            }
        ]
        listed = JobStore(step_seconds=0.02, runtime_hook=hook)
        listed_job = listed.submit({"demo": "echo", "message": "x"})
        listed_body = listed.events(listed_job.id)
        self.assertEqual(listed_body["source"], EVENTS_SOURCE_DURABLE)
        self.assertIs(listed_body["events_durable"], True)
        self.assertEqual(listed_body["events_n"], 1)
        self.assertEqual(listed_body["events"][0]["event"], "succeed")
        listed.cancel(listed_job.id)

        hook.payload = {
            "events": [
                {"ts": "2026-09-11T16:20:00Z", "event": "cancel", "type": "WorkflowExecutionCanceled"}
            ],
            "durable": True,
            "n": 1,
        }
        ctl = JobStore(step_seconds=0.02, runtime_hook=hook)
        ctl_job = ctl.submit({"demo": "reserve", "seconds": 8})
        ctl_body = ctl.events(ctl_job.id)
        self.assertEqual(ctl_body["source"], EVENTS_SOURCE_DURABLE)
        self.assertIs(ctl_body["events_durable"], True)
        self.assertEqual(ctl_body["events_n"], 1)
        self.assertEqual(ctl_body["events"][0]["event"], "cancel")
        ctl.cancel(ctl_job.id)

        class SilentDurableHook(DurableEventsHook):
            def events(self, job_id, runtime_ref):
                return None

        silent = SilentDurableHook()
        fallback = JobStore(step_seconds=0.02, runtime_hook=silent)
        backed = fallback.submit({"demo": "reserve", "seconds": 8})
        memory = fallback.events(backed.id)
        self.assertEqual(memory["source"], EVENTS_SOURCE_MEMORY)
        self.assertIn("submitted", [item["event"] for item in memory["events"]])
        self.assertNotIn("events_durable", memory)
        fallback.cancel(backed.id)

    def test_guest_never_imports_runtime(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        for path in [*root.joinpath("sos").glob("*.py"), root / "platform_run.py"]:
            text = path.read_text(encoding="utf-8")
            imports = [
                line.strip()
                for line in text.splitlines()
                if line.strip().startswith(("import ", "from "))
            ]
            blob = "\n".join(imports)
            self.assertNotIn("from runtime", blob, path)
            self.assertNotIn("import runtime", blob, path)
            # Opt-in lab adapter may subprocess reserve-temporal; nothing else.
            if path.name != "lab_ctl.py":
                self.assertNotIn("subprocess", text, path)
            self.assertNotIn("os.system", text, path)
            self.assertNotIn("Popen", text, path)

    def test_docs_match_confirmed_ctl_contract(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        vocab = root.joinpath("sos/handoff_vocab.py").read_text(encoding="utf-8")
        self.assertIn("runtime.reserve.recorded_params", vocab)
        self.assertIn("live_params", vocab)
        self.assertIn("parity_params", vocab)
        self.assertIn("digest_for", vocab)
        self.assertIn(
            "sha256:e180d2c2e3589b8762f92efa1bedb3d53ffeeb16648581ba13d537bcd3311102",
            vocab,
        )
        self.assertIn("docs/reserve.md", vocab)
        self.assertNotIn("TODO(#83)", vocab)
        self.assertNotIn("PR #84", vocab)
        self.assertIn(
            "sha256:77e9299f4b8ea4aeed46f71b91cc947d56e9bd169d795e70845123fef53d7e4e",
            vocab,
        )
        for name in ("README.md", "PANORAMIX_OPERATIONAL.md"):
            text = root.joinpath(name).read_text(encoding="utf-8")
            self.assertIn("python3 -m runtime.apply reserve-temporal", text, name)
            self.assertIn("python3 -m runtime.apply reserve-temporal pause", text, name)
            self.assertIn("python3 -m runtime.apply reserve-temporal resume", text, name)
            self.assertIn("python3 -m runtime.apply reserve-temporal progress", text, name)
            self.assertIn("reserve-temporal progress --id", text, name)
            self.assertIn("python3 -m runtime.apply reserve-temporal events", text, name)
            self.assertIn("reserve-temporal events --id", text, name)
            self.assertIn("local-reserve-temporal.example.yaml", text, name)
            self.assertIn("verified @ `63c4d8e`", text, name)
            self.assertIn("verified @ `d86552e`", text, name)
            self.assertIn("verified @ `3a164cd`", text, name)
            self.assertIn(".runtime/reserve-temporal/events/", text, name)
            self.assertIn("stages_completed", text, name)
            self.assertIn("stages_total", text, name)
            self.assertIn("nested `progress`", text, name)
            self.assertIn("pause|resume", text, name)
            self.assertIn("`paused`", text, name)
            self.assertNotIn("73c311c", text, name)
            self.assertNotIn("28437ea", text, name)
            self.assertNotIn("landing pr", text.lower(), name)
            self.assertNotIn("pending ci", text.lower(), name)
            self.assertNotIn("landing pr #92", text.lower(), name)
            self.assertNotIn("landing pr #97", text.lower(), name)
            self.assertNotIn("#97 is the landing", text.lower(), name)
            self.assertNotIn("runtime#89", text.lower(), name)
            self.assertNotIn("after #89", text.lower(), name)
            self.assertIn("runtime.apply compute-work", text, name)
            self.assertIn("does **not** call `runtime.apply compute-work`", text, name)
            self.assertIn("hook stays inert", text.lower(), name)
            self.assertIn("PANORAMIX_RUNTIME_ROOT", text, name)
            self.assertTrue(
                "fail closed" in text.lower() or "fails closed" in text.lower(),
                name,
            )
            self.assertNotIn("fixes #70", text.lower(), name)
            self.assertNotIn("fixes #78", text.lower(), name)
            self.assertIn("workflow cancel", text.lower(), name)
            self.assertIn("workflow_id", text, name)
            self.assertIn("task_queue", text, name)
            self.assertIn("not #78 done", text.lower(), name)
            self.assertIn("north_star_done", text, name)
            self.assertIn("runtime.reserve.digest_for", text, name)
            self.assertIn("recorded_params", text, name)
            self.assertIn("live_params", text, name)
            self.assertIn("parity_params", text, name)
            self.assertIn("docs/reserve.md", text, name)
            self.assertNotIn("until on main", text, name)
            self.assertNotIn("until those helpers", text, name)
            self.assertNotIn("until helpers land", text, name)
            self.assertIn(
                "sha256:e180d2c2e3589b8762f92efa1bedb3d53ffeeb16648581ba13d537bcd3311102",
                text,
                name,
            )
            self.assertIn("stub fallback", text.lower(), name)
            self.assertIn("operator binding", text.lower(), name)
            self.assertIn("guest→ctl HTTP", text, name)
            self.assertNotIn("digests will be aligned when #83 lands", text, name)
            self.assertNotIn("TODO(#83)", text, name)
            self.assertNotIn("PR #84", text, name)
            self.assertIn("#83 + remeasure", text, name)
            self.assertNotIn("awaiting runtime stamp", text.lower(), name)
            self.assertIn("not #70 done", text.lower(), name)
            self.assertIn("/progress", text, name)
            self.assertIn("/events", text, name)
            self.assertIn(
                "sha256:77e9299f4b8ea4aeed46f71b91cc947d56e9bd169d795e70845123fef53d7e4e",
                text,
                name,
            )

        ux = root.joinpath("docs/ux-side-by-side.md").read_text(encoding="utf-8")
        self.assertIn("run_lifecycle_monitoring.md", ux)
        self.assertIn("GET /v0/jobs/{id}/progress", ux)
        self.assertIn("GET /v0/jobs/{id}/events", ux)
        self.assertIn("local event trail", ux.lower())
        self.assertIn("not iec chunk progress", ux.lower())
        self.assertIn("**match** (thinner)", ux)
        self.assertIn("python3 -m runtime.apply reserve-temporal pause", ux)
        self.assertIn("python3 -m runtime.apply reserve-temporal resume", ux)
        self.assertIn("python3 -m runtime.apply reserve-temporal progress", ux)
        self.assertIn("reserve-temporal progress --id", ux)
        self.assertIn("python3 -m runtime.apply reserve-temporal events", ux)
        self.assertIn("reserve-temporal events --id", ux)
        self.assertIn(
            "| 1.2 Step/chunk progress | `GET /v1/jobs/{id}/progress` | **match** (thinner) |",
            ux,
        )
        self.assertIn(
            "| 4.1 Audit trail | `GET /v1/audit/events?job_id=…` | **match** (thinner) |",
            ux,
        )
        self.assertNotIn(
            "| 4.1 Audit trail | `GET /v1/audit/events?job_id=…` | **partial** |",
            ux,
        )
        self.assertIn("path-slices", ux.lower())
        self.assertIn("not iec planner", ux.lower())
        self.assertIn("- [ ] Real chunk / step progress", ux)
        self.assertNotIn("- [x] Real chunk / step progress", ux)
        self.assertIn("- [ ] Regulatory audit trail", ux)
        self.assertNotIn("- [x] Regulatory audit trail", ux)
        self.assertIn("siem", ux.lower())
        self.assertIn("not a SIEM", ux)
        self.assertIn("/v1/audit/events", ux)
        self.assertIn("stub_only", ux)
        self.assertIn("409", ux)
        self.assertIn("| 2.1 Pause |", ux)
        self.assertIn("| 3.1a Resume |", ux)
        self.assertNotIn("| 2.1 Pause | `POST /v1/jobs/{id}/pause` | **missing**", ux)
        self.assertNotIn("| 3.1a Resume | `POST /v1/jobs/{id}/resume` | **missing**", ux)
        self.assertIn("parity (parity-scale)", ux)
        self.assertIn("runtime.reserve.parity_params", ux)
        self.assertIn("digest_for", ux)
        self.assertIn("docs/reserve.md", ux)
        self.assertIn("recorded / live / parity (parity-scale)", ux)
        self.assertNotIn("until on main", ux)
        self.assertNotIn("until those helpers", ux)
        self.assertIn(
            "sha256:e180d2c2e3589b8762f92efa1bedb3d53ffeeb16648581ba13d537bcd3311102",
            ux,
        )
        self.assertIn("- [ ] `north_star_done: true`", ux)
        self.assertNotIn("- [x] `north_star_done: true`", ux)
        self.assertIn("- [ ] Operator/actuary path", ux)
        self.assertIn("does **not** mark #70 Done", ux)
        self.assertIn("reserve-temporal", ux)
        self.assertIn("temporal-local", ux)
        self.assertIn("local-reserve-temporal.example.yaml", ux)
        self.assertIn("verified @ `63c4d8e`", ux)
        self.assertIn("verified @ `d86552e`", ux)
        self.assertIn("verified @ `3a164cd`", ux)
        self.assertIn(".runtime/reserve-temporal/events/", ux)
        self.assertIn("stages_completed", ux)
        self.assertIn("stages_total", ux)
        self.assertIn("nested `progress`", ux)
        self.assertIn("pause|resume", ux)
        self.assertIn("`paused`", ux)
        self.assertNotIn("73c311c", ux)
        self.assertNotIn("28437ea", ux)
        self.assertNotIn("landing pr", ux.lower())
        self.assertNotIn("pending ci", ux.lower())
        self.assertNotIn("landing pr #92", ux.lower())
        self.assertNotIn("landing pr #97", ux.lower())
        self.assertNotIn("#97 is the landing", ux.lower())
        self.assertNotIn("runtime#89", ux.lower())
        self.assertNotIn("after #89", ux.lower())
        self.assertIn("- [ ] Temporal-backed UX", ux)
        self.assertNotIn("- [x] Temporal-backed UX", ux)
        self.assertIn("PANORAMIX_RUNTIME_ROOT", ux)
        self.assertIn("opt-in lab", ux.lower())
        self.assertIn("workflow cancel", ux.lower())
        self.assertNotIn("ray:", ux)
        self.assertNotIn("temporal:", ux)


if __name__ == "__main__":
    unittest.main()
