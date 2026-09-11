"""Runtime admit/cancel/pause/resume/progress/events hook.

Transport stays **operator/ctl-mediated**. This guest emits WorkHandoff
JSON (kind/class/payload_digest + status/id). It does not open
guest→ctl HTTP for compute-work, does not call
``runtime.apply compute-work``, and does not set env that adds mesh
destinations. Mesh on local-sos-compute is ``from: compute-job`` →
``to: sos`` (worker calls Unit).

Do not invent PLATFORM_RAY_* / engine URLs / guest-callable ctl HTTP.
Default ``InertRuntimeHandoffHook`` stays no-op; JobStore falls back to
the in-process stub. An **opt-in lab adapter** (``PANORAMIX_RUNTIME_ROOT``)
may inject ``LabReserveTemporalHook`` on this same seam and invoke
local ``python3 -m runtime.apply reserve-temporal``.
That is not a second control plane and not mesh ctl HTTP. Unset or
missing runtime root fails closed (inert).

Does not close #70. Does not close #78. Does not unlock #61 / #29.
Does not stamp north_star_done. Cloud stays locked.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class RuntimeHandoffHook(Protocol):
    """Admit/cancel/status/pause/resume/progress/events when an operator injects a live hook."""

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

    def progress(
        self, job_id: str, runtime_ref: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Durable stage/chunk counters, or None if unknown / not backed.

        Prefer this over scraping counters from ``status()``. Inert returns None.
        """
        return None

    def events(
        self, job_id: str, runtime_ref: dict[str, Any] | None
    ) -> dict[str, Any] | list[Any] | None:
        """Durable job-scoped event trail, or None if unknown / not backed.

        Prefer this over scraping events from ``status()``. Inert returns None.
        """
        return None


class InertRuntimeHandoffHook:
    """Default hook: always fall back to the local stub.

    Transport is operator/ctl-mediated. Do not add guest→ctl HTTP,
    PLATFORM_MESH_* destinations, PLATFORM_RAY_*, engine URLs, or a call
    to runtime.apply compute-work. pause/resume stay False; progress and
    events stay None (stub / process-memory fallback). The default hook
    stays inert unless an operator injects a hook or opts in the lab
    adapter via PANORAMIX_RUNTIME_ROOT.
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

    def progress(
        self, job_id: str, runtime_ref: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        return None

    def events(
        self, job_id: str, runtime_ref: dict[str, Any] | None
    ) -> dict[str, Any] | list[Any] | None:
        return None


def resolve_runtime_hook(
    env: Mapping[str, str] | None = None,
) -> RuntimeHandoffHook:
    """Inert unless PANORAMIX_RUNTIME_ROOT is a usable runtime checkout.

    Fail closed when the env is unset or the root is missing. Does not
    close #70 / #78. Does not unlock cloud.
    """
    from sos.lab_ctl import lab_hook_from_env

    hook = lab_hook_from_env(env)
    if hook is None:
        return InertRuntimeHandoffHook()
    return hook
