import io

from openpyxl import load_workbook

from strainforge.routes.reports import _filename, build_xlsx


def _rows(data):
    return [[c for c in r if c is not None] for r in load_workbook(io.BytesIO(data)).active.iter_rows(values_only=True)]


def test_numbers_become_numbers_and_formulas_stay_text():
    data = build_xlsx({"title": "=cmd", "meta": [["Date", "24 November 2026"]], "sections": [
        {"title": "Inputs", "columns": ["Input", "Value", "Unit"],
         "rows": [["De", "1,234.5", "mm"], ["t'", "= t", "mm"], ["evil", "=HYPERLINK(\"x\")", ""], {"group": "Stresses"}, ["neg", "−3,404.49", "N/mm²"]]}]})
    wb = load_workbook(io.BytesIO(data))
    ws = wb.active
    cells = [c for row in ws.iter_rows() for c in row if c.value is not None]
    assert not any(c.data_type == "f" for c in cells)
    rows = _rows(data)
    assert ["De", 1234.5, "mm"] in rows
    assert ["neg", -3404.49, "N/mm²"] in rows
    assert ["t'", "= t", "mm"] in rows
    assert ["Stresses"] in rows


def test_limits_and_filename():
    big = {"title": "x", "sections": [{"title": "s", "columns": ["a"] * 50, "rows": [["1"] * 50] * 1000}] * 50}
    rows = _rows(build_xlsx(big))
    assert len(rows) < 1200 + 20 * 4 + 20
    assert _filename("Disc stack A / ../x").startswith("Disc-stack-A-")
    assert _filename("").startswith("strainforge-report-")
