"""Job-scoped event filter and salvage export.

Thinner than a SIEM or iec ``/v1/audit/events``. Memory and durable
trails use the same filter. Empty trails stay empty. Does not stamp
``north_star_done``. Pin 0.5.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

EVENTS_FORMAT_JSON = "json"
EVENTS_FORMAT_JSONL = "jsonl"
EVENTS_FORMATS = frozenset({EVENTS_FORMAT_JSON, EVENTS_FORMAT_JSONL})

# Operator-facing kinds from durable reserve-temporal JSONL, plus
# memory-trail aliases (canceled / succeeded / …). Ellipsis kinds
# (submitted, backed, stage, running, …) match by the same tokens.
KIND_ALIASES: dict[str, frozenset[str]] = {
    "admit": frozenset({"admit"}),
    "stagecompleted": frozenset(
        {"stagecompleted", "stage_completed", "stage-completed", "stage"}
    ),
    "pause": frozenset({"pause", "paused"}),
    "resume": frozenset({"resume", "resumed"}),
    "cancel": frozenset({"cancel", "canceled", "cancelled"}),
    "succeed": frozenset({"succeed", "succeeded", "success"}),
    "fail": frozenset({"fail", "failed", "failure"}),
}

EVENTS_EXPORT_NOTE = (
    "Local salvage of this job's event trail - not a SIEM; "
    "not regulatory defensibility; not iec /v1/audit/events product"
)
MEMORY_EVENTS_NOTE = (
    "Process-memory event trail - not a SIEM; "
    "not regulatory defensibility; not a regulatory audit product"
)
DURABLE_EVENTS_NOTE = (
    "Durable reserve-temporal JSONL trail - not a SIEM; "
    "not regulatory defensibility; not iec /v1/audit/events product"
)


def canon_kind(name: str) -> str:
    """Lowercase alphanumerics only so StageCompleted == stage_completed."""
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def _alias_group(token: str) -> frozenset[str]:
    key = canon_kind(token)
    if not key:
        return frozenset()
    for group in KIND_ALIASES.values():
        if key in {canon_kind(item) for item in group} or key in group:
            return frozenset({canon_kind(item) for item in group} | {key})
    return frozenset({key})


def parse_kind_filter(raw: str | Iterable[str] | None) -> list[str]:
    """Split ``kind=admit,pause`` / repeated values. Empty → no filter."""
    if raw is None:
        return []
    parts: list[str] = []
    if isinstance(raw, str):
        chunks = [raw]
    else:
        chunks = list(raw)
    for chunk in chunks:
        for piece in str(chunk).replace(";", ",").split(","):
            name = piece.strip()
            if name:
                parts.append(name)
    seen: set[str] = set()
    out: list[str] = []
    for name in parts:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def parse_events_format(raw: str | None) -> str:
    value = (raw or EVENTS_FORMAT_JSON).strip().lower()
    if value in ("ndjson", "jsonlines"):
        value = EVENTS_FORMAT_JSONL
    if value not in EVENTS_FORMATS:
        raise ValueError(value)
    return value


def event_kind_tokens(item: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for key in ("event", "kind", "type"):
        value = item.get(key)
        if value is None or value == "":
            continue
        tokens |= _alias_group(str(value))
        tokens.add(canon_kind(str(value)))
    return {tok for tok in tokens if tok}


def event_matches_kinds(item: dict[str, Any], kinds: list[str]) -> bool:
    if not kinds:
        return True
    wanted: set[str] = set()
    for kind in kinds:
        wanted |= _alias_group(kind)
        wanted.add(canon_kind(kind))
    wanted.discard("")
    if not wanted:
        return True
    return bool(event_kind_tokens(item) & wanted)


def filter_events(
    events: list[dict[str, Any]] | None, kinds: list[str] | None
) -> list[dict[str, Any]]:
    trail = [dict(item) for item in events] if events else []
    if not kinds:
        return trail
    return [item for item in trail if event_matches_kinds(item, kinds)]


def export_meta(*, job_id: str, source: str, kinds: list[str]) -> dict[str, Any]:
    return {
        "formats": [EVENTS_FORMAT_JSON, EVENTS_FORMAT_JSONL],
        "json": f"GET /v0/jobs/{job_id}/events?format=json",
        "jsonl": f"GET /v0/jobs/{job_id}/events?format=jsonl",
        "kind_query": "kind=admit,StageCompleted,pause,resume,cancel,succeed,fail",
        "note": EVENTS_EXPORT_NOTE,
        "source": source,
        "kind_filter": list(kinds),
    }


def events_to_jsonl(events: list[dict[str, Any]]) -> bytes:
    """One JSON object per line. Empty trail → empty body (honest)."""
    if not events:
        return b""
    lines = [
        json.dumps(item, separators=(",", ":"), ensure_ascii=False)
        for item in events
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def download_filename(job_id: str, fmt: str) -> str:
    suffix = "jsonl" if fmt == EVENTS_FORMAT_JSONL else "json"
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in job_id)
    return f"sos-job-{safe}-events.{suffix}"
