"""Inert runtime admit/cancel hook — awaiting a platform-stamped guest path.

Operator/ctl takes GET /v0/jobs/{id}/handoff plus /payload and admits that
opaque tuple to panoramix-runtime ``submit_work`` / ``parse_work``. Compute
mesh is ``from: compute-job`` → ``to: sos`` (engine calls guest). This guest
does not call Ray / Temporal / AWS.

Runtime main documents no guest-callable submit env (no PLATFORM_COMPUTE_*,
no PLATFORM_RAY_*). Until a stamp exists, ``admit`` / ``cancel`` / ``status``
return None/False and JobStore falls back to the in-process stub.

Does not close #70. Does not unlock #61 / #29.
"""

from __future__ import annotations

from typing import Any, Protocol


class RuntimeHandoffHook(Protocol):
    """Admit/cancel/status against runtime compute when a stamp exists."""

    def admit(
        self, handoff: dict[str, str], payload_bytes: bytes | None
    ) -> dict[str, Any] | None:
        """Return an opaque runtime ref if admitted, else None (stub fallback)."""

    def cancel(self, job_id: str, runtime_ref: dict[str, Any] | None) -> bool:
        """True if runtime was signaled. False → caller still cancels locally."""

    def status(self, job_id: str, runtime_ref: dict[str, Any] | None) -> str | None:
        """Runtime lifecycle status, or None if unknown / not backed."""


class InertRuntimeHandoffHook:
    """Default hook: always fall back to the local stub.

    TODO: awaiting runtime stamp of a guest-callable submit path. Do not
    invent PLATFORM_COMPUTE_* / PLATFORM_RAY_* / engine URL env here.
    """

    def admit(
        self, handoff: dict[str, str], payload_bytes: bytes | None
    ) -> dict[str, Any] | None:
        return None

    def cancel(self, job_id: str, runtime_ref: dict[str, Any] | None) -> bool:
        return False

    def status(self, job_id: str, runtime_ref: dict[str, Any] | None) -> str | None:
        return None
