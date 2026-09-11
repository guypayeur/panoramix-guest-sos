# UX side-by-side: iec run-lifecycle vs guest SoS operator

Walk of [iec-proto-c `docs/ux/journeys/run_lifecycle_monitoring.md`](https://github.com/guypayeur/iec-proto-c/blob/main/docs/ux/journeys/run_lifecycle_monitoring.md) (iec `@4d5d44d`) against this guest’s operator UI (`GET /`, `GET /ui`) and jobs API. Named iec baseline remains [`grammar/examples/reserve_ifrs17`](https://github.com/guypayeur/iec-proto-c) (runtime [`proofs/fixtures/iec-parity/method.yaml`](https://github.com/guypayeur/panoramix-runtime/blob/main/proofs/fixtures/iec-parity/method.yaml) after [#82](https://github.com/guypayeur/panoramix-runtime/pull/82)).

**Honesty:** this note does **not** stamp [runtime#70](https://github.com/guypayeur/panoramix-runtime/issues/70) UX Done, does **not** set `north_star_done`, and does **not** unlock cloud [#61](https://github.com/guypayeur/panoramix-runtime/issues/61) / [#29](https://github.com/guypayeur/panoramix-runtime/issues/29). [#78](https://github.com/guypayeur/panoramix-runtime/issues/78) stays open. Guest `demo: reserve` is a stub / UX seed — **not** IFRS17 math.

## Links

| Surface | Where |
|---|---|
| iec journey | [`docs/ux/journeys/run_lifecycle_monitoring.md`](https://github.com/guypayeur/iec-proto-c/blob/main/docs/ux/journeys/run_lifecycle_monitoring.md) |
| Guest operator UI | `GET /` and `GET /ui` (stdlib HTML/JS, no SPA framework) |
| Guest jobs API | `POST/GET /v0/jobs`, `GET /v0/jobs/{id}`, `POST /v0/jobs/{id}/cancel` |
| Progress (thinner) | `GET /v0/jobs/{id}/progress` |
| Local event trail | `GET /v0/jobs/{id}/events` (also `events` on the job resource) |
| Ctl handoff | `GET /v0/jobs/{id}/handoff`, `GET /v0/jobs/{id}/payload` |
| Durable ctl (temporal-local) | operator/ctl `runtime.apply reserve-temporal` + runtime [`bindings/local-reserve-temporal.example.yaml`](https://github.com/guypayeur/panoramix-runtime/blob/main/bindings/local-reserve-temporal.example.yaml) (pin 0.5) on panoramix-runtime **main** |
| Catalogs | recorded / live / parity (parity-scale) — guest mirrors panoramix-runtime **main** `runtime.reserve.parity_params` / `digest_for` / [`docs/reserve.md`](https://github.com/guypayeur/panoramix-runtime/blob/main/docs/reserve.md) |

## Journey walk

| Journey step | iec touchpoint | Guest support | Notes |
|---|---|---|---|
| 1.1 Job detail + status | SPA → `GET /v1/jobs/{job_id}` | **match** (thinner) | `GET /v0/jobs/{id}` + job detail panel: id, status pill, kind/class/digest (short), created/updated/elapsed, `message`, `local.stage`, `local.backed` |
| 1.2 Step/chunk progress | `GET /v1/jobs/{id}/progress` | **partial** | `GET /v0/jobs/{id}/progress` returns `{id,status,stage,stages_total?,message,backed}` derived from stub fields. UI shows “stage i of n”. This is not iec chunk progress / parallelism |
| 2.1 Pause | `POST /v1/jobs/{id}/pause` | **missing** | No pause. Operator/ctl temporal-local has status/cancel only — not pause/resume. Do not add guest buttons that pretend otherwise |
| 2.2 Investigate | SPA progress + catalog + Slack | **partial** | Current `message` / `local.stage` / local event trail. No data catalog, no step-ownership tags |
| 3.1a Resume | `POST /v1/jobs/{id}/resume` | **missing** | No resume. Cancel + resubmit is the only recoverability path |
| 3.1b Cancel | `POST /v1/jobs/{id}/cancel` | **match** (thinner) | Guest UI cancel is **local stub** cancel (`canceled`). Durable cancel/status is operator/ctl `reserve-temporal` (workflow cancel on temporal-local). Confirm dialog: no pause/resume |
| 4.1 Audit trail | `GET /v1/audit/events?job_id=…` | **partial** | In-memory `[{ts,event,detail}]` on submit / stage / cancel / terminal. Labeled **local event trail** — not a regulatory audit product |

Support key: **match** = same operator intent, thinner surface; **partial** = honest subset; **missing** = not implemented and not faked.

## What matches today

- Submit → list → get → status pills (`queued` → `running` → `succeeded` \| `failed` \| `canceled`).
- Job detail for a selected run (identity, timestamps, current message/stage, stub vs runtime `backed`).
- Cancel of a live run with clear framing and `canceled` (one L). Stub-backed cancel is **guest local**. Durable temporal-local cancel/status is **operator/ctl** (`runtime.apply reserve-temporal`), not the guest UI. An injected hook (if present) is signaled first, then the guest job is marked `canceled` if still live. Terminal cancel is **409**. The default hook stays inert.
- Opaque WorkHandoff emit (`kind` / `class` / `payload_digest` + `id` / `status`) and payload export for the ctl path. Guest does **not** call `runtime.apply`.
- Echo / sleep / reserve demos still work. Default recorded catalog digest stays `sha256:77e9299f4b8ea4aeed46f71b91cc947d56e9bd169d795e70845123fef53d7e4e`.

## What is still thinner

- **Pause / resume** (iec Temporal-signal path). Operator/ctl temporal-local exposes durable **status + cancel** only. This guest will not add buttons that pretend pause/resume exists.
- **Temporal-backed guest UX.** Durable admit/status/cancel is operator/ctl (`reserve-temporal`). Guest UI cancel remains local stub cancel. Loopback hook wiring is deferred.
- **Real chunk progress** / planner observations / parallelism visualization.
- **Regulatory audit** product (job-scoped `/v1/audit/events`, six-month defensibility). Local trail is process-memory and dies on restart.
- **SPA polish**: no historical-run comparison, no ETA vs prior quarter, no step-ownership, no cross-tool investigation.
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
- [ ] Pause / resume only when a real compute-plane durable path exists (not a guest stub)
- [ ] Temporal-backed UX (guest UI status/cancel follows durable temporal-local runs) — operator/ctl `reserve-temporal` exists; guest UI is still local cancel
- [ ] Real chunk / step progress (not stub stage metadata)
- [ ] Regulatory audit trail (not the local in-memory event list)
- [ ] `north_star_done: true` (UX **and** perf). Perf is out of scope here
- [ ] Cloud unlock (#61 / #29) — **locked**; not this box

Guest-side progress that is **not** the #70 stamp:

- [x] Honest job detail panel on the operator UI
- [x] Honest thinner progress endpoint + stage timeline
- [x] Cancel confirm framing (no pause/resume; stub vs runtime)
- [x] Local event trail (labeled as such)
- [x] Handoff / payload affordances (WorkHandoff emit only)
- [x] This side-by-side note
- [x] Mirror recorded / live / parity (parity-scale) catalog keys + parity digest (`runtime.reserve.parity_params` on main)
