"""Geometry tests for the bilateral 4+4 AC Block layout engine.

Owner-confirmed concept (docs/CLAUDE_HANDOFF_10MW_8PCS_8DC_2026-07-24.md §1-§2):
central vertical 40 ft AC Block, west 4-DC field + east 4-DC field, each a 2x2
``田`` of two mirrored back-to-back pairs; ~18.79 m x 13.02 m equipment envelope.
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
    # Recorded concept envelope ~ 18.79 m x 13.02 m (handoff §2).
    assert layout.envelope_w_m == pytest.approx(18.790, abs=0.001)
    assert layout.envelope_d_m == pytest.approx(13.016, abs=0.001)
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
