"""Strainforge web app (FastAPI).

Public: the calculator and /api/calc.  Signed in: saved history, team
workspaces with shared calculations, admin role, custom materials.
"""
import json
import math
import re
import uuid
from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import FastAPI, Form, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from . import config, db
from .calc import DEFAULT_MATERIALS, PRESETS, PROCESS_SHAPES, PROCESS_SLUG, PROCESSES, SHAPE_NAMES, Calculator
from .drawings import SVG_CSS, SVG_DEFS, all_drawings

HERE = Path(__file__).parent
app = FastAPI(title="Strainforge", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")

PROC_DRAW, SHAPE_DRAW = all_drawings()
PROC_NOTE = {1: "Shearing wire to length", 2: "Upsetting a head in a closed die", 3: "Upsetting with underfill",
             4: "Upsetting to a preform", 5: "Flattening a preform to the head", 6: "Open die reduction of the shank",
             7: "Forward extrusion in a closed die", 8: "Cup forming with a punch", 9: "Punching out the web",
             10: "Trimming a hexagon, square or round head"}


def library() -> list[dict]:
    """The standard library (edited by site owners). Falls back to the built-in list without a database."""
    if not config.DATABASE_URL:
        return list(DEFAULT_MATERIALS)
    return list(db.library()) or list(DEFAULT_MATERIALS)


def library_names() -> set[str]:
    return {m["name"] for m in library()}
SID, WS = "sf_sid", "sf_ws"
MONTH = 60 * 60 * 24 * 30


def fmt_num(v, d=None):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    if not isinstance(v, (int, float)):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return str(v)
    if d is None:
        a = abs(v)
        d = 0 if v == 0 else 1 if a >= 1000 else 2 if a >= 100 else 3 if a >= 1 else 4
    return f"{v:,.{d}f}"


def fmt_time(t):
    if not t:
        return ""
    iso = t.isoformat() if hasattr(t, "isoformat") else str(t)
    text = t.strftime("%Y-%m-%d %H:%M UTC") if hasattr(t, "strftime") else iso[:16].replace("T", " ")
    return Markup(f'<time datetime="{escape(iso)}">{escape(text)}</time>')


templates.env.filters["num"] = fmt_num
templates.env.filters["when"] = fmt_time
templates.env.globals.update(PROCESSES=PROCESSES, SHAPE_NAMES=SHAPE_NAMES, config=config)


def is_uuid(v) -> bool:
    try:
        uuid.UUID(str(v))
        return True
    except ValueError:
        return False


# ------------------------------------------------------------------ session

class Session:
    def __init__(self, user=None, token=None):
        self.user = user
        self.token = token
        self.workspaces: list[dict] = []
        self.ws: dict | None = None

    @property
    def signed_in(self):
        return bool(self.user)

    @property
    def user_id(self):
        return str(self.user["id"]) if self.user else None

    @property
    def email(self):
        return self.user["email"] if self.user else ""

    @property
    def name(self):
        return (self.user["full_name"] or self.email.split("@")[0]) if self.user else ""

    @property
    def is_site_admin(self):
        return bool(self.user) and self.email.lower() in config.SITE_ADMIN_EMAILS

    @property
    def is_admin(self):
        return bool(self.ws and self.ws["role"] == "admin")


def _cookie(resp: Response, key, value, max_age=MONTH):
    resp.set_cookie(key, value, max_age=max_age, httponly=True, secure=config.COOKIE_SECURE, samesite="lax", path="/")


def sign_in_response(url: str, uid, ws=None) -> RedirectResponse:
    resp = RedirectResponse(url, 303)
    _cookie(resp, SID, db.new_session(uid))
    if ws:
        _cookie(resp, WS, str(ws))
    else:
        resp.delete_cookie(WS, path="/")
    return resp


def load_session(request: Request) -> Session:
    if hasattr(request.state, "session"):
        return request.state.session
    token = request.cookies.get(SID)
    if token:
        db.ensure_schema()
    user = db.session_user(token) if token else None
    s = Session(user, token if user else None)
    if user:
        s.workspaces = [{**w, "id": str(w["id"]), "owner_id": str(w["owner_id"])} for w in db.workspaces_for(user["id"])]
        want = request.cookies.get(WS)
        s.ws = next((w for w in s.workspaces if w["id"] == want), s.workspaces[0] if s.workspaces else None)
    elif token:
        request.state.clear_sid = True
    request.state.session = s
    return s


@app.middleware("http")
async def headers_and_csrf(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin") or request.headers.get("referer")
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
        if origin and urlparse(origin).netloc != host:
            return JSONResponse({"error": "Cross-site request blocked"}, status_code=403)
    resp = await call_next(request)
    if getattr(request.state, "clear_sid", False):
        resp.delete_cookie(SID, path="/")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    return resp


@app.exception_handler(db.Denied)
async def denied(request: Request, exc: db.Denied):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": str(exc)}, status_code=403)
    back = request.headers.get("referer") or "/history"
    return flash_redirect(urlparse(back).path or "/history", err=str(exc))


def page(request: Request, name: str, s: Session, status_code=200, **ctx):
    ctx.setdefault("msg", request.query_params.get("msg", ""))
    ctx.setdefault("err", request.query_params.get("err", ""))
    return templates.TemplateResponse(request, name, {"s": s, "path": request.url.path, **ctx}, status_code=status_code)


def safe_next(nxt: str | None, default="/history") -> str:
    if nxt and nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt:
        return nxt
    return default


def need_login(request: Request) -> RedirectResponse:
    here = request.url.path + ("?" + request.url.query if request.url.query else "")
    return RedirectResponse(f"/login?next={quote(here)}", 303)


def site_url(request: Request) -> str:
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return f"{proto}://{host}"


def flash_redirect(url: str, msg: str = "", err: str = "") -> RedirectResponse:
    q = f"msg={quote(msg)}" if msg else f"err={quote(err)}" if err else ""
    url, _, frag = url.partition("#")
    url += ("&" if "?" in url else "?") + q if q else ""
    return RedirectResponse(url + ("#" + frag if frag else ""), 303)


def jresp(data, status=200):
    return JSONResponse(jsonable_encoder(data), status_code=status)


# ------------------------------------------------------------------ materials

def workspace_materials(s: Session) -> tuple[list[dict], list[dict]]:
    """(materials visible in the calculator, custom rows with ids)."""
    if not s.ws:
        return library(), []
    hidden = set(s.ws.get("hidden_materials") or [])
    custom = db.custom_materials(s.user_id, s.ws["id"])
    out = [m for m in library() if m["name"] not in hidden]
    out += [{"name": m["name"], "C": float(m["c"]), "n": float(m["n"]),
             "Rm": float(m["rm"]) if m["rm"] is not None else None, "custom": True} for m in custom]
    out.sort(key=lambda m: m["name"].lower())
    return out, custom


def _material_props(material: str, custom):
    if custom and isinstance(custom, dict) and custom.get("name") == material:
        try:
            C, n = float(custom["C"]), float(custom["n"])
            Rm = custom.get("Rm")
            Rm = float(Rm) if Rm not in (None, "") else None
        except (KeyError, TypeError, ValueError):
            return None
        if not (math.isfinite(C) and C > 0 and 0 <= n < 1):
            return None
        return {"name": material, "C": C, "n": n, "Rm": Rm}
    return None


def run_calc(process, shape, material, inputs, custom=None, sweep=None):
    mats = library()
    props = _material_props(material, custom)
    if props:
        mats = [m for m in mats if m["name"] != material] + [props]
    elif not any(m["name"] == material for m in mats):
        material = "CuZr" if any(m["name"] == "CuZr" for m in mats) else mats[0]["name"]
    if not props:
        m = next(m for m in mats if m["name"] == material)
        props = {"name": m["name"], "C": m["C"], "n": m["n"], "Rm": m.get("Rm")}
    clean = {}
    for k, v in (inputs or {}).items():
        if not re.fullmatch(r"C\d{2}", str(k)):
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            clean[k] = v
        elif isinstance(v, str) and len(v) < 40:
            clean[k] = v
    if sweep is not None and not re.fullmatch(r"C\d{2}", str(sweep)):
        sweep = None
    return Calculator(mats).compute(int(process), int(shape), material, clean, sweep=sweep), props, clean


def summary_of(res: dict) -> dict:
    r = res["results"]
    states = [c["state"] for c in res["checks"]]
    return {"F": r["F"], "W": r["W"], "phi": r["phi"], "check": r["check"], "checkLabel": r["checkLabel"],
            "processName": res["processName"], "shapeName": res["shapeName"],
            "status": "bad" if ("bad" in states or res["warnings"]) else "warn" if "warn" in states else "ok"}


# ------------------------------------------------------------------ calculator

@app.get("/", response_class=HTMLResponse)
def calculator(request: Request, calc: str | None = None):
    s = load_session(request)
    saved = None
    switch_to = None
    if calc:
        if not s.signed_in:
            return need_login(request)
        saved = db.get_calc(s.user_id, calc) if is_uuid(calc) else None
        if not saved:
            return flash_redirect("/history", err="That calculation doesn't exist or isn't shared with you.")
        wsid = str(saved["workspace_id"])
        if not s.ws or s.ws["id"] != wsid:
            s.ws = next((w for w in s.workspaces if w["id"] == wsid), s.ws)
            switch_to = wsid
    mats, _ = workspace_materials(s) if s.signed_in else (library(), [])
    resp = page(request, "calculator.html", s, **_calc_ctx(mats, saved, s))
    if switch_to:
        _cookie(resp, WS, switch_to)
    return resp


def _calc_ctx(mats, saved, s):
    boot = {
        "processes": PROCESSES, "notes": PROC_NOTE, "slugs": PROCESS_SLUG,
        "processShapes": PROCESS_SHAPES, "shapeNames": SHAPE_NAMES, "presets": PRESETS,
        "materials": mats, "saved": saved, "signedIn": s.signed_in, "canSave": bool(s.ws),
        "workspace": s.ws and {"id": s.ws["id"], "name": s.ws["name"], "kind": s.ws["kind"]},
        "user": s.user_id,
    }
    return {"boot": json.dumps(jsonable_encoder(boot), ensure_ascii=False).replace("</", "<\\/"),
            "proc_draw": PROC_DRAW, "shape_draw": SHAPE_DRAW, "svg_css": SVG_CSS, "svg_defs": SVG_DEFS,
            "saved": saved}


@app.post("/api/calc")
async def api_calc(request: Request):
    try:
        body = await request.json()
        res, _, _ = run_calc(body.get("process", 6), body.get("shape", 11), str(body.get("material", "CuZr")),
                             body.get("inputs") or {}, body.get("custom"), body.get("sweep"))
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        return JSONResponse({"error": f"Could not calculate: {e}"}, status_code=400)
    return JSONResponse(res)


# ------------------------------------------------------------------ saved calculations

def _save_payload(body: dict):
    title = str(body.get("title") or "").strip()[:120] or "Untitled calculation"
    notes = str(body.get("notes") or "")[:4000]
    material = str(body["material"])[:80]
    res, props, clean = run_calc(int(body["process"]), int(body["shape"]), material, body.get("inputs") or {}, body.get("custom"))
    stored = dict(clean)
    if props:
        stored["_material"] = props
    return {"title": title, "notes": notes, "process": res["process"], "shape": res["shape"],
            "material": res["material"], "inputs": stored, "summary": summary_of(res)}


async def _body(request):
    try:
        b = await request.json()
        return b if isinstance(b, dict) else {}
    except ValueError:
        return {}


@app.post("/api/calculations")
async def create_calc(request: Request):
    s = load_session(request)
    if not s.signed_in or not s.ws:
        return jresp({"error": "Sign in to save calculations"}, 401)
    body = await _body(request)
    try:
        row = _save_payload(body)
    except (KeyError, ValueError, TypeError) as e:
        return jresp({"error": f"Could not save: {e}"}, 400)
    return jresp(db.create_calc(s.user_id, s.ws["id"], row))


@app.put("/api/calculations/{cid}")
async def update_calc(request: Request, cid: str):
    s = load_session(request)
    if not s.signed_in:
        return jresp({"error": "Sign in to save calculations"}, 401)
    if not is_uuid(cid):
        return jresp({"error": "Not found"}, 404)
    body = await _body(request)
    try:
        row = _save_payload(body)
    except (KeyError, ValueError, TypeError) as e:
        return jresp({"error": f"Could not save: {e}"}, 400)
    expected = None if body.get("force") else body.get("expected")
    try:
        return jresp(db.update_calc(s.user_id, cid, row, expected))
    except db.Conflict:
        return jresp({"error": "conflict", "current": db.get_calc(s.user_id, cid)}, 409)


@app.get("/api/calculations/{cid}")
def get_calc(request: Request, cid: str):
    s = load_session(request)
    if not s.signed_in:
        return jresp({"error": "Sign in first"}, 401)
    row = db.get_calc(s.user_id, cid) if is_uuid(cid) else None
    return jresp(row) if row else jresp({"error": "Not found"}, 404)


@app.get("/api/calculations/{cid}/versions")
def calc_versions(request: Request, cid: str):
    s = load_session(request)
    if not s.signed_in:
        return jresp({"error": "Sign in first"}, 401)
    if not is_uuid(cid):
        return jresp({"error": "Not found"}, 404)
    return jresp(db.versions(s.user_id, cid))


@app.delete("/api/calculations/{cid}")
def delete_calc(request: Request, cid: str):
    s = load_session(request)
    if not s.signed_in:
        return jresp({"error": "Sign in first"}, 401)
    if not is_uuid(cid):
        return jresp({"error": "Not found"}, 404)
    db.delete_calc(s.user_id, cid)
    return jresp({"ok": True})


@app.get("/history", response_class=HTMLResponse)
def history(request: Request, q: str = "", process: int = 0, mine: int = 0):
    s = load_session(request)
    if not s.signed_in:
        return need_login(request)
    rows = db.list_calcs(s.user_id, s.ws["id"], q.strip()[:60], process if 1 <= process <= 10 else 0, bool(mine)) if s.ws else []
    return page(request, "history.html", s, rows=rows, q=q, process=process, mine=mine)


@app.post("/workspace/switch")
def switch_ws(request: Request, workspace: str = Form(...), next: str = Form("/history")):
    s = load_session(request)
    if not any(w["id"] == workspace for w in s.workspaces):
        return RedirectResponse("/history", 303)
    nxt = safe_next(next)
    resp = RedirectResponse(nxt, 303)
    _cookie(resp, WS, workspace)
    return resp


# ------------------------------------------------------------------ auth

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = ""):
    s = load_session(request)
    if s.signed_in:
        return RedirectResponse(safe_next(next), 303)
    return page(request, "auth.html", s, mode="login", next=next)


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("")):
    db.ensure_schema()
    try:
        uid = db.authenticate(email[:200], password[:200])
    except ValueError as e:
        return page(request, "auth.html", Session(), mode="login", next=next, err=str(e), email=email, status_code=400)
    return sign_in_response(safe_next(next), uid)


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request, next: str = ""):
    s = load_session(request)
    if s.signed_in:
        return RedirectResponse(safe_next(next), 303)
    return page(request, "auth.html", s, mode="signup", next=next)


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@app.post("/signup")
def signup(request: Request, email: str = Form(...), password: str = Form(...), full_name: str = Form(""),
           next: str = Form(""), account: str = Form("personal"), team_name: str = Form("")):
    db.ensure_schema()
    email, full_name, team_name = email.strip()[:200], full_name.strip()[:80], team_name.strip()[:80]
    err = None
    if not EMAIL_RE.match(email):
        err = "Enter a valid email address."
    elif len(password) < 8 or len(password) > 200:
        err = "Use at least 8 characters for the password."
    elif account == "team" and not next and not team_name:
        err = "Give your company or team a name."
    if not err:
        try:
            uid, ws = db.create_user(email, password, full_name, team_name if account == "team" and not next else "")
        except ValueError as e:
            err = str(e)
    if err:
        return page(request, "auth.html", Session(), mode="signup", next=next, email=email, full_name=full_name,
                    team_name=team_name, account=account, err=err, status_code=400)
    if account == "team" and not next:
        return sign_in_response("/team?msg=" + quote("Your team is ready. Invite your engineers below."), uid, ws)
    return sign_in_response(safe_next(next, "/"), uid)


@app.post("/logout")
def logout(request: Request):
    db.end_session(request.cookies.get(SID))
    resp = RedirectResponse("/", 303)
    resp.delete_cookie(SID, path="/")
    resp.delete_cookie(WS, path="/")
    return resp


@app.get("/forgot", response_class=HTMLResponse)
def forgot_page(request: Request):
    return page(request, "auth.html", load_session(request), mode="forgot")


@app.get("/reset/{token}", response_class=HTMLResponse)
def reset_page(request: Request, token: str):
    db.ensure_schema()
    t = db.reset_target(token)
    return page(request, "auth.html", Session(), mode="reset", token=token, target=t)


@app.post("/reset/{token}")
def reset(request: Request, token: str, password: str = Form(...)):
    if len(password) < 8 or len(password) > 200:
        return page(request, "auth.html", Session(), mode="reset", token=token, target=db.reset_target(token),
                    err="Use at least 8 characters.", status_code=400)
    try:
        uid = db.use_reset(token, password)
    except ValueError as e:
        return page(request, "auth.html", Session(), mode="reset", token=token, target=None, err=str(e), status_code=400)
    return sign_in_response("/history?msg=" + quote("Your password is updated."), uid)


@app.get("/account", response_class=HTMLResponse)
def account(request: Request):
    s = load_session(request)
    if not s.signed_in:
        return need_login(request)
    return page(request, "account.html", s)


@app.post("/account/name")
def account_name(request: Request, full_name: str = Form(...)):
    s = load_session(request)
    if not s.signed_in:
        return need_login(request)
    db.set_name(s.user_id, full_name.strip()[:80])
    return flash_redirect("/account", msg="Name updated.")


@app.post("/account/password")
def account_password(request: Request, current: str = Form(...), new: str = Form(...)):
    s = load_session(request)
    if not s.signed_in:
        return need_login(request)
    if len(new) < 8 or len(new) > 200:
        return flash_redirect("/account", err="Use at least 8 characters for the new password.")
    try:
        db.change_password(s.user_id, current, new)
        db.set_password(s.user_id, new, keep_session=s.token)
    except ValueError as e:
        return flash_redirect("/account", err=str(e))
    return flash_redirect("/account", msg="Password changed. Other devices were signed out.")


# ------------------------------------------------------------------ team

@app.get("/team", response_class=HTMLResponse)
def team(request: Request):
    s = load_session(request)
    if not s.signed_in:
        return need_login(request)
    mem = db.members(s.user_id, s.ws["id"]) if s.ws else []
    for m in mem:
        m["user_id"] = str(m["user_id"])
        m["me"] = m["user_id"] == s.user_id
    inv = db.invites(s.user_id, s.ws["id"]) if s.ws and s.ws["kind"] == "team" else []
    seats = len(mem)
    price = (config.PRICE_BASE_CENTS + max(0, seats - 1) * config.PRICE_SEAT_CENTS) if s.ws and s.ws["kind"] == "team" else config.PRICE_BASE_CENTS
    return page(request, "team.html", s, members=mem, invites=inv, seats=seats, price=price / 100, base=site_url(request),
                new_link=request.query_params.get("link", ""), reset_link=request.query_params.get("reset", ""),
                reset_for=request.query_params.get("for", ""))


@app.post("/team/create")
def team_create(request: Request, name: str = Form(...)):
    s = load_session(request)
    if not s.signed_in:
        return need_login(request)
    name = name.strip()[:80]
    if not name:
        return flash_redirect("/team", err="Give the team a name.")
    ws = db.create_team(s.user_id, name)
    resp = flash_redirect("/team", msg=f"Team “{name}” created. Invite your engineers below.")
    _cookie(resp, WS, str(ws))
    return resp


@app.post("/team/rename")
def team_rename(request: Request, name: str = Form(...)):
    s = load_session(request)
    if not s.ws:
        return need_login(request)
    db.rename_workspace(s.user_id, s.ws["id"], name.strip()[:80] or s.ws["name"])
    return flash_redirect("/team", msg="Workspace renamed.")


@app.post("/team/invite")
def team_invite(request: Request, role: str = Form("engineer"), email: str = Form("")):
    s = load_session(request)
    if not s.ws:
        return need_login(request)
    token = db.create_invite(s.user_id, s.ws["id"], role, email.strip()[:200])
    return RedirectResponse(f"/team?link={token}", 303)


@app.post("/team/invite/{iid}/revoke")
def team_revoke(request: Request, iid: str):
    s = load_session(request)
    if s.ws and is_uuid(iid):
        db.revoke_invite(s.user_id, s.ws["id"], iid)
    return flash_redirect("/team", msg="Invite link revoked.")


@app.post("/team/member/{uid}/role")
def team_role(request: Request, uid: str, role: str = Form(...)):
    s = load_session(request)
    if not s.ws or not is_uuid(uid):
        return RedirectResponse("/team", 303)
    db.set_role(s.user_id, s.ws["id"], uid, role)
    return flash_redirect("/team", msg="Role updated.")


@app.post("/team/member/{uid}/remove")
def team_remove(request: Request, uid: str):
    s = load_session(request)
    if not s.ws or not is_uuid(uid):
        return RedirectResponse("/team", 303)
    db.remove_member(s.user_id, s.ws["id"], uid)
    if uid == s.user_id:
        resp = flash_redirect("/history", msg=f"You left {s.ws['name']}.")
        resp.delete_cookie(WS, path="/")
        return resp
    return flash_redirect("/team", msg="Member removed.")


@app.post("/team/member/{uid}/reset")
def team_reset(request: Request, uid: str):
    s = load_session(request)
    if not s.ws or not is_uuid(uid):
        return RedirectResponse("/team", 303)
    token = db.create_reset_link(s.user_id, s.ws["id"], uid)
    name = next((m["name"] or m["email"] for m in db.members(s.user_id, s.ws["id"]) if str(m["user_id"]) == uid), "")
    return RedirectResponse(f"/team?reset={token}&for={quote(name)}", 303)


@app.get("/invite/{token}", response_class=HTMLResponse)
def invite_page(request: Request, token: str):
    s = load_session(request)
    info = db.invite_info(token) if re.fullmatch(r"[0-9a-f]{20,80}", token) else None
    member = bool(info and s.signed_in and any(w["id"] == str(info["workspace_id"]) for w in s.workspaces))
    return page(request, "invite.html", s, info=info, token=token, member=member)


@app.post("/invite/{token}")
def invite_accept(request: Request, token: str):
    s = load_session(request)
    if not s.signed_in:
        return need_login(request)
    try:
        ws = db.accept_invite(s.user_id, token)
    except ValueError as e:
        return flash_redirect(f"/invite/{token}", err=str(e))
    resp = flash_redirect("/history", msg="You joined the team. Calculations saved here are shared with everyone in it.")
    _cookie(resp, WS, str(ws))
    return resp


# ------------------------------------------------------------------ materials

@app.get("/materials", response_class=HTMLResponse)
def materials(request: Request):
    s = load_session(request)
    if not s.signed_in or not s.ws:
        return page(request, "materials.html", s, defaults=library(), custom=[], hidden=set())
    _, custom = workspace_materials(s)
    return page(request, "materials.html", s, defaults=library(), custom=custom,
                hidden=set(s.ws.get("hidden_materials") or []), edit=request.query_params.get("edit", ""))


def _float(v, lo=None, hi=None):
    try:
        x = float(str(v).replace(",", "."))
    except ValueError:
        return None
    if not math.isfinite(x) or (lo is not None and x <= lo) or (hi is not None and x >= hi):
        return None
    return x


@app.post("/materials/add")
def material_add(request: Request, name: str = Form(...), c: str = Form(...), n: str = Form(...), rm: str = Form("")):
    s = load_session(request)
    if not s.ws:
        return need_login(request)
    name = name.strip()[:60]
    C, N = _float(c, 0, 1e6), _float(n, -1e-12, 1)
    Rm = _float(rm, 0, 1e6) if rm.strip() else None
    if not name or C is None or N is None or (rm.strip() and Rm is None):
        return flash_redirect("/materials", err="Enter a name, C above 0 and n from 0 up to 1.")
    if name.lower() in {n.lower() for n in library_names()}:
        return flash_redirect("/materials", err=f"{name} is already in the standard library. Choose another name.")
    if Rm is None:
        Rm = C * (N / math.e) ** N if N > 0 else C
    try:
        db.add_material(s.user_id, s.ws["id"], name, C, N, round(Rm, 2))
    except ValueError as e:
        return flash_redirect("/materials", err=str(e))
    return flash_redirect("/materials", msg=f"{name} added. It's now in the material list for everyone in {s.ws['name']}.")


@app.post("/materials/{mid}/delete")
def material_delete(request: Request, mid: str):
    s = load_session(request)
    if s.ws and is_uuid(mid):
        db.delete_material(s.user_id, s.ws["id"], mid)
    return flash_redirect("/materials", msg="Material removed.")


@app.post("/materials/visibility")
def material_visibility(request: Request, name: str = Form(...), hide: int = Form(...)):
    s = load_session(request)
    if not s.ws:
        return need_login(request)
    hidden = set(s.ws.get("hidden_materials") or [])
    if name in library_names() or not hide:
        (hidden.add if hide else hidden.discard)(name)
    db.set_hidden(s.user_id, s.ws["id"], hidden)
    return RedirectResponse("/materials#std", 303)


def _material_form(name, c, n, rm):
    name = name.strip()[:60]
    C, N = _float(c, 0, 1e6), _float(n, -1e-12, 1)
    Rm = _float(rm, 0, 1e6) if rm.strip() else None
    if not name or C is None or N is None or (rm.strip() and Rm is None):
        raise ValueError("Enter a name, C above 0 and n from 0 up to 1.")
    if Rm is None:
        Rm = C * (N / math.e) ** N if N > 0 else C
    return name, C, N, round(Rm, 2)


def _need_site_admin(s: Session):
    if not s.is_site_admin:
        raise db.Denied("Only the site owner can change the standard library.")


@app.post("/library/add")
def library_add(request: Request, name: str = Form(...), c: str = Form(...), n: str = Form(...), rm: str = Form("")):
    s = load_session(request)
    _need_site_admin(s)
    try:
        name, C, N, Rm = _material_form(name, c, n, rm)
        db.lib_add(s.user_id, name, C, N, Rm)
    except ValueError as e:
        return flash_redirect("/materials#std", err=str(e))
    return flash_redirect("/materials#std", msg=f"{name} added to the standard library for everyone.")


@app.post("/library/{mid}/edit")
def library_edit(request: Request, mid: str, name: str = Form(...), c: str = Form(...), n: str = Form(...), rm: str = Form("")):
    s = load_session(request)
    _need_site_admin(s)
    if not is_uuid(mid):
        return RedirectResponse("/materials#std", 303)
    try:
        name, C, N, Rm = _material_form(name, c, n, rm)
        db.lib_update(s.user_id, mid, name, C, N, Rm)
    except ValueError as e:
        return flash_redirect(f"/materials?edit={mid}#std", err=str(e))
    return flash_redirect("/materials#std", msg=f"{name} updated for everyone.")


@app.post("/library/{mid}/delete")
def library_delete(request: Request, mid: str):
    s = load_session(request)
    _need_site_admin(s)
    if is_uuid(mid):
        db.lib_delete(mid)
    return flash_redirect("/materials#std", msg="Material removed from the standard library.")


# ------------------------------------------------------------------ misc

@app.get("/pricing", response_class=HTMLResponse)
def pricing(request: Request):
    return page(request, "pricing.html", load_session(request))


@app.get("/healthz")
def healthz():
    db.ensure_schema()
    db.q("select 1")
    return {"ok": True}
