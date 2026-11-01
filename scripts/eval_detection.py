"""Detection eval on a frozen split: qwen flag, Decisions and the E2 ensemble (commit 20).

Real API calls, paced by the per-model limiter (CEREBRAS_RPM_QWEN, default 5/min: 122 rows take about 25 min).
Refused while DEMO_MODE=1. Never run during the demo.
  .venv/bin/python scripts/eval_detection.py testset/detection_real_test.jsonl [--limit N]
Writes out/eval/<split>_scores.jsonl and out/eval/<split>_summary.md (IST timestamp). Prints only metrics.
"""
import argparse
import asyncio
import json
import pathlib
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.detection.decisions import decisions_verdict  # noqa: E402
from app.detection.ensemble import combine, load_config  # noqa: E402
from app.detection.flag import cerebras_flag  # noqa: E402
from app.detection.prefilter import prefilter  # noqa: E402
from app.providers import build_clients  # noqa: E402
from app.runtime import Runtime, set_runtime  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))


class NullBus:
    async def emit(self, event):
        return event


def prf(pairs):
    tp = sum(1 for y, p in pairs if y and p)
    fp = sum(1 for y, p in pairs if not y and p)
    fn = sum(1 for y, p in pairs if y and not p)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1, fp


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("split")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    settings = get_settings()
    if settings.demo_mode:
        print("Refused: DEMO_MODE=1 blocks eval runs.")
        return 2
    cerebras, openai_client = build_clients(settings)
    set_runtime(Runtime(settings=settings, store=None, bus=NullBus(), cerebras=cerebras, openai=openai_client))
    cfg = load_config()
    rows = [json.loads(line) for line in open(args.split, encoding="utf-8")]
    if args.limit:
        rows = rows[: args.limit]
    name = pathlib.Path(args.split).stem
    out_dir = pathlib.Path("out/eval")
    out_dir.mkdir(parents=True, exist_ok=True)
    scores = []
    started = datetime.now(IST)
    with open(out_dir / f"{name}_scores.jsonl", "w", encoding="utf-8") as fh:
        for i, row in enumerate(rows, 1):
            text, y = row["vars"]["message"], row["vars"]["expected"] == "scam"
            window = [{"role": "scammer", "text": text}]
            t0 = time.time()
            cv, dv = await asyncio.gather(cerebras_flag(window, f"eval-{i}"), decisions_verdict(window, f"eval-{i}"))
            final = combine(cv, dv, prefilter(text)["score"], cfg)
            rec = {"id": row["metadata"].get("id"), "y_scam": y, "p_cerebras": cv.p_scam, "cerebras_ok": cv.available,
                   "p_decisions": dv.p_scam, "decisions_ok": dv.available, "e2": final.verdict,
                   "ms": int((time.time() - t0) * 1000)}
            scores.append(rec)
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            print(f"{i}/{len(rows)}", end="\r", flush=True)
    arms = {
        "qwen flag (p>=0.5)": [(r["y_scam"], (r["p_cerebras"] or 0) >= 0.5) for r in scores if r["cerebras_ok"]],
        "Decisions (p>=0.5)": [(r["y_scam"], (r["p_decisions"] or 0) >= 0.5) for r in scores if r["decisions_ok"]],
        "E2 ensemble (unknown counted as scam)": [(r["y_scam"], r["e2"] != "not_scam") for r in scores],
    }
    lines = [f"# Detection eval: {name}", "",
             f"Run {started:%Y-%m-%d %H:%M} IST to {datetime.now(IST):%H:%M} IST, {len(scores)} rows, "
             f"config {json.dumps(cfg)}", "", "| Arm | Rows | Precision | Recall | F1 | False positives |",
             "|---|---|---|---|---|---|"]
    for arm, pairs in arms.items():
        p, r, f, fp = prf(pairs)
        lines.append(f"| {arm} | {len(pairs)} | {p:.2f} | {r:.2f} | {f:.2f} | {fp} |")
    ms = sorted(r["ms"] for r in scores)
    if ms:
        lines.append(f"\nPer-row wall time incl. limiter wait: p50 {ms[len(ms) // 2]} ms, p95 {ms[int(len(ms) * 0.95) - 1]} ms")
    (out_dir / f"{name}_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
