"""OpenAI: Decisions (gpt-6-luna), moderation, Responses fallback for the case report. Track A, commit 4/7.

Error messages carry the HTTP status, never the key.
"""
from __future__ import annotations

import json
from typing import Optional

import httpx
import openai

from app.providers import ProviderError

DECISIONS_URL = "https://api.openai.com/v1/decisions"
DECISIONS_TIMEOUT_S = 15.0
MODERATION_MODEL = "omni-moderation-latest"


class OpenAIClient:
    def __init__(self, settings, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self.settings = settings
        self.http = http_client or httpx.AsyncClient(timeout=DECISIONS_TIMEOUT_S)
        self.client = openai.AsyncOpenAI(api_key=settings.openai_api_key or "missing", max_retries=0, timeout=30,
                                         http_client=http_client)

    async def decisions(self, *, input, questions: list[dict], cache_key: str) -> dict:
        """POST /v1/decisions. input is a string or a list of input items. Returns the parsed JSON body."""
        body = {"model": self.settings.decisions_model, "input": input, "questions": questions,
                "prompt_cache_key": cache_key}
        headers = {"Authorization": f"Bearer {self.settings.openai_api_key}", "Content-Type": "application/json"}
        try:
            r = await self.http.post(DECISIONS_URL, json=body, headers=headers, timeout=DECISIONS_TIMEOUT_S)
        except httpx.TimeoutException:
            raise ProviderError("outage", "decisions: timeout") from None
        except httpx.HTTPError as e:
            raise ProviderError("outage", f"decisions: {type(e).__name__}") from None
        if r.status_code in (401, 403, 404):
            raise ProviderError("unavailable", f"decisions: HTTP {r.status_code}")
        if not 200 <= r.status_code < 300:
            raise ProviderError("outage", f"decisions: HTTP {r.status_code}")
        try:
            data = r.json()
        except ValueError:
            raise ProviderError("bad_output", "decisions: invalid JSON") from None
        if not isinstance(data, dict):
            raise ProviderError("bad_output", "decisions: JSON is not an object")
        return data

    async def moderate(self, text: str) -> dict:
        """{flagged: bool, categories: [names]}"""
        try:
            resp = await self.client.moderations.create(model=MODERATION_MODEL, input=text)
        except openai.APIStatusError as e:
            kind = "unavailable" if e.status_code in (401, 403, 404) else "outage"
            raise ProviderError(kind, f"moderation: HTTP {e.status_code}") from None
        except (openai.APITimeoutError, openai.APIConnectionError) as e:
            raise ProviderError("outage", f"moderation: {type(e).__name__}") from None
        result = resp.results[0]
        cats = result.categories
        cat_map = cats.model_dump(by_alias=True) if hasattr(cats, "model_dump") else dict(cats)
        return {"flagged": bool(result.flagged), "categories": sorted(k for k, v in cat_map.items() if v)}

    async def responses_json(self, *, instructions: str, input: str, schema: dict, schema_name: str) -> dict:
        """Only for the case report after a hard Cerebras outage, never for a 429."""
        try:
            resp = await self.client.responses.create(
                model=self.settings.decisions_model, instructions=instructions, input=input,
                text={"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}})
        except openai.APIStatusError as e:
            kind = "unavailable" if e.status_code in (401, 403, 404) else "outage"
            raise ProviderError(kind, f"responses: HTTP {e.status_code}") from None
        except (openai.APITimeoutError, openai.APIConnectionError) as e:
            raise ProviderError("outage", f"responses: {type(e).__name__}") from None
        try:
            data = json.loads(resp.output_text)
        except (TypeError, ValueError):
            raise ProviderError("bad_output", "responses: invalid JSON") from None
        if not isinstance(data, dict):
            raise ProviderError("bad_output", "responses: JSON is not an object")
        return data
