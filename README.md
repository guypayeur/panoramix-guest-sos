# panoramix-guest-sos

Day-one **SoS** (actuarial) guest for [Panoramix](https://github.com/guypayeur/panoramix).

Pin **0.5**. This repository is opaque domain code plus a platform Unit contract. Compute engines live in [panoramix-runtime](https://github.com/guypayeur/panoramix-runtime) bindings — see [runtime#70](https://github.com/guypayeur/panoramix-runtime/issues/70) Slice B. The opaque handoff shape is defined by [`runtime/compute_work.py`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/compute_work.py) on runtime **main**. This guest does **not** close #70 and does **not** unlock cloud #61 / #29.

## What this is

- A greenfield Panoramix **0.5** guest: Unit `sos`, public HTTP on **18280**, probes at `/health`.
- A **day-one operator path**: submit work, watch status, cancel. Guest-facing handoff is opaque `kind` / `class` / `payload_digest` ([`runtime/compute_work.py`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/compute_work.py)). In-process stub runner only — engines stay in runtime bindings. Local demos: `echo`, `sleep`, and **`reserve`** (shaped UX seed — not IFRS17 math, not a perf baseline).
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

Those boxes live on [panoramix-runtime#70](https://github.com/guypayeur/panoramix-runtime/issues/70). Slice B alignment here is the opaque seam only — **not** #70 Done.

The named iec comparison path (runtime [method.yaml](https://github.com/guypayeur/panoramix-runtime/blob/main/proofs/fixtures/iec-parity/method.yaml) after [#82](https://github.com/guypayeur/panoramix-runtime/pull/82)) is **`grammar/examples/reserve_ifrs17`**, with UX journey [`docs/ux/journeys/run_lifecycle_monitoring.md`](https://github.com/guypayeur/iec-proto-c/blob/main/docs/ux/journeys/run_lifecycle_monitoring.md). This guest’s `demo: "reserve"` is a **thinner stub / UX seed** so operators can walk submit → status pills → cancel beside that named baseline. Comparable **perf** waits on runtime compute-plane engines. This path does **not** claim UX/perf parity and does **not** close #70.

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
2. **Local demo shortcut** (operator UX only): `{"demo":"echo","message":"..."}`, `{"demo":"sleep","seconds":8}`, or `{"demo":"reserve", ...}` (optional `label`, `stages`, `seconds`, `class`). The server synthesizes `{kind:"job", class:"cpu"|"gpu", payload_digest}` from canonical JSON of those params (`json.dumps(..., sort_keys=True, separators=(",", ":"))` then sha256). `class: "gpu"` on reserve is a **UX label only** (still in-process; no GPU kernels). It never stores engine URLs. The seam `kind` is always `job` for this shortcut — demo labels are not seam kinds. **Reserve is a stub / UX seed only** — not IFRS17 math, not a perf baseline; named iec baseline remains `reserve_ifrs17`.

Resources expose at least `id`, `kind`, `class`, `payload_digest`, `status`. Status is `queued` → `running` → `succeeded` | `failed` | `canceled` (one L). Guest-local stub metadata may appear under `local` (not a runtime handoff field).

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
  -d '{"demo":"reserve","label":"ux-seed","stages":3,"seconds":8}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

curl -sS "http://127.0.0.1:18280/v0/jobs/${ID}"
# optional: class=gpu is a UX label only (still in-process stub)
curl -sS -X POST http://127.0.0.1:18280/v0/jobs \
  -H 'Content-Type: application/json' \
  -d '{"demo":"reserve","class":"gpu","seconds":8}'
```

Sleep, then cancel while queued/running:

```bash
ID=$(curl -sS -X POST http://127.0.0.1:18280/v0/jobs \
  -H 'Content-Type: application/json' \
  -d '{"demo":"sleep","seconds":8}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

curl -sS -X POST "http://127.0.0.1:18280/v0/jobs/${ID}/cancel"
curl -sS "http://127.0.0.1:18280/v0/jobs/${ID}"
```

Bad `kind` / `class` / `payload_digest` return **400**. Cancel of a terminal job returns **409** `{"error":"already_terminal", ...}`. Missing ids return **404**.

Jobs are process-local and disappear on restart. The stub records opaque work locally; it does not start an engine.

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
