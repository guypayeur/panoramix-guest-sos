# Lab compose: one-shot Temporal-backed reserve path

One-shot local lab so an operator can start **runtime.serve** (ctl **19215**) and this guest with `PANORAMIX_CTL_HTTP`, POST a recorded reserve demo, and see `local.backed=runtime` plus durable progress / events / `pause_resume`, then **admit → cancel/fail → one-click `POST /v0/jobs/{id}/re-admit` → new job id** when the durable hook is active (`PANORAMIX_CTL_HTTP` preferred or `PANORAMIX_RUNTIME_ROOT`).

WSL stamps already exist at operator lab `~/panoramix-lab/evidence-70/stamp-71fb4c9-ctl-http/`, `~/panoramix-lab/evidence-70/stamp-9b6646e8-wall-elapsed/` (recorded+STRICT exit 0; wall probe OK), `~/panoramix-lab/evidence-70/stamp-b81130f-iec-parity-pack/` (assist smoke named by runtime docs tip [`63a168d`](https://github.com/guypayeur/panoramix-runtime/commit/63a168d55dd00b19bfdc5fb914247117744238b7) / [PR #122](https://github.com/guypayeur/panoramix-runtime/pull/122); assist ≠ fill), `~/panoramix-lab/evidence-70/stamp-84cb202-iec-parity-gap-report/` (gap-report smoke named by runtime tip [`84cb202`](https://github.com/guypayeur/panoramix-runtime/commit/84cb202f9795b5e8759cdc2757c55d91f273de87) / [PR #124](https://github.com/guypayeur/panoramix-runtime/pull/124); gap-report ≠ Done; assist ≠ fill), `~/panoramix-lab/evidence-70/stamp-5086d0f-iec-parity-merge/` (merge assist smoke named by runtime tip [`5086d0f`](https://github.com/guypayeur/panoramix-runtime/commit/5086d0fe8ff260a4ca9db9098db562dcc05b04b2) / [PR #128](https://github.com/guypayeur/panoramix-runtime/pull/128); docs stamp [`6ecb645`](https://github.com/guypayeur/panoramix-runtime/commit/6ecb6453934a0a6fda5fc06c3b37d5b9b088b97f) / [PR #130](https://github.com/guypayeur/panoramix-runtime/pull/130) or **main**; merge ≠ fill; merge ≠ Done; assist ≠ Done), and `~/panoramix-lab/evidence-70/stamp-5d399f7-iec-parity-apply-metrics/` (apply-metrics assist smoke named by runtime tip [`5d399f7`](https://github.com/guypayeur/panoramix-runtime/commit/5d399f765180c7d729ba1a6853ad7833d974acc4) / [PR #132](https://github.com/guypayeur/panoramix-runtime/pull/132) or **main**; docs stamp [`3904ee4`](https://github.com/guypayeur/panoramix-runtime/commit/3904ee483b6d28b929dc45fc7f124fad8bf4f65c) / [PR #134](https://github.com/guypayeur/panoramix-runtime/pull/134) or **main**; apply-metrics ≠ fill; apply-metrics ≠ Done; assist ≠ Done; assist smoke ≠ fill; smoke walls ≠ Done) — this page does **not** reproduce those packs.

**Honesty:** fail-closed without env. Not guest→mesh ctl. Not a second control plane. Not SIEM. Not IFRS17. Pin **0.5**. WorkHandoff triple only. Path-slice elapsed omitted when timestamps missing (never invent). Optional durable `stages[].elapsed_ms` can come from runtime tip [`9ba95bbb`](https://github.com/guypayeur/panoramix-runtime/commit/9ba95bbb4fa4c9046abee6eac60158e4fd649b90) / docs tip [`5dc191cb`](https://github.com/guypayeur/panoramix-runtime/commit/5dc191cbfb103147c2b9c32a6be3f5b97732994d) (or **main**, [PR #110](https://github.com/guypayeur/panoramix-runtime/pull/110) / [PR #112](https://github.com/guypayeur/panoramix-runtime/pull/112)) — omit when missing; never invent. Optional durable `wall_elapsed_ms` / `started_at` can come from runtime tip [`9b6646e8`](https://github.com/guypayeur/panoramix-runtime/commit/9b6646e8829056c22339842321986afaf7d6b957) (or **main**, [PR #114](https://github.com/guypayeur/panoramix-runtime/pull/114); docs tip [`6511cec7`](https://github.com/guypayeur/panoramix-runtime/commit/6511cec7) / [PR #116](https://github.com/guypayeur/panoramix-runtime/pull/116) for evidence-index lineage) — omit when missing; never invent; **not** a forecast; **not** IFRS17; **not** iec SPA. Historical compare prefers that durable wall when present (else guest created/updated clocks) and persists it on the job record for priors across restart. Job-detail **Handoff docs** panel is operator clarity only. Live and `--dry-run` emit a small `pack_fill.fragment` the operator can paste into the off-box iec-parity pack (`tips.panoramix_runtime_tip` / `tips.guest_tip` when known from checkout / env / documented tip; optional `durable.wall_elapsed_ms.panoramix` / `durable.stage_elapsed_ms.panoramix` **only** when measured from the hooked run). The same fragment can feed optional tips / measured durable into `python3 -m runtime.iec_parity_pack skeleton` via `--from-json` (file or stdin) or flags — **measured durable only; omit when missing**. Never invent `metrics.wall_time_sec`. assist ≠ fill; assist ≠ Done. Assist for runtime [#78](https://github.com/guypayeur/panoramix-runtime/issues/78) **D** fill checklist only — does **not** write the full live pack, does **not** stamp #70 UX Done / `north_star_done`. Documented runtime tip [`b81130f`](https://github.com/guypayeur/panoramix-runtime/commit/b81130f2187109eabc2342df6345ca877e98023f) ([PR #120](https://github.com/guypayeur/panoramix-runtime/pull/120) `skeleton|validate`, or **main**); docs tip [`63a168d`](https://github.com/guypayeur/panoramix-runtime/commit/63a168d55dd00b19bfdc5fb914247117744238b7) ([PR #122](https://github.com/guypayeur/panoramix-runtime/pull/122) WSL assist-smoke stamp lineage); gap-report tip [`84cb202`](https://github.com/guypayeur/panoramix-runtime/commit/84cb202f9795b5e8759cdc2757c55d91f273de87) ([PR #124](https://github.com/guypayeur/panoramix-runtime/pull/124) gap-report); gap-report docs tip [`aa4f09e`](https://github.com/guypayeur/panoramix-runtime/commit/aa4f09e89569e98681e7385adcfecda014723019) ([PR #126](https://github.com/guypayeur/panoramix-runtime/pull/126) stamp link, or **main**); merge tip [`5086d0f`](https://github.com/guypayeur/panoramix-runtime/commit/5086d0fe8ff260a4ca9db9098db562dcc05b04b2) ([PR #128](https://github.com/guypayeur/panoramix-runtime/pull/128) `iec_parity_pack merge`, or **main**); merge docs tip [`6ecb645`](https://github.com/guypayeur/panoramix-runtime/commit/6ecb6453934a0a6fda5fc06c3b37d5b9b088b97f) ([PR #130](https://github.com/guypayeur/panoramix-runtime/pull/130) stamp link, or **main**); apply-metrics tip [`5d399f7`](https://github.com/guypayeur/panoramix-runtime/commit/5d399f765180c7d729ba1a6853ad7833d974acc4) ([PR #132](https://github.com/guypayeur/panoramix-runtime/pull/132) `iec_parity_pack apply-metrics`, or **main**); apply-metrics docs tip [`3904ee4`](https://github.com/guypayeur/panoramix-runtime/commit/3904ee483b6d28b929dc45fc7f124fad8bf4f65c) ([PR #134](https://github.com/guypayeur/panoramix-runtime/pull/134) stamp link, or **main**); guest emit tip [`b859466`](https://github.com/guypayeur/panoramix-guest-sos/commit/b859466dcd079eb063b615728b258a686f79749a) ([PR #52](https://github.com/guypayeur/panoramix-guest-sos/pull/52)); guest gap-report tip [`eb48605`](https://github.com/guypayeur/panoramix-guest-sos/commit/eb48605ab85edae54b748446070834ff67f97403) ([PR #60](https://github.com/guypayeur/panoramix-guest-sos/pull/60)); guest merge tip [`39064d5`](https://github.com/guypayeur/panoramix-guest-sos/commit/39064d5) ([PR #64](https://github.com/guypayeur/panoramix-guest-sos/pull/64)); schema / checklist era remains [PR #118](https://github.com/guypayeur/panoramix-runtime/pull/118); wall feature tip remains `9b6646e8`. Live and `--dry-run` also record `pack_fill.apply_metrics` — the exact `python3 -m runtime.iec_parity_pack apply-metrics … --from-durable-panoramix` command (cd+cmd when `PANORAMIX_RUNTIME_ROOT` is known, else a copy-paste template; does **not** supply wall numbers) — then `pack_fill.merge` for `merge … --from-json` and `pack_fill.gap_report` for `gap-report` against that pack. Hint only; does **not** run apply-metrics, merge, or gap-report. apply-metrics + merge + gap-report pairing. **apply-metrics ≠ fill; apply-metrics ≠ Done; assist ≠ Done; merge ≠ fill; merge ≠ Done; gap-report ≠ Done.** Does **not** close runtime [#70](https://github.com/guypayeur/panoramix-runtime/issues/70) / [#78](https://github.com/guypayeur/panoramix-runtime/issues/78). Does **not** unlock [#61](https://github.com/guypayeur/panoramix-runtime/issues/61) / [#29](https://github.com/guypayeur/panoramix-runtime/issues/29). `north_star_done` stays false. Default hook stays inert. Journey rows stay **match (thinner)** — this page does **not** stamp the #70 UX Done-when boxes.

## What it starts

1. `python3 -m runtime.serve --binding bindings/local-reserve-temporal.example.yaml` from a [panoramix-runtime](https://github.com/guypayeur/panoramix-runtime) checkout (**main** @ `fb901542`, PR #100; optional durable `stages[].elapsed_ms` from tip `9ba95bbb` / docs tip `5dc191cb` / PR #110 / PR #112 / **main** — omit when missing; optional durable `wall_elapsed_ms` / `started_at` from tip `9b6646e8` / PR #114 / **main** / docs tip `6511cec7` / PR #116 — omit when missing). Binding `publish.ctl_port` is **19215**.
2. This guest: `PLATFORM_LISTEN_HTTP=18280` and `PANORAMIX_CTL_HTTP=http://127.0.0.1:19215` (loopback only; off-loopback fails closed).
3. `POST /v0/jobs` with `{"demo":"reserve","catalog":"recorded"}`.
4. Show `local.backed=runtime`, durable `GET /progress` / `GET /events`, and `pause_resume`. Path-slice `elapsed_ms` only when the hook/progress supplies it (tip `9ba95bbb` / docs tip `5dc191cb` / main) or durable event timestamps subtract honestly — **omit when missing; never invent**. Durable `wall_elapsed_ms` / `started_at` only when the hook/progress supplies it (tip `9b6646e8` / PR #114 / main; docs tip `6511cec7` / PR #116) — **omit when missing; never invent**; not a forecast; not IFRS17; not iec SPA. `GET /v0/jobs/{id}/compare` prefers that durable wall when present (persisted for priors across restart); else guest created/updated clocks. Job detail **Handoff docs** panel is operator clarity, not a second control plane.
5. `POST /v0/jobs/{id}/cancel` (or wait for fail), then one-click `POST /v0/jobs/{id}/re-admit` and show a **new** job id (`local.re_admit_from` = the canceled/failed id). Not resume-from-failed.
6. Tear down both processes.

CI uses `--dry-run` (plan JSON plus in-process re-admit smokes: hooked new job id, inert / payload-unknown **409** `re_admit_unavailable`). Plan also records `timeline_elapsed` (runtime tip `9ba95bbb` / docs tip `5dc191cb` / main; `omit_when_missing: true`; `invent: false`), `wall_elapsed` (runtime tip `9b6646e8` / PR #114 / main; docs tip `6511cec7` / PR #116; `omit_when_missing: true`; `invent: false`; compare prefers when present), `handoff_docs` (panel; not a second control plane), and `pack_fill` (paste fragment for runtime #78 D; documented runtime tip `b81130f` / PR #120 / main; docs tip `63a168d` / PR #122 WSL assist-smoke stamp lineage; gap-report tip `84cb202` / PR #124; gap-report docs tip `aa4f09e` / PR #126 / main; merge tip `5086d0f` / PR #128 / main; merge docs tip `6ecb645` / PR #130 / main; apply-metrics tip `5d399f7` / PR #132 / main; apply-metrics docs tip `3904ee4` / PR #134 / main; guest emit tip `b859466` / PR #52; guest gap-report tip `eb48605` / PR #60; guest merge tip `39064d5` / PR #64; emit → `runtime.iec_parity_pack skeleton` via `--from-json` / flags; `pack_fill.apply_metrics` hint for `runtime.iec_parity_pack apply-metrics … --from-durable-panoramix` (does **not** supply wall numbers); `pack_fill.merge` hint for `runtime.iec_parity_pack merge … --from-json`; `pack_fill.gap_report` hint for `gap-report` — cd+cmd when `PANORAMIX_RUNTIME_ROOT` known, else a copy-paste template; does **not** run apply-metrics, merge, or gap-report; wall feature tip remains `9b6646e8`; `omit_when_missing: true`; `invent: false`; `invent_wall_time_sec: false`; `writes_live_pack: false`; assist ≠ fill; apply-metrics ≠ fill; apply-metrics ≠ Done; merge ≠ fill; merge ≠ Done; assist ≠ Done; gap-report ≠ Done; durable omitted on dry-run because nothing was measured). No live Temporal is required for unit tests. Fail-closed without hook or payload — **no silent stub**.

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

`--dry-run` and the live report include `pack_fill.fragment`: a small JSON object to paste under `tips` / optional `durable` in `~/panoramix-lab/evidence-70/iec-parity/` (runtime [live-pack.schema.json](https://github.com/guypayeur/panoramix-runtime/blob/b81130f2187109eabc2342df6345ca877e98023f/proofs/fixtures/iec-parity/live-pack.schema.json) after [PR #120](https://github.com/guypayeur/panoramix-runtime/pull/120); schema era [PR #118](https://github.com/guypayeur/panoramix-runtime/pull/118); docs tip [`63a168d`](https://github.com/guypayeur/panoramix-runtime/commit/63a168d55dd00b19bfdc5fb914247117744238b7) / [PR #122](https://github.com/guypayeur/panoramix-runtime/pull/122) names the WSL assist-smoke stamp lineage; gap-report tip [`84cb202`](https://github.com/guypayeur/panoramix-runtime/commit/84cb202f9795b5e8759cdc2757c55d91f273de87) / [PR #124](https://github.com/guypayeur/panoramix-runtime/pull/124) names the WSL gap-report stamp lineage). Example when only tips are known (dry-run; durable omitted):

```json
{
  "tips": {
    "panoramix_runtime_tip": "b81130f2187109eabc2342df6345ca877e98023f",
    "guest_tip": "b859466dcd079eb063b615728b258a686f79749a"
  }
}
```

`durable.wall_elapsed_ms.panoramix` / `durable.stage_elapsed_ms.panoramix` appear **only** when the hooked run's durable progress actually supplied those measurements. **Omit when missing; never invent.** Fail-closed without a durable hook.

#### Emit → `runtime.iec_parity_pack skeleton`

Guest emit (this fragment) can feed optional tips / measured durable into runtime tip [`b81130f`](https://github.com/guypayeur/panoramix-runtime/commit/b81130f2187109eabc2342df6345ca877e98023f) (`python3 -m runtime.iec_parity_pack skeleton|validate`, [PR #120](https://github.com/guypayeur/panoramix-runtime/pull/120); docs tip [`63a168d`](https://github.com/guypayeur/panoramix-runtime/commit/63a168d55dd00b19bfdc5fb914247117744238b7) / [PR #122](https://github.com/guypayeur/panoramix-runtime/pull/122) for the WSL assist-smoke stamp lineage; gap-report tip [`84cb202`](https://github.com/guypayeur/panoramix-runtime/commit/84cb202f9795b5e8759cdc2757c55d91f273de87) / [PR #124](https://github.com/guypayeur/panoramix-runtime/pull/124); wall feature tip remains `9b6646e8`):

```bash
# Plan JSON includes pack_fill.fragment (durable omitted on --dry-run):
python3 scripts/lab_compose_reserve_temporal.py --dry-run > /tmp/lab-compose.json

# Feed the fragment (tips / optional measured durable only):
python3 -c 'import json,sys; json.dump(json.load(sys.stdin)["pack_fill"]["fragment"], sys.stdout)' \
  < /tmp/lab-compose.json \
  | python3 -m runtime.iec_parity_pack skeleton --from-json -

# Same pairing via flags (omit durable flags when missing; never invent):
python3 -m runtime.iec_parity_pack skeleton \
  --panoramix-runtime-tip b81130f2187109eabc2342df6345ca877e98023f \
  --guest-tip b859466dcd079eb063b615728b258a686f79749a
# add --durable-wall-elapsed-ms-panoramix / --durable-stage-elapsed-ms-panoramix
# only when the hooked run measured them
```

`--from-json` accepts a file path or `-` (stdin). Fragment keys stay `tips` / optional `durable` — the same shape skeleton already admits. **Never invent `metrics.wall_time_sec`.** Skeleton refuses `--invent` / `--wall-time-sec`. **assist ≠ fill; assist ≠ Done.** Does **not** stamp `north_star_done`. WSL stamp `~/panoramix-lab/evidence-70/stamp-b81130f-iec-parity-pack/` is assist smoke only (named by runtime docs tip `63a168d` / [PR #122](https://github.com/guypayeur/panoramix-runtime/pull/122); assist tip remains `b81130f` / [PR #120](https://github.com/guypayeur/panoramix-runtime/pull/120); wall tip remains `9b6646e8`). WSL stamp `~/panoramix-lab/evidence-70/stamp-84cb202-iec-parity-gap-report/` is gap-report smoke only (named by runtime tip `84cb202` / [PR #124](https://github.com/guypayeur/panoramix-runtime/pull/124); docs stamp [`aa4f09e`](https://github.com/guypayeur/panoramix-runtime/commit/aa4f09e89569e98681e7385adcfecda014723019) / [PR #126](https://github.com/guypayeur/panoramix-runtime/pull/126) or **main**; docs tip remains `63a168d` / [PR #122](https://github.com/guypayeur/panoramix-runtime/pull/122); assist tip remains `b81130f` / [PR #120](https://github.com/guypayeur/panoramix-runtime/pull/120); wall tip remains `9b6646e8`); **gap-report ≠ Done**; **assist ≠ fill**; #78 D still unfilled. WSL stamp `~/panoramix-lab/evidence-70/stamp-5086d0f-iec-parity-merge/` is merge assist smoke only (named by runtime tip `5086d0f` / [PR #128](https://github.com/guypayeur/panoramix-runtime/pull/128) or **main**; docs stamp [`6ecb645`](https://github.com/guypayeur/panoramix-runtime/commit/6ecb6453934a0a6fda5fc06c3b37d5b9b088b97f) / [PR #130](https://github.com/guypayeur/panoramix-runtime/pull/130) or **main**; gap-report tip remains `84cb202`; wall tip remains `9b6646e8`); **merge ≠ fill; merge ≠ Done; assist ≠ Done**. WSL stamp `~/panoramix-lab/evidence-70/stamp-5d399f7-iec-parity-apply-metrics/` is apply-metrics assist smoke only (named by runtime tip `5d399f7` / [PR #132](https://github.com/guypayeur/panoramix-runtime/pull/132) or **main**; docs stamp [`3904ee4`](https://github.com/guypayeur/panoramix-runtime/commit/3904ee483b6d28b929dc45fc7f124fad8bf4f65c) / [PR #134](https://github.com/guypayeur/panoramix-runtime/pull/134) or **main**; merge tip remains `5086d0f`; gap-report tip remains `84cb202`; wall tip remains `9b6646e8`); **apply-metrics ≠ fill; apply-metrics ≠ Done; assist ≠ Done**; assist smoke ≠ fill; smoke walls ≠ Done.

#### Apply-metrics + merge + gap-report

`--dry-run` and the live report include `pack_fill.merge` with the exact `python3 -m runtime.iec_parity_pack merge … --from-json` command, `pack_fill.apply_metrics` for `apply-metrics … --from-durable-panoramix` (does **not** supply wall numbers), then `pack_fill.gap_report` for gap-report against that pack. This is the apply-metrics + merge + gap-report pairing (merge+gap-report remains). When `PANORAMIX_RUNTIME_ROOT` is known the hint is cd+cmd; otherwise a copy-paste template:

```bash
# Plan JSON includes pack_fill.fragment (durable omitted on --dry-run):
python3 scripts/lab_compose_reserve_temporal.py --dry-run > /tmp/lab-compose.json

# Template (no PANORAMIX_RUNTIME_ROOT):
cd /path/to/panoramix-runtime
python3 -c 'import json,sys; json.dump(json.load(sys.stdin)["pack_fill"]["fragment"], sys.stdout)' \
  < /tmp/lab-compose.json \
  | python3 -m runtime.iec_parity_pack merge ~/panoramix-lab/evidence-70/iec-parity/iec-parity.json --from-json -

python3 -m runtime.iec_parity_pack apply-metrics ~/panoramix-lab/evidence-70/iec-parity/iec-parity.json --from-durable-panoramix

python3 -m runtime.iec_parity_pack gap-report ~/panoramix-lab/evidence-70/iec-parity/iec-parity.json

# When PANORAMIX_RUNTIME_ROOT is known, pack_fill.merge.hint is:
# cd $PANORAMIX_RUNTIME_ROOT && python3 -m runtime.iec_parity_pack merge \
#   ~/panoramix-lab/evidence-70/iec-parity/iec-parity.json --from-json -
# pack_fill.apply_metrics.hint is:
# cd $PANORAMIX_RUNTIME_ROOT && python3 -m runtime.iec_parity_pack apply-metrics \
#   ~/panoramix-lab/evidence-70/iec-parity/iec-parity.json --from-durable-panoramix
# pack_fill.gap_report.hint is:
# cd $PANORAMIX_RUNTIME_ROOT && python3 -m runtime.iec_parity_pack gap-report \
#   ~/panoramix-lab/evidence-70/iec-parity/iec-parity.json
```

**apply-metrics ≠ fill; apply-metrics ≠ Done; assist ≠ Done; merge ≠ fill; merge ≠ Done; gap-report ≠ Done.** The hints do **not** run apply-metrics, merge, or gap-report (CI `--dry-run` stays recorded; no live pack required). The apply-metrics hint does **not** supply wall numbers. Null walls stay null. Does **not** invent `metrics.wall_time_sec`. Does **not** stamp `north_star_done`. Apply-metrics tip `5d399f7` / [PR #132](https://github.com/guypayeur/panoramix-runtime/pull/132) or **main**; apply-metrics docs stamp `3904ee4` / [PR #134](https://github.com/guypayeur/panoramix-runtime/pull/134) or **main**; merge tip `5086d0f` / [PR #128](https://github.com/guypayeur/panoramix-runtime/pull/128) or **main**; merge docs stamp `6ecb645` / [PR #130](https://github.com/guypayeur/panoramix-runtime/pull/130) or **main**; gap-report tip remains `84cb202` / [PR #124](https://github.com/guypayeur/panoramix-runtime/pull/124); docs stamp `aa4f09e` / [PR #126](https://github.com/guypayeur/panoramix-runtime/pull/126) or **main**; wall tip remains `9b6646e8`. WSL stamp `~/panoramix-lab/evidence-70/stamp-5086d0f-iec-parity-merge/` is assist smoke only (assist ≠ fill). WSL stamp `~/panoramix-lab/evidence-70/stamp-5d399f7-iec-parity-apply-metrics/` is assist smoke only (assist smoke ≠ fill; smoke walls ≠ Done).

This is **not** a forecast, **not** IFRS17, **not** iec SPA, and does **not** write the full live pack (operator / runtime assist owns schema validation). Not #70 Done.

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
- Inventing wall / stage elapsed or `metrics.wall_time_sec` for `#78` D
- Claiming `runtime.iec_parity_pack skeleton` is a fill / `north_star_done`
- Claiming `runtime.iec_parity_pack gap-report` is a fill / Done
- Claiming `runtime.iec_parity_pack merge` is a fill / Done
- Claiming `runtime.iec_parity_pack apply-metrics` is a fill / Done
- Resume-from-failed / silent stub re-admit
