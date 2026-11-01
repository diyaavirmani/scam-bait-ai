/* /cases: every case (chats and calls) with summary, report, intel and source message, verdict history. */
(function () {
  "use strict";
  var h = SB.h, $ = SB.$;
  SB.header("cases");
  var S = { cases: [], sel: null, snap: null };
  var main = $("main");
  main.className = "layout";
  var listPanel = h("aside", { class: "panel" }, h("h2", { text: "Cases" }), h("ul", { class: "list", id: "case-list" }),
    h("p", { class: "empty", id: "list-empty", text: "No cases yet." }));
  var detail = h("section", { id: "detail" });
  var netPanel = h("div", { class: "panel nets" }, h("h2", { text: "Scammer networks" }), h("div", { id: "net-list" }),
    h("p", { class: "empty", id: "net-empty", text: "No linked cases yet. Cases join a network when they share a UPI ID, phone, account, link or other identifier." }));
  SB.append(listPanel, netPanel);
  SB.append(main, [listPanel, detail]);
  S.nets = [];

  // Shared identifiers are masked except the last 4 characters; the case page and export show full values.
  function mask(v) {
    v = String(v || "");
    return v.length <= 4 ? v : new Array(v.length - 3).join("*") + v.slice(-4);
  }

  function renderNetworks(flashId) {
    var box = SB.clear($("net-list"));
    $("net-empty").hidden = S.nets.length > 0;
    S.nets.forEach(function (n) {
      var links = [];
      n.case_ids.forEach(function (id) {
        links.push(h("a", { href: "#" + id, class: "mono", onclick: function (e) { e.preventDefault(); select(id); } }, id), " ");
      });
      SB.append(box, h("div", { class: "net-card" + (n.network_id === flashId ? " flash" : ""), id: "net-" + n.network_id },
        h("div", { class: "row1" }, h("span", { class: "mono", text: n.network_id }), h("span", { class: "badge scam", text: n.case_ids.length + " cases" })),
        h("div", { class: "sub", text: n.scam_types.length ? n.scam_types.join(", ") : "scam type not set" }),
        h("ul", { class: "net-shared" }, n.shared.map(function (x) {
          return h("li", null, x.field + ": ", h("span", { class: "mono", text: mask(x.value) }), h("span", { class: "muted", text: " in " + x.case_count + " cases" }));
        })),
        h("div", { class: "net-cases" }, links)));
    });
    if (flashId) setTimeout(function () { var el = $("net-" + flashId); if (el) el.classList.remove("flash"); }, 4000);
  }

  function loadNetworks(flashId) {
    return SB.api("/api/networks").then(function (r) { S.nets = r; renderNetworks(flashId); });
  }

  function loadList() {
    return SB.api("/api/v1/cases?limit=200").then(function (r) {
      S.cases = r.cases;
      renderList();
      if (!S.sel) {
        var want = location.hash.slice(1);
        if (want && r.cases.some(function (c) { return c.id === want; })) select(want);
        else if (r.cases.length) select(r.cases[0].id);
        else renderDetail();
      }
    });
  }

  function renderList() {
    var ul = SB.clear($("case-list"));
    $("list-empty").hidden = S.cases.length > 0;
    S.cases.forEach(function (c) {
      SB.append(ul, h("li", { class: c.id === S.sel ? "sel" : null, onclick: function () { select(c.id); } },
        h("div", { class: "row1" }, h("span", { class: "mono", text: c.id }), SB.verdictBadge(c.verdict)),
        h("div", { class: "sub", text: c.channel + ", " + c.status + ", " + (c.scam_type || "unknown") + ", " + SB.fmtIST(c.updated_at, false) })));
    });
  }

  function select(id) {
    S.sel = id;
    history.replaceState(null, "", "#" + id);
    renderList();
    return SB.api("/api/v1/cases/" + encodeURIComponent(id)).then(function (snap) {
      if (S.sel !== id) return;
      S.snap = snap;
      renderDetail();
    });
  }
  var reload = SB.debounce(function () { if (S.sel) select(S.sel); }, 600);
  var reloadList = SB.debounce(loadList, 600);

  function section(title) {
    var body = h("div");
    return { el: h("div", { class: "panel", style: "margin-bottom:14px" }, h("h2", { text: title }), body), body: body };
  }

  function renderDetail() {
    SB.clear(detail);
    var snap = S.snap;
    if (!snap) { SB.append(detail, h("p", { class: "panel empty", text: S.cases.length ? "Select a case." : "No cases yet." })); return; }
    var c = snap.case;
    var facts = section("Case " + c.id);
    var kv = h("dl", { class: "kv" });
    [["Channel", c.channel], ["Status", c.status], ["Verdict", SB.verdictBadge(c.verdict)], ["Scam type", c.scam_type],
      ["Opened", SB.fmtIST(c.created_at)], ["Last update", SB.fmtIST(c.updated_at)],
      ["Scammer messages", snap.turns + " of " + snap.max_turns]].forEach(function (r) {
      SB.append(kv, [h("dt", { text: r[0] }), h("dd", null, r[1])]);
    });
    SB.append(facts.body, [kv, h("p", null,
      h("a", { class: "btn", href: "/api/v1/cases/" + c.id + "/export.csv", onclick: function () { setTimeout(reload, 1500); } }, "Export CSV"), " ",
      h("a", { class: "btn", href: "/api/v1/cases/" + c.id + "/export.pdf", onclick: function () { setTimeout(reload, 2500); } }, "Export PDF"))]);

    var report = null;
    snap.events.forEach(function (e) { if (e.type === "case.summary" && e.data && e.data.report) report = e.data.report; });
    var sum = section("Summary and case report");
    SB.append(sum.body, c.summary ? h("div", { class: "summary", text: c.summary }) : h("p", { class: "empty", text: "No summary yet." }));
    if (report) SB.append(sum.body, [h("p", { class: "muted", text: "Case report" }), h("div", { class: "report", text: LIVE_format(report) })]);
    else SB.append(sum.body, h("p", { class: "muted", text: "No case report yet. It appears when the case closes." }));

    var byId = {};
    snap.messages.forEach(function (m) { byId[m.id] = m; });
    var intel = section("Intel");
    if (!snap.intel.length) SB.append(intel.body, h("p", { class: "empty", text: "No intel extracted yet." }));
    else {
      var tb = h("tbody");
      snap.intel.forEach(function (i) {
        var m = byId[i.message_id];
        SB.append(tb, h("tr", null, h("td", { text: i.kind }), h("td", { class: "mono", text: i.value }), h("td", { class: "muted", text: i.source || "n/a" }),
          h("td", { text: m ? m.text : "" }), h("td", { class: "muted", text: SB.fmtIST(i.first_seen, false) })));
      });
      SB.append(intel.body, h("table", { class: "grid" }, h("thead", null, h("tr", null, h("th", { text: "Kind" }), h("th", { text: "Value" }),
        h("th", { text: "Source" }), h("th", { text: "Source message" }), h("th", { text: "First seen" }))), tb));
    }

    var hist = section("Verdict history");
    var dets = snap.events.filter(function (e) { return e.type === "scam.detected"; });
    if (!dets.length) SB.append(hist.body, h("p", { class: "empty", text: "No detection results yet." }));
    else {
      var hb = h("tbody");
      dets.forEach(function (e) {
        var x = e.data || {};
        SB.append(hb, h("tr", null, h("td", { text: SB.fmtIST(e.ts, false) }), h("td", { text: (x.stage || "") + (x.recheck ? " re-check" : "") }),
          h("td", { class: "num", text: SB.pct(x.p_cerebras) }),
          h("td", { class: "num" }, x.decisions_available === false ? h("span", { class: "badge warn", text: "Decisions unavailable" }) : SB.pct(x.p_decisions)),
          h("td", null, SB.verdictBadge(x.verdict)), h("td", { class: "muted", text: (x.scam_type || "") + (x.decided_by ? ", by " + x.decided_by : "") })));
      });
      SB.append(hist.body, h("table", { class: "grid" }, h("thead", null, h("tr", null, h("th", { text: "Time" }), h("th", { text: "Stage" }),
        h("th", { class: "num", text: "qwen (Cerebras)" }), h("th", { class: "num", text: "Decisions" }), h("th", { text: "Verdict" }), h("th", { text: "Type" }))), hb));
    }

    var ev = section("Evidence files (SHA-256)");
    if (!snap.evidence.length) SB.append(ev.body, h("p", { class: "empty", text: "Nothing exported yet." }));
    else {
      var eb = h("tbody");
      snap.evidence.slice().reverse().forEach(function (f) {
        SB.append(eb, h("tr", null, h("td", { text: f.kind }), h("td", { class: "mono", text: f.sha256 }), h("td", { class: "muted", text: SB.fmtIST(f.created_at, false) })));
      });
      SB.append(ev.body, h("table", { class: "grid" }, h("thead", null, h("tr", null, h("th", { text: "Kind" }), h("th", { text: "SHA-256" }), h("th", { text: "Created" }))), eb));
    }
    SB.append(detail, [facts.el, sum.el, intel.el, hist.el, ev.el]);
  }

  function LIVE_format(r) {
    if (typeof r === "string") return r;
    try { return JSON.stringify(r, null, 2); } catch (e) { return String(r); }
  }

  var live = SB.stream();
  loadList().then(function () { return loadNetworks(); }).then(function () {
    live.start(function (ev) {
      if (ev.type === "transcript.partial" || ev.type === "ratelimit.status" || ev.type === "metrics.speed") return;
      if (ev.type === "network.updated") { loadNetworks((ev.data || {}).network_id); return; }
      var known = S.cases.some(function (c) { return c.id === ev.case_id; });
      if (!known) { reloadList(); return; }
      if (ev.case_id === S.sel) reload();
      if (ev.type === "case.summary" || ev.type === "scam.detected") reloadList();
    });
  });
})();
