#!/usr/bin/env python3
"""One-shot lab compose: runtime.serve + guest CTL_HTTP + recorded reserve.

Starts ``python3 -m runtime.serve --binding bindings/local-reserve-temporal.example.yaml``
(ctl **19215**), starts this guest with ``PANORAMIX_CTL_HTTP`` +
``PLATFORM_LISTEN_HTTP``, POSTs ``{"demo":"reserve","catalog":"recorded"}``,
prints ``local.backed=runtime`` / durable progress+events / ``pause_resume``,
then cancel/fail → one-click ``POST /v0/jobs/{id}/re-admit`` → new job id
when the durable hook is active. Fail-closed without hook or payload
(no silent stub). Not resume-from-failed.

Requires ``PANORAMIX_RUNTIME_ROOT`` for the live path. ``--dry-run`` prints
the plan plus in-process re-admit smokes (CI / no Temporal). Fail closed
without a usable runtime checkout on the live path.

Honesty: not guest→mesh ctl. Not SIEM. Not IFRS17. Pin 0.5.
Optional durable stage elapsed from runtime tip 9ba95bbb / docs tip
5dc191cb (or main); omit when missing — never invent. Optional
durable wall_elapsed_ms / started_at from runtime tip 9b6646e8
(PR #114, or main; docs tip 6511cec7 / PR #116 lineage); omit
when missing — never invent. Compare prefers that wall when
present. Dry-run / live emit a small paste fragment for runtime
#78 D pack fill (tips when known; optional durable only when
measured from the hooked run). Runtime tip b81130f (#120
runtime.iec_parity_pack skeleton|validate, or main); docs tip
63a168d (PR #122 WSL assist-smoke stamp lineage); gap-report
tip 84cb202 (PR #124 gap-report); guest emit
tip b859466 (#52). Wall feature tip remains 9b6646e8. Guest
fragment can feed optional tips / measured durable into
python3 -m runtime.iec_parity_pack skeleton via --from-json
(file or stdin) or flags; omit durable when missing. Never
invent metrics.wall_time_sec. assist ≠ fill; assist ≠ Done.
Does not write the full live pack. Not a forecast. Not IFRS17.
Not iec SPA. Handoff docs panel is operator clarity, not a
second control plane. Does not close runtime
#70 / #78. Does not unlock #61 / #29. north_star_done false.
Cloud stays locked.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

GUEST_ROOT = Path(__file__).resolve().parents[1]
if str(GUEST_ROOT) not in sys.path:
    sys.path.insert(0, str(GUEST_ROOT))

from sos.lab_compose import (  # noqa: E402
    DEFAULT_CTL_PORT,
    DEFAULT_GUEST_PORT,
    LIVE_JOB_STATUSES,
    build_compose_plan,
    classify_lab_evidence,
    classify_readmit_evidence,
    dry_run_readmit_smokes,
    guest_paths,
    job_paths,
    pack_fill_plan,
    plan_json,
    port_from_origin,
    readmit_smokes_honest,
    runtime_root_usable,
    wait_loopback_port,
)
from sos.lab_ctl import ENV_RUNTIME_ROOT  # noqa: E402


def _http(
    method: str, url: str, body: dict | None = None, timeout: float = 8.0
) -> tuple[int, dict]:
    raw = None
    headers = {"Accept": "application/json"}
    if body is not None:
        raw = (json.dumps(body, separators=(",", ":")) + "\n").encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=raw, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = (resp.read() or b"").decode("utf-8")
            return int(resp.status), json.loads(text) if text.strip() else {}
    except urllib.error.HTTPError as exc:
        text = (exc.read() or b"").decode("utf-8", errors="replace")
        try:
            payload = json.loads(text) if text.strip() else {}
        except json.JSONDecodeError:
            payload = {"error": text}
        return int(exc.code), payload


def _spawn(argv: list[str], *, cwd: Path, env: dict[str, str], log_path: Path):
    log = log_path.open("w", encoding="utf-8")
    merged = dict(os.environ)
    merged.update(env)
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd),
        env=merged,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return proc, log


def _stop(proc: subprocess.Popen | None, log) -> None:
    if log is not None:
        try:
            log.close()
        except OSError:
            pass
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=6)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        proc.wait(timeout=3)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-shot lab compose for reserve-temporal + guest CTL_HTTP"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print the plan JSON plus in-process re-admit smokes "
            "(no processes, no Temporal)"
        ),
    )
    parser.add_argument(
        "--runtime-root",
        default=os.environ.get(ENV_RUNTIME_ROOT, ""),
        help="panoramix-runtime checkout (or PANORAMIX_RUNTIME_ROOT)",
    )
    parser.add_argument("--ctl-port", type=int, default=DEFAULT_CTL_PORT)
    parser.add_argument("--guest-port", type=int, default=DEFAULT_GUEST_PORT)
    parser.add_argument("--binding", default="")
    parser.add_argument(
        "--bearer",
        default=os.environ.get("PANORAMIX_CTL_HTTP_BEARER", ""),
        help="Optional loopback bearer when ctl.require is on",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=20.0,
        help="How long to wait for ports / job evidence",
    )
    return parser.parse_args(argv)


def dry_run(args: argparse.Namespace) -> int:
    plan = build_compose_plan(
        guest_root=GUEST_ROOT,
        runtime_root=args.runtime_root or None,
        ctl_port=args.ctl_port,
        guest_port=args.guest_port,
        binding=args.binding or None,
        bearer=args.bearer or None,
    )
    blob = json.loads(plan_json(plan))
    smokes = dry_run_readmit_smokes()
    blob["readmit_smoke"] = smokes
    sys.stdout.write(json.dumps(blob, indent=2, sort_keys=True) + "\n")
    if not readmit_smokes_honest(smokes):
        sys.stderr.write(
            "fail closed: dry-run re-admit smoke did not show hooked new job id "
            "plus inert/payload fail-closed (no silent stub; not resume-from-failed).\n"
        )
        return 1
    return 0


def live(args: argparse.Namespace) -> int:
    usable = runtime_root_usable(args.runtime_root or None)
    if usable is None:
        sys.stderr.write(
            "fail closed: set PANORAMIX_RUNTIME_ROOT to a panoramix-runtime "
            "checkout that contains runtime/apply.py (or pass --runtime-root). "
            "Use --dry-run for the plan without Temporal.\n"
        )
        return 2
    plan = build_compose_plan(
        guest_root=GUEST_ROOT,
        runtime_root=usable,
        ctl_port=args.ctl_port,
        guest_port=args.guest_port,
        binding=args.binding or None,
        bearer=args.bearer or None,
    )
    ctl_port = port_from_origin(plan.ctl_http)
    guest_port = int(plan.guest_listen)
    serve_proc = None
    guest_proc = None
    serve_log = None
    guest_log = None
    tmp = Path(tempfile.mkdtemp(prefix="sos-lab-compose-"))
    try:
        serve_log_path = tmp / "runtime-serve.log"
        guest_log_path = tmp / "guest.log"
        print(
            f"starting runtime.serve {list(plan.serve_argv)} cwd={usable}",
            flush=True,
        )
        serve_proc, serve_log = _spawn(
            list(plan.serve_argv),
            cwd=usable,
            env={"PYTHONPATH": str(usable)},
            log_path=serve_log_path,
        )
        if not wait_loopback_port(ctl_port, timeout_s=args.wait_seconds):
            sys.stderr.write(
                f"runtime.serve did not listen on 127.0.0.1:{ctl_port}; "
                f"see {serve_log_path}\n"
            )
            return 1
        print(
            f"starting guest {list(plan.guest_argv)} "
            f"PANORAMIX_CTL_HTTP={plan.ctl_http} "
            f"PLATFORM_LISTEN_HTTP={plan.guest_listen}",
            flush=True,
        )
        guest_proc, guest_log = _spawn(
            list(plan.guest_argv),
            cwd=Path(plan.guest_cwd),
            env=plan.guest_env,
            log_path=guest_log_path,
        )
        if not wait_loopback_port(guest_port, timeout_s=args.wait_seconds):
            sys.stderr.write(
                f"guest did not listen on 127.0.0.1:{guest_port}; "
                f"see {guest_log_path}\n"
            )
            return 1
        paths = guest_paths(plan)
        health_code, health = _http("GET", paths["health"])
        if health_code != 200:
            sys.stderr.write(f"guest /health failed: {health_code} {health}\n")
            return 1
        info_code, info = _http("GET", paths["info"])
        hook = ((info.get("jobs") or {}).get("durable_hook") or {}) if info_code == 200 else {}
        print(
            json.dumps(
                {
                    "health": health,
                    "durable_hook": hook,
                    "note": "HTTP adapter hooked only when durable_hook.kind=ctl_http",
                },
                indent=2,
            ),
            flush=True,
        )
        create_code, job = _http("POST", paths["jobs"], plan.reserve_body)
        if create_code not in {200, 201} or not job.get("id"):
            sys.stderr.write(f"POST recorded reserve failed: {create_code} {job}\n")
            return 1
        job_id = str(job["id"])
        jp = job_paths(plan, job_id)
        deadline = time.monotonic() + float(args.wait_seconds)
        evidence = classify_lab_evidence(job)
        progress: dict = {}
        events: dict = {}
        while time.monotonic() < deadline:
            _code, job = _http("GET", jp["job"])
            _pcode, progress = _http("GET", jp["progress"])
            _ecode, events = _http("GET", jp["events"])
            evidence = classify_lab_evidence(job, progress, events)
            if evidence["ok"]:
                break
            if job.get("local", {}).get("backed") == "stub":
                break
            time.sleep(0.2)
        if evidence["backed"] == "runtime" and job.get("status") == "running":
            pause_code, paused = _http("POST", jp["pause"])
            if pause_code == 200:
                job = paused
                evidence = classify_lab_evidence(job, progress, events)
                if job.get("status") == "paused":
                    _http("POST", jp["resume"])
                    _code, job = _http("GET", jp["job"])
                    evidence = classify_lab_evidence(job, progress, events)
        readmit_job: dict = {}
        if job.get("status") in LIVE_JOB_STATUSES:
            cancel_code, canceled = _http("POST", jp["cancel"])
            if cancel_code == 200:
                job = canceled
        if job.get("status") in {"failed", "canceled"}:
            readmit_code, fresh = _http("POST", jp["readmit"])
            readmit_ok = readmit_code in {200, 201}
            readmit_job = fresh if readmit_ok else {}
            readmit_evidence = classify_readmit_evidence(
                job,
                fresh if readmit_ok else None,
                http_status=readmit_code,
                error=None if readmit_ok else fresh,
            )
        else:
            readmit_evidence = classify_readmit_evidence(
                job,
                None,
                http_status=409,
                error={
                    "error": "illegal_transition",
                    "reason": "not_failed_or_canceled",
                    "detail": (
                        "re-admit needs failed/canceled; job already terminal "
                        "without cancel/fail (not resume-from-failed)"
                    ),
                },
            )
        _pcode, latest_progress = _http("GET", jp["progress"])
        if isinstance(latest_progress, dict) and latest_progress:
            progress = latest_progress
        hooked = bool(
            progress.get("source") == "durable"
            and (
                hook.get("durable_path") is True
                or hook.get("kind") == "ctl_http"
            )
        )
        fill = pack_fill_plan(
            guest_root=plan.guest_cwd,
            runtime_root=plan.runtime_root,
            progress=progress,
            hooked=hooked,
        )
        report = {
            "id": job_id,
            "status": job.get("status"),
            "evidence": evidence,
            "job_local": job.get("local"),
            "pause_resume": job.get("pause_resume"),
            "progress": {
                "source": progress.get("source"),
                "stage": progress.get("stage"),
                "stages_completed": progress.get("stages_completed"),
                "stages_total": progress.get("stages_total"),
                "fraction": progress.get("fraction"),
            },
            "events": {
                "source": events.get("source"),
                "events_durable": events.get("events_durable"),
                "events_n": events.get("events_n"),
            },
            "readmit": {
                "source_id": job_id,
                "source_status": job.get("status"),
                "new_id": readmit_job.get("id"),
                "re_admit_from": (readmit_job.get("local") or {}).get("re_admit_from"),
                "evidence": readmit_evidence,
            },
            "pack_fill": fill,
            "north_star_done": False,
            "honesty": list(plan.honesty),
        }
        print(json.dumps(report, indent=2), flush=True)
        if not evidence["ok"]:
            sys.stderr.write(
                "compose did not observe local.backed=runtime with durable "
                "progress/events and pause_resume (no pretend).\n"
            )
            return 1
        if not readmit_evidence["ok"]:
            sys.stderr.write(
                "compose did not observe admit → cancel/fail → re-admit → "
                "new job id (no silent stub; not resume-from-failed).\n"
            )
            return 1
        print(
            "OK lab compose: local.backed=runtime, durable progress/events, "
            "pause_resume, re-admit new job id",
            flush=True,
        )
        return 0
    finally:
        _stop(guest_proc, guest_log)
        _stop(serve_proc, serve_log)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.dry_run:
        return dry_run(args)
    return live(args)


if __name__ == "__main__":
    sys.exit(main())
