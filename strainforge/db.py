"""Postgres (Neon) access: schema, accounts, sessions and workspace data.

All permission checks live here, next to the queries, so every page and API
call goes through the same rules:
  * members of a workspace can read its calculations and materials;
  * members can save calculations (paid workspaces only; all are paid during early access);
  * the creator or an admin can delete a calculation;
  * only admins manage members, invites and materials.
"""
import hashlib
import hmac
import os
import secrets
import threading
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from . import config

SCHEMA_VERSION = 2
SCHEMA = """
create extension if not exists pgcrypto;
create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  full_name text not null default '',
  password_hash text not null,
  created_at timestamptz not null default now()
);
create unique index if not exists users_email_key on users (lower(email));
create table if not exists sessions (
  token_hash text primary key,
  user_id uuid not null references users(id) on delete cascade,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null
);
create index if not exists sessions_user on sessions(user_id);
create table if not exists workspaces (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  kind text not null check (kind in ('personal','team')),
  owner_id uuid not null references users(id) on delete cascade,
  plan text not null default 'early_access' check (plan in ('early_access','trial','personal','team','inactive')),
  subscription_status text,
  hidden_materials text[] not null default '{}',
  created_at timestamptz not null default now()
);
create table if not exists memberships (
  workspace_id uuid not null references workspaces(id) on delete cascade,
  user_id uuid not null references users(id) on delete cascade,
  role text not null check (role in ('admin','engineer')),
  created_at timestamptz not null default now(),
  primary key (workspace_id, user_id)
);
create index if not exists memberships_user on memberships(user_id);
create table if not exists invites (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  email text,
  role text not null default 'engineer' check (role in ('admin','engineer')),
  token text not null unique,
  created_by uuid references users(id) on delete set null,
  accepted_by uuid references users(id) on delete set null,
  accepted_at timestamptz,
  expires_at timestamptz not null default now() + interval '14 days',
  created_at timestamptz not null default now()
);
create table if not exists calculations (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  title text not null,
  process int not null,
  shape int not null,
  material text not null,
  inputs jsonb not null default '{}',
  summary jsonb not null default '{}',
  notes text not null default '',
  created_by uuid references users(id) on delete set null,
  updated_by uuid references users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists calculations_ws on calculations(workspace_id, updated_at desc);
create table if not exists calculation_versions (
  id bigserial primary key,
  calculation_id uuid not null references calculations(id) on delete cascade,
  title text not null,
  process int not null, shape int not null, material text not null,
  inputs jsonb not null, summary jsonb not null, notes text not null default '',
  edited_by uuid references users(id) on delete set null,
  created_at timestamptz not null default now()
);
create index if not exists versions_calc on calculation_versions(calculation_id, id desc);
create table if not exists materials (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  name text not null,
  c numeric not null check (c > 0),
  n numeric not null check (n >= 0 and n < 1),
  rm numeric,
  created_by uuid references users(id) on delete set null,
  created_at timestamptz not null default now(),
  unique (workspace_id, name)
);
create table if not exists reset_tokens (
  token_hash text primary key,
  user_id uuid not null references users(id) on delete cascade,
  created_by uuid references users(id) on delete set null,
  expires_at timestamptz not null,
  used_at timestamptz
);
create table if not exists login_attempts (
  email text not null,
  at timestamptz not null default now()
);
create index if not exists login_attempts_email on login_attempts(lower(email), at);
create table if not exists schema_version (v int primary key);
create table if not exists library_materials (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  c numeric not null check (c > 0),
  n numeric not null check (n >= 0 and n < 1),
  rm numeric,
  updated_by uuid references users(id) on delete set null,
  updated_at timestamptz not null default now()
);
create unique index if not exists library_materials_name on library_materials (lower(name));
"""

SESSION_DAYS = 30
CALC_COLS = ("c.id, c.workspace_id, c.title, c.process, c.shape, c.material, c.inputs, c.summary, c.notes, "
             "c.created_by, c.updated_by, c.created_at, c.updated_at, "
             "coalesce(nullif(cu.full_name,''), cu.email) as created_by_name, "
             "coalesce(nullif(uu.full_name,''), uu.email) as updated_by_name")
CALC_FROM = "calculations c left join users cu on cu.id = c.created_by left join users uu on uu.id = c.updated_by"


class Denied(Exception):
    """The signed-in person is not allowed to do this."""


class Conflict(Exception):
    def __init__(self, current):
        super().__init__("conflict")
        self.current = current


# ------------------------------------------------------------------ connection

_local = threading.local()
_schema_ready = False
_schema_lock = threading.Lock()


def _dsn():
    dsn = config.DATABASE_URL
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set")
    return dsn


def _connect():
    return psycopg.connect(_dsn(), autocommit=True, row_factory=dict_row, prepare_threshold=None, connect_timeout=10)


def conn():
    c = getattr(_local, "conn", None)
    if c is None or c.closed or c.broken:
        c = _local.conn = _connect()
    return c


def _run(fn):
    """Run fn(connection); reconnect once if the pooled connection went stale."""
    try:
        return fn(conn())
    except psycopg.OperationalError:
        _local.conn = None
        return fn(conn())


def q(sql, params=None):
    def go(c):
        with c.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else []
    return _run(go)


def q1(sql, params=None):
    rows = q(sql, params)
    return rows[0] if rows else None


@contextmanager
def tx():
    c = conn()
    try:
        with c.transaction():
            with c.cursor() as cur:
                yield cur
    except psycopg.OperationalError:
        _local.conn = None
        raise


def ensure_schema():
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        row = None
        try:
            row = q1("select max(v) as v from schema_version")
        except psycopg.errors.UndefinedTable:
            pass
        if not row or (row["v"] or 0) < SCHEMA_VERSION:
            with tx() as cur:
                cur.execute("select pg_advisory_xact_lock(424242)")
                cur.execute(SCHEMA)
                cur.execute("select count(*) as n from library_materials")
                if cur.fetchone()["n"] == 0:
                    from .calc import DEFAULT_MATERIALS
                    cur.executemany("insert into library_materials(name, c, n, rm) values (%s,%s,%s,%s) on conflict do nothing",
                                    [(m["name"], m["C"], m["n"], m.get("Rm")) for m in DEFAULT_MATERIALS])
                cur.execute("insert into schema_version(v) values (%s) on conflict do nothing", (SCHEMA_VERSION,))
        _schema_ready = True


# ------------------------------------------------------------------ passwords and tokens

def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${dk.hex()}"


def check_password(pw: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, dk = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(dk) // 2)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got.hex(), dk)


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


_DUMMY = None


# ------------------------------------------------------------------ accounts

def create_user(email: str, password: str, full_name: str, team_name: str = ""):
    email = email.strip()
    with tx() as cur:
        cur.execute("select 1 from users where lower(email) = lower(%s)", (email,))
        if cur.fetchone():
            raise ValueError("An account with this email already exists. Sign in instead.")
        cur.execute("insert into users(email, full_name, password_hash) values (%s,%s,%s) returning id",
                    (email, full_name or email.split("@")[0], hash_password(password)))
        uid = cur.fetchone()["id"]
        cur.execute("insert into workspaces(name, kind, owner_id) values ('Personal','personal',%s) returning id", (uid,))
        ws = cur.fetchone()["id"]
        cur.execute("insert into memberships values (%s,%s,'admin')", (ws, uid))
        if team_name:
            cur.execute("insert into workspaces(name, kind, owner_id) values (%s,'team',%s) returning id", (team_name, uid))
            ws = cur.fetchone()["id"]
            cur.execute("insert into memberships values (%s,%s,'admin')", (ws, uid))
    return uid, ws


def authenticate(email: str, password: str):
    """Returns the user id, or raises ValueError with a message for the person."""
    global _DUMMY
    email = email.strip()
    recent = q1("select count(*) as n from login_attempts where lower(email) = lower(%s) and at > now() - interval '15 minutes'",
                (email,))["n"]
    if recent >= 10:
        raise ValueError("Too many attempts. Wait 15 minutes and try again.")
    u = q1("select id, password_hash from users where lower(email) = lower(%s)", (email,))
    if not u:
        _DUMMY = _DUMMY or hash_password("x")
        check_password(password, _DUMMY)  # same timing whether or not the account exists
    if not u or not check_password(password, u["password_hash"]):
        q("insert into login_attempts(email) values (%s)", (email,))
        raise ValueError("Wrong email or password.")
    q("delete from login_attempts where lower(email) = lower(%s) or at < now() - interval '1 day'", (email,))
    return u["id"]


def new_session(uid) -> str:
    token = secrets.token_urlsafe(32)
    q("insert into sessions(token_hash, user_id, expires_at) values (%s,%s, now() + make_interval(days => %s))",
      (_h(token), uid, SESSION_DAYS))
    return token


def session_user(token: str | None):
    if not token or len(token) > 100:
        return None
    return q1("select u.id, u.email, u.full_name from sessions s join users u on u.id = s.user_id "
              "where s.token_hash = %s and s.expires_at > now()", (_h(token),))


def end_session(token: str | None):
    if token:
        q("delete from sessions where token_hash = %s", (_h(token),))


def set_name(uid, name):
    q("update users set full_name = %s where id = %s", (name, uid))


def change_password(uid, current: str, new: str):
    u = q1("select password_hash from users where id = %s", (uid,))
    if not u or not check_password(current, u["password_hash"]):
        raise ValueError("Your current password is not right.")
    set_password(uid, new)


def set_password(uid, new: str, keep_session: str | None = None):
    with tx() as cur:
        cur.execute("update users set password_hash = %s where id = %s", (hash_password(new), uid))
        cur.execute("delete from sessions where user_id = %s and token_hash <> %s", (uid, _h(keep_session or "")))


def create_reset_link(admin_id, ws_id, member_id) -> str:
    _need_admin(admin_id, ws_id)
    if not q1("select 1 from memberships where workspace_id = %s and user_id = %s", (ws_id, member_id)):
        raise Denied("That person is not in this workspace.")
    token = secrets.token_urlsafe(24)
    q("insert into reset_tokens(token_hash, user_id, created_by, expires_at) values (%s,%s,%s, now() + interval '24 hours')",
      (_h(token), member_id, admin_id))
    return token


def reset_target(token: str):
    return q1("select r.user_id, u.email from reset_tokens r join users u on u.id = r.user_id "
              "where r.token_hash = %s and r.used_at is null and r.expires_at > now()", (_h(token),))


def use_reset(token: str, new_password: str):
    t = reset_target(token)
    if not t:
        raise ValueError("This reset link has expired or was already used. Ask your admin for a new one.")
    with tx() as cur:
        cur.execute("update reset_tokens set used_at = now() where token_hash = %s", (_h(token),))
        cur.execute("update users set password_hash = %s where id = %s", (hash_password(new_password), t["user_id"]))
        cur.execute("delete from sessions where user_id = %s", (t["user_id"],))
    return t["user_id"]


# ------------------------------------------------------------------ workspaces

def workspaces_for(uid):
    return q("select w.id, w.name, w.kind, w.plan, w.owner_id, w.hidden_materials, m.role from memberships m "
             "join workspaces w on w.id = m.workspace_id where m.user_id = %s "
             "order by (w.kind <> 'personal'), lower(w.name)", (uid,))


def _role(uid, ws_id):
    r = q1("select m.role, w.plan, w.kind, w.owner_id from memberships m join workspaces w on w.id = m.workspace_id "
           "where m.workspace_id = %s and m.user_id = %s", (ws_id, uid))
    return r


def _need_member(uid, ws_id):
    r = _role(uid, ws_id)
    if not r:
        raise Denied("You are not a member of this workspace.")
    return r


def _need_admin(uid, ws_id):
    r = _need_member(uid, ws_id)
    if r["role"] != "admin":
        raise Denied("Only an admin can do this.")
    return r


def _need_paid(r):
    if r["plan"] not in ("early_access", "personal", "team", "trial"):
        raise Denied("This workspace needs an active plan.")


def create_team(uid, name):
    with tx() as cur:
        cur.execute("insert into workspaces(name, kind, owner_id) values (%s,'team',%s) returning id", (name, uid))
        ws = cur.fetchone()["id"]
        cur.execute("insert into memberships values (%s,%s,'admin')", (ws, uid))
    return ws


def rename_workspace(uid, ws_id, name):
    _need_admin(uid, ws_id)
    q("update workspaces set name = %s where id = %s", (name, ws_id))


def members(uid, ws_id):
    _need_member(uid, ws_id)
    return q("select m.user_id, m.role, m.created_at, u.full_name as name, u.email, (w.owner_id = m.user_id) as owner "
             "from memberships m join users u on u.id = m.user_id join workspaces w on w.id = m.workspace_id "
             "where m.workspace_id = %s order by m.created_at", (ws_id,))


def set_role(uid, ws_id, member_id, role):
    r = _need_admin(uid, ws_id)
    if role not in ("admin", "engineer"):
        raise ValueError("Unknown role")
    if str(member_id) == str(r["owner_id"]) and role != "admin":
        raise Denied("The workspace owner always stays an admin.")
    q("update memberships set role = %s where workspace_id = %s and user_id = %s", (role, ws_id, member_id))


def remove_member(uid, ws_id, member_id):
    r = _need_member(uid, ws_id)
    if str(member_id) != str(uid) and r["role"] != "admin":
        raise Denied("Only an admin can remove people.")
    if str(member_id) == str(r["owner_id"]):
        raise Denied("The workspace owner can't be removed." if str(member_id) != str(uid) else
                     "You own this workspace, so you can't leave it.")
    q("delete from memberships where workspace_id = %s and user_id = %s", (ws_id, member_id))


def create_invite(uid, ws_id, role, email):
    r = _need_admin(uid, ws_id)
    _need_paid(r)
    if r["kind"] != "team":
        raise Denied("Invites are for team workspaces. Create a team first.")
    token = secrets.token_hex(20)
    q("insert into invites(workspace_id, email, role, token, created_by) values (%s,%s,%s,%s,%s)",
      (ws_id, email or None, "admin" if role == "admin" else "engineer", token, uid))
    return token


def invites(uid, ws_id):
    r = _need_member(uid, ws_id)
    if r["role"] != "admin":
        return []
    return q("select id, email, role, token, expires_at, created_at from invites where workspace_id = %s "
             "and accepted_at is null and expires_at > now() order by created_at desc", (ws_id,))


def revoke_invite(uid, ws_id, invite_id):
    _need_admin(uid, ws_id)
    q("delete from invites where id = %s and workspace_id = %s", (invite_id, ws_id))


def invite_info(token):
    return q1("select w.name as workspace_name, i.role, i.workspace_id from invites i join workspaces w on w.id = i.workspace_id "
              "where i.token = %s and i.accepted_at is null and i.expires_at > now()", (token,))


def accept_invite(uid, token):
    with tx() as cur:
        cur.execute("select * from invites where token = %s and accepted_at is null and expires_at > now() for update", (token,))
        inv = cur.fetchone()
        if not inv:
            raise ValueError("This invite link is not valid any more. Ask your admin for a new one.")
        cur.execute("insert into memberships(workspace_id, user_id, role) values (%s,%s,%s) on conflict do nothing",
                    (inv["workspace_id"], uid, inv["role"]))
        cur.execute("update invites set accepted_by = %s, accepted_at = now() where id = %s", (uid, inv["id"]))
    return inv["workspace_id"]


# ------------------------------------------------------------------ calculations

def list_calcs(uid, ws_id, term="", process=0, mine=False):
    _need_member(uid, ws_id)
    sql = (f"select {CALC_COLS} from {CALC_FROM} where c.workspace_id = %s")
    args = [ws_id]
    if term:
        sql += " and (c.title ilike %s or c.material ilike %s or c.notes ilike %s)"
        like = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        args += [like, like, like]
    if process:
        sql += " and c.process = %s"
        args.append(process)
    if mine:
        sql += " and c.created_by = %s"
        args.append(uid)
    return q(sql + " order by c.updated_at desc limit 300", args)


def get_calc(uid, cid):
    row = q1(f"select {CALC_COLS} from {CALC_FROM} where c.id = %s", (cid,))
    if not row or not _role(uid, row["workspace_id"]):
        return None
    return row


def _version(cur, cid, row, uid):
    cur.execute("insert into calculation_versions(calculation_id, title, process, shape, material, inputs, summary, notes, edited_by) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (cid, row["title"], row["process"], row["shape"], row["material"], Jsonb(row["inputs"]),
                 Jsonb(row["summary"]), row["notes"], uid))


def create_calc(uid, ws_id, row):
    _need_paid(_need_member(uid, ws_id))
    with tx() as cur:
        cur.execute("insert into calculations(workspace_id, title, process, shape, material, inputs, summary, notes, created_by, updated_by) "
                    "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id",
                    (ws_id, row["title"], row["process"], row["shape"], row["material"], Jsonb(row["inputs"]),
                     Jsonb(row["summary"]), row["notes"], uid, uid))
        cid = cur.fetchone()["id"]
        _version(cur, cid, row, uid)
    return get_calc(uid, cid)


def update_calc(uid, cid, row, expected=None):
    cur_row = get_calc(uid, cid)
    if not cur_row:
        raise Denied("This calculation no longer exists or you can't open it.")
    _need_paid(_need_member(uid, cur_row["workspace_id"]))
    with tx() as cur:
        sql = ("update calculations set title=%s, process=%s, shape=%s, material=%s, inputs=%s, summary=%s, notes=%s, "
               "updated_by=%s, updated_at=now() where id=%s")
        args = [row["title"], row["process"], row["shape"], row["material"], Jsonb(row["inputs"]), Jsonb(row["summary"]),
                row["notes"], uid, cid]
        if expected:
            sql += " and date_trunc('milliseconds', updated_at) = date_trunc('milliseconds', %s::timestamptz)"
            args.append(expected)
        cur.execute(sql + " returning id", args)
        if not cur.fetchone():
            raise Conflict(None)
        _version(cur, cid, row, uid)
    return get_calc(uid, cid)


def delete_calc(uid, cid):
    row = get_calc(uid, cid)
    if not row:
        raise Denied("Not found.")
    r = _role(uid, row["workspace_id"])
    if r["role"] != "admin" and str(row["created_by"]) != str(uid):
        raise Denied("Only an admin or the person who created it can delete this.")
    q("delete from calculations where id = %s", (cid,))


def versions(uid, cid):
    if not get_calc(uid, cid):
        raise Denied("Not found.")
    return q("select v.id, v.title, v.process, v.shape, v.material, v.inputs, v.summary, v.notes, v.created_at, "
             "coalesce(nullif(u.full_name,''), u.email) as edited_by_name from calculation_versions v "
             "left join users u on u.id = v.edited_by where v.calculation_id = %s order by v.id desc limit 50", (cid,))


# ------------------------------------------------------------------ materials

def custom_materials(uid, ws_id):
    _need_member(uid, ws_id)
    return q("select id, name, c, n, rm, created_at from materials where workspace_id = %s order by lower(name)", (ws_id,))


def add_material(uid, ws_id, name, c, n, rm):
    _need_paid(_need_admin(uid, ws_id))
    try:
        q("insert into materials(workspace_id, name, c, n, rm, created_by) values (%s,%s,%s,%s,%s,%s)",
          (ws_id, name, c, n, rm, uid))
    except psycopg.errors.UniqueViolation:
        raise ValueError("A material with that name already exists.")


def delete_material(uid, ws_id, mid):
    _need_admin(uid, ws_id)
    q("delete from materials where id = %s and workspace_id = %s", (mid, ws_id))


def set_hidden(uid, ws_id, hidden):
    _need_paid(_need_admin(uid, ws_id))
    q("update workspaces set hidden_materials = %s where id = %s", (sorted(hidden), ws_id))


# ------------------------------------------------------------------ standard material library (site-wide)

_lib_cache = {"at": 0.0, "rows": None}
LIB_TTL = 30


def library(fresh=False):
    """The standard library everyone sees, as [{id, name, C, n, Rm}]."""
    import time
    if not fresh and _lib_cache["rows"] is not None and time.time() - _lib_cache["at"] < LIB_TTL:
        return _lib_cache["rows"]
    ensure_schema()
    rows = [{"id": str(r["id"]), "name": r["name"], "C": float(r["c"]), "n": float(r["n"]),
             "Rm": float(r["rm"]) if r["rm"] is not None else None}
            for r in q("select id, name, c, n, rm from library_materials order by lower(name)")]
    _lib_cache.update(at=time.time(), rows=rows)
    return rows


def _lib_changed():
    _lib_cache.update(at=0.0, rows=None)


def lib_add(uid, name, c, n, rm):
    try:
        q("insert into library_materials(name, c, n, rm, updated_by) values (%s,%s,%s,%s,%s)", (name, c, n, rm, uid))
    except psycopg.errors.UniqueViolation:
        raise ValueError(f"{name} is already in the standard library.")
    _lib_changed()


def lib_update(uid, mid, name, c, n, rm):
    try:
        rows = q("update library_materials set name=%s, c=%s, n=%s, rm=%s, updated_by=%s, updated_at=now() "
                 "where id=%s returning id", (name, c, n, rm, uid, mid))
    except psycopg.errors.UniqueViolation:
        raise ValueError(f"Another material is already called {name}.")
    _lib_changed()
    if not rows:
        raise ValueError("That material no longer exists.")


def lib_delete(mid):
    q("delete from library_materials where id = %s", (mid,))
    _lib_changed()
