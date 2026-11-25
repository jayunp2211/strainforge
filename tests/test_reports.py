import io
import re
import zipfile

from openpyxl import load_workbook

from strainforge import builtin, report
from strainforge.calc import PRESETS

META = [("Prepared by", "Test"), ("Workspace", "Shop")]


def _sleeve(units="metric", title="M10 die", notes=""):
    bt = builtin.get("slotted-sleeve-die")
    m = report.tool_model(bt, dict(bt["example"]), report.Units(units))
    return report.finish(m, title, notes, META, "24 November 2026")


def _calc(units="metric"):
    m = report.calc_model(6, 11, "CuZr", PRESETS["6-11"], None, report.Units(units))
    return report.finish(m, "Reduction", "", META, "24 November 2026")


def _values(data, sheet=None):
    wb = load_workbook(io.BytesIO(data))
    ws = wb[sheet] if sheet else wb.active
    return wb, ws, [c for row in ws.iter_rows() for c in row if c.value is not None]


def test_pdf_is_a_real_pdf_and_short():
    for m in (_sleeve(), _calc(), _sleeve("imperial")):
        pdf = report.build_pdf(m)
        assert pdf[:5] == b"%PDF-"
        assert len(re.findall(rb"/Type\s*/Page(?!s)", pdf)) <= 2


def test_every_tool_and_process_builds():
    for slug, bt in builtin.TOOLS.items():
        assert report.build_pdf(report.finish(report.tool_model(bt, dict(bt["example"]), report.Units()), "", "", META, "d"))
        assert report.build_pdf(report.finish(report.tool_model(bt, {}, report.Units()), "", "", META, "d"))  # empty inputs
    for key, inputs in PRESETS.items():
        p, shape = (int(x) for x in key.split("-"))
        m = report.finish(report.calc_model(p, shape, "CuZr", inputs, None, report.Units("imperial")), "", "", META, "d")
        assert report.build_pdf(m)[:5] == b"%PDF-"


def test_units_follow_the_viewer():
    met, imp = _sleeve(), _sleeve("imperial")
    assert met["kpis"][0]["unit"] == "kN" and imp["kpis"][0]["unit"] == "tonf"
    a, b = met["kpis"][0]["value"]["n"], imp["kpis"][0]["value"]["n"]
    assert abs(a / 8.896443230521 - b) < 1e-6
    assert ">1.0" in report.svg_for_pdf('<svg viewBox="0 0 10 10"><text data-qty="25.4" data-unit="mm">25.4</text></svg>', report.Units("imperial"))


def test_excel_numbers_are_numbers_and_text_is_never_a_formula():
    data = report.build_xlsx([_sleeve(title="=HYPERLINK(\"x\")", notes="=1+1")])
    wb, ws, cells = _values(data)
    assert not any(c.data_type == "f" for c in cells)
    assert any(c.value == "=1+1" for c in cells)
    nums = [c for c in cells if isinstance(c.value, float)]
    assert nums and all(c.number_format.startswith("#,##0") for c in nums)


def test_excel_batch_has_overview_and_a_sheet_each():
    data = report.build_xlsx([_sleeve(), _sleeve(), _calc()])
    wb = load_workbook(io.BytesIO(data))
    assert wb.sheetnames[0] == "Overview"
    assert len(wb.sheetnames) == 4 and len(set(n.lower() for n in wb.sheetnames)) == 4
    ov = wb["Overview"]
    assert ov.cell(6, 2).hyperlink is not None


def test_zip_dedupes_names_and_filename():
    z = zipfile.ZipFile(io.BytesIO(report.build_zip([("a.pdf", b"1"), ("a.pdf", b"2"), ("A.pdf", b"3")])))
    assert z.namelist() == ["a.pdf", "a-2.pdf", "A-3.pdf"]
    assert report.filename("Disc stack A / ../x", "pdf").startswith("Disc-stack-A-")
    assert report.filename("", "xlsx").startswith("strainforge-report-")


def test_source_is_validated():
    U = report.Units()
    for bad in (None, {"kind": "tool", "tool": "nope", "values": {}}, {"kind": "tool", "tool": "disc-spring", "values": []}):
        try:
            report.model_from_source(bad, U)
            assert False, bad
        except ValueError:
            pass
    m = report.model_from_source({"kind": "tool", "tool": "disc-spring", "values": {"De": 12, "evil": "x" * 1000}}, U)
    assert m["kind"] == "Disc spring calculator"
    assert report.today_label("<script>") != "<script>"
    assert report.today_label("24 November 2026") == "24 November 2026"


def test_project_report_pdf_and_workbook():
    models = [_sleeve(title="Insert"), _calc(), _sleeve(title="Second insert")]
    info = {"title": "=M10 flange bolt", "description": "Press line 4", "date": "1 May 2026",
            "meta": [("Workspace", "Acme"), ("Started by", "A"), ("Prepared by", "B")]}
    pdf = report.build_project_pdf(info, models)
    assert pdf[:5] == b"%PDF-"
    assert len(re.findall(rb"/Type /Page\b", pdf)) >= 1 + len(models)  # a contents page, then each calculation
    data = report.build_xlsx(models, info)
    wb = load_workbook(io.BytesIO(data))
    assert wb.sheetnames[0] == "Project" and len(wb.sheetnames) == 1 + len(models)
    assert wb["Project"]["A2"].data_type == "s"  # a name starting with = stays text
    one = load_workbook(io.BytesIO(report.build_xlsx(models[:1], info)))
    assert one.sheetnames[0] == "Project"  # a one-calculation project still gets its project sheet
