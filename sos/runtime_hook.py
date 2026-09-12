"""Runtime admit/cancel/pause/resume/progress/events hook.

Transport stays **operator/ctl-mediated**. This guest emits WorkHandoff
JSON (kind/class/payload_digest + status/id). It does not open
guest→ctl HTTP for compute-work, does not call
``runtime.apply compute-work``, and does not set env that adds mesh
destinations. Mesh on local-sos-compute is ``from: compute-job`` →
``to: sos`` (worker calls Unit).

Do not invent PLATFORM_RAY_* / engine URLs / guest-callable ctl HTTP.
Default ``InertRuntimeHandoffHook`` stays no-op; JobStore falls back to
the in-process stub. Opt-in lab adapters on this same seam:

- ``PANORAMIX_CTL_HTTP`` (preferred when set) injects
  ``LabReserveTemporalHttpHook`` and talks to loopback ctl HTTP
  (``POST/GET /reserve-temporal/…`` or ``/iec-local/…`` on port
  **19216** / ``PANORAMIX_CTL_KIND=iec-local``). Non-loopback / unset
  fails closed. Guest does not run IFRS17 math.
- ``PANORAMIX_RUNTIME_ROOT`` injects ``LabReserveTemporalHook`` and
  invokes local ``python3 -m runtime.apply reserve-temporal`` (or
  ``iec-local`` when that ctl is selected).

Neither is a second control plane and neither is guest→mesh ctl.
Unset fails closed (inert).

Does not close #70. Does not close #78. Does not unlock #61 / #29.
Does not stamp north_star_done. Cloud stays locked.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol

HOOK_KIND_INERT = "inert"
HOOK_KIND_CTL_HTTP = "ctl_http"
HOOK_KIND_CTL_APPLY = "ctl_apply"


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
    adapter via PANORAMIX_CTL_HTTP or PANORAMIX_RUNTIME_ROOT.
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
    """Inert unless an opt-in lab adapter is configured.

    Prefer ``PANORAMIX_CTL_HTTP`` (loopback ctl HTTP) when set.
    Else ``PANORAMIX_RUNTIME_ROOT`` (local apply). Fail closed
    when both are unset or unusable. Does not close #70 / #78.
    Does not unlock cloud.
    """
    from sos.lab_ctl import lab_hook_from_env
    from sos.lab_ctl_http import http_hook_from_env

    http_hook = http_hook_from_env(env)
    if http_hook is not None:
        return http_hook
    hook = lab_hook_from_env(env)
    if hook is None:
        return InertRuntimeHandoffHook()
    return hook


def durable_hook_active(hook: RuntimeHandoffHook) -> bool:
    """True when one-click re-admit can use the hook seam.

    Lab adapters follow ``describe_runtime_hook.durable_path``
    (unreachable CTL_HTTP is False). Default inert is False.
    An injected non-inert hook (tests / operator inject) is the
    same seam. Not guest→mesh ctl. Does not close #70 / #78.
    """
    desc = describe_runtime_hook(hook)
    if desc.get("durable_path") is True:
        return True
    if isinstance(hook, InertRuntimeHandoffHook):
        return False
    from sos.lab_ctl import LabReserveTemporalHook
    from sos.lab_ctl_http import LabReserveTemporalHttpHook

    if isinstance(hook, (LabReserveTemporalHttpHook, LabReserveTemporalHook)):
        return False
    return True


def describe_runtime_hook(hook: RuntimeHandoffHook) -> dict[str, Any]:
    """Honest hook label for /v0/info + UI. No pretend when inert.

    ``durable_path`` is true only when an opt-in lab adapter is
    actually hooked. Default is inert (fail closed). Not guest→mesh
    ctl. Does not close #70 / #78. north_star_done stays false.
    """
    from sos.lab_ctl import LabReserveTemporalHook
    from sos.lab_ctl_http import LabReserveTemporalHttpHook

    if isinstance(hook, LabReserveTemporalHttpHook):
        from sos.errors import ERROR_CTL_HTTP_UNREACHABLE
        from sos.lab_ctl import CTL_KIND_IEC_LOCAL

        iec = hook.ctl == CTL_KIND_IEC_LOCAL
        if hook.last_unreachable is not None:
            return {
                "kind": HOOK_KIND_CTL_HTTP,
                "durable_path": False,
                "reachable": False,
                "error": ERROR_CTL_HTTP_UNREACHABLE,
                "adapter": "LabReserveTemporalHttpHook",
                "ctl": hook.ctl,
                "ctl_http": hook.base_url,
                "guest_to_mesh_ctl": False,
                "ifrs17_guest": False,
                "north_star_done": False,
                "note": (
                    "lab serve down — PANORAMIX_CTL_HTTP origin is "
                    "unreachable. Fail closed — not durable. "
                    "Not guest→mesh ctl. Not SIEM. Not IFRS17. "
                    "Guest does not run IFRS17 math. "
                    "Not #70 Done. north_star_done false."
                ),
            }
        return {
            "kind": HOOK_KIND_CTL_HTTP,
            "durable_path": True,
            "adapter": "LabReserveTemporalHttpHook",
            "ctl": hook.ctl,
            "ctl_http": hook.base_url,
            "guest_to_mesh_ctl": False,
            "ifrs17_guest": False,
            "north_star_done": False,
            "note": (
                "Durable path active via loopback "
                + ("iec-local " if iec else "")
                + "ctl HTTP. Guest does not run IFRS17 math"
                + (
                    " — runtime binding wraps the operator iec checkout."
                    if iec
                    else "."
                )
                + " Not guest→mesh ctl. Not SIEM. Not IFRS17. "
                "Not #70 Done. north_star_done false."
            ),
        }
    if isinstance(hook, LabReserveTemporalHook):
        from sos.lab_ctl import CTL_KIND_IEC_LOCAL

        iec = hook.ctl == CTL_KIND_IEC_LOCAL
        return {
            "kind": HOOK_KIND_CTL_APPLY,
            "durable_path": True,
            "adapter": "LabReserveTemporalHook",
            "ctl": hook.ctl,
            "guest_to_mesh_ctl": False,
            "ifrs17_guest": False,
            "north_star_done": False,
            "note": (
                "Durable path via local "
                + ("iec-local" if iec else "reserve-temporal")
                + " apply hook. Guest does not run IFRS17 math. "
                "Not guest→mesh ctl. Not SIEM. Not IFRS17. "
                "Not #70 Done. north_star_done false."
            ),
        }
    from sos.lab_compose_iec import IecLocalComposeHook

    if isinstance(hook, IecLocalComposeHook):
        return {
            "kind": HOOK_KIND_CTL_HTTP,
            "durable_path": True,
            "adapter": "IecLocalComposeHook",
            "ctl": "iec-local",
            "guest_to_mesh_ctl": False,
            "ifrs17_guest": False,
            "north_star_done": False,
            "note": (
                "Durable path via iec-local compose hook (dry-run / lab). "
                "Guest does not run IFRS17 math. Not guest→mesh ctl. "
                "Not SIEM. Not IFRS17. Not #70 Done. north_star_done false."
            ),
        }
    return {
        "kind": HOOK_KIND_INERT,
        "durable_path": False,
        "adapter": type(hook).__name__,
        "guest_to_mesh_ctl": False,
        "north_star_done": False,
        "note": (
            "Default hook is inert. Fail-closed without "
            "PANORAMIX_CTL_HTTP or PANORAMIX_RUNTIME_ROOT. "
            "No pretend durable path."
        ),
    }
