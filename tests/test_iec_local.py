"""iec-local same-job admit / compose / ctl prefix. No live iec checkout."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

from sos.errors import (
    ERROR_CTL_HTTP_UNREACHABLE,
    ERROR_DURABLE_ADMIT_FAILED,
    SAME_JOB_STUB_DETAIL,
    AlreadyCanceled,
    DurableAdmitFailed,
    IllegalTransition,
    InvalidClass,
    InvalidDemo,
)
from sos.handoff import parse_submit, same_job_params
from sos.handoff_vocab import (
    IEC_METHOD_PIN,
    IEC_SOURCE_FILE,
    SAME_JOB_CANONICAL_JSON,
    SAME_JOB_PAYLOAD_DIGEST,
    extract_lifecycle_overlay,
)
from sos.http import SosApp
from sos.jobs import PROGRESS_SOURCE_DURABLE, JobStore
from sos.lab_compose import DEFAULT_GUEST_PORT
from sos.lab_compose_iec import (
    COMPOSE_HOOK_ID,
    DEFAULT_IEC_BINDING_REL,
    DEFAULT_IEC_CTL_PORT,
    HONESTY_LINES,
    RUNTIME_IEC_PIN,
    SAME_JOB_BODY,
    IecLocalComposeHook,
    build_iec_compose_plan,
    classify_iec_evidence,
    dry_run_iec_smokes,
    iec_smokes_honest,
    resolve_same_job_catalog,
    same_job_body,
)
from sos.lab_ctl import (
    CTL_KIND_IEC_LOCAL,
    CTL_KIND_RESERVE_TEMPORAL,
    ENV_CTL_KIND,
    LabReserveTemporalHook,
    resolve_ctl_kind,
)
from sos.lab_ctl_http import (
    CTL_HTTP_TIMEOUT_CODE,
    ENV_CTL_HTTP,
    IEC_LOCAL_PREFIX,
    LabReserveTemporalHttpHook,
    http_hook_from_env,
)
from sos.runtime_hook import describe_runtime_hook


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "lab_compose_iec_local.py"
LOOPBACK_IEC = "http://127.0.0.1:19216"


def _json(resp) -> dict:
    return json.loads(resp.body.decode("utf-8"))


class SameJobIdentityTests(unittest.TestCase):
    def test_digest_matches_canonical_json(self) -> None:
        canonical = json.dumps(
            same_job_params(), sort_keys=True, separators=(",", ":")
        )
        self.assertEqual(canonical, SAME_JOB_CANONICAL_JSON)
        digest = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.assertEqual(digest, SAME_JOB_PAYLOAD_DIGEST)
        self.assertEqual(
            digest,
            "sha256:1a1e14a08f08b7fd310c335bf863b475c86919cf0e59e9326207b49e8ae2206c",
        )
        self.assertEqual(same_job_params()["revision"], IEC_METHOD_PIN)
        self.assertEqual(same_job_params()["source_file"], IEC_SOURCE_FILE)
        self.assertEqual(same_job_params()["workload"], "reserve_ifrs17")

    def test_parse_same_job_and_alias(self) -> None:
        for catalog in ("reserve_ifrs17", "same-job"):
            parsed = parse_submit({"demo": "reserve", "catalog": catalog})
            self.assertEqual(parsed.kind, "job")
            self.assertEqual(parsed.resource_class, "cpu")
            self.assertEqual(parsed.payload_digest, SAME_JOB_PAYLOAD_DIGEST)
            self.assertEqual(parsed.local["catalog"], "reserve_ifrs17")
            self.assertIs(parsed.local["same_job"], True)
            self.assertIs(parsed.local["ifrs17_guest"], False)
            self.assertEqual(parsed.payload_bytes.decode("utf-8"), SAME_JOB_CANONICAL_JSON)

    def test_same_job_refuses_thinner_params_and_gpu(self) -> None:
        with self.assertRaises(InvalidDemo):
            parse_submit({"demo": "reserve", "catalog": "reserve_ifrs17", "accounts": 48})
        with self.assertRaises(InvalidClass):
            parse_submit({"demo": "reserve", "catalog": "reserve_ifrs17", "class": "gpu"})
        with self.assertRaises(InvalidDemo):
            parse_submit({"demo": "reserve", "catalog": "ifrs17"})

    def test_inert_same_job_fail_closes(self) -> None:
        store = JobStore(step_seconds=0.01)
        with self.assertRaises(DurableAdmitFailed) as ctx:
            store.submit({"demo": "reserve", "catalog": "reserve_ifrs17"})
        self.assertEqual(ctx.exception.error, ERROR_DURABLE_ADMIT_FAILED)
        self.assertEqual(ctx.exception.fields["reason"], "same_job_stub")
        self.assertEqual(ctx.exception.fields["detail"], SAME_JOB_STUB_DETAIL)
        self.assertIs(ctx.exception.fields["north_star_done"], False)

    def test_opaque_digest_also_fail_closes(self) -> None:
        store = JobStore(step_seconds=0.01)
        with self.assertRaises(DurableAdmitFailed) as ctx:
            store.submit(
                {
                    "kind": "job",
                    "class": "cpu",
                    "payload_digest": SAME_JOB_PAYLOAD_DIGEST,
                }
            )
        self.assertEqual(ctx.exception.fields["reason"], "same_job_stub")

    def test_http_inert_same_job_is_409(self) -> None:
        app = SosApp(JobStore(step_seconds=0.01))
        resp = app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "catalog": "same-job"}).encode(),
        )
        self.assertEqual(resp.status, 409)
        body = _json(resp)
        self.assertEqual(body["error"], ERROR_DURABLE_ADMIT_FAILED)
        self.assertEqual(body["reason"], "same_job_stub")
        self.assertIn("does not run IFRS17", body["detail"])

    def test_hooked_same_job_shows_durable_phase(self) -> None:
        store = JobStore(runtime_hook=IecLocalComposeHook(), step_seconds=0.01)
        job = store.submit({"demo": "reserve", "catalog": "reserve_ifrs17"})
        public = store.public_dict(store.get(job.id))
        self.assertEqual(public["status"], "running")
        self.assertEqual(public["local"]["backed"], "runtime")
        self.assertIs(public["local"]["same_job"], True)
        progress = store.progress(job.id)
        self.assertEqual(progress["source"], PROGRESS_SOURCE_DURABLE)
        self.assertEqual(progress["phase"], "admitted")
        self.assertEqual(progress["fraction"], 0.0)
        self.assertIs(progress["same_job"], True)
        self.assertIs(progress["ifrs17_guest"], False)
        self.assertNotIn("timeline", progress)
        self.assertNotIn("walls", progress)
        self.assertEqual(public["cw_id"], COMPOSE_HOOK_ID)
        self.assertEqual(progress["cw_id"], COMPOSE_HOOK_ID)
        self.assertNotIn("iec_job_id", public)
        self.assertNotIn("iec_job_id", progress)

    def test_progress_and_job_pass_through_nested_identities(self) -> None:
        class NestedHook(IecLocalComposeHook):
            def progress(self, job_id, runtime_ref):
                del job_id, runtime_ref
                return {
                    "same_job": True,
                    "id": COMPOSE_HOOK_ID,
                    "iec_job_id": "ab12cd34",
                    "phase": "running",
                    "fraction": 0.2,
                }

            def status(self, job_id, runtime_ref):
                del job_id, runtime_ref
                self.last_status_payload = {
                    "id": COMPOSE_HOOK_ID,
                    "iec_job_id": "ab12cd34",
                    "handoff": {"id": COMPOSE_HOOK_ID, "status": "running"},
                }
                return "running"

        store = JobStore(runtime_hook=NestedHook(), step_seconds=0.01)
        job = store.submit(same_job_body())
        progress = store.progress(job.id)
        self.assertEqual(progress["source"], PROGRESS_SOURCE_DURABLE)
        self.assertEqual(progress["iec_job_id"], "ab12cd34")
        self.assertEqual(progress["cw_id"], COMPOSE_HOOK_ID)
        self.assertEqual(progress["id"], job.id)
        self.assertNotEqual(progress["id"], progress["cw_id"])
        self.assertNotIn("eta_elapsed_s", progress)
        self.assertNotIn("heartbeat", progress)
        public = store.public_dict(store.get(job.id))
        self.assertEqual(public["iec_job_id"], "ab12cd34")
        self.assertEqual(public["cw_id"], COMPOSE_HOOK_ID)
        self.assertEqual(public["id"], job.id)

    def test_progress_omits_nested_identities_when_missing(self) -> None:
        class WallsOnlyHook(IecLocalComposeHook):
            def admit(self, handoff, payload_bytes):
                del handoff, payload_bytes
                return {"ctl": "iec-local", "status": "running"}

            def progress(self, job_id, runtime_ref):
                del job_id, runtime_ref
                return {"same_job": True, "walls": {"api_e2e_ms": 40, "invented": False}}

        store = JobStore(runtime_hook=WallsOnlyHook(), step_seconds=0.01)
        job = store.submit(same_job_body())
        progress = store.progress(job.id)
        public = store.public_dict(store.get(job.id))
        self.assertEqual(progress["source"], PROGRESS_SOURCE_DURABLE)
        self.assertNotIn("iec_job_id", progress)
        self.assertNotIn("cw_id", progress)
        self.assertNotIn("iec_job_id", public)
        self.assertNotIn("cw_id", public)

    def test_http_job_and_progress_expose_nested_identities(self) -> None:
        class NestedHook(IecLocalComposeHook):
            def progress(self, job_id, runtime_ref):
                del job_id, runtime_ref
                return {
                    "same_job": True,
                    "compute_work_id": COMPOSE_HOOK_ID,
                    "iec_job_id": "plat-9f",
                    "progress": {"phase": "kernel"},
                }

        app = SosApp(JobStore(runtime_hook=NestedHook(), step_seconds=0.01))
        created = app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "catalog": "reserve_ifrs17"}).encode(),
        )
        self.assertEqual(created.status, 201)
        job_id = _json(created)["id"]
        body = _json(app.handle("GET", f"/v0/jobs/{job_id}/progress"))
        self.assertEqual(body["iec_job_id"], "plat-9f")
        self.assertEqual(body["cw_id"], COMPOSE_HOOK_ID)
        detail = _json(app.handle("GET", f"/v0/jobs/{job_id}"))
        self.assertEqual(detail["iec_job_id"], "plat-9f")
        self.assertEqual(detail["cw_id"], COMPOSE_HOOK_ID)
        self.assertIs(detail["handoff_docs"]["north_star_done"], False)

    def test_job_detail_picks_iec_job_id_from_status(self) -> None:
        class MidFlightHook(IecLocalComposeHook):
            def progress(self, job_id, runtime_ref):
                del job_id, runtime_ref
                return {"same_job": True, "phase": "unknown", "fraction": 0.0}

            def status(self, job_id, runtime_ref):
                del job_id, runtime_ref
                self.last_status_payload = {
                    "id": COMPOSE_HOOK_ID,
                    "iec_job_id": "live-iec-1",
                    "handoff": {"id": COMPOSE_HOOK_ID, "status": "running"},
                }
                return "running"

        store = JobStore(runtime_hook=MidFlightHook(), step_seconds=0.01)
        job = store.submit(same_job_body())
        public = store.public_dict(store.get(job.id))
        self.assertEqual(public["iec_job_id"], "live-iec-1")
        self.assertEqual(public["cw_id"], COMPOSE_HOOK_ID)
        progress = store.progress(job.id)
        self.assertEqual(progress["iec_job_id"], "live-iec-1")
        self.assertEqual(progress["cw_id"], COMPOSE_HOOK_ID)
        self.assertNotIn("phase", progress)
        self.assertNotIn("fraction", progress)

    def test_progress_omits_platform_unknown_zero_defaults(self) -> None:
        class ZeroedHook(IecLocalComposeHook):
            def progress(self, job_id, runtime_ref):
                del job_id, runtime_ref
                return {
                    "same_job": True,
                    "phase": "unknown",
                    "fraction": 0.0,
                    "pct": 0,
                    "iec_job_id": "unknown",
                    "progress": {"invented": False},
                    "walls": {
                        "api_e2e_ms": 1800,
                        "wall_elapsed_ms": 1800,
                        "invented": False,
                    },
                }

        store = JobStore(runtime_hook=ZeroedHook(), step_seconds=0.01)
        job = store.submit(same_job_body())
        progress = store.progress(job.id)
        self.assertEqual(progress["source"], PROGRESS_SOURCE_DURABLE)
        self.assertIs(progress["same_job"], True)
        self.assertNotIn("phase", progress)
        self.assertNotIn("fraction", progress)
        self.assertNotIn("pct", progress)
        self.assertNotIn("iec_job_id", progress)
        self.assertNotEqual(progress.get("phase"), "unknown")
        self.assertNotIn("timeline", progress)
        self.assertEqual(progress["walls"]["api_e2e_ms"], 1800)
        self.assertIn("unknown/0", progress["note"])

    def test_progress_omits_when_hook_leaves_phase_fraction_out(self) -> None:
        class WallsOnlyHook(IecLocalComposeHook):
            def progress(self, job_id, runtime_ref):
                del job_id, runtime_ref
                return {
                    "same_job": True,
                    "progress": {"invented": False},
                    "walls": {"api_e2e_ms": 900, "invented": False},
                }

        class EmptyHook(IecLocalComposeHook):
            def progress(self, job_id, runtime_ref):
                del job_id, runtime_ref
                return {"invented": False}

        store = JobStore(runtime_hook=WallsOnlyHook(), step_seconds=0.01)
        job = store.submit(same_job_body())
        progress = store.progress(job.id)
        self.assertEqual(progress["source"], PROGRESS_SOURCE_DURABLE)
        self.assertNotIn("phase", progress)
        self.assertNotIn("fraction", progress)
        self.assertNotIn("pct", progress)
        self.assertNotIn("timeline", progress)
        self.assertEqual(progress["walls"]["api_e2e_ms"], 900)

        empty = JobStore(runtime_hook=EmptyHook(), step_seconds=0.01)
        omitted = empty.progress(empty.submit(same_job_body()).id)
        self.assertEqual(omitted["source"], PROGRESS_SOURCE_DURABLE)
        self.assertNotIn("phase", omitted)
        self.assertNotIn("fraction", omitted)
        self.assertNotIn("timeline", omitted)

    def test_progress_surfaces_honest_hook_fields(self) -> None:
        class RichHook(IecLocalComposeHook):
            def progress(self, job_id, runtime_ref):
                del job_id, runtime_ref
                return {
                    "same_job": True,
                    "progress": {
                        "phase": "compile_dag",
                        "pct": 0.12,
                        "updated_at": "2026-04-14T11:02:17Z",
                    },
                    "chunk_idx": 2,
                    "n_chunks": 4,
                }

        store = JobStore(runtime_hook=RichHook(), step_seconds=0.01)
        job = store.submit(same_job_body())
        progress = store.progress(job.id)
        self.assertEqual(progress["source"], PROGRESS_SOURCE_DURABLE)
        self.assertEqual(progress["phase"], "compile_dag")
        self.assertAlmostEqual(progress["fraction"], 0.12)
        self.assertEqual(progress["pct"], 0.12)
        self.assertEqual(progress["updated_at"], "2026-04-14T11:02:17Z")
        self.assertEqual(progress["chunk_idx"], 2)
        self.assertEqual(progress["n_chunks"], 4)
        self.assertNotIn("timeline", progress)
        self.assertNotIn("eta_elapsed_s", progress)
        self.assertNotIn("heartbeat", progress)

    def test_progress_maps_event_and_keeps_honest_zero_fraction(self) -> None:
        class InitHook(IecLocalComposeHook):
            def progress(self, job_id, runtime_ref):
                del job_id, runtime_ref
                return {"phase": "init", "pct": 0.0, "fraction": 0.0}

        store = JobStore(runtime_hook=InitHook(), step_seconds=0.01)
        job = store.submit(same_job_body())
        progress = store.progress(job.id)
        self.assertEqual(progress["phase"], "init")
        self.assertEqual(progress["fraction"], 0.0)
        self.assertEqual(progress["pct"], 0.0)

    def test_http_progress_omits_unknown_zero(self) -> None:
        class ZeroedHook(IecLocalComposeHook):
            def progress(self, job_id, runtime_ref):
                del job_id, runtime_ref
                return {"phase": "unknown", "fraction": 0.0, "pct": 0}

        app = SosApp(JobStore(runtime_hook=ZeroedHook(), step_seconds=0.01))
        created = app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "catalog": "reserve_ifrs17"}).encode(),
        )
        self.assertEqual(created.status, 201)
        job_id = _json(created)["id"]
        body = _json(app.handle("GET", f"/v0/jobs/{job_id}/progress"))
        self.assertEqual(body["source"], PROGRESS_SOURCE_DURABLE)
        self.assertNotIn("phase", body)
        self.assertNotIn("fraction", body)
        self.assertNotIn("pct", body)

    def test_progress_copies_honest_walls_only(self) -> None:
        class WallHook(IecLocalComposeHook):
            def progress(self, job_id, runtime_ref):
                del job_id, runtime_ref
                return {
                    "phase": "running",
                    "fraction": 0.4,
                    "pct": 40,
                    "walls": {
                        "api_e2e_ms": 1200,
                        "wall_elapsed_ms": 1200,
                        "invented": False,
                    },
                }

        store = JobStore(runtime_hook=WallHook(), step_seconds=0.01)
        job = store.submit(same_job_body())
        progress = store.progress(job.id)
        self.assertEqual(progress["walls"]["api_e2e_ms"], 1200)
        self.assertEqual(progress["wall_elapsed_ms"], 1200)

        class InventedHook(IecLocalComposeHook):
            def progress(self, job_id, runtime_ref):
                del job_id, runtime_ref
                return {
                    "phase": "admitted",
                    "fraction": 0.0,
                    "walls": {"api_e2e_ms": 1, "invented": True},
                }

        store = JobStore(runtime_hook=InventedHook(), step_seconds=0.01)
        job = store.submit(same_job_body())
        progress = store.progress(job.id)
        self.assertNotIn("walls", progress)
        self.assertNotIn("wall_elapsed_ms", progress)


class CtlKindTests(unittest.TestCase):
    def test_port_19216_selects_iec_local(self) -> None:
        self.assertEqual(resolve_ctl_kind({}), CTL_KIND_RESERVE_TEMPORAL)
        self.assertEqual(
            resolve_ctl_kind({}, origin="http://127.0.0.1:19215"),
            CTL_KIND_RESERVE_TEMPORAL,
        )
        self.assertEqual(
            resolve_ctl_kind({}, origin=LOOPBACK_IEC),
            CTL_KIND_IEC_LOCAL,
        )
        self.assertEqual(
            resolve_ctl_kind({ENV_CTL_KIND: "iec-local"}, origin="http://127.0.0.1:19215"),
            CTL_KIND_IEC_LOCAL,
        )

    def test_http_hook_uses_iec_local_prefix(self) -> None:
        calls: list[tuple[str, str]] = []

        def transport(method, url, headers, body):
            del headers, body
            calls.append((method, url))
            if url.endswith("/iec-local/admit"):
                return 200, json.dumps(
                    {
                        "ok": True,
                        "id": COMPOSE_HOOK_ID,
                        "handoff": {"id": COMPOSE_HOOK_ID, "status": "running"},
                    }
                )
            if "/iec-local/progress" in url:
                return 200, json.dumps({"phase": "admitted", "fraction": 0.0})
            if "/iec-local/status" in url:
                return 200, json.dumps(
                    {"handoff": {"id": COMPOSE_HOOK_ID, "status": "running"}}
                )
            return 404, json.dumps({"error": url})

        hook = http_hook_from_env({ENV_CTL_HTTP: LOOPBACK_IEC}, transport=transport)
        self.assertIsNotNone(hook)
        assert hook is not None
        self.assertEqual(hook.ctl, CTL_KIND_IEC_LOCAL)
        self.assertEqual(hook.prefix, IEC_LOCAL_PREFIX)
        ref = hook.admit(
            {
                "kind": "job",
                "class": "cpu",
                "payload_digest": SAME_JOB_PAYLOAD_DIGEST,
            },
            None,
        )
        self.assertEqual(ref["id"], COMPOSE_HOOK_ID)
        self.assertEqual(ref["ctl"], CTL_KIND_IEC_LOCAL)
        self.assertNotIn("iec_job_id", ref)
        self.assertIsNone(hook.events("job", ref))
        self.assertTrue(any(url.endswith("/iec-local/admit") for _, url in calls))
        self.assertFalse(any("/reserve-temporal/" in url for _, url in calls))
        desc = describe_runtime_hook(hook)
        self.assertEqual(desc["ctl"], CTL_KIND_IEC_LOCAL)
        self.assertIs(desc["durable_path"], True)
        self.assertIn("does not run IFRS17", desc["note"])

    def test_http_hook_admit_and_progress_keep_nested_identities(self) -> None:
        def transport(method, url, headers, body):
            del method, headers, body
            if url.endswith("/iec-local/admit"):
                return 200, json.dumps(
                    {
                        "ok": True,
                        "id": COMPOSE_HOOK_ID,
                        "iec_job_id": "plat-admit",
                        "handoff": {"id": COMPOSE_HOOK_ID, "status": "running"},
                    }
                )
            if "/iec-local/progress" in url:
                return 200, json.dumps(
                    {
                        "ok": True,
                        "id": COMPOSE_HOOK_ID,
                        "iec_job_id": "plat-mid",
                        "same_job": True,
                        "progress": {"invented": False},
                        "walls": {"api_e2e_ms": 250, "invented": False},
                    }
                )
            if "/iec-local/status" in url:
                return 200, json.dumps(
                    {
                        "id": COMPOSE_HOOK_ID,
                        "iec_job_id": "plat-mid",
                        "handoff": {"id": COMPOSE_HOOK_ID, "status": "running"},
                    }
                )
            return 404, json.dumps({"error": url})

        hook = LabReserveTemporalHttpHook(
            LOOPBACK_IEC,
            transport=transport,
            ctl=CTL_KIND_IEC_LOCAL,
        )
        ref = hook.admit(
            {
                "kind": "job",
                "class": "cpu",
                "payload_digest": SAME_JOB_PAYLOAD_DIGEST,
            },
            None,
        )
        self.assertEqual(ref["id"], COMPOSE_HOOK_ID)
        self.assertEqual(ref["iec_job_id"], "plat-admit")
        store = JobStore(runtime_hook=hook, step_seconds=0.01)
        job = store.submit(same_job_body())
        public = store.public_dict(store.get(job.id))
        self.assertEqual(public["iec_job_id"], "plat-mid")
        self.assertEqual(public["cw_id"], COMPOSE_HOOK_ID)
        progress = store.progress(job.id)
        self.assertEqual(progress["iec_job_id"], "plat-mid")
        self.assertEqual(progress["cw_id"], COMPOSE_HOOK_ID)
        self.assertEqual(progress["walls"]["api_e2e_ms"], 250)
        self.assertNotIn("phase", progress)
        self.assertNotIn("timeline", progress)

    def test_admit_then_status_timeout_is_201_not_lab_serve_down(self) -> None:
        """#79: slow-but-up ctl after admit must not stamp lab-serve-down."""

        def transport(method, url, headers, body, **_kwargs):
            del method, headers, body
            if url.split("?")[0].endswith("/iec-local/admit"):
                return 200, json.dumps(
                    {
                        "ok": True,
                        "id": COMPOSE_HOOK_ID,
                        "handoff": {
                            "id": COMPOSE_HOOK_ID,
                            "status": "running",
                        },
                    }
                )
            return CTL_HTTP_TIMEOUT_CODE, ""

        hook = LabReserveTemporalHttpHook(
            LOOPBACK_IEC,
            transport=transport,
            listen_probe=lambda: True,
            ctl=CTL_KIND_IEC_LOCAL,
        )
        self.assertEqual(hook.ctl, CTL_KIND_IEC_LOCAL)
        app = SosApp(JobStore(step_seconds=0.01, runtime_hook=hook))
        created = app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "catalog": "reserve_ifrs17"}).encode(),
        )
        self.assertEqual(created.status, 201)
        body = _json(created)
        self.assertNotEqual(body.get("error"), ERROR_CTL_HTTP_UNREACHABLE)
        self.assertIsNone(body.get("error"))
        self.assertEqual(body["status"], "running")
        self.assertEqual(body["local"]["backed"], "runtime")
        self.assertNotIn("lab_serve", body)
        self.assertIsNone(hook.last_unreachable)

        progress = _json(app.handle("GET", f"/v0/jobs/{body['id']}/progress"))
        self.assertNotEqual(progress.get("source"), "unreachable")
        self.assertNotEqual(progress.get("error"), ERROR_CTL_HTTP_UNREACHABLE)

    def test_http_env_19215_stays_reserve_temporal(self) -> None:
        hook = http_hook_from_env({ENV_CTL_HTTP: "http://127.0.0.1:19215"})
        self.assertIsNotNone(hook)
        assert hook is not None
        self.assertEqual(hook.ctl, CTL_KIND_RESERVE_TEMPORAL)
        self.assertEqual(hook.prefix, "/reserve-temporal")

    def test_apply_hook_uses_iec_local_prefix(self) -> None:
        calls: list[list[str]] = []

        def runner(argv, *, cwd, env):
            del cwd, env
            calls.append(list(argv))
            return 0, json.dumps({"id": COMPOSE_HOOK_ID, "handoff": {"status": "queued"}}), ""

        hook = LabReserveTemporalHook(
            Path("."),
            runner=runner,
            ctl=CTL_KIND_IEC_LOCAL,
        )
        ref = hook.admit(
            {
                "kind": "job",
                "class": "cpu",
                "payload_digest": SAME_JOB_PAYLOAD_DIGEST,
            },
            None,
        )
        self.assertEqual(ref["ctl"], CTL_KIND_IEC_LOCAL)
        self.assertEqual(calls[0][:5], ["python3", "-m", "runtime.apply", "iec-local", "admit"])
        self.assertIsNone(hook.events("job", ref))


class ComposePlanTests(unittest.TestCase):
    def test_plan_defaults(self) -> None:
        plan = build_iec_compose_plan(guest_root=ROOT)
        self.assertEqual(plan.ctl_http, LOOPBACK_IEC)
        self.assertEqual(int(plan.guest_listen), DEFAULT_GUEST_PORT)
        self.assertEqual(plan.binding, DEFAULT_IEC_BINDING_REL)
        self.assertEqual(plan.reserve_body, SAME_JOB_BODY)
        self.assertEqual(plan.guest_env[ENV_CTL_HTTP], LOOPBACK_IEC)
        self.assertEqual(plan.guest_env[ENV_CTL_KIND], CTL_KIND_IEC_LOCAL)
        self.assertNotIn("PANORAMIX_RESERVE_TEMPORAL_LIVE", plan.guest_env)
        self.assertIs(plan.north_star_done, False)
        self.assertIn("guest does not run IFRS17 math", HONESTY_LINES)
        self.assertTrue(RUNTIME_IEC_PIN.startswith("d480dc8"))
        blob = plan.to_dict()
        self.assertNotIn("pack_fill", blob)
        self.assertIs(blob["closes_runtime_70"], False)
        self.assertIs(blob["closes_runtime_78"], False)
        self.assertEqual(resolve_same_job_catalog("same-job"), "reserve_ifrs17")

    def test_classify_does_not_require_events(self) -> None:
        evidence = classify_iec_evidence(
            {
                "payload_digest": SAME_JOB_PAYLOAD_DIGEST,
                "local": {"backed": "runtime", "same_job": True},
            },
            {"source": "durable", "phase": "admitted", "fraction": 0.0},
        )
        self.assertTrue(evidence["ok"])
        self.assertEqual(evidence["phase"], "admitted")
        self.assertEqual(evidence["fraction"], 0.0)
        self.assertIs(evidence["events_required"], False)
        self.assertIs(evidence["pause_resume_required"], False)
        self.assertIs(evidence["north_star_done"], False)

    def test_classify_omits_unknown_phase_and_missing_fraction(self) -> None:
        evidence = classify_iec_evidence(
            {
                "payload_digest": SAME_JOB_PAYLOAD_DIGEST,
                "local": {"backed": "runtime", "same_job": True},
            },
            {"source": "durable"},
        )
        self.assertTrue(evidence["ok"])
        self.assertNotIn("phase", evidence)
        self.assertNotIn("fraction", evidence)

        fake = classify_iec_evidence(
            {
                "payload_digest": SAME_JOB_PAYLOAD_DIGEST,
                "local": {"backed": "runtime", "same_job": True},
            },
            {"source": "durable", "phase": "unknown", "fraction": 0.0},
        )
        self.assertTrue(fake["ok"])
        self.assertNotIn("phase", fake)
        self.assertNotIn("fraction", fake)

    def test_dry_run_smokes_and_script(self) -> None:
        smokes = dry_run_iec_smokes()
        self.assertTrue(iec_smokes_honest(smokes))
        self.assertTrue(smokes["hooked"]["ok"])
        self.assertEqual(smokes["hooked"]["status"], "running")
        self.assertEqual(smokes["inert"]["reason"], "same_job_stub")
        self.assertIs(smokes["inert"]["stub_fallback"], False)
        self.assertIs(smokes["ifrs17_guest"], False)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        blob = json.loads(proc.stdout)
        self.assertEqual(blob["ctl_http"], LOOPBACK_IEC)
        self.assertEqual(blob["reserve_body"]["catalog"], "reserve_ifrs17")
        self.assertTrue(blob["iec_smoke"]["honest"])
        self.assertIs(blob["north_star_done"], False)
        self.assertNotIn("pack_fill", blob)

    def test_info_and_ui_name_same_job(self) -> None:
        app = SosApp(JobStore())
        info = _json(app.handle("GET", "/v0/info"))
        self.assertEqual(info["jobs"]["reserve_catalogs"], ["recorded", "live", "parity"])
        iec = info["jobs"]["iec_local"]
        self.assertEqual(iec["catalog"], "reserve_ifrs17")
        self.assertEqual(iec["digest"], SAME_JOB_PAYLOAD_DIGEST)
        self.assertEqual(iec["ctl_port"], DEFAULT_IEC_CTL_PORT)
        self.assertIs(iec["ifrs17_guest"], False)
        self.assertIs(iec["north_star_done"], False)
        self.assertIn("Phase/fraction omit when", iec["note"])
        html = app.handle("GET", "/").body.decode("utf-8")
        self.assertIn('value="reserve_ifrs17"', html)
        self.assertIn("iec-local same-job", html)
        self.assertIn("Guest does", html)
        self.assertIn("does not run ifrs17", html.lower())
        self.assertIn("docs/lab-compose-iec-local.md", html)
        self.assertIn("isSameJob", html)
        self.assertIn("honestPhase", html)
        self.assertIn("honestNumber", html)
        self.assertIn("nestedIdentities", html)
        self.assertIn("iec_job_id", html)
        self.assertIn("cw_id", html)
        self.assertIn("omit unknown/0", html)
        self.assertIn("19216", html)
        self.assertIn("already_canceled", html)
        self.assertIn("pause_limit", html)
        self.assertIn("can_pause", html)
        self.assertIn("next_action", html)
        self.assertIn('value="held"', html)
        self.assertIn("st-held", html)


class DayOneHonestyTests(unittest.TestCase):
    """Pause/held/FAILED/already_canceled omit-when-missing plumbing."""

    def test_extract_overlay_omits_unknown(self) -> None:
        overlay = extract_lifecycle_overlay(
            {
                "pause_limit": "iec pause-before-start",
                "can_pause": False,
                "next_action": "unknown",
                "nextAction": "retry fold",
                "valuation": "",
                "held_reason": "operator hold",
                "error": {"error_code": "VALUATION_FAILED"},
            }
        )
        self.assertEqual(overlay["pause_limit"], "iec pause-before-start")
        self.assertIs(overlay["can_pause"], False)
        self.assertEqual(overlay["next_action"], "retry fold")
        self.assertEqual(overlay["held_reason"], "operator hold")
        self.assertEqual(overlay["error_code"], "VALUATION_FAILED")
        self.assertNotIn("valuation", overlay)
        from sos.lab_ctl import _lifecycle_status

        self.assertEqual(_lifecycle_status({"status": "HELD"}), "held")
        self.assertEqual(_lifecycle_status({"status": "HOLD"}), "held")
        self.assertEqual(_lifecycle_status({"status": "COMPLETED"}), "succeeded")

    def test_same_job_omits_pause_until_hook_supplies_it(self) -> None:
        hook = IecLocalComposeHook()
        store = JobStore(runtime_hook=hook, step_seconds=0.01)
        job = store.submit(same_job_body())
        public = store.public_dict(store.get(job.id))
        self.assertEqual(public["status"], "running")
        self.assertIs(public["pause_resume"], False)
        self.assertNotIn("can_pause", public)
        self.assertNotIn("pause_limit", public)
        self.assertNotIn("pause_resume", store.handoff(job.id))
        self.assertNotIn("can_pause", store.handoff(job.id))
        with self.assertRaises(IllegalTransition) as ctx:
            store.pause(job.id)
        body = ctx.exception.to_dict()
        self.assertEqual(body["error"], "illegal_transition")
        self.assertIn("pause_limit", body)

        hook.last_status_payload = {
            "status": "running",
            "can_pause": True,
            "pause_limit": "pause-before-start only unless can_pause",
        }
        got = store.public_dict(store.get(job.id))
        self.assertIs(got["pause_resume"], True)
        self.assertIs(got["can_pause"], True)
        self.assertEqual(got["pause_limit"], "pause-before-start only unless can_pause")
        paused = store.pause(job.id)
        self.assertEqual(paused.status, "paused")
        self.assertNotIn("can_pause", store.handoff(job.id))

    def test_held_and_failure_fields_pass_through(self) -> None:
        hook = IecLocalComposeHook()
        store = JobStore(runtime_hook=hook, step_seconds=0.01)
        job = store.submit(same_job_body())
        hook.last_status_payload = {
            "status": "HELD",
            "held_reason": "operator hold",
            "can_resume": True,
            "pause_limit": "iec pause-before-start (single-activity)",
        }
        held = store.public_dict(store.get(job.id))
        self.assertEqual(held["status"], "held")
        self.assertIs(held["pause_resume"], True)
        self.assertIs(held["can_resume"], True)
        self.assertEqual(held["held_reason"], "operator hold")
        self.assertIn("held", [item["event"] for item in held["events"]])
        resumed = store.resume(job.id)
        self.assertEqual(resumed.status, "running")

        hook.last_status_payload = {
            "status": "FAILED",
            "next_action": "re-admit with revised params",
            "valuation": "FAILED",
            "stage_name": "fold",
            "error_code": "VALUATION_FAILED",
        }
        failed = store.public_dict(store.get(job.id))
        self.assertEqual(failed["status"], "failed")
        term = failed["terminal"]
        self.assertEqual(term["next_action"], "re-admit with revised params")
        self.assertEqual(term["valuation"], "FAILED")
        self.assertEqual(term["stage_name"], "fold")
        self.assertEqual(term["stage"], "fold")
        self.assertEqual(term["error_code"], "VALUATION_FAILED")
        self.assertNotIn("next_action", store.handoff(job.id))

        hook.last_status_payload = {
            "status": "failed",
            "next_action": "unknown",
            "valuation": "",
        }
        omitted = store.public_dict(store.get(job.id))
        self.assertNotIn("next_action", omitted)
        self.assertNotIn("valuation", omitted.get("terminal") or {})

    def test_same_job_cancel_already_canceled(self) -> None:
        hook = IecLocalComposeHook()
        store = JobStore(runtime_hook=hook, step_seconds=0.01)
        job = store.submit(same_job_body())
        canceled = store.cancel(job.id)
        self.assertEqual(canceled.status, "canceled")
        with self.assertRaises(AlreadyCanceled) as ctx:
            store.cancel(job.id)
        body = ctx.exception.to_dict()
        self.assertEqual(body["error"], "already_canceled")
        self.assertIs(body["already_canceled"], True)

        app = SosApp(JobStore(runtime_hook=IecLocalComposeHook(), step_seconds=0.01))
        created = app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "reserve", "catalog": "reserve_ifrs17"}).encode(),
        )
        job_id = _json(created)["id"]
        first = app.handle("POST", f"/v0/jobs/{job_id}/cancel")
        self.assertEqual(first.status, 200)
        conflict = app.handle("POST", f"/v0/jobs/{job_id}/cancel")
        self.assertEqual(conflict.status, 409)
        payload = _json(conflict)
        self.assertEqual(payload["error"], "already_canceled")
        self.assertIs(payload["already_canceled"], True)


if __name__ == "__main__":
    unittest.main()
