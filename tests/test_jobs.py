"""Job store and stub runner — no sockets."""

from __future__ import annotations

import time
import unittest

from sos.jobs import (
    KIND_ECHO,
    KIND_SLEEP,
    AlreadyTerminal,
    InvalidSpec,
    JobNotFound,
    JobStore,
    UnknownKind,
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


class JobStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = JobStore(step_seconds=0.02)

    def test_echo_submit_get_list_succeeds(self) -> None:
        job = self.store.submit(KIND_ECHO, {"message": "ping"})
        self.assertEqual(job.kind, KIND_ECHO)
        self.assertIn(job.status, ("accepted", "queued", "running", "succeeded"))
        self.assertEqual(job.spec, {"message": "ping"})
        self.assertIsNone(job.error)
        for key in job.to_dict():
            self.assertNotIn(key, ("engine", "ray", "temporal", "aws", "image"))

        fetched = self.store.get(job.id)
        self.assertEqual(fetched.id, job.id)

        wait_status(self.store, job.id, {"succeeded"})
        done = self.store.get(job.id)
        self.assertEqual(done.status, "succeeded")
        self.assertEqual(done.message, "ping")

        listed = self.store.list()
        self.assertEqual([j.id for j in listed], [job.id])

    def test_list_newest_first(self) -> None:
        a = self.store.submit(KIND_ECHO, {"message": "a"})
        b = self.store.submit(KIND_ECHO, {"message": "b"})
        ids = [j.id for j in self.store.list()]
        self.assertEqual(ids[0], b.id)
        self.assertEqual(ids[1], a.id)

    def test_unknown_kind(self) -> None:
        with self.assertRaises(UnknownKind) as ctx:
            self.store.submit("sos.demo.nope", {})
        body = ctx.exception.to_dict()
        self.assertEqual(body["error"], "unknown_kind")
        self.assertIn("sos.demo.echo", body["allowed"])

    def test_invalid_sleep_spec(self) -> None:
        with self.assertRaises(InvalidSpec):
            self.store.submit(KIND_SLEEP, {"seconds": -1})
        with self.assertRaises(InvalidSpec):
            self.store.submit(KIND_SLEEP, {"seconds": True})
        with self.assertRaises(InvalidSpec):
            self.store.submit(KIND_SLEEP, {"seconds": 99})

    def test_get_missing(self) -> None:
        with self.assertRaises(JobNotFound) as ctx:
            self.store.get("missing")
        self.assertEqual(ctx.exception.http_status, 404)

    def test_cancel_sleep_before_terminal(self) -> None:
        job = self.store.submit(KIND_SLEEP, {"seconds": 8})
        cancelled = self.store.cancel(job.id)
        self.assertEqual(cancelled.status, "cancelled")
        time.sleep(0.08)
        again = self.store.get(job.id)
        self.assertEqual(again.status, "cancelled")
        self.assertIsNone(again.error)

    def test_cancel_missing(self) -> None:
        with self.assertRaises(JobNotFound):
            self.store.cancel("nope")

    def test_cancel_terminal_conflict(self) -> None:
        job = self.store.submit(KIND_ECHO, {"message": "x"})
        wait_status(self.store, job.id, {"succeeded"})
        with self.assertRaises(AlreadyTerminal) as ctx:
            self.store.cancel(job.id)
        self.assertEqual(ctx.exception.http_status, 409)
        self.assertEqual(ctx.exception.to_dict()["status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
