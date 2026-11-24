"""Disc springs (Belleville washers): load, stresses, stacks, fatigue life and tolerances.

Load and stress equations follow EN 16983 (formerly DIN 2092), including the reduced
thickness t' and K4 for springs with contact flats (group 3). Tolerances follow
EN 16984 / DIN 2093. The fatigue life estimate, stack correction, material table and
limits are taken from the source workbook.

Units: mm, N, N/mm², °C.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from ..drawings import Sk

MU = 0.3  # Poisson's ratio

# name, max thickness t' (mm), min °C, max °C, E (N/mm²) at 20, 100, 200, ... 700 °C
MATERIALS = [
    ("1.1231 (C67S)", 1.25, -10, 100, [206000, 202000]),
    ("1.8159 (51CrV4)", 25, -20, 150, [206000, 202000, 196000]),
    ("1.7701 (52CrMoV4)", 40, -20, 150, [206000, 202000, 196000]),
    ("1.4310 (X10CrNi18-8)", 2, -150, 200, [190000, 185000, 178000]),
    ("1.4568 (X7CrNiAl17-7)", 2.5, -200, 200, [200000, 195000, 190000]),
    ("1.4401 (X5CrNiMo17-12-2)", 1.6, -200, 200, [190000, 185000, 178000]),
    ("1.7737 (45CrMoV6-7)", 20, -60, 250, [206000, 202000, 196000, 189000]),
    ("1.6580 (30CrNiMo8)", 20, -80, 250, [206000, 202000, 196000, 189000]),
    ("1.4122 (X39CrMo17-1)", 8, -60, 300, [209000, 205000, 199000, 192000]),
    ("1.2567 (X30WCrV5-3)", 20, -60, 350, [206000, 202000, 196000, 189000, 178000]),
    ("1.4923 (X22CrMoV12-1)", 8, -60, 350, [209000, 205000, 200000, 193000]),
    ("2.1247 (CuBe2)", 3, -250, 150, [135000, 131000, 126000]),
    ("2.4668 (Inconel 718)", 8, -200, 500, [200000, 196000, 190000, 186000, 179000, 172000]),
    ("2.4669 (Inconel X-750)", 8, -200, 500, [214000, 207000, 198000, 190000, 179000, 170000]),
    ("2.4632 (Nimonic 90)", 8, -200, 600, [206000, 201000, 195000, 189000, 181000, 175000, 167000, 160000]),
]
MAT = {m[0]: m for m in MATERIALS}
LIFE_MATERIALS = {MATERIALS[0][0], MATERIALS[1][0], MATERIALS[2][0]}  # fatigue data exists for these
TEMPS = [20, 100, 200, 300, 400, 500, 600, 700]

MODES = {  # how the five load points are entered
    "l": ("Height l of one spring", "mm"),
    "s": ("Travel s of one spring", "mm"),
    "pct": ("Travel in % of h0'", "%"),
    "F": ("Load F of one spring", "N"),
    "L": ("Length of the stack", "mm"),
    "S": ("Travel of the stack", "mm"),
    "FS": ("Load of the stack", "N"),
}

_SIZES = json.loads((Path(__file__).with_name("disc_spring_sizes.json")).read_text())


def _size_options():
    out = []
    for grp, title in (("standard", "Standard sizes"), ("extra", "Extra sizes")):
        for De, Di, t, tr, l0, _w in _SIZES[grp]:
            h0 = l0 - t
            lab = f"{De:g} × {Di:g} × {t:g}" + (f" (t' {tr:g})" if tr else "") + f", l0 {l0:g}"
            out.append({"group": title, "label": lab, "values": {
                "De": De, "Di": Di, "t": t, "tr": tr, "l0": l0, "mode": "l",
                "P1": round(l0 - 0.25 * h0, 4), "P2": round(l0 - 0.75 * h0, 4), "P3": None, "P4": None, "P5": None}})
    return out


POINT_KEYS = ["P1", "P2", "P3", "P4", "P5"]
INPUTS = [
    {"key": "size", "label": "Pick a size", "kind": "preset", "group": "dims", "options": _size_options(),
     "fills": ["De", "Di", "t", "tr", "l0"], "hint": "Fills the dimensions and two load points at 25 % and 75 % of h0"},
    {"key": "De", "label": "De outer diameter", "unit": "mm", "group": "dims"},
    {"key": "Di", "label": "Di inner diameter", "unit": "mm", "group": "dims"},
    {"key": "t", "label": "t thickness", "unit": "mm", "group": "dims"},
    {"key": "tr", "label": "t' reduced thickness", "unit": "mm", "group": "dims", "placeholder": "= t",
     "hint": "Only for springs with contact flats (group 3). Leave empty otherwise"},
    {"key": "l0", "label": "l0 free height", "unit": "mm", "group": "dims"},
    {"key": "nS", "label": "Springs in series", "unit": "", "group": "stack", "hint": "Alternating, face to face. 1 for a single spring"},
    {"key": "nP", "label": "Springs in parallel", "unit": "", "group": "stack", "hint": "Nested in the same direction in each package"},
    {"key": "mode", "label": "Enter load points as", "kind": "select", "group": "points", "remap": True,
     "options": [{"value": k, "label": v[0]} for k, v in MODES.items()]},
    *[{"key": k, "label": f"Load point {k[1]}", "unit": "mm", "unitBy": {"key": "mode", "map": {m: v[1] for m, v in MODES.items()}},
       "group": "points"} for k in POINT_KEYS],
    {"key": "lo", "label": "Fatigue: lower point", "kind": "select", "options": ["1", "2", "3", "4", "5"], "group": "points"},
    {"key": "hi", "label": "Fatigue: upper point", "kind": "select", "options": ["1", "2", "3", "4", "5"], "group": "points"},
    {"key": "mat", "label": "Material", "kind": "select", "options": [m[0] for m in MATERIALS], "group": "mat"},
    {"key": "temp", "label": "Temperature", "unit": "°C", "group": "mat"},
    {"key": "E", "label": "Young's modulus E", "unit": "N/mm²", "group": "mat", "placeholder": "auto",
     "hint": "Empty: from the material at the temperature"},
]

EXAMPLE = {"size": "", "De": 12, "Di": 5.2, "t": 0.5, "tr": None, "l0": 0.9, "nS": 1, "nP": 1, "mode": "l",
           "P1": 0.8, "P2": 0.6, "P3": None, "P4": None, "P5": None, "lo": "1", "hi": "2",
           "mat": "1.8159 (51CrV4)", "temp": 20, "E": None}

GROUPS = [
    {"key": "dims", "title": "Dimensions"},
    {"key": "points", "title": "Load points"},
    {"key": "stack", "title": "Spring stack"},
    {"key": "mat", "title": "Material", "drawer": True},
]

EQUATIONS = [
    "δ = De/Di,  h0 = l0 − t,  h0' = l0 − t'",
    "K1 = (1/π)·((δ−1)/δ)² / ((δ+1)/(δ−1) − 2/ln δ)",
    "K2 = (6/π)·((δ−1)/ln δ − 1)/ln δ,  K3 = (3/π)·(δ−1)/ln δ",
    "C1 = (t'/t)² / ((l0/(4t) − t'/t + 3/4)·(5l0/(8t) − t'/t + 3/8))",
    "C2 = C1/(t'/t)³ · (5/32·(l0/t − 1)² + 1),  K4 = √(−C1/2 + √((C1/2)² + C2))  (K4 = 1 without flats)",
    "F = 4E/(1−µ²) · t'⁴/(K1·De²) · K4² · s/t' · [K4²·(h0'/t' − s/t')·(h0'/t' − s/(2t')) + 1]",
    "σI = −4E/(1−µ²) · t'²/(K1·De²) · K4 · s/t' · [K4·K2·(h0'/t' − s/(2t')) + K3]",
    "σII = −4E/(1−µ²) · t'²/(K1·De²) · K4 · s/t' · [K4·K2·(h0'/t' − s/(2t')) − K3]",
    "σIII = −4E/(1−µ²) · t'²/(K1·De²) · K4 · s/t' · (1/δ) · [K4·(K2 − 2K3)·(h0'/t' − s/(2t')) − K3]",
    "σOM = −4E/(1−µ²) · t'²/(K1·De²) · K4 · s/t' · 3/π",
    "R = 4E/(1−µ²) · t'³/(K1·De²) · K4² · [K4²·((h0'/t')² − 3·h0'/t'·s/t' + 3/2·(s/t')²) + 1]",
    "Stack: L = nS·(l + (nP − 1)·t'),  s = nS·s1,  F = nP·F1,  R = R1·nP/nS",
    "Fatigue: σeq = k·(σmax − σmin/√3) for σII and σIII,  N = 10^((σeq − B)/M)",
]

NOTES = [
    ("Load and stress equations.", "EN 16983 with Poisson's ratio µ = 0.3. Springs with contact flats use the reduced thickness t' and K4; without flats K4 = 1."),
    ("Load points.", "Enter up to five points as a height, a travel, a % of h0', a load, or for the whole stack. Switching the way you enter them converts the points you already have. A load is solved on the rising part of the curve."),
    ("Fatigue life.", "Estimated between the lower and the upper load point at 99 % survival probability, from σII and σIII: "
     "σeq = k·(σmax − σmin/√3) with the stack factor k, then N = 10^((σeq − B)/M) where M and B depend on t'. "
     "Only for C67S, 51CrV4 and 52CrMoV4, up to 60 springs, at most 2 in parallel, t' up to 16 mm, preload of at least 15 % of h0 and travel up to 80 % of h0. "
     "For t' between 5 and 7 mm confirm the result with a fatigue test."),
    ("Preload and travel limits.", "Checked on the two fatigue points. The original sheet checked every load point, so an extra static point could switch the fatigue estimate off."),
    ("Load tolerance.", "From t: +25/−7.5 % below 1.25 mm, +15/−7.5 % to 3 mm, +10/−5 % to 6 mm, ±5 % above, at 75 % of h0 of one spring."),
    ("Temperature.", "E is interpolated linearly between the material's values at 20, 100, 200 … °C. Stresses for the fatigue estimate are scaled back to E at 20 °C."),
]


def _num(v):
    if v is None or v == "":
        return None
    try:
        x = float(str(v).replace(",", "."))
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def _f(v, d=2):
    return f"{v:,.{d}f}"


def e_at(mat, temp):
    Es = mat[4]
    if temp <= 20:
        return Es[0]
    pts = list(zip(TEMPS, Es))
    for (t0, e0), (t1, e1) in zip(pts, pts[1:]):
        if temp <= t1:
            return e0 + (e1 - e0) * (temp - t0) / (t1 - t0)
    return Es[-1]


class Spring:
    def __init__(self, De, Di, t, tr, l0, E):
        self.De, self.Di, self.t, self.tr, self.l0, self.E = De, Di, t, tr, l0, E
        self.h0, self.h0r = l0 - t, l0 - tr
        d = self.delta = De / Di
        ln = math.log(d)
        self.K1 = ((d - 1) / d) ** 2 / ((d + 1) / (d - 1) - 2 / ln) / math.pi
        self.K2 = 6 / math.pi * ((d - 1) / ln - 1) / ln
        self.K3 = 3 / math.pi * (d - 1) / ln
        if abs(tr - t) < 1e-12:
            self.C1 = self.C2 = None
            self.K4 = 1.0
        else:
            q = tr / t
            self.C1 = q ** 2 / ((l0 / (4 * t) - q + 0.75) * (5 * l0 / (8 * t) - q + 3 / 8))
            self.C2 = self.C1 / q ** 3 * (5 / 32 * (l0 / t - 1) ** 2 + 1)
            self.K4 = math.sqrt(-self.C1 / 2 + math.sqrt((self.C1 / 2) ** 2 + self.C2))
        self.A = 4 * E / (1 - MU * MU)
        self.base = self.A / (self.K1 * De * De)

    def F(self, s):
        tr, K4, h = self.tr, self.K4, self.h0r / self.tr
        return self.base * tr ** 4 * K4 ** 2 * (s / tr) * (K4 ** 2 * (h - s / tr) * (h - s / (2 * tr)) + 1)

    def R(self, s):
        tr, K4, h = self.tr, self.K4, self.h0r / self.tr
        return self.base * tr ** 3 * K4 ** 2 * (K4 ** 2 * (h * h - 3 * h * s / tr + 1.5 * (s / tr) ** 2) + 1)

    def stresses(self, s):
        tr, K4, h = self.tr, self.K4, self.h0r / self.tr
        c = -self.base * tr ** 2 * K4 * (s / tr)
        m = K4 * (h - s / (2 * tr))
        return {"sI": c * (self.K2 * m + self.K3), "sII": c * (self.K2 * m - self.K3),
                "sIII": c / self.delta * ((self.K2 - 2 * self.K3) * m - self.K3), "sOM": c * 3 / math.pi}

    def s_for_load(self, F):
        """Smallest travel with this load (on the rising part), or None if it is never reached before flat."""
        if F <= 0:
            return 0.0
        n, prev = 400, 0.0
        for i in range(1, n + 1):
            s = self.h0r * i / n
            if self.F(s) >= F:
                lo, hi = prev, s
                for _ in range(60):
                    mid = (lo + hi) / 2
                    if self.F(mid) >= F:
                        hi = mid
                    else:
                        lo = mid
                return (lo + hi) / 2
            prev = s
        return None


def _tolerances(De, Di, t, tr, l0, mat_name):
    """EN 16984 / DIN 2093 tolerances as in the workbook."""
    def band(x, edges, vals, last):
        for e, v in zip(edges, vals):
            if x < e:
                return v
        return last
    big_d = lambda x: band(x, [180, 250, 315, 400, 500, 600], [0.4, 0.46, 0.52, 0.57, 0.63, 0.68], 0.75)
    small = [6, 10, 18, 30, 50, 80, 120]
    sv = [0.12, 0.15, 0.18, 0.21, 0.25, 0.3, 0.35]
    di = band(Di, small, sv, big_d(Di))
    de = band(De, small, sv, big_d(De))
    tl = band(tr, [0.6, 1.25, 3.8, 6, 15, 25, 40], [0.06, 0.09, 0.12, 0.15, 0.1, 0.12, 0.15], None)
    tu = band(tr, [0.6, 1.25, 3.8, 6, 15, 25, 40], [0.02, 0.03, 0.04, 0.05, 0.1, 0.12, 0.15], None)
    ll = band(tr, [1.25, 2, 3, 6, 15, 25, 40], [0.05, 0.08, 0.1, 0.15, 0.3, 0.5, 1], None)
    lu = band(tr, [1.25, 2, 3, 6, 15, 25, 40], [0.1, 0.15, 0.2, 0.3, 0.3, 0.5, 1], None)
    load = "+25 / −7.5 %" if tr < 1.25 else "+15 / −7.5 %" if tr <= 3 else "+10 / −5 %" if tr <= 6 else "+5 / −5 %"
    clear_i = band(Di, [16, 20, 26, 31.5, 50, 80, 140, 250], [0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1, 1.6], 2)
    clear_e = band(De, [16, 20, 26, 31.5, 50, 80, 140, 250], [0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1, 1.6], 2)
    no_t = "Inconel" in mat_name
    return {"De": (De - de, De), "Di": (Di, Di + di), "t": None if no_t or tl is None else (tr - tl, tr + tu),
            "l0": None if ll is None else (l0 - ll, l0 + lu), "load": load, "clear_i": clear_i, "clear_e": clear_e}


def calculate(values: dict) -> dict:
    v = {k: _num(values.get(k)) for k in ("De", "Di", "t", "tr", "l0", "nS", "nP", "temp", "E", *POINT_KEYS)}
    mode = values.get("mode") if values.get("mode") in MODES else "l"
    mat = MAT.get(values.get("mat")) or MATERIALS[1]
    lo_i = int(values.get("lo")) if str(values.get("lo")) in "12345" and values.get("lo") else 1
    hi_i = int(values.get("hi")) if str(values.get("hi")) in "12345" and values.get("hi") else 2
    temp = 20.0 if v["temp"] is None else v["temp"]
    nS = max(1, int(round(v["nS"] or 1)))
    nP = max(1, int(round(v["nP"] or 1)))
    out = {"kpis": [], "values": [], "checks": [], "steps": [], "equations": EQUATIONS, "warnings": [],
           "figures": [], "tables": [], "auto": {}}

    De, Di, t, l0 = v["De"], v["Di"], v["t"], v["l0"]
    missing = [n for n, x in (("De", De), ("Di", Di), ("t", t), ("l0", l0)) if not x or x <= 0]
    if missing:
        out["warnings"].append("Enter " + ", ".join(missing) + " to calculate")
        out["figures"] = _empty_figs()
        return out
    tr = v["tr"] if v["tr"] and v["tr"] > 0 else t
    if De <= Di:
        out["warnings"].append("De must be larger than Di")
    if tr > t:
        out["warnings"].append("t' cannot be larger than t")
    if l0 <= t:
        out["warnings"].append("l0 must be larger than t (the spring needs some height)")
    if out["warnings"]:
        out["figures"] = _empty_figs()
        return out

    E_auto = e_at(mat, temp)
    E = v["E"] if v["E"] else E_auto
    out["auto"] = {"E": E_auto}
    sp = Spring(De, Di, t, tr, l0, E)

    # ---- load points -> travel s of one spring
    pts = []
    for i, k in enumerate(POINT_KEYS, 1):
        x = v[k]
        if x is None:
            pts.append(None)
            continue
        err, s = None, None
        if mode == "l":
            s = l0 - x
        elif mode == "s":
            s = x
        elif mode == "pct":
            s = x / 100 * sp.h0r
        elif mode == "L":
            s = l0 - (x / nS - (nP - 1) * tr)
        elif mode == "S":
            s = x / nS
        else:
            F1 = x if mode == "F" else x / nP
            s = sp.s_for_load(F1)
            if s is None:
                err = f"Point {i}: the load is more than the spring gives before it is flat"
        if s is not None and s < -1e-9:
            err = f"Point {i}: higher than the free height l0"
        elif s is not None and s > sp.h0r + 1e-9:
            err = f"Point {i}: beyond flat"
        if err:
            out["warnings"].append(err)
            pts.append({"i": i, "error": err})
        else:
            pts.append(_point(sp, max(0.0, s), i, nS, nP))
    flat = _point(sp, sp.h0r, "flat", nS, nP)
    out["auto"]["remap"] = {m: {k: (None if p is None or "error" in p else float(f"{_in_mode(p, m):.6g}")) for k, p in zip(POINT_KEYS, pts)} for m in MODES}

    # ---- fatigue life between the chosen points
    life, life_note = None, ""
    plo, phi = pts[lo_i - 1], pts[hi_i - 1]
    eratio = mat[4][0] / E
    stack_k = (1 if nS <= 10 else 0.004 * nS + 0.96) if nP == 1 else 0.007143 * nS + 1.092857
    smax_allowed = 1300 if tr <= 1.25 else 1290 if tr <= 3 else 1278 if tr <= 6 else 1264 if tr <= 10 else 1248
    reasons = []
    if mat[0] not in LIFE_MATERIALS:
        reasons.append("special material")
    if nS * nP > 60:
        reasons.append("more than 60 springs")
    if nP > 2:
        reasons.append("more than 2 in parallel")
    if nS > 15 and nP > 1:
        reasons.append("more than 15 packages")
    if tr > 16:
        reasons.append("thickness too large")
    if not plo or not phi or "error" in plo or "error" in phi:
        reasons.append("enter both fatigue load points")
    elif lo_i == hi_i:
        reasons.append("pick two different load points")
    eq = {}
    if not reasons:
        lo_p, hi_p = sorted((plo, phi), key=lambda p: p["s"])
        if lo_p["s"] / sp.h0r < 0.15:
            reasons.append(f"preload travel too small (point {lo_p['i']})")
        if hi_p["s"] / sp.h0r > 0.8:
            reasons.append(f"travel too large (point {hi_p['i']})")
        for key in ("sII", "sIII"):
            a, b = plo[key] * eratio, phi[key] * eratio
            smin, smax = min(a, b), max(a, b)
            eq[key] = (stack_k * (smax - smin / math.sqrt(3)), smin, smax)
            if smax > smax_allowed:
                reasons.append(f"upper stress {'σII' if key == 'sII' else 'σIII'} above {smax_allowed} N/mm²")
    if not reasons:
        M = -162.68900024962775 + 3.6699263738180856 * tr - 0.0022546290579634394 * tr * tr
        B = 1921.1046244709878 - 43.3812365744092 * tr + 0.1204467699703401 * tr * tr
        N = min(10 ** ((eq[k][0] - B) / M) for k in eq)
        life = N
        if 5 <= tr <= 7:
            life_note = "Confirm with a fatigue test (t' 5 to 7 mm)"

    # ---- outputs
    valid = [p for p in pts if p and "error" not in p]
    top = phi if phi and "error" not in phi else (max(valid, key=lambda p: p["s"]) if valid else flat)
    stack = nS * nP > 1
    who = "stack" if stack else "one spring"
    out["kpis"] = [
        {"label": f"Load at point {top['i']}" if top is not flat else "Load when flat", "value": top["FS"], "unit": "N",
         "sub": f"{who}, height {_f(top['L'], 3)} mm", "main": True},
        {"label": "Load when flat", "value": flat["FS"], "unit": "N", "sub": who},
        _life_kpi(life, reasons, lo_i, hi_i),
        {"label": "σI when flat", "value": flat["sI"], "unit": "N/mm²", "sub": "Top inner edge, for the set check"},
    ]
    if life_note:
        out["kpis"][2]["sub"] += " · " + life_note

    tol = _tolerances(De, Di, t, tr, l0, mat[0])
    group = 1 if t < 1.25 else (2 if tr == t else 3)
    cone = math.degrees(math.atan(sp.h0r / ((De - Di) / 2)))
    out["values"] = [
        {"label": "Group (EN 16983)", "value": group, "unit": "", "note": "3 = with contact flats" if group == 3 else ""},
        {"label": "h0 = l0 − t", "value": sp.h0, "unit": "mm"},
        {"label": "h0'/t'", "value": sp.h0r / tr, "unit": ""},
        {"label": "De/Di", "value": sp.delta, "unit": ""},
        {"label": "Cone angle at l0", "value": cone, "unit": "°"},
        {"label": "Young's modulus used", "value": E, "unit": "N/mm²", "decimals": 0, "note": f"{mat[0]} at {temp:g} °C" if not v["E"] else "your value"},
        {"label": "Stack length unloaded", "value": nS * (l0 + (nP - 1) * tr), "unit": "mm", "key": stack},
        {"label": "Stack length when flat", "value": flat["L"], "unit": "mm"},
        {"label": "Rate at l0", "value": sp.R(0) * nP / nS, "unit": "N/mm", "decimals": 1, "note": who},
    ]
    if plo and phi and "error" not in plo and "error" not in phi and lo_i != hi_i:
        out["values"].append({"label": f"Travel between points {lo_i} and {hi_i}", "value": abs(phi["L"] - plo["L"]), "unit": "mm",
                              "note": f"{who}: {_f(plo['L'], 3)} mm to {_f(phi['L'], 3)} mm", "key": True})
    out["tolerances"] = tol

    # ---- checks
    def chk(state, title, desc, value, limit):
        out["checks"].append({"state": state, "title": title, "desc": desc, "value": value, "limit": limit})

    lim1 = max(3400.0242823123926 - 5800.022975624218 * sp.delta + 1200.005084544848 * sp.delta ** 2, -3600)
    chk("ok" if flat["sI"] >= lim1 else "bad", "Set-proof", "σI when flat must stay above the limit, or the spring loses height in use.",
        f"{_f(flat['sI'], 0)} N/mm²", f"≥ {_f(lim1, 0)} N/mm²")
    smax_static = max([max(p["sII"], p["sIII"]) for p in valid] or [0])
    chk("ok" if smax_static <= 1680 else "bad", "Static upper stress", "Largest σII or σIII at the load points.",
        f"{_f(smax_static, 0)} N/mm²", "≤ 1,680 N/mm²")
    chk("ok" if tr <= mat[1] else "bad", "Thickness for this material", f"{mat[0]} is made up to {mat[1]:g} mm.",
        f"{_f(tr)} mm", f"≤ {_f(mat[1])} mm")
    chk("ok" if mat[2] <= temp <= mat[3] else "bad", "Temperature", f"Range for {mat[0]}.",
        f"{temp:g} °C", f"{mat[2]:g} to {mat[3]:g} °C")
    hr = sp.h0r / tr
    chk("ok" if hr <= 1.3 else ("bad" if nS > 1 else "warn"), "h0'/t' for stacking",
        "Above 1.3 the spring can't be used in an alternating stack.", f"{_f(hr)}", "≤ 1.30")
    chk("ok" if 1.8 <= sp.delta <= 2.5 else "warn", "De/Di", "Standard springs lie between 1.8 and 2.5.", f"{_f(sp.delta)}", "1.80 to 2.50")
    chk("ok" if 16 <= De / tr <= 40 else "warn", "De/t'", "Standard springs lie between 16 and 40.", f"{_f(De / tr, 1)}", "16 to 40")
    if life is None:
        chk("na", "Fatigue life", "Not estimated: " + "; ".join(reasons) + ".", "—", "")
    else:
        chk("ok", "Fatigue life", f"Between points {lo_i} and {hi_i}" + (f". {life_note}." if life_note else "."),
            _life_text(life), "99 % survival")
    if temp != 20:
        chk("warn", "Test temperature", "Check all spring properties at 20 °C.", f"{temp:g} °C", "20 °C")
    out["warnings"] += [c["title"] + " is outside its limit" for c in out["checks"] if c["state"] == "bad"]

    # ---- tables
    cols = [{"label": "Point", "unit": ""}, {"label": "l", "unit": "mm"}, {"label": "s", "unit": "mm"},
            {"label": "s/h0'", "unit": "%"}, {"label": "F", "unit": "N"}, {"label": "σI", "unit": "N/mm²"},
            {"label": "σII", "unit": "N/mm²"}, {"label": "σIII", "unit": "N/mm²"}, {"label": "σOM", "unit": "N/mm²"},
            {"label": "Rate", "unit": "N/mm"}]
    if stack:
        cols += [{"label": "Stack L", "unit": "mm"}, {"label": "Stack s", "unit": "mm"}, {"label": "Stack F", "unit": "N"}]
    rows = []
    for p in [_point(sp, 0.0, 0, nS, nP)] + [p for p in pts if p] + [flat]:
        if "error" in p:
            rows.append([str(p["i"]), {"error": "invalid"}])
            continue
        r = [("Flat" if p["i"] == "flat" else str(p["i"])), p["l"], p["s"], p["pct"], p["F"], p["sI"], p["sII"], p["sIII"], p["sOM"], p["R"]]
        if stack:
            r += [p["L"], p["S"], p["FS"]]
        rows.append(r)
    out["tables"].append({"title": "Load points", "sub": "One spring" + (", then the stack" if stack else ""), "columns": cols, "rows": rows})
    tl = [["De", tol["De"][0], tol["De"][1], "mm"], ["Di", tol["Di"][0], tol["Di"][1], "mm"]]
    if tol["t"]:
        tl.append(["t'" if tr != t else "t", tol["t"][0], tol["t"][1], "mm"])
    if tol["l0"]:
        tl.append(["l0", tol["l0"][0], tol["l0"][1], "mm"])
    out["tables"].append({"title": "Tolerances", "sub": "EN 16984 / DIN 2093",
                          "columns": [{"label": "Size", "unit": ""}, {"label": "Min", "unit": "mm"}, {"label": "Max", "unit": "mm"}],
                          "rows": [[a, b, c] for a, b, c, _ in tl],
                          "foot": [f"Load tolerance at 75 % of h0 of one spring: {tol['load']}.",
                                   f"Guide clearance in total: {_f(tol['clear_i'], 1)} mm on a guide rod (Di), {_f(tol['clear_e'], 1)} mm in a sleeve (De)."]})

    out["steps"] = [
        {"group": "Geometry"},
        {"label": "δ = De/Di", "value": sp.delta, "unit": ""},
        {"label": "t'", "value": tr, "unit": "mm"},
        {"label": "h0 = l0 − t", "value": sp.h0, "unit": "mm"},
        {"label": "h0' = l0 − t'", "value": sp.h0r, "unit": "mm", "key": True},
        {"label": "h0/t", "value": sp.h0 / t, "unit": ""},
        {"label": "h0'/t'", "value": sp.h0r / tr, "unit": ""},
        {"group": "Factors"},
        {"label": "K1", "value": sp.K1, "unit": ""},
        {"label": "K2", "value": sp.K2, "unit": ""},
        {"label": "K3", "value": sp.K3, "unit": ""},
        *([{"label": "C1", "value": sp.C1, "unit": ""}, {"label": "C2", "value": sp.C2, "unit": ""}] if sp.C1 else []),
        {"label": "K4", "value": sp.K4, "unit": ""},
        {"label": "E", "value": E, "unit": "N/mm²"},
        {"label": "4E/(1−µ²)", "value": sp.A, "unit": "N/mm²"},
        {"group": "When flat (s = h0')"},
        {"label": "F flat, one spring", "value": flat["F"], "unit": "N", "key": True},
        {"label": "σI", "value": flat["sI"], "unit": "N/mm²"},
        {"label": "σOM", "value": flat["sOM"], "unit": "N/mm²"},
        {"label": "Set-proof limit for σI", "value": lim1, "unit": "N/mm²"},
    ]
    if eq:
        out["steps"] += [
            {"group": f"Fatigue between points {lo_i} and {hi_i}"},
            {"label": "Stack factor k", "value": stack_k, "unit": ""},
            {"label": "E ratio E20/E", "value": eratio, "unit": ""},
            {"label": "σII min / max", "value": eq["sII"][1], "unit": "N/mm²"},
            {"label": "", "value": eq["sII"][2], "unit": "N/mm²"},
            {"label": "σeq II", "value": eq["sII"][0], "unit": "N/mm²"},
            {"label": "σIII min / max", "value": eq["sIII"][1], "unit": "N/mm²"},
            {"label": "", "value": eq["sIII"][2], "unit": "N/mm²"},
            {"label": "σeq III", "value": eq["sIII"][0], "unit": "N/mm²"},
        ]
        if life is not None:
            M = -162.68900024962775 + 3.6699263738180856 * tr - 0.0022546290579634394 * tr * tr
            B = 1921.1046244709878 - 43.3812365744092 * tr + 0.1204467699703401 * tr * tr
            out["steps"] += [{"label": "M", "value": M, "unit": ""}, {"label": "B", "value": B, "unit": "N/mm²"},
                             {"label": "N", "value": life, "unit": "cycles", "key": True}]

    out["figures"] = [_section(sp), _stack(sp, nS, nP), _curve(sp, nS, nP, pts, flat)]
    return out


def _point(sp, s, i, nS, nP):
    st = sp.stresses(s)
    l = sp.l0 - s
    st = {k: x + 0.0 for k, x in st.items()}  # no "-0"
    return {"i": i, "s": s, "l": l, "pct": s / sp.h0r * 100, "F": sp.F(s), "R": sp.R(s) * nP / nS, **st,
            "L": nS * (l + (nP - 1) * sp.tr), "S": nS * s, "FS": nP * sp.F(s)}


def _in_mode(p, m):
    return {"l": p["l"], "s": p["s"], "pct": p["pct"], "F": p["F"], "L": p["L"], "S": p["S"], "FS": p["FS"]}[m]


def _life_text(N):
    if N >= 2e6:
        return "more than 2 million"
    r = round(N, -1) if N < 1e4 else round(N, -2) if N < 1e5 else round(N, -3) if N < 1e6 else round(N, -4)
    return f"{r:,.0f} cycles"


def _life_kpi(life, reasons, lo, hi):
    if life is None:
        return {"label": "Fatigue life", "value": None, "text": "—", "unit": "", "sub": "Not estimated: " + reasons[0]}
    if life >= 2e6:
        return {"label": "Fatigue life", "value": None, "text": "> 2 million", "unit": "", "sub": f"Points {lo} → {hi}, 99 % survival"}
    r = round(life, -1) if life < 1e4 else round(life, -2) if life < 1e5 else round(life, -3) if life < 1e6 else round(life, -4)
    return {"label": "Fatigue life", "value": r, "unit": "cycles", "decimals": 0, "sub": f"Points {lo} → {hi}, 99 % survival"}


# ---------------------------------------------------------------- drawings
class _Sk(Sk):
    KEYS = {"De": "De", "Di": "Di", "t": "t", "l0": "l0", "t'": "tr"}

    def text(self, x, y, s, anchor="middle", cls="tx"):
        super().text(x, y, s, anchor, cls)
        if cls == "dt" and s in self.KEYS:
            self.p[-1] = self.p[-1].replace('<text ', f'<text data-k="{self.KEYS[s]}" ', 1)
        return self

    def raw(self, s):
        self.p.append(s)
        return self


def _empty_figs():
    s = _Sk(440, 240)
    s.text(220, 120, "Enter De, Di, t and l0 to draw the spring", cls="tx")
    svg = s.svg("Disc spring")
    return [svg, svg, svg]


def _ring_section(s, cx, base, sc, sp, cls="tl"):
    """Both halves of the cone section, inner edge up, sitting on y = base."""
    ro, ri, t, h = sp.De / 2 * sc, sp.Di / 2 * sc, sp.t * sc, sp.h0 * sc
    for sg in (1, -1):
        # parallelogram: outer bottom, outer top, inner top, inner bottom
        pts = [(cx + sg * ro, base), (cx + sg * ro, base - t), (cx + sg * ri, base - h - t), (cx + sg * ri, base - h)]
        if sp.tr != sp.t:  # contact flats trim the outer bottom and the inner top corners
            f = (sp.t - sp.tr) * sc
            pts = [(cx + sg * (ro - f * 2.2), base), (cx + sg * ro, base - f), (cx + sg * ro, base - t),
                   (cx + sg * (ri + f * 2.2), base - h - t), (cx + sg * ri, base - h - t + f), (cx + sg * ri, base - h)]
        s.poly(pts, cls)


def _section(sp):
    W = 440
    sc = min((W - 80) / sp.De, 160 / sp.l0)
    k = max(1.0, min(8.0, 60 / (sp.l0 * sc)))  # thin springs: stretch the height so it can be read
    if k > 1.05:
        k = math.floor(k * 2) / 2
    else:
        k = 1.0
    H = sp.l0 * sc * k + 130
    s = _Sk(W, H)
    cx, base = W / 2, 60 + sp.l0 * sc * k
    v = _Scaled(sp, k)
    _ring_section(s, cx, base, sc, v)
    s.cl(cx, base - sp.l0 * sc * k - 30, base + 14)
    s.hdim(cx - sp.De / 2 * sc, cx + sp.De / 2 * sc, base + 34, "De", ext_from=base, above=False)
    s.hdim(cx - sp.Di / 2 * sc, cx + sp.Di / 2 * sc, base - sp.l0 * sc * k - 22, "Di", ext_from=base - sp.l0 * sc * k)
    x0 = cx + sp.De / 2 * sc + 18
    s.vdim(base - sp.l0 * sc * k, base, x0, "l0", ext_from=cx + sp.Di / 2 * sc)
    xr = cx - sp.De / 2 * sc - 14
    s.vdim(base - sp.t * sc * k, base, xr, "t", ext_from=cx - sp.De / 2 * sc, side="left")
    if k > 1:
        s.text(12, H - 10, f"heights drawn ×{k:g} so the section can be read", anchor="start", cls="tx")
    return s.svg("Disc spring section")


class _Scaled:
    """The spring with its heights multiplied by k, for drawing only."""
    def __init__(self, sp, k):
        self.De, self.Di, self.t, self.tr, self.h0, self.l0 = sp.De, sp.Di, sp.t * k, sp.tr * k, sp.h0 * k, sp.l0 * k


def _stack(sp, nS, nP):
    W = 440
    show = min(nS, 12)
    unit_h = sp.l0 + (nP - 1) * sp.tr
    total = show * unit_h
    sc = min((W - 120) / sp.De, 300 / max(total, 1e-9))
    k = max(1.0, min(8.0, 70 / (total * sc)))
    k = math.floor(k * 2) / 2 if k > 1.05 else 1.0
    vs = sc * k  # vertical scale
    H = total * vs + 90
    s = _Sk(W, H)
    cx, y = W / 2, 40 + total * vs
    ro, ri, t, h = sp.De / 2 * sc, sp.Di / 2 * sc, sp.tr * vs, sp.h0r * vs
    for k in range(show):
        flip = k % 2 == 1
        for j in range(nP):
            off = j * t
            for sg in (1, -1):
                if not flip:  # inner edge up
                    pts = [(cx + sg * ro, y - off), (cx + sg * ro, y - off - t), (cx + sg * ri, y - off - h - t), (cx + sg * ri, y - off - h)]
                else:  # outer edge up
                    yb = y - unit_h * vs
                    pts = [(cx + sg * ro, yb + off), (cx + sg * ro, yb + off + t), (cx + sg * ri, yb + off + h + t), (cx + sg * ri, yb + off + h)]
                s.poly(pts, "tl" if j % 2 == 0 else "tl2")
        y -= unit_h * vs
    s.cl(cx, 26, 40 + total * vs + 10)
    s.vdim(y, 40 + total * vs, cx + ro + 20, "L0", ext_from=cx + ro)
    lab = f"{nS} in series" + (f" × {nP} in parallel" if nP > 1 else "") + (f" (first {show} shown)" if nS > show else "") + (f", heights ×{k:g}" if k > 1 else "")
    s.text(cx, H - 12, lab, cls="tx")
    return s.svg("Disc spring stack")


def _curve(sp, nS, nP, pts, flat):
    W, H, l, r, tp, b = 440, 300, 62, 18, 16, 44
    n = 60
    xs = [sp.h0r * i / n for i in range(n + 1)]
    Fs = [sp.F(x) * nP for x in xs]
    X = [x * nS for x in xs]
    fmax = max(Fs) * 1.08 or 1
    xmax = X[-1] or 1
    px = lambda x: l + x / xmax * (W - l - r)
    py = lambda f: tp + (1 - f / fmax) * (H - tp - b)
    s = _Sk(W, H)
    for i in range(5):
        f = fmax * i / 4
        s.raw(f'<line x1="{l}" x2="{W - r}" y1="{py(f):.1f}" y2="{py(f):.1f}" stroke="var(--line)"/>')
        s.raw(f'<text class="tx" x="{l - 6}" y="{py(f) + 4:.1f}" text-anchor="end" data-qty="{f:.6g}" data-unit="N" data-d="0">{f:,.0f}</text>')
    for i in range(5):
        x = xmax * i / 4
        s.raw(f'<text class="tx" x="{px(x):.1f}" y="{H - b + 16}" text-anchor="middle" data-qty="{x:.6g}" data-unit="mm">{x:.3g}</text>')
    d = "M" + " L".join(f"{px(x):.1f},{py(f):.1f}" for x, f in zip(X, Fs))
    s.raw(f'<path d="{d} L{px(X[-1]):.1f},{py(0):.1f} L{px(0):.1f},{py(0):.1f}Z" fill="var(--accent-soft)" stroke="none"/>')
    s.raw(f'<path d="{d}" fill="none" stroke="var(--chart-line)" stroke-width="2"/>')
    for p in [p for p in pts if p and "error" not in p] + [flat]:
        x, y = px(p["S"]), py(p["FS"])
        s.raw(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="var(--chart-line)" stroke="var(--panel)" stroke-width="2"/>')
        s.raw(f'<text class="dt" x="{x - 6:.1f}" y="{y - 8:.1f}" text-anchor="end">{"c" if p["i"] == "flat" else p["i"]}</text>')
    who = "stack" if nS * nP > 1 else "one spring"
    s.raw(f'<text class="tx" x="{W - r}" y="{H - 6}" text-anchor="end">travel s of the {who} →  (c = flat)</text>')
    s.raw(f'<text class="tx" x="12" y="{tp + 4}" text-anchor="start">F</text>')
    return s.svg(f"Load against travel, {who}")


TOOL = {
    "slug": "disc-spring",
    "title": "Disc spring calculator",
    "summary": "Load, stresses, stacks, fatigue life and tolerances of disc springs (Belleville washers), with standard sizes to pick from.",
    "inputs": INPUTS,
    "example": EXAMPLE,
    "groups": GROUPS,
    "figures": ["Section", "Stack", "Characteristic"],
    "notes": NOTES,
    "calculate": calculate,
}
