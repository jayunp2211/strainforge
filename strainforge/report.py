"""Calculation reports: one report model, written out as a PDF (fpdf2) or an Excel workbook (openpyxl).

The model is built on the server from the inputs (the page's current inputs, or a saved result),
so a report reads the same whether it comes from the calculator, a tool page or the history page.
Values are converted to the viewer's units here, the same way static/units.js does in the browser.
"""
from __future__ import annotations

import io
import math
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import builtin
from .drawings import SVG_CSS

HERE = Path(__file__).parent
FONTS = HERE / "fonts"
DISCLAIMER = "Results are estimates for tool design. Confirm critical steps with simulation or trials."
MAX_BATCH = 25

# ------------------------------------------------------------------ units (mirrors static/units.js)
IMP = {
    "mm": ("in", 1 / 25.4),
    "mm²": ("in²", 1 / 645.16),
    "mm³": ("in³", 1 / 16387.064),
    "N/mm²": ("ksi", 0.1450377377),
    "Nmm/mm³": ("in·kip/in³", 0.1450377377),
    "kN": ("tonf", 1 / 8.896443230521),
    "N": ("lbf", 1 / 4.4482216152605),
    "N/mm": ("lbf/in", 25.4 / 4.4482216152605),
    "kJ": ("ft·lbf", 737.5621493),
}
_TEXT_QTY = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)\s?(mm³|mm²|mm|kN|kJ|N/mm²|N/mm|N)(?![\w²³/])")


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def auto_decimals(v, big=1) -> int:
    a = abs(v)
    if v == 0:
        return 0
    return big if a >= 1000 else 2 if a >= 100 else 3 if a >= 1 else 4


def fmt(v, d=None) -> str:
    if not is_num(v):
        return "—"
    if d is None:
        d = auto_decimals(v)
    return f"{v:,.{d}f}"


class Units:
    def __init__(self, system: str = "metric"):
        self.system = "imperial" if system == "imperial" else "metric"

    @property
    def imperial(self):
        return self.system == "imperial"

    def conv(self, u):
        return IMP.get(u or "") if self.imperial else None

    def unit(self, u):
        c = self.conv(u)
        return c[0] if c else (u or "")

    def out(self, v, u):
        c = self.conv(u)
        return v * c[1] if c and is_num(v) else v

    def text(self, s):
        if not self.imperial or not isinstance(s, str):
            return s if isinstance(s, str) else ("" if s is None else str(s))

        def rep(m):
            v = self.out(float(m.group(1).replace(",", "")), m.group(2))
            return f"{fmt(v)} {self.unit(m.group(2))}"
        return _TEXT_QTY.sub(rep, s)

    @property
    def label(self):
        return "Imperial (in, lbf, ksi)" if self.imperial else "Metric (mm, kN, N/mm²)"


def cell(text="", num=None, d=None):
    """A table cell: the text shown in the PDF, plus the number and decimals Excel stores."""
    return {"t": "" if text is None else str(text), "n": num if is_num(num) else None, "d": d}


def qty(U: Units, v, u, d=None, keep_d=False):
    """A quantity in the viewer's units. Converted values pick their own decimals (as on the page),
    unless keep_d asks for at least the given decimals (the calculator's KPI rule)."""
    if not is_num(v):
        if isinstance(v, dict) and v.get("error"):
            return cell(v["error"])
        return cell("—")
    x = U.out(v, u)
    if U.conv(u):
        d = max(d, 1) if (keep_d and d is not None) else None
    if d is None:
        d = auto_decimals(x)
    return cell(fmt(x, d), x, d)


def _typed(v, U, u):
    """An input as typed: up to 6 significant digits, no padding."""
    x = U.out(v, u)
    if U.conv(u):
        x = float(f"{x:.6g}")
    if float(x).is_integer() and abs(x) < 1e15:
        return cell(f"{int(x):,}", x, 0)
    s = f"{x:,.6f}".rstrip("0").rstrip(".")
    d = len(s.split(".")[1]) if "." in s else 0
    return cell(s, x, d)


def section(title, columns, rows, kind="side"):
    return {"title": title, "columns": columns, "rows": rows, "kind": kind}


# ------------------------------------------------------------------ report models

def _status_from(checks, warnings, ok_text, empty_text=None):
    if warnings:
        return {"state": "bad", "text": "; ".join(warnings)}
    if empty_text:
        return {"state": "na", "text": empty_text}
    if any(c["state"] == "bad" for c in checks):
        return {"state": "bad", "text": "A design check fails"}
    if any(c["state"] == "warn" for c in checks):
        return {"state": "warn", "text": "Within limits, see the notes under the checks"}
    return {"state": "ok", "text": ok_text}


def _checks(U, checks):
    return [{"title": c.get("title", ""), "desc": U.text(c.get("desc", "")), "value": U.text(str(c.get("value", "—"))),
             "limit": U.text(str(c.get("limit", ""))), "state": c.get("state", "na")} for c in checks]


def tool_model(bt: dict, values: dict, U: Units) -> dict:
    res = bt["calculate"](values)
    auto = res.get("auto") or {}

    def unit_of(i):
        ub = i.get("unitBy")
        if ub:
            return ub["map"].get(values.get(ub["key"]), "")
        return i.get("unit", "")

    rows = []
    for g in bt["groups"]:
        items = [i for i in bt["inputs"] if i["group"] == g["key"]]
        if not items:
            continue
        rows.append({"group": g["title"]})
        for i in items:
            v, u = values.get(i["key"]), unit_of(i)
            if i.get("kind") == "select":
                opt = next((o for o in i["options"] if str(o["value"] if isinstance(o, dict) else o) == str(v)), None)
                c = cell(opt["label"] if isinstance(opt, dict) else (opt if opt is not None else (v or "—")))
            elif i.get("kind") == "preset":
                try:
                    c = cell(i["options"][int(v)]["label"])
                except (TypeError, ValueError, IndexError, KeyError):
                    c = cell("Your own size")
                u = ""
            elif is_num(v):
                c = _typed(v, U, u)
            elif i.get("placeholder"):
                a = auto.get(i["key"])
                c = cell("auto " + fmt(U.out(a, u)), U.out(a, u), auto_decimals(U.out(a, u))) if is_num(a) else cell("auto")
            else:
                c = cell("—")
            rows.append([cell(i["label"]), c, cell(U.unit(u))])

    kpis = []
    for k in res.get("kpis", []):
        if is_num(k.get("value")):
            d = k.get("decimals")
            if d is None:
                d = 0 if abs(k["value"]) >= 1000 else 1 if abs(k["value"]) >= 100 else 2
            c = qty(U, k["value"], k.get("unit", ""), d)
            unit = U.unit(k.get("unit", ""))
        else:
            c, unit = cell(k.get("text") or "—"), ""
        kpis.append({"label": k["label"], "value": c, "unit": unit, "sub": U.text(k.get("sub", "")), "main": bool(k.get("main"))})

    checks = _checks(U, res.get("checks", []))
    status = _status_from(checks, [U.text(w) for w in res.get("warnings", [])], "All design checks pass",
                          None if kpis else "Results appear once the dimensions are filled in")

    sections = [section("Inputs", ["Input", "Value", "Unit"], rows)]
    vals = []
    for v in res.get("values", []):
        d = v.get("decimals")
        if d is None:
            d = 0 if (isinstance(v.get("value"), int) or (is_num(v.get("value")) and float(v["value"]).is_integer() and not v.get("unit"))) and not v.get("unit") else 3
        lab = v["label"] + (f" ({v['note']})" if v.get("note") else "")
        r = [cell(lab), qty(U, v.get("value"), v.get("unit", ""), d), cell(U.unit(v.get("unit", "")))]
        vals.append({"key": True, "cells": r} if v.get("key") else r)
    if vals:
        sections.append(section("Design values", ["Quantity", "Value", "Unit"], vals))
    for t in res.get("tables", []) or []:
        cols = [c["label"] + (f" ({U.unit(c['unit'])})" if c.get("unit") else "") for c in t["columns"]]
        trows = []
        for r in t["rows"]:
            out = []
            for n, v in enumerate(r):
                col = t["columns"][n] if n < len(t["columns"]) else {}
                out.append(cell(v) if n == 0 or col.get("text") else qty(U, v, col.get("unit", ""), col.get("decimals")))
            trows.append(out)
        sec = section(t["title"], cols, trows, kind="wide")
        sec["align"] = ["L" if n == 0 or c.get("text") else "R" for n, c in enumerate(t["columns"])]
        sec["sub"] = t.get("sub", "")
        sec["foot"] = [U.text(f) for f in t.get("foot", []) or []]
        sections.append(sec)
    steps = []
    for d in res.get("steps", []):
        if d.get("group"):
            steps.append({"group": d["group"]})
        else:
            r = [cell(d["label"]), qty(U, d.get("value"), d.get("unit", "")), cell(U.unit(d.get("unit", "")))]
            steps.append({"key": True, "cells": r} if d.get("key") else r)
    if steps:
        sections.append(section("Calculation steps", ["Quantity", "Value", "Unit"], steps, kind="steps"))

    eqs = list(res.get("equations", []))
    if U.imperial:
        eqs.append("The equations work in mm, N/mm² and kN. Inputs are converted to metric before calculating "
                   "and results are converted back for display.")
    figs = [{"svg": svg, "caption": (bt["figures"][i] if i < len(bt["figures"]) else "")}
            for i, svg in enumerate(res.get("figures", []) or [])]
    first = next((k for k in res.get("kpis", []) if k.get("main")), (res.get("kpis") or [None])[0])
    return {"kind": bt["title"], "subtitle": bt["title"], "kpis": kpis, "checks": checks, "status": status,
            "sections": sections, "equations": eqs, "figures": figs, "units": U.label,
            "headline": _headline(kpis), "_first": first}


def calc_model(process, shape, material, inputs: dict, custom, U: Units) -> dict:
    from .calc import PROCESSES, SHAPE_NAMES  # noqa: F401  (imported for clarity of the source of names)
    from .routes.common import PROC_DRAW, SHAPE_DRAW, run_calc

    inputs = dict(inputs or {})
    custom = custom or inputs.pop("_material", None)
    inputs.pop("_material", None)
    res, props, clean = run_calc(int(process), int(shape), str(material), inputs, custom)
    r = res["results"]
    setup = [[cell("Process"), cell(res["processName"]), cell("")],
             [cell("Shape"), cell(res["shapeName"]), cell("")],
             [cell("Material"), cell(res["material"]), cell("")]]
    if props:
        setup.append([cell("Material constant C"), qty(U, props.get("C"), "N/mm²", 0), cell(U.unit("N/mm²"))])
    setup.append([cell("Flow stress kf"), qty(U, res.get("kf"), "N/mm²", 0), cell(U.unit("N/mm²"))])
    setup.append([cell("Work hardening n"), qty(U, res.get("n"), "", 3), cell("")])
    rows = []
    for x in res["inputs"]:
        v = clean.get(x["cell"])
        if x.get("kind") == "select":
            c = cell(v or "Not chosen")
        elif is_num(v):
            c = _typed(v, U, x["unit"])
        else:
            c = cell("auto" if x["cell"] in ("C47", "C48") else "—")
        rows.append([cell(x["label"]), c, cell(U.unit(x["unit"]))])
    for x in res["auto"]:
        rows.append([cell(x["label"] + " (automatic)"), qty(U, x.get("value"), x.get("unit", "")), cell(U.unit(x.get("unit", "")))])

    def kpi(label, v, u, sub, main=False):
        if is_num(v):
            x = U.out(v, u)
            d = 1 if (U.conv(u) and abs(x) >= 100) else None
            c = qty(U, v, u, d, keep_d=True)
            return {"label": label, "value": c, "unit": U.unit(u) if u else "", "sub": sub, "main": main}
        return {"label": label, "value": cell("—"), "unit": "", "sub": sub, "main": main}
    p = res["process"]
    kpis = [kpi("Load F", r["F"], "kN", "Press force for this step", True),
            kpi("Energy W", r["W"], "kJ", "Not calculated for cut off" if p == 1 else "Forming work"),
            kpi("Deformation grade φ", r["phi"], "", r["phiNote"]),
            kpi(r["checkLabel"], r["check"], r["checkUnit"], r["checkNote"])]
    checks = _checks(U, res["checks"])
    empty = None if (is_num(r["F"]) and r["F"] != 0) else "Enter the dimensions to get a load"
    status = _status_from(checks, res["warnings"], "All tooling checks pass", empty)
    steps = []
    for d in res["detail"]:
        if d.get("group"):
            steps.append({"group": d["group"]})
        else:
            c = [cell(d["label"]), qty(U, d.get("value"), d.get("unit", "")), cell(U.unit(d.get("unit", "")))]
            steps.append({"key": True, "cells": c} if d.get("key") else c)
    sections = [section("Setup", ["Item", "Value", "Unit"], setup), section("Inputs", ["Input", "Value", "Unit"], rows)]
    if steps:
        sections.append(section("Calculation steps", ["Quantity", "Value", "Unit"], steps, kind="steps"))
    eqs = list(res["equations"])
    if U.imperial:
        eqs.append("The equations work in mm, N/mm², kN and kJ. Inputs are converted to metric before calculating "
                   "and results are converted back for display.")
    figs = [{"svg": PROC_DRAW[p], "caption": "Tooling"}]
    if SHAPE_DRAW.get(res["shape"]):
        figs.append({"svg": SHAPE_DRAW[res["shape"]], "caption": "Part: before and after"})
    return {"kind": "Force calculation", "subtitle": f"{res['processName']} · {res['shapeName']} · {res['material']}",
            "kpis": kpis, "checks": checks, "status": status, "sections": sections, "equations": eqs,
            "figures": figs, "units": U.label, "headline": _headline(kpis)}


def _headline(kpis):
    k = next((k for k in kpis if k["main"]), kpis[0] if kpis else None)
    if not k:
        return ""
    return f"{k['label']}: {k['value']['t']} {k['unit']}".strip()


def model_from_source(src: dict, U: Units) -> dict:
    """Build a model from what a page sends: {kind: 'calc'|'tool', ...}."""
    if not isinstance(src, dict):
        raise ValueError("Nothing to report")
    if src.get("kind") == "tool":
        bt = builtin.get(str(src.get("tool") or ""))
        if not bt:
            raise ValueError("Unknown tool")
        values = src.get("values")
        if not isinstance(values, dict):
            raise ValueError("Send the inputs as values")
        keys = {i["key"] for i in bt["inputs"]}
        values = {k: (v[:80] if isinstance(v, str) else v) for k, v in values.items()
                  if k in keys and (v is None or isinstance(v, (int, float, str)))}
        return tool_model(bt, values, U)
    return calc_model(src.get("process", 6), src.get("shape", 11), str(src.get("material") or "CuZr")[:80],
                      src.get("inputs") if isinstance(src.get("inputs"), dict) else {}, src.get("custom"), U)


def model_from_saved(row: dict, U: Units) -> dict:
    if row.get("tool"):
        bt = builtin.get(row["tool"])
        if not bt:
            raise ValueError("Unknown tool")
        return tool_model(bt, dict(bt["example"], **(row.get("inputs") or {})), U)
    return calc_model(row["process"], row["shape"], row["material"], row.get("inputs") or {}, None, U)


def finish(model: dict, title: str, notes: str, meta: list, date: str) -> dict:
    model["title"] = (title or "").strip()[:120] or f"Untitled {model['kind'].lower()}"
    model["notes"] = (notes or "").strip()[:4000]
    model["date"] = date
    model["meta"] = [(k, v) for k, v in meta if v] + [("Units", model["units"])]
    return model


def today_label(date: str | None = None) -> str:
    if isinstance(date, str) and 4 <= len(date.strip()) <= 40 and re.fullmatch(r"[\w ,./-]+", date.strip()):
        return date.strip()
    d = datetime.now(timezone.utc)
    return f"{d.day} {d:%B %Y}"


def filename(title: str, ext: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "", title or "").strip().replace(" ", "-")[:60].strip("-.") or "strainforge-report"
    return f"{stem}-{datetime.now(timezone.utc):%Y-%m-%d}.{ext}"


# ------------------------------------------------------------------ drawings for the PDF

LIGHT = {"--d-ink": "#1d2731", "--d-muted": "#6b7785", "--d-dim": "#0b6e8a", "--d-accent": "#c2410c", "--d-wp": "#dfe7ee",
         "--d-wp2": "#b9d6e2", "--d-tool": "#f3f5f7", "--d-tool2": "#eef1f4", "--d-hatch": "#9aa6b2", "--paper": "#ffffff",
         "--panel": "#ffffff", "--line": "#e2e7ec", "--accent-soft": "#e4f2f6", "--chart-line": "#0b7393",
         "--muted": "#5d6b79", "--ink": "#0f1b27"}
_RULES: dict[str, str] = {}
for _sel, _body in re.findall(r"([^{}]+)\{([^{}]*)\}", SVG_CSS):
    for _s in _sel.split(","):
        _m = re.fullmatch(r"\s*\.dwg \.([\w-]+)\s*", _s)
        if _m:
            _RULES[_m.group(1)] = _body


def _vars(s: str) -> str:
    s = re.sub(r"var\((--[\w-]+)[^)]*\)", lambda m: LIGHT.get(m.group(1), "#5d6b79"), s)
    return s.replace("url(#hatch2)", "#dfe5eb").replace("url(#hatch)", "#e8ecf0")


def _decls(body: str) -> dict:
    out = {}
    for decl in _vars(body).split(";"):
        if ":" not in decl:
            continue
        k, v = (x.strip() for x in decl.split(":", 1))
        if k == "font":
            m = re.match(r"(\d+)\s+([\d.]+)px", v)
            if m:
                out["font-weight"] = "bold" if int(m.group(1)) >= 600 else "normal"
                out["font-size"] = m.group(2)
            out["font-family"] = "Sans"
        elif k in ("opacity",):
            out["stroke-opacity"] = v
        else:
            out[k] = v
    return out


def svg_for_pdf(svg: str, U: Units) -> str:
    """The page's drawings use CSS classes and variables; the PDF writer needs plain attributes."""
    def cls(m):
        attrs = {}
        for c in m.group(1).split():
            attrs.update(_decls(_RULES.get(c, "")))
        return " ".join(f'{k}="{v}"' for k, v in attrs.items())

    def styl(m):
        return " ".join(f'{k}="{v}"' for k, v in _decls(m.group(1)).items())

    def text_qty(m):
        attrs, body = m.group(1), m.group(2)
        q = re.search(r'data-qty="([^"]+)"', attrs)
        u = re.search(r'data-unit="([^"]*)"', attrs)
        if q and u and U.conv(u.group(1)):
            try:
                body = fmt(U.out(float(q.group(1)), u.group(1)))
            except ValueError:
                pass
        return f"<text{attrs}>{body}</text>"
    svg = re.sub(r"<title>.*?</title>", "", svg, flags=re.S)
    svg = re.sub(r"<text([^>]*)>([^<]*)</text>", text_qty, svg)
    svg = re.sub(r'\sdata-[\w-]+="[^"]*"', "", svg)
    svg = re.sub(r'\s(role|aria-label|tabindex)="[^"]*"', "", svg)
    svg = re.sub(r'style="([^"]*)"', styl, svg)
    svg = re.sub(r'class="([^"]*)"', cls, svg)
    svg = _vars(svg)
    if "font-family" not in svg.split(">", 1)[0]:
        svg = svg.replace("<svg ", '<svg font-family="Sans" font-size="11" ', 1)
    return svg


def _viewbox(svg: str):
    m = re.search(r'viewBox="\s*[\d.-]+\s+[\d.-]+\s+([\d.]+)\s+([\d.]+)', svg)
    return (float(m.group(1)), float(m.group(2))) if m else (440.0, 360.0)


# ------------------------------------------------------------------ PDF

INK, MUTED, ACCENT, LINE, SOFT = (15, 27, 39), (93, 107, 121), (11, 115, 147), (220, 226, 232), (244, 246, 248)
ACCENT_SOFT = (228, 242, 246)
STATE = {"ok": ((29, 122, 73), (226, 244, 234), "OK"), "warn": ((148, 96, 0), (252, 241, 218), "Warning"),
         "bad": ((180, 35, 24), (253, 232, 230), "Fails"), "na": ((93, 107, 121), (240, 243, 246), "—")}
PAGE_W, PAGE_H, M = 210, 297, 12
CW = PAGE_W - 2 * M
BOTTOM = PAGE_H - 16
ROW = 4.3


def _pdf_class():
    from fpdf import FPDF

    class Doc(FPDF):
        model: dict = {}

        def footer(self):
            self.set_draw_color(*LINE)
            self.set_line_width(0.2)
            self.line(M, PAGE_H - 12, PAGE_W - M, PAGE_H - 12)
            self.set_font("Sans", "", 6.5)
            self.set_text_color(*MUTED)
            self.set_xy(M, PAGE_H - 11)
            self.cell(CW - 30, 4, f"Strainforge · strainforge.vercel.app · {DISCLAIMER}")
            self.set_xy(PAGE_W - M - 30, PAGE_H - 11)
            self.cell(30, 4, f"Page {self.page_no()} of {{nb}}", align="R")
    return Doc


class _Writer:
    def __init__(self, model: dict):
        Doc = _pdf_class()
        pdf = Doc(orientation="P", unit="mm", format="A4")
        pdf.model = model
        pdf.set_auto_page_break(False)
        pdf.set_margins(M, M, M)
        pdf.add_font("Sans", "", str(FONTS / "DejaVuSans.ttf"))
        pdf.add_font("Sans", "B", str(FONTS / "DejaVuSans-Bold.ttf"))
        pdf.set_title(model["title"])
        pdf.set_author("Strainforge")
        pdf.set_creator("Strainforge")
        self.pdf, self.m, self.y = pdf, model, M
        self.units = Units("imperial" if model["units"].startswith("Imperial") else "metric")

    # helpers
    def font(self, size, bold=False, color=INK):
        self.pdf.set_font("Sans", "B" if bold else "", size)
        self.pdf.set_text_color(*color)

    def fit(self, text, w):
        text = str(text)
        if self.pdf.get_string_width(text) <= w:
            return text
        while text and self.pdf.get_string_width(text + "…") > w:
            text = text[:-1]
        return text + "…"

    def lines(self, text, w):
        if not text:
            return []
        return self.pdf.multi_cell(w, 3, str(text), dry_run=True, output="LINES")

    def text(self, x, y, w, h, s, align="L"):
        self.pdf.set_xy(x, y)
        self.pdf.cell(w, h, s, align=align)

    def new_page(self):
        pdf = self.pdf
        pdf.add_page()
        self.y = M
        if pdf.page_no() > 1:
            self.font(7, color=MUTED)
            self.text(M, self.y, CW, 4, self.fit(f"Strainforge · {self.m['title']}", CW - 40))
            self.text(M, self.y, CW, 4, self.m["date"], align="R")
            self.y += 5
            pdf.set_draw_color(*LINE)
            pdf.line(M, self.y, PAGE_W - M, self.y)
            self.y += 3

    def need(self, h):
        if self.y + h > BOTTOM:
            self.new_page()
            return True
        return False

    # blocks
    def header(self):
        pdf, m = self.pdf, self.m
        pdf.set_fill_color(*ACCENT)
        pdf.rect(M, self.y, CW, 1.2, style="F")
        self.y += 3.5
        self.font(8, True, ACCENT)
        self.text(M, self.y, CW, 4, "STRAINFORGE")
        self.font(7.5, color=MUTED)
        self.text(M, self.y, CW, 4, f"{m['kind']} report · {m['date']}", align="R")
        self.y += 5
        self.font(15, True)
        for ln in self.lines(m["title"], CW)[:2] or [m["title"]]:
            pdf.set_font("Sans", "B", 15)
            self.text(M, self.y, CW, 7, ln)
            self.y += 6.6
        self.font(8.5, color=MUTED)
        self.text(M, self.y, CW, 4.5, self.fit(m["subtitle"], CW))
        self.y += 6.5
        # meta strip
        meta = list(m["meta"])
        n = len(meta)
        if n:
            w = CW / n
            for i, (k, v) in enumerate(meta):
                x = M + i * w
                self.font(6.3, True, MUTED)
                self.text(x, self.y, w - 3, 3.5, k.upper())
                self.font(8)
                self.text(x, self.y + 3.6, w - 3, 4, self.fit(v, w - 3))
            self.y += 9.5
        # status banner
        st = m["status"]
        fg, bg, _ = STATE.get(st["state"], STATE["na"])
        txt_lines = self.lines(st["text"], CW - 12) if st["text"] else [""]
        pdf.set_font("Sans", "B", 8)
        txt_lines = pdf.multi_cell(CW - 12, 3.6, st["text"], dry_run=True, output="LINES")[:4]
        h = 3 + 3.8 * len(txt_lines)
        pdf.set_fill_color(*bg)
        pdf.rect(M, self.y, CW, h, style="F", round_corners=True, corner_radius=1.2)
        pdf.set_fill_color(*fg)
        pdf.ellipse(M + 3, self.y + h / 2 - 1.1, 2.2, 2.2, style="F")
        self.font(8, True, fg)
        yy = self.y + 1.5
        for ln in txt_lines:
            self.text(M + 7, yy, CW - 10, 3.8, ln)
            yy += 3.8
        self.y += h + 4

    def figure(self, fig, x, y, w, max_h, caption=True):
        """Draw one drawing scaled into a box; returns the height used."""
        pdf = self.pdf
        vw, vh = _viewbox(fig["svg"])
        inner_w = w - 4
        cap_h = 4 if caption and fig.get("caption") else 0
        dw = min(inner_w, (max_h - 4 - cap_h) * vw / vh)
        dh = dw * vh / vw
        h = dh + 4 + cap_h
        pdf.set_fill_color(*SOFT)
        pdf.rect(x, y, w, h, style="F", round_corners=True, corner_radius=1.5)
        try:
            pdf.image(io.BytesIO(svg_for_pdf(fig["svg"], self.units).encode("utf-8")), x=x + (w - dw) / 2, y=y + 2, w=dw, h=dh)
        except Exception:  # a drawing the PDF writer can't read should not cost the whole report
            self.font(7, color=MUTED)
            self.text(x, y + dh / 2, w, 4, "Drawing not available", align="C")
        if cap_h:
            self.font(6.5, color=MUTED)
            self.text(x, y + 2 + dh + 0.3, w, 3.5, self.fit(fig["caption"], w - 4), align="C")
        return h

    def kpi_grid(self, x, y, w):
        kp = self.m["kpis"]
        if not kp:
            return 0
        cols = 2 if len(kp) != 3 else 3
        gap = 2.5
        tw = (w - gap * (cols - 1)) / cols
        th = 17
        pdf = self.pdf
        for i, k in enumerate(kp):
            r, c = divmod(i, cols)
            tx, ty = x + c * (tw + gap), y + r * (th + gap)
            pdf.set_fill_color(*(ACCENT_SOFT if k["main"] else SOFT))
            pdf.rect(tx, ty, tw, th, style="F", round_corners=True, corner_radius=1.5)
            self.font(6.3, True, ACCENT if k["main"] else MUTED)
            self.text(tx + 2.5, ty + 1.8, tw - 5, 3.5, self.fit(k["label"].upper(), tw - 5))
            self.font(13, True, ACCENT if k["main"] else INK)
            val = self.fit(k["value"]["t"], tw - 16)
            self.text(tx + 2.5, ty + 5.6, tw - 5, 6, val)
            vw = pdf.get_string_width(val)
            if k["unit"]:
                self.font(7.5, color=MUTED)
                self.text(tx + 3.5 + vw, ty + 7.2, tw - vw - 6, 4, self.fit(k["unit"], max(tw - vw - 6, 4)))
            self.font(6.3, color=MUTED)
            self.text(tx + 2.5, ty + 12, tw - 5, 3.5, self.fit(k["sub"], tw - 5))
        rows = (len(kp) + cols - 1) // cols
        return rows * th + (rows - 1) * gap

    def checks_height(self, w):
        h = 0
        self.pdf.set_font("Sans", "", 6.5)
        for c in self.m["checks"]:
            h += 5.5 + 2.9 * min(3, len(self.lines(c["desc"], w - 36))) + 1.5
        return h + (6 if self.m["checks"] else 0)

    def checks(self, x, y, w):
        if not self.m["checks"]:
            return 0
        pdf, y0 = self.pdf, y
        self.font(9, True, ACCENT)
        self.text(x, y, w, 4.5, "Design checks")
        y += 6
        for c in self.m["checks"]:
            fg, bg, label = STATE.get(c["state"], STATE["na"])
            pdf.set_font("Sans", "", 6.5)
            desc = self.lines(c["desc"], w - 36)[:3]
            h = 5.5 + 2.9 * len(desc)
            pdf.set_fill_color(*SOFT)
            pdf.rect(x, y, w, h, style="F")
            pdf.set_fill_color(*fg)
            pdf.rect(x, y, 1.1, h, style="F")
            self.font(7.8, True)
            self.text(x + 3, y + 1.2, w - 36, 3.8, self.fit(c["title"], w - 40))
            self.font(6.5, color=MUTED)
            yy = y + 4.8
            for ln in desc:
                self.text(x + 3, yy, w - 36, 2.9, ln)
                yy += 2.9
            self.font(7.8, True, fg)
            self.text(x + w - 33, y + 1.2, 31, 3.8, self.fit(f"{c['value']}", 31), align="R")
            self.font(6.3, color=MUTED)
            self.text(x + w - 33, y + 4.8, 31, 3, self.fit(f"limit {c['limit']}" if c["limit"] else "", 31), align="R")
            self.font(6.3, True, fg)
            self.text(x + w - 33, y + 7.6, 31, 3, label if c["state"] != "na" else "", align="R")
            y += h + 1.5
        return y - y0

    def top(self):
        """Drawing on the left; key results and checks on the right."""
        figs = self.m["figures"]
        fw, gap = 80, 6
        rw = CW - fw - gap
        right_h = (self.kpi_grid_height(rw)) + 4 + self.checks_height(rw)
        y0 = self.y
        left_h = 0
        if figs:
            max_h = max(70, min(105, right_h))
            left_h = self.figure(figs[0], M, y0, fw, max_h)
            figs_done = 1
            while figs_done < len(figs) and right_h - left_h > 42:
                left_h += 3 + self.figure(figs[figs_done], M, y0 + left_h + 3, fw, right_h - left_h - 3)
                figs_done += 1
        else:
            figs_done, rw = 0, CW
        x = M + (fw + gap if figs else 0)
        kh = self.kpi_grid(x, y0, rw)
        ch = self.checks(x, y0 + kh + 4, rw)
        self.y = y0 + max(left_h, kh + 4 + ch) + 5
        rest = figs[figs_done:]
        if rest:
            n = len(rest)
            w = (CW - 4 * (n - 1)) / n
            hs = []
            for f in rest:
                vw, vh = _viewbox(f["svg"])
                hs.append(min(52, (w - 4) * vh / vw + 8))
            h = max(hs)
            self.need(h + 2)
            if n == 1:
                vw, vh = _viewbox(rest[0]["svg"])
                w = min(CW, max(80, (h - 8) * vw / vh + 8))
            x0 = M + (CW - (w * n + 4 * (n - 1))) / 2
            for i, f in enumerate(rest):
                self.figure(f, x0 + i * (w + 4), self.y, w, h)
            self.y += h + 5

    def kpi_grid_height(self, w):
        n = len(self.m["kpis"])
        if not n:
            return 0
        cols = 2 if n != 3 else 3
        rows = (n + cols - 1) // cols
        return rows * 17 + (rows - 1) * 2.5

    # tables
    SIDE_VW, SIDE_UW = 23, 14

    def side_items(self, sec, w):
        lw = w - self.SIDE_VW - self.SIDE_UW
        items = [("title", 6.5, sec, None, None), ("head", 4.2, sec, None, None)]
        for r in sec["rows"]:
            if isinstance(r, dict) and r.get("group"):
                items.append(("group", ROW, sec, r, None))
                continue
            cells = r["cells"] if isinstance(r, dict) else r
            self.pdf.set_font("Sans", "B" if isinstance(r, dict) else "", 7.3)
            lines = self.lines(cells[0]["t"], lw - 3)[:2] or [""]
            items.append(("row", ROW + 3.1 * (len(lines) - 1), sec, r, lines))
        items.append(("gap", 4, sec, None, None))
        return items

    def side_item(self, it, x, y, w):
        kind, h, sec, r, lines = it
        pdf = self.pdf
        vw, uw = self.SIDE_VW, self.SIDE_UW
        lw = w - vw - uw
        if kind == "title":
            self.font(9, True, ACCENT)
            self.text(x, y, w, 4.5, sec["title"] + (" (continued)" if r == "cont" else ""))
        elif kind == "head":
            pdf.set_fill_color(*SOFT)
            pdf.rect(x, y, w, 4.2, style="F")
            self.font(6.3, True, MUTED)
            c = sec["columns"]
            self.text(x + 1.5, y + 0.4, lw - 2, 3.5, c[0].upper())
            self.text(x + lw, y + 0.4, vw - 1, 3.5, c[1].upper(), align="R")
            self.text(x + lw + vw + 1.5, y + 0.4, uw - 2, 3.5, c[2].upper())
        elif kind in ("group", "row"):
            if kind == "group":
                self.font(6.8, True, ACCENT)
                self.text(x + 1.5, y + 0.5, w - 3, ROW - 0.5, self.fit(r["group"], w - 3))
            else:
                key = isinstance(r, dict)
                cells = r["cells"] if key else r
                self.font(7.3, key)
                for i, ln in enumerate(lines):
                    self.text(x + 1.5, y + 0.3 + 3.1 * i, lw - 3, ROW - 0.5, ln)
                self.text(x + lw, y + 0.3, vw - 1, ROW - 0.5, self.fit(cells[1]["t"], vw + 6), align="R")
                self.font(7, color=MUTED)
                self.text(x + lw + vw + 1.5, y + 0.3, uw - 2, ROW - 0.5, self.fit(cells[2]["t"], uw - 2))
            pdf.set_draw_color(*LINE)
            pdf.set_line_width(0.15)
            pdf.line(x, y + h, x + w, y + h)

    def side_sections(self, secs):
        """Inputs, setup and design values in two balanced columns, continuing onto the next page as needed."""
        if not secs:
            return
        gap = 7
        w = (CW - gap) / 2
        per = [self.side_items(s, w) for s in secs]
        hs = [sum(i[1] for i in its) for its in per]
        best = None
        for k in range(1, len(secs) + 1):
            m = max(sum(hs[:k]), sum(hs[k:]))
            if best is None or m < best[0]:
                best = (m, k)
        k = best[1]
        cols = [[i for its in per[:k] for i in its], [i for its in per[k:] for i in its]]
        if BOTTOM - self.y < 35:
            self.new_page()
        while True:
            y0, ends = self.y, []
            for c, items in enumerate(cols):
                x, y = M + c * (w + gap), y0
                while items:
                    it = items[0]
                    need = it[1] + (4.2 + ROW if it[0] == "title" else ROW if it[0] == "head" else 0)
                    if y + need > BOTTOM:
                        break
                    self.side_item(it, x, y, w)
                    y += it[1]
                    items.pop(0)
                ends.append(y)
            if not any(cols):
                self.y = max(ends) + 1
                return
            self.new_page()
            for items in cols:
                if items and items[0][0] in ("row", "group"):
                    sec = items[0][2]
                    items[0:0] = [("title", 6.5, sec, "cont", None), ("head", 4.2, sec, None, None)]

    def steps(self, sec):
        """Every intermediate value, in two columns to keep the report short."""
        pdf = self.pdf
        gap = 7
        w = (CW - gap) / 2
        blocks, cur = [], {"group": None, "rows": []}
        for r in sec["rows"]:
            if isinstance(r, dict) and r.get("group"):
                if cur["rows"] or cur["group"]:
                    blocks.append(cur)
                cur = {"group": r["group"], "rows": []}
            else:
                cur["rows"].append(r)
        if cur["rows"] or cur["group"]:
            blocks.append(cur)
        self.need(6.5 + ROW * 4)
        self.font(9, True, ACCENT)
        self.text(M, self.y, CW, 4.5, sec["title"])
        self.y += 6.5
        vw, uw = 22, 16
        lw = w - vw - uw
        pdf.set_draw_color(*LINE)
        pdf.set_line_width(0.15)
        for b in blocks:
            half = (len(b["rows"]) + 1) // 2
            pairs = [(b["rows"][i], b["rows"][half + i] if half + i < len(b["rows"]) else None) for i in range(half)]
            if b["group"]:
                self.need(ROW * (1 + min(2, len(pairs))))
                pdf.set_fill_color(*SOFT)
                pdf.rect(M, self.y, CW, ROW, style="F")
                self.font(6.8, True, ACCENT)
                self.text(M + 1.5, self.y + 0.4, CW - 3, ROW - 0.5, self.fit(b["group"], CW - 3))
                self.y += ROW
            for a, c in pairs:
                if self.need(ROW):
                    self.font(9, True, ACCENT)
                    self.text(M, self.y, CW, 4.5, sec["title"] + " (continued)")
                    self.y += 6.5
                for col, r in ((0, a), (1, c)):
                    if r is None:
                        continue
                    x = M + col * (w + gap)
                    key = isinstance(r, dict)
                    cells = r["cells"] if key else r
                    self.font(7, key)
                    self.text(x + 1.5, self.y + 0.3, lw - 2.5, ROW - 0.5, self.fit(cells[0]["t"], lw - 2.5))
                    self.text(x + lw, self.y + 0.3, vw - 1, ROW - 0.5, self.fit(cells[1]["t"], vw + 6), align="R")
                    self.font(6.8, color=MUTED)
                    self.text(x + lw + vw + 1.2, self.y + 0.3, uw - 1.5, ROW - 0.5, self.fit(cells[2]["t"], uw - 1.5))
                    pdf.line(x, self.y + ROW, x + w, self.y + ROW)
                self.y += ROW
        self.y += 5

    def wide(self, sec):
        pdf = self.pdf
        cols = sec["columns"]
        n = len(cols)
        align = sec.get("align") or ["L"] + ["R"] * (n - 1)
        need = []
        for i, c in enumerate(cols):
            pdf.set_font("Sans", "B", 6.2)
            wmax = pdf.get_string_width(c)
            pdf.set_font("Sans", "", 7)
            for r in sec["rows"]:
                if i < len(r):
                    wmax = max(wmax, pdf.get_string_width(r[i]["t"]))
            need.append(wmax + 3)
        total = sum(need)
        widths = [x * CW / total for x in need] if total > CW else [x + (CW - total) / n for x in need]

        def head():
            pdf.set_fill_color(*SOFT)
            pdf.rect(M, self.y, CW, 4.6, style="F")
            self.font(6.2, True, MUTED)
            x = M
            for i, c in enumerate(cols):
                self.text(x + 1, self.y + 0.5, widths[i] - 2, 3.6, self.fit(c, widths[i] - 2), align=align[i])
                x += widths[i]
            self.y += 4.6
        self.need(6.5 + 4.6 + ROW * min(4, len(sec["rows"])))
        self.font(9, True, ACCENT)
        self.text(M, self.y, CW, 4.5, sec["title"])
        if sec.get("sub"):
            self.font(7, color=MUTED)
            self.text(M, self.y + 0.4, CW, 4, self.fit(sec["sub"], CW / 2), align="R")
        self.y += 6.5
        head()
        pdf.set_draw_color(*LINE)
        pdf.set_line_width(0.15)
        for r in sec["rows"]:
            if self.need(ROW):
                head()
            x = M
            self.font(7)
            for i, c in enumerate(r[:n]):
                self.text(x + 1, self.y + 0.3, widths[i] - 2, ROW - 0.5, self.fit(c["t"], widths[i] - 2), align=align[i])
                x += widths[i]
            pdf.line(M, self.y + ROW, M + CW, self.y + ROW)
            self.y += ROW
        for f in sec.get("foot") or []:
            self.font(6.5, color=MUTED)
            for ln in self.lines(f, CW):
                self.need(3)
                self.text(M, self.y + 0.5, CW, 3, ln)
                self.y += 3
        self.y += 5

    def paragraphs(self, title, items, bullet=True, size=6.8):
        if not items:
            return
        self.need(6.5 + 8)
        self.font(9, True, ACCENT)
        self.text(M, self.y, CW, 4.5, title)
        self.y += 6.5
        lh = 3.2
        if bullet:  # equations: two columns when they fit on this page
            gap = 7
            w = (CW - gap) / 2
            self.pdf.set_font("Sans", "", size)
            blocks = [self.lines(it, w - 4) for it in items]
            hs = [len(b) * lh + 0.8 for b in blocks]
            best = min(range(len(blocks) + 1), key=lambda k: max(sum(hs[:k]), sum(hs[k:])))
            height = max(sum(hs[:best]), sum(hs[best:]))
            if self.y + height <= BOTTOM:
                ends = []
                for c, grp in enumerate((range(0, best), range(best, len(blocks)))):
                    x, y = M + c * (w + gap), self.y
                    for i in grp:
                        self.font(size, color=MUTED if "converted to metric" in items[i] else INK)
                        for j, ln in enumerate(blocks[i]):
                            if j == 0:
                                self.text(x, y, 4, lh, "•")
                            self.text(x + 4, y, w - 4, lh, ln)
                            y += lh
                        y += 0.8
                    ends.append(y)
                self.y = max(ends) + 4
                return
        for it in items:
            self.pdf.set_font("Sans", "", size)
            for i, ln in enumerate(self.lines(it, CW - 5)):
                self.need(lh)
                self.font(size, color=MUTED if "converted to metric" in it else INK)
                if bullet and i == 0:
                    self.text(M, self.y, 4, lh, "•")
                self.text(M + (4 if bullet else 0), self.y, CW - 4, lh, ln)
                self.y += lh
            self.y += 0.8
        self.y += 4

    def build(self) -> bytes:
        m = self.m
        self.new_page()
        self.header()
        self.top()
        side = [s for s in m["sections"] if s["kind"] == "side"]
        self.side_sections(side)
        for s in m["sections"]:
            if s["kind"] == "wide":
                self.wide(s)
        for s in m["sections"]:
            if s["kind"] == "steps":
                self.steps(s)
        self.paragraphs("Equations", m["equations"])
        if m.get("notes"):
            self.paragraphs("Notes", [p for p in m["notes"].splitlines() if p.strip()], bullet=False, size=7.5)
        return bytes(self.pdf.output())


def build_pdf(model: dict) -> bytes:
    return _Writer(model).build()


# ------------------------------------------------------------------ Excel

X_ACCENT, X_INK, X_MUTED, X_LINE, X_SOFT, X_ACCENT_SOFT = "0B7393", "0F1B27", "5D6B79", "DCE2E8", "F4F6F8", "E4F2F6"
X_STATE = {"ok": ("1D7A49", "E2F4EA", "OK"), "warn": ("946000", "FCF1DA", "Warning"), "bad": ("B42318", "FDE8E6", "Fails"),
           "na": ("5D6B79", "F0F3F6", "—")}
X_COLS = 10


def _safe(v):
    """Report text goes in as text; callers mark formula-like strings as plain text (never a formula)."""
    return v


def _numfmt(d):
    if d is None:
        return "General"
    return "#,##0" + ("." + "0" * d if d else "")


def _sheet(ws, model: dict):
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    fill = lambda c: PatternFill("solid", fgColor=c)  # noqa: E731
    thin = Side(style="thin", color=X_LINE)
    under = Border(bottom=thin)
    ws.sheet_view.showGridLines = False
    widths = [38, 16, 12, 14, 14, 14, 14, 14, 14, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + i)].width = w
    r = 1

    def put(row, col, v, **kw):
        c = ws.cell(row, col)
        c.value = _safe(v)
        if isinstance(c.value, str) and c.data_type == "f":
            c.data_type = "s"
        for k, val in kw.items():
            setattr(c, k, val)
        return c

    def band(row, text, size, color, bg, bold=True, height=None):
        for col in range(1, X_COLS + 1):
            ws.cell(row, col).fill = fill(bg)
        put(row, 1, text, font=Font(bold=bold, size=size, color=color), alignment=Alignment(vertical="center"))
        if height:
            ws.row_dimensions[row].height = height

    band(r, "STRAINFORGE", 9, "FFFFFF", X_ACCENT, height=16)
    put(r, X_COLS, f"{model['kind']} report", font=Font(size=9, color="FFFFFF"), alignment=Alignment(horizontal="right", vertical="center"))
    r += 1
    band(r, model["title"], 16, X_INK, X_ACCENT_SOFT, height=26)
    r += 1
    band(r, model["subtitle"], 10, X_MUTED, X_ACCENT_SOFT, bold=False, height=16)
    r += 2
    for k, v in [("Date", model["date"])] + list(model["meta"]):
        put(r, 1, k, font=Font(bold=True, color=X_MUTED, size=9))
        put(r, 2, v, font=Font(size=10))
        r += 1
    st = model["status"]
    fg, bg, _ = X_STATE.get(st["state"], X_STATE["na"])
    put(r, 1, "Status", font=Font(bold=True, color=X_MUTED, size=9))
    for col in range(2, X_COLS + 1):
        ws.cell(r, col).fill = fill(bg)
    put(r, 2, st["text"], font=Font(bold=True, color=fg))
    r += 2

    def title(text):
        nonlocal r
        put(r, 1, text, font=Font(bold=True, size=12, color=X_ACCENT))
        for col in range(1, X_COLS + 1):
            ws.cell(r, col).border = Border(bottom=Side(style="medium", color=X_ACCENT))
        ws.row_dimensions[r].height = 20
        r += 1

    def header(cols, right_from=1):
        nonlocal r
        for i, c in enumerate(cols, start=1):
            put(r, i, c, font=Font(bold=True, size=9, color=X_MUTED), fill=fill(X_SOFT),
                alignment=Alignment(horizontal="right" if i > right_from else "left", wrap_text=True))
        r += 1

    def value_cell(row, col, c, bold=False, color=X_INK):
        if c["n"] is not None:
            put(row, col, c["n"], number_format=_numfmt(c["d"]), font=Font(bold=bold, color=color),
                alignment=Alignment(horizontal="right"))
        else:
            put(row, col, c["t"], font=Font(bold=bold, color=color), alignment=Alignment(horizontal="right"))

    if model["kpis"]:
        title("Key results")
        header(["Result", "Value", "Unit", "Note"], right_from=1)
        ws.cell(r - 1, 3).alignment = Alignment(horizontal="left")
        ws.cell(r - 1, 4).alignment = Alignment(horizontal="left")
        for k in model["kpis"]:
            put(r, 1, k["label"], font=Font(bold=True))
            value_cell(r, 2, k["value"], bold=True, color=X_ACCENT if k["main"] else X_INK)
            ws.cell(r, 2).font = Font(bold=True, size=12, color=X_ACCENT if k["main"] else X_INK)
            put(r, 3, k["unit"], font=Font(color=X_MUTED))
            put(r, 4, k["sub"], font=Font(color=X_MUTED, size=9))
            for col in range(1, X_COLS + 1):
                ws.cell(r, col).border = under
            ws.row_dimensions[r].height = 18
            r += 1
        r += 1
    if model["checks"]:
        title("Design checks")
        header(["Check", "Value", "Limit", "Status", "Note"], right_from=1)
        for col in (3, 4, 5):
            ws.cell(r - 1, col).alignment = Alignment(horizontal="left")
        for c in model["checks"]:
            fg, bg, label = X_STATE.get(c["state"], X_STATE["na"])
            put(r, 1, c["title"], font=Font(bold=True))
            put(r, 2, c["value"], alignment=Alignment(horizontal="right"))
            put(r, 3, c["limit"], font=Font(color=X_MUTED))
            put(r, 4, label, font=Font(bold=True, color=fg), fill=fill(bg), alignment=Alignment(horizontal="center"))
            ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=X_COLS)
            put(r, 5, c["desc"], font=Font(color=X_MUTED, size=9), alignment=Alignment(wrap_text=True, vertical="top"))
            ws.row_dimensions[r].height = max(15, 12 * (1 + len(c["desc"]) // 95))
            for col in range(1, X_COLS + 1):
                ws.cell(r, col).border = under
            r += 1
        r += 1
    for s in model["sections"]:
        title(s["title"] + (f"  ·  {s['sub']}" if s.get("sub") else ""))
        if s["kind"] == "wide":
            header(s["columns"][:X_COLS])
            for row in s["rows"]:
                for i, c in enumerate(row[:X_COLS], start=1):
                    if i == 1:
                        put(r, 1, c["t"])
                    else:
                        value_cell(r, i, c)
                    ws.cell(r, i).border = under
                r += 1
            for f in s.get("foot") or []:
                put(r, 1, f, font=Font(italic=True, size=9, color=X_MUTED))
                r += 1
        else:
            header(s["columns"])
            ws.cell(r - 1, 3).alignment = Alignment(horizontal="left")
            for row in s["rows"]:
                if isinstance(row, dict) and row.get("group"):
                    for col in range(1, 4):
                        ws.cell(r, col).fill = fill(X_ACCENT_SOFT)
                    put(r, 1, row["group"], font=Font(bold=True, color=X_ACCENT, size=9))
                    r += 1
                    continue
                key = isinstance(row, dict)
                cells = row["cells"] if key else row
                label = cells[0]["t"]
                if cells[1]["t"].startswith("auto ") and cells[1]["n"] is not None:
                    label += " (automatic)"
                put(r, 1, label, font=Font(bold=key))
                value_cell(r, 2, cells[1], bold=key)
                put(r, 3, cells[2]["t"], font=Font(color=X_MUTED))
                for col in range(1, 4):
                    ws.cell(r, col).border = under
                r += 1
        r += 1
    if model["equations"]:
        title("Equations")
        for e in model["equations"]:
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=X_COLS)
            put(r, 1, e, font=Font(name="Consolas", size=9), alignment=Alignment(wrap_text=True, vertical="top"))
            ws.row_dimensions[r].height = max(14, 12 * (1 + len(e) // 120))
            r += 1
        r += 1
    if model.get("notes"):
        title("Notes")
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=X_COLS)
        put(r, 1, model["notes"], alignment=Alignment(wrap_text=True, vertical="top"))
        ws.row_dimensions[r].height = min(400, 14 * (1 + model["notes"].count("\n") + len(model["notes"]) // 120))
        r += 2
    put(r, 1, DISCLAIMER, font=Font(italic=True, size=9, color=X_MUTED))
    ws.page_setup.orientation = "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.oddFooter.left.text = "Strainforge · &[Tab]"
    ws.oddFooter.right.text = "Page &P of &N"


def _sheet_name(title: str, used: set) -> str:
    base = re.sub(r"[\[\]:*?/\\']", "", title).strip()[:28] or "Report"
    name, n = base, 2
    while name.lower() in used:
        name = f"{base[:25]} ({n})"
        n += 1
    used.add(name.lower())
    return name


def build_xlsx(models: list[dict]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = Workbook()
    used: set = set()
    if len(models) == 1:
        ws = wb.active
        ws.title = _sheet_name(models[0]["title"], used)
        _sheet(ws, models[0])
    else:
        ov = wb.active
        ov.title = "Overview"
        used.add("overview")
        ov.sheet_view.showGridLines = False
        for col, w in zip("ABCDEFG", (5, 44, 30, 30, 14, 22, 22)):
            ov.column_dimensions[col].width = w
        for col in range(1, 8):
            ov.cell(1, col).fill = PatternFill("solid", fgColor=X_ACCENT)
        ov.cell(1, 1, "STRAINFORGE").font = Font(bold=True, color="FFFFFF", size=9)
        ov.cell(2, 1, f"{len(models)} reports").font = Font(bold=True, size=16, color=X_INK)
        ov.cell(3, 1, f"{models[0]['date']} · {models[0]['units']}").font = Font(color=X_MUTED)
        heads = ["#", "Name", "Type", "Key result", "Status", "Saved by", "Last change"]
        for i, h in enumerate(heads, start=1):
            c = ov.cell(5, i, h)
            c.font, c.fill = Font(bold=True, size=9, color=X_MUTED), PatternFill("solid", fgColor=X_SOFT)
        for n, m in enumerate(models, start=1):
            name = _sheet_name(m["title"], used)
            ws = wb.create_sheet(name)
            _sheet(ws, m)
            fg, bg, label = X_STATE.get(m["status"]["state"], X_STATE["na"])
            row = 5 + n
            vals = [n, m["title"], m["subtitle"], m["headline"], {"ok": "OK", "warn": "Warning", "bad": "Fails"}.get(m["status"]["state"], "—"),
                    m.get("saved_by", ""), m.get("changed", "")]
            for i, v in enumerate(vals, start=1):
                c = ov.cell(row, i, _safe(v))
                if isinstance(c.value, str) and c.data_type == "f":
                    c.data_type = "s"
                c.border = Border(bottom=Side(style="thin", color=X_LINE))
                c.alignment = Alignment(vertical="top", wrap_text=i in (2, 3, 4))
            link = ov.cell(row, 2)
            link.hyperlink = f"#'{name}'!A1"
            link.font = Font(color=X_ACCENT, underline="single")
            st = ov.cell(row, 5)
            st.font, st.fill = Font(bold=True, color=fg), PatternFill("solid", fgColor=bg)
            st.alignment = Alignment(horizontal="center", vertical="top")
        ov.cell(7 + len(models), 1, DISCLAIMER).font = Font(italic=True, size=9, color=X_MUTED)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_zip(files: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    used: set = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            stem, ext = name.rsplit(".", 1)
            final, n = name, 2
            while final.lower() in used:
                final = f"{stem}-{n}.{ext}"
                n += 1
            used.add(final.lower())
            z.writestr(final, data)
    return buf.getvalue()
