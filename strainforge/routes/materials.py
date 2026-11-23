"""Workspace materials and the site-wide standard library."""
import math

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import db
from .common import (
    flash_redirect, is_uuid, library, library_names, load_session, material_form, need_login,
    need_site_admin, page, to_float, workspace_materials,
)

router = APIRouter()


# ------------------------------------------------------------------ materials

@router.get("/materials", response_class=HTMLResponse)
def materials(request: Request):
    s = load_session(request)
    if not s.signed_in or not s.ws:
        return page(request, "materials.html", s, defaults=library(), custom=[], hidden=set())
    _, custom = workspace_materials(s)
    return page(request, "materials.html", s, defaults=library(), custom=custom,
                hidden=set(s.ws.get("hidden_materials") or []), edit=request.query_params.get("edit", ""))



@router.post("/materials/add")
def material_add(request: Request, name: str = Form(...), c: str = Form(...), n: str = Form(...), rm: str = Form("")):
    s = load_session(request)
    if not s.ws:
        return need_login(request)
    name = name.strip()[:60]
    C, N = to_float(c, 0, 1e6), to_float(n, -1e-12, 1)
    Rm = to_float(rm, 0, 1e6) if rm.strip() else None
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


@router.post("/materials/{mid}/delete")
def material_delete(request: Request, mid: str):
    s = load_session(request)
    if s.ws and is_uuid(mid):
        db.delete_material(s.user_id, s.ws["id"], mid)
    return flash_redirect("/materials", msg="Material removed.")


@router.post("/materials/visibility")
def material_visibility(request: Request, name: str = Form(...), hide: int = Form(...)):
    s = load_session(request)
    if not s.ws:
        return need_login(request)
    hidden = set(s.ws.get("hidden_materials") or [])
    if name in library_names() or not hide:
        (hidden.add if hide else hidden.discard)(name)
    db.set_hidden(s.user_id, s.ws["id"], hidden)
    return RedirectResponse("/materials#std", 303)



@router.post("/library/add")
def library_add(request: Request, name: str = Form(...), c: str = Form(...), n: str = Form(...), rm: str = Form("")):
    s = load_session(request)
    need_site_admin(s, "change the standard library")
    try:
        name, C, N, Rm = material_form(name, c, n, rm)
        db.lib_add(s.user_id, name, C, N, Rm)
    except ValueError as e:
        return flash_redirect("/materials#std", err=str(e))
    return flash_redirect("/materials#std", msg=f"{name} added to the standard library for everyone.")


@router.post("/library/{mid}/edit")
def library_edit(request: Request, mid: str, name: str = Form(...), c: str = Form(...), n: str = Form(...), rm: str = Form("")):
    s = load_session(request)
    need_site_admin(s, "change the standard library")
    if not is_uuid(mid):
        return RedirectResponse("/materials#std", 303)
    try:
        name, C, N, Rm = material_form(name, c, n, rm)
        db.lib_update(s.user_id, mid, name, C, N, Rm)
    except ValueError as e:
        return flash_redirect(f"/materials?edit={mid}#std", err=str(e))
    return flash_redirect("/materials#std", msg=f"{name} updated for everyone.")


@router.post("/library/{mid}/delete")
def library_delete(request: Request, mid: str):
    s = load_session(request)
    need_site_admin(s, "change the standard library")
    if is_uuid(mid):
        db.lib_delete(mid)
    return flash_redirect("/materials#std", msg="Material removed from the standard library.")
