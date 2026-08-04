"""Geometry tests for the bilateral 4+4 AC Block layout engine.

Owner-confirmed concept (docs/CLAUDE_HANDOFF_10MW_8PCS_8DC_2026-07-24.md §1-§2,
reaffirmed 2026-08-03 as the single-axis / 一字型 arrangement):
central vertical 40 ft AC Block, west 4-DC field + east 4-DC field, each a 2x2
``田`` of two mirrored back-to-back pairs; ~18.79 m x 15.12 m equipment envelope
(the north-south pair gap is the DC EQUIPMENT-END clearance, owner 2026-08-03).
The removed single-row eight-DC draft must not reappear.
"""
from __future__ import annotations

import pytest

from calb_diagrams.ac_block_bilateral_layout import (
    AC40_STATION_LENGTH_M,
    LAYOUT_VARIANT,
    compute_bilateral_layout,
    render_bilateral_plan_svg,
)


def _overlap(a, b) -> bool:
    return (
        a.x_m < b.x_m + b.width_m
        and b.x_m < a.x_m + a.width_m
        and a.y_m < b.y_m + b.height_m
        and b.y_m < a.y_m + a.height_m
    )


def test_envelope_matches_recorded_concept():
    layout = compute_bilateral_layout(8)
    assert layout.layout_variant == LAYOUT_VARIANT
    # Recorded concept envelope ~ 18.79 m x 15.12 m (handoff §2 + owner 2026-08-03).
    assert layout.envelope_w_m == pytest.approx(18.790, abs=0.001)
    # Owner ruling 2026-08-03: the two pairs stack north-south, so the touching
    # faces are DC END faces and one of them is always the EQUIPMENT END
    # (liquid-cooling + fan grilles) -> 3.0 m, not the 0.9 m plain-end gap.
    # 2 x 6.058 + 3.0 = 15.116 (was 13.016 under the old uniform 0.9 m).
    assert layout.envelope_d_m == pytest.approx(15.116, abs=0.001)
    assert layout.dc_field_split == (4, 4)


def test_nine_placements_eight_dc_one_station():
    layout = compute_bilateral_layout(8)
    assert len(layout.placements) == 9
    dc = layout.by_type("dc_block")
    stations = layout.by_type("ac_station")
    assert len(dc) == 8
    assert len(stations) == 1
    assert {p.equipment_id for p in dc} == {f"DC-{i}" for i in range(1, 9)}


def test_bilateral_split_west_and_east():
    layout = compute_bilateral_layout(8)
    west = [p for p in layout.by_type("dc_block") if p.side == "west"]
    east = [p for p in layout.by_type("dc_block") if p.side == "east"]
    assert {p.equipment_id for p in west} == {"DC-1", "DC-2", "DC-3", "DC-4"}
    assert {p.equipment_id for p in east} == {"DC-5", "DC-6", "DC-7", "DC-8"}
    # West field is strictly west of the station; east field strictly east.
    station = layout.by_type("ac_station")[0]
    assert all(p.x_m + p.width_m <= station.x_m + 1e-6 for p in west)
    assert all(p.x_m >= station.x_m + station.width_m - 1e-6 for p in east)


def test_mirrored_pairs_are_2x2_fields():
    layout = compute_bilateral_layout(8)
    dc = layout.by_type("dc_block")
    pairs = {}
    for p in dc:
        pairs.setdefault(p.pair_id, []).append(p)
    assert set(pairs) == {"W1", "W2", "E1", "E2"}
    # each pair is two back-to-back containers sharing a north-south row
    for members in pairs.values():
        assert len(members) == 2
        assert members[0].y_m == pytest.approx(members[1].y_m)
        # doors face outward (opposite directions) across the back-to-back gap
        assert {m.door_orientation for m in members} == {"west", "east"}


def test_central_station_is_vertical_40ft():
    layout = compute_bilateral_layout(8)
    station = layout.by_type("ac_station")[0]
    assert station.side == "center"
    assert station.rotation_deg == 90.0
    assert station.height_m == pytest.approx(AC40_STATION_LENGTH_M)
    # station vertically centred within the envelope depth
    assert station.center_y_m == pytest.approx(layout.envelope_d_m / 2.0, abs=0.001)


def test_no_dc_block_overlaps():
    layout = compute_bilateral_layout(8)
    dc = layout.by_type("dc_block")
    collisions = [
        (a.equipment_id, b.equipment_id)
        for i, a in enumerate(dc)
        for b in dc[i + 1 :]
        if _overlap(a, b)
    ]
    assert collisions == []


def test_placements_carry_provenance_and_provisional_flags():
    layout = compute_bilateral_layout(8)
    assert layout.provisional_notes  # rule-profile assumptions recorded
    dc = layout.by_type("dc_block")[0]
    assert dc.provenance
    assert dc.provisional is True
    station = layout.by_type("ac_station")[0]
    # nominal ISO 40 ft dims + rule-profile aisle -> provisional
    assert station.provisional is True


def test_dedicated_feeder_index_matches_dc_numbering():
    layout = compute_bilateral_layout(8)
    for p in layout.by_type("dc_block"):
        assert p.feeder_index == int(p.equipment_id.split("-")[1])


def test_owner_confirmed_dims_clear_provisional_flags():
    layout = compute_bilateral_layout(
        8,
        dc_field_to_station_aisle_m=3.0,
        station_length_m=12.0,
        station_width_m=2.5,
    )
    station = layout.by_type("ac_station")[0]
    assert station.provisional is False


def test_only_eight_dc_supported_in_phase_a():
    with pytest.raises(ValueError):
        compute_bilateral_layout(4)
    with pytest.raises(ValueError):
        compute_bilateral_layout(16)


def test_plan_svg_renders_concept_markers():
    layout = compute_bilateral_layout(8)
    svg = render_bilateral_plan_svg(layout)
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "CONCEPT ONLY" in svg
    assert "PCS &amp; MV STATION (40 FT)" in svg
    assert "DC-1" in svg and "DC-8" in svg
    assert "18.79 m" in svg
    # No CJK in the drawing: the report rasterises it with a monospace face that
    # has no CJK coverage, so a Chinese glyph prints as tofu boxes.
    cjk = [ch for ch in svg if "一" <= ch <= "鿿"]
    assert not cjk, f"arrangement SVG has CJK the report font cannot draw: {cjk}"


def test_perimeter_field_is_gone_and_must_not_come_back():
    """Owner ruling 2026-08-03: '不能搞环绕布置 … 按一字型排'.

    A four-side / perimeter field (DC Blocks wrapped around all four sides of the
    station) was built, reviewed and rejected: it needs a third and fourth 3.0 m
    aisle (~536 m2 vs ~284 m2), routes the north/south DC cables around the
    station, and breaks the site row model. This test is the lock — the module
    must expose exactly ONE 8-DC geometry.
    """
    import calb_diagrams.ac_block_bilateral_layout as mod

    assert not hasattr(mod, "compute_quad_layout")
    assert not hasattr(mod, "QUAD_LAYOUT_VARIANT")
    assert compute_bilateral_layout(8).layout_variant == LAYOUT_VARIANT


def test_the_field_stays_on_one_axis():
    """一字型: both DC fields and the station sit on a single east-west axis.

    Nothing is placed north or south of the station, and every DC Block overlaps
    the station's north-south band — that is what makes the block tileable into a
    site row.
    """
    layout = compute_bilateral_layout(8)
    station = layout.by_type("ac_station")[0]
    st_x0, st_x1 = station.x_m, station.x_m + station.width_m
    for p in layout.by_type("dc_block"):
        # strictly west or strictly east of the station — never above/below it
        assert p.x_m + p.width_m <= st_x0 + 1e-6 or p.x_m >= st_x1 - 1e-6
    assert {p.side for p in layout.by_type("dc_block")} == {"west", "east"}
    # Single-axis means the block is wider than it is deep once the station and
    # both fields are laid out along that axis.
    assert layout.envelope_w_m > layout.envelope_d_m


def test_eight_pcs_eight_dc_report_uses_the_same_engine_as_a_governed_run():
    """P1-3: engine choice follows the block SHAPE, not only layout_variant.

    A generic 8-PCS / 8-DC run is physically the same 10 MW product as the
    governed one, so §8 must draw the SAME arrangement — one product, one
    geometry — not the ~48 m linear strip and not the rejected perimeter field.
    """
    import io as _io

    from docx import Document as _Document

    from calb_sizing_tool.reporting.report_context import build_report_context
    from calb_sizing_tool.reporting.report_v2 import export_report_v2_1

    ctx = build_report_context(
        session_state={},
        stage_outputs={
            "stage13_output": {
                "project_name": "P13", "poi_power_req_mw": 115.0,
                "poi_energy_req_mwh": 400.0, "project_life_years": 20,
                "poi_guarantee_year": 4, "cycles_per_year": 365,
            },
            "ac_output": {
                "num_blocks": 13, "pcs_per_block": 8, "pcs_kw": 1250.0,
                "block_size_mw": 10.0, "transformer_mva": 11.111,
                "total_ac_mw": 130.0, "lv_winding_count": 2,
                "transformer_topology": "three_winding", "dc_blocks_total": 104,
            },
            "stage2": {"container_count": 104, "dc_nameplate_bol_mwh": 521.6},
        },
        project_inputs={},
    )
    doc = _Document(_io.BytesIO(export_report_v2_1(ctx)))
    caption = next(
        (p.text for p in doc.paragraphs if "Typical AC Block Arrangement" in p.text
         and p.text.startswith("Figure")), "",
    )
    assert caption, "§8 arrangement caption not found"
    # The single-axis bilateral unit — identical to what a governed run draws.
    governed = compute_bilateral_layout(8)
    assert f"{governed.envelope_w_m:.2f}" in caption, caption
    assert f"{governed.envelope_d_m:.2f}" in caption, caption
    assert "48.42" not in caption, caption   # not the linear strip
    assert "28.54" not in caption, caption   # not the rejected perimeter field
