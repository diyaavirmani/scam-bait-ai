"""Evidence pack export: GET /api/v1/cases/{id}/export.csv and /export.pdf. Track C, commit 19.

The CSV has one row per intel item plus the NCRP / 1930 fields. The PDF holds the case facts, the NCRP
field table, the intel table, the summary and report, the verdict history, the full transcript, the
generated time (IST) and the SHA-256 of the CSV and of the transcript. Every file is written under
out/exports/<case_id>/ (EXPORT_DIR overrides out/exports) and recorded with store.add_evidence.
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.web.api import case_events, intel_with_source, load_case
from app.web.auth import require_api

router = APIRouter(dependencies=[Depends(require_api)])

IST = timezone(timedelta(hours=5, minutes=30))
NCRP_BANNED = set("#$@^*`'~|!") | {"‘", "’"}
MIN_DETAILS = 200
SUSPECT_FIELDS = [  # (CSV column, label, intel kinds)
    ("suspect_mobile", "Suspect mobile", ("phone",)),
    ("suspect_email", "Suspect email", ("email",)),
    ("suspect_bank_account", "Suspect bank account", ("bank_account",)),
    ("suspect_ifsc", "Suspect IFSC", ("ifsc",)),
    ("suspect_urls", "Suspect URLs", ("url", "apk")),
    ("suspect_upi", "Suspect UPI IDs", ("upi",)),
    ("suspect_social_handles", "Suspect social handles", ("social_handle",)),
]
CSV_COLUMNS = (["case_id", "channel", "generated_at_ist", "incident_datetime_ist", "incident_details"]
               + [c for c, _, _ in SUSPECT_FIELDS]
               + ["intel_kind", "intel_value", "intel_source", "intel_first_seen_ist", "intel_source_message"])
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/DejaVuSans.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]


def export_root() -> Path:
    return Path(os.getenv("EXPORT_DIR", "out/exports"))


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def to_ist(ts: Optional[str]) -> str:
    if not ts:
        return ""
    try:
        d = datetime.fromisoformat(str(ts))
    except ValueError:
        return str(ts)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def strip_banned(text: str) -> str:
    return re.sub(r"\s+", " ", "".join(ch for ch in (text or "") if ch not in NCRP_BANNED)).strip()


def incident_details(case: dict, intel: list[dict], scammer_turns: int) -> str:
    """Case summary for the NCRP 'incident details' field: banned symbols stripped, at least 200 characters."""
    text = strip_banned(case.get("summary") or "")
    kinds = sorted({i["kind"] for i in intel})
    extra = [
        f"The suspect contacted a SCAM-BAIT decoy over {case.get('channel')} (case {case.get('id')}).",
        f"Scam type: {case.get('scam_type') or 'unknown'}. Verdict: {case.get('verdict') or 'unknown'}.",
        f"Scammer messages recorded: {scammer_turns}.",
        f"Suspect identifiers collected: {len(intel)}" + (f" ({', '.join(kinds)})." if kinds else "."),
        "No money was paid by the decoy. The attached CSV and PDF evidence pack hold the full transcript and identifiers.",
    ]
    for sentence in extra:
        if len(text) >= MIN_DETAILS:
            break
        text = (text + " " + strip_banned(sentence)).strip()
    while len(text) < MIN_DETAILS:
        text += " Reported from a honeypot conversation."
    return text


def incident_time(messages: list[dict], events: list, case: dict) -> str:
    """Timestamp of the first scam turn: the last scammer message at or before the first scam verdict."""
    scammer = [m for m in messages if m.get("role") == "scammer"]
    first_scam = next((e.ts for e in events if e.type == "scam.detected" and (e.data or {}).get("verdict") == "scam"), None)
    if first_scam and scammer:
        before = [m for m in scammer if str(m.get("ts")) <= str(first_scam)]
        if before:
            return before[-1]["ts"]
    if scammer:
        return scammer[0]["ts"]
    return case.get("created_at") or ""


def transcript_text(case: dict, messages: list[dict], events: list) -> str:
    lines = [f"Transcript of case {case['id']} ({case.get('channel')})"]
    if messages:
        for m in messages:
            who = "Scammer" if m.get("role") == "scammer" else "Persona"
            lines.append(f"[{to_ist(m.get('ts'))}] {who}: {m.get('text', '')}")
    else:
        for e in events:
            if e.type == "transcript.final":
                who = "Caller" if e.data.get("speaker") == "caller" else "Persona"
                lines.append(f"[{to_ist(e.ts)}] {who}: {e.data.get('text', '')}")
    if len(lines) == 1:
        lines.append("(no messages recorded)")
    return "\n".join(lines) + "\n"


def _csv_cell(v) -> str:
    s = "" if v is None else str(v)
    if s[:1] in ("=", "@", "\t", "\r") or (s[:1] in ("+", "-") and not re.fullmatch(r"[+-][0-9 ]+", s)):
        return "'" + s  # spreadsheet formula injection guard
    return s


async def build_pack(case_id: str) -> dict:
    from app.runtime import get_runtime
    store = get_runtime().store
    case = await load_case(case_id)
    events = await case_events(case_id)
    messages = await store.list_messages(case_id)
    intel = intel_with_source(await store.list_intel(case_id), events)
    msg_by_id = {m["id"]: m for m in messages}
    for i in intel:
        src = msg_by_id.get(i.get("message_id"))
        i["source_message"] = src["text"] if src else ""
    scammer_turns = sum(1 for m in messages if m.get("role") == "scammer")
    report = None
    for e in events:
        if e.type == "case.summary" and (e.data or {}).get("report"):
            report = e.data["report"]
    ncrp = {
        "incident_datetime_ist": to_ist(incident_time(messages, events, case)),
        "incident_details": incident_details(case, intel, scammer_turns),
    }
    for col, _, kinds in SUSPECT_FIELDS:
        ncrp[col] = "; ".join(i["value"] for i in intel if i["kind"] in kinds)
    verdicts = [e for e in events if e.type == "scam.detected"]
    return {"case": case, "events": events, "messages": messages, "intel": intel, "report": report, "ncrp": ncrp,
            "verdicts": verdicts, "generated_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
            "stamp": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"),
            "transcript": transcript_text(case, messages, events)}


def render_csv(pack: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(CSV_COLUMNS)
    c, n = pack["case"], pack["ncrp"]
    base = [c["id"], c.get("channel"), pack["generated_at"], n["incident_datetime_ist"], n["incident_details"]]
    base += [n[col] for col, _, _ in SUSPECT_FIELDS]
    rows = pack["intel"] or [None]
    for i in rows:
        tail = ["", "", "", "", ""] if i is None else [i["kind"], i["value"], i.get("source") or "",
                                                         to_ist(i.get("first_seen")), i.get("source_message", "")]
        w.writerow([_csv_cell(v) for v in base + tail])
    return buf.getvalue().encode("utf-8")


def _find_font() -> Optional[str]:
    for p in [os.getenv("PDF_FONT_PATH", "")] + FONT_CANDIDATES:
        if p and os.path.isfile(p):
            return p
    return None


def _latin1(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text)
    return "".join(ch if ord(ch) < 256 else ("" if unicodedata.combining(ch) else "?") for ch in norm)


def render_pdf(pack: dict, csv_sha: str, transcript_sha: str) -> bytes:
    from fpdf import FPDF
    from fpdf.fonts import FontFace

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=15)
    pdf.set_margins(15, 15, 15)
    font = _find_font()
    if font:
        pdf.add_font("U", "", font)
        family, clean = "U", (lambda s: s)
    else:
        family, clean = "helvetica", _latin1
    pdf.add_page()

    def heading(text: str) -> None:
        pdf.ln(3)
        pdf.set_font(family, size=13)
        pdf.multi_cell(0, 7, clean(text), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(family, size=9)

    def para(text: str) -> None:
        pdf.multi_cell(0, 5, clean(text or ""), new_x="LMARGIN", new_y="NEXT")

    def table(rows: list[list[str]], widths: tuple) -> None:
        head = FontFace(emphasis="", fill_color=(230, 230, 230))  # no bold face is loaded for the Unicode font
        with pdf.table(col_widths=widths, text_align="LEFT", line_height=5, headings_style=head) as t:
            for r in rows:
                row = t.row()
                for cell in r:
                    row.cell(clean("" if cell is None else str(cell)))

    c, n = pack["case"], pack["ncrp"]
    pdf.set_font(family, size=16)
    pdf.multi_cell(0, 9, clean(f"SCAM-BAIT evidence pack: case {c['id']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(family, size=9)
    para(f"Generated {pack['generated_at']}. For filing on cybercrime.gov.in (NCRP) or with 1930.")
    if not font:
        para("Note: no Unicode font was found, so non Latin-1 characters are transliterated or shown as '?'. "
             "The CSV and the transcript (see the SHA-256 values below) hold the exact text.")
    else:
        para("The CSV and the transcript (see the SHA-256 values below) hold the exact text of every item.")

    heading("Case facts")
    table([["Field", "Value"], ["Case id", c["id"]], ["Channel", c.get("channel")], ["Status", c.get("status")],
           ["Scam type", c.get("scam_type")], ["Verdict", c.get("verdict")], ["Opened", to_ist(c.get("created_at"))],
           ["Last update", to_ist(c.get("updated_at"))]], (35, 145))

    heading("NCRP / 1930 fields")
    rows = [["Field", "Value"], ["Incident date and time", n["incident_datetime_ist"]],
            ["Incident details", n["incident_details"]]]
    rows += [[label, n[col] or "none collected"] for col, label, _ in SUSPECT_FIELDS]
    table(rows, (45, 135))

    heading("Extracted intel")
    if pack["intel"]:
        table([["Kind", "Value", "Source", "First seen", "Source message"]] +
              [[i["kind"], i["value"], i.get("source") or "", to_ist(i.get("first_seen")), (i.get("source_message") or "")[:300]]
               for i in pack["intel"]], (24, 45, 20, 33, 58))
    else:
        para("No intel items were extracted.")

    heading("Summary")
    para(c.get("summary") or "No summary yet.")
    if pack["report"] is not None:
        heading("Case report")
        rep = pack["report"]
        para(rep if isinstance(rep, str) else json.dumps(rep, ensure_ascii=False, indent=2))

    heading("Verdict history")
    if pack["verdicts"]:
        table([["Time", "Stage", "qwen (Cerebras)", "Decisions", "Verdict", "Decided by"]] +
              [[to_ist(e.ts), e.data.get("stage", "") + (" re-check" if e.data.get("recheck") else ""),
                _p(e.data.get("p_cerebras")), "unavailable" if e.data.get("decisions_available") is False else _p(e.data.get("p_decisions")),
                e.data.get("verdict", ""), e.data.get("decided_by", "")] for e in pack["verdicts"]],
              (40, 25, 28, 27, 25, 35))
    else:
        para("No detection results recorded.")

    heading("Full transcript")
    para(pack["transcript"])

    heading("Integrity")
    para(f"SHA-256 of the CSV export: {csv_sha}")
    para(f"SHA-256 of the transcript text (UTF-8): {transcript_sha}")
    para(f"Generated {pack['generated_at']}. The SHA-256 of this PDF is recorded in the case evidence log.")
    return bytes(pdf.output())


def _p(v) -> str:
    try:
        return f"{round(float(v) * 100)}%"
    except (TypeError, ValueError):
        return "n/a"


async def _write(case_id: str, kind: str, name: str, data: bytes) -> dict:
    from app.runtime import get_runtime
    folder = export_root() / case_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(data)
    digest = sha256_bytes(data)
    await get_runtime().store.add_evidence(case_id, kind, str(path), digest)
    return {"kind": kind, "path": str(path), "sha256": digest}


async def export_case(case_id: str, with_pdf: bool) -> dict:
    pack = await build_pack(case_id)
    base = f"{case_id}_{pack['stamp']}"
    tr = await _write(case_id, "transcript", base + "_transcript.txt", pack["transcript"].encode("utf-8"))
    csv_bytes = render_csv(pack)
    out = {"transcript": tr, "csv": await _write(case_id, "csv", base + ".csv", csv_bytes), "csv_bytes": csv_bytes}
    if with_pdf:
        pdf_bytes = await asyncio.to_thread(render_pdf, pack, out["csv"]["sha256"], tr["sha256"])  # off the event loop
        out["pdf"] = await _write(case_id, "pdf", base + ".pdf", pdf_bytes)
        out["pdf_bytes"] = pdf_bytes
    out["name"] = base
    return out


def _download(data: bytes, media: str, filename: str, digest: str, extra: dict) -> Response:
    headers = {"Content-Disposition": f'attachment; filename="{filename}"', "X-SHA256": digest,
               "Cache-Control": "no-store"}
    headers.update(extra)
    return Response(content=data, media_type=media, headers=headers)


@router.get("/api/v1/cases/{case_id}/export.csv")
async def export_csv(case_id: str) -> Response:
    out = await export_case(case_id, with_pdf=False)
    return _download(out["csv_bytes"], "text/csv; charset=utf-8", out["name"] + ".csv", out["csv"]["sha256"],
                     {"X-Transcript-SHA256": out["transcript"]["sha256"]})


@router.get("/api/v1/cases/{case_id}/export.pdf")
async def export_pdf(case_id: str) -> Response:
    out = await export_case(case_id, with_pdf=True)
    return _download(out["pdf_bytes"], "application/pdf", out["name"] + ".pdf", out["pdf"]["sha256"],
                     {"X-CSV-SHA256": out["csv"]["sha256"], "X-Transcript-SHA256": out["transcript"]["sha256"]})
