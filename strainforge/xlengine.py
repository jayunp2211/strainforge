"""Small Excel formula engine with Excel semantics (blank cells, mixed-type
comparison, error propagation). Evaluates the calculation workbook's own
formulas so results match the spreadsheet."""
from __future__ import annotations

import math
import re


class Blank:
    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    def __repr__(self):
        return "BLANK"


BLANK = Blank()


class XErr:
    def __init__(self, code: str):
        self.code = code

    def __repr__(self):
        return self.code


VALUE, DIV0, NUM, NA, REF, NAME = (XErr(c) for c in ("#VALUE!", "#DIV/0!", "#NUM!", "#N/A", "#REF!", "#NAME?"))


def is_err(v) -> bool:
    return isinstance(v, XErr)


class Range:
    def __init__(self, rows):
        self.rows = rows


# ---------------- tokenizer / parser ----------------
_TOKEN_NUM = re.compile(r"(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")
_TOKEN_WORD = re.compile(r"[A-Za-z_$][A-Za-z0-9_.$]*")
_REF = re.compile(r"^\$?[A-Z]{1,3}\$?\d+$", re.I)


def tokenize(src: str):
    t, i, n = [], 0, len(src)
    while i < n:
        ch = src[i]
        if ch in " \n\t":
            i += 1
            continue
        if ch == '"':
            s, i = "", i + 1
            while i < n:
                if src[i] == '"':
                    if i + 1 < n and src[i + 1] == '"':
                        s += '"'
                        i += 2
                        continue
                    break
                s += src[i]
                i += 1
            i += 1
            t.append(("str", s))
            continue
        if ch == "'":
            s, i = "", i + 1
            while i < n:
                if src[i] == "'":
                    if i + 1 < n and src[i + 1] == "'":
                        s += "'"
                        i += 2
                        continue
                    break
                s += src[i]
                i += 1
            i += 2  # closing quote and '!'
            t.append(("sheet", s))
            continue
        if ch.isdigit() or ch == ".":
            m = _TOKEN_NUM.match(src, i)
            t.append(("num", float(m.group(0))))
            i = m.end()
            continue
        if ch.isalpha() or ch in "_$":
            m = _TOKEN_WORD.match(src, i)
            w = m.group(0)
            i = m.end()
            if i < n and src[i] == "!":
                t.append(("sheet", w))
                i += 1
            elif i < n and src[i] == "(":
                t.append(("fn", w.upper()))
                i += 1
            elif _REF.match(w):
                t.append(("ref", w.replace("$", "").upper()))
            elif w.upper() in ("TRUE", "FALSE"):
                t.append(("bool", w.upper() == "TRUE"))
            else:
                t.append(("name", w))
            continue
        two = src[i:i + 2]
        if two in ("<>", "<=", ">="):
            t.append(("op", two))
            i += 2
            continue
        if ch in "+-*/^&=<>(),:%":
            t.append(("op", ch))
            i += 1
            continue
        raise ValueError(f"Unexpected {ch!r} in {src}")
    return t


def parse(src: str):
    toks = tokenize(src)
    pos = [0]

    def peek_op(v):
        return pos[0] < len(toks) and toks[pos[0]] == ("op", v)

    def nxt():
        tok = toks[pos[0]]
        pos[0] += 1
        return tok

    def expr():
        left = cat()
        while pos[0] < len(toks) and toks[pos[0]][0] == "op" and toks[pos[0]][1] in ("=", "<>", "<", ">", "<=", ">="):
            o = nxt()[1]
            left = ("bin", o, left, cat())
        return left

    def cat():
        left = add()
        while peek_op("&"):
            nxt()
            left = ("bin", "&", left, add())
        return left

    def add():
        left = mul()
        while peek_op("+") or peek_op("-"):
            o = nxt()[1]
            left = ("bin", o, left, mul())
        return left

    def mul():
        left = pw()
        while peek_op("*") or peek_op("/"):
            o = nxt()[1]
            left = ("bin", o, left, pw())
        return left

    def pw():
        left = un()
        while peek_op("^"):
            nxt()
            left = ("bin", "^", left, un())
        return left

    def un():
        if peek_op("-"):
            nxt()
            return ("neg", un())
        if peek_op("+"):
            nxt()
            return un()
        return prim()

    def prim():
        k, v = nxt()
        if k in ("num", "str", "bool"):
            return ("lit", v)
        if k == "op" and v == "(":
            e = expr()
            nxt()
            return e
        if k == "fn":
            args = []
            if not peek_op(")"):
                while True:
                    if peek_op(","):
                        args.append(("lit", BLANK))
                    else:
                        args.append(expr())
                    if peek_op(","):
                        nxt()
                        continue
                    break
            nxt()
            return ("fn", v, args)
        sheet = None
        if k == "sheet":
            sheet = v
            k, v = nxt()
        if k == "ref":
            if peek_op(":"):
                nxt()
                _, b = nxt()
                return ("range", sheet, v, b)
            return ("ref", sheet, v)
        if k == "name":
            return ("name", v)
        raise ValueError(f"Unexpected token {k} {v} in {src}")

    e = expr()
    if pos[0] != len(toks):
        raise ValueError(f"Trailing tokens in {src}")
    return e


# ---------------- helpers ----------------
def col_num(c: str) -> int:
    n = 0
    for ch in c:
        n = n * 26 + ord(ch) - 64
    return n


def col_str(n: int) -> str:
    s = ""
    while n > 0:
        m = (n - 1) % 26
        s = chr(65 + m) + s
        n = (n - 1 - m) // 26
    return s


def split_ref(a: str):
    m = re.match(r"^([A-Z]+)(\d+)$", a)
    return col_num(m.group(1)), int(m.group(2))


def to_num(v):
    if is_err(v):
        return v
    if v is BLANK or v is None:
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        try:
            return float(s) if s else VALUE
        except ValueError:
            return VALUE
    return VALUE


def to_bool(v):
    if is_err(v):
        return v
    if v is BLANK:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        u = v.upper()
        if u == "TRUE":
            return True
        if u == "FALSE":
            return False
    return VALUE


def to_str(v) -> str:
    if v is BLANK:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        r = float(f"{v:.15g}")
        return str(int(r)) if r == int(r) else repr(r)
    return str(v)


def _rank(v):
    if isinstance(v, bool):
        return 2
    if isinstance(v, (int, float)):
        return 0
    return 1


def compare(a, b) -> int:
    if a is BLANK and b is BLANK:
        return 0
    if a is BLANK:
        a = "" if isinstance(b, str) else (False if isinstance(b, bool) else 0)
    if b is BLANK:
        b = "" if isinstance(a, str) else (False if isinstance(a, bool) else 0)
    ra, rb = _rank(a), _rank(b)
    if ra != rb:
        return -1 if ra < rb else 1
    if isinstance(a, str):
        a, b = a.lower(), b.lower()
    return -1 if a < b else (1 if a > b else 0)


def xpow(a, b):
    if a == 0 and b == 0:
        return NUM
    if a == 0 and b < 0:
        return DIV0
    if a < 0 and not float(b).is_integer():
        return NUM
    try:
        r = math.pow(a, b)
    except (OverflowError, ValueError):
        return NUM
    return r if math.isfinite(r) else NUM


class Workbook:
    def __init__(self, sheets: dict, names: dict | None = None):
        self.sheets = sheets
        self.names = names or {}
        self.ast: dict = {}
        self.cache: dict = {}
        self.overrides: dict = {}

    def set(self, sheet, addr, v):
        self.overrides[(sheet, addr)] = v
        self.cache = {}

    def clear_overrides(self):
        self.overrides = {}
        self.cache = {}

    def raw(self, sheet, addr):
        k = (sheet, addr)
        if k in self.overrides:
            return self.overrides[k]
        return self.sheets.get(sheet, {}).get(addr)

    def get(self, sheet, addr):
        k = (sheet, addr)
        if k in self.cache:
            return self.cache[k]
        self.cache[k] = REF  # cycle guard
        r = self.raw(sheet, addr)
        if r is None or r == "":
            v = BLANK
        elif isinstance(r, str) and r.startswith("="):
            key = (sheet, addr, r)
            a = self.ast.get(key)
            if a is None:
                a = parse(r[1:])
                self.ast[key] = a
            v = self.ev(a, sheet)
            if v is BLANK:
                v = 0.0
            if isinstance(v, Range):
                v = VALUE
        else:
            v = r
        self.cache[k] = v
        return v

    def range_vals(self, sheet, a, b):
        c1, r1 = split_ref(a)
        c2, r2 = split_ref(b)
        rows = []
        for r in range(min(r1, r2), max(r1, r2) + 1):
            rows.append([self.get(sheet, f"{col_str(c)}{r}") for c in range(min(c1, c2), max(c1, c2) + 1)])
        return Range(rows)

    def ev(self, n, sh):
        t = n[0]
        if t == "lit":
            return n[1]
        if t == "ref":
            return self.get(n[1] or sh, n[2])
        if t == "range":
            return self.range_vals(n[1] or sh, n[2], n[3])
        if t == "name":
            d = self.names.get(n[1]) or self.names.get(n[1].lower())
            if not d:
                return NAME
            return self.range_vals(*d)
        if t == "neg":
            v = to_num(self.ev(n[1], sh))
            return v if is_err(v) else -v
        if t == "bin":
            return self.bin(n[1], self.ev(n[2], sh), self.ev(n[3], sh))
        if t == "fn":
            return self.fn(n[1], n[2], sh)
        raise ValueError(t)

    def bin(self, o, a, b):
        if isinstance(a, Range):
            a = VALUE
        if isinstance(b, Range):
            b = VALUE
        if is_err(a):
            return a
        if is_err(b):
            return b
        if o == "&":
            return to_str(a) + to_str(b)
        if o in ("=", "<>", "<", ">", "<=", ">="):
            c = compare(a, b)
            return {"=": c == 0, "<>": c != 0, "<": c < 0, ">": c > 0, "<=": c <= 0, ">=": c >= 0}[o]
        x, y = to_num(a), to_num(b)
        if is_err(x):
            return x
        if is_err(y):
            return y
        if o == "+":
            return x + y
        if o == "-":
            return x - y
        if o == "*":
            return x * y
        if o == "/":
            return DIV0 if y == 0 else x / y
        if o == "^":
            return xpow(x, y)
        raise ValueError(o)

    def _num1(self, args, sh, f):
        v = self.ev(args[0], sh)
        if isinstance(v, Range):
            v = VALUE
        v = to_num(v)
        return v if is_err(v) else f(v)

    def fn(self, name, args, sh):
        if name == "IF":
            c = self.ev(args[0], sh)
            if isinstance(c, Range):
                c = VALUE
            c = to_bool(c)
            if is_err(c):
                return c
            if c:
                return self.ev(args[1], sh) if len(args) > 1 else True
            return self.ev(args[2], sh) if len(args) > 2 else False
        if name == "OR":
            anyv = False
            for a in args:
                v = self.ev(a, sh)
                if isinstance(v, Range):
                    for row in v.rows:
                        for x in row:
                            if is_err(x):
                                return x
                            if isinstance(x, (bool, int, float)):
                                anyv = anyv or bool(to_bool(x))
                    continue
                if v is BLANK:
                    continue
                v = to_bool(v)
                if is_err(v):
                    return v
                anyv = anyv or v
            return anyv
        if name == "PI":
            return math.pi
        if name == "LN":
            return self._num1(args, sh, lambda x: NUM if x <= 0 else math.log(x))
        if name == "SQRT":
            return self._num1(args, sh, lambda x: NUM if x < 0 else math.sqrt(x))
        if name == "SIN":
            return self._num1(args, sh, math.sin)
        if name == "TAN":
            return self._num1(args, sh, math.tan)
        if name == "RADIANS":
            return self._num1(args, sh, math.radians)
        if name == "ROUND":
            x = to_num(self.ev(args[0], sh))
            d = to_num(self.ev(args[1], sh))
            if is_err(x):
                return x
            if is_err(d):
                return d
            d = int(d)
            f = 10 ** d
            y = float(f"{abs(x) * f:.15g}")
            return math.copysign(math.floor(y + 0.5), x) / f if x != 0 else 0.0
        if name == "SUM":
            s = 0.0
            for a in args:
                v = self.ev(a, sh)
                if isinstance(v, Range):
                    for row in v.rows:
                        for x in row:
                            if is_err(x):
                                return x
                            if isinstance(x, (int, float)) and not isinstance(x, bool):
                                s += x
                else:
                    x = to_num(v)
                    if is_err(x):
                        return x
                    s += x
            return s
        if name == "VLOOKUP":
            key = self.ev(args[0], sh)
            tbl = self.ev(args[1], sh)
            col = to_num(self.ev(args[2], sh))
            if is_err(key):
                return key
            if key is BLANK:
                key = 0.0
            if not isinstance(tbl, Range):
                return NA
            if is_err(col):
                return col
            for row in tbl.rows:
                if row[0] is not BLANK and type(row[0]) is type(key) and compare(row[0], key) == 0:
                    idx = int(col) - 1
                    return row[idx] if idx < len(row) else REF
            return NA
        return NAME
