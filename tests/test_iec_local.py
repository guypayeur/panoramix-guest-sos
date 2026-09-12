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
    DurableAdmitFailed,
    InvalidClass,
    InvalidDemo,
)
from sos.handoff import parse_submit, same_job_params
from sos.handoff_vocab import (
    IEC_METHOD_PIN,
    IEC_SOURCE_FILE,
    SAME_JOB_CANONICAL_JSON,
    SAME_JOB_PAYLOAD_DIGEST,
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
        self.assertIsNone(hook.events("job", ref))
        self.assertTrue(any(url.endswith("/iec-local/admit") for _, url in calls))
        self.assertFalse(any("/reserve-temporal/" in url for _, url in calls))
        desc = describe_runtime_hook(hook)
        self.assertEqual(desc["ctl"], CTL_KIND_IEC_LOCAL)
        self.assertIs(desc["durable_path"], True)
        self.assertIn("does not run IFRS17", desc["note"])

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
        self.assertIs(evidence["events_required"], False)
        self.assertIs(evidence["pause_resume_required"], False)
        self.assertIs(evidence["north_star_done"], False)

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
        html = app.handle("GET", "/").body.decode("utf-8")
        self.assertIn('value="reserve_ifrs17"', html)
        self.assertIn("iec-local same-job", html)
        self.assertIn("Guest does", html)
        self.assertIn("does not run ifrs17", html.lower())
        self.assertIn("docs/lab-compose-iec-local.md", html)
        self.assertIn("isSameJob", html)
        self.assertIn("19216", html)


if __name__ == "__main__":
    unittest.main()
