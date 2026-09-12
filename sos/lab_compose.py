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
Not IFRS17. Pin 0.5. WorkHandoff triple only. Optional durable
stage elapsed from runtime tip ``9ba95bbb`` / docs tip
``5dc191cb`` (PR #112, or main); omit when missing — never invent.
Optional durable ``wall_elapsed_ms`` / ``started_at`` from runtime
tip ``9b6646e8`` (PR #114, or main; docs tip ``6511cec7`` / PR
#116 for evidence-index lineage); omit when missing — never
invent. Compare prefers that wall when present. Not a forecast.
Not IFRS17. Not iec SPA. Handoff docs
panel is operator clarity, not a second control plane. Dry-run /
live emit a small paste fragment for runtime #78 D pack fill
(``tips`` when known; optional ``durable`` only when measured
from the hooked run). Documented runtime tip ``b81130f``
(#120 ``runtime.iec_parity_pack skeleton|validate``, or main);
docs tip ``63a168d`` (PR #122 WSL assist-smoke stamp lineage);
gap-report tip ``84cb202`` (PR #124 gap-report);
gap-report docs tip ``aa4f09e`` (PR #126 stamp link, or main);
merge tip ``5086d0f`` (PR #128 ``iec_parity_pack merge``, or main);
merge docs tip ``6ecb645`` (PR #130 stamp link, or main);
apply-metrics tip ``5d399f7`` (PR #132 ``iec_parity_pack
apply-metrics``, or main); apply-metrics docs tip ``3904ee4``
(PR #134 stamp link, or main); apply-notes tip ``48a8645``
(PR #136 ``iec_parity_pack apply-notes``, or main); guest emit
tip ``b859466`` (#52); guest gap-report tip ``eb48605`` (#60);
guest merge tip ``39064d5`` (#64); guest apply-metrics tip
``7c09f32`` (#68). Wall feature tip remains
``9b6646e8``. Guest fragment can feed optional tips / measured
durable into ``python3 -m runtime.iec_parity_pack skeleton``
via ``--from-json`` (file or stdin) or flags; omit durable when
missing. Dry-run / live also record a ``pack_fill.apply_notes``
hint (cd+cmd when ``PANORAMIX_RUNTIME_ROOT`` known, else a
copy-paste template) for ``python3 -m runtime.iec_parity_pack
apply-notes …`` against the off-box pack (does not supply wall
numbers; does not invent UX strings), a ``pack_fill.apply_metrics``
hint for ``apply-metrics … --from-durable-panoramix``, a
``pack_fill.merge`` hint for ``merge … --from-json``, then a
``pack_fill.gap_report`` hint for ``gap-report``. Hint only —
does not run apply-notes, apply-metrics, merge, or gap-report.
Never invent ``metrics.wall_time_sec``. Never invent UX strings.
assist ≠ fill; assist ≠ Done; apply-notes ≠ fill;
apply-notes ≠ Done; apply-metrics ≠ fill;
apply-metrics ≠ Done; merge ≠ fill; merge ≠ Done;
gap-report ≠ Done. Does not write the full live pack.
Does not close runtime
#70 / #78. Does not unlock #61 / #29. Does not
stamp north_star_done or #70 UX Done. Cloud stays locked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from sos.lab_ctl import APPLY_REL
from sos.lab_ctl_http import ENV_CTL_BEARER, ENV_CTL_HTTP, normalize_ctl_http_base
from sos.stage_elapsed import (
    elapsed_ms_from_mapping,
    wall_elapsed_ms_from_durable,
    wall_elapsed_ms_from_mapping,
)

GUEST_LISTEN_ENV = "PLATFORM_LISTEN_HTTP"
DEFAULT_GUEST_PORT = 18280
DEFAULT_CTL_PORT = 19215
DEFAULT_BINDING_REL = "bindings/local-reserve-temporal.example.yaml"
RUNTIME_SERVE_PIN = "fb901542"
RUNTIME_ELAPSED_PIN = "9ba95bbb"
RUNTIME_DOCS_PIN = "5dc191cb"
RUNTIME_WALL_PIN = "9b6646e8"
RUNTIME_WALL_DOCS_PIN = "6511cec7"
# Runtime #120 iec_parity_pack skeleton|validate (or main).
# Schema / #78 D checklist era remains #118.
# Docs tip #122 links the WSL assist-smoke stamp (assist ≠ fill).
# Gap-report tip #124 names the WSL gap-report stamp (gap-report ≠ Done).
# Docs tip #126 links that stamp on main (or tip aa4f09e).
# Merge tip #128 names the WSL merge assist-smoke stamp (merge ≠ fill).
# Docs tip #130 links that stamp on main (or tip 6ecb645).
# Apply-metrics tip #132 names the WSL apply-metrics stamp (apply-metrics ≠ fill).
# Docs tip #134 links that stamp on main (or tip 3904ee4).
# Apply-notes tip #136 names the WSL apply-notes stamp (apply-notes ≠ fill).
RUNTIME_PACK_TIP = "b81130f2187109eabc2342df6345ca877e98023f"
RUNTIME_PACK_DOCS_PIN = "63a168d"
RUNTIME_PACK_GAP_REPORT_PIN = "84cb202"
RUNTIME_PACK_GAP_REPORT_DOCS_PIN = "aa4f09e"
RUNTIME_PACK_MERGE_PIN = "5086d0f"
RUNTIME_PACK_MERGE_DOCS_PIN = "6ecb645"
RUNTIME_PACK_APPLY_METRICS_PIN = "5d399f7"
RUNTIME_PACK_APPLY_METRICS_DOCS_PIN = "3904ee4"
RUNTIME_PACK_APPLY_NOTES_PIN = "48a8645"
OFFBOX_IEC_PARITY_PACK = "~/panoramix-lab/evidence-70/iec-parity/iec-parity.json"
GAP_REPORT_CMD = "python3 -m runtime.iec_parity_pack gap-report"
MERGE_CMD = "python3 -m runtime.iec_parity_pack merge"
MERGE_FROM_JSON = "--from-json -"
APPLY_METRICS_CMD = "python3 -m runtime.iec_parity_pack apply-metrics"
APPLY_METRICS_FROM_DURABLE = "--from-durable-panoramix"
APPLY_NOTES_CMD = "python3 -m runtime.iec_parity_pack apply-notes"
RUNTIME_ROOT_TEMPLATE = "/path/to/panoramix-runtime"
# Guest main after #52 (emit tips + optional durable). Checkout HEAD wins.
GUEST_PACK_TIP = "b859466dcd079eb063b615728b258a686f79749a"
# Guest main after #60 (gap-report hint). Mention only — emit tip stays #52.
GUEST_GAP_REPORT_TIP = "eb48605"
# Guest main after #64 (merge docs pin). Mention only — emit tip stays #52.
GUEST_MERGE_TIP = "39064d5"
# Guest main after #68 (apply-metrics docs pin). Mention only — emit tip stays #52.
GUEST_APPLY_METRICS_TIP = "7c09f32"
ENV_RUNTIME_TIP = "PANORAMIX_RUNTIME_TIP"
ENV_GUEST_TIP = "PANORAMIX_GUEST_TIP"
RECORDED_RESERVE_BODY: dict[str, Any] = {"demo": "reserve", "catalog": "recorded"}
_SHA_CHARS = frozenset("0123456789abcdefABCDEF")

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
    "optional durable stage elapsed from runtime tip 9ba95bbb / docs tip 5dc191cb (or main)",
    "optional durable wall_elapsed_ms from runtime tip 9b6646e8 (or main; omit when missing)",
    "compare prefers durable wall_elapsed_ms when present (runtime tip 9b6646e8 / main; omit when missing)",
    "handoff docs panel is operator clarity (not a second control plane)",
    "pack-fill tips from checkout / env / documented tip (omit when missing)",
    "pack-fill durable wall/stage elapsed only when measured from hooked run (omit when missing; never invent)",
    "pack-fill emit fragment can feed runtime.iec_parity_pack skeleton via --from-json / flags (measured durable only; omit when missing)",
    "pack-fill docs tip 63a168d / PR #122 names WSL assist-smoke stamp lineage (assist ≠ fill)",
    "pack-fill gap-report tip 84cb202 / PR #124 names WSL gap-report stamp lineage (gap-report ≠ Done; assist ≠ fill)",
    "pack-fill gap-report docs tip aa4f09e / PR #126 (or main) links WSL gap-report stamp (gap-report ≠ Done)",
    "pack-fill gap-report hint is cd+cmd when PANORAMIX_RUNTIME_ROOT known else copy-paste template (does not run gap-report; gap-report ≠ Done)",
    "pack-fill merge tip 5086d0f / PR #128 (or main) names WSL merge assist-smoke stamp lineage (merge ≠ fill; merge ≠ Done; assist ≠ Done)",
    "pack-fill merge docs tip 6ecb645 / PR #130 (or main) links WSL merge stamp (merge ≠ fill; merge ≠ Done; assist ≠ Done)",
    "pack-fill merge hint is cd+cmd when PANORAMIX_RUNTIME_ROOT known else copy-paste template (does not run merge; merge ≠ fill; merge ≠ Done)",
    "pack-fill merge+gap-report pairing (hint only; merge ≠ fill; merge ≠ Done; assist ≠ Done; gap-report ≠ Done)",
    "pack-fill apply-metrics tip 5d399f7 / PR #132 (or main) names WSL apply-metrics assist-smoke stamp lineage (apply-metrics ≠ fill; apply-metrics ≠ Done; assist ≠ Done; smoke walls ≠ Done)",
    "pack-fill apply-metrics docs tip 3904ee4 / PR #134 (or main) links WSL apply-metrics stamp (apply-metrics ≠ fill; apply-metrics ≠ Done; assist ≠ Done)",
    "pack-fill apply-metrics hint is cd+cmd when PANORAMIX_RUNTIME_ROOT known else copy-paste template (does not run apply-metrics; does not supply wall numbers; apply-metrics ≠ fill; apply-metrics ≠ Done)",
    "pack-fill apply-metrics+merge+gap-report pairing (hint only; apply-metrics ≠ fill; apply-metrics ≠ Done; assist ≠ Done; merge ≠ fill; merge ≠ Done; gap-report ≠ Done)",
    "pack-fill apply-notes tip 48a8645 / PR #136 (or main) names WSL apply-notes assist-smoke stamp lineage (apply-notes ≠ fill; apply-notes ≠ Done; assist ≠ Done; smoke notes ≠ Done)",
    "pack-fill apply-notes hint is cd+cmd when PANORAMIX_RUNTIME_ROOT known else copy-paste template (does not run apply-notes; does not supply wall numbers; does not invent UX strings; apply-notes ≠ fill; apply-notes ≠ Done)",
    "pack-fill apply-notes+apply-metrics+merge+gap-report pairing (hint only; apply-notes ≠ fill; apply-notes ≠ Done; apply-metrics ≠ fill; apply-metrics ≠ Done; assist ≠ Done; merge ≠ fill; merge ≠ Done; gap-report ≠ Done)",
    "never invent metrics.wall_time_sec",
    "never invent UX strings",
    "assist ≠ fill; assist ≠ Done",
    "apply-notes ≠ fill; apply-notes ≠ Done",
    "apply-metrics ≠ fill; apply-metrics ≠ Done",
    "merge ≠ fill; merge ≠ Done",
    "gap-report ≠ Done",
    "pack-fill assist for runtime #78 D only (does not write the live pack)",
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
            "wall_elapsed": wall_plan(),
            "handoff_docs": handoff_docs_plan(),
            "pack_fill": pack_fill_plan(
                guest_root=self.guest_cwd,
                runtime_root=self.runtime_root,
            ),
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
        "runtime_tip": RUNTIME_ELAPSED_PIN,
        "docs_tip": RUNTIME_DOCS_PIN,
        "or": "main",
        "runtime_pr": 110,
        "docs_pr": 112,
        "omit_when_missing": True,
        "invent": False,
        "north_star_done": False,
        "note": (
            "Optional per-stage elapsed on the path-slice timeline. "
            f"Runtime tip {RUNTIME_ELAPSED_PIN} (or main, PR #110) can "
            "supply durable stages[].elapsed_ms on progress. Docs tip "
            f"{RUNTIME_DOCS_PIN} after PR #112 pins that lineage on main. "
            "Prefer progress elapsed_ms when present; else derive from "
            "durable event timestamps. Omit when missing. Never invent. "
            "Not iec planner. Not #70 Done."
        ),
    }


def wall_plan() -> dict[str, Any]:
    """Dry-run honesty for optional durable job wall. No invented numbers."""
    return {
        "when": "durable progress/status wall_elapsed_ms / started_at (or equivalent)",
        "runtime_tip": RUNTIME_WALL_PIN,
        "docs_tip": RUNTIME_WALL_DOCS_PIN,
        "or": "main",
        "runtime_pr": 114,
        "docs_pr": 116,
        "omit_when_missing": True,
        "invent": False,
        "forecast": False,
        "ifrs17": False,
        "iec_spa": False,
        "north_star_done": False,
        "note": (
            "Optional durable job wall on job detail / progress / compare. "
            f"Runtime tip {RUNTIME_WALL_PIN} (or main, PR #114) can "
            "supply durable wall_elapsed_ms / started_at on "
            "status/progress. Docs tip "
            f"{RUNTIME_WALL_DOCS_PIN} (PR #116) is evidence-index lineage. "
            "Compare prefers this wall when present; persist on the job "
            "record for priors across restart. Accept when hook JSON "
            "includes the field. Omit when missing. Never invent. "
            "Not a forecast. Not IFRS17. Not iec SPA. Not #70 Done."
        ),
    }


def handoff_docs_plan() -> dict[str, Any]:
    """Dry-run honesty for the compact handoff docs panel."""
    return {
        "panel": True,
        "second_control_plane": False,
        "covers": (
            "handoff + payload export",
            "recoverability / re-admit",
            "lab-compose",
        ),
        "north_star_done": False,
        "note": (
            "Job-detail Handoff docs panel is operator clarity only — "
            "not a second control plane. Not guest→mesh ctl. "
            "Not #70 Done. Not SIEM. Not IFRS17."
        ),
    }


def looks_like_git_tip(value: str | None) -> str | None:
    """Accept a hex SHA of at least 7 chars. Omit otherwise."""
    text = str(value or "").strip()
    if len(text) < 7:
        return None
    if not all(char in _SHA_CHARS for char in text):
        return None
    return text


def _sha_from_packed_refs(packed: Path, ref: str) -> str | None:
    if not packed.is_file():
        return None
    try:
        text = packed.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or raw.startswith("^"):
            continue
        parts = raw.split()
        if len(parts) >= 2 and parts[1] == ref:
            return looks_like_git_tip(parts[0])
    return None


def git_head_sha(root: str | Path | None) -> str | None:
    """Read checkout HEAD SHA from ``.git``. No spawn. Omit if unknown."""
    if root is None or not str(root).strip():
        return None
    path = Path(root)
    try:
        path = path.expanduser()
        if not path.exists():
            return None
        path = path.resolve()
    except OSError:
        return None
    git_dir = path / ".git"
    try:
        if git_dir.is_file():
            raw = git_dir.read_text(encoding="utf-8").strip()
            if raw.lower().startswith("gitdir:"):
                nested = Path(raw.split(":", 1)[1].strip())
                git_dir = nested if nested.is_absolute() else (path / nested)
                git_dir = git_dir.resolve()
        if not git_dir.is_dir():
            return None
        head_path = git_dir / "HEAD"
        if not head_path.is_file():
            return None
        head = head_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if head.startswith("ref:"):
        ref = head.split(":", 1)[1].strip()
        ref_file = git_dir / ref
        try:
            if ref_file.is_file():
                return looks_like_git_tip(ref_file.read_text(encoding="utf-8").strip())
        except OSError:
            return None
        return _sha_from_packed_refs(git_dir / "packed-refs", ref)
    return looks_like_git_tip(head)


def resolve_known_tip(
    *,
    checkout: str | Path | None = None,
    env_value: str | None = None,
    documented: str | None = None,
) -> tuple[str | None, str | None]:
    """Prefer checkout HEAD, then env, then documented tip. Omit if none."""
    sha = git_head_sha(checkout)
    if sha:
        return sha, "checkout"
    sha = looks_like_git_tip(env_value)
    if sha:
        return sha, "env"
    sha = looks_like_git_tip(documented)
    if sha:
        return sha, "documented"
    return None, None


def _tip_env(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    if environ is not None:
        return environ
    import os

    return os.environ


def measured_wall_elapsed_ms(progress: Mapping[str, Any]) -> int | None:
    """Honest job wall from hooked durable progress. Never guest clocks."""
    if not isinstance(progress, Mapping):
        return None
    blob = dict(progress)
    if wall_elapsed_ms_from_mapping(blob) is not None or any(
        key in blob
        for key in (
            "wall_elapsed_ms",
            "wall_ms",
            "job_elapsed_ms",
            "job_wall_ms",
            "wall_elapsed_s",
            "wall_s",
            "job_elapsed_s",
            "job_wall_s",
            "wall_elapsed_sec",
        )
    ):
        return wall_elapsed_ms_from_mapping(blob)
    return wall_elapsed_ms_from_durable(blob)


def measured_stage_elapsed_ms(progress: Mapping[str, Any]) -> list[int] | None:
    """Honest per-stage elapsed from hooked durable progress. Omit if none."""
    if not isinstance(progress, Mapping):
        return None
    values: list[int] = []
    for key in ("timeline", "stages"):
        raw = progress.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            ms = elapsed_ms_from_mapping(item)
            if ms is not None:
                values.append(ms)
        if values:
            return values
    raw_list = progress.get("stage_elapsed_ms")
    if isinstance(raw_list, list):
        for item in raw_list:
            ms = elapsed_ms_from_mapping({"elapsed_ms": item})
            if ms is not None:
                values.append(ms)
    return values or None


def durable_pack_observations(
    progress: Mapping[str, Any] | None,
    *,
    hooked: bool,
) -> dict[str, Any] | None:
    """Optional ``durable.*`` from a hooked run only. Fail-closed otherwise.

    Omit when missing. Never invent. Not a forecast. Not IFRS17. Not iec SPA.
    """
    if not hooked or not isinstance(progress, Mapping):
        return None
    if progress.get("source") != "durable":
        return None
    out: dict[str, Any] = {}
    wall = measured_wall_elapsed_ms(progress)
    if wall is not None:
        out["wall_elapsed_ms"] = {"panoramix": wall}
    stages = measured_stage_elapsed_ms(progress)
    if stages:
        out["stage_elapsed_ms"] = {"panoramix": stages}
    return out or None


def pack_fill_fragment(
    *,
    guest_root: str | Path | None = None,
    runtime_root: str | Path | None = None,
    runtime_tip: str | None = None,
    guest_tip: str | None = None,
    progress: Mapping[str, Any] | None = None,
    hooked: bool = False,
    environ: Mapping[str, str] | None = None,
    documented_runtime_tip: str | None = RUNTIME_PACK_TIP,
    documented_guest_tip: str | None = GUEST_PACK_TIP,
) -> dict[str, Any]:
    """Paste-ready ``tips`` / optional ``durable`` for the off-box pack.

    Tips when known (checkout / env / documented). Durable only when
    measured from the hooked run. Omit when missing. Never invent.
    Does not write the live pack file.
    """
    env = _tip_env(environ)
    runtime_sha, _src = resolve_known_tip(
        checkout=runtime_root,
        env_value=runtime_tip if runtime_tip is not None else env.get(ENV_RUNTIME_TIP),
        documented=documented_runtime_tip,
    )
    guest_sha, _gsrc = resolve_known_tip(
        checkout=guest_root,
        env_value=guest_tip if guest_tip is not None else env.get(ENV_GUEST_TIP),
        documented=documented_guest_tip,
    )
    fragment: dict[str, Any] = {}
    tips: dict[str, str] = {}
    if runtime_sha:
        tips["panoramix_runtime_tip"] = runtime_sha
    if guest_sha:
        tips["guest_tip"] = guest_sha
    if tips:
        fragment["tips"] = tips
    durable = durable_pack_observations(progress, hooked=hooked)
    if durable:
        fragment["durable"] = durable
    return fragment


def skeleton_handoff_plan() -> dict[str, Any]:
    """Guest emit → ``runtime.iec_parity_pack skeleton``. Assist ≠ fill."""
    return {
        "cmd": "python3 -m runtime.iec_parity_pack skeleton",
        "validate_cmd": "python3 -m runtime.iec_parity_pack validate",
        "runtime_tip": RUNTIME_PACK_TIP,
        "runtime_pr": 120,
        "docs_tip": RUNTIME_PACK_DOCS_PIN,
        "docs_pr": 122,
        "gap_report_tip": RUNTIME_PACK_GAP_REPORT_PIN,
        "gap_report_pr": 124,
        "gap_report_docs_tip": RUNTIME_PACK_GAP_REPORT_DOCS_PIN,
        "gap_report_docs_pr": 126,
        "merge_tip": RUNTIME_PACK_MERGE_PIN,
        "merge_pr": 128,
        "merge_docs_tip": RUNTIME_PACK_MERGE_DOCS_PIN,
        "merge_docs_pr": 130,
        "apply_metrics_tip": RUNTIME_PACK_APPLY_METRICS_PIN,
        "apply_metrics_pr": 132,
        "apply_metrics_docs_tip": RUNTIME_PACK_APPLY_METRICS_DOCS_PIN,
        "apply_metrics_docs_pr": 134,
        "apply_notes_tip": RUNTIME_PACK_APPLY_NOTES_PIN,
        "apply_notes_pr": 136,
        "guest_emit_tip": GUEST_PACK_TIP,
        "guest_pr": 52,
        "from_json": True,
        "stdin": True,
        "flags": (
            "--from-json",
            "--panoramix-runtime-tip",
            "--guest-tip",
            "--durable-wall-elapsed-ms-panoramix",
            "--durable-stage-elapsed-ms-panoramix",
        ),
        "durable_only_when_measured": True,
        "omit_when_missing": True,
        "invent": False,
        "invent_wall_time_sec": False,
        "writes_live_pack": False,
        "assist_ne_fill": True,
        "north_star_done": False,
        "note": (
            "Guest pack_fill.fragment can feed optional tips / measured "
            "durable into python3 -m runtime.iec_parity_pack skeleton via "
            "--from-json (file or stdin -) or CLI flags. Durable only when "
            "measured. Omit when missing. Never invent metrics.wall_time_sec. "
            "Never stamp north_star_done. assist ≠ fill; assist ≠ Done. "
            f"Runtime tip {RUNTIME_PACK_TIP} (PR #120, or main). "
            f"Docs tip {RUNTIME_PACK_DOCS_PIN} (PR #122 WSL assist-smoke "
            "stamp lineage). "
            f"Gap-report tip {RUNTIME_PACK_GAP_REPORT_PIN} (PR #124 "
            "gap-report ≠ Done). "
            f"Gap-report docs tip {RUNTIME_PACK_GAP_REPORT_DOCS_PIN} "
            "(PR #126, or main). "
            f"Merge tip {RUNTIME_PACK_MERGE_PIN} (PR #128, or main). "
            f"Merge docs tip {RUNTIME_PACK_MERGE_DOCS_PIN} "
            "(PR #130, or main). "
            f"Apply-metrics tip {RUNTIME_PACK_APPLY_METRICS_PIN} "
            "(PR #132, or main). "
            f"Apply-metrics docs tip {RUNTIME_PACK_APPLY_METRICS_DOCS_PIN} "
            "(PR #134, or main). "
            f"Apply-notes tip {RUNTIME_PACK_APPLY_NOTES_PIN} "
            "(PR #136, or main). "
            f"Guest emit tip {GUEST_PACK_TIP} (PR #52). "
            "Does not write the live pack. Not #70 Done. Not #78 Done."
        ),
    }


def _known_runtime_root(runtime_root: str | Path | None) -> str | None:
    """Non-empty ``PANORAMIX_RUNTIME_ROOT`` / plan path, or None."""
    if runtime_root is None:
        return None
    text = str(runtime_root).strip()
    if not text:
        return None
    try:
        return str(Path(text).expanduser())
    except OSError:
        return text


def gap_report_plan(
    *,
    runtime_root: str | Path | None = None,
) -> dict[str, Any]:
    """Hint for ``runtime.iec_parity_pack gap-report``. Does not run it.

    When ``PANORAMIX_RUNTIME_ROOT`` is known, show cd+cmd. Else a
    copy-paste template. merge+gap-report pairing. assist ≠ fill;
    gap-report ≠ Done. Never invent walls. Does not write the pack.
    """
    known = _known_runtime_root(runtime_root)
    template = known is None
    cd = known if known is not None else RUNTIME_ROOT_TEMPLATE
    hint = f"cd {cd} && {GAP_REPORT_CMD} {OFFBOX_IEC_PARITY_PACK}"
    return {
        "cmd": GAP_REPORT_CMD,
        "pack": OFFBOX_IEC_PARITY_PACK,
        "cd": cd,
        "hint": hint,
        "template": template,
        "runtime_root_known": not template,
        "executes": False,
        "executes_in_ci": False,
        "runtime_tip": RUNTIME_PACK_GAP_REPORT_DOCS_PIN,
        "or": "main",
        "runtime_pr": 126,
        "gap_report_tip": RUNTIME_PACK_GAP_REPORT_PIN,
        "gap_report_pr": 124,
        "docs_tip": RUNTIME_PACK_DOCS_PIN,
        "docs_pr": 122,
        "merge_tip": RUNTIME_PACK_MERGE_PIN,
        "merge_pr": 128,
        "merge_docs_tip": RUNTIME_PACK_MERGE_DOCS_PIN,
        "merge_docs_pr": 130,
        "apply_metrics_tip": RUNTIME_PACK_APPLY_METRICS_PIN,
        "apply_metrics_pr": 132,
        "apply_metrics_docs_tip": RUNTIME_PACK_APPLY_METRICS_DOCS_PIN,
        "apply_metrics_docs_pr": 134,
        "apply_notes_tip": RUNTIME_PACK_APPLY_NOTES_PIN,
        "apply_notes_pr": 136,
        "wall_feature_tip": RUNTIME_WALL_PIN,
        "omit_when_missing": True,
        "invent": False,
        "invent_wall_time_sec": False,
        "forecast": False,
        "ifrs17": False,
        "iec_spa": False,
        "writes_live_pack": False,
        "assist_ne_fill": True,
        "apply_notes_ne_fill": True,
        "apply_notes_ne_done": True,
        "apply_metrics_ne_fill": True,
        "apply_metrics_ne_done": True,
        "merge_ne_fill": True,
        "merge_ne_done": True,
        "gap_report_ne_done": True,
        "north_star_done": False,
        "note": (
            "After pack_fill.merge (python3 -m runtime.iec_parity_pack "
            "merge … --from-json), optional pack_fill.apply_metrics, "
            "and optional pack_fill.apply_notes, "
            "run python3 -m runtime.iec_parity_pack "
            "gap-report against that pack. "
            "apply-notes+apply-metrics+merge+gap-report pairing. "
            "Hint only — does not run gap-report here or in CI. "
            "When PANORAMIX_RUNTIME_ROOT is known, hint is cd+cmd; "
            "else a copy-paste template. Never invent metrics.wall_time_sec. "
            "Never invent UX strings. "
            "Never stamp north_star_done. apply-notes ≠ fill; "
            "apply-notes ≠ Done; apply-metrics ≠ fill; "
            "apply-metrics ≠ Done; merge ≠ fill; merge ≠ Done; "
            "assist ≠ fill; assist ≠ Done; gap-report ≠ Done. "
            f"Runtime tip {RUNTIME_PACK_GAP_REPORT_DOCS_PIN} (PR #126, or main). "
            f"Gap-report tip remains {RUNTIME_PACK_GAP_REPORT_PIN} (PR #124). "
            f"Merge tip {RUNTIME_PACK_MERGE_PIN} (PR #128, or main). "
            f"Merge docs tip {RUNTIME_PACK_MERGE_DOCS_PIN} "
            "(PR #130, or main). "
            f"Apply-metrics tip {RUNTIME_PACK_APPLY_METRICS_PIN} "
            "(PR #132, or main). "
            f"Apply-metrics docs tip {RUNTIME_PACK_APPLY_METRICS_DOCS_PIN} "
            "(PR #134, or main). "
            f"Apply-notes tip {RUNTIME_PACK_APPLY_NOTES_PIN} "
            "(PR #136, or main). "
            f"Wall feature tip remains {RUNTIME_WALL_PIN}. "
            "Does not write the live pack. Not #70 Done. Not #78 Done."
        ),
    }


def merge_plan(
    *,
    runtime_root: str | Path | None = None,
) -> dict[str, Any]:
    """Hint for ``runtime.iec_parity_pack merge``. Does not run it.

    When ``PANORAMIX_RUNTIME_ROOT`` is known, show cd+cmd. Else a
    copy-paste template. merge+gap-report pairing. merge ≠ fill;
    merge ≠ Done; assist ≠ Done. Never invent walls. Does not
    write the pack.
    """
    known = _known_runtime_root(runtime_root)
    template = known is None
    cd = known if known is not None else RUNTIME_ROOT_TEMPLATE
    hint = f"cd {cd} && {MERGE_CMD} {OFFBOX_IEC_PARITY_PACK} {MERGE_FROM_JSON}"
    return {
        "cmd": MERGE_CMD,
        "pack": OFFBOX_IEC_PARITY_PACK,
        "from_json": True,
        "from_json_arg": MERGE_FROM_JSON,
        "cd": cd,
        "hint": hint,
        "template": template,
        "runtime_root_known": not template,
        "executes": False,
        "executes_in_ci": False,
        "runtime_tip": RUNTIME_PACK_MERGE_PIN,
        "or": "main",
        "runtime_pr": 128,
        "gap_report_tip": RUNTIME_PACK_GAP_REPORT_PIN,
        "gap_report_pr": 124,
        "gap_report_docs_tip": RUNTIME_PACK_GAP_REPORT_DOCS_PIN,
        "gap_report_docs_pr": 126,
        "docs_tip": RUNTIME_PACK_DOCS_PIN,
        "docs_pr": 122,
        "merge_docs_tip": RUNTIME_PACK_MERGE_DOCS_PIN,
        "merge_docs_pr": 130,
        "apply_metrics_tip": RUNTIME_PACK_APPLY_METRICS_PIN,
        "apply_metrics_pr": 132,
        "apply_metrics_docs_tip": RUNTIME_PACK_APPLY_METRICS_DOCS_PIN,
        "apply_metrics_docs_pr": 134,
        "apply_notes_tip": RUNTIME_PACK_APPLY_NOTES_PIN,
        "apply_notes_pr": 136,
        "wall_feature_tip": RUNTIME_WALL_PIN,
        "guest_gap_report_tip": GUEST_GAP_REPORT_TIP,
        "guest_gap_report_pr": 60,
        "omit_when_missing": True,
        "invent": False,
        "invent_wall_time_sec": False,
        "forecast": False,
        "ifrs17": False,
        "iec_spa": False,
        "writes_live_pack": False,
        "assist_ne_fill": True,
        "merge_ne_fill": True,
        "merge_ne_done": True,
        "gap_report_ne_done": True,
        "north_star_done": False,
        "note": (
            "Overlay pack_fill.fragment tips / measured durable into the "
            "off-box iec-parity pack with python3 -m runtime.iec_parity_pack "
            "merge … --from-json (file or stdin -). Then run gap-report "
            "(pack_fill.gap_report). merge+gap-report pairing. "
            "Hint only — does not run merge here or in CI. "
            "When PANORAMIX_RUNTIME_ROOT is known, hint is cd+cmd; "
            "else a copy-paste template. Never invent metrics.wall_time_sec. "
            "Never stamp north_star_done. merge ≠ fill; merge ≠ Done; "
            "assist ≠ Done; gap-report ≠ Done. "
            f"Runtime tip {RUNTIME_PACK_MERGE_PIN} (PR #128, or main). "
            f"Merge docs tip {RUNTIME_PACK_MERGE_DOCS_PIN} "
            "(PR #130, or main). "
            f"Gap-report tip remains {RUNTIME_PACK_GAP_REPORT_PIN} (PR #124). "
            f"Apply-metrics tip {RUNTIME_PACK_APPLY_METRICS_PIN} "
            "(PR #132, or main). "
            f"Apply-metrics docs tip {RUNTIME_PACK_APPLY_METRICS_DOCS_PIN} "
            "(PR #134, or main). "
            f"Apply-notes tip {RUNTIME_PACK_APPLY_NOTES_PIN} "
            "(PR #136, or main). "
            f"Wall feature tip remains {RUNTIME_WALL_PIN}. "
            "Does not write the live pack. Not #70 Done. Not #78 Done."
        ),
    }


def apply_metrics_plan(
    *,
    runtime_root: str | Path | None = None,
) -> dict[str, Any]:
    """Hint for ``runtime.iec_parity_pack apply-metrics``. Does not run it.

    When ``PANORAMIX_RUNTIME_ROOT`` is known, show cd+cmd. Else a
    copy-paste template. apply-metrics+merge+gap-report pairing.
    apply-metrics ≠ fill; apply-metrics ≠ Done; assist ≠ Done.
    Does not supply wall numbers. Never invent walls. Does not
    write the pack.
    """
    known = _known_runtime_root(runtime_root)
    template = known is None
    cd = known if known is not None else RUNTIME_ROOT_TEMPLATE
    hint = (
        f"cd {cd} && {APPLY_METRICS_CMD} {OFFBOX_IEC_PARITY_PACK} "
        f"{APPLY_METRICS_FROM_DURABLE}"
    )
    return {
        "cmd": APPLY_METRICS_CMD,
        "pack": OFFBOX_IEC_PARITY_PACK,
        "from_durable_panoramix": True,
        "from_durable_arg": APPLY_METRICS_FROM_DURABLE,
        "cd": cd,
        "hint": hint,
        "template": template,
        "runtime_root_known": not template,
        "executes": False,
        "executes_in_ci": False,
        "supplies_wall_numbers": False,
        "runtime_tip": RUNTIME_PACK_APPLY_METRICS_PIN,
        "or": "main",
        "runtime_pr": 132,
        "apply_metrics_docs_tip": RUNTIME_PACK_APPLY_METRICS_DOCS_PIN,
        "apply_metrics_docs_pr": 134,
        "apply_notes_tip": RUNTIME_PACK_APPLY_NOTES_PIN,
        "apply_notes_pr": 136,
        "merge_tip": RUNTIME_PACK_MERGE_PIN,
        "merge_pr": 128,
        "merge_docs_tip": RUNTIME_PACK_MERGE_DOCS_PIN,
        "merge_docs_pr": 130,
        "gap_report_tip": RUNTIME_PACK_GAP_REPORT_PIN,
        "gap_report_pr": 124,
        "gap_report_docs_tip": RUNTIME_PACK_GAP_REPORT_DOCS_PIN,
        "gap_report_docs_pr": 126,
        "docs_tip": RUNTIME_PACK_DOCS_PIN,
        "docs_pr": 122,
        "wall_feature_tip": RUNTIME_WALL_PIN,
        "guest_merge_tip": GUEST_MERGE_TIP,
        "guest_merge_pr": 64,
        "omit_when_missing": True,
        "invent": False,
        "invent_wall_time_sec": False,
        "forecast": False,
        "ifrs17": False,
        "iec_spa": False,
        "writes_live_pack": False,
        "assist_ne_fill": True,
        "apply_notes_ne_fill": True,
        "apply_notes_ne_done": True,
        "apply_metrics_ne_fill": True,
        "apply_metrics_ne_done": True,
        "merge_ne_fill": True,
        "merge_ne_done": True,
        "gap_report_ne_done": True,
        "north_star_done": False,
        "note": (
            "After merge (pack_fill.merge), write operator-measured live "
            "walls with python3 -m runtime.iec_parity_pack apply-metrics "
            "… --from-durable-panoramix (derive panoramix seconds from "
            "already-present durable.wall_elapsed_ms.panoramix; refuse if "
            "missing). Hint does not supply wall numbers. Then optional "
            "apply-notes (pack_fill.apply_notes) and run "
            "gap-report (pack_fill.gap_report). "
            "apply-notes+apply-metrics+merge+gap-report pairing. "
            "Hint only — does not run apply-metrics here or in CI. "
            "When PANORAMIX_RUNTIME_ROOT is known, hint is cd+cmd; "
            "else a copy-paste template. Never invent metrics.wall_time_sec. "
            "Never invent UX strings. "
            "Never stamp north_star_done. apply-metrics ≠ fill; "
            "apply-metrics ≠ Done; assist ≠ Done; merge ≠ fill; "
            "merge ≠ Done; gap-report ≠ Done. apply-notes ≠ fill; "
            "apply-notes ≠ Done. "
            f"Runtime tip {RUNTIME_PACK_APPLY_METRICS_PIN} (PR #132, or main). "
            f"Apply-metrics docs tip {RUNTIME_PACK_APPLY_METRICS_DOCS_PIN} "
            "(PR #134, or main). "
            f"Apply-notes tip {RUNTIME_PACK_APPLY_NOTES_PIN} "
            "(PR #136, or main). "
            f"Merge tip remains {RUNTIME_PACK_MERGE_PIN} (PR #128). "
            f"Gap-report tip remains {RUNTIME_PACK_GAP_REPORT_PIN} (PR #124). "
            f"Wall feature tip remains {RUNTIME_WALL_PIN}. "
            "Does not write the live pack. Not #70 Done. Not #78 Done."
        ),
    }


def apply_notes_plan(
    *,
    runtime_root: str | Path | None = None,
) -> dict[str, Any]:
    """Hint for ``runtime.iec_parity_pack apply-notes``. Does not run it.

    When ``PANORAMIX_RUNTIME_ROOT`` is known, show cd+cmd. Else a
    copy-paste template. apply-notes+apply-metrics+merge+gap-report
    pairing. apply-notes ≠ fill; apply-notes ≠ Done; assist ≠ Done.
    Does not supply wall numbers. Does not invent UX strings.
    Never invent walls. Does not write the pack.
    """
    known = _known_runtime_root(runtime_root)
    template = known is None
    cd = known if known is not None else RUNTIME_ROOT_TEMPLATE
    hint = f"cd {cd} && {APPLY_NOTES_CMD} {OFFBOX_IEC_PARITY_PACK}"
    return {
        "cmd": APPLY_NOTES_CMD,
        "pack": OFFBOX_IEC_PARITY_PACK,
        "cd": cd,
        "hint": hint,
        "template": template,
        "runtime_root_known": not template,
        "executes": False,
        "executes_in_ci": False,
        "supplies_wall_numbers": False,
        "invents_ux_strings": False,
        "runtime_tip": RUNTIME_PACK_APPLY_NOTES_PIN,
        "or": "main",
        "runtime_pr": 136,
        "apply_metrics_tip": RUNTIME_PACK_APPLY_METRICS_PIN,
        "apply_metrics_pr": 132,
        "apply_metrics_docs_tip": RUNTIME_PACK_APPLY_METRICS_DOCS_PIN,
        "apply_metrics_docs_pr": 134,
        "merge_tip": RUNTIME_PACK_MERGE_PIN,
        "merge_pr": 128,
        "merge_docs_tip": RUNTIME_PACK_MERGE_DOCS_PIN,
        "merge_docs_pr": 130,
        "gap_report_tip": RUNTIME_PACK_GAP_REPORT_PIN,
        "gap_report_pr": 124,
        "gap_report_docs_tip": RUNTIME_PACK_GAP_REPORT_DOCS_PIN,
        "gap_report_docs_pr": 126,
        "docs_tip": RUNTIME_PACK_DOCS_PIN,
        "docs_pr": 122,
        "wall_feature_tip": RUNTIME_WALL_PIN,
        "guest_apply_metrics_tip": GUEST_APPLY_METRICS_TIP,
        "guest_apply_metrics_pr": 68,
        "omit_when_missing": True,
        "invent": False,
        "invent_wall_time_sec": False,
        "invent_ux_strings": False,
        "forecast": False,
        "ifrs17": False,
        "iec_spa": False,
        "writes_live_pack": False,
        "assist_ne_fill": True,
        "apply_notes_ne_fill": True,
        "apply_notes_ne_done": True,
        "apply_metrics_ne_fill": True,
        "apply_metrics_ne_done": True,
        "merge_ne_fill": True,
        "merge_ne_done": True,
        "gap_report_ne_done": True,
        "north_star_done": False,
        "note": (
            "After apply-metrics (pack_fill.apply_metrics), write "
            "operator-supplied live UX notes with python3 -m "
            "runtime.iec_parity_pack apply-notes (flags and/or "
            "--from-json; strings only; omit when missing). "
            "Hint does not supply wall numbers or invent UX strings. "
            "Then run gap-report (pack_fill.gap_report). "
            "apply-notes+apply-metrics+merge+gap-report pairing. "
            "Hint only — does not run apply-notes here or in CI. "
            "When PANORAMIX_RUNTIME_ROOT is known, hint is cd+cmd; "
            "else a copy-paste template. Never invent metrics.wall_time_sec. "
            "Never invent UX strings. "
            "Never stamp north_star_done. apply-notes ≠ fill; "
            "apply-notes ≠ Done; assist ≠ Done; apply-metrics ≠ fill; "
            "apply-metrics ≠ Done; merge ≠ fill; merge ≠ Done; "
            "gap-report ≠ Done. "
            f"Runtime tip {RUNTIME_PACK_APPLY_NOTES_PIN} (PR #136, or main). "
            f"Apply-metrics tip remains {RUNTIME_PACK_APPLY_METRICS_PIN} "
            "(PR #132). "
            f"Apply-metrics docs tip remains "
            f"{RUNTIME_PACK_APPLY_METRICS_DOCS_PIN} (PR #134). "
            f"Merge tip remains {RUNTIME_PACK_MERGE_PIN} (PR #128). "
            f"Gap-report tip remains {RUNTIME_PACK_GAP_REPORT_PIN} (PR #124). "
            f"Wall feature tip remains {RUNTIME_WALL_PIN}. "
            "Does not write the live pack. Not #70 Done. Not #78 Done."
        ),
    }


def pack_fill_plan(
    *,
    guest_root: str | Path | None = None,
    runtime_root: str | Path | None = None,
    runtime_tip: str | None = None,
    guest_tip: str | None = None,
    progress: Mapping[str, Any] | None = None,
    hooked: bool = False,
    environ: Mapping[str, str] | None = None,
    documented_runtime_tip: str | None = RUNTIME_PACK_TIP,
    documented_guest_tip: str | None = GUEST_PACK_TIP,
) -> dict[str, Any]:
    """Dry-run / live honesty plus the paste fragment. No invented walls."""
    env = _tip_env(environ)
    _runtime_sha, runtime_src = resolve_known_tip(
        checkout=runtime_root,
        env_value=runtime_tip if runtime_tip is not None else env.get(ENV_RUNTIME_TIP),
        documented=documented_runtime_tip,
    )
    _guest_sha, guest_src = resolve_known_tip(
        checkout=guest_root,
        env_value=guest_tip if guest_tip is not None else env.get(ENV_GUEST_TIP),
        documented=documented_guest_tip,
    )
    fragment = pack_fill_fragment(
        guest_root=guest_root,
        runtime_root=runtime_root,
        runtime_tip=runtime_tip,
        guest_tip=guest_tip,
        progress=progress,
        hooked=hooked,
        environ=env,
        documented_runtime_tip=documented_runtime_tip,
        documented_guest_tip=documented_guest_tip,
    )
    sources: dict[str, str] = {}
    if runtime_src:
        sources["panoramix_runtime_tip"] = runtime_src
    if guest_src:
        sources["guest_tip"] = guest_src
    return {
        "assist": "runtime #78 D fill checklist",
        "when": (
            "tips from checkout / env / documented tip; "
            "durable only from hooked measured progress"
        ),
        "runtime_tip": RUNTIME_PACK_TIP,
        "or": "main",
        "runtime_pr": 120,
        "docs_tip": RUNTIME_PACK_DOCS_PIN,
        "docs_pr": 122,
        "gap_report_tip": RUNTIME_PACK_GAP_REPORT_PIN,
        "gap_report_pr": 124,
        "gap_report_docs_tip": RUNTIME_PACK_GAP_REPORT_DOCS_PIN,
        "gap_report_docs_pr": 126,
        "merge_tip": RUNTIME_PACK_MERGE_PIN,
        "merge_pr": 128,
        "merge_docs_tip": RUNTIME_PACK_MERGE_DOCS_PIN,
        "merge_docs_pr": 130,
        "apply_metrics_tip": RUNTIME_PACK_APPLY_METRICS_PIN,
        "apply_metrics_pr": 132,
        "apply_metrics_docs_tip": RUNTIME_PACK_APPLY_METRICS_DOCS_PIN,
        "apply_metrics_docs_pr": 134,
        "apply_notes_tip": RUNTIME_PACK_APPLY_NOTES_PIN,
        "apply_notes_pr": 136,
        "schema_pr": 118,
        "wall_feature_tip": RUNTIME_WALL_PIN,
        "omit_when_missing": True,
        "invent": False,
        "invent_wall_time_sec": False,
        "invent_ux_strings": False,
        "forecast": False,
        "ifrs17": False,
        "iec_spa": False,
        "writes_live_pack": False,
        "assist_ne_fill": True,
        "apply_notes_ne_fill": True,
        "apply_notes_ne_done": True,
        "apply_metrics_ne_fill": True,
        "apply_metrics_ne_done": True,
        "merge_ne_fill": True,
        "merge_ne_done": True,
        "gap_report_ne_done": True,
        "ux_done": False,
        "north_star_done": False,
        "tip_sources": sources,
        "fragment": fragment,
        "skeleton_handoff": skeleton_handoff_plan(),
        "apply_notes": apply_notes_plan(runtime_root=runtime_root),
        "apply_metrics": apply_metrics_plan(runtime_root=runtime_root),
        "merge": merge_plan(runtime_root=runtime_root),
        "gap_report": gap_report_plan(runtime_root=runtime_root),
        "note": (
            "Small JSON fragment to paste into the off-box iec-parity pack "
            "under tips / optional durable, or feed to "
            "python3 -m runtime.iec_parity_pack skeleton via --from-json "
            "(file or stdin) or flags. Overlay with "
            "python3 -m runtime.iec_parity_pack merge … --from-json "
            "(pack_fill.merge hint: cd+cmd when PANORAMIX_RUNTIME_ROOT "
            "known, else a copy-paste template). Then apply-metrics "
            "(pack_fill.apply_metrics hint: cd+cmd when "
            "PANORAMIX_RUNTIME_ROOT known, else a copy-paste template; "
            "does not supply wall numbers), then apply-notes "
            "(pack_fill.apply_notes hint: cd+cmd when "
            "PANORAMIX_RUNTIME_ROOT known, else a copy-paste template; "
            "does not supply wall numbers; does not invent UX strings) "
            "and run "
            "python3 -m runtime.iec_parity_pack gap-report against that pack "
            "(pack_fill.gap_report hint). "
            "apply-notes+apply-metrics+merge+gap-report pairing. "
            "Hint only — does not run apply-notes, apply-metrics, merge, or "
            "gap-report. Assist for runtime #78 D fill checklist only. "
            "Does not write the full live pack. Does not stamp #70 UX Done "
            "/ north_star_done. "
            f"Runtime tip {RUNTIME_PACK_TIP} (#120 skeleton|validate, or main). "
            f"Docs tip {RUNTIME_PACK_DOCS_PIN} (PR #122 WSL assist-smoke "
            "stamp lineage). "
            f"Gap-report tip {RUNTIME_PACK_GAP_REPORT_PIN} (PR #124 "
            "gap-report ≠ Done). "
            f"Gap-report docs tip {RUNTIME_PACK_GAP_REPORT_DOCS_PIN} "
            "(PR #126, or main). "
            f"Merge tip {RUNTIME_PACK_MERGE_PIN} (PR #128, or main). "
            f"Merge docs tip {RUNTIME_PACK_MERGE_DOCS_PIN} "
            "(PR #130, or main). "
            f"Apply-metrics tip {RUNTIME_PACK_APPLY_METRICS_PIN} "
            "(PR #132, or main). "
            f"Apply-metrics docs tip {RUNTIME_PACK_APPLY_METRICS_DOCS_PIN} "
            "(PR #134, or main). "
            f"Apply-notes tip {RUNTIME_PACK_APPLY_NOTES_PIN} "
            "(PR #136, or main). "
            "Schema / checklist era remains #118. "
            f"Guest emit tip {GUEST_PACK_TIP} (PR #52). "
            f"Guest gap-report tip {GUEST_GAP_REPORT_TIP} (PR #60). "
            f"Guest merge tip {GUEST_MERGE_TIP} (PR #64). "
            f"Guest apply-metrics tip {GUEST_APPLY_METRICS_TIP} (PR #68). "
            f"Wall feature tip remains {RUNTIME_WALL_PIN}. "
            "Durable wall/stage elapsed only when measured from the hooked "
            "run. Omit when missing. Never invent. Never invent "
            "metrics.wall_time_sec. Never invent UX strings. "
            "assist ≠ fill; assist ≠ Done; "
            "apply-notes ≠ fill; apply-notes ≠ Done; "
            "apply-metrics ≠ fill; apply-metrics ≠ Done; "
            "merge ≠ fill; merge ≠ Done; gap-report ≠ Done. "
            "Not a forecast. Not IFRS17. Not iec SPA. Not #70 Done."
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
