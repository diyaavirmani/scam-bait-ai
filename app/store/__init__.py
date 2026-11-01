"""SQLite store: WAL, one aiosqlite connection (single writer). Implemented in commit 3."""
from __future__ import annotations

from typing import Optional

from app.models import Event


class Store:
    def __init__(self, path: str) -> None:
        self.path = path

    async def init(self) -> None: raise NotImplementedError
    async def close(self) -> None: raise NotImplementedError
    async def ping(self) -> bool: raise NotImplementedError
    # cases
    async def get_or_create_case(self, channel: str, external_id: str) -> dict: raise NotImplementedError
    async def new_case(self, channel: str, external_id: str) -> dict: raise NotImplementedError
    async def get_case(self, case_id: str) -> Optional[dict]: raise NotImplementedError
    async def update_case(self, case_id: str, **fields) -> None: raise NotImplementedError
    async def list_cases(self, limit: int = 100) -> list[dict]: raise NotImplementedError
    # messages
    async def add_message(self, case_id: str, role: str, text: str) -> int: raise NotImplementedError
    async def list_messages(self, case_id: str) -> list[dict]: raise NotImplementedError
    async def count_messages(self, case_id: str, role: str) -> int: raise NotImplementedError
    # intel
    async def add_intel(self, case_id: str, kind: str, value: str, message_id: Optional[int]) -> bool: raise NotImplementedError
    async def list_intel(self, case_id: str) -> list[dict]: raise NotImplementedError
    # events
    async def add_event(self, event: Event) -> int: raise NotImplementedError
    async def events_after(self, last_id: int, limit: int = 500) -> list[Event]: raise NotImplementedError
    # evidence + idempotency
    async def add_evidence(self, case_id: str, kind: str, path: str, sha256: str) -> None: raise NotImplementedError
    async def list_evidence(self, case_id: str) -> list[dict]: raise NotImplementedError
    async def mark_seen(self, key: str) -> bool: raise NotImplementedError
