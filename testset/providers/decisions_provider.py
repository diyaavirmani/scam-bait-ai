"""Promptfoo python provider for OpenAI Decisions API (POST /v1/decisions, model gpt-6-luna).
Skeleton: confirm request/response field names against developers.openai.com/api/docs/guides/decisions before use.
Returns JSON text so promptfoo assertions can read probabilities."""
import json, os, time, urllib.request

QUESTIONS = [  # shape per Decisions guide (29 Oct 2026): type, name, instructions, choices[{value,description}], levels[{label,description}]
  {"type": "predicate", "name": "is_scam", "instructions": "Is this message an attempt to defraud the recipient?"},
  {"type": "choice", "name": "scam_type", "instructions": "Which scam type fits best?",
   "choices": [{"value": v, "description": v.replace("_", " ")} for v in
     ["investment_trading","crypto_investment","digital_arrest","sextortion","job_task","customer_care","kyc_phishing",
      "upi_collect","delivery_phishing","utility_bill","lottery_prize","loan_offer","other","not_a_scam"]]},
  {"type": "predicate", "name": "promises_assured_returns", "instructions": "Does it promise guaranteed or fixed investment returns?"},
  {"type": "predicate", "name": "group_reinvite", "instructions": "Does it ask to join a new group because an old one was banned or removed?"},
  {"type": "predicate", "name": "pay_to_personal_account", "instructions": "Does it ask to pay to a personal or third-party bank account or UPI ID?"},
  {"type": "predicate", "name": "withdrawal_fee_demand", "instructions": "Does it demand a fee or tax before money can be withdrawn?"},
  {"type": "predicate", "name": "credential_request", "instructions": "Does it ask for an OTP, PIN, password or trading login?"},
  {"type": "score", "name": "risk", "instructions": "How risky is this message for the recipient?",
   "levels": [{"label": l, "description": d} for l, d in [("None","Ordinary message"),("Low","Some pressure, no ask"),
     ("High","Asks for money, credentials or an install"),("Critical","Active fraud step: payment, OTP, remote access")]]},
]

def call_api(prompt, options, context):
    body = {"model": os.environ.get("DECISIONS_MODEL", "gpt-6-luna"),
            "input": context["vars"].get("message", prompt),
            "questions": QUESTIONS, "prompt_cache_key": "sb-detect-v1"}
    req = urllib.request.Request("https://api.openai.com/v1/decisions", data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"], "Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=30) as r: out = json.load(r)
    return {"output": json.dumps(out), "metadata": {"latency_ms": int((time.time()-t0)*1000)}}
