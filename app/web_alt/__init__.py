"""Side-by-side dashboard (alternate build) under /alt: /alt/chats, /alt/calls, /alt/cases, /alt/export.

Built in parallel with app/web (Track C) so the integrator can compare both against docs/DEMO_SCRIPT.md.
Reuses the shared contracts only: the SSE stream at GET /api/v1/events/stream, app.models.Event types and the
login cookie from app/web/auth.py (imported read-only). It renders only real data from the store and the stream;
there is no mock data anywhere (A-01). All text is inserted with textContent in the browser (no HTML injection).
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from app.web.auth import is_authed, login_redirect, require_api

router = APIRouter(prefix="/alt")

STATIC = Path(__file__).parent / "static"
CASE_ID_RE = re.compile(r"^c_[0-9a-f]{12}$")
IST = timezone(timedelta(hours=5, minutes=30))
NCRP_BANNED = "#$@^*`'’~|!"
NCRP_MIN_DETAILS = 200
MAX_TURNS = 20
PAGES = {"chats", "calls", "cases", "export"}
FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
SUSPECT_FIELDS = {  # NCRP suspect field -> intel kinds
    "suspect_mobile_numbers": ("phone",),
    "suspect_emails": ("email",),
    "suspect_bank_accounts": ("bank_account",),
    "suspect_ifsc": ("ifsc",),
    "suspect_upi_ids": ("upi",),
    "suspect_urls": ("url", "apk"),
    "suspect_social_handles": ("social_handle",),
    "suspect_names": ("name",),
}


def _rt():
    from app.runtime import get_runtime
    return get_runtime()


def to_ist(ts: Optional[str]) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromisoformat(ts).astimezone(IST).strftime("%d %b %Y, %H:%M:%S IST")
    except ValueError:
        return ts


def _check_case_id(case_id: str) -> None:
    if not CASE_ID_RE.match(case_id):
        raise HTTPException(status_code=400, detail="bad case id")


# ---------------------------------------------------------------- pages
def _page(request: Request, name: str):
    if not is_authed(request):
        return login_redirect(request)
    return HTMLResponse((STATIC / f"{name}.html").read_text(encoding="utf-8"))


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
async def alt_root(request: Request):
    return _page(request, "chats")


@router.get("/{page}", include_in_schema=False)
async def alt_page(page: str, request: Request):
    if page not in PAGES:
        raise HTTPException(status_code=404)
    return _page(request, page)


@router.get("/static/{name}", include_in_schema=False)
async def alt_static(name: str, request: Request):
    if name not in {"alt.js", "alt.css"}:
        raise HTTPException(status_code=404)
    media = "text/javascript" if name.endswith(".js") else "text/css"
    return Response((STATIC / name).read_text(encoding="utf-8"), media_type=media,
                    headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------- JSON snapshot API
async def _case_view(case: dict) -> dict:
    store = _rt().store
    scammer = await store.count_messages(case["id"], "scammer")
    intel = await store.list_intel(case["id"])
    return {**case, "turn": scammer, "max_turns": MAX_TURNS, "intel_count": len(intel),
            "created_ist": to_ist(case["created_at"]), "updated_ist": to_ist(case["updated_at"])}


@router.get("/api/cases", dependencies=[Depends(require_api)])
async def api_cases(channel: Optional[str] = None, limit: int = 100):
    rows = await _rt().store.list_cases(min(max(limit, 1), 500))
    if channel == "chat":
        rows = [r for r in rows if r["channel"] in ("telegram", "api")]
    elif channel:
        rows = [r for r in rows if r["channel"] == channel]
    return {"cases": [await _case_view(r) for r in rows]}


@router.get("/api/cases/{case_id}", dependencies=[Depends(require_api)])
async def api_case(case_id: str):
    _check_case_id(case_id)
    store = _rt().store
    case = await store.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    messages = await store.list_messages(case_id)
    by_id = {m["id"]: m for m in messages}
    intel = [{**i, "first_seen_ist": to_ist(i["first_seen"]),
              "source_text": (by_id.get(i["message_id"]) or {}).get("text", "")} for i in await store.list_intel(case_id)]
    events = await store.events_for_case(case_id)
    evidence = await store.list_evidence(case_id)
    last_event_id = max((e.id or 0 for e in events), default=0)
    return {
        "case": await _case_view(case),
        "messages": [{**m, "ts_ist": to_ist(m["ts"])} for m in messages],
        "intel": intel,
        "events": [e.model_dump() for e in events],
        "evidence": [{**e, "created_ist": to_ist(e["created_at"])} for e in evidence],
        "last_event_id": last_event_id,
    }


@router.get("/api/stream-cursor", dependencies=[Depends(require_api)])
async def api_cursor():
    """Highest stored event id, so a page can open the SSE stream with ?last_id= and miss nothing."""
    async with _rt().store.db.execute("SELECT COALESCE(MAX(id), 0) FROM events") as cur:
        return {"last_id": (await cur.fetchone())[0]}


# ---------------------------------------------------------------- export (CSV + PDF, SHA-256, NCRP)
def ncrp_clean(text: str) -> str:
    out = "".join(ch for ch in text if ch not in NCRP_BANNED)
    return re.sub(r"\s+", " ", out).strip()


def _latest_report(events) -> Optional[dict]:
    for e in reversed(events):
        if e.type == "case.summary" and isinstance(e.data.get("report"), dict):
            return e.data["report"]
    return None


def _incident_ts(case: dict, events, messages: list[dict]) -> str:
    for e in events:
        if e.type == "scam.detected" and e.data.get("verdict") == "scam":
            return e.ts
    first = next((m for m in messages if m["role"] == "scammer"), None)
    return first["ts"] if first else case["created_at"]


def build_ncrp(case: dict, messages: list[dict], intel: list[dict], events) -> dict:
    report = _latest_report(events) or {}
    summary = report.get("summary") or case.get("summary") or ""
    scam_type = (report.get("scam_type") or case.get("scam_type") or "unknown").replace("_", " ")
    details = (f"Scam type: {scam_type}. {summary} Channel: {case['channel']}. "
               f"Scammer messages captured: {sum(1 for m in messages if m['role'] == 'scammer')}. "
               f"Identifiers collected: {len(intel)}. Captured by a decoy conversation; no money was paid.")
    details = ncrp_clean(details)
    if len(details) < NCRP_MIN_DETAILS:
        details = ncrp_clean(details + " The full transcript, the identifier list and SHA-256 hashes of each file are "
                             "attached in this evidence pack for verification.")
    fields = {
        "case_id": case["id"],
        "channel": case["channel"],
        "incident_datetime_ist": to_ist(_incident_ts(case, events, messages)),
        "incident_details": details,
        "scam_type": scam_type,
        "money_lost": "No (decoy session; report via Chakshu or 1930/NCRP as intelligence)",
    }
    for field, kinds in SUSPECT_FIELDS.items():
        fields[field] = "; ".join(i["value"] for i in intel if i["kind"] in kinds)
    return fields


def transcript_text(messages: list[dict]) -> str:
    return "\n".join(f"[{to_ist(m['ts'])}] {m['role']}: {m['text']}" for m in messages) + "\n"


def build_csv(fields: dict, intel: list[dict], messages: list[dict]) -> bytes:
    by_id = {m["id"]: m for m in messages}
    buf = io.StringIO()
    w = csv.writer(buf)
    head = ["intel_kind", "intel_value", "first_seen_ist", "source_message_id", "source_message_text", *fields.keys()]
    w.writerow(head)
    rows = intel or [{"kind": "", "value": "", "first_seen": "", "message_id": None}]
    for i in rows:
        src = by_id.get(i.get("message_id")) or {}
        w.writerow([i["kind"], i["value"], to_ist(i.get("first_seen")), i.get("message_id") or "", src.get("text", ""),
                    *fields.values()])
    return buf.getvalue().encode("utf-8")


def _font_path() -> Optional[str]:
    return next((p for p in FONT_CANDIDATES if Path(p).exists()), None)


def build_pdf(fields: dict, intel: list[dict], report: Optional[dict], transcript: str, hashes: dict) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    font = _font_path()
    if font:
        pdf.add_font("U", "", font)
        family = "U"

        def t(s: str) -> str:
            return s
    else:
        family = "Helvetica"

        def t(s: str) -> str:
            return s.encode("latin-1", "replace").decode("latin-1")
    width = pdf.w - pdf.l_margin - pdf.r_margin

    def heading(text: str) -> None:
        pdf.set_font(family, size=13)
        pdf.ln(2)
        pdf.multi_cell(width, 7, t(text), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(family, size=9)

    def line(text: str) -> None:
        pdf.multi_cell(width, 5, t(text), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font(family, size=16)
    pdf.multi_cell(width, 9, t("SCAM-BAIT evidence pack"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(family, size=9)
    line(f"Generated: {datetime.now(IST).strftime('%d %b %Y, %H:%M:%S IST')}")
    if not font:
        line("Note: this PDF could not embed a Unicode font; non-Latin characters are replaced. "
             "The CSV and the transcript hash hold the exact text.")
    heading("NCRP / 1930 fields")
    for k, v in fields.items():
        line(f"{k.replace('_', ' ')}: {v or '-'}")
    heading("Identifiers")
    for i in intel:
        line(f"{i['kind']}: {i['value']} (first seen {to_ist(i['first_seen'])})")
    if not intel:
        line("None collected.")
    heading("Case report")
    if report:
        for k in ("summary", "modus_operandi", "risk", "recommended_action"):
            if report.get(k):
                line(f"{k.replace('_', ' ')}: {report[k]}")
        for p in report.get("key_points") or []:
            line(f"- {p}")
    else:
        line("No case report yet.")
    heading("SHA-256")
    for k, v in hashes.items():
        line(f"{k}: {v}")
    heading("Transcript")
    for row in transcript.splitlines():
        line(row)
    return bytes(pdf.output())


async def _export(case_id: str) -> dict:
    _check_case_id(case_id)
    store = _rt().store
    case = await store.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    messages = await store.list_messages(case_id)
    intel = await store.list_intel(case_id)
    events = await store.events_for_case(case_id)
    fields = build_ncrp(case, messages, intel, events)
    transcript = transcript_text(messages)
    csv_bytes = build_csv(fields, intel, messages)
    hashes = {"transcript_sha256": hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
              "csv_sha256": hashlib.sha256(csv_bytes).hexdigest()}
    pdf_bytes = build_pdf(fields, intel, _latest_report(events), transcript, hashes)
    hashes["pdf_sha256"] = hashlib.sha256(pdf_bytes).hexdigest()
    out = Path("out") / "exports_alt" / case_id
    out.mkdir(parents=True, exist_ok=True)
    files = {"transcript": (out / "transcript.txt", transcript.encode("utf-8")),
             "csv": (out / "evidence.csv", csv_bytes), "pdf": (out / "evidence.pdf", pdf_bytes)}
    for kind, (path, body) in files.items():
        path.write_bytes(body)
        await store.add_evidence(case_id, kind, str(path), hashes[f"{kind}_sha256"])
    return {"paths": {k: str(p) for k, (p, _) in files.items()}, "hashes": hashes, "ncrp": fields}


@router.post("/api/cases/{case_id}/export", dependencies=[Depends(require_api)])
async def api_export(case_id: str):
    return JSONResponse(await _export(case_id))


@router.get("/api/cases/{case_id}/export.csv", dependencies=[Depends(require_api)])
async def api_export_csv(case_id: str):
    res = await _export(case_id)
    return FileResponse(res["paths"]["csv"], media_type="text/csv", filename=f"{case_id}.csv",
                        headers={"X-SHA256": res["hashes"]["csv_sha256"]})


@router.get("/api/cases/{case_id}/export.pdf", dependencies=[Depends(require_api)])
async def api_export_pdf(case_id: str):
    res = await _export(case_id)
    return FileResponse(res["paths"]["pdf"], media_type="application/pdf", filename=f"{case_id}.pdf",
                        headers={"X-SHA256": res["hashes"]["pdf_sha256"]})
