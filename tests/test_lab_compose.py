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
    ENV_GUEST_TIP,
    ENV_RUNTIME_TIP,
    GUEST_PACK_TIP,
    HONESTY_LINES,
    OPAQUE_HANDOFF_BODY,
    RUNTIME_PACK_DOCS_PIN,
    RUNTIME_PACK_GAP_REPORT_PIN,
    RUNTIME_PACK_TIP,
    elapsed_plan,
    git_head_sha,
    handoff_docs_plan,
    looks_like_git_tip,
    pack_fill_fragment,
    pack_fill_plan,
    skeleton_handoff_plan,
    wall_plan,
    RECORDED_RESERVE_BODY,
    RUNTIME_DOCS_PIN,
    RUNTIME_ELAPSED_PIN,
    RUNTIME_SERVE_PIN,
    RUNTIME_WALL_PIN,
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
    resolve_known_tip,
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
        self.assertEqual(RUNTIME_ELAPSED_PIN, "9ba95bbb")
        self.assertEqual(RUNTIME_DOCS_PIN, "5dc191cb")
        self.assertEqual(RUNTIME_WALL_PIN, "9b6646e8")
        self.assertEqual(RUNTIME_PACK_TIP, "b81130f2187109eabc2342df6345ca877e98023f")
        self.assertTrue(RUNTIME_PACK_TIP.startswith("b81130f"))
        self.assertEqual(RUNTIME_PACK_DOCS_PIN, "63a168d")
        self.assertEqual(RUNTIME_PACK_GAP_REPORT_PIN, "84cb202")
        self.assertEqual(GUEST_PACK_TIP, "b859466dcd079eb063b615728b258a686f79749a")
        self.assertTrue(GUEST_PACK_TIP.startswith("b859466"))
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
        elapsed = parsed["timeline_elapsed"]
        self.assertIs(elapsed["omit_when_missing"], True)
        self.assertIs(elapsed["invent"], False)
        self.assertIs(elapsed["north_star_done"], False)
        self.assertEqual(elapsed["runtime_tip"], "9ba95bbb")
        self.assertEqual(elapsed["docs_tip"], "5dc191cb")
        self.assertEqual(elapsed["or"], "main")
        self.assertEqual(elapsed_plan()["when"], elapsed["when"])
        wall = parsed["wall_elapsed"]
        self.assertIs(wall["omit_when_missing"], True)
        self.assertIs(wall["invent"], False)
        self.assertIs(wall["forecast"], False)
        self.assertIs(wall["ifrs17"], False)
        self.assertIs(wall["iec_spa"], False)
        self.assertIs(wall["north_star_done"], False)
        self.assertEqual(wall["runtime_tip"], "9b6646e8")
        self.assertEqual(wall["docs_tip"], "6511cec7")
        self.assertEqual(wall["or"], "main")
        self.assertEqual(wall["runtime_pr"], 114)
        self.assertEqual(wall["docs_pr"], 116)
        self.assertEqual(wall_plan()["when"], wall["when"])
        self.assertIn("compare", wall["note"].lower())
        docs = parsed["handoff_docs"]
        self.assertIs(docs["panel"], True)
        self.assertIs(docs["second_control_plane"], False)
        self.assertIs(docs["north_star_done"], False)
        self.assertEqual(handoff_docs_plan()["note"], docs["note"])
        self.assertIn("path-slice elapsed omitted when timestamps missing (never invent)", plan.honesty)
        self.assertIn("optional durable stage elapsed from runtime tip 9ba95bbb / docs tip 5dc191cb (or main)", plan.honesty)
        self.assertIn("optional durable wall_elapsed_ms from runtime tip 9b6646e8 (or main; omit when missing)", plan.honesty)
        self.assertIn("compare prefers durable wall_elapsed_ms when present (runtime tip 9b6646e8 / main; omit when missing)", plan.honesty)
        self.assertIn("handoff docs panel is operator clarity (not a second control plane)", plan.honesty)
        self.assertIn("pack-fill tips from checkout / env / documented tip (omit when missing)", plan.honesty)
        self.assertIn(
            "pack-fill durable wall/stage elapsed only when measured from hooked run (omit when missing; never invent)",
            plan.honesty,
        )
        self.assertIn(
            "pack-fill emit fragment can feed runtime.iec_parity_pack skeleton via --from-json / flags (measured durable only; omit when missing)",
            plan.honesty,
        )
        self.assertIn(
            "pack-fill docs tip 63a168d / PR #122 names WSL assist-smoke stamp lineage (assist ≠ fill)",
            plan.honesty,
        )
        self.assertIn(
            "pack-fill gap-report tip 84cb202 / PR #124 names WSL gap-report stamp lineage (gap-report ≠ Done; assist ≠ fill)",
            plan.honesty,
        )
        self.assertIn("never invent metrics.wall_time_sec", plan.honesty)
        self.assertIn("assist ≠ fill; assist ≠ Done", plan.honesty)
        fill = parsed["pack_fill"]
        self.assertIs(fill["omit_when_missing"], True)
        self.assertIs(fill["invent"], False)
        self.assertIs(fill["forecast"], False)
        self.assertIs(fill["ifrs17"], False)
        self.assertIs(fill["iec_spa"], False)
        self.assertIs(fill["writes_live_pack"], False)
        self.assertIs(fill["ux_done"], False)
        self.assertIs(fill["north_star_done"], False)
        self.assertEqual(fill["runtime_tip"], RUNTIME_PACK_TIP)
        self.assertEqual(fill["or"], "main")
        self.assertEqual(fill["runtime_pr"], 120)
        self.assertEqual(fill["docs_tip"], "63a168d")
        self.assertEqual(fill["docs_pr"], 122)
        self.assertEqual(fill["gap_report_tip"], "84cb202")
        self.assertEqual(fill["gap_report_pr"], 124)
        self.assertEqual(fill["schema_pr"], 118)
        self.assertIs(fill["invent_wall_time_sec"], False)
        self.assertIs(fill["assist_ne_fill"], True)
        self.assertEqual(fill["wall_feature_tip"], "9b6646e8")
        self.assertEqual(fill["assist"], "runtime #78 D fill checklist")
        handoff = fill["skeleton_handoff"]
        self.assertEqual(handoff["cmd"], "python3 -m runtime.iec_parity_pack skeleton")
        self.assertEqual(handoff["runtime_tip"], RUNTIME_PACK_TIP)
        self.assertEqual(handoff["docs_tip"], "63a168d")
        self.assertEqual(handoff["docs_pr"], 122)
        self.assertEqual(handoff["gap_report_tip"], "84cb202")
        self.assertEqual(handoff["gap_report_pr"], 124)
        self.assertEqual(handoff["guest_emit_tip"], GUEST_PACK_TIP)
        self.assertIs(handoff["from_json"], True)
        self.assertIs(handoff["invent_wall_time_sec"], False)
        self.assertIs(handoff["north_star_done"], False)
        self.assertEqual(skeleton_handoff_plan()["note"], handoff["note"])
        fragment = fill["fragment"]
        self.assertIn("tips", fragment)
        self.assertEqual(
            looks_like_git_tip(fragment["tips"]["guest_tip"]),
            git_head_sha(ROOT),
        )
        self.assertTrue(
            looks_like_git_tip(fragment["tips"]["panoramix_runtime_tip"])
        )
        self.assertNotIn("durable", fragment)
        self.assertEqual(pack_fill_plan()["when"], fill["when"])

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
        elapsed = plan["timeline_elapsed"]
        self.assertEqual(elapsed["runtime_tip"], "9ba95bbb")
        self.assertEqual(elapsed["docs_tip"], "5dc191cb")
        self.assertEqual(elapsed["or"], "main")
        self.assertIs(elapsed["omit_when_missing"], True)
        self.assertIs(elapsed["invent"], False)
        wall = plan["wall_elapsed"]
        self.assertEqual(wall["runtime_tip"], "9b6646e8")
        self.assertEqual(wall["docs_tip"], "6511cec7")
        self.assertEqual(wall["or"], "main")
        self.assertEqual(wall["runtime_pr"], 114)
        self.assertEqual(wall["docs_pr"], 116)
        self.assertIs(wall["omit_when_missing"], True)
        self.assertIs(wall["invent"], False)
        self.assertIs(wall["forecast"], False)
        self.assertIs(plan["handoff_docs"]["panel"], True)
        self.assertIs(plan["handoff_docs"]["second_control_plane"], False)
        self.assertIs(plan["handoff_docs"]["north_star_done"], False)
        fill = plan["pack_fill"]
        self.assertIs(fill["omit_when_missing"], True)
        self.assertIs(fill["invent"], False)
        self.assertIs(fill["writes_live_pack"], False)
        self.assertIs(fill["north_star_done"], False)
        self.assertEqual(fill["runtime_tip"], RUNTIME_PACK_TIP)
        self.assertEqual(fill["wall_feature_tip"], "9b6646e8")
        self.assertEqual(fill["runtime_pr"], 120)
        self.assertEqual(fill["docs_tip"], "63a168d")
        self.assertEqual(fill["docs_pr"], 122)
        self.assertEqual(fill["gap_report_tip"], "84cb202")
        self.assertEqual(fill["gap_report_pr"], 124)
        self.assertEqual(fill["schema_pr"], 118)
        self.assertIs(fill["invent_wall_time_sec"], False)
        self.assertEqual(
            fill["skeleton_handoff"]["cmd"],
            "python3 -m runtime.iec_parity_pack skeleton",
        )
        self.assertIs(fill["skeleton_handoff"]["invent_wall_time_sec"], False)
        self.assertNotIn("durable", fill["fragment"])
        self.assertTrue(
            looks_like_git_tip(fill["fragment"]["tips"]["panoramix_runtime_tip"])
        )
        self.assertEqual(
            looks_like_git_tip(fill["fragment"]["tips"]["guest_tip"]),
            git_head_sha(ROOT),
        )

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


class PackFillTests(unittest.TestCase):
    def test_git_head_and_resolve_order(self) -> None:
        self.assertIsNone(git_head_sha(None))
        self.assertIsNone(git_head_sha("/no/such/checkout"))
        self.assertIsNone(looks_like_git_tip("short"))
        self.assertIsNone(looks_like_git_tip("not-a-sha!!!!"))
        self.assertEqual(looks_like_git_tip("411aa68"), "411aa68")
        self.assertEqual(looks_like_git_tip("b81130f"), "b81130f")
        self.assertEqual(git_head_sha(ROOT), looks_like_git_tip(git_head_sha(ROOT)))
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            git_dir = root / ".git"
            (git_dir / "refs" / "heads").mkdir(parents=True)
            (git_dir / "HEAD").write_text("ref: refs/heads/lab\n", encoding="utf-8")
            (git_dir / "refs" / "heads" / "lab").write_text(
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n", encoding="utf-8"
            )
            self.assertEqual(
                git_head_sha(root),
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            )
            packed = root / "packed"
            (packed / ".git").mkdir(parents=True)
            (packed / ".git" / "HEAD").write_text(
                "ref: refs/heads/packed\n", encoding="utf-8"
            )
            (packed / ".git" / "packed-refs").write_text(
                "# pack-refs\n"
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb refs/heads/packed\n",
                encoding="utf-8",
            )
            self.assertEqual(
                git_head_sha(packed),
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            )
        sha, source = resolve_known_tip(
            checkout=ROOT,
            env_value="ddddddd",
            documented=RUNTIME_PACK_TIP,
        )
        self.assertEqual(sha, git_head_sha(ROOT))
        self.assertEqual(source, "checkout")
        sha, source = resolve_known_tip(
            checkout=None,
            env_value="ccccccc",
            documented=RUNTIME_PACK_TIP,
        )
        self.assertEqual(sha, "ccccccc")
        self.assertEqual(source, "env")
        sha, source = resolve_known_tip(
            checkout=None,
            env_value="",
            documented=RUNTIME_PACK_TIP,
        )
        self.assertEqual(sha, RUNTIME_PACK_TIP)
        self.assertEqual(source, "documented")
        sha, source = resolve_known_tip(checkout=None, env_value=None, documented=None)
        self.assertIsNone(sha)
        self.assertIsNone(source)

    def test_dry_run_omits_unmeasured_durable(self) -> None:
        fill = pack_fill_plan(
            guest_root=ROOT,
            runtime_root=None,
            environ={},
            hooked=False,
        )
        self.assertIs(fill["omit_when_missing"], True)
        self.assertIs(fill["invent"], False)
        self.assertIs(fill["writes_live_pack"], False)
        self.assertIs(fill["north_star_done"], False)
        self.assertIs(fill["ux_done"], False)
        self.assertIs(fill["invent_wall_time_sec"], False)
        self.assertIs(fill["assist_ne_fill"], True)
        self.assertEqual(fill["runtime_pr"], 120)
        self.assertEqual(fill["docs_tip"], "63a168d")
        self.assertEqual(fill["docs_pr"], 122)
        self.assertEqual(fill["gap_report_tip"], "84cb202")
        self.assertEqual(fill["gap_report_pr"], 124)
        self.assertEqual(fill["wall_feature_tip"], "9b6646e8")
        self.assertEqual(
            fill["skeleton_handoff"]["cmd"],
            "python3 -m runtime.iec_parity_pack skeleton",
        )
        self.assertEqual(fill["tip_sources"]["panoramix_runtime_tip"], "documented")
        self.assertEqual(fill["tip_sources"]["guest_tip"], "checkout")
        fragment = fill["fragment"]
        self.assertEqual(fragment["tips"]["panoramix_runtime_tip"], RUNTIME_PACK_TIP)
        self.assertEqual(fragment["tips"]["guest_tip"], git_head_sha(ROOT))
        self.assertNotIn("durable", fragment)
        self.assertNotIn("wall_elapsed_ms", json.dumps(fragment))
        self.assertNotIn("stage_elapsed_ms", json.dumps(fragment))

    def test_env_tips_when_no_checkout(self) -> None:
        fragment = pack_fill_fragment(
            environ={
                ENV_RUNTIME_TIP: "411aa68eeeeeee",
                ENV_GUEST_TIP: "4e2251cfffffff",
            },
            documented_runtime_tip=None,
            documented_guest_tip=None,
        )
        self.assertEqual(fragment["tips"]["panoramix_runtime_tip"], "411aa68eeeeeee")
        self.assertEqual(fragment["tips"]["guest_tip"], "4e2251cfffffff")
        self.assertNotIn("durable", fragment)

    def test_omit_tips_when_unknown(self) -> None:
        fragment = pack_fill_fragment(
            environ={},
            documented_runtime_tip=None,
            documented_guest_tip=None,
        )
        self.assertEqual(fragment, {})

    def test_measured_durable_only_when_hooked(self) -> None:
        progress = {
            "source": "durable",
            "wall_elapsed_ms": 1500,
            "timeline": [
                {"name": "admit", "elapsed_ms": 120},
                {"name": "project", "elapsed_ms": 200},
            ],
        }
        hooked = pack_fill_fragment(
            progress=progress,
            hooked=True,
            environ={},
            documented_runtime_tip=None,
            documented_guest_tip=None,
        )
        self.assertEqual(hooked["durable"]["wall_elapsed_ms"]["panoramix"], 1500)
        self.assertEqual(
            hooked["durable"]["stage_elapsed_ms"]["panoramix"],
            [120, 200],
        )
        self.assertNotIn("tips", hooked)

        not_hooked = pack_fill_fragment(
            progress=progress,
            hooked=False,
            environ={},
            documented_runtime_tip=None,
            documented_guest_tip=None,
        )
        self.assertNotIn("durable", not_hooked)

        stub = pack_fill_fragment(
            progress={
                "source": "stub",
                "wall_elapsed_ms": 9999,
                "timeline": [{"name": "admit", "elapsed_ms": 1}],
            },
            hooked=True,
            environ={},
            documented_runtime_tip=None,
            documented_guest_tip=None,
        )
        self.assertNotIn("durable", stub)
        self.assertTrue(set(hooked).issubset({"tips", "durable"}))
        self.assertNotIn("metrics", hooked)
        self.assertNotIn("wall_time_sec", json.dumps(hooked))
        self.assertNotIn("north_star_done", json.dumps(hooked))

    def test_never_invent_from_guest_clocks_or_junk(self) -> None:
        clocks = pack_fill_fragment(
            progress={
                "source": "durable",
                "created_at": "2026-09-12T00:00:00Z",
                "updated_at": "2026-09-12T00:01:00Z",
            },
            hooked=True,
            environ={},
            documented_runtime_tip=None,
            documented_guest_tip=None,
        )
        self.assertEqual(clocks, {})

        junk = pack_fill_fragment(
            progress={
                "source": "durable",
                "wall_elapsed_ms": -4,
                "timeline": [
                    {"name": "admit", "elapsed_ms": True},
                    {"name": "project"},
                ],
            },
            hooked=True,
            environ={},
            documented_runtime_tip=None,
            documented_guest_tip=None,
        )
        self.assertEqual(junk, {})

        stages_only = pack_fill_fragment(
            progress={
                "source": "durable",
                "stages": [{"name": "admit", "elapsed_ms": 80}],
            },
            hooked=True,
            environ={},
            documented_runtime_tip=None,
            documented_guest_tip=None,
        )
        self.assertNotIn("wall_elapsed_ms", stages_only.get("durable", {}))
        self.assertEqual(
            stages_only["durable"]["stage_elapsed_ms"]["panoramix"],
            [80],
        )
        self.assertTrue(set(stages_only).issubset({"tips", "durable"}))
        self.assertNotIn("metrics", stages_only)
        self.assertNotIn("wall_time_sec", json.dumps(stages_only))

    def test_skeleton_handoff_refuses_invented_walls(self) -> None:
        handoff = skeleton_handoff_plan()
        self.assertEqual(handoff["cmd"], "python3 -m runtime.iec_parity_pack skeleton")
        self.assertEqual(handoff["validate_cmd"], "python3 -m runtime.iec_parity_pack validate")
        self.assertTrue(handoff["runtime_tip"].startswith("b81130f"))
        self.assertEqual(handoff["runtime_pr"], 120)
        self.assertEqual(handoff["docs_tip"], "63a168d")
        self.assertEqual(handoff["docs_pr"], 122)
        self.assertEqual(handoff["gap_report_tip"], "84cb202")
        self.assertEqual(handoff["gap_report_pr"], 124)
        self.assertTrue(handoff["guest_emit_tip"].startswith("b859466"))
        self.assertIn("--from-json", handoff["flags"])
        self.assertIs(handoff["durable_only_when_measured"], True)
        self.assertIs(handoff["omit_when_missing"], True)
        self.assertIs(handoff["invent"], False)
        self.assertIs(handoff["invent_wall_time_sec"], False)
        self.assertIs(handoff["writes_live_pack"], False)
        self.assertIs(handoff["assist_ne_fill"], True)
        self.assertIs(handoff["north_star_done"], False)
        self.assertIn("metrics.wall_time_sec", handoff["note"])
        self.assertIn("assist ≠ fill", handoff["note"])
        self.assertNotIn("Fixes #70", handoff["note"])
        self.assertNotIn("Fixes #78", handoff["note"])


class HonestyTests(unittest.TestCase):
    def test_helpers_and_docs(self) -> None:
        helper = (ROOT / "sos" / "lab_compose.py").read_text(encoding="utf-8")
        self.assertIn("Does not close runtime", helper)
        self.assertIn("#70", helper)
        self.assertIn("#78", helper)
        self.assertIn("b81130f", helper)
        self.assertIn("63a168d", helper)
        self.assertIn("84cb202", helper)
        self.assertIn("b859466", helper)
        self.assertIn("iec_parity_pack", helper)
        self.assertIn("skeleton", helper)
        self.assertIn("metrics.wall_time_sec", helper)
        self.assertIn("pack-fill", helper)
        self.assertIn("does not write the full live pack", helper.lower())
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
            self.assertIn("9ba95bbb", text, name)
            self.assertIn("5dc191cb", text, name)
            self.assertIn("9b6646e8", text, name)
            self.assertIn("6511cec7", text, name)
            self.assertIn("b81130f", text, name)
            self.assertIn("63a168d", text, name)
            self.assertIn("84cb202", text, name)
            self.assertIn("b859466", text, name)
            self.assertIn("iec_parity_pack", text, name)
            self.assertIn("skeleton", text, name)
            self.assertIn("metrics.wall_time_sec", text, name)
            self.assertIn("wall_elapsed_ms", text, name)
            self.assertIn("compare prefers", text.lower(), name)
            self.assertIn("handoff docs", text.lower(), name)
            self.assertIn("omit when missing", text.lower(), name)
            self.assertIn("never invent", text.lower(), name)
            self.assertIn("pack_fill", text, name)
            self.assertIn("#78", text, name)
            self.assertNotIn("Fixes #70", text)
            self.assertNotIn("Fixes #78", text)
            self.assertNotIn("may not yet expose", text.lower(), name)

        lab = (ROOT / "docs" / "lab-compose.md").read_text(encoding="utf-8")
        self.assertIn("Handoff docs", lab)
        self.assertIn("timeline_elapsed", lab)
        self.assertIn("wall_elapsed", lab)
        self.assertIn("omit_when_missing", lab)
        self.assertIn("pack_fill", lab)
        self.assertIn("b81130f", lab)
        self.assertIn("63a168d", lab)
        self.assertIn("84cb202", lab)
        self.assertIn("b859466", lab)
        self.assertIn("PR #122", lab)
        self.assertIn("PR #124", lab)
        self.assertIn("gap-report ≠ Done", lab)
        self.assertIn("runtime.iec_parity_pack skeleton", lab)
        self.assertIn("--from-json", lab)
        self.assertIn("metrics.wall_time_sec", lab)
        self.assertIn("assist ≠ fill", lab)
        self.assertIn("does **not** write the full live pack", lab)
        self.assertIn("#78 D", lab)
        self.assertNotIn("may not yet expose", lab.lower())

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
        self.assertIn("- [x] Thinner lab-compose pack-fill fragment", ux)
        self.assertIn("- [x] Overnight assist smoke stamp is assist ≠ fill", ux)
        self.assertIn("- [x] Overnight gap-report smoke stamp is gap-report ≠ Done / assist ≠ fill", ux)
        self.assertIn("b81130f", ux)
        self.assertIn("63a168d", ux)
        self.assertIn("84cb202", ux)
        self.assertIn("b859466", ux)
        self.assertIn("iec_parity_pack skeleton", ux)
        self.assertIn("metrics.wall_time_sec", ux)
        self.assertIn("#78 D", ux)
        self.assertIn("does not write the live pack", ux)
        self.assertIn("- [ ] `north_star_done: true`", ux)
        self.assertNotIn("- [x] `north_star_done: true`", ux)
        self.assertIn("- [ ] Operator/actuary path", ux)
        self.assertNotIn("- [x] Operator/actuary path", ux)
        self.assertIn("does **not** mark #70 Done", ux)
        self.assertIn("9ba95bbb", ux)
        self.assertIn("verified @ `9ba95bbb`", ux)
        self.assertIn("5dc191cb", ux)
        self.assertIn("9b6646e8", ux)
        self.assertIn("verified @ `9b6646e8`", ux)
        self.assertIn("wall_elapsed_ms", ux)
        self.assertIn("- [x] Optional durable wall_elapsed_ms", ux)
        self.assertNotIn("- [x] Operator/actuary path", ux)
        self.assertNotIn("may not yet expose", ux.lower())
        self.assertIn("- [ ] `north_star_done: true`", ux)
        self.assertNotIn("- [x] Operator/actuary path", ux)


if __name__ == "__main__":
    unittest.main()
