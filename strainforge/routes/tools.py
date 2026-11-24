"""Calculators the site owner built, open to everyone like the main calculator."""
import json

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse

from .. import builtin, config, db
from ..drawings import SVG_CSS, SVG_DEFS
from ..formula import run
from fastapi.responses import RedirectResponse

from .common import (WS, can_report, flash_redirect, is_uuid, jresp, library, load_session, need_login, page, read_json,
                     set_cookie, workspace_materials)

router = APIRouter()


def published_tools():
    return db.tools(published_only=True) if config.DATABASE_URL else []


@router.get("/tools", response_class=HTMLResponse)
def tools_index(request: Request):
    s = load_session(request)
    return page(request, "tools.html", s, tools=published_tools(), builtins=list(builtin.TOOLS.values()))


@router.get("/tools/{slug}", response_class=HTMLResponse)
def tool_page(request: Request, slug: str, calc: str | None = None):
    s = load_session(request)
    bt = builtin.get(slug)
    if bt:
        saved, switch_to = None, None
        if calc:
            if not s.signed_in:
                return need_login(request)
            saved = db.get_calc(s.user_id, calc) if is_uuid(calc) else None
            if not saved or saved.get("tool") != slug:
                return flash_redirect("/history", err="That saved result doesn't exist or isn't shared with you.")
            wsid = str(saved["workspace_id"])
            if not s.ws or s.ws["id"] != wsid:
                s.ws = next((w for w in s.workspaces if w["id"] == wsid), s.ws)
                switch_to = wsid
        else:
            db.count_view("tool:" + slug)
        boot = {"tool": builtin.public_spec(bt), "saved": saved, "canSave": bool(s.signed_in and s.ws),
                "canReport": can_report(s),
                "workspace": {"name": s.ws["name"], "kind": s.ws["kind"]} if s.ws else None,
                "user": s.name if s.signed_in else ""}
        resp = page(request, "builtin_tool.html", s, t=bt, saved=saved, can_report=can_report(s), canonical_path=f"/tools/{slug}",
                    svg_css=SVG_CSS, svg_defs=SVG_DEFS,
                    boot=json.dumps(jsonable_encoder(boot), ensure_ascii=False).replace("</", "<\\/"))
        if switch_to:
            set_cookie(resp, WS, switch_to)
        return resp
    t = db.tool(slug[:60]) if config.DATABASE_URL else None
    if not t or (not t["published"] and not s.is_site_admin):
        return flash_redirect("/tools", err="That calculator isn't available.")
    if t["published"]:
        db.tool_viewed(t["id"])
        db.count_view("tool:" + t["slug"])
    mats = workspace_materials(s)[0] if s.signed_in else library()
    boot = {"slug": t["slug"], "spec": t["spec"], "materials": mats if t["spec"].get("material") else []}
    return page(request, "tool.html", s, t=t, canonical_path=f"/tools/{t['slug']}",
                boot=json.dumps(jsonable_encoder(boot), ensure_ascii=False).replace("</", "<\\/"))


@router.post("/api/tools/{slug}")
async def tool_run(request: Request, slug: str):
    bt = builtin.get(slug)
    if bt:
        body = await read_json(request)
        values = body.get("values") if isinstance(body, dict) else None
        if not isinstance(values, dict):
            return jresp({"error": "Send the inputs as values"}, 400)
        return jresp(bt["calculate"](values))
    s = load_session(request)
    t = db.tool(slug[:60]) if config.DATABASE_URL else None
    if not t or (not t["published"] and not s.is_site_admin):
        return jresp({"error": "Not found"}, 404)
    body = await read_json(request)
    mats = workspace_materials(s)[0] if s.signed_in else library()
    mat = next((m for m in mats if m["name"] == body.get("material")), None) or (mats[0] if mats else None)
    return jresp({"outputs": run(t["spec"], body.get("values") or {}, mat), "material": mat})


# ------------------------------------------------------------------ saved tool results

def _tool_summary(res: dict) -> dict:
    states = [c["state"] for c in res.get("checks", [])]
    kpis = [{"label": k["label"], "value": k.get("value"), "unit": k.get("unit", ""), "text": k.get("text")}
            for k in res.get("kpis", [])[:2]]
    return {"kpis": kpis,
            "status": "bad" if ("bad" in states or res.get("warnings")) else "warn" if "warn" in states else "ok"}


def _tool_row(bt, body: dict) -> dict:
    values = body.get("values")
    if not isinstance(values, dict):
        raise ValueError("send the inputs as values")
    keys = {i["key"] for i in bt["inputs"]}
    clean = {k: v for k, v in values.items() if k in keys and (v is None or isinstance(v, (int, float, str)))}
    clean = {k: (v[:80] if isinstance(v, str) else v) for k, v in clean.items()}
    res = bt["calculate"](clean)
    return {"title": str(body.get("title") or "").strip()[:120] or "Untitled " + bt["title"].lower(),
            "notes": str(body.get("notes") or "")[:4000], "tool": bt["slug"], "process": 0, "shape": 0,
            "material": "", "inputs": clean, "summary": _tool_summary(res)}


@router.post("/api/tools/{slug}/saved")
async def tool_save(request: Request, slug: str):
    bt = builtin.get(slug)
    if not bt:
        return jresp({"error": "Not found"}, 404)
    s = load_session(request)
    if not s.signed_in or not s.ws:
        return jresp({"error": "Create a free account to save results"}, 401)
    body = await read_json(request)
    try:
        row = _tool_row(bt, body)
    except (KeyError, ValueError, TypeError) as e:
        return jresp({"error": f"Could not save: {e}"}, 400)
    return jresp(db.create_calc(s.user_id, s.ws["id"], row))


@router.put("/api/tools/{slug}/saved/{cid}")
async def tool_update(request: Request, slug: str, cid: str):
    bt = builtin.get(slug)
    s = load_session(request)
    if not bt or not is_uuid(cid):
        return jresp({"error": "Not found"}, 404)
    if not s.signed_in:
        return jresp({"error": "Sign in to save results"}, 401)
    body = await read_json(request)
    try:
        row = _tool_row(bt, body)
    except (KeyError, ValueError, TypeError) as e:
        return jresp({"error": f"Could not save: {e}"}, 400)
    expected = None if body.get("force") else body.get("expected")
    try:
        return jresp(db.update_calc(s.user_id, cid, row, expected))
    except db.Conflict:
        return jresp({"error": "conflict", "current": db.get_calc(s.user_id, cid)}, 409)
