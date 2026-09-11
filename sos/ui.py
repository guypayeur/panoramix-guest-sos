"""Stdlib HTML operator UI (no SPA framework, no CDN)."""

OPERATOR_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SoS operator — day-one</title>
  <style>
    :root {
      --bg: #0f1419;
      --panel: #171e27;
      --line: #2a3544;
      --text: #e7ecf1;
      --muted: #8b9aab;
      --accent: #d4a017;
      --ok: #3dba7a;
      --run: #4c9adf;
      --warn: #e0a04c;
      --bad: #e05d5d;
      --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      --sans: "Segoe UI", system-ui, sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: var(--sans);
      background: var(--bg);
      color: var(--text);
      line-height: 1.45;
    }
    header {
      padding: 1.1rem 1.4rem 0.9rem;
      border-bottom: 1px solid var(--line);
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      flex-wrap: wrap;
      align-items: baseline;
    }
    h1 { font-size: 1.15rem; font-weight: 650; margin: 0; }
    .sub { color: var(--muted); font-size: 0.88rem; max-width: 52rem; }
    main {
      display: grid;
      grid-template-columns: minmax(18rem, 22rem) 1fr;
      gap: 1.1rem;
      padding: 1.1rem 1.4rem 2rem;
    }
    @media (max-width: 820px) { main { grid-template-columns: 1fr; } }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 1rem 1.05rem 1.1rem;
    }
    h2 { font-size: 0.78rem; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); margin: 0 0 0.75rem; }
    label { display: block; font-size: 0.8rem; color: var(--muted); margin: 0.55rem 0 0.2rem; }
    input, select, textarea, button {
      font: inherit;
      color: var(--text);
      background: #0c1116;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0.4rem 0.55rem;
      width: 100%;
    }
    .row { display: flex; gap: 0.5rem; margin-top: 0.85rem; flex-wrap: wrap; align-items: center; }
    button {
      width: auto;
      cursor: pointer;
      background: var(--accent);
      color: #1a1404;
      border-color: transparent;
      font-weight: 650;
      padding: 0.45rem 0.85rem;
    }
    button.secondary { background: transparent; color: var(--text); border: 1px solid var(--line); font-weight: 500; }
    button.danger {
      background: transparent;
      color: #f3b4b4;
      border: 1px solid var(--bad);
      font-weight: 650;
    }
    button.danger:disabled {
      color: var(--muted);
      border-color: var(--line);
      background: transparent;
      opacity: 1;
      cursor: not-allowed;
    }
    button.secondary:disabled {
      color: var(--muted);
      border-color: var(--line);
      background: transparent;
      cursor: not-allowed;
    }
    button.row-cancel {
      padding: 0.18rem 0.5rem;
      font-size: 0.75rem;
    }
    .hint { font-size: 0.78rem; color: var(--muted); margin-top: 0.7rem; }
    table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
    th, td { text-align: left; padding: 0.4rem 0.35rem; border-bottom: 1px solid var(--line); vertical-align: middle; }
    th { color: var(--muted); font-weight: 550; font-size: 0.75rem; }
    tr.selected td { background: #1f2a36; }
    tr.job { cursor: pointer; }
    .id { font-family: var(--mono); font-size: 0.78rem; }
    .pill {
      display: inline-block;
      font-size: 0.72rem;
      font-weight: 650;
      letter-spacing: 0.03em;
      text-transform: uppercase;
      padding: 0.12rem 0.45rem;
      border-radius: 999px;
      border: 1px solid var(--line);
    }
    .st-queued { color: #c9b36a; }
    .st-running { color: var(--run); }
    .st-paused { color: var(--warn); }
    .st-succeeded { color: var(--ok); }
    .st-failed { color: var(--bad); }
    .st-canceled { color: var(--muted); }
    #flash { min-height: 1.2rem; font-size: 0.82rem; color: var(--bad); margin: 0.4rem 0 0; }
    #detail, #seam-view {
      font-family: var(--mono);
      font-size: 0.8rem;
      white-space: pre-wrap;
      background: #0c1116;
      border-radius: 6px;
      padding: 0.75rem;
      border: 1px solid var(--line);
      overflow: auto;
    }
    .empty { color: var(--muted); font-size: 0.88rem; padding: 0.4rem 0; }
    .banner {
      margin: 0.85rem 1.4rem 0;
      padding: 0.7rem 0.9rem;
      border: 1px solid var(--warn);
      background: #241c10;
      color: #f0d9a8;
      border-radius: 8px;
      font-size: 0.86rem;
      max-width: 72rem;
    }
    .banner strong { color: #ffd27a; }
    .meta { display: grid; grid-template-columns: 7.5rem 1fr; gap: 0.28rem 0.7rem; font-size: 0.86rem; }
    .meta dt { color: var(--muted); }
    .meta dd { margin: 0; word-break: break-all; }
    .meta .id { font-size: 0.8rem; }
    .timeline { display: flex; gap: 0.35rem; flex-wrap: wrap; margin: 0.45rem 0 0.15rem; }
    .step {
      font-size: 0.72rem;
      padding: 0.15rem 0.45rem;
      border-radius: 999px;
      border: 1px solid var(--line);
      color: var(--muted);
    }
    .step.done { color: var(--ok); }
    .step.current { color: var(--run); border-color: var(--run); }
    .step .owner { display: block; font-size: 0.64rem; font-weight: 500; letter-spacing: 0; }
    .investigate {
      margin-top: 0.65rem;
      padding-top: 0.55rem;
      border-top: 1px solid var(--line);
    }
    .investigate h3 {
      font-size: 0.72rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted);
      margin: 0 0 0.4rem;
    }
    .investigate p { margin: 0.25rem 0; font-size: 0.82rem; }
    .owners { display: flex; gap: 0.35rem; flex-wrap: wrap; margin: 0.4rem 0 0.15rem; }
    .trail { font-size: 0.8rem; padding-left: 1.1rem; }
    .trail li { margin: 0.2rem 0; }
    .trail .ts { font-family: var(--mono); color: var(--muted); font-size: 0.74rem; }
    .trail .kind { font-weight: 650; }
    #cancel-modal {
      position: fixed;
      inset: 0;
      background: rgba(6, 8, 12, 0.72);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1.2rem;
      z-index: 20;
    }
    #cancel-modal[hidden] { display: none; }
    .modal-card {
      background: var(--panel);
      border: 1px solid var(--bad);
      border-radius: 8px;
      padding: 1rem 1.1rem 1.15rem;
      max-width: 32rem;
    }
    .modal-card h3 { margin: 0 0 0.55rem; font-size: 1rem; }
    .modal-card p { margin: 0 0 0.55rem; font-size: 0.88rem; }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>SoS operator</h1>
      <p class="sub">Day-one guest path: submit → status → cancel. Opaque handoff is
        kind / class / payload_digest (runtime/compute_work.py, #70 Slice B). Local
        echo / sleep / reserve is a demo shortcut that synthesizes that shape —
        this page never takes engine URLs. Pause/Resume is durable-path only.</p>
    </div>
    <p class="sub" id="info-line">loading…</p>
  </header>
  <p class="banner"><strong>Stub / UX seed only.</strong> Reserve (shaped) is an
    in-process lifecycle demo so operators can compare submit → status pills →
    cancel with iec <code>docs/ux/journeys/run_lifecycle_monitoring.md</code>.
    It is <strong>not</strong> a performance baseline until runtime #83 + remeasure,
    <strong>not</strong> IFRS17 math, and <strong>not</strong> runtime #70 Done.
    Named iec baseline remains
    <code>grammar/examples/reserve_ifrs17</code> (see panoramix-runtime
    <code>proofs/fixtures/iec-parity/method.yaml</code>).     Guest is thinner:
    Pause/Resume exist on the <strong>durable path only</strong>
    (injected hook, opt-in <code>PANORAMIX_RUNTIME_ROOT</code> lab adapter,
    or operator/ctl
    <code>python3 -m runtime.apply reserve-temporal pause|resume --id cw_…</code>).
    Stub-only jobs refuse pause/resume (<code>409 stub_only</code>) —
    this page does not pretend otherwise. Cancel ends the run
    (<code>canceled</code>) from running or paused; cancel is not pause.
    Progress prefers durable path-slice counters when a runtime hook
    provides them; otherwise stub stage metadata (not iec planner
    parallelism / iec chunk progress).
    Event trail prefers durable reserve-temporal JSONL when a hook
    provides it; otherwise process-memory (not a SIEM / not a
    regulatory audit).
    Investigate is thinner: catalog identity already on the job
    (name + short digest) for cross-check — not a data-catalog product.
    Static path-slice ownership tags when hooked (not Slack, not a
    live team directory). Event trail stays on this panel (not a SIEM).
    <strong>Stub fallback</strong> (default, in-process) vs
    <strong>operator binding path</strong>: operator/ctl reads
    <code>GET /v0/jobs/{id}/handoff</code> and <code>/payload</code>
    (mesh is compute-job → sos; worker calls this Unit). Transport today is
    operator/ctl-mediated only — no guest→ctl HTTP, no
    <code>runtime.apply compute-work</code> from the guest, no env that adds
    mesh destinations. Default hook stays inert. Opt-in lab
    <code>PANORAMIX_RUNTIME_ROOT</code> may invoke
    <code>reserve-temporal</code> locally on the existing hook seam (not #70 Done).
    Recorded digest matches
    <code>runtime.reserve.digest_for(recorded_params())</code> on
    panoramix-runtime main (<code>docs/reserve.md</code>).
    Side-by-side: <code>docs/ux-side-by-side.md</code>.</p>
  <main>
    <section>
      <h2>Submit local demo</h2>
      <form id="submit-form">
        <label for="demo">Demo</label>
        <select id="demo">
          <option value="echo">echo</option>
          <option value="sleep">sleep</option>
          <option value="reserve">Reserve (shaped)</option>
        </select>
        <div id="echo-fields">
          <label for="message">Message</label>
          <input id="message" value="hello from operator" autocomplete="off">
        </div>
        <div id="sleep-fields" hidden>
          <label for="seconds">Seconds</label>
          <input id="seconds" type="number" min="0" max="30" step="0.1" value="8">
        </div>
        <div id="reserve-fields" hidden>
          <label for="catalog">Catalog (digest)</label>
          <select id="catalog">
            <option value="recorded" selected>recorded (CI)</option>
            <option value="live">live</option>
            <option value="parity">parity (parity-scale)</option>
          </select>
          <label for="label">Label (local UX)</label>
          <input id="label" value="reserve-shaped" autocomplete="off">
          <label for="stages">Stages (local UX)</label>
          <input id="stages" type="number" min="2" max="8" step="1" value="3">
          <label for="resource-class">Class (UX label)</label>
          <select id="resource-class">
            <option value="cpu" selected>cpu</option>
            <option value="gpu">gpu (label only — no GPU kernels)</option>
          </select>
        </div>
        <div class="row">
          <button type="submit">Submit</button>
          <button type="button" class="secondary" id="fill-sleep">Sleep template</button>
          <button type="button" class="secondary" id="fill-reserve">Reserve template</button>
        </div>
      </form>
      <p class="hint">Stored as kind=job, class=cpu (or gpu label), payload_digest=sha256 of canonical catalog JSON
        (workload/accounts/horizon/paths/seed/lapse_bps/discount_bps — same as runtime.reserve.digest_for on main; docs/reserve.md).
        Echo returns the message. Sleep waits (default 2, max 30) and can be canceled while queued or running.
        Reserve (shaped) defaults to the <strong>recorded</strong> catalog. Stages/seconds are local stub UX only
        (admit → project → fold, …) so cancel mid-flight is visible — still an in-memory thread, not engines, not IFRS17 math.
        Ctl: GET /v0/jobs/{id}/handoff (kind/class/payload_digest/status) and /payload (canonical bytes).
        Guest never calls runtime.apply compute-work. The seam kind is job — never a demo label.</p>
      <p id="flash"></p>
    </section>
    <section>
      <h2>Jobs (newest first)</h2>
      <div id="list"><p class="empty">No jobs yet.</p></div>
      <h2 style="margin-top:1.1rem">Job detail</h2>
      <div class="row" style="margin:0 0 0.55rem">
        <button type="button" class="danger" id="cancel-btn" disabled>Cancel selected job</button>
        <button type="button" class="secondary" id="pause-btn" disabled>Pause</button>
        <button type="button" class="secondary" id="resume-btn" disabled>Resume</button>
        <button type="button" class="secondary" id="handoff-btn" disabled>View/copy handoff</button>
        <button type="button" class="secondary" id="payload-btn" disabled>Fetch payload</button>
      </div>
      <p class="hint" id="pause-hint" style="margin-top:0">Pause/Resume require the durable path.
        Stub jobs stay disabled. Operator/ctl:
        <code>python3 -m runtime.apply reserve-temporal pause|resume --id cw_…</code></p>
      <div id="detail-panel"><p class="empty">Select a job.</p></div>
      <h2 style="margin-top:1.1rem">Event trail</h2>
      <p class="hint" style="margin-top:0">On this same panel. Durable reserve-temporal JSONL when a hook provides it;
        otherwise process-memory. Not a SIEM, not a regulatory audit product.
        Operator/ctl: <code>python3 -m runtime.apply reserve-temporal events --id cw_…</code></p>
      <div id="events"><p class="empty">No events.</p></div>
      <h2 style="margin-top:1.1rem">Handoff / payload</h2>
      <pre id="seam-view">Use View/copy handoff or Fetch payload for the ctl path. WorkHandoff emit only — no runtime.apply from this guest.</pre>
      <pre id="detail" hidden>Select a job.</pre>
    </section>
  </main>
  <div id="cancel-modal" hidden>
    <div class="modal-card" role="dialog" aria-labelledby="cancel-title">
      <h3 id="cancel-title">Cancel this run?</h3>
      <p>Cancel ends the run (status <code>canceled</code>).
        <strong>Cancel is not pause.</strong></p>
      <p class="hint" style="margin-top:0">Pause/Resume exist on the durable/ctl
        path only
        (<code>python3 -m runtime.apply reserve-temporal pause|resume --id cw_…</code>).
        Stub-backed jobs cancel locally. Runtime-backed jobs (injected hook)
        signal the hook, then the guest job is marked <code>canceled</code>
        if it was still live (running or paused).</p>
      <div class="row" style="margin-top:0.85rem">
        <button type="button" class="danger" id="cancel-confirm">End run (canceled)</button>
        <button type="button" class="secondary" id="cancel-dismiss">Keep running</button>
      </div>
    </div>
  </div>
  <script>
    let selectedId = null;
    let jobs = [];
    let pendingCancelId = null;
    let lastSeamText = "";
    let lastProgress = null;
    let lastEvents = null;

    const $ = (id) => document.getElementById(id);
    const flash = (msg) => { $("flash").textContent = msg || ""; };

    function syncDemoFields() {
      const demo = $("demo").value;
      $("echo-fields").hidden = demo !== "echo";
      $("sleep-fields").hidden = demo !== "sleep";
      $("reserve-fields").hidden = demo !== "reserve";
      if (demo === "reserve" && $("sleep-fields").hidden) {
        // Reuse the seconds input for reserve duration.
        $("sleep-fields").hidden = false;
      }
    }
    $("demo").addEventListener("change", syncDemoFields);
    $("fill-sleep").addEventListener("click", () => {
      $("demo").value = "sleep";
      $("seconds").value = "8";
      syncDemoFields();
    });
    $("fill-reserve").addEventListener("click", () => {
      $("demo").value = "reserve";
      $("catalog").value = "recorded";
      $("label").value = "reserve-shaped";
      $("stages").value = "3";
      $("seconds").value = "8";
      $("resource-class").value = "cpu";
      syncDemoFields();
    });

    $("submit-form").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      flash("");
      const demo = $("demo").value;
      let body;
      if (demo === "sleep") {
        const seconds = Number($("seconds").value);
        if (!Number.isFinite(seconds)) { flash("Seconds must be a number."); return; }
        body = { demo: "sleep", seconds };
      } else if (demo === "reserve") {
        const seconds = Number($("seconds").value);
        const stages = Number($("stages").value);
        if (!Number.isFinite(seconds)) { flash("Seconds must be a number."); return; }
        if (!Number.isInteger(stages)) { flash("Stages must be an integer."); return; }
        body = {
          demo: "reserve",
          catalog: $("catalog").value,
          label: $("label").value,
          stages,
          seconds,
          class: $("resource-class").value
        };
      } else {
        body = { demo: "echo", message: $("message").value };
      }
      const res = await fetch("/v0/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const payload = await res.json();
      if (!res.ok) {
        flash(payload.error ? JSON.stringify(payload) : ("HTTP " + res.status));
        return;
      }
      selectedId = payload.id;
      await refresh();
    });

    function openCancelDialog(id) {
      pendingCancelId = id;
      $("cancel-modal").hidden = false;
    }
    function closeCancelDialog() {
      pendingCancelId = null;
      $("cancel-modal").hidden = true;
    }
    $("cancel-btn").addEventListener("click", () => {
      if (!selectedId) return;
      openCancelDialog(selectedId);
    });
    $("cancel-dismiss").addEventListener("click", closeCancelDialog);
    $("cancel-confirm").addEventListener("click", async () => {
      const id = pendingCancelId;
      closeCancelDialog();
      if (id) await cancelJob(id);
    });
    $("handoff-btn").addEventListener("click", () => fetchSeam("handoff"));
    $("payload-btn").addEventListener("click", () => fetchSeam("payload"));

    function live(status) {
      return status !== "succeeded" && status !== "failed" && status !== "canceled";
    }

    function durable(job) {
      if (!job) return false;
      if (job.pause_resume === true) return true;
      const backed = job.local && job.local.backed;
      return backed === "runtime";
    }

    function syncLifecycleButtons(job) {
      const canCancel = !!(job && live(job.status));
      $("cancel-btn").disabled = !canCancel;
      $("cancel-btn").textContent = canCancel
        ? "Cancel selected job"
        : (job ? "Cannot cancel (terminal)" : "Cancel selected job");
      const canPause = !!(job && durable(job) && job.status === "running");
      const canResume = !!(job && durable(job) && job.status === "paused");
      $("pause-btn").disabled = !canPause;
      $("resume-btn").disabled = !canResume;
      const hint = $("pause-hint");
      if (!job) {
        hint.textContent = "Pause/Resume require the durable path. Stub jobs stay disabled. Operator/ctl: python3 -m runtime.apply reserve-temporal pause|resume --id cw_…";
        return;
      }
      if (!durable(job)) {
        hint.textContent = "Stub-only job: Pause/Resume disabled (409 stub_only). Durable path or operator/ctl: python3 -m runtime.apply reserve-temporal pause|resume --id cw_…";
        return;
      }
      if (job.status === "running") {
        hint.textContent = "Durable-backed: Pause is enabled. Cancel is not pause.";
        return;
      }
      if (job.status === "paused") {
        hint.textContent = "Durable-backed: Resume is enabled. Cancel from paused still ends the run.";
        return;
      }
      hint.textContent = "Durable-backed pause/resume is idle on this status. Cancel is not pause.";
    }

    async function signalJob(id, action) {
      flash("");
      const res = await fetch("/v0/jobs/" + id + "/" + action, { method: "POST" });
      const body = await res.json();
      if (!res.ok) {
        flash(body.error ? JSON.stringify(body) : ("HTTP " + res.status));
      }
      selectedId = id;
      await refresh();
    }

    $("pause-btn").addEventListener("click", () => {
      if (selectedId) signalJob(selectedId, "pause");
    });
    $("resume-btn").addEventListener("click", () => {
      if (selectedId) signalJob(selectedId, "resume");
    });

    async function cancelJob(id) {
      flash("");
      const res = await fetch("/v0/jobs/" + id + "/cancel", { method: "POST" });
      const body = await res.json();
      if (!res.ok) {
        flash(body.error ? JSON.stringify(body) : ("HTTP " + res.status));
      }
      selectedId = id;
      await refresh();
    }

    async function copyText(text) {
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text);
          return true;
        }
      } catch (e) { /* fall through */ }
      return false;
    }

    async function fetchSeam(kind) {
      if (!selectedId) return;
      flash("");
      const res = await fetch("/v0/jobs/" + selectedId + "/" + kind);
      const body = await res.json();
      const text = JSON.stringify(body, null, 2);
      lastSeamText = text;
      if (!res.ok) {
        $("seam-view").textContent = text;
        flash(body.error ? JSON.stringify(body) : ("HTTP " + res.status));
        return;
      }
      let note = kind === "handoff"
        ? "WorkHandoff JSON (id/kind/class/payload_digest/status). Copied when clipboard is available. Guest does not call runtime.apply."
        : "Payload export for the ctl path (canonical bytes). Guest does not call runtime.apply.";
      const copied = await copyText(text);
      if (kind === "handoff" && copied) note += " Copied to clipboard.";
      $("seam-view").textContent = note + "\\n\\n" + text;
    }

    function pill(status) {
      const span = document.createElement("span");
      span.className = "pill st-" + status;
      span.textContent = status;
      return span;
    }

    function shortDigest(digest) {
      if (!digest) return "";
      const hex = String(digest).replace(/^sha256:/, "");
      return "sha256:" + hex.slice(0, 8) + "…";
    }

    function fmtTs(raw) {
      return (raw || "").replace("T", " ").replace("Z", "");
    }

    function elapsed(job) {
      const start = Date.parse(job.created_at);
      const end = live(job.status) ? Date.now() : Date.parse(job.updated_at);
      if (!Number.isFinite(start) || !Number.isFinite(end)) return "—";
      const s = Math.max(0, (end - start) / 1000);
      if (s < 60) return s.toFixed(1) + "s";
      return Math.floor(s / 60) + "m " + Math.floor(s % 60) + "s";
    }

    function dlRow(term, value, mono) {
      const dt = document.createElement("dt");
      dt.textContent = term;
      const dd = document.createElement("dd");
      if (value instanceof Node) {
        dd.appendChild(value);
      } else {
        dd.textContent = value == null || value === "" ? "—" : String(value);
        if (mono) dd.className = "id";
      }
      return [dt, dd];
    }

    function ownershipTags(job) {
      const prog = (lastProgress && lastProgress.id === job.id) ? lastProgress : null;
      const fromProg = prog && prog.investigate && prog.investigate.ownership;
      const fromJob = job.investigate && job.investigate.ownership;
      const block = fromProg || fromJob;
      return (block && block.tags) || [];
    }

    function catalogIdentity(job) {
      const prog = (lastProgress && lastProgress.id === job.id) ? lastProgress : null;
      const fromProg = prog && prog.investigate && prog.investigate.catalog;
      const fromJob = job.investigate && job.investigate.catalog;
      if (fromProg || fromJob) return fromProg || fromJob;
      const name = job.local && job.local.catalog;
      if (!name) return null;
      return { name: name, digest_short: shortDigest(job.payload_digest) };
    }

    function renderProgress(job) {
      const wrap = document.createElement("div");
      const local = job.local || {};
      const prog = (lastProgress && lastProgress.id === job.id) ? lastProgress : null;
      const line = document.createElement("p");
      line.className = "hint";
      line.style.marginTop = "0.35rem";
      const completed = prog && prog.stages_completed;
      const fraction = prog && prog.fraction;
      const source = prog && prog.source;
      const durable = source === "durable" ||
        (source !== "stub" && (completed != null || fraction != null));
      const owners = durable ? ownershipTags(job) : [];
      if (durable && (completed != null || fraction != null)) {
        const total = Number(prog.stages_total);
        const done = Number(completed);
        const frac = Number(fraction);
        let text = "";
        if (Number.isFinite(done) && Number.isFinite(total) && total > 0) {
          text = "Path-slices " + done + " / " + total;
          const bar = document.createElement("div");
          bar.className = "timeline";
          const current = Number(prog.stage);
          for (let i = 1; i <= total; i++) {
            const step = document.createElement("span");
            let cls = "step";
            if (i <= done) cls += " done";
            else if (Number.isFinite(current) && i === current) cls += " current";
            step.className = cls;
            const tag = owners[i - 1];
            step.textContent = tag ? (i + " " + tag.slice) : String(i);
            if (tag && tag.owner) {
              const own = document.createElement("span");
              own.className = "owner";
              own.textContent = tag.owner;
              step.appendChild(own);
            }
            bar.appendChild(step);
          }
          wrap.appendChild(bar);
        }
        if (Number.isFinite(frac)) {
          text += (text ? " · " : "") + "fraction " + frac;
        }
        text += " — durable reserve-temporal path-slices, not iec planner parallelism.";
        line.textContent = text;
        wrap.appendChild(line);
        return wrap;
      }
      const total = Number((prog && prog.stages_total != null) ? prog.stages_total : local.stages);
      const index = Number((prog && prog.stage_index != null) ? prog.stage_index : local.stage_index);
      const stage = (prog && prog.stage != null) ? prog.stage : local.stage;
      if (Number.isInteger(total) && total > 0 && Number.isInteger(index)) {
        line.textContent = "Stage " + index + " of " + total +
          (stage ? (": " + stage) : "") +
          " — stub timeline only, not iec chunk progress.";
        const bar = document.createElement("div");
        bar.className = "timeline";
        for (let i = 1; i <= total; i++) {
          const step = document.createElement("span");
          step.className = "step" + (i < index ? " done" : (i === index ? " current" : ""));
          step.textContent = String(i);
          bar.appendChild(step);
        }
        wrap.appendChild(bar);
      } else {
        line.textContent = "No named stub stages (status only). Not iec chunk progress.";
      }
      wrap.appendChild(line);
      return wrap;
    }

    function renderInvestigate(job) {
      const wrap = document.createElement("div");
      wrap.className = "investigate";
      const title = document.createElement("h3");
      title.textContent = "Investigate (thinner)";
      wrap.appendChild(title);
      const catalog = catalogIdentity(job);
      const cat = document.createElement("p");
      if (catalog) {
        cat.textContent = "Catalog cross-check: " + catalog.name + " · " +
          (catalog.digest_short || shortDigest(job.payload_digest)) +
          " — identity already on this job. Not a data-catalog product.";
      } else {
        cat.textContent = "No catalog name on this job (digest only). Not a data-catalog product.";
      }
      wrap.appendChild(cat);
      const owners = ownershipTags(job);
      const hooked = !!(job.investigate && job.investigate.ownership) ||
        !!(lastProgress && lastProgress.id === job.id &&
          lastProgress.investigate && lastProgress.investigate.ownership);
      if (hooked && owners.length) {
        const bar = document.createElement("div");
        bar.className = "owners";
        for (const tag of owners) {
          const step = document.createElement("span");
          step.className = "step";
          step.textContent = tag.slice;
          const own = document.createElement("span");
          own.className = "owner";
          own.textContent = tag.owner;
          step.appendChild(own);
          bar.appendChild(step);
        }
        wrap.appendChild(bar);
        const ownNote = document.createElement("p");
        ownNote.className = "hint";
        ownNote.textContent = "Static day-one path-slice owners when hooked. Not Slack, not a live team directory.";
        wrap.appendChild(ownNote);
      } else {
        const ownNote = document.createElement("p");
        ownNote.className = "hint";
        ownNote.textContent = "Path-slice ownership tags appear when durable-hooked (admit / project / fold / complete). Not Slack.";
        wrap.appendChild(ownNote);
      }
      const trail = document.createElement("p");
      trail.className = "hint";
      trail.textContent = "Event trail is on this panel (scroll). Not a SIEM.";
      wrap.appendChild(trail);
      return wrap;
    }

    function eventLabel(ev) {
      return String(ev.event || ev.type || ev.kind || "event");
    }

    function eventDetail(ev) {
      if (ev.detail) return String(ev.detail);
      if (ev.type && String(ev.type) !== eventLabel(ev)) return String(ev.type);
      if (ev.signal) return String(ev.signal);
      if (ev.activity) return String(ev.activity);
      return "";
    }

    function renderEvents(job) {
      const host = $("events");
      host.replaceChildren();
      const payload = (lastEvents && job && lastEvents.id === job.id) ? lastEvents : null;
      const events = (payload && payload.events) || (job && job.events) || [];
      const source = (payload && payload.source) || (job && job.events_source) || "memory";
      const src = document.createElement("p");
      src.className = "hint";
      src.style.marginTop = "0.15rem";
      if (source === "durable") {
        const n = (payload && payload.events_n != null) ? payload.events_n
          : (job && job.events_n != null) ? job.events_n : events.length;
        src.textContent = "Source: durable — reserve-temporal JSONL (n=" + n
          + "). Survives runtime restart. Not a SIEM / not iec /v1/audit/events.";
      } else {
        src.textContent = "Source: memory — process-local trail; dies on restart. Not a regulatory audit.";
      }
      host.appendChild(src);
      if (!events.length) {
        const p = document.createElement("p");
        p.className = "empty";
        p.textContent = "No events.";
        host.appendChild(p);
        return;
      }
      const ul = document.createElement("ul");
      ul.className = "trail";
      for (const ev of events) {
        const li = document.createElement("li");
        const ts = document.createElement("span");
        ts.className = "ts";
        ts.textContent = fmtTs(ev.ts);
        const kind = document.createElement("span");
        kind.className = "kind";
        kind.textContent = eventLabel(ev);
        li.appendChild(ts);
        li.appendChild(document.createTextNode(" · "));
        li.appendChild(kind);
        const detail = eventDetail(ev);
        if (detail) {
          li.appendChild(document.createTextNode(" — " + detail));
        }
        ul.appendChild(li);
      }
      host.appendChild(ul);
    }

    function renderDetail(job) {
      const host = $("detail-panel");
      host.replaceChildren();
      if (!job) {
        const p = document.createElement("p");
        p.className = "empty";
        p.textContent = "Select a job.";
        host.appendChild(p);
        $("detail").textContent = "Select a job.";
        $("events").replaceChildren();
        const empty = document.createElement("p");
        empty.className = "empty";
        empty.textContent = "No events.";
        $("events").appendChild(empty);
        $("handoff-btn").disabled = true;
        $("payload-btn").disabled = true;
        $("pause-btn").disabled = true;
        $("resume-btn").disabled = true;
        return;
      }
      const local = job.local || {};
      const catalog = catalogIdentity(job);
      const dl = document.createElement("dl");
      dl.className = "meta";
      const rows = [
        ...dlRow("id", job.id, true),
        ...dlRow("status", pill(job.status)),
        ...dlRow("kind / class", (job.kind || "—") + " / " + (job.class || "—")),
        ...dlRow("digest", shortDigest(job.payload_digest), true),
        ...dlRow("catalog", catalog ? catalog.name : "—"),
        ...dlRow("created", fmtTs(job.created_at), true),
        ...dlRow("updated", fmtTs(job.updated_at), true),
        ...dlRow("elapsed", elapsed(job)),
        ...dlRow("message", job.message),
        ...dlRow("stage", (lastProgress && lastProgress.id === job.id && lastProgress.stage != null)
          ? lastProgress.stage : (local.stage || "—")),
        ...dlRow("backed", local.backed || "—")
      ];
      const prog = (lastProgress && lastProgress.id === job.id) ? lastProgress : null;
      if (prog && prog.source) {
        rows.push(...dlRow("progress source", prog.source));
      }
      if (prog && prog.stages_completed != null) {
        const tot = prog.stages_total != null ? (" / " + prog.stages_total) : "";
        rows.push(...dlRow("stages completed", String(prog.stages_completed) + tot));
      }
      if (prog && prog.fraction != null) {
        rows.push(...dlRow("fraction", String(prog.fraction)));
      }
      const trail = (lastEvents && lastEvents.id === job.id) ? lastEvents : null;
      const evSource = (trail && trail.source) || job.events_source;
      if (evSource) {
        rows.push(...dlRow("events source", evSource));
      }
      if (job.events_durable === true || (trail && trail.events_durable === true)) {
        const n = (trail && trail.events_n != null) ? trail.events_n : job.events_n;
        rows.push(...dlRow("events durable", n != null ? ("yes · n=" + n) : "yes"));
      }
      for (const node of rows) dl.appendChild(node);
      host.appendChild(dl);
      host.appendChild(renderProgress(job));
      host.appendChild(renderInvestigate(job));
      $("detail").textContent = JSON.stringify(job, null, 2);
      $("handoff-btn").disabled = false;
      $("payload-btn").disabled = false;
      renderEvents(job);
    }

    function render() {
      const host = $("list");
      host.replaceChildren();
      if (!jobs.length) {
        const p = document.createElement("p");
        p.className = "empty";
        p.textContent = "No jobs yet.";
        host.appendChild(p);
        renderDetail(null);
        $("cancel-btn").disabled = true;
        $("cancel-btn").textContent = "Cancel selected job";
        $("pause-btn").disabled = true;
        $("resume-btn").disabled = true;
        syncLifecycleButtons(null);
        return;
      }
      const table = document.createElement("table");
      const thead = document.createElement("thead");
      thead.innerHTML = "<tr><th>Status</th><th>Kind</th><th>Class</th><th>Demo</th><th>Stage</th><th>Digest</th><th>Id</th><th>Updated</th><th>Action</th></tr>";
      table.appendChild(thead);
      const tbody = document.createElement("tbody");
      for (const job of jobs) {
        const tr = document.createElement("tr");
        tr.className = "job" + (job.id === selectedId ? " selected" : "");
        tr.addEventListener("click", () => {
          selectedId = job.id;
          loadProgress(job.id).then(() => loadEvents(job.id)).then(() => render());
        });
        const tdS = document.createElement("td"); tdS.appendChild(pill(job.status));
        const tdK = document.createElement("td"); tdK.textContent = job.kind;
        const tdC = document.createElement("td"); tdC.textContent = job.class || "";
        const tdD = document.createElement("td"); tdD.textContent = (job.local && job.local.demo) || "—";
        const tdSt = document.createElement("td");
        tdSt.textContent = (job.local && job.local.stage) || "—";
        const tdG = document.createElement("td"); tdG.className = "id"; tdG.textContent = shortDigest(job.payload_digest);
        const tdI = document.createElement("td"); tdI.className = "id"; tdI.textContent = job.id.slice(0, 8);
        const tdU = document.createElement("td"); tdU.className = "id"; tdU.textContent = fmtTs(job.updated_at);
        const tdA = document.createElement("td");
        if (live(job.status)) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "danger row-cancel";
          btn.textContent = "Cancel";
          btn.addEventListener("click", (ev) => {
            ev.stopPropagation();
            openCancelDialog(job.id);
          });
          tdA.appendChild(btn);
        } else {
          tdA.textContent = "—";
        }
        tr.append(tdS, tdK, tdC, tdD, tdSt, tdG, tdI, tdU, tdA);
        tbody.appendChild(tr);
      }
      table.appendChild(tbody);
      host.appendChild(table);

      const selected = jobs.find(j => j.id === selectedId) || jobs[0];
      selectedId = selected.id;
      renderDetail(selected);
      syncLifecycleButtons(selected);
    }

    async function loadProgress(id) {
      if (!id) {
        lastProgress = null;
        return;
      }
      try {
        const res = await fetch("/v0/jobs/" + id + "/progress");
        const body = await res.json();
        lastProgress = res.ok ? body : null;
      } catch (e) {
        lastProgress = null;
      }
    }

    async function loadEvents(id) {
      if (!id) {
        lastEvents = null;
        return;
      }
      try {
        const res = await fetch("/v0/jobs/" + id + "/events");
        const body = await res.json();
        lastEvents = res.ok ? body : null;
      } catch (e) {
        lastEvents = null;
      }
    }

    async function refresh() {
      try {
        const res = await fetch("/v0/jobs");
        const body = await res.json();
        jobs = body.jobs || [];
        const selected = jobs.find(j => j.id === selectedId) || jobs[0];
        if (selected) {
          selectedId = selected.id;
          await loadProgress(selectedId);
          await loadEvents(selectedId);
        } else {
          lastProgress = null;
          lastEvents = null;
        }
        render();
      } catch (e) {
        flash("poll failed: " + e.message);
      }
    }

    async function loadInfo() {
      try {
        const res = await fetch("/v0/info");
        const info = await res.json();
        $("info-line").textContent = info.product + " · " + info.status + " · engines " + info.engines;
      } catch (e) {
        $("info-line").textContent = "info unavailable";
      }
    }

    syncDemoFields();
    loadInfo();
    refresh();
    setInterval(refresh, 1000);
  </script>
</body>
</html>
"""
