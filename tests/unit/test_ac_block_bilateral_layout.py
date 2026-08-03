"""Geometry tests for the bilateral 4+4 AC Block layout engine.

Owner-confirmed concept (docs/CLAUDE_HANDOFF_10MW_8PCS_8DC_2026-07-24.md §1-§2):
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
    assert "40FT AC BLOCK" in svg
    assert "DC-1" in svg and "DC-8" in svg
    assert "18.79 m" in svg


def test_four_side_field_places_two_dc_on_every_side():
    """Owner 2026-08-03: with 8 DC Blocks the field is not limited to two sides.

    Each of N/W/E/S carries one mirrored pair, so every DC Block still shows its
    door face to a 3.0 m aisle and shares only its door-free wide face (0.30 m).
    """
    from calb_diagrams.ac_block_bilateral_layout import (
        QUAD_LAYOUT_VARIANT,
        compute_quad_layout,
    )

    layout = compute_quad_layout(8)
    assert layout.layout_variant == QUAD_LAYOUT_VARIANT
    assert layout.dc_count == 8

    dc = layout.by_type("dc_block")
    assert len(dc) == 8
    by_side = {}
    for placement in dc:
        by_side.setdefault(placement.side, []).append(placement)
    assert set(by_side) == {"north", "south", "east", "west"}
    assert all(len(items) == 2 for items in by_side.values())

    # One central 40 ft station, and every DC door faces an aisle direction.
    station = layout.by_type("ac_station")
    assert len(station) == 1
    assert station[0].height_m == pytest.approx(12.192, abs=0.001)
    assert {p.door_orientation for p in dc} <= {"north", "south", "east", "west"}

    # 5.176 + 3.0 + 2.438 + 3.0 + 5.176 wide; 5.176 + 3.0 + 12.192 + 3.0 + 5.176 deep
    assert layout.envelope_w_m == pytest.approx(18.790, abs=0.001)
    assert layout.envelope_d_m == pytest.approx(28.544, abs=0.001)


def test_eight_pcs_eight_dc_report_uses_a_multi_side_field_not_a_linear_strip():
    """P1-3: engine choice follows the block SHAPE, not only layout_variant."""
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
    # The four-side field, not the ~48 m linear strip.
    assert "18.79" in caption and "28.54" in caption, caption
    assert "48.42" not in caption, caption
