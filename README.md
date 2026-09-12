# panoramix-guest-sos

Day-one **SoS** (actuarial) guest for [Panoramix](https://github.com/guypayeur/panoramix).

Pin **0.5**. This repository is opaque domain code plus a platform Unit contract. Compute engines live in [panoramix-runtime](https://github.com/guypayeur/panoramix-runtime) bindings — see [runtime#70](https://github.com/guypayeur/panoramix-runtime/issues/70) Slice B. The opaque handoff shape is defined by [`runtime/compute_work.py`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/compute_work.py) on runtime **main**. This guest does **not** close #70 and does **not** unlock cloud #61 / #29.

## What this is

- A greenfield Panoramix **0.5** guest: Unit `sos`, public HTTP on **18280**, probes at `/health`.
- A **day-one operator path**: submit work, watch status, cancel. Pause/resume is **durable-path only** (injected hook or operator/ctl `reserve-temporal pause|resume`) — stub-only jobs refuse it. Guest-facing handoff is opaque `kind` / `class` / `payload_digest` ([`runtime/compute_work.py`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/compute_work.py)). In-process stub runner is the **fallback** (the default). Engines stay in runtime bindings. Local demos: `echo`, `sleep`, and **`reserve`** (shaped UX seed — not IFRS17 math, not a perf baseline until runtime #83 + remeasure). Guest **emits WorkHandoff JSON only**; operator/ctl admits it via the binding. No guest→ctl HTTP for compute-work.
- Stdlib Python 3.12 (`platform_run.py` + `sos/`). Thin entrypoint imports domain the same way [httpbin](https://github.com/guypayeur/panoramix-guest-httpbin) `platform_run.py` imports `httpbin.core.app`.
- A minimal operator UI at `GET /` (also `GET /ui`) that lists jobs (status filter + optional light auto-refresh) against the JSON API.

## What this is not

- **Not** a lift of [iec-proto-c](https://github.com/guypayeur/iec-proto-c). This tree does not vend iec code, L1–L2 layers, ADSL/compiler, or claim feature/UX/perf equivalence.
- **Not** a place for `image:`, `ray:`, `temporal:`, or `aws:` fields on Unit/System YAML. Pin stays **0.5**.
- **Not** engine management. Ray / Temporal / GPU / AWS stay in runtime bindings ([runtime#70](https://github.com/guypayeur/panoramix-runtime/issues/70)).
- **Not** cloud-first. Local lab before AWS. Do not invent `PLATFORM_RAY_*`, engine URLs, guest-callable ctl HTTP, or env that adds mesh destinations.

## North star (documented only)

Day-one **is thinner** than iec-proto-c. The Done-when north star — owned with the runtime compute plane — is:

- **UX:** a representative SoS operator/actuary path that **matches or beats** the corresponding iec-proto-c experience.
- **Performance:** an agreed local workload class on the **same** host **matches or beats** that iec baseline.

Those boxes live on [panoramix-runtime#70](https://github.com/guypayeur/panoramix-runtime/issues/70). Slice B alignment here is the opaque seam only — **not** #70 Done.

The named iec comparison path (runtime [method.yaml](https://github.com/guypayeur/panoramix-runtime/blob/main/proofs/fixtures/iec-parity/method.yaml) after [#82](https://github.com/guypayeur/panoramix-runtime/pull/82)) is **`grammar/examples/reserve_ifrs17`**, with UX journey [`docs/ux/journeys/run_lifecycle_monitoring.md`](https://github.com/guypayeur/iec-proto-c/blob/main/docs/ux/journeys/run_lifecycle_monitoring.md). This guest’s `demo: "reserve"` is a **thinner stub / UX seed** so operators can walk submit → status pills → cancel beside that named baseline. Payload bytes **mirror** panoramix-runtime **main** helpers [`runtime.reserve.recorded_params`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/reserve.py) / `live_params` / `parity_params` / `digest_for` ([`docs/reserve.md`](https://github.com/guypayeur/panoramix-runtime/blob/main/docs/reserve.md)). Guest copies the catalogs; it does **not** import runtime. Recorded digest is `sha256:77e9299f4b8ea4aeed46f71b91cc947d56e9bd169d795e70845123fef53d7e4e`. Parity digest is `sha256:e180d2c2e3589b8762f92efa1bedb3d53ffeeb16648581ba13d537bcd3311102`. This path does **not** claim UX/perf parity, is **not** a perf baseline until #83 + remeasure, and does **not** close #70.

## Contract

`.platform/contract.yaml` is a v0.5 Unit. Port **18280** avoids colliding with httpbin **18080** and shop **18180**.

Listen env (same idea as [panoramix-guest-httpbin](https://github.com/guypayeur/panoramix-guest-httpbin) `platform_run.py`):

- `PLATFORM_LISTEN_HTTP` or `PLATFORM_LISTEN_http`
- accepted shapes: `port`, `:port`, `host:port`
- port-only binds loopback (`127.0.0.1`) for emulate

`run.entrypoint` is only `platform_run.py`. Emulate digest is entrypoint paths only — editing `sos/*.py` alone must **not** be assumed to change it. Do not teach `apply` to walk imports.

## Local run

Python **3.12** stdlib only. No `requirements.txt`.

```bash
python3 ./platform_run.py
# or:
PLATFORM_LISTEN_HTTP=18280 python3 ./platform_run.py
```

Health and product info:

```bash
curl -sS http://127.0.0.1:18280/health
curl -sS http://127.0.0.1:18280/v0/info
```

Operator UI: open http://127.0.0.1:18280/ (or `/ui`).

### Jobs API (Slice B handoff)

`POST /v0/jobs` accepts either:

1. **Opaque seam** (must match [`runtime/compute_work.py`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/compute_work.py) on panoramix-runtime main, #70 Slice B):
   - `kind`: `job` | `stage` | `chunk`
   - `class`: `cpu` | `gpu`
   - `payload_digest`: `sha256:` + 64 lowercase hex
2. **Local demo shortcut** (operator UX only): `{"demo":"echo","message":"..."}`, `{"demo":"sleep","seconds":8}`, or `{"demo":"reserve", ...}`. The server synthesizes `{kind:"job", class:"cpu"|"gpu", payload_digest}` from canonical JSON of the stored payload bytes (`json.dumps(..., sort_keys=True, separators=(",", ":"))` then sha256). For **reserve**, those bytes **must match** `runtime.reserve.digest_for` of `recorded_params()` / `live_params()` / `parity_params()` on panoramix-runtime **main** ([`docs/reserve.md`](https://github.com/guypayeur/panoramix-runtime/blob/main/docs/reserve.md) / [`runtime/reserve.py`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/reserve.py)):

```json
{"accounts":48,"discount_bps":300,"horizon":12,"lapse_bps":80,"paths":96,"seed":17070,"workload":"reserve"}
```

Default catalog is **recorded** (CI). Recorded digest is `sha256:77e9299f4b8ea4aeed46f71b91cc947d56e9bd169d795e70845123fef53d7e4e` (`runtime.reserve.digest_for(recorded_params())` on main). `{"demo":"reserve","catalog":"live"}` uses the heavier live catalog. `{"demo":"reserve","catalog":"parity"}` (alias `parity-scale`) uses the third catalog (`runtime.reserve.parity_params()` / `digest_for` on main); digest is `sha256:e180d2c2e3589b8762f92efa1bedb3d53ffeeb16648581ba13d537bcd3311102`. Catalogs: recorded / live / parity (parity-scale). Separate iec-local same-job catalog `reserve_ifrs17` (alias `same-job`; digest `sha256:1a1e14a08f08b7fd310c335bf863b475c86919cf0e59e9326207b49e8ae2206c`) is **not** in that thinner list — guest does **not** run IFRS17 math ([docs/lab-compose-iec-local.md](docs/lab-compose-iec-local.md)). Explicit ints (`accounts`, `horizon`, `paths`, `seed`, `lapse_bps`, `discount_bps`) override catalog fields. Optional `label` / `stages` / `seconds` are **local stub UX only** and are not in the digest. `class: "gpu"` is a **UX / opaque label only** on the stub. The seam `kind` is always `job`. Guest **emits WorkHandoff JSON only** — it never calls `runtime.apply compute-work`. **Reserve is a stub / UX seed only** — not IFRS17 math, not a perf baseline until #83 + remeasure; named iec baseline remains `reserve_ifrs17`. Not #70 Done.

Resources expose at least `id`, `kind`, `class`, `payload_digest`, `status`. Status is `queued` → `running` ⇄ `paused` → `succeeded` | `failed` | `canceled` (one L). `paused` is **non-terminal**. `GET /v0/jobs?status=` filters by those real statuses (repeat or comma-separate to OR; unknown values such as `accepted` / `cancelled` return **400** `invalid_status`). Operator UI filter uses the same list. Light auto-refresh is **opt-in**, or on when `GET /v0/info` `jobs.durable_hook.durable_path` is true; it polls list + selected job detail and **stops on terminal**. It does **not** invent progress. Guest-local stub metadata may appear under `local` (not a runtime handoff field). `local.backed` is `stub` (in-process fallback) or `runtime` (only if an operator-injected hook admits the job). Selected-job UI shows id, status pill, kind/class/digest, created/updated/elapsed, `message` / `local.stage`, and `local.backed`. Failed/canceled jobs add a **terminal** summary (`status` + `message` + optional last events / stage) — **not** a SIEM, **not** iec `/v1/audit/events`. Recoverability (thinner): `handoff` + `payload` export for operator/ctl re-admit (`python3 -m runtime.apply reserve-temporal admit --handoff JSON`). When a durable hook is active (`PANORAMIX_CTL_HTTP` preferred or `PANORAMIX_RUNTIME_ROOT`), `POST /v0/jobs/{id}/re-admit` posts that handoff/payload through the same hook seam as a **new** admit (new job id). Fail-closed without hook or when payload is missing (no silent stub). Cancel/fail does **not** auto-retry; no resume-from-failed. Pause/resume remains durable-only. Historical comparison (thinner): `GET /v0/jobs/{id}/compare` against recent same-catalog (or same kind/class) jobs in guest history (in-process plus local lab files when persisted) — elapsed for this run + priors; typical/ETA only from succeeded prior walls when two or more samples exist. Honest when history is empty or a single prior (no invented numbers). **not a forecast**, **not** IFRS17, **not** iec SPA historical widget. Investigate (thinner): catalog name + short digest called out for cross-check when already on the job (**not** a data-catalog product); static day-one path-slice ownership tags (`admit` / `project` / `fold` / `complete`) when durable-hooked (**not** Slack); event trail stays on the same panel (**not** a SIEM). Durable-path responses set `pause_resume: true` when honest; stub jobs stay `false`. Job and progress resources may include an `investigate` object with those fields. Failed/canceled job resources may include `terminal` and `recoverability`. Selected-job UI also shows compact **Handoff docs** (export + re-admit + lab-compose reminders — not a second control plane). Durable path-slice timeline may show per-stage elapsed only when progress/events provide real timestamps. Optional durable `wall_elapsed_ms` / `started_at` appears on job detail / progress only when the hook progress/status JSON includes it (runtime tip `9b6646e8` / main, PR #114) — omitted when missing; never invented; **not** a forecast; **not** IFRS17; **not** iec SPA.

Ctl export (no engine fields; nested `payload` is omitted because runtime `parse_work` rejects that key on submit):

- `GET /v0/jobs` — newest first. Optional `?status=queued|running|paused|succeeded|failed|canceled` (repeat or comma-separate). Unknown statuses are **400** `invalid_status`.
- `GET /v0/jobs/{id}/handoff` — exactly `id` / `kind` / `class` / `payload_digest` / `status` (WorkHandoff projection).
- `GET /v0/jobs/{id}/payload` — canonical JSON bytes as `utf8` + `hex` plus `payload_digest`. Demo shortcuts store bytes; opaque digest-only submit returns **404** `payload_unknown`.
- `GET /v0/jobs/{id}/progress` — prefers durable reserve-temporal path-slice counters (`stage`, `stages_total`, `stages_completed`, `fraction`, nested `progress`) when a runtime hook provides them (`source: "durable"`). Named timeline may include optional per-stage `elapsed_ms` when durable progress exposes it (runtime tip `9ba95bbb` / docs tip `5dc191cb` / main) or durable `GET /v0/jobs/{id}/events` timestamps can be subtracted honestly — **omitted when missing; never invented**. Optional `wall_elapsed_ms` / `started_at` when durable progress/status supplies it (runtime tip `9b6646e8` / main, PR #114) — **omitted when missing; never invented**; **not** a forecast; **not** IFRS17; **not** iec SPA. iec-local same-job (`reserve_ifrs17`) prefers hook `phase` / `fraction` when present and **omits** Platform `unknown` / `0` defaults (runtime #149 / #150) — **never invent**; richer hook fields surface when present (no invented SPA chunk/ETA/heartbeat chrome). Nested `iec_job_id` / `cw_id` pass through on job detail + progress when the hook/ctl supplies them — **omit when missing**. Otherwise stub fallback (`source: "stub"`) from local stage fields (`stage_index` / “stage i of n”). **Not** iec planner parallelism or iec chunk progress. Operator/ctl: `python3 -m runtime.apply reserve-temporal progress --id cw_…`.
- `GET /v0/jobs/{id}/events` — prefers durable reserve-temporal JSONL when a runtime hook provides it (`source: "durable"`, `events_durable: true` / `events_n` when present). Otherwise process-memory fallback (`source: "memory"`). Filter by kind (`?kind=admit,StageCompleted,pause,resume,cancel,succeed,fail` — aliases cover canceled / succeeded / stage_completed). Export/download JSON (default) or JSONL (`?format=jsonl`) for local salvage. Empty trail and empty filter match stay empty. Day-one local durable trail — **not** a SIEM, **not** iec `/v1/audit/events`, **not** a regulatory audit product, **not** regulatory defensibility. Operator/ctl: `python3 -m runtime.apply reserve-temporal events --id cw_…`. Also on the job resource when the hook overlay is present.
- `GET /v0/jobs/{id}/compare` — thinner vs recent same-catalog (or same kind/class) jobs in guest history (in-process plus local lab files when persisted). Elapsed prefers durable `wall_elapsed_ms` when the hook or a persisted job field includes it (runtime tip `9b6646e8` / main, PR #114); else created/updated timestamps. Typical/ETA only from succeeded prior walls when two or more samples exist. **Omit when missing; never invent.** **not a forecast**, **not** IFRS17, **not** iec SPA historical widget. No guest→ctl HTTP. Persistence: default `.sos/jobs`; override or disable with `PANORAMIX_SOS_JOBS_DIR` (`off` / empty **fails closed** — in-process only).
- Failed/canceled `GET /v0/jobs/{id}` — `terminal` (status + message + optional last events / stage; **not** a SIEM) and `recoverability` (handoff + payload for operator/ctl re-admit; one-click `POST /v0/jobs/{id}/re-admit` when a durable hook is active; cancel/fail does **not** auto-retry).
- `POST /v0/jobs/{id}/re-admit` — new admit of the existing handoff + payload through the durable hook. Failed/canceled only. **409** `re_admit_unavailable` without hook or when payload is missing (no silent stub). Not resume-from-failed. Not SIEM. Not IFRS17.
- `POST /v0/jobs/{id}/pause` / `POST /v0/jobs/{id}/resume` — durable path only. Stub-only (`local.backed == "stub"` or no runtime ref) returns **409** `stub_only`. Illegal transitions (pause when not `running`, resume when not `paused`, terminal) return **409**. Cancel is not pause.

Operator UI Pause/Resume controls are **disabled** for stub jobs (with an explanation pointing at ctl). Durable-backed jobs can pause (`paused`) and resume (`running`). Job list status filter and light auto-refresh (opt-in or when `durable_hook` is active; **stops on terminal**; no invented progress) are thinner SPA polish — not a SPA framework. Cancel confirm dialog: cancel ends the run (`canceled`) from running or paused; pause exists on the durable/ctl path only. See [docs/ux-side-by-side.md](docs/ux-side-by-side.md). This does **not** close #70.

Engine brand keys/schemes on the body (`engine`, `engine_kind`, `payload`, `url` / `uri` / `endpoint` / `address`, `ray:` / `temporal:` / `s3:` / `image:` / …) return **400** `engine_smuggle`.

Opaque submit:

```bash
DIGEST=$(python3 -c 'import hashlib,json; p={"demo":"echo","message":"hello"}; print("sha256:"+hashlib.sha256(json.dumps(p,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest())')
curl -sS -X POST http://127.0.0.1:18280/v0/jobs \
  -H 'Content-Type: application/json' \
  -d "{\"kind\":\"job\",\"class\":\"cpu\",\"payload_digest\":\"${DIGEST}\"}"
```

Local demo (same digest as above for echo/`hello`; no hand-computed digest required):

```bash
curl -sS -X POST http://127.0.0.1:18280/v0/jobs \
  -H 'Content-Type: application/json' \
  -d '{"demo":"echo","message":"hello"}'

curl -sS http://127.0.0.1:18280/v0/jobs
curl -sS http://127.0.0.1:18280/v0/jobs/<id>
```

Reserve-shaped UX seed (stub stages in `message` / `local.stage`; cancel while queued or running). **Not** a perf run and **not** `grammar/examples/reserve_ifrs17`:

```bash
ID=$(curl -sS -X POST http://127.0.0.1:18280/v0/jobs \
  -H 'Content-Type: application/json' \
  -d '{"demo":"reserve","catalog":"recorded"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

curl -sS "http://127.0.0.1:18280/v0/jobs/${ID}"
curl -sS "http://127.0.0.1:18280/v0/jobs/${ID}/handoff"
curl -sS "http://127.0.0.1:18280/v0/jobs/${ID}/payload"
# optional: class=gpu is a UX label only (still in-process stub)
curl -sS -X POST http://127.0.0.1:18280/v0/jobs \
  -H 'Content-Type: application/json' \
  -d '{"demo":"reserve","class":"gpu","seconds":8}'
# third catalog (runtime.reserve.parity_params on main); same keys; stub UX only
curl -sS -X POST http://127.0.0.1:18280/v0/jobs \
  -H 'Content-Type: application/json' \
  -d '{"demo":"reserve","catalog":"parity"}'
```

### Operator / ctl handoff (stub fallback vs binding)

Transport today is **operator/ctl-mediated only**. This guest does **not** open guest→ctl HTTP for compute-work, does **not** call `runtime.apply compute-work`, and does **not** invent `PLATFORM_RAY_*`, engine URLs, guest-callable ctl HTTP, or env that adds mesh destinations. Mesh on [`local-sos-compute.example.yaml`](https://github.com/guypayeur/panoramix-runtime/blob/main/bindings/local-sos-compute.example.yaml) is **from `compute-job` → to `sos`** (the worker calls this Unit). Example binding: [`local-reserve.example.yaml`](https://github.com/guypayeur/panoramix-runtime/blob/main/bindings/local-reserve.example.yaml) (Unit sos @18280, pin 0.5; engine in the binding only).

Two paths (plus an opt-in lab adapter below):

1. **Stub fallback (default):** `POST /v0/jobs` runs in-process. `local.backed` is `stub`. Submit/status/cancel stay on this Unit. Pause/resume is **refused** (`409 stub_only`).
2. **Operator binding path:** operator/ctl reads the exported WorkHandoff and admits that tuple on the runtime compute plane via the binding. This Unit only **emits** the JSON.
3. **Opt-in lab loopback:** `PANORAMIX_CTL_HTTP` (preferred) talks to runtime loopback ctl HTTP (`/reserve-temporal/…`); `PANORAMIX_RUNTIME_ROOT` still subprocesses `reserve-temporal` locally. Fail closed if unset. Not guest→ctl HTTP (not mesh). Not #70 Done.

```bash
# Guest UX (unchanged):
curl -sS -X POST http://127.0.0.1:18280/v0/jobs \
  -H 'Content-Type: application/json' \
  -d '{"demo":"reserve","label":"ux-seed","stages":3,"seconds":8}'

# Ctl reads the WorkHandoff projection + canonical payload bytes:
curl -sS http://127.0.0.1:18280/v0/jobs/<id>/handoff
curl -sS http://127.0.0.1:18280/v0/jobs/<id>/payload
# Admit those fields on the runtime compute plane (operator/ctl / binding).
# Guest never POSTs to ctl and never calls runtime.apply compute-work.
```

#### Durable temporal-local reserve (operator/ctl)

Same guest emit. Operator/ctl admits on the temporal-local binding with `runtime.apply reserve-temporal` (`admit|status|progress|events|cancel|pause|resume`; lifecycle status `paused`; pause|resume verified @ `3a164cd`) and [`bindings/local-reserve-temporal.example.yaml`](https://github.com/guypayeur/panoramix-runtime/blob/main/bindings/local-reserve-temporal.example.yaml) (`engine.kind: temporal-local`, guest-sos pin 0.5; mesh `temporal-worker` → `sos`) on panoramix-runtime **main**. Ctl `python3 -m runtime.apply reserve-temporal progress --id cw_…` exposes durable `stage` / `stages_total` / `stages_completed` / `fraction` / nested `progress` (verified @ `63c4d8e`); optional `stages[].elapsed_ms` when the tip supplies it (verified @ `9ba95bbb` / docs tip `5dc191cb` / main — omit when missing; never invent); optional `wall_elapsed_ms` / `started_at` when the tip supplies it (verified @ `9b6646e8` / main, PR #114 — omit when missing; never invent; not a forecast; not IFRS17; not iec SPA). Ctl `python3 -m runtime.apply reserve-temporal events --id cw_…` exposes the append-only JSONL trail under `.runtime/reserve-temporal/events/` (`events` / `events_n` / `events_durable` on status; kinds admit / StageCompleted / pause / resume / cancel / succeed|fail; verified @ `d86552e`). Survives runtime restart. Not a SIEM.

```bash
python3 -m runtime.apply reserve-temporal admit --catalog recorded   # or live|parity; or --handoff JSON
python3 -m runtime.apply reserve-temporal status --id cw_…
python3 -m runtime.apply reserve-temporal progress --id cw_…
python3 -m runtime.apply reserve-temporal events --id cw_…
python3 -m runtime.apply reserve-temporal pause --id cw_…
python3 -m runtime.apply reserve-temporal resume --id cw_…
python3 -m runtime.apply reserve-temporal cancel --id cw_…
```

Guest flow: UI / `POST /v0/jobs` with `demo:"reserve"` → `GET /v0/jobs/{id}/handoff` (+ `/payload`) → operator/ctl `reserve-temporal`. Guest-facing shape stays WorkHandoff only — no `workflow_id` / `task_queue` on the seam. Guest does not call apply. Cancel on this path is workflow cancel. When a durable hook is active, guest cancel is ctl-mediated (signals `reserve-temporal cancel` first). Guest local cancel is unchanged for stub-only. Pause/resume on the guest HTTP/UI is durable-path only (injected hook or opt-in lab adapter); stub jobs return `409 stub_only` and point here. Cancel is not pause. This does **not** close #70 and is not #78 Done; it does **not** stamp `north_star_done`.

`sos.runtime_hook.InertRuntimeHandoffHook` is **inert**: admit/cancel/status/pause/resume/progress/events return none/false, so the in-process stub still runs. The default hook stays inert (fail-closed without env). Do **not** invent guest→ctl HTTP over the mesh, `PLATFORM_RAY_*`, or mesh destinations. If an operator injects a hook that admits, cancel signals the hook first (same honesty as pause), then marks the guest job `canceled` if still live — or follows `hook.status()` when ctl already reports terminal. `GET /v0/jobs/{id}` and list refresh prefer `hook.status()` when `runtime_ref` exists so Temporal-backed runs show paused/running/terminal from ctl, not a stale stub clock. Pause/resume call the hook when present and only then set `paused` / `running`. `GET /v0/jobs/{id}/progress` prefers `hook.progress()` counters when the job is durable-backed; otherwise stub metadata. `GET /v0/jobs/{id}/events` prefers `hook.events()` JSONL when the job is durable-backed; otherwise process-memory.

#### Opt-in lab loopback (ctl HTTP, preferred)

Local lab only. When runtime `runtime.serve` is already listening on the reserve-temporal binding (`publish.ctl_bind` / `publish.ctl_port` **19215**), set `PANORAMIX_CTL_HTTP` to that **loopback** origin (example: `http://127.0.0.1:19215`). `SosApp` then injects `sos.lab_ctl_http.LabReserveTemporalHttpHook` on the **existing** hook seam and prefers durable status / progress / events / pause / resume / cancel via:

```bash
# runtime (already serving):
python3 -m runtime.serve --binding bindings/local-reserve-temporal.example.yaml
# guest:
export PANORAMIX_CTL_HTTP=http://127.0.0.1:19215
# optional when ctl.require is on:
# export PANORAMIX_CTL_HTTP_BEARER=…
```

Verbs match runtime **main** @ `fb901542` (PR #100) / [`docs/reserve.md`](https://github.com/guypayeur/panoramix-runtime/blob/main/docs/reserve.md) § Loopback ctl HTTP: `POST /reserve-temporal/admit` (WorkHandoff triple JSON or `?catalog=recorded`), `GET /reserve-temporal/status|progress|events?id=cw_…`, `POST /reserve-temporal/pause|resume|cancel?id=cw_…`. Unset, non-loopback, or an unusable origin **fails closed** (inert stub). If the origin is valid but `runtime.serve` is down (connection refused / origin not listening), admit/status/progress **fail closed** with `ctl_http_unreachable` (lab-serve down) — not a hung poll, not pretend durable. HTTP timeout while the origin is listening is **`ctl_admit_timeout`** on admit (not lab-serve-down); status/progress timeout is a missed poll. Admit that exceeds guest timeout (HTTP admit 8s / poll 1.5s / ctl-apply admit 2s) before a running id is **`ctl_admit_timeout`** — not lab-serve-down. live|parity is minutes-class and depends on runtime [#143](https://github.com/guypayeur/panoramix-runtime/issues/143) so admit returns `{id: cw_…, handoff.status: running}` while work continues; guest then polls `GET /v0/jobs/{id}/progress` and `GET /events` mid-flight. Fail closed — no stub progress. Recorded stays sync-fast / stub fallback on HTTP 4xx/5xx. Optional `PANORAMIX_CTL_HTTP_BEARER` sends `Authorization: Bearer …`. Optional `PANORAMIX_RESERVE_TEMPORAL_LIVE=1` adds `live=1` on admit. This is **operator loopback ctl HTTP**, not guest→mesh ctl, not a Unit Git scheme, and not `runtime.apply compute-work`. Pin stays **0.5**.

When `PANORAMIX_CTL_HTTP` is unset, the subprocess path below still works. When both are set, HTTP wins. CI without either env is unchanged.

#### Lab compose (one-shot serve + CTL_HTTP)

One-shot local lab (script + [docs/lab-compose.md](docs/lab-compose.md)): start `runtime.serve` with [`bindings/local-reserve-temporal.example.yaml`](https://github.com/guypayeur/panoramix-runtime/blob/main/bindings/local-reserve-temporal.example.yaml) (ctl **19215**), start this guest with `PANORAMIX_CTL_HTTP=http://127.0.0.1:19215` and `PLATFORM_LISTEN_HTTP`, POST a recorded reserve demo, show `local.backed=runtime` plus durable progress/events/`pause_resume`, then cancel/fail → one-click `POST /v0/jobs/{id}/re-admit` (new job id). Opt-in `--catalog live|parity` is minutes-class: admit must return a running id (runtime #143) so `:18280` can poll mid-flight; `--catalog parity` smoke is mid-flight poll + cancel, not wait-for-succeed; timeout is `ctl_admit_timeout` (no stub progress). `--dry-run` covers hooked + fail-closed without Temporal (no silent stub; not resume-from-failed) and records `async_admit` plus elapsed honesty (`9ba95bbb` / docs tip `5dc191cb` / main; omit when missing) plus optional `wall_elapsed_ms` / `started_at` (runtime tip `9b6646e8` / PR #114 / main; omit when missing) plus the Handoff docs panel (not a second control plane) plus `pack_fill.fragment` (tips; optional durable only when measured) that can feed `python3 -m runtime.iec_parity_pack skeleton` via `--from-json` / flags (runtime tip `b81130f` / [PR #120](https://github.com/guypayeur/panoramix-runtime/pull/120); docs tip `63a168d` / [PR #122](https://github.com/guypayeur/panoramix-runtime/pull/122) WSL assist-smoke stamp lineage; gap-report tip `84cb202` / [PR #124](https://github.com/guypayeur/panoramix-runtime/pull/124); gap-report docs tip `aa4f09e` / [PR #126](https://github.com/guypayeur/panoramix-runtime/pull/126) / main; guest emit `b859466` / [PR #52](https://github.com/guypayeur/panoramix-guest-sos/pull/52); wall tip remains `9b6646e8`; omit when missing; never invent `metrics.wall_time_sec`; assist ≠ fill) plus a `pack_fill.merge` hint (`python3 -m runtime.iec_parity_pack merge … --from-json`; runtime tip `5086d0f` / [PR #128](https://github.com/guypayeur/panoramix-runtime/pull/128) / main; merge docs tip `6ecb645` / [PR #130](https://github.com/guypayeur/panoramix-runtime/pull/130) / main; cd+cmd when `PANORAMIX_RUNTIME_ROOT` known, else a copy-paste template; does **not** run merge; **merge ≠ fill; merge ≠ Done; assist ≠ Done**) plus a `pack_fill.apply_metrics` hint (`python3 -m runtime.iec_parity_pack apply-metrics … --from-durable-panoramix`; runtime tip `5d399f7` / [PR #132](https://github.com/guypayeur/panoramix-runtime/pull/132) / main; apply-metrics docs tip `3904ee4` / [PR #134](https://github.com/guypayeur/panoramix-runtime/pull/134) / main; cd+cmd when `PANORAMIX_RUNTIME_ROOT` known, else a copy-paste template; does **not** run apply-metrics; does **not** supply wall numbers; **apply-metrics ≠ fill; apply-metrics ≠ Done; assist ≠ Done**) plus a `pack_fill.apply_notes` hint (`python3 -m runtime.iec_parity_pack apply-notes …`; runtime tip `48a8645` / [PR #136](https://github.com/guypayeur/panoramix-runtime/pull/136) / main; apply-notes docs tip `6807509` / [PR #138](https://github.com/guypayeur/panoramix-runtime/pull/138) / main; cd+cmd when `PANORAMIX_RUNTIME_ROOT` known, else a copy-paste template; does **not** run apply-notes; does **not** supply wall numbers; does **not** invent UX strings; **apply-notes ≠ fill; apply-notes ≠ Done; assist ≠ Done**) plus a `pack_fill.gap_report` hint (`python3 -m runtime.iec_parity_pack gap-report`; does **not** run gap-report; **gap-report ≠ Done**). Operator live #78 D pack is off-box at `~/panoramix-lab/evidence-70/iec-parity-live-20260912/` with STRICT `stamp-48a8645-iec-parity-live/` — **live fill ≠ Done**; `north_star_done` false; `comparable` false; does **not** unlock cloud. Fail-closed without env. Not guest→mesh ctl. Not SIEM. Not IFRS17. Pin **0.5**. Does **not** close runtime #70 / #78; does **not** unlock #61 / #29; `north_star_done` stays false.

```bash
# Plan only (no processes, no Temporal — CI):
python3 scripts/lab_compose_reserve_temporal.py --dry-run

# Live one-shot (operator lab; needs a panoramix-runtime checkout):
export PANORAMIX_RUNTIME_ROOT=/path/to/panoramix-runtime
python3 scripts/lab_compose_reserve_temporal.py
```

Sibling **iec-local same-job** compose (ctl **19216**, catalog `reserve_ifrs17` / `same-job`; [docs/lab-compose-iec-local.md](docs/lab-compose-iec-local.md)): `PANORAMIX_CTL_HTTP=http://127.0.0.1:19216` talks to `POST/GET /iec-local/…`. Guest does **not** run IFRS17 math — the runtime binding wraps the operator iec checkout (`POST /v1/jobs`). Fail-closed on the stub (`same_job_stub`). `--dry-run` covers hooked running + inert fail-closed without a checkout. Does **not** close runtime #70 / #78. `north_star_done` stays false.

```bash
python3 scripts/lab_compose_iec_local.py --dry-run
export PANORAMIX_RUNTIME_ROOT=/path/to/panoramix-runtime
python3 scripts/lab_compose_iec_local.py
```

WSL stamp already exists at `~/panoramix-lab/evidence-70/stamp-71fb4c9-ctl-http/` — this compose does **not** reproduce that pack and does **not** stamp the #70 UX Done-when boxes.

#### Opt-in lab loopback (local subprocess)

Local lab only. Set `PANORAMIX_RUNTIME_ROOT` to a [panoramix-runtime](https://github.com/guypayeur/panoramix-runtime) checkout that contains `runtime/apply.py`. `SosApp` then injects `sos.lab_ctl.LabReserveTemporalHook` on the **existing** hook seam. That adapter runs `python3 -m runtime.apply reserve-temporal` (`admit|status|progress|events|pause|resume|cancel`) as a **local subprocess** against that checkout, using the WorkHandoff the guest already emits. Optional `PANORAMIX_RESERVE_TEMPORAL_BINDING` passes `--binding`. Optional `PANORAMIX_RESERVE_TEMPORAL_LIVE=1` passes `--live`. Unset or missing root **fails closed** (inert stub). Prefer `PANORAMIX_CTL_HTTP` when serve is already up; this subprocess path stays valid.

This is not guest-callable ctl HTTP, not a second control plane, and not `runtime.apply compute-work`. Stub-only pause/resume still **409** `stub_only`. Does **not** close runtime #70 / #78, does **not** unlock cloud, does **not** stamp `north_star_done`.

**Cancel contract:** cancel is not pause. Durable cancel is ctl-mediated. Stub-backed → local cancel (`canceled`, one L). Runtime-backed (opt-in `PANORAMIX_CTL_HTTP` preferred or `PANORAMIX_RUNTIME_ROOT`) → signal ctl cancel first (same honesty as pause), then mark the guest job `canceled` if still live — or follow `hook.status()` when ctl already reports terminal. Job detail / list refresh prefer hook `status()` when `runtime_ref` exists (not a stale stub clock). Fail-closed without hook (inert default). Cancel/fail does **not** auto-retry. Terminal cancel is still **409**. Pause/resume require the durable path.

### Guest job history (local lab files)

Default: persist job records under `.sos/jobs` (catalog / kind / class, created / updated, status, digests, payload bytes when known, optional durable `wall_elapsed_ms` when seen, handoff / `runtime_ref` pointers). On start, recent records reload so `GET /v0/jobs/{id}/compare` can use succeeded priors across guest restart (including a persisted durable wall). Typical/ETA still only from **≥2 real succeeded walls**. Recoverability still exports handoff / payload when known — persistence does **not** invent metrics, walls, or SIEM claims.

- `PANORAMIX_SOS_JOBS_DIR` — override the directory (absolute or relative).
- Unset — keep the default `.sos/jobs`.
- `off` / `0` / `disabled` / `false` / empty — **fail closed** (in-process only; restart wipes priors; compare stays honest).
- Unwritable dir — **fail closed** (guest keeps serving; no invented history).

Not a SIEM. Not a six-month regulatory audit product. Not a cross-host DB. Does **not** close #70 / #78. Does **not** stamp `north_star_done`. The stub records opaque work locally; it does not start an engine.

Sleep, then cancel while queued/running:

```bash
ID=$(curl -sS -X POST http://127.0.0.1:18280/v0/jobs \
  -H 'Content-Type: application/json' \
  -d '{"demo":"sleep","seconds":8}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

curl -sS -X POST "http://127.0.0.1:18280/v0/jobs/${ID}/cancel"
curl -sS "http://127.0.0.1:18280/v0/jobs/${ID}"
```

Pause/resume of a **stub** job (default) is refused:

```bash
curl -sS -X POST "http://127.0.0.1:18280/v0/jobs/${ID}/pause"
# 409 {"error":"stub_only", ...} — requires durable path; see ctl pause|resume
```

Bad `kind` / `class` / `payload_digest` return **400**. Cancel of a terminal job returns **409** `{"error":"already_terminal", ...}`. Missing ids return **404**. Opaque digest-only jobs have no stored bytes: `GET .../payload` returns **404** `payload_unknown`.

### Tests

```bash
python3 -m unittest
# or:
python3 -m unittest discover -s tests -v
```

With Panoramix tools (from a [panoramix](https://github.com/guypayeur/panoramix) checkout):

```bash
GUEST=/path/to/panoramix-guest-sos
python3 platform-tools/platform_check.py "$GUEST"
python3 platform-tools/platform_emulate.py "$GUEST" --run --duration 2
```

Emulate is Unix adapter / localhost edge. It does not execute `build.command`. It is not `process` / `container` / `microvm`, and it is not AWS.

## Operational notes

See [PANORAMIX_OPERATIONAL.md](PANORAMIX_OPERATIONAL.md) (domain-leak log and guest compute seam).
