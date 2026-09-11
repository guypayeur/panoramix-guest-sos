"""In-guest job store and stub runner.

Emits WorkHandoff JSON (kind/class/payload_digest + status/id). Does
not call runtime.apply compute-work. Mesh is compute-job → sos
(worker calls Unit). In-process stub is the fallback; operator/ctl
admits the exported handoff. Pause/resume is durable-path only
(injected hook or opt-in lab adapter); stub jobs are refused.
Progress prefers hook.progress() path-slices when durable-backed.
Events prefer hook.events() JSONL when durable-backed. Historical
comparison uses list/get identity (in-process plus local lab files
when persisted). Default hook stays inert. Does not close #70.
Does not close #78.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sos.compare import compare_vs_priors
from sos.errors import AlreadyTerminal, IllegalTransition, JobNotFound, PayloadUnknown, StubOnly
from sos.handoff import ParsedSubmit, parse_submit, payload_export, HANDOFF_EXPORT_KEYS
from sos.persist import (
    RESTART_LOST_ERROR,
    RESTART_LOST_MESSAGE,
    job_to_record,
    load_recent_records,
    prepare_jobs_dir,
    record_to_job_kwargs,
    write_record,
)
from sos.handoff_vocab import (
    BACKED_RUNTIME,
    BACKED_STUB,
    CATALOG_CROSSCHECK_NOTE,
    CTL_ADMIT,
    DEFAULT_SLEEP_SECONDS,
    DEMO_ECHO,
    DEMO_RESERVE,
    DEMO_SLEEP,
    FAILED_OR_CANCELED,
    LAST_EVENTS_N,
    OWNERSHIP_NOTE,
    PATH_SLICE_OWNERS,
    RECOVERABILITY_NOTE,
    STATUS_CANCELED,
    STATUS_FAILED,
    STATUS_PAUSED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    TERMINAL,
    TERMINAL_NOTE,
    WORK_STATUSES,
    reserve_stage_names,
    short_digest,
)
from sos.runtime_hook import InertRuntimeHandoffHook, RuntimeHandoffHook

DEFAULT_STEP_SECONDS = 0.15
PROGRESS_SOURCE_STUB = "stub"
PROGRESS_SOURCE_DURABLE = "durable"
EVENTS_SOURCE_MEMORY = "memory"
EVENTS_SOURCE_DURABLE = "durable"
_PROGRESS_COUNTER_KEYS = (
    "stage",
    "stages_total",
    "stages_completed",
    "fraction",
    "inner_steps",
    "inner_steps_expected",
)
STUB_PROGRESS_NOTE = (
    "Stub stage metadata derived from job fields — "
    "not iec chunk progress or parallelism"
)
DURABLE_PROGRESS_NOTE = (
    "Durable reserve-temporal path-slices — "
    "not iec planner parallelism; not iec chunk progress"
)
MEMORY_EVENTS_NOTE = (
    "Process-memory event trail — not a regulatory audit product"
)
DURABLE_EVENTS_NOTE = (
    "Durable reserve-temporal JSONL trail — not a SIEM; "
    "not iec /v1/audit/events product"
)
INVESTIGATE_NOTE = (
    "Thinner investigate — catalog identity + static path-slice owners "
    "when hooked; not Slack; not a data-catalog product; not a SIEM"
)


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class Job:
    id: str
    kind: str
    resource_class: str
    payload_digest: str
    status: str
    created_at: str
    updated_at: str
    message: str | None = None
    error: str | None = None
    local: dict[str, Any] | None = None
    payload_bytes: bytes | None = field(default=None, repr=False)
    runtime_ref: dict[str, Any] | None = field(default=None, repr=False)
    events: list[dict[str, Any]] = field(default_factory=list)
    events_source: str | None = None
    events_durable: bool | None = None
    events_n: int | None = None

    def to_seam(self) -> dict[str, str]:
        """Runtime-aligned projection: id/kind/class/payload_digest/status."""
        return {
            "id": self.id,
            "kind": self.kind,
            "class": self.resource_class,
            "payload_digest": self.payload_digest,
            "status": self.status,
        }

    def to_handoff(self) -> dict[str, str]:
        """Ctl export: WorkHandoff guest shape only (no nested payload)."""
        seam = self.to_seam()
        return {key: seam[key] for key in HANDOFF_EXPORT_KEYS}

    def to_payload(self) -> dict[str, Any]:
        if self.payload_bytes is None:
            raise PayloadUnknown(self.id)
        return payload_export(self.payload_digest, self.payload_bytes)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            **self.to_seam(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message": self.message,
            "error": self.error,
            "local": dict(self.local) if self.local else None,
            "events": _copy_events(self.events),
            "pause_resume": _pause_resume_honest(self),
        }
        if self.events_source:
            payload["events_source"] = self.events_source
        if self.events_durable is not None:
            payload["events_durable"] = self.events_durable
        if self.events_n is not None:
            payload["events_n"] = self.events_n
        investigate = _investigate_payload(self, hooked=_pause_resume_honest(self))
        if investigate:
            payload["investigate"] = investigate
        terminal = _terminal_payload(self)
        if terminal:
            payload["terminal"] = terminal
        recoverability = _recoverability_payload(self)
        if recoverability:
            payload["recoverability"] = recoverability
        return payload

    def to_progress(self) -> dict[str, Any]:
        """Stub stage metadata only — not iec chunk progress / parallelism."""
        local = self.local or {}
        payload: dict[str, Any] = {
            "id": self.id,
            "status": self.status,
            "stage": local.get("stage"),
            "message": self.message,
            "backed": local.get("backed"),
            "pause_resume": _pause_resume_honest(self),
            "source": PROGRESS_SOURCE_STUB,
            "note": STUB_PROGRESS_NOTE,
        }
        stages_total = local.get("stages")
        if stages_total is not None:
            payload["stages_total"] = stages_total
        stage_index = local.get("stage_index")
        if stage_index is not None:
            payload["stage_index"] = stage_index
        _attach_investigate(payload, self, hooked=False)
        return payload

    def to_events(self) -> dict[str, Any]:
        """Process-memory trail, or durable overlay already applied on the snapshot."""
        if self.events_source == EVENTS_SOURCE_DURABLE:
            payload: dict[str, Any] = {
                "id": self.id,
                "events": _copy_events(self.events),
                "source": EVENTS_SOURCE_DURABLE,
                "note": DURABLE_EVENTS_NOTE,
                "events_durable": (
                    True if self.events_durable is None else self.events_durable
                ),
            }
            if self.events_n is not None:
                payload["events_n"] = self.events_n
            return payload
        return {
            "id": self.id,
            "events": _copy_events(self.events),
            "source": EVENTS_SOURCE_MEMORY,
            "note": MEMORY_EVENTS_NOTE,
        }


def _catalog_identity(job: Job) -> dict[str, Any] | None:
    """Name + short digest already on the job. Not a data-catalog product."""
    name = (job.local or {}).get("catalog")
    if not name:
        return None
    digest = job.payload_digest
    return {
        "name": name,
        "digest": digest,
        "digest_short": short_digest(digest),
        "note": CATALOG_CROSSCHECK_NOTE,
    }


def _ownership_tags() -> dict[str, Any]:
    """Static day-one labels for durable path-slices. Not Slack."""
    return {
        "tags": [
            {"slice": slice_name, "owner": owner}
            for slice_name, owner in PATH_SLICE_OWNERS
        ],
        "note": OWNERSHIP_NOTE,
    }


def _investigate_payload(job: Job, *, hooked: bool) -> dict[str, Any] | None:
    catalog = _catalog_identity(job)
    if catalog is None and not hooked:
        return None
    payload: dict[str, Any] = {"note": INVESTIGATE_NOTE}
    if catalog is not None:
        payload["catalog"] = catalog
    if hooked:
        payload["ownership"] = _ownership_tags()
    return payload


def _attach_investigate(payload: dict[str, Any], job: Job, *, hooked: bool) -> None:
    investigate = _investigate_payload(job, hooked=hooked)
    if investigate:
        payload["investigate"] = investigate


def _last_events(
    events: list[dict[str, Any]] | None, n: int = LAST_EVENTS_N
) -> list[dict[str, Any]]:
    if not events:
        return []
    return _copy_events(events[-n:])


def _terminal_payload(job: Job) -> dict[str, Any] | None:
    """Failed/canceled summary. Honesty: not SIEM / not iec audit product."""
    if job.status not in FAILED_OR_CANCELED:
        return None
    local = job.local or {}
    payload: dict[str, Any] = {
        "status": job.status,
        "message": job.message,
        "note": TERMINAL_NOTE,
        "events_source": job.events_source or EVENTS_SOURCE_MEMORY,
    }
    if job.error:
        payload["error"] = job.error
    stage = local.get("stage")
    if stage:
        payload["stage"] = stage
        if local.get("stage_index") is not None:
            payload["stage_index"] = local["stage_index"]
    last = _last_events(job.events)
    if last:
        payload["last_events"] = last
    return payload


def _recoverability_payload(job: Job) -> dict[str, Any] | None:
    """Handoff/payload re-admit. Cancel/fail does not auto-retry."""
    if job.status not in FAILED_OR_CANCELED:
        return None
    return {
        "auto_retry": False,
        "resume_from_failed": False,
        "handoff": f"GET /v0/jobs/{job.id}/handoff",
        "payload": f"GET /v0/jobs/{job.id}/payload",
        "payload_known": job.payload_bytes is not None,
        "re_admit": CTL_ADMIT,
        "note": RECOVERABILITY_NOTE,
    }


def _copy_local(local: dict[str, Any] | None) -> dict[str, Any] | None:
    return dict(local) if local else None


def _copy_events(events: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [dict(item) for item in events] if events else []


def _pause_resume_honest(job: Job) -> bool:
    """True only when a runtime ref / runtime-backed path exists."""
    backed = (job.local or {}).get("backed")
    return backed == BACKED_RUNTIME or job.runtime_ref is not None


def _copy_progress_counters(src: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in _PROGRESS_COUNTER_KEYS:
        if key in src and src[key] is not None:
            out[key] = src[key]
    return out


def _has_progress_counters(data: dict[str, Any]) -> bool:
    nested = data.get("progress")
    blobs = [data]
    if isinstance(nested, dict):
        blobs.append(nested)
    return any(key in blob for blob in blobs for key in _PROGRESS_COUNTER_KEYS)


def _progress_from_durable(job: Job, durable: dict[str, Any]) -> dict[str, Any]:
    """Prefer hook counters. Honesty: path-slices, not iec planner parallelism."""
    nested_raw = durable.get("progress")
    nested = (
        _copy_progress_counters(nested_raw) if isinstance(nested_raw, dict) else {}
    )
    top = _copy_progress_counters(durable)
    payload: dict[str, Any] = {
        "id": job.id,
        "status": job.status,
        "message": job.message,
        "backed": (job.local or {}).get("backed"),
        "pause_resume": _pause_resume_honest(job),
        "source": PROGRESS_SOURCE_DURABLE,
        "note": DURABLE_PROGRESS_NOTE,
    }
    for key in _PROGRESS_COUNTER_KEYS:
        if key in top:
            payload[key] = top[key]
        elif key in nested:
            payload[key] = nested[key]
    if nested:
        payload["progress"] = nested
    elif isinstance(nested_raw, dict):
        payload["progress"] = {}
    _attach_investigate(payload, job, hooked=True)
    return payload


def _normalize_event(item: Any) -> dict[str, Any] | None:
    """Keep JSONL-style records readable: at least ``event`` + copied fields."""
    if not isinstance(item, dict):
        return None
    out = dict(item)
    if "event" not in out:
        if out.get("type") is not None:
            out["event"] = str(out["type"])
        elif out.get("kind") is not None:
            out["event"] = str(out["kind"])
        else:
            return None
    return out


def _events_list_from_durable(
    durable: dict[str, Any] | list[Any],
) -> list[dict[str, Any]]:
    if isinstance(durable, list):
        raw = durable
    else:
        raw = durable.get("events") or []
        if not isinstance(raw, list):
            raw = []
    out: list[dict[str, Any]] = []
    for item in raw:
        norm = _normalize_event(item)
        if norm is not None:
            out.append(norm)
    return out


def _apply_durable_events(
    job: Job, durable: dict[str, Any] | list[Any]
) -> Job:
    """Overlay JSONL-style trail on a snapshot. Honesty: local durable, not SIEM."""
    trail = _events_list_from_durable(durable)
    job.events = trail
    job.events_source = EVENTS_SOURCE_DURABLE
    meta = durable if isinstance(durable, dict) else {}
    if "events_durable" in meta:
        job.events_durable = bool(meta["events_durable"])
    elif "durable" in meta:
        job.events_durable = bool(meta["durable"])
    else:
        job.events_durable = True
    if meta.get("events_n") is not None:
        job.events_n = int(meta["events_n"])
    elif meta.get("n") is not None:
        job.events_n = int(meta["n"])
    else:
        job.events_n = len(trail)
    return job


def _has_durable_events(reported: Any) -> bool:
    if isinstance(reported, list):
        return True
    if not isinstance(reported, dict) or not reported:
        return False
    if "events" in reported:
        return True
    if reported.get("events_durable") or reported.get("durable"):
        return True
    return False


@dataclass
class JobStore:
    """Thread-safe jobs. Optional local lab files survive guest restart."""

    step_seconds: float = DEFAULT_STEP_SECONDS
    runtime_hook: RuntimeHandoffHook = field(default_factory=InertRuntimeHandoffHook)
    persist_dir: Path | str | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _jobs: dict[str, Job] = field(default_factory=dict, repr=False)
    _cancel: dict[str, threading.Event] = field(default_factory=dict, repr=False)
    _clock: Callable[[], str] = field(default=utcnow, repr=False)

    def __post_init__(self) -> None:
        prepared = prepare_jobs_dir(self.persist_dir)
        self.persist_dir = prepared
        if prepared is not None:
            self._reload()

    def _persist_locked(self, job: Job) -> None:
        """Caller holds ``_lock``. Fail-closed: write errors are ignored."""
        if self.persist_dir is None:
            return
        write_record(self.persist_dir, job_to_record(job))

    def _reload(self) -> None:
        """Load recent records. Non-terminal stub work is not resumed."""
        if self.persist_dir is None:
            return
        records = load_recent_records(self.persist_dir)
        records.sort(
            key=lambda item: (
                str(item.get("created_at") or ""),
                str(item.get("id") or ""),
            )
        )
        with self._lock:
            for record in records:
                kwargs = record_to_job_kwargs(record)
                if kwargs is None:
                    continue
                job_id = kwargs["id"]
                if job_id in self._jobs:
                    continue
                job = Job(**kwargs)
                if job.status not in TERMINAL:
                    job.status = STATUS_FAILED
                    job.updated_at = self._clock()
                    job.message = RESTART_LOST_MESSAGE
                    job.error = RESTART_LOST_ERROR
                    self._append_event_locked(job, "failed", RESTART_LOST_MESSAGE)
                self._jobs[job.id] = job
                self._persist_locked(job)

    def submit(self, body: dict[str, Any]) -> Job:
        parsed: ParsedSubmit = parse_submit(body)
        job_id = str(uuid.uuid4())
        now = self._clock()
        local = _copy_local(parsed.local)
        job = Job(
            id=job_id,
            kind=parsed.kind,
            resource_class=parsed.resource_class,
            payload_digest=parsed.payload_digest,
            status=STATUS_QUEUED,
            created_at=now,
            updated_at=now,
            local=local,
            payload_bytes=parsed.payload_bytes,
        )
        cancel = threading.Event()
        demo = (local or {}).get("demo")
        submit_detail = f"kind={parsed.kind} class={parsed.resource_class}"
        if demo:
            submit_detail += f" demo={demo}"
        with self._lock:
            self._jobs[job_id] = job
            self._cancel[job_id] = cancel
            self._append_event_locked(job, "submitted", submit_detail)
            self._persist_locked(job)

        runtime_ref = self._try_admit(job)
        if runtime_ref is not None:
            with self._lock:
                live = self._jobs.get(job_id)
                if live is not None and live.status not in TERMINAL:
                    live.runtime_ref = runtime_ref
                    live.message = (
                        "admitted via runtime hook (operator/ctl; no local stub)"
                    )
                    live.updated_at = self._clock()
                    merged = dict(live.local) if live.local else {}
                    merged["backed"] = BACKED_RUNTIME
                    live.local = merged
                    self._append_event_locked(live, "backed", BACKED_RUNTIME)
                    self._persist_locked(live)
            return self.get(job_id)

        with self._lock:
            live = self._jobs.get(job_id)
            if live is not None:
                merged = dict(live.local) if live.local else {}
                merged["backed"] = BACKED_STUB
                live.local = merged
                self._append_event_locked(live, "backed", BACKED_STUB)
                self._persist_locked(live)
        thread = threading.Thread(
            target=self._run,
            args=(job_id, cancel),
            name=f"sos-job-{job_id[:8]}",
            daemon=True,
        )
        thread.start()
        return self.get(job_id)

    def _try_admit(self, job: Job) -> dict[str, Any] | None:
        try:
            return self.runtime_hook.admit(job.to_handoff(), job.payload_bytes)
        except Exception:
            return None

    def get(self, job_id: str) -> Job:
        self._refresh_runtime_status(job_id)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFound(job_id)
            snap = self._snapshot(job)
        if self._is_durable(snap):
            durable = self._try_runtime_events(job_id, snap.runtime_ref)
            if durable is not None:
                return _apply_durable_events(snap, durable)
        return snap

    def handoff(self, job_id: str) -> dict[str, str]:
        return self.get(job_id).to_handoff()

    def payload(self, job_id: str) -> dict[str, Any]:
        return self.get(job_id).to_payload()

    def progress(self, job_id: str) -> dict[str, Any]:
        """Prefer dedicated hook.progress(); stub fields are fallback only.

        ``get()`` already refreshes lifecycle via ``status()``. Stage
        counters are not scraped from status strings.
        """
        job = self.get(job_id)
        if self._is_durable(job):
            durable = self._try_runtime_progress(job_id, job.runtime_ref)
            if durable is not None:
                return _progress_from_durable(job, durable)
        return job.to_progress()

    def events(self, job_id: str) -> dict[str, Any]:
        """Prefer dedicated hook.events(); process-memory trail is fallback only.

        ``get()`` already overlays durable JSONL onto the job snapshot when
        the hook returns events.
        """
        return self.get(job_id).to_events()

    def compare(self, job_id: str) -> dict[str, Any]:
        """Vs recent same-catalog or same-kind/class jobs in guest history.

        Reuses ``list()`` / ``get()`` identity (in-process plus reloaded
        lab files). No guest→ctl channel. Does not invent typical/ETA
        without succeeded prior walls.
        """
        current = self.get(job_id)
        peers = [job for job in self.list() if job.id != job_id]
        return compare_vs_priors(current, peers, now=self._clock())

    def list(self) -> list[Job]:
        with self._lock:
            ids = list(self._jobs.keys())
        jobs = [self.get(job_id) for job_id in ids]
        jobs.reverse()  # insertion order, newest first
        return jobs

    def cancel(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFound(job_id)
            if job.status in TERMINAL:
                raise AlreadyTerminal(job_id, job.status)
            runtime_ref = job.runtime_ref
        self._try_runtime_cancel(job_id, runtime_ref)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFound(job_id)
            if job.status in TERMINAL:
                raise AlreadyTerminal(job_id, job.status)
            now = self._clock()
            job.status = STATUS_CANCELED
            job.updated_at = now
            job.message = "canceled by operator"
            self._append_event_locked(job, "canceled", "canceled by operator")
            self._persist_locked(job)
            event = self._cancel.get(job_id)
            if event is not None:
                event.set()
            return self._snapshot(job)

    def pause(self, job_id: str) -> Job:
        return self._pause_or_resume(job_id, "pause")

    def resume(self, job_id: str) -> Job:
        return self._pause_or_resume(job_id, "resume")

    def _is_durable(self, job: Job) -> bool:
        return _pause_resume_honest(job)

    def _pause_or_resume(self, job_id: str, action: str) -> Job:
        wanted = STATUS_RUNNING if action == "pause" else STATUS_PAUSED
        next_status = STATUS_PAUSED if action == "pause" else STATUS_RUNNING
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFound(job_id)
            if not self._is_durable(job):
                raise StubOnly(job_id, action)
            if job.status in TERMINAL:
                raise AlreadyTerminal(job_id, job.status)
            if job.status != wanted:
                raise IllegalTransition(job_id, job.status, action)
            runtime_ref = job.runtime_ref
        signaled = self._try_runtime_signal(action, job_id, runtime_ref)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFound(job_id)
            if not self._is_durable(job):
                raise StubOnly(job_id, action)
            if job.status in TERMINAL:
                raise AlreadyTerminal(job_id, job.status)
            if job.status != wanted:
                raise IllegalTransition(job_id, job.status, action)
            if not signaled and job.runtime_ref is None:
                raise StubOnly(job_id, action)
            now = self._clock()
            job.status = next_status
            job.updated_at = now
            detail = f"{next_status} via runtime hook"
            job.message = detail
            self._append_event_locked(job, next_status, detail)
            self._persist_locked(job)
            return self._snapshot(job)

    def _append_event_locked(self, job: Job, event: str, detail: str) -> None:
        """Caller holds ``_lock``. Process-local trail only."""
        trail = list(job.events)
        trail.append({"ts": self._clock(), "event": event, "detail": detail})
        job.events = trail

    def _try_runtime_cancel(
        self, job_id: str, runtime_ref: dict[str, Any] | None
    ) -> bool:
        return self._try_runtime_signal("cancel", job_id, runtime_ref)

    def _try_runtime_signal(
        self,
        action: str,
        job_id: str,
        runtime_ref: dict[str, Any] | None,
    ) -> bool:
        method = getattr(self.runtime_hook, action, None)
        if not callable(method):
            return False
        try:
            return bool(method(job_id, runtime_ref))
        except Exception:
            return False

    def _try_runtime_progress(
        self, job_id: str, runtime_ref: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        method = getattr(self.runtime_hook, "progress", None)
        if not callable(method):
            return None
        try:
            reported = method(job_id, runtime_ref)
        except Exception:
            return None
        if not isinstance(reported, dict) or not reported:
            return None
        if not _has_progress_counters(reported):
            return None
        return reported

    def _try_runtime_events(
        self, job_id: str, runtime_ref: dict[str, Any] | None
    ) -> dict[str, Any] | list[Any] | None:
        method = getattr(self.runtime_hook, "events", None)
        if not callable(method):
            return None
        try:
            reported = method(job_id, runtime_ref)
        except Exception:
            return None
        if not _has_durable_events(reported):
            return None
        return reported

    def _refresh_runtime_status(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.runtime_ref is None or job.status in TERMINAL:
                return
            runtime_ref = job.runtime_ref
        try:
            reported = self.runtime_hook.status(job_id, runtime_ref)
        except Exception:
            return
        if not reported or reported not in WORK_STATUSES:
            return
        if reported == job.status:
            return
        self._advance(
            job_id,
            reported,
            message="status via runtime hook",
        )

    def _snapshot(self, job: Job) -> Job:
        return Job(
            id=job.id,
            kind=job.kind,
            resource_class=job.resource_class,
            payload_digest=job.payload_digest,
            status=job.status,
            created_at=job.created_at,
            updated_at=job.updated_at,
            message=job.message,
            error=job.error,
            local=_copy_local(job.local),
            payload_bytes=job.payload_bytes,
            runtime_ref=dict(job.runtime_ref) if job.runtime_ref else None,
            events=_copy_events(job.events),
            events_source=job.events_source,
            events_durable=job.events_durable,
            events_n=job.events_n,
        )

    def _advance(
        self,
        job_id: str,
        status: str,
        *,
        message: str | None = None,
        error: str | None = None,
        local_update: dict[str, Any] | None = None,
    ) -> bool:
        """Move a live job to `status`. False if it already terminated (e.g. cancel)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in TERMINAL:
                return False
            previous_status = job.status
            previous_stage = (job.local or {}).get("stage")
            job.status = status
            job.updated_at = self._clock()
            if message is not None:
                job.message = message
            if error is not None:
                job.error = error
            if local_update:
                merged = dict(job.local) if job.local else {}
                merged.update(local_update)
                job.local = merged
            stage = (job.local or {}).get("stage")
            if stage and stage != previous_stage:
                index = (job.local or {}).get("stage_index")
                total = (job.local or {}).get("stages")
                detail = str(stage)
                if index is not None and total is not None:
                    detail = f"{detail} ({index}/{total})"
                self._append_event_locked(job, "stage", detail)
            if status != previous_status:
                if status in TERMINAL:
                    self._append_event_locked(job, status, message or status)
                elif status == STATUS_RUNNING:
                    self._append_event_locked(job, "running", message or "running")
                elif status == STATUS_PAUSED:
                    self._append_event_locked(job, "paused", message or "paused")
            self._persist_locked(job)
            return True

    def _wait(self, job_id: str, cancel: threading.Event, seconds: float) -> bool:
        """Sleep up to `seconds`. True if the wait finished and the job is still live."""
        remaining = max(0.0, float(seconds))
        slice_s = 0.05
        while remaining > 0:
            if cancel.is_set():
                return False
            wait = slice_s if remaining > slice_s else remaining
            if cancel.wait(timeout=wait):
                return False
            remaining -= wait
        with self._lock:
            job = self._jobs.get(job_id)
            return job is not None and job.status not in TERMINAL

    def _run(self, job_id: str, cancel: threading.Event) -> None:
        try:
            if not self._wait(job_id, cancel, self.step_seconds):
                return
            if not self._advance(job_id, STATUS_RUNNING, message="running locally"):
                return
            job = self.get(job_id)
            local = job.local or {}
            demo = local.get("demo")
            if demo == DEMO_SLEEP:
                seconds = float(local.get("seconds", DEFAULT_SLEEP_SECONDS))
                if not self._wait(job_id, cancel, seconds):
                    return
                self._advance(job_id, STATUS_SUCCEEDED, message=f"slept {seconds:g}s")
                return
            if demo == DEMO_ECHO:
                if not self._wait(job_id, cancel, self.step_seconds):
                    return
                raw = local.get("message", "ok")
                echoed = raw if isinstance(raw, str) else str(raw)
                self._advance(job_id, STATUS_SUCCEEDED, message=echoed)
                return
            if demo == DEMO_RESERVE:
                self._run_reserve(job_id, cancel, local)
                return
            if not self._wait(job_id, cancel, self.step_seconds):
                return
            self._advance(
                job_id,
                STATUS_SUCCEEDED,
                message="opaque work recorded (local stub; no engine)",
            )
        except Exception as exc:  # noqa: BLE001 — stub runner; surface as job failure
            self._advance(job_id, STATUS_FAILED, error=str(exc), message="stub runner failed")

    def _run_reserve(self, job_id: str, cancel: threading.Event, local: dict[str, Any]) -> None:
        """Walk named stub stages so cancel mid-flight is visible. No engines, no math."""
        stages = int(local.get("stages") or 3)
        seconds = float(local.get("seconds") or 0.0)
        names = reserve_stage_names(stages)
        per = seconds / stages if stages else 0.0
        gpu_label = local.get("class") == "gpu"
        for index, name in enumerate(names, start=1):
            note = "UX seed stub; no IFRS17 math"
            if gpu_label:
                note += "; class=gpu is a label only (no GPU kernels)"
            message = f"stage {index}/{stages}: {name} ({note})"
            if not self._advance(
                job_id,
                STATUS_RUNNING,
                message=message,
                local_update={"stage": name, "stage_index": index},
            ):
                return
            if not self._wait(job_id, cancel, per):
                return
        done = "reserve-shaped stub finished (UX seed only; no IFRS17 math"
        if gpu_label:
            done += "; class=gpu is a label only (no GPU kernels)"
        done += ")"
        self._advance(job_id, STATUS_SUCCEEDED, message=done)
