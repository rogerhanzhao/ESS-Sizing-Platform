import inspect

import pytest

pytest.importorskip("svgwrite")

from calb_diagrams import sld_engineering_v2_renderer as renderer_module
from calb_diagrams.sld_engineering_v2_layout import build_sld_engineering_v2_layout_plan
from calb_diagrams.sld_engineering_v2_renderer import render_sld_engineering_v2_svg
from calb_sizing_tool.services.sld_engineering_v2_builder import build_sld_engineering_v2_graph
from tests.unit.test_sld_layout_engine import _build_topology


def _build_plan(sample_excel_path):
    topology = _build_topology(sample_excel_path)
    graph = build_sld_engineering_v2_graph(topology)
    return build_sld_engineering_v2_layout_plan(graph)


def test_engineering_v2_renderer_emits_svg_from_layout_plan(sample_excel_path, tmp_path):
    plan = _build_plan(sample_excel_path)
    svg_path = tmp_path / "sld_engineering_v2.svg"

    result_path, warning = render_sld_engineering_v2_svg(plan, svg_path)

    assert result_path == svg_path
    assert warning is None
    svg_text = svg_path.read_text(encoding="utf-8")
    assert "EQUIPMENT LIST" in svg_text
    assert "Cable Connection Vault" in svg_text
    assert "Step-up Transformer (OIL)" in svg_text
    assert "Power Converter System" in svg_text
    assert "Battery Energy Storage System" in svg_text
    assert "RMU-01" in svg_text
    assert "Transformer Feeder" in svg_text
    assert "Dyn11" in svg_text
    assert "LV Winding 1" in svg_text
    assert "LV Winding 2" in svg_text
    assert "INV-01" in svg_text
    assert "BESS-01" in svg_text
    assert "T-01" in svg_text
    assert "SINGLE LINE DIAGRAM" in svg_text
    assert "DC BUSBAR" not in svg_text
    assert "BUSBAR A" not in svg_text


def test_engineering_v2_renderer_draws_port_anchored_connectors(sample_excel_path, tmp_path):
    plan = _build_plan(sample_excel_path)
    svg_path = tmp_path / "sld_engineering_v2.svg"

    render_sld_engineering_v2_svg(plan, svg_path, show_port_anchors=True)
    svg_text = svg_path.read_text(encoding="utf-8")

    assert 'id="edge-G01-E-RINGIN-TERM-BAY"' in svg_text
    assert 'id="edge-G01-E-TX-LV-LVBUS-W01"' in svg_text
    assert 'id="edge-G01-E-TX-LV-LVBUS-W02"' in svg_text
    assert 'id="edge-G01-F01-E-LVFEEDER-PCS"' in svg_text
    assert 'id="edge-G01-F01-E-PCS-DCIF"' in svg_text
    assert 'id="port-G01-TRANSFORMER-hv_port"' in svg_text
    assert 'id="port-G01-F01-PCS-dc_port"' in svg_text


def test_engineering_v2_renderer_supports_light_and_dark_backgrounds(sample_excel_path, tmp_path):
    dark_plan = _build_plan(sample_excel_path)
    light_plan = build_sld_engineering_v2_layout_plan(
        build_sld_engineering_v2_graph(_build_topology(sample_excel_path)),
        theme="light",
    )
    dark_svg = tmp_path / "dark.svg"
    light_svg = tmp_path / "light.svg"

    render_sld_engineering_v2_svg(dark_plan, dark_svg)
    render_sld_engineering_v2_svg(light_plan, light_svg)

    # Both themes render in professional monochrome B&W (print-ready)
    assert "#ffffff" in dark_svg.read_text(encoding="utf-8")
    assert "#ffffff" in light_svg.read_text(encoding="utf-8")


def test_engineering_v2_renderer_source_is_layout_only():
    source = inspect.getsource(render_sld_engineering_v2_svg)
    assert "build_professional_sld_sheet" in source
    assert "SldTopology" not in source
    assert "SldEngineeringV2Graph" not in source
    assert "ac_output" not in source
    assert "stage13_output" not in source
    assert "session_state" not in source
    assert "st.session_state" not in source


def test_transformer_vector_symbol_is_drawn_as_shapes_not_text():
    source = inspect.getsource(renderer_module._transformer_2w)

    assert "_delta_mark" in source
    assert "_wye_grounded_mark" in source
    assert all(ord(character) < 128 for character in source)
