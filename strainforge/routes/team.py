"""Team workspaces: members, roles, invites."""
from urllib.parse import quote
import re

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import config, db
from .common import (
    WS, flash_redirect, is_uuid, load_session, need_login, page, set_cookie, site_url,
)

router = APIRouter()


# ------------------------------------------------------------------ team

@router.get("/team", response_class=HTMLResponse)
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


@router.post("/team/create")
def team_create(request: Request, name: str = Form(...)):
    s = load_session(request)
    if not s.signed_in:
        return need_login(request)
    name = name.strip()[:80]
    if not name:
        return flash_redirect("/team", err="Give the team a name.")
    ws = db.create_team(s.user_id, name)
    resp = flash_redirect("/team", msg=f"Team “{name}” created. Invite your engineers below.")
    set_cookie(resp, WS, str(ws))
    return resp


@router.post("/team/rename")
def team_rename(request: Request, name: str = Form(...)):
    s = load_session(request)
    if not s.ws:
        return need_login(request)
    db.rename_workspace(s.user_id, s.ws["id"], name.strip()[:80] or s.ws["name"])
    return flash_redirect("/team", msg="Workspace renamed.")


@router.post("/team/delete")
def team_delete(request: Request, confirm: str = Form("")):
    s = load_session(request)
    if not s.ws:
        return need_login(request)
    try:
        name = db.delete_workspace(s.user_id, s.ws["id"], confirm)
    except ValueError as e:
        return flash_redirect("/team#delete", err=str(e))
    resp = flash_redirect("/team", msg=f"Workspace “{name}” deleted.")
    resp.delete_cookie(WS, path="/")
    return resp


@router.post("/team/invite")
def team_invite(request: Request, role: str = Form("engineer"), email: str = Form("")):
    s = load_session(request)
    if not s.ws:
        return need_login(request)
    token = db.create_invite(s.user_id, s.ws["id"], role, email.strip()[:200])
    return RedirectResponse(f"/team?link={token}", 303)


@router.post("/team/invite/{iid}/revoke")
def team_revoke(request: Request, iid: str):
    s = load_session(request)
    if s.ws and is_uuid(iid):
        db.revoke_invite(s.user_id, s.ws["id"], iid)
    return flash_redirect("/team", msg="Invite link revoked.")


@router.post("/team/member/{uid}/role")
def team_role(request: Request, uid: str, role: str = Form(...)):
    s = load_session(request)
    if not s.ws or not is_uuid(uid):
        return RedirectResponse("/team", 303)
    db.set_role(s.user_id, s.ws["id"], uid, role)
    return flash_redirect("/team", msg="Role updated.")


@router.post("/team/member/{uid}/remove")
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


@router.post("/team/member/{uid}/reset")
def team_reset(request: Request, uid: str):
    s = load_session(request)
    if not s.ws or not is_uuid(uid):
        return RedirectResponse("/team", 303)
    token = db.create_reset_link(s.user_id, s.ws["id"], uid)
    name = next((m["name"] or m["email"] for m in db.members(s.user_id, s.ws["id"]) if str(m["user_id"]) == uid), "")
    return RedirectResponse(f"/team?reset={token}&for={quote(name)}", 303)


@router.get("/invite/{token}", response_class=HTMLResponse)
def invite_page(request: Request, token: str):
    s = load_session(request)
    info = db.invite_info(token) if re.fullmatch(r"[0-9a-f]{20,80}", token) else None
    member = bool(info and s.signed_in and any(w["id"] == str(info["workspace_id"]) for w in s.workspaces))
    return page(request, "invite.html", s, info=info, token=token, member=member)


@router.post("/invite/{token}")
def invite_accept(request: Request, token: str):
    s = load_session(request)
    if not s.signed_in:
        return need_login(request)
    try:
        ws = db.accept_invite(s.user_id, token)
    except ValueError as e:
        return flash_redirect(f"/invite/{token}", err=str(e))
    resp = flash_redirect("/history", msg="You joined the team. Calculations saved here are shared with everyone in it.")
    set_cookie(resp, WS, str(ws))
    return resp
