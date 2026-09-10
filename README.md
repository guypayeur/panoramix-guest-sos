# panoramix-guest-sos

Day-one **SoS** (actuarial) guest for [Panoramix](https://github.com/guypayeur/panoramix).

Pin **0.5**. This repository is opaque domain code plus a platform Unit contract. Compute engines live in [panoramix-runtime](https://github.com/guypayeur/panoramix-runtime) bindings — see [runtime#70](https://github.com/guypayeur/panoramix-runtime/issues/70).

## What this is

- A greenfield Panoramix **0.5** guest: Unit `sos`, public HTTP on **18280**, probes at `/health`.
- A **day-one operator path**: submit a demo job, watch status, cancel. In-process stub runner only — no Ray, Temporal, GPU, or cloud engines in this tree.
- Stdlib Python 3.12 (`platform_run.py` + `sos/`). Thin entrypoint imports domain the same way [httpbin](https://github.com/guypayeur/panoramix-guest-httpbin) `platform_run.py` imports `httpbin.core.app`.
- A minimal operator UI at `GET /` (also `GET /ui`) that polls the JSON API.

## What this is not

- **Not** a lift of [iec-proto-c](https://github.com/guypayeur/iec-proto-c). This tree does not vend iec code, L1–L2 layers, ADSL/compiler, or claim feature/UX/perf equivalence.
- **Not** a place for `image:`, `ray:`, `temporal:`, or `aws:` fields on Unit/System YAML. Pin stays **0.5**.
- **Not** engine management. Ray / Temporal / GPU / AWS stay in runtime bindings ([runtime#70](https://github.com/guypayeur/panoramix-runtime/issues/70)).
- **Not** cloud-first. Local lab before AWS. Do not set `PLATFORM_RAY_*` (or any engine URL) here.

## North star (documented only)

Day-one **is thinner** than iec-proto-c. The Done-when north star — owned with the runtime compute plane — is:

- **UX:** a representative SoS operator/actuary path that **matches or beats** the corresponding iec-proto-c experience.
- **Performance:** an agreed local workload class on the **same** host **matches or beats** that iec baseline.

Those boxes live on [panoramix-runtime#70](https://github.com/guypayeur/panoramix-runtime/issues/70). This guest does **not** check them.

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

### Demo job lifecycle (curl)

Echo (queued → running → succeeded on a short local thread):

```bash
curl -sS -X POST http://127.0.0.1:18280/v0/jobs \
  -H 'Content-Type: application/json' \
  -d '{"kind":"sos.demo.echo","spec":{"message":"hello"}}'

curl -sS http://127.0.0.1:18280/v0/jobs
curl -sS http://127.0.0.1:18280/v0/jobs/<id>
```

Sleep, then cancel while queued/running:

```bash
ID=$(curl -sS -X POST http://127.0.0.1:18280/v0/jobs \
  -H 'Content-Type: application/json' \
  -d '{"kind":"sos.demo.sleep","spec":{"seconds":8}}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

curl -sS -X POST "http://127.0.0.1:18280/v0/jobs/${ID}/cancel"
curl -sS "http://127.0.0.1:18280/v0/jobs/${ID}"
```

Unknown kinds return **400** `{"error":"unknown_kind", ...}`. Cancel of a terminal job returns **409** `{"error":"already_terminal", ...}`. Missing ids return **404**.

Demo kinds: `sos.demo.echo`, `sos.demo.sleep`. Spec is an opaque JSON object (no engine URLs). Jobs are process-local and disappear on restart.

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
