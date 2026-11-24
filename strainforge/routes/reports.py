"""PDF and Excel reports (a paid feature): for the page you're on, or for several saved results at once."""
from fastapi import APIRouter, Request
from fastapi.responses import Response

from .. import db, report
from .common import can_report, is_uuid, jresp, load_session, read_json

router = APIRouter()

TYPES = {"pdf": "application/pdf", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         "zip": "application/zip"}
NO_PLAN = "Reports come with the Personal and Team plans. Sign in to download one."


def _file(data: bytes, name: str, inline=False):
    ext = name.rsplit(".", 1)[1]
    how = "inline" if inline else "attachment"
    return Response(data, media_type=TYPES[ext],
                    headers={"Content-Disposition": f'{how}; filename="{name}"', "Cache-Control": "no-store"})


def _changed(t):
    if not t:
        return ""
    return f"{t.day} {t:%B %Y}" if hasattr(t, "strftime") else str(t)[:10]


@router.post("/api/report")
async def page_report(request: Request):
    """The report for what's on the page now (saved or not)."""
    s = load_session(request)
    if not can_report(s):
        return jresp({"error": NO_PLAN}, 403)
    body = await read_json(request)
    fmt = body.get("format")
    if fmt not in ("pdf", "xlsx"):
        return jresp({"error": "Choose pdf or xlsx"}, 400)
    U = report.Units(body.get("units"))
    try:
        model = report.model_from_source(body.get("source"), U)
    except (KeyError, ValueError, TypeError, AttributeError, IndexError) as e:
        return jresp({"error": f"Could not build the report: {e}"}, 400)
    report.finish(model, str(body.get("title") or ""), str(body.get("notes") or ""),
                  [("Prepared by", s.name), ("Workspace", s.ws["name"])], report.today_label(body.get("date")))
    if fmt == "pdf":
        return _file(report.build_pdf(model), report.filename(model["title"], "pdf"), inline=bool(body.get("inline")))
    return _file(report.build_xlsx([model]), report.filename(model["title"], "xlsx"))


@router.post("/api/reports/batch")
async def batch_report(request: Request):
    """Reports for several saved results: PDFs in a zip file, or one workbook with a sheet per result."""
    s = load_session(request)
    if not can_report(s):
        return jresp({"error": NO_PLAN}, 403)
    body = await read_json(request)
    fmt = body.get("format")
    ids = body.get("ids")
    if fmt not in ("pdf", "xlsx") or not isinstance(ids, list):
        return jresp({"error": "Choose some saved results and a format"}, 400)
    ids = list(dict.fromkeys(str(i) for i in ids if is_uuid(str(i))))
    if not ids:
        return jresp({"error": "Choose at least one saved result"}, 400)
    if len(ids) > report.MAX_BATCH:
        return jresp({"error": f"Choose at most {report.MAX_BATCH} at a time"}, 400)
    rows = db.get_calcs(s.user_id, s.ws["id"], ids)
    if not rows:
        return jresp({"error": "Those results don't exist or aren't in this workspace"}, 404)
    U = report.Units(body.get("units"))
    date = report.today_label(body.get("date"))
    models = []
    for row in rows:
        try:
            m = report.model_from_saved(row, U)
        except (KeyError, ValueError, TypeError, AttributeError, IndexError):
            continue
        report.finish(m, row["title"], row.get("notes") or "",
                      [("Saved by", row.get("created_by_name") or ""), ("Last change", _changed(row.get("updated_at"))),
                       ("Workspace", s.ws["name"])], date)
        m["saved_by"] = row.get("created_by_name") or ""
        m["changed"] = _changed(row.get("updated_at"))
        models.append(m)
    if not models:
        return jresp({"error": "Could not build those reports"}, 400)
    if fmt == "xlsx":
        name = report.filename(models[0]["title"] if len(models) == 1 else f"Strainforge {len(models)} reports", "xlsx")
        return _file(report.build_xlsx(models), name)
    files = [(report.filename(m["title"], "pdf"), report.build_pdf(m)) for m in models]
    if len(files) == 1:
        return _file(files[0][1], files[0][0])
    return _file(report.build_zip(files), report.filename(f"Strainforge {len(files)} reports", "zip"))
