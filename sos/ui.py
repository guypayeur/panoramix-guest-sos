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
    textarea { min-height: 4.2rem; font-family: var(--mono); font-size: 0.82rem; }
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
    .st-accepted, .st-queued { color: #c9b36a; }
    .st-running { color: var(--run); }
    .st-succeeded { color: var(--ok); }
    .st-failed { color: var(--bad); }
    .st-cancelled { color: var(--muted); }
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
  </style>
</head>
<body>
  <header>
    <div>
      <h1>SoS operator</h1>
      <p class="sub">Day-one guest path: submit → status → cancel. Jobs are process-local stubs.
        Compute engines stay in runtime bindings (runtime#70) — this page never takes engine URLs.</p>
    </div>
    <p class="sub" id="info-line">loading…</p>
  </header>
  <main>
    <section>
      <h2>Submit demo job</h2>
      <form id="submit-form">
        <label for="kind">Kind</label>
        <select id="kind">
          <option value="sos.demo.echo">sos.demo.echo</option>
          <option value="sos.demo.sleep">sos.demo.sleep</option>
        </select>
        <label for="spec">Spec (JSON object)</label>
        <textarea id="spec" spellcheck="false">{"message": "hello from operator"}</textarea>
        <div class="row">
          <button type="submit">Submit</button>
          <button type="button" class="secondary" id="fill-sleep">Sleep template</button>
        </div>
      </form>
      <p class="hint">Echo returns spec.message. Sleep waits spec.seconds (default 2, max 30) and can be cancelled while queued or running.</p>
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
    const KIND_SLEEP = "sos.demo.sleep";
    const SPECS = {
      "sos.demo.echo": '{"message": "hello from operator"}',
      "sos.demo.sleep": '{"seconds": 8}'
    };
    let selectedId = null;
    let jobs = [];

    const $ = (id) => document.getElementById(id);
    const flash = (msg) => { $("flash").textContent = msg || ""; };

    $("kind").addEventListener("change", () => {
      $("spec").value = SPECS[$("kind").value] || "{}";
    });
    $("fill-sleep").addEventListener("click", () => {
      $("kind").value = KIND_SLEEP;
      $("spec").value = SPECS[KIND_SLEEP];
    });

    $("submit-form").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      flash("");
      let spec;
      try { spec = JSON.parse($("spec").value); }
      catch (e) { flash("Spec must be JSON: " + e.message); return; }
      if (spec === null || typeof spec !== "object" || Array.isArray(spec)) {
        flash("Spec must be a JSON object.");
        return;
      }
      const res = await fetch("/v0/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: $("kind").value, spec })
      });
      const body = await res.json();
      if (!res.ok) {
        flash(body.error ? JSON.stringify(body) : ("HTTP " + res.status));
        return;
      }
      selectedId = body.id;
      await refresh();
    });

    $("cancel-btn").addEventListener("click", async () => {
      if (!selectedId) return;
      await cancelJob(selectedId);
    });

    function live(status) {
      return status !== "succeeded" && status !== "failed" && status !== "cancelled";
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
      thead.innerHTML = "<tr><th>Status</th><th>Kind</th><th>Id</th><th>Updated</th><th>Action</th></tr>";
      table.appendChild(thead);
      const tbody = document.createElement("tbody");
      for (const job of jobs) {
        const tr = document.createElement("tr");
        tr.className = "job" + (job.id === selectedId ? " selected" : "");
        tr.addEventListener("click", () => { selectedId = job.id; render(); });
        const tdS = document.createElement("td"); tdS.appendChild(pill(job.status));
        const tdK = document.createElement("td"); tdK.textContent = job.kind;
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
        tr.append(tdS, tdK, tdI, tdU, tdA);
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

    loadInfo();
    refresh();
    setInterval(refresh, 1000);
  </script>
</body>
</html>
"""
