"""Die assembly with a slotted sleeve: case + tapered slotted sleeve + (carbide) insert.

Follows the original workbook cell for cell, with two corrections taken from the
reference training method:
  * Assembly force uses (µ + tan α); the workbook's cell referenced an empty cell
    instead of tan α, so it dropped the taper term.
  * Short sleeves use α = 3°, the industry norm (the training method says 2.5°).

Units: mm, N/mm², kN, degrees.
"""
from __future__ import annotations

import math

from ..drawings import Sk

# Material grades. Typical values for guidance: E in N/mm², m = Poisson number 1/ν,
# Rp = 0.2 % yield strength (steels) or compressive strength (carbide) in N/mm².
# The workbook gives steel E 210 000, m 3.33 and carbide E 550 000, m 4.25; the other
# grades use usual handbook values for the hardness shown.
STEELS = {
    "1.2343": {"label": "1.2343 (H11)", "kind": "Hot-work tool steel", "E": 210000.0, "m": 3.33, "Rp": 1300.0, "hard": "44–48 HRC"},
    "1.2344": {"label": "1.2344 (H13)", "kind": "Hot-work tool steel", "E": 210000.0, "m": 3.33, "Rp": 1350.0, "hard": "44–48 HRC"},
    "1.2367": {"label": "1.2367", "kind": "Hot-work tool steel", "E": 210000.0, "m": 3.33, "Rp": 1450.0, "hard": "46–50 HRC"},
    "1.2709": {"label": "1.2709 maraging", "kind": "Maraging steel, aged", "E": 190000.0, "m": 3.33, "Rp": 1800.0, "hard": "50–54 HRC"},
    "1.6582": {"label": "1.6582 (34CrNiMo6)", "kind": "Alloy steel, hardened and tempered", "E": 210000.0, "m": 3.33, "Rp": 900.0, "hard": "30–36 HRC"},
    "1.7225": {"label": "1.7225 (42CrMo4)", "kind": "Alloy steel, hardened and tempered", "E": 210000.0, "m": 3.33, "Rp": 750.0, "hard": "28–34 HRC"},
}
INSERTS = {
    "WC-12Co": {"label": "Carbide 12%", "kind": "Tungsten carbide, 12 % cobalt", "type": "carbide", "E": 580000.0, "m": 4.55, "Rp": 4800.0, "hard": "≈ 1,400 HV"},
    "WC-15Co": {"label": "Carbide 15%", "kind": "Tungsten carbide, 15 % cobalt", "type": "carbide", "E": 550000.0, "m": 4.25, "Rp": 4300.0, "hard": "≈ 1,250 HV"},
    "WC-20Co": {"label": "Carbide 20%", "kind": "Tungsten carbide, 20 % cobalt", "type": "carbide", "E": 500000.0, "m": 4.17, "Rp": 3800.0, "hard": "≈ 1,050 HV"},
    "WC-25Co": {"label": "Carbide 25%", "kind": "Tungsten carbide, 25 % cobalt", "type": "carbide", "E": 470000.0, "m": 4.0, "Rp": 3300.0, "hard": "≈ 900 HV"},
    "1.3343": {"label": "1.3343 (M2) HSS", "kind": "High-speed steel", "type": "steel", "E": 210000.0, "m": 3.33, "Rp": 3000.0, "hard": "60–62 HRC"},
    "1.3395": {"label": "1.3395 PM-HSS", "kind": "Powder-metallurgy high-speed steel", "type": "steel", "E": 230000.0, "m": 3.33, "Rp": 3300.0, "hard": "62–64 HRC"},
}
# Older links used just "Carbide" or "Steel" for the insert.
INSERT_ALIAS = {"Carbide": "WC-15Co", "Steel": "1.3343"}
PRE = {"carbide": 0.004, "steel": 0.007}  # bore ground oversize before pressing in

_opts = lambda d: [{"value": k, "label": m["label"]} for k, m in d.items()]  # noqa: E731

INPUTS = [
    {"key": "A", "label": "ØA case OD", "unit": "mm", "group": "dims", "hint": "Outer diameter of the case"},
    {"key": "B", "label": "ØB sleeve OD", "unit": "mm", "group": "dims", "hint": "Large end of the taper, equal to the case bore. At most A/2"},
    {"key": "D", "label": "ØD insert bore", "unit": "mm", "group": "dims", "hint": "Product diameter after assembly"},
    {"key": "L", "label": "L sleeve length", "unit": "mm", "group": "dims"},
    {"key": "alpha", "label": "α taper angle", "unit": "°", "group": "dims", "hint": "About 3° for short sleeves, 0.5° for long sleeves"},
    {"key": "C", "label": "ØC insert OD", "unit": "mm", "group": "dims", "placeholder": "auto",
     "hint": "Leave empty to use the optimum k·√(A·D), or enter your rounded size"},
    {"key": "case_mat", "dynHint": True, "label": "Case", "kind": "select", "options": _opts(STEELS), "group": "mat"},
    {"key": "sleeve_mat", "dynHint": True, "label": "Sleeve", "kind": "select", "options": _opts(STEELS), "group": "mat"},
    {"key": "insert", "dynHint": True, "label": "Insert", "kind": "select", "options": _opts(INSERTS), "group": "mat"},
    {"key": "E1", "label": "E1 case", "unit": "N/mm²", "group": "adv", "placeholder": "auto", "hint": "Empty: from the case material"},
    {"key": "E2", "label": "E2 insert", "unit": "N/mm²", "group": "adv", "placeholder": "auto", "hint": "Empty: from the insert material"},
    {"key": "E3", "label": "E3 sleeve", "unit": "N/mm²", "group": "adv", "placeholder": "auto", "hint": "Empty: from the sleeve material"},
    {"key": "m1", "label": "m1 case", "unit": "", "group": "adv", "placeholder": "auto", "hint": "Poisson number 1/ν of the case. Empty: from the material"},
    {"key": "m2", "label": "m2 insert", "unit": "", "group": "adv", "placeholder": "auto", "hint": "Poisson number 1/ν of the insert. Empty: from the material"},
    {"key": "k", "label": "Optimum factor k", "unit": "", "group": "adv", "hint": "ØC = k·√(A·D), k from 0.85 to 0.9"},
    {"key": "z", "label": "Oversize Z/B", "unit": "%", "group": "adv", "hint": "Diametral oversize of the sleeve on the case bore (0.7 %)"},
    {"key": "mua", "label": "µ assembling", "unit": "", "group": "adv", "hint": "Friction while pressing in (≈ 0.03)"},
    {"key": "mud", "label": "µ disassembling", "unit": "", "group": "adv", "hint": "Friction while pressing out (≈ 0.1)"},
]

EXAMPLE = {"A": 60, "B": 30, "D": 10, "L": 50, "alpha": 3, "C": None,
           "case_mat": "1.2343", "sleeve_mat": "1.2343", "insert": "WC-15Co",
           "E1": None, "E2": None, "E3": None, "m1": None, "m2": None, "k": 0.85, "z": 0.7,
           "mua": 0.03, "mud": 0.1}

GROUPS = [
    {"key": "dims", "title": "Dimensions"},
    {"key": "mat", "title": "Materials"},
    {"key": "adv", "title": "Material values and factors", "drawer": True},
]

EQUATIONS = [
    "A / D ≥ 5  (minimum diameter ratio for a slotted sleeve)",
    "C = k · √(A · D),  k = 0.85 … 0.9",
    "B ≤ A / 2,  1.2 < B / C < 1.8",
    "Z = B · 0.007",
    "L2 = Z · 0.5 / tan α",
    "U1 = A / B,  U2 = C / D,  U3 = B / C",
    "K1 = (U1² + 1)/(U1² − 1),  K2 = (U2² + 1)/(U2² − 1),  K3 = (U3² − 1)/(2·U3)",
    "ΔD = Z·[2·U2/(U2² − 1)] / [E2/E1·(K1 + 1/m1) + (K2 − 1/m2) + E2/E3·K3]",
    "ΔA = Z·[2·U1/(U1² − 1)] / [(K1 + 1/m1) + E1/E2·(K2 − 1/m2) + E1/E3·K3]",
    "pB = Z / (B·[1/E1·(K1 + 1/m1) + 1/E2·(K2 − 1/m2) + 1/E3·K3])",
    "F assemble = pB · B · L · (µ + tan α) · π / 1000,  µ ≈ 0.03",
    "F disassemble = pB · B · L · (µ − tan α) · π / 1000,  µ ≈ 0.1",
    "pi max = 2·U2² / (U2² + 1) · pB · U3",
    "σv case = pB · √(K1² + K1 + 1)",
]

NOTES = [
    ("Assembly force includes the taper.",
     "F assemble = pB·B·L·(µ + tan α)·π/1000. The original sheet referenced an empty cell in place of tan α, "
     "which gave only the friction part. With the example values that is 72.6 kN instead of 178.3 kN."),
    ("Taper angle.", "Use about 3° for short sleeves and 0.5° for long sleeves."),
    ("Poisson number.", "m is 1/ν: 3.33 for steel (ν = 0.30) and 4.25 for carbide with 15 % Co (ν ≈ 0.235)."),
    ("Material values.",
     "The grades fill in E and m with typical values for the hardness shown. Strength is the 0.2 % yield strength "
     "for steels and the compressive strength for carbide. Check them against your supplier's data sheet, "
     "or type your own values under Material values and factors."),
    ("Insert bore before pressing in.",
     "The ΔD formula is the theoretical shrink. In practice the bore is ground 0.4 % oversize for carbide "
     "and 0.7 % for steel, so a 19.8 mm bore after assembly is ground to 19.88 mm (carbide) or 19.94 mm (steel)."),
    ("Insert OD.", "The optimum ØC = 0.85·√(A·D) can go up to 0.9·√(A·D). Round it to a practical size and enter it in ØC."),
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


def calculate(values: dict) -> dict:
    v = {k: _num(values.get(k)) for k in EXAMPLE if k not in ("insert", "case_mat", "sleeve_mat")}
    ins_key = INSERT_ALIAS.get(values.get("insert"), values.get("insert"))
    ins_key = ins_key if ins_key in INSERTS else "WC-15Co"
    case_key = values.get("case_mat") if values.get("case_mat") in STEELS else "1.2343"
    slv_key = values.get("sleeve_mat") if values.get("sleeve_mat") in STEELS else "1.2343"
    ins, case, slv = INSERTS[ins_key], STEELS[case_key], STEELS[slv_key]
    defaults = {"k": 0.85, "z": 0.7, "mua": 0.03, "mud": 0.1}
    for k, d in defaults.items():
        if v[k] is None:
            v[k] = d
    E1 = v["E1"] or case["E"]
    E2 = v["E2"] or ins["E"]
    E3 = v["E3"] or slv["E"]
    m1 = v["m1"] or case["m"]
    m2 = v["m2"] or ins["m"]
    pre_f = PRE[ins["type"]]
    A, B, D, L, al = v["A"], v["B"], v["D"], v["L"], v["alpha"]
    hint = lambda m: f"{m['kind']}, {m['hard']}. E {m['E']:,.0f} N/mm², ν {1 / m['m']:.2f}, " + (  # noqa: E731
        "compressive strength" if m.get("type") == "carbide" else "yield") + f" {m['Rp']:,.0f} N/mm²"
    out = {"kpis": [], "values": [], "checks": [], "steps": [], "equations": EQUATIONS, "warnings": [],
           "figures": [], "tables": [],
           "auto": {"E1": E1, "E2": E2, "E3": E3, "m1": m1, "m2": m2,
                    "hints": {"case_mat": hint(case), "sleeve_mat": hint(slv), "insert": hint(ins)}}}

    missing = [lbl for key, lbl in (("A", "ØA"), ("B", "ØB"), ("D", "ØD"), ("L", "L"), ("alpha", "α")) if not v[key] or v[key] <= 0]
    if missing:
        out["warnings"].append("Enter " + ", ".join(missing) + " to calculate")
        out["figures"] = drawings(A or 60, B or 30, None, D or 10, L or 50, al or 3)
        return out
    if not (0 < al < 30):
        out["warnings"].append("The taper angle must be between 0° and 30°")
        return out

    C_opt = v["k"] * math.sqrt(A * D)
    C = v["C"] if v["C"] else C_opt
    out["auto"]["C"] = C_opt
    c_given = bool(v["C"])
    if not (A > B > C > D):
        if not (A > B):
            msg = "The case OD ØA must be larger than the sleeve OD ØB"
        elif not (B > C):
            msg = (f"The insert OD ØC = {_f(C)} mm must be smaller than the sleeve OD ØB"
                   + ("" if c_given else f" (ØC is {v['k']:g}·√(A·D) here)"))
        else:
            msg = f"The insert bore ØD must be smaller than the insert OD ØC = {_f(C)} mm"
        out["warnings"].append(msg)
        out["figures"] = drawings(A, B, C, D, L, al)
        return out

    tg = math.tan(math.radians(al))
    Z = B * v["z"] / 100
    L2 = Z * 0.5 / tg
    U1, U2, U3 = A / B, C / D, B / C
    K1 = (U1 ** 2 + 1) / (U1 ** 2 - 1)
    K2 = (U2 ** 2 + 1) / (U2 ** 2 - 1)
    K3 = (U3 ** 2 - 1) / (2 * U3)
    dD = Z * (2 * U2 / (U2 ** 2 - 1)) / (E2 / E1 * (K1 + 1 / m1) + (K2 - 1 / m2) + E2 / E3 * K3)
    dA = Z * (2 * U1 / (U1 ** 2 - 1)) / ((K1 + 1 / m1) + E1 / E2 * (K2 - 1 / m2) + E1 / E3 * K3)
    pB = Z / (B * (1 / E1 * (K1 + 1 / m1) + 1 / E2 * (K2 - 1 / m2) + 1 / E3 * K3))
    Fa = pB * B * L * (v["mua"] + tg) * math.pi / 1000
    Fd = pB * B * L * (v["mud"] - tg) * math.pi / 1000
    pimax = (2 * U2 ** 2) / (U2 ** 2 + 1) * pB * U3
    sv = pB * math.sqrt(K1 ** 2 + K1 + 1)
    pre = D * (1 + pre_f)
    b_small = B - 2 * L * tg

    out["kpis"] = [
        {"label": "Assembly force", "value": Fa, "unit": "kN", "sub": f"Press-in, µ = {v['mua']:g}", "main": True},
        {"label": "Disassembly force", "value": Fd, "unit": "kN", "sub": f"Press-out, µ = {v['mud']:g}"},
        {"label": "Contact pressure pB", "value": pB, "unit": "N/mm²", "sub": "Case bore on sleeve OD"},
        {"label": "Max. internal pressure", "value": pimax, "unit": "N/mm²", "sub": "Allowed pi in the insert"},
    ]
    out["values"] = [
        {"label": "Insert OD ØC", "value": C, "unit": "mm", "note": "your value" if c_given else f"optimum {v['k']:g}·√(A·D)", "key": True},
        {"label": "Max. sleeve OD ØB (A/2)", "value": A / 2, "unit": "mm"},
        {"label": "Oversize Z", "value": Z, "unit": "mm", "note": "on diameter", "key": True},
        {"label": "Axial push-in L2", "value": L2, "unit": "mm", "note": "to check the oversize"},
        {"label": "Bore shrink ΔD", "value": dD, "unit": "mm", "note": "theoretical"},
        {"label": "Insert bore before pressing", "value": pre, "unit": "mm", "note": f"practice: +{pre_f * 100:g} % for {ins['type']}", "key": True},
        {"label": "Case OD growth ΔA", "value": dA, "unit": "mm"},
        {"label": "Equivalent stress σv at case bore", "value": sv, "unit": "N/mm²"},
    ]

    def chk(ok, title, desc, value, limit, warn=False):
        out["checks"].append({"state": "ok" if ok else ("warn" if warn else "bad"), "title": title, "desc": desc,
                              "value": value, "limit": limit})

    chk(A / D >= 5, "Minimum diameter ratio", "A slotted sleeve needs a case at least 5 times the product diameter.",
        f"A/D = {_f(A / D)}", "≥ 5.00")
    chk(B <= A / 2 + 1e-9, "Sleeve OD", "The sleeve OD may be at most half the case OD.",
        f"{_f(B)} mm", f"≤ {_f(A / 2)} mm")
    chk(1.2 < U3 < 1.8, "Sleeve wall thickness", "Ratio of sleeve OD to insert OD sets the thinnest and thickest wall.",
        f"B/C = {_f(U3)}", "1.20 to 1.80")
    lo, hi = 0.85 * math.sqrt(A * D), 0.9 * math.sqrt(A * D)
    if c_given:
        chk(lo - 0.5 <= C <= hi + 0.5, "Insert OD", "Close to the optimum range 0.85 to 0.9·√(A·D), allowing for rounding.",
            f"{_f(C)} mm", f"{_f(lo)} to {_f(hi)} mm", warn=True)
    chk(b_small > C, "Taper clears the insert", "Small end of the sleeve OD must stay larger than the insert OD.",
        f"{_f(b_small)} mm", f"> {_f(C)} mm")
    chk(Fd > 0, "Sleeve stays put", "With tan α above µ disassembling the sleeve could push itself out.",
        f"tan α = {tg:.4f}", f"< µ = {v['mud']:g}", warn=True)
    chk(0.5 - 1e-9 <= al <= 3 + 1e-9, "Taper angle", "Usual range from 0.5° (long sleeves) to 3° (short sleeves).",
        f"{al:g}°", "0.5° to 3°", warn=True)
    chk(sv <= case["Rp"], "Case stress", f"Equivalent stress at the case bore against the yield strength of {case_key}.",
        f"{_f(sv, 0)} N/mm²", f"≤ {_f(case['Rp'], 0)} N/mm²")
    if any(c["state"] == "bad" for c in out["checks"]):
        out["warnings"] = [c["title"] + " is outside its limit" for c in out["checks"] if c["state"] == "bad"]

    out["steps"] = [
        {"group": "Geometry"},
        {"label": "A / D", "value": A / D, "unit": ""},
        {"label": "Optimum ØC = k·√(A·D)", "value": C_opt, "unit": "mm"},
        {"label": "ØC used", "value": C, "unit": "mm", "key": True},
        {"label": "B / C", "value": U3, "unit": ""},
        {"label": "tan α", "value": tg, "unit": ""},
        {"label": "Small end of sleeve OD", "value": b_small, "unit": "mm"},
        {"group": "Oversize"},
        {"label": "Z = B · " + f"{v['z'] / 100:g}", "value": Z, "unit": "mm", "key": True},
        {"label": "L2 = Z · 0.5 / tan α", "value": L2, "unit": "mm"},
        {"group": "Intermediate results"},
        {"label": "U1 = A / B", "value": U1, "unit": ""},
        {"label": "U2 = C / D", "value": U2, "unit": ""},
        {"label": "U3 = B / C", "value": U3, "unit": ""},
        {"label": "K1", "value": K1, "unit": ""},
        {"label": "K2", "value": K2, "unit": ""},
        {"label": "K3", "value": K3, "unit": ""},
        {"label": "E1 case", "value": E1, "unit": "N/mm²"},
        {"label": "E2 insert", "value": E2, "unit": "N/mm²"},
        {"label": "E3 sleeve", "value": E3, "unit": "N/mm²"},
        {"label": "m1 case", "value": m1, "unit": ""},
        {"label": "m2 insert", "value": m2, "unit": ""},
        {"group": "After assembling"},
        {"label": "ΔD decrease of insert bore", "value": dD, "unit": "mm", "key": True},
        {"label": "ΔA increase of case OD", "value": dA, "unit": "mm"},
        {"label": "pB radial pressure", "value": pB, "unit": "N/mm²", "key": True},
        {"label": "pi max", "value": pimax, "unit": "N/mm²"},
        {"label": "σv case", "value": sv, "unit": "N/mm²"},
        {"group": "Press forces"},
        {"label": "F assemble", "value": Fa, "unit": "kN", "key": True},
        {"label": "F disassemble", "value": Fd, "unit": "kN", "key": True},
    ]
    own = lambda key: " (your value)" if v[key] else ""  # noqa: E731
    out["tables"].append({
        "title": "Materials", "sub": "Typical values for the grades chosen",
        "columns": [{"label": "Part", "unit": ""}, {"label": "Material", "unit": "", "text": True}, {"label": "Type", "unit": "", "text": True}, {"label": "Hardness", "unit": "", "text": True},
                    {"label": "E", "unit": "N/mm²", "decimals": 0}, {"label": "Poisson ν", "unit": "", "decimals": 3},
                    {"label": "Strength", "unit": "N/mm²", "decimals": 0}, {"label": "Stress here", "unit": "N/mm²", "decimals": 0}],
        "rows": [
            ["Case", case["label"] + (own("E1") or own("m1")), case["kind"], case["hard"], E1, 1 / m1, case["Rp"], sv],
            ["Sleeve", slv["label"] + own("E3"), slv["kind"], slv["hard"], E3, 1 / slv["m"], slv["Rp"], pB],
            ["Insert", ins["label"] + (own("E2") or own("m2")), ins["kind"], ins["hard"], E2, 1 / m2, ins["Rp"], pimax],
        ],
        "foot": ["Strength is the 0.2 % yield strength for steels and the compressive strength for carbide.",
                 "Stress here: equivalent stress σv at the case bore, contact pressure pB on the sleeve, "
                 "and the largest pressure pi max the insert can take from its prestress."],
    })
    out["figures"] = drawings(A, B, C, D, L, al)
    return out


# ---------------------------------------------------------------- drawings
class _Sk(Sk):
    """Dimension labels carry data-k so the page can link them to inputs."""
    KEYS = {"ØA": "A", "ØB": "B", "ØC": "C", "ØD": "D", "L": "L", "α": "alpha"}

    def text(self, x, y, s, anchor="middle", cls="tx"):
        super().text(x, y, s, anchor, cls)
        if cls == "dt" and s in self.KEYS:
            self.p[-1] = self.p[-1].replace('<text ', f'<text data-k="{self.KEYS[s]}" ', 1)
        return self

    def raw(self, s):
        self.p.append(s)
        return self


def drawings(A, B, C, D, L, al):
    C = C or 0.85 * math.sqrt(A * D)
    return [_section(A, B, C, D, L, al), _plan(A, B, C, D)]


def _section(A, B, C, D, L, al):
    W = 440
    sc = min((W - 120) / A, 300 / L)
    H = L * sc + 150  # room for the dimensions above and below
    s = _Sk(W, H)
    cx, y0 = W / 2 + 10, 78
    y1 = y0 + L * sc
    ra, rb, rc, rd = A / 2 * sc, B / 2 * sc, C / 2 * sc, D / 2 * sc
    rbs = max(rc + 1.5, (B / 2 - L * math.tan(math.radians(al))) * sc)
    for sg in (1, -1):
        s.poly([(cx + sg * ra, y0), (cx + sg * ra, y1), (cx + sg * rbs, y1), (cx + sg * rb, y0)], "tl")
        s.poly([(cx + sg * rb, y0), (cx + sg * rbs, y1), (cx + sg * rc, y1), (cx + sg * rc, y0)], "tl2")
        s.poly([(cx + sg * rc, y0), (cx + sg * rc, y1), (cx + sg * rd, y1), (cx + sg * rd, y0)], "wp2")
    s.cl(cx, y0 - 14, y1 + 14)
    s.hdim(cx - ra, cx + ra, y0 - 44, "ØA", ext_from=y0)
    s.hdim(cx - rb, cx + rb, y0 - 18, "ØB", ext_from=y0)
    s.hdim(cx - rc, cx + rc, y1 + 22, "ØC", ext_from=y1, above=False)
    s.hdim(cx - rd, cx + rd, y1 + 48, "ØD", ext_from=y1, above=False)
    s.vdim(y0, y1, cx - ra - 22, "L", ext_from=cx - ra, side="left")
    # taper angle: vertical reference at the small end against the sleeve OD line
    s.line(cx + rbs, y1, cx + rbs, y1 - min(60, (y1 - y0) * 0.6), "dx")
    s.text(cx + rbs + 10, y1 - 20, "α", anchor="start", cls="dt")
    s.text(cx + (ra + rb) / 2, y0 + (y1 - y0) / 2, "case", cls="tx")
    return s.svg("Die assembly with slotted sleeve: section")


def _plan(A, B, C, D):
    W, H = 440, 360
    s = _Sk(W, H)
    sc = (H - 110) / A
    cx, cy = W / 2, H / 2 + 22
    ra, rb, rc, rd = A / 2 * sc, B / 2 * sc, C / 2 * sc, D / 2 * sc
    s.raw(f'<circle class="tl" cx="{cx:.1f}" cy="{cy:.1f}" r="{ra:.1f}"/>')
    s.raw(f'<circle class="tl2" cx="{cx:.1f}" cy="{cy:.1f}" r="{rb:.1f}"/>')
    s.raw(f'<circle class="wp2" cx="{cx:.1f}" cy="{cy:.1f}" r="{rc:.1f}"/>')
    s.raw(f'<circle class="bore" cx="{cx:.1f}" cy="{cy:.1f}" r="{rd:.1f}"/>')
    gap = max(2.5, min(5, (rb - rc) * 0.18))
    s.raw(f'<rect class="bore" x="{cx + rc:.1f}" y="{cy - gap / 2:.1f}" width="{rb - rc:.1f}" height="{gap:.1f}"/>')
    s.cl(cx, cy - ra - 10, cy + ra + 10)
    s.hcl(cy, cx - ra - 10, cx + ra + 10)
    s.hdim(cx - ra, cx + ra, cy - ra - 30, "ØA", ext_from=cy - ra * 0.2)
    s.text(cx + (rb + rc) / 2 + 4, cy - gap - 6, "slot", anchor="middle", cls="tx")
    s.text(cx + ra + 6, cy + ra, "top view", anchor="start", cls="tx")
    return s.svg("Die assembly with slotted sleeve: top view")


TOOL = {
    "slug": "slotted-sleeve-die",
    "title": "Die assembly with slotted sleeve",
    "summary": "Insert OD, sleeve limits, oversize, shrink of the insert bore, contact pressure and press-in and press-out forces.",
    "inputs": INPUTS,
    "example": EXAMPLE,
    "groups": GROUPS,
    "figures": ["Section", "Top view"],
    "notes": NOTES,
    "calculate": calculate,
}
