"""Domain errors with stable JSON ``error`` codes."""

from __future__ import annotations

from typing import Any

from sos.handoff_vocab import (
    CTL_ADMIT,
    CTL_CANCEL,
    CTL_PAUSE_RESUME,
    LOCAL_DEMOS,
    RESOURCE_CLASSES,
    WORK_KINDS,
    WORK_STATUSES,
)


class SosError(Exception):
    """Domain error with a stable JSON `error` code."""

    http_status = 400

    def __init__(self, error: str, **fields: Any) -> None:
        self.error = error
        self.fields = fields
        super().__init__(error)

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.error, **self.fields}


class EngineSmuggle(SosError):
    def __init__(self, detail: str) -> None:
        super().__init__("engine_smuggle", detail=detail)


class InvalidHandoff(SosError):
    def __init__(self, detail: str) -> None:
        super().__init__("invalid_handoff", detail=detail)


class InvalidKind(SosError):
    def __init__(self, kind: str, *, detail: str | None = None) -> None:
        fields: dict[str, Any] = {"kind": kind, "allowed": sorted(WORK_KINDS)}
        if detail:
            fields["detail"] = detail
        super().__init__("invalid_kind", **fields)


class InvalidClass(SosError):
    def __init__(self, resource_class: str, *, detail: str | None = None) -> None:
        fields: dict[str, Any] = {
            "class": resource_class,
            "allowed": sorted(RESOURCE_CLASSES),
        }
        if detail:
            fields["detail"] = detail
        super().__init__("invalid_class", **fields)


class InvalidDigest(SosError):
    def __init__(self, detail: str) -> None:
        super().__init__("invalid_digest", detail=detail)


class InvalidDemo(SosError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            "invalid_demo",
            detail=detail,
            allowed=sorted(LOCAL_DEMOS),
        )


class InvalidStatus(SosError):
    def __init__(self, status: str) -> None:
        super().__init__(
            "invalid_status",
            status=status,
            allowed=list(WORK_STATUSES),
            detail=(
                "Job list filter uses real job.status only "
                "(queued/running/paused/succeeded/failed/canceled). "
                "Unknown values such as accepted or cancelled are rejected."
            ),
        )


class JobNotFound(SosError):
    http_status = 404

    def __init__(self, job_id: str) -> None:
        super().__init__("not_found", id=job_id)


class PayloadUnknown(SosError):
    http_status = 404

    def __init__(self, job_id: str) -> None:
        super().__init__(
            "payload_unknown",
            id=job_id,
            detail=(
                "opaque submit recorded payload_digest only; "
                "demo shortcuts store canonical JSON bytes for ctl export"
            ),
        )


class AlreadyTerminal(SosError):
    http_status = 409

    def __init__(self, job_id: str, status: str) -> None:
        super().__init__(
            "already_terminal",
            id=job_id,
            status=status,
            note=(
                "Cancel ends a live run (status canceled), including paused. "
                "Cancel is not pause. Durable cancel is ctl-mediated. "
                "Pause/resume is durable-path only "
                f"({CTL_PAUSE_RESUME}). Stub-backed cancel is local; "
                "runtime-backed cancel signals the hook first "
                f"({CTL_CANCEL}), then marks the guest job canceled if "
                "it was still live or follows hook.status() when ctl "
                "already reports terminal. Fail-closed without hook."
            ),
        )


class StubOnly(SosError):
    http_status = 409

    def __init__(self, job_id: str, action: str) -> None:
        super().__init__(
            "stub_only",
            id=job_id,
            action=action,
            detail=(
                f"{action} requires the durable path; the in-process stub "
                "cannot pause or resume. Operator/ctl: "
                f"{CTL_PAUSE_RESUME}"
            ),
        )


class IllegalTransition(SosError):
    http_status = 409

    def __init__(self, job_id: str, status: str, action: str) -> None:
        super().__init__(
            "illegal_transition",
            id=job_id,
            status=status,
            action=action,
            detail=f"cannot {action} job in status {status}",
        )


class ReAdmitUnavailable(SosError):
    """One-click re-admit refused. Fail-closed; no silent stub."""

    http_status = 409

    def __init__(self, job_id: str, reason: str, *, detail: str) -> None:
        super().__init__(
            "re_admit_unavailable",
            id=job_id,
            action="re-admit",
            reason=reason,
            detail=detail,
            note=(
                "Re-admit is a new admit through the durable hook "
                "(PANORAMIX_CTL_HTTP preferred or PANORAMIX_RUNTIME_ROOT). "
                "Not resume-from-failed. Cancel/fail does not auto-retry. "
                "Fail-closed without hook or when handoff/payload is missing "
                f"(no silent stub re-admit). Operator/ctl: {CTL_ADMIT}. "
                "Not SIEM. Not IFRS17."
            ),
        )


ERROR_CTL_HTTP_UNREACHABLE = "ctl_http_unreachable"
CTL_HTTP_UNREACHABLE_REASON = "connection refused / origin not listening"
CTL_HTTP_UNREACHABLE_DETAIL = (
    "lab serve down — PANORAMIX_CTL_HTTP origin is unreachable "
    "(connection refused or not listening). Fail closed — not durable. "
    "Start runtime.serve or unset PANORAMIX_CTL_HTTP. HTTP timeout "
    "while the origin is listening is not this error. Not #70 Done."
)
ERROR_CTL_ADMIT_TIMEOUT = "ctl_admit_timeout"
CTL_ADMIT_TIMEOUT_REASON = "admit exceeded guest timeout"
CTL_ADMIT_TIMEOUT_DETAIL = (
    "durable admit exceeded guest timeout "
    "(HTTP admit 8s / poll 1.5s / ctl-apply admit 2s) before a "
    "running id returned. Origin was listening — not lab-serve-down. "
    "live|parity is minutes-class — admit must return running while "
    "work continues (runtime #143). Fail closed — not durable, "
    "not stub progress. Poll GET /progress and GET /events mid-flight "
    "once a running id exists. Not #70 Done. north_star_done false."
)
ERROR_DURABLE_ADMIT_FAILED = "durable_admit_failed"
DURABLE_ADMIT_FAILED_DETAIL = (
    "live|parity durable admit did not return a running id. "
    "Fail closed — no stub fallback (would fake minutes-class progress). "
    "Depends on runtime #143 async admit. Not #70 Done. "
    "north_star_done false."
)
SAME_JOB_STUB_DETAIL = (
    "iec-local same-job (reserve_ifrs17) is not a guest stub. "
    "Guest does not run IFRS17 math. Point PANORAMIX_CTL_HTTP at "
    "iec-local ctl (19216) so the runtime binding can wrap the "
    "operator iec checkout (POST /v1/jobs). Fail closed — no stub "
    "progress. Not #70 Done. north_star_done false."
)


def lab_serve_affordance(*, origin: str | None = None) -> dict[str, Any]:
    """Stable operator payload when loopback ctl HTTP cannot connect."""
    payload: dict[str, Any] = {
        "reachable": False,
        "error": ERROR_CTL_HTTP_UNREACHABLE,
        "note": CTL_HTTP_UNREACHABLE_DETAIL,
    }
    if origin:
        payload["origin"] = origin
    return payload


class CtlHttpUnreachable(SosError):
    """Opt-in CTL_HTTP set, but runtime.serve refused / is not listening.

    Fail closed. Do not pretend durable. Not guest→mesh ctl.
    HTTP timeout while the origin is listening is CtlAdmitTimeout
    (admit) or a missed poll — not this error.
    """

    http_status = 503

    def __init__(
        self,
        *,
        action: str,
        origin: str | None = None,
        reason: str = CTL_HTTP_UNREACHABLE_REASON,
        job_id: str | None = None,
    ) -> None:
        fields: dict[str, Any] = {
            "action": action,
            "reason": reason,
            "detail": CTL_HTTP_UNREACHABLE_DETAIL,
        }
        if origin:
            fields["origin"] = origin
        if job_id:
            fields["id"] = job_id
        super().__init__(ERROR_CTL_HTTP_UNREACHABLE, **fields)


class CtlAdmitTimeout(SosError):
    """Durable admit blocked past the guest timeout.

    Distinct from lab-serve-down. live|parity needs runtime #143
    so admit returns a running id. Fail closed — not stub progress.
    """

    http_status = 503

    def __init__(
        self,
        *,
        action: str = "admit",
        origin: str | None = None,
        transport: str | None = None,
        job_id: str | None = None,
        reason: str = CTL_ADMIT_TIMEOUT_REASON,
    ) -> None:
        fields: dict[str, Any] = {
            "action": action,
            "reason": reason,
            "detail": CTL_ADMIT_TIMEOUT_DETAIL,
            "runtime_issue": 143,
            "north_star_done": False,
        }
        if origin:
            fields["origin"] = origin
        if transport:
            fields["transport"] = transport
        if job_id:
            fields["id"] = job_id
        super().__init__(ERROR_CTL_ADMIT_TIMEOUT, **fields)


class DurableAdmitFailed(SosError):
    """live|parity hook admit returned nothing. No stub fallback."""

    http_status = 409

    def __init__(
        self,
        job_id: str,
        *,
        reason: str = "hook_refused",
        detail: str = DURABLE_ADMIT_FAILED_DETAIL,
    ) -> None:
        super().__init__(
            ERROR_DURABLE_ADMIT_FAILED,
            id=job_id,
            action="admit",
            reason=reason,
            detail=detail,
            runtime_issue=143,
            north_star_done=False,
        )
