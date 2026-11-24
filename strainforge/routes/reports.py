"""Excel reports of a calculation (a paid feature; the PDF report is printed in the browser)."""
import io
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import Response

from .common import can_report, jresp, load_session, read_json

router = APIRouter()

NUM = re.compile(r"^[−-]?\d{1,3}(,\d{3})*(\.\d+)?$|^[−-]?\d+(\.\d+)?$")
MAX_SECTIONS, MAX_ROWS, MAX_COLS, MAX_CELL, MAX_TOTAL_ROWS = 20, 300, 8, 300, 1200


def _cell(v):
    """Numbers shown on the page arrive as text ("1,234.5"); store them as numbers so Excel can use them."""
    if v is None:
        return None
    v = str(v)[:MAX_CELL]
    t = v.strip()
    if NUM.match(t):
        try:
            return float(t.replace(",", "").replace("−", "-"))
        except ValueError:
            pass
    return v


def _as_text_if_formula(c):
    """Never store page text as a formula (e.g. "= t" or "=HYPERLINK(...)"): keep it as plain text."""
    if isinstance(c.value, str) and c.value[:1] in ("=", "+", "-", "@") and c.data_type == "f":
        c.data_type = "s"


def build_xlsx(report: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
    bold = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="E7F1FB")
    title = str(report.get("title") or "Strainforge report")[:200]
    ws.append([title])
    _as_text_if_formula(ws["A1"])
    ws["A1"].font = Font(bold=True, size=14)
    for k, v in [m for m in (report.get("meta") or []) if isinstance(m, list) and len(m) == 2][:20]:
        ws.append([str(k)[:80], str(v)[:MAX_CELL]])
        ws.cell(ws.max_row, 1).font = bold
        _as_text_if_formula(ws.cell(ws.max_row, 1))
        _as_text_if_formula(ws.cell(ws.max_row, 2))
    widths = [36, 18, 14, 14, 14, 14]
    total = 0
    for sec in (report.get("sections") or [])[:MAX_SECTIONS]:
        if not isinstance(sec, dict) or total >= MAX_TOTAL_ROWS:
            continue
        ws.append([])
        ws.append([str(sec.get("title") or "")[:120]])
        _as_text_if_formula(ws.cell(ws.max_row, 1))
        ws.cell(ws.max_row, 1).font = Font(bold=True, size=12)
        cols = [str(c)[:80] for c in (sec.get("columns") or [])[:MAX_COLS]]
        if cols:
            ws.append(cols)
            for i in range(1, len(cols) + 1):
                c = ws.cell(ws.max_row, i)
                _as_text_if_formula(c)
                c.font, c.fill = bold, head_fill
        for row in (sec.get("rows") or [])[:MAX_ROWS]:
            total += 1
            if total > MAX_TOTAL_ROWS:
                break
            if isinstance(row, dict) and row.get("group"):
                ws.append([str(row["group"])[:120]])
                _as_text_if_formula(ws.cell(ws.max_row, 1))
                ws.cell(ws.max_row, 1).font = bold
                continue
            if not isinstance(row, list):
                continue
            ws.append([_cell(v) for v in row[:MAX_COLS]])
            for i in range(1, min(len(row), MAX_COLS) + 1):
                _as_text_if_formula(ws.cell(ws.max_row, i))
                c = ws.cell(ws.max_row, i)
                if isinstance(c.value, float):
                    c.alignment = Alignment(horizontal="right")
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + i)].width = w
    ws.append([])
    ws.append(["Results are estimates for tool design; confirm critical steps with simulation or trials."])
    ws.cell(ws.max_row, 1).font = Font(italic=True, color="666666")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _filename(title: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "", title).strip().replace(" ", "-")[:60] or "strainforge-report"
    return f"{stem}-{datetime.now(timezone.utc):%Y-%m-%d}.xlsx"


@router.post("/api/report.xlsx")
async def report_xlsx(request: Request):
    s = load_session(request)
    if not can_report(s):
        return jresp({"error": "Reports come with the Personal and Team plans. Sign in to download one."}, 403)
    body = await read_json(request)
    if not isinstance(body.get("sections"), list):
        return jresp({"error": "Nothing to put in the report"}, 400)
    try:
        data = build_xlsx(body)
    except (TypeError, ValueError, AttributeError):
        return jresp({"error": "Could not read the report contents"}, 400)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{_filename(str(body.get("title") or ""))}"',
                             "Cache-Control": "no-store"})
