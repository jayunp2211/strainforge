"""Built-in tools checked against the original workbook (values recalculated in a spreadsheet)."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from strainforge.builtin import TOOLS  # noqa: E402
from strainforge.builtin import disc_spring  # noqa: E402
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


def _rows(r):
    return {row[0]: row for row in r["tables"][0]["rows"]}


def test_disc_spring_matches_workbook_example():
    # The workbook's own example: 12 x 5.2 x 0.5, l0 0.9, 51CrV4, load points at l = 0.8 and 0.6
    r = disc_spring.calculate(disc_spring.EXAMPLE)
    rows = _rows(r)
    #            l    s    s/h0  F                   σI                   σII                 σIII                σOM                 rate
    assert close(rows["1"][4], 150.45006158726636) and close(rows["2"][4], 349.6374670689993)
    assert close(rows["2"][5], -2717.0686866135948) and close(rows["2"][6], 1080.0757182384011)
    assert close(rows["2"][7], 1290.7474322879063) and close(rows["2"][8], -1214.1061347089676)
    assert close(rows["Flat"][4], 423.8029903866659) and close(rows["Flat"][5], -3404.492519701434)
    assert close(rows["0"][9], 1737.5922605853302) and close(rows["Flat"][9], 720.465083657332)
    assert r["kpis"][2]["value"] == 357000  # fatigue life, 99 %
    tol = {row[0]: row[1:] for row in r["tables"][1]["rows"]}
    assert tol["De"] == [11.82, 12] and close(tol["Di"][1], 5.32) and close(tol["t"][0], 0.44) and close(tol["l0"][1], 1.0)
    assert all(c["state"] in ("ok",) for c in r["checks"])


def test_disc_spring_flats_stack_and_temperature():
    # Group 3 spring with contact flats, 3 in series x 2 in parallel at 100 °C (workbook recalculated)
    r = disc_spring.calculate({"De": 70, "Di": 35.5, "t": 4, "tr": 3.75, "l0": 5.8, "nS": 3, "nP": 2, "temp": 100,
                               "mode": "l", "P1": 5.35, "P2": 4.45, "P3": 5.0, "lo": "1", "hi": "2", "mat": "1.8159 (51CrV4)"})
    rows = _rows(r)
    assert close(rows["1"][4], 8989.30452361228) and close(rows["2"][4], 23458.7701336842)
    assert close(rows["3"][6], 673.361241594757) and close(rows["Flat"][7], 2005.06158419798)
    assert close(rows["2"][10], 24.6) and close(rows["2"][12], 46917.5402673684)
    assert close(rows["0"][9], 14452.8432330382)
    assert r["kpis"][2]["value"] is None  # upper stress too high for a fatigue estimate, as in the sheet
    assert any(c["title"] == "Set-proof" and c["state"] == "bad" for c in r["checks"])
    tol = {row[0]: row[1:] for row in r["tables"][1]["rows"]}
    assert close(tol["t'"][0], 3.63) and close(tol["t'"][1], 3.79) and close(tol["l0"][0], 5.65)


def test_disc_spring_load_point_modes_agree():
    base = dict(disc_spring.EXAMPLE)
    r = disc_spring.calculate(base)
    for mode, vals in r["auto"]["remap"].items():
        r2 = disc_spring.calculate(dict(base, mode=mode, **vals))
        assert close(_rows(r2)["2"][4], _rows(r)["2"][4], 1e-5), mode


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


def test_sleeve_three_degrees_is_in_range():
    # 3° is the industry norm for short sleeves, so it must not raise the taper-angle warning
    r = calculate({"A": 60, "B": 30, "D": 10, "L": 50, "alpha": 3, "insert": "Carbide"})
    assert next(c for c in r["checks"] if c["title"] == "Taper angle")["state"] == "ok"
    r = calculate({"A": 60, "B": 30, "D": 10, "L": 50, "alpha": 3.5, "insert": "Carbide"})
    assert next(c for c in r["checks"] if c["title"] == "Taper angle")["state"] == "warn"


def test_sleeve_materials():
    base = {"A": 60, "B": 30, "D": 10, "L": 50, "alpha": 3}
    r = calculate(dict(base, case_mat="1.2343", sleeve_mat="1.2709", insert="WC-20Co"))
    assert r["auto"]["E1"] == 210000 and r["auto"]["E3"] == 190000
    assert r["auto"]["E2"] == 500000 and r["auto"]["m2"] == 4.17
    assert set(r["auto"]["hints"]) == {"case_mat", "sleeve_mat", "insert"}
    mats = {row[0]: row for row in r["tables"][0]["rows"]}
    assert mats["Insert"][1] == "Carbide 20%" and mats["Sleeve"][4] == 190000
    # The old "Carbide" value still means the workbook's carbide (15 % Co)
    old = calculate(dict(base, insert="Carbide"))
    assert old["auto"]["E2"] == 550000 and old["auto"]["m2"] == 4.25
    # A weak case steel fails the stress check
    weak = calculate(dict(base, case_mat="1.7225"))
    assert next(c for c in weak["checks"] if c["title"] == "Case stress")["state"] == "bad"
    ok = calculate(dict(base, case_mat="1.2343"))
    assert next(c for c in ok["checks"] if c["title"] == "Case stress")["state"] == "ok"
    # Typed values win over the material
    own = calculate(dict(base, E1=200000))
    assert own["auto"]["E1"] == 200000
