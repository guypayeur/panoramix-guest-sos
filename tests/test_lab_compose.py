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
    COMPOSE_CATALOG_ALIASES,
    DEFAULT_BINDING_REL,
    DEFAULT_COMPOSE_CATALOG,
    DEFAULT_CTL_PORT,
    DEFAULT_GUEST_PORT,
    ENV_COMPOSE_CATALOG,
    ENV_GUEST_TIP,
    ENV_RUNTIME_TIP,
    GUEST_APPLY_METRICS_TIP,
    GUEST_APPLY_NOTES_TIP,
    GUEST_GAP_REPORT_TIP,
    GUEST_MERGE_TIP,
    GUEST_PACK_TIP,
    HONESTY_LINES,
    OPAQUE_HANDOFF_BODY,
    RUNTIME_PACK_APPLY_METRICS_DOCS_PIN,
    RUNTIME_PACK_APPLY_METRICS_PIN,
    RUNTIME_PACK_APPLY_NOTES_DOCS_PIN,
    RUNTIME_PACK_APPLY_NOTES_PIN,
    RUNTIME_PACK_DOCS_PIN,
    RUNTIME_PACK_GAP_REPORT_DOCS_PIN,
    RUNTIME_PACK_GAP_REPORT_PIN,
    RUNTIME_PACK_MERGE_DOCS_PIN,
    RUNTIME_PACK_MERGE_PIN,
    RUNTIME_PACK_TIP,
    APPLY_METRICS_CMD,
    APPLY_METRICS_FROM_DURABLE,
    APPLY_NOTES_CMD,
    GAP_REPORT_CMD,
    MERGE_CMD,
    MERGE_FROM_JSON,
    OFFBOX_IEC_PARITY_LIVE_DIR,
    OFFBOX_IEC_PARITY_LIVE_STAMP,
    OFFBOX_IEC_PARITY_PACK,
    RUNTIME_ROOT_TEMPLATE,
    elapsed_plan,
    git_head_sha,
    handoff_docs_plan,
    looks_like_git_tip,
    apply_metrics_plan,
    apply_notes_plan,
    gap_report_plan,
    merge_plan,
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
    reserve_body_for_catalog,
    resolve_compose_catalog,
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
        self.assertEqual(RUNTIME_PACK_GAP_REPORT_DOCS_PIN, "aa4f09e")
        self.assertEqual(RUNTIME_PACK_MERGE_PIN, "5086d0f")
        self.assertEqual(RUNTIME_PACK_MERGE_DOCS_PIN, "6ecb645")
        self.assertEqual(RUNTIME_PACK_APPLY_METRICS_PIN, "5d399f7")
        self.assertEqual(RUNTIME_PACK_APPLY_METRICS_DOCS_PIN, "3904ee4")
        self.assertEqual(RUNTIME_PACK_APPLY_NOTES_PIN, "48a8645")
        self.assertEqual(RUNTIME_PACK_APPLY_NOTES_DOCS_PIN, "6807509")
        self.assertEqual(GAP_REPORT_CMD, "python3 -m runtime.iec_parity_pack gap-report")
        self.assertEqual(MERGE_CMD, "python3 -m runtime.iec_parity_pack merge")
        self.assertEqual(MERGE_FROM_JSON, "--from-json -")
        self.assertEqual(APPLY_METRICS_CMD, "python3 -m runtime.iec_parity_pack apply-metrics")
        self.assertEqual(APPLY_METRICS_FROM_DURABLE, "--from-durable-panoramix")
        self.assertEqual(APPLY_NOTES_CMD, "python3 -m runtime.iec_parity_pack apply-notes")
        self.assertEqual(GUEST_GAP_REPORT_TIP, "eb48605")
        self.assertEqual(GUEST_MERGE_TIP, "39064d5")
        self.assertEqual(GUEST_APPLY_METRICS_TIP, "7c09f32")
        self.assertEqual(GUEST_APPLY_NOTES_TIP, "e5562c3")
        self.assertEqual(
            OFFBOX_IEC_PARITY_PACK,
            "~/panoramix-lab/evidence-70/iec-parity/iec-parity.json",
        )
        self.assertEqual(
            OFFBOX_IEC_PARITY_LIVE_DIR,
            "~/panoramix-lab/evidence-70/iec-parity-live-20260912/",
        )
        self.assertEqual(
            OFFBOX_IEC_PARITY_LIVE_STAMP,
            "stamp-48a8645-iec-parity-live/",
        )
        self.assertEqual(RUNTIME_ROOT_TEMPLATE, "/path/to/panoramix-runtime")
        self.assertEqual(GUEST_PACK_TIP, "b859466dcd079eb063b615728b258a686f79749a")
        self.assertTrue(GUEST_PACK_TIP.startswith("b859466"))
        self.assertEqual(recorded_reserve_body(), RECORDED_RESERVE_BODY)
        self.assertEqual(RECORDED_RESERVE_BODY["catalog"], "recorded")
        self.assertEqual(DEFAULT_COMPOSE_CATALOG, "recorded")
        self.assertEqual(ENV_COMPOSE_CATALOG, "LAB_COMPOSE_CATALOG")
        self.assertEqual(COMPOSE_CATALOG_ALIASES["parity-scale"], "parity")
        self.assertNotIn("ci", COMPOSE_CATALOG_ALIASES)
        self.assertNotIn("lab", COMPOSE_CATALOG_ALIASES)

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
        self.assertEqual(reserve_body_for_catalog(None), plan.reserve_body)
        self.assertIs(plan.north_star_done, False)
        self.assertIn("not guest→mesh ctl", plan.honesty)
        self.assertIn("north_star_done false", plan.honesty)
        self.assertIn("lab-compose catalog default recorded (CI / --dry-run unchanged)", plan.honesty)
        self.assertIn(
            "opt-in catalog live|parity (alias parity-scale) via --catalog / LAB_COMPOSE_CATALOG",
            plan.honesty,
        )
        self.assertIn("opt-in catalog is not IFRS17 / not ADSL", plan.honesty)
        self.assertIn("opt-in catalog does not stamp north_star_done", plan.honesty)
        self.assertIn("opt-in catalog does not unlock #61 / #29", plan.honesty)
        self.assertIn(
            "opt-in catalog does not invent walls or flip comparison flags",
            plan.honesty,
        )
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
        self.assertIn(
            "pack-fill gap-report docs tip aa4f09e / PR #126 (or main) links WSL gap-report stamp (gap-report ≠ Done)",
            plan.honesty,
        )
        self.assertIn(
            "pack-fill gap-report hint is cd+cmd when PANORAMIX_RUNTIME_ROOT known else copy-paste template (does not run gap-report; gap-report ≠ Done)",
            plan.honesty,
        )
        self.assertIn(
            "pack-fill merge tip 5086d0f / PR #128 (or main) names WSL merge assist-smoke stamp lineage (merge ≠ fill; merge ≠ Done; assist ≠ Done)",
            plan.honesty,
        )
        self.assertIn(
            "pack-fill merge docs tip 6ecb645 / PR #130 (or main) links WSL merge stamp (merge ≠ fill; merge ≠ Done; assist ≠ Done)",
            plan.honesty,
        )
        self.assertIn(
            "pack-fill merge hint is cd+cmd when PANORAMIX_RUNTIME_ROOT known else copy-paste template (does not run merge; merge ≠ fill; merge ≠ Done)",
            plan.honesty,
        )
        self.assertIn(
            "pack-fill merge+gap-report pairing (hint only; merge ≠ fill; merge ≠ Done; assist ≠ Done; gap-report ≠ Done)",
            plan.honesty,
        )
        self.assertIn(
            "pack-fill apply-metrics tip 5d399f7 / PR #132 (or main) names WSL apply-metrics assist-smoke stamp lineage (apply-metrics ≠ fill; apply-metrics ≠ Done; assist ≠ Done; smoke walls ≠ Done)",
            plan.honesty,
        )
        self.assertIn(
            "pack-fill apply-metrics docs tip 3904ee4 / PR #134 (or main) links WSL apply-metrics stamp (apply-metrics ≠ fill; apply-metrics ≠ Done; assist ≠ Done)",
            plan.honesty,
        )
        self.assertIn(
            "pack-fill apply-metrics hint is cd+cmd when PANORAMIX_RUNTIME_ROOT known else copy-paste template (does not run apply-metrics; does not supply wall numbers; apply-metrics ≠ fill; apply-metrics ≠ Done)",
            plan.honesty,
        )
        self.assertIn(
            "pack-fill apply-metrics+merge+gap-report pairing (hint only; apply-metrics ≠ fill; apply-metrics ≠ Done; assist ≠ Done; merge ≠ fill; merge ≠ Done; gap-report ≠ Done)",
            plan.honesty,
        )
        self.assertIn(
            "pack-fill apply-notes tip 48a8645 / PR #136 (or main) names WSL apply-notes assist-smoke stamp lineage (apply-notes ≠ fill; apply-notes ≠ Done; assist ≠ Done; smoke notes ≠ Done)",
            plan.honesty,
        )
        self.assertIn(
            "pack-fill apply-notes docs tip 6807509 / PR #138 (or main) links WSL apply-notes stamp (apply-notes ≠ fill; apply-notes ≠ Done; assist ≠ Done)",
            plan.honesty,
        )
        self.assertIn(
            "operator live #78 D pack is off-box ~/panoramix-lab/evidence-70/iec-parity-live-20260912/ with STRICT stamp-48a8645-iec-parity-live/ (live fill ≠ Done; north_star_done false; comparable false; does not unlock cloud)",
            plan.honesty,
        )
        self.assertIn(
            "pack-fill apply-notes hint is cd+cmd when PANORAMIX_RUNTIME_ROOT known else copy-paste template (does not run apply-notes; does not supply wall numbers; does not invent UX strings; apply-notes ≠ fill; apply-notes ≠ Done)",
            plan.honesty,
        )
        self.assertIn(
            "pack-fill apply-notes+apply-metrics+merge+gap-report pairing (hint only; apply-notes ≠ fill; apply-notes ≠ Done; apply-metrics ≠ fill; apply-metrics ≠ Done; assist ≠ Done; merge ≠ fill; merge ≠ Done; gap-report ≠ Done)",
            plan.honesty,
        )
        self.assertIn("never invent metrics.wall_time_sec", plan.honesty)
        self.assertIn("never invent UX strings", plan.honesty)
        self.assertIn("assist ≠ fill; assist ≠ Done", plan.honesty)
        self.assertIn("apply-notes ≠ fill; apply-notes ≠ Done", plan.honesty)
        self.assertIn("apply-metrics ≠ fill; apply-metrics ≠ Done", plan.honesty)
        self.assertIn("merge ≠ fill; merge ≠ Done", plan.honesty)
        self.assertIn("gap-report ≠ Done", plan.honesty)
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
        self.assertEqual(fill["gap_report_docs_tip"], "aa4f09e")
        self.assertEqual(fill["gap_report_docs_pr"], 126)
        self.assertEqual(fill["merge_tip"], "5086d0f")
        self.assertEqual(fill["merge_pr"], 128)
        self.assertEqual(fill["merge_docs_tip"], "6ecb645")
        self.assertEqual(fill["merge_docs_pr"], 130)
        self.assertEqual(fill["apply_metrics_tip"], "5d399f7")
        self.assertEqual(fill["apply_metrics_pr"], 132)
        self.assertEqual(fill["apply_metrics_docs_tip"], "3904ee4")
        self.assertEqual(fill["apply_metrics_docs_pr"], 134)
        self.assertEqual(fill["apply_notes_tip"], "48a8645")
        self.assertEqual(fill["apply_notes_pr"], 136)
        self.assertEqual(fill["apply_notes_docs_tip"], "6807509")
        self.assertEqual(fill["apply_notes_docs_pr"], 138)
        self.assertEqual(fill["schema_pr"], 118)
        self.assertIs(fill["invent_wall_time_sec"], False)
        self.assertIs(fill["invent_ux_strings"], False)
        self.assertIs(fill["assist_ne_fill"], True)
        self.assertIs(fill["apply_notes_ne_fill"], True)
        self.assertIs(fill["apply_notes_ne_done"], True)
        self.assertIs(fill["apply_metrics_ne_fill"], True)
        self.assertIs(fill["apply_metrics_ne_done"], True)
        self.assertIs(fill["merge_ne_fill"], True)
        self.assertIs(fill["merge_ne_done"], True)
        self.assertIs(fill["gap_report_ne_done"], True)
        self.assertEqual(fill["wall_feature_tip"], "9b6646e8")
        self.assertEqual(fill["assist"], "runtime #78 D fill checklist")
        handoff = fill["skeleton_handoff"]
        self.assertEqual(handoff["cmd"], "python3 -m runtime.iec_parity_pack skeleton")
        self.assertEqual(handoff["runtime_tip"], RUNTIME_PACK_TIP)
        self.assertEqual(handoff["docs_tip"], "63a168d")
        self.assertEqual(handoff["docs_pr"], 122)
        self.assertEqual(handoff["gap_report_tip"], "84cb202")
        self.assertEqual(handoff["gap_report_pr"], 124)
        self.assertEqual(handoff["gap_report_docs_tip"], "aa4f09e")
        self.assertEqual(handoff["gap_report_docs_pr"], 126)
        self.assertEqual(handoff["merge_tip"], "5086d0f")
        self.assertEqual(handoff["merge_pr"], 128)
        self.assertEqual(handoff["merge_docs_tip"], "6ecb645")
        self.assertEqual(handoff["merge_docs_pr"], 130)
        self.assertEqual(handoff["apply_metrics_tip"], "5d399f7")
        self.assertEqual(handoff["apply_metrics_pr"], 132)
        self.assertEqual(handoff["apply_metrics_docs_tip"], "3904ee4")
        self.assertEqual(handoff["apply_metrics_docs_pr"], 134)
        self.assertEqual(handoff["apply_notes_tip"], "48a8645")
        self.assertEqual(handoff["apply_notes_pr"], 136)
        self.assertEqual(handoff["apply_notes_docs_tip"], "6807509")
        self.assertEqual(handoff["apply_notes_docs_pr"], 138)
        self.assertEqual(handoff["guest_emit_tip"], GUEST_PACK_TIP)
        self.assertIs(handoff["from_json"], True)
        self.assertIs(handoff["invent_wall_time_sec"], False)
        self.assertIs(handoff["north_star_done"], False)
        self.assertEqual(skeleton_handoff_plan()["note"], handoff["note"])
        gap = fill["gap_report"]
        self.assertEqual(gap["cmd"], GAP_REPORT_CMD)
        self.assertEqual(gap["pack"], OFFBOX_IEC_PARITY_PACK)
        self.assertIs(gap["template"], True)
        self.assertIs(gap["runtime_root_known"], False)
        self.assertIs(gap["executes"], False)
        self.assertIs(gap["executes_in_ci"], False)
        self.assertIs(gap["invent"], False)
        self.assertIs(gap["invent_wall_time_sec"], False)
        self.assertIs(gap["writes_live_pack"], False)
        self.assertIs(gap["gap_report_ne_done"], True)
        self.assertIs(gap["north_star_done"], False)
        self.assertEqual(gap["runtime_tip"], "aa4f09e")
        self.assertEqual(gap["or"], "main")
        self.assertEqual(gap["runtime_pr"], 126)
        self.assertEqual(gap["gap_report_tip"], "84cb202")
        self.assertEqual(gap["merge_tip"], "5086d0f")
        self.assertEqual(gap["merge_docs_tip"], "6ecb645")
        self.assertEqual(gap["merge_docs_pr"], 130)
        self.assertEqual(gap["apply_metrics_tip"], "5d399f7")
        self.assertEqual(gap["apply_metrics_pr"], 132)
        self.assertEqual(gap["apply_metrics_docs_tip"], "3904ee4")
        self.assertEqual(gap["apply_metrics_docs_pr"], 134)
        self.assertEqual(gap["apply_notes_tip"], "48a8645")
        self.assertEqual(gap["apply_notes_pr"], 136)
        self.assertEqual(gap["apply_notes_docs_tip"], "6807509")
        self.assertEqual(gap["apply_notes_docs_pr"], 138)
        self.assertEqual(gap["wall_feature_tip"], "9b6646e8")
        self.assertIn("cd /path/to/panoramix-runtime", gap["hint"])
        self.assertIn(GAP_REPORT_CMD, gap["hint"])
        self.assertIn(OFFBOX_IEC_PARITY_PACK, gap["hint"])
        self.assertNotIn("wall_time_sec", json.dumps(gap["hint"]))
        self.assertEqual(gap_report_plan()["note"], gap["note"])
        merged = fill["merge"]
        self.assertEqual(merged["cmd"], MERGE_CMD)
        self.assertEqual(merged["pack"], OFFBOX_IEC_PARITY_PACK)
        self.assertEqual(merged["from_json_arg"], MERGE_FROM_JSON)
        self.assertIs(merged["from_json"], True)
        self.assertIs(merged["template"], True)
        self.assertIs(merged["runtime_root_known"], False)
        self.assertIs(merged["executes"], False)
        self.assertIs(merged["executes_in_ci"], False)
        self.assertIs(merged["invent"], False)
        self.assertIs(merged["invent_wall_time_sec"], False)
        self.assertIs(merged["writes_live_pack"], False)
        self.assertIs(merged["merge_ne_fill"], True)
        self.assertIs(merged["merge_ne_done"], True)
        self.assertIs(merged["gap_report_ne_done"], True)
        self.assertIs(merged["north_star_done"], False)
        self.assertEqual(merged["runtime_tip"], "5086d0f")
        self.assertEqual(merged["or"], "main")
        self.assertEqual(merged["runtime_pr"], 128)
        self.assertEqual(merged["merge_docs_tip"], "6ecb645")
        self.assertEqual(merged["merge_docs_pr"], 130)
        self.assertEqual(merged["apply_metrics_tip"], "5d399f7")
        self.assertEqual(merged["apply_metrics_pr"], 132)
        self.assertEqual(merged["apply_metrics_docs_tip"], "3904ee4")
        self.assertEqual(merged["apply_metrics_docs_pr"], 134)
        self.assertEqual(merged["apply_notes_tip"], "48a8645")
        self.assertEqual(merged["apply_notes_pr"], 136)
        self.assertEqual(merged["apply_notes_docs_tip"], "6807509")
        self.assertEqual(merged["apply_notes_docs_pr"], 138)
        self.assertEqual(merged["gap_report_tip"], "84cb202")
        self.assertEqual(merged["wall_feature_tip"], "9b6646e8")
        self.assertIn("cd /path/to/panoramix-runtime", merged["hint"])
        self.assertIn(MERGE_CMD, merged["hint"])
        self.assertIn("--from-json", merged["hint"])
        self.assertIn(OFFBOX_IEC_PARITY_PACK, merged["hint"])
        self.assertNotIn("wall_time_sec", json.dumps(merged["hint"]))
        self.assertEqual(merge_plan()["note"], merged["note"])
        applied = fill["apply_metrics"]
        self.assertEqual(applied["cmd"], APPLY_METRICS_CMD)
        self.assertEqual(applied["pack"], OFFBOX_IEC_PARITY_PACK)
        self.assertEqual(applied["from_durable_arg"], APPLY_METRICS_FROM_DURABLE)
        self.assertIs(applied["from_durable_panoramix"], True)
        self.assertIs(applied["template"], True)
        self.assertIs(applied["runtime_root_known"], False)
        self.assertIs(applied["executes"], False)
        self.assertIs(applied["executes_in_ci"], False)
        self.assertIs(applied["supplies_wall_numbers"], False)
        self.assertIs(applied["invent"], False)
        self.assertIs(applied["invent_wall_time_sec"], False)
        self.assertIs(applied["writes_live_pack"], False)
        self.assertIs(applied["apply_metrics_ne_fill"], True)
        self.assertIs(applied["apply_metrics_ne_done"], True)
        self.assertIs(applied["merge_ne_fill"], True)
        self.assertIs(applied["merge_ne_done"], True)
        self.assertIs(applied["gap_report_ne_done"], True)
        self.assertIs(applied["north_star_done"], False)
        self.assertEqual(applied["runtime_tip"], "5d399f7")
        self.assertEqual(applied["or"], "main")
        self.assertEqual(applied["runtime_pr"], 132)
        self.assertEqual(applied["apply_metrics_docs_tip"], "3904ee4")
        self.assertEqual(applied["apply_metrics_docs_pr"], 134)
        self.assertEqual(applied["merge_tip"], "5086d0f")
        self.assertEqual(applied["merge_docs_tip"], "6ecb645")
        self.assertEqual(applied["gap_report_tip"], "84cb202")
        self.assertEqual(applied["wall_feature_tip"], "9b6646e8")
        self.assertIn("cd /path/to/panoramix-runtime", applied["hint"])
        self.assertIn(APPLY_METRICS_CMD, applied["hint"])
        self.assertIn("--from-durable-panoramix", applied["hint"])
        self.assertIn(OFFBOX_IEC_PARITY_PACK, applied["hint"])
        self.assertNotIn("wall_time_sec", json.dumps(applied["hint"]))
        self.assertEqual(apply_metrics_plan()["note"], applied["note"])
        noted = fill["apply_notes"]
        self.assertEqual(noted["cmd"], APPLY_NOTES_CMD)
        self.assertEqual(noted["pack"], OFFBOX_IEC_PARITY_PACK)
        self.assertIs(noted["template"], True)
        self.assertIs(noted["runtime_root_known"], False)
        self.assertIs(noted["executes"], False)
        self.assertIs(noted["executes_in_ci"], False)
        self.assertIs(noted["supplies_wall_numbers"], False)
        self.assertIs(noted["invents_ux_strings"], False)
        self.assertIs(noted["invent"], False)
        self.assertIs(noted["invent_wall_time_sec"], False)
        self.assertIs(noted["invent_ux_strings"], False)
        self.assertIs(noted["writes_live_pack"], False)
        self.assertIs(noted["apply_notes_ne_fill"], True)
        self.assertIs(noted["apply_notes_ne_done"], True)
        self.assertIs(noted["apply_metrics_ne_fill"], True)
        self.assertIs(noted["apply_metrics_ne_done"], True)
        self.assertIs(noted["merge_ne_fill"], True)
        self.assertIs(noted["merge_ne_done"], True)
        self.assertIs(noted["gap_report_ne_done"], True)
        self.assertIs(noted["north_star_done"], False)
        self.assertEqual(noted["runtime_tip"], "48a8645")
        self.assertEqual(noted["apply_notes_docs_tip"], "6807509")
        self.assertEqual(noted["apply_notes_docs_pr"], 138)
        self.assertEqual(noted["or"], "main")
        self.assertEqual(noted["runtime_pr"], 136)
        self.assertEqual(noted["apply_metrics_tip"], "5d399f7")
        self.assertEqual(noted["apply_metrics_docs_tip"], "3904ee4")
        self.assertEqual(noted["merge_tip"], "5086d0f")
        self.assertEqual(noted["gap_report_tip"], "84cb202")
        self.assertEqual(noted["wall_feature_tip"], "9b6646e8")
        self.assertIn("cd /path/to/panoramix-runtime", noted["hint"])
        self.assertIn(APPLY_NOTES_CMD, noted["hint"])
        self.assertIn(OFFBOX_IEC_PARITY_PACK, noted["hint"])
        self.assertNotIn("wall_time_sec", json.dumps(noted["hint"]))
        self.assertNotIn("failure_clarity", noted["hint"])
        self.assertEqual(apply_notes_plan()["note"], noted["note"])
        live = fill["operator_live_pack"]
        self.assertEqual(live["path"], OFFBOX_IEC_PARITY_LIVE_DIR)
        self.assertEqual(live["strict_stamp"], OFFBOX_IEC_PARITY_LIVE_STAMP)
        self.assertIs(live["off_box"], True)
        self.assertIs(live["live_fill_ne_done"], True)
        self.assertIs(live["north_star_done"], False)
        self.assertIs(live["comparable"], False)
        self.assertIs(live["unlocks_cloud"], False)
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


class ComposeCatalogTests(unittest.TestCase):
    def test_resolve_recorded_live_parity_and_alias(self) -> None:
        self.assertEqual(resolve_compose_catalog(None), "recorded")
        self.assertEqual(resolve_compose_catalog(""), "recorded")
        self.assertEqual(resolve_compose_catalog("  recorded  "), "recorded")
        self.assertEqual(resolve_compose_catalog("LIVE"), "live")
        self.assertEqual(resolve_compose_catalog("parity"), "parity")
        self.assertEqual(resolve_compose_catalog("parity-scale"), "parity")
        self.assertEqual(resolve_compose_catalog("PARITY-SCALE"), "parity")

    def test_reject_unknown_and_handoff_extras(self) -> None:
        for bad in ("ifrs17", "adsl", "ci", "small", "lab", "heavy", "parity_scale"):
            with self.assertRaises(ValueError) as ctx:
                resolve_compose_catalog(bad)
            self.assertIn("recorded|live|parity", str(ctx.exception))
            self.assertIn("parity-scale", str(ctx.exception))

    def test_reserve_body_selection(self) -> None:
        self.assertEqual(
            reserve_body_for_catalog(),
            {"demo": "reserve", "catalog": "recorded"},
        )
        self.assertEqual(reserve_body_for_catalog(), recorded_reserve_body())
        self.assertEqual(
            reserve_body_for_catalog("live"),
            {"demo": "reserve", "catalog": "live"},
        )
        self.assertEqual(
            reserve_body_for_catalog("parity-scale"),
            {"demo": "reserve", "catalog": "parity"},
        )
        plan = build_compose_plan(guest_root=ROOT, catalog="parity")
        self.assertEqual(plan.reserve_body, {"demo": "reserve", "catalog": "parity"})
        self.assertIs(plan.north_star_done, False)
        parsed = json.loads(plan_json(plan))
        self.assertEqual(parsed["reserve_body"]["catalog"], "parity")
        self.assertIs(parsed["north_star_done"], False)
        self.assertIs(parsed["pack_fill"]["operator_live_pack"]["comparable"], False)
        with self.assertRaises(ValueError):
            build_compose_plan(guest_root=ROOT, catalog="ifrs17")


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
        self.assertEqual(plan["reserve_body"], {"demo": "reserve", "catalog": "recorded"})
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
        self.assertEqual(fill["gap_report_docs_tip"], "aa4f09e")
        self.assertEqual(fill["gap_report_docs_pr"], 126)
        self.assertEqual(fill["merge_tip"], "5086d0f")
        self.assertEqual(fill["merge_pr"], 128)
        self.assertEqual(fill["merge_docs_tip"], "6ecb645")
        self.assertEqual(fill["merge_docs_pr"], 130)
        self.assertEqual(fill["apply_metrics_tip"], "5d399f7")
        self.assertEqual(fill["apply_metrics_pr"], 132)
        self.assertEqual(fill["apply_metrics_docs_tip"], "3904ee4")
        self.assertEqual(fill["apply_metrics_docs_pr"], 134)
        self.assertEqual(fill["apply_notes_tip"], "48a8645")
        self.assertEqual(fill["apply_notes_pr"], 136)
        self.assertEqual(fill["apply_notes_docs_tip"], "6807509")
        self.assertEqual(fill["apply_notes_docs_pr"], 138)
        self.assertEqual(fill["schema_pr"], 118)
        self.assertIs(fill["invent_wall_time_sec"], False)
        self.assertIs(fill["invent_ux_strings"], False)
        self.assertIs(fill["apply_notes_ne_fill"], True)
        self.assertIs(fill["apply_notes_ne_done"], True)
        self.assertIs(fill["apply_metrics_ne_fill"], True)
        self.assertIs(fill["apply_metrics_ne_done"], True)
        self.assertIs(fill["merge_ne_fill"], True)
        self.assertIs(fill["merge_ne_done"], True)
        self.assertEqual(
            fill["skeleton_handoff"]["cmd"],
            "python3 -m runtime.iec_parity_pack skeleton",
        )
        self.assertIs(fill["skeleton_handoff"]["invent_wall_time_sec"], False)
        merged = fill["merge"]
        self.assertEqual(merged["cmd"], MERGE_CMD)
        self.assertIs(merged["executes"], False)
        self.assertIs(merged["executes_in_ci"], False)
        self.assertIs(merged["invent"], False)
        self.assertIs(merged["invent_wall_time_sec"], False)
        self.assertIs(merged["writes_live_pack"], False)
        self.assertIs(merged["merge_ne_fill"], True)
        self.assertIs(merged["merge_ne_done"], True)
        self.assertEqual(merged["runtime_tip"], "5086d0f")
        self.assertEqual(merged["merge_docs_tip"], "6ecb645")
        self.assertEqual(merged["gap_report_tip"], "84cb202")
        self.assertEqual(merged["wall_feature_tip"], "9b6646e8")
        self.assertIn("--from-json", merged["hint"])
        if plan.get("runtime_root"):
            self.assertIs(merged["runtime_root_known"], True)
            self.assertIs(merged["template"], False)
            self.assertIn(f"cd {plan['runtime_root']}", merged["hint"])
        else:
            self.assertIs(merged["template"], True)
            self.assertIs(merged["runtime_root_known"], False)
            self.assertIn("cd /path/to/panoramix-runtime", merged["hint"])
        self.assertIn(MERGE_CMD, merged["hint"])
        self.assertIn(OFFBOX_IEC_PARITY_PACK, merged["hint"])
        applied = fill["apply_metrics"]
        self.assertEqual(applied["cmd"], APPLY_METRICS_CMD)
        self.assertIs(applied["executes"], False)
        self.assertIs(applied["executes_in_ci"], False)
        self.assertIs(applied["supplies_wall_numbers"], False)
        self.assertIs(applied["invent"], False)
        self.assertIs(applied["invent_wall_time_sec"], False)
        self.assertIs(applied["writes_live_pack"], False)
        self.assertIs(applied["apply_metrics_ne_fill"], True)
        self.assertIs(applied["apply_metrics_ne_done"], True)
        self.assertEqual(applied["runtime_tip"], "5d399f7")
        self.assertEqual(applied["apply_metrics_docs_tip"], "3904ee4")
        self.assertEqual(applied["merge_tip"], "5086d0f")
        self.assertEqual(applied["gap_report_tip"], "84cb202")
        self.assertEqual(applied["wall_feature_tip"], "9b6646e8")
        self.assertIn("--from-durable-panoramix", applied["hint"])
        if plan.get("runtime_root"):
            self.assertIs(applied["runtime_root_known"], True)
            self.assertIs(applied["template"], False)
            self.assertIn(f"cd {plan['runtime_root']}", applied["hint"])
        else:
            self.assertIs(applied["template"], True)
            self.assertIs(applied["runtime_root_known"], False)
            self.assertIn("cd /path/to/panoramix-runtime", applied["hint"])
        self.assertIn(APPLY_METRICS_CMD, applied["hint"])
        self.assertIn(OFFBOX_IEC_PARITY_PACK, applied["hint"])
        noted = fill["apply_notes"]
        self.assertEqual(noted["cmd"], APPLY_NOTES_CMD)
        self.assertIs(noted["executes"], False)
        self.assertIs(noted["executes_in_ci"], False)
        self.assertIs(noted["supplies_wall_numbers"], False)
        self.assertIs(noted["invents_ux_strings"], False)
        self.assertIs(noted["invent"], False)
        self.assertIs(noted["invent_wall_time_sec"], False)
        self.assertIs(noted["writes_live_pack"], False)
        self.assertIs(noted["apply_notes_ne_fill"], True)
        self.assertIs(noted["apply_notes_ne_done"], True)
        self.assertEqual(noted["runtime_tip"], "48a8645")
        self.assertEqual(noted["apply_notes_docs_tip"], "6807509")
        self.assertEqual(noted["apply_notes_docs_pr"], 138)
        self.assertEqual(noted["apply_metrics_tip"], "5d399f7")
        self.assertEqual(noted["merge_tip"], "5086d0f")
        self.assertEqual(noted["gap_report_tip"], "84cb202")
        self.assertEqual(noted["wall_feature_tip"], "9b6646e8")
        if plan.get("runtime_root"):
            self.assertIs(noted["runtime_root_known"], True)
            self.assertIs(noted["template"], False)
            self.assertIn(f"cd {plan['runtime_root']}", noted["hint"])
        else:
            self.assertIs(noted["template"], True)
            self.assertIs(noted["runtime_root_known"], False)
            self.assertIn("cd /path/to/panoramix-runtime", noted["hint"])
        self.assertIn(APPLY_NOTES_CMD, noted["hint"])
        self.assertIn(OFFBOX_IEC_PARITY_PACK, noted["hint"])
        self.assertNotIn("wall_time_sec", noted["hint"])
        self.assertNotIn("failure_clarity", noted["hint"])
        gap = fill["gap_report"]
        self.assertEqual(gap["cmd"], GAP_REPORT_CMD)
        self.assertIs(gap["executes"], False)
        self.assertIs(gap["executes_in_ci"], False)
        self.assertIs(gap["invent"], False)
        self.assertIs(gap["invent_wall_time_sec"], False)
        self.assertIs(gap["writes_live_pack"], False)
        self.assertIs(gap["gap_report_ne_done"], True)
        self.assertEqual(gap["runtime_tip"], "aa4f09e")
        self.assertEqual(gap["gap_report_tip"], "84cb202")
        self.assertEqual(gap["wall_feature_tip"], "9b6646e8")
        if plan.get("runtime_root"):
            self.assertIs(gap["runtime_root_known"], True)
            self.assertIs(gap["template"], False)
            self.assertIn(f"cd {plan['runtime_root']}", gap["hint"])
        else:
            self.assertIs(gap["template"], True)
            self.assertIs(gap["runtime_root_known"], False)
            self.assertIn("cd /path/to/panoramix-runtime", gap["hint"])
        self.assertIn(GAP_REPORT_CMD, gap["hint"])
        self.assertIn(OFFBOX_IEC_PARITY_PACK, gap["hint"])
        self.assertNotIn("durable", fill["fragment"])
        self.assertTrue(
            looks_like_git_tip(fill["fragment"]["tips"]["panoramix_runtime_tip"])
        )
        self.assertEqual(
            looks_like_git_tip(fill["fragment"]["tips"]["guest_tip"]),
            git_head_sha(ROOT),
        )

    def test_dry_run_catalog_flag_and_env(self) -> None:
        recorded = subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        recorded_plan = json.loads(recorded.stdout)
        self.assertEqual(
            recorded_plan["reserve_body"],
            {"demo": "reserve", "catalog": "recorded"},
        )

        parity = subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run", "--catalog", "parity"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(parity.returncode, 0, parity.stderr)
        parity_plan = json.loads(parity.stdout)
        self.assertEqual(
            parity_plan["reserve_body"],
            {"demo": "reserve", "catalog": "parity"},
        )
        self.assertIs(parity_plan["north_star_done"], False)
        self.assertTrue(readmit_smokes_honest(parity_plan["readmit_smoke"]))

        alias = subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run", "--catalog", "parity-scale"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(alias.returncode, 0, alias.stderr)
        self.assertEqual(json.loads(alias.stdout)["reserve_body"]["catalog"], "parity")

        env = dict(__import__("os").environ)
        env[ENV_COMPOSE_CATALOG] = "live"
        from_env = subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        self.assertEqual(from_env.returncode, 0, from_env.stderr)
        self.assertEqual(json.loads(from_env.stdout)["reserve_body"]["catalog"], "live")

        override = subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run", "--catalog", "recorded"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        self.assertEqual(override.returncode, 0, override.stderr)
        self.assertEqual(
            json.loads(override.stdout)["reserve_body"]["catalog"],
            "recorded",
        )

        bad = subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run", "--catalog", "ifrs17"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("recorded|live|parity", bad.stderr)

        env_bad = dict(__import__("os").environ)
        env_bad[ENV_COMPOSE_CATALOG] = "adsl"
        bad_env = subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            env=env_bad,
        )
        self.assertNotEqual(bad_env.returncode, 0)
        self.assertIn("recorded|live|parity", bad_env.stderr)

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
        self.assertEqual(fill["gap_report_docs_tip"], "aa4f09e")
        self.assertEqual(fill["gap_report_docs_pr"], 126)
        self.assertEqual(fill["merge_tip"], "5086d0f")
        self.assertEqual(fill["merge_pr"], 128)
        self.assertEqual(fill["merge_docs_tip"], "6ecb645")
        self.assertEqual(fill["merge_docs_pr"], 130)
        self.assertEqual(fill["apply_metrics_tip"], "5d399f7")
        self.assertEqual(fill["apply_metrics_pr"], 132)
        self.assertEqual(fill["apply_metrics_docs_tip"], "3904ee4")
        self.assertEqual(fill["apply_metrics_docs_pr"], 134)
        self.assertEqual(fill["apply_notes_tip"], "48a8645")
        self.assertEqual(fill["apply_notes_pr"], 136)
        self.assertEqual(fill["apply_notes_docs_tip"], "6807509")
        self.assertEqual(fill["apply_notes_docs_pr"], 138)
        self.assertIs(fill["apply_notes_ne_fill"], True)
        self.assertIs(fill["apply_notes_ne_done"], True)
        self.assertIs(fill["apply_metrics_ne_fill"], True)
        self.assertIs(fill["apply_metrics_ne_done"], True)
        self.assertIs(fill["merge_ne_fill"], True)
        self.assertIs(fill["merge_ne_done"], True)
        self.assertIs(fill["gap_report_ne_done"], True)
        self.assertEqual(fill["wall_feature_tip"], "9b6646e8")
        self.assertEqual(
            fill["skeleton_handoff"]["cmd"],
            "python3 -m runtime.iec_parity_pack skeleton",
        )
        gap = fill["gap_report"]
        self.assertEqual(gap["cmd"], GAP_REPORT_CMD)
        self.assertIs(gap["template"], True)
        self.assertIs(gap["executes"], False)
        self.assertIs(gap["invent"], False)
        self.assertIs(gap["invent_wall_time_sec"], False)
        self.assertEqual(gap["runtime_tip"], "aa4f09e")
        self.assertEqual(gap["gap_report_tip"], "84cb202")
        self.assertEqual(gap["wall_feature_tip"], "9b6646e8")
        self.assertIn("cd /path/to/panoramix-runtime", gap["hint"])
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
        self.assertEqual(handoff["gap_report_docs_tip"], "aa4f09e")
        self.assertEqual(handoff["gap_report_docs_pr"], 126)
        self.assertEqual(handoff["merge_tip"], "5086d0f")
        self.assertEqual(handoff["merge_pr"], 128)
        self.assertEqual(handoff["merge_docs_tip"], "6ecb645")
        self.assertEqual(handoff["merge_docs_pr"], 130)
        self.assertEqual(handoff["apply_metrics_tip"], "5d399f7")
        self.assertEqual(handoff["apply_metrics_pr"], 132)
        self.assertEqual(handoff["apply_metrics_docs_tip"], "3904ee4")
        self.assertEqual(handoff["apply_metrics_docs_pr"], 134)
        self.assertEqual(handoff["apply_notes_tip"], "48a8645")
        self.assertEqual(handoff["apply_notes_pr"], 136)
        self.assertEqual(handoff["apply_notes_docs_tip"], "6807509")
        self.assertEqual(handoff["apply_notes_docs_pr"], 138)
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

    def test_gap_report_hint_template_and_known_root(self) -> None:
        hint = gap_report_plan()
        self.assertEqual(hint["cmd"], GAP_REPORT_CMD)
        self.assertEqual(hint["pack"], OFFBOX_IEC_PARITY_PACK)
        self.assertEqual(hint["cd"], RUNTIME_ROOT_TEMPLATE)
        self.assertIs(hint["template"], True)
        self.assertIs(hint["runtime_root_known"], False)
        self.assertIs(hint["executes"], False)
        self.assertIs(hint["executes_in_ci"], False)
        self.assertIs(hint["invent"], False)
        self.assertIs(hint["invent_wall_time_sec"], False)
        self.assertIs(hint["forecast"], False)
        self.assertIs(hint["ifrs17"], False)
        self.assertIs(hint["iec_spa"], False)
        self.assertIs(hint["writes_live_pack"], False)
        self.assertIs(hint["assist_ne_fill"], True)
        self.assertIs(hint["gap_report_ne_done"], True)
        self.assertIs(hint["north_star_done"], False)
        self.assertEqual(hint["runtime_tip"], "aa4f09e")
        self.assertEqual(hint["or"], "main")
        self.assertEqual(hint["runtime_pr"], 126)
        self.assertEqual(hint["gap_report_tip"], "84cb202")
        self.assertEqual(hint["gap_report_pr"], 124)
        self.assertEqual(hint["merge_tip"], "5086d0f")
        self.assertEqual(hint["merge_docs_tip"], "6ecb645")
        self.assertEqual(hint["merge_docs_pr"], 130)
        self.assertEqual(hint["apply_metrics_tip"], "5d399f7")
        self.assertEqual(hint["apply_metrics_pr"], 132)
        self.assertEqual(hint["apply_metrics_docs_tip"], "3904ee4")
        self.assertEqual(hint["apply_metrics_docs_pr"], 134)
        self.assertEqual(hint["apply_notes_tip"], "48a8645")
        self.assertEqual(hint["apply_notes_pr"], 136)
        self.assertEqual(hint["apply_notes_docs_tip"], "6807509")
        self.assertEqual(hint["apply_notes_docs_pr"], 138)
        self.assertEqual(hint["wall_feature_tip"], "9b6646e8")
        self.assertEqual(
            hint["hint"],
            f"cd {RUNTIME_ROOT_TEMPLATE} && {GAP_REPORT_CMD} {OFFBOX_IEC_PARITY_PACK}",
        )
        self.assertIn("merge+gap-report", hint["note"])
        self.assertIn("gap-report ≠ Done", hint["note"])
        self.assertIn("assist ≠ fill", hint["note"])
        self.assertIn("does not run gap-report", hint["note"])
        self.assertNotIn("Fixes #70", hint["note"])
        self.assertNotIn("Fixes #78", hint["note"])
        self.assertNotIn("wall_time_sec", hint["hint"])
        blob = json.dumps(hint)
        self.assertNotIn("Fixes #70", blob)
        self.assertNotIn("Fixes #78", blob)

        known = gap_report_plan(runtime_root="/opt/panoramix-runtime")
        self.assertIs(known["template"], False)
        self.assertIs(known["runtime_root_known"], True)
        self.assertEqual(known["cd"], "/opt/panoramix-runtime")
        self.assertEqual(
            known["hint"],
            f"cd /opt/panoramix-runtime && {GAP_REPORT_CMD} {OFFBOX_IEC_PARITY_PACK}",
        )
        self.assertIs(known["executes"], False)
        self.assertIs(known["invent"], False)
        self.assertIs(known["invent_wall_time_sec"], False)
        self.assertEqual(known["runtime_tip"], "aa4f09e")
        self.assertEqual(known["gap_report_tip"], "84cb202")
        self.assertEqual(known["merge_tip"], "5086d0f")
        self.assertEqual(known["merge_docs_tip"], "6ecb645")
        self.assertEqual(known["apply_metrics_tip"], "5d399f7")
        self.assertEqual(known["apply_metrics_docs_tip"], "3904ee4")
        self.assertEqual(known["apply_notes_tip"], "48a8645")
        self.assertEqual(known["apply_notes_docs_tip"], "6807509")
        self.assertEqual(known["apply_notes_docs_pr"], 138)
        self.assertEqual(known["wall_feature_tip"], "9b6646e8")

        fill = pack_fill_plan(
            guest_root=ROOT,
            runtime_root="/opt/panoramix-runtime",
            environ={},
            hooked=False,
        )
        self.assertEqual(fill["gap_report"]["hint"], known["hint"])
        self.assertIs(fill["gap_report"]["runtime_root_known"], True)
        self.assertEqual(fill["merge"]["hint"], merge_plan(runtime_root="/opt/panoramix-runtime")["hint"])
        self.assertIs(fill["merge"]["runtime_root_known"], True)
        self.assertEqual(
            fill["apply_metrics"]["hint"],
            apply_metrics_plan(runtime_root="/opt/panoramix-runtime")["hint"],
        )
        self.assertIs(fill["apply_metrics"]["runtime_root_known"], True)
        self.assertEqual(
            fill["apply_notes"]["hint"],
            apply_notes_plan(runtime_root="/opt/panoramix-runtime")["hint"],
        )
        self.assertIs(fill["apply_notes"]["runtime_root_known"], True)
        self.assertNotIn("durable", fill["fragment"])
        self.assertNotIn("wall_time_sec", json.dumps(fill["fragment"]))

    def test_merge_hint_template_and_known_root(self) -> None:
        hint = merge_plan()
        self.assertEqual(hint["cmd"], MERGE_CMD)
        self.assertEqual(hint["pack"], OFFBOX_IEC_PARITY_PACK)
        self.assertEqual(hint["from_json_arg"], MERGE_FROM_JSON)
        self.assertIs(hint["from_json"], True)
        self.assertEqual(hint["cd"], RUNTIME_ROOT_TEMPLATE)
        self.assertIs(hint["template"], True)
        self.assertIs(hint["runtime_root_known"], False)
        self.assertIs(hint["executes"], False)
        self.assertIs(hint["executes_in_ci"], False)
        self.assertIs(hint["invent"], False)
        self.assertIs(hint["invent_wall_time_sec"], False)
        self.assertIs(hint["forecast"], False)
        self.assertIs(hint["ifrs17"], False)
        self.assertIs(hint["iec_spa"], False)
        self.assertIs(hint["writes_live_pack"], False)
        self.assertIs(hint["assist_ne_fill"], True)
        self.assertIs(hint["merge_ne_fill"], True)
        self.assertIs(hint["merge_ne_done"], True)
        self.assertIs(hint["gap_report_ne_done"], True)
        self.assertIs(hint["north_star_done"], False)
        self.assertEqual(hint["runtime_tip"], "5086d0f")
        self.assertEqual(hint["or"], "main")
        self.assertEqual(hint["runtime_pr"], 128)
        self.assertEqual(hint["merge_docs_tip"], "6ecb645")
        self.assertEqual(hint["merge_docs_pr"], 130)
        self.assertEqual(hint["apply_metrics_tip"], "5d399f7")
        self.assertEqual(hint["apply_metrics_pr"], 132)
        self.assertEqual(hint["apply_metrics_docs_tip"], "3904ee4")
        self.assertEqual(hint["apply_metrics_docs_pr"], 134)
        self.assertEqual(hint["apply_notes_tip"], "48a8645")
        self.assertEqual(hint["apply_notes_pr"], 136)
        self.assertEqual(hint["apply_notes_docs_tip"], "6807509")
        self.assertEqual(hint["apply_notes_docs_pr"], 138)
        self.assertEqual(hint["gap_report_tip"], "84cb202")
        self.assertEqual(hint["gap_report_pr"], 124)
        self.assertEqual(hint["wall_feature_tip"], "9b6646e8")
        self.assertEqual(hint["guest_gap_report_tip"], "eb48605")
        self.assertEqual(
            hint["hint"],
            f"cd {RUNTIME_ROOT_TEMPLATE} && {MERGE_CMD} {OFFBOX_IEC_PARITY_PACK} {MERGE_FROM_JSON}",
        )
        self.assertIn("--from-json", hint["hint"])
        self.assertIn("merge+gap-report", hint["note"])
        self.assertIn("merge ≠ fill", hint["note"])
        self.assertIn("merge ≠ Done", hint["note"])
        self.assertIn("assist ≠ Done", hint["note"])
        self.assertIn("gap-report ≠ Done", hint["note"])
        self.assertIn("does not run merge", hint["note"])
        self.assertNotIn("Fixes #70", hint["note"])
        self.assertNotIn("Fixes #78", hint["note"])
        self.assertNotIn("wall_time_sec", hint["hint"])
        blob = json.dumps(hint)
        self.assertNotIn("Fixes #70", blob)
        self.assertNotIn("Fixes #78", blob)

        known = merge_plan(runtime_root="/opt/panoramix-runtime")
        self.assertIs(known["template"], False)
        self.assertIs(known["runtime_root_known"], True)
        self.assertEqual(known["cd"], "/opt/panoramix-runtime")
        self.assertEqual(
            known["hint"],
            f"cd /opt/panoramix-runtime && {MERGE_CMD} {OFFBOX_IEC_PARITY_PACK} {MERGE_FROM_JSON}",
        )
        self.assertIs(known["executes"], False)
        self.assertIs(known["invent"], False)
        self.assertIs(known["invent_wall_time_sec"], False)
        self.assertEqual(known["runtime_tip"], "5086d0f")
        self.assertEqual(known["merge_docs_tip"], "6ecb645")
        self.assertEqual(known["apply_metrics_tip"], "5d399f7")
        self.assertEqual(known["apply_metrics_docs_tip"], "3904ee4")
        self.assertEqual(known["apply_notes_tip"], "48a8645")
        self.assertEqual(known["apply_notes_docs_tip"], "6807509")
        self.assertEqual(known["apply_notes_docs_pr"], 138)
        self.assertEqual(known["gap_report_tip"], "84cb202")
        self.assertEqual(known["wall_feature_tip"], "9b6646e8")

        fill = pack_fill_plan(
            guest_root=ROOT,
            runtime_root="/opt/panoramix-runtime",
            environ={},
            hooked=False,
        )
        self.assertEqual(fill["merge"]["hint"], known["hint"])
        self.assertIs(fill["merge"]["runtime_root_known"], True)
        self.assertNotIn("durable", fill["fragment"])
        self.assertNotIn("wall_time_sec", json.dumps(fill["fragment"]))

    def test_apply_metrics_hint_template_and_known_root(self) -> None:
        hint = apply_metrics_plan()
        self.assertEqual(hint["cmd"], APPLY_METRICS_CMD)
        self.assertEqual(hint["pack"], OFFBOX_IEC_PARITY_PACK)
        self.assertEqual(hint["from_durable_arg"], APPLY_METRICS_FROM_DURABLE)
        self.assertIs(hint["from_durable_panoramix"], True)
        self.assertEqual(hint["cd"], RUNTIME_ROOT_TEMPLATE)
        self.assertIs(hint["template"], True)
        self.assertIs(hint["runtime_root_known"], False)
        self.assertIs(hint["executes"], False)
        self.assertIs(hint["executes_in_ci"], False)
        self.assertIs(hint["supplies_wall_numbers"], False)
        self.assertIs(hint["invent"], False)
        self.assertIs(hint["invent_wall_time_sec"], False)
        self.assertIs(hint["forecast"], False)
        self.assertIs(hint["ifrs17"], False)
        self.assertIs(hint["iec_spa"], False)
        self.assertIs(hint["writes_live_pack"], False)
        self.assertIs(hint["assist_ne_fill"], True)
        self.assertIs(hint["apply_metrics_ne_fill"], True)
        self.assertIs(hint["apply_metrics_ne_done"], True)
        self.assertIs(hint["merge_ne_fill"], True)
        self.assertIs(hint["merge_ne_done"], True)
        self.assertIs(hint["gap_report_ne_done"], True)
        self.assertIs(hint["north_star_done"], False)
        self.assertEqual(hint["runtime_tip"], "5d399f7")
        self.assertEqual(hint["or"], "main")
        self.assertEqual(hint["runtime_pr"], 132)
        self.assertEqual(hint["apply_metrics_docs_tip"], "3904ee4")
        self.assertEqual(hint["apply_metrics_docs_pr"], 134)
        self.assertEqual(hint["apply_notes_tip"], "48a8645")
        self.assertEqual(hint["apply_notes_pr"], 136)
        self.assertEqual(hint["apply_notes_docs_tip"], "6807509")
        self.assertEqual(hint["apply_notes_docs_pr"], 138)
        self.assertEqual(hint["merge_tip"], "5086d0f")
        self.assertEqual(hint["merge_pr"], 128)
        self.assertEqual(hint["merge_docs_tip"], "6ecb645")
        self.assertEqual(hint["gap_report_tip"], "84cb202")
        self.assertEqual(hint["gap_report_pr"], 124)
        self.assertEqual(hint["wall_feature_tip"], "9b6646e8")
        self.assertEqual(hint["guest_merge_tip"], "39064d5")
        self.assertEqual(
            hint["hint"],
            f"cd {RUNTIME_ROOT_TEMPLATE} && {APPLY_METRICS_CMD} "
            f"{OFFBOX_IEC_PARITY_PACK} {APPLY_METRICS_FROM_DURABLE}",
        )
        self.assertIn("--from-durable-panoramix", hint["hint"])
        self.assertIn("apply-metrics+merge+gap-report", hint["note"])
        self.assertIn("apply-metrics ≠ fill", hint["note"])
        self.assertIn("apply-metrics ≠ Done", hint["note"])
        self.assertIn("assist ≠ Done", hint["note"])
        self.assertIn("does not run apply-metrics", hint["note"])
        self.assertIn("does not supply wall numbers", hint["note"])
        self.assertNotIn("Fixes #70", hint["note"])
        self.assertNotIn("Fixes #78", hint["note"])
        self.assertNotIn("wall_time_sec", hint["hint"])
        blob = json.dumps(hint)
        self.assertNotIn("Fixes #70", blob)
        self.assertNotIn("Fixes #78", blob)
        self.assertNotRegex(hint["hint"], r"\b\d+\.\d+\b")

        known = apply_metrics_plan(runtime_root="/opt/panoramix-runtime")
        self.assertIs(known["template"], False)
        self.assertIs(known["runtime_root_known"], True)
        self.assertEqual(known["cd"], "/opt/panoramix-runtime")
        self.assertEqual(
            known["hint"],
            f"cd /opt/panoramix-runtime && {APPLY_METRICS_CMD} "
            f"{OFFBOX_IEC_PARITY_PACK} {APPLY_METRICS_FROM_DURABLE}",
        )
        self.assertIs(known["executes"], False)
        self.assertIs(known["supplies_wall_numbers"], False)
        self.assertIs(known["invent"], False)
        self.assertIs(known["invent_wall_time_sec"], False)
        self.assertEqual(known["runtime_tip"], "5d399f7")
        self.assertEqual(known["apply_metrics_docs_tip"], "3904ee4")
        self.assertEqual(known["apply_notes_tip"], "48a8645")
        self.assertEqual(known["apply_notes_docs_tip"], "6807509")
        self.assertEqual(known["apply_notes_docs_pr"], 138)
        self.assertEqual(known["merge_tip"], "5086d0f")
        self.assertEqual(known["gap_report_tip"], "84cb202")
        self.assertEqual(known["wall_feature_tip"], "9b6646e8")

        fill = pack_fill_plan(
            guest_root=ROOT,
            runtime_root="/opt/panoramix-runtime",
            environ={},
            hooked=False,
        )
        self.assertEqual(fill["apply_metrics"]["hint"], known["hint"])
        self.assertIs(fill["apply_metrics"]["runtime_root_known"], True)
        self.assertNotIn("durable", fill["fragment"])
        self.assertNotIn("wall_time_sec", json.dumps(fill["fragment"]))

    def test_apply_notes_hint_template_and_known_root(self) -> None:
        hint = apply_notes_plan()
        self.assertEqual(hint["cmd"], APPLY_NOTES_CMD)
        self.assertEqual(hint["pack"], OFFBOX_IEC_PARITY_PACK)
        self.assertEqual(hint["cd"], RUNTIME_ROOT_TEMPLATE)
        self.assertIs(hint["template"], True)
        self.assertIs(hint["runtime_root_known"], False)
        self.assertIs(hint["executes"], False)
        self.assertIs(hint["executes_in_ci"], False)
        self.assertIs(hint["supplies_wall_numbers"], False)
        self.assertIs(hint["invents_ux_strings"], False)
        self.assertIs(hint["invent"], False)
        self.assertIs(hint["invent_wall_time_sec"], False)
        self.assertIs(hint["invent_ux_strings"], False)
        self.assertIs(hint["forecast"], False)
        self.assertIs(hint["ifrs17"], False)
        self.assertIs(hint["iec_spa"], False)
        self.assertIs(hint["writes_live_pack"], False)
        self.assertIs(hint["assist_ne_fill"], True)
        self.assertIs(hint["apply_notes_ne_fill"], True)
        self.assertIs(hint["apply_notes_ne_done"], True)
        self.assertIs(hint["apply_metrics_ne_fill"], True)
        self.assertIs(hint["apply_metrics_ne_done"], True)
        self.assertIs(hint["merge_ne_fill"], True)
        self.assertIs(hint["merge_ne_done"], True)
        self.assertIs(hint["gap_report_ne_done"], True)
        self.assertIs(hint["north_star_done"], False)
        self.assertEqual(hint["runtime_tip"], "48a8645")
        self.assertEqual(hint["or"], "main")
        self.assertEqual(hint["runtime_pr"], 136)
        self.assertEqual(hint["apply_notes_docs_tip"], "6807509")
        self.assertEqual(hint["apply_notes_docs_pr"], 138)
        self.assertEqual(hint["apply_metrics_tip"], "5d399f7")
        self.assertEqual(hint["apply_metrics_pr"], 132)
        self.assertEqual(hint["apply_metrics_docs_tip"], "3904ee4")
        self.assertEqual(hint["apply_metrics_docs_pr"], 134)
        self.assertEqual(hint["merge_tip"], "5086d0f")
        self.assertEqual(hint["merge_pr"], 128)
        self.assertEqual(hint["merge_docs_tip"], "6ecb645")
        self.assertEqual(hint["gap_report_tip"], "84cb202")
        self.assertEqual(hint["gap_report_pr"], 124)
        self.assertEqual(hint["wall_feature_tip"], "9b6646e8")
        self.assertEqual(hint["guest_apply_metrics_tip"], "7c09f32")
        self.assertEqual(hint["guest_apply_notes_tip"], "e5562c3")
        self.assertEqual(hint["guest_apply_notes_pr"], 70)
        self.assertEqual(
            hint["hint"],
            f"cd {RUNTIME_ROOT_TEMPLATE} && {APPLY_NOTES_CMD} {OFFBOX_IEC_PARITY_PACK}",
        )
        self.assertIn("apply-notes+apply-metrics+merge+gap-report", hint["note"])
        self.assertIn("apply-notes ≠ fill", hint["note"])
        self.assertIn("apply-notes ≠ Done", hint["note"])
        self.assertIn("assist ≠ Done", hint["note"])
        self.assertIn("does not run apply-notes", hint["note"])
        self.assertIn("does not supply wall numbers or invent UX strings", hint["note"])
        self.assertIn("6807509", hint["note"])
        self.assertIn("PR #138", hint["note"])
        self.assertIn("iec-parity-live-20260912", hint["note"])
        self.assertIn("stamp-48a8645-iec-parity-live", hint["note"])
        self.assertIn("live fill ≠ Done", hint["note"])
        self.assertNotIn("Fixes #70", hint["note"])
        self.assertNotIn("Fixes #78", hint["note"])
        self.assertNotIn("wall_time_sec", hint["hint"])
        self.assertNotIn("failure_clarity", hint["hint"])
        self.assertNotIn("recoverability", hint["hint"])
        blob = json.dumps(hint)
        self.assertNotIn("Fixes #70", blob)
        self.assertNotIn("Fixes #78", blob)
        self.assertNotRegex(hint["hint"], r"\b\d+\.\d+\b")

        known = apply_notes_plan(runtime_root="/opt/panoramix-runtime")
        self.assertIs(known["template"], False)
        self.assertIs(known["runtime_root_known"], True)
        self.assertEqual(known["cd"], "/opt/panoramix-runtime")
        self.assertEqual(
            known["hint"],
            f"cd /opt/panoramix-runtime && {APPLY_NOTES_CMD} {OFFBOX_IEC_PARITY_PACK}",
        )
        self.assertIs(known["executes"], False)
        self.assertIs(known["supplies_wall_numbers"], False)
        self.assertIs(known["invents_ux_strings"], False)
        self.assertIs(known["invent"], False)
        self.assertIs(known["invent_wall_time_sec"], False)
        self.assertEqual(known["runtime_tip"], "48a8645")
        self.assertEqual(known["apply_notes_docs_tip"], "6807509")
        self.assertEqual(known["apply_notes_docs_pr"], 138)
        self.assertEqual(known["apply_metrics_tip"], "5d399f7")
        self.assertEqual(known["apply_metrics_docs_tip"], "3904ee4")
        self.assertEqual(known["merge_tip"], "5086d0f")
        self.assertEqual(known["gap_report_tip"], "84cb202")
        self.assertEqual(known["wall_feature_tip"], "9b6646e8")

        fill = pack_fill_plan(
            guest_root=ROOT,
            runtime_root="/opt/panoramix-runtime",
            environ={},
            hooked=False,
        )
        self.assertEqual(fill["apply_notes"]["hint"], known["hint"])
        self.assertEqual(fill["operator_live_pack"]["path"], OFFBOX_IEC_PARITY_LIVE_DIR)
        self.assertIs(fill["operator_live_pack"]["north_star_done"], False)
        self.assertIs(fill["operator_live_pack"]["comparable"], False)
        self.assertIs(fill["operator_live_pack"]["unlocks_cloud"], False)
        self.assertIs(fill["apply_notes"]["runtime_root_known"], True)
        self.assertNotIn("durable", fill["fragment"])
        self.assertNotIn("wall_time_sec", json.dumps(fill["fragment"]))
        self.assertNotIn("failure_clarity", json.dumps(fill["fragment"]))


class HonestyTests(unittest.TestCase):
    def test_helpers_and_docs(self) -> None:
        helper = (ROOT / "sos" / "lab_compose.py").read_text(encoding="utf-8")
        self.assertIn("Does not close runtime", helper)
        self.assertIn("#70", helper)
        self.assertIn("#78", helper)
        self.assertIn("b81130f", helper)
        self.assertIn("63a168d", helper)
        self.assertIn("84cb202", helper)
        self.assertIn("aa4f09e", helper)
        self.assertIn("5086d0f", helper)
        self.assertIn("6ecb645", helper)
        self.assertIn("5d399f7", helper)
        self.assertIn("3904ee4", helper)
        self.assertIn("48a8645", helper)
        self.assertIn("6807509", helper)
        self.assertIn("eb48605", helper)
        self.assertIn("39064d5", helper)
        self.assertIn("7c09f32", helper)
        self.assertIn("e5562c3", helper)
        self.assertIn("b859466", helper)
        self.assertIn("iec-parity-live-20260912", helper)
        self.assertIn("stamp-48a8645-iec-parity-live", helper)
        self.assertIn("iec_parity_pack", helper)
        self.assertIn("skeleton", helper)
        self.assertIn("gap-report", helper)
        self.assertIn("gap_report", helper)
        self.assertIn("merge", helper)
        self.assertIn("apply-metrics", helper)
        self.assertIn("apply_metrics", helper)
        self.assertIn("apply-notes", helper)
        self.assertIn("apply_notes", helper)
        self.assertIn("merge+gap-report", helper)
        self.assertIn("apply-metrics+merge+gap-report", helper)
        self.assertIn("apply-notes+apply-metrics+merge+gap-report", helper)
        self.assertIn("merge ≠ fill", helper)
        self.assertIn("merge ≠ Done", helper)
        self.assertIn("apply-metrics ≠ fill", helper)
        self.assertIn("apply-metrics ≠ Done", helper)
        self.assertIn("apply-notes ≠ fill", helper)
        self.assertIn("apply-notes ≠ Done", helper)
        self.assertIn("metrics.wall_time_sec", helper)
        self.assertIn("pack-fill", helper)
        self.assertIn("does not write the full live pack", helper.lower())
        self.assertIn("LAB_COMPOSE_CATALOG", helper)
        self.assertIn("parity-scale", helper)
        self.assertIn("not ADSL", helper)
        self.assertIn("does not invent walls", helper)
        self.assertIn("does not flip comparison flags", helper)
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
            self.assertIn("aa4f09e", text, name)
            self.assertIn("5086d0f", text, name)
            self.assertIn("6ecb645", text, name)
            self.assertIn("5d399f7", text, name)
            self.assertIn("3904ee4", text, name)
            self.assertIn("48a8645", text, name)
            self.assertIn("6807509", text, name)
            self.assertIn("eb48605", text, name)
            self.assertIn("39064d5", text, name)
            self.assertIn("7c09f32", text, name)
            self.assertIn("e5562c3", text, name)
            self.assertIn("b859466", text, name)
            self.assertIn("iec-parity-live-20260912", text, name)
            self.assertIn("stamp-48a8645-iec-parity-live", text, name)
            self.assertIn("iec_parity_pack", text, name)
            self.assertIn("skeleton", text, name)
            self.assertIn("gap-report", text, name)
            self.assertIn("merge", text, name)
            self.assertIn("apply-metrics", text, name)
            self.assertIn("apply-notes", text, name)
            self.assertIn("metrics.wall_time_sec", text, name)
            self.assertIn("wall_elapsed_ms", text, name)
            self.assertIn("compare prefers", text.lower(), name)
            self.assertIn("handoff docs", text.lower(), name)
            self.assertIn("omit when missing", text.lower(), name)
            self.assertIn("never invent", text.lower(), name)
            self.assertIn("pack_fill", text, name)
            self.assertIn("#78", text, name)
            self.assertIn("LAB_COMPOSE_CATALOG", text, name)
            self.assertIn("--catalog", text, name)
            self.assertIn("parity-scale", text, name)
            self.assertIn("ADSL", text, name)
            self.assertIn("does not invent walls", text.lower(), name)
            self.assertIn("comparison flags", text.lower(), name)
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
        self.assertIn("aa4f09e", lab)
        self.assertIn("5086d0f", lab)
        self.assertIn("6ecb645", lab)
        self.assertIn("5d399f7", lab)
        self.assertIn("3904ee4", lab)
        self.assertIn("48a8645", lab)
        self.assertIn("6807509", lab)
        self.assertIn("eb48605", lab)
        self.assertIn("39064d5", lab)
        self.assertIn("7c09f32", lab)
        self.assertIn("e5562c3", lab)
        self.assertIn("b859466", lab)
        self.assertIn("iec-parity-live-20260912", lab)
        self.assertIn("stamp-48a8645-iec-parity-live", lab)
        self.assertIn("PR #122", lab)
        self.assertIn("PR #124", lab)
        self.assertIn("PR #126", lab)
        self.assertIn("PR #128", lab)
        self.assertIn("PR #130", lab)
        self.assertIn("PR #132", lab)
        self.assertIn("PR #134", lab)
        self.assertIn("PR #136", lab)
        self.assertIn("PR #138", lab)
        self.assertIn("gap-report ≠ Done", lab)
        self.assertIn("merge ≠ fill", lab)
        self.assertIn("merge ≠ Done", lab)
        self.assertIn("apply-metrics ≠ fill", lab)
        self.assertIn("apply-metrics ≠ Done", lab)
        self.assertIn("apply-notes ≠ fill", lab)
        self.assertIn("apply-notes ≠ Done", lab)
        self.assertIn("assist ≠ Done", lab)
        self.assertIn("merge+gap-report", lab)
        self.assertIn("apply-metrics + merge + gap-report", lab)
        self.assertIn("apply-notes + apply-metrics + merge + gap-report", lab)
        self.assertIn("pack_fill.gap_report", lab)
        self.assertIn("pack_fill.merge", lab)
        self.assertIn("pack_fill.apply_metrics", lab)
        self.assertIn("pack_fill.apply_notes", lab)
        self.assertIn("runtime.iec_parity_pack gap-report", lab)
        self.assertIn("runtime.iec_parity_pack merge", lab)
        self.assertIn("runtime.iec_parity_pack apply-metrics", lab)
        self.assertIn("runtime.iec_parity_pack apply-notes", lab)
        self.assertIn("runtime.iec_parity_pack skeleton", lab)
        self.assertIn("--from-json", lab)
        self.assertIn("--from-durable-panoramix", lab)
        self.assertIn("stamp-5086d0f-iec-parity-merge", lab)
        self.assertIn("stamp-5d399f7-iec-parity-apply-metrics", lab)
        self.assertIn("stamp-48a8645-iec-parity-apply-notes", lab)
        self.assertIn("live fill ≠ Done", lab)
        self.assertIn("smoke walls ≠ Done", lab)
        self.assertIn("smoke notes ≠ Done", lab)
        self.assertIn("metrics.wall_time_sec", lab)
        self.assertIn("assist ≠ fill", lab)
        self.assertIn("does **not** write the full live pack", lab)
        self.assertIn("#78 D", lab)
        self.assertIn("LAB_COMPOSE_CATALOG", lab)
        self.assertIn("--catalog live|parity", lab)
        self.assertIn("parity-scale", lab)
        self.assertIn("sha256:e180d2c2e3589b8762f92efa1bedb3d53ffeeb16648581ba13d537bcd3311102", lab)
        self.assertIn("**not** ADSL", lab)
        self.assertIn("does **not** invent walls", lab)
        self.assertIn("does **not** flip comparison flags", lab)
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
        self.assertIn("- [x] Lab-compose pack_fill.gap_report hint", ux)
        self.assertIn("- [x] Overnight merge assist smoke stamp is merge ≠ fill / merge ≠ Done", ux)
        self.assertIn("- [x] Lab-compose pack_fill.merge hint", ux)
        self.assertIn("- [x] Overnight apply-metrics assist smoke stamp is apply-metrics ≠ fill / apply-metrics ≠ Done", ux)
        self.assertIn("- [x] Lab-compose pack_fill.apply_metrics hint", ux)
        self.assertIn("- [x] Overnight apply-notes assist smoke stamp is apply-notes ≠ fill / apply-notes ≠ Done", ux)
        self.assertIn("- [x] Lab-compose pack_fill.apply_notes hint", ux)
        self.assertIn("- [x] Operator live #78 D pack is off-box", ux)
        self.assertIn("- [x] Lab-compose opt-in catalog live|parity", ux)
        self.assertIn("LAB_COMPOSE_CATALOG", ux)
        self.assertIn("sha256:e180d2c2e3589b8762f92efa1bedb3d53ffeeb16648581ba13d537bcd3311102", ux)
        self.assertIn("parity ≠ IFRS17 / ≠ ADSL", ux)
        self.assertIn("does not invent walls or flip comparison flags", ux)
        self.assertIn("b81130f", ux)
        self.assertIn("63a168d", ux)
        self.assertIn("84cb202", ux)
        self.assertIn("aa4f09e", ux)
        self.assertIn("5086d0f", ux)
        self.assertIn("6ecb645", ux)
        self.assertIn("5d399f7", ux)
        self.assertIn("3904ee4", ux)
        self.assertIn("48a8645", ux)
        self.assertIn("6807509", ux)
        self.assertIn("eb48605", ux)
        self.assertIn("39064d5", ux)
        self.assertIn("7c09f32", ux)
        self.assertIn("e5562c3", ux)
        self.assertIn("b859466", ux)
        self.assertIn("iec-parity-live-20260912", ux)
        self.assertIn("stamp-48a8645-iec-parity-live", ux)
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
