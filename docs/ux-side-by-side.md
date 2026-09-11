# UX side-by-side: iec run-lifecycle vs guest SoS operator

Walk of [iec-proto-c `docs/ux/journeys/run_lifecycle_monitoring.md`](https://github.com/guypayeur/iec-proto-c/blob/main/docs/ux/journeys/run_lifecycle_monitoring.md) (iec `@4d5d44d`) against this guest’s operator UI (`GET /`, `GET /ui`) and jobs API. Named iec baseline remains [`grammar/examples/reserve_ifrs17`](https://github.com/guypayeur/iec-proto-c) (runtime [`proofs/fixtures/iec-parity/method.yaml`](https://github.com/guypayeur/panoramix-runtime/blob/main/proofs/fixtures/iec-parity/method.yaml) after [#82](https://github.com/guypayeur/panoramix-runtime/pull/82)).

**Honesty:** this note does **not** stamp [runtime#70](https://github.com/guypayeur/panoramix-runtime/issues/70) UX Done, does **not** set `north_star_done`, and does **not** unlock cloud [#61](https://github.com/guypayeur/panoramix-runtime/issues/61) / [#29](https://github.com/guypayeur/panoramix-runtime/issues/29). [#78](https://github.com/guypayeur/panoramix-runtime/issues/78) stays open. Guest `demo: reserve` is a stub / UX seed — **not** IFRS17 math.

## Links

| Surface | Where |
|---|---|
| iec journey | [`docs/ux/journeys/run_lifecycle_monitoring.md`](https://github.com/guypayeur/iec-proto-c/blob/main/docs/ux/journeys/run_lifecycle_monitoring.md) |
| Guest operator UI | `GET /` and `GET /ui` (stdlib HTML/JS, no SPA framework) |
| Guest jobs API | `POST/GET /v0/jobs`, `GET /v0/jobs/{id}`, `POST /v0/jobs/{id}/cancel`, `POST /v0/jobs/{id}/pause`, `POST /v0/jobs/{id}/resume` |
| Progress (thinner) | `GET /v0/jobs/{id}/progress` |
| Event trail (thinner) | `GET /v0/jobs/{id}/events` (durable JSONL when hooked; else process-memory; also `events` on the job resource) |
| Historical compare (thinner) | `GET /v0/jobs/{id}/compare` — recent same-catalog (or same kind/class) jobs already in this process; elapsed + optional typical/ETA from succeeded priors |
| Failure / terminal (thinner) | Failed/canceled `GET /v0/jobs/{id}` exposes `terminal` (status + message + optional last events / stage) — **not** a SIEM, **not** iec `/v1/audit/events` |
| Recoverability (thinner) | Failed/canceled jobs expose `recoverability` (handoff + payload for operator/ctl re-admit). Cancel/fail does **not** auto-retry. Pause/resume remains durable-only |
| Ctl handoff | `GET /v0/jobs/{id}/handoff`, `GET /v0/jobs/{id}/payload` |
| Durable ctl (temporal-local) | operator/ctl `runtime.apply reserve-temporal` admit\|status\|progress\|events\|cancel\|pause\|resume on panoramix-runtime **main** (`progress --id` → `stage` / `stages_total` / `stages_completed` / `fraction` / nested `progress`, verified @ `63c4d8e`; `events --id` → JSONL under `.runtime/reserve-temporal/events/`, verified @ `d86552e`; `pause\|resume` verified @ `3a164cd`; status `paused` + `events` / `events_n` / `events_durable`) + runtime [`bindings/local-reserve-temporal.example.yaml`](https://github.com/guypayeur/panoramix-runtime/blob/main/bindings/local-reserve-temporal.example.yaml) (pin 0.5). Same verbs on operator loopback ctl HTTP (`runtime.serve` / `publish.ctl_port` **19215**: `POST /reserve-temporal/admit`, `GET /reserve-temporal/status\|progress\|events`, `POST /reserve-temporal/pause\|resume\|cancel`). Guest may opt in via `PANORAMIX_CTL_HTTP` (preferred) or `PANORAMIX_RUNTIME_ROOT` (subprocess) on the existing hook seam — not guest→mesh ctl |
| Catalogs | recorded / live / parity (parity-scale) — guest mirrors panoramix-runtime **main** `runtime.reserve.parity_params` / `digest_for` / [`docs/reserve.md`](https://github.com/guypayeur/panoramix-runtime/blob/main/docs/reserve.md) |

## Journey walk

| Journey step | iec touchpoint | Guest support | Notes |
|---|---|---|---|
| 1.1 Job detail + status | SPA → `GET /v1/jobs/{job_id}` | **match** (thinner) | `GET /v0/jobs/{id}` + job detail panel: id, status pill, kind/class/digest (short), created/updated/elapsed, `message`, `local.stage`, `local.backed`. Failed/canceled jobs add a **terminal** summary (`status` + `message` + optional last events / stage) — labeled **not** SIEM / **not** iec `/v1/audit/events`. Historical comparison (`GET /v0/jobs/{id}/compare`) against recent same-catalog (or same kind/class) jobs already in this process: elapsed for this run + priors; typical/ETA only from succeeded prior walls when two or more samples exist. Honest empty / single-prior (no invented numbers). **not a forecast**, **not** IFRS17, **not** iec SPA historical widget |
| 1.2 Step/chunk progress | `GET /v1/jobs/{id}/progress` | **match** (thinner) | `GET /v0/jobs/{id}/progress` prefers durable reserve-temporal path-slice counters (`stage`, `stages_total`, `stages_completed`, `fraction`, nested `progress`) when a hook provides them (`source: durable`). Stub fallback (`source: stub`) still shows “stage i of n”. UI shows `stages_completed` / `fraction` when present. Operator/ctl: `python3 -m runtime.apply reserve-temporal progress --id cw_…`. This is not iec chunk progress and not iec planner parallelism or SPA progress |
| 2.1 Pause | `POST /v1/jobs/{id}/pause` | **match** (thinner) | Guest `POST /v0/jobs/{id}/pause` on durable-backed jobs (status `paused` on WorkHandoff). Stub-only → **409** `stub_only` (no pretend). Operator/ctl: `python3 -m runtime.apply reserve-temporal pause --id cw_…`. Cancel is not pause |
| 2.2 Investigate | SPA progress + catalog + Slack | **match** (thinner) | Catalog identity already on the job (name + short digest) called out for cross-check — **not** a data-catalog product. Static day-one step-ownership tags on durable path-slices when hooked (`admit` / `project` / `fold` / `complete` → `ctl / admit`, `kernel / project`, `kernel / fold`, `ctl / complete`; **not** Slack, **not** a live team directory). Event trail stays on the same panel (durable JSONL when hooked; labeled **not** SIEM). Still **not** iec SPA / Slack / real data catalog |
| 3.1a Resume | `POST /v1/jobs/{id}/resume` | **match** (thinner) | Guest `POST /v0/jobs/{id}/resume` on paused durable-backed jobs (status back to `running`). Stub-only → **409** `stub_only`. Operator/ctl: `python3 -m runtime.apply reserve-temporal resume --id cw_…` |
| 3.1b Cancel | `POST /v1/jobs/{id}/cancel` | **match** (thinner) | Guest UI cancel is **local stub** cancel (`canceled`) from running or paused. Durable cancel/status is operator/ctl `reserve-temporal` (workflow cancel on temporal-local). Confirm dialog: cancel is not pause; pause exists on durable/ctl path only. Cancel/fail does **not** auto-retry |
| Failure surface (clarity) | job detail after fail/cancel | **match** (thinner) | Failed and canceled job detail (API `terminal` + operator UI panel): status + message + optional last events / stage when known. Labeled **not** SIEM / **not** iec `/v1/audit/events` product. No invented wall times or SIEM claims |
| Recoverability (handoff re-admit) | ctl re-admit after fail/cancel | **match** (thinner) | Easy access to `GET /v0/jobs/{id}/handoff` + `/payload` for operator/ctl re-admit (`python3 -m runtime.apply reserve-temporal admit --handoff JSON`). Copy: cancel/fail does **not** auto-retry; no resume-from-failed. Pause/resume remains durable-only (stub **409** `stub_only`). Salvageable is handoff identity + payload bytes when known — not in-flight compute |
| 4.1 Audit trail | `GET /v1/audit/events?job_id=…` | **match** (thinner) | `GET /v0/jobs/{id}/events` prefers durable reserve-temporal JSONL (`source: durable`, `events_durable`, `events_n`) when a hook provides it. Operator/ctl: `python3 -m runtime.apply reserve-temporal events --id cw_…` (append-only JSONL under `.runtime/reserve-temporal/events/`; kinds admit / StageCompleted / pause / resume / cancel / succeed/fail). Process-memory fallback (`source: memory`, local event trail) otherwise. Day-one local durable trail — **not a SIEM**, **not** iec `/v1/audit/events` product, **not** six-month regulatory defensibility |

Support key: **match** = same operator intent, thinner surface; **partial** = honest subset; **missing** = not implemented and not faked.

## What matches today

- Submit → list → get → status pills (`queued` → `running` ⇄ `paused` → `succeeded` \| `failed` \| `canceled`). `paused` is non-terminal.
- Job detail for a selected run (identity, timestamps, current message/stage, stub vs runtime `backed`). Failed/canceled jobs surface a **terminal** summary (status + message + optional last events / stage) — labeled **not** SIEM / **not** iec audit product. Recoverability (thinner): handoff + payload export for operator/ctl re-admit; cancel/fail does **not** auto-retry; no resume-from-failed. Progress prefers durable path-slice counters when a hook provides them; otherwise stub “stage i of n”. Events prefer durable JSONL when a hook provides them; otherwise process-memory. Historical comparison (thinner) against recent same-catalog / same-kind-class jobs already in guest history: elapsed for this run + priors; typical/ETA only from real succeeded prior walls. Investigate (thinner): catalog name + short digest called out for cross-check; static path-slice ownership tags when hooked; event trail on the same panel.
- Cancel of a live run with clear framing and `canceled` (one L). Stub-backed cancel is **guest local**. Durable temporal-local cancel/status/pause/resume is **operator/ctl** (`runtime.apply reserve-temporal` or loopback ctl HTTP), not guest→ctl HTTP over the mesh. An injected hook (if present) is signaled first, then the guest job is marked `canceled` if still live (running or paused). Terminal cancel is **409**. The default hook stays inert. Opt-in lab (`PANORAMIX_CTL_HTTP` preferred, or `PANORAMIX_RUNTIME_ROOT` subprocess) may follow `reserve-temporal` on that same hook seam. Cancel is not pause.
- Pause/Resume on the **durable path** (injected hook or opt-in lab adapter): guest `POST .../pause` → `paused`, `POST .../resume` → `running`, `pause_resume: true` on those responses. Stub-only jobs **409** `stub_only`; UI controls stay disabled with an explanation. Operator/ctl: `python3 -m runtime.apply reserve-temporal pause --id cw_…` and `python3 -m runtime.apply reserve-temporal resume --id cw_…` (or the same verbs on loopback ctl HTTP when `PANORAMIX_CTL_HTTP` is set).
- Opaque WorkHandoff emit (`kind` / `class` / `payload_digest` + `id` / `status`) and payload export for the ctl path. Failed/canceled recoverability points at the same exports for operator/ctl `reserve-temporal admit --handoff JSON`. Guest does **not** call `runtime.apply compute-work`. Default guest does not invoke apply; opt-in lab may talk loopback ctl HTTP or subprocess `reserve-temporal` only.
- Echo / sleep / reserve demos still work. Default recorded catalog digest stays `sha256:77e9299f4b8ea4aeed46f71b91cc947d56e9bd169d795e70845123fef53d7e4e`.

## What is still thinner

- **Pause / resume full Temporal-backed UX.** Guest HTTP/UI pause/resume is thinner: durable-backed only (injected hook or opt-in lab adapter), stub refused honestly. Default hook stays inert — no guest→ctl HTTP over the mesh. Operators still use `python3 -m runtime.apply reserve-temporal pause|resume --id cw_…` for the ctl path, or set `PANORAMIX_CTL_HTTP` (loopback HTTP) / `PANORAMIX_RUNTIME_ROOT` (subprocess) for local-lab follow on the same hook. This does **not** stamp the #70 UX box.
- **Temporal-backed guest UX.** Durable admit/status/cancel/pause/resume is operator/ctl (`reserve-temporal`). Guest UI cancel remains local stub cancel unless a hook admits. Opt-in lab loopback is a thinner local HTTP or subprocess on the existing hook seam — not #70 Done, not cloud, not IFRS17.
- **Real chunk progress** / planner observations / parallelism visualization. Guest progress is reserve-temporal **path-slices** (four kernel stages when hooked) — **not** iec planner parallelism or iec SPA progress.
- **Regulatory audit** product (job-scoped `/v1/audit/events`, six-month defensibility). Guest events prefer reserve-temporal JSONL when hooked (survives runtime restart); else process-memory. Still not SIEM / compliance / iec `/v1/audit/events`.
- **SPA polish**: historical comparison is **match (thinner)** — guest-history only (same catalog / kind-class elapsed + typical from priors when enough samples). **Not** iec SPA historical widget, **not a forecast**, **not** prior-quarter IFRS17. Still no Slack, no live team directory, no data-catalog product. Guest investigate is catalog identity + static ownership tags on durable path-slices + event trail — **not** iec SPA / Slack / real data catalog.
- **IFRS17 / `reserve_ifrs17` math** and comparable **perf**. Guest now mirrors the third **parity** catalog from panoramix-runtime **main** (`runtime.reserve.parity_params` / `digest_for`); the stub still does not run that kernel. Faster stub wall time is not evidence. #70/#78 stay open.

## Catalogs

| Catalog | Guest today | Notes |
|---|---|---|
| recorded | yes | CI / default; digest `sha256:77e9299f4b8ea4aeed46f71b91cc947d56e9bd169d795e70845123fef53d7e4e` |
| live | yes | Heavier lab catalog; still not IFRS17 |
| parity (parity-scale) | yes | Same keys as recorded/live. Mirrors `runtime.reserve.parity_params()` / `digest_for` on panoramix-runtime **main** (`docs/reserve.md`). Digest `sha256:e180d2c2e3589b8762f92efa1bedb3d53ffeeb16648581ba13d537bcd3311102`. Still not IFRS17; not #70 Done |

## Done-when checklist for the #70 UX box

These are the [runtime#70](https://github.com/guypayeur/panoramix-runtime/issues/70) UX north-star items. **Unchecked items stay unchecked.** This guest PR does **not** mark #70 Done.

- [ ] Operator/actuary path for a representative SoS workflow is **match or better** than the corresponding iec-proto-c experience (clarity of job status, failure surface, recoverability, handoff docs)
- [ ] Side-by-side recorded against the named iec baseline **and** the #70 UX box stamped
- [ ] Pause / resume only when a real compute-plane durable path exists (not a guest stub) — guest HTTP is thinner/durable-only; default hook still inert; ctl `reserve-temporal pause|resume` is the operator path; opt-in lab adapter (loopback HTTP or subprocess) is the same hook seam, not a stub pretend
- [ ] Temporal-backed UX (guest UI status/cancel/pause/resume follows durable temporal-local runs without an injected hook) — operator/ctl `reserve-temporal` exists; opt-in lab still uses the hook injection point (`PANORAMIX_CTL_HTTP` or `PANORAMIX_RUNTIME_ROOT`); default remains inert stub cancel + disabled stub pause
- [ ] Real chunk / step progress (not stub stage metadata) — guest now prefers durable path-slices when hooked; still not iec planner / SPA progress
- [ ] Regulatory audit trail (not the local in-memory event list) — guest now prefers durable JSONL when hooked; still not SIEM / six-month / iec `/v1/audit/events`
- [ ] `north_star_done: true` (UX **and** perf). Perf is out of scope here
- [ ] Cloud unlock (#61 / #29) — **locked**; not this box

Guest-side progress that is **not** the #70 stamp:

- [x] Honest job detail panel on the operator UI
- [x] Honest thinner progress endpoint + stage timeline (durable path-slices when hooked, else stub)
- [x] Cancel confirm framing (cancel is not pause; pause on durable/ctl path only)
- [x] Pause/Resume HTTP + UI (durable path only; stub `409 stub_only`; no pretend)
- [x] Event trail (durable JSONL when hooked, else process-memory; labeled not SIEM / not regulatory audit)
- [x] Thinner investigate (catalog identity + static path-slice ownership tags when hooked; event trail on the same panel; not Slack / not data catalog / not SIEM)
- [x] Thinner historical-run comparison (guest process history; elapsed vs priors; typical/ETA only from real succeeded priors; not a forecast / not iec SPA widget)
- [x] Thinner failure / terminal summary (status + message + optional last events / stage; labeled not SIEM / not iec audit product)
- [x] Thinner recoverability (handoff + payload re-admit; cancel/fail does not auto-retry; pause/resume remains durable-only)
- [x] Handoff / payload affordances (WorkHandoff emit only)
- [x] This side-by-side note
- [x] Mirror recorded / live / parity (parity-scale) catalog keys + parity digest (`runtime.reserve.parity_params` on main)
