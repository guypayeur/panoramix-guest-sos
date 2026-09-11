"""Slice B work vocabulary (no engine brands)."""

from __future__ import annotations

WORK_KINDS = frozenset({"job", "stage", "chunk"})
RESOURCE_CLASSES = frozenset({"cpu", "gpu"})
WORK_STATUSES = (
    "queued",
    "running",
    "paused",
    "succeeded",
    "failed",
    "canceled",
)
TERMINAL = frozenset({"succeeded", "failed", "canceled"})
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELED = "canceled"
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
    "stage when known; not a SIEM; not iec /v1/audit/events product"
)
RECOVERABILITY_NOTE = (
    "Cancel/fail does not auto-retry. Re-admit via operator/ctl "
    "reserve-temporal (handoff + payload). Pause/resume remains "
    "durable-only (stub 409 stub_only). Not IFRS17."
)

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
