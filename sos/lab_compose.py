"""Lab compose helpers: one-shot Temporal-backed reserve path.

Documents and plans ``runtime.serve`` (binding
``local-reserve-temporal.example.yaml``, ctl **19215**) plus guest
``PANORAMIX_CTL_HTTP`` + ``PLATFORM_LISTEN_HTTP``. Process spawn lives
in ``scripts/lab_compose_reserve_temporal.py`` so this module stays
unit-testable without live Temporal.

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
    "does not close runtime #70 / #78",
    "does not unlock #61 / #29",
    "north_star_done false",
)


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
    }


def port_from_origin(origin: str) -> int:
    parsed = urlsplit(origin)
    if parsed.port is not None:
        return int(parsed.port)
    return 80


def plan_json(plan: ComposePlan) -> str:
    return json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n"
