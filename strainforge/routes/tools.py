"""Calculators the site owner built, open to everyone like the main calculator."""
import json

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse

from .. import builtin, config, db
from ..drawings import SVG_CSS, SVG_DEFS
from ..formula import run
from .common import flash_redirect, jresp, library, load_session, page, read_json, workspace_materials

router = APIRouter()


def published_tools():
    return db.tools(published_only=True) if config.DATABASE_URL else []


@router.get("/tools", response_class=HTMLResponse)
def tools_index(request: Request):
    s = load_session(request)
    return page(request, "tools.html", s, tools=published_tools(), builtins=list(builtin.TOOLS.values()))


@router.get("/tools/{slug}", response_class=HTMLResponse)
def tool_page(request: Request, slug: str):
    s = load_session(request)
    bt = builtin.get(slug)
    if bt:
        db.count_view("tool:" + slug)
        boot = {"tool": builtin.public_spec(bt)}
        return page(request, "builtin_tool.html", s, t=bt, canonical_path=f"/tools/{slug}", svg_css=SVG_CSS, svg_defs=SVG_DEFS,
                    boot=json.dumps(jsonable_encoder(boot), ensure_ascii=False).replace("</", "<\\/"))
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
