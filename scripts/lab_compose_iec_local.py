#!/usr/bin/env python3
"""One-shot lab compose: runtime.serve iec-local + guest CTL_HTTP + same-job.

Starts ``python3 -m runtime.serve --binding bindings/local-iec.example.yaml``
(ctl **19216**), starts this guest with ``PANORAMIX_CTL_HTTP`` +
``PANORAMIX_CTL_KIND=iec-local`` + ``PLATFORM_LISTEN_HTTP``, POSTs
``{"demo":"reserve","catalog":"reserve_ifrs17"}``, and shows
``local.backed=runtime`` plus durable phase/fraction progress.

Recorded fixture needs no iec checkout. Opt-in ``--live`` passes
``live=1`` so ctl wraps the operator iec Platform API
(``POST /v1/jobs``). Evidence does **not** require events or
pause_resume. Guest does **not** run IFRS17 math.

Requires ``PANORAMIX_RUNTIME_ROOT`` for the live path. ``--dry-run``
prints the plan plus in-process hooked-running / inert
``same_job_stub`` smokes (CI / no checkout).

Honesty: not guest→mesh ctl. Not SIEM. Guest does not run IFRS17.
Pin 0.5. Walls omit when missing — never invent. Does not close
runtime #70 / #78. Does not unlock #61 / #29. north_star_done false.
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
    DEFAULT_GUEST_PORT,
    guest_paths,
    job_paths,
    port_from_origin,
    runtime_root_usable,
    wait_loopback_port,
)
from sos.lab_compose_iec import (  # noqa: E402
    DEFAULT_IEC_CTL_PORT,
    build_iec_compose_plan,
    classify_iec_evidence,
    dry_run_iec_smokes,
    iec_smokes_honest,
    plan_json,
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
        description="One-shot lab compose for iec-local same-job + guest CTL_HTTP"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print the plan JSON plus in-process hooked-running / "
            "inert same_job_stub smokes (no processes, no iec checkout)"
        ),
    )
    parser.add_argument(
        "--runtime-root",
        default=os.environ.get(ENV_RUNTIME_ROOT, ""),
        help="panoramix-runtime checkout (or PANORAMIX_RUNTIME_ROOT)",
    )
    parser.add_argument("--ctl-port", type=int, default=DEFAULT_IEC_CTL_PORT)
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
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Opt-in: pass live=1 so iec-local wraps the operator iec "
            "Platform API (needs IEC_ROOT + IEC_API). Recorded fixture "
            "is the default and needs no checkout."
        ),
    )
    return parser.parse_args(argv)


def dry_run(args: argparse.Namespace) -> int:
    plan = build_iec_compose_plan(
        guest_root=GUEST_ROOT,
        runtime_root=args.runtime_root or None,
        ctl_port=args.ctl_port,
        guest_port=args.guest_port,
        binding=args.binding or None,
        bearer=args.bearer or None,
        live=args.live,
    )
    blob = json.loads(plan_json(plan))
    smokes = dry_run_iec_smokes()
    blob["iec_smoke"] = smokes
    sys.stdout.write(json.dumps(blob, indent=2, sort_keys=True) + "\n")
    if not iec_smokes_honest(smokes):
        sys.stderr.write(
            "fail closed: dry-run did not show hooked running + durable "
            "progress plus inert same_job_stub (no stub IFRS17).\n"
        )
        return 1
    return 0


def live(args: argparse.Namespace) -> int:
    usable = runtime_root_usable(args.runtime_root or None)
    if usable is None:
        sys.stderr.write(
            "fail closed: set PANORAMIX_RUNTIME_ROOT to a panoramix-runtime "
            "checkout that contains runtime/apply.py (or pass --runtime-root). "
            "Use --dry-run for the plan without an iec checkout.\n"
        )
        return 2
    plan = build_iec_compose_plan(
        guest_root=GUEST_ROOT,
        runtime_root=usable,
        ctl_port=args.ctl_port,
        guest_port=args.guest_port,
        binding=args.binding or None,
        bearer=args.bearer or None,
        live=args.live,
    )
    ctl_port = port_from_origin(plan.ctl_http)
    guest_port = int(plan.guest_listen)
    serve_proc = None
    guest_proc = None
    serve_log = None
    guest_log = None
    tmp = Path(tempfile.mkdtemp(prefix="sos-lab-compose-iec-"))
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
            f"PANORAMIX_CTL_KIND=iec-local "
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
                    "ui": paths.get("ui"),
                    "note": (
                        "HTTP adapter hooked when durable_hook.kind=ctl_http. "
                        "Guest does not run IFRS17 math. Watch :18280."
                    ),
                },
                indent=2,
            ),
            flush=True,
        )
        create_code, job = _http("POST", paths["jobs"], plan.reserve_body)
        if create_code not in {200, 201} or not job.get("id"):
            sys.stderr.write(
                f"POST reserve catalog=reserve_ifrs17 failed: {create_code} {job}\n"
            )
            return 1
        job_id = str(job["id"])
        jp = job_paths(plan, job_id)
        deadline = time.monotonic() + float(args.wait_seconds)
        evidence = classify_iec_evidence(job)
        progress: dict = {}
        while time.monotonic() < deadline:
            _code, job = _http("GET", jp["job"])
            _pcode, progress = _http("GET", jp["progress"])
            evidence = classify_iec_evidence(job, progress)
            if evidence["ok"]:
                break
            if job.get("error") == "durable_admit_failed":
                break
            time.sleep(0.2)
        if job.get("status") in {"queued", "running", "paused"}:
            _http("POST", jp["cancel"])
            _code, job = _http("GET", jp["job"])
            _pcode, latest = _http("GET", jp["progress"])
            if isinstance(latest, dict) and latest:
                progress = latest
            evidence = classify_iec_evidence(job, progress)
        report = {
            "id": job_id,
            "status": job.get("status"),
            "evidence": evidence,
            "job_local": job.get("local"),
            "progress": {
                "source": progress.get("source"),
                "phase": progress.get("phase"),
                "fraction": progress.get("fraction"),
                "pct": progress.get("pct"),
                "same_job": progress.get("same_job"),
                "ifrs17_guest": progress.get("ifrs17_guest"),
                "walls": progress.get("walls"),
            },
            "ui": paths.get("ui"),
            "north_star_done": False,
            "closes_runtime_70": False,
            "closes_runtime_78": False,
            "honesty": list(plan.honesty),
        }
        print(json.dumps(report, indent=2), flush=True)
        if not evidence["ok"]:
            sys.stderr.write(
                "compose did not observe local.backed=runtime with durable "
                "iec-local progress (no pretend; guest does not run IFRS17).\n"
            )
            return 1
        print(
            "OK lab compose iec-local: local.backed=runtime, durable "
            "phase/fraction. Guest does not run IFRS17 math. "
            "north_star_done false.",
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
