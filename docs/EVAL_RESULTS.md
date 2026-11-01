# Evaluation results

Only numbers that were actually run are listed here, with the IST time of the run.

## Model evals: not run

No detection, persona or extraction model eval has been run on this build. No `OPENAI_API_KEY` or `CEREBRAS_API_KEY` was available during the build (1 Nov 2026, 12:45 to 14:00 IST), so there are no precision, recall, F1, latency or Cerebras tokens/s figures yet.

To run the detection eval on the frozen 122-row real test split (79 scam, 43 legitimate look-alikes) once keys are in `.env`, well before any demo:

```bash
DEMO_MODE=0 .venv/bin/python scripts/eval_detection.py testset/detection_real_test.jsonl
```

It paces itself to `CEREBRAS_RPM_QWEN` (Free Trial: 5 per minute, so about 25 minutes) and writes `out/eval/detection_real_test_summary.md`. Add the table here with its run time.

## Measured: regex freeze fixes (local, no network)

Run on 1 Nov 2026 at 13:44 IST, on the build laptop (Python 3.12, median of 5 runs each).

| Input (old behaviour from docs/AUDIT.md section 6.3) | New prefilter | New extraction |
|---|---|---|
| `http://` + 160 x `a` (old APK regex: did not finish in 330 s) | 0.07 ms | 0.07 ms |
| `you are now ` repeated to 2,880 chars (old jailbreak regex: 35.2 s) | 0.45 ms | 2.30 ms |
| `txn of ` repeated to 10k chars (old trusted-sender regex: 13.7 s) | 0.72 ms | 2.57 ms |
| `http://` repeated to 10k chars (the suggested lazy APK regex: 0.175 s) | 0.47 ms | 1.22 ms |

## Measured: test suite

`pytest -q`: 257 passed on 1 Nov 2026 at 13:42 IST (all model, Telegram and Twilio calls mocked).
