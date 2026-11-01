from __future__ import annotations


class SessionMemory:
    """In-process memory per case: full history, pinned key facts, stage. Rebuilt from the store if missing."""

    async def get(self, case_id: str) -> dict: raise NotImplementedError
    def append(self, case_id: str, role: str, text: str) -> None: raise NotImplementedError
    def add_key_fact(self, case_id: str, fact: str) -> None: raise NotImplementedError
