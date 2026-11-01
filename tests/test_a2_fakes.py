"""Shared fakes for the Track A2 tests (persona, extraction, orchestrator). No network calls."""
from __future__ import annotations

import asyncio
import itertools
from typing import Any, Callable, Optional

import pytest

from app.config import Settings
from app.models import CallMetrics, Event, utc_now
from app.runtime import Runtime, set_runtime


class MemStore:
    """In-memory stand-in for app.store.Store, used only if the real store is not implemented yet."""

    def __init__(self) -> None:
        self.cases: dict[str, dict] = {}
        self.messages: list[dict] = []
        self.intel: list[dict] = []
        self.events: list[Event] = []
        self._ids = itertools.count(1)

    async def init(self) -> None: ...
    async def close(self) -> None: ...

    async def new_case(self, channel: str, external_id: str) -> dict:
        cid = f"c_{len(self.cases):012x}"
        self.cases[cid] = {"id": cid, "channel": channel, "external_id": external_id, "status": "watching",
                           "scam_type": None, "verdict": None, "summary": None, "created_at": utc_now(),
                           "updated_at": utc_now()}
        return dict(self.cases[cid])

    async def get_or_create_case(self, channel: str, external_id: str) -> dict:
        for c in self.cases.values():
            if c["external_id"] == external_id and c["status"] != "closed":
                return dict(c)
        return await self.new_case(channel, external_id)

    async def get_case(self, case_id: str) -> Optional[dict]:
        c = self.cases.get(case_id)
        return dict(c) if c else None

    async def update_case(self, case_id: str, **fields) -> None:
        self.cases[case_id].update(fields, updated_at=utc_now())

    async def add_message(self, case_id: str, role: str, text: str) -> int:
        mid = next(self._ids)
        self.messages.append({"id": mid, "case_id": case_id, "role": role, "text": text, "ts": utc_now()})
        return mid

    async def list_messages(self, case_id: str) -> list[dict]:
        return [dict(m) for m in self.messages if m["case_id"] == case_id]

    async def count_messages(self, case_id: str, role: str) -> int:
        return sum(1 for m in self.messages if m["case_id"] == case_id and m["role"] == role)

    async def add_intel(self, case_id: str, kind: str, value: str, message_id: Optional[int]) -> bool:
        if any(i["case_id"] == case_id and i["kind"] == kind and i["value"] == value for i in self.intel):
            return False
        self.intel.append({"case_id": case_id, "kind": kind, "value": value, "message_id": message_id,
                           "first_seen": utc_now()})
        return True

    async def list_intel(self, case_id: str) -> list[dict]:
        return [dict(i) for i in self.intel if i["case_id"] == case_id]


class ListBus:
    def __init__(self) -> None:
        self.events: list[Event] = []

    async def emit(self, event: Event) -> Event:
        self.events.append(event)
        return event

    def of(self, type_: str) -> list[Event]:
        return [e for e in self.events if e.type == type_]


def _metrics(step: str, model: str) -> CallMetrics:
    return CallMetrics(step=step, provider="cerebras", model=model, ms=5)


class FakeCerebras:
    """chat_json returns handler(step, kwargs) -> dict, or raises what the handler raises."""

    def __init__(self, handler: Callable[[str, dict], Any]) -> None:
        self.handler = handler
        self.calls: list[dict] = []
        self.delay = 0.0

    async def chat_json(self, step, model, messages, schema, schema_name, priority, max_completion_tokens,
                        reasoning_effort, case_id=None, cache_key=None, seed=None):
        kw = dict(step=step, model=model, messages=messages, schema=schema, schema_name=schema_name,
                  priority=priority, max_completion_tokens=max_completion_tokens,
                  reasoning_effort=reasoning_effort, case_id=case_id, cache_key=cache_key)
        self.calls.append(kw)
        if self.delay:
            await asyncio.sleep(self.delay)
        res = self.handler(step, kw)
        if asyncio.iscoroutine(res):
            res = await res
        return res, _metrics(step, model)


class FakeOpenAI:
    def __init__(self) -> None:
        self.moderated: list[str] = []

    async def moderate(self, text: str) -> dict:
        self.moderated.append(text)
        return {"flagged": False, "categories": {}}

    async def decisions(self, input, questions, cache_key=None) -> dict:
        return {}


async def make_store(tmp_path) -> Any:
    """Real app.store.Store on a tmp path when implemented, else the in-memory stand-in."""
    try:
        from app.store import Store
        s = Store(str(tmp_path / "t.db"))
        await s.init()
        return s
    except NotImplementedError:
        return MemStore()


_open_stores: list = []


@pytest.fixture(autouse=False)
async def a2_cleanup():
    """Closes every store opened by install() so aiosqlite threads do not outlive the test loop."""
    yield
    while _open_stores:
        s = _open_stores.pop()
        try:
            await s.close()
        except Exception:
            pass


async def install(tmp_path, handler: Callable[[str, dict], Any]) -> Runtime:
    store = await make_store(tmp_path)
    _open_stores.append(store)
    rt = Runtime(settings=Settings(), store=store, bus=ListBus(), cerebras=FakeCerebras(handler),
                 openai=FakeOpenAI())
    set_runtime(rt)
    return rt
