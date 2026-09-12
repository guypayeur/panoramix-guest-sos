"""Omit-when-missing coverage for path-slice elapsed. Never invent."""

from __future__ import annotations

import json
import unittest

from sos.http import SosApp
from sos.jobs import JobStore, PROGRESS_SOURCE_DURABLE, PROGRESS_SOURCE_STUB
from sos.lab_compose import elapsed_plan
from sos.stage_elapsed import (
    ELAPSED_SOURCE_EVENTS,
    ELAPSED_SOURCE_PROGRESS,
    attach_timeline_elapsed,
    elapsed_from_events,
    elapsed_from_progress,
    elapsed_ms_from_mapping,
)


def _timeline() -> list[dict]:
    return [
        {"index": 1, "name": "admit", "state": "completed"},
        {"index": 2, "name": "project", "state": "completed"},
        {"index": 3, "name": "fold", "state": "current"},
        {"index": 4, "name": "complete", "state": "pending"},
    ]


class ElapsedPureTests(unittest.TestCase):
    def test_mapping_omits_missing_negative_and_bool(self) -> None:
        self.assertIsNone(elapsed_ms_from_mapping({}))
        self.assertIsNone(elapsed_ms_from_mapping(None))
        self.assertIsNone(elapsed_ms_from_mapping({"elapsed_ms": -1}))
        self.assertIsNone(elapsed_ms_from_mapping({"elapsed_ms": True}))
        self.assertIsNone(elapsed_ms_from_mapping({"elapsed_ms": "nope"}))
        self.assertEqual(elapsed_ms_from_mapping({"elapsed_ms": 120}), 120)
        self.assertEqual(elapsed_ms_from_mapping({"elapsed_s": 1.5}), 1500)
        self.assertEqual(elapsed_ms_from_mapping({"elapsed_ms": 0}), 0)

    def test_progress_elapsed_attached_and_gaps_omitted(self) -> None:
        durable = {
            "stages": [
                {"name": "admit", "elapsed_ms": 120},
                {"name": "project"},
                {"name": "fold", "elapsed_ms": -4},
            ]
        }
        values = elapsed_from_progress(durable, _timeline())
        self.assertEqual(values[0], 120)
        self.assertIsNone(values[1])
        self.assertIsNone(values[2])
        self.assertIsNone(values[3])

    def test_progress_stage_elapsed_ms_list(self) -> None:
        values = elapsed_from_progress(
            {"stage_elapsed_ms": [80, 200]}, _timeline()
        )
        self.assertEqual(values[0], 80)
        self.assertEqual(values[1], 200)
        self.assertIsNone(values[2])

    def test_progress_omit_when_no_elapsed_fields(self) -> None:
        self.assertEqual(
            elapsed_from_progress(
                {"stage": 2, "stages_total": 4, "stages_completed": 2},
                _timeline(),
            ),
            [],
        )

    def test_events_derive_completed_only(self) -> None:
        events = [
            {"ts": "2026-09-11T16:00:00Z", "event": "admit"},
            {
                "ts": "2026-09-11T16:00:01.500Z",
                "event": "StageCompleted",
                "stages_completed": 1,
            },
            {
                "ts": "2026-09-11T16:00:04Z",
                "event": "stage_completed",
                "stage": "project",
            },
            {"ts": "2026-09-11T16:00:10Z", "event": "pause"},
        ]
        values = elapsed_from_events(events, _timeline())
        self.assertEqual(values[0], 1500)
        self.assertEqual(values[1], 2500)
        self.assertIsNone(values[2])
        self.assertIsNone(values[3])

    def test_events_omit_when_missing_or_unparseable(self) -> None:
        self.assertEqual(elapsed_from_events([], _timeline()), [])
        self.assertEqual(
            elapsed_from_events(
                [{"event": "admit"}, {"event": "StageCompleted"}],
                _timeline(),
            ),
            [],
        )
        self.assertEqual(
            elapsed_from_events(
                [
                    {"ts": "not-a-time", "event": "admit"},
                    {"ts": "also-bad", "event": "StageCompleted"},
                ],
                _timeline(),
            ),
            [],
        )
        self.assertEqual(
            elapsed_from_events(
                [{"ts": "2026-09-11T16:00:00Z", "event": "admit"}],
                _timeline(),
            ),
            [],
        )

    def test_pause_is_not_a_stage_boundary(self) -> None:
        events = [
            {"ts": "2026-09-11T16:00:00Z", "event": "admit"},
            {"ts": "2026-09-11T16:00:02Z", "event": "pause"},
            {"ts": "2026-09-11T16:00:03Z", "event": "resume"},
            {
                "ts": "2026-09-11T16:00:05Z",
                "event": "StageCompleted",
                "stages_completed": 1,
            },
        ]
        values = elapsed_from_events(events, _timeline())
        self.assertEqual(values[0], 5000)
        self.assertTrue(all(item is None for item in values[1:]))

    def test_event_elapsed_ms_preferred_when_present(self) -> None:
        events = [
            {"ts": "2026-09-11T16:00:00Z", "event": "admit"},
            {
                "ts": "2026-09-11T16:00:09Z",
                "event": "StageCompleted",
                "stages_completed": 1,
                "elapsed_ms": 111,
            },
        ]
        values = elapsed_from_events(events, _timeline())
        self.assertEqual(values[0], 111)

    def test_attach_prefers_progress_then_events_then_omit(self) -> None:
        timeline = _timeline()
        source = attach_timeline_elapsed(
            timeline,
            durable={
                "stages": [{"name": "admit", "elapsed_ms": 90}],
            },
            events=[
                {"ts": "2026-09-11T16:00:00Z", "event": "admit"},
                {
                    "ts": "2026-09-11T16:00:02Z",
                    "event": "StageCompleted",
                    "stages_completed": 1,
                },
            ],
            events_durable=True,
        )
        self.assertEqual(source, ELAPSED_SOURCE_PROGRESS)
        self.assertEqual(timeline[0]["elapsed_ms"], 90)
        self.assertNotIn("elapsed_ms", timeline[1])

        from_events = _timeline()
        source = attach_timeline_elapsed(
            from_events,
            durable={"stage": 1, "stages_total": 4},
            events=[
                {"ts": "2026-09-11T16:00:00Z", "event": "admit"},
                {
                    "ts": "2026-09-11T16:00:02Z",
                    "event": "StageCompleted",
                    "stages_completed": 1,
                },
            ],
            events_durable=True,
        )
        self.assertEqual(source, ELAPSED_SOURCE_EVENTS)
        self.assertEqual(from_events[0]["elapsed_ms"], 2000)

        omitted = _timeline()
        source = attach_timeline_elapsed(
            omitted,
            durable={"stage": 1, "stages_total": 4},
            events=[{"event": "admit"}, {"event": "StageCompleted"}],
            events_durable=True,
        )
        self.assertIsNone(source)
        self.assertTrue(all("elapsed_ms" not in item for item in omitted))

        memory = _timeline()
        source = attach_timeline_elapsed(
            memory,
            durable={"stage": 1},
            events=[
                {"ts": "2026-09-11T16:00:00Z", "event": "admit"},
                {
                    "ts": "2026-09-11T16:00:02Z",
                    "event": "StageCompleted",
                    "stages_completed": 1,
                },
            ],
            events_durable=False,
        )
        self.assertIsNone(source)
        self.assertTrue(all("elapsed_ms" not in item for item in memory))

    def test_dry_run_elapsed_plan_omits(self) -> None:
        plan = elapsed_plan()
        self.assertIs(plan["omit_when_missing"], True)
        self.assertIs(plan["invent"], False)
        self.assertIs(plan["north_star_done"], False)
        self.assertIn("Never invent", plan["note"])
        self.assertIn("Omit when missing", plan["note"])


class _ProgressEventsHook:
    def __init__(self, progress, events=None) -> None:
        self._progress = progress
        self._events = events

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
        return dict(self._progress)

    def events(self, job_id, runtime_ref):
        if self._events is None:
            return None
        return dict(self._events)


class ElapsedStoreTests(unittest.TestCase):
    def test_durable_progress_elapsed_and_omit(self) -> None:
        with_ms = _ProgressEventsHook(
            {
                "stage": 2,
                "stages_total": 4,
                "stages_completed": 2,
                "fraction": 0.5,
                "stages": [
                    {"name": "admit", "elapsed_ms": 120},
                    {"name": "project", "elapsed_ms": 3400},
                ],
            }
        )
        store = JobStore(step_seconds=0.02, runtime_hook=with_ms)
        job = store.submit({"demo": "reserve", "seconds": 8})
        body = store.progress(job.id)
        self.assertEqual(body["source"], PROGRESS_SOURCE_DURABLE)
        self.assertEqual(body["elapsed_source"], ELAPSED_SOURCE_PROGRESS)
        self.assertEqual(body["timeline"][0]["elapsed_ms"], 120)
        self.assertEqual(body["timeline"][1]["elapsed_ms"], 3400)
        self.assertEqual(body["timeline"][0]["name"], "admit")
        self.assertEqual(body["timeline"][2]["name"], "fold")
        self.assertEqual(body["timeline"][3]["name"], "complete")
        self.assertNotIn("elapsed_ms", body["timeline"][2])
        self.assertNotIn("elapsed_ms", body["timeline"][3])
        store.cancel(job.id)

        bare = _ProgressEventsHook(
            {
                "stage": 2,
                "stages_total": 4,
                "stages_completed": 2,
                "fraction": 0.5,
            }
        )
        missing = JobStore(step_seconds=0.02, runtime_hook=bare)
        other = missing.submit({"demo": "reserve", "seconds": 8})
        omitted = missing.progress(other.id)
        self.assertEqual(omitted["source"], PROGRESS_SOURCE_DURABLE)
        self.assertNotIn("elapsed_source", omitted)
        for item in omitted["timeline"]:
            self.assertNotIn("elapsed_ms", item)
        missing.cancel(other.id)

    def test_durable_events_derive_elapsed(self) -> None:
        hook = _ProgressEventsHook(
            {
                "stage": 2,
                "stages_total": 4,
                "stages_completed": 2,
                "fraction": 0.5,
            },
            {
                "events": [
                    {"ts": "2026-09-11T16:00:00Z", "event": "admit"},
                    {
                        "ts": "2026-09-11T16:00:01Z",
                        "event": "StageCompleted",
                        "stages_completed": 1,
                    },
                    {
                        "ts": "2026-09-11T16:00:04Z",
                        "event": "StageCompleted",
                        "stages_completed": 2,
                    },
                ],
                "events_durable": True,
                "events_n": 3,
            },
        )
        store = JobStore(step_seconds=0.02, runtime_hook=hook)
        job = store.submit({"demo": "reserve", "seconds": 8})
        body = store.progress(job.id)
        self.assertEqual(body["elapsed_source"], ELAPSED_SOURCE_EVENTS)
        self.assertEqual(body["timeline"][0]["elapsed_ms"], 1000)
        self.assertEqual(body["timeline"][1]["elapsed_ms"], 3000)
        self.assertNotIn("elapsed_ms", body["timeline"][2])
        store.cancel(job.id)

    def test_stub_progress_has_no_timeline_elapsed(self) -> None:
        store = JobStore(step_seconds=0.02)
        job = store.submit({"demo": "reserve", "seconds": 8})
        body = store.progress(job.id)
        self.assertEqual(body["source"], PROGRESS_SOURCE_STUB)
        self.assertNotIn("timeline", body)
        self.assertNotIn("elapsed_source", body)
        store.cancel(job.id)

    def test_handoff_docs_on_job_not_on_handoff(self) -> None:
        store = JobStore(step_seconds=0.02)
        job = store.submit({"demo": "echo", "message": "ok"})
        body = store.public_dict(store.get(job.id))
        docs = body["handoff_docs"]
        self.assertIn("not a second control plane", docs["note"])
        self.assertEqual(docs["handoff"], f"GET /v0/jobs/{job.id}/handoff")
        self.assertEqual(docs["payload"], f"GET /v0/jobs/{job.id}/payload")
        self.assertEqual(docs["lab_compose"], "docs/lab-compose.md")
        self.assertIs(docs["not_control_plane"], True)
        self.assertIs(docs["north_star_done"], False)
        handoff = store.handoff(job.id)
        self.assertNotIn("handoff_docs", handoff)
        self.assertNotIn("elapsed_ms", handoff)


class ElapsedHttpTests(unittest.TestCase):
    def test_progress_http_omits_and_attaches(self) -> None:
        hook = _ProgressEventsHook(
            {
                "stage": 2,
                "stages_total": 4,
                "stages_completed": 2,
                "fraction": 0.5,
                "stages": [{"name": "admit", "elapsed_ms": 50}],
            }
        )
        app = SosApp(JobStore(step_seconds=0.02, runtime_hook=hook))
        created = app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "seconds": 8}).encode(),
        )
        job_id = json.loads(created.body.decode("utf-8"))["id"]
        body = json.loads(
            app.handle("GET", f"/v0/jobs/{job_id}/progress").body.decode("utf-8")
        )
        self.assertEqual(body["timeline"][0]["elapsed_ms"], 50)
        self.assertNotIn("elapsed_ms", body["timeline"][1])
        job = json.loads(
            app.handle("GET", f"/v0/jobs/{job_id}").body.decode("utf-8")
        )
        self.assertIn("not a second control plane", job["handoff_docs"]["note"])
        app.handle("POST", f"/v0/jobs/{job_id}/cancel")


if __name__ == "__main__":
    unittest.main()
