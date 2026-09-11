# Panoramix operational notes (sos guest)

Guest for [guypayeur/panoramix](https://github.com/guypayeur/panoramix). Pin **0.5**. Compute engines: [panoramix-runtime#70](https://github.com/guypayeur/panoramix-runtime/issues/70) Slice B. Hard reference: [`runtime/compute_work.py`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/compute_work.py) on runtime main. Not #70 Done; does not unlock #61 / #29.

## Claim

This repo is a real guest origin (not under `platform-tools/fixtures/`). The platform owns the envelope; sos stays opaque domain code. Day-one is a **jobs HTTP API + operator UI** with an in-process stub runner — **not** iec-proto-c and **not** a compute plane.

## Guest compute seam (#70 Slice B; not Done)

The guest submits **opaque work** over HTTP (`POST /v0/jobs`) using the Slice B shape in [`runtime/compute_work.py`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/compute_work.py) on panoramix-runtime main: `kind` (`job`|`stage`|`chunk`), `class` (`cpu`|`gpu`), `payload_digest` (`sha256:` + 64 hex). Status lifecycle is `queued` → `running` → `succeeded` | `failed` | `canceled`. List/get/cancel stay on the same public port.

A **local-only** demo shortcut (`demo: echo|sleep|reserve` plus params) synthesizes that opaque shape so the operator UI does not require hand-computed digests. Stub runner metadata may nest under `local`; it is not a runtime handoff field. `local.backed` is `stub` (in-process fallback) unless an operator-injected hook admits the job (`runtime`).

`demo: "reserve"` is a **stub / UX seed** for operator submit → status → cancel beside the named iec baseline **`grammar/examples/reserve_ifrs17`**. Payload bytes **mirror** panoramix-runtime **main** helpers `runtime.reserve.recorded_params` / `runtime.reserve.live_params` / `runtime.reserve.digest_for` ([`docs/reserve.md`](https://github.com/guypayeur/panoramix-runtime/blob/main/docs/reserve.md) / [`runtime/reserve.py`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/reserve.py)): `workload`, `accounts`, `horizon`, `paths`, `seed`, `lapse_bps`, `discount_bps` — thinner than IFRS17; guest copies catalogs and does **not** import runtime. Recorded digest is `sha256:77e9299f4b8ea4aeed46f71b91cc947d56e9bd169d795e70845123fef53d7e4e`. Optional `label` / `stages` / `seconds` are local stub UX only. **Not** IFRS17 math, **not** a copy of iec-proto-c, **not** a perf baseline until #83 + remeasure. This does **not** close #70.

### Operator / ctl seam (stub fallback vs binding)

Transport today is **operator/ctl-mediated only**. Compute mesh is **`from: compute-job` → `to: sos`** (worker calls Unit). The guest does **not** dial Ray / Temporal / AWS, does **not** open guest→ctl HTTP for compute-work, and does **not** call `runtime.apply compute-work`.

Do not invent `PLATFORM_RAY_*`, engine URLs, guest-callable ctl HTTP, or env that adds mesh destinations (`PLATFORM_MESH_*`). Operator/ctl:

1. **Stub fallback (default):** Guest UX `POST /v0/jobs` runs in-process.
2. **Export:** `GET /v0/jobs/{id}/handoff` (exactly `id`/`kind`/`class`/`payload_digest`/`status` — WorkHandoff projection, **no** nested `payload` key) and `GET /v0/jobs/{id}/payload` (`utf8`/`hex` of canonical JSON bytes).
3. **Operator binding path:** operator/ctl admits that tuple on the runtime compute plane via the binding. Guest **never** POSTs to ctl and **never** calls `runtime.apply compute-work`. Binding examples: [`local-sos-compute.example.yaml`](https://github.com/guypayeur/panoramix-runtime/blob/main/bindings/local-sos-compute.example.yaml), [`local-reserve.example.yaml`](https://github.com/guypayeur/panoramix-runtime/blob/main/bindings/local-reserve.example.yaml) (Unit sos, port 18280, pin 0.5; engine kind in the binding only).

`sos.runtime_hook.InertRuntimeHandoffHook` is inert: admit/cancel/status no-op and the in-process stub is the fallback. Cancel always attempts the hook first, then local cancel.

**Cancel:** stub-backed → local only. Runtime-backed (injected hook) → signal the hook, then mark the guest job `canceled` if it was still live.

Runtime bindings will select engines later (slices C/D/E). Request bodies that smuggle engine brand keys or URL schemes are **400**. How bindings attach compute is documented on [runtime#70](https://github.com/guypayeur/panoramix-runtime/issues/70), not in `.platform/contract.yaml`. This alignment does **not** close #70 and does **not** unlock #61 / #29.

## Domain-leak log

| Temptation | Decision |
|---|---|
| Add `image:`, `ray:`, `temporal:`, or `aws:` to Unit/System YAML | **Rejected** — pin stays **0.5**; engines and image digests live in runtime bindings / lock sidecars |
| Lift iec-proto-c L1–L2 (or any iec tree) into this Git | **Rejected** — greenfield guest; iec is a north-star UX/perf **benchmark**, not a dependency |
| Put actuarial request/response schema types on the adapter | **Rejected** — guest speaks HTTP on the public port |
| Encode workflow IDs / cluster addresses in Unit Git | **Rejected** — [runtime#70](https://github.com/guypayeur/panoramix-runtime/issues/70) Slice B: submit `kind`/`class`/`payload_digest` without engine URLs/schemas in the contract |
| Accept engine brand fields on `POST /v0/jobs` | **Rejected** — 400 `engine_smuggle`; engines stay in runtime bindings |
| Add `PLATFORM_RAY_*` / invent `PLATFORM_COMPUTE_*` so “jobs can run for real” | **Rejected** — no guest-callable ctl HTTP; operator/ctl admits WorkHandoff; mesh is compute-job → sos |
| Env that adds mesh destinations (`PLATFORM_MESH_*`) | **Rejected** — mesh on local-sos-compute is already compute-job → sos; guest does not grow destinations |
| Guest→ctl HTTP for compute-work | **Rejected** — transport is operator/ctl-mediated only; guest emits WorkHandoff JSON |
| Put a nested `payload` field on `GET /v0/jobs/{id}/handoff` | **Rejected** — runtime `parse_work` refuses `payload` on submit; bytes live on `GET .../payload` as `utf8`/`hex` |
| Call `runtime.apply compute-work` from the guest | **Rejected** — guest emits WorkHandoff JSON only; mesh is compute-job → sos |
| Add a “SoS SDK” facet so apply understands the DSL | **Rejected** — HTTP/1.1 + `PLATFORM_*` env is the envelope |
| Teach `apply` to walk `sos/` imports so UI/job edits bump digest | **Rejected** — Rec 2 gotcha: digest is entrypoint paths only (`platform_run.py`). Entry may import `sos.http` (httpbin pattern); sibling `sos/` edits still must not be assumed to change emulate digest |
| Pin Flask/FastAPI/Ray on the Unit | **Rejected** — `build` is admission shape; this guest is stdlib; emulate does not execute `build.command` |
| Claim `demo: reserve` is IFRS17 math, iec `grammar/examples/reserve_ifrs17`, or a perf baseline | **Rejected** — UX seed stub only; named iec baseline stays on runtime `proofs/fixtures/iec-parity/method.yaml`; no perf baseline until runtime #83 + remeasure |
| Mark runtime #70 Done from this guest | **Rejected** — Slice B alignment is the opaque seam only |
| Claim day-one feature/UX/perf parity with iec-proto-c | **Rejected** — north star is UX/perf on agreed workflows ([runtime#70](https://github.com/guypayeur/panoramix-runtime/issues/70)); day-one is thinner |
| Unlock AWS/GKE/ECS from this guest | **Rejected** — local lab before AWS; cloud spend issues stay locked on the runtime |

## Digest gotcha

`run.entrypoint` names only `platform_run.py`. Editing `sos/jobs.py` (or other siblings) alone must **not** change the deploy digest under emulate’s entrypoint rule. Editing `platform_run.py` must. The thin entrypoint **may** import `sos.http` (like httpbin’s `platform_run` importing `httpbin.core.app`); that import does not expand the digest to the package.

## Engines

Do not add engine fields here. The container/compute runtime ([panoramix-runtime](https://github.com/guypayeur/panoramix-runtime)) records image digests and binding-selected engines **outside** this Unit.

## Run (with panoramix tools available)

```bash
GUEST=/path/to/panoramix-guest-sos
# from a panoramix checkout:
python3 platform-tools/platform_check.py "$GUEST"
python3 platform-tools/platform_emulate.py "$GUEST" --run --duration 2
python3 platform-tools/platform_serve.py "$GUEST" --port 19220
```

Emulate only: Unix adapter, localhost edge, stamped `PLATFORM_NETWORK_EGRESS`. `build.command` is not run. Still not `process` / `container` / `microvm`.

## Image digest (container profile, later)

If a container runtime admits a guest-CI image digest, that pin is **not** a Unit field. Pin stays **0.5**. Do not add `image:` here.
