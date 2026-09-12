"""Opaque work handoff aligned with panoramix-runtime #70 Slice B.

Hard reference: runtime/compute_work.py on panoramix-runtime main.
Guest emits WorkHandoff JSON only (kind/class/payload_digest + status/id).
Does not call runtime.apply compute-work. Does not open guest→ctl HTTP.
Reserve catalogs mirror runtime.reserve.recorded_params / live_params /
parity_params / digest_for on panoramix-runtime main (docs/reserve.md).
Ctl export has no nested ``payload`` field. Does not close #70. Does not
unlock #61 / #29.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
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
    LIVE_PARAMS,
    LOCAL_DEMOS,
    PARITY_PARAMS,
    MAX_RESERVE_SECONDS,
    MAX_RESERVE_STAGES,
    MAX_SLEEP_SECONDS,
    MIN_RESERVE_STAGES,
    RECORDED_PARAMS,
    RESERVE_CATALOG_ALIASES,
    RESERVE_CATALOG_RECORDED,
    RESERVE_CATALOG_SAME_JOB,
    RESERVE_PARAM_KEYS,
    RESERVE_WORKLOAD,
    RESOURCE_CLASSES,
    SAME_JOB_CATALOG_ALIASES,
    SAME_JOB_PARAMS,
    SAME_JOB_PAYLOAD_DIGEST,
    WORK_KINDS,
)

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SEAM_KEYS = frozenset({"kind", "class", "payload_digest"})
ECHO_DEMO_KEYS = frozenset({"demo", "message"})
SLEEP_DEMO_KEYS = frozenset({"demo", "seconds"})
RESERVE_DEMO_KEYS = frozenset(
    {
        "demo",
        "catalog",
        "class",
        "label",
        "stages",
        "seconds",
        *RESERVE_PARAM_KEYS,
    }
)
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


HANDOFF_EXPORT_KEYS = ("id", "kind", "class", "payload_digest", "status")


@dataclass(frozen=True)
class ParsedSubmit:
    """Admitted submit: opaque seam fields plus optional stored payload bytes."""

    kind: str
    resource_class: str
    payload_digest: str
    local: dict[str, Any] | None = None
    payload_bytes: bytes | None = None


def canonical_json_bytes(payload: Any) -> bytes:
    """Canonical JSON bytes (same rules as runtime digest_payload for mappings)."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest_bytes(blob: bytes) -> str:
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def digest_canonical(payload: Any) -> str:
    """sha256 of canonical JSON (same separators as runtime digest_payload)."""
    return digest_bytes(canonical_json_bytes(payload))


def payload_export(digest: str, blob: bytes) -> dict[str, Any]:
    """Ctl-facing payload record. No ``payload`` key (runtime submit rejects it)."""
    return {
        "payload_digest": digest,
        "hex": blob.hex(),
        "utf8": blob.decode("utf-8"),
        "encoding": "canonical-json",
    }


def recorded_params() -> dict[str, Any]:
    """Recorded/CI catalog. Mirrors runtime.reserve.recorded_params on main."""
    return dict(RECORDED_PARAMS)


def live_params() -> dict[str, Any]:
    """Live/lab catalog. Mirrors runtime.reserve.live_params on main."""
    return dict(LIVE_PARAMS)


def parity_params() -> dict[str, Any]:
    """Parity-scale catalog. Mirrors runtime.reserve.parity_params on main."""
    return dict(PARITY_PARAMS)


def params_for_catalog(catalog: str) -> dict[str, Any]:
    name = str(catalog or RESERVE_CATALOG_RECORDED).strip().lower()
    if name in SAME_JOB_CATALOG_ALIASES:
        raise InvalidDemo(
            "reserve catalog reserve_ifrs17 / same-job is the iec-local "
            "identity, not the thinner recorded|live|parity kernel"
        )
    resolved = RESERVE_CATALOG_ALIASES.get(name)
    if resolved == "recorded":
        return recorded_params()
    if resolved == "live":
        return live_params()
    if resolved == "parity":
        return parity_params()
    raise InvalidDemo(
        "reserve catalog must be recorded|live|parity or "
        f"reserve_ifrs17|same-job (got {catalog!r})"
    )


def same_job_params() -> dict[str, Any]:
    """Pinned iec reserve_ifrs17 identity. Mirrors runtime.reserve_iec."""
    return dict(SAME_JOB_PARAMS)


def resolve_same_job_catalog(catalog: str | None) -> str | None:
    """reserve_ifrs17 / same-job, or None."""
    name = str(catalog or "").strip().lower()
    return SAME_JOB_CATALOG_ALIASES.get(name)


def payload_for(params: dict[str, Any]) -> dict[str, Any]:
    """Canonical reserve bytes. Mirrors runtime.reserve.payload_for on main.

    Keys match docs/reserve.md (not IFRS17). Guest copies them; it does
    not import runtime.
    """
    return {
        "workload": str(params.get("workload") or RESERVE_WORKLOAD),
        "accounts": int(params["accounts"]),
        "horizon": int(params["horizon"]),
        "paths": int(params["paths"]),
        "seed": int(params["seed"]),
        "lapse_bps": int(params["lapse_bps"]),
        "discount_bps": int(params["discount_bps"]),
    }


def digest_for(params: dict[str, Any]) -> str:
    """sha256 of payload_for canonical JSON.

    Must match runtime.reserve.digest_for on panoramix-runtime main
    (docs/reserve.md).
    Recorded catalog is sha256:77e9299f4b8ea4aeed46f71b91cc947d56e9bd169d795e70845123fef53d7e4e.
    Parity catalog is sha256:e180d2c2e3589b8762f92efa1bedb3d53ffeeb16648581ba13d537bcd3311102.
    """
    return digest_canonical(payload_for(params))


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


def _parse_reserve_int(raw: Any, *, name: str, minimum: int) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise InvalidDemo(f"reserve {name} must be an integer")
    if raw < minimum:
        raise InvalidDemo(f"reserve {name} must be >= {minimum}")
    return raw


def parse_same_job_demo(body: dict[str, Any]) -> ParsedSubmit:
    """iec-local same-job identity. Guest does not run IFRS17 math.

    Payload bytes match ``runtime.reserve_iec.same_job_payload`` /
    ``SAME_JOB_DIGEST`` on panoramix-runtime **main** @ ``d480dc8``
    (docs/iec-local.md). Class is cpu only. Thinner reserve ints
    (accounts/horizon/…) are refused. Optional label/stages/seconds
    are local UX only and are **not** in the digest. Fail-closed on
    the stub — runtime binding runs the iec checkout.
    """
    catalog_raw = body.get("catalog", RESERVE_CATALOG_SAME_JOB)
    if not isinstance(catalog_raw, str):
        raise InvalidDemo("reserve catalog must be a string")
    catalog = resolve_same_job_catalog(catalog_raw)
    if catalog is None:
        raise InvalidDemo(
            "same-job catalog must be reserve_ifrs17|same-job "
            f"(got {catalog_raw!r})"
        )
    for key in RESERVE_PARAM_KEYS:
        if key in body:
            raise InvalidDemo(
                "same-job catalog refuses thinner reserve params "
                f"{key!r} (identity is pinned reserve_ifrs17; "
                "guest does not run IFRS17 math)"
            )
    if "class" not in body:
        cls = "cpu"
    else:
        class_raw = body.get("class")
        cls = str(class_raw or "").strip().lower() if isinstance(class_raw, str) else ""
        if cls != "cpu":
            raise InvalidClass(
                class_raw if isinstance(class_raw, str) else type(class_raw).__name__,
            )
    work = same_job_params()
    blob = canonical_json_bytes(work)
    digest = digest_bytes(blob)
    if digest != SAME_JOB_PAYLOAD_DIGEST:
        raise InvalidDemo(
            "same-job digest drifted from runtime.reserve_iec.SAME_JOB_DIGEST "
            f"(got {digest}; need {SAME_JOB_PAYLOAD_DIGEST})"
        )
    local = {
        "demo": DEMO_RESERVE,
        "catalog": catalog,
        "class": cls,
        "same_job": True,
        "ifrs17_guest": False,
        "workload": work["workload"],
        "revision": work["revision"],
        "source_file": work["source_file"],
        "mode": work["mode"],
    }
    label = body.get("label")
    if isinstance(label, str) and label.strip():
        local["label"] = label.strip()[:MAX_RESERVE_LABEL]
    return ParsedSubmit(
        kind="job",
        resource_class=cls,
        payload_digest=digest,
        local=local,
        payload_bytes=blob,
    )


def parse_reserve_demo(body: dict[str, Any]) -> ParsedSubmit:
    """UX-seed reserve shortcut → synthesized job + stable payload digest.

    Default kind is ``job``, default class is ``cpu``. Optional ``class: gpu``
    is an opaque label only. Payload bytes match runtime.reserve.payload_for
    / digest_for on panoramix-runtime main (docs/reserve.md). Local
    ``label`` / ``stages`` / ``seconds`` are stub UX and are **not** in the
    digest. Guest emits WorkHandoff JSON only — it never calls
    ``runtime.apply compute-work``. Catalog ``reserve_ifrs17`` / ``same-job``
    is the iec-local identity (not this thinner kernel).
    """
    catalog_raw = body.get("catalog", RESERVE_CATALOG_RECORDED)
    if not isinstance(catalog_raw, str):
        raise InvalidDemo("reserve catalog must be a string")
    if resolve_same_job_catalog(catalog_raw) is not None:
        return parse_same_job_demo(body)
    params = params_for_catalog(catalog_raw)
    catalog = RESERVE_CATALOG_ALIASES[catalog_raw.strip().lower()]

    for key in RESERVE_PARAM_KEYS:
        if key not in body:
            continue
        minimum = 0 if key in {"seed", "lapse_bps", "discount_bps"} else 1
        params[key] = _parse_reserve_int(body.get(key), name=key, minimum=minimum)

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

    work = payload_for(params)
    blob = canonical_json_bytes(work)
    local = {
        "demo": DEMO_RESERVE,
        "catalog": catalog,
        "class": cls,
        "label": label,
        "seconds": seconds,
        "stages": stages,
        "accounts": work["accounts"],
        "horizon": work["horizon"],
        "paths": work["paths"],
        "seed": work["seed"],
        "lapse_bps": work["lapse_bps"],
        "discount_bps": work["discount_bps"],
    }
    return ParsedSubmit(
        kind="job",
        resource_class=cls,
        payload_digest=digest_bytes(blob),
        local=local,
        payload_bytes=blob,
    )


def parse_demo(body: dict[str, Any]) -> ParsedSubmit:
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
            "reserve: demo/catalog/class + catalog ints + optional label/stages/seconds)"
        )
    if demo == DEMO_ECHO:
        message = body.get("message", DEFAULT_ECHO_MESSAGE)
        if not isinstance(message, str):
            raise InvalidDemo("echo message must be a string")
        canonical = {"demo": DEMO_ECHO, "message": message}
        blob = canonical_json_bytes(canonical)
        return ParsedSubmit(
            kind="job",
            resource_class="cpu",
            payload_digest=digest_bytes(blob),
            local={"demo": DEMO_ECHO, "message": message},
            payload_bytes=blob,
        )
    if demo == DEMO_SLEEP:
        seconds = _parse_nonneg_seconds(
            body.get("seconds", DEFAULT_SLEEP_SECONDS),
            name="sleep",
            maximum=MAX_SLEEP_SECONDS,
        )
        canonical = {"demo": DEMO_SLEEP, "seconds": seconds}
        blob = canonical_json_bytes(canonical)
        return ParsedSubmit(
            kind="job",
            resource_class="cpu",
            payload_digest=digest_bytes(blob),
            local={"demo": DEMO_SLEEP, "seconds": seconds},
            payload_bytes=blob,
        )
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


def parse_submit(body: dict[str, Any]) -> ParsedSubmit:
    """Route POST /v0/jobs: opaque seam or local demo shortcut."""
    if not isinstance(body, dict):
        raise InvalidHandoff("body must be a JSON object")
    reject_smuggle(body)
    if "demo" in body:
        return parse_demo(body)
    kind, cls, digest = parse_handoff(body)
    return ParsedSubmit(kind=kind, resource_class=cls, payload_digest=digest)
