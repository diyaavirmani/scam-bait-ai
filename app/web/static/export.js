/* /export: CSV and PDF evidence packs per case, with the SHA-256 of every exported file. */
(function () {
  "use strict";
  var h = SB.h, $ = SB.$;
  SB.header("export");
  var main = $("main");
  main.style.padding = "14px";
  var panel = h("div", { class: "panel" }, h("h2", { text: "Evidence packs for 1930 / NCRP" }),
    h("p", { class: "muted", text: "Each export writes a CSV (one row per intel item plus the NCRP fields), a transcript and, for PDF, a full evidence pack. The SHA-256 of every file is recorded in the case evidence log and shown here." }),
    h("div", { id: "rows" }));
  SB.append(main, panel);

  function latest(evidence, kind) {
    var hit = null;
    (evidence || []).forEach(function (e) { if (e.kind === kind) hit = e; });
    return hit;
  }

  function load() {
    return SB.api("/api/v1/cases?limit=200&with_evidence=1").then(function (r) {
      var box = SB.clear($("rows"));
      if (!r.cases.length) { SB.append(box, h("p", { class: "empty", text: "No cases yet. Cases appear here once a chat or call starts." })); return; }
      var tb = h("tbody");
      r.cases.forEach(function (c) {
        var hashes = h("div");
        ["csv", "pdf", "transcript"].forEach(function (k) {
          var e = latest(c.evidence, k);
          SB.append(hashes, h("div", { class: "mono" }, k.toUpperCase() + ": " + (e ? e.sha256 + "  (" + SB.fmtIST(e.created_at, false) + ")" : "not exported yet")));
        });
        SB.append(tb, h("tr", null,
          h("td", null, h("a", { href: "/cases#" + c.id, class: "mono", text: c.id }), h("div", { class: "muted", text: c.channel + ", " + c.status })),
          h("td", null, SB.verdictBadge(c.verdict), h("div", { class: "muted", text: c.scam_type || "unknown" })),
          h("td", { text: c.summary ? (c.summary.length > 160 ? c.summary.slice(0, 160) + "..." : c.summary) : "No summary yet." }),
          h("td", null, h("a", { class: "btn", href: "/api/v1/cases/" + c.id + "/export.csv", onclick: later }, "CSV"), " ",
            h("a", { class: "btn", href: "/api/v1/cases/" + c.id + "/export.pdf", onclick: later }, "PDF")),
          h("td", null, hashes)));
      });
      SB.append(box, h("table", { class: "grid" }, h("thead", null, h("tr", null, h("th", { text: "Case" }), h("th", { text: "Verdict" }),
        h("th", { text: "Summary" }), h("th", { text: "Download" }), h("th", { text: "Latest SHA-256" }))), tb));
    });
  }
  function later() { setTimeout(load, 2500); }
  var reload = SB.debounce(load, 800);
  var live = SB.stream();
  load().then(function () {
    live.start(function (ev) { if (ev.type === "case.summary" || ev.type === "scam.detected") reload(); });
  });
})();
