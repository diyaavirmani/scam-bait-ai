"""Cerebras through the openai SDK (base_url=https://api.cerebras.ai/v1, max_retries=0). Track A, commit 4.

Rules (docs/REBUILD_REPORT.md, Rate limits and model pinning):
- one pooled client, SDK retries off, 30 s timeout;
- a 429 waits (Retry-After or 3 s) and retries the SAME model, never another one;
- a 429 that names an hourly or daily bucket raises ProviderError("rate_limit_quota") at once;
- 5xx, timeouts and connection errors retry twice (1 s, 2 s), then ProviderError("outage").
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Optional

import httpx
import openai

from app.models import CallMetrics, Event
from app.providers import ProviderError
from app.providers.limiter import RateLimiter

log = logging.getLogger(__name__)

MAX_429_ATTEMPTS = 6
DEFAULT_429_WAIT_S = 3.0
OUTAGE_BACKOFF_S = (1.0, 2.0)
QUOTA_RE = re.compile(r"\b(hour|hours|hourly|day|days|daily)\b", re.IGNORECASE)

_case_channels: dict[str, str] = {}


async def _channel_for(case_id: Optional[str]) -> str:
    """Channel of a case for event routing; "api" when unknown. Never raises."""
    if not case_id:
        return "api"
    if case_id in _case_channels:
        return _case_channels[case_id]
    channel = "api"
    try:
        from app.runtime import get_runtime
        case = await get_runtime().store.get_case(case_id)
        if case and case.get("channel") in ("telegram", "api", "call"):
            channel = case["channel"]
            _case_channels[case_id] = channel
    except Exception as e:  # store not ready or stubbed
        log.debug("channel lookup failed: %s", type(e).__name__)
    return channel


async def emit_event(case_id: Optional[str], type_: str, data: dict) -> None:
    """Emit through app.events; a missing or stub bus never breaks a model call."""
    try:
        from app import events
        channel = await _channel_for(case_id)
        await events.emit(Event(case_id=case_id, channel=channel, type=type_, data=data))
    except Exception as e:
        log.debug("event %s not emitted: %s", type_, type(e).__name__)


def _retry_after_s(err: openai.APIStatusError) -> float:
    try:
        raw = err.response.headers.get("retry-after")
        if raw is not None:
            return max(0.0, float(raw))
    except (TypeError, ValueError, AttributeError):
        pass
    return DEFAULT_429_WAIT_S


def _err_text(err: openai.APIStatusError) -> str:
    parts = [str(getattr(err, "message", "") or "")]
    body = getattr(err, "body", None)
    if body is not None:
        parts.append(json.dumps(body) if not isinstance(body, str) else body)
    return " ".join(parts)


def _time_info(resp: Any) -> dict:
    ti = None
    extra = getattr(resp, "model_extra", None) or {}
    if isinstance(extra, dict):
        ti = extra.get("time_info")
    if ti is None:
        ti = getattr(resp, "time_info", None)
    if ti is None:
        return {}
    if isinstance(ti, dict):
        return ti
    try:
        return dict(ti.model_dump()) if hasattr(ti, "model_dump") else dict(vars(ti))
    except Exception:
        return {}


def parse_metrics(resp: Any, *, step: str, model: str, ms: int, queued_ms: int, retries: int) -> CallMetrics:
    """usage + Cerebras time_info -> CallMetrics. tokens_per_s = completion_tokens / completion_time."""
    usage = getattr(resp, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
    completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
    cached = None
    details = getattr(usage, "prompt_tokens_details", None) if usage else None
    if details is not None:
        cached = details.get("cached_tokens") if isinstance(details, dict) else getattr(details, "cached_tokens", None)
    tps = None
    ti = _time_info(resp)
    ct = ti.get("completion_time")
    if completion_tokens and isinstance(ct, (int, float)) and ct > 0:
        tps = round(completion_tokens / ct, 1)
    return CallMetrics(step=step, provider="cerebras", model=model, ms=ms, queued_ms=queued_ms, retries=retries,
                       tokens_per_s=tps, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                       cached_tokens=cached)


class CerebrasClient:
    def __init__(self, settings, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self.settings = settings
        self.client = openai.AsyncOpenAI(base_url=settings.cerebras_base_url, api_key=settings.cerebras_api_key or "missing",
                                         max_retries=0, timeout=30, http_client=http_client)
        self.limiters: dict[str, RateLimiter] = {}
        self._sleep = asyncio.sleep  # tests replace this

    def limiter(self, model: str) -> RateLimiter:
        if model not in self.limiters:
            rpm = self.settings.cerebras_rpm_qwen if model == self.settings.flag_model else self.settings.cerebras_rpm_oss
            self.limiters[model] = RateLimiter(model, rpm)
        return self.limiters[model]

    async def chat_json(self, *, step: str, model: str, messages: list[dict], schema: dict, schema_name: str,
                        priority: int, max_completion_tokens: int, reasoning_effort: Optional[str],
                        case_id: Optional[str] = None, cache_key: Optional[str] = None,
                        seed: Optional[int] = None) -> tuple[dict, CallMetrics]:
        """Strict json_schema call. Retries a 429 on the same model. Emits metrics.speed. Raises ProviderError."""
        kwargs: dict[str, Any] = {
            "model": model, "messages": messages, "max_completion_tokens": max_completion_tokens,
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": schema_name, "strict": True, "schema": schema}},
        }
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
        if seed is not None:
            kwargs["seed"] = seed
        if cache_key:
            kwargs["extra_body"] = {"prompt_cache_key": cache_key}

        lim = self.limiter(model)
        retries, rl_attempts, outage_attempts, queued_total = 0, 0, 0, 0
        t0 = time.monotonic()
        while True:
            queued_total += await lim.acquire(priority)
            await emit_event(case_id, "ratelimit.status", lim.status())
            try:
                resp = await self.client.chat.completions.create(**kwargs)
                break
            except openai.RateLimitError as e:
                rl_attempts += 1
                text = _err_text(e)
                if QUOTA_RE.search(text):
                    raise ProviderError("rate_limit_quota", f"{model}: hourly or daily bucket exhausted (429)") from None
                if rl_attempts >= MAX_429_ATTEMPTS:
                    raise ProviderError("rate_limit", f"{model}: still 429 after {rl_attempts} attempts") from None
                wait = _retry_after_s(e)
                retries += 1
                await emit_event(case_id, "task.retrying", {"step": step, "model": model,
                                                            "retry_in_ms": int(wait * 1000), "reason": "rate_limit_429"})
                await self._sleep(wait)
            except (openai.APITimeoutError, openai.APIConnectionError, openai.InternalServerError) as e:
                if outage_attempts >= len(OUTAGE_BACKOFF_S):
                    raise ProviderError("outage", f"{model}: {type(e).__name__} after retries") from None
                wait = OUTAGE_BACKOFF_S[outage_attempts]
                outage_attempts += 1
                retries += 1
                await emit_event(case_id, "task.retrying", {"step": step, "model": model,
                                                            "retry_in_ms": int(wait * 1000), "reason": type(e).__name__})
                await self._sleep(wait)
            except (openai.AuthenticationError, openai.PermissionDeniedError, openai.NotFoundError) as e:
                raise ProviderError("unavailable", f"{model}: HTTP {e.status_code}") from None
            except openai.APIStatusError as e:  # other 4xx: our request is wrong
                raise ProviderError("bad_request", f"{model}: HTTP {e.status_code}") from None

        ms = int((time.monotonic() - t0) * 1000)
        metrics = parse_metrics(resp, step=step, model=model, ms=ms, queued_ms=queued_total, retries=retries)
        await emit_event(case_id, "metrics.speed", metrics.model_dump())
        await emit_event(case_id, "ratelimit.status", lim.status())

        content = None
        try:
            content = resp.choices[0].message.content
        except (AttributeError, IndexError):
            pass
        if not content:
            raise ProviderError("bad_output", f"{model}: empty content")
        try:
            data = json.loads(content)
        except (TypeError, ValueError):
            raise ProviderError("bad_output", f"{model}: invalid JSON") from None
        if not isinstance(data, dict):
            raise ProviderError("bad_output", f"{model}: JSON is not an object")
        missing = [k for k in schema.get("required", []) if k not in data]
        if missing:
            raise ProviderError("bad_output", f"{model}: missing keys {missing}")
        return data, metrics

    async def self_test(self) -> dict:
        """List models; fail loudly if PERSONA_MODEL or FLAG_MODEL is missing."""
        try:
            page = await self.client.models.list()
            ids = [m.id for m in page.data]
        except openai.APIStatusError as e:
            raise ProviderError("unavailable", f"Cerebras model list failed: HTTP {e.status_code}") from None
        except (openai.APITimeoutError, openai.APIConnectionError) as e:
            raise ProviderError("outage", f"Cerebras model list failed: {type(e).__name__}") from None
        wanted = [self.settings.persona_model, self.settings.flag_model]
        missing = [m for m in wanted if m not in ids]
        if missing:
            raise ProviderError("unavailable", f"Cerebras models missing: {', '.join(missing)} (available: {', '.join(ids)})")
        return {"ok": True, "models": wanted}

