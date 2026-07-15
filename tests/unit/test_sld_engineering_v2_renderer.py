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
    assert "LV-A DISTRIBUTION SECTION" in svg_text
    assert "LV-B DISTRIBUTION SECTION" in svg_text
    assert "NO LV BUS TIE" in svg_text
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
    # The winding-mark dispatcher owns the shape selection…
    dispatcher_source = inspect.getsource(renderer_module._winding_mark)
    assert "_delta_mark" in dispatcher_source
    assert "_wye_grounded_mark" in dispatcher_source
    assert "_wye_mark" in dispatcher_source

    # …and both transformer symbols derive their marks from the vector group.
    for symbol in (renderer_module._transformer_2w,
                   renderer_module._transformer_split_secondary):
        source = inspect.getsource(symbol)
        assert "_parse_vector_group" in source
        assert "_winding_mark" in source
        assert all(ord(character) < 128 for character in source)


def test_parse_vector_group_tokens():
    parse = renderer_module._parse_vector_group

    assert parse("Dyn11", 1) == ("D", ["yn11"])
    # A single secondary token applies to both identical LV windings.
    assert parse("Dyn11", 2) == ("D", ["yn11", "yn11"])
    assert parse("YNd11y0", 2) == ("YN", ["d11", "y0"])
    # Unparsable input falls back to text annotation (no symbol guessing).
    assert parse("", 2) == ("", [])
    assert parse("???", 2) == ("", [])


def _circle_by_id(svg_text, circle_id):
    import re as _re
    match = _re.search(
        rf'<circle[^>]*id="{circle_id}"[^>]*/?>', svg_text
    ) or _re.search(rf'<circle[^>]*id="{circle_id}"[^>]*>', svg_text)
    assert match, f"circle {circle_id} not found"
    tag = match.group(0)
    cx = float(_re.search(r'cx="([-\d.]+)"', tag).group(1))
    cy = float(_re.search(r'cy="([-\d.]+)"', tag).group(1))
    r = float(_re.search(r'r="([-\d.]+)"', tag).group(1))
    return cx, cy, r


def test_three_winding_transformer_circles_interlock(sample_excel_path, tmp_path):
    """IEC/ANSI three-winding symbol: three equal circles, every pair overlapping —
    not three detached devices floating apart (the defect recorded by the
    2026-07-15 audit)."""
    import math

    from tests.unit.test_sld_shared_dc_blocks import _shared_topology
    from calb_sizing_tool.services.sld_engineering_v2_builder import (
        build_sld_engineering_v2_graph as _build_graph,
    )

    graph = _build_graph(_shared_topology(sample_excel_path))
    plan = build_sld_engineering_v2_layout_plan(graph)
    svg_path = tmp_path / "three_winding.svg"
    render_sld_engineering_v2_svg(plan, svg_path)
    svg_text = svg_path.read_text(encoding="utf-8")

    hv = _circle_by_id(svg_text, "tx-hv-winding")
    lv1 = _circle_by_id(svg_text, "tx-lv-winding-1")
    lv2 = _circle_by_id(svg_text, "tx-lv-winding-2")

    # Equal radii — one device, not a big primary with satellite secondaries.
    assert hv[2] == lv1[2] == lv2[2]
    # Every pair of circles overlaps (centre distance < sum of radii).
    for a, b in ((hv, lv1), (hv, lv2), (lv1, lv2)):
        distance = math.hypot(a[0] - b[0], a[1] - b[1])
        assert distance < a[2] + b[2], f"circles do not interlock: {a} vs {b}"
    # HV on top, secondaries side by side below.
    assert hv[1] < lv1[1] == lv2[1]
    assert lv1[0] < hv[0] < lv2[0]

    # The vector group is printed exactly once at the transformer (nameplate);
    # the old renderer printed a second standalone copy.
    tx_region = [
        line for line in svg_text.splitlines() if "Dyn11" in line
    ]
    standalone = [line for line in tx_region if ">Dyn11<" in line]
    assert not standalone, "vector group must not be printed as a duplicate standalone label"


def test_two_winding_transformer_circles_interlock(sample_excel_path, tmp_path):
    import math

    plan = _build_plan(sample_excel_path)
    svg_path = tmp_path / "two_winding.svg"
    render_sld_engineering_v2_svg(plan, svg_path)
    svg_text = svg_path.read_text(encoding="utf-8")

    hv = _circle_by_id(svg_text, "tx-hv-winding")
    lv = _circle_by_id(svg_text, "tx-lv-winding-1")
    assert hv[2] == lv[2]
    distance = math.hypot(hv[0] - lv[0], hv[1] - lv[1])
    assert distance < hv[2] + lv[2]


def test_rendered_svg_quality_gate_catches_planted_defects():
    from calb_diagrams.sld_engineering_v2_validation import validate_rendered_sld_svg

    bad_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2000 1160">'
        '<circle id="tx-hv-winding" cx="1000" cy="480" r="28"/>'
        '<circle id="tx-lv-winding-1" cx="1000" cy="600" r="20"/>'
        '<text class="label" x="900" y="1100">stray label</text>'
        "</svg>"
    )
    issue_kinds = {issue.issue_id.split(":")[0] for issue in validate_rendered_sld_svg(bad_svg)}
    assert "winding_circles_unequal" in issue_kinds
    assert "winding_circles_detached" in issue_kinds
    assert "text_in_title_block" in issue_kinds


def test_renderer_rejects_missing_secondary_branch(sample_excel_path, tmp_path):
    """A transformer declaring 2 LV windings while the PCS groups resolve to 1
    must fail loudly instead of silently drawing a single secondary."""
    import dataclasses

    from tests.unit.test_sld_shared_dc_blocks import _shared_topology
    from calb_sizing_tool.services.sld_engineering_v2_builder import (
        build_sld_engineering_v2_graph as _build_graph,
    )

    graph = _build_graph(_shared_topology(sample_excel_path))
    plan = build_sld_engineering_v2_layout_plan(graph)

    broken_boxes = tuple(
        dataclasses.replace(
            box, attributes={**box.attributes, "lv_winding_index": 1}
        )
        if box.node_type == "pcs"
        else box
        for box in plan.boxes
    )
    broken_plan = dataclasses.replace(plan, boxes=broken_boxes)

    with pytest.raises(ValueError, match="declares 2 LV windings"):
        render_sld_engineering_v2_svg(broken_plan, tmp_path / "broken.svg")
