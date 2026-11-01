/* /chats: live text cases (Telegram and API). */
(function () {
  "use strict";
  var $ = SB.$;
  SB.header("chats");
  LIVE.controller({
    channels: ["telegram", "api"],
    listLine: function (c) {
      return c.channel + ", " + (c.status || "") + ", " + (c.turns || 0) + " of 20, " + SB.fmtIST(c.updated_at, false) +
        (c.scam_type && c.scam_type !== "unknown" ? ", " + c.scam_type : "");
    },
    renderDetail: function (d) {
      LIVE.renderFacts(d, $("case-facts"));
      var turns = d.msgs.filter(function (m) { return m.role === "scammer"; }).length;
      $("turns").textContent = turns + " of " + d.maxTurns;
      LIVE.renderThread(d, $("thread"), { scammer: "Scammer", persona: "Persona" });
      LIVE.renderReply(d, $("reply"));
      LIVE.renderDetection(d, $("detection"));
      LIVE.renderIntel(d, $("intel"));
      LIVE.renderSummary(d, $("summary"));
      LIVE.renderSpeed(d, $("speed"));
    }
  });
})();
