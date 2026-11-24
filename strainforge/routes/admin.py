"""Site-owner pages: the business dashboard and the calculator builder."""
import json
import re

from fastapi import APIRouter, Form, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import config, db
from ..calc import PROCESSES
from ..formula import EXAMPLE, FormulaError, clean_spec, run
from .common import (
    flash_redirect, is_uuid, jresp, library, load_session, need_login, need_site_admin, page, read_json,
)

router = APIRouter()
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _owner(request: Request):
    s = load_session(request)
    if not s.signed_in:
        return s, need_login(request)
    need_site_admin(s, "open the owner dashboard")
    return s, None


def _boot(data) -> str:
    return json.dumps(jsonable_encoder(data), ensure_ascii=False).replace("</", "<\\/")


# ------------------------------------------------------------------ dashboard

def dashboard(request: Request):
    s, redirect = _owner(request)
    if redirect:
        return redirect
    st = db.owner_stats(config.PRICE_PERSONAL_CENTS, config.team_price_cents, config.SITE_ADMIN_EMAILS)
    k = st["k"]
    growth = None
    if k["users_prev_30"]:
        growth = (k["users_30"] - k["users_prev_30"]) / k["users_prev_30"] * 100
    proc_total = sum(r["n"] for r in st["by_process"]) or 1
    charts = {
        "weeks": [{"label": r["week"].strftime("%d %b"), "signups": r["signups"], "calcs": r["calcs"]} for r in st["weeks"]],
        "days": [{"label": r["day"].strftime("%d %b"), "views": r["views"]} for r in st["days"]],
    }
    return page(request, "dashboard.html", s, st=st, k=k, growth=growth, charts=_boot(charts),
                by_process=[{"name": PROCESSES[r["process"] - 1] if 1 <= r["process"] <= len(PROCESSES) else "?",
                             "n": r["n"], "pct": r["n"] / proc_total * 100} for r in st["by_process"]],
                tools=db.tools(published_only=False), price_personal=config.PRICE_PERSONAL_CENTS / 100,
                price_team=config.PRICE_TEAM_CENTS / 100, team_seats=config.TEAM_INCLUDED_SEATS,
                price_seat=config.PRICE_SEAT_CENTS / 100, billing=config.BILLING_ENABLED)


@router.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request):
    return dashboard(request)


# ------------------------------------------------------------------ calculator builder

@router.get("/admin/tools/new", response_class=HTMLResponse)
def tool_new(request: Request, example: int = 0):
    s, redirect = _owner(request)
    if redirect:
        return redirect
    t = {"id": "", "slug": "upset-head-force" if example else "", "title": "Upset head force" if example else "",
         "summary": "Quick open-upsetting estimate for a round head." if example else "", "published": False,
         "spec": EXAMPLE if example else {"material": False, "inputs": [{"key": "", "label": "", "unit": "", "default": 0}],
                                          "outputs": [{"key": "", "label": "", "unit": "", "formula": "", "decimals": 2}],
                                          "notes": ""}}
    return page(request, "tool_edit.html", s, t=t, boot=_boot({"tool": t, "materials": library()}))


@router.get("/admin/tools/{tid}", response_class=HTMLResponse)
def tool_edit(request: Request, tid: str):
    s, redirect = _owner(request)
    if redirect:
        return redirect
    t = db.tool(tid) if is_uuid(tid) else None
    if not t:
        return flash_redirect("/admin#tools", err="That calculator no longer exists.")
    t = {**t, "id": str(t["id"])}
    return page(request, "tool_edit.html", s, t=t, boot=_boot({"tool": t, "materials": library()}))


@router.post("/api/admin/tools/preview")
async def tool_preview(request: Request):
    s = load_session(request)
    need_site_admin(s, "build calculators")
    body = await read_json(request)
    try:
        spec = clean_spec(body.get("spec") or {})
    except FormulaError as e:
        return jresp({"error": str(e)}, 400)
    mat = next((m for m in library() if m["name"] == body.get("material")), None) or (library() or [None])[0]
    return jresp({"outputs": run(spec, body.get("values") or {}, mat)})


@router.post("/api/admin/tools")
async def tool_save(request: Request):
    s = load_session(request)
    need_site_admin(s, "build calculators")
    body = await read_json(request)
    title = str(body.get("title") or "").strip()[:80]
    slug = str(body.get("slug") or "").strip().lower()[:60] or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
    tid = str(body.get("id") or "")
    if not title:
        return jresp({"error": "Give the calculator a name."}, 400)
    if not SLUG_RE.match(slug):
        return jresp({"error": "The web address can use lowercase letters, digits and single dashes."}, 400)
    from .. import builtin
    if builtin.get(slug):
        return jresp({"error": "That web address is taken by a built-in tool. Pick another."}, 400)
    if tid and not is_uuid(tid):
        return jresp({"error": "Not found"}, 404)
    try:
        spec = clean_spec(body.get("spec") or {})
        new_id = db.save_tool(s.user_id, tid or None, slug, title, str(body.get("summary") or "").strip()[:240],
                              spec, bool(body.get("published")))
    except (FormulaError, ValueError) as e:
        return jresp({"error": str(e)}, 400)
    return jresp({"id": new_id, "slug": slug})


@router.post("/admin/tools/{tid}/publish")
def tool_publish(request: Request, tid: str, published: int = Form(...)):
    s = load_session(request)
    need_site_admin(s, "publish calculators")
    if is_uuid(tid):
        db.set_tool_published(tid, bool(published))
    return flash_redirect("/admin#tools", msg="Calculator is live for everyone." if published else "Calculator hidden from visitors.")


@router.post("/admin/tools/{tid}/delete")
def tool_delete(request: Request, tid: str):
    s = load_session(request)
    need_site_admin(s, "delete calculators")
    if is_uuid(tid):
        db.delete_tool(tid)
    return flash_redirect("/admin#tools", msg="Calculator deleted.")


@router.get("/admin/export/users.csv")
def export_users(request: Request):
    s, redirect = _owner(request)
    if redirect:
        return redirect
    import csv
    import io
    rows = db.q("""select u.email, u.full_name, u.created_at, u.last_seen_at,
                   (select count(*) from calculations c where c.created_by = u.id) as calculations,
                   (select string_agg(w.name, '; ') from memberships m join workspaces w on w.id = m.workspace_id
                     where m.user_id = u.id and w.kind = 'team') as teams
                   from users u order by u.created_at""")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["email", "name", "joined", "last_seen", "calculations", "teams"])
    def cell(v):  # keep spreadsheet apps from reading names as formulas
        v = str(v or "")
        return "'" + v if v[:1] in ("=", "+", "-", "@") else v
    for r in rows:
        w.writerow([cell(r["email"]), cell(r["full_name"]), r["created_at"].isoformat(),
                    r["last_seen_at"].isoformat() if r["last_seen_at"] else "", r["calculations"], cell(r["teams"])])
    from fastapi.responses import Response
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="strainforge-accounts.csv"',
                             "Cache-Control": "no-store"})


@router.get("/admin/tools", response_class=HTMLResponse)
def tools_redirect():
    return RedirectResponse("/admin#tools", 303)
