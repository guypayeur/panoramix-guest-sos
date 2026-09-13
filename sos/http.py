"""Public HTTP surface for the SoS guest (health, jobs API, operator UI).

Served on the Unit public port. JSON errors are `{"error": ..., ...}`.
No engine URL schemes in request or response bodies. Ctl exports
``GET /v0/jobs/{id}/handoff`` (WorkHandoff projection, no nested payload)
and ``GET /v0/jobs/{id}/payload`` (canonical JSON bytes as hex/utf8).
Pause/resume (``POST .../pause`` / ``POST .../resume``) require the
durable path; stub-only jobs return 409 stub_only. One-click
re-admit (``POST .../re-admit``) is durable-hook only; inert or
missing payload fail closed. Events prefer
``hook.events()`` JSONL when durable-backed. Compare uses guest
history (in-process plus local lab files when persisted). Transport
is operator/ctl-mediated: no guest→ctl HTTP, no
``runtime.apply compute-work`` from this guest.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from sos.errors import InvalidStatus, SosError
from sos.events_export import (
    EVENTS_EXPORT_NOTE,
    EVENTS_FORMAT_JSON,
    EVENTS_FORMAT_JSONL,
    download_filename,
    events_to_jsonl,
    parse_events_format,
    parse_kind_filter,
)
from sos.handoff_vocab import (
    CTL_ADMIT,
    CTL_CANCEL,
    CTL_EVENTS,
    CTL_IEC_LOCAL_ADMIT,
    CTL_IEC_LOCAL_PORT,
    CTL_PAUSE_RESUME,
    CTL_PROGRESS,
    IEC_METHOD_PIN,
    IEC_SOURCE_FILE,
    LAB_COMPOSE_IEC_DOCS,
    LAB_COMPOSE_IEC_SCRIPT,
    LOCAL_DEMOS,
    PARITY_PAYLOAD_DIGEST,
    RECORDED_PAYLOAD_DIGEST,
    RESERVE_CATALOG_SAME_JOB,
    RESOURCE_CLASSES,
    SAME_JOB_PAYLOAD_DIGEST,
    WORK_KINDS,
    WORK_STATUSES,
)
from sos.jobs import JobStore
from sos.persist import describe_history_persist, jobs_dir_from_env
from sos.runtime_hook import describe_runtime_hook, resolve_runtime_hook
from sos.ui import OPERATOR_HTML

MAX_BODY = 64 * 1024
HEALTH_PAYLOAD = {"status": "ok"}
INFO_PAYLOAD = {
    "name": "sos",
    "product": "panoramix-guest-sos",
    "kind": "actuarial-guest",
    "contract_version": "0.5",
    "status": "day-one",
    "iec_equivalent": False,
    "engines": "runtime-bindings-only",
    "jobs": {
        "kinds": sorted(WORK_KINDS),
        "classes": sorted(RESOURCE_CLASSES),
        "statuses": list(WORK_STATUSES),
        "handoff": ["kind", "class", "payload_digest"],
        "local_demo": sorted(LOCAL_DEMOS),
        "ux_seed": (
            "reserve is a stub lifecycle for operator UX; "
            "not a perf baseline until runtime #83 + remeasure"
        ),
        "iec_named_baseline": "grammar/examples/reserve_ifrs17",
        "reserve_payload_keys": [
            "accounts",
            "discount_bps",
            "horizon",
            "lapse_bps",
            "paths",
            "seed",
            "workload",
        ],
        "reserve_catalogs": ["recorded", "live", "parity"],
        "reserve_digest_recorded": RECORDED_PAYLOAD_DIGEST,
        "reserve_digest_parity": PARITY_PAYLOAD_DIGEST,
        "iec_local": {
            "ctl": "iec-local",
            "ctl_port": CTL_IEC_LOCAL_PORT,
            "binding": "bindings/local-iec.example.yaml",
            "catalog": RESERVE_CATALOG_SAME_JOB,
            "catalog_alias": "same-job",
            "digest": SAME_JOB_PAYLOAD_DIGEST,
            "revision": IEC_METHOD_PIN,
            "source_file": IEC_SOURCE_FILE,
            "ifrs17_guest": False,
            "lab_compose": LAB_COMPOSE_IEC_DOCS,
            "script": LAB_COMPOSE_IEC_SCRIPT,
            "runtime_docs": "docs/iec-local.md",
            "runtime_tip": "d480dc8",
            "ux_runtime_tip": "d9b9948",
            "ux_runtime_signal_tip": "e2f41fd",
            "admit": CTL_IEC_LOCAL_ADMIT,
            "north_star_done": False,
            "note": (
                "Pinned iec reserve_ifrs17 same-job. Guest does not "
                "run IFRS17 math. Runtime binding wraps the operator "
                "iec checkout (POST /v1/jobs). Phase/fraction omit when "
                "missing (Platform unknown/0 defaults) — never invent. "
                "Walls (api_e2e_ms) omit when missing — never invent. "
                "Pause/held/resume and FAILED next_action / stage_name "
                "pass through when ctl supplies them (runtime tip "
                "d9b9948+ pause_limit / already_canceled) — omit when "
                "missing. pause_signaled / resume_signaled pass through "
                "when iec-local ctl returns them after pause/resume "
                "(runtime tip e2f41fd+) — omit when missing; never "
                "invent held; do not enable pause without can_pause. "
                "Not #70 Done. north_star_done false. Cloud locked."
            ),
        },
        "runtime_reserve": "docs/reserve.md",
        "runtime_reserve_helpers": [
            "runtime.reserve.digest_for",
            "runtime.reserve.recorded_params",
            "runtime.reserve.live_params",
            "runtime.reserve.parity_params",
        ],
        "runtime_reserve_parity": "runtime.reserve.parity_params",
        "ctl_handoff": {
            "mode": "operator-ctl",
            "guest_to_ctl_http": False,
            "guest_callable_submit": False,
            "handoff": "GET /v0/jobs/{id}/handoff",
            "payload": "GET /v0/jobs/{id}/payload",
            "mesh": "compute-job -> sos",
            "note": (
                "Transport is operator/ctl-mediated. Guest UX is "
                "submit/status/cancel plus durable-path pause/resume. "
                "Emit WorkHandoff JSON only — no "
                "guest→ctl HTTP, no runtime.apply compute-work, no env "
                "that adds mesh destinations. Stub is the fallback; "
                "operator/ctl admits via the binding. Default hook stays "
                "inert. Opt-in lab: PANORAMIX_CTL_HTTP loopback ctl "
                "HTTP (preferred) or PANORAMIX_RUNTIME_ROOT local "
                "apply loopback to reserve-temporal on the existing hook "
                "seam (not mesh HTTP; not guest→mesh ctl). "
                "One-shot lab: scripts/lab_compose_reserve_temporal.py "
                "(runtime.serve + PANORAMIX_CTL_HTTP). "
                "Sibling iec-local same-job: "
                "scripts/lab_compose_iec_local.py (ctl 19216, catalog "
                "reserve_ifrs17 / same-job). Guest does not run IFRS17 "
                "math — runtime binding wraps the operator iec checkout. "
                "When PANORAMIX_CTL_HTTP is set but runtime.serve is down, "
                "admit/status/progress fail closed with ctl_http_unreachable "
                "(lab-serve down) — not a hung poll, not pretend durable. "
                "HTTP timeout while the origin is listening is "
                "ctl_admit_timeout on admit (not lab-serve-down); status/"
                "progress timeout is a missed poll. Admit that exceeds "
                "guest timeout before a running id is ctl_admit_timeout "
                "(runtime #143; live|parity is minutes-class) — fail closed, "
                "not stub progress. Poll GET /progress and GET /events "
                "once admit returns running. "
                "Not a perf baseline until runtime #83 + remeasure. Not #70 Done."
            ),
        },
        "ctl_http_unreachable": (
            "When PANORAMIX_CTL_HTTP is a valid loopback origin but "
            "runtime.serve is down (connection refused / origin not "
            "listening), admit/status/progress fail closed with error "
            "ctl_http_unreachable (lab-serve down). Not a hung poll. "
            "Not pretend durable. HTTP timeout while the origin is "
            "listening is not this error. Without the env, inert stub "
            "is unchanged. Not #70 Done."
        ),
        "ctl_admit_timeout": (
            "Durable admit that exceeds guest timeout (HTTP admit 8s / "
            "poll 1.5s / ctl-apply admit 2s) before a running id is "
            "ctl_admit_timeout — not lab-serve-down. Origin was "
            "listening. live|parity is minutes-class and depends on "
            "runtime #143 admit-return-running. Fail closed; no stub "
            "progress. Poll GET /progress and GET /events mid-flight "
            "once a running id exists. Not #70 Done. "
            "north_star_done false."
        ),
        "list": "GET /v0/jobs",
        "list_status": "GET /v0/jobs?status=queued|running|paused|held|succeeded|failed|canceled",
        "list_status_honesty": (
            "Filter is the real job.status from the store. "
            "Repeat or comma-separate to OR known statuses. "
            "Unknown values (accepted, cancelled) are 400 invalid_status. "
            "Not a SPA query language."
        ),
        "auto_refresh_honesty": (
            "Operator UI light poll of list + selected job detail. "
            "Opt-in checkbox, or on when jobs.durable_hook.durable_path. "
            "Stops when the selected job is terminal. "
            "Does not invent progress. Not a SPA framework."
        ),
        "progress": "GET /v0/jobs/{id}/progress",
        "events": "GET /v0/jobs/{id}/events",
        "events_filter": "GET /v0/jobs/{id}/events?kind=admit,StageCompleted,pause,resume,cancel,succeed,fail",
        "events_export": "GET /v0/jobs/{id}/events?format=jsonl",
        "compare": "GET /v0/jobs/{id}/compare",
        "progress_honesty": (
            "durable reserve-temporal path-slices when a hook provides them "
            "(named stages admit/project/fold/complete or hook-provided, "
            "plus investigate ownership tags, completed vs current vs pending); "
            "fraction / stages_completed stay the hook counters; "
            "iec-local same-job prefers phase/fraction when the hook "
            "supplies them (runtime #149 / #150 omit Platform unknown/0 "
            "defaults — never invent; no invented SPA chunk/ETA/"
            "heartbeat chrome); optional nested iec_job_id / cw_id when "
            "the hook/ctl supplies them — omitted when missing; "
            "optional pause_limit / held / can_pause / next_action / "
            "valuation / stage_name when ctl supplies them (runtime "
            "tip d9b9948+) — omitted when missing; "
            "optional pause_signaled / resume_signaled / is_paused when "
            "iec-local ctl returns them after pause/resume (runtime "
            "tip e2f41fd+) — omitted when missing; never invent held; "
            "guest does not run IFRS17 math; "
            "optional per-stage elapsed from durable progress "
            "stages[].elapsed_ms (runtime tip 9ba95bbb / docs tip 5dc191cb / "
            "main) or GET /events timestamps when present; "
            "optional wall_elapsed_ms / api_e2e_ms / started_at from durable "
            "progress/status/walls (runtime tip 9b6646e8 / main, PR #114; "
            "iec-local #145 api_e2e) when "
            "the hook JSON includes it — omitted when missing — never invented; "
            "not a forecast; not IFRS17; not iec SPA; "
            "else stub stage i of n without fake names; "
            "not iec planner parallelism; not iec chunk progress. "
            f"Operator/ctl: {CTL_PROGRESS}"
        ),
        "handoff_docs": (
            "Job-detail compact reminders for handoff + payload export, "
            "recoverability / re-admit, and lab-compose "
            "(docs/lab-compose.md; iec-local docs/lab-compose-iec-local.md). "
            "Operator clarity — not a second "
            "control plane. Guest does not run IFRS17 math. "
            "Not #70 Done. Not SIEM. Not IFRS17."
        ),
        "events_honesty": (
            "durable reserve-temporal JSONL trail when a hook provides it; "
            "else process-memory fallback; filter by kind "
            "(admit / StageCompleted / pause / resume / cancel / "
            "succeed/fail / …); export JSON or JSONL for local salvage; "
            "not a SIEM; not iec /v1/audit/events product; "
            "not a regulatory audit; not regulatory defensibility. "
            f"Operator/ctl: {CTL_EVENTS}"
        ),
        "events_export_honesty": EVENTS_EXPORT_NOTE,
        "investigate_honesty": (
            "catalog identity already on the job (name + short digest) "
            "for cross-check; not a data-catalog product. "
            "Static day-one path-slice ownership tags when durable-hooked "
            "(admit / project / fold / complete); not Slack; "
            "not a live team directory. "
            "Event trail stays on the same panel; not a SIEM."
        ),
        "compare_honesty": (
            "guest process history plus local lab files when persisted "
            "(.sos/jobs or PANORAMIX_SOS_JOBS_DIR). recent same-catalog "
            "jobs when catalog is on the job, else same kind/class. "
            "Elapsed prefers durable wall_elapsed_ms when the hook or a "
            "persisted job field includes it (runtime tip 9b6646e8 / "
            "main, PR #114); else created/updated timestamps. "
            "Typical/ETA only from succeeded prior walls when two or "
            "more samples exist. Omit when missing; never invent. "
            "Fail-closed if persistence is disabled or the dir is "
            "unwritable. not a forecast; not IFRS17; not iec SPA "
            "historical widget. No guest→ctl HTTP."
        ),
        "history_persist": {
            "env": "PANORAMIX_SOS_JOBS_DIR",
            "default": ".sos/jobs",
            "disable": "off",
            "note": (
                "Local lab job records for compare / recoverability. "
                "Fail-closed if disabled or unwritable. Reloads recent "
                "succeeded priors across guest restart. Optional "
                "wall_elapsed_ms when a durable hook returned it. "
                "Does not invent typical/ETA or walls. Not a SIEM. "
                "Not a six-month audit product. Not a cross-host DB. "
                "Not #70 Done."
            ),
        },
        "pause": "POST /v0/jobs/{id}/pause",
        "resume": "POST /v0/jobs/{id}/resume",
        "pause_resume": True,
        "pause_resume_honesty": (
            "durable path only (runtime-backed / injected hook). "
            "Stub-only jobs return 409 stub_only. Cancel is not pause. "
            "iec-local same-job pause/held/resume stay omitted unless "
            "the hook supplies can_pause / can_resume / held "
            "(runtime tip d9b9948+ pause_limit). "
            "pause_signaled / resume_signaled surface when ctl returns "
            "them (runtime tip e2f41fd+) — not invented held; pause "
            "stays disabled without can_pause. "
            f"Operator/ctl: {CTL_PAUSE_RESUME}"
        ),
        "cancel_note": (
            "Cancel ends a live run (canceled), including paused or held. "
            "Cancel is not pause. Durable cancel is ctl-mediated "
            "(PANORAMIX_CTL_HTTP preferred or PANORAMIX_RUNTIME_ROOT). "
            "Pause/resume is durable-path only. "
            "Stub-backed cancel is local; runtime-backed cancel signals "
            "the hook first (same honesty as pause), then marks the guest "
            "job canceled if still live or follows hook.status() when ctl "
            "already reports terminal. Cancel of an already-canceled job "
            "is 409 already_canceled (runtime tip d9b9948 ctl cancel is "
            "idempotent). Succeeded/failed cancel stays 409 already_terminal. "
            "Fail-closed without hook (inert default). "
            "Cancel/fail does not auto-retry. "
            f"Operator/ctl: {CTL_CANCEL}"
        ),
        "terminal": (
            "Failed/canceled job resources expose a terminal summary "
            "(status + message + optional last events / stage / "
            "next_action / valuation / stage_name when the hook "
            "supplies them). Omit when missing. "
            "Not a SIEM; not iec /v1/audit/events product."
        ),
        "recoverability": (
            "Failed/canceled jobs expose handoff + payload export for "
            "operator/ctl re-admit (payload bytes when known, including "
            "after a guest restart if history was persisted). "
            "When a durable hook is active (PANORAMIX_CTL_HTTP preferred "
            "or PANORAMIX_RUNTIME_ROOT), POST /v0/jobs/{id}/re-admit "
            "posts that handoff/payload through the same hook seam as a "
            "new admit (new job id). Fail-closed without hook or when "
            "handoff/payload is missing (no silent stub re-admit). "
            "Cancel/fail does not auto-retry. "
            "No resume-from-failed. Pause/resume remains durable-only "
            f"(stub 409 stub_only). Operator/ctl: {CTL_ADMIT}"
        ),
        "re_admit": "POST /v0/jobs/{id}/re-admit",
    },
    "ui": "/",
}

_JOB_RE = re.compile(r"^/v0/jobs/([^/]+)$")
_CANCEL_RE = re.compile(r"^/v0/jobs/([^/]+)/cancel$")
_PAUSE_RE = re.compile(r"^/v0/jobs/([^/]+)/pause$")
_RESUME_RE = re.compile(r"^/v0/jobs/([^/]+)/resume$")
_HANDOFF_RE = re.compile(r"^/v0/jobs/([^/]+)/handoff$")
_PAYLOAD_RE = re.compile(r"^/v0/jobs/([^/]+)/payload$")
_PROGRESS_RE = re.compile(r"^/v0/jobs/([^/]+)/progress$")
_EVENTS_RE = re.compile(r"^/v0/jobs/([^/]+)/events$")
_COMPARE_RE = re.compile(r"^/v0/jobs/([^/]+)/compare$")
_READMIT_RE = re.compile(r"^/v0/jobs/([^/]+)/re-admit$")


def parse_job_status_filter(
    query: dict[str, list[str]],
) -> frozenset[str] | None:
    """Parse ``?status=`` into known WORK_STATUSES. None means unfiltered."""
    raw: list[str] = []
    for item in query.get("status", []):
        raw.extend(part.strip() for part in item.split(","))
    wanted = [value for value in raw if value]
    if not wanted:
        return None
    unknown = [value for value in wanted if value not in WORK_STATUSES]
    if unknown:
        raise InvalidStatus(unknown[0])
    return frozenset(wanted)


@dataclass
class HttpResponse:
    status: int
    body: bytes
    content_type: str = "application/json"
    headers: dict[str, str] | None = None


def _json_response(status: int, payload: Any, extra_headers: dict[str, str] | None = None) -> HttpResponse:
    body = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    return HttpResponse(status=status, body=body, content_type="application/json", headers=extra_headers)


def _html_response(html: str) -> HttpResponse:
    body = html.encode("utf-8")
    return HttpResponse(status=200, body=body, content_type="text/html; charset=utf-8")


def _read_json_object(body: bytes) -> dict[str, Any]:
    if not body or not body.strip():
        raise SosError("invalid_json", detail="request body is required")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SosError("invalid_json", detail=str(exc)) from exc
    if not isinstance(payload, dict):
        raise SosError("invalid_json", detail="body must be a JSON object")
    return payload


class SosApp:
    """Dispatch table used by the HTTP handler and by tests (no sockets)."""

    def __init__(self, store: JobStore | None = None) -> None:
        self.store = store or JobStore(
            runtime_hook=resolve_runtime_hook(),
            persist_dir=jobs_dir_from_env(),
        )

    def handle(self, method: str, path: str, body: bytes = b"") -> HttpResponse:
        method = method.upper()
        split = urlsplit(path)
        path = split.path or "/"
        query = parse_qs(split.query, keep_blank_values=False)
        try:
            return self._route(method, path, body, query)
        except SosError as err:
            return _json_response(err.http_status, err.to_dict())

    def _route(
        self,
        method: str,
        path: str,
        body: bytes,
        query: dict[str, list[str]] | None = None,
    ) -> HttpResponse:
        if path == "/health":
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, HEALTH_PAYLOAD)
        if path == "/v0/info":
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, self._info_payload())
        if path in ("/", "/ui"):
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _html_response(OPERATOR_HTML)
        if path == "/v0/jobs":
            if method == "GET":
                statuses = parse_job_status_filter(query or {})
                payload: dict[str, Any] = {
                    "jobs": [
                        self.store.public_dict(j)
                        for j in self.store.list(statuses=statuses)
                    ]
                }
                if statuses is not None:
                    payload["status"] = [name for name in WORK_STATUSES if name in statuses]
                return _json_response(200, payload)
            if method == "POST":
                return self._create_job(body)
            return _json_response(405, {"error": "method_not_allowed", "path": path})
        cancel = _CANCEL_RE.match(path)
        if cancel:
            if method != "POST":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            job = self.store.cancel(cancel.group(1))
            return _json_response(200, self.store.public_dict(job))
        pause = _PAUSE_RE.match(path)
        if pause:
            if method != "POST":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            job = self.store.pause(pause.group(1))
            return _json_response(200, self.store.public_dict(job))
        resume = _RESUME_RE.match(path)
        if resume:
            if method != "POST":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            job = self.store.resume(resume.group(1))
            return _json_response(200, self.store.public_dict(job))
        readmit = _READMIT_RE.match(path)
        if readmit:
            if method != "POST":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            job = self.store.readmit(readmit.group(1))
            return _json_response(
                201,
                self.store.public_dict(job),
                extra_headers={"Location": f"/v0/jobs/{job.id}"},
            )
        handoff = _HANDOFF_RE.match(path)
        if handoff:
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, self.store.handoff(handoff.group(1)))
        payload = _PAYLOAD_RE.match(path)
        if payload:
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, self.store.payload(payload.group(1)))
        progress = _PROGRESS_RE.match(path)
        if progress:
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, self.store.progress(progress.group(1)))
        events = _EVENTS_RE.match(path)
        if events:
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return self._events_response(events.group(1), query or {})
        compare = _COMPARE_RE.match(path)
        if compare:
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, self.store.compare(compare.group(1)))
        job_match = _JOB_RE.match(path)
        if job_match:
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            job = self.store.get(job_match.group(1))
            return _json_response(200, self.store.public_dict(job))
        return _json_response(404, {"error": "not_found", "path": path})

    def _info_payload(self) -> dict[str, Any]:
        """Static product info plus an honest durable-hook badge.

        ``durable_path`` is true only when an opt-in lab adapter is
        hooked. Inert default does not pretend. Not guest→mesh ctl.
        """
        payload = json.loads(json.dumps(INFO_PAYLOAD))
        payload["jobs"]["durable_hook"] = describe_runtime_hook(
            self.store.runtime_hook
        )
        payload["jobs"]["history_persist"] = describe_history_persist(
            self.store.persist_dir
        )
        return payload

    def _events_response(
        self, job_id: str, query: dict[str, list[str]]
    ) -> HttpResponse:
        """JSON envelope or JSONL salvage. Filter by kind. Not a SIEM."""
        raw_kinds = list(query.get("kind") or []) + list(query.get("kinds") or [])
        kinds = parse_kind_filter(raw_kinds)
        fmt_raw = (query.get("format") or query.get("export") or [None])[0]
        try:
            fmt = parse_events_format(fmt_raw)
        except ValueError as exc:
            raise SosError(
                "invalid_format",
                format=str(exc),
                allowed=sorted((EVENTS_FORMAT_JSON, EVENTS_FORMAT_JSONL)),
                detail="events export format is json or jsonl",
            ) from exc
        download = (query.get("download") or [""])[0].lower() in {
            "1",
            "true",
            "yes",
            "download",
        }
        payload = self.store.events(job_id, kinds or None)
        honesty = {
            "X-Sos-Events-Note": EVENTS_EXPORT_NOTE,
            "X-Sos-Events-Source": str(payload.get("source") or "memory"),
        }
        if fmt == EVENTS_FORMAT_JSONL:
            body = events_to_jsonl(payload.get("events") or [])
            headers = {
                **honesty,
                "Content-Disposition": (
                    f'attachment; filename="{download_filename(job_id, fmt)}"'
                ),
            }
            return HttpResponse(
                status=200,
                body=body,
                content_type="application/x-ndjson",
                headers=headers,
            )
        headers = dict(honesty)
        if download:
            headers["Content-Disposition"] = (
                f'attachment; filename="{download_filename(job_id, EVENTS_FORMAT_JSON)}"'
            )
        return _json_response(200, payload, extra_headers=headers)

    def _create_job(self, body: bytes) -> HttpResponse:
        payload = _read_json_object(body)
        job = self.store.submit(payload)
        return _json_response(
            201,
            self.store.public_dict(job),
            extra_headers={"Location": f"/v0/jobs/{job.id}"},
        )


class SosServer(ThreadingHTTPServer):
    allow_reuse_address = True


def bind_handler(app: SosApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: object) -> None:
            print("%s - %s" % (self.address_string(), fmt % args), flush=True)

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

        def _dispatch(self, method: str) -> None:
            length_raw = self.headers.get("Content-Length") or "0"
            try:
                length = int(length_raw)
            except ValueError:
                self._write(_json_response(400, {"error": "invalid_json", "detail": "bad Content-Length"}))
                return
            if length < 0 or length > MAX_BODY:
                self._write(_json_response(413, {"error": "payload_too_large"}))
                return
            body = self.rfile.read(length) if length else b""
            self._write(app.handle(method, self.path, body))

        def _write(self, resp: HttpResponse) -> None:
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.content_type)
            self.send_header("Content-Length", str(len(resp.body)))
            self.send_header("Connection", "close")
            if resp.headers:
                for key, value in resp.headers.items():
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(resp.body)

    return Handler
