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

# Reserve-shaped UX seed (not IFRS17 math; not the iec baseline).
DEFAULT_RESERVE_LABEL = "reserve-shaped"
DEFAULT_RESERVE_STAGES = 3
MIN_RESERVE_STAGES = 2
MAX_RESERVE_STAGES = 8
DEFAULT_RESERVE_SECONDS = 6
MAX_RESERVE_SECONDS = MAX_SLEEP_SECONDS
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
