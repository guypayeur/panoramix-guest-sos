"""In-guest job store and stub runner.

Process-local only. Opaque handoff is kind/class/payload_digest
(runtime/compute_work.py on panoramix-runtime main, #70 Slice B). Local
echo/sleep/reserve is a demo shortcut that synthesizes that shape.
Reserve payload bytes match runtime.reserve.payload_for / digest_for
(PR #84 catalogs). Guest emits handoff JSON only — never runtime.apply.

When no runtime admit is configured (the default inert hook), the
in-process stub remains the fallback. Operator/ctl GETs /handoff +
/payload and admits to runtime compute; mesh is compute-job → sos.
Does not close #70.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from sos.errors import AlreadyTerminal, JobNotFound, PayloadUnknown
from sos.handoff import ParsedSubmit, parse_submit, payload_export, HANDOFF_EXPORT_KEYS
from sos.handoff_vocab import (
    BACKED_RUNTIME,
    BACKED_STUB,
    DEFAULT_SLEEP_SECONDS,
    DEMO_ECHO,
    DEMO_RESERVE,
    DEMO_SLEEP,
    STATUS_CANCELED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    TERMINAL,
    WORK_STATUSES,
    reserve_stage_names,
)
from sos.runtime_hook import InertRuntimeHandoffHook, RuntimeHandoffHook

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
    payload_bytes: bytes | None = field(default=None, repr=False)
    runtime_ref: dict[str, Any] | None = field(default=None, repr=False)

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
    runtime_hook: RuntimeHandoffHook = field(default_factory=InertRuntimeHandoffHook)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _jobs: dict[str, Job] = field(default_factory=dict, repr=False)
    _cancel: dict[str, threading.Event] = field(default_factory=dict, repr=False)
    _clock: Callable[[], str] = field(default=utcnow, repr=False)

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
        with self._lock:
            self._jobs[job_id] = job
            self._cancel[job_id] = cancel

        runtime_ref = self._try_admit(job)
        if runtime_ref is not None:
            with self._lock:
                live = self._jobs.get(job_id)
                if live is not None and live.status not in TERMINAL:
                    live.runtime_ref = runtime_ref
                    live.message = (
                        "admitted via runtime hook (awaiting runtime stamp; "
                        "no local stub)"
                    )
                    live.updated_at = self._clock()
                    merged = dict(live.local) if live.local else {}
                    merged["backed"] = BACKED_RUNTIME
                    live.local = merged
            return self.get(job_id)

        if local is not None:
            with self._lock:
                live = self._jobs.get(job_id)
                if live is not None:
                    merged = dict(live.local) if live.local else {}
                    merged["backed"] = BACKED_STUB
                    live.local = merged
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
            return self._snapshot(job)

    def handoff(self, job_id: str) -> dict[str, str]:
        return self.get(job_id).to_handoff()

    def payload(self, job_id: str) -> dict[str, Any]:
        return self.get(job_id).to_payload()

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
            job.status = STATUS_CANCELED
            job.updated_at = self._clock()
            job.message = "canceled by operator"
            event = self._cancel.get(job_id)
            if event is not None:
                event.set()
            return self._snapshot(job)

    def _try_runtime_cancel(
        self, job_id: str, runtime_ref: dict[str, Any] | None
    ) -> bool:
        try:
            return bool(self.runtime_hook.cancel(job_id, runtime_ref))
        except Exception:
            return False

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
