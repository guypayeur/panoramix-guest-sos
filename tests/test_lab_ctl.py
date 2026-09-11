"""Opt-in lab reserve-temporal ctl loopback — recorded/fake ctl only.

No live Temporal. Default (env unset) stays inert. Does not close
runtime #70 / #78. Does not unlock cloud. Does not stamp north_star_done.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sos.errors import StubOnly
from sos.http import SosApp
from sos.jobs import EVENTS_SOURCE_DURABLE, PROGRESS_SOURCE_DURABLE, JobStore
from sos.lab_ctl import (
    APPLY_REL,
    ENV_LIVE,
    ENV_RUNTIME_ROOT,
    LabReserveTemporalHook,
    lab_hook_from_env,
    runtime_root_from_env,
)
from sos.runtime_hook import InertRuntimeHandoffHook, resolve_runtime_hook


CTL_ID = "cw_deadbeefdeadbeef"


def _fake_root() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="sos-lab-ctl-"))
    apply_py = tmp / APPLY_REL
    apply_py.parent.mkdir(parents=True)
    apply_py.write_text("# fake runtime.apply for opt-in probe\n", encoding="utf-8")
    return tmp


class _FakeCtl:
    """Recorded ctl fixture — argv in, JSON out. No Temporal."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.status = "running"
        self.paused = False
        self.canceled = False
        self.admitted: list[dict[str, str]] = []

    def __call__(
        self, argv: list[str], *, cwd: Path, env: dict[str, str]
    ) -> tuple[int, str, str]:
        del cwd, env
        self.calls.append(list(argv))
        if len(argv) < 5 or argv[:4] != [
            "python3",
            "-m",
            "runtime.apply",
            "reserve-temporal",
        ]:
            return 1, json.dumps({"ok": False, "error": "bad argv"}), ""
        action = argv[4]
        if action == "admit":
            handoff_path = None
            if "--handoff" in argv:
                handoff_path = Path(argv[argv.index("--handoff") + 1])
            raw = json.loads(handoff_path.read_text(encoding="utf-8")) if handoff_path else {}
            self.admitted.append(raw)
            self.status = "running"
            body = {
                "ok": True,
                "id": CTL_ID,
                "handoff": {
                    "id": CTL_ID,
                    "kind": raw.get("kind", "job"),
                    "class": raw.get("class", "cpu"),
                    "payload_digest": raw.get("payload_digest", ""),
                    "status": "running",
                },
                "north_star_done": False,
            }
            return 0, json.dumps(body), ""
        work_id = argv[argv.index("--id") + 1] if "--id" in argv else ""
        if work_id != CTL_ID:
            return 1, json.dumps({"ok": False, "error": "unknown id"}), ""
        if action == "status":
            return 0, json.dumps(
                {
                    "ok": True,
                    "id": CTL_ID,
                    "handoff": {"id": CTL_ID, "status": self.status},
                    "ctl": "status",
                }
            ), ""
        if action == "progress":
            return 0, json.dumps(
                {
                    "ok": True,
                    "id": CTL_ID,
                    "ctl": "progress",
                    "stage": 2,
                    "stages_total": 4,
                    "stages_completed": 2,
                    "fraction": 0.5,
                    "progress": {
                        "stage": 2,
                        "stages_total": 4,
                        "stages_completed": 2,
                        "fraction": 0.5,
                    },
                    "north_star_done": False,
                }
            ), ""
        if action == "events":
            return 0, json.dumps(
                {
                    "ok": True,
                    "id": CTL_ID,
                    "ctl": "events",
                    "events": [
                        {
                            "ts": "2026-09-11T17:00:00Z",
                            "event": "admit",
                            "type": "WorkflowExecutionStarted",
                        },
                        {
                            "ts": "2026-09-11T17:00:01Z",
                            "event": "stage_completed",
                            "type": "StageCompleted",
                        },
                    ],
                    "n": 2,
                    "durable": True,
                    "siem": False,
                    "north_star_done": False,
                }
            ), ""
        if action == "pause":
            if self.status != "running":
                return 1, json.dumps({"ok": False, "error": "not running"}), ""
            self.status = "paused"
            self.paused = True
            return 0, json.dumps({"ok": True, "id": CTL_ID, "ctl": "pause"}), ""
        if action == "resume":
            if self.status != "paused":
                return 1, json.dumps({"ok": False, "error": "not paused"}), ""
            self.status = "running"
            return 0, json.dumps({"ok": True, "id": CTL_ID, "ctl": "resume"}), ""
        if action == "cancel":
            self.status = "canceled"
            self.canceled = True
            return 0, json.dumps({"ok": True, "id": CTL_ID, "ctl": "cancel"}), ""
        return 1, json.dumps({"ok": False, "error": action}), ""


class OptInOffTests(unittest.TestCase):
    def test_resolve_without_env_is_inert(self) -> None:
        self.assertIsNone(runtime_root_from_env({}))
        self.assertIsNone(lab_hook_from_env({}))
        hook = resolve_runtime_hook({})
        self.assertIsInstance(hook, InertRuntimeHandoffHook)
        self.assertIsNone(hook.admit({"kind": "job"}, None))
        self.assertIs(hook.pause("id", None), False)
        self.assertIs(hook.resume("id", None), False)
        self.assertIsNone(hook.progress("id", None))
        self.assertIsNone(hook.events("id", None))

    def test_missing_root_fails_closed(self) -> None:
        env = {ENV_RUNTIME_ROOT: "/no/such/panoramix-runtime"}
        self.assertIsNone(runtime_root_from_env(env))
        self.assertIsInstance(resolve_runtime_hook(env), InertRuntimeHandoffHook)

    def test_empty_dir_without_apply_fails_closed(self) -> None:
        empty = Path(tempfile.mkdtemp(prefix="sos-lab-empty-"))
        env = {ENV_RUNTIME_ROOT: str(empty)}
        self.assertIsNone(runtime_root_from_env(env))
        self.assertIsInstance(resolve_runtime_hook(env), InertRuntimeHandoffHook)

    def test_default_store_and_http_stay_stub(self) -> None:
        store = JobStore(step_seconds=0.02)
        self.assertIsInstance(store.runtime_hook, InertRuntimeHandoffHook)
        job = store.submit({"demo": "sleep", "seconds": 8})
        self.assertEqual(job.local["backed"], "stub")
        with self.assertRaises(StubOnly) as ctx:
            store.pause(job.id)
        self.assertEqual(ctx.exception.to_dict()["error"], "stub_only")
        store.cancel(job.id)

        app = SosApp(JobStore(step_seconds=0.02))
        created = app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "sleep", "seconds": 8}).encode(),
        )
        body = json.loads(created.body.decode("utf-8"))
        self.assertEqual(body["local"]["backed"], "stub")
        pause = app.handle("POST", f"/v0/jobs/{body['id']}/pause")
        self.assertEqual(pause.status, 409)
        self.assertEqual(json.loads(pause.body.decode("utf-8"))["error"], "stub_only")
        app.handle("POST", f"/v0/jobs/{body['id']}/cancel")


class OptInFakeCtlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = _fake_root()
        self.ctl = _FakeCtl()
        self.hook = LabReserveTemporalHook(self.root, runner=self.ctl)
        self.store = JobStore(step_seconds=0.02, runtime_hook=self.hook)

    def test_lab_hook_from_env_when_root_valid(self) -> None:
        env = {ENV_RUNTIME_ROOT: str(self.root)}
        self.assertEqual(runtime_root_from_env(env), self.root)
        hook = lab_hook_from_env(env, runner=self.ctl)
        self.assertIsInstance(hook, LabReserveTemporalHook)
        resolved = resolve_runtime_hook(env)
        self.assertIsInstance(resolved, LabReserveTemporalHook)
        self.assertFalse(resolved.live)

    def test_live_flag_is_opt_in(self) -> None:
        env = {ENV_RUNTIME_ROOT: str(self.root), ENV_LIVE: "1"}
        hook = lab_hook_from_env(env, runner=self.ctl)
        self.assertTrue(hook.live)

    def test_admit_status_pause_resume_progress_events_cancel(self) -> None:
        job = self.store.submit({"demo": "reserve", "seconds": 8})
        self.assertEqual(job.local["backed"], "runtime")
        self.assertEqual(job.status, "running")
        self.assertIs(job.to_dict()["pause_resume"], True)
        self.assertEqual(job.runtime_ref["id"], CTL_ID)
        self.assertEqual(job.runtime_ref["ctl"], "reserve-temporal")
        self.assertNotIn("workflow_id", job.runtime_ref)
        self.assertNotIn("task_queue", job.runtime_ref)
        self.assertEqual(len(self.ctl.admitted), 1)
        self.assertEqual(self.ctl.admitted[0]["kind"], "job")
        self.assertNotIn("payload", self.ctl.admitted[0])
        self.assertEqual(self.ctl.calls[0][:5], [
            "python3",
            "-m",
            "runtime.apply",
            "reserve-temporal",
            "admit",
        ])
        self.assertIn("--handoff", self.ctl.calls[0])

        progress = self.store.progress(job.id)
        self.assertEqual(progress["source"], PROGRESS_SOURCE_DURABLE)
        self.assertEqual(progress["stages_completed"], 2)
        self.assertEqual(progress["fraction"], 0.5)
        self.assertIn("path-slices", progress["note"].lower())

        events = self.store.events(job.id)
        self.assertEqual(events["source"], EVENTS_SOURCE_DURABLE)
        self.assertIs(events["events_durable"], True)
        self.assertEqual(events["events_n"], 2)
        self.assertEqual([item["event"] for item in events["events"]], ["admit", "stage_completed"])
        self.assertIn("not a siem", events["note"].lower())

        paused = self.store.pause(job.id)
        self.assertEqual(paused.status, "paused")
        self.assertTrue(self.ctl.paused)

        resumed = self.store.resume(job.id)
        self.assertEqual(resumed.status, "running")

        canceled = self.store.cancel(job.id)
        self.assertEqual(canceled.status, "canceled")
        self.assertTrue(self.ctl.canceled)
        actions = [call[4] for call in self.ctl.calls]
        self.assertIn("pause", actions)
        self.assertIn("resume", actions)
        self.assertIn("cancel", actions)
        self.assertIn("progress", actions)
        self.assertIn("events", actions)

    def test_http_opt_in_fake_ctl(self) -> None:
        app = SosApp(self.store)
        created = app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "seconds": 8}).encode(),
        )
        self.assertEqual(created.status, 201)
        job = json.loads(created.body.decode("utf-8"))
        self.assertEqual(job["local"]["backed"], "runtime")
        self.assertIs(job["pause_resume"], True)
        job_id = job["id"]

        paused = app.handle("POST", f"/v0/jobs/{job_id}/pause")
        self.assertEqual(paused.status, 200)
        self.assertEqual(json.loads(paused.body.decode("utf-8"))["status"], "paused")

        progress = json.loads(
            app.handle("GET", f"/v0/jobs/{job_id}/progress").body.decode("utf-8")
        )
        self.assertEqual(progress["source"], "durable")
        self.assertEqual(progress["stages_total"], 4)

        trail = json.loads(
            app.handle("GET", f"/v0/jobs/{job_id}/events").body.decode("utf-8")
        )
        self.assertEqual(trail["source"], "durable")
        self.assertIn("not a siem", trail["note"].lower())

        resumed = app.handle("POST", f"/v0/jobs/{job_id}/resume")
        self.assertEqual(json.loads(resumed.body.decode("utf-8"))["status"], "running")
        canceled = app.handle("POST", f"/v0/jobs/{job_id}/cancel")
        self.assertEqual(json.loads(canceled.body.decode("utf-8"))["status"], "canceled")

    def test_ctl_failure_fails_closed_to_stub(self) -> None:
        def boom(argv, *, cwd, env):
            del argv, cwd, env
            return 1, json.dumps({"ok": False, "error": "nope"}), ""

        hook = LabReserveTemporalHook(self.root, runner=boom)
        store = JobStore(step_seconds=0.02, runtime_hook=hook)
        job = store.submit({"demo": "echo", "message": "fallback"})
        self.assertEqual(job.local["backed"], "stub")
        with self.assertRaises(StubOnly):
            store.pause(job.id)

    def test_honesty_comments(self) -> None:
        text = Path(__file__).resolve().parents[1].joinpath("sos/lab_ctl.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("Does not close runtime #70", text)
        self.assertIn("Does not close #78", text)
        self.assertIn("Does not unlock", text)
        self.assertIn("north_star_done", text)
        self.assertIn("Cloud stays locked", text)
        self.assertIn("fail closed", text)
        self.assertIn("Not guest-callable ctl HTTP", text)
        self.assertNotIn("Fixes #70", text)
        self.assertNotIn("Fixes #78", text)
        imports = [
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        blob = "\n".join(imports)
        self.assertNotIn("from runtime", blob)
        self.assertNotIn("import runtime", blob)
        self.assertIn("import subprocess", blob)


if __name__ == "__main__":
    unittest.main()
