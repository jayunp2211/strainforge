"""Run with: python -m pytest tests  (or python tests/test_calc.py)"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from strainforge.calc import PRESETS, PROCESS_SHAPES, Calculator  # noqa: E402

REF = {"name": "Ref", "C": 777, "n": 0.164, "Rm": None}


def test_reference_closed_upset():
    r = Calculator([REF]).compute(2, 2, "Ref", {"C45": 0.05, "C48": 0.15, "C49": 14, "C50": 24, "C51": 2.2, "C52": 14})
    assert math.isclose(r["results"]["F"], 554.074, abs_tol=0.01)
    assert math.isclose(r["results"]["W"], 0.98721, abs_tol=1e-4)


def test_every_preset_gives_a_load():
    c = Calculator()
    for p, shapes in PROCESS_SHAPES.items():
        for s in shapes:
            r = c.compute(p, s, "CuZr", PRESETS.get(f"{p}-{s}", {}))
            assert isinstance(r["results"]["F"], float) and r["results"]["F"] > 0, (p, s)


if __name__ == "__main__":
    test_reference_closed_upset()
    test_every_preset_gives_a_load()
    print("ok")
