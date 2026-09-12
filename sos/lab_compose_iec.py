"""Thin lab compose: iec-local same-job admit + UI watch.

Documents and plans ``runtime.serve`` (binding
``local-iec.example.yaml``, ctl **19216**) plus guest
``PANORAMIX_CTL_HTTP`` + ``PLATFORM_LISTEN_HTTP``. Process spawn lives
in ``scripts/lab_compose_iec_local.py`` so this module stays
unit-testable without a live iec checkout.

POST body is ``{"demo":"reserve","catalog":"reserve_ifrs17"}``
(alias ``same-job``). Evidence is ``local.backed=runtime`` plus
durable progress (phase/fraction when the hook supplies them).
Does **not** require events or pause_resume (iec-local has no
events verb; pause is pause-before-start only).

Honesty: guest does not run IFRS17 math. Runtime binding wraps the
operator iec checkout (``POST /v1/jobs``). Recorded fixture needs no
checkout. Opt-in ``--live`` / ``PANORAMIX_RESERVE_TEMPORAL_LIVE``
passes ``live=1`` so ctl wraps the operator Platform API. Phase/
fraction omit Platform unknown/0 (runtime #149 / #150) — never
invent. Walls (``api_e2e_ms``) omit when missing — never invent.
Pin 0.5.
WorkHandoff triple only. Does **not** grow pack_fill. Does **not**
close runtime #70 / #78. Does **not** unlock #61 / #29. Does **not**
stamp ``north_star_done``. Cloud stays locked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from sos.errors import (
    ERROR_DURABLE_ADMIT_FAILED,
    DurableAdmitFailed,
)
from sos.handoff_vocab import (
    LAB_COMPOSE_IEC_DOCS,
    LAB_COMPOSE_IEC_SCRIPT,
    RESERVE_CATALOG_SAME_JOB,
    SAME_JOB_PAYLOAD_DIGEST,
)
from sos.jobs import JobStore
from sos.lab_compose import (
    DEFAULT_GUEST_PORT,
    GUEST_LISTEN_ENV,
    ctl_origin,
    guest_base_url,
    guest_listen_value,
    runtime_root_usable,
    runtime_serve_argv,
)
from sos.lab_ctl import (
    CTL_KIND_IEC_LOCAL,
    ENV_CTL_KIND,
    ENV_IEC_BINDING,
    ENV_LIVE,
)
from sos.lab_ctl_http import ENV_CTL_BEARER, ENV_CTL_HTTP, normalize_ctl_http_base

DEFAULT_IEC_CTL_PORT = 19216
DEFAULT_IEC_BINDING_REL = "bindings/local-iec.example.yaml"
# panoramix-runtime main tip for #146 / PR #148 (docs/iec-local.md).
RUNTIME_IEC_PIN = "d480dc826e2f8e98502224c3230ab561f48c8114"
SAME_JOB_BODY: dict[str, Any] = {
    "demo": "reserve",
    "catalog": RESERVE_CATALOG_SAME_JOB,
}
SAME_JOB_CATALOG_ALIASES = {
    RESERVE_CATALOG_SAME_JOB: RESERVE_CATALOG_SAME_JOB,
    "same-job": RESERVE_CATALOG_SAME_JOB,
}

HONESTY_LINES = (
    "fail-closed without PANORAMIX_CTL_HTTP (or a usable PANORAMIX_RUNTIME_ROOT)",
    "not guest→mesh ctl",
    "not a second control plane",
    "not SIEM",
    "guest does not run IFRS17 math",
    "runtime binding wraps operator iec checkout (POST /v1/jobs)",
    "not invented walls (api_e2e_ms omit when missing)",
    "not invented path-slices",
    "phase/fraction omit Platform unknown/0 (runtime #149 / #150)",
    "iec-local has no events verb",
    "pause is pause-before-start only (iec single-activity limit)",
    "recorded fixture needs no iec checkout",
    "opt-in --live wraps operator Platform API",
    "pin 0.5",
    "WorkHandoff triple only",
    "does not close runtime #70 / #78",
    "does not unlock cloud #61 / #29",
    "north_star_done false",
    "admit timeout while ctl is listening is ctl_admit_timeout (not lab-serve-down)",
    "fail closed when ctl is unreachable",
)

COMPOSE_HOOK_ID = "cw_aaaaaaaaaaaaaaaa"


@dataclass(frozen=True)
class IecComposePlan:
    """Argv / env for the iec-local one-shot. No processes started here."""

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
    live: bool = False
    north_star_done: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ctl": CTL_KIND_IEC_LOCAL,
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
            "live": self.live,
            "same_job": True,
            "ifrs17_guest": False,
            "digest": SAME_JOB_PAYLOAD_DIGEST,
            "docs": LAB_COMPOSE_IEC_DOCS,
            "script": LAB_COMPOSE_IEC_SCRIPT,
            "evidence": (
                "local.backed=runtime + durable progress "
                "(phase/fraction when the hook supplies them; omit "
                "unknown/0). events/pause_resume not required."
            ),
            "guest_to_mesh_ctl": False,
            "north_star_done": self.north_star_done,
            "closes_runtime_70": False,
            "closes_runtime_78": False,
            "cloud_locked": True,
        }


def resolve_same_job_catalog(catalog: str | None = None) -> str:
    raw = "" if catalog is None else str(catalog).strip()
    if not raw:
        return RESERVE_CATALOG_SAME_JOB
    resolved = SAME_JOB_CATALOG_ALIASES.get(raw.lower())
    if resolved is None:
        raise ValueError("catalog must be reserve_ifrs17 (alias same-job)")
    return resolved


def same_job_body(catalog: str | None = None) -> dict[str, Any]:
    return {"demo": "reserve", "catalog": resolve_same_job_catalog(catalog)}


def guest_env_for_iec(
    *,
    ctl_http: str,
    guest_listen: str,
    bearer: str | None = None,
    live: bool = False,
    binding: str | None = None,
) -> dict[str, str]:
    origin = normalize_ctl_http_base(ctl_http)
    if origin is None:
        raise ValueError("PANORAMIX_CTL_HTTP must be a loopback http origin")
    env = {
        ENV_CTL_HTTP: origin,
        ENV_CTL_KIND: CTL_KIND_IEC_LOCAL,
        GUEST_LISTEN_ENV: str(guest_listen).strip(),
    }
    token = str(bearer or "").strip()
    if token:
        env[ENV_CTL_BEARER] = token
    if live:
        env[ENV_LIVE] = "1"
    bind = str(binding or "").strip()
    if bind:
        env[ENV_IEC_BINDING] = bind
    return env


def build_iec_compose_plan(
    *,
    guest_root: str | Path,
    runtime_root: str | Path | None = None,
    ctl_port: int = DEFAULT_IEC_CTL_PORT,
    guest_port: int = DEFAULT_GUEST_PORT,
    binding: str | None = None,
    bearer: str | None = None,
    live: bool = False,
) -> IecComposePlan:
    """Describe the one-shot iec-local lab. Does not spawn processes."""
    guest = Path(guest_root).expanduser().resolve()
    bind = str(binding or DEFAULT_IEC_BINDING_REL).strip() or DEFAULT_IEC_BINDING_REL
    ctl = ctl_origin(ctl_port)
    listen = guest_listen_value(guest_port)
    usable = runtime_root_usable(runtime_root)
    return IecComposePlan(
        runtime_root=str(usable)
        if usable is not None
        else (str(Path(runtime_root).expanduser()) if runtime_root else None),
        binding=bind,
        serve_argv=runtime_serve_argv(bind),
        guest_argv=("python3", "./platform_run.py"),
        guest_cwd=str(guest),
        guest_env=guest_env_for_iec(
            ctl_http=ctl,
            guest_listen=listen,
            bearer=bearer,
            live=live,
        ),
        ctl_http=ctl,
        guest_listen=listen,
        guest_base=guest_base_url(guest_port),
        reserve_body=same_job_body(),
        honesty=HONESTY_LINES,
        runtime_serve_pin=RUNTIME_IEC_PIN,
        live=bool(live),
        north_star_done=False,
    )


def classify_iec_evidence(
    job: Mapping[str, Any],
    progress: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify a same-job snapshot. No pretend on stub. No invented walls."""
    local = job.get("local") if isinstance(job.get("local"), dict) else {}
    backed = local.get("backed")
    progress_source = None
    phase = None
    fraction = None
    walls = None
    if isinstance(progress, Mapping):
        progress_source = progress.get("source")
        raw_phase = progress.get("phase")
        if raw_phase not in (None, "", "unknown"):
            phase = raw_phase
        raw_frac = progress.get("fraction")
        if raw_frac is not None and not (phase is None and raw_frac == 0.0):
            fraction = raw_frac
        raw_walls = progress.get("walls")
        if isinstance(raw_walls, dict) and raw_walls.get("invented") is not True:
            walls = {
                key: raw_walls[key]
                for key in ("api_e2e_ms", "wall_elapsed_ms", "method_wall_time_s")
                if key in raw_walls and raw_walls[key] is not None
            } or None
    ok = backed == "runtime" and progress_source == "durable"
    payload: dict[str, Any] = {
        "ok": ok,
        "backed": backed,
        "progress_source": progress_source,
        "same_job": local.get("same_job") is True
        or local.get("catalog") == RESERVE_CATALOG_SAME_JOB
        or job.get("payload_digest") == SAME_JOB_PAYLOAD_DIGEST,
        "ifrs17_guest": False,
        "pause_resume_required": False,
        "events_required": False,
        "north_star_done": False,
        "guest_to_mesh_ctl": False,
        "note": (
            "local.backed=runtime + durable progress when the HTTP "
            "adapter admitted. Phase/fraction omit when missing "
            "(Platform unknown/0). Events/pause_resume not required. "
            "Stub stays fail-closed (same_job_stub). Guest does not "
            "run IFRS17 math."
        ),
    }
    if phase is not None:
        payload["phase"] = phase
    if fraction is not None:
        payload["fraction"] = fraction
    if walls:
        payload["walls"] = walls
    return payload


class IecLocalComposeHook:
    """Injected hook for iec-local dry-run smoke. Not a live iec checkout."""

    def admit(
        self, handoff: dict[str, str], payload_bytes: bytes | None
    ) -> dict[str, Any] | None:
        del payload_bytes
        if str(handoff.get("payload_digest") or "") != SAME_JOB_PAYLOAD_DIGEST:
            return None
        return {
            "id": COMPOSE_HOOK_ID,
            "ctl": CTL_KIND_IEC_LOCAL,
            "status": "running",
        }

    def cancel(self, job_id: str, runtime_ref: dict[str, Any] | None) -> bool:
        del job_id, runtime_ref
        return True

    def status(self, job_id: str, runtime_ref: dict[str, Any] | None) -> str | None:
        del job_id, runtime_ref
        return "running"

    def pause(self, job_id: str, runtime_ref: dict[str, Any] | None) -> bool:
        del job_id, runtime_ref
        return False

    def resume(self, job_id: str, runtime_ref: dict[str, Any] | None) -> bool:
        del job_id, runtime_ref
        return False

    def progress(
        self, job_id: str, runtime_ref: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        del job_id, runtime_ref
        return {"phase": "admitted", "fraction": 0.0, "pct": 0}

    def events(
        self, job_id: str, runtime_ref: dict[str, Any] | None
    ) -> dict[str, Any] | list[Any] | None:
        del job_id, runtime_ref
        return None


def dry_run_iec_smokes() -> dict[str, Any]:
    """Hooked running + inert same_job_stub. No processes. No iec checkout."""
    hooked_store = JobStore(runtime_hook=IecLocalComposeHook(), step_seconds=0.01)
    job = hooked_store.submit(same_job_body())
    public = hooked_store.public_dict(hooked_store.get(job.id))
    progress = hooked_store.progress(job.id)
    hooked = classify_iec_evidence(public, progress)
    hooked["status"] = public.get("status")
    hooked["id"] = public.get("id")

    inert_ok = False
    reason = "unexpected_stub"
    detail = None
    try:
        JobStore(step_seconds=0.01).submit(same_job_body())
    except DurableAdmitFailed as exc:
        reason = str(exc.fields.get("reason") or "")
        detail = str(exc.fields.get("detail") or "")
        inert_ok = reason == "same_job_stub"

    return {
        "hooked": hooked,
        "inert": {
            "ok": inert_ok,
            "error": ERROR_DURABLE_ADMIT_FAILED,
            "reason": reason,
            "detail": detail,
            "stub_fallback": False,
        },
        "honest": bool(hooked.get("ok")) and inert_ok,
        "ifrs17_guest": False,
        "north_star_done": False,
        "note": (
            "hooked admit returns running + durable phase; inert "
            "same-job fails closed (same_job_stub). Guest does not "
            "run IFRS17 math. Not #70 Done."
        ),
    }


def iec_smokes_honest(smokes: Mapping[str, Any]) -> bool:
    return smokes.get("honest") is True and smokes.get("north_star_done") is False


def plan_json(plan: IecComposePlan) -> str:
    return json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n"
