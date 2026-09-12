"""In-guest job store and stub runner.

Emits WorkHandoff JSON (kind/class/payload_digest + status/id). Does
not call runtime.apply compute-work. Mesh is compute-job → sos
(worker calls Unit). In-process stub is the fallback; operator/ctl
admits the exported handoff. Pause/resume is durable-path only
(injected hook or opt-in lab adapter); stub jobs are refused.
Progress prefers hook.progress() path-slices when durable-backed.
Events prefer hook.events() JSONL when durable-backed. Cancel on the
durable path signals hook.cancel() first (same honesty as pause),
then prefers hook.status() so Temporal-backed runs show ctl
lifecycle — not a stale stub clock. Stub-only stays local cancel.
Historical comparison uses list/get identity (in-process plus local
lab files when persisted) and prefers durable wall_elapsed_ms when
the hook (or a persisted job field) includes it. One-click re-admit posts the existing
handoff/payload through the same hook seam as a new admit when a
durable hook is active; fail-closed without hook or payload (no
silent stub). Default hook stays inert. live|parity admit must return a
running id (runtime #143) so UI can poll mid-flight; timeout is
ctl_admit_timeout / missing id fail closed — no stub progress. Does not close
#70. Does not close #78.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sos.compare import compare_vs_priors
from sos.stage_elapsed import (
    WALL_SOURCE_PROGRESS,
    WALL_SOURCE_STATUS,
    attach_timeline_elapsed,
    wall_elapsed_ms_from_durable,
)
from sos.errors import (
    CTL_ADMIT_TIMEOUT_DETAIL,
    CTL_HTTP_UNREACHABLE_DETAIL,
    DURABLE_ADMIT_FAILED_DETAIL,
    ERROR_CTL_ADMIT_TIMEOUT,
    ERROR_CTL_HTTP_UNREACHABLE,
    ERROR_DURABLE_ADMIT_FAILED,
    SAME_JOB_STUB_DETAIL,
    AlreadyTerminal,
    CtlAdmitTimeout,
    CtlHttpUnreachable,
    DurableAdmitFailed,
    IllegalTransition,
    JobNotFound,
    PayloadUnknown,
    ReAdmitUnavailable,
    StubOnly,
    lab_serve_affordance,
)
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
    LIVE_PAYLOAD_DIGEST,
    CTL_ADMIT,
    CTL_IEC_LOCAL_ADMIT,
    DEFAULT_SLEEP_SECONDS,
    DEMO_ECHO,
    DEMO_RESERVE,
    DEMO_SLEEP,
    FAILED_OR_CANCELED,
    HANDOFF_DOCS_NOTE,
    LAB_COMPOSE_DOCS,
    LAB_COMPOSE_IEC_DOCS,
    LAB_COMPOSE_IEC_SCRIPT,
    LAB_COMPOSE_SCRIPT,
    LAST_EVENTS_N,
    OWNERSHIP_NOTE,
    PARITY_PAYLOAD_DIGEST,
    PATH_SLICE_OWNERS,
    RECOVERABILITY_NOTE,
    RESERVE_CATALOG_LIVE,
    RESERVE_CATALOG_PARITY,
    RESERVE_CATALOG_SAME_JOB,
    SAME_JOB_CATALOG_ALIASES,
    SAME_JOB_PAYLOAD_DIGEST,
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
from sos.events_export import (
    DURABLE_EVENTS_NOTE,
    EVENTS_EXPORT_NOTE,
    MEMORY_EVENTS_NOTE,
    export_meta,
    filter_events,
)
from sos.runtime_hook import (
    InertRuntimeHandoffHook,
    RuntimeHandoffHook,
    durable_hook_active,
)

DEFAULT_STEP_SECONDS = 0.15
PROGRESS_SOURCE_STUB = "stub"
PROGRESS_SOURCE_DURABLE = "durable"
PROGRESS_SOURCE_UNREACHABLE = "unreachable"
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
# iec-local / Platform extras. Surface when the hook supplies them.
# Do not invent a chunk / ETA / heartbeat panel from these.
_IEC_PROGRESS_EXTRA_KEYS = (
    "current_scenario",
    "total_scenarios",
    "scenarios_completed",
    "kernel_time_s",
    "chunk_idx",
    "n_chunks",
    "updated_at",
    "heartbeat_interval_s",
)
# Platform GET /v1/jobs/{id}/progress zeros these when the blob is empty.
_IEC_PLATFORM_ZERO_DEFAULTS = frozenset(
    {
        "pct",
        "current_scenario",
        "total_scenarios",
        "scenarios_completed",
        "kernel_time_s",
    }
)
STUB_PROGRESS_NOTE = (
    "Stub stage metadata derived from job fields — "
    "not iec chunk progress or parallelism"
)
DURABLE_PROGRESS_NOTE = (
    "Durable hook progress (reserve-temporal path-slices or iec-local "
    "phase/fraction) — not iec planner parallelism; not iec chunk "
    "progress. Guest does not run IFRS17 math. Optional per-stage "
    "elapsed from progress or event timestamps when present; omitted "
    "when missing — never invented. Optional wall_elapsed_ms / "
    "api_e2e_ms from durable progress/status/walls when present; "
    "omitted when missing — never invented"
)
DURABLE_WALL_NOTE = (
    "Durable wall from hook timestamps (reserve-temporal or iec-local "
    "api_e2e) — not a forecast; not invented; not IFRS17; not iec SPA; "
    "guest does not run IFRS17"
)
SAME_JOB_PROGRESS_NOTE = (
    "iec-local same-job progress from the runtime binding "
    "(operator iec checkout / POST /v1/jobs). Guest does not run "
    "IFRS17 math. Phase/fraction when the hook supplies them — "
    "omit Platform unknown/0 defaults (runtime #149 / #150); never "
    "invent. Richer hook fields surface when present (no invented "
    "SPA chunk/ETA/heartbeat chrome). Walls (api_e2e_ms / "
    "wall_elapsed_ms) omitted when missing — never invented. "
    "Not #70 Done. north_star_done false"
)
TIMELINE_COMPLETED = "completed"
TIMELINE_CURRENT = "current"
TIMELINE_PENDING = "pending"
_HOOK_STAGE_NAME_KEYS = ("stage_names", "timeline", "slices")
INVESTIGATE_NOTE = (
    "Thinner investigate — catalog identity + static path-slice owners "
    "when hooked; not Slack; not a data-catalog product; not a SIEM"
)
MINUTES_CLASS_CATALOGS = frozenset(
    {RESERVE_CATALOG_LIVE, RESERVE_CATALOG_PARITY}
)
MINUTES_CLASS_DIGESTS = frozenset({LIVE_PAYLOAD_DIGEST, PARITY_PAYLOAD_DIGEST})


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
    wall_elapsed_ms: int | None = None

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

    def to_dict(self, *, durable_hook: bool = False) -> dict[str, Any]:
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
        recoverability = _recoverability_payload(self, durable_hook=durable_hook)
        if recoverability:
            payload["recoverability"] = recoverability
        payload["handoff_docs"] = _handoff_docs_payload(self)
        if self.error == ERROR_CTL_HTTP_UNREACHABLE:
            payload["lab_serve"] = lab_serve_affordance()
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

    def to_events(self, kinds: list[str] | None = None) -> dict[str, Any]:
        """Process-memory trail, or durable overlay already applied on the snapshot.

        ``kinds`` filters by event/kind/type (admit / StageCompleted /
        pause / …). Empty filter returns the full trail. Empty match
        stays empty — not a SIEM.
        """
        raw = _copy_events(self.events)
        wanted = list(kinds) if kinds else []
        trail = filter_events(raw, wanted)
        payload: dict[str, Any] = {
            "id": self.id,
            "events": trail,
            "export": export_meta(
                job_id=self.id,
                source=(
                    EVENTS_SOURCE_DURABLE
                    if self.events_source == EVENTS_SOURCE_DURABLE
                    else EVENTS_SOURCE_MEMORY
                ),
                kinds=wanted,
            ),
            "export_note": EVENTS_EXPORT_NOTE,
        }
        if wanted:
            payload["kind_filter"] = wanted
        if self.events_source == EVENTS_SOURCE_DURABLE:
            payload["source"] = EVENTS_SOURCE_DURABLE
            payload["note"] = DURABLE_EVENTS_NOTE
            payload["events_durable"] = (
                True if self.events_durable is None else self.events_durable
            )
            if wanted:
                payload["events_n"] = len(trail)
                payload["events_total"] = (
                    self.events_n if self.events_n is not None else len(raw)
                )
            elif self.events_n is not None:
                payload["events_n"] = self.events_n
            else:
                payload["events_n"] = len(trail)
            return payload
        payload["source"] = EVENTS_SOURCE_MEMORY
        payload["note"] = MEMORY_EVENTS_NOTE
        if wanted:
            payload["events_n"] = len(trail)
            payload["events_total"] = len(raw)
        return payload


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


def _recoverability_payload(
    job: Job, *, durable_hook: bool = False
) -> dict[str, Any] | None:
    """Handoff/payload re-admit. Cancel/fail does not auto-retry.

    ``one_click`` is true only when a durable hook is active **and**
    payload bytes are known. Fail-closed otherwise — no silent stub.
    """
    if job.status not in FAILED_OR_CANCELED:
        return None
    payload_known = job.payload_bytes is not None
    one_click = bool(durable_hook and payload_known)
    if payload_known:
        reason = None if one_click else "hook_inert"
    else:
        reason = "payload_unknown"
    payload: dict[str, Any] = {
        "auto_retry": False,
        "resume_from_failed": False,
        "new_admit": True,
        "one_click": one_click,
        "one_click_path": f"POST /v0/jobs/{job.id}/re-admit",
        "handoff": f"GET /v0/jobs/{job.id}/handoff",
        "payload": f"GET /v0/jobs/{job.id}/payload",
        "payload_known": payload_known,
        "re_admit": CTL_ADMIT,
        "note": RECOVERABILITY_NOTE,
    }
    if reason:
        payload["one_click_reason"] = reason
    return payload


def _handoff_docs_payload(job: Job) -> dict[str, Any]:
    """Compact operator reminders. Not a second control plane."""
    return {
        "note": HANDOFF_DOCS_NOTE,
        "handoff": f"GET /v0/jobs/{job.id}/handoff",
        "payload": f"GET /v0/jobs/{job.id}/payload",
        "re_admit": CTL_IEC_LOCAL_ADMIT if _same_job(job) else CTL_ADMIT,
        "re_admit_http": f"POST /v0/jobs/{job.id}/re-admit",
        "lab_compose": LAB_COMPOSE_DOCS,
        "lab_compose_script": LAB_COMPOSE_SCRIPT,
        "lab_compose_iec": LAB_COMPOSE_IEC_DOCS,
        "lab_compose_iec_script": LAB_COMPOSE_IEC_SCRIPT,
        "not_control_plane": True,
        "ifrs17_guest": False,
        "north_star_done": False,
    }


def _local_for_readmit(source: Job) -> dict[str, Any] | None:
    """Copy catalog/demo identity; drop in-flight stage. New admit."""
    local = _copy_local(source.local) or {}
    for key in ("stage", "stage_index", "backed"):
        local.pop(key, None)
    local["re_admit_from"] = source.id
    return local or None


def _copy_local(local: dict[str, Any] | None) -> dict[str, Any] | None:
    return dict(local) if local else None


def _copy_events(events: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [dict(item) for item in events] if events else []


def _is_runtime_backed(job: Job) -> bool:
    """True when a runtime ref / runtime-backed path exists."""
    backed = (job.local or {}).get("backed")
    return backed == BACKED_RUNTIME or job.runtime_ref is not None


def _minutes_class(job: Job) -> bool:
    """live|parity catalogs (or matching digests). Minutes-class walls."""
    catalog = (job.local or {}).get("catalog")
    if catalog in MINUTES_CLASS_CATALOGS:
        return True
    return job.payload_digest in MINUTES_CLASS_DIGESTS


def _same_job(job: Job) -> bool:
    """Pinned iec reserve_ifrs17 identity. Not the thinner kernel."""
    catalog = str((job.local or {}).get("catalog") or "").strip().lower()
    if catalog in SAME_JOB_CATALOG_ALIASES or catalog == RESERVE_CATALOG_SAME_JOB:
        return True
    if (job.local or {}).get("same_job") is True:
        return True
    return job.payload_digest == SAME_JOB_PAYLOAD_DIGEST


def _pause_resume_honest(job: Job) -> bool:
    """True only when a live durable path exists.

    Fail closed when CTL_HTTP is opted in but lab serve is down —
    do not pretend pause/resume still works.
    """
    if job.error == ERROR_CTL_HTTP_UNREACHABLE:
        return False
    return _is_runtime_backed(job)


def _copy_progress_counters(src: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in _PROGRESS_COUNTER_KEYS:
        if key in src and src[key] is not None:
            out[key] = src[key]
    return out


def _progress_number(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _honest_phase(value: Any) -> str | None:
    """Pass through hook phase/event only when present. Omit unknown."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "unknown":
        return None
    return text


def _progress_field_blobs(data: dict[str, Any]) -> list[dict[str, Any]]:
    blobs: list[dict[str, Any]] = [data]
    nested = data.get("progress")
    if isinstance(nested, dict):
        blobs.append(nested)
    return blobs


def _first_progress_value(data: dict[str, Any], key: str) -> Any:
    for blob in _progress_field_blobs(data):
        if key in blob and blob[key] not in (None, ""):
            return blob[key]
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _slice_label(item: Any) -> str | None:
    """A hook-provided stage name. Numeric stage indexes are not names."""
    if isinstance(item, str):
        text = item.strip()
        if not text or text.isdigit() or text.lstrip("-").isdigit():
            return None
        return text
    if isinstance(item, dict):
        for key in ("name", "slice", "stage"):
            label = _slice_label(item.get(key))
            if label:
                return label
    return None


def _hook_stage_names(durable: dict[str, Any], total: int) -> list[str | None] | None:
    """Names the hook returned. None means use day-one path-slice defaults."""
    blobs: list[dict[str, Any]] = [durable]
    nested = durable.get("progress")
    if isinstance(nested, dict):
        blobs.append(nested)
    for blob in blobs:
        for key in _HOOK_STAGE_NAME_KEYS:
            raw = blob.get(key)
            if not isinstance(raw, list) or not raw:
                continue
            names = [_slice_label(item) for item in raw[:total]]
            if any(names):
                while len(names) < total:
                    names.append(None)
                return names
        raw_stages = blob.get("stages")
        if isinstance(raw_stages, list) and raw_stages:
            names = [_slice_label(item) for item in raw_stages[:total]]
            # A short stages[] list is elapsed (or a prefix), not a
            # name override — do not drop day-one admit/project/fold/complete.
            if any(names) and len(raw_stages) >= total:
                while len(names) < total:
                    names.append(None)
                return names
    return None


def _default_slice_names(total: int) -> list[str | None]:
    """admit/project/fold/complete for known slices. No invented extras."""
    names: list[str | None] = []
    for index in range(total):
        if index < len(PATH_SLICE_OWNERS):
            names.append(PATH_SLICE_OWNERS[index][0])
        else:
            names.append(None)
    return names


def _owner_for_slice(name: str | None) -> str | None:
    """Same static owners as investigate. No invented Slack / team tags."""
    if not name:
        return None
    for tag in _ownership_tags()["tags"]:
        if tag.get("slice") == name:
            owner = tag.get("owner")
            return str(owner) if owner else None
    return None


def _current_slice_index(
    stage: Any, names: list[str | None], total: int
) -> int | None:
    if isinstance(stage, str):
        label = stage.strip()
        if label and not label.lstrip("-").isdigit():
            for index, name in enumerate(names, start=1):
                if name == label:
                    return index
            return None
    current = _as_int(stage)
    if current is None or current < 1 or current > total:
        return None
    return current


def _progress_timeline(
    durable: dict[str, Any], counters: dict[str, Any]
) -> list[dict[str, Any]] | None:
    """Named path-slices + ownership. States follow honest counters only."""
    total = _as_int(counters.get("stages_total"))
    if total is None or total <= 0:
        return None
    hook_names = _hook_stage_names(durable, total)
    names = hook_names if hook_names is not None else _default_slice_names(total)
    done_raw = counters.get("stages_completed")
    done = _as_int(done_raw) if done_raw is not None else None
    if done is not None:
        done = max(0, min(done, total))
    current = _current_slice_index(counters.get("stage"), names, total)
    items: list[dict[str, Any]] = []
    for index in range(1, total + 1):
        name = names[index - 1] if index - 1 < len(names) else None
        if done is not None and index <= done:
            state = TIMELINE_COMPLETED
        elif current is not None and index == current:
            state = TIMELINE_CURRENT
        else:
            state = TIMELINE_PENDING
        item: dict[str, Any] = {"index": index, "state": state}
        if name:
            item["name"] = name
        owner = _owner_for_slice(name)
        if owner:
            item["owner"] = owner
        items.append(item)
    return items


def _has_progress_counters(data: dict[str, Any]) -> bool:
    return any(
        key in blob
        for blob in _progress_field_blobs(data)
        for key in _PROGRESS_COUNTER_KEYS
    )


def _has_iec_progress_fields(data: dict[str, Any]) -> bool:
    """True when iec-local supplied phase/extras/walls — counters optional.

    Runtime #149 / #150 may omit phase/fraction (Platform unknown/0).
    Walls-only or same_job blobs stay durable — do not fall back to stub.
    """
    if data.get("same_job") is True or data.get("iec_job_id"):
        return True
    walls = data.get("walls")
    if isinstance(walls, dict) and walls.get("invented") is not True:
        return True
    for blob in _progress_field_blobs(data):
        if blob.get("same_job") is True:
            return True
        if _honest_phase(blob.get("phase")) or _honest_phase(blob.get("event")):
            return True
        for key in _IEC_PROGRESS_EXTRA_KEYS:
            if blob.get(key) not in (None, ""):
                return True
        messages = blob.get("messages")
        if isinstance(messages, list) and messages:
            return True
    return False


def _has_durable_progress(data: dict[str, Any]) -> bool:
    """Path-slice counters, or iec-local fields/walls without invented zeros."""
    return _has_progress_counters(data) or _has_iec_progress_fields(data)


def _sanitize_same_job_progress(
    payload: dict[str, Any],
    *,
    durable: dict[str, Any],
    nested_raw: dict[str, Any] | None,
) -> None:
    """Omit Platform unknown/0 defaults. Keep hook-supplied honest fields."""
    phase = _honest_phase(payload.get("phase")) or _honest_phase(
        payload.get("event")
        or _first_progress_value(durable, "event")
        or (nested_raw or {}).get("event")
    )
    if phase is None:
        payload.pop("phase", None)
        payload.pop("event", None)
    else:
        payload["phase"] = phase

    frac = _progress_number(payload.get("fraction"))
    pct = _progress_number(payload.get("pct"))
    if phase is None:
        if frac is None or frac == 0.0:
            payload.pop("fraction", None)
        if pct is None or pct == 0.0:
            payload.pop("pct", None)
    elif frac is None and pct is not None:
        payload["fraction"] = pct if 0.0 <= pct <= 1.0 else pct / 100.0

    nested = payload.get("progress")
    if isinstance(nested, dict):
        if "fraction" not in payload:
            nested.pop("fraction", None)
        if "phase" not in payload:
            nested.pop("phase", None)
        if not nested:
            payload.pop("progress", None)


def _attach_iec_progress_extras(
    payload: dict[str, Any],
    *,
    durable: dict[str, Any],
    nested_raw: dict[str, Any] | None,
) -> None:
    """Copy richer hook fields when present. No invented chrome."""
    blobs: list[dict[str, Any]] = [durable]
    if isinstance(nested_raw, dict):
        blobs.append(nested_raw)
    for key in _IEC_PROGRESS_EXTRA_KEYS:
        if key in payload:
            continue
        value = None
        for blob in blobs:
            if key in blob and blob[key] not in (None, ""):
                value = blob[key]
                break
        if value is None:
            continue
        if key in _IEC_PLATFORM_ZERO_DEFAULTS and _progress_number(value) == 0.0:
            continue
        payload[key] = value
    messages = None
    for blob in blobs:
        raw = blob.get("messages")
        if isinstance(raw, list) and raw:
            messages = raw[-10:]
            break
    if messages:
        payload["messages"] = messages


def _attach_wall_elapsed(
    payload: dict[str, Any],
    *,
    durable: dict[str, Any] | None,
    status: dict[str, Any] | None = None,
) -> None:
    """Copy an honest hook wall onto durable progress. Omit when absent."""
    ms = wall_elapsed_ms_from_durable(durable)
    source = WALL_SOURCE_PROGRESS if ms is not None else None
    if ms is None:
        ms = wall_elapsed_ms_from_durable(status)
        if ms is not None:
            source = WALL_SOURCE_STATUS
    if ms is None:
        return
    payload["wall_elapsed_ms"] = ms
    payload["wall_source"] = source
    payload["wall_note"] = DURABLE_WALL_NOTE


def _hook_status_payload(hook: Any) -> dict[str, Any] | None:
    """Last ctl status JSON when a lab hook cached it. Else omit."""
    raw = getattr(hook, "last_status_payload", None)
    return raw if isinstance(raw, dict) and raw else None


def _progress_from_durable(
    job: Job,
    durable: dict[str, Any],
    *,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    for key in ("phase", "pct", "event"):
        if durable.get(key) is not None:
            payload[key] = durable[key]
        elif isinstance(nested_raw, dict) and nested_raw.get(key) is not None:
            payload[key] = nested_raw[key]
    walls = durable.get("walls")
    if isinstance(walls, dict) and walls.get("invented") is not True:
        honest_walls = {
            key: walls[key]
            for key in (
                "api_e2e_ms",
                "wall_elapsed_ms",
                "method_wall_time_s",
                "started_at",
                "completed_at",
                "contract",
                "invented",
            )
            if key in walls and walls[key] is not None
        }
        if honest_walls:
            payload["walls"] = honest_walls
    if _same_job(job):
        payload["same_job"] = True
        payload["ifrs17_guest"] = False
        payload["note"] = SAME_JOB_PROGRESS_NOTE
    if nested:
        payload["progress"] = nested
    elif isinstance(nested_raw, dict) and nested_raw and not (
        _same_job(job) or durable.get("same_job") is True
    ):
        payload["progress"] = {}
    if _same_job(job) or durable.get("same_job") is True:
        nested_dict = nested_raw if isinstance(nested_raw, dict) else None
        _sanitize_same_job_progress(
            payload, durable=durable, nested_raw=nested_dict
        )
        _attach_iec_progress_extras(
            payload, durable=durable, nested_raw=nested_dict
        )
    timeline = _progress_timeline(durable, payload)
    if timeline:
        elapsed_source = attach_timeline_elapsed(
            timeline,
            durable=durable,
            events=job.events if job.events_source == EVENTS_SOURCE_DURABLE else None,
            events_durable=job.events_source == EVENTS_SOURCE_DURABLE,
        )
        payload["timeline"] = timeline
        if elapsed_source:
            payload["elapsed_source"] = elapsed_source
    _attach_wall_elapsed(payload, durable=durable, status=status)
    _attach_investigate(payload, job, hooked=True)
    return payload


def _progress_from_unreachable(job: Job) -> dict[str, Any]:
    """Honest progress when opted-in CTL_HTTP cannot connect."""
    return {
        "id": job.id,
        "status": job.status,
        "message": job.message or CTL_HTTP_UNREACHABLE_DETAIL,
        "error": ERROR_CTL_HTTP_UNREACHABLE,
        "backed": (job.local or {}).get("backed"),
        "pause_resume": False,
        "source": PROGRESS_SOURCE_UNREACHABLE,
        "note": CTL_HTTP_UNREACHABLE_DETAIL,
        "lab_serve": lab_serve_affordance(),
    }


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

        try:
            runtime_ref = self._try_admit(job)
        except CtlHttpUnreachable as exc:
            self._fail_admit_closed(
                job_id,
                error=ERROR_CTL_HTTP_UNREACHABLE,
                message=CTL_HTTP_UNREACHABLE_DETAIL,
            )
            exc.fields["id"] = job_id
            raise
        except CtlAdmitTimeout as exc:
            self._fail_admit_closed(
                job_id,
                error=ERROR_CTL_ADMIT_TIMEOUT,
                message=CTL_ADMIT_TIMEOUT_DETAIL,
            )
            exc.fields["id"] = job_id
            raise
        if runtime_ref is not None:
            with self._lock:
                live = self._jobs.get(job_id)
                if live is not None and live.status not in TERMINAL:
                    self._bind_runtime_locked(live, runtime_ref)
            return self.get(job_id)
        if _same_job(job):
            exc = DurableAdmitFailed(
                job_id,
                reason="same_job_stub",
                detail=SAME_JOB_STUB_DETAIL,
            )
            self._fail_admit_closed(
                job_id,
                error=ERROR_DURABLE_ADMIT_FAILED,
                message=SAME_JOB_STUB_DETAIL,
            )
            raise exc
        if _minutes_class(job) and durable_hook_active(self.runtime_hook):
            exc = DurableAdmitFailed(job_id, reason="hook_refused")
            self._fail_admit_closed(
                job_id,
                error=ERROR_DURABLE_ADMIT_FAILED,
                message=DURABLE_ADMIT_FAILED_DETAIL,
            )
            raise exc

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
        except (CtlHttpUnreachable, CtlAdmitTimeout, DurableAdmitFailed):
            raise
        except Exception:
            return None

    def _bind_runtime_locked(
        self, job: Job, runtime_ref: dict[str, Any]
    ) -> None:
        """Caller holds ``_lock``. Apply running id from admit; work continues."""
        status = runtime_ref.get("status")
        job.runtime_ref = {
            key: value for key, value in runtime_ref.items() if key != "status"
        }
        if isinstance(status, str) and status in WORK_STATUSES:
            previous = job.status
            job.status = status
            if status == STATUS_RUNNING and previous != STATUS_RUNNING:
                self._append_event_locked(
                    job, "running", "admit returned running"
                )
        job.message = "admitted via runtime hook (operator/ctl; no local stub)"
        job.updated_at = self._clock()
        merged = dict(job.local) if job.local else {}
        merged["backed"] = BACKED_RUNTIME
        job.local = merged
        self._append_event_locked(job, "backed", BACKED_RUNTIME)
        self._persist_locked(job)

    def _fail_admit_closed(
        self, job_id: str, *, error: str, message: str
    ) -> None:
        """Record a failed job. Do not start the stub. Not durable."""
        with self._lock:
            live = self._jobs.get(job_id)
            if live is None:
                return
            live.status = STATUS_FAILED
            live.error = error
            live.message = message
            live.updated_at = self._clock()
            merged = dict(live.local) if live.local else {}
            merged["backed"] = BACKED_STUB
            live.local = merged
            self._append_event_locked(live, "failed", message)
            self._persist_locked(live)

    def _fail_admit_unreachable(
        self, job_id: str, exc: CtlHttpUnreachable
    ) -> None:
        """Record a failed job. Do not start the stub. Not durable."""
        del exc
        self._fail_admit_closed(
            job_id,
            error=ERROR_CTL_HTTP_UNREACHABLE,
            message=CTL_HTTP_UNREACHABLE_DETAIL,
        )

    def _apply_unreachable(self, job_id: str, exc: CtlHttpUnreachable) -> None:
        """Attach the lab-serve-down affordance. Do not invent ctl status."""
        del exc
        with self._lock:
            live = self._jobs.get(job_id)
            if live is None:
                return
            already = live.error == ERROR_CTL_HTTP_UNREACHABLE
            live.error = ERROR_CTL_HTTP_UNREACHABLE
            live.message = CTL_HTTP_UNREACHABLE_DETAIL
            live.updated_at = self._clock()
            if not already:
                self._append_event_locked(
                    live, ERROR_CTL_HTTP_UNREACHABLE, CTL_HTTP_UNREACHABLE_DETAIL
                )
            self._persist_locked(live)

    def get(self, job_id: str) -> Job:
        """Snapshot plus hook.status() follow when ``runtime_ref`` exists."""
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

    def public_dict(self, job: Job) -> dict[str, Any]:
        """Job resource with recoverability one-click honesty for this hook."""
        return job.to_dict(durable_hook=durable_hook_active(self.runtime_hook))

    def handoff(self, job_id: str) -> dict[str, str]:
        return self.get(job_id).to_handoff()

    def payload(self, job_id: str) -> dict[str, Any]:
        return self.get(job_id).to_payload()

    def readmit(self, job_id: str) -> Job:
        """New admit of the same handoff identity + payload. Not resume.

        Fail-closed without a durable hook, when payload bytes are
        missing, or when ``hook.admit`` refuses. Never falls back to
        the in-process stub. New job id.
        """
        source = self.get(job_id)
        if source.status not in FAILED_OR_CANCELED:
            raise IllegalTransition(job_id, source.status, "re-admit")
        if source.payload_bytes is None:
            raise ReAdmitUnavailable(
                job_id,
                "payload_unknown",
                detail=(
                    "handoff or payload missing; cannot one-click re-admit. "
                    "Fail-closed; no silent stub re-admit. "
                    f"Operator/ctl: {CTL_ADMIT}"
                ),
            )
        if not durable_hook_active(self.runtime_hook):
            raise ReAdmitUnavailable(
                job_id,
                "hook_inert",
                detail=(
                    "re-admit requires an active durable hook "
                    "(PANORAMIX_CTL_HTTP preferred or PANORAMIX_RUNTIME_ROOT). "
                    "Fail-closed; no silent stub re-admit. "
                    f"Operator/ctl: {CTL_ADMIT}"
                ),
            )

        new_id = str(uuid.uuid4())
        now = self._clock()
        local = _local_for_readmit(source)
        new_job = Job(
            id=new_id,
            kind=source.kind,
            resource_class=source.resource_class,
            payload_digest=source.payload_digest,
            status=STATUS_QUEUED,
            created_at=now,
            updated_at=now,
            local=local,
            payload_bytes=source.payload_bytes,
        )
        try:
            runtime_ref = self.runtime_hook.admit(
                new_job.to_handoff(), new_job.payload_bytes
            )
        except CtlHttpUnreachable as exc:
            exc.fields["id"] = job_id
            exc.fields.setdefault("action", "re-admit")
            raise
        except CtlAdmitTimeout as exc:
            exc.fields["id"] = job_id
            exc.fields.setdefault("action", "re-admit")
            raise
        except Exception as exc:
            raise ReAdmitUnavailable(
                job_id,
                "hook_refused",
                detail=(
                    f"hook.admit failed ({exc}); no silent stub re-admit. "
                    "Not resume-from-failed."
                ),
            ) from exc
        if runtime_ref is None:
            raise ReAdmitUnavailable(
                job_id,
                "hook_refused",
                detail=(
                    "hook.admit returned None; no silent stub re-admit. "
                    "Not resume-from-failed."
                ),
            )

        cancel = threading.Event()
        submit_detail = (
            f"kind={new_job.kind} class={new_job.resource_class} "
            f"re-admit from {source.id}"
        )
        with self._lock:
            self._jobs[new_id] = new_job
            self._cancel[new_id] = cancel
            self._append_event_locked(new_job, "submitted", submit_detail)
            new_job.runtime_ref = runtime_ref
            new_job.message = (
                "re-admitted via runtime hook (new admit; not resume-from-failed)"
            )
            new_job.updated_at = self._clock()
            merged = dict(new_job.local) if new_job.local else {}
            merged["backed"] = BACKED_RUNTIME
            merged["re_admit_from"] = source.id
            new_job.local = merged
            self._append_event_locked(new_job, "backed", BACKED_RUNTIME)
            self._persist_locked(new_job)
        return self.get(new_id)

    def progress(self, job_id: str) -> dict[str, Any]:
        """Prefer dedicated hook.progress(); stub fields are fallback only.

        ``get()`` already refreshes lifecycle via ``status()``. Stage
        counters are not scraped from status strings.
        """
        job = self.get(job_id)
        if job.error == ERROR_CTL_HTTP_UNREACHABLE:
            return _progress_from_unreachable(job)
        if self._is_durable(job):
            try:
                durable = self._try_runtime_progress(job_id, job.runtime_ref)
            except CtlHttpUnreachable as exc:
                self._apply_unreachable(job_id, exc)
                return _progress_from_unreachable(self.get(job_id))
            if durable is not None:
                payload = _progress_from_durable(
                    job,
                    durable,
                    status=_hook_status_payload(self.runtime_hook),
                )
                self._store_wall_ms(job.id, payload.get("wall_elapsed_ms"))
                return payload
        return job.to_progress()

    def events(
        self, job_id: str, kinds: list[str] | None = None
    ) -> dict[str, Any]:
        """Prefer dedicated hook.events(); process-memory trail is fallback only.

        ``get()`` already overlays durable JSONL onto the job snapshot when
        the hook returns events. Optional ``kinds`` filters that trail
        (memory and durable). Empty match is an empty list.
        """
        return self.get(job_id).to_events(kinds)

    def compare(self, job_id: str) -> dict[str, Any]:
        """Vs recent same-catalog or same-kind/class jobs in guest history.

        Reuses ``list()`` / ``get()`` identity (in-process plus reloaded
        lab files). Prefers durable ``wall_elapsed_ms`` when the hook
        or a persisted job field includes it. No guest→ctl channel.
        Does not invent typical/ETA without succeeded prior walls.
        """
        current = self._remember_durable_wall(self.get(job_id))
        peers = [
            self._remember_durable_wall(job)
            for job in self.list()
            if job.id != job_id
        ]
        return compare_vs_priors(current, peers, now=self._clock())

    def list(self, statuses: frozenset[str] | set[str] | None = None) -> list[Job]:
        """Newest first. Optional ``statuses`` is real ``job.status`` only."""
        with self._lock:
            ids = list(self._jobs.keys())
        jobs = [self.get(job_id) for job_id in ids]
        jobs.reverse()  # insertion order, newest first
        if statuses:
            jobs = [job for job in jobs if job.status in statuses]
        return jobs

    def cancel(self, job_id: str) -> Job:
        """Signal runtime cancel first when hooked; stub stays local.

        Same honesty as pause: durable jobs call the hook before the
        guest store changes. Then ``status()`` is preferred when
        ``runtime_ref`` exists so ctl terminal wins over a local mark.
        Stub-only (no runtime ref) stays ``canceled by operator``.
        Inert hook cancel returns False and does not pretend.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFound(job_id)
            if job.status in TERMINAL:
                raise AlreadyTerminal(job_id, job.status)
            runtime_ref = job.runtime_ref
            follow = runtime_ref is not None
        signaled = self._try_runtime_cancel(job_id, runtime_ref)
        if follow:
            self._refresh_runtime_status(job_id)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFound(job_id)
            if job.status in TERMINAL:
                # Ctl already reported canceled/failed/succeeded.
                return self._snapshot(job)
            now = self._clock()
            job.status = STATUS_CANCELED
            job.updated_at = now
            detail = (
                "canceled via runtime hook" if signaled else "canceled by operator"
            )
            job.message = detail
            self._append_event_locked(job, "canceled", detail)
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
        return _is_runtime_backed(job)

    def _store_wall_ms(self, job_id: str, ms: Any) -> None:
        """Persist a real durable wall. Omit invalid. Never invent."""
        if isinstance(ms, bool) or ms is None:
            return
        if isinstance(ms, int):
            wall = ms if ms >= 0 else None
        elif isinstance(ms, float) and ms >= 0 and ms == ms:
            wall = int(round(ms))
        else:
            return
        if wall is None:
            return
        with self._lock:
            live = self._jobs.get(job_id)
            if live is None or live.wall_elapsed_ms == wall:
                return
            live.wall_elapsed_ms = wall
            self._persist_locked(live)

    def _remember_durable_wall(self, job: Job) -> Job:
        """Prefer hook wall when present; keep a persisted wall for priors.

        Terminal jobs that already have a real wall are left alone so
        restart priors stay honest without a live hook. Never invents
        a wall from guest clocks.
        """
        if job.status in TERMINAL and job.wall_elapsed_ms is not None:
            return job
        if (
            not self._is_durable(job)
            or job.error == ERROR_CTL_HTTP_UNREACHABLE
        ):
            return job
        durable: dict[str, Any] | None = None
        method = getattr(self.runtime_hook, "progress", None)
        if callable(method):
            try:
                reported = method(job.id, job.runtime_ref)
            except CtlHttpUnreachable:
                reported = None
            except Exception:
                reported = None
            if isinstance(reported, dict) and reported:
                durable = reported
        ms = wall_elapsed_ms_from_durable(durable)
        if ms is None:
            try:
                self.runtime_hook.status(job.id, job.runtime_ref)
            except CtlHttpUnreachable:
                return job
            except Exception:
                return job
            ms = wall_elapsed_ms_from_durable(_hook_status_payload(self.runtime_hook))
        if ms is None:
            return job
        self._store_wall_ms(job.id, ms)
        with self._lock:
            live = self._jobs.get(job.id)
            if live is None:
                return job
            return self._snapshot(live)

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
        except CtlHttpUnreachable as exc:
            self._apply_unreachable(job_id, exc)
            raise
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
        except CtlHttpUnreachable:
            raise
        except Exception:
            return None
        if not isinstance(reported, dict) or not reported:
            return None
        if _has_durable_progress(reported):
            return reported
        with self._lock:
            job = self._jobs.get(job_id)
        if job is not None and _same_job(job):
            return reported
        return None

    def _try_runtime_events(
        self, job_id: str, runtime_ref: dict[str, Any] | None
    ) -> dict[str, Any] | list[Any] | None:
        method = getattr(self.runtime_hook, "events", None)
        if not callable(method):
            return None
        try:
            reported = method(job_id, runtime_ref)
        except CtlHttpUnreachable as exc:
            self._apply_unreachable(job_id, exc)
            return None
        except Exception:
            return None
        if not _has_durable_events(reported):
            return None
        return reported

    def _refresh_runtime_status(self, job_id: str) -> None:
        """Prefer hook.status() on get/list when a runtime ref exists.

        Temporal-backed runs show paused/running/terminal from ctl,
        not a stale stub clock. No-op without runtime_ref (stub /
        inert). Terminal guest jobs are left alone.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.runtime_ref is None or job.status in TERMINAL:
                return
            runtime_ref = job.runtime_ref
        try:
            reported = self.runtime_hook.status(job_id, runtime_ref)
        except CtlHttpUnreachable as exc:
            self._apply_unreachable(job_id, exc)
            return
        except Exception:
            return
        self._store_wall_ms(
            job_id, wall_elapsed_ms_from_durable(_hook_status_payload(self.runtime_hook))
        )
        if not reported or reported not in WORK_STATUSES:
            return
        with self._lock:
            live = self._jobs.get(job_id)
            if live is None or live.status in TERMINAL:
                return
            if live.error == ERROR_CTL_HTTP_UNREACHABLE:
                live.error = None
                if live.message == CTL_HTTP_UNREACHABLE_DETAIL:
                    live.message = "status via runtime hook"
                live.updated_at = self._clock()
                self._persist_locked(live)
            if live.status == reported:
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
            wall_elapsed_ms=job.wall_elapsed_ms,
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
