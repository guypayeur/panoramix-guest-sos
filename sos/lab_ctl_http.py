"""Opt-in lab adapter: loopback ctl HTTP to reserve-temporal.

Uses the existing ``RuntimeHandoffHook`` injection point. Alternative
to the ``PANORAMIX_RUNTIME_ROOT`` apply hook — same seam, same
honesty. Prefer this path when a base URL is set so status / progress /
events / pause / resume / cancel talk to runtime.serve verbs.

Not guest→mesh ctl. Not a Unit Git scheme. Not ``PLATFORM_RAY_*``.
Not engine URLs. Pin stays 0.5.

Opt-in via ``PANORAMIX_CTL_HTTP`` pointing at a loopback origin
(example: ``http://127.0.0.1:19215``, the ``publish.ctl_port`` on
``local-reserve-temporal``). Unset, non-loopback, or an unusable URL
fails closed (caller keeps the inert stub). Optional
``PANORAMIX_CTL_HTTP_BEARER`` sends ``Authorization: Bearer …`` when
the binding has ``ctl.require``. Optional
``PANORAMIX_RESERVE_TEMPORAL_LIVE=1`` adds ``live=1`` on admit.

Calls only ``/reserve-temporal/{admit,status,progress,events,pause,resume,cancel}``.
Never ``runtime.apply compute-work``. Does not import the runtime package.

Does not close runtime #70. Does not close #78. Does not unlock
#61 / #29. Does not stamp north_star_done. Cloud stays locked.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from sos.lab_ctl import (
    ENV_LIVE,
    _admit_handoff,
    _ctl_id,
    _extract_work_id,
    _lifecycle_status,
    _parse_json,
    _truthy,
)

ENV_CTL_HTTP = "PANORAMIX_CTL_HTTP"
ENV_CTL_BEARER = "PANORAMIX_CTL_HTTP_BEARER"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
CTL_HTTP_TIMEOUT_SEC = 30.0
RESERVE_TEMPORAL_PREFIX = "/reserve-temporal"
GET_VERBS = frozenset({"status", "progress", "events"})
POST_VERBS = frozenset({"admit", "pause", "resume", "cancel"})

HttpTransport = Callable[..., tuple[int, str]]


def normalize_ctl_http_base(raw: str | None) -> str | None:
    """Return a loopback http origin, or None (fail closed)."""
    text = str(raw or "").strip()
    if not text:
        return None
    parsed = urlsplit(text)
    if parsed.scheme.lower() != "http":
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    host = (parsed.hostname or "").strip().lower()
    if host not in LOOPBACK_HOSTS:
        return None
    if parsed.path not in {"", "/"}:
        return None
    if parsed.query or parsed.fragment:
        return None
    port = parsed.port
    if port is not None and not (1 <= int(port) <= 65535):
        return None
    host_part = "[::1]" if host == "::1" else host
    netloc = host_part if port is None else f"{host_part}:{int(port)}"
    return urlunsplit(("http", netloc, "", "", ""))


def ctl_http_base_from_env(env: Mapping[str, str] | None = None) -> str | None:
    """Return a usable loopback ctl origin, or None (fail closed)."""
    source = os.environ if env is None else env
    return normalize_ctl_http_base(source.get(ENV_CTL_HTTP))


def bearer_from_env(env: Mapping[str, str] | None = None) -> str | None:
    source = os.environ if env is None else env
    raw = str(source.get(ENV_CTL_BEARER) or "").strip()
    return raw or None


def urllib_request_ctl(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: bytes | None,
    *,
    timeout: float = CTL_HTTP_TIMEOUT_SEC,
) -> tuple[int, str]:
    """Stdlib HTTP only. Loopback origin is enforced by the hook."""
    req = Request(url, data=body, method=method, headers=dict(headers))
    try:
        with urlopen(req, timeout=timeout) as resp:
            return int(resp.status), (resp.read() or b"").decode("utf-8")
    except HTTPError as exc:
        raw = b""
        try:
            raw = exc.read() or b""
        except OSError:
            raw = b""
        return int(exc.code), raw.decode("utf-8", errors="replace")
    except (OSError, URLError, TimeoutError, ValueError):
        return 0, ""


class LabReserveTemporalHttpHook:
    """Existing hook seam → loopback ``/reserve-temporal/*`` HTTP.

    Honesty: lab opt-in only. Does not close #70 / #78. Cloud locked.
    Not guest→mesh ctl.
    """

    def __init__(
        self,
        base_url: str,
        *,
        transport: HttpTransport | None = None,
        bearer: str | None = None,
        live: bool = False,
    ) -> None:
        origin = normalize_ctl_http_base(base_url)
        if origin is None:
            raise ValueError("ctl HTTP base must be a loopback http origin")
        self.base_url = origin
        self.transport = transport or urllib_request_ctl
        self.bearer = str(bearer).strip() if bearer else None
        self.live = bool(live)

    def _headers(self, *, has_body: bool) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if has_body:
            headers["Content-Type"] = "application/json"
        if self.bearer:
            headers["Authorization"] = f"Bearer {self.bearer}"
        return headers

    def _invoke(
        self,
        action: str,
        *,
        work_id: str | None = None,
        handoff: dict[str, str] | None = None,
        resource_class: str | None = None,
    ) -> dict[str, Any] | None:
        if action not in GET_VERBS and action not in POST_VERBS:
            return None
        method = "GET" if action in GET_VERBS else "POST"
        query: dict[str, str] = {}
        body_obj: dict[str, Any] | None = None
        if action == "admit":
            if not handoff:
                return None
            body_obj = dict(_admit_handoff(handoff))
            cls = str(resource_class or handoff.get("class") or "").strip()
            if cls:
                body_obj["class"] = cls
            if self.live:
                query["live"] = "1"
        else:
            if not work_id:
                return None
            query["id"] = work_id
        qs = urlencode(query) if query else ""
        url = urlunsplit(
            ("http", urlsplit(self.base_url).netloc, f"{RESERVE_TEMPORAL_PREFIX}/{action}", qs, "")
        )
        raw_body = (
            (json.dumps(body_obj, separators=(",", ":")) + "\n").encode("utf-8")
            if body_obj is not None
            else None
        )
        try:
            code, stdout = self.transport(
                method,
                url,
                self._headers(has_body=raw_body is not None),
                raw_body,
            )
        except Exception:
            return None
        if not (200 <= int(code) < 300):
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
        work_id = _extract_work_id(payload, handoff.get("id"))
        if work_id is None:
            return None
        return {"id": work_id, "ctl": "reserve-temporal"}

    def cancel(self, job_id: str, runtime_ref: dict[str, Any] | None) -> bool:
        work_id = _ctl_id(job_id, runtime_ref)
        if work_id is None:
            return False
        return self._invoke("cancel", work_id=work_id) is not None

    def status(self, job_id: str, runtime_ref: dict[str, Any] | None) -> str | None:
        work_id = _ctl_id(job_id, runtime_ref)
        if work_id is None:
            return None
        payload = self._invoke("status", work_id=work_id)
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


def http_hook_from_env(
    env: Mapping[str, str] | None = None,
    *,
    transport: HttpTransport | None = None,
) -> LabReserveTemporalHttpHook | None:
    """Build the HTTP hook when opted in. None → fail closed (inert)."""
    source = os.environ if env is None else env
    base = ctl_http_base_from_env(source)
    if base is None:
        return None
    return LabReserveTemporalHttpHook(
        base,
        transport=transport,
        bearer=bearer_from_env(source),
        live=_truthy(source.get(ENV_LIVE)),
    )
