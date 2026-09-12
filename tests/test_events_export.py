"""Kind filter + JSON/JSONL salvage export — not SIEM, no live Temporal."""

from __future__ import annotations

import json
import unittest

from sos.events_export import (
    EVENTS_EXPORT_NOTE,
    event_matches_kinds,
    events_to_jsonl,
    filter_events,
    parse_events_format,
    parse_kind_filter,
)
from sos.http import SosApp
from sos.jobs import EVENTS_SOURCE_DURABLE, EVENTS_SOURCE_MEMORY, JobStore


def _json(resp) -> dict:
    return json.loads(resp.body.decode("utf-8"))


class KindFilterHelpersTests(unittest.TestCase):
    def test_parse_kind_filter_splits_and_dedupes(self) -> None:
        self.assertEqual(parse_kind_filter(None), [])
        self.assertEqual(
            parse_kind_filter(["admit,pause", "cancel"]),
            ["admit", "pause", "cancel"],
        )
        self.assertEqual(parse_kind_filter("admit, admit,pause"), ["admit", "pause"])

    def test_aliases_match_memory_and_durable_names(self) -> None:
        canceled = {"event": "canceled"}
        self.assertTrue(event_matches_kinds(canceled, ["cancel"]))
        self.assertTrue(event_matches_kinds(canceled, ["canceled"]))
        self.assertFalse(event_matches_kinds(canceled, ["pause"]))

        stage = {
            "event": "stage_completed",
            "type": "StageCompleted",
        }
        self.assertTrue(event_matches_kinds(stage, ["StageCompleted"]))
        self.assertTrue(event_matches_kinds(stage, ["stage_completed"]))
        self.assertTrue(event_matches_kinds({"event": "stage"}, ["StageCompleted"]))

        self.assertTrue(event_matches_kinds({"event": "succeeded"}, ["succeed"]))
        self.assertTrue(event_matches_kinds({"event": "fail"}, ["failed"]))
        self.assertTrue(event_matches_kinds({"event": "paused"}, ["pause"]))
        self.assertTrue(event_matches_kinds({"kind": "admit"}, ["admit"]))

    def test_filter_empty_is_honest(self) -> None:
        trail = [
            {"event": "admit"},
            {"event": "pause"},
        ]
        self.assertEqual(filter_events(trail, ["fail"]), [])
        self.assertEqual(filter_events([], ["admit"]), [])
        self.assertEqual(filter_events(None, ["admit"]), [])
        self.assertEqual(len(filter_events(trail, [])), 2)

    def test_jsonl_empty_and_roundtrip(self) -> None:
        self.assertEqual(events_to_jsonl([]), b"")
        raw = events_to_jsonl([{"event": "admit"}, {"event": "pause"}])
        lines = [json.loads(line) for line in raw.decode().splitlines()]
        self.assertEqual([item["event"] for item in lines], ["admit", "pause"])

    def test_parse_format(self) -> None:
        self.assertEqual(parse_events_format(None), "json")
        self.assertEqual(parse_events_format("JSONL"), "jsonl")
        self.assertEqual(parse_events_format("ndjson"), "jsonl")
        with self.assertRaises(ValueError):
            parse_events_format("csv")


class _DurableEventsHook:
    def __init__(self, payload) -> None:
        self.payload = payload

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

    def events(self, job_id, runtime_ref):
        return self.payload


class MemoryAndDurableFilterTests(unittest.TestCase):
    def test_memory_filter_and_empty_match(self) -> None:
        store = JobStore(step_seconds=0.02)
        job = store.submit({"demo": "echo", "message": "hi"})
        store.cancel(job.id)
        all_events = store.events(job.id)
        self.assertEqual(all_events["source"], EVENTS_SOURCE_MEMORY)
        self.assertIn("not a siem", all_events["note"].lower())
        self.assertIn("not regulatory defensibility", all_events["note"].lower())
        self.assertIn("not a regulatory audit", all_events["note"])
        self.assertIn("not a SIEM", all_events["export_note"])
        self.assertNotIn("kind_filter", all_events)
        names = [item["event"] for item in all_events["events"]]
        self.assertIn("submitted", names)
        self.assertIn("canceled", names)

        canceled = store.events(job.id, ["cancel"])
        self.assertEqual(canceled["kind_filter"], ["cancel"])
        self.assertTrue(canceled["events"])
        self.assertEqual(canceled["events"][-1]["event"], "canceled")
        self.assertEqual(canceled["events_n"], len(canceled["events"]))
        self.assertGreaterEqual(canceled["events_total"], canceled["events_n"])

        empty = store.events(job.id, ["fail"])
        self.assertEqual(empty["events"], [])
        self.assertEqual(empty["events_n"], 0)
        self.assertGreater(empty["events_total"], 0)
        self.assertIn("not regulatory defensibility", empty["export_note"])

    def test_durable_filter_stagecompleted_and_empty_trail(self) -> None:
        hook = _DurableEventsHook(
            {
                "events": [
                    {"event": "admit", "type": "WorkflowExecutionStarted"},
                    {
                        "event": "stage_completed",
                        "type": "StageCompleted",
                    },
                    {"event": "pause", "signal": "pause"},
                    {"event": "succeed", "type": "WorkflowExecutionCompleted"},
                ],
                "events_durable": True,
                "events_n": 4,
            }
        )
        store = JobStore(step_seconds=0.02, runtime_hook=hook)
        job = store.submit({"demo": "reserve", "seconds": 8})
        full = store.events(job.id)
        self.assertEqual(full["source"], EVENTS_SOURCE_DURABLE)
        self.assertEqual(full["events_n"], 4)
        self.assertIn("not regulatory defensibility", full["note"].lower())

        staged = store.events(job.id, ["StageCompleted"])
        self.assertEqual([item["event"] for item in staged["events"]], ["stage_completed"])
        self.assertEqual(staged["events_n"], 1)
        self.assertEqual(staged["events_total"], 4)
        self.assertEqual(staged["kind_filter"], ["StageCompleted"])

        multi = store.events(job.id, ["admit", "succeed"])
        self.assertEqual(
            [item["event"] for item in multi["events"]], ["admit", "succeed"]
        )

        miss = store.events(job.id, ["resume"])
        self.assertEqual(miss["events"], [])
        self.assertEqual(miss["events_n"], 0)
        store.cancel(job.id)

        empty_hook = _DurableEventsHook(
            {"events": [], "events_durable": True, "events_n": 0}
        )
        empty_store = JobStore(step_seconds=0.02, runtime_hook=empty_hook)
        empty_job = empty_store.submit({"demo": "echo", "message": "x"})
        trail = empty_store.events(empty_job.id)
        self.assertEqual(trail["source"], EVENTS_SOURCE_DURABLE)
        self.assertEqual(trail["events"], [])
        self.assertEqual(trail["events_n"], 0)
        self.assertIn("not a siem", trail["note"].lower())
        empty_store.cancel(empty_job.id)


class EventsExportHttpTests(unittest.TestCase):
    def test_info_lists_filter_and_export(self) -> None:
        app = SosApp(JobStore(step_seconds=0.02))
        body = _json(app.handle("GET", "/v0/info"))
        self.assertIn("?kind=", body["jobs"]["events_filter"])
        self.assertIn("format=jsonl", body["jobs"]["events_export"])
        self.assertIn("not regulatory defensibility", body["jobs"]["events_honesty"])
        self.assertIn("not a SIEM", body["jobs"]["events_export_honesty"])
        self.assertIn(EVENTS_EXPORT_NOTE, body["jobs"]["events_export_honesty"])

    def test_http_kind_filter_and_jsonl_download(self) -> None:
        app = SosApp(JobStore(step_seconds=0.02))
        created = app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "sleep", "seconds": 8}).encode(),
        )
        job_id = _json(created)["id"]
        app.handle("POST", f"/v0/jobs/{job_id}/cancel")

        filtered = app.handle("GET", f"/v0/jobs/{job_id}/events?kind=cancel")
        self.assertEqual(filtered.status, 200)
        body = _json(filtered)
        self.assertEqual(body["kind_filter"], ["cancel"])
        self.assertTrue(body["events"])
        self.assertEqual(body["events"][-1]["event"], "canceled")
        self.assertIn("not regulatory defensibility", body["export_note"])
        self.assertEqual(
            filtered.headers["X-Sos-Events-Note"], EVENTS_EXPORT_NOTE
        )
        self.assertEqual(filtered.headers["X-Sos-Events-Source"], "memory")

        empty = _json(app.handle("GET", f"/v0/jobs/{job_id}/events?kind=fail"))
        self.assertEqual(empty["events"], [])
        self.assertEqual(empty["events_n"], 0)

        jsonl = app.handle(
            "GET", f"/v0/jobs/{job_id}/events?kind=cancel&format=jsonl"
        )
        self.assertEqual(jsonl.status, 200)
        self.assertEqual(jsonl.content_type, "application/x-ndjson")
        self.assertIn("attachment", jsonl.headers["Content-Disposition"])
        self.assertIn(job_id, jsonl.headers["Content-Disposition"])
        self.assertTrue(jsonl.headers["Content-Disposition"].endswith('.jsonl"'))
        lines = [
            json.loads(line)
            for line in jsonl.body.decode("utf-8").splitlines()
            if line.strip()
        ]
        self.assertTrue(lines)
        self.assertEqual(lines[-1]["event"], "canceled")

        empty_jsonl = app.handle(
            "GET", f"/v0/jobs/{job_id}/events?kind=fail&format=jsonl"
        )
        self.assertEqual(empty_jsonl.status, 200)
        self.assertEqual(empty_jsonl.body, b"")
        self.assertIn("not a SIEM", empty_jsonl.headers["X-Sos-Events-Note"])

        downloaded = app.handle(
            "GET", f"/v0/jobs/{job_id}/events?format=json&download=1"
        )
        self.assertIn("attachment", (downloaded.headers or {}).get("Content-Disposition", ""))
        self.assertIn(".json", downloaded.headers["Content-Disposition"])

        bad = app.handle("GET", f"/v0/jobs/{job_id}/events?format=csv")
        self.assertEqual(bad.status, 400)
        self.assertEqual(_json(bad)["error"], "invalid_format")

    def test_http_durable_filter_and_jsonl(self) -> None:
        hook = _DurableEventsHook(
            {
                "events": [
                    {"event": "admit"},
                    {"event": "stage_completed", "type": "StageCompleted"},
                    {"event": "fail"},
                ],
                "events_durable": True,
                "events_n": 3,
            }
        )
        app = SosApp(JobStore(step_seconds=0.02, runtime_hook=hook))
        created = app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "seconds": 8}).encode(),
        )
        job_id = _json(created)["id"]
        staged = _json(
            app.handle("GET", f"/v0/jobs/{job_id}/events?kind=StageCompleted")
        )
        self.assertEqual(staged["source"], EVENTS_SOURCE_DURABLE)
        self.assertEqual([item["event"] for item in staged["events"]], ["stage_completed"])
        jsonl = app.handle(
            "GET", f"/v0/jobs/{job_id}/events?kind=admit,fail&format=jsonl"
        )
        names = [
            json.loads(line)["event"]
            for line in jsonl.body.decode("utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(names, ["admit", "fail"])
        self.assertEqual(jsonl.headers["X-Sos-Events-Source"], "durable")
        app.handle("POST", f"/v0/jobs/{job_id}/cancel")


if __name__ == "__main__":
    unittest.main()
