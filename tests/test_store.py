import asyncio

import pytest

from app.models import Event
from app.store import Store


@pytest.fixture
async def store(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    await s.init()
    yield s
    await s.close()


async def test_wal_and_ping(store):
    async with store.db.execute("PRAGMA journal_mode") as cur:
        assert (await cur.fetchone())[0] == "wal"
    assert await store.ping()


async def test_case_lifecycle(store):
    c = await store.get_or_create_case("telegram", "tg:1")
    assert c["status"] == "watching" and c["id"].startswith("c_")
    assert (await store.get_or_create_case("telegram", "tg:1"))["id"] == c["id"]
    await store.update_case(c["id"], status="closed", verdict="scam", scam_type="investment_trading")
    c2 = await store.get_or_create_case("telegram", "tg:1")
    assert c2["id"] != c["id"]
    with pytest.raises(ValueError):
        await store.update_case(c["id"], id="x")


async def test_messages_and_intel_dedupe(store):
    c = await store.new_case("api", "api:s1")
    m = await store.add_message(c["id"], "scammer", "pay to x@okaxis")
    assert await store.count_messages(c["id"], "scammer") == 1
    assert await store.add_intel(c["id"], "upi", "x@okaxis", m) is True
    assert await store.add_intel(c["id"], "upi", "x@okaxis", m) is False
    assert len(await store.list_intel(c["id"])) == 1
    with pytest.raises(ValueError):
        await store.add_message(c["id"], "user", "spoofed role")


async def test_events_replay_and_seen(store):
    ids = [await store.add_event(Event(channel="api", type="message.received", data={"n": i})) for i in range(3)]
    after = await store.events_after(ids[0])
    assert [e.data["n"] for e in after] == [1, 2] and after[0].id == ids[1]
    assert await store.mark_seen("tg:5") is True
    assert await store.mark_seen("tg:5") is False


async def test_concurrent_writes_single_writer(store):
    c = await store.new_case("api", "api:s2")
    await asyncio.gather(*[store.add_message(c["id"], "scammer", f"m{i}") for i in range(50)])
    assert await store.count_messages(c["id"], "scammer") == 50
