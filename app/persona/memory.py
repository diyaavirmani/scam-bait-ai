"""In-process persona memory per case (one uvicorn worker): full history, pinned key facts, stage.
Rebuilt from the store when missing (after a restart), never silently reset (C-03)."""
from __future__ import annotations

import re

from app.runtime import get_runtime

MAX_KEY_FACTS = 40

# Labels used when intel becomes a pinned key fact.
FACT_LABELS = {
    "name": "Name they gave", "reference_code": "Code they gave", "organisation": "Organisation they claim",
    "employee_id": "Employee ID they gave", "amount": "Amount they asked for", "phone": "Phone they gave",
    "upi": "UPI ID they gave", "url": "Link they sent", "apk": "App file they sent",
    "bank_account": "Bank account they gave", "ifsc": "IFSC they gave", "email": "Email they gave",
    "card": "Card number they gave", "crypto_wallet": "Wallet they gave", "social_handle": "Handle they gave",
}

_CODE_RE = re.compile(r"\b[A-Za-z0-9-]{3,20}\b")
_NAME_RE = re.compile(r"\b(?:I am|I'm|my name is|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})")
_ORG_RE = re.compile(r"\bfrom\s+([A-Z][A-Za-z&.]*(?:\s+[A-Z][A-Za-z&.]*){0,3})")


def fact_for(kind: str, value: str) -> str:
    return f"{FACT_LABELS.get(kind, kind)}: {value}"


def opening_facts(text: str) -> list[str]:
    """Codes and names from the first scammer message, so the persona can recall them later."""
    facts: list[str] = []
    for m in _CODE_RE.finditer(text or ""):
        code = m.group(0)
        # Codes look like GOLD77 or REF-1234: letters and digits together (pure numbers go through extraction).
        if any(c.isdigit() for c in code) and any(c.isalpha() for c in code):
            facts.append(f"Code they gave: {code}")
    for m in _NAME_RE.finditer(text or ""):
        facts.append(f"Name they gave: {m.group(1)}")
    for m in _ORG_RE.finditer(text or ""):
        facts.append(f"They said they are from: {m.group(1).rstrip('.')}")
    facts.append("Their first message: " + (text or "")[:200])
    return facts


class SessionMemory:
    """In-process memory per case: full history, pinned key facts, stage. Rebuilt from the store if missing."""

    def __init__(self) -> None:
        self._cases: dict[str, dict] = {}

    def _new(self) -> dict:
        return {"history": [], "key_facts": [], "stage": "opening"}

    def has(self, case_id: str) -> bool:
        return case_id in self._cases

    async def get(self, case_id: str) -> dict:
        mem = self._cases.get(case_id)
        if mem is not None:
            return mem
        # Rebuild from the store; a store error propagates (fail loudly, never a silent reset).
        rows = await get_runtime().store.list_messages(case_id)
        mem = self._new()
        for r in rows:
            mem["history"].append({"role": r["role"], "text": r["text"]})
        first = next((h["text"] for h in mem["history"] if h["role"] == "scammer"), None)
        if first:
            for f in opening_facts(first):
                self._add_fact(mem, f)
        try:
            for item in await get_runtime().store.list_intel(case_id):
                self._add_fact(mem, fact_for(item["kind"], item["value"]))
        except Exception:  # intel facts are a nice-to-have on rebuild
            pass
        if any(h["role"] == "persona" for h in mem["history"]):
            mem["stage"] = "engaged"
        # Another coroutine may have built it meanwhile; keep the first one.
        return self._cases.setdefault(case_id, mem)

    def append(self, case_id: str, role: str, text: str) -> None:
        self._cases.setdefault(case_id, self._new())["history"].append({"role": role, "text": text})

    @staticmethod
    def _add_fact(mem: dict, fact: str) -> None:
        fact = fact.strip()
        if not fact:
            return
        if fact.lower() in (f.lower() for f in mem["key_facts"]):
            return
        if len(mem["key_facts"]) < MAX_KEY_FACTS:
            mem["key_facts"].append(fact)

    def add_key_fact(self, case_id: str, fact: str) -> None:
        self._add_fact(self._cases.setdefault(case_id, self._new()), fact)

    def set_stage(self, case_id: str, stage: str) -> None:
        self._cases.setdefault(case_id, self._new())["stage"] = stage

    def forget(self, case_id: str) -> None:
        self._cases.pop(case_id, None)


memory = SessionMemory()  # process-wide singleton (one uvicorn worker)
