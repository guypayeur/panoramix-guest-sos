"""Opt-in lab adapter: loopback ctl HTTP to reserve-temporal.

Uses the existing ``RuntimeHandoffHook`` injection point. Alternative
to the ``PANORAMIX_RUNTIME_ROOT`` apply hook — same seam, same
honesty. Prefer this path when a base URL is set so status / progress /
events / pause / resume / cancel talk to runtime.serve verbs.

Not guest→mesh ctl. Not a Unit Git scheme. Not ``PLATFORM_RAY_*``.
Not engine URLs. Pin stays 0.5.

Opt-in via ``PANORAMIX_CTL_HTTP`` pointing at a loopback origin
(example: ``http://127.0.0.1:19215``, the ``publish.ctl_port`` on
``local-reserve-temporal``). Shape is panoramix-runtime **main**
@ ``fb901542`` (PR #100). Unset, non-loopback, or an unusable URL
fails closed (caller keeps the inert stub). Optional
``PANORAMIX_CTL_HTTP_BEARER`` sends ``Authorization: Bearer …`` when
the binding has ``ctl.require``. Optional
``PANORAMIX_RESERVE_TEMPORAL_LIVE=1`` adds ``live=1`` on admit.

Calls ``/reserve-temporal/{admit,status,progress,events,pause,resume,cancel}``
or, when ``PANORAMIX_CTL_KIND=iec-local`` / ctl port **19216**,
``/iec-local/{admit,status,progress,pause,resume,cancel}`` (no events
verb — iec-local has none). Never ``runtime.apply compute-work``.
Does not import the runtime package.

When the origin is valid but runtime.serve is down (connection
refused / not listening), admit/status/progress fail closed with
``ctl_http_unreachable`` (lab-serve down). Poll timeout stays short
(``CTL_HTTP_TIMEOUT_SEC``) so list/detail do not hang. HTTP admit
uses a longer ``CTL_HTTP_ADMIT_TIMEOUT_SEC`` so a slow-but-up
iec-local admit is not raced. If admit still exceeds that window
while the origin is listening, the error is ``ctl_admit_timeout``
(runtime still blocking; needs #143 for live|parity) — fail closed,
not stub progress, not lab-serve-down. Status/progress HTTP timeout
while the origin is listening is a missed poll (return None) — not
``ctl_http_unreachable``. Guest polls progress/events mid-flight
once a running id exists. HTTP 4xx/5xx on recorded stay the
existing stub fallback; live|parity refuse stub.

Does not close runtime #70. Does not close #78. Does not unlock
#61 / #29. Does not stamp north_star_done. Cloud stays locked.
"""

from __future__ import annotations

import errno
import json
import os
import socket
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from sos.errors import (
    CTL_HTTP_UNREACHABLE_REASON,
    CtlAdmitTimeout,
    CtlHttpUnreachable,
)
from sos.lab_ctl import (
    ENV_LIVE,
    _admit_handoff,
    _ctl_id,
    _lifecycle_status,
    _parse_json,
    _runtime_ref_from_admit,
    _truthy,
    resolve_ctl_kind,
)

ENV_CTL_HTTP = "PANORAMIX_CTL_HTTP"
ENV_CTL_BEARER = "PANORAMIX_CTL_HTTP_BEARER"
ENV_CTL_KIND = "PANORAMIX_CTL_KIND"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
CTL_KIND_RESERVE_TEMPORAL = "reserve-temporal"
CTL_KIND_IEC_LOCAL = "iec-local"
CTL_KINDS = frozenset({CTL_KIND_RESERVE_TEMPORAL, CTL_KIND_IEC_LOCAL})
DEFAULT_IEC_LOCAL_PORT = 19216
# Short so operator list/detail polls do not hang when serve is down.
CTL_HTTP_TIMEOUT_SEC = 1.5
# Admit (especially iec-local live wrap of POST /v1/jobs) can exceed the
# poll window while ctl is still listening. Compose guest POST waits 8s.
CTL_HTTP_ADMIT_TIMEOUT_SEC = 8.0
CTL_HTTP_LISTEN_PROBE_SEC = 0.25
CTL_HTTP_UNREACHABLE_COOLDOWN_SEC = 2.0
CTL_HTTP_UNREACHABLE_CODE = 0
# Distinct from connection-refused so admit timeout is not "lab serve down".
CTL_HTTP_TIMEOUT_CODE = -1
RESERVE_TEMPORAL_PREFIX = "/reserve-temporal"
IEC_LOCAL_PREFIX = "/iec-local"
GET_VERBS = frozenset({"status", "progress", "events"})
POST_VERBS = frozenset({"admit", "pause", "resume", "cancel"})
IEC_LOCAL_GET_VERBS = frozenset({"status", "progress"})
IEC_LOCAL_POST_VERBS = frozenset({"admit", "pause", "resume", "cancel"})

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


def is_http_timeout(exc: BaseException) -> bool:
    """True when urllib/socket timed out — not connection refused."""
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == errno.ETIMEDOUT:
        return True
    reason = getattr(exc, "reason", None)
    if isinstance(reason, BaseException) and is_http_timeout(reason):
        return True
    text = str(reason if reason is not None else exc).lower()
    return "timed out" in text


def origin_listening(origin: str, *, timeout: float = CTL_HTTP_LISTEN_PROBE_SEC) -> bool:
    """True when the loopback ctl origin accepts TCP (slow-but-up)."""
    parsed = urlsplit(str(origin or "").strip())
    host = parsed.hostname
    port = parsed.port or 80
    if not host or not (1 <= int(port) <= 65535):
        return False
    try:
        with socket.create_connection((host, int(port)), timeout=float(timeout)):
            return True
    except OSError:
        return False


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
    except TimeoutError:
        return CTL_HTTP_TIMEOUT_CODE, ""
    except URLError as exc:
        if is_http_timeout(exc):
            return CTL_HTTP_TIMEOUT_CODE, ""
        return CTL_HTTP_UNREACHABLE_CODE, ""
    except OSError as exc:
        if is_http_timeout(exc):
            return CTL_HTTP_TIMEOUT_CODE, ""
        return CTL_HTTP_UNREACHABLE_CODE, ""
    except ValueError:
        return CTL_HTTP_UNREACHABLE_CODE, ""


class LabReserveTemporalHttpHook:
    """Existing hook seam → loopback ctl HTTP.

    Default prefix is ``/reserve-temporal/*``. When ``ctl`` is
    ``iec-local`` (port 19216 or ``PANORAMIX_CTL_KIND``) the prefix is
    ``/iec-local/*``. Honesty: lab opt-in only. Guest does not run
    IFRS17 math. Does not close #70 / #78. Cloud locked.
    Not guest→mesh ctl.
    """

    def __init__(
        self,
        base_url: str,
        *,
        transport: HttpTransport | None = None,
        bearer: str | None = None,
        live: bool = False,
        ctl: str = CTL_KIND_RESERVE_TEMPORAL,
        listen_probe: Callable[[], bool] | None = None,
        admit_timeout_sec: float | None = None,
        request_timeout_sec: float | None = None,
    ) -> None:
        origin = normalize_ctl_http_base(base_url)
        if origin is None:
            raise ValueError("ctl HTTP base must be a loopback http origin")
        self.base_url = origin
        self.transport = transport or urllib_request_ctl
        self.bearer = str(bearer).strip() if bearer else None
        self.live = bool(live)
        self.ctl = (
            str(ctl).strip()
            if ctl in CTL_KINDS
            else resolve_ctl_kind(origin=origin)
        )
        self.prefix = (
            IEC_LOCAL_PREFIX
            if self.ctl == CTL_KIND_IEC_LOCAL
            else RESERVE_TEMPORAL_PREFIX
        )
        self.listen_probe = listen_probe
        self.admit_timeout_sec = (
            CTL_HTTP_ADMIT_TIMEOUT_SEC
            if admit_timeout_sec is None
            else float(admit_timeout_sec)
        )
        self.request_timeout_sec = (
            CTL_HTTP_TIMEOUT_SEC
            if request_timeout_sec is None
            else float(request_timeout_sec)
        )
        self.last_unreachable: CtlHttpUnreachable | None = None
        self.last_status_payload: dict[str, Any] | None = None
        self._unreachable_until = 0.0

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
        if self.ctl == CTL_KIND_IEC_LOCAL:
            if action not in IEC_LOCAL_GET_VERBS and action not in IEC_LOCAL_POST_VERBS:
                return None
            method = "GET" if action in IEC_LOCAL_GET_VERBS else "POST"
        else:
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
            ("http", urlsplit(self.base_url).netloc, f"{self.prefix}/{action}", qs, "")
        )
        raw_body = (
            (json.dumps(body_obj, separators=(",", ":")) + "\n").encode("utf-8")
            if body_obj is not None
            else None
        )
        if (
            self.last_unreachable is not None
            and time.monotonic() < self._unreachable_until
        ):
            self._raise_unreachable(action)
        timeout = (
            self.admit_timeout_sec if action == "admit" else self.request_timeout_sec
        )
        try:
            code, stdout = self._call_transport(
                method,
                url,
                self._headers(has_body=raw_body is not None),
                raw_body,
                timeout=timeout,
            )
        except CtlHttpUnreachable:
            raise
        except Exception:
            return None
        if int(code) == CTL_HTTP_TIMEOUT_CODE:
            return self._on_http_timeout(action)
        if int(code) == CTL_HTTP_UNREACHABLE_CODE:
            self._raise_unreachable(action)
        if not (200 <= int(code) < 300):
            self._clear_unreachable()
            return None
        self._clear_unreachable()
        return _parse_json(stdout)

    def _call_transport(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        *,
        timeout: float,
    ) -> tuple[int, str]:
        try:
            return self.transport(
                method, url, headers, body, timeout=timeout
            )
        except TypeError:
            return self.transport(method, url, headers, body)

    def _origin_is_listening(self) -> bool:
        """True when ctl accepts TCP (or a test probe says so).

        Injected transports that return a timeout code are treated as
        listening unless ``listen_probe`` says otherwise — that keeps
        recorded fixtures from probing a closed lab port.
        """
        if self.listen_probe is not None:
            return bool(self.listen_probe())
        if self.transport is not urllib_request_ctl:
            return True
        return origin_listening(self.base_url)

    def _on_http_timeout(self, action: str) -> dict[str, Any] | None:
        """Listening + slow ≠ lab-serve-down. Down origin fails closed."""
        if not self._origin_is_listening():
            self._raise_unreachable(action)
        if action == "admit":
            raise CtlAdmitTimeout(
                action="admit",
                origin=self.base_url,
                transport="http",
            )
        return None

    def _raise_unreachable(self, action: str) -> None:
        err = CtlHttpUnreachable(
            action=action,
            origin=self.base_url,
            reason=CTL_HTTP_UNREACHABLE_REASON,
        )
        self.last_unreachable = err
        self._unreachable_until = time.monotonic() + CTL_HTTP_UNREACHABLE_COOLDOWN_SEC
        raise err

    def _clear_unreachable(self) -> None:
        self.last_unreachable = None
        self._unreachable_until = 0.0

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

    def _remember_payload(self, payload: dict[str, Any] | None) -> dict[str, Any] | None:
        """Keep last ctl JSON so pause_signaled can surface on job/progress."""
        if isinstance(payload, dict) and payload:
            self.last_status_payload = payload
        return payload

    def pause(self, job_id: str, runtime_ref: dict[str, Any] | None) -> bool:
        work_id = _ctl_id(job_id, runtime_ref)
        if work_id is None:
            return False
        return self._remember_payload(self._invoke("pause", work_id=work_id)) is not None

    def resume(self, job_id: str, runtime_ref: dict[str, Any] | None) -> bool:
        work_id = _ctl_id(job_id, runtime_ref)
        if work_id is None:
            return False
        return self._remember_payload(self._invoke("resume", work_id=work_id)) is not None

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
        if self.ctl == CTL_KIND_IEC_LOCAL:
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
        ctl=resolve_ctl_kind(source, origin=base),
    )
