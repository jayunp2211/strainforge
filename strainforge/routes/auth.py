"""Sign in, sign up, password resets and the account page."""
from urllib.parse import quote
import re

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import db
from .common import (
    SID, Session, WS, flash_redirect, load_session, need_login, page, safe_next, sign_in_response,
)

router = APIRouter()


# ------------------------------------------------------------------ auth

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = ""):
    s = load_session(request)
    if s.signed_in:
        return RedirectResponse(safe_next(next), 303)
    return page(request, "auth.html", s, mode="login", next=next)


@router.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("")):
    db.ensure_schema()
    try:
        uid = db.authenticate(email[:200], password[:200])
    except ValueError as e:
        return page(request, "auth.html", Session(), mode="login", next=next, err=str(e), email=email, status_code=400)
    return sign_in_response(safe_next(next), uid)


@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request, next: str = ""):
    s = load_session(request)
    if s.signed_in:
        return RedirectResponse(safe_next(next), 303)
    return page(request, "auth.html", s, mode="signup", next=next)


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.post("/signup")
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


@router.post("/logout")
def logout(request: Request):
    db.end_session(request.cookies.get(SID))
    resp = RedirectResponse("/", 303)
    resp.delete_cookie(SID, path="/")
    resp.delete_cookie(WS, path="/")
    return resp


@router.get("/forgot", response_class=HTMLResponse)
def forgot_page(request: Request):
    return page(request, "auth.html", load_session(request), mode="forgot")


@router.get("/reset/{token}", response_class=HTMLResponse)
def reset_page(request: Request, token: str):
    db.ensure_schema()
    t = db.reset_target(token)
    return page(request, "auth.html", Session(), mode="reset", token=token, target=t)


@router.post("/reset/{token}")
def reset(request: Request, token: str, password: str = Form(...)):
    if len(password) < 8 or len(password) > 200:
        return page(request, "auth.html", Session(), mode="reset", token=token, target=db.reset_target(token),
                    err="Use at least 8 characters.", status_code=400)
    try:
        uid = db.use_reset(token, password)
    except ValueError as e:
        return page(request, "auth.html", Session(), mode="reset", token=token, target=None, err=str(e), status_code=400)
    return sign_in_response("/history?msg=" + quote("Your password is updated."), uid)


@router.get("/account", response_class=HTMLResponse)
def account(request: Request):
    s = load_session(request)
    if not s.signed_in:
        return need_login(request)
    return page(request, "account.html", s)


@router.post("/account/name")
def account_name(request: Request, full_name: str = Form(...)):
    s = load_session(request)
    if not s.signed_in:
        return need_login(request)
    db.set_name(s.user_id, full_name.strip()[:80])
    return flash_redirect("/account", msg="Name updated.")


@router.post("/account/password")
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
