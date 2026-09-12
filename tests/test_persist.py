"""Guest job history persistence — restart reload, empty store, fail-closed.

No live Temporal. No invented typical/ETA. Not a SIEM.
"""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from sos.compare import COMPARE_NOTE_EMPTY
from sos.errors import JobNotFound, PayloadUnknown, ReAdmitUnavailable
from sos.handoff_vocab import RECOVERABILITY_NOTE, RECORDED_PAYLOAD_DIGEST
from sos.http import SosApp
from sos.jobs import Job, JobStore
from sos.persist import (
    DEFAULT_JOBS_DIR,
    ENV_JOBS_DIR,
    HISTORY_PERSIST_NOTE,
    RESTART_LOST_ERROR,
    RESTART_LOST_MESSAGE,
    describe_history_persist,
    job_to_record,
    jobs_dir_from_env,
    load_recent_records,
    prepare_jobs_dir,
    record_to_job_kwargs,
    write_record,
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


def _json(resp) -> dict:
    return json.loads(resp.body.decode("utf-8"))


class PersistEnvTests(unittest.TestCase):
    def test_unset_defaults_to_lab_path(self) -> None:
        self.assertEqual(jobs_dir_from_env({}), DEFAULT_JOBS_DIR)
        self.assertEqual(str(DEFAULT_JOBS_DIR), ".sos/jobs")

    def test_disabled_tokens_fail_closed(self) -> None:
        for raw in ("off", "0", "disabled", "false", "no", "none", "-", ""):
            self.assertIsNone(jobs_dir_from_env({ENV_JOBS_DIR: raw}), raw)

    def test_explicit_dir(self) -> None:
        path = jobs_dir_from_env({ENV_JOBS_DIR: "/tmp/sos-jobs-lab"})
        self.assertEqual(path, Path("/tmp/sos-jobs-lab"))

    def test_unwritable_prepare_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            blocked = Path(tmp) / "blocked"
            blocked.write_text("not-a-dir", encoding="utf-8")
            self.assertIsNone(prepare_jobs_dir(blocked))

    def test_describe_disabled(self) -> None:
        body = describe_history_persist(None)
        self.assertIs(body["enabled"], False)
        self.assertIsNone(body["dir"])
        self.assertEqual(body["env"], ENV_JOBS_DIR)
        self.assertIn("Fail-closed", body["note"])
        self.assertIn("Not a SIEM", body["note"])
        self.assertNotIn("typical_elapsed_s", json.dumps(body))


class PersistRecordTests(unittest.TestCase):
    def test_roundtrip_skips_metrics(self) -> None:
        job = Job(
            id="aa-bb",
            kind="job",
            resource_class="cpu",
            payload_digest=RECORDED_PAYLOAD_DIGEST,
            status="succeeded",
            created_at="2026-09-11T12:00:00.000000Z",
            updated_at="2026-09-11T12:00:08.000000Z",
            message="ok",
            local={"demo": "reserve", "catalog": "recorded", "backed": "stub"},
            payload_bytes=b'{"workload":"reserve"}',
            runtime_ref={"id": "cw_deadbeefdeadbeef"},
            events=[{"ts": "t", "event": "succeeded", "detail": "ok"}],
        )
        record = job_to_record(job)
        self.assertEqual(record["v"], 1)
        self.assertEqual(record["catalog"] if "catalog" in record else record["local"]["catalog"], "recorded")
        self.assertNotIn("typical_elapsed_s", record)
        self.assertNotIn("eta_elapsed_s", record)
        self.assertNotIn("siem", json.dumps(record).lower())
        kwargs = record_to_job_kwargs(record)
        assert kwargs is not None
        self.assertEqual(kwargs["id"], "aa-bb")
        self.assertEqual(kwargs["payload_bytes"], b'{"workload":"reserve"}')
        self.assertEqual(kwargs["runtime_ref"]["id"], "cw_deadbeefdeadbeef")
        self.assertEqual(kwargs["local"]["catalog"], "recorded")

    def test_corrupt_and_empty_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.json").write_text("{not json", encoding="utf-8")
            (root / "skip.json").write_text('{"v":99,"id":"x"}\n', encoding="utf-8")
            self.assertEqual(load_recent_records(root), [])
            store = JobStore(persist_dir=root)
            self.assertEqual(store.list(), [])
            job = store.submit({"demo": "echo", "message": "only"})
            wait_status(store, job.id, {"succeeded"})
            empty = store.compare(job.id)
            self.assertEqual(empty["priors_n"], 0)
            self.assertNotIn("typical_elapsed_s", empty)
            self.assertEqual(empty["note"], COMPARE_NOTE_EMPTY)

    def test_bad_hex_payload_stays_unknown(self) -> None:
        record = {
            "v": 1,
            "id": "opaque-1",
            "kind": "job",
            "class": "cpu",
            "payload_digest": _digest("11"),
            "status": "succeeded",
            "created_at": "2026-09-11T12:00:00.000000Z",
            "updated_at": "2026-09-11T12:00:01.000000Z",
            "payload_hex": "zz",
        }
        kwargs = record_to_job_kwargs(record)
        assert kwargs is not None
        self.assertIsNone(kwargs["payload_bytes"])


class PersistRestartTests(unittest.TestCase):
    def test_reload_succeeded_priors_for_compare(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = JobStore(step_seconds=0.01, persist_dir=tmp)
            a = first.submit({"demo": "reserve", "seconds": 0, "stages": 2})
            wait_status(first, a.id, {"succeeded"})
            b = first.submit({"demo": "reserve", "seconds": 0, "stages": 2})
            wait_status(first, b.id, {"succeeded"})
            before = first.compare(b.id)
            self.assertEqual(before["priors_n"], 1)
            self.assertNotIn("typical_elapsed_s", before)

            restarted = JobStore(step_seconds=0.01, persist_dir=tmp)
            self.assertEqual({job.id for job in restarted.list()}, {a.id, b.id})
            c = restarted.submit({"demo": "reserve", "seconds": 0, "stages": 2})
            wait_status(restarted, c.id, {"succeeded"})
            multi = restarted.compare(c.id)
            self.assertEqual(multi["priors_n"], 2)
            self.assertGreaterEqual(multi["typical_n"], 2)
            self.assertIn("typical_elapsed_s", multi)
            self.assertNotIn("eta_elapsed_s", multi)
            self.assertIn("Not a forecast", multi["note"])
            self.assertNotIn("typical_elapsed_s", c.to_dict())

    def test_empty_dir_honest_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(step_seconds=0.01, persist_dir=tmp)
            job = store.submit({"demo": "echo", "message": "solo"})
            wait_status(store, job.id, {"succeeded"})
            body = store.compare(job.id)
            self.assertEqual(body["priors_n"], 0)
            self.assertNotIn("typical_elapsed_s", body)
            self.assertNotIn("eta_elapsed_s", body)

    def test_disabled_persist_does_not_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            writer = JobStore(step_seconds=0.01, persist_dir=tmp)
            job = writer.submit({"demo": "echo", "message": "gone"})
            wait_status(writer, job.id, {"succeeded"})
            isolated = JobStore(step_seconds=0.01)
            self.assertIsNone(isolated.persist_dir)
            with self.assertRaises(JobNotFound):
                isolated.get(job.id)
            self.assertEqual(isolated.list(), [])

    def test_recoverability_after_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = JobStore(step_seconds=0.01, persist_dir=tmp)
            live = first.submit({"demo": "sleep", "seconds": 8})
            canceled = first.cancel(live.id)
            self.assertEqual(canceled.status, "canceled")
            self.assertIs(canceled.to_dict()["recoverability"]["payload_known"], True)

            opaque = first.submit(
                {"kind": "job", "class": "cpu", "payload_digest": _digest("22")}
            )
            wait_status(first, opaque.id, {"succeeded"})

            restarted = JobStore(step_seconds=0.01, persist_dir=tmp)
            again = restarted.get(canceled.id)
            body = again.to_dict()
            self.assertEqual(body["status"], "canceled")
            self.assertIs(body["recoverability"]["auto_retry"], False)
            self.assertIs(body["recoverability"]["resume_from_failed"], False)
            self.assertIs(body["recoverability"]["payload_known"], True)
            self.assertEqual(body["recoverability"]["note"], RECOVERABILITY_NOTE)
            self.assertEqual(restarted.payload(canceled.id)["payload_digest"], canceled.payload_digest)
            self.assertEqual(restarted.handoff(canceled.id)["id"], canceled.id)
            self.assertIs(body["recoverability"]["one_click"], False)
            self.assertEqual(body["recoverability"]["one_click_reason"], "hook_inert")
            self.assertNotIn("typical_elapsed_s", body)
            self.assertIn("not a siem", body["terminal"]["note"].lower())

            with self.assertRaises(ReAdmitUnavailable) as ctx:
                restarted.readmit(canceled.id)
            self.assertEqual(ctx.exception.to_dict()["reason"], "hook_inert")

            class ReloadHook:
                def admit(self, handoff, payload_bytes):
                    return {"accepted": True}

                def cancel(self, job_id, runtime_ref) -> bool:
                    return False

                def status(self, job_id, runtime_ref):
                    return None

            hooked = JobStore(
                step_seconds=0.01, persist_dir=tmp, runtime_hook=ReloadHook()
            )
            fresh = hooked.readmit(canceled.id)
            self.assertNotEqual(fresh.id, canceled.id)
            self.assertEqual(fresh.payload_digest, canceled.payload_digest)
            self.assertEqual(fresh.local["re_admit_from"], canceled.id)
            self.assertEqual(fresh.local["backed"], "runtime")

            done = restarted.get(opaque.id)
            self.assertIsNone(done.payload_bytes)
            with self.assertRaises(PayloadUnknown):
                restarted.payload(opaque.id)

    def test_inflight_stub_fails_closed_on_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = JobStore(step_seconds=0.01, persist_dir=tmp)
            live = first.submit({"demo": "sleep", "seconds": 30})
            self.assertIn(live.status, {"queued", "running"})
            restarted = JobStore(step_seconds=0.01, persist_dir=tmp)
            lost = restarted.get(live.id)
            self.assertEqual(lost.status, "failed")
            self.assertEqual(lost.error, RESTART_LOST_ERROR)
            self.assertEqual(lost.message, RESTART_LOST_MESSAGE)
            rec = lost.to_dict()
            self.assertIs(rec["recoverability"]["auto_retry"], False)
            self.assertIs(rec["recoverability"]["payload_known"], True)
            self.assertNotIn("typical_elapsed_s", rec)
            vs = restarted.compare(lost.id)
            self.assertEqual(vs["priors_n"], 0)
            self.assertNotIn("typical_elapsed_s", vs)

    def test_http_restart_simulation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app1 = SosApp(JobStore(step_seconds=0.01, persist_dir=tmp))
            first = app1.handle(
                "POST",
                "/v0/jobs",
                json.dumps({"demo": "reserve", "seconds": 0, "stages": 2}).encode(),
            )
            first_id = _json(first)["id"]
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if _json(app1.handle("GET", f"/v0/jobs/{first_id}")).get("status") == "succeeded":
                    break
                time.sleep(0.02)
            else:
                raise AssertionError("first reserve did not succeed")
            second = app1.handle(
                "POST",
                "/v0/jobs",
                json.dumps({"demo": "reserve", "seconds": 0, "stages": 2}).encode(),
            )
            second_id = _json(second)["id"]
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if _json(app1.handle("GET", f"/v0/jobs/{second_id}")).get("status") == "succeeded":
                    break
                time.sleep(0.02)
            else:
                raise AssertionError("second reserve did not succeed")

            app2 = SosApp(JobStore(step_seconds=0.01, persist_dir=tmp))
            info = _json(app2.handle("GET", "/v0/info"))
            persist = info["jobs"]["history_persist"]
            self.assertIs(persist["enabled"], True)
            self.assertIn(HISTORY_PERSIST_NOTE[:20], persist["note"])
            third = app2.handle(
                "POST",
                "/v0/jobs",
                json.dumps({"demo": "reserve", "seconds": 0, "stages": 2}).encode(),
            )
            third_id = _json(third)["id"]
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if _json(app2.handle("GET", f"/v0/jobs/{third_id}")).get("status") == "succeeded":
                    break
                time.sleep(0.02)
            else:
                raise AssertionError("third reserve did not succeed")
            vs = _json(app2.handle("GET", f"/v0/jobs/{third_id}/compare"))
            self.assertEqual(vs["priors_n"], 2)
            self.assertIn("typical_elapsed_s", vs)
            self.assertNotIn("eta_elapsed_s", vs)

    def test_write_record_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = {
                "v": 1,
                "id": "job-1",
                "kind": "job",
                "class": "cpu",
                "payload_digest": _digest("33"),
                "status": "succeeded",
                "created_at": "2026-09-11T12:00:00.000000Z",
                "updated_at": "2026-09-11T12:00:01.000000Z",
            }
            self.assertTrue(write_record(root, record))
            loaded = load_recent_records(root)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["id"], "job-1")


class PersistHonestyDocsTests(unittest.TestCase):
    def test_no_temporal_in_persist_module(self) -> None:
        text = Path(__file__).resolve().parents[1].joinpath("sos/persist.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("temporal", text.lower())
        self.assertNotIn("workflow_id", text)
        self.assertNotIn("typical_elapsed_s", text)
        self.assertIn("fail closed", text.lower().replace("fail-closed", "fail closed"))
        self.assertIn("not a siem", text.lower())


if __name__ == "__main__":
    unittest.main()
