/* Shared helpers for the dashboard pages. No sample data: everything shown comes from the API or SSE. */
var SB = (function () {
  "use strict";
  var TYPES = ["message.received", "persona.reply", "scam.detected", "intel.extracted", "case.summary",
    "transcript.partial", "transcript.final", "call.status", "metrics.speed", "ratelimit.status", "task.retrying"];

  // Build DOM safely: strings become text nodes, never HTML (scammer text is untrusted).
  function h(tag, attrs) {
    var el = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === "class") el.className = v;
        else if (k === "text") el.textContent = v;
        else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
        else el.setAttribute(k, v === true ? "" : String(v));
      });
    }
    for (var i = 2; i < arguments.length; i++) append(el, arguments[i]);
    return el;
  }
  function append(el, c) {
    if (c === null || c === undefined || c === false) return;
    if (Array.isArray(c)) { c.forEach(function (x) { append(el, x); }); return; }
    el.appendChild(typeof c === "object" ? c : document.createTextNode(String(c)));
  }
  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }
  function $(id) { return document.getElementById(id); }

  function fmtIST(ts, withDate) {
    if (!ts) return "";
    var d = new Date(ts);
    if (isNaN(d.getTime())) return String(ts);
    var opts = { timeZone: "Asia/Kolkata", hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" };
    if (withDate !== false) { opts.day = "2-digit"; opts.month = "short"; }
    return d.toLocaleString("en-IN", opts) + " IST";
  }
  function pct(p) {
    if (p === null || p === undefined || p === "" || isNaN(Number(p))) return "n/a";
    return Math.round(Number(p) * 100) + "%";
  }
  function num(v, digits) {
    if (v === null || v === undefined || v === "" || isNaN(Number(v))) return "n/a";
    return Number(v).toFixed(digits || 0);
  }
  function verdictBadge(v) {
    var label = v === "scam" ? "SCAM" : v === "not_scam" ? "not scam" : "unknown";
    return h("span", { class: "badge " + (v || "unknown"), text: label });
  }

  function loginRedirect() {
    location.href = "/login?next=" + encodeURIComponent(location.pathname + location.search);
  }
  function api(path) {
    return fetch(path, { credentials: "same-origin", headers: { Accept: "application/json" } }).then(function (r) {
      if (r.status === 401) { loginRedirect(); throw new Error("login required"); }
      if (!r.ok) throw new Error(path + " -> HTTP " + r.status);
      return r.json();
    });
  }

  function header(active) {
    var top = $("top");
    var links = [["chats", "Chats"], ["calls", "Calls"], ["cases", "Cases"], ["export", "Export"]];
    clear(top);
    append(top, [
      h("span", { class: "brand", text: "SCAM-BAIT" }),
      h("nav", null, links.map(function (l) {
        return h("a", { href: "/" + l[0], class: l[0] === active ? "active" : null, text: l[1] });
      })),
      h("span", { class: "conn" }, h("span", { class: "dot", id: "conn-dot" }), h("span", { id: "conn-text", text: "connecting" })),
      h("form", { method: "post", action: "/logout" }, h("button", { class: "linkbtn", type: "submit", text: "Log out" }))
    ]);
  }
  function setConn(state, text) {
    var d = $("conn-dot"), t = $("conn-text");
    if (d) d.className = "dot " + (state || "");
    if (t) t.textContent = text;
  }

  // One EventSource per tab. Events are buffered until start(handler) so a page can load its snapshot
  // first; events already seen (same id) are skipped. The browser resends Last-Event-ID on reconnect.
  function stream() {
    var handler = null, buffer = [], seen = new Set();
    var es = new EventSource("/api/v1/events/stream");
    es.onopen = function () { setConn("on", "live"); };
    es.onerror = function () {
      setConn("off", "reconnecting");
      // A 401 closes the stream for good; check the session and go to login if it expired.
      if (es.readyState === 2) api("/api/v1/cases?limit=1").catch(function () {});
    };
    function deliver(ev) {
      if (ev.id !== null && ev.id !== undefined) {
        if (seen.has(ev.id)) return;
        seen.add(ev.id);
      }
      if (handler) { try { handler(ev); } catch (e) { console.error(e); } } else buffer.push(ev);
    }
    TYPES.forEach(function (t) {
      es.addEventListener(t, function (m) {
        try { deliver(JSON.parse(m.data)); } catch (e) { console.error(e); }
      });
    });
    return {
      markSeen: function (id) { if (id !== null && id !== undefined) seen.add(id); },
      start: function (fn) {
        handler = fn;
        var b = buffer; buffer = [];
        b.forEach(function (ev) { try { fn(ev); } catch (e) { console.error(e); } });
      }
    };
  }

  function debounce(fn, ms) {
    var t = null;
    return function () { clearTimeout(t); t = setTimeout(fn, ms); };
  }

  return { h: h, append: append, clear: clear, $: $, fmtIST: fmtIST, pct: pct, num: num, verdictBadge: verdictBadge,
    api: api, header: header, stream: stream, debounce: debounce, TYPES: TYPES };
})();
