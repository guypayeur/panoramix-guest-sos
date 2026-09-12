"""Async durable admit — running id + timeout honesty. No live Temporal."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sos.errors import (
    ERROR_CTL_ADMIT_TIMEOUT,
    ERROR_CTL_HTTP_UNREACHABLE,
    ERROR_DURABLE_ADMIT_FAILED,
    CtlAdmitTimeout,
    CtlHttpUnreachable,
    DurableAdmitFailed,
    StubOnly,
)
from sos.http import SosApp
from sos.jobs import EVENTS_SOURCE_DURABLE, PROGRESS_SOURCE_DURABLE, JobStore
from sos.lab_compose import async_admit_plan
from sos.lab_ctl import (
    APPLY_REL,
    CTL_SUBPROCESS_TIMEOUT_CODE,
    LabReserveTemporalHook,
)
from sos.lab_ctl_http import (
    CTL_HTTP_TIMEOUT_CODE,
    LabReserveTemporalHttpHook,
)

ROOT = Path(__file__).resolve().parents[1]
CTL_ID = "cw_deadbeefdeadbeef"
LOOPBACK = "http://127.0.0.1:19215"


class _RunningAdmitHook:
    """Admit returns running; status stays None so UI polls mid-flight."""

    def __init__(self) -> None:
        self.progress_calls = 0
        self.events_calls = 0
        self.status_calls = 0

    def admit(self, handoff: dict[str, str], payload_bytes: bytes | None):
        del handoff, payload_bytes
        return {
            "id": CTL_ID,
            "ctl": "reserve-temporal",
            "status": "running",
        }

    def status(self, job_id: str, runtime_ref: dict | None):
        del job_id, runtime_ref
        self.status_calls += 1
        return None

    def progress(self, job_id: str, runtime_ref: dict | None):
        del job_id
        self.progress_calls += 1
        self.last_ref = runtime_ref
        return {
            "stage": 1,
            "stages_total": 4,
            "stages_completed": 1,
            "fraction": 0.25,
        }

    def events(self, job_id: str, runtime_ref: dict | None):
        del job_id, runtime_ref
        self.events_calls += 1
        return {
            "events": [
                {
                    "ts": "2026-09-12T11:00:00Z",
                    "event": "admit",
                    "type": "WorkflowExecutionStarted",
                }
            ],
            "durable": True,
        }

    def cancel(self, job_id: str, runtime_ref: dict | None) -> bool:
        del job_id, runtime_ref
        return True


class _RefuseAdmitHook:
    def admit(self, handoff: dict[str, str], payload_bytes: bytes | None):
        del handoff, payload_bytes
        return None

    def status(self, job_id: str, runtime_ref: dict | None):
        del job_id, runtime_ref
        return None


def _fake_root() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="sos-async-admit-"))
    apply_py = tmp / APPLY_REL
    apply_py.parent.mkdir(parents=True)
    apply_py.write_text("# fake runtime.apply for timeout probe\n", encoding="utf-8")
    return tmp


class RunningIdTests(unittest.TestCase):
    def test_admit_running_id_polls_progress_without_status(self) -> None:
        hook = _RunningAdmitHook()
        store = JobStore(step_seconds=0.02, runtime_hook=hook)
        job = store.submit({"demo": "reserve", "catalog": "parity"})
        self.assertEqual(job.status, "running")
        self.assertEqual(job.local["backed"], "runtime")
        self.assertEqual(job.runtime_ref["id"], CTL_ID)
        self.assertEqual(job.runtime_ref["ctl"], "reserve-temporal")
        self.assertNotIn("status", job.runtime_ref)
        self.assertNotIn("workflow_id", job.runtime_ref)
        self.assertIn("admitted via runtime hook", job.message or "")
        self.assertGreaterEqual(hook.status_calls, 1)

        progress = store.progress(job.id)
        self.assertEqual(progress["source"], PROGRESS_SOURCE_DURABLE)
        self.assertEqual(progress["stages_completed"], 1)
        self.assertEqual(progress["fraction"], 0.25)
        self.assertGreaterEqual(hook.progress_calls, 1)
        self.assertEqual(hook.last_ref["id"], CTL_ID)

        trail = store.events(job.id)
        self.assertEqual(trail["source"], EVENTS_SOURCE_DURABLE)
        self.assertEqual(trail["events"][0]["event"], "admit")
        self.assertGreaterEqual(hook.events_calls, 1)

        still = store.get(job.id)
        self.assertEqual(still.status, "running")
        self.assertEqual(still.local["backed"], "runtime")


class MinutesClassFailClosedTests(unittest.TestCase):
    def test_parity_hook_none_is_durable_admit_failed(self) -> None:
        store = JobStore(step_seconds=0.02, runtime_hook=_RefuseAdmitHook())
        with self.assertRaises(DurableAdmitFailed) as ctx:
            store.submit({"demo": "reserve", "catalog": "parity"})
        err = ctx.exception
        self.assertEqual(err.error, ERROR_DURABLE_ADMIT_FAILED)
        self.assertEqual(err.http_status, 409)
        self.assertEqual(err.fields["runtime_issue"], 143)
        self.assertIs(err.fields["north_star_done"], False)
        job = store.get(err.fields["id"])
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.error, ERROR_DURABLE_ADMIT_FAILED)
        self.assertIsNone(job.runtime_ref)
        with self.assertRaises(StubOnly):
            store.pause(job.id)

    def test_live_hook_none_is_durable_admit_failed(self) -> None:
        store = JobStore(step_seconds=0.02, runtime_hook=_RefuseAdmitHook())
        with self.assertRaises(DurableAdmitFailed):
            store.submit({"demo": "reserve", "catalog": "live"})

    def test_recorded_hook_none_still_stubs(self) -> None:
        store = JobStore(step_seconds=0.02, runtime_hook=_RefuseAdmitHook())
        job = store.submit({"demo": "echo", "message": "fallback"})
        self.assertEqual(job.local["backed"], "stub")
        self.assertIsNone(job.error)
        self.assertNotEqual(job.status, "failed")
        store.cancel(job.id)

    def test_inert_parity_still_stubs(self) -> None:
        """Default inert hook is not a durable path — live|parity stay UX seed."""
        store = JobStore(step_seconds=0.02)
        job = store.submit({"demo": "reserve", "catalog": "parity", "seconds": 0})
        self.assertEqual(job.local["backed"], "stub")
        self.assertEqual(job.local["catalog"], "parity")
        self.assertIsNone(job.error)
        self.assertNotEqual(job.status, "failed")
        store.cancel(job.id)


class TimeoutHonestyTests(unittest.TestCase):
    def test_http_admit_timeout_is_named_error(self) -> None:
        hook = LabReserveTemporalHttpHook(
            LOOPBACK, transport=lambda *_a, **_k: (CTL_HTTP_TIMEOUT_CODE, "")
        )
        store = JobStore(step_seconds=0.02, runtime_hook=hook)
        with self.assertRaises(CtlAdmitTimeout) as ctx:
            store.submit({"demo": "reserve", "catalog": "parity"})
        err = ctx.exception
        self.assertEqual(err.error, ERROR_CTL_ADMIT_TIMEOUT)
        self.assertEqual(err.http_status, 503)
        self.assertEqual(err.fields["transport"], "http")
        self.assertEqual(err.fields["runtime_issue"], 143)
        self.assertIs(err.fields["north_star_done"], False)
        self.assertNotEqual(err.error, ERROR_CTL_HTTP_UNREACHABLE)
        job = store.get(err.fields["id"])
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.error, ERROR_CTL_ADMIT_TIMEOUT)
        self.assertNotIn("lab_serve", job.to_dict())
        with self.assertRaises(StubOnly):
            store.pause(job.id)

    def test_http_connection_refused_stays_unreachable(self) -> None:
        hook = LabReserveTemporalHttpHook(
            LOOPBACK, transport=lambda *_a, **_k: (0, "")
        )
        store = JobStore(step_seconds=0.02, runtime_hook=hook)
        with self.assertRaises(CtlHttpUnreachable) as ctx:
            store.submit({"demo": "reserve", "seconds": 8})
        self.assertEqual(ctx.exception.error, ERROR_CTL_HTTP_UNREACHABLE)

    def test_http_admit_timeout_returns_503(self) -> None:
        hook = LabReserveTemporalHttpHook(
            LOOPBACK, transport=lambda *_a, **_k: (CTL_HTTP_TIMEOUT_CODE, "")
        )
        app = SosApp(JobStore(step_seconds=0.02, runtime_hook=hook))
        created = app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "catalog": "parity"}).encode(),
        )
        self.assertEqual(created.status, 503)
        body = json.loads(created.body.decode("utf-8"))
        self.assertEqual(body["error"], "ctl_admit_timeout")
        self.assertIn("runtime #143", body["detail"])
        self.assertNotEqual(body["error"], "ctl_http_unreachable")

    def test_subprocess_admit_timeout_is_named_error(self) -> None:
        def timed_out(argv, *, cwd, env):
            del argv, cwd, env
            return CTL_SUBPROCESS_TIMEOUT_CODE, "", "timed out"

        hook = LabReserveTemporalHook(_fake_root(), runner=timed_out)
        store = JobStore(step_seconds=0.02, runtime_hook=hook)
        with self.assertRaises(CtlAdmitTimeout) as ctx:
            store.submit({"demo": "reserve", "catalog": "live"})
        err = ctx.exception
        self.assertEqual(err.error, ERROR_CTL_ADMIT_TIMEOUT)
        self.assertEqual(err.fields["transport"], "subprocess")
        job = store.get(err.fields["id"])
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.error, ERROR_CTL_ADMIT_TIMEOUT)
        with self.assertRaises(StubOnly):
            store.pause(job.id)

    def test_recorded_http_500_still_stubs(self) -> None:
        hook = LabReserveTemporalHttpHook(
            LOOPBACK, transport=lambda *_a, **_k: (500, '{"ok":false}')
        )
        store = JobStore(step_seconds=0.02, runtime_hook=hook)
        job = store.submit({"demo": "echo", "message": "fallback"})
        self.assertEqual(job.local["backed"], "stub")
        self.assertIsNone(job.error)
        with self.assertRaises(StubOnly):
            store.pause(job.id)
        store.cancel(job.id)


class ComposeAsyncAdmitTests(unittest.TestCase):
    def test_parity_plan_is_minutes_class(self) -> None:
        plan = async_admit_plan("parity")
        self.assertEqual(plan["catalog"], "parity")
        self.assertIs(plan["minutes_class"], True)
        self.assertEqual(plan["depends_on"], "panoramix-runtime#143")
        self.assertEqual(plan["timeout_error"], "ctl_admit_timeout")
        self.assertIs(plan["stub_fallback"], False)
        self.assertIs(plan["invent"], False)
        self.assertIs(plan["forecast"], False)
        self.assertIs(plan["north_star_done"], False)
        self.assertIs(plan["closes_runtime_70"], False)
        self.assertIs(plan["closes_runtime_78"], False)
        self.assertIn("mid-flight", plan["compose"])
        self.assertIn("#143", plan["note"])

    def test_recorded_plan_is_not_minutes_class(self) -> None:
        plan = async_admit_plan("recorded")
        self.assertIs(plan["minutes_class"], False)
        self.assertEqual(plan["stub_fallback"], "recorded HTTP 4xx/5xx only")
        self.assertIs(plan["north_star_done"], False)


class HonestyTests(unittest.TestCase):
    def test_guest_mentions_143_and_timeout(self) -> None:
        pins = (
            "sos/errors.py",
            "sos/jobs.py",
            "sos/lab_ctl.py",
            "sos/lab_ctl_http.py",
            "sos/lab_compose.py",
            "sos/http.py",
            "sos/ui.py",
            "docs/lab-compose.md",
            "docs/ux-side-by-side.md",
            "README.md",
            "PANORAMIX_OPERATIONAL.md",
            "scripts/lab_compose_reserve_temporal.py",
        )
        for name in pins:
            text = ROOT.joinpath(name).read_text(encoding="utf-8")
            self.assertIn("#143", text, name)
            self.assertIn("ctl_admit_timeout", text, name)
            self.assertIn("mid-flight", text, name)
            self.assertNotIn("Fixes #70", text, name)
            self.assertNotIn("Fixes #78", text, name)

    def test_compose_helper_avoids_subprocess_token(self) -> None:
        helper = (ROOT / "sos" / "lab_compose.py").read_text(encoding="utf-8")
        self.assertNotIn("subprocess", helper)
        self.assertIn("ctl-apply admit", helper)


if __name__ == "__main__":
    unittest.main()
