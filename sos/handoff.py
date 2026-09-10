"""Opaque work handoff aligned with panoramix-runtime #70 Slice B.

Hard reference: runtime/compute_work.py on panoramix-runtime main (not a PR
number). Guest-facing submit shape is ``kind`` / ``class`` /
``payload_digest`` — not engine brands. Local demo echo/sleep/reserve is a
guest-only shortcut that synthesizes that shape before storage. Reserve is a
UX seed stub (not IFRS17 math, not a perf baseline). Does not close #70.
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
    DEFAULT_RESERVE_LABEL,
    DEFAULT_RESERVE_SECONDS,
    DEFAULT_RESERVE_STAGES,
    DEFAULT_SLEEP_SECONDS,
    DEMO_ECHO,
    DEMO_RESERVE,
    DEMO_SLEEP,
    LOCAL_DEMOS,
    MAX_RESERVE_SECONDS,
    MAX_RESERVE_STAGES,
    MAX_SLEEP_SECONDS,
    MIN_RESERVE_STAGES,
    RESOURCE_CLASSES,
    WORK_KINDS,
)

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SEAM_KEYS = frozenset({"kind", "class", "payload_digest"})
ECHO_DEMO_KEYS = frozenset({"demo", "message"})
SLEEP_DEMO_KEYS = frozenset({"demo", "seconds"})
RESERVE_DEMO_KEYS = frozenset({"demo", "label", "stages", "seconds", "class"})
MAX_RESERVE_LABEL = 80

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


def _demo_allowed_keys(demo: str) -> frozenset[str]:
    if demo == DEMO_ECHO:
        return ECHO_DEMO_KEYS
    if demo == DEMO_SLEEP:
        return SLEEP_DEMO_KEYS
    return RESERVE_DEMO_KEYS


def _parse_nonneg_seconds(seconds: Any, *, name: str, maximum: float) -> int | float:
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise InvalidDemo(f"{name} seconds must be a non-negative number")
    if seconds < 0:
        raise InvalidDemo(f"{name} seconds must be a non-negative number")
    if seconds > maximum:
        raise InvalidDemo(f"{name} seconds must be <= {maximum:g}")
    return _canon_seconds(float(seconds))


def parse_reserve_demo(body: dict[str, Any]) -> tuple[str, str, str, dict[str, Any]]:
    """UX-seed reserve shortcut → synthesized job + digest + stub metadata.

    Optional ``class: gpu`` is a seam label only (still in-process; no GPU
    kernels). Not IFRS17 math. Not the named iec baseline ``reserve_ifrs17``.
    """
    label = body.get("label", DEFAULT_RESERVE_LABEL)
    if not isinstance(label, str):
        raise InvalidDemo("reserve label must be a string")
    label = label.strip()
    if not label:
        raise InvalidDemo("reserve label must be a non-empty string")
    if len(label) > MAX_RESERVE_LABEL:
        raise InvalidDemo(f"reserve label must be <= {MAX_RESERVE_LABEL} characters")

    stages = body.get("stages", DEFAULT_RESERVE_STAGES)
    if isinstance(stages, bool) or not isinstance(stages, int):
        raise InvalidDemo("reserve stages must be an integer")
    if stages < MIN_RESERVE_STAGES or stages > MAX_RESERVE_STAGES:
        raise InvalidDemo(
            f"reserve stages must be {MIN_RESERVE_STAGES}..{MAX_RESERVE_STAGES}"
        )

    seconds = _parse_nonneg_seconds(
        body.get("seconds", DEFAULT_RESERVE_SECONDS),
        name="reserve",
        maximum=MAX_RESERVE_SECONDS,
    )

    if "class" not in body:
        cls = "cpu"
    else:
        class_raw = body.get("class")
        cls = str(class_raw or "").strip().lower() if isinstance(class_raw, str) else ""
        if cls not in RESOURCE_CLASSES:
            raise InvalidClass(class_raw if isinstance(class_raw, str) else type(class_raw).__name__)

    canonical = {
        "class": cls,
        "demo": DEMO_RESERVE,
        "label": label,
        "seconds": seconds,
        "stages": stages,
    }
    local = dict(canonical)
    digest = digest_canonical(canonical)
    return "job", cls, digest, local


def parse_demo(body: dict[str, Any]) -> tuple[str, str, str, dict[str, Any]]:
    """Local-only shortcut → synthesized job + digest + stub metadata."""
    demo = body.get("demo")
    if not isinstance(demo, str) or demo.strip().lower() not in LOCAL_DEMOS:
        raise InvalidDemo(demo if isinstance(demo, str) else type(demo).__name__)
    demo = demo.strip().lower()
    extra = sorted(str(k) for k in body if str(k) not in _demo_allowed_keys(demo))
    if extra:
        raise InvalidHandoff(
            f"local demo refuses extra fields {extra} "
            "(echo: demo/message; sleep: demo/seconds; "
            "reserve: demo/label/stages/seconds/class)"
        )
    if demo == DEMO_ECHO:
        message = body.get("message", DEFAULT_ECHO_MESSAGE)
        if not isinstance(message, str):
            raise InvalidDemo("echo message must be a string")
        canonical = {"demo": DEMO_ECHO, "message": message}
        local = {"demo": DEMO_ECHO, "message": message}
        digest = digest_canonical(canonical)
        return "job", "cpu", digest, local
    if demo == DEMO_SLEEP:
        seconds = _parse_nonneg_seconds(
            body.get("seconds", DEFAULT_SLEEP_SECONDS),
            name="sleep",
            maximum=MAX_SLEEP_SECONDS,
        )
        canonical = {"demo": DEMO_SLEEP, "seconds": seconds}
        local = {"demo": DEMO_SLEEP, "seconds": seconds}
        digest = digest_canonical(canonical)
        return "job", "cpu", digest, local
    return parse_reserve_demo(body)


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
