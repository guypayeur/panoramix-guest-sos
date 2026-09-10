"""Opaque work handoff aligned with panoramix-runtime #70 Slice B.

Hard reference: runtime/compute_work.py on panoramix-runtime main (not a PR
number). Guest-facing submit shape is ``kind`` / ``class`` /
``payload_digest`` — not engine brands. Local demo echo/sleep is a guest-only
shortcut that synthesizes that shape before storage. Does not close #70.
Does not unlock #61 / #29.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sos.errors import EngineSmuggle, InvalidClass, InvalidDemo, InvalidDigest, InvalidHandoff, InvalidKind
from sos.handoff_vocab import (
    DEFAULT_ECHO_MESSAGE,
    DEFAULT_SLEEP_SECONDS,
    DEMO_ECHO,
    DEMO_SLEEP,
    LOCAL_DEMOS,
    MAX_SLEEP_SECONDS,
    RESOURCE_CLASSES,
    WORK_KINDS,
)

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SEAM_KEYS = frozenset({"kind", "class", "payload_digest"})
DEMO_KEYS = frozenset({"demo", "message", "seconds"})

# Schemes / prefixes that would smuggle an engine URL into the seam.
ENGINE_SCHEMES = (
    "ray:",
    "temporal:",
    "aws:",
    "s3:",
    "iec:",
    "podman:",
    "docker:",
    "image:",
    "firecracker:",
    "anyscale:",
    "gke:",
    "ecs:",
    "compute:",
)
ENGINE_BRAND_KEYS = frozenset(
    {
        "ray",
        "temporal",
        "aws",
        "iec",
        "iec-proto-c",
        "iec_proto_c",
        "podman",
        "docker",
        "image",
        "firecracker",
        "gke",
        "ecs",
        "s3",
        "anyscale",
        "engine",
        "engine_kind",
        "engine_url",
        "ray_address",
        "ray_namespace",
        "temporal_host",
        "temporal_namespace",
        "workflow_id",
        "task_queue",
        "cluster_url",
        "payload",
        "url",
        "uri",
        "endpoint",
        "address",
    }
)
_BRAND_KEYS_COMPACT = frozenset(k.replace("_", "") for k in ENGINE_BRAND_KEYS)


def _norm_key(key: Any) -> str:
    return str(key or "").strip().lower().replace("-", "_")


def _engine_scheme_in(text: str) -> str | None:
    raw = str(text or "")
    lower = raw.lower()
    for scheme in ENGINE_SCHEMES:
        if scheme in lower:
            return scheme
    if "://" in raw:
        return "://"
    return None


def _reject_smuggled_text(text: str, *, where: str) -> None:
    hit = _engine_scheme_in(text)
    if hit:
        raise EngineSmuggle(
            f"{where} smuggles engine URL/schema {hit!r} "
            "(guest seam is kind/class/payload_digest; engines stay in runtime bindings)"
        )


def reject_smuggle(obj: Any, *, where: str = "body") -> None:
    """Refuse engine brand keys and URL schemes anywhere in the request."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            nk = _norm_key(key)
            if nk in ENGINE_BRAND_KEYS or nk.replace("_", "") in _BRAND_KEYS_COMPACT:
                raise EngineSmuggle(
                    f"{where} field {key!r} is an engine brand/schema "
                    "(not guest-facing; engines in runtime bindings only)"
                )
            _reject_smuggled_text(str(key), where=f"{where} key")
            reject_smuggle(val, where=f"{where}.{key}")
        return
    if isinstance(obj, list):
        for i, item in enumerate(obj):
            reject_smuggle(item, where=f"{where}[{i}]")
        return
    if isinstance(obj, str):
        _reject_smuggled_text(obj, where=where)


def digest_canonical(payload: Any) -> str:
    """sha256 of canonical JSON (same separators as runtime digest_payload)."""
    blob = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _canon_seconds(seconds: float) -> int | float:
    if seconds == int(seconds):
        return int(seconds)
    return float(seconds)


def parse_demo(body: dict[str, Any]) -> tuple[str, str, str, dict[str, Any]]:
    """Local-only shortcut → synthesized job/cpu + digest + stub metadata."""
    extra = sorted(str(k) for k in body if str(k) not in DEMO_KEYS)
    if extra:
        raise InvalidHandoff(
            f"local demo refuses extra fields {extra} "
            "(demo shortcut is demo/message/seconds only)"
        )
    demo = body.get("demo")
    if not isinstance(demo, str) or demo.strip().lower() not in LOCAL_DEMOS:
        raise InvalidDemo(demo if isinstance(demo, str) else type(demo).__name__)
    demo = demo.strip().lower()
    if demo == DEMO_ECHO:
        if "seconds" in body:
            raise InvalidDemo("echo does not take seconds")
        message = body.get("message", DEFAULT_ECHO_MESSAGE)
        if not isinstance(message, str):
            raise InvalidDemo("echo message must be a string")
        canonical = {"demo": DEMO_ECHO, "message": message}
        local = {"demo": DEMO_ECHO, "message": message}
    else:
        if "message" in body:
            raise InvalidDemo("sleep does not take message")
        seconds = body.get("seconds", DEFAULT_SLEEP_SECONDS)
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            raise InvalidDemo("sleep seconds must be a non-negative number")
        if seconds < 0:
            raise InvalidDemo("sleep seconds must be a non-negative number")
        if seconds > MAX_SLEEP_SECONDS:
            raise InvalidDemo(f"sleep seconds must be <= {MAX_SLEEP_SECONDS}")
        canon_seconds = _canon_seconds(float(seconds))
        canonical = {"demo": DEMO_SLEEP, "seconds": canon_seconds}
        local = {"demo": DEMO_SLEEP, "seconds": canon_seconds}
    digest = digest_canonical(canonical)
    return "job", "cpu", digest, local


def parse_handoff(body: dict[str, Any]) -> tuple[str, str, str]:
    """Admit an opaque Slice B body. Reject extra keys and bad vocab."""
    extra = sorted(str(k) for k in body if str(k) not in SEAM_KEYS)
    if extra:
        raise InvalidHandoff(
            f"handoff refuses extra fields {extra} "
            "(guest shape is kind/class/payload_digest)"
        )
    if "kind" not in body:
        raise InvalidKind("", detail="kind is required")
    kind_raw = body.get("kind")
    kind = str(kind_raw or "").strip().lower() if isinstance(kind_raw, str) else ""
    if kind not in WORK_KINDS:
        raise InvalidKind(kind_raw if isinstance(kind_raw, str) else type(kind_raw).__name__)
    if "class" not in body:
        raise InvalidClass("", detail="class is required")
    class_raw = body.get("class")
    cls = str(class_raw or "").strip().lower() if isinstance(class_raw, str) else ""
    if cls not in RESOURCE_CLASSES:
        raise InvalidClass(class_raw if isinstance(class_raw, str) else type(class_raw).__name__)
    if "payload_digest" not in body:
        raise InvalidDigest("payload_digest is required")
    digest_raw = body.get("payload_digest")
    digest = str(digest_raw or "").strip().lower() if isinstance(digest_raw, str) else ""
    if not DIGEST_RE.fullmatch(digest):
        raise InvalidDigest("payload_digest must be sha256:<64 hex>")
    return kind, cls, digest


def parse_submit(body: dict[str, Any]) -> tuple[str, str, str, dict[str, Any] | None]:
    """Route POST /v0/jobs: opaque seam or local demo shortcut."""
    if not isinstance(body, dict):
        raise InvalidHandoff("body must be a JSON object")
    reject_smuggle(body)
    if "demo" in body:
        return parse_demo(body)
    kind, cls, digest = parse_handoff(body)
    return kind, cls, digest, None
