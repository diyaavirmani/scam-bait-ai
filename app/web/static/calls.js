/* /calls: active and past phone calls with live two-speaker captions. */
(function () {
  "use strict";
  var $ = SB.$, h = SB.h;
  SB.header("calls");

  function renderCall(d, el) {
    SB.clear(el);
    var c = d.call;
    var rows = [["Call SID", d.callSid || (c && c.call_sid) || "n/a"], ["Call status", c ? c.status : "no status yet"],
      ["From", c && c.from_masked ? c.from_masked : "n/a"], ["Detail", c && c.detail ? c.detail : ""],
      ["Updated", c ? SB.fmtIST(c.ts) : ""]];
    rows.forEach(function (r) {
      SB.append(el, [h("dt", { text: r[0] }), h("dd", null, r[0] === "Call status" && c ?
        h("span", { class: "badge " + (/completed|stopped|failed|busy|no-answer|canceled/.test(c.status || "") ? "closed" : "live"), text: c.status }) : r[1])]);
    });
  }

  LIVE.controller({
    channels: ["call"],
    listLine: function (c) {
      return (c.call_status || c.status || "") + ", " + SB.fmtIST(c.created_at, false) +
        (c.scam_type && c.scam_type !== "unknown" ? ", " + c.scam_type : "");
    },
    renderDetail: function (d) {
      LIVE.renderFacts(d, $("case-facts"));
      renderCall(d, $("call-facts"));
      LIVE.renderCaptions(d, $("captions"));
      LIVE.renderDetection(d, $("detection"));
      LIVE.renderIntel(d, $("intel"));
      LIVE.renderSummary(d, $("summary"));
      LIVE.renderSpeed(d, $("speed"));
    }
  });
})();
