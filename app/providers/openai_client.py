"""OpenAI: Decisions (gpt-6-luna), moderation, Responses fallback for the case report. Track A, commit 4/7."""
from __future__ import annotations


class OpenAIClient:
    async def decisions(self, *, input: str, questions: list[dict], cache_key: str) -> dict:
        raise NotImplementedError

    async def moderate(self, text: str) -> dict:
        """{flagged: bool, categories: [names]}"""
        raise NotImplementedError

    async def responses_json(self, *, instructions: str, input: str, schema: dict, schema_name: str) -> dict:
        """Only for the case report after a hard Cerebras outage, never for a 429."""
        raise NotImplementedError
