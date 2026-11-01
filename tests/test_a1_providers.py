"""Milestone 04: limiter, Cerebras client (429 drill, metrics), OpenAI client. All HTTP is mocked."""
import asyncio
import json

import httpx
import pytest

from app.config import Settings
from app.providers import PRIORITY_BACKGROUND, PRIORITY_LIVE, PRIORITY_PERSONA, ProviderError, build_clients
from app.providers.cerebras import CerebrasClient, parse_metrics
from app.providers.limiter import RateLimiter
from app.providers.openai_client import OpenAIClient
from app.runtime import Runtime, set_runtime

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["is_scam", "p_scam"],
          "properties": {"is_scam": {"type": "boolean"}, "p_scam": {"type": "number"}}}


class FakeBus:
    def __init__(self):
        self.events = []

    async def emit(self, event):
        self.events.append(event)
        return event


class FakeStore:
    async def get_case(self, case_id):
        return {"id": case_id, "channel": "telegram"}


def settings(**kw):
    base = dict(openai_api_key="sk-test", cerebras_api_key="csk-test", cerebras_rpm_oss=50, cerebras_rpm_qwen=50,
                persona_model="gpt-oss-120b", flag_model="qwen-3.8-27b", decisions_model="gpt-6-luna")
    base.update(kw)
    return Settings(**base)


@pytest.fixture
def bus():
    b = FakeBus()
    set_runtime(Runtime(settings=settings(), store=FakeStore(), bus=b))
    return b


def completion(content: dict | str, completion_tokens=40, completion_time=0.02):
    return {
        "id": "chatcmpl-1", "object": "chat.completion", "created": 1, "model": "qwen-3.8-27b",
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant",
                                 "content": content if isinstance(content, str) else json.dumps(content)}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": completion_tokens, "total_tokens": 120 + completion_tokens,
                  "prompt_tokens_details": {"cached_tokens": 64}},
        "time_info": {"queue_time": 0.001, "prompt_time": 0.01, "completion_time": completion_time,
                      "total_time": 0.04, "created": 1},
    }


def cerebras_with(handler) -> CerebrasClient:
    client = CerebrasClient(settings(), http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    client._sleep = lambda s: asyncio.sleep(0)
    return client


async def call(client, **kw):
    args = dict(step="flag", model="qwen-3.8-27b", messages=[{"role": "user", "content": "x"}], schema=SCHEMA,
                schema_name="flag", priority=PRIORITY_LIVE, max_completion_tokens=150, reasoning_effort="none",
                case_id="c_000000000001", seed=7, cache_key="c_000000000001")
    args.update(kw)
    return await client.chat_json(**args)


async def test_429_then_200_retries_same_model(bus):
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append(body)
        if len(seen) == 1:
            return httpx.Response(429, headers={"retry-after": "0"},
                                  json={"message": "Requests per minute limit exceeded", "type": "too_many_requests_error"})
        return httpx.Response(200, json=completion({"is_scam": True, "p_scam": 0.93}))

    data, metrics = await call(cerebras_with(handler))
    assert data == {"is_scam": True, "p_scam": 0.93}
    assert [b["model"] for b in seen] == ["qwen-3.8-27b", "qwen-3.8-27b"]
    first = seen[0]
    assert first["response_format"]["type"] == "json_schema"
    assert first["response_format"]["json_schema"] == {"name": "flag", "strict": True, "schema": SCHEMA}
    assert first["reasoning_effort"] == "none" and first["seed"] == 7
    assert first["prompt_cache_key"] == "c_000000000001"
    assert "tools" not in first
    assert metrics.retries == 1
    types = [e.type for e in bus.events]
    assert "task.retrying" in types and "metrics.speed" in types and "ratelimit.status" in types
    retry = next(e for e in bus.events if e.type == "task.retrying")
    assert retry.data["model"] == "qwen-3.8-27b" and retry.data["step"] == "flag" and retry.channel == "telegram"


async def test_429_daily_bucket_raises_quota(bus):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(429, json={"message": "Tokens per day limit exceeded: too many requests per day"})

    with pytest.raises(ProviderError) as ei:
        await call(cerebras_with(handler))
    assert ei.value.kind == "rate_limit_quota"
    assert len(calls) == 1


async def test_429_gives_up_after_six_attempts(bus):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(429, headers={"retry-after": "0"}, json={"message": "Requests per minute exceeded"})

    with pytest.raises(ProviderError) as ei:
        await call(cerebras_with(handler))
    assert ei.value.kind == "rate_limit" and len(calls) == 6


async def test_5xx_retries_twice_then_outage(bus):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503, json={"message": "unavailable"})

    with pytest.raises(ProviderError) as ei:
        await call(cerebras_with(handler))
    assert ei.value.kind == "outage" and len(calls) == 3


async def test_bad_json_and_missing_keys(bus):
    with pytest.raises(ProviderError) as ei:
        await call(cerebras_with(lambda r: httpx.Response(200, json=completion("not json"))))
    assert ei.value.kind == "bad_output"
    with pytest.raises(ProviderError) as ei:
        await call(cerebras_with(lambda r: httpx.Response(200, json=completion({"is_scam": True}))))
    assert ei.value.kind == "bad_output"


async def test_time_info_metrics(bus):
    _, m = await call(cerebras_with(lambda r: httpx.Response(200, json=completion({"is_scam": False, "p_scam": 0.1},
                                                                                  completion_tokens=50,
                                                                                  completion_time=0.025))))
    assert m.provider == "cerebras" and m.model == "qwen-3.8-27b"
    assert m.tokens_per_s == 2000.0
    assert m.prompt_tokens == 120 and m.completion_tokens == 50 and m.cached_tokens == 64
    speed = next(e for e in bus.events if e.type == "metrics.speed")
    assert speed.data["tokens_per_s"] == 2000.0


def test_parse_metrics_without_time_info():
    class R:
        usage = None
        model_extra = {}
    m = parse_metrics(R(), step="flag", model="x", ms=5, queued_ms=0, retries=0)
    assert m.tokens_per_s is None and m.ms == 5


async def test_events_never_break_calls():
    class BrokenBus:
        async def emit(self, e):
            raise NotImplementedError
    set_runtime(Runtime(settings=settings(), store=object(), bus=BrokenBus()))
    data, _ = await call(cerebras_with(lambda r: httpx.Response(200, json=completion({"is_scam": True, "p_scam": 1}))))
    assert data["is_scam"] is True


async def test_self_test_reports_missing_model(bus):
    def handler(req):
        return httpx.Response(200, json={"object": "list", "data": [{"id": "gpt-oss-120b", "object": "model",
                                                                     "created": 1, "owned_by": "cerebras"}]})
    with pytest.raises(ProviderError) as ei:
        await cerebras_with(handler).self_test()
    assert "qwen-3.8-27b" in str(ei.value)


async def test_limiter_priority_order():
    lim = RateLimiter("m", rpm=1, window_s=0.2)
    assert await lim.acquire(PRIORITY_BACKGROUND) == 0
    order = []

    async def take(p, name):
        await lim.acquire(p)
        order.append(name)

    tasks = [asyncio.create_task(take(PRIORITY_BACKGROUND, "bg")), asyncio.create_task(take(PRIORITY_LIVE, "live"))]
    await asyncio.sleep(0.01)
    tasks.append(asyncio.create_task(take(PRIORITY_PERSONA, "persona")))
    await asyncio.sleep(0.01)
    st = lim.status()
    assert st == {"model": "m", "rpm_used": 1, "rpm_limit": 1, "waiting": 3}
    await asyncio.wait_for(asyncio.gather(*tasks), 2)
    assert order == ["persona", "live", "bg"]


async def test_limiter_returns_queued_ms():
    lim = RateLimiter("m", rpm=1, window_s=0.1)
    await lim.acquire(0)
    q = await lim.acquire(0)
    assert q >= 50


async def test_decisions_errors_and_body():
    seen = []

    def handler(req):
        seen.append(req)
        if len(seen) == 1:
            return httpx.Response(200, json={"answers": []})
        if len(seen) == 2:
            return httpx.Response(403, json={"error": {"message": "no access"}})
        return httpx.Response(500, json={})

    oc = OpenAIClient(settings(), http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await oc.decisions(input="hi", questions=[{"type": "predicate", "name": "q", "instructions": "x"}],
                              cache_key="k") == {"answers": []}
    body = json.loads(seen[0].content)
    assert body["model"] == "gpt-6-luna" and body["prompt_cache_key"] == "k"
    assert str(seen[0].url) == "https://api.openai.com/v1/decisions"
    with pytest.raises(ProviderError) as ei:
        await oc.decisions(input="hi", questions=[], cache_key="k")
    assert ei.value.kind == "unavailable" and "403" in str(ei.value) and "sk-test" not in str(ei.value)
    with pytest.raises(ProviderError) as ei:
        await oc.decisions(input="hi", questions=[], cache_key="k")
    assert ei.value.kind == "outage"


async def test_moderate_parses_categories():
    def handler(req):
        return httpx.Response(200, json={"id": "modr-1", "model": "omni-moderation-latest", "results": [{
            "flagged": True,
            "categories": {"harassment": True, "violence": False, "self-harm": False},
            "category_scores": {"harassment": 0.9, "violence": 0.0, "self-harm": 0.0},
        }]})
    oc = OpenAIClient(settings(), http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    out = await oc.moderate("x")
    assert out["flagged"] is True and out["categories"] == ["harassment"]


def test_build_clients():
    c, o = build_clients(settings())
    assert isinstance(c, CerebrasClient) and isinstance(o, OpenAIClient)
    assert c.limiter("qwen-3.8-27b").rpm == 50
