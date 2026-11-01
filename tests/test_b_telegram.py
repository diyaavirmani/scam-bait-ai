"""Track B: POST /telegram/webhook (orchestrator and store faked; Telegram Bot API faked with MockTransport)."""
import asyncio
import json
import logging

import httpx
import pytest
from fastapi import FastAPI

import app.orchestrator as orchestrator
from app.channels import router, telegram
from app.channels.telegram_api import TelegramAPI
from app.config import Settings
from app.models import Reply
from app.runtime import Runtime

SECRET = "test-webhook-secret"
TOKEN = "123456:FAKE-TOKEN-for-tests"


class FakeStore:
    def __init__(self):
        self.cases: list[dict] = []
        self.seen: set[str] = set()

    async def mark_seen(self, key):
        if key in self.seen:
            return False
        self.seen.add(key)
        return True

    async def new_case(self, channel, external_id):
        case = {"id": f"c_{len(self.cases):012x}", "channel": channel, "external_id": external_id,
                "status": "watching"}
        self.cases.append(case)
        return case

    async def get_or_create_case(self, channel, external_id):
        for case in reversed(self.cases):
            if case["external_id"] == external_id and case["status"] != "closed":
                return case
        return await self.new_case(channel, external_id)


@pytest.fixture
def env(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr("app.runtime._runtime", Runtime(
        settings=Settings(telegram_webhook_secret=SECRET, telegram_bot_token=TOKEN), store=store, bus=None))
    sent = []  # (method, payload) in order

    def tg_handler(request: httpx.Request) -> httpx.Response:
        sent.append((request.url.path.rsplit("/", 1)[-1], json.loads(request.content)))
        return httpx.Response(200, json={"ok": True, "result": True})

    telegram.set_api(TelegramAPI(TOKEN, client=httpx.AsyncClient(transport=httpx.MockTransport(tg_handler))))
    orch_calls = []
    state = {"reply": None, "delay": 0.0}

    async def fake_handle(case_id, channel, text):
        orch_calls.append((case_id, channel, text))
        if state["delay"]:
            await asyncio.sleep(state["delay"])
        r = state["reply"] or Reply(case_id=case_id, text="Haan ji, who is calling?", turn=len(orch_calls))
        return r.model_copy(update={"case_id": case_id})

    monkeypatch.setattr(orchestrator, "handle_message", fake_handle)
    app = FastAPI()
    app.include_router(router)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    yield {"client": client, "store": store, "sent": sent, "orch": orch_calls, "state": state}
    telegram.set_api(None)


def _update(update_id, chat_id=42, **msg):
    msg.setdefault("message_id", update_id)
    msg["chat"] = {"id": chat_id, "type": "private"}
    return {"update_id": update_id, "message": msg}


async def _post(env, update, secret=SECRET):
    headers = {"X-Telegram-Bot-Api-Secret-Token": secret} if secret is not None else {}
    r = await env["client"].post("/telegram/webhook", json=update, headers=headers)
    await telegram.drain()
    return r


async def test_secret_required(env):
    assert (await _post(env, _update(1, text="hi"), secret=None)).status_code == 403
    assert (await _post(env, _update(1, text="hi"), secret="wrong")).status_code == 403
    assert env["orch"] == [] and env["sent"] == [] and env["store"].seen == set()


async def test_unset_secret_is_403(env, monkeypatch):
    monkeypatch.setattr("app.runtime._runtime", Runtime(
        settings=Settings(telegram_webhook_secret="", telegram_bot_token=TOKEN), store=env["store"], bus=None))
    assert (await _post(env, _update(1, text="hi"), secret="")).status_code == 403


async def test_text_message_typing_then_reply(env):
    env["state"]["delay"] = 0.05
    r = await _post(env, _update(1, text="Hello sir, I am Rahul from SEBI"))
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert env["orch"] == [(env["store"].cases[0]["id"], "telegram", "Hello sir, I am Rahul from SEBI")]
    assert env["store"].cases[0]["external_id"] == "tg:42"
    methods = [m for m, _ in env["sent"]]
    assert methods[0] == "sendChatAction" and methods[-1] == "sendMessage"
    assert env["sent"][0][1] == {"chat_id": 42, "action": "typing"}
    assert env["sent"][-1][1] == {"chat_id": 42, "text": "Haan ji, who is calling?"}


async def test_typing_sent_even_when_reply_is_instant(env):
    await _post(env, _update(1, text="hi"))
    assert [m for m, _ in env["sent"]] == ["sendChatAction", "sendMessage"]


async def test_typing_repeats_while_waiting(env, monkeypatch):
    monkeypatch.setattr(telegram, "TYPING_INTERVAL", 0.02)
    env["state"]["delay"] = 0.09
    await _post(env, _update(1, text="hi"))
    methods = [m for m, _ in env["sent"]]
    assert methods.count("sendChatAction") >= 3 and methods[-1] == "sendMessage"
    assert "sendChatAction" not in methods[methods.index("sendMessage"):]


async def test_duplicate_update_processed_once(env):
    await _post(env, _update(7, text="pay to x@okaxis"))
    r = await _post(env, _update(7, text="pay to x@okaxis"))
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert len(env["orch"]) == 1
    assert [m for m, _ in env["sent"]].count("sendMessage") == 1


async def test_coalesced_reply_not_sent(env):
    env["state"]["reply"] = Reply(case_id="x", text="", coalesced=True)
    await _post(env, _update(1, text="part one"))
    assert len(env["orch"]) == 1
    assert "sendMessage" not in [m for m, _ in env["sent"]]


async def test_document_message_handled(env):
    doc = {"file_id": "abc", "file_name": "StockPro.apk", "mime_type": "application/vnd.android.package-archive"}
    r = await _post(env, _update(1, document=doc, caption="install this"))
    assert r.status_code == 200
    assert env["orch"][0][2] == "[sent a document: StockPro.apk] install this"
    assert env["sent"][-1][0] == "sendMessage"


async def test_other_media_notes(env):
    await _post(env, _update(1, photo=[{"file_id": "p", "width": 1, "height": 1}]))
    await _post(env, _update(2, voice={"file_id": "v", "duration": 3}))
    await _post(env, _update(3, sticker={"file_id": "s"}))
    await _post(env, _update(4, contact={"phone_number": "+919000000001", "first_name": "Priya"}))
    assert [c[2] for c in env["orch"]] == ["[sent a photo]", "[sent a voice note]", "[sent a sticker]",
                                           "[shared a contact: Priya +919000000001]"]


async def test_non_message_updates_ignored(env):
    for i, key in enumerate(["edited_message", "channel_post", "callback_query"], start=1):
        r = await _post(env, {"update_id": i, key: {"message_id": 1, "chat": {"id": 42}, "text": "x"}})
        assert r.status_code == 200
    r = await _post(env, _update(9, new_chat_members=[{"id": 1}]))
    assert r.status_code == 200
    assert env["orch"] == [] and env["sent"] == []


async def test_start_opens_new_case(env):
    await _post(env, _update(1, text="hello"))
    first = env["store"].cases[0]["id"]
    await _post(env, _update(2, text="/start"))
    assert len(env["store"].cases) == 2
    assert env["sent"][-1] == ("sendMessage", {"chat_id": 42, "text": "Hello? Who is this?"})
    assert len(env["orch"]) == 1  # /start is not passed to the orchestrator
    await _post(env, _update(3, text="I am from your bank"))
    assert env["orch"][-1][0] == env["store"].cases[1]["id"] != first


async def test_orchestrator_error_sends_in_character_fallback(env, monkeypatch):
    async def boom(case_id, channel, text):
        raise RuntimeError("model down")

    monkeypatch.setattr(orchestrator, "handle_message", boom)
    r = await _post(env, _update(1, text="hi"))
    assert r.status_code == 200
    assert env["sent"][-1] == ("sendMessage", {"chat_id": 42, "text": telegram.FALLBACK_REPLY})


async def test_telegram_api_errors_do_not_crash_and_token_not_logged(env, caplog):
    def failing(request):
        raise httpx.ConnectError("connection refused for " + str(request.url))

    telegram.set_api(TelegramAPI(TOKEN, client=httpx.AsyncClient(transport=httpx.MockTransport(failing))))
    caplog.set_level(logging.DEBUG)
    r = await _post(env, _update(1, text="hi"))
    assert r.status_code == 200 and len(env["orch"]) == 1
    assert "sendMessage" in caplog.text
    assert TOKEN not in caplog.text and TOKEN.split(":")[1] not in caplog.text


async def test_token_not_logged_on_success(env, caplog):
    caplog.set_level(logging.DEBUG)
    await _post(env, _update(1, text="hi"))
    assert env["sent"][-1][0] == "sendMessage"
    assert TOKEN not in caplog.text and TOKEN.split(":")[1] not in caplog.text
