"""Slice B work vocabulary (no engine brands)."""

from __future__ import annotations

WORK_KINDS = frozenset({"job", "stage", "chunk"})
RESOURCE_CLASSES = frozenset({"cpu", "gpu"})
WORK_STATUSES = (
    "queued",
    "running",
    "paused",
    "held",
    "succeeded",
    "failed",
    "canceled",
)
TERMINAL = frozenset({"succeeded", "failed", "canceled"})
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_HELD = "held"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELED = "canceled"
# Non-terminal hold. Overlay when ctl/hook reports held; omit when missing.
HELD_OR_PAUSED = frozenset({STATUS_PAUSED, STATUS_HELD})
# Operator/ctl pointer — default guest does not invoke this.
# Opt-in lab adapter may invoke reserve-temporal locally; not compute-work.
CTL_PAUSE_RESUME = (
    "python3 -m runtime.apply reserve-temporal pause|resume --id cw_…"
)
CTL_CANCEL = (
    "python3 -m runtime.apply reserve-temporal cancel --id cw_…"
)
CTL_PROGRESS = (
    "python3 -m runtime.apply reserve-temporal progress --id cw_…"
)
CTL_EVENTS = (
    "python3 -m runtime.apply reserve-temporal events --id cw_…"
)
CTL_ADMIT = (
    "python3 -m runtime.apply reserve-temporal admit --handoff JSON"
)
FAILED_OR_CANCELED = frozenset({STATUS_FAILED, STATUS_CANCELED})
LAST_EVENTS_N = 5
TERMINAL_NOTE = (
    "Terminal/failure summary — status + message + optional last events / "
    "stage / next_action / valuation when the hook supplies them; "
    "not a SIEM; not iec /v1/audit/events product"
)
IEC_PAUSE_LIMIT_NOTE = (
    "iec-local pause is pause-before-start (single-activity). "
    "Mid-flight pause/held only when the hook/ctl supplies them — "
    "omitted when missing; never invented. Runtime tip d9b9948+. "
    "pause_signaled / resume_signaled pass through when ctl returns "
    "them (runtime tip e2f41fd+) — omit when missing; never invent held"
)
RECOVERABILITY_NOTE = (
    "Cancel/fail does not auto-retry. Re-admit is a new admit "
    "(POST /v0/jobs/{id}/re-admit when a durable hook is active; "
    "else operator/ctl reserve-temporal). No resume-from-failed. "
    "Fail-closed without hook or when payload is missing "
    "(no silent stub re-admit). Pause/resume remains durable-only "
    "(stub 409 stub_only). Not SIEM. Not IFRS17."
)
HANDOFF_DOCS_NOTE = (
    "Operator reminders for handoff + payload export, recoverability / "
    "re-admit, and lab-compose (reserve-temporal or iec-local). Clarity "
    "only — not a second control plane. Guest does not run IFRS17 math. "
    "Not #70 Done. Not SIEM. Not IFRS17-in-guest."
)
LAB_COMPOSE_DOCS = "docs/lab-compose.md"
LAB_COMPOSE_SCRIPT = "scripts/lab_compose_reserve_temporal.py"

DEMO_ECHO = "echo"
DEMO_SLEEP = "sleep"
DEMO_RESERVE = "reserve"
LOCAL_DEMOS = frozenset({DEMO_ECHO, DEMO_SLEEP, DEMO_RESERVE})
DEFAULT_ECHO_MESSAGE = "ok"
DEFAULT_SLEEP_SECONDS = 2
MAX_SLEEP_SECONDS = 30.0

# Reserve-shaped work request — small stable param set, thinner than IFRS17.
# Hardcoded catalogs; do not import runtime; do not vendor iec.
#
# Mirrored from panoramix-runtime **main** helpers (docs/reserve.md):
# runtime.reserve.recorded_params, live_params, parity_params, digest_for.
# Do not change RECORDED_PAYLOAD_DIGEST / PARITY_PAYLOAD_DIGEST unless
# those helpers change on main.
RESERVE_WORKLOAD = "reserve"
RESERVE_CATALOG_RECORDED = "recorded"
RESERVE_CATALOG_LIVE = "live"
RESERVE_CATALOG_PARITY = "parity"
RESERVE_CATALOGS = frozenset(
    {RESERVE_CATALOG_RECORDED, RESERVE_CATALOG_LIVE, RESERVE_CATALOG_PARITY}
)
RESERVE_CATALOG_ALIASES = {
    "recorded": RESERVE_CATALOG_RECORDED,
    "ci": RESERVE_CATALOG_RECORDED,
    "small": RESERVE_CATALOG_RECORDED,
    "live": RESERVE_CATALOG_LIVE,
    "lab": RESERVE_CATALOG_LIVE,
    "heavy": RESERVE_CATALOG_LIVE,
    "parity": RESERVE_CATALOG_PARITY,
    "parity-scale": RESERVE_CATALOG_PARITY,
}
# Same-job iec identity (runtime #146 / docs/iec-local.md @ d480dc8).
# Not a thinner recorded/live/parity catalog. Guest copies the digest;
# it does not run IFRS17 math. Runtime binding wraps the operator iec
# checkout (POST /v1/jobs). Alias same-job → reserve_ifrs17.
RESERVE_CATALOG_SAME_JOB = "reserve_ifrs17"
SAME_JOB_CATALOG_ALIASES = {
    "reserve_ifrs17": RESERVE_CATALOG_SAME_JOB,
    "same-job": RESERVE_CATALOG_SAME_JOB,
}
IEC_METHOD_PIN = "4d5d44d3747b0700eba7b4af1987184f76cc56a8"
IEC_SOURCE_FILE = "reserve_ifrs17/reserve_ifrs17.adsl"
IEC_MODE = "STANDARD"
IEC_WORKLOAD = "reserve_ifrs17"
SAME_JOB_PARAMS: dict[str, str] = {
    "mode": IEC_MODE,
    "revision": IEC_METHOD_PIN,
    "source_file": IEC_SOURCE_FILE,
    "workload": IEC_WORKLOAD,
}
# sha256 of canonical JSON (sort_keys, separators=(",", ":")) of
# same_job_payload. Must equal runtime.reserve_iec.SAME_JOB_DIGEST
# on panoramix-runtime main @ d480dc8 (docs/iec-local.md).
SAME_JOB_PAYLOAD_DIGEST = (
    "sha256:1a1e14a08f08b7fd310c335bf863b475c86919cf0e59e9326207b49e8ae2206c"
)
SAME_JOB_CANONICAL_JSON = (
    '{"mode":"STANDARD",'
    '"revision":"4d5d44d3747b0700eba7b4af1987184f76cc56a8",'
    '"source_file":"reserve_ifrs17/reserve_ifrs17.adsl",'
    '"workload":"reserve_ifrs17"}'
)
CTL_IEC_LOCAL = "iec-local"
CTL_IEC_LOCAL_PORT = 19216
CTL_IEC_LOCAL_ADMIT = (
    "python3 -m runtime.apply iec-local admit --handoff JSON"
)
LAB_COMPOSE_IEC_DOCS = "docs/lab-compose-iec-local.md"
LAB_COMPOSE_IEC_SCRIPT = "scripts/lab_compose_iec_local.py"
RESERVE_PARAM_KEYS = (
    "accounts",
    "horizon",
    "paths",
    "seed",
    "lapse_bps",
    "discount_bps",
)
RECORDED_PARAMS: dict[str, int | str] = {
    "workload": RESERVE_WORKLOAD,
    "accounts": 48,
    "horizon": 12,
    "paths": 96,
    "seed": 17070,
    "lapse_bps": 80,
    "discount_bps": 300,
}
LIVE_PARAMS: dict[str, int | str] = {
    "workload": RESERVE_WORKLOAD,
    "accounts": 640,
    "horizon": 40,
    "paths": 2048,
    "seed": 17070,
    "lapse_bps": 80,
    "discount_bps": 300,
}
# Third catalog. Mirrors runtime.reserve.parity_params on main. Same keys; not IFRS17.
PARITY_PARAMS: dict[str, int | str] = {
    "workload": RESERVE_WORKLOAD,
    "accounts": 2048,
    "horizon": 64,
    "paths": 4096,
    "seed": 17070,
    "lapse_bps": 80,
    "discount_bps": 300,
}
# sha256 of canonical JSON (sort_keys, separators=(",", ":")) of payload_for
# recorded catalog. Must equal runtime.reserve.digest_for(recorded_params())
# on panoramix-runtime main (docs/reserve.md).
RECORDED_PAYLOAD_DIGEST = (
    "sha256:77e9299f4b8ea4aeed46f71b91cc947d56e9bd169d795e70845123fef53d7e4e"
)
LIVE_PAYLOAD_DIGEST = (
    "sha256:9207915bfa0c563ccc6d167ef79db47c5318219bd0269aae5c4b8313d2fceea6"
)
# Must equal runtime.reserve.digest_for(parity_params()) on panoramix-runtime
# main (docs/reserve.md).
PARITY_PAYLOAD_DIGEST = (
    "sha256:e180d2c2e3589b8762f92efa1bedb3d53ffeeb16648581ba13d537bcd3311102"
)
RECORDED_CANONICAL_JSON = (
    '{"accounts":48,"discount_bps":300,"horizon":12,"lapse_bps":80,'
    '"paths":96,"seed":17070,"workload":"reserve"}'
)
PARITY_CANONICAL_JSON = (
    '{"accounts":2048,"discount_bps":300,"horizon":64,"lapse_bps":80,'
    '"paths":4096,"seed":17070,"workload":"reserve"}'
)

# Local stub UX only — not part of payload_digest.
DEFAULT_RESERVE_LABEL = "reserve-shaped"
DEFAULT_RESERVE_STAGES = 3
MIN_RESERVE_STAGES = 2
MAX_RESERVE_STAGES = 8
DEFAULT_RESERVE_SECONDS = 6
MAX_RESERVE_SECONDS = MAX_SLEEP_SECONDS
BACKED_STUB = "stub"
BACKED_RUNTIME = "runtime"
RESERVE_STAGE_NAMES = (
    "admit",
    "project",
    "fold",
    "review",
    "close",
    "archive",
    "audit",
    "done",
)


def reserve_stage_names(stages: int) -> tuple[str, ...]:
    """Stub labels for the reserve-shaped UX seed. Not iec grammar stages."""
    n = max(1, int(stages))
    return RESERVE_STAGE_NAMES[:n]


# Day-one static owners for durable reserve-temporal path-slices (four kernel
# stages). Documented strings only — not Slack, not a live team directory.
PATH_SLICE_OWNERS: tuple[tuple[str, str], ...] = (
    ("admit", "ctl / admit"),
    ("project", "kernel / project"),
    ("fold", "kernel / fold"),
    ("complete", "ctl / complete"),
)
CATALOG_CROSSCHECK_NOTE = (
    "Catalog identity already on the job — cross-check only; "
    "not a data-catalog product"
)
OWNERSHIP_NOTE = (
    "Static day-one path-slice owners — not Slack; "
    "not a live team directory"
)


def short_digest(digest: str | None) -> str:
    """Operator-facing digest prefix (sha256:<8 hex>…)."""
    raw = str(digest or "").strip()
    if not raw:
        return ""
    hex_part = raw[7:] if raw.startswith("sha256:") else raw
    return "sha256:" + hex_part[:8] + "…"


# Optional ctl honesty fields. Omit when missing / unknown / empty.
# Guest must not invent these; wire them when runtime/ctl supplies them
# (iec-local tip d9b9948+ pause_limit / already_canceled; e2f41fd+
# pause_signaled / resume_signaled; held + FAILED next_action when
# ctl grows them).
HONESTY_PASSTHROUGH_KEYS: tuple[str, ...] = (
    "held",
    "held_reason",
    "pause_limit",
    "can_pause",
    "can_resume",
    "pause_resume",
    "pause_signaled",
    "resume_signaled",
    "is_paused",
    "held_while_paused",
    "next_action",
    "error_code",
    "valuation",
    "valuation_status",
    "stage_name",
    "failure_stage",
)
# Pause/resume POST outcomes. Sticky until ctl contradicts them so a
# later status poll that omits the keys does not hide the signal.
HONESTY_SIGNAL_KEYS: frozenset[str] = frozenset(
    {
        "pause_signaled",
        "resume_signaled",
        "is_paused",
        "held_while_paused",
    }
)

_HONESTY_ALIASES: dict[str, str] = {
    "nextAction": "next_action",
    "errorCode": "error_code",
    "valuationStatus": "valuation_status",
    "stageName": "stage_name",
    "failureStage": "failure_stage",
    "heldReason": "held_reason",
    "pauseLimit": "pause_limit",
    "canPause": "can_pause",
    "canResume": "can_resume",
    "pauseResume": "pause_resume",
    "pauseSignaled": "pause_signaled",
    "resumeSignaled": "resume_signaled",
    "isPaused": "is_paused",
    "heldWhilePaused": "held_while_paused",
}


def _honesty_value_ok(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and value.strip().lower() in {"", "unknown"}:
        return False
    return True


def extract_lifecycle_overlay(*blobs: object) -> dict[str, object]:
    """Collect optional pause/held/failure honesty fields. Omit when missing."""
    out: dict[str, object] = {}
    for blob in blobs:
        if not isinstance(blob, dict):
            continue
        for src, dest in _HONESTY_ALIASES.items():
            if dest in out:
                continue
            if src in blob and _honesty_value_ok(blob[src]):
                out[dest] = blob[src]
        for key in HONESTY_PASSTHROUGH_KEYS:
            if key in out:
                continue
            if key in blob and _honesty_value_ok(blob[key]):
                out[key] = blob[key]
        nested_error = blob.get("error")
        if isinstance(nested_error, dict):
            for key in ("next_action", "error_code", "stage_name", "failure_stage"):
                if key not in out and key in nested_error and _honesty_value_ok(
                    nested_error[key]
                ):
                    out[key] = nested_error[key]
            if "next_action" not in out and _honesty_value_ok(
                nested_error.get("nextAction")
            ):
                out["next_action"] = nested_error["nextAction"]
        nested_progress = blob.get("progress")
        if isinstance(nested_progress, dict):
            extra = extract_lifecycle_overlay(nested_progress)
            for key, value in extra.items():
                out.setdefault(key, value)
    return out
