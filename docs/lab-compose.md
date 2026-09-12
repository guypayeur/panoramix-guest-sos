# Lab compose: one-shot Temporal-backed reserve path

One-shot local lab so an operator can start **runtime.serve** (ctl **19215**) and this guest with `PANORAMIX_CTL_HTTP`, POST a recorded reserve demo, and see `local.backed=runtime` plus durable progress / events / `pause_resume`, then **admit → cancel/fail → one-click `POST /v0/jobs/{id}/re-admit` → new job id** when the durable hook is active (`PANORAMIX_CTL_HTTP` preferred or `PANORAMIX_RUNTIME_ROOT`).

WSL stamps already exist at operator lab `~/panoramix-lab/evidence-70/stamp-71fb4c9-ctl-http/` and `~/panoramix-lab/evidence-70/stamp-9b6646e8-wall-elapsed/` (recorded+STRICT exit 0; wall probe OK) — this page does **not** reproduce those packs.

**Honesty:** fail-closed without env. Not guest→mesh ctl. Not a second control plane. Not SIEM. Not IFRS17. Pin **0.5**. WorkHandoff triple only. Path-slice elapsed omitted when timestamps missing (never invent). Optional durable `stages[].elapsed_ms` can come from runtime tip [`9ba95bbb`](https://github.com/guypayeur/panoramix-runtime/commit/9ba95bbb4fa4c9046abee6eac60158e4fd649b90) / docs tip [`5dc191cb`](https://github.com/guypayeur/panoramix-runtime/commit/5dc191cbfb103147c2b9c32a6be3f5b97732994d) (or **main**, [PR #110](https://github.com/guypayeur/panoramix-runtime/pull/110) / [PR #112](https://github.com/guypayeur/panoramix-runtime/pull/112)) — omit when missing; never invent. Optional durable `wall_elapsed_ms` / `started_at` can come from runtime tip [`9b6646e8`](https://github.com/guypayeur/panoramix-runtime/commit/9b6646e8829056c22339842321986afaf7d6b957) (or **main**, [PR #114](https://github.com/guypayeur/panoramix-runtime/pull/114); docs tip [`6511cec7`](https://github.com/guypayeur/panoramix-runtime/commit/6511cec7) / [PR #116](https://github.com/guypayeur/panoramix-runtime/pull/116) for evidence-index lineage) — omit when missing; never invent; **not** a forecast; **not** IFRS17; **not** iec SPA. Historical compare prefers that durable wall when present (else guest created/updated clocks) and persists it on the job record for priors across restart. Job-detail **Handoff docs** panel is operator clarity only. Live and `--dry-run` emit a small `pack_fill.fragment` the operator can paste into the off-box iec-parity pack (`tips.panoramix_runtime_tip` / `tips.guest_tip` when known from checkout / env / documented tip; optional `durable.wall_elapsed_ms.panoramix` / `durable.stage_elapsed_ms.panoramix` **only** when measured from the hooked run). Assist for runtime [#78](https://github.com/guypayeur/panoramix-runtime/issues/78) **D** fill checklist only — does **not** write the full live pack, does **not** stamp #70 UX Done / `north_star_done`. Documented runtime tip [`411aa68`](https://github.com/guypayeur/panoramix-runtime/commit/411aa68bd1dd9c8a11d4ec98b3570acb5b90b4d9) ([PR #118](https://github.com/guypayeur/panoramix-runtime/pull/118) checklist era, or **main**); wall feature tip remains `9b6646e8`. Does **not** close runtime [#70](https://github.com/guypayeur/panoramix-runtime/issues/70) / [#78](https://github.com/guypayeur/panoramix-runtime/issues/78). Does **not** unlock [#61](https://github.com/guypayeur/panoramix-runtime/issues/61) / [#29](https://github.com/guypayeur/panoramix-runtime/issues/29). `north_star_done` stays false. Default hook stays inert. Journey rows stay **match (thinner)** — this page does **not** stamp the #70 UX Done-when boxes.

## What it starts

1. `python3 -m runtime.serve --binding bindings/local-reserve-temporal.example.yaml` from a [panoramix-runtime](https://github.com/guypayeur/panoramix-runtime) checkout (**main** @ `fb901542`, PR #100; optional durable `stages[].elapsed_ms` from tip `9ba95bbb` / docs tip `5dc191cb` / PR #110 / PR #112 / **main** — omit when missing; optional durable `wall_elapsed_ms` / `started_at` from tip `9b6646e8` / PR #114 / **main** / docs tip `6511cec7` / PR #116 — omit when missing). Binding `publish.ctl_port` is **19215**.
2. This guest: `PLATFORM_LISTEN_HTTP=18280` and `PANORAMIX_CTL_HTTP=http://127.0.0.1:19215` (loopback only; off-loopback fails closed).
3. `POST /v0/jobs` with `{"demo":"reserve","catalog":"recorded"}`.
4. Show `local.backed=runtime`, durable `GET /progress` / `GET /events`, and `pause_resume`. Path-slice `elapsed_ms` only when the hook/progress supplies it (tip `9ba95bbb` / docs tip `5dc191cb` / main) or durable event timestamps subtract honestly — **omit when missing; never invent**. Durable `wall_elapsed_ms` / `started_at` only when the hook/progress supplies it (tip `9b6646e8` / PR #114 / main; docs tip `6511cec7` / PR #116) — **omit when missing; never invent**; not a forecast; not IFRS17; not iec SPA. `GET /v0/jobs/{id}/compare` prefers that durable wall when present (persisted for priors across restart); else guest created/updated clocks. Job detail **Handoff docs** panel is operator clarity, not a second control plane.
5. `POST /v0/jobs/{id}/cancel` (or wait for fail), then one-click `POST /v0/jobs/{id}/re-admit` and show a **new** job id (`local.re_admit_from` = the canceled/failed id). Not resume-from-failed.
6. Tear down both processes.

CI uses `--dry-run` (plan JSON plus in-process re-admit smokes: hooked new job id, inert / payload-unknown **409** `re_admit_unavailable`). Plan also records `timeline_elapsed` (runtime tip `9ba95bbb` / docs tip `5dc191cb` / main; `omit_when_missing: true`; `invent: false`), `wall_elapsed` (runtime tip `9b6646e8` / PR #114 / main; docs tip `6511cec7` / PR #116; `omit_when_missing: true`; `invent: false`; compare prefers when present), `handoff_docs` (panel; not a second control plane), and `pack_fill` (paste fragment for runtime #78 D; documented runtime tip `411aa68` / PR #118 / main; wall feature tip remains `9b6646e8`; `omit_when_missing: true`; `invent: false`; `writes_live_pack: false`; durable omitted on dry-run because nothing was measured). No live Temporal is required for unit tests. Fail-closed without hook or payload — **no silent stub**.

## Commands

```bash
# Plan + in-process re-admit smokes (no processes, no Temporal):
python3 scripts/lab_compose_reserve_temporal.py --dry-run

# Live one-shot (operator lab; needs a runtime checkout + serve):
export PANORAMIX_RUNTIME_ROOT=/path/to/panoramix-runtime
python3 scripts/lab_compose_reserve_temporal.py
```

Equivalent manual steps (same honesty):

```bash
# terminal 1 — runtime (already serving):
cd /path/to/panoramix-runtime
python3 -m runtime.serve --binding bindings/local-reserve-temporal.example.yaml

# terminal 2 — guest:
export PANORAMIX_CTL_HTTP=http://127.0.0.1:19215
export PLATFORM_LISTEN_HTTP=18280
python3 ./platform_run.py

# terminal 3 — recorded reserve, then cancel + one-click re-admit:
JOB=$(curl -sS -X POST http://127.0.0.1:18280/v0/jobs \
  -H 'Content-Type: application/json' \
  -d '{"demo":"reserve","catalog":"recorded"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
curl -sS -X POST http://127.0.0.1:18280/v0/jobs/$JOB/cancel
curl -sS -X POST http://127.0.0.1:18280/v0/jobs/$JOB/re-admit
```

Without `PANORAMIX_CTL_HTTP` the guest stays stub (`local.backed=stub`, pause **409** `stub_only`). One-click re-admit is **409** `re_admit_unavailable` (`hook_inert`). Missing handoff/payload is **409** `re_admit_unavailable` (`payload_unknown`). That is fail-closed — **no silent stub re-admit**, not resume-from-failed, not a pretend durable path.

When the env is set to a valid loopback origin but `runtime.serve` is down (connection refused / timeout), admit/status/progress fail closed with **`ctl_http_unreachable`** (lab-serve down) — not a hung poll, not pretend durable. Start serve or unset the env. Not #70 Done.

Optional `PANORAMIX_CTL_HTTP_BEARER` when the binding has `ctl.require`.

Optional `PANORAMIX_RUNTIME_TIP` / `PANORAMIX_GUEST_TIP` override documented pins when a checkout SHA is not readable. Checkout HEAD still wins.

### Off-box pack fill (`pack_fill.fragment`)

`--dry-run` and the live report include `pack_fill.fragment`: a small JSON object to paste under `tips` / optional `durable` in `~/panoramix-lab/evidence-70/iec-parity/` (runtime [live-pack.schema.json](https://github.com/guypayeur/panoramix-runtime/blob/411aa68bd1dd9c8a11d4ec98b3570acb5b90b4d9/proofs/fixtures/iec-parity/live-pack.schema.json) after [PR #118](https://github.com/guypayeur/panoramix-runtime/pull/118)). Example when only tips are known (dry-run; durable omitted):

```json
{
  "tips": {
    "panoramix_runtime_tip": "411aa68bd1dd9c8a11d4ec98b3570acb5b90b4d9",
    "guest_tip": "4e2251c7d8374dbec408e0febb0a33f4c00f33c2"
  }
}
```

`durable.wall_elapsed_ms.panoramix` / `durable.stage_elapsed_ms.panoramix` appear **only** when the hooked run's durable progress actually supplied those measurements. **Omit when missing; never invent.** Fail-closed without a durable hook. This is **not** a forecast, **not** IFRS17, **not** iec SPA, and does **not** write the full live pack (operator / runtime assist owns schema validation). Not #70 Done.

## UI

Operator UI (`GET /`) reads `GET /v0/info` → `jobs.durable_hook`. A badge says the durable path is active **only** when the HTTP adapter is hooked (`kind: ctl_http`). Inert stub copy stays honest (no pretend).

Job detail shows a compact **Handoff docs** panel (handoff + payload export, recoverability / re-admit, this page) — operator clarity, **not** a second control plane.

Optional path-slice `elapsed_ms` appears when durable progress supplies it (runtime tip `9ba95bbb` / docs tip [`5dc191cb`](https://github.com/guypayeur/panoramix-runtime/commit/5dc191cbfb103147c2b9c32a6be3f5b97732994d) / [PR #110](https://github.com/guypayeur/panoramix-runtime/pull/110) / [PR #112](https://github.com/guypayeur/panoramix-runtime/pull/112) / **main**) or durable event timestamps can be subtracted honestly. Optional durable `wall_elapsed_ms` / `started_at` appears when durable progress/status supplies it (runtime tip [`9b6646e8`](https://github.com/guypayeur/panoramix-runtime/commit/9b6646e8829056c22339842321986afaf7d6b957) / [PR #114](https://github.com/guypayeur/panoramix-runtime/pull/114) / **main**; docs tip [`6511cec7`](https://github.com/guypayeur/panoramix-runtime/commit/6511cec7) / [PR #116](https://github.com/guypayeur/panoramix-runtime/pull/116)). Historical compare prefers that wall when present. **Omit when missing; never invent.** Durable wall is **not** a forecast, **not** IFRS17, **not** iec SPA. Serve pin `fb901542` remains valid for compose; elapsed / wall stay omitted on older tips without those fields. Not #70 Done.

## Not this page

- Guest→mesh ctl
- IFRS17 math / comparable perf
- Claiming #70 UX Done or `north_star_done`
- Cloud unlock (#61 / #29)
- Closing runtime #70 / #78
- Writing the full off-box iec-parity live pack (assist / paste fragment only)
- Inventing wall / stage elapsed for `#78` D
- Resume-from-failed / silent stub re-admit
