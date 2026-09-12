"""Lab compose helpers — plan / evidence / wait. No live Temporal."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sos.http import SosApp
from sos.jobs import JobStore
from sos.lab_compose import (
    DEFAULT_BINDING_REL,
    DEFAULT_CTL_PORT,
    DEFAULT_GUEST_PORT,
    HONESTY_LINES,
    OPAQUE_HANDOFF_BODY,
    RECORDED_RESERVE_BODY,
    RUNTIME_SERVE_PIN,
    LabComposeReadmitHook,
    build_compose_plan,
    classify_lab_evidence,
    classify_readmit_evidence,
    ctl_origin,
    dry_run_readmit_smokes,
    exercise_readmit_smoke,
    guest_env_for_ctl,
    guest_paths,
    job_paths,
    plan_json,
    port_from_origin,
    readmit_plan,
    readmit_smokes_honest,
    recorded_reserve_body,
    runtime_root_usable,
    runtime_serve_argv,
    wait_loopback_port,
)
from sos.lab_ctl_http import ENV_CTL_HTTP, LabReserveTemporalHttpHook
from sos.runtime_hook import (
    HOOK_KIND_CTL_HTTP,
    HOOK_KIND_INERT,
    InertRuntimeHandoffHook,
    describe_runtime_hook,
    durable_hook_active,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "lab_compose_reserve_temporal.py"


class ComposePlanTests(unittest.TestCase):
    def test_serve_argv_and_defaults(self) -> None:
        argv = runtime_serve_argv()
        self.assertEqual(
            argv,
            (
                "python3",
                "-m",
                "runtime.serve",
                "--binding",
                DEFAULT_BINDING_REL,
            ),
        )
        self.assertEqual(DEFAULT_CTL_PORT, 19215)
        self.assertEqual(DEFAULT_GUEST_PORT, 18280)
        self.assertEqual(RUNTIME_SERVE_PIN, "fb901542")
        self.assertEqual(recorded_reserve_body(), RECORDED_RESERVE_BODY)
        self.assertEqual(RECORDED_RESERVE_BODY["catalog"], "recorded")

    def test_ctl_origin_loopback_only(self) -> None:
        self.assertEqual(ctl_origin(), "http://127.0.0.1:19215")
        self.assertEqual(ctl_origin(19216, "localhost"), "http://localhost:19216")
        with self.assertRaises(ValueError):
            ctl_origin(host="0.0.0.0")
        with self.assertRaises(ValueError):
            ctl_origin(host="10.0.0.2")
        with self.assertRaises(ValueError):
            ctl_origin(port=0)

    def test_guest_env_fail_closed_off_loopback(self) -> None:
        env = guest_env_for_ctl(
            ctl_http="http://127.0.0.1:19215",
            guest_listen="18280",
        )
        self.assertEqual(env[ENV_CTL_HTTP], "http://127.0.0.1:19215")
        self.assertEqual(env["PLATFORM_LISTEN_HTTP"], "18280")
        with self.assertRaises(ValueError):
            guest_env_for_ctl(ctl_http="http://10.0.0.2:19215", guest_listen="18280")
        with self.assertRaises(ValueError):
            guest_env_for_ctl(ctl_http="https://127.0.0.1:19215", guest_listen="18280")

    def test_build_plan_without_runtime_root(self) -> None:
        plan = build_compose_plan(guest_root=ROOT)
        self.assertIsNone(plan.runtime_root)
        self.assertEqual(plan.ctl_http, "http://127.0.0.1:19215")
        self.assertEqual(plan.guest_listen, "18280")
        self.assertEqual(plan.guest_env[ENV_CTL_HTTP], plan.ctl_http)
        self.assertEqual(plan.guest_env["PLATFORM_LISTEN_HTTP"], "18280")
        self.assertEqual(plan.serve_argv[4], DEFAULT_BINDING_REL)
        self.assertEqual(plan.guest_argv, ("python3", "./platform_run.py"))
        self.assertEqual(plan.reserve_body, {"demo": "reserve", "catalog": "recorded"})
        self.assertIs(plan.north_star_done, False)
        self.assertIn("not guest→mesh ctl", plan.honesty)
        self.assertIn("north_star_done false", plan.honesty)
        self.assertIn("pin 0.5", plan.honesty)
        blob = plan_json(plan)
        parsed = json.loads(blob)
        self.assertIs(parsed["guest_to_mesh_ctl"], False)
        self.assertIs(parsed["north_star_done"], False)
        paths = guest_paths(plan)
        self.assertEqual(paths["jobs"], "http://127.0.0.1:18280/v0/jobs")
        self.assertEqual(
            job_paths(plan, "abc")["progress"],
            "http://127.0.0.1:18280/v0/jobs/abc/progress",
        )
        self.assertEqual(
            job_paths(plan, "abc")["readmit"],
            "http://127.0.0.1:18280/v0/jobs/abc/re-admit",
        )
        self.assertEqual(port_from_origin(plan.ctl_http), 19215)
        readmit = parsed["readmit"]
        self.assertEqual(readmit["path"], "POST /v0/jobs/{id}/re-admit")
        self.assertEqual(
            readmit["journey"],
            ["admit", "cancel_or_fail", "re-admit", "new_job_id"],
        )
        self.assertIs(readmit["resume_from_failed"], False)
        self.assertIs(readmit["silent_stub"], False)
        self.assertIs(readmit["north_star_done"], False)
        self.assertEqual(readmit_plan()["when"], readmit["when"])

    def test_runtime_root_usable_fail_closed(self) -> None:
        self.assertIsNone(runtime_root_usable(None))
        self.assertIsNone(runtime_root_usable(""))
        self.assertIsNone(runtime_root_usable("/no/such/runtime-root"))
        with tempfile.TemporaryDirectory() as raw:
            empty = Path(raw)
            self.assertIsNone(runtime_root_usable(empty))
            (empty / "runtime").mkdir()
            (empty / "runtime" / "apply.py").write_text("# apply\n", encoding="utf-8")
            self.assertEqual(runtime_root_usable(empty), empty.resolve())


class EvidenceTests(unittest.TestCase):
    def test_ok_only_when_runtime_and_durable(self) -> None:
        stub = classify_lab_evidence(
            {"local": {"backed": "stub"}, "pause_resume": False},
            {"source": "stub"},
            {"source": "memory"},
        )
        self.assertFalse(stub["ok"])
        self.assertEqual(stub["backed"], "stub")
        self.assertIs(stub["pause_resume"], False)
        self.assertIs(stub["north_star_done"], False)

        partial = classify_lab_evidence(
            {"local": {"backed": "runtime"}, "pause_resume": True},
            {"source": "stub"},
            {"source": "durable", "events_durable": True},
        )
        self.assertFalse(partial["ok"])

        ok = classify_lab_evidence(
            {
                "local": {"backed": "runtime"},
                "pause_resume": True,
                "events_source": "durable",
                "events_durable": True,
            },
            {"source": "durable", "stages_completed": 1},
            {"source": "durable", "events_durable": True, "events_n": 3},
        )
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["progress_source"], "durable")
        self.assertEqual(ok["events_source"], "durable")
        self.assertIs(ok["events_durable"], True)
        self.assertIs(ok["guest_to_mesh_ctl"], False)


class ReadmitSmokeTests(unittest.TestCase):
    def test_hooked_admit_cancel_readmit_new_id(self) -> None:
        result = exercise_readmit_smoke(runtime_hook=LabComposeReadmitHook())
        evidence = result["evidence"]
        self.assertIs(evidence["ok"], True)
        self.assertIs(evidence["fail_closed"], False)
        self.assertIs(evidence["silent_stub"], False)
        self.assertIs(evidence["resume_from_failed"], False)
        self.assertIs(evidence["new_admit"], True)
        self.assertIs(evidence["one_click"], True)
        self.assertIs(evidence["north_star_done"], False)
        self.assertIs(evidence["guest_to_mesh_ctl"], False)
        self.assertEqual(result["readmit_status"], 201)
        self.assertNotEqual(evidence["new_id"], evidence["source_id"])
        self.assertEqual(evidence["re_admit_from"], evidence["source_id"])
        self.assertEqual(evidence["backed"], "runtime")
        self.assertEqual(evidence["source_status"], "canceled")
        self.assertIn("not resume-from-failed", (result["readmit"] or {}).get("message", ""))
        self.assertEqual(
            classify_readmit_evidence(
                result["source"],
                result["readmit"],
                http_status=201,
            )["ok"],
            True,
        )

    def test_inert_and_payload_unknown_fail_closed(self) -> None:
        inert = exercise_readmit_smoke()
        self.assertIs(inert["evidence"]["ok"], False)
        self.assertIs(inert["evidence"]["fail_closed"], True)
        self.assertEqual(inert["evidence"]["fail_closed_reason"], "hook_inert")
        self.assertIs(inert["evidence"]["silent_stub"], False)
        self.assertIs(inert["evidence"]["resume_from_failed"], False)
        self.assertEqual(inert["readmit_status"], 409)
        self.assertEqual((inert["error"] or {}).get("error"), "re_admit_unavailable")
        self.assertIn("no silent stub", (inert["error"] or {}).get("detail", "").lower())
        self.assertIsNone(inert["readmit"])

        missing = exercise_readmit_smoke(
            runtime_hook=LabComposeReadmitHook(),
            submit_body=OPAQUE_HANDOFF_BODY,
        )
        self.assertIs(missing["evidence"]["ok"], False)
        self.assertIs(missing["evidence"]["fail_closed"], True)
        self.assertEqual(missing["evidence"]["fail_closed_reason"], "payload_unknown")
        self.assertIs(missing["evidence"]["silent_stub"], False)
        self.assertEqual(missing["readmit_status"], 409)
        self.assertIsNone(missing["readmit"])

        refused = classify_readmit_evidence(
            {
                "id": "src",
                "status": "canceled",
                "recoverability": {
                    "one_click": True,
                    "new_admit": True,
                    "resume_from_failed": False,
                },
            },
            {"error": "re_admit_unavailable", "reason": "hook_refused"},
            http_status=409,
        )
        self.assertIs(refused["ok"], False)
        self.assertIs(refused["fail_closed"], True)
        self.assertEqual(refused["fail_closed_reason"], "hook_refused")
        self.assertIs(refused["silent_stub"], False)

        stub = classify_readmit_evidence(
            {
                "id": "src",
                "status": "canceled",
                "recoverability": {
                    "one_click": False,
                    "new_admit": True,
                    "resume_from_failed": False,
                },
            },
            {"id": "other", "local": {"backed": "stub", "re_admit_from": "src"}},
            http_status=201,
        )
        self.assertIs(stub["ok"], False)
        self.assertIs(stub["silent_stub"], True)
        self.assertIs(stub["fail_closed"], False)

    def test_dry_run_smokes_honest(self) -> None:
        smokes = dry_run_readmit_smokes()
        self.assertTrue(readmit_smokes_honest(smokes))
        self.assertIs(smokes["hooked"]["ok"], True)
        self.assertNotEqual(smokes["hooked"]["new_id"], smokes["hooked"]["source_id"])
        self.assertEqual(smokes["inert"]["fail_closed_reason"], "hook_inert")
        self.assertEqual(
            smokes["payload_unknown"]["fail_closed_reason"], "payload_unknown"
        )
        self.assertIs(smokes["north_star_done"], False)
        self.assertIs(smokes["resume_from_failed"], False)
        self.assertIs(smokes["silent_stub"], False)


class WaitPortTests(unittest.TestCase):
    def test_wait_succeeds_and_times_out(self) -> None:
        seen: list[tuple[str, int]] = []

        def connect(host: str, port: int) -> None:
            seen.append((host, port))
            if len(seen) < 2:
                raise OSError("not yet")

        self.assertTrue(
            wait_loopback_port(
                19215,
                timeout_s=1.0,
                interval_s=0.0,
                clock=lambda: 0.0,
                sleeper=lambda _s: None,
                connector=connect,
            )
        )
        self.assertEqual(seen[-1], ("127.0.0.1", 19215))

        def refuse(_host: str, _port: int) -> None:
            raise OSError("refused")

        ticks = {"n": 0.0}

        def clock() -> float:
            ticks["n"] += 0.5
            return ticks["n"]

        self.assertFalse(
            wait_loopback_port(
                9,
                timeout_s=1.0,
                interval_s=0.0,
                clock=clock,
                sleeper=lambda _s: None,
                connector=refuse,
            )
        )


class HookDescribeTests(unittest.TestCase):
    def test_inert_does_not_pretend(self) -> None:
        desc = describe_runtime_hook(InertRuntimeHandoffHook())
        self.assertEqual(desc["kind"], HOOK_KIND_INERT)
        self.assertIs(desc["durable_path"], False)
        self.assertIs(desc["north_star_done"], False)
        self.assertIs(desc["guest_to_mesh_ctl"], False)
        self.assertIn("No pretend", desc["note"])
        self.assertIs(durable_hook_active(InertRuntimeHandoffHook()), False)

    def test_injected_hook_is_active_for_readmit(self) -> None:
        class TinyHook:
            def admit(self, handoff, payload_bytes):
                return {"accepted": True}

        self.assertIs(durable_hook_active(TinyHook()), True)
        self.assertIs(describe_runtime_hook(TinyHook())["durable_path"], False)

    def test_http_hook_badge(self) -> None:
        hook = LabReserveTemporalHttpHook(
            "http://127.0.0.1:19215",
            transport=lambda *_a, **_k: (500, ""),
        )
        desc = describe_runtime_hook(hook)
        self.assertEqual(desc["kind"], HOOK_KIND_CTL_HTTP)
        self.assertIs(desc["durable_path"], True)
        self.assertEqual(desc["ctl_http"], "http://127.0.0.1:19215")
        self.assertIs(desc["north_star_done"], False)

    def test_info_exposes_hook(self) -> None:
        inert = SosApp(JobStore())
        body = json.loads(inert.handle("GET", "/v0/info").body.decode())
        self.assertEqual(body["jobs"]["durable_hook"]["kind"], HOOK_KIND_INERT)
        self.assertIs(body["jobs"]["durable_hook"]["durable_path"], False)

        hooked = SosApp(
            JobStore(
                runtime_hook=LabReserveTemporalHttpHook(
                    "http://127.0.0.1:19215",
                    transport=lambda *_a, **_k: (500, ""),
                )
            )
        )
        hooked_body = json.loads(hooked.handle("GET", "/v0/info").body.decode())
        hook = hooked_body["jobs"]["durable_hook"]
        self.assertEqual(hook["kind"], HOOK_KIND_CTL_HTTP)
        self.assertIs(hook["durable_path"], True)
        self.assertIn("lab_compose_reserve_temporal", hooked_body["jobs"]["ctl_handoff"]["note"])


class ScriptDryRunTests(unittest.TestCase):
    def test_dry_run_prints_plan(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        plan = json.loads(proc.stdout)
        self.assertEqual(plan["ctl_http"], "http://127.0.0.1:19215")
        self.assertEqual(plan["guest_env"][ENV_CTL_HTTP], "http://127.0.0.1:19215")
        self.assertEqual(plan["guest_env"]["PLATFORM_LISTEN_HTTP"], "18280")
        self.assertIn("runtime.serve", plan["serve_argv"])
        self.assertIn(DEFAULT_BINDING_REL, plan["serve_argv"])
        self.assertEqual(plan["reserve_body"]["catalog"], "recorded")
        self.assertIs(plan["north_star_done"], False)
        self.assertIs(plan["guest_to_mesh_ctl"], False)
        self.assertEqual(plan["readmit"]["path"], "POST /v0/jobs/{id}/re-admit")
        self.assertEqual(plan["readmit"]["journey"][-1], "new_job_id")
        self.assertIs(plan["readmit"]["resume_from_failed"], False)
        self.assertIs(plan["readmit"]["silent_stub"], False)
        smoke = plan["readmit_smoke"]
        self.assertTrue(readmit_smokes_honest(smoke))
        self.assertIs(smoke["hooked"]["ok"], True)
        self.assertNotEqual(smoke["hooked"]["new_id"], smoke["hooked"]["source_id"])
        self.assertEqual(smoke["inert"]["fail_closed_reason"], "hook_inert")
        self.assertEqual(smoke["payload_unknown"]["fail_closed_reason"], "payload_unknown")
        self.assertIs(smoke["north_star_done"], False)

    def test_live_fail_closed_without_runtime_root(self) -> None:
        env = dict(**{k: v for k, v in __import__("os").environ.items() if k != "PANORAMIX_RUNTIME_ROOT"})
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("fail closed", proc.stderr.lower())
        self.assertIn("dry-run", proc.stderr.lower())


class HonestyTests(unittest.TestCase):
    def test_helpers_and_docs(self) -> None:
        helper = (ROOT / "sos" / "lab_compose.py").read_text(encoding="utf-8")
        self.assertIn("Does not close runtime", helper)
        self.assertIn("#70", helper)
        self.assertIn("#78", helper)
        self.assertIn("north_star_done", helper)
        self.assertIn("Not guest→mesh ctl", helper)
        self.assertIn("Not SIEM", helper)
        self.assertIn("Not IFRS17", helper)
        self.assertIn("Pin 0.5", helper)
        self.assertIn("fail-closed", helper)
        self.assertNotIn("Fixes #70", helper)
        self.assertNotIn("Fixes #78", helper)
        self.assertNotIn("subprocess", helper)
        self.assertNotIn("Popen", helper)
        self.assertNotIn("urllib.request", helper)
        imports = [
            line.strip()
            for line in helper.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        blob = "\n".join(imports)
        self.assertNotIn("from runtime", blob)
        self.assertNotIn("import runtime", blob)

        for name in (
            "docs/lab-compose.md",
            "scripts/lab_compose_reserve_temporal.py",
        ):
            text = ROOT.joinpath(name).read_text(encoding="utf-8")
            self.assertIn("PANORAMIX_CTL_HTTP", text, name)
            self.assertIn("19215", text, name)
            self.assertIn("local-reserve-temporal.example.yaml", text, name)
            self.assertIn("runtime.serve", text, name)
            self.assertIn("PLATFORM_LISTEN_HTTP", text, name)
            self.assertIn("north_star_done", text, name)
            self.assertIn("fail-closed", text.lower().replace("fail closed", "fail-closed"), name)
            self.assertTrue(
                "not guest→mesh ctl" in text.lower() or "Not guest→mesh ctl" in text,
                name,
            )
            self.assertNotIn("Fixes #70", text)
            self.assertNotIn("Fixes #78", text)
            self.assertIn("#61", text, name)
            self.assertIn("#29", text, name)
            self.assertIn("/re-admit", text, name)
            self.assertIn("no silent stub", text.lower(), name)
            self.assertIn("not resume-from-failed", text.lower(), name)

        for line in HONESTY_LINES:
            self.assertTrue(line)
        helper = (ROOT / "sos" / "lab_compose.py").read_text(encoding="utf-8")
        self.assertIn("no silent stub re-admit", helper)
        self.assertIn("not resume-from-failed", helper)
        self.assertNotIn("Fixes #70", helper)
        self.assertNotIn("Fixes #78", helper)

        ux = (ROOT / "docs" / "ux-side-by-side.md").read_text(encoding="utf-8")
        self.assertIn(
            "| Recoverability (handoff re-admit) | ctl re-admit after fail/cancel | **match** (thinner) |",
            ux,
        )
        self.assertNotIn(
            "| Recoverability (handoff re-admit) | ctl re-admit after fail/cancel | **partial** |",
            ux,
        )
        self.assertIn("- [x] One-shot lab compose", ux)
        self.assertIn("re-admit smoke", ux)
        self.assertIn("- [ ] `north_star_done: true`", ux)
        self.assertNotIn("- [x] `north_star_done: true`", ux)
        self.assertIn("- [ ] Operator/actuary path", ux)
        self.assertNotIn("- [x] Operator/actuary path", ux)
        self.assertIn("does **not** mark #70 Done", ux)


if __name__ == "__main__":
    unittest.main()
