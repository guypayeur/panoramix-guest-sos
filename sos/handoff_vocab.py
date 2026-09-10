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
LOCAL_DEMOS = frozenset({DEMO_ECHO, DEMO_SLEEP})
DEFAULT_ECHO_MESSAGE = "ok"
DEFAULT_SLEEP_SECONDS = 2
MAX_SLEEP_SECONDS = 30.0
