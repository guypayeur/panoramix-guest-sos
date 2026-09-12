"""Historical-run comparison — empty / single / multi prior. No invented numbers."""

from __future__ import annotations

import time
import unittest

from sos.compare import (
    COMPARE_HONESTY,
    COMPARE_NOTE_EMPTY,
    COMPARE_NOTE_THIN,
    COMPARE_NOTE_TYPICAL,
    COMPARE_SOURCE,
    ELAPSED_SOURCE_DURABLE,
    ELAPSED_SOURCE_GUEST,
    MATCH_CATALOG,
    MATCH_KIND_CLASS,
    compare_vs_priors,
    elapsed_seconds,
    guest_clock_seconds,
    wall_elapsed_seconds,
)
from sos.errors import JobNotFound
from sos.handoff_vocab import RECORDED_PAYLOAD_DIGEST
from sos.jobs import Job, JobStore


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


def _job(
    job_id: str,
    *,
    created: str,
    updated: str,
    status: str = "succeeded",
    catalog: str | None = "recorded",
    kind: str = "job",
    resource_class: str = "cpu",
    digest: str = RECORDED_PAYLOAD_DIGEST,
    wall_elapsed_ms: int | None = None,
) -> Job:
    local: dict | None = {"backed": "stub"}
    if catalog is not None:
        local["catalog"] = catalog
        local["demo"] = "reserve"
    return Job(
        id=job_id,
        kind=kind,
        resource_class=resource_class,
        payload_digest=digest,
        status=status,
        created_at=created,
        updated_at=updated,
        local=local,
        wall_elapsed_ms=wall_elapsed_ms,
    )


NOW = "2026-09-11T12:01:00.000000Z"


class ComparePureTests(unittest.TestCase):
    def test_empty_history_invents_nothing(self) -> None:
        current = _job(
            "only",
            created="2026-09-11T12:00:00.000000Z",
            updated="2026-09-11T12:00:08.000000Z",
        )
        body = compare_vs_priors(current, [], now=NOW)
        self.assertEqual(body["id"], "only")
        self.assertEqual(body["source"], COMPARE_SOURCE)
        self.assertEqual(body["matched_by"], MATCH_CATALOG)
        self.assertEqual(body["priors"], [])
        self.assertEqual(body["priors_n"], 0)
        self.assertEqual(body["typical_n"], 0)
        self.assertNotIn("typical_elapsed_s", body)
        self.assertNotIn("eta_elapsed_s", body)
        self.assertEqual(body["this"]["elapsed_s"], 8.0)
        self.assertEqual(body["this"]["elapsed_source"], ELAPSED_SOURCE_GUEST)
        self.assertNotIn("wall_elapsed_ms", body["this"])
        self.assertEqual(body["note"], COMPARE_NOTE_EMPTY)
        self.assertIn("Not a forecast", body["note"])
        self.assertIn("Not IFRS17", body["note"])
        self.assertIn("Not iec SPA historical widget", body["note"])

    def test_single_prior_shows_elapsed_omits_typical(self) -> None:
        prior = _job(
            "p1",
            created="2026-09-11T12:00:00.000000Z",
            updated="2026-09-11T12:00:10.000000Z",
        )
        current = _job(
            "c1",
            created="2026-09-11T12:00:20.000000Z",
            updated="2026-09-11T12:00:26.000000Z",
            status="running",
        )
        body = compare_vs_priors(current, [prior], now="2026-09-11T12:00:30.000000Z")
        self.assertEqual(body["priors_n"], 1)
        self.assertEqual(body["priors"][0]["id"], "p1")
        self.assertEqual(body["priors"][0]["elapsed_s"], 10.0)
        self.assertEqual(body["priors"][0]["elapsed_source"], ELAPSED_SOURCE_GUEST)
        self.assertEqual(body["this"]["elapsed_s"], 10.0)
        self.assertEqual(body["this"]["elapsed_source"], ELAPSED_SOURCE_GUEST)
        self.assertEqual(body["typical_n"], 1)
        self.assertNotIn("typical_elapsed_s", body)
        self.assertNotIn("eta_elapsed_s", body)
        self.assertEqual(body["note"], COMPARE_NOTE_THIN)

    def test_multi_prior_typical_and_live_eta(self) -> None:
        p1 = _job(
            "a",
            created="2026-09-11T12:00:00.000000Z",
            updated="2026-09-11T12:00:10.000000Z",
        )
        p2 = _job(
            "b",
            created="2026-09-11T12:00:20.000000Z",
            updated="2026-09-11T12:00:50.000000Z",
        )
        current = _job(
            "c",
            created="2026-09-11T12:00:55.000000Z",
            updated="2026-09-11T12:00:56.000000Z",
            status="running",
        )
        body = compare_vs_priors(current, [p2, p1], now="2026-09-11T12:01:00.000000Z")
        self.assertEqual(body["priors_n"], 2)
        self.assertEqual(body["typical_n"], 2)
        self.assertEqual(body["typical_elapsed_s"], 20.0)
        self.assertEqual(body["eta_elapsed_s"], 20.0)
        self.assertEqual(body["this"]["elapsed_s"], 5.0)
        self.assertEqual(body["note"], COMPARE_NOTE_TYPICAL)
        self.assertEqual([row["elapsed_s"] for row in body["priors"]], [30.0, 10.0])

    def test_succeeded_current_has_typical_but_no_eta(self) -> None:
        p1 = _job(
            "a",
            created="2026-09-11T12:00:00.000000Z",
            updated="2026-09-11T12:00:10.000000Z",
        )
        p2 = _job(
            "b",
            created="2026-09-11T12:00:20.000000Z",
            updated="2026-09-11T12:00:30.000000Z",
        )
        current = _job(
            "c",
            created="2026-09-11T12:00:40.000000Z",
            updated="2026-09-11T12:00:55.000000Z",
        )
        body = compare_vs_priors(current, [p2, p1], now=NOW)
        self.assertEqual(body["typical_elapsed_s"], 10.0)
        self.assertNotIn("eta_elapsed_s", body)

    def test_canceled_priors_do_not_invent_typical(self) -> None:
        p1 = _job(
            "a",
            created="2026-09-11T12:00:00.000000Z",
            updated="2026-09-11T12:00:04.000000Z",
            status="canceled",
        )
        p2 = _job(
            "b",
            created="2026-09-11T12:00:10.000000Z",
            updated="2026-09-11T12:00:12.000000Z",
            status="failed",
        )
        current = _job(
            "c",
            created="2026-09-11T12:00:20.000000Z",
            updated="2026-09-11T12:00:21.000000Z",
            status="running",
        )
        body = compare_vs_priors(current, [p2, p1], now=NOW)
        self.assertEqual(body["priors_n"], 2)
        self.assertEqual(body["typical_n"], 0)
        self.assertNotIn("typical_elapsed_s", body)
        self.assertNotIn("eta_elapsed_s", body)
        self.assertEqual(body["priors"][0]["elapsed_s"], 2.0)

    def test_other_catalog_is_not_a_prior(self) -> None:
        live = _job(
            "live",
            created="2026-09-11T12:00:00.000000Z",
            updated="2026-09-11T12:00:10.000000Z",
            catalog="live",
        )
        current = _job(
            "rec",
            created="2026-09-11T12:00:20.000000Z",
            updated="2026-09-11T12:00:25.000000Z",
            catalog="recorded",
        )
        body = compare_vs_priors(current, [live], now=NOW)
        self.assertEqual(body["priors_n"], 0)
        self.assertEqual(body["matched_by"], MATCH_CATALOG)
        self.assertNotIn("typical_elapsed_s", body)

    def test_kind_class_match_excludes_cataloged_jobs(self) -> None:
        opaque = _job(
            "op",
            created="2026-09-11T12:00:00.000000Z",
            updated="2026-09-11T12:00:03.000000Z",
            catalog=None,
            digest=_digest("aa"),
        )
        reserve = _job(
            "rs",
            created="2026-09-11T12:00:10.000000Z",
            updated="2026-09-11T12:00:20.000000Z",
            catalog="recorded",
        )
        current = _job(
            "now",
            created="2026-09-11T12:00:30.000000Z",
            updated="2026-09-11T12:00:31.000000Z",
            catalog=None,
            digest=_digest("bb"),
            status="running",
        )
        gpu = _job(
            "gpu",
            created="2026-09-11T12:00:05.000000Z",
            updated="2026-09-11T12:00:08.000000Z",
            catalog=None,
            resource_class="gpu",
            digest=_digest("cc"),
        )
        body = compare_vs_priors(current, [reserve, opaque, gpu], now=NOW)
        self.assertEqual(body["matched_by"], MATCH_KIND_CLASS)
        self.assertEqual([row["id"] for row in body["priors"]], ["op"])
        self.assertEqual(body["priors"][0]["elapsed_s"], 3.0)
        self.assertNotIn("typical_elapsed_s", body)

    def test_unparseable_timestamps_omit_elapsed(self) -> None:
        current = _job("bad", created="", updated="", status="succeeded")
        self.assertIsNone(elapsed_seconds(current, now=NOW))
        body = compare_vs_priors(current, [], now=NOW)
        self.assertNotIn("elapsed_s", body["this"])
        self.assertNotIn("typical_elapsed_s", body)

    def test_prefers_durable_wall_over_guest_clocks(self) -> None:
        prior = _job(
            "p1",
            created="2026-09-11T12:00:00.000000Z",
            updated="2026-09-11T12:00:10.000000Z",
            wall_elapsed_ms=2500,
        )
        current = _job(
            "c1",
            created="2026-09-11T12:00:20.000000Z",
            updated="2026-09-11T12:00:50.000000Z",
            status="running",
            wall_elapsed_ms=4000,
        )
        body = compare_vs_priors(current, [prior], now="2026-09-11T12:00:30.000000Z")
        self.assertEqual(body["this"]["elapsed_s"], 4.0)
        self.assertEqual(body["this"]["elapsed_source"], ELAPSED_SOURCE_DURABLE)
        self.assertEqual(body["this"]["wall_elapsed_ms"], 4000)
        self.assertEqual(body["priors"][0]["elapsed_s"], 2.5)
        self.assertEqual(body["priors"][0]["elapsed_source"], ELAPSED_SOURCE_DURABLE)
        self.assertEqual(guest_clock_seconds(prior, now=NOW), 10.0)
        self.assertNotEqual(body["priors"][0]["elapsed_s"], 10.0)
        self.assertNotIn("typical_elapsed_s", body)

    def test_omits_invalid_wall_and_falls_back_to_guest_clock(self) -> None:
        for bad in (-8, True, "nope", float("nan")):
            job = _job(
                "bad-wall",
                created="2026-09-11T12:00:00.000000Z",
                updated="2026-09-11T12:00:06.000000Z",
                wall_elapsed_ms=bad,  # type: ignore[arg-type]
            )
            self.assertIsNone(wall_elapsed_seconds(job))
            self.assertEqual(elapsed_seconds(job, now=NOW), 6.0)
            body = compare_vs_priors(job, [], now=NOW)
            self.assertEqual(body["this"]["elapsed_s"], 6.0)
            self.assertEqual(body["this"]["elapsed_source"], ELAPSED_SOURCE_GUEST)
            self.assertNotIn("wall_elapsed_ms", body["this"])

    def test_typical_prefers_durable_walls_when_two_priors(self) -> None:
        p1 = _job(
            "a",
            created="2026-09-11T12:00:00.000000Z",
            updated="2026-09-11T12:00:10.000000Z",
            wall_elapsed_ms=1000,
        )
        p2 = _job(
            "b",
            created="2026-09-11T12:00:20.000000Z",
            updated="2026-09-11T12:00:50.000000Z",
            wall_elapsed_ms=3000,
        )
        current = _job(
            "c",
            created="2026-09-11T12:00:55.000000Z",
            updated="2026-09-11T12:00:56.000000Z",
            status="running",
        )
        body = compare_vs_priors(current, [p2, p1], now="2026-09-11T12:01:00.000000Z")
        self.assertEqual(body["typical_elapsed_s"], 2.0)
        self.assertEqual(body["eta_elapsed_s"], 2.0)
        self.assertEqual(body["this"]["elapsed_source"], ELAPSED_SOURCE_GUEST)
        self.assertEqual([row["elapsed_s"] for row in body["priors"]], [3.0, 1.0])
        self.assertEqual(
            [row["elapsed_source"] for row in body["priors"]],
            [ELAPSED_SOURCE_DURABLE, ELAPSED_SOURCE_DURABLE],
        )


class CompareStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = JobStore(step_seconds=0.01)

    def _reserve(self, **extra: object) -> Job:
        body = {"demo": "reserve", "seconds": 0, "stages": 2}
        body.update(extra)
        job = self.store.submit(body)
        wait_status(self.store, job.id, {"succeeded"})
        return self.store.get(job.id)

    def test_store_empty_single_multi(self) -> None:
        first = self._reserve()
        empty = self.store.compare(first.id)
        self.assertEqual(empty["priors_n"], 0)
        self.assertNotIn("typical_elapsed_s", empty)
        self.assertNotIn("eta_elapsed_s", empty)
        self.assertEqual(empty["note"], COMPARE_NOTE_EMPTY)
        self.assertIn("elapsed_s", empty["this"])

        second = self._reserve()
        single = self.store.compare(second.id)
        self.assertEqual(single["priors_n"], 1)
        self.assertEqual(single["priors"][0]["id"], first.id)
        self.assertIn("elapsed_s", single["priors"][0])
        self.assertNotIn("typical_elapsed_s", single)
        self.assertNotIn("eta_elapsed_s", single)
        self.assertEqual(single["matched_by"], MATCH_CATALOG)

        third = self._reserve()
        multi = self.store.compare(third.id)
        self.assertEqual(multi["priors_n"], 2)
        self.assertGreaterEqual(multi["typical_n"], 2)
        self.assertIn("typical_elapsed_s", multi)
        self.assertIsInstance(multi["typical_elapsed_s"], float)
        self.assertNotIn("eta_elapsed_s", multi)
        self.assertIn(COMPARE_HONESTY, multi["note"])
        self.assertNotIn("compare", third.to_handoff())
        self.assertNotIn("typical_elapsed_s", third.to_dict())

    def test_store_live_eta_from_priors_only(self) -> None:
        self._reserve()
        self._reserve()
        live = self.store.submit({"demo": "reserve", "seconds": 8, "stages": 2})
        body = self.store.compare(live.id)
        self.assertEqual(body["priors_n"], 2)
        self.assertIn("typical_elapsed_s", body)
        self.assertEqual(body["eta_elapsed_s"], body["typical_elapsed_s"])
        self.assertEqual(live.status in {"queued", "running"}, True)

    def test_store_catalog_and_kind_class_seams(self) -> None:
        recorded = self._reserve(catalog="recorded")
        live = self._reserve(catalog="live")
        vs_live = self.store.compare(live.id)
        self.assertEqual(vs_live["priors_n"], 0)
        vs_rec = self.store.compare(recorded.id)
        self.assertEqual(vs_rec["priors_n"], 0)

        opaque_a = self.store.submit(
            {"kind": "job", "class": "cpu", "payload_digest": _digest("11")}
        )
        wait_status(self.store, opaque_a.id, {"succeeded"})
        opaque_b = self.store.submit(
            {"kind": "job", "class": "cpu", "payload_digest": _digest("22")}
        )
        wait_status(self.store, opaque_b.id, {"succeeded"})
        vs_opaque = self.store.compare(opaque_b.id)
        self.assertEqual(vs_opaque["matched_by"], MATCH_KIND_CLASS)
        self.assertEqual([row["id"] for row in vs_opaque["priors"]], [opaque_a.id])
        self.assertNotIn(recorded.id, [row["id"] for row in vs_opaque["priors"]])

    def test_store_missing(self) -> None:
        with self.assertRaises(JobNotFound):
            self.store.compare("missing")


class _WallHook:
    def __init__(self, wall_ms: int | None, *, via: str = "progress") -> None:
        self.wall_ms = wall_ms
        self.via = via
        self.last_status_payload: dict | None = None

    def admit(self, handoff, payload_bytes):
        return {"accepted": True}

    def cancel(self, job_id, runtime_ref) -> bool:
        return True

    def status(self, job_id, runtime_ref):
        if self.via == "status" and self.wall_ms is not None:
            self.last_status_payload = {"wall_elapsed_ms": self.wall_ms}
        else:
            self.last_status_payload = {"id": "cw_status"}
        return "running"

    def progress(self, job_id, runtime_ref):
        body: dict = {
            "stage": 2,
            "stages_total": 4,
            "stages_completed": 1,
        }
        if self.via == "progress" and self.wall_ms is not None:
            body["wall_elapsed_ms"] = self.wall_ms
        return body


class CompareDurableWallTests(unittest.TestCase):
    def test_store_compare_prefers_hook_wall_and_omits_when_missing(self) -> None:
        present = JobStore(step_seconds=0.02, runtime_hook=_WallHook(4500))
        job = present.submit({"demo": "reserve", "seconds": 8, "catalog": "recorded"})
        body = present.compare(job.id)
        self.assertEqual(body["this"]["elapsed_s"], 4.5)
        self.assertEqual(body["this"]["elapsed_source"], ELAPSED_SOURCE_DURABLE)
        self.assertEqual(body["this"]["wall_elapsed_ms"], 4500)
        self.assertEqual(present.get(job.id).wall_elapsed_ms, 4500)
        present.cancel(job.id)

        omitted = JobStore(step_seconds=0.02, runtime_hook=_WallHook(None))
        other = omitted.submit({"demo": "reserve", "seconds": 8, "catalog": "recorded"})
        bare = omitted.compare(other.id)
        self.assertEqual(bare["this"]["elapsed_source"], ELAPSED_SOURCE_GUEST)
        self.assertNotIn("wall_elapsed_ms", bare["this"])
        self.assertIsNone(omitted.get(other.id).wall_elapsed_ms)
        omitted.cancel(other.id)

    def test_store_compare_prefers_status_wall(self) -> None:
        store = JobStore(
            step_seconds=0.02, runtime_hook=_WallHook(900, via="status")
        )
        job = store.submit({"demo": "reserve", "seconds": 8, "catalog": "recorded"})
        body = store.compare(job.id)
        self.assertEqual(body["this"]["elapsed_s"], 0.9)
        self.assertEqual(body["this"]["elapsed_source"], ELAPSED_SOURCE_DURABLE)
        store.cancel(job.id)

    def test_persisted_wall_used_after_restart(self) -> None:
        import tempfile
        from pathlib import Path

        from sos.persist import job_to_record, write_record

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = _job(
                "prior-a",
                created="2026-09-11T12:00:00.000000Z",
                updated="2026-09-11T12:00:10.000000Z",
                wall_elapsed_ms=8000,
            )
            b = _job(
                "prior-b",
                created="2026-09-11T12:00:20.000000Z",
                updated="2026-09-11T12:00:50.000000Z",
                wall_elapsed_ms=2000,
            )
            self.assertTrue(write_record(root, job_to_record(a)))
            self.assertTrue(write_record(root, job_to_record(b)))
            restarted = JobStore(step_seconds=0.01, persist_dir=root)
            self.assertEqual(restarted.get(a.id).wall_elapsed_ms, 8000)
            self.assertEqual(restarted.get(b.id).wall_elapsed_ms, 2000)
            c = restarted.submit(
                {"demo": "reserve", "seconds": 0, "stages": 2, "catalog": "recorded"}
            )
            wait_status(restarted, c.id, {"succeeded"})
            vs = restarted.compare(c.id)
            self.assertEqual(vs["priors_n"], 2)
            walls = {row["id"]: row["elapsed_s"] for row in vs["priors"]}
            self.assertEqual(walls[a.id], 8.0)
            self.assertEqual(walls[b.id], 2.0)
            self.assertTrue(
                all(
                    row["elapsed_source"] == ELAPSED_SOURCE_DURABLE
                    for row in vs["priors"]
                )
            )
            self.assertEqual(vs["typical_elapsed_s"], 5.0)
            self.assertEqual(vs["this"]["elapsed_source"], ELAPSED_SOURCE_GUEST)


if __name__ == "__main__":
    unittest.main()
