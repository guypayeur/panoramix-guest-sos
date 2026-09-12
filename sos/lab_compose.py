"""Lab compose helpers: one-shot Temporal-backed reserve path.

Documents and plans ``runtime.serve`` (binding
``local-reserve-temporal.example.yaml``, ctl **19215**) plus guest
``PANORAMIX_CTL_HTTP`` + ``PLATFORM_LISTEN_HTTP``. Process spawn lives
in ``scripts/lab_compose_reserve_temporal.py`` so this module stays
unit-testable without live Temporal.

Also classifies and dry-runs the thinner recoverability smoke:
admit → cancel/fail → ``POST /v0/jobs/{id}/re-admit`` → new job id
on the existing hook seam. Fail-closed without hook or payload
(no silent stub). Not resume-from-failed.

Honesty: fail-closed without env. Not guest→mesh ctl. Not SIEM.
Not IFRS17. Pin 0.5. WorkHandoff triple only. Does not close runtime
#70 / #78. Does not unlock #61 / #29. Does not stamp north_star_done.
Cloud stays locked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from sos.lab_ctl import APPLY_REL
from sos.lab_ctl_http import ENV_CTL_BEARER, ENV_CTL_HTTP, normalize_ctl_http_base

GUEST_LISTEN_ENV = "PLATFORM_LISTEN_HTTP"
DEFAULT_GUEST_PORT = 18280
DEFAULT_CTL_PORT = 19215
DEFAULT_BINDING_REL = "bindings/local-reserve-temporal.example.yaml"
RUNTIME_SERVE_PIN = "fb901542"
RECORDED_RESERVE_BODY: dict[str, Any] = {"demo": "reserve", "catalog": "recorded"}

HONESTY_LINES = (
    "fail-closed without PANORAMIX_CTL_HTTP (or a usable PANORAMIX_RUNTIME_ROOT)",
    "not guest→mesh ctl",
    "not a second control plane",
    "not SIEM",
    "not IFRS17",
    "pin 0.5",
    "WorkHandoff triple only",
    "re-admit is a new admit (not resume-from-failed)",
    "no silent stub re-admit",
    "path-slice elapsed omitted when timestamps missing (never invent)",
    "does not close runtime #70 / #78",
    "does not unlock #61 / #29",
    "north_star_done false",
)

READMIT_JOURNEY = ("admit", "cancel_or_fail", "re-admit", "new_job_id")
READMIT_FAIL_CLOSED = ("hook_inert", "payload_unknown", "hook_refused")
OPAQUE_HANDOFF_BODY: dict[str, Any] = {
    "kind": "job",
    "class": "cpu",
    "payload_digest": "sha256:" + ("ab" * 32),
}
_FAILED_OR_CANCELED = frozenset({"failed", "canceled"})
LIVE_JOB_STATUSES = frozenset({"queued", "running", "paused"})


@dataclass(frozen=True)
class ComposePlan:
    """Argv / env for the one-shot lab. No processes are started here."""

    runtime_root: str | None
    binding: str
    serve_argv: tuple[str, ...]
    guest_argv: tuple[str, ...]
    guest_cwd: str
    guest_env: dict[str, str]
    ctl_http: str
    guest_listen: str
    guest_base: str
    reserve_body: dict[str, Any]
    honesty: tuple[str, ...]
    runtime_serve_pin: str
    north_star_done: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_root": self.runtime_root,
            "binding": self.binding,
            "serve_argv": list(self.serve_argv),
            "guest_argv": list(self.guest_argv),
            "guest_cwd": self.guest_cwd,
            "guest_env": dict(self.guest_env),
            "ctl_http": self.ctl_http,
            "guest_listen": self.guest_listen,
            "guest_base": self.guest_base,
            "reserve_body": dict(self.reserve_body),
            "honesty": list(self.honesty),
            "runtime_serve_pin": self.runtime_serve_pin,
            "north_star_done": self.north_star_done,
            "guest_to_mesh_ctl": False,
            "readmit": readmit_plan(),
            "timeline_elapsed": elapsed_plan(),
        }


def ctl_origin(port: int = DEFAULT_CTL_PORT, host: str = "127.0.0.1") -> str:
    """Loopback ctl origin. Non-loopback fails closed at hook resolve."""
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("ctl host must be loopback")
    if not (1 <= int(port) <= 65535):
        raise ValueError("ctl port out of range")
    host_part = "[::1]" if host == "::1" else host
    origin = f"http://{host_part}:{int(port)}"
    if normalize_ctl_http_base(origin) is None:
        raise ValueError("ctl origin is not a usable loopback http origin")
    return origin


def runtime_serve_argv(binding: str = DEFAULT_BINDING_REL) -> tuple[str, ...]:
    rel = str(binding or DEFAULT_BINDING_REL).strip() or DEFAULT_BINDING_REL
    return ("python3", "-m", "runtime.serve", "--binding", rel)


def guest_listen_value(port: int = DEFAULT_GUEST_PORT) -> str:
    """Port-only so platform_run binds 127.0.0.1 (emulate loopback)."""
    if not (1 <= int(port) <= 65535):
        raise ValueError("guest port out of range")
    return str(int(port))


def guest_base_url(port: int = DEFAULT_GUEST_PORT) -> str:
    return f"http://127.0.0.1:{int(guest_listen_value(port))}"


def recorded_reserve_body() -> dict[str, Any]:
    return dict(RECORDED_RESERVE_BODY)


def elapsed_plan() -> dict[str, Any]:
    """Dry-run honesty for optional path-slice elapsed. No invented numbers."""
    return {
        "when": "durable progress stages[].elapsed_ms and/or GET /events timestamps",
        "omit_when_missing": True,
        "invent": False,
        "north_star_done": False,
        "note": (
            "Optional per-stage elapsed on the path-slice timeline. "
            "Prefer progress elapsed_ms when present; else derive from "
            "durable event timestamps. Omit when missing. Never invent. "
            "Not iec planner. Not #70 Done."
        ),
    }


def readmit_plan() -> dict[str, Any]:
    """Dry-run description of the re-admit smoke. No Temporal."""
    return {
        "path": "POST /v0/jobs/{id}/re-admit",
        "journey": list(READMIT_JOURNEY),
        "when": "PANORAMIX_CTL_HTTP (preferred) or PANORAMIX_RUNTIME_ROOT",
        "fail_closed": list(READMIT_FAIL_CLOSED),
        "resume_from_failed": False,
        "silent_stub": False,
        "new_admit": True,
        "north_star_done": False,
        "guest_to_mesh_ctl": False,
        "note": (
            "admit → cancel/fail → one-click re-admit → new job id. "
            "Fail-closed without hook or payload (no silent stub). "
            "Not resume-from-failed. Not #70 Done."
        ),
    }


def runtime_root_usable(root: str | Path | None) -> Path | None:
    """Usable panoramix-runtime checkout, or None (fail closed)."""
    if root is None:
        return None
    if not str(root).strip():
        return None
    path = Path(root).expanduser()
    try:
        path = path.resolve()
    except OSError:
        return None
    if not path.is_dir():
        return None
    if not (path / APPLY_REL).is_file():
        return None
    return path


def guest_env_for_ctl(
    *,
    ctl_http: str,
    guest_listen: str,
    bearer: str | None = None,
) -> dict[str, str]:
    origin = normalize_ctl_http_base(ctl_http)
    if origin is None:
        raise ValueError("PANORAMIX_CTL_HTTP must be a loopback http origin")
    env = {
        ENV_CTL_HTTP: origin,
        GUEST_LISTEN_ENV: str(guest_listen).strip(),
    }
    token = str(bearer or "").strip()
    if token:
        env[ENV_CTL_BEARER] = token
    return env


def build_compose_plan(
    *,
    guest_root: str | Path,
    runtime_root: str | Path | None = None,
    ctl_port: int = DEFAULT_CTL_PORT,
    guest_port: int = DEFAULT_GUEST_PORT,
    binding: str | None = None,
    bearer: str | None = None,
) -> ComposePlan:
    """Describe the one-shot lab. Does not spawn processes."""
    guest = Path(guest_root).expanduser().resolve()
    bind = str(binding or DEFAULT_BINDING_REL).strip() or DEFAULT_BINDING_REL
    ctl = ctl_origin(ctl_port)
    listen = guest_listen_value(guest_port)
    usable = runtime_root_usable(runtime_root)
    return ComposePlan(
        runtime_root=str(usable) if usable is not None else (
            str(Path(runtime_root).expanduser()) if runtime_root else None
        ),
        binding=bind,
        serve_argv=runtime_serve_argv(bind),
        guest_argv=("python3", "./platform_run.py"),
        guest_cwd=str(guest),
        guest_env=guest_env_for_ctl(
            ctl_http=ctl, guest_listen=listen, bearer=bearer
        ),
        ctl_http=ctl,
        guest_listen=listen,
        guest_base=guest_base_url(guest_port),
        reserve_body=recorded_reserve_body(),
        honesty=HONESTY_LINES,
        runtime_serve_pin=RUNTIME_SERVE_PIN,
    )


def classify_lab_evidence(
    job: Mapping[str, Any],
    progress: Mapping[str, Any] | None = None,
    events: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify a guest job snapshot. No Temporal. No pretend on stub."""
    local = job.get("local") if isinstance(job.get("local"), dict) else {}
    backed = local.get("backed")
    pause_resume = job.get("pause_resume") is True
    progress_source = None
    if isinstance(progress, Mapping):
        progress_source = progress.get("source")
    events_source = None
    events_durable = False
    if isinstance(events, Mapping):
        events_source = events.get("source")
        events_durable = bool(events.get("events_durable"))
    if events_source is None:
        events_source = job.get("events_source")
    if not events_durable:
        events_durable = bool(job.get("events_durable"))
    ok = (
        backed == "runtime"
        and pause_resume
        and progress_source == "durable"
        and events_source == "durable"
    )
    return {
        "ok": ok,
        "backed": backed,
        "pause_resume": pause_resume,
        "progress_source": progress_source,
        "events_source": events_source,
        "events_durable": events_durable,
        "north_star_done": False,
        "guest_to_mesh_ctl": False,
        "note": (
            "local.backed=runtime + durable progress/events + pause_resume "
            "when the HTTP adapter admitted. Stub stays stub (no pretend)."
        ),
    }


class LabComposeReadmitHook:
    """Injected hook for compose re-admit smoke. Not Temporal.

    Same seam as ``PANORAMIX_CTL_HTTP`` / ``PANORAMIX_RUNTIME_ROOT``.
    Not a second control plane. Not guest→mesh ctl.
    """

    def admit(
        self, handoff: dict[str, str], payload_bytes: bytes | None
    ) -> dict[str, Any] | None:
        return {"accepted": True, "lab_compose": True, "id": handoff.get("id")}

    def cancel(self, job_id: str, runtime_ref: dict[str, Any] | None) -> bool:
        return True

    def status(self, job_id: str, runtime_ref: dict[str, Any] | None) -> str | None:
        return None


def classify_readmit_evidence(
    source: Mapping[str, Any],
    readmit: Mapping[str, Any] | None = None,
    *,
    http_status: int | None = None,
    error: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify admit→cancel/fail→re-admit. No Temporal. No silent stub."""
    source_id = source.get("id")
    source_status = source.get("status")
    rec = source.get("recoverability")
    recover = rec if isinstance(rec, Mapping) else {}
    resume_from_failed = recover.get("resume_from_failed") is True
    new_admit = recover.get("new_admit") is True
    one_click = recover.get("one_click") is True
    err = dict(error) if isinstance(error, Mapping) else {}
    if (
        not err
        and http_status is not None
        and http_status >= 400
        and isinstance(readmit, Mapping)
    ):
        err = dict(readmit)
    reason = err.get("reason")
    fail_closed = (
        http_status == 409
        and err.get("error") == "re_admit_unavailable"
        and reason in READMIT_FAIL_CLOSED
    )
    new_id = None
    from_id = None
    backed = None
    if isinstance(readmit, Mapping) and http_status in {None, 200, 201}:
        new_id = readmit.get("id")
        local = readmit.get("local") if isinstance(readmit.get("local"), dict) else {}
        from_id = local.get("re_admit_from")
        backed = local.get("backed")
    silent_stub = bool(
        new_id
        and backed == "stub"
        and http_status in {None, 200, 201}
    )
    ok = (
        source_status in _FAILED_OR_CANCELED
        and new_id is not None
        and new_id != source_id
        and from_id == source_id
        and backed == "runtime"
        and not resume_from_failed
        and not silent_stub
        and not fail_closed
        and http_status in {None, 200, 201}
    )
    return {
        "ok": ok,
        "fail_closed": fail_closed,
        "fail_closed_reason": reason if fail_closed else None,
        "silent_stub": silent_stub,
        "source_id": source_id,
        "source_status": source_status,
        "new_id": new_id,
        "re_admit_from": from_id,
        "backed": backed,
        "one_click": one_click,
        "new_admit": new_admit,
        "resume_from_failed": resume_from_failed,
        "http_status": http_status,
        "north_star_done": False,
        "guest_to_mesh_ctl": False,
        "note": (
            "admit → cancel/fail → POST .../re-admit → new job id when hooked. "
            "Fail-closed without hook or payload (no silent stub). "
            "Not resume-from-failed. Not #70 Done."
        ),
    }


def exercise_readmit_smoke(
    *,
    runtime_hook: Any | None = None,
    submit_body: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """In-process admit → cancel → re-admit. No Temporal. No sockets.

    Uses the jobs HTTP table (``SosApp``) on the existing hook seam.
    Default hook is inert (fail-closed). Inject ``LabComposeReadmitHook``
    (or any durable hook) for the new-job-id path.
    """
    from sos.http import SosApp
    from sos.jobs import JobStore
    from sos.runtime_hook import InertRuntimeHandoffHook

    hook = runtime_hook if runtime_hook is not None else InertRuntimeHandoffHook()
    store = JobStore(step_seconds=0.02, runtime_hook=hook, persist_dir=None)
    app = SosApp(store)
    body = dict(submit_body) if submit_body is not None else recorded_reserve_body()
    if body.get("demo") is not None:
        body.setdefault("seconds", 8)
    created = app.handle(
        "POST", "/v0/jobs", (json.dumps(body, separators=(",", ":")) + "\n").encode()
    )
    created_payload = json.loads(created.body.decode("utf-8")) if created.body else {}
    job_id = created_payload.get("id")
    if created.status not in {200, 201} or not job_id:
        evidence = classify_readmit_evidence(
            created_payload,
            None,
            http_status=int(created.status),
            error=created_payload if created.status >= 400 else None,
        )
        return {
            "source": created_payload,
            "readmit_status": None,
            "readmit": None,
            "error": created_payload if created.status >= 400 else None,
            "evidence": evidence,
            "north_star_done": False,
            "guest_to_mesh_ctl": False,
        }
    canceled = app.handle("POST", f"/v0/jobs/{job_id}/cancel")
    source = json.loads(canceled.body.decode("utf-8")) if canceled.body else {}
    readmit = app.handle("POST", f"/v0/jobs/{job_id}/re-admit")
    payload = json.loads(readmit.body.decode("utf-8")) if readmit.body else {}
    ok_http = readmit.status in {200, 201}
    evidence = classify_readmit_evidence(
        source,
        payload if ok_http else None,
        http_status=int(readmit.status),
        error=None if ok_http else payload,
    )
    return {
        "source": source,
        "readmit_status": int(readmit.status),
        "readmit": payload if ok_http else None,
        "error": None if ok_http else payload,
        "evidence": evidence,
        "north_star_done": False,
        "guest_to_mesh_ctl": False,
    }


def dry_run_readmit_smokes() -> dict[str, Any]:
    """Hooked + fail-closed smokes for ``--dry-run``. No Temporal."""
    hooked = exercise_readmit_smoke(runtime_hook=LabComposeReadmitHook())
    inert = exercise_readmit_smoke()
    missing = exercise_readmit_smoke(
        runtime_hook=LabComposeReadmitHook(),
        submit_body=OPAQUE_HANDOFF_BODY,
    )
    return {
        "hooked": hooked["evidence"],
        "inert": inert["evidence"],
        "payload_unknown": missing["evidence"],
        "north_star_done": False,
        "guest_to_mesh_ctl": False,
        "resume_from_failed": False,
        "silent_stub": False,
        "note": (
            "In-process SosApp re-admit smoke. No Temporal. "
            "Fail-closed without hook or payload (no silent stub). "
            "Not resume-from-failed. Not #70 Done."
        ),
    }


def readmit_smokes_honest(smokes: Mapping[str, Any]) -> bool:
    """True when dry-run smokes show hooked ok + fail-closed, no silent stub."""
    hooked = smokes.get("hooked") if isinstance(smokes.get("hooked"), Mapping) else {}
    inert = smokes.get("inert") if isinstance(smokes.get("inert"), Mapping) else {}
    missing = (
        smokes.get("payload_unknown")
        if isinstance(smokes.get("payload_unknown"), Mapping)
        else {}
    )
    return bool(
        hooked.get("ok") is True
        and hooked.get("silent_stub") is False
        and hooked.get("resume_from_failed") is False
        and hooked.get("new_id")
        and hooked.get("new_id") != hooked.get("source_id")
        and inert.get("fail_closed") is True
        and inert.get("fail_closed_reason") == "hook_inert"
        and inert.get("silent_stub") is False
        and inert.get("ok") is False
        and missing.get("fail_closed") is True
        and missing.get("fail_closed_reason") == "payload_unknown"
        and missing.get("silent_stub") is False
        and missing.get("ok") is False
        and smokes.get("north_star_done") is False
        and smokes.get("guest_to_mesh_ctl") is False
        and smokes.get("resume_from_failed") is False
    )


def wait_loopback_port(
    port: int,
    *,
    host: str = "127.0.0.1",
    timeout_s: float = 20.0,
    interval_s: float = 0.05,
    clock: Callable[[], float] | None = None,
    sleeper: Callable[[float], None] | None = None,
    connector: Callable[[str, int], None] | None = None,
) -> bool:
    """Wait until a TCP port accepts. Injectable — no live Temporal in CI."""
    import time

    tick = clock or time.monotonic
    sleep = sleeper or time.sleep

    def _connect(h: str, p: int) -> None:
        import socket

        sock = socket.create_connection((h, p), timeout=0.25)
        sock.close()

    connect = connector or _connect
    deadline = tick() + float(timeout_s)
    while tick() < deadline:
        try:
            connect(host, int(port))
            return True
        except OSError:
            sleep(float(interval_s))
    return False


def guest_paths(plan: ComposePlan) -> dict[str, str]:
    """Guest HTTP paths the compose script POSTs/GETs."""
    base = plan.guest_base.rstrip("/")
    return {
        "health": f"{base}/health",
        "info": f"{base}/v0/info",
        "jobs": f"{base}/v0/jobs",
        "ui": f"{base}/",
    }


def job_paths(plan: ComposePlan, job_id: str) -> dict[str, str]:
    base = plan.guest_base.rstrip("/")
    root = f"{base}/v0/jobs/{job_id}"
    return {
        "job": root,
        "progress": f"{root}/progress",
        "events": f"{root}/events",
        "pause": f"{root}/pause",
        "resume": f"{root}/resume",
        "cancel": f"{root}/cancel",
        "readmit": f"{root}/re-admit",
    }


def port_from_origin(origin: str) -> int:
    parsed = urlsplit(origin)
    if parsed.port is not None:
        return int(parsed.port)
    return 80


def plan_json(plan: ComposePlan) -> str:
    return json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n"
