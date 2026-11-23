"""Safe formulas for owner-built calculators.

A calculator is a spec: named inputs, optional material (C, n, Rm), and outputs
whose formulas may use the inputs, the material and earlier outputs.  Formulas
are parsed with Python's ast and only a small whitelist of nodes is allowed, so
nothing in a formula can reach the interpreter.  Excel habits work: ^ is power,
IF(cond, a, b), PI(), and function names are case-insensitive.
"""
import ast
import math
import re

KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,23}$")
MAX_FORMULA = 400
MAX_INPUTS = 30
MAX_OUTPUTS = 30


class FormulaError(ValueError):
    pass


def _rad(f):
    return lambda x: f(math.radians(x))


FUNCS = {
    "sqrt": math.sqrt, "abs": abs, "min": min, "max": max, "exp": math.exp,
    "ln": math.log, "log": math.log10, "log10": math.log10,
    "sin": _rad(math.sin), "cos": _rad(math.cos), "tan": _rad(math.tan),
    "asin": lambda x: math.degrees(math.asin(x)), "acos": lambda x: math.degrees(math.acos(x)),
    "atan": lambda x: math.degrees(math.atan(x)),
    "round": lambda x, d=0: round(x, int(d)), "floor": math.floor, "ceil": math.ceil,
    "pi": lambda: math.pi,
}
CONSTS = {"PI": math.pi, "E": math.e}
MATERIAL_VARS = ("C", "n", "Rm")
RESERVED = {k.lower() for k in FUNCS} | {k.lower() for k in CONSTS} | {"if", "kf", "and", "or", "not"}

_BIN = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b, ast.Pow: lambda a, b: a ** b, ast.Mod: lambda a, b: a % b}
_CMP = {ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b, ast.Gt: lambda a, b: a > b,
        ast.GtE: lambda a, b: a >= b, ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b}


def parse(src: str) -> ast.Expression:
    src = (src or "").strip()
    if not src:
        raise FormulaError("Formula is empty.")
    if len(src) > MAX_FORMULA:
        raise FormulaError(f"Keep formulas under {MAX_FORMULA} characters.")
    py = src.replace("^", "**").replace("<>", "!=")
    py = re.sub(r"(?<![<>!=])=(?!=)", "==", py)  # Excel-style a=b comparisons
    try:
        tree = ast.parse(py, mode="eval")
    except SyntaxError:
        raise FormulaError("Check the formula: brackets, operators or commas don't line up.")
    for node in ast.walk(tree):
        ok = isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Compare, ast.BoolOp, ast.Name, ast.Load,
                               ast.Call, ast.IfExp, ast.Constant, ast.And, ast.Or, ast.Not, ast.USub, ast.UAdd,
                               *_BIN, *_CMP))
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            ok = False
        if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Name) or node.keywords):
            ok = False
        if not ok:
            raise FormulaError("Only numbers, names, + - * / ^, comparisons and functions are allowed.")
    return tree


def names_in(tree) -> set[str]:
    called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and id(n) not in called}


def calls_in(tree) -> set[str]:
    return {n.func.id.lower() for n in ast.walk(tree) if isinstance(n, ast.Call)}


def _num(v):
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    return float(v)


def evaluate(tree: ast.Expression, env: dict) -> float:
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant):
            return float(n.value)
        if isinstance(n, ast.Name):
            if n.id in env:
                return env[n.id]
            if n.id.upper() in CONSTS:
                return CONSTS[n.id.upper()]
            raise FormulaError(f"Unknown name {n.id}.")
        if isinstance(n, ast.UnaryOp):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else v if isinstance(n.op, ast.UAdd) else _num(not v)
        if isinstance(n, ast.BinOp):
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 1000:
                raise FormulaError("Exponent too large.")
            return _BIN[type(n.op)](a, b)
        if isinstance(n, ast.Compare):
            left = ev(n.left)
            for op, comp in zip(n.ops, n.comparators):
                right = ev(comp)
                if not _CMP[type(op)](left, right):
                    return 0.0
                left = right
            return 1.0
        if isinstance(n, ast.BoolOp):
            vals = (ev(v) for v in n.values)
            return _num(all(vals) if isinstance(n.op, ast.And) else any(vals))
        if isinstance(n, ast.IfExp):
            return ev(n.body) if ev(n.test) else ev(n.orelse)
        if isinstance(n, ast.Call):
            name = n.func.id.lower()
            if name == "if":
                if len(n.args) != 3:
                    raise FormulaError("IF takes three parts: IF(condition, value if true, value if false).")
                return ev(n.args[1]) if ev(n.args[0]) else ev(n.args[2])
            if name == "kf":
                if "C" not in env:
                    raise FormulaError("kf() needs a material on this calculator.")
                phi = ev(n.args[0]) if n.args else 0.0
                return env["C"] * max(phi, 0.0) ** env["n"]
            fn = FUNCS.get(name)
            if not fn:
                raise FormulaError(f"Unknown function {n.func.id}().")
            return float(fn(*[ev(a) for a in n.args]))
        raise FormulaError("Unsupported formula.")

    try:
        v = ev(tree)
    except FormulaError:
        raise
    except ZeroDivisionError:
        raise FormulaError("Division by zero.")
    except (ValueError, OverflowError, TypeError):
        raise FormulaError("Out of range for this function.")
    if isinstance(v, complex) or not math.isfinite(v):
        raise FormulaError("Result is not a real number.")
    return v


# ------------------------------------------------------------------ specs

def _txt(v, n):
    return str(v or "").strip()[:n]


def clean_spec(raw: dict) -> dict:
    """Validate an editor submission. Raises FormulaError with a message for the owner."""
    if not isinstance(raw, dict):
        raise FormulaError("The calculator could not be read.")
    use_mat = bool(raw.get("material"))
    inputs, outputs, seen = [], [], set()
    for i, r in enumerate(raw.get("inputs") or []):
        if not isinstance(r, dict):
            continue
        key = _txt(r.get("key"), 24)
        if not key:
            continue
        if not KEY_RE.match(key):
            raise FormulaError(f"Input name “{key}” must start with a letter and use only letters, digits and _.")
        if key.lower() in RESERVED or (use_mat and key in MATERIAL_VARS) or key in seen:
            raise FormulaError(f"The name “{key}” is already taken. Pick another.")
        try:
            default = float(str(r.get("default") or 0).replace(",", "."))
        except ValueError:
            raise FormulaError(f"Default for {key} must be a number.")
        seen.add(key)
        inputs.append({"key": key, "label": _txt(r.get("label"), 60) or key, "unit": _txt(r.get("unit"), 16),
                       "default": default, "hint": _txt(r.get("hint"), 140)})
    if len(inputs) > MAX_INPUTS:
        raise FormulaError(f"Up to {MAX_INPUTS} inputs.")
    known = set(seen) | (set(MATERIAL_VARS) if use_mat else set())
    for r in raw.get("outputs") or []:
        if not isinstance(r, dict):
            continue
        key, formula = _txt(r.get("key"), 24), _txt(r.get("formula"), MAX_FORMULA)
        if not key and not formula:
            continue
        if not KEY_RE.match(key):
            raise FormulaError(f"Result name “{key}” must start with a letter and use only letters, digits and _.")
        if key.lower() in RESERVED or key in known:
            raise FormulaError(f"The name “{key}” is already taken. Pick another.")
        try:
            tree = parse(formula)
        except FormulaError as e:
            raise FormulaError(f"{key}: {e}")
        unknown = sorted(n for n in names_in(tree) if n not in known and n.upper() not in CONSTS)
        if unknown:
            raise FormulaError(f"{key} uses {', '.join(unknown)}, which isn't an input or an earlier result.")
        bad = sorted(c for c in calls_in(tree) if c not in FUNCS and c not in ("if", "kf"))
        if bad:
            raise FormulaError(f"{key} uses unknown function {bad[0]}().")
        if "kf" in calls_in(tree) and not use_mat:
            raise FormulaError(f"{key} uses kf(), so turn on “Uses a material”.")
        try:
            dec = max(0, min(6, int(r.get("decimals") if r.get("decimals") not in (None, "") else 2)))
        except (TypeError, ValueError):
            dec = 2
        known.add(key)
        outputs.append({"key": key, "label": _txt(r.get("label"), 60) or key, "unit": _txt(r.get("unit"), 16),
                        "formula": formula, "decimals": dec, "main": bool(r.get("main"))})
    if not outputs:
        raise FormulaError("Add at least one result with a formula.")
    if len(outputs) > MAX_OUTPUTS:
        raise FormulaError(f"Up to {MAX_OUTPUTS} results.")
    if not any(o["main"] for o in outputs):
        outputs[0]["main"] = True
    return {"material": use_mat, "inputs": inputs, "outputs": outputs, "notes": _txt(raw.get("notes"), 2000)}


def run(spec: dict, values: dict, material: dict | None = None) -> list[dict]:
    """Evaluate every output. Errors stay on the output they belong to."""
    env = {}
    for i in spec["inputs"]:
        v = values.get(i["key"], i["default"]) if isinstance(values, dict) else i["default"]
        try:
            v = float(str(v).replace(",", "."))
        except ValueError:
            v = float("nan")
        env[i["key"]] = v
    if spec.get("material") and material:
        env.update(C=float(material["C"]), n=float(material["n"]),
                   Rm=float(material["Rm"]) if material.get("Rm") is not None else float("nan"))
    out = []
    for o in spec["outputs"]:
        row = {k: o[k] for k in ("key", "label", "unit", "decimals", "main")}
        try:
            bad = [k for k, v in env.items() if isinstance(v, float) and math.isnan(v) and k in names_in(parse(o["formula"]))]
            if bad:
                raise FormulaError(f"Enter a number for {', '.join(bad)}.")
            row["value"] = env[o["key"]] = evaluate(parse(o["formula"]), env)
        except FormulaError as e:
            row["error"] = str(e)
            env[o["key"]] = float("nan")
        out.append(row)
    return out


EXAMPLE = {
    "material": True,
    "inputs": [
        {"key": "d0", "label": "Wire diameter", "unit": "mm", "default": 10, "hint": ""},
        {"key": "L0", "label": "Cut length", "unit": "mm", "default": 25, "hint": ""},
        {"key": "dh", "label": "Head diameter", "unit": "mm", "default": 18, "hint": ""},
        {"key": "mu", "label": "Friction factor", "unit": "", "default": 0.12, "hint": "0.08 to 0.15 for phosphated wire"},
    ],
    "outputs": [
        {"key": "V", "label": "Slug volume", "unit": "mm³", "formula": "PI()*d0^2/4*L0", "decimals": 0, "main": False},
        {"key": "h", "label": "Head height", "unit": "mm", "formula": "V/(PI()*dh^2/4)", "decimals": 2, "main": False},
        {"key": "phi", "label": "Logarithmic strain", "unit": "", "formula": "ln(L0/h)", "decimals": 3, "main": False},
        {"key": "F", "label": "Upsetting force", "unit": "kN",
         "formula": "kf(phi)*PI()*dh^2/4*(1+mu*dh/(3*h))/1000", "decimals": 1, "main": True},
    ],
    "notes": "Open upsetting estimate with Siebel's friction term.",
}
