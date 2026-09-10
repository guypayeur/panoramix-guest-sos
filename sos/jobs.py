"""In-guest job store and stub runner.

Process-local only. Opaque handoff is kind/class/payload_digest (runtime#73,
#70 Slice B). Local echo/sleep is a demo shortcut that synthesizes that shape.
Real engines are selected later by panoramix-runtime bindings — this module
has no engine URLs, addresses, or schemes. Does not close #70.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from sos.errors import AlreadyTerminal, JobNotFound
from sos.handoff import parse_submit
from sos.handoff_vocab import (
    DEFAULT_SLEEP_SECONDS,
    DEMO_ECHO,
    DEMO_SLEEP,
    STATUS_CANCELED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    TERMINAL,
)

DEFAULT_STEP_SECONDS = 0.15


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

    def to_seam(self) -> dict[str, str]:
        """Runtime-aligned projection: id/kind/class/payload_digest/status."""
        return {
            "id": self.id,
            "kind": self.kind,
            "class": self.resource_class,
            "payload_digest": self.payload_digest,
            "status": self.status,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.to_seam(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message": self.message,
            "error": self.error,
            "local": dict(self.local) if self.local else None,
        }


def _copy_local(local: dict[str, Any] | None) -> dict[str, Any] | None:
    return dict(local) if local else None


@dataclass
class JobStore:
    """Thread-safe in-memory jobs. One process; gone on restart."""

    step_seconds: float = DEFAULT_STEP_SECONDS
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _jobs: dict[str, Job] = field(default_factory=dict, repr=False)
    _cancel: dict[str, threading.Event] = field(default_factory=dict, repr=False)
    _clock: Callable[[], str] = field(default=utcnow, repr=False)

    def submit(self, body: dict[str, Any]) -> Job:
        kind, resource_class, payload_digest, local = parse_submit(body)
        job_id = str(uuid.uuid4())
        now = self._clock()
        job = Job(
            id=job_id,
            kind=kind,
            resource_class=resource_class,
            payload_digest=payload_digest,
            status=STATUS_QUEUED,
            created_at=now,
            updated_at=now,
            local=_copy_local(local),
        )
        cancel = threading.Event()
        with self._lock:
            self._jobs[job_id] = job
            self._cancel[job_id] = cancel
        thread = threading.Thread(
            target=self._run,
            args=(job_id, cancel),
            name=f"sos-job-{job_id[:8]}",
            daemon=True,
        )
        thread.start()
        return self.get(job_id)

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFound(job_id)
            return self._snapshot(job)

    def list(self) -> list[Job]:
        with self._lock:
            jobs = [self._snapshot(j) for j in self._jobs.values()]
        jobs.reverse()  # insertion order, newest first
        return jobs

    def cancel(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFound(job_id)
            if job.status in TERMINAL:
                raise AlreadyTerminal(job_id, job.status)
            job.status = STATUS_CANCELED
            job.updated_at = self._clock()
            job.message = "canceled by operator"
            event = self._cancel.get(job_id)
            if event is not None:
                event.set()
            return self._snapshot(job)

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
        )

    def _advance(self, job_id: str, status: str, *, message: str | None = None, error: str | None = None) -> bool:
        """Move a live job to `status`. False if it already terminated (e.g. cancel)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in TERMINAL:
                return False
            job.status = status
            job.updated_at = self._clock()
            if message is not None:
                job.message = message
            if error is not None:
                job.error = error
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
            if not self._wait(job_id, cancel, self.step_seconds):
                return
            self._advance(
                job_id,
                STATUS_SUCCEEDED,
                message="opaque work recorded (local stub; no engine)",
            )
        except Exception as exc:  # noqa: BLE001 — stub runner; surface as job failure
            self._advance(job_id, STATUS_FAILED, error=str(exc), message="stub runner failed")
