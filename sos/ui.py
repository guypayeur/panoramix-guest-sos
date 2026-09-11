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
    .row { display: flex; gap: 0.5rem; margin-top: 0.85rem; }
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
    .st-succeeded { color: var(--ok); }
    .st-failed { color: var(--bad); }
    .st-canceled { color: var(--muted); }
    #flash { min-height: 1.2rem; font-size: 0.82rem; color: var(--bad); margin: 0.4rem 0 0; }
    #detail {
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
  </style>
</head>
<body>
  <header>
    <div>
      <h1>SoS operator</h1>
      <p class="sub">Day-one guest path: submit → status → cancel. Opaque handoff is
        kind / class / payload_digest (runtime/compute_work.py, #70 Slice B). Local
        echo / sleep / reserve is a demo shortcut that synthesizes that shape —
        this page never takes engine URLs.</p>
    </div>
    <p class="sub" id="info-line">loading…</p>
  </header>
  <p class="banner"><strong>Stub / UX seed only.</strong> Reserve (shaped) is an
    in-process lifecycle demo so operators can compare submit → status pills →
    cancel with iec <code>docs/ux/journeys/run_lifecycle_monitoring.md</code>.
    It is <strong>not</strong> a performance baseline, <strong>not</strong> IFRS17
    math, and <strong>not</strong> runtime #70 Done. Comparable perf waits on
    runtime compute-plane engines. Named iec baseline remains
    <code>grammar/examples/reserve_ifrs17</code> (see panoramix-runtime
    <code>proofs/fixtures/iec-parity/method.yaml</code>). Guest is thinner:
    no pause / resume / progress endpoints — cancel only. Operator/ctl admits
    opaque work via <code>GET /v0/jobs/{id}/handoff</code> and
    <code>/payload</code> (mesh is compute-job → sos; awaiting a platform-stamped
    guest submit path). Reserve digest keys match runtime
    <code>docs/reserve.md</code> / PR #84 (<code>runtime.reserve.digest_for</code>).
    Guest never calls <code>runtime.apply</code>.</p>
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
        (workload/accounts/horizon/paths/seed/lapse_bps/discount_bps — same as runtime.reserve.digest_for).
        Echo returns the message. Sleep waits (default 2, max 30) and can be canceled while queued or running.
        Reserve (shaped) defaults to the <strong>recorded</strong> catalog. Stages/seconds are local stub UX only
        (admit → project → fold, …) so cancel mid-flight is visible — still an in-memory thread, not engines, not IFRS17 math.
        Ctl: GET /v0/jobs/{id}/handoff (kind/class/payload_digest/status) and /payload (canonical bytes).
        Guest never calls runtime.apply. The seam kind is job — never a demo label.</p>
      <p id="flash"></p>
    </section>
    <section>
      <h2>Jobs (newest first)</h2>
      <div id="list"><p class="empty">No jobs yet.</p></div>
      <h2 style="margin-top:1.1rem">Detail</h2>
      <div class="row" style="margin:0 0 0.55rem">
        <button type="button" class="danger" id="cancel-btn" disabled>Cancel selected job</button>
      </div>
      <pre id="detail">Select a job.</pre>
    </section>
  </main>
  <script>
    let selectedId = null;
    let jobs = [];

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

    $("cancel-btn").addEventListener("click", async () => {
      if (!selectedId) return;
      await cancelJob(selectedId);
    });

    function live(status) {
      return status !== "succeeded" && status !== "failed" && status !== "canceled";
    }

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

    function render() {
      const host = $("list");
      host.replaceChildren();
      if (!jobs.length) {
        const p = document.createElement("p");
        p.className = "empty";
        p.textContent = "No jobs yet.";
        host.appendChild(p);
        $("detail").textContent = "Select a job.";
        $("cancel-btn").disabled = true;
        $("cancel-btn").textContent = "Cancel selected job";
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
        tr.addEventListener("click", () => { selectedId = job.id; render(); });
        const tdS = document.createElement("td"); tdS.appendChild(pill(job.status));
        const tdK = document.createElement("td"); tdK.textContent = job.kind;
        const tdC = document.createElement("td"); tdC.textContent = job.class || "";
        const tdD = document.createElement("td"); tdD.textContent = (job.local && job.local.demo) || "—";
        const tdSt = document.createElement("td");
        tdSt.textContent = (job.local && job.local.stage) || "—";
        const tdG = document.createElement("td"); tdG.className = "id"; tdG.textContent = shortDigest(job.payload_digest);
        const tdI = document.createElement("td"); tdI.className = "id"; tdI.textContent = job.id.slice(0, 8);
        const tdU = document.createElement("td"); tdU.className = "id"; tdU.textContent = (job.updated_at || "").replace("T", " ").replace("Z", "");
        const tdA = document.createElement("td");
        if (live(job.status)) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "danger row-cancel";
          btn.textContent = "Cancel";
          btn.addEventListener("click", (ev) => {
            ev.stopPropagation();
            cancelJob(job.id);
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
      $("detail").textContent = JSON.stringify(selected, null, 2);
      const can = live(selected.status);
      $("cancel-btn").disabled = !can;
      $("cancel-btn").textContent = can ? "Cancel selected job" : "Cannot cancel (terminal)";
    }

    async function refresh() {
      try {
        const res = await fetch("/v0/jobs");
        const body = await res.json();
        jobs = body.jobs || [];
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
