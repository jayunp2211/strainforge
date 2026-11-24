"""Calculation service: drives the workbook model with user inputs and
returns everything the UI shows (inputs, results, checks, steps)."""
from __future__ import annotations

import json
import math
from pathlib import Path

from .xlengine import BLANK, Workbook, is_err

HERE = Path(__file__).parent
MODEL = json.loads((HERE / "model.json").read_text(encoding="utf-8"))
DEFAULT_MATERIALS = json.loads((HERE / "materials.json").read_text(encoding="utf-8"))

M, U, T = "Force calculations", "Underlying force calculation", "Material"
PROCESSES = [MODEL["M"][f"AD{r}"] for r in range(3, 13)]
SHAPES = {MODEL["M"][f"Z{r}"]: r - 2 for r in range(3, 20) if MODEL["M"].get(f"Z{r}")}
SHAPE_NAMES = {v: k.replace("\n", " ").replace("  ", " ").strip() for k, v in SHAPES.items()}
SHAPE_RAW = {v: k for k, v in SHAPES.items()}
INPUT_CELLS = ["C45", "C47", "C48", "C49", "C50", "C51", "C52", "C53", "C54", "C55", "C57", "C58", "C59"]
CARBON_OPTIONS = ["<0.1% C", "0.1%C - 0.3%C", "0.3%C - 0.5%C"]

PROCESS_SHAPES = {1: [1], 2: [2, 3], 3: [2], 4: [4, 5, 6], 5: [7, 8, 10], 6: [11], 7: [12], 8: [13], 9: [14], 10: [15, 16, 17]}
PROCESS_SLUG = {1: "cut-off", 2: "closed-upset", 3: "open-upset", 4: "setting", 5: "pre-upset", 6: "reduction",
                7: "trap-extrusion", 8: "backward-extrusion", 9: "piercing", 10: "trimming"}

PRESETS = {
    "1-1": {"C49": 10},
    "2-2": {"C45": 0.05, "C49": 14, "C50": 24, "C51": 2.2, "C52": 14},
    "2-3": {"C45": 0.05, "C49": 14, "C50": 24, "C51": 2.2, "C52": 14},
    "3-2": {"C45": 0.05, "C49": 14, "C50": 24, "C51": 2.2, "C52": 1.1},
    "4-4": {"C45": 0.05, "C49": 14, "C50": 18, "C51": 16, "C52": 6, "C53": 10, "C54": 30},
    "4-5": {"C49": 14, "C50": 20, "C51": 16, "C52": 15, "C53": 6, "C54": 14, "C55": 4, "C57": 30},
    "4-6": {"C49": 14, "C50": 20, "C51": 16, "C52": 15, "C53": 6, "C54": 14, "C55": 2500, "C57": 30},
    "5-7": {"C45": 0.05, "C49": 18, "C50": 16, "C51": 4, "C52": 12, "C53": 24, "C54": 3, "C55": 20, "C57": 14},
    "5-8": {"C49": 20, "C50": 16, "C51": 15, "C52": 5, "C53": 14, "C54": 4, "C55": 24, "C57": 3, "C58": 20},
    "5-10": {"C49": 20, "C50": 16, "C51": 15, "C52": 5, "C53": 14, "C54": 2500, "C55": 24, "C57": 3, "C58": 20},
    "6-11": {"C49": 11.04, "C50": 9.9, "C51": 3},
    "7-12": {"C49": 14, "C50": 10, "C51": 12, "C52": 20, "C53": 25, "C59": "<0.1% C"},
    "8-13": {"C48": 2.04, "C49": 15, "C50": 20, "C51": 160, "C52": 15, "C53": 8, "C54": 12},
    "9-14": {"C48": 6, "C49": 3, "C50": 8},
    "10-15": {"C49": 20, "C50": 8, "C51": 17},
    "10-16": {"C49": 20, "C50": 8, "C51": 14},
    "10-17": {"C49": 20, "C50": 8, "C51": 18},
}

TR = {"NVT": "N/A", "Begin": "Start", "Eind": "End", "TRAPEZIUM": "Trapezoid", "2X TRAPEZIUM": "Double trapezoid",
      "BOL": "Sphere", "ZESKANT": "Hexagon", "VIERKANT": "Square", "ROND": "Round", "alles in orde": "All OK",
      "moet min 0.5xD geleid worden in de stempel": "Guide at least 0.5×D in the punch",
      "Voorvorm is noodzakelijk!": "A preform is required"}

EQUATIONS = {
    1: ["τB = 0.8 · Rm   (cutting resistance, VDI 3144)", "F = (π · D² / 4) · τB / 1000   [kN]"],
    3: ["V = π·d1²/4 · h1 ;  h0 = 4V / (π·d0²)", "φ = ln(d1² / d0²) + φ0", "kf1 = C · φⁿ",
        "a = C · [φⁿ⁺¹ − φ0ⁿ⁺¹] / (n+1)   (φ includes φ0)", "aw = a · [1 + µ/6 · (d0/h0 + d1/h1)]",
        "F = kf1 · π·d1²/4 · [1 + µ/3 · d1/h1] / 1000", "W = π·d0²/4 · h0 · aw · 10⁻⁶", "S = h0 / d0 ;  ξ = (1 − d²/d1²) · 100"],
    "B": ["φ = ln(D1² / D0²)   (preform at the start: ln(D0²/Deq²))", "kf1 = C · (φ + φ0)ⁿ",
          "a = C · [(φ+φ0)ⁿ⁺¹ − φ0ⁿ⁺¹] / (n+1)", "aw = a · [1 + µ/6 · (D0/H0 + D1/Hk)]",
          "F = kf1 · π·D1²/4 · [1 + µ/3 · D1/Hk] / 1000", "W = Σ V · aw · 10⁻⁶   (top, middle and bottom volumes)",
          "Truncated cone: V = π/3 · h · (R² + R·r + r²)", "S = Lf / D0 ;  ξ = (1 − d²/D1²) · 100"],
    6: ["φ = ln(d1² / d2²) + φ0", "kf1 = C · φⁿ", "a = C · [φⁿ⁺¹ − φ0ⁿ⁺¹] / (n+1)", "p = a · [1 + 2µ / sin 2α + ⅔ · α / φ]",
        "F = π·d1²/4 · p / 1000", "W = F · S / 1000", "E = (d1² − d2²) / d1² · 100"],
    7: ["φ = ln(d1² / d2²) ;  φ0 = input (0.05 if empty)", "a = C · [(φ+φ0)ⁿ⁺¹ − φ0ⁿ⁺¹] / (n+1)",
        "p = a · [1 + 2µ / sin 2α + ⅔ · α / (φ+φ0)]", "kf0.1 = C · φ0ⁿ", "p' = (p − kf0.1) · (e^(4µ·H0/d1) − 1)",
        "F = π·d1²/4 · (p + p') / 1000", "W = F · S / 1000"],
    8: ["φ = ln(d2² / (d2² − d1²))", "a = C · [(φ+φ0)ⁿ⁺¹ − φ0ⁿ⁺¹] / (n+1)",
        "K1 = 0.7 / (φ+φ0+0.05) + 1.3   if H0/d2 ≥ 1", "K1 = 0.7 / (φ+φ0+0.04+d2/(50·H0)) + 1.3   otherwise",
        "K2 = 1.05 − sin α / 6   (K2 = 1 for α ≥ 2.8 rad)", "F = π·d2²/4 · a · K1 · K2 / 1000", "W = F · S / 1000"],
    9: ["kf1 = C · (φ0 + ln(H0 / T))ⁿ", "F = d · π · T · kf1 · 0.8 / 1000", "W = F · T/4 / 1000"],
    10: ["kf = C · 0.8ⁿ", "deq: round = d1 ; square = 4z/π ; hexagon = 12·tan 30° · (SW/2) / π",
         "F = (π·d0²/4 − π·deq²/4) · kf / 1000", "W = F · H1 / 1000"],
}

G = "grp"
DETAIL = {
    1: [(G, "Inputs"), ("C4", "Tensile strength Rm", "N/mm²"), ("C6", "Wire diameter D", "mm"), (G, "Results"),
        ("C10", "Shear resistance τB = 0.8 · Rm", "N/mm²"), ("C11", "Cut-off load F", "kN", 1)],
    3: [(G, "Inputs"), ("E21", "Kf100 / C", "N/mm²"), ("E22", "n", ""), ("E23", "φ0", ""), ("E24", "µ", ""),
        ("E28", "d0", "mm"), ("E29", "d1", "mm"), ("E27", "h1", "mm"), ("E30", "h/2", "mm"), ("I27", "Volume V", "mm³"),
        ("E26", "h0 (from volume)", "mm"), (G, "Results"), ("E40", "φ", ""), ("E41", "kf1", "N/mm²"), ("E42", "a", "Nmm/mm³"),
        ("E43", "aw", "Nmm/mm³"), ("E45", "F", "kN", 1), ("E46", "W", "kJ", 1), (G, "Checks"), ("E34", "S = h0 / d0", ""),
        ("E35", "ξ", "%"), ("F35", "ξ limit", "%")],
    "B": [(G, "Inputs"), ("E60", "Kf100 / C", "N/mm²"), ("E61", "n", ""), ("E62", "φ0", ""), ("E63", "µ", ""),
          ("E64", "Preform location", ""), ("E65", "Preform shape", ""), ("E66", "@D66", "mm"), ("E69", "@D69", "mm"),
          ("E70", "@D70", "mm"), ("E71", "@D71", "mm"), ("E72", "@D72", "mm"), ("E73", "H1", "mm"), ("E74", "H above", "mm"),
          ("E75", "Sphere volume", "mm³"), ("E76", "Hk (preform → head)", "mm"), ("B69", "d stem", "mm"),
          (G, "Geometry"), ("H67", "Volume top", "mm³"), ("H68", "Volume middle", "mm³"), ("H69", "Volume bottom", "mm³"),
          ("E67", "Deq", "mm"), ("E68", "H0", "mm"), ("B83", "Lf", "mm"),
          (G, "Results"), ("E80", "φ", ""), ("E81", "kf1", "N/mm²"), ("E82", "a", "Nmm/mm³"), ("E83", "aw", "Nmm/mm³"),
          ("H72", "aw top", "Nmm/mm³"), ("H73", "aw bottom", "Nmm/mm³"), ("E85", "F", "kN", 1), ("H74", "W top", "kJ"),
          ("H75", "W middle", "kJ"), ("H76", "W bottom", "kJ"), ("E86", "W total", "kJ", 1),
          (G, "Checks"), ("E88", "Upset ratio S", ""), ("F88", "Upset ratio advice", ""), ("E89", "ξ", "%"), ("F89", "ξ limit", "%")],
    6: [(G, "Inputs"), ("E101", "Kf100 / C", "N/mm²"), ("E102", "n", ""), ("E103", "φ0", ""), ("E104", "µ", ""),
        ("E108", "d1", "mm"), ("E109", "d2", "mm"), ("G107", "α", "°"), ("E107", "α", "rad"), ("E105", "S stroke", "mm"),
        ("E106", "LK free length", "mm"), (G, "Results"), ("E120", "φ (incl. φ0)", ""), ("E121", "kf1", "N/mm²"),
        ("E122", "a", "Nmm/mm³"), ("E123", "p", "N/mm²"), ("E125", "F", "kN", 1), ("E126", "W", "kJ", 1), (G, "Checks"),
        ("E128", "Area change E", "%"), ("E129", "LK / d1", "")],
    7: [(G, "Inputs"), ("E141", "Kf100 / C", "N/mm²"), ("E142", "n", ""), ("E143", "φ0", ""), ("E144", "µ", ""),
        ("E148", "d1", "mm"), ("E149", "d2", "mm"), ("G147", "α", "°"), ("E147", "α", "rad"), ("E146", "H0", "mm"),
        ("E145", "S stroke", "mm"), ("E152", "%C", ""), ("E150", "kf0.1", "N/mm²"), (G, "Results"), ("E160", "φ", ""),
        ("E161", "a", "Nmm/mm³"), ("E162", "p", "N/mm²"), ("E163", "p' (wall friction)", "N/mm²"), ("E166", "F", "kN", 1),
        ("E167", "W", "kJ", 1), (G, "Checks"), ("E169", "Area change E", "%"), ("F169", "Area change limit", "%"),
        ("H169", "Advice", "")],
    8: [(G, "Inputs"), ("E181", "Kf100 / C", "N/mm²"), ("E182", "n", ""), ("E183", "φ0", ""), ("E189", "d1 (punch)", "mm"),
        ("E190", "d2 (die)", "mm"), ("G188", "α", "°"), ("E188", "α", "rad"), ("E186", "H0", "mm"), ("E187", "H1", "mm"),
        ("E185", "S stroke", "mm"), (G, "Results"), ("E198", "φ", ""), ("E199", "a", "Nmm/mm³"),
        ("F200", "K1 theoretical", ""), ("F201", "K1 simulation", ""), ("E200", "K1 used", ""), ("E202", "K2", ""),
        ("E204", "F", "kN", 1), ("E205", "W", "kJ", 1), (G, "Checks"), ("E207", "Area change E", "%"), ("E208", "H1", "mm"),
        ("F208", "Minimum H1", "mm")],
    9: [(G, "Inputs"), ("E221", "Kf100 / C", "N/mm²"), ("E222", "n", ""), ("E223", "φ0", ""), ("E226", "H0 punch thickness", "mm"),
        ("E227", "T web thickness", "mm"), ("E228", "d punch diameter", "mm"), (G, "Results"), ("E240", "kf1", "N/mm²"),
        ("E243", "F", "kN", 1), ("E244", "W", "kJ", 1)],
    10: [(G, "Inputs"), ("E261", "Kf100 / C", "N/mm²"), ("E262", "n", ""), ("E263", "φ (fixed)", ""), ("E272", "Head shape", ""),
         ("E266", "d0 preform diameter", "mm"), ("E267", "H1 head height", "mm"), ("TRIM", "", "mm"), ("E271", "deq", "mm"),
         (G, "Results"), ("E280", "kf", "N/mm²"), ("E283", "F", "kN", 1), ("E284", "W", "kJ", 1)],
}
_SKIP_ZERO = {f"E{r}" for r in range(66, 77)} | {"B69", "H67", "H68", "H69", "H72", "H73", "H74", "H75", "H76"}


def _material_sheet(materials):
    sheet = {"B2": "Material", "C2": "C", "D2": "n", "E2": "Rm"}
    for i, m in enumerate(materials[:61]):
        r = i + 3
        sheet[f"B{r}"] = m["name"]
        sheet[f"C{r}"] = m.get("C")
        sheet[f"D{r}"] = m.get("n")
        rm = m.get("Rm")
        if rm in (None, "") and m.get("C") and m.get("n"):
            n = float(m["n"])
            rm = float(m["C"]) * (n / math.e) ** n  # Rm = C·(n/e)^n
        sheet[f"E{r}"] = rm
    return sheet


def clean(v):
    """JSON-friendly value."""
    if is_err(v):
        return {"error": v.code}
    if v is BLANK or v == "":
        return None
    if isinstance(v, float) and not math.isfinite(v):
        return {"error": "#NUM!"}
    if isinstance(v, str):
        return TR.get(v, v)
    return v


def _s(v):
    return "" if (v is BLANK or is_err(v) or v is None) else str(v)


def _strip_paren(s):
    s = s.strip()
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
    return s


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


class Calculator:
    def __init__(self, materials=None):
        self.materials = materials or DEFAULT_MATERIALS
        sheets = {M: dict(MODEL["M"]), U: dict(MODEL["U"]), T: _material_sheet(self.materials)}
        self.wb = Workbook(sheets, {"tabelMateriaal": (T, "B2", "E63")})

    def setup(self, p, shape, material, inputs):
        wb = self.wb
        wb.clear_overrides()
        wb.set(M, "E7", PROCESSES[p - 1])
        wb.set(M, "O7", SHAPE_RAW[shape])
        wb.set(M, "C41", material)
        for a in INPUT_CELLS:
            v = inputs.get(a)
            if a == "C47":
                if p == 1:
                    wb.set(M, a, "" if v in (None, "") else v)
                continue
            wb.set(M, a, None if v in (None, "") else v)

    def g(self, a):
        return self.wb.get(M, a)

    def u(self, a):
        return self.wb.get(U, a)

    def input_rows(self, p):
        rows = []
        for r in (45, 47, 48, 49, 50, 51, 52, 53, 54, 55, 57, 58, 59):
            lab = _s(self.g(f"A{r}"))
            if not lab or (r == 47 and p != 1):
                continue
            row = {"cell": f"C{r}", "label": lab.rstrip(": ").strip(), "unit": _s(self.g(f"E{r}")),
                   "hint": _strip_paren(_s(self.g(f"F{r}"))), "kind": "select" if r == 59 else "number"}
            if row["unit"] == "mm" and "volume" in row["label"].lower():
                row["unit"] = "mm³"  # the workbook labels one sphere volume as mm
            if r == 45:
                row.update(label="Pre-strain φ0", hint="Strain already in the material from earlier steps (wire drawing, previous stations)")
            if r == 59:
                row["options"] = CARBON_OPTIONS
            if r == 48 and p == 8:
                row["k1"] = {"theoretical": clean(self.g("C46")), "simulation": clean(self.g("C47"))}
            rows.append(row)
        auto = []
        a46 = _s(self.g("A46"))
        if a46:
            auto.append({"label": a46.rstrip(": "), "value": clean(self.g("C46")), "unit": _s(self.g("E46")),
                         "hint": _strip_paren(_s(self.g("F46")))})
        a47 = _s(self.g("A47"))
        if a47 and p != 1:
            auto.append({"label": a47.rstrip(": "), "value": clean(self.g("C47")), "unit": "",
                         "hint": _strip_paren(_s(self.g("F47")))})
        return rows, auto

    def checks(self, p):
        out = []
        u = self.u

        def add(title, desc, v, limit, bad, shown, warn=False):
            state = "na" if not _num(v) else ("bad" if bad else ("warn" if warn else "ok"))
            out.append({"title": title, "desc": desc, "value": shown if _num(v) else "—", "limit": limit, "state": state})

        def f(v, d):
            return f"{v:,.{d}f}" if _num(v) else "—"

        if p in (2, 3, 4, 5):
            S = u("E34") if p == 3 else u("E88")
            msg = "" if p == 3 else TR.get(_s(u("F88")), _s(u("F88")))
            add("Danger of kink", "Upset ratio S = free length / diameter. Above 1.8 there is a risk of buckling" + (f". Advice: {msg}" if msg else "") + ".",
                S, "≤ 1.80", _num(S) and S > 1.8, f(S, 2), _num(S) and 1.8 < S <= 2.25)
            xi, xl = (u("E35"), u("F35")) if p == 3 else (u("E89"), u("F89"))
            add("Cracking of the head surface", "Surface strain ξ against the limit for this head shape.", xi,
                f"≤ {f(xl, 0)} %", _num(xi) and _num(xl) and xi > xl, f"{f(xi, 1)} %")
        elif p == 6:
            e, lk = u("E128"), u("E129")
            add("Area change", "Cross-section reduction (d1² − d2²)/d1². Above 30 % the material may upset instead of reduce.",
                e, "≤ 30 %", _num(e) and e > u("F128"), f"{f(e, 1)} %")
            add("Danger of kink", "Free length LK / d1 against the limit of 7.", lk, "≤ 7", _num(lk) and lk > u("F129"), f(lk, 2))
        elif p == 7:
            e, lim = u("E169"), u("F169")
            add("Area change", "Cross-section reduction against the limit set by the carbon content (%C).", e,
                f"≤ {f(lim, 0)} %", _num(e) and _num(lim) and e > lim, f"{f(e, 1)} %")
            if _num(e) and e < 30:
                add("Process choice", "Area change below 30 %: open-die reduction is the better choice.", e, "≥ 30 %", False,
                    f"{f(e, 1)} %", True)
        elif p == 8:
            e, h, hm = u("E207"), u("E208"), u("F208")
            add("Area change", "d1² / d2² against the 75 % limit.", e, "≤ 75 %", _num(e) and e > u("F207"), f"{f(e, 1)} %")
            add("Minimum bottom depth", f"Bottom height H1 must be at least (d2 − d1)/2 = {f(hm, 2)} mm.", h,
                f"≥ {f(hm, 2)} mm", _num(h) and _num(hm) and h < hm, f"{f(h, 2)} mm")
        return out

    def detail(self, p, shape):
        rows = []
        for r in DETAIL.get(p, DETAIL["B"]):
            if r[0] == G:
                rows.append({"group": r[1]})
                continue
            a, lab, unit = r[0], r[1], r[2]
            key = len(r) > 3
            if a == "TRIM":
                a, lab = {17: ("E268", "d1 head diameter"), 16: ("E269", "z square side")}.get(shape, ("E270", "SW wrench width"))
            if lab.startswith("@"):
                lab = _s(self.u(lab[1:])).rstrip(": ")
            v = self.u(a)
            if v is BLANK or v == "" or (v == 0 and not key and a in _SKIP_ZERO):
                continue
            rows.append({"label": lab, "value": clean(v), "unit": unit, "key": key})
        return rows

    def compute(self, p: int, shape: int, material: str, inputs: dict, sweep: str | None = None):
        p = int(p)
        shape = int(shape)
        if p not in PROCESS_SHAPES:
            raise ValueError("Unknown process")
        if shape not in PROCESS_SHAPES[p]:
            shape = PROCESS_SHAPES[p][0]
        inputs = {k: v for k, v in (inputs or {}).items() if k in INPUT_CELLS}
        self.setup(p, shape, material, inputs)
        g = self.g
        rows, auto = self.input_rows(p)
        phi, phi_note = g("S41"), "True strain"
        if p in (2, 5):
            phi = self.u("E80")
        if p == 9:
            phi_note = "Pre-strain φ0 (piercing has no φ)"
        if p == 10:
            phi_note = "Pre-strain φ0 (kf taken at φ = 0.8)"
        chk_label = _s(g("Q54")).rstrip(": ")
        warnings = []
        for a in ("L41", "L45", "L50", "L54"):
            v = g(a)
            if is_err(v):
                warnings.append(f"Check could not run ({v.code})")
            elif v not in (BLANK, "", None):
                warnings.append(str(v).replace(" !", "!"))
        result = {
            "process": p, "shape": shape, "material": material,
            "processName": PROCESSES[p - 1], "shapeName": SHAPE_NAMES[shape],
            "shapes": [{"id": s, "name": SHAPE_NAMES[s]} for s in PROCESS_SHAPES[p]],
            "kf": clean(g("C42")), "n": clean(g("C43")),
            "inputs": rows, "auto": auto,
            "results": {
                "F": clean(g("S45")),
                "W": None if p == 1 else clean(g("S49")),
                "phi": None if p == 1 else clean(phi), "phiNote": "Not applicable" if p == 1 else phi_note,
                "check": None if not chk_label else clean(g("S54")),
                "checkLabel": chk_label or "Check value",
                "checkUnit": "%" if "E)" in chk_label else "",
                "checkNote": ("Upset ratio" if "S)" in chk_label else "Area change") if chk_label else "No ratio for this process",
            },
            "warnings": warnings,
            "checks": self.checks(p),
            "detail": self.detail(p, shape),
            "equations": EQUATIONS.get(p, EQUATIONS["B"]),
        }
        if sweep and isinstance(inputs.get(sweep), (int, float)) and inputs[sweep]:
            base = float(inputs[sweep])
            pts = []
            for i in range(25):
                fct = 0.7 + 0.6 * i / 24
                self.setup(p, shape, material, {**inputs, sweep: base * fct})
                F = g("S45")
                pts.append([base * fct, F if _num(F) else None])
            result["sweep"] = {"cell": sweep, "points": pts}
            self.setup(p, shape, material, inputs)
        return result
