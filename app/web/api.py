"""Dashboard JSON API: GET /api/v1/cases and GET /api/v1/cases/{id}. Login cookie required. Track C, commit 18."""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.web.auth import require_api

router = APIRouter(dependencies=[Depends(require_api)])

CASE_ID_RE = re.compile(r"^c_[0-9a-f]{12}$")
MAX_TURNS = 20
CASE_EVENT_LIMIT = 2000


def _store():
    from app.runtime import get_runtime
    return get_runtime().store


async def load_case(case_id: str) -> dict:
    if not CASE_ID_RE.match(case_id or ""):
        raise HTTPException(status_code=404, detail="case not found")
    case = await _store().get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    return case


async def case_events(case_id: str, limit: int = CASE_EVENT_LIMIT) -> list:
    store = _store()
    if hasattr(store, "events_for_case"):
        return await store.events_for_case(case_id, limit)
    out, cursor = [], 0  # fallback scan for stores without the per-case query
    while True:
        batch = await store.events_after(cursor, 1000)
        out.extend(e for e in batch if e.case_id == case_id)
        if len(batch) < 1000:
            return out[-limit:]
        cursor = batch[-1].id


def intel_with_source(intel: list[dict], events: list) -> list[dict]:
    """intel_items rows plus the extraction source (regex, persona, call_batch) from intel.extracted events."""
    src = {}
    for e in events:
        if e.type == "intel.extracted":
            src.setdefault((e.data.get("kind"), e.data.get("value")), e.data.get("source"))
    return [{**row, "source": src.get((row.get("kind"), row.get("value")))} for row in intel]


async def case_detail(case_id: str) -> dict:
    store = _store()
    case = await load_case(case_id)
    events = await case_events(case_id)
    messages = await store.list_messages(case_id)
    intel = intel_with_source(await store.list_intel(case_id), events)
    evidence = await store.list_evidence(case_id) if hasattr(store, "list_evidence") else []
    turns = sum(1 for m in messages if m.get("role") == "scammer")
    return {
        "case": case, "messages": messages, "intel": intel, "evidence": evidence,
        "events": [e.model_dump() for e in events], "turns": turns, "max_turns": MAX_TURNS,
    }


@router.get("/api/v1/cases")
async def list_cases(channel: Optional[str] = None, limit: int = 100, with_evidence: bool = False) -> dict:
    store = _store()
    limit = max(1, min(int(limit), 500))
    rows = await store.list_cases(limit)
    if channel:
        wanted = {c.strip() for c in channel.split(",") if c.strip()}
        rows = [r for r in rows if r.get("channel") in wanted]
    for r in rows:
        r["turns"] = await store.count_messages(r["id"], "scammer")
        if with_evidence:
            r["evidence"] = await store.list_evidence(r["id"])
    return {"cases": rows, "max_turns": MAX_TURNS}


@router.get("/api/v1/cases/{case_id}")
async def get_case(case_id: str) -> dict:
    return await case_detail(case_id)


@router.get("/api/networks")
async def list_networks() -> list:
    """Scammer networks: cases sharing an identical normalised identifier, grouped with union-find."""
    from app.networks import compute_networks
    return await compute_networks(_store())
