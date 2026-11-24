"""Built-in tools checked against the original workbook (values recalculated in a spreadsheet)."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from strainforge.builtin import TOOLS  # noqa: E402
from strainforge.builtin.sleeve import calculate  # noqa: E402


def steps(r):
    return {d["label"]: d["value"] for d in r["steps"] if "value" in d}


def close(a, b, rel=2e-6):
    return math.isclose(a, b, rel_tol=rel)


def test_sleeve_matches_workbook_example():
    # A 60, B 30, D 10, L 50, α 2.5°: the training example (C 20.82, Z 0.21, L2 2.4)
    r = calculate({"A": 60, "B": 30, "D": 10, "L": 50, "alpha": 2.5, "insert": "Carbide"})
    s = steps(r)
    assert close(s["ØC used"], 20.820662813657)
    assert close(s["Z = B · 0.007"], 0.21)
    assert close(s["L2 = Z · 0.5 / tan α"], 2.40489538258528)
    assert close(s["K3"], 0.373427112747828)
    assert close(s["ΔD decrease of insert bore"], 0.0349891795874937)
    assert close(s["ΔA increase of case OD"], 0.0978559376064322)
    assert close(s["pB radial pressure"], 513.743672433769)
    assert close(s["F disassemble"], 136.394923773429, 1e-5)  # sheet uses π = 3.1416
    assert close(s["pi max"], 1202.97849406486)
    assert close(s["σv case"], 1198.7352356788)
    # Assembly force includes tan α (the sheet dropped it): 513.74·30·50·(0.03 + tan 2.5°)·π/1000
    assert close(s["F assemble"], 513.743672433769 * 30 * 50 * (0.03 + math.tan(math.radians(2.5))) * math.pi / 1000)
    assert all(c["state"] == "ok" for c in r["checks"])


def test_sleeve_long_sleeve_case():
    r = calculate({"A": 80, "B": 38, "D": 12, "L": 70, "alpha": 0.5, "insert": "Carbide"})
    s = steps(r)
    assert close(s["ØC used"], 26.3362867542104)
    assert close(s["L2 = Z · 0.5 / tan α"], 15.2402904671982)
    assert close(s["pB radial pressure"], 534.546562827436)
    assert close(s["pi max"], 1277.37086762138)


def test_sleeve_flags_bad_geometry():
    r = calculate({"A": 40, "B": 25, "D": 10, "L": 50, "alpha": 2.5})
    bad = {c["title"] for c in r["checks"] if c["state"] == "bad"}
    assert {"Minimum diameter ratio", "Sleeve OD"} <= bad
    assert r["warnings"]
    assert calculate({"A": 60, "B": 30})["kpis"] == []
    assert calculate({"A": 60, "B": 30, "D": 10, "L": 50, "alpha": 2.5, "C": 35})["warnings"]


def test_steel_insert_and_override():
    r = calculate({"A": 60, "B": 30, "D": 10, "L": 50, "alpha": 2.5, "insert": "Steel", "C": 21})
    assert r["auto"]["E2"] == 210000 and r["auto"]["m2"] == 3.33
    assert steps(r)["ØC used"] == 21
    bore = next(v for v in r["values"] if v["label"].startswith("Insert bore"))
    assert close(bore["value"], 10.07)


def test_every_tool_runs_its_example():
    for t in TOOLS.values():
        r = t["calculate"](t["example"])
        assert r["kpis"] and r["figures"], t["slug"]
        assert {i["key"] for i in t["inputs"]} == set(t["example"]), t["slug"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
