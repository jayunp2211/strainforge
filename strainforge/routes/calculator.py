"""The calculator page, the calculation API and saved history."""
import json

from fastapi import APIRouter, Form, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .. import builtin, config, db
from ..calc import PRESETS, PROCESSES, PROCESS_SHAPES, PROCESS_SLUG, SHAPE_NAMES
from ..drawings import SVG_CSS, SVG_DEFS
from .common import (
    PROC_DRAW, PROC_NOTE, SHAPE_DRAW, WS, can_report, flash_redirect, is_uuid, jresp, library, load_session,
    need_login, page, read_json, run_calc, safe_next, set_cookie, summary_of, workspace_materials,
)

router = APIRouter()


# ------------------------------------------------------------------ calculator

@router.get("/", response_class=HTMLResponse)
def home(request: Request, calc: str | None = None):
    """The site owner lands on the dashboard; everyone else on the calculator."""
    s = load_session(request)
    if s.is_site_admin and not calc:
        from .admin import dashboard
        return dashboard(request)
    return calculator(request, calc)


@router.get("/calculator", response_class=HTMLResponse)
def calculator(request: Request, calc: str | None = None):
    s = load_session(request)
    if not calc:
        db.count_view("calculator")
    saved = None
    switch_to = None
    if calc:
        if not s.signed_in:
            return need_login(request)
        saved = db.get_calc(s.user_id, calc) if is_uuid(calc) else None
        if not saved:
            return flash_redirect("/history", err="That calculation doesn't exist or isn't shared with you.")
        if saved.get("tool"):
            return RedirectResponse(f"/tools/{saved['tool']}?calc={saved['id']}", 303)
        wsid = str(saved["workspace_id"])
        if not s.ws or s.ws["id"] != wsid:
            s.ws = next((w for w in s.workspaces if w["id"] == wsid), s.ws)
            switch_to = wsid
    mats, _ = workspace_materials(s) if s.signed_in else (library(), [])
    resp = page(request, "calculator.html", s, **_calc_ctx(mats, saved, s))
    if switch_to:
        set_cookie(resp, WS, switch_to)
    return resp


def _calc_ctx(mats, saved, s):
    boot = {
        "processes": PROCESSES, "notes": PROC_NOTE, "slugs": PROCESS_SLUG, "assetVersion": config.ASSET_VERSION,
        "processShapes": PROCESS_SHAPES, "shapeNames": SHAPE_NAMES, "presets": PRESETS,
        "materials": mats, "saved": saved, "signedIn": s.signed_in, "canSave": bool(s.ws),
        "workspace": s.ws and {"id": s.ws["id"], "name": s.ws["name"], "kind": s.ws["kind"]},
        "user": s.user_id,
    }
    return {"canonical_path": "/", "boot": json.dumps(jsonable_encoder(boot), ensure_ascii=False).replace("</", "<\\/"),
            "proc_draw": PROC_DRAW, "shape_draw": SHAPE_DRAW, "svg_css": SVG_CSS, "svg_defs": SVG_DEFS,
            "saved": saved, "can_report": can_report(s)}


@router.post("/api/calc")
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



@router.post("/api/calculations")
async def create_calc(request: Request):
    s = load_session(request)
    if not s.signed_in or not s.ws:
        return jresp({"error": "Sign in to save calculations"}, 401)
    body = await read_json(request)
    try:
        row = _save_payload(body)
    except (KeyError, ValueError, TypeError) as e:
        return jresp({"error": f"Could not save: {e}"}, 400)
    return jresp(db.create_calc(s.user_id, s.ws["id"], row))


@router.put("/api/calculations/{cid}")
async def update_calc(request: Request, cid: str):
    s = load_session(request)
    if not s.signed_in:
        return jresp({"error": "Sign in to save calculations"}, 401)
    if not is_uuid(cid):
        return jresp({"error": "Not found"}, 404)
    body = await read_json(request)
    try:
        row = _save_payload(body)
    except (KeyError, ValueError, TypeError) as e:
        return jresp({"error": f"Could not save: {e}"}, 400)
    expected = None if body.get("force") else body.get("expected")
    try:
        return jresp(db.update_calc(s.user_id, cid, row, expected))
    except db.Conflict:
        return jresp({"error": "conflict", "current": db.get_calc(s.user_id, cid)}, 409)


@router.get("/api/calculations/{cid}")
def get_calc(request: Request, cid: str):
    s = load_session(request)
    if not s.signed_in:
        return jresp({"error": "Sign in first"}, 401)
    row = db.get_calc(s.user_id, cid) if is_uuid(cid) else None
    return jresp(row) if row else jresp({"error": "Not found"}, 404)


@router.get("/api/calculations/{cid}/versions")
def calc_versions(request: Request, cid: str):
    s = load_session(request)
    if not s.signed_in:
        return jresp({"error": "Sign in first"}, 401)
    if not is_uuid(cid):
        return jresp({"error": "Not found"}, 404)
    return jresp(db.versions(s.user_id, cid))


@router.delete("/api/calculations/{cid}")
def delete_calc(request: Request, cid: str):
    s = load_session(request)
    if not s.signed_in:
        return jresp({"error": "Sign in first"}, 401)
    if not is_uuid(cid):
        return jresp({"error": "Not found"}, 404)
    db.delete_calc(s.user_id, cid)
    return jresp({"ok": True})


@router.get("/history", response_class=HTMLResponse)
def history(request: Request, q: str = "", process: str = "0", mine: int = 0):
    s = load_session(request)
    if not s.signed_in:
        return need_login(request)
    tool = process[2:] if process.startswith("t:") and process[2:] in builtin.TOOLS else ""
    proc = int(process) if process.isdigit() and 1 <= int(process) <= 10 else 0
    rows = db.list_calcs(s.user_id, s.ws["id"], q.strip()[:60], proc, bool(mine), tool) if s.ws else []
    return page(request, "history.html", s, rows=rows, q=q, process=process if (tool or proc) else "0", mine=mine,
                tools=builtin.TOOLS)


@router.post("/workspace/switch")
def switch_ws(request: Request, workspace: str = Form(...), next: str = Form("/history")):
    s = load_session(request)
    if not any(w["id"] == workspace for w in s.workspaces):
        return RedirectResponse("/history", 303)
    nxt = safe_next(next)
    resp = RedirectResponse(nxt, 303)
    set_cookie(resp, WS, workspace)
    return resp
