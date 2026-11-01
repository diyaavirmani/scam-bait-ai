"""SQLite store: WAL, one aiosqlite connection that is the only writer (C-01). Schema in docs/CONTRACTS.md."""
from __future__ import annotations

import asyncio
import json
import secrets
from typing import Optional

import aiosqlite

from app.models import Event, utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY, channel TEXT NOT NULL, external_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'watching',
    scam_type TEXT NOT NULL DEFAULT 'unknown', verdict TEXT NOT NULL DEFAULT 'unknown', summary TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cases_external ON cases(external_id, status);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL REFERENCES cases(id), role TEXT NOT NULL,
    text TEXT NOT NULL, ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_case ON messages(case_id, id);
CREATE TABLE IF NOT EXISTS intel_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL REFERENCES cases(id), kind TEXT NOT NULL,
    value TEXT NOT NULL, message_id INTEGER, first_seen TEXT NOT NULL, norm TEXT NOT NULL DEFAULT '',
    UNIQUE(case_id, kind, value)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, case_id TEXT, channel TEXT NOT NULL, type TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_case ON events(case_id, id);
CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL REFERENCES cases(id), kind TEXT NOT NULL,
    path TEXT NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS seen_keys (key TEXT PRIMARY KEY, ts TEXT NOT NULL);
"""

CASE_FIELDS = {"channel", "external_id", "status", "scam_type", "verdict", "summary"}


class Store:
    def __init__(self, path: str) -> None:
        self.path = path
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()  # one write at a time on the one connection

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.execute("PRAGMA busy_timeout=5000")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(SCHEMA)
        await self._migrate()
        await self._db.execute("CREATE INDEX IF NOT EXISTS idx_intel_norm ON intel_items(kind, norm)")
        await self._db.commit()

    async def _migrate(self) -> None:
        """Older databases have no intel_items.norm column: add it and backfill normalised values."""
        from app.networks import normalise
        async with self._db.execute("PRAGMA table_info(intel_items)") as cur:
            cols = {r[1] for r in await cur.fetchall()}
        if "norm" in cols:
            return
        await self._db.execute("ALTER TABLE intel_items ADD COLUMN norm TEXT NOT NULL DEFAULT ''")
        async with self._db.execute("SELECT id, kind, value FROM intel_items") as cur:
            rows = await cur.fetchall()
        for rid, kind, value in rows:
            await self._db.execute("UPDATE intel_items SET norm=? WHERE id=?", (normalise(kind, value), rid))

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Store.init() was not called")
        return self._db

    async def ping(self) -> bool:
        try:
            async with self.db.execute("SELECT 1") as cur:
                return (await cur.fetchone())[0] == 1
        except Exception:
            return False

    async def _write(self, sql: str, params: tuple = ()) -> int:
        async with self._lock:
            cur = await self.db.execute(sql, params)
            await self.db.commit()
            return cur.lastrowid

    async def _all(self, sql: str, params: tuple = ()) -> list[dict]:
        async with self.db.execute(sql, params) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def _one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        async with self.db.execute(sql, params) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    # ---------- cases ----------
    async def new_case(self, channel: str, external_id: str) -> dict:
        case_id = "c_" + secrets.token_hex(6)
        now = utc_now()
        await self._write(
            "INSERT INTO cases (id, channel, external_id, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (case_id, channel, external_id, "watching", now, now))
        return await self.get_case(case_id)

    async def get_or_create_case(self, channel: str, external_id: str) -> dict:
        """The newest case for this external id that is not closed, or a new one."""
        row = await self._one(
            "SELECT * FROM cases WHERE external_id=? AND status!='closed' ORDER BY created_at DESC LIMIT 1",
            (external_id,))
        return row or await self.new_case(channel, external_id)

    async def get_case(self, case_id: str) -> Optional[dict]:
        return await self._one("SELECT * FROM cases WHERE id=?", (case_id,))

    async def update_case(self, case_id: str, **fields) -> None:
        bad = set(fields) - CASE_FIELDS
        if bad:
            raise ValueError(f"unknown case fields: {sorted(bad)}")
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        await self._write(f"UPDATE cases SET {cols}, updated_at=? WHERE id=?",
                          (*fields.values(), utc_now(), case_id))

    async def list_cases(self, limit: int = 100) -> list[dict]:
        return await self._all("SELECT * FROM cases ORDER BY updated_at DESC LIMIT ?", (limit,))

    # ---------- messages ----------
    async def add_message(self, case_id: str, role: str, text: str) -> int:
        if role not in ("scammer", "persona"):
            raise ValueError("role must be scammer or persona")
        return await self._write("INSERT INTO messages (case_id, role, text, ts) VALUES (?,?,?,?)",
                                 (case_id, role, text, utc_now()))

    async def list_messages(self, case_id: str) -> list[dict]:
        return await self._all("SELECT * FROM messages WHERE case_id=? ORDER BY id", (case_id,))

    async def count_messages(self, case_id: str, role: str) -> int:
        row = await self._one("SELECT COUNT(*) AS n FROM messages WHERE case_id=? AND role=?", (case_id, role))
        return int(row["n"])

    # ---------- intel ----------
    async def add_intel(self, case_id: str, kind: str, value: str, message_id: Optional[int]) -> bool:
        """Stores the value as extracted plus its normalised form (field type = kind) for network matching."""
        from app.networks import normalise
        async with self._lock:
            cur = await self.db.execute(
                "INSERT OR IGNORE INTO intel_items (case_id, kind, value, message_id, first_seen, norm) "
                "VALUES (?,?,?,?,?,?)",
                (case_id, kind, value, message_id, utc_now(), normalise(kind, value)))
            await self.db.commit()
            return cur.rowcount == 1

    async def list_intel(self, case_id: str) -> list[dict]:
        return await self._all("SELECT * FROM intel_items WHERE case_id=? ORDER BY id", (case_id,))

    async def network_rows(self) -> list[dict]:
        """Every (field, normalised value) that appears in 2 or more cases, joined with case facts."""
        return await self._all(
            "SELECT i.case_id, i.kind, i.norm, i.first_seen, c.scam_type, c.created_at FROM intel_items i "
            "JOIN cases c ON c.id = i.case_id WHERE i.norm != '' AND (i.kind, i.norm) IN ("
            "SELECT kind, norm FROM intel_items WHERE norm != '' GROUP BY kind, norm "
            "HAVING COUNT(DISTINCT case_id) >= 2)")

    # ---------- events ----------
    async def add_event(self, event: Event) -> int:
        return await self._write(
            "INSERT INTO events (ts, case_id, channel, type, data) VALUES (?,?,?,?,?)",
            (event.ts, event.case_id, event.channel, event.type, json.dumps(event.data, ensure_ascii=False)))

    async def events_after(self, last_id: int, limit: int = 500) -> list[Event]:
        rows = await self._all("SELECT * FROM events WHERE id>? ORDER BY id LIMIT ?", (last_id, limit))
        return [Event(id=r["id"], ts=r["ts"], case_id=r["case_id"], channel=r["channel"], type=r["type"],
                      data=json.loads(r["data"])) for r in rows]

    async def events_for_case(self, case_id: str, limit: int = 1000) -> list[Event]:
        rows = await self._all("SELECT * FROM events WHERE case_id=? ORDER BY id LIMIT ?", (case_id, limit))
        return [Event(id=r["id"], ts=r["ts"], case_id=r["case_id"], channel=r["channel"], type=r["type"],
                      data=json.loads(r["data"])) for r in rows]

    # ---------- evidence + idempotency ----------
    async def add_evidence(self, case_id: str, kind: str, path: str, sha256: str) -> None:
        await self._write("INSERT INTO evidence (case_id, kind, path, sha256, created_at) VALUES (?,?,?,?,?)",
                          (case_id, kind, path, sha256, utc_now()))

    async def list_evidence(self, case_id: str) -> list[dict]:
        return await self._all("SELECT * FROM evidence WHERE case_id=? ORDER BY id", (case_id,))

    async def mark_seen(self, key: str) -> bool:
        """True the first time a key is seen, False after (Telegram update_id, Twilio callbacks)."""
        async with self._lock:
            cur = await self.db.execute("INSERT OR IGNORE INTO seen_keys (key, ts) VALUES (?,?)", (key, utc_now()))
            await self.db.commit()
            return cur.rowcount == 1
