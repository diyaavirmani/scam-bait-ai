"""Scammer networks: cases that share an identical identifier (exact match on normalised values, no ML).

Two cases are linked when they share at least one (field, normalised value) in intel_items. Links are merged with
union-find, so A-B and B-C form one network. Only groups of 2 or more cases are networks.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Optional
from urllib.parse import urlsplit

log = logging.getLogger("scambait.networks")

# Only identifiers that point at one scammer or one asset. Names, organisations, amounts, IFSC codes (a whole bank
# branch) and reference codes are too generic to link cases on.
LINK_KINDS = ("upi", "phone", "bank_account", "card", "url", "apk", "email", "crypto_wallet", "social_handle")

_DIGITS = re.compile(r"\D+")


def normalise(kind: str, value: str) -> str:
    """Normalised value used for exact matching. Empty string means: do not link on this item."""
    v = (value or "").strip()
    if not v:
        return ""
    if kind == "phone":
        d = _DIGITS.sub("", v)
        return d[-10:] if len(d) >= 10 else d
    if kind in ("bank_account", "card"):
        return _DIGITS.sub("", v)
    if kind in ("url", "apk"):
        raw = v if "://" in v else "http://" + v
        try:
            parts = urlsplit(raw)
        except ValueError:
            return v.lower()
        host = (parts.hostname or "").lower()
        path = parts.path.rstrip("/")
        return host + path
    return v.lower()


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def build_networks(rows: list[dict]) -> list[dict]:
    """rows: {case_id, kind, norm, first_seen, scam_type, created_at}. Returns networks, largest first."""
    by_key: dict[tuple[str, str], dict[str, str]] = {}
    case_info: dict[str, dict] = {}
    for r in rows:
        if r["kind"] not in LINK_KINDS or not r["norm"]:
            continue
        seen = by_key.setdefault((r["kind"], r["norm"]), {})
        prev = seen.get(r["case_id"])
        if prev is None or r["first_seen"] < prev:
            seen[r["case_id"]] = r["first_seen"]
        case_info[r["case_id"]] = {"scam_type": r.get("scam_type") or "unknown", "created_at": r.get("created_at") or ""}
    uf = _UnionFind()
    shared_keys = {k: cases for k, cases in by_key.items() if len(cases) >= 2}
    for cases in shared_keys.values():
        ids = sorted(cases)
        for other in ids[1:]:
            uf.union(ids[0], other)
    groups: dict[str, set[str]] = {}
    for cases in shared_keys.values():
        for cid in cases:
            groups.setdefault(uf.find(cid), set()).add(cid)
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        shared, times = [], []
        for (kind, norm), cases in sorted(shared_keys.items()):
            inside = {c: t for c, t in cases.items() if c in members}
            if len(inside) >= 2:
                shared.append({"field": kind, "value": norm, "case_count": len(inside)})
                times.extend(inside.values())
        ordered = sorted(members, key=lambda c: (case_info[c]["created_at"], c))
        out.append({
            "network_id": "net_" + ordered[0].removeprefix("c_"),
            "case_ids": ordered,
            "shared": shared,
            "first_seen": min(times) if times else None,
            "last_seen": max(times) if times else None,
            "scam_types": sorted({case_info[c]["scam_type"] for c in members} - {"unknown", "", "not_a_scam"}),
        })
    out.sort(key=lambda n: (-len(n["case_ids"]), n["network_id"]))
    return out


async def compute_networks(store) -> list[dict]:
    return build_networks(await store.network_rows())


def network_for_case(networks: list[dict], case_id: str) -> Optional[dict]:
    return next((n for n in networks if case_id in n["case_ids"]), None)


_lock = asyncio.Lock()
_last_sent: dict[str, Any] = {}


async def on_intel_extracted(bus, event) -> None:
    """Recompute after every intel.extracted and emit network.updated for a network that changed. Never raises."""
    store = getattr(bus, "store", None)
    if store is None or not hasattr(store, "network_rows") or not event.case_id:
        return
    from app.models import Event
    try:
        async with _lock:
            net = network_for_case(await compute_networks(store), event.case_id)
            if net is None:
                return
            signature = (tuple(net["case_ids"]), tuple((s["field"], s["value"], s["case_count"]) for s in net["shared"]))
            if _last_sent.get(net["network_id"]) == signature:
                return
            _last_sent[net["network_id"]] = signature
        await bus.emit(Event(case_id=event.case_id, channel=event.channel, type="network.updated",
                             data={"network_id": net["network_id"], "case_ids": net["case_ids"],
                                   "shared": net["shared"]}))
    except Exception:
        log.exception("network recompute failed")
