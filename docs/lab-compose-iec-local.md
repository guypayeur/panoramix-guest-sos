# Lab compose: iec-local same-job admit + UI watch

Thin local lab so an operator can start **runtime.serve** (binding [`bindings/local-iec.example.yaml`](https://github.com/guypayeur/panoramix-runtime/blob/main/bindings/local-iec.example.yaml), ctl **19216**) and this guest with `PANORAMIX_CTL_HTTP`, POST the pinned iec **same-job**, and watch durable progress on `:18280` (phase/fraction **when the hook supplies them**).

This is the guest follow-up for runtime [#146](https://github.com/guypayeur/panoramix-runtime/issues/146) / [PR #148](https://github.com/guypayeur/panoramix-runtime/pull/148) (`docs/iec-local.md` @ `d480dc8`) so [#70](https://github.com/guypayeur/panoramix-runtime/issues/70) north-star compare can admit the **same** `reserve_ifrs17` job iec measures. Sibling reserve-temporal compose stays [`docs/lab-compose.md`](lab-compose.md) (ctl **19215**).

**Honesty:** guest does **not** run IFRS17 math. The runtime binding wraps the operator iec checkout (`POST /v1/jobs`). Fail-closed without env. Not guest→mesh ctl. Not a second control plane. Not SIEM. Pin **0.5**. Phase/fraction **omit when missing** — guest matches runtime [#149](https://github.com/guypayeur/panoramix-runtime/issues/149) / [PR #150](https://github.com/guypayeur/panoramix-runtime/pull/150) (`docs/iec-local.md`: omit Platform `unknown`/`0` defaults; map only when present). Walls (`api_e2e_ms` / `wall_elapsed_ms`) **omit when missing — never invent**. Recorded fixture **omits** measured walls. Does **not** invent SPA chunk/ETA/heartbeat chrome. Does **not** stamp `north_star_done`. Does **not** close runtime [#70](https://github.com/guypayeur/panoramix-runtime/issues/70) / [#78](https://github.com/guypayeur/panoramix-runtime/issues/78). Does **not** unlock cloud [#61](https://github.com/guypayeur/panoramix-runtime/issues/61) / [#29](https://github.com/guypayeur/panoramix-runtime/issues/29). This page does **not** grow pack_fill.

## Same-job identity

Guest POST (or UI catalog **reserve_ifrs17**):

```json
{"demo":"reserve","catalog":"reserve_ifrs17"}
```

Alias `same-job` → `reserve_ifrs17`. Digest must match runtime `reserve_iec.SAME_JOB_DIGEST` on **main** @ `d480dc8`:

`sha256:1a1e14a08f08b7fd310c335bf863b475c86919cf0e59e9326207b49e8ae2206c`

Pinned payload (canonical JSON, sort_keys, separators `(",", ":")`):

```json
{"mode":"STANDARD","revision":"4d5d44d3747b0700eba7b4af1987184f76cc56a8","source_file":"reserve_ifrs17/reserve_ifrs17.adsl","workload":"reserve_ifrs17"}
```

This is **not** the thinner recorded / live / parity kernel. `class: gpu` is refused. Thinner reserve ints (`accounts`, `horizon`, …) are refused. Without a durable hook the guest **fail-closes** (`durable_admit_failed` / `same_job_stub`) — no in-guest IFRS17 stub.

## What it starts

1. `python3 -m runtime.serve --binding bindings/local-iec.example.yaml` from a [panoramix-runtime](https://github.com/guypayeur/panoramix-runtime) checkout (**main** @ `d480dc8`, PR #148). Binding `publish.ctl_port` is **19216**.
2. This guest: `PLATFORM_LISTEN_HTTP=18280`, `PANORAMIX_CTL_HTTP=http://127.0.0.1:19216`, `PANORAMIX_CTL_KIND=iec-local` (port **19216** also selects iec-local when kind is unset).
3. `POST /v0/jobs` with `{"demo":"reserve","catalog":"reserve_ifrs17"}`.
4. Show `local.backed=runtime` and durable `GET /progress` (`source: durable`). `phase` / `fraction` only when the hook supplies them — **omit** Platform `unknown` / `0` defaults (runtime [#149](https://github.com/guypayeur/panoramix-runtime/issues/149) / [PR #150](https://github.com/guypayeur/panoramix-runtime/pull/150)). Richer hook fields surface when present (no invented SPA chunk/ETA/heartbeat chrome). Nested `iec_job_id` / `cw_id` pass through on job detail + progress when ctl `/iec-local/status|progress` supplies them — **omit when missing**. **Events are not required** (iec-local has no events verb). **pause_resume is not required** (iec pause is pause-before-start only). Mid-flight **pause / held / resume**, `pause_limit`, and FAILED **next_action / stage_name / valuation** pass through when ctl supplies them (runtime tip [`d9b9948`](https://github.com/guypayeur/panoramix-runtime/commit/d9b9948)+: `pause_limit` always; `already_canceled` on idempotent ctl cancel) — **omit when missing**. Walls only when the hook supplies them (`walls.api_e2e_ms` per runtime [#145](https://github.com/guypayeur/panoramix-runtime/issues/145)) — omit when missing.
5. Operator UI `:18280` polls mid-flight once admit returns a running id. Honesty labels: guest does not run IFRS17; runtime binding runs the iec checkout.
6. Tear down both processes.

Recorded fixture (`python3 -m runtime.apply iec-local` without `--live`) needs **no** iec checkout. Opt-in `--live` / `PANORAMIX_RESERVE_TEMPORAL_LIVE=1` passes `live=1` so ctl wraps operator `IEC_ROOT` + `IEC_API` (`http://127.0.0.1:8410`). Missing checkout is a named live miss on the runtime side, not a guest-invented wall.

CI uses `--dry-run` (plan JSON plus in-process smokes: hooked running + durable phase; inert **409** `same_job_stub`). No iec checkout is required for unit tests.

## Commands

```bash
# Plan + in-process hooked / inert smokes (no processes, no checkout):
python3 scripts/lab_compose_iec_local.py --dry-run

# Live one-shot recorded fixture (runtime checkout; no IEC_ROOT):
export PANORAMIX_RUNTIME_ROOT=/path/to/panoramix-runtime
python3 scripts/lab_compose_iec_local.py

# Opt-in live wrap of operator iec Platform API:
export IEC_ROOT=~/iec-proto-c
export IEC_API=http://127.0.0.1:8410
python3 scripts/lab_compose_iec_local.py --live
```

Equivalent manual steps (same honesty):

```bash
# terminal 1 — runtime (already serving):
cd /path/to/panoramix-runtime
python3 -m runtime.serve --binding bindings/local-iec.example.yaml

# terminal 2 — guest:
export PANORAMIX_CTL_HTTP=http://127.0.0.1:19216
export PANORAMIX_CTL_KIND=iec-local
export PLATFORM_LISTEN_HTTP=18280
python3 ./platform_run.py

# terminal 3 — same-job, then watch UI / progress:
JOB=$(curl -sS -X POST http://127.0.0.1:18280/v0/jobs \
  -H 'Content-Type: application/json' \
  -d '{"demo":"reserve","catalog":"reserve_ifrs17"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
curl -sS "http://127.0.0.1:18280/v0/jobs/${JOB}/progress"
# open http://127.0.0.1:18280/
```

Without `PANORAMIX_CTL_HTTP` the same-job POST is **409** `durable_admit_failed` (`same_job_stub`). That is fail-closed — **no stub IFRS17**.

When ctl is listening but admit is slow, guest fail-closes with **`ctl_admit_timeout`** — not **`ctl_http_unreachable`** / lab-serve-down. A later progress poll may still show durable running (nested iec job created). True serve-down (origin not listening) stays **`ctl_http_unreachable`**. Does not invent UX progress. `north_star_done` false.

Ctl verbs (runtime `docs/iec-local.md` @ `d480dc8`):

```text
POST /iec-local/admit
GET  /iec-local/status?id=
GET  /iec-local/progress?id=
POST /iec-local/cancel?id=
POST /iec-local/pause?id=     # pause-before-start only
POST /iec-local/resume?id=
POST /iec-local/await?id=
```

No events verb. CLI: `python3 -m runtime.apply iec-local admit|status|progress|cancel|pause|resume|await` (`--handoff`, `--catalog reserve_ifrs17|same-job`, optional `--live`).

## Not this page

- IFRS17 math in the guest
- Invented walls / invented `phase=unknown` / `fraction=0.0` / `comparable=true` / `north_star_done`
- SPA chunk / ETA / heartbeat chrome to chase the UX gate
- Closing runtime #70 / #78
- Cloud unlock (#61 / #29)
- Growing pack_fill / apply-notes / gap-report
- Claiming pause mid-flight (iec single-activity limit)
- A guest `iec:` scheme or pin bump (pin stays **0.5**)
