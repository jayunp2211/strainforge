import math

import pytest

from strainforge.formula import EXAMPLE, FormulaError, clean_spec, evaluate, parse, run


def ev(src, **env):
    return evaluate(parse(src), env)


def test_excel_style():
    assert ev("2^3") == 8
    assert ev("PI()*2") == pytest.approx(2 * math.pi)
    assert ev("IF(a>1, 10, 1/0)", a=2) == 10
    assert ev("IF(a=2, 1, 0)", a=2) == 1
    assert ev("SQRT(16)+max(1,4)") == 8
    assert ev("a<>b", a=1, b=2) == 1


@pytest.mark.parametrize("src", ["__import__('os')", "a.b", "'x'", "[1]", "f(x=1)", "(lambda: 1)()", "a[0]"])
def test_rejects_unsafe(src):
    with pytest.raises(FormulaError):
        ev(src, a=1)


def test_errors_are_friendly():
    with pytest.raises(FormulaError, match="Division by zero"):
        ev("1/0")
    with pytest.raises(FormulaError, match="Exponent"):
        ev("9^9^9")
    with pytest.raises(FormulaError):
        ev("sqrt(-1)")


def test_example_runs():
    spec = clean_spec(EXAMPLE)
    out = {o["key"]: o for o in run(spec, {}, {"C": 777, "n": 0.164, "Rm": None})}
    V = math.pi * 100 / 4 * 25
    h = V / (math.pi * 18 ** 2 / 4)
    assert out["h"]["value"] == pytest.approx(h)
    phi = math.log(25 / h)
    assert out["F"]["value"] == pytest.approx(777 * phi ** 0.164 * math.pi * 81 * (1 + 0.12 * 18 / (3 * h)) / 1000)
    assert out["F"]["main"]


def test_spec_validation():
    with pytest.raises(FormulaError, match="isn't an input"):
        clean_spec({"inputs": [{"key": "a"}], "outputs": [{"key": "x", "formula": "a*b"}]})
    with pytest.raises(FormulaError, match="taken"):
        clean_spec({"inputs": [{"key": "a"}, {"key": "a"}], "outputs": [{"key": "x", "formula": "a"}]})
    with pytest.raises(FormulaError, match="material"):
        clean_spec({"inputs": [{"key": "a"}], "outputs": [{"key": "x", "formula": "kf(a)"}]})


def test_bad_input_stays_on_output():
    spec = clean_spec({"inputs": [{"key": "a", "default": 1}], "outputs": [{"key": "x", "formula": "1/a"}, {"key": "y", "formula": "2"}]})
    out = run(spec, {"a": 0})
    assert "error" in out[0] and out[1]["value"] == 2
