"""Job store, handoff parse, and stub runner — no sockets."""

from __future__ import annotations

import time
import unittest

from sos.errors import (
    AlreadyTerminal,
    EngineSmuggle,
    InvalidClass,
    InvalidDemo,
    InvalidDigest,
    InvalidHandoff,
    InvalidKind,
    JobNotFound,
)
from sos.handoff import digest_canonical, parse_submit
from sos.handoff_vocab import STATUS_CANCELED, STATUS_QUEUED
from sos.jobs import JobStore


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
        kind, cls, digest, local = parse_submit(
            {"kind": "job", "class": "cpu", "payload_digest": _digest()}
        )
        self.assertEqual(kind, "job")
        self.assertEqual(cls, "cpu")
        self.assertEqual(digest, _digest())
        self.assertIsNone(local)

    def test_stage_gpu_handoff(self) -> None:
        kind, cls, digest, local = parse_submit(
            {"kind": "stage", "class": "gpu", "payload_digest": _digest("cd")}
        )
        self.assertEqual((kind, cls, digest, local), ("stage", "gpu", _digest("cd"), None))

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
        kind, cls, digest, local = parse_submit({"demo": "echo", "message": "ping"})
        self.assertEqual(kind, "job")
        self.assertEqual(cls, "cpu")
        self.assertEqual(digest, digest_canonical({"demo": "echo", "message": "ping"}))
        self.assertRegex(digest, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(local, {"demo": "echo", "message": "ping"})

    def test_reserve_synthesizes_opaque_job(self) -> None:
        kind, cls, digest, local = parse_submit(
            {"demo": "reserve", "label": "ux-seed", "stages": 3, "seconds": 6}
        )
        self.assertEqual(kind, "job")
        self.assertEqual(cls, "cpu")
        expected = {
            "class": "cpu",
            "demo": "reserve",
            "label": "ux-seed",
            "seconds": 6,
            "stages": 3,
        }
        self.assertEqual(digest, digest_canonical(expected))
        self.assertEqual(local, expected)
        self.assertNotEqual(local["demo"], "reserve_ifrs17")

    def test_reserve_defaults_and_gpu_label(self) -> None:
        kind, cls, digest, local = parse_submit({"demo": "reserve"})
        self.assertEqual((kind, cls), ("job", "cpu"))
        self.assertEqual(local["label"], "reserve-shaped")
        self.assertEqual(local["stages"], 3)
        self.assertEqual(local["seconds"], 6)
        self.assertEqual(digest, digest_canonical(local))

        kind, cls, digest, local = parse_submit({"demo": "reserve", "class": "gpu"})
        self.assertEqual((kind, cls), ("job", "gpu"))
        self.assertEqual(local["class"], "gpu")
        self.assertEqual(digest, digest_canonical(local))

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
        self.assertEqual(job.local, {"demo": "echo", "message": "ping"})
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
        self.assertIsNone(job.local)
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
        self.assertEqual(
            job.payload_digest,
            digest_canonical(
                {
                    "class": "cpu",
                    "demo": "reserve",
                    "label": "ux-seed",
                    "seconds": 0.3,
                    "stages": 3,
                }
            ),
        )
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
        self.assertEqual(ctx.exception.to_dict()["status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
