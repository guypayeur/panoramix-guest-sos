"""Inert runtime admit/cancel/pause/resume hook.

Transport today is **operator/ctl-mediated only**. This guest emits
WorkHandoff JSON (kind/class/payload_digest + status/id). It does not
open guest→ctl HTTP for compute-work, does not call
``runtime.apply compute-work``, and does not set env that adds mesh
destinations. Mesh on local-sos-compute is ``from: compute-job`` →
``to: sos`` (worker calls Unit).

Do not invent PLATFORM_RAY_* / engine URLs / guest-callable ctl HTTP.
``admit`` / ``cancel`` / ``status`` / ``pause`` / ``resume`` stay no-ops;
JobStore falls back to the in-process stub. Temporal-local
admit/status/cancel/pause/resume is operator/ctl via reserve-temporal;
this hook stays inert. Optional guest→ctl loopback is deferred until a
documented safe loopback admit exists.

Does not close #70. Does not close #78. Does not unlock #61 / #29.
"""

from __future__ import annotations

from typing import Any, Protocol


class RuntimeHandoffHook(Protocol):
    """Admit/cancel/status/pause/resume when an operator injects a live hook."""

    def admit(
        self, handoff: dict[str, str], payload_bytes: bytes | None
    ) -> dict[str, Any] | None:
        """Return an opaque runtime ref if admitted, else None (stub fallback)."""

    def cancel(self, job_id: str, runtime_ref: dict[str, Any] | None) -> bool:
        """True if runtime was signaled. False → caller still cancels locally."""

    def status(self, job_id: str, runtime_ref: dict[str, Any] | None) -> str | None:
        """Runtime lifecycle status, or None if unknown / not backed."""

    def pause(self, job_id: str, runtime_ref: dict[str, Any] | None) -> bool:
        """True if runtime pause was signaled. Default: not durable."""
        return False

    def resume(self, job_id: str, runtime_ref: dict[str, Any] | None) -> bool:
        """True if runtime resume was signaled. Default: not durable."""
        return False


class InertRuntimeHandoffHook:
    """Default hook: always fall back to the local stub.

    Transport is operator/ctl-mediated. Do not add guest→ctl HTTP,
    PLATFORM_MESH_* destinations, PLATFORM_RAY_*, engine URLs, or a call
    to runtime.apply compute-work. pause/resume stay False.
    """

    def admit(
        self, handoff: dict[str, str], payload_bytes: bytes | None
    ) -> dict[str, Any] | None:
        return None

    def cancel(self, job_id: str, runtime_ref: dict[str, Any] | None) -> bool:
        return False

    def status(self, job_id: str, runtime_ref: dict[str, Any] | None) -> str | None:
        return None

    def pause(self, job_id: str, runtime_ref: dict[str, Any] | None) -> bool:
        return False

    def resume(self, job_id: str, runtime_ref: dict[str, Any] | None) -> bool:
        return False
