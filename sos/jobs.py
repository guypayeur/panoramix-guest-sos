"""In-guest job store and stub runner.

Process-local only. Demo kinds run on a background thread with no external
compute. Real engines are selected later by panoramix-runtime bindings
(runtime#70) — this module has no engine URLs, addresses, or schemes.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

KIND_ECHO = "sos.demo.echo"
KIND_SLEEP = "sos.demo.sleep"
KNOWN_KINDS = (KIND_ECHO, KIND_SLEEP)

STATUSES = (
    "accepted",
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled",
)
TERMINAL = frozenset({"succeeded", "failed", "cancelled"})

DEFAULT_SLEEP_SECONDS = 2.0
MAX_SLEEP_SECONDS = 30.0
DEFAULT_STEP_SECONDS = 0.15


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class SosError(Exception):
    """Domain error with a stable JSON `error` code."""

    http_status = 400

    def __init__(self, error: str, **fields: Any) -> None:
        self.error = error
        self.fields = fields
        super().__init__(error)

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.error, **self.fields}


class UnknownKind(SosError):
    def __init__(self, kind: str) -> None:
        super().__init__("unknown_kind", kind=kind, allowed=list(KNOWN_KINDS))


class InvalidSpec(SosError):
    def __init__(self, detail: str) -> None:
        super().__init__("invalid_spec", detail=detail)


class JobNotFound(SosError):
    http_status = 404

    def __init__(self, job_id: str) -> None:
        super().__init__("not_found", id=job_id)


class AlreadyTerminal(SosError):
    http_status = 409

    def __init__(self, job_id: str, status: str) -> None:
        super().__init__("already_terminal", id=job_id, status=status)


@dataclass
class Job:
    id: str
    kind: str
    status: str
    created_at: str
    updated_at: str
    spec: dict[str, Any]
    message: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "spec": self.spec,
            "message": self.message,
            "error": self.error,
        }


def _copy_spec(spec: dict[str, Any]) -> dict[str, Any]:
    return dict(spec)


def validate_kind_spec(kind: str, spec: dict[str, Any]) -> None:
    if kind not in KNOWN_KINDS:
        raise UnknownKind(kind)
    if kind == KIND_SLEEP:
        seconds = spec.get("seconds", DEFAULT_SLEEP_SECONDS)
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            raise InvalidSpec("spec.seconds must be a non-negative number")
        if seconds < 0:
            raise InvalidSpec("spec.seconds must be a non-negative number")
        if seconds > MAX_SLEEP_SECONDS:
            raise InvalidSpec(f"spec.seconds must be <= {MAX_SLEEP_SECONDS}")


@dataclass
class JobStore:
    """Thread-safe in-memory jobs. One process; gone on restart."""

    step_seconds: float = DEFAULT_STEP_SECONDS
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _jobs: dict[str, Job] = field(default_factory=dict, repr=False)
    _cancel: dict[str, threading.Event] = field(default_factory=dict, repr=False)
    _clock: Callable[[], str] = field(default=utcnow, repr=False)

    def submit(self, kind: str, spec: dict[str, Any]) -> Job:
        if not isinstance(kind, str) or not kind.strip():
            raise SosError("invalid_kind", detail="kind must be a non-empty string")
        if not isinstance(spec, dict):
            raise InvalidSpec("spec must be a JSON object")
        spec = _copy_spec(spec)
        validate_kind_spec(kind, spec)
        job_id = str(uuid.uuid4())
        now = self._clock()
        job = Job(
            id=job_id,
            kind=kind,
            status="accepted",
            created_at=now,
            updated_at=now,
            spec=spec,
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
            job.status = "cancelled"
            job.updated_at = self._clock()
            job.message = "cancelled by operator"
            event = self._cancel.get(job_id)
            if event is not None:
                event.set()
            return self._snapshot(job)

    def _snapshot(self, job: Job) -> Job:
        return Job(
            id=job.id,
            kind=job.kind,
            status=job.status,
            created_at=job.created_at,
            updated_at=job.updated_at,
            spec=_copy_spec(job.spec),
            message=job.message,
            error=job.error,
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
            if not self._advance(job_id, "queued", message="queued locally"):
                return
            if not self._wait(job_id, cancel, self.step_seconds):
                return
            if not self._advance(job_id, "running", message="running locally"):
                return
            job = self.get(job_id)
            if job.kind == KIND_SLEEP:
                seconds = float(job.spec.get("seconds", DEFAULT_SLEEP_SECONDS))
                if not self._wait(job_id, cancel, seconds):
                    return
                self._advance(job_id, "succeeded", message=f"slept {seconds:g}s")
                return
            # sos.demo.echo
            if not self._wait(job_id, cancel, self.step_seconds):
                return
            raw = job.spec.get("message", "ok")
            echoed = raw if isinstance(raw, str) else str(raw)
            self._advance(job_id, "succeeded", message=echoed)
        except Exception as exc:  # noqa: BLE001 — stub runner; surface as job failure
            self._advance(job_id, "failed", error=str(exc), message="stub runner failed")
