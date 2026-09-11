"""Slice B work vocabulary (no engine brands)."""

from __future__ import annotations

WORK_KINDS = frozenset({"job", "stage", "chunk"})
RESOURCE_CLASSES = frozenset({"cpu", "gpu"})
WORK_STATUSES = (
    "queued",
    "running",
    "succeeded",
    "failed",
    "canceled",
)
TERMINAL = frozenset({"succeeded", "failed", "canceled"})
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELED = "canceled"

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
# Mirrored from panoramix-runtime **main** helpers (see docs/reserve.md):
# runtime.reserve.recorded_params, live_params, digest_for.
# Do not change RECORDED_PAYLOAD_DIGEST unless those helpers change on main.
RESERVE_WORKLOAD = "reserve"
RESERVE_CATALOG_RECORDED = "recorded"
RESERVE_CATALOG_LIVE = "live"
RESERVE_CATALOGS = frozenset({RESERVE_CATALOG_RECORDED, RESERVE_CATALOG_LIVE})
RESERVE_CATALOG_ALIASES = {
    "recorded": RESERVE_CATALOG_RECORDED,
    "ci": RESERVE_CATALOG_RECORDED,
    "small": RESERVE_CATALOG_RECORDED,
    "live": RESERVE_CATALOG_LIVE,
    "lab": RESERVE_CATALOG_LIVE,
    "heavy": RESERVE_CATALOG_LIVE,
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
# sha256 of canonical JSON (sort_keys, separators=(",", ":")) of payload_for
# recorded catalog. Must equal runtime.reserve.digest_for(recorded_params())
# on panoramix-runtime main (docs/reserve.md).
RECORDED_PAYLOAD_DIGEST = (
    "sha256:77e9299f4b8ea4aeed46f71b91cc947d56e9bd169d795e70845123fef53d7e4e"
)
LIVE_PAYLOAD_DIGEST = (
    "sha256:9207915bfa0c563ccc6d167ef79db47c5318219bd0269aae5c4b8313d2fceea6"
)
RECORDED_CANONICAL_JSON = (
    '{"accounts":48,"discount_bps":300,"horizon":12,"lapse_bps":80,'
    '"paths":96,"seed":17070,"workload":"reserve"}'
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
