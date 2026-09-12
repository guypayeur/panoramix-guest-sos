"""Opt-in lab adapter: local subprocess to reserve-temporal ctl.

Uses the existing ``RuntimeHandoffHook`` injection point. Not a second
control plane. Not guest-callable ctl HTTP over the mesh. Not
``PLATFORM_RAY_*``. Not engine URLs. Pin stays 0.5.

Sibling ``sos.lab_ctl_http`` is the preferred opt-in when
``PANORAMIX_CTL_HTTP`` is a loopback origin (runtime.serve verbs).
This module stays the subprocess path via ``PANORAMIX_RUNTIME_ROOT``.
Default without either env stays inert.

Opt-in via ``PANORAMIX_RUNTIME_ROOT`` pointing at a panoramix-runtime
checkout that contains ``runtime/apply.py``. Unset or missing root
fails closed (caller keeps the inert stub). Optional
``PANORAMIX_RESERVE_TEMPORAL_BINDING`` passes ``--binding``; optional
``PANORAMIX_RESERVE_TEMPORAL_LIVE=1`` passes ``--live``.

Invokes ``python3 -m runtime.apply reserve-temporal`` only — never
``runtime.apply compute-work``. Does not import the runtime package.

Admit must return a running ``cw_…`` id within ``CTL_ADMIT_TIMEOUT_SEC``
so the guest UI can poll progress/events mid-flight. live|parity walls are
minutes-class — that return depends on runtime #143. Admit timeout
is ctl_admit_timeout and fails closed (not stub progress).
Does not close runtime #70. Does not close #78. Does not unlock
#61 / #29. Does not stamp north_star_done. Cloud stays locked.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from sos.errors import CtlAdmitTimeout
from sos.handoff_vocab import WORK_STATUSES, extract_lifecycle_overlay

ENV_RUNTIME_ROOT = "PANORAMIX_RUNTIME_ROOT"
ENV_BINDING = "PANORAMIX_RESERVE_TEMPORAL_BINDING"
ENV_IEC_BINDING = "PANORAMIX_IEC_LOCAL_BINDING"
ENV_LIVE = "PANORAMIX_RESERVE_TEMPORAL_LIVE"
ENV_CTL_KIND = "PANORAMIX_CTL_KIND"
APPLY_REL = Path("runtime") / "apply.py"
CTL_KIND_RESERVE_TEMPORAL = "reserve-temporal"
CTL_KIND_IEC_LOCAL = "iec-local"
CTL_KINDS = frozenset({CTL_KIND_RESERVE_TEMPORAL, CTL_KIND_IEC_LOCAL})
DEFAULT_IEC_LOCAL_PORT = 19216
CTL_PREFIX = ("python3", "-m", "runtime.apply", "reserve-temporal")
CTL_PREFIX_BY_KIND = {
    CTL_KIND_RESERVE_TEMPORAL: ("python3", "-m", "runtime.apply", "reserve-temporal"),
    CTL_KIND_IEC_LOCAL: ("python3", "-m", "runtime.apply", "iec-local"),
}
WORK_ID_RE = re.compile(r"^cw_[0-9a-f]{16}$")
CTL_TIMEOUT_SEC = 120.0
# Admit must return a running id. live|parity walls are minutes-class
# (runtime #143). Do not wait 120s then stub.
CTL_ADMIT_TIMEOUT_SEC = 2.0
CTL_SUBPROCESS_TIMEOUT_CODE = 124

CtlRunner = Callable[..., tuple[int, str, str]]


def _truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def resolve_ctl_kind(
    env: Mapping[str, str] | None = None,
    *,
    origin: str | None = None,
) -> str:
    """reserve-temporal (default) or iec-local.

    Explicit ``PANORAMIX_CTL_KIND`` wins. Else ctl port **19216**
    selects iec-local (bindings/local-iec.example.yaml). Fail closed
    to reserve-temporal when unset — existing lab compose unchanged.
    """
    source = os.environ if env is None else env
    raw = str(source.get(ENV_CTL_KIND) or "").strip().lower()
    if raw in CTL_KINDS:
        return raw
    if origin:
        from urllib.parse import urlsplit

        port = urlsplit(str(origin)).port
        if port == DEFAULT_IEC_LOCAL_PORT:
            return CTL_KIND_IEC_LOCAL
    return CTL_KIND_RESERVE_TEMPORAL


def runtime_root_from_env(
    env: Mapping[str, str] | None = None,
) -> Path | None:
    """Return a usable runtime checkout, or None (fail closed)."""
    source = os.environ if env is None else env
    raw = str(source.get(ENV_RUNTIME_ROOT) or "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser()
    try:
        root = root.resolve()
    except OSError:
        return None
    if not root.is_dir():
        return None
    if not (root / APPLY_REL).is_file():
        return None
    return root


def binding_from_env(env: Mapping[str, str] | None = None) -> Path | None:
    source = os.environ if env is None else env
    kind = resolve_ctl_kind(source)
    names = (ENV_IEC_BINDING, ENV_BINDING) if kind == CTL_KIND_IEC_LOCAL else (ENV_BINDING,)
    for name in names:
        raw = str(source.get(name) or "").strip()
        if not raw:
            continue
        path = Path(raw).expanduser()
        try:
            path = path.resolve()
        except OSError:
            continue
        if path.is_file():
            return path
    return None


def subprocess_run_ctl(
    argv: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: float | None = None,
) -> tuple[int, str, str]:
    """Local subprocess only. Not HTTP. Not a mesh destination."""
    merged = dict(os.environ)
    merged.update(env)
    pythonpath = str(cwd)
    existing = merged.get("PYTHONPATH", "")
    if existing:
        pythonpath = pythonpath + os.pathsep + existing
    merged["PYTHONPATH"] = pythonpath
    if timeout is None:
        action = argv[4] if len(argv) > 4 else ""
        timeout = CTL_ADMIT_TIMEOUT_SEC if action == "admit" else CTL_TIMEOUT_SEC
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            env=merged,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CTL_SUBPROCESS_TIMEOUT_CODE, "", "ctl subprocess timed out"
    except OSError:
        return 1, "", "ctl subprocess failed"
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _parse_json(stdout: str) -> dict[str, Any] | None:
    text = (stdout or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not payload:
        return None
    if payload.get("ok") is False:
        return None
    return payload


def _ctl_id(job_id: str, runtime_ref: dict[str, Any] | None) -> str | None:
    if runtime_ref:
        raw = str(runtime_ref.get("id") or "").strip()
        if WORK_ID_RE.fullmatch(raw):
            return raw
    guest = str(job_id or "").strip()
    if WORK_ID_RE.fullmatch(guest):
        return guest
    return None


_LIFECYCLE_ALIASES = {
    "queued": "queued",
    "running": "running",
    "paused": "paused",
    "held": "held",
    "hold": "held",
    "succeeded": "succeeded",
    "completed": "succeeded",
    "complete": "succeeded",
    "failed": "failed",
    "canceled": "canceled",
    "cancelled": "canceled",
}


def _map_lifecycle_token(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip().lower()
    if not text:
        return None
    if text in WORK_STATUSES:
        return text
    return _LIFECYCLE_ALIASES.get(text)


def _lifecycle_status(payload: dict[str, Any]) -> str | None:
    handoff = payload.get("handoff")
    if isinstance(handoff, dict):
        mapped = _map_lifecycle_token(handoff.get("status"))
        if mapped:
            return mapped
    mapped = _map_lifecycle_token(payload.get("status"))
    if mapped:
        return mapped
    return _map_lifecycle_token(payload.get("lifecycle"))


def _extract_work_id(payload: dict[str, Any], fallback: str | None) -> str | None:
    for candidate in (
        payload.get("id"),
        (payload.get("handoff") or {}).get("id")
        if isinstance(payload.get("handoff"), dict)
        else None,
        fallback,
    ):
        raw = str(candidate or "").strip()
        if WORK_ID_RE.fullmatch(raw):
            return raw
    return None


def _runtime_ref_from_admit(
    payload: dict[str, Any],
    fallback: str | None,
    *,
    ctl: str = CTL_KIND_RESERVE_TEMPORAL,
) -> dict[str, Any] | None:
    """Running id (+ optional admit status). Work continues after return."""
    work_id = _extract_work_id(payload, fallback)
    if work_id is None:
        return None
    kind = str(ctl or CTL_KIND_RESERVE_TEMPORAL).strip() or CTL_KIND_RESERVE_TEMPORAL
    ref: dict[str, Any] = {"id": work_id, "ctl": kind}
    status = _lifecycle_status(payload)
    if status:
        ref["status"] = status
    iec_job_id = _honest_nested_id(payload.get("iec_job_id"))
    if iec_job_id is None and isinstance(payload.get("handoff"), dict):
        iec_job_id = _honest_nested_id(payload["handoff"].get("iec_job_id"))
    if iec_job_id:
        ref["iec_job_id"] = iec_job_id
    overlay = extract_lifecycle_overlay(
        payload, payload.get("handoff"), payload.get("progress")
    )
    for key, value in overlay.items():
        ref[key] = value
    return ref


def _honest_nested_id(value: Any) -> str | None:
    """Pass through a hook/ctl identity. Omit empty / unknown. Never invent."""
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "unknown", "undefined"}:
        return None
    return text


def _admit_handoff(handoff: dict[str, str]) -> dict[str, str]:
    """WorkHandoff guest shape only. Drop ids runtime parse_work would refuse."""
    out: dict[str, str] = {}
    for key in ("kind", "class", "payload_digest", "status"):
        value = handoff.get(key)
        if value is not None and str(value).strip():
            out[key] = str(value)
    raw_id = str(handoff.get("id") or "").strip()
    if WORK_ID_RE.fullmatch(raw_id):
        out["id"] = raw_id
    return out


class LabReserveTemporalHook:
    """Existing hook seam → local ``reserve-temporal`` subprocess.

    Honesty: lab opt-in only. Does not close #70 / #78. Cloud locked.
    """

    def __init__(
        self,
        root: Path,
        *,
        runner: CtlRunner | None = None,
        binding: Path | None = None,
        live: bool = False,
        ctl: str = CTL_KIND_RESERVE_TEMPORAL,
    ) -> None:
        self.root = Path(root)
        self.runner = runner or subprocess_run_ctl
        self.binding = Path(binding) if binding is not None else None
        self.live = bool(live)
        self.ctl = (
            str(ctl).strip()
            if ctl in CTL_KINDS
            else CTL_KIND_RESERVE_TEMPORAL
        )
        self.last_status_payload: dict[str, Any] | None = None

    def _invoke(
        self,
        action: str,
        *,
        work_id: str | None = None,
        handoff: dict[str, str] | None = None,
        resource_class: str | None = None,
    ) -> dict[str, Any] | None:
        if self.ctl == CTL_KIND_IEC_LOCAL and action == "events":
            return None
        prefix = CTL_PREFIX_BY_KIND.get(self.ctl, CTL_PREFIX)
        argv = list(prefix) + [action]
        if self.binding is not None:
            argv.extend(["--binding", str(self.binding)])
        if self.live:
            argv.append("--live")
        tmp_path: Path | None = None
        try:
            if action == "admit":
                if not handoff:
                    return None
                handle = tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    suffix=".json",
                    prefix="sos-handoff-",
                    delete=False,
                )
                with handle:
                    json.dump(_admit_handoff(handoff), handle)
                    handle.write("\n")
                    tmp_path = Path(handle.name)
                argv.extend(["--handoff", str(tmp_path)])
                cls = str(resource_class or handoff.get("class") or "").strip()
                if cls:
                    argv.extend(["--class", cls])
            else:
                if not work_id:
                    return None
                argv.extend(["--id", work_id])
            code, stdout, _stderr = self.runner(argv, cwd=self.root, env={})
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
        if int(code) == CTL_SUBPROCESS_TIMEOUT_CODE:
            if action == "admit":
                raise CtlAdmitTimeout(action="admit", transport="subprocess")
            return None
        if code != 0:
            return None
        return _parse_json(stdout)

    def admit(
        self, handoff: dict[str, str], payload_bytes: bytes | None
    ) -> dict[str, Any] | None:
        del payload_bytes
        payload = self._invoke(
            "admit",
            handoff=handoff,
            resource_class=handoff.get("class"),
        )
        if payload is None:
            return None
        return _runtime_ref_from_admit(payload, handoff.get("id"), ctl=self.ctl)

    def cancel(self, job_id: str, runtime_ref: dict[str, Any] | None) -> bool:
        work_id = _ctl_id(job_id, runtime_ref)
        if work_id is None:
            return False
        return self._invoke("cancel", work_id=work_id) is not None

    def status(self, job_id: str, runtime_ref: dict[str, Any] | None) -> str | None:
        work_id = _ctl_id(job_id, runtime_ref)
        self.last_status_payload = None
        if work_id is None:
            return None
        payload = self._invoke("status", work_id=work_id)
        self.last_status_payload = payload
        if payload is None:
            return None
        return _lifecycle_status(payload)

    def pause(self, job_id: str, runtime_ref: dict[str, Any] | None) -> bool:
        work_id = _ctl_id(job_id, runtime_ref)
        if work_id is None:
            return False
        return self._invoke("pause", work_id=work_id) is not None

    def resume(self, job_id: str, runtime_ref: dict[str, Any] | None) -> bool:
        work_id = _ctl_id(job_id, runtime_ref)
        if work_id is None:
            return False
        return self._invoke("resume", work_id=work_id) is not None

    def progress(
        self, job_id: str, runtime_ref: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        work_id = _ctl_id(job_id, runtime_ref)
        if work_id is None:
            return None
        return self._invoke("progress", work_id=work_id)

    def events(
        self, job_id: str, runtime_ref: dict[str, Any] | None
    ) -> dict[str, Any] | list[Any] | None:
        work_id = _ctl_id(job_id, runtime_ref)
        if work_id is None:
            return None
        return self._invoke("events", work_id=work_id)


def lab_hook_from_env(
    env: Mapping[str, str] | None = None,
    *,
    runner: CtlRunner | None = None,
) -> LabReserveTemporalHook | None:
    """Build the lab hook when opted in. None → fail closed (inert)."""
    source = os.environ if env is None else env
    root = runtime_root_from_env(source)
    if root is None:
        return None
    return LabReserveTemporalHook(
        root,
        runner=runner,
        binding=binding_from_env(source),
        live=_truthy(source.get(ENV_LIVE)),
        ctl=resolve_ctl_kind(source),
    )
