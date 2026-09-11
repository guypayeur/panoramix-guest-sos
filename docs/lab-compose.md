# Lab compose: one-shot Temporal-backed reserve path

One-shot local lab so an operator can start **runtime.serve** (ctl **19215**) and this guest with `PANORAMIX_CTL_HTTP`, POST a recorded reserve demo, and see `local.backed=runtime` plus durable progress / events / `pause_resume`.

WSL stamp already exists at operator lab `~/panoramix-lab/evidence-70/stamp-71fb4c9-ctl-http/` — this page does **not** reproduce that pack.

**Honesty:** fail-closed without env. Not guest→mesh ctl. Not a second control plane. Not SIEM. Not IFRS17. Pin **0.5**. WorkHandoff triple only. Does **not** close runtime [#70](https://github.com/guypayeur/panoramix-runtime/issues/70) / [#78](https://github.com/guypayeur/panoramix-runtime/issues/78). Does **not** unlock [#61](https://github.com/guypayeur/panoramix-runtime/issues/61) / [#29](https://github.com/guypayeur/panoramix-runtime/issues/29). `north_star_done` stays false. Default hook stays inert. Journey rows stay **match (thinner)** — this page does **not** stamp the #70 UX Done-when boxes.

## What it starts

1. `python3 -m runtime.serve --binding bindings/local-reserve-temporal.example.yaml` from a [panoramix-runtime](https://github.com/guypayeur/panoramix-runtime) checkout (**main** @ `fb901542`, PR #100). Binding `publish.ctl_port` is **19215**.
2. This guest: `PLATFORM_LISTEN_HTTP=18280` and `PANORAMIX_CTL_HTTP=http://127.0.0.1:19215` (loopback only; off-loopback fails closed).
3. `POST /v0/jobs` with `{"demo":"reserve","catalog":"recorded"}`.
4. Show `local.backed=runtime`, durable `GET /progress` / `GET /events`, and `pause_resume`.
5. Tear down both processes.

CI uses `--dry-run` (plan JSON only). No live Temporal is required for unit tests.

## Commands

```bash
# Plan only (no processes, no Temporal):
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

# terminal 3 — recorded reserve:
curl -sS -X POST http://127.0.0.1:18280/v0/jobs \
  -H 'Content-Type: application/json' \
  -d '{"demo":"reserve","catalog":"recorded"}'
```

Without `PANORAMIX_CTL_HTTP` the guest stays stub (`local.backed=stub`, pause **409** `stub_only`). That is fail-closed, not a pretend durable path.

Optional `PANORAMIX_CTL_HTTP_BEARER` when the binding has `ctl.require`.

## UI

Operator UI (`GET /`) reads `GET /v0/info` → `jobs.durable_hook`. A badge says the durable path is active **only** when the HTTP adapter is hooked (`kind: ctl_http`). Inert stub copy stays honest (no pretend).

## Not this page

- Guest→mesh ctl
- IFRS17 math / comparable perf
- Claiming #70 UX Done or `north_star_done`
- Cloud unlock (#61 / #29)
- Closing runtime #70 / #78
