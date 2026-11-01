"""Read-only analysis of one case from the local SQLite events (used for the real-API test run).

  .venv/bin/python -B scripts/analyze_case.py <external_id> [db_path]
Prints per-turn verdicts, per-step latency, 429 retries, intel and evidence. No secrets are stored in the DB.
"""
import json
import sqlite3
import statistics
import sys
from collections import defaultdict

ext = sys.argv[1]
db = sqlite3.connect(f"file:{sys.argv[2] if len(sys.argv) > 2 else 'scambait.db'}?mode=ro", uri=True)
db.row_factory = sqlite3.Row
cases = db.execute("SELECT * FROM cases WHERE external_id=? ORDER BY created_at", (ext,)).fetchall()
if not cases:
    sys.exit(f"no case for {ext}")
for case in cases:
    cid = case["id"]
    print(f"case {cid} status={case['status']} verdict={case['verdict']} scam_type={case['scam_type']}")
    print(f"summary: {case['summary']}")
    events = [dict(r) | {"data": json.loads(r["data"])} for r in
              db.execute("SELECT * FROM events WHERE case_id=? ORDER BY id", (cid,))]
    turn, rows, steps = 0, [], defaultdict(list)
    for e in events:
        d = e["data"]
        if e["type"] == "message.received":
            turn = d.get("turn") or turn + 1
        elif e["type"] == "scam.detected":
            rows.append((turn, d.get("stage"), d.get("p_cerebras"), d.get("p_decisions"), d.get("verdict"),
                         d.get("decided_by"), d.get("decisions_available"), d.get("recheck")))
        elif e["type"] == "metrics.speed":
            steps[(d.get("step"), d.get("model"))].append((d.get("ms"), d.get("queued_ms"), d.get("tokens_per_s"),
                                                          d.get("cached_tokens")))
    print("\nturn | stage | p_qwen | p_decisions | verdict | decided_by | decisions_available | recheck")
    for r in rows:
        print(" | ".join(str(x) for x in r))
    print("\nstep, model: n, ms p50/p95, queued_ms max, tokens/s p50, cached tokens total")
    for (step, model), xs in sorted(steps.items()):
        ms = sorted(x[0] for x in xs if x[0] is not None)
        q = [x[1] or 0 for x in xs]
        tps = [x[2] for x in xs if x[2]]
        p95 = ms[min(len(ms) - 1, int(round(0.95 * (len(ms) - 1))))] if ms else None
        print(f"{step}, {model}: n={len(xs)}, {statistics.median(ms) if ms else None}/{p95}, "
              f"{max(q) if q else 0}, {round(statistics.median(tps), 1) if tps else None}, "
              f"{sum(x[3] or 0 for x in xs)}")
    retries = [e["data"] for e in events if e["type"] == "task.retrying"]
    print(f"\ntask.retrying events: {len(retries)}; max retry_in_ms: "
          f"{max((r.get('retry_in_ms') or 0) for r in retries) if retries else 0}; reasons: "
          f"{sorted({str(r.get('reason')) for r in retries})}")
    intel = db.execute("SELECT kind, value FROM intel_items WHERE case_id=? ORDER BY id", (cid,)).fetchall()
    print("\nintel:", [(i["kind"], i["value"]) for i in intel])
    ev = db.execute("SELECT kind, path, sha256 FROM evidence WHERE case_id=? ORDER BY id", (cid,)).fetchall()
    print("evidence:", [(e["kind"], e["path"], e["sha256"][:16]) for e in ev])
    persona = db.execute("SELECT text FROM messages WHERE case_id=? AND role='persona' ORDER BY id", (cid,)).fetchall()
    print(f"persona replies: {len(persona)}")
    types = defaultdict(int)
    for e in events:
        types[e["type"]] += 1
    print("event counts:", dict(types))
