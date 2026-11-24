"""Shared helpers for every route: session, templates, redirects, material lookup and the calculator runner."""
import math
import re
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from .. import config, db
from ..calc import DEFAULT_MATERIALS, PROCESSES, SHAPE_NAMES, Calculator
from ..drawings import all_drawings

HERE = Path(__file__).parent.parent
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


def set_cookie(resp: Response, key, value, max_age=MONTH):
    resp.set_cookie(key, value, max_age=max_age, httponly=True, secure=config.COOKIE_SECURE, samesite="lax", path="/")


def sign_in_response(url: str, uid, ws=None) -> RedirectResponse:
    resp = RedirectResponse(url, 303)
    set_cookie(resp, SID, db.new_session(uid))
    if ws:
        set_cookie(resp, WS, str(ws))
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



def page(request: Request, name: str, s: Session, status_code=200, **ctx):
    ctx.setdefault("msg", request.query_params.get("msg", ""))
    ctx.setdefault("err", request.query_params.get("err", ""))
    ctx.setdefault("nav_tools", has_tools())
    return templates.TemplateResponse(request, name, {"s": s, "path": request.url.path, **ctx}, status_code=status_code)


def has_tools() -> bool:
    from .. import builtin
    if builtin.TOOLS:
        return True
    if not config.DATABASE_URL:
        return False
    try:
        return bool(db.tools(published_only=True))
    except Exception:  # the nav must render even if the database is briefly unreachable
        return False


ACTIVE_PLANS = ("early_access", "trial", "personal", "team")


def can_report(s) -> bool:
    """PDF and Excel reports are a paid feature (every active plan, including early access)."""
    return bool(s.signed_in and s.ws and s.ws.get("plan") in ACTIVE_PLANS)


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


async def read_json(request):
    try:
        b = await request.json()
        return b if isinstance(b, dict) else {}
    except ValueError:
        return {}

def to_float(v, lo=None, hi=None):
    try:
        x = float(str(v).replace(",", "."))
    except ValueError:
        return None
    if not math.isfinite(x) or (lo is not None and x <= lo) or (hi is not None and x >= hi):
        return None
    return x

def material_form(name, c, n, rm):
    name = name.strip()[:60]
    C, N = to_float(c, 0, 1e6), to_float(n, -1e-12, 1)
    Rm = to_float(rm, 0, 1e6) if rm.strip() else None
    if not name or C is None or N is None or (rm.strip() and Rm is None):
        raise ValueError("Enter a name, C above 0 and n from 0 up to 1.")
    if Rm is None:
        Rm = C * (N / math.e) ** N if N > 0 else C
    return name, C, N, round(Rm, 2)


def need_site_admin(s: Session, what="do that"):
    if not s.is_site_admin:
        raise db.Denied(f"Only the site owner can {what}.")

