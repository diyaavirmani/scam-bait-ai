// SCAM-BAIT side-by-side dashboard. Real data only: the /alt/api snapshot plus the shared SSE stream.
// Every value is inserted with textContent only, so scammer text cannot inject markup.
"use strict";

const PAGE = document.body.dataset.page;
const EVENT_TYPES = ["message.received", "persona.reply", "scam.detected", "intel.extracted", "case.summary",
  "transcript.partial", "transcript.final", "call.status", "metrics.speed", "ratelimit.status", "task.retrying"];
const CHANNELS = { chats: "chat", calls: "call", cases: "", export: "" };
const state = { cases: new Map(), sel: null, view: null, speed: new Map(), limits: new Map(), partial: {} };

// ---------- helpers ----------
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = String(text);
  return n;
}
function clear(id) { const n = document.getElementById(id); if (n) n.textContent = ""; return n; }
function empty(id, text) { const n = clear(id); if (n) n.appendChild(el("div", "empty", text)); }
function ist(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  if (isNaN(d)) return String(ts);
  return d.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", hour12: false, day: "2-digit", month: "short",
    hour: "2-digit", minute: "2-digit", second: "2-digit" }) + " IST";
}
function pct(p) { return (p === null || p === undefined) ? "n/a" : (Math.round(p * 100) + "%"); }
function verdictBadge(v) { const b = el("span", "badge v-" + (v || "unknown"), (v || "unknown").replace("_", " ")); return b; }
async function api(url, opts) {
  const r = await fetch(url, Object.assign({ credentials: "same-origin" }, opts || {}));
  if (r.status === 401) { location.href = "/login?next=" + encodeURIComponent(location.pathname); throw new Error("401"); }
  if (!r.ok) throw new Error(url + " " + r.status);
  return r.json();
}
function table(headers, rows) {
  const t = el("table"); const h = el("tr");
  headers.forEach((x) => h.appendChild(el("th", null, x))); t.appendChild(h);
  rows.forEach((row) => { const tr = el("tr"); row.forEach((c) => {
    const td = el("td"); if (c instanceof Node) td.appendChild(c); else td.textContent = c === null || c === undefined ? "" : String(c);
    tr.appendChild(td); }); t.appendChild(tr); });
  return t;
}

// ---------- case list ----------
function caseMatchesPage(c) {
  const ch = CHANNELS[PAGE];
  if (ch === "chat") return c.channel === "telegram" || c.channel === "api";
  if (ch === "call") return c.channel === "call";
  return true;
}
function renderCases() {
  const box = clear("cases"); if (!box) return;
  const list = [...state.cases.values()].filter(caseMatchesPage).sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
  if (!list.length) { box.appendChild(el("div", "empty", PAGE === "calls" ? "No calls yet." : "No cases yet.")); return; }
  list.forEach((c) => {
    const row = el("div", "case" + (c.id === state.sel ? " sel" : ""));
    const top = el("div"); top.appendChild(el("b", null, c.channel + " " + c.id)); top.appendChild(verdictBadge(c.verdict));
    if (c.status === "closed") top.appendChild(el("span", "badge", "closed"));
    row.appendChild(top);
    row.appendChild(el("div", "meta", "turn " + (c.turn || 0) + " of " + (c.max_turns || 20) + " | " + (c.scam_type || "unknown") + " | " + ist(c.updated_at)));
    row.onclick = () => selectCase(c.id);
    box.appendChild(row);
  });
}
async function loadCases() {
  const ch = CHANNELS[PAGE];
  const data = await api("/alt/api/cases" + (ch ? "?channel=" + ch : ""));
  data.cases.forEach((c) => state.cases.set(c.id, c));
  renderCases();
  if (PAGE === "export") renderExports();
  const want = new URLSearchParams(location.search).get("case");
  const first = [...state.cases.values()].filter(caseMatchesPage).sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""))[0];
  if (PAGE !== "export" && (want || first)) await selectCase(want || first.id);
}
async function refreshCase(id) {
  try { const v = await api("/alt/api/cases/" + id); state.cases.set(id, v.case); if (id === state.sel) { state.view = v; renderView(); } renderCases(); if (PAGE === "export") renderExports(); }
  catch (e) { /* case may be gone; ignore */ }
}
async function selectCase(id) {
  state.sel = id; renderCases();
  state.view = await api("/alt/api/cases/" + id);
  state.partial = {};
  renderView();
}

// ---------- panels ----------
function renderView() {
  const v = state.view; if (!v) return;
  const title = document.getElementById("thread-title");
  if (title) title.textContent = (PAGE === "calls" ? "Live transcript: " : "Conversation: ") + v.case.channel + " " + v.case.id;
  if (PAGE === "chats") renderThread();
  if (PAGE === "calls") renderCaptions();
  renderDetect(); renderIntel(); renderSummary(); renderCaseBox();
  if (PAGE === "calls") renderCallStatus();
  if (PAGE === "cases") renderEvidence();
  renderSpeed();
}
function renderThread() {
  const box = clear("thread"); const msgs = state.view.messages;
  if (!msgs.length) { box.appendChild(el("div", "empty", "No messages yet.")); return; }
  const degraded = new Set(state.view.events.filter((e) => e.type === "persona.reply" && e.data.degraded).map((e) => e.data.message_id));
  msgs.forEach((m) => {
    const b = el("div", "msg " + m.role + (degraded.has(m.id) ? " degraded" : ""));
    b.appendChild(el("span", "who", (m.role === "scammer" ? "Scammer" : "Persona (Meena)") + " | " + ist(m.ts) + (degraded.has(m.id) ? " | degraded" : "")));
    b.appendChild(document.createTextNode(m.text));
    box.appendChild(b);
  });
  box.scrollTop = box.scrollHeight;
  const sec = box.parentElement; if (sec) sec.scrollTop = sec.scrollHeight;
}
function detections() { return state.view.events.filter((e) => e.type === "scam.detected"); }
function renderDetect() {
  const box = clear("detect"); if (!box) return;
  const ds = detections();
  if (!ds.length) { box.appendChild(el("div", "empty", "No verdict yet.")); return; }
  const lastFast = [...ds].reverse().find((e) => e.data.stage === "fast");
  const lastFinal = [...ds].reverse().find((e) => e.data.stage === "final");
  const side = el("div");
  const cell = (label, e) => { const d = el("div", "pill"); d.appendChild(el("b", null, label + ": "));
    if (!e) { d.appendChild(document.createTextNode("waiting")); return d; }
    d.appendChild(document.createTextNode("Cerebras " + pct(e.data.p_cerebras) + " | Decisions " + (e.data.decisions_available === false ? "unavailable" : pct(e.data.p_decisions)) + " | "));
    d.appendChild(verdictBadge(e.data.verdict)); return d; };
  side.appendChild(cell("Fast (qwen flag)", lastFast)); side.appendChild(cell("Final (E2)", lastFinal));
  box.appendChild(side);
  if (ds.some((e) => e.data.decisions_available === false)) box.appendChild(el("div", "warn", "Decisions unavailable: detection runs on Cerebras alone."));
  box.appendChild(table(["time", "stage", "Cerebras", "Decisions", "final", "decided by"],
    ds.map((e) => [ist(e.ts), e.data.stage + (e.data.recheck ? " (recheck)" : ""), pct(e.data.p_cerebras),
      e.data.decisions_available === false ? "unavailable" : pct(e.data.p_decisions), verdictBadge(e.data.verdict), e.data.decided_by || ""])));
}
function renderIntel() {
  const box = clear("intel"); if (!box) return;
  const items = state.view.intel;
  if (!items.length) { box.appendChild(el("div", "empty", "No intel yet.")); return; }
  const src = new Map(state.view.events.filter((e) => e.type === "intel.extracted").map((e) => [e.data.kind + "|" + e.data.value, e.data.source]));
  const cols = PAGE === "cases" ? ["kind", "value", "source", "first seen", "source message"] : ["kind", "value", "source", "first seen"];
  box.appendChild(table(cols, items.map((i) => { const r = [i.kind, i.value, src.get(i.kind + "|" + i.value) || "", ist(i.first_seen)];
    if (PAGE === "cases") r.push(i.source_text || ""); return r; })));
}
function latestSummaryEvent() { return [...state.view.events].reverse().find((e) => e.type === "case.summary"); }
function renderSummary() {
  const box = clear("summary"); if (!box) return;
  const ev = latestSummaryEvent(); const summary = (ev && ev.data.summary) || state.view.case.summary;
  if (!summary) { box.appendChild(el("div", "empty", "No summary yet.")); return; }
  box.appendChild(el("div", null, summary));
  const rep = [...state.view.events].reverse().find((e) => e.type === "case.summary" && e.data.report);
  if (rep) {
    const r = rep.data.report; box.appendChild(el("div", "pill", "Case report (" + (r.generated_by || "cerebras") + ")"));
    ["scam_type", "modus_operandi", "risk", "recommended_action"].forEach((k) => { if (r[k]) box.appendChild(el("div", null, k.replace("_", " ") + ": " + r[k])); });
    (r.key_points || []).forEach((p) => box.appendChild(el("div", null, "- " + p)));
  } else if (ev && ev.data.report_error) {
    box.appendChild(el("div", "warn", "Case report waiting: " + ev.data.report_error));
  }
}
function renderCaseBox() {
  const box = clear("casebox"); if (!box) return;
  const c = state.view.case;
  const top = el("div"); top.appendChild(el("span", "big", c.turn + " of " + (c.max_turns || 20)));
  top.appendChild(el("span", null, " scammer messages")); box.appendChild(top);
  const v = el("div", null, "Verdict: "); v.appendChild(verdictBadge(c.verdict)); box.appendChild(v);
  box.appendChild(el("div", null, "Status: " + c.status + " | scam type: " + (c.scam_type || "unknown")));
  box.appendChild(el("div", null, "Started " + ist(c.created_at) + " | updated " + ist(c.updated_at)));
  if (PAGE === "cases") {
    const b = el("div"); const btn = el("button", null, "Generate evidence pack");
    btn.onclick = async () => { btn.disabled = true; try { await api("/alt/api/cases/" + c.id + "/export", { method: "POST" }); await refreshCase(c.id); } finally { btn.disabled = false; } };
    b.appendChild(btn); box.appendChild(b);
  }
}
function renderEvidence() {
  const box = clear("evidence"); if (!box) return;
  const ev = state.view.evidence;
  if (!ev.length) { box.appendChild(el("div", "empty", "No export yet. Use Generate evidence pack.")); return; }
  box.appendChild(table(["kind", "sha256", "created"], ev.map((e) => [e.kind, el("span", "mono", e.sha256), ist(e.created_at)])));
  const links = el("div", "kv");
  [["Download CSV", "export.csv"], ["Download PDF", "export.pdf"]].forEach(([t, f]) => {
    const a = el("a", "btn", t); a.href = "/alt/api/cases/" + state.view.case.id + "/" + f; links.appendChild(a); links.appendChild(document.createTextNode(" ")); });
  box.appendChild(links);
}

// ---------- speed meter and rate limits (global, from the stream and the snapshot) ----------
function addSpeed(e) {
  const d = e.data; const k = d.step + " | " + d.model;
  const s = state.speed.get(k) || { n: 0, msSum: 0, tpsSum: 0, tpsN: 0, last: null };
  s.n += 1; s.msSum += d.ms || 0; if (d.tokens_per_s) { s.tpsSum += d.tokens_per_s; s.tpsN += 1; } s.last = d; s.case_id = e.case_id;
  state.speed.set(k, s);
}
function renderSpeed() {
  const box = clear("speed"); if (!box) return;
  if (!state.speed.size) { box.appendChild(el("div", "empty", "No model calls yet.")); return; }
  box.appendChild(table(["step | model", "last ms", "avg ms", "tokens/s", "cached", "queued ms", "retries"],
    [...state.speed.entries()].map(([k, s]) => [k, s.last.ms, Math.round(s.msSum / s.n),
      s.tpsN ? Math.round(s.tpsSum / s.tpsN) : "n/a", s.last.cached_tokens === null || s.last.cached_tokens === undefined ? "n/a" : s.last.cached_tokens,
      s.last.queued_ms || 0, s.last.retries || 0])));
}
function renderLimits() {
  const box = clear("limits"); if (!box) return;
  if (!state.limits.size) { box.appendChild(el("div", "empty", "No rate-limit data yet.")); return; }
  box.appendChild(table(["model", "requests last minute", "waiting", "last retry"],
    [...state.limits.entries()].map(([m, s]) => [m, (s.rpm_used ?? "n/a") + " of " + (s.rpm_limit ?? "n/a"), s.waiting ?? 0,
      s.retry ? ("waiting " + Math.round((s.retry.retry_in_ms || 0) / 1000) + " s (" + (s.retry.reason || "429") + ")") : "none"])));
}

// ---------- calls ----------
function callSid() {
  const st = state.view.events.find((e) => e.type === "call.status" && e.data.call_sid);
  if (st) return st.data.call_sid;
  const ext = state.view.case.external_id || ""; return ext.startsWith("call:") ? ext.slice(5) : "";
}
function renderCallStatus() {
  const box = clear("callstatus"); if (!box) return;
  box.appendChild(el("div", null, "callSid: " + (callSid() || "unknown")));
  const sts = state.view.events.filter((e) => e.type === "call.status");
  if (!sts.length) { box.appendChild(el("div", "empty", "No status yet.")); return; }
  const last = sts[sts.length - 1]; box.appendChild(el("div", "big", last.data.status));
  if (last.data.from_masked) box.appendChild(el("div", null, "From: " + last.data.from_masked));
  box.appendChild(table(["time", "status", "detail"], sts.map((e) => [ist(e.ts), e.data.status, e.data.detail || ""])));
}
function renderCaptions() {
  const box = clear("captions"); if (!box) return;
  const finals = state.view.events.filter((e) => e.type === "transcript.final");
  if (!finals.length && !Object.keys(state.partial).length) { box.appendChild(el("div", "empty", "No speech yet.")); return; }
  finals.forEach((e) => box.appendChild(el("div", "cap", (e.data.speaker === "caller" ? "Caller: " : "Persona: ") + e.data.text)));
  Object.entries(state.partial).forEach(([spk, txt]) => { if (txt) box.appendChild(el("div", "cap partial", (spk === "caller" ? "Caller: " : "Persona: ") + txt)); });
  const sec = box.parentElement; if (sec) sec.scrollTop = sec.scrollHeight;
}

// ---------- export page ----------
function renderExports() {
  const box = clear("exports"); if (!box) return;
  const list = [...state.cases.values()].sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
  if (!list.length) { box.appendChild(el("div", "empty", "No cases yet.")); return; }
  box.appendChild(table(["case", "channel", "status", "verdict", "scam type", "intel", "pack"], list.map((c) => {
    const cell = el("div"); const btn = el("button", null, "Generate");
    const out = el("div", "mono");
    btn.onclick = async () => { btn.disabled = true; try { const r = await api("/alt/api/cases/" + c.id + "/export", { method: "POST" });
      out.textContent = "CSV " + r.hashes.csv_sha256 + " | PDF " + r.hashes.pdf_sha256 + " | transcript " + r.hashes.transcript_sha256; } finally { btn.disabled = false; } };
    cell.appendChild(btn);
    [["CSV", "export.csv"], ["PDF", "export.pdf"]].forEach(([t, f]) => { const a = el("a", "btn", t); a.href = "/alt/api/cases/" + c.id + "/" + f; cell.appendChild(document.createTextNode(" ")); cell.appendChild(a); });
    cell.appendChild(out);
    return [c.id, c.channel, c.status, verdictBadge(c.verdict), c.scam_type || "unknown", c.intel_count || 0, cell];
  })));
}

// ---------- live stream ----------
function onEvent(e) {
  if (e.type === "metrics.speed") { addSpeed(e); renderSpeed(); }
  if (e.type === "ratelimit.status") { const s = state.limits.get(e.data.model) || {}; Object.assign(s, e.data); state.limits.set(e.data.model, s); renderLimits(); }
  if (e.type === "task.retrying") { const s = state.limits.get(e.data.model) || {}; s.retry = e.data; state.limits.set(e.data.model, s); renderLimits(); }
  if (!e.case_id) return;
  if (e.type === "transcript.partial") {
    if (e.case_id === state.sel && PAGE === "calls") { state.partial[e.data.speaker] = (state.partial[e.data.speaker] || "") + (e.data.delta || ""); renderCaptions(); }
    return;
  }
  if (e.type === "transcript.final" && e.case_id === state.sel) state.partial[e.data.speaker] = "";
  if (e.id && state.view && e.case_id === state.sel && state.view.events.some((x) => x.id === e.id)) return; // already in the snapshot
  if (!state.cases.has(e.case_id) || e.case_id === state.sel || ["scam.detected", "case.summary", "message.received", "persona.reply", "intel.extracted", "call.status"].includes(e.type)) {
    refreshCase(e.case_id).then(() => { if (!state.sel && PAGE !== "export") { const c = state.cases.get(e.case_id); if (c && caseMatchesPage(c)) selectCase(e.case_id); } });
  }
}
async function connect() {
  const conn = document.getElementById("conn");
  let last = 0;
  try { last = (await api("/alt/api/stream-cursor")).last_id; } catch (e) { /* login redirect handled in api() */ }
  const es = new EventSource("/api/v1/events/stream?last_id=" + last, { withCredentials: true });
  es.onopen = () => { conn.textContent = "live"; conn.className = "live"; };
  es.onerror = () => { conn.textContent = "reconnecting"; conn.className = "down"; };
  EVENT_TYPES.forEach((t) => es.addEventListener(t, (m) => { try { onEvent(JSON.parse(m.data)); } catch (err) { console.error(err); } }));
}

document.querySelectorAll("header nav a").forEach((a) => { if (a.dataset.p === PAGE) a.className = "on"; });
(async () => {
  try {
    await loadCases();
    // Seed the speed meter and gauges from stored events of the selected case so a reload is not empty.
    if (state.view) state.view.events.filter((e) => e.type === "metrics.speed").forEach(addSpeed);
    renderSpeed(); renderLimits();
  } catch (e) { console.error(e); }
  connect();
})();
