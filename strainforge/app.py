"""Strainforge web app (FastAPI).

Public: the calculator, owner-built calculators and /api/calc.  Signed in:
saved history, team workspaces with shared calculations, admin role, custom
materials.  Site owner: the business dashboard, the standard library and the
calculator builder.

Routes live in strainforge/routes/, one module per area; shared helpers are in
routes/common.py and every permission rule is in db.py.
"""
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import db
from .routes import admin, auth, calculator, materials, team, tools
from .routes.common import HERE, flash_redirect, load_session, page

app = FastAPI(title="Strainforge", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
for r in (calculator, auth, team, materials, tools, admin):
    app.include_router(r.router)


@app.middleware("http")
async def headers_and_csrf(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin") or request.headers.get("referer")
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
        if origin and urlparse(origin).netloc != host:
            return JSONResponse({"error": "Cross-site request blocked"}, status_code=403)
    resp = await call_next(request)
    if getattr(request.state, "clear_sid", False):
        resp.delete_cookie("sf_sid", path="/")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    if request.url.path.startswith("/static/"):
        resp.headers.setdefault("Cache-Control", "public, max-age=86400")
    elif resp.headers.get("content-type", "").startswith("text/html"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


@app.exception_handler(db.Denied)
async def denied(request: Request, exc: db.Denied):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": str(exc)}, status_code=403)
    back = urlparse(request.headers.get("referer") or "").path
    if not back or back == request.url.path:
        back = "/calculator"
    return flash_redirect(back, err=str(exc))


@app.exception_handler(StarletteHTTPException)
async def not_found(request: Request, exc: StarletteHTTPException):
    if exc.status_code != 404 or request.url.path.startswith(("/api/", "/static/")):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
    return page(request, "error.html", load_session(request), status_code=404,
                title="Page not found", text="That address doesn't exist. It may have moved.")


@app.get("/pricing", response_class=HTMLResponse)
def pricing(request: Request):
    return page(request, "pricing.html", load_session(request))


@app.get("/healthz")
def healthz():
    db.ensure_schema()
    db.q("select 1")
    return {"ok": True, "schema": db.SCHEMA_VERSION}
