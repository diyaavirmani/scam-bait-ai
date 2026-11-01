/* Live case model shared by /chats and /calls: a case list on the left, one selected case on the right.
   State is built from GET /api/v1/cases/{id} and then updated by SSE events. No sample data. */
var LIVE = (function () {
  "use strict";
  var h = SB.h, $ = SB.$;

  function newDetail(snap) {
    var d = {
      id: snap.case.id, c: snap.case, maxTurns: snap.max_turns || 20, msgs: [], msgKeys: new Set(),
      intel: [], intelKeys: new Set(), det: [], detByKey: {}, lastScammer: null, summary: snap.case.summary || "",
      report: null, summaryFinal: false, reply: null, speed: {}, evIds: new Set(), captions: [], partial: {},
      call: null, callSid: null
    };
    var ext = snap.case.external_id || "";
    if (ext.indexOf("call:") === 0) d.callSid = ext.slice(5);
    (snap.messages || []).forEach(function (m) { addMsg(d, m.id, m.role, m.text, m.ts, null); });
    (snap.intel || []).forEach(function (i) { addIntel(d, i.kind, i.value, i.source, i.first_seen, i.message_id); });
    (snap.events || []).forEach(function (ev) { apply(d, ev); });
    return d;
  }

  function addMsg(d, id, role, text, ts, extra) {
    var key = id !== null && id !== undefined ? "m" + id : null;
    if (key && d.msgKeys.has(key)) return false;
    if (key) d.msgKeys.add(key);
    d.msgs.push({ id: id, role: role, text: text || "", ts: ts, extra: extra || {} });
    d.msgs.sort(function (a, b) { return (a.id || 1e15) - (b.id || 1e15); });
    return true;
  }

  function addIntel(d, kind, value, source, ts, messageId) {
    var key = kind + "|" + value;
    if (d.intelKeys.has(key)) {
      d.intel.forEach(function (i) { if (i.kind === kind && i.value === value && !i.source && source) i.source = source; });
      return false;
    }
    d.intelKeys.add(key);
    d.intel.push({ kind: kind, value: value, source: source, ts: ts, message_id: messageId });
    return true;
  }

  function detKey(d, data) {
    if (data.recheck) return "recheck-" + d.det.length;
    var turn = data.turn !== undefined && data.turn !== null ? data.turn : (d.lastScammer ? d.lastScammer.turn : null);
    return "t" + (turn === null ? "?" : turn);
  }

  // Apply one event to the selected case. Returns true if anything changed.
  function apply(d, ev) {
    if (ev.id !== null && ev.id !== undefined) {
      if (d.evIds.has(ev.id)) return false;
      d.evIds.add(ev.id);
    }
    var x = ev.data || {};
    switch (ev.type) {
      case "message.received": {
        d.lastScammer = { turn: x.turn, text: x.text || "" };
        return addMsg(d, x.message_id, x.role || "scammer", x.text, ev.ts, null) || true;
      }
      case "persona.reply": {
        d.reply = { text: x.text || "", ts: ev.ts, mode: x.mode, degraded: x.degraded, language: x.language, turn: x.turn };
        addMsg(d, x.message_id, "persona", x.text, ev.ts, { degraded: x.degraded, mode: x.mode, language: x.language });
        return true;
      }
      case "scam.detected": {
        var key = detKey(d, x), row = d.detByKey[key];
        if (!row) {
          row = { key: key, turn: x.recheck ? null : (d.lastScammer ? d.lastScammer.turn : x.turn),
            text: x.recheck ? "background re-check" : (d.lastScammer ? d.lastScammer.text : ""),
            recheck: !!x.recheck, fast: null, final: null, ts: ev.ts };
          d.detByKey[key] = row;
          d.det.push(row);
        }
        if (x.stage === "fast") row.fast = x; else row.final = x;
        if (x.stage !== "fast") { d.c.verdict = x.verdict || d.c.verdict; d.c.scam_type = x.scam_type || d.c.scam_type; }
        return true;
      }
      case "intel.extracted":
        return addIntel(d, x.kind, x.value, x.source, ev.ts, x.message_id);
      case "case.summary":
        if (x.summary !== undefined) d.summary = x.summary;
        if (x.status) d.c.status = x.status;
        if (x.report) d.report = x.report;
        d.summaryFinal = !!x.final;
        return true;
      case "metrics.speed": {
        var s = d.speed[x.step || "?"] || (d.speed[x.step || "?"] = { n: 0, msSum: 0, tpsSum: 0, tpsN: 0, last: null });
        s.n += 1; s.msSum += Number(x.ms) || 0; s.last = x; s.ts = ev.ts;
        if (x.tokens_per_s !== null && x.tokens_per_s !== undefined) { s.tpsSum += Number(x.tokens_per_s); s.tpsN += 1; }
        return true;
      }
      case "call.status":
        d.call = { status: x.status, call_sid: x.call_sid, from_masked: x.from_masked, detail: x.detail, ts: ev.ts };
        if (x.call_sid) d.callSid = x.call_sid;
        return true;
      case "transcript.partial": {
        var sp = x.speaker || "caller";
        d.partial[sp] = (d.partial[sp] || "") + (x.delta || "");
        return true;
      }
      case "transcript.final": {
        var spk = x.speaker || "caller";
        d.partial[spk] = "";
        d.captions.push({ speaker: spk, text: x.text || "", start_ms: x.start_ms, end_ms: x.end_ms, ts: ev.ts });
        return true;
      }
    }
    return false;
  }

  // ---------- renderers ----------
  function renderFacts(d, el) {
    SB.clear(el);
    var rows = [["Case", d.id], ["Channel", d.c.channel], ["Status", d.c.status], ["Started", SB.fmtIST(d.c.created_at)],
      ["Verdict", null], ["Scam type", d.c.scam_type || "unknown"]];
    rows.forEach(function (r) {
      SB.append(el, [h("dt", { text: r[0] }), h("dd", null, r[0] === "Verdict" ? SB.verdictBadge(d.c.verdict) : (r[1] || ""))]);
    });
  }

  function renderThread(d, el, roleLabels) {
    var nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    SB.clear(el);
    if (!d.msgs.length) { SB.append(el, h("p", { class: "empty", text: "No messages yet." })); return; }
    d.msgs.forEach(function (m) {
      var meta = (roleLabels[m.role] || m.role) + "  " + SB.fmtIST(m.ts, false);
      SB.append(el, h("div", { class: "bubble " + m.role }, h("div", { class: "meta", text: meta }), m.text,
        m.extra && m.extra.degraded ? h("div", null, h("span", { class: "badge warn", text: "fallback reply" })) : null));
    });
    if (nearBottom) el.scrollTop = el.scrollHeight;
  }

  function renderReply(d, el) {
    SB.clear(el);
    if (!d.reply) { SB.append(el, h("p", { class: "empty", text: "No persona reply yet." })); return; }
    SB.append(el, [h("div", { class: "bubble persona" }, d.reply.text),
      h("p", { class: "muted" }, "Turn " + (d.reply.turn !== undefined ? d.reply.turn : "?") + ", mode " + (d.reply.mode || "n/a") +
        ", language " + (d.reply.language || "n/a") + ", " + SB.fmtIST(d.reply.ts, false) + " ",
        d.reply.degraded ? h("span", { class: "badge warn", text: "degraded" }) : null)]);
  }

  function renderDetection(d, el) {
    SB.clear(el);
    if (!d.det.length) { SB.append(el, h("p", { class: "empty", text: "No detection result yet." })); return; }
    var body = h("tbody");
    d.det.forEach(function (r) {
      var fin = r.final, fast = r.fast, src = fin || fast;
      var pc = fin && fin.p_cerebras !== null && fin.p_cerebras !== undefined ? fin.p_cerebras : (fast ? fast.p_cerebras : null);
      var unavailable = (fin && fin.decisions_available === false) || (!fin && fast && fast.decisions_available === false);
      var text = r.text && r.text.length > 70 ? r.text.slice(0, 70) + "..." : r.text;
      SB.append(body, h("tr", null,
        h("td", null, r.recheck ? "re-check" : (r.turn === null || r.turn === undefined ? "n/a" : String(r.turn)), h("div", { class: "muted", text: text || "" })),
        h("td", { class: "num", text: SB.pct(pc) }),
        h("td", { class: "num" }, unavailable ? h("span", { class: "badge warn", text: "Decisions unavailable" }) : SB.pct(fin ? fin.p_decisions : null)),
        h("td", null, SB.verdictBadge(src.verdict), " ", h("span", { class: "muted", text: fin ? "final" : "fast" }),
          src.scam_type && src.scam_type !== "unknown" ? h("div", { class: "muted", text: src.scam_type + (src.risk ? ", risk " + src.risk : "") }) : null,
          fin && fin.decided_by ? h("div", { class: "muted", text: "decided by " + fin.decided_by }) : null)));
    });
    SB.append(el, h("table", { class: "grid" }, h("thead", null, h("tr", null, h("th", { text: "Turn" }),
      h("th", { class: "num", text: "qwen (Cerebras)" }), h("th", { class: "num", text: "Decisions" }), h("th", { text: "Verdict" }))), body));
  }

  function renderIntel(d, el) {
    SB.clear(el);
    if (!d.intel.length) { SB.append(el, h("p", { class: "empty", text: "No intel extracted yet." })); return; }
    var body = h("tbody");
    d.intel.forEach(function (i) {
      SB.append(body, h("tr", null, h("td", { text: i.kind }), h("td", { class: "mono", text: i.value }),
        h("td", { class: "muted", text: i.source || "n/a" }), h("td", { class: "muted", text: SB.fmtIST(i.ts, false) })));
    });
    SB.append(el, h("table", { class: "grid" }, h("thead", null, h("tr", null, h("th", { text: "Kind" }), h("th", { text: "Value" }),
      h("th", { text: "Source" }), h("th", { text: "First seen" }))), body));
  }

  function renderSummary(d, el) {
    SB.clear(el);
    if (!d.summary && !d.report) { SB.append(el, h("p", { class: "empty", text: "No summary yet." })); return; }
    if (d.summary) SB.append(el, h("div", { class: "summary", text: d.summary }));
    if (d.summaryFinal) SB.append(el, h("p", { class: "muted", text: "Final summary." }));
    if (d.report) SB.append(el, [h("p", { class: "muted", text: "Case report" }), h("div", { class: "report", text: formatReport(d.report) })]);
  }

  function formatReport(r) {
    if (typeof r === "string") return r;
    try { return JSON.stringify(r, null, 2); } catch (e) { return String(r); }
  }

  function renderSpeed(d, el) {
    SB.clear(el);
    var steps = Object.keys(d.speed);
    if (!steps.length) { SB.append(el, h("p", { class: "empty", text: "No model calls measured yet." })); return; }
    var maxMs = 1;
    steps.forEach(function (s) { maxMs = Math.max(maxMs, Number(d.speed[s].last.ms) || 0); });
    var body = h("tbody");
    steps.forEach(function (s) {
      var v = d.speed[s], l = v.last;
      SB.append(body, h("tr", null,
        h("td", null, s, h("div", { class: "muted", text: (l.provider || "") + " " + (l.model || "") })),
        h("td", { class: "num" }, SB.num(l.ms) + " ms", h("div", { class: "bar" }, h("span", { style: "width:" + Math.round(100 * (Number(l.ms) || 0) / maxMs) + "%" }))),
        h("td", { class: "num", text: SB.num(l.tokens_per_s) }),
        h("td", { class: "num", text: SB.num(l.cached_tokens) }),
        h("td", { class: "num", text: SB.num(l.queued_ms) + (l.retries ? " (" + l.retries + " retries)" : "") }),
        h("td", { class: "num", text: SB.num(v.msSum / v.n) + " ms / " + (v.tpsN ? SB.num(v.tpsSum / v.tpsN) : "n/a") + " (" + v.n + ")" })));
    });
    SB.append(el, h("table", { class: "grid" }, h("thead", null, h("tr", null, h("th", { text: "Step" }), h("th", { class: "num", text: "Latest" }),
      h("th", { class: "num", text: "Tokens/s" }), h("th", { class: "num", text: "Cached tok" }), h("th", { class: "num", text: "Queued ms" }),
      h("th", { class: "num", text: "Avg ms / tok/s (n)" }))), body));
  }

  function renderRateLimits(rl, el) {
    SB.clear(el);
    var models = Object.keys(rl.models);
    var now = Date.now();
    var retry = Object.keys(rl.retrying).filter(function (k) { return rl.retrying[k].until > now; });
    if (!models.length && !retry.length) { SB.append(el, h("p", { class: "empty", text: "No rate-limit status received yet." })); return; }
    var body = h("tbody");
    models.forEach(function (m) {
      var s = rl.models[m], used = Number(s.rpm_used) || 0, lim = Number(s.rpm_limit) || 0;
      var frac = lim ? Math.min(1, used / lim) : 0;
      SB.append(body, h("tr", null, h("td", { class: "mono", text: m }),
        h("td", null, h("div", { class: "bar" + (frac >= 0.8 ? " hot" : "") }, h("span", { style: "width:" + Math.round(frac * 100) + "%" }))),
        h("td", { class: "num", text: used + " / " + (lim || "?") + " rpm" }),
        h("td", { class: "num" }, Number(s.waiting) > 0 ? h("span", { class: "badge warn", text: s.waiting + " waiting" }) : "0 waiting")));
    });
    retry.forEach(function (k) {
      var r = rl.retrying[k];
      SB.append(body, h("tr", null, h("td", { class: "mono", text: r.model || "" }),
        h("td", { colspan: "3" }, h("span", { class: "badge warn", text: "429: waiting" }),
          " " + (r.step || "") + " retries in " + Math.ceil(Math.max(0, r.until - now) / 1000) + " s" + (r.reason ? " (" + r.reason + ")" : ""))));
    });
    SB.append(el, h("table", { class: "grid" }, h("thead", null, h("tr", null, h("th", { text: "Model" }), h("th", { text: "Budget" }),
      h("th", { class: "num", text: "Used" }), h("th", { class: "num", text: "Queue" }))), body));
  }

  function renderCaptions(d, el) {
    var nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    SB.clear(el);
    var any = false;
    var label = { caller: "Caller", persona: "Persona" };
    d.captions.forEach(function (c) {
      any = true;
      var t = c.start_ms !== undefined && c.start_ms !== null ? "  " + (Number(c.start_ms) / 1000).toFixed(1) + " s" : "";
      SB.append(el, h("div", { class: "bubble " + c.speaker }, h("div", { class: "meta", text: (label[c.speaker] || c.speaker) + t }), c.text));
    });
    if (!d.captions.length && d.msgs.length) {
      d.msgs.forEach(function (m) {
        any = true;
        SB.append(el, h("div", { class: "bubble " + (m.role === "scammer" ? "caller" : "persona") },
          h("div", { class: "meta", text: (m.role === "scammer" ? "Caller" : "Persona") + "  " + SB.fmtIST(m.ts, false) }), m.text));
      });
    }
    Object.keys(d.partial).forEach(function (sp) {
      if (!d.partial[sp]) return;
      any = true;
      SB.append(el, h("div", { class: "bubble partial " + sp }, h("div", { class: "meta", text: (label[sp] || sp) + "  speaking" }), d.partial[sp]));
    });
    if (!any) SB.append(el, h("p", { class: "empty", text: "No transcript yet." }));
    if (nearBottom) el.scrollTop = el.scrollHeight;
  }

  // ---------- list + detail controller ----------
  function controller(opts) {
    var S = { cases: {}, sel: null, d: null, loading: null, pending: [], rl: { models: {}, retrying: {} } };
    var live = SB.stream();
    var refreshList = SB.debounce(loadList, 400);

    function inScope(c) { return c && opts.channels.indexOf(c.channel) >= 0; }

    function loadList() {
      return SB.api("/api/v1/cases?limit=200&channel=" + encodeURIComponent(opts.channels.join(","))).then(function (r) {
        S.cases = {};
        r.cases.forEach(function (c) { S.cases[c.id] = c; });
        renderList();
        if (!S.sel && !S.loading) {
          var want = location.hash.slice(1);
          var first = sorted()[0];
          if (want && S.cases[want]) select(want); else if (first) select(first.id);
        }
      });
    }

    function sorted() {
      return Object.keys(S.cases).map(function (k) { return S.cases[k]; })
        .sort(function (a, b) { return String(b.updated_at).localeCompare(String(a.updated_at)); });
    }

    function renderList() {
      var ul = $("case-list"), list = sorted();
      SB.clear(ul);
      $("list-empty").hidden = list.length > 0;
      list.forEach(function (c) {
        SB.append(ul, h("li", { class: c.id === S.sel ? "sel" : null, onclick: function () { select(c.id); } },
          h("div", { class: "row1" }, h("span", { class: "mono", text: c.id }), SB.verdictBadge(c.verdict)),
          h("div", { class: "sub" }, opts.listLine(c))));
      });
    }

    function select(id) {
      S.sel = id; S.loading = id; S.pending = [];
      if (location.hash.slice(1) !== id) history.replaceState(null, "", "#" + id);
      renderList();
      return SB.api("/api/v1/cases/" + encodeURIComponent(id)).then(function (snap) {
        if (S.loading !== id) return;
        var d = newDetail(snap);
        S.pending.forEach(function (ev) { apply(d, ev); });
        S.loading = null; S.pending = []; S.d = d;
        render();
      }).catch(function (e) { console.error(e); if (S.loading === id) S.loading = null; });
    }

    function render() {
      $("no-sel").hidden = !!S.d;
      $("detail").hidden = !S.d;
      if (S.d) opts.renderDetail(S.d, S);
      if ($("ratelimit")) renderRateLimits(S.rl, $("ratelimit"));
    }

    function caseIdFor(ev) {
      if (ev.case_id) return ev.case_id;
      var sid = ev.data && ev.data.call_sid;
      if (!sid) return null;
      var hit = Object.keys(S.cases).filter(function (k) { return S.cases[k].external_id === "call:" + sid; })[0];
      return hit || null;
    }

    function onEvent(ev) {
      if (ev.type === "ratelimit.status") { S.rl.models[ev.data.model || "?"] = ev.data; render(); return; }
      if (ev.type === "task.retrying") {
        var key = (ev.data.model || "?") + "|" + (ev.data.step || "");
        S.rl.retrying[key] = { model: ev.data.model, step: ev.data.step, reason: ev.data.reason, until: Date.now() + (Number(ev.data.retry_in_ms) || 0) };
        render();
        setTimeout(render, (Number(ev.data.retry_in_ms) || 0) + 50);
      }
      var cid = caseIdFor(ev);
      if (!cid) return;
      var c = S.cases[cid];
      if (!c) {
        if (opts.channels.indexOf(ev.channel) >= 0) refreshList();
        return;
      }
      c.updated_at = ev.ts;
      var x = ev.data || {};
      if (ev.type === "message.received" && (x.role || "scammer") === "scammer" && x.turn) c.turns = Math.max(c.turns || 0, x.turn);
      if (ev.type === "scam.detected" && x.stage !== "fast") { c.verdict = x.verdict || c.verdict; c.scam_type = x.scam_type || c.scam_type; }
      if (ev.type === "case.summary" && x.status) c.status = x.status;
      if (ev.type === "call.status" && x.status) c.call_status = x.status;
      renderList();
      if (cid === S.loading) { S.pending.push(ev); return; }
      if (S.d && cid === S.d.id && apply(S.d, ev)) render();
    }

    loadList().then(function () { live.start(onEvent); }).catch(function (e) { console.error(e); live.start(onEvent); });
    setInterval(function () { if (Object.keys(S.rl.retrying).length) render(); }, 1000);
    return S;
  }

  return { controller: controller, apply: apply, newDetail: newDetail, renderFacts: renderFacts, renderThread: renderThread,
    renderReply: renderReply, renderDetection: renderDetection, renderIntel: renderIntel, renderSummary: renderSummary,
    renderSpeed: renderSpeed, renderRateLimits: renderRateLimits, renderCaptions: renderCaptions, formatReport: formatReport };
})();
