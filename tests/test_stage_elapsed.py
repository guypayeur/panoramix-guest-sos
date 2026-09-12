"""Omit-when-missing coverage for path-slice elapsed. Never invent."""

from __future__ import annotations

import json
import unittest

from sos.http import SosApp
from sos.jobs import JobStore, PROGRESS_SOURCE_DURABLE, PROGRESS_SOURCE_STUB
from sos.lab_compose import elapsed_plan, wall_plan
from sos.stage_elapsed import (
    ELAPSED_SOURCE_EVENTS,
    ELAPSED_SOURCE_PROGRESS,
    WALL_SOURCE_PROGRESS,
    WALL_SOURCE_STATUS,
    attach_timeline_elapsed,
    elapsed_from_events,
    elapsed_from_progress,
    elapsed_ms_from_mapping,
    wall_elapsed_ms_from_durable,
    wall_elapsed_ms_from_mapping,
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
        self.assertEqual(plan["runtime_tip"], "9ba95bbb")
        self.assertEqual(plan["docs_tip"], "5dc191cb")
        self.assertEqual(plan["or"], "main")
        self.assertIn("Never invent", plan["note"])
        self.assertIn("Omit when missing", plan["note"])
        self.assertIn("9ba95bbb", plan["note"])
        self.assertIn("5dc191cb", plan["note"])

    def test_wall_mapping_omits_missing_negative_and_bool(self) -> None:
        self.assertIsNone(wall_elapsed_ms_from_mapping({}))
        self.assertIsNone(wall_elapsed_ms_from_mapping(None))
        self.assertIsNone(wall_elapsed_ms_from_mapping({"wall_elapsed_ms": -1}))
        self.assertIsNone(wall_elapsed_ms_from_mapping({"wall_elapsed_ms": True}))
        self.assertIsNone(wall_elapsed_ms_from_mapping({"wall_elapsed_ms": "nope"}))
        self.assertEqual(wall_elapsed_ms_from_mapping({"wall_elapsed_ms": 2500}), 2500)
        self.assertEqual(wall_elapsed_ms_from_mapping({"wall_elapsed_s": 1.5}), 1500)
        self.assertEqual(wall_elapsed_ms_from_mapping({"elapsed_ms": 80}), 80)
        self.assertEqual(wall_elapsed_ms_from_mapping({"wall_elapsed_ms": 0}), 0)

    def test_wall_prefers_explicit_over_generic_elapsed(self) -> None:
        self.assertEqual(
            wall_elapsed_ms_from_mapping(
                {"wall_elapsed_ms": 400, "elapsed_ms": 9}
            ),
            400,
        )
        self.assertIsNone(
            wall_elapsed_ms_from_mapping(
                {"wall_elapsed_ms": -2, "elapsed_ms": 9}
            )
        )

    def test_wall_from_durable_nested_and_omit(self) -> None:
        self.assertEqual(
            wall_elapsed_ms_from_durable({"wall_elapsed_ms": 1200}),
            1200,
        )
        self.assertEqual(
            wall_elapsed_ms_from_durable(
                {"progress": {"wall_elapsed_ms": 3300}}
            ),
            3300,
        )
        self.assertEqual(
            wall_elapsed_ms_from_durable({"wall_elapsed_s": "2"}),
            2000,
        )
        self.assertIsNone(
            wall_elapsed_ms_from_durable(
                {
                    "stage": 2,
                    "stages_total": 4,
                    "stages": [
                        {"name": "admit", "elapsed_ms": 120},
                        {"name": "project", "elapsed_ms": 3400},
                    ],
                }
            )
        )
        self.assertIsNone(wall_elapsed_ms_from_durable({}))
        self.assertIsNone(wall_elapsed_ms_from_durable(None))

    def test_dry_run_wall_plan_omits(self) -> None:
        plan = wall_plan()
        self.assertIs(plan["omit_when_missing"], True)
        self.assertIs(plan["invent"], False)
        self.assertIs(plan["forecast"], False)
        self.assertIs(plan["ifrs17"], False)
        self.assertIs(plan["iec_spa"], False)
        self.assertIs(plan["north_star_done"], False)
        self.assertEqual(plan["runtime_tip"], "5dc191cb")
        self.assertEqual(plan["lineage"], "9ba95bbb")
        self.assertIn("Never invent", plan["note"])
        self.assertIn("Omit when missing", plan["note"])
        self.assertIn("not a forecast", plan["note"].lower())
        self.assertIn("not ifrs17", plan["note"].lower())
        self.assertIn("not iec spa", plan["note"].lower())


class _ProgressEventsHook:
    def __init__(self, progress, events=None, status_payload=None) -> None:
        self._progress = progress
        self._events = events
        self.last_status_payload = status_payload

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
        self.assertNotIn("wall_elapsed_ms", body)
        self.assertNotIn("wall_source", body)
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
        self.assertNotIn("wall_elapsed_ms", omitted)
        self.assertNotIn("wall_source", omitted)
        for item in omitted["timeline"]:
            self.assertNotIn("elapsed_ms", item)
        missing.cancel(other.id)

    def test_durable_wall_from_progress_and_omit(self) -> None:
        with_wall = _ProgressEventsHook(
            {
                "stage": 2,
                "stages_total": 4,
                "stages_completed": 2,
                "fraction": 0.5,
                "wall_elapsed_ms": 2500,
            }
        )
        store = JobStore(step_seconds=0.02, runtime_hook=with_wall)
        job = store.submit({"demo": "reserve", "seconds": 8})
        body = store.progress(job.id)
        self.assertEqual(body["source"], PROGRESS_SOURCE_DURABLE)
        self.assertEqual(body["wall_elapsed_ms"], 2500)
        self.assertEqual(body["wall_source"], WALL_SOURCE_PROGRESS)
        self.assertIn("not a forecast", body["wall_note"].lower())
        self.assertIn("not ifrs17", body["wall_note"].lower())
        self.assertIn("not iec spa", body["wall_note"].lower())
        store.cancel(job.id)

        nested = _ProgressEventsHook(
            {
                "stage": 1,
                "stages_total": 4,
                "progress": {"wall_elapsed_s": 3},
            }
        )
        nest_store = JobStore(step_seconds=0.02, runtime_hook=nested)
        nest_job = nest_store.submit({"demo": "reserve", "seconds": 8})
        nest_body = nest_store.progress(nest_job.id)
        self.assertEqual(nest_body["wall_elapsed_ms"], 3000)
        self.assertEqual(nest_body["wall_source"], WALL_SOURCE_PROGRESS)
        nest_store.cancel(nest_job.id)

        from_status = _ProgressEventsHook(
            {
                "stage": 2,
                "stages_total": 4,
                "stages_completed": 1,
            },
            status_payload={"id": "cw_statuswall", "wall_elapsed_ms": 900},
        )
        status_store = JobStore(step_seconds=0.02, runtime_hook=from_status)
        status_job = status_store.submit({"demo": "reserve", "seconds": 8})
        status_body = status_store.progress(status_job.id)
        self.assertEqual(status_body["wall_elapsed_ms"], 900)
        self.assertEqual(status_body["wall_source"], WALL_SOURCE_STATUS)
        status_store.cancel(status_job.id)

        invalid = _ProgressEventsHook(
            {
                "stage": 2,
                "stages_total": 4,
                "wall_elapsed_ms": -8,
            }
        )
        bad = JobStore(step_seconds=0.02, runtime_hook=invalid)
        bad_job = bad.submit({"demo": "reserve", "seconds": 8})
        omitted = bad.progress(bad_job.id)
        self.assertEqual(omitted["source"], PROGRESS_SOURCE_DURABLE)
        self.assertNotIn("wall_elapsed_ms", omitted)
        bad.cancel(bad_job.id)

    def test_progress_wall_preferred_over_status(self) -> None:
        hook = _ProgressEventsHook(
            {
                "stage": 2,
                "stages_total": 4,
                "wall_elapsed_ms": 111,
            },
            status_payload={"wall_elapsed_ms": 999},
        )
        store = JobStore(step_seconds=0.02, runtime_hook=hook)
        job = store.submit({"demo": "reserve", "seconds": 8})
        body = store.progress(job.id)
        self.assertEqual(body["wall_elapsed_ms"], 111)
        self.assertEqual(body["wall_source"], WALL_SOURCE_PROGRESS)
        store.cancel(job.id)

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
        self.assertNotIn("wall_elapsed_ms", body)
        self.assertNotIn("wall_source", body)
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
        self.assertNotIn("wall_elapsed_ms", body)
        job = json.loads(
            app.handle("GET", f"/v0/jobs/{job_id}").body.decode("utf-8")
        )
        self.assertIn("not a second control plane", job["handoff_docs"]["note"])
        app.handle("POST", f"/v0/jobs/{job_id}/cancel")

    def test_progress_http_wall_present_and_omit(self) -> None:
        present = _ProgressEventsHook(
            {
                "stage": 2,
                "stages_total": 4,
                "stages_completed": 2,
                "fraction": 0.5,
                "wall_elapsed_ms": 1800,
            }
        )
        app = SosApp(JobStore(step_seconds=0.02, runtime_hook=present))
        created = app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "seconds": 8}).encode(),
        )
        job_id = json.loads(created.body.decode("utf-8"))["id"]
        body = json.loads(
            app.handle("GET", f"/v0/jobs/{job_id}/progress").body.decode("utf-8")
        )
        self.assertEqual(body["wall_elapsed_ms"], 1800)
        self.assertEqual(body["wall_source"], WALL_SOURCE_PROGRESS)
        self.assertIn("not a forecast", body["wall_note"].lower())
        app.handle("POST", f"/v0/jobs/{job_id}/cancel")

        omitted_app = SosApp(
            JobStore(
                step_seconds=0.02,
                runtime_hook=_ProgressEventsHook(
                    {
                        "stage": 2,
                        "stages_total": 4,
                        "stages_completed": 2,
                    }
                ),
            )
        )
        other = omitted_app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "seconds": 8}).encode(),
        )
        other_id = json.loads(other.body.decode("utf-8"))["id"]
        omitted = json.loads(
            omitted_app.handle("GET", f"/v0/jobs/{other_id}/progress").body.decode(
                "utf-8"
            )
        )
        self.assertEqual(omitted["source"], PROGRESS_SOURCE_DURABLE)
        self.assertNotIn("wall_elapsed_ms", omitted)
        omitted_app.handle("POST", f"/v0/jobs/{other_id}/cancel")


if __name__ == "__main__":
    unittest.main()
