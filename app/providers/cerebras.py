"""Cerebras through the openai SDK (base_url=https://api.cerebras.ai/v1, max_retries=0). Track A, commit 4."""
from __future__ import annotations

from typing import Optional

from app.models import CallMetrics


class CerebrasClient:
    async def chat_json(self, *, step: str, model: str, messages: list[dict], schema: dict, schema_name: str,
                        priority: int, max_completion_tokens: int, reasoning_effort: Optional[str],
                        case_id: Optional[str] = None, cache_key: Optional[str] = None,
                        seed: Optional[int] = None) -> tuple[dict, CallMetrics]:
        """Strict json_schema call. Retries a 429 on the same model. Emits metrics.speed. Raises ProviderError."""
        raise NotImplementedError

    async def self_test(self) -> dict:
        """List models; fail loudly if PERSONA_MODEL or FLAG_MODEL is missing."""
        raise NotImplementedError
