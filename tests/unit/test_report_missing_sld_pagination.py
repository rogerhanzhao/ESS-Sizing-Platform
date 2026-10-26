"""Missing SLD status stays in flow; available figures keep their dedicated page."""
import base64
import io

from docx import Document
import pytest

from calb_sizing_tool.reporting.report_context import build_report_context
from calb_sizing_tool.reporting.report_v2 import export_report_v2_1


@pytest.mark.parametrize("source", ["missing", "png", "svg"])
def test_sld_section_only_reserves_a_page_for_an_available_drawing(tmp_path, monkeypatch, source):
    monkeypatch.setenv("CALB_OUTPUTS_DIR", str(tmp_path))
    ctx = build_report_context({}, {
        "stage13_output": dict(project_name="SLD pagination", poi_power_req_mw=10,
            poi_energy_req_mwh=40, project_life_years=20, cycles_per_year=365, poi_guarantee_year=0),
        "stage2": {"container_count": 8},
        "ac_output": dict(num_blocks=2, pcs_per_block=2, pcs_kw=2500, block_size_mw=5,
            dc_blocks_per_ac=4, dc_blocks_total=8, pcs_count_total=4, total_ac_mw=10),
    }, {})
    if source == "png":
        ctx.sld_pro_png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=")
    elif source == "svg":
        ctx.sld_preview_svg_bytes = (
            b'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="250">'
            b'<rect x="1" y="1" width="598" height="248" fill="white" stroke="black"/>'
            b'<text x="20" y="50">Test SLD</text></svg>')
    document = Document(io.BytesIO(export_report_v2_1(ctx)))
    index = next(i for i, p in enumerate(document.paragraphs) if p.text == "7.  Single Line Diagram")
    assert bool(document.paragraphs[index-1]._p.xpath('.//w:br[@w:type="page"]')) is (source != "missing")
    next_index = next(i for i, p in enumerate(document.paragraphs) if p.text.startswith("8.  Typical AC Block"))
    assert bool(document.paragraphs[next_index-1]._p.xpath('.//w:br[@w:type="page"]')) is (source != "missing")
    section = document.paragraphs[index:next_index]
    figures = sum(len(p._p.xpath('.//w:drawing')) for p in section)
    assert figures == (0 if source == "missing" else 1)
    assert any("SLD not generated" in p.text for p in section) is (source == "missing")
