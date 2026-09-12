"""Optional per-stage elapsed for the durable path-slice timeline.

Prefer hook-provided ``stages[].elapsed_ms`` (or equivalent) when the
number is real. Runtime tip ``9ba95bbb`` (or main, PR #110) can
supply those on durable progress; older tips omit the field.
Else derive from durable ``GET /v0/jobs/{id}/events`` timestamps
when both ends parse. Otherwise omit — never invent.

Not iec planner. Not a forecast. Not SIEM. Does not stamp
``north_star_done``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from sos.compare import parse_job_ts
from sos.events_export import event_matches_kinds

ELAPSED_SOURCE_PROGRESS = "progress"
ELAPSED_SOURCE_EVENTS = "events"

_PROGRESS_STAGE_LIST_KEYS = ("stages", "timeline", "slices")
_MS_KEYS = ("elapsed_ms", "duration_ms")
_SEC_KEYS = ("elapsed_s", "duration_s", "elapsed_sec", "duration_sec")
_TS_KEYS = ("ts", "at", "timestamp", "time")
_NAME_KEYS = ("name", "slice", "stage")


def _as_nonneg_number(value: Any) -> float | None:
    """Parse a real non-negative number. Bool / NaN / negative → omit."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    else:
        return None
    if number < 0 or number != number:
        return None
    return number


def elapsed_ms_from_mapping(item: dict[str, Any] | None) -> int | None:
    """Read an honest elapsed from a progress/event record. Omit if absent."""
    if not isinstance(item, dict):
        return None
    for key in _MS_KEYS:
        if key not in item:
            continue
        number = _as_nonneg_number(item.get(key))
        if number is None:
            return None
        return int(round(number))
    for key in _SEC_KEYS:
        if key not in item:
            continue
        number = _as_nonneg_number(item.get(key))
        if number is None:
            return None
        return int(round(number * 1000))
    return None


def _progress_blobs(durable: dict[str, Any]) -> list[dict[str, Any]]:
    blobs: list[dict[str, Any]] = [durable]
    nested = durable.get("progress")
    if isinstance(nested, dict):
        blobs.append(nested)
    return blobs


def _slice_name(item: dict[str, Any] | None) -> str | None:
    if not isinstance(item, dict):
        return None
    for key in _NAME_KEYS:
        raw = item.get(key)
        if isinstance(raw, str):
            label = raw.strip()
            if label and not label.lstrip("-").isdigit():
                return label
    return None


def _index_for_name(timeline: list[dict[str, Any]], name: str) -> int | None:
    for index, item in enumerate(timeline):
        if item.get("name") == name:
            return index
    return None


def _apply_at(
    out: list[int | None], index: int, ms: int | None
) -> bool:
    if ms is None or index < 0 or index >= len(out):
        return False
    out[index] = ms
    return True


def elapsed_from_progress(
    durable: dict[str, Any] | None, timeline: list[dict[str, Any]]
) -> list[int | None]:
    """Per-index elapsed_ms from durable progress. Empty if none are honest."""
    if not isinstance(durable, dict) or not timeline:
        return []
    n = len(timeline)
    out: list[int | None] = [None] * n
    found = False
    for blob in _progress_blobs(durable):
        for key in ("stage_elapsed_ms",):
            raw = blob.get(key)
            if not isinstance(raw, list) or not raw:
                continue
            for index, value in enumerate(raw[:n]):
                if _apply_at(out, index, elapsed_ms_from_mapping({"elapsed_ms": value})):
                    found = True
        for key in _PROGRESS_STAGE_LIST_KEYS:
            raw = blob.get(key)
            if not isinstance(raw, list):
                continue
            for index, item in enumerate(raw[:n]):
                if not isinstance(item, dict):
                    continue
                ms = elapsed_ms_from_mapping(item)
                if ms is None:
                    continue
                name = _slice_name(item)
                if name:
                    named = _index_for_name(timeline, name)
                    if named is not None:
                        out[named] = ms
                        found = True
                        continue
                if _apply_at(out, index, ms):
                    found = True
    return out if found else []


def _event_ts(item: dict[str, Any]) -> datetime | None:
    for key in _TS_KEYS:
        if key not in item:
            continue
        parsed = parse_job_ts(item.get(key))
        if parsed is not None:
            return parsed
    return None


def _is_admit(item: dict[str, Any]) -> bool:
    return event_matches_kinds(item, ["admit"])


def _is_stage_complete(item: dict[str, Any]) -> bool:
    return event_matches_kinds(item, ["StageCompleted"])


def _completed_index(
    item: dict[str, Any], timeline: list[dict[str, Any]]
) -> int | None:
    raw = item.get("stages_completed")
    number = _as_nonneg_number(raw) if raw is not None else None
    if number is not None and number >= 1:
        return int(number) - 1
    name = _slice_name(item)
    if name:
        return _index_for_name(timeline, name)
    for key in ("stage", "index"):
        idx = _as_nonneg_number(item.get(key)) if key in item else None
        if idx is not None and idx >= 1:
            return int(idx) - 1
    return None


def elapsed_from_events(
    events: Iterable[dict[str, Any]] | None,
    timeline: list[dict[str, Any]],
) -> list[int | None]:
    """Wall ms between admit / StageCompleted timestamps. Omit if incomplete.

    Pause / resume / cancel / succeed / fail are not stage boundaries.
    In-flight current slices stay omitted (no invented now-minus-start).
    """
    if not events or not timeline:
        return []
    stamped: list[tuple[datetime, dict[str, Any]]] = []
    for item in events:
        if not isinstance(item, dict):
            continue
        ts = _event_ts(item)
        if ts is None:
            continue
        stamped.append((ts, item))
    if len(stamped) < 2:
        return []

    n = len(timeline)
    out: list[int | None] = [None] * n
    found = False
    sequential = 0
    start: datetime | None = None
    for ts, item in stamped:
        direct = elapsed_ms_from_mapping(item) if _is_stage_complete(item) else None
        if _is_admit(item) and start is None:
            start = ts
            continue
        if not _is_stage_complete(item):
            continue
        index = _completed_index(item, timeline)
        if index is None:
            index = sequential
        sequential = max(sequential, index + 1)
        if direct is not None and _apply_at(out, index, direct):
            found = True
        elif start is not None and out[index] is None:
            delta_ms = int(round((ts - start).total_seconds() * 1000))
            if delta_ms >= 0 and _apply_at(out, index, delta_ms):
                found = True
        start = ts
    return out if found else []


def _write_elapsed(timeline: list[dict[str, Any]], values: list[int | None]) -> bool:
    wrote = False
    for item, ms in zip(timeline, values):
        if ms is None:
            continue
        item["elapsed_ms"] = ms
        wrote = True
    return wrote


def attach_timeline_elapsed(
    timeline: list[dict[str, Any]],
    *,
    durable: dict[str, Any] | None = None,
    events: Iterable[dict[str, Any]] | None = None,
    events_durable: bool = False,
) -> str | None:
    """Mutate timeline items with ``elapsed_ms`` when honest. Return source."""
    if not timeline:
        return None
    from_progress = elapsed_from_progress(durable, timeline)
    if from_progress and _write_elapsed(timeline, from_progress):
        return ELAPSED_SOURCE_PROGRESS
    if events_durable:
        from_events = elapsed_from_events(events, timeline)
        if from_events and _write_elapsed(timeline, from_events):
            return ELAPSED_SOURCE_EVENTS
    return None
