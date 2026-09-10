# Panoramix operational notes (sos guest)

Guest for [guypayeur/panoramix](https://github.com/guypayeur/panoramix). Pin **0.5**. Compute engines: [panoramix-runtime#70](https://github.com/guypayeur/panoramix-runtime/issues/70).

## Claim

This repo is a real guest origin (not under `platform-tools/fixtures/`). The platform owns the envelope; sos stays opaque domain code. Day-one is a health/info HTTP stub, **not** iec-proto-c and **not** a compute plane.

## Domain-leak log

| Temptation | Decision |
|---|---|
| Add `image:`, `ray:`, `temporal:`, or `aws:` to Unit/System YAML | **Rejected** — pin stays **0.5**; engines and image digests live in runtime bindings / lock sidecars |
| Lift iec-proto-c L1–L2 (or any iec tree) into this Git | **Rejected** — greenfield guest; iec is a north-star UX/perf **benchmark**, not a dependency |
| Put actuarial request/response schema types on the adapter | **Rejected** — guest speaks HTTP on the public port |
| Encode Temporal workflow IDs / Ray addresses in Unit Git | **Rejected** — [runtime#70](https://github.com/guypayeur/panoramix-runtime/issues/70) guest seam: submit work without engine URLs/schemas in the contract |
| Add a “SoS SDK” facet so apply understands the DSL | **Rejected** — HTTP/1.1 + `PLATFORM_*` env is the envelope |
| Teach `apply` to walk `sos/` imports | **Rejected** — Rec 2 gotcha: digest is entrypoint paths only (`platform_run.py`) |
| Pin Flask/FastAPI/Ray on the Unit | **Rejected** — `build` is admission shape; this stub is stdlib; emulate does not execute `build.command` |
| Claim day-one feature parity with iec-proto-c | **Rejected** — north star is UX/perf on agreed workflows ([runtime#70](https://github.com/guypayeur/panoramix-runtime/issues/70)); day-one may be thinner |
| Unlock AWS/GKE/ECS from this guest | **Rejected** — local lab before AWS; cloud spend issues stay locked on the runtime |

## Digest gotcha

`run.entrypoint` names only `platform_run.py`. Editing `sos/control.py` alone must **not** change the deploy digest under emulate’s entrypoint rule. Editing `platform_run.py` must.

## Engines

Do not add engine fields here. The container/compute runtime ([panoramix-runtime](https://github.com/guypayeur/panoramix-runtime)) records image digests and binding-selected engines **outside** this Unit. How a future SoS guest submits compute work without embedding engine URLs is documented on [runtime#70](https://github.com/guypayeur/panoramix-runtime/issues/70) — not in `.platform/contract.yaml`.

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
