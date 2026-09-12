"""Thinner historical-run comparison from guest job history.

Uses list/get identity already present: catalog name (when on the job),
kind/class, created_at/updated_at, plus optional persisted
``wall_elapsed_ms`` when a durable hook actually returned it.
Prefers that durable wall for elapsed / typical / ETA; else guest
created/updated clocks. History may include records reloaded from
local lab files. Does not invent wall times or ETAs. Never labels a
guest clock as durable.
Not a forecast. Not IFRS17. Not iec SPA historical widget.
Does not close #70 / #78. Does not unlock #61 / #29.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sos.handoff_vocab import STATUS_SUCCEEDED, TERMINAL

COMPARE_SOURCE = "guest_history"
COMPARE_PRIOR_LIMIT = 5
TYPICAL_MIN_SAMPLES = 2
MATCH_CATALOG = "catalog"
MATCH_KIND_CLASS = "kind_class"
ELAPSED_SOURCE_DURABLE = "durable"
ELAPSED_SOURCE_GUEST = "guest_clock"

COMPARE_HONESTY = (
    "Not a forecast. Not IFRS17. Not iec SPA historical widget."
)
COMPARE_NOTE_EMPTY = (
    "No prior jobs in guest history to compare. " + COMPARE_HONESTY
)
COMPARE_NOTE_THIN = (
    "Guest history only (in-process plus local lab files when persisted) — "
    "elapsed prefers durable wall_elapsed_ms when present "
    "(runtime tip 9b6646e8 / main); else created/updated timestamps. "
    "Typical/ETA omitted until two succeeded priors exist. "
    + COMPARE_HONESTY
)
COMPARE_NOTE_TYPICAL = (
    "Typical wall is the median of succeeded prior elapsed times "
    "in guest history (in-process plus local lab files when persisted). "
    "Elapsed prefers durable wall_elapsed_ms when present "
    "(runtime tip 9b6646e8 / main); else created/updated timestamps. "
    "ETA is that same typical wall when this run is still live. "
    + COMPARE_HONESTY
)


def parse_job_ts(raw: Any) -> datetime | None:
    """Parse guest job timestamps. None if missing or unreadable — do not invent."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def wall_elapsed_seconds(job: Any) -> float | None:
    """Seconds from a persisted durable ``wall_elapsed_ms``. Omit if missing.

    Never invents a wall from guest created_at/updated_at.
    """
    raw = getattr(job, "wall_elapsed_ms", None)
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int):
        number = float(raw)
    elif isinstance(raw, float):
        number = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            number = float(raw.strip())
        except ValueError:
            return None
    else:
        return None
    if number < 0 or number != number:
        return None
    return round(number / 1000.0, 3)


def guest_clock_seconds(job: Any, *, now: str) -> float | None:
    """Wall seconds from created_at to updated_at (terminal) or now (live)."""
    start = parse_job_ts(getattr(job, "created_at", None))
    if start is None:
        return None
    status = getattr(job, "status", None)
    if status in TERMINAL:
        end = parse_job_ts(getattr(job, "updated_at", None))
    else:
        end = parse_job_ts(now)
    if end is None:
        return None
    seconds = (end - start).total_seconds()
    if seconds < 0:
        return 0.0
    return round(seconds, 3)


def elapsed_seconds(job: Any, *, now: str) -> float | None:
    """Prefer durable wall seconds; else guest created/updated clocks."""
    wall = wall_elapsed_seconds(job)
    if wall is not None:
        return wall
    return guest_clock_seconds(job, now=now)


def _catalog_name(job: Any) -> str | None:
    local = getattr(job, "local", None) or {}
    name = local.get("catalog") if isinstance(local, dict) else None
    if not name:
        return None
    return str(name)


def _kind(job: Any) -> str:
    return str(getattr(job, "kind", "") or "")


def _resource_class(job: Any) -> str:
    value = getattr(job, "resource_class", None)
    if value:
        return str(value)
    return str(getattr(job, "class", "") or "")


def _same_kind_class(current: Any, peer: Any) -> bool:
    return _kind(current) == _kind(peer) and _resource_class(current) == _resource_class(
        peer
    )


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return round((ordered[mid - 1] + ordered[mid]) / 2.0, 3)


def _row(job: Any, *, now: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": getattr(job, "id", ""),
        "status": getattr(job, "status", None),
        "kind": _kind(job),
        "class": _resource_class(job),
        "payload_digest": getattr(job, "payload_digest", None),
        "created_at": getattr(job, "created_at", None),
        "updated_at": getattr(job, "updated_at", None),
    }
    catalog = _catalog_name(job)
    if catalog is not None:
        row["catalog"] = catalog
    wall = wall_elapsed_seconds(job)
    if wall is not None:
        row["elapsed_s"] = wall
        row["elapsed_source"] = ELAPSED_SOURCE_DURABLE
        raw_ms = getattr(job, "wall_elapsed_ms", None)
        if isinstance(raw_ms, bool):
            raw_ms = None
        if isinstance(raw_ms, int) and raw_ms >= 0:
            row["wall_elapsed_ms"] = raw_ms
        elif isinstance(raw_ms, float) and raw_ms >= 0 and raw_ms == raw_ms:
            row["wall_elapsed_ms"] = int(round(raw_ms))
    else:
        elapsed = guest_clock_seconds(job, now=now)
        if elapsed is not None:
            row["elapsed_s"] = elapsed
            row["elapsed_source"] = ELAPSED_SOURCE_GUEST
    return row


def compare_vs_priors(
    current: Any,
    peers: Iterable[Any],
    *,
    now: str,
) -> dict[str, Any]:
    """Compare one job to recent same-catalog or same-kind/class peers.

    Typical/ETA appear only when at least two succeeded priors have
    real elapsed walls (durable ``wall_elapsed_ms`` when present,
    else guest clocks). Empty and single-prior stay honest.
    """
    current_id = getattr(current, "id", None)
    catalog = _catalog_name(current)
    if catalog:
        matched_by = MATCH_CATALOG
        matched = [
            peer
            for peer in peers
            if getattr(peer, "id", None) != current_id
            and _catalog_name(peer) == catalog
        ]
    else:
        matched_by = MATCH_KIND_CLASS
        matched = [
            peer
            for peer in peers
            if getattr(peer, "id", None) != current_id
            and _catalog_name(peer) is None
            and _same_kind_class(current, peer)
        ]

    priors = [_row(peer, now=now) for peer in matched[:COMPARE_PRIOR_LIMIT]]
    succeeded_elapsed = [
        row["elapsed_s"]
        for row in priors
        if row.get("status") == STATUS_SUCCEEDED and "elapsed_s" in row
    ]
    payload: dict[str, Any] = {
        "id": current_id,
        "source": COMPARE_SOURCE,
        "matched_by": matched_by,
        "this": _row(current, now=now),
        "priors": priors,
        "priors_n": len(priors),
        "typical_n": len(succeeded_elapsed),
    }
    if not priors:
        payload["note"] = COMPARE_NOTE_EMPTY
        return payload
    if len(succeeded_elapsed) >= TYPICAL_MIN_SAMPLES:
        typical = _median(succeeded_elapsed)
        payload["typical_elapsed_s"] = typical
        if getattr(current, "status", None) not in TERMINAL:
            payload["eta_elapsed_s"] = typical
        payload["note"] = COMPARE_NOTE_TYPICAL
        return payload
    payload["note"] = COMPARE_NOTE_THIN
    return payload
