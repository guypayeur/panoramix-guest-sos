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
