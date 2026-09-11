"""Domain errors with stable JSON ``error`` codes."""

from __future__ import annotations

from typing import Any

from sos.handoff_vocab import (
    CTL_PAUSE_RESUME,
    LOCAL_DEMOS,
    RESOURCE_CLASSES,
    WORK_KINDS,
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
                "Cancel is not pause. Pause/resume is durable-path only "
                f"({CTL_PAUSE_RESUME}). Stub-backed cancel is local; "
                "runtime-backed cancel signals the injected hook, then marks "
                "the guest job canceled if it was still live."
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
