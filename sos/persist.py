"""Local lab persistence for guest job history.

Stores enough identity for compare and recoverability: catalog / kind /
class, created/updated, status, digests, payload bytes when known, and
handoff / runtime_ref pointers. Reloads recent records on start.

Default dir is ``.sos/jobs``. Override with ``PANORAMIX_SOS_JOBS_DIR``.
Unset keeps the default. ``off`` / ``0`` / ``disabled`` / ``false`` /
empty **fails closed** (in-process only; no files; no invented priors).
Unwritable dirs also fail closed.

Does not invent typical/ETA (those stay computed at compare time).
Does not claim SIEM / six-month audit / IFRS17. Not a cross-host DB.
Does not close #70 / #78. Does not unlock cloud. Pin stays 0.5.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from sos.handoff import DIGEST_RE
from sos.handoff_vocab import RESOURCE_CLASSES, WORK_KINDS, WORK_STATUSES

ENV_JOBS_DIR = "PANORAMIX_SOS_JOBS_DIR"
DEFAULT_JOBS_DIR = Path(".sos") / "jobs"
DISABLED_TOKENS = frozenset({"", "off", "0", "false", "no", "disabled", "none", "-"})
RECORD_VERSION = 1
RECENT_LIMIT = 200
PERSIST_EVENTS_MAX = 64
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
RESTART_LOST_MESSAGE = (
    "guest restarted; in-process work was not resumed "
    "(no invented status or wall). Not a SIEM."
)
RESTART_LOST_ERROR = "lost_on_restart"
HISTORY_PERSIST_NOTE = (
    "Local lab job records for compare / recoverability. "
    "Fail-closed if disabled or unwritable. Reloads recent "
    "succeeded priors across guest restart. Does not invent "
    "typical/ETA. Not a SIEM. Not a six-month audit product. "
    "Not a cross-host DB. Not #70 Done."
)


def jobs_dir_from_env(env: Mapping[str, str] | None = None) -> Path | None:
    """Return the intended persist dir, or None when persistence is disabled.

    Missing env → default ``.sos/jobs``. Disabled tokens / empty → None
    (fail closed). Does not mkdir; ``prepare_jobs_dir`` does that.
    """
    source = os.environ if env is None else env
    if ENV_JOBS_DIR not in source:
        return Path(DEFAULT_JOBS_DIR)
    raw = str(source.get(ENV_JOBS_DIR) or "").strip()
    if raw.lower() in DISABLED_TOKENS:
        return None
    return Path(raw).expanduser()


def prepare_jobs_dir(path: Path | str | None) -> Path | None:
    """Create and probe the persist dir. None on any OSError (fail closed)."""
    if path is None:
        return None
    root = Path(path).expanduser()
    probe: Path | None = None
    try:
        root.mkdir(parents=True, exist_ok=True)
        root = root.resolve()
        if not root.is_dir():
            return None
        probe = root / f".probe.{os.getpid()}"
        probe.write_text("", encoding="utf-8")
    except OSError:
        return None
    finally:
        if probe is not None:
            try:
                probe.unlink()
            except OSError:
                pass
    return root


def describe_history_persist(persist_dir: Path | str | None) -> dict[str, Any]:
    """Honest /v0/info overlay. No pretend when persistence is disabled."""
    enabled = persist_dir is not None
    return {
        "enabled": enabled,
        "env": ENV_JOBS_DIR,
        "default": str(DEFAULT_JOBS_DIR),
        "dir": str(persist_dir) if enabled else None,
        "disable": "off",
        "note": HISTORY_PERSIST_NOTE,
    }


def job_to_record(job: Any) -> dict[str, Any]:
    """Projection for disk. No typical/ETA. No SIEM claims."""
    payload: dict[str, Any] = {
        "v": RECORD_VERSION,
        "id": getattr(job, "id", ""),
        "kind": getattr(job, "kind", ""),
        "class": getattr(job, "resource_class", None) or getattr(job, "class", ""),
        "payload_digest": getattr(job, "payload_digest", ""),
        "status": getattr(job, "status", ""),
        "created_at": getattr(job, "created_at", ""),
        "updated_at": getattr(job, "updated_at", ""),
    }
    message = getattr(job, "message", None)
    if message is not None:
        payload["message"] = message
    error = getattr(job, "error", None)
    if error is not None:
        payload["error"] = error
    local = getattr(job, "local", None)
    if isinstance(local, dict) and local:
        payload["local"] = dict(local)
    blob = getattr(job, "payload_bytes", None)
    if isinstance(blob, (bytes, bytearray)):
        payload["payload_hex"] = bytes(blob).hex()
    runtime_ref = getattr(job, "runtime_ref", None)
    if isinstance(runtime_ref, dict) and runtime_ref:
        payload["runtime_ref"] = dict(runtime_ref)
    events = getattr(job, "events", None)
    if isinstance(events, list) and events:
        payload["events"] = [dict(item) for item in events[-PERSIST_EVENTS_MAX:] if isinstance(item, dict)]
    return payload


def record_to_job_kwargs(record: Any) -> dict[str, Any] | None:
    """Validated Job kwargs, or None if the record is unusable (skip)."""
    if not isinstance(record, dict):
        return None
    if record.get("v") != RECORD_VERSION:
        return None
    job_id = str(record.get("id") or "").strip()
    if not SAFE_ID_RE.fullmatch(job_id):
        return None
    kind = str(record.get("kind") or "").strip().lower()
    if kind not in WORK_KINDS:
        return None
    resource_class = str(record.get("class") or "").strip().lower()
    if resource_class not in RESOURCE_CLASSES:
        return None
    digest = str(record.get("payload_digest") or "").strip().lower()
    if not DIGEST_RE.fullmatch(digest):
        return None
    status = str(record.get("status") or "").strip().lower()
    if status not in WORK_STATUSES:
        return None
    created_at = str(record.get("created_at") or "").strip()
    updated_at = str(record.get("updated_at") or "").strip()
    if not created_at or not updated_at:
        return None
    local = record.get("local")
    if local is not None and not isinstance(local, dict):
        return None
    runtime_ref = record.get("runtime_ref")
    if runtime_ref is not None and not isinstance(runtime_ref, dict):
        return None
    events_raw = record.get("events")
    events: list[dict[str, Any]] = []
    if isinstance(events_raw, list):
        for item in events_raw[-PERSIST_EVENTS_MAX:]:
            if isinstance(item, dict) and item.get("event") is not None:
                events.append(dict(item))
    payload_bytes: bytes | None = None
    hex_raw = record.get("payload_hex")
    if isinstance(hex_raw, str) and hex_raw:
        try:
            payload_bytes = bytes.fromhex(hex_raw)
        except ValueError:
            payload_bytes = None
    kwargs: dict[str, Any] = {
        "id": job_id,
        "kind": kind,
        "resource_class": resource_class,
        "payload_digest": digest,
        "status": status,
        "created_at": created_at,
        "updated_at": updated_at,
        "message": record.get("message"),
        "error": record.get("error"),
        "local": dict(local) if isinstance(local, dict) else None,
        "payload_bytes": payload_bytes,
        "runtime_ref": dict(runtime_ref) if isinstance(runtime_ref, dict) else None,
        "events": events,
    }
    return kwargs


def write_record(persist_dir: Path, record: dict[str, Any]) -> bool:
    """Atomic replace of ``{id}.json``. False on failure (fail closed)."""
    job_id = str(record.get("id") or "")
    if not SAFE_ID_RE.fullmatch(job_id):
        return False
    dest = persist_dir / f"{job_id}.json"
    tmp = persist_dir / f".{job_id}.{os.getpid()}.tmp"
    try:
        tmp.write_text(
            json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, dest)
        return True
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        return False


def _updated_sort_key(record: dict[str, Any]) -> str:
    return str(record.get("updated_at") or "")


def load_recent_records(
    persist_dir: Path, *, limit: int = RECENT_LIMIT
) -> list[dict[str, Any]]:
    """Load usable records. Skip corrupt / unknown versions. Newest first."""
    if not persist_dir.is_dir():
        return []
    loaded: list[dict[str, Any]] = []
    try:
        names = list(persist_dir.glob("*.json"))
    except OSError:
        return []
    for path in names:
        if path.name.startswith("."):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if record_to_job_kwargs(raw) is None:
            continue
        loaded.append(raw)
    loaded.sort(key=_updated_sort_key, reverse=True)
    return loaded[: max(0, int(limit))]
