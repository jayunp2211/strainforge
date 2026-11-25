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
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import config, db
from .routes import admin, auth, calculator, materials, reports, team, tools
from .routes.common import HERE, flash_redirect, load_session, page

app = FastAPI(title="Strainforge", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
for r in (calculator, auth, team, materials, tools, reports, admin):
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
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if not config.IS_PRODUCTION:
        resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    if request.url.path.startswith("/static/"):
        # Versioned URLs (?v=<deploy>) never change, so they can be cached for a year.
        long = request.query_params.get("v") == config.ASSET_VERSION and config.ASSET_VERSION != "dev"
        resp.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable" if long else "public, max-age=3600")
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


# ------------------------------------------------------------------ search engines
# Only the free public pages are listed; everything behind a sign-in also says noindex in its <head>.
PRIVATE = ("/admin", "/account", "/history", "/team", "/workspace", "/invite", "/reset", "/api/", "/login",
           "/signup", "/forgot")


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    if not config.IS_PRODUCTION:
        return "User-agent: *\nDisallow: /\n"
    lines = ["User-agent: *", *[f"Disallow: {p}" for p in PRIVATE], "", f"Sitemap: {config.SITE_URL}/sitemap.xml", ""]
    return "\n".join(lines)


@app.get("/sitemap.xml")
def sitemap():
    from xml.sax.saxutils import escape as x
    from . import builtin
    paths = ["/", "/calculator", "/materials", "/pricing", *[f"/calculator/{k}" for k in builtin.TOOLS]]
    try:
        paths += [f"/calculator/{t['slug']}" for t in tools.published_tools()]
    except Exception:  # the static pages are still worth listing if the database is briefly unreachable
        pass
    urls = "".join(f"<url><loc>{x(config.SITE_URL + p)}</loc></url>" for p in paths)
    body = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return Response(body, media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})
