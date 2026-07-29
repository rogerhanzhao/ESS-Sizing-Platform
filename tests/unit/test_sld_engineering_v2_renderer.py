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
    assert "Dyn11yn11" in svg_text
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
    assert "_wye_mark" in dispatcher_source
    assert "_wye_grounded_mark" not in dispatcher_source

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
    # A single secondary token may not be copied to two independent LV windings.
    assert parse("Dyn11", 2) == ("", [])
    assert parse("Dy11y11", 2) == ("D", ["y11", "y11"])
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
        line for line in svg_text.splitlines() if "Dyn11yn11" in line
    ]
    standalone = [line for line in tx_region if ">Dyn11yn11<" in line]
    assert not standalone, "vector group must not be printed as a duplicate standalone label"


def test_three_winding_product_dy_marks_both_lvs_as_ungrounded_wye(sample_excel_path, tmp_path):
    """A product Dy11y11 must draw two plain Y marks and no neutral earth bars."""
    from tests.unit.test_sld_shared_dc_blocks import _shared_topology
    from calb_sizing_tool.services.sld_engineering_v2_builder import (
        build_sld_engineering_v2_graph as _build_graph,
    )

    topology = _shared_topology(sample_excel_path)
    topology = topology.model_copy(
        update={
            "summary": topology.summary.model_copy(
                update={"transformer_vector_group": "Dy11y11"}
            )
        }
    )
    plan = build_sld_engineering_v2_layout_plan(_build_graph(topology))
    svg_path = tmp_path / "three_winding_dy11y11.svg"
    render_sld_engineering_v2_svg(plan, svg_path)
    svg_text = svg_path.read_text(encoding="utf-8")

    for winding in (1, 2):
        prefix = f'tx-lv-winding-{winding}'
        assert f'id="{prefix}-wye-left"' in svg_text
        assert f'id="{prefix}-wye-right"' in svg_text
        # The wye is a three-arm star: all three arms (incl. the neutral/star-point
        # arm) are drawn — but never an ANSI earth bar.
        assert f'id="{prefix}-neutral-leg"' in svg_text
        assert f'id="{prefix}-earth-bar-1"' not in svg_text
        assert f'id="{prefix}-earth-bar-2"' not in svg_text
        assert f'id="{prefix}-earth-bar-3"' not in svg_text


def test_two_winding_dyn_marks_the_single_lv_as_plain_wye(sample_excel_path, tmp_path):
    """``n`` means neutral brought out; it must never infer neutral earthing."""
    from tests.unit.test_sld_layout_engine import _build_single_winding_topology
    from calb_sizing_tool.services.sld_engineering_v2_builder import (
        build_sld_engineering_v2_graph as _build_graph,
    )

    plan = build_sld_engineering_v2_layout_plan(
        _build_graph(_build_single_winding_topology(sample_excel_path))
    )
    svg_path = tmp_path / "two_winding_dyn11.svg"
    render_sld_engineering_v2_svg(plan, svg_path)
    svg_text = svg_path.read_text(encoding="utf-8")

    prefix = "tx-lv-winding-1"
    assert f'id="{prefix}-wye-left"' in svg_text
    assert f'id="{prefix}-wye-right"' in svg_text
    # Three-arm wye star (neutral/star-point arm included), but no earth bar.
    assert f'id="{prefix}-neutral-leg"' in svg_text
    assert f'id="{prefix}-earth-bar-1"' not in svg_text
    assert f'id="{prefix}-earth-bar-2"' not in svg_text
    assert f'id="{prefix}-earth-bar-3"' not in svg_text


@pytest.mark.parametrize("token", ("y0", "yn0", "z0", "zn0"))
def test_all_wye_family_tokens_never_infer_an_earth_connection(token, tmp_path):
    """Connection and neutral tokens must not fabricate a protection design."""
    import svgwrite

    svg_path = tmp_path / f"winding_{token}.svg"
    drawing = svgwrite.Drawing(str(svg_path), profile="full")
    renderer_module._winding_mark(
        drawing,
        100,
        100,
        token,
        id_prefix="test-winding",
    )
    drawing.save()
    svg_text = svg_path.read_text(encoding="utf-8")

    assert 'id="test-winding-wye-left"' in svg_text
    assert 'id="test-winding-wye-right"' in svg_text
    # Three-arm wye star (neutral/star-point arm included), but no earth bar.
    assert 'id="test-winding-neutral-leg"' in svg_text
    assert 'id="test-winding-earth-bar-1"' not in svg_text
    assert 'id="test-winding-earth-bar-2"' not in svg_text
    assert 'id="test-winding-earth-bar-3"' not in svg_text


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


def test_transformer_vector_group_confirmed_helper():
    confirmed = renderer_module._transformer_vector_group_confirmed
    assert confirmed("Dyn11", 1) is True
    assert confirmed("Dyn11yn11", 2) is True
    assert confirmed("Dy11y11", 2) is True
    # Missing / TBD / wrong LV-token count are all unconfirmed.
    assert confirmed("TBD", 2) is False
    assert confirmed("", 1) is False
    assert confirmed("Dyn11", 2) is False   # one LV token, but two windings
    assert confirmed("Dyn11yn11", 1) is False  # two LV tokens, but one winding


def _build_plan_unconfirmed(sample_excel_path):
    from calb_sizing_tool.schemas.diagram_inputs import SldRenderOptions
    from calb_sizing_tool.schemas.sld_render_input import SldInputOverride, legacy_sld_override_preset
    from calb_sizing_tool.services.sld_input_builder import build_sld_canonical_input
    from calb_sizing_tool.services.sld_topology_builder import build_sld_topology
    from tests.unit.test_sld_topology_builder import _build_run_bundle, _make_ac_snapshot

    run_bundle = _build_run_bundle(sample_excel_path)
    override_payload = legacy_sld_override_preset()
    override_payload.pop("transformer_vector_group", None)  # leave it unconfirmed -> TBD
    override_payload["dc_block_voltage_v"] = 1500.0
    override_payload["dc_blocks_per_feeder"] = [1, 1, 1, 1]
    canonical = build_sld_canonical_input(
        run_bundle=run_bundle,
        ac_snapshot=_make_ac_snapshot(),
        options=SldRenderOptions(
            group_index=1,
            override_mode=True,
            overrides=SldInputOverride.model_validate(override_payload),
        ),
        validation_mode="draft",
    )
    assert canonical.transformer_vector_group == "TBD"
    graph = build_sld_engineering_v2_graph(build_sld_topology(canonical))
    return build_sld_engineering_v2_layout_plan(graph)


def test_unconfirmed_vector_group_draws_default_windings_annotated_assumed(sample_excel_path, tmp_path):
    """Owner decision 2026-07-29: an unconfirmed vector group is drawn with the
    real winding symbol using the standard default (Dyn11 / Dyn11yn11) and
    annotated as assumed — no red 'NOT A DRAWING' placeholder box. The
    formal-readiness gate independently keeps the sheet a watermarked concept."""
    plan = _build_plan_unconfirmed(sample_excel_path)
    svg_path = tmp_path / "sld_tbd.svg"
    render_sld_engineering_v2_svg(plan, svg_path)
    svg = svg_path.read_text(encoding="utf-8")
    # The old red placeholder box is gone.
    assert "UNCONFIRMED" not in svg
    assert "NOT A DRAWING" not in svg
    # Real winding circles are drawn with a default vector group…
    assert 'id="tx-hv-winding"' in svg
    assert 'id="tx-lv-winding-1"' in svg
    # …and the drawing honestly states the group is an assumed default.
    assert "assumed (standard default" in svg
    assert "Dyn11" in svg
    # The wye is a full three-arm star; still no fabricated earth bar.
    assert 'id="tx-lv-winding-1-wye-left"' in svg
    assert 'id="tx-lv-winding-1-neutral-leg"' in svg
    assert 'id="tx-lv-winding-1-earth-bar-1"' not in svg


def _build_two_winding_dyn11(sample_excel_path):
    from calb_sizing_tool.schemas.diagram_inputs import SldRenderOptions
    from calb_sizing_tool.schemas.sld_render_input import SldInputOverride, legacy_sld_override_preset
    from calb_sizing_tool.services.sld_input_builder import build_sld_canonical_input
    from calb_sizing_tool.services.sld_topology_builder import build_sld_topology
    from tests.unit.test_sld_topology_builder import _build_run_bundle, _make_ac_snapshot

    run_bundle = _build_run_bundle(sample_excel_path)
    ac_snapshot = _make_ac_snapshot()
    ac_output = dict(ac_snapshot.output)
    ac_output.update({
        "pcs_per_block": 2, "pcs_kw": 2500.0, "block_size_mw": 5.0, "transformer_mva": 5.0,
        "lv_winding_count": 1, "transformer_topology": "two_winding",
        "dc_allocation_plan": [{"ac_block_index": 1, "dc_blocks_total": 2, "feeder_allocations": [1, 1]}],
    })
    override_payload = legacy_sld_override_preset()
    override_payload["transformer_vector_group"] = "Dyn11"
    override_payload["dc_block_voltage_v"] = 1500.0
    override_payload["dc_blocks_per_feeder"] = [1, 1]
    canonical = build_sld_canonical_input(
        run_bundle=run_bundle,
        ac_snapshot=ac_snapshot.model_copy(update={"output": ac_output}),
        options=SldRenderOptions(group_index=1, override_mode=True,
                                 overrides=SldInputOverride.model_validate(override_payload)),
        validation_mode="strict",
    )
    graph = build_sld_engineering_v2_graph(build_sld_topology(canonical))
    return build_sld_engineering_v2_layout_plan(graph)


def test_three_winding_dyn11yn11_export_is_plain_y_no_earth_two_busbars(sample_excel_path, tmp_path, monkeypatch):
    grounds: list = []
    wyes: list = []
    real_ground, real_wye = renderer_module._ground, renderer_module._wye_mark
    monkeypatch.setattr(renderer_module, "_ground",
                        lambda dwg, x, y: (grounds.append((x, y)), real_ground(dwg, x, y))[1])
    monkeypatch.setattr(renderer_module, "_wye_mark",
                        lambda *a, **k: (wyes.append(a[1:3]), real_wye(*a, **k))[1])
    plan = _build_plan(sample_excel_path)  # Dyn11yn11 (three-winding, 2 LV)
    svg_path = tmp_path / "sld_3w.svg"
    render_sld_engineering_v2_svg(plan, svg_path)
    svg = svg_path.read_text(encoding="utf-8")
    # Two independent LV secondary windings, no LV bus tie.
    assert 'id="tx-hv-winding"' in svg
    assert 'id="tx-lv-winding-1"' in svg and 'id="tx-lv-winding-2"' in svg
    assert "NO LV BUS TIE" in svg
    assert "LV-A DISTRIBUTION SECTION" in svg and "LV-B DISTRIBUTION SECTION" in svg
    # Plain Y windings were drawn (yn tokens render as wye, never an earth bar).
    assert len(wyes) >= 2
    three_w_grounds = len(grounds)
    # PNG renders.
    import cairosvg
    png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), background_color="white")
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 1000

    # Two-winding Dyn11 baseline: exactly one LV winding, and the number of
    # ground symbols is identical — proving the extra LV secondary adds NO earth.
    grounds.clear(); wyes.clear()
    plan2 = _build_two_winding_dyn11(sample_excel_path)
    svg2_path = tmp_path / "sld_2w.svg"
    render_sld_engineering_v2_svg(plan2, svg2_path)
    svg2 = svg2_path.read_text(encoding="utf-8")
    assert 'id="tx-lv-winding-1"' in svg2
    assert 'id="tx-lv-winding-2"' not in svg2   # single LV winding
    assert len(wyes) >= 1
    two_w_grounds = len(grounds)
    # The transformer LV windings contribute no ground symbol in either topology.
    assert three_w_grounds == two_w_grounds
