/* Co-op Scout front end. Reads data/*.json written by the daily GitHub Actions run. */
(function () {
  "use strict";

  const FACTORS = [
    { k: "match", label: "Keyword match", c: "--c-match" },
    { k: "dist", label: "Distance", c: "--c-dist" },
    { k: "term", label: "Term fit (12/16 mo)", c: "--c-term" },
    { k: "start", label: "Start fit", c: "--c-start" },
    { k: "pay", label: "Pay", c: "--c-pay" },
    { k: "fresh", label: "Freshness", c: "--c-fresh" }
  ];
  const PRESETS = {
    balanced: { match: 35, dist: 20, term: 15, start: 15, pay: 10, fresh: 5 },
    fit: { match: 55, dist: 10, term: 15, start: 15, pay: 5, fresh: 0 },
    close: { match: 25, dist: 45, term: 10, start: 10, pay: 5, fresh: 5 },
    pay: { match: 25, dist: 10, term: 10, start: 10, pay: 40, fresh: 5 }
  };
  const STATUSES = ["To review", "Shortlisted", "Applied", "Interview", "Offer", "Not a fit"];
  const TERMS = [["12", "12 mo"], ["16", "16 mo"], ["12-16", "12–16 mo"], ["unclear", "Unclear"], ["other", "4/8 mo"]];
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const LS = "coopscout.v1.";

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
  const col = (v) => `var(${v})`;
  function load(k, d) { try { const v = localStorage.getItem(LS + k); return v ? JSON.parse(v) : d; } catch (e) { return d; } }
  function save(k, v) { try { localStorage.setItem(LS + k, JSON.stringify(v)); } catch (e) { /* private mode */ } }

  let META = {}, JOBS = [], SOURCES = { sources: [], manual: [] }, DETAILS = null;
  const TODAY = new Date(); TODAY.setHours(12, 0, 0, 0);
  let EARLIEST = "2027-05";
  const DEFAULT_STATE = () => ({
    w: { ...PRESETS.balanced }, preset: "balanced", sort: "score", maxKm: 300, unknownKm: true,
    terms: ["12", "16", "12-16", "unclear"], sector: "all", status: "all", onlyNew: false, onlyVerified: false,
    hideEarly: false, onlyStar: false, showClosed: false, q: "", view: "cards"
  });
  let S = Object.assign(DEFAULT_STATE(), load("state", {}));
  let STATUS = load("status", {}), STAR = load("star", {});

  /* ------------------------------------------------------------ formatting */
  const fmtStart = (s) => (!s || s === "unclear") ? "Unclear" : MONTHS[+s.split("-")[1] - 1] + " " + s.split("-")[0];
  const fmtTerm = (t) => ({ "unclear": "Unclear", "12-16": "12–16 mo", "other": "4/8 mo" }[t] || (t + " mo"));
  const fmtPay = (p) => p ? (p[0] === p[1] ? `$${+p[0].toFixed(2)}/h` : `$${+p[0].toFixed(2)}–${+p[1].toFixed(2)}/h`) : "Not listed";
  const dateOf = (d) => d ? new Date(d + "T12:00:00") : null;
  const fmtDate = (d) => { const x = dateOf(d); return x && !isNaN(x) ? MONTHS[x.getMonth()] + " " + x.getDate() : "—"; };
  const daysTo = (d) => { const x = dateOf(d); return x && !isNaN(x) ? Math.round((x - TODAY) / 864e5) : null; };
  const kmText = (j) => j.km == null ? "Unknown" : j.km + " km";

  /* ------------------------------------------------------------ scoring (mirrors agent/pipeline.py) */
  function comps(j) {
    const dist = j.km == null ? 0.5 : Math.max(0, 1 - j.km / 200);
    let pay = 0.4;
    if (j.pay) pay = Math.min(1, Math.max(0, ((j.pay[0] + j.pay[1]) / 2 - 18) / (34 - 18)));
    const term = { "16": 1, "12": 1, "12-16": 1, "unclear": 0.45, "other": 0.1 }[j.term] ?? 0.45;
    let start = 0.45;
    if (j.start && j.start !== "unclear") {
      const [y, m] = j.start.split("-").map(Number), [ey, em] = EARLIEST.split("-").map(Number);
      const diff = (y * 12 + m) - (ey * 12 + em);
      start = diff < 0 ? 0.1 : diff === 0 ? 1 : Math.max(0.5, 1 - diff * 0.06);
    }
    let fresh = 0.5;
    const pd = dateOf(j.posted);
    if (pd && !isNaN(pd)) fresh = Math.min(1, Math.max(0, 1 - (TODAY - pd) / 864e5 / 45));
    return { match: j.match || 0, dist, term, start, pay, fresh };
  }
  function scoreOf(j) {
    const c = comps(j); let tw = 0, s = 0; const parts = {};
    FACTORS.forEach((f) => { tw += S.w[f.k]; });
    FACTORS.forEach((f) => { const v = tw ? c[f.k] * S.w[f.k] / tw : 0; parts[f.k] = v; s += v; });
    return { total: Math.round(s * 100), parts, c };
  }

  /* ------------------------------------------------------------ panel */
  function buildWeights() {
    const g = $("weights");
    g.querySelectorAll(".w").forEach((n) => n.remove());
    FACTORS.forEach((f) => {
      const d = document.createElement("div"); d.className = "w";
      d.innerHTML = `<span class="sw" style="background:${col(f.c)}"></span><label for="w_${f.k}">${f.label}</label><output id="o_${f.k}" for="w_${f.k}">${S.w[f.k]}</output><input type="range" id="w_${f.k}" min="0" max="60" step="5" value="${S.w[f.k]}">`;
      g.appendChild(d);
      d.querySelector("input").addEventListener("input", (e) => { S.w[f.k] = +e.target.value; $("o_" + f.k).textContent = e.target.value; S.preset = null; syncPresets(); render(); });
    });
  }
  function syncPresets() { document.querySelectorAll("#presets .chipbtn").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.preset === S.preset))); }
  function buildPanel() {
    document.querySelectorAll("#presets .chipbtn").forEach((b) => b.addEventListener("click", () => { S.w = { ...PRESETS[b.dataset.preset] }; S.preset = b.dataset.preset; buildWeights(); syncPresets(); render(); }));
    const tc = $("termChips"); tc.innerHTML = "";
    TERMS.forEach(([v, l]) => {
      const b = document.createElement("button"); b.type = "button"; b.className = "chipbtn"; b.textContent = l;
      b.setAttribute("aria-pressed", String(S.terms.includes(v)));
      b.addEventListener("click", () => { S.terms = S.terms.includes(v) ? S.terms.filter((x) => x !== v) : S.terms.concat(v); b.setAttribute("aria-pressed", String(S.terms.includes(v))); render(); });
      tc.appendChild(b);
    });
    const sectors = [...new Set(JOBS.map((j) => j.sector).filter(Boolean))].sort();
    $("sector").innerHTML = `<option value="all">All sectors</option>` + sectors.map((s) => `<option${s === S.sector ? " selected" : ""}>${esc(s)}</option>`).join("");
    $("statusF").innerHTML = `<option value="all">Any status</option>` + STATUSES.map((s) => `<option${s === S.status ? " selected" : ""}>${s}</option>`).join("");
    const setChk = (id) => { $(id).checked = !!S[id]; $(id).addEventListener("change", (e) => { S[id] = e.target.checked; render(); }); };
    ["onlyNew", "onlyVerified", "hideEarly", "onlyStar", "showClosed", "unknownKm"].forEach(setChk);
    $("maxKm").value = S.maxKm; $("maxKmOut").textContent = S.maxKm >= 300 ? "Any" : S.maxKm + " km";
    $("maxKm").addEventListener("input", (e) => { S.maxKm = +e.target.value; $("maxKmOut").textContent = S.maxKm >= 300 ? "Any" : S.maxKm + " km"; render(); });
    $("sector").addEventListener("change", (e) => { S.sector = e.target.value; render(); });
    $("statusF").addEventListener("change", (e) => { S.status = e.target.value; render(); });
    $("q").value = S.q; $("q").addEventListener("input", (e) => { S.q = e.target.value; render(); });
    $("sort").value = S.sort; $("sort").addEventListener("change", (e) => { S.sort = e.target.value; render(); });
    const setView = (v) => { S.view = v; $("vCards").setAttribute("aria-pressed", String(v === "cards")); $("vTable").setAttribute("aria-pressed", String(v === "table")); render(); };
    $("vCards").addEventListener("click", () => setView("cards"));
    $("vTable").addEventListener("click", () => setView("table"));
    setView(S.view);
    $("resetBtn").addEventListener("click", () => { S = DEFAULT_STATE(); save("state", S); location.reload(); });
    $("exportBtn").addEventListener("click", exportCsv);
    if (window.matchMedia("(max-width:900px)").matches) $("panelDetails").open = false;
    buildWeights(); syncPresets();
  }

  /* ------------------------------------------------------------ filtering & sorting */
  const termRank = { "16": 4, "12-16": 3, "12": 2, "unclear": 1, "other": 0 };
  const SORTS = {
    score: (a, b) => b._s.total - a._s.total,
    match: (a, b) => (b.match || 0) - (a.match || 0) || b._s.total - a._s.total,
    dist: (a, b) => (a.km ?? 9999) - (b.km ?? 9999),
    pay: (a, b) => (b.pay ? b.pay[1] : -1) - (a.pay ? a.pay[1] : -1),
    term: (a, b) => termRank[b.term] - termRank[a.term] || b._s.total - a._s.total,
    start: (a, b) => (a.start === "unclear" ? "9999" : a.start).localeCompare(b.start === "unclear" ? "9999" : b.start),
    deadline: (a, b) => (a.deadline || "9999").localeCompare(b.deadline || "9999"),
    posted: (a, b) => (b.posted || b.first_seen || "").localeCompare(a.posted || a.first_seen || ""),
    company: (a, b) => (a.company || "").localeCompare(b.company || "")
  };
  const statusOf = (id) => STATUS[id] || "To review";
  function filtered() {
    const q = S.q.trim().toLowerCase();
    return JOBS.filter((j) => {
      if (!S.showClosed && j.active === false) return false;
      if (j.km == null) { if (!S.unknownKm) return false; }
      else if (S.maxKm < 300 && j.km > S.maxKm) return false;
      if (!S.terms.includes(j.term)) return false;
      if (S.sector !== "all" && j.sector !== S.sector) return false;
      if (S.status !== "all" && statusOf(j.id) !== S.status) return false;
      if (S.onlyNew && !j.is_new) return false;
      if (S.onlyVerified && (j.term === "unclear" || j.start === "unclear")) return false;
      if (S.hideEarly && j.start !== "unclear" && j.start < EARLIEST) return false;
      if (S.onlyStar && !STAR[j.id]) return false;
      if (q) {
        const hay = [j.title, j.company, j.city, j.location, j.sector, (j.kw || []).join(" "), (j.skills || []).join(" "), j.summary, j.snippet].join(" ").toLowerCase();
        if (!q.split(/\s+/).every((t) => hay.includes(t))) return false;
      }
      return true;
    }).sort(SORTS[S.sort] || SORTS.score);
  }

  /* ------------------------------------------------------------ render */
  function stackBar(parts) { return `<div class="stack" aria-hidden="true">${FACTORS.map((f) => `<span style="width:${(parts[f.k] * 100).toFixed(1)}%;background:${col(f.c)}"></span>`).join("")}</div>`; }
  function renderStats() {
    const act = JOBS.filter((j) => j.active !== false);
    const near = act.filter((j) => j.km != null && j.km <= (META.priority_radius_km || 50)).length;
    const ver = act.filter((j) => j.term !== "unclear" && j.term !== "other" && j.start !== "unclear").length;
    const soon = act.filter((j) => { const d = daysTo(j.deadline); return d !== null && d >= 0 && d <= 21; }).length;
    const applied = Object.entries(STATUS).filter(([id, s]) => s === "Applied" && act.some((j) => j.id === id)).length;
    const stats = [
      [act.filter((j) => j.is_new).length, "New since last run", () => { S.onlyNew = true; $("onlyNew").checked = true; }],
      [act.length, "Listings tracked", () => { }],
      [near, `Within ${META.priority_radius_km || 50} km`, () => { S.maxKm = 50; $("maxKm").value = 50; $("maxKmOut").textContent = "50 km"; }],
      [ver, "Term & start confirmed", () => { S.onlyVerified = true; $("onlyVerified").checked = true; }],
      [soon, "Deadlines in 3 weeks", () => { S.sort = "deadline"; $("sort").value = "deadline"; }],
      [applied, "Applied", () => { S.status = "Applied"; $("statusF").value = "Applied"; }]
    ];
    $("stats").innerHTML = stats.map(([n, l], i) => `<button type="button" class="stat" data-i="${i}"><div class="n">${n}</div><div class="l">${l}</div></button>`).join("");
    $("stats").querySelectorAll(".stat").forEach((b) => b.addEventListener("click", () => { stats[+b.dataset.i][2](); render(); }));
  }

  function tagsFor(j) {
    const dl = daysTo(j.deadline), out = [];
    if (j.active === false) out.push(`<span class="pill bad">Closed</span>`);
    if (j.is_new) out.push(`<span class="pill new">New</span>`);
    if (j.km == null) out.push(`<span class="pill plain">Location unclear</span>`);
    else out.push(j.km <= (META.priority_radius_km || 50) ? `<span class="pill ok">≤ ${META.priority_radius_km || 50} km</span>` : j.km <= 100 ? `<span class="pill plain">50–100 km</span>` : `<span class="pill warn">100+ km</span>`);
    if (j.term === "other") out.push(`<span class="pill bad">4/8-month term</span>`);
    else if (j.term === "unclear" || j.start === "unclear") out.push(`<span class="pill warn">Needs check</span>`);
    else out.push(`<span class="pill ok">Term &amp; start confirmed</span>`);
    if (j.start !== "unclear" && j.start < EARLIEST) out.push(`<span class="pill bad">Starts before ${fmtStart(EARLIEST)}</span>`);
    if (j.citizen) out.push(`<span class="pill plain">Clearance / citizenship</span>`);
    if (dl !== null && dl >= 0 && dl <= 21) out.push(`<span class="pill bad">Closes in ${dl} d</span>`);
    if (dl !== null && dl < 0 && j.active !== false) out.push(`<span class="pill plain">Deadline passed</span>`);
    return out.join("");
  }

  function card(j) {
    const st = statusOf(j.id), kwAll = META.keywords || [];
    const summary = j.summary
      ? `<p class="sum"><span class="lbl">Claude summary</span>${esc(j.summary)}</p>${j.fit_notes ? `<p class="notes">${esc(j.fit_notes)}</p>` : ""}`
      : (j.snippet ? `<p class="sum snip"><span class="lbl">From the posting</span>${esc(j.snippet.slice(0, 260))}${j.snippet.length > 260 ? "…" : ""}</p>` : "");
    return `<article class="card ${st === "Not a fit" ? "dim" : ""} ${j.active === false ? "closed" : ""}" data-id="${esc(j.id)}">
      <div class="score"><div class="cap">Fit</div><div class="big">${j._s.total}</div>${stackBar(j._s.parts)}<div class="rank">#${j._rank} of ${JOBS.length}</div></div>
      <div class="main">
        <div class="head"><div><h2 class="title"><a href="${esc(j.url)}" target="_blank" rel="noopener">${esc(j.title)}</a></h2>
          <div class="co"><b>${esc(j.company)}</b> · ${esc(j.city || j.location || "Location not stated")}${j.city ? ", ON" : ""}${j.mode ? " · " + esc(j.mode) : ""}${j.sector ? " · " + esc(j.sector) : ""}</div></div>
          <div class="tags">${tagsFor(j)}</div></div>
        ${summary}
        <div class="kws">${kwAll.map((k) => `<span class="kw ${(j.kw || []).includes(k) ? "" : "miss"}">${esc(k)}</span>`).join("")}${(j.skills || []).map((s) => `<span class="kw skill">${esc(s)}</span>`).join("")}</div>
        <dl class="tb">
          <div><dt>Term</dt><dd class="${j.term === "unclear" ? "unk" : ""}">${fmtTerm(j.term)}</dd></div>
          <div><dt>Start</dt><dd class="${j.start === "unclear" ? "unk" : ""}">${fmtStart(j.start)}</dd></div>
          <div><dt>From Newmarket</dt><dd class="${j.km == null ? "unk" : ""}">${kmText(j)}</dd></div>
          <div><dt>Pay</dt><dd class="${j.pay ? "" : "unk"}">${fmtPay(j.pay)}</dd></div>
          <div><dt>Deadline</dt><dd>${fmtDate(j.deadline)}</dd></div>
          <div><dt>${j.posted ? "Posted" : "First seen"}</dt><dd>${fmtDate(j.posted || j.first_seen)}</dd></div>
        </dl>
        <div class="actions">
          <a href="${esc(j.url)}" target="_blank" rel="noopener">Open posting ↗</a>
          <details class="more"><summary>Why this score</summary><table>${FACTORS.map((f) => `<tr><td><span class="dot" style="background:${col(f.c)}"></span>${f.label}</td><td>${Math.round(j._s.c[f.k] * 100)}/100</td><td>× ${S.w[f.k]}</td><td>= ${(j._s.parts[f.k] * 100).toFixed(1)}</td></tr>`).join("")}</table></details>
          <details class="more" data-desc="${esc(j.id)}"><summary>Full description</summary><div class="fulldesc">Loading…</div></details>
          <span class="act-right">
            <button type="button" class="star" data-star="${esc(j.id)}" aria-pressed="${!!STAR[j.id]}">${STAR[j.id] ? "★ Shortlisted" : "☆ Shortlist"}</button>
            <select data-status="${esc(j.id)}" aria-label="My status for ${esc(j.title)}">${STATUSES.map((s) => `<option${s === st ? " selected" : ""}>${s}</option>`).join("")}</select>
          </span>
        </div>
        <div class="srcline">Found via ${esc(j.source)}${j.first_seen ? " · first seen " + fmtDate(j.first_seen) : ""}</div>
      </div></article>`;
  }

  function table(rows) {
    return `<div class="tablewrap"><table class="grid"><thead><tr><th>Score</th><th>Role</th><th>Distance</th><th>Term</th><th>Start</th><th>Pay</th><th>Deadline</th><th>Status</th></tr></thead><tbody>${rows.map((j) => `<tr>
      <td><div class="sc">${j._s.total}</div>${stackBar(j._s.parts)}</td>
      <td><a href="${esc(j.url)}" target="_blank" rel="noopener">${esc(j.title)}</a>${j.is_new ? ' <span class="pill new">New</span>' : ""}${STAR[j.id] ? " ★" : ""}<div class="co">${esc(j.company)} · ${esc(j.city || j.location || "—")}</div></td>
      <td class="num ${j.km == null ? "unk" : ""}">${kmText(j)}</td><td class="num ${j.term === "unclear" ? "unk" : ""}">${fmtTerm(j.term)}</td>
      <td class="num ${j.start === "unclear" ? "unk" : ""}">${fmtStart(j.start)}</td><td class="num">${fmtPay(j.pay)}</td><td class="num">${fmtDate(j.deadline)}</td><td>${statusOf(j.id)}</td></tr>`).join("")}</tbody></table></div>`;
  }

  function render() {
    save("state", S);
    JOBS.forEach((j) => { j._s = scoreOf(j); });
    [...JOBS].sort(SORTS.score).forEach((j, i) => { j._rank = i + 1; });
    renderStats();
    const rows = filtered();
    const activeN = JOBS.filter((j) => j.active !== false).length;
    $("count").textContent = `Showing ${rows.length} of ${activeN} open listings`;
    if (!JOBS.length) {
      $("results").innerHTML = META.last_run
        ? `<div class="empty"><h3>No matching listings yet</h3><p>The agent ran on ${esc(META.run_label || META.last_run)} but found no student roles that match. Most postings for May 2027 starts appear between October and March, so check back soon.</p></div>`
        : `<div class="empty"><h3>Waiting for the first run</h3><p>The daily search hasn't run yet. On GitHub, open the <b>Actions</b> tab, choose <b>Daily co-op search</b> and click <b>Run workflow</b>. The list appears here a few minutes after it finishes.</p></div>`;
      return;
    }
    if (!rows.length) { $("results").innerHTML = `<div class="empty"><h3>Nothing matches these filters</h3><p>Try widening the distance, turning on "Unclear" term length, or clicking "Reset filters &amp; weights".</p></div>`; return; }
    $("results").innerHTML = S.view === "table" ? table(rows) : `<div class="list">${rows.map(card).join("")}</div>`;
  }

  /* ------------------------------------------------------------ events on the list (delegated) */
  document.addEventListener("change", (e) => {
    const id = e.target.dataset && e.target.dataset.status;
    if (id) { STATUS[id] = e.target.value; save("status", STATUS); render(); toast(`Marked "${e.target.value}"`); }
  });
  document.addEventListener("click", (e) => {
    const b = e.target.closest && e.target.closest("[data-star]");
    if (b) { const id = b.dataset.star; STAR[id] = !STAR[id]; if (!STAR[id]) delete STAR[id]; save("star", STAR); render(); toast(STAR[id] ? "Added to shortlist" : "Removed from shortlist"); }
  });
  document.addEventListener("toggle", async (e) => {
    const d = e.target;
    if (!(d instanceof HTMLDetailsElement) || !d.dataset.desc || !d.open) return;
    const box = d.querySelector(".fulldesc");
    try {
      if (!DETAILS) DETAILS = await (await fetch("data/details.json", { cache: "no-cache" })).json();
      box.textContent = DETAILS[d.dataset.desc] || "No description was saved for this listing. Open the posting to read it.";
    } catch (err) { box.textContent = "Couldn't load the description. Open the posting instead."; }
  }, true);

  let toastT;
  function toast(msg) {
    let t = document.querySelector(".toast");
    if (!t) { t = document.createElement("div"); t.className = "toast"; t.setAttribute("role", "status"); document.body.appendChild(t); }
    t.textContent = msg; t.classList.add("show"); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("show"), 1600);
  }

  function exportCsv() {
    const rows = filtered();
    const head = ["Score", "Title", "Company", "City", "Distance km", "Term", "Start", "Pay low $/h", "Pay high $/h", "Deadline", "Posted", "Keywords", "My status", "Shortlisted", "Link", "Summary"];
    const q = (v) => `"${String(v == null ? "" : v).replace(/"/g, '""')}"`;
    const lines = [head.map(q).join(",")].concat(rows.map((j) => [j._s.total, j.title, j.company, j.city || j.location, j.km, fmtTerm(j.term), fmtStart(j.start),
      j.pay ? j.pay[0] : "", j.pay ? j.pay[1] : "", j.deadline, j.posted, (j.kw || []).join("; "), statusOf(j.id), STAR[j.id] ? "yes" : "", j.url, j.summary || ""].map(q).join(",")));
    const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `co-op-scout-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    toast(`Exported ${rows.length} listings`);
  }

  /* ------------------------------------------------------------ header & sources */
  function renderHeader() {
    const fmt = (iso) => { if (!iso) return "—"; const d = new Date(iso); return isNaN(d) ? iso : d.toLocaleString("en-CA", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }); };
    const sumDates = JOBS.map((j) => j.summary_date).filter(Boolean).sort();
    $("runinfo").innerHTML = META.last_run
      ? `Last run <b>${esc(fmt(META.last_run))}</b><br>Next run ${esc(fmt(META.next_run))}<br>Claude summaries ${sumDates.length ? "updated <b>" + esc(fmtDate(sumDates[sumDates.length - 1])) + "</b>" : "not written yet"}`
      : "Waiting for the first run";
    if (META.earliest_start) EARLIEST = META.earliest_start;
    if (META.home && META.home.name) $("tagline").textContent = `12- and 16-month mechanical engineering co-op roles across Ontario starting ${fmtStart(EARLIEST)} or later, ranked by fit and distance from ${META.home.name}.`;
    if (META.weights && !load("state", null)) { S.w = { ...META.weights }; }
    document.getElementById("hideEarly").parentElement.lastChild.textContent = ` Hide listings starting before ${fmtStart(EARLIEST)}`;
  }
  function renderSources() {
    const colr = { ok: "var(--good)", blocked: "var(--bad)", error: "var(--bad)", "not-configured": "var(--muted)", undetected: "var(--warn)", skipped: "var(--line-strong)" };
    const label = { ok: null, blocked: "blocked", error: "error", "not-configured": "not set up", undetected: "unrecognised", skipped: "not checked" };
    const src = SOURCES.sources || [];
    $("sources").innerHTML = src.length ? src.map((s) => `<details><summary><span><span class="dot" style="background:${colr[s.status] || "var(--muted)"}"></span>${esc(s.name)}</span><span>${label[s.status] ? label[s.status] : s.kept + " kept / " + s.found}</span></summary>${s.message ? `<div class="msg">${esc(s.message)}</div>` : `<div class="msg">${s.found} student postings found, ${s.kept} matched the filters${s.seconds != null ? " (" + s.seconds + " s)" : ""}.</div>`}</details>`).join("") : `<p>Appears after the first run.</p>`;
    const man = SOURCES.manual || [];
    $("manual").innerHTML = man.map((m) => `<div><a href="${esc(m.url)}" target="_blank" rel="noopener">${esc(m.name)} ↗</a><small>${esc(m.why || "")}${m.sector ? " · " + esc(m.sector) : ""}</small></div>`).join("") || "<p>None.</p>";
  }

  /* ------------------------------------------------------------ boot */
  async function getJson(path, dflt) {
    try { const r = await fetch(path, { cache: "no-cache" }); if (!r.ok) return dflt; return await r.json(); } catch (e) { return dflt; }
  }
  async function boot() {
    const [meta, jobs, sources, summaries] = await Promise.all([
      getJson("data/meta.json", {}), getJson("data/jobs.json", { jobs: [] }), getJson("data/sources.json", { sources: [], manual: [] }), getJson("data/summaries.json", {})
    ]);
    META = meta || {}; SOURCES = sources || { sources: [], manual: [] };
    JOBS = (jobs && jobs.jobs) || [];
    JOBS.forEach((j) => { const s = summaries && summaries[j.id]; if (s) { j.summary = s.summary || j.summary; j.fit_notes = s.fit_notes || j.fit_notes; j.summary_date = s.date || j.summary_date; } });
    renderHeader(); buildPanel(); renderSources(); render();
  }
  boot();
})();
