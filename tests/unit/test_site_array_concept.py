# -----------------------------------------------------------------------------
# Personal Open-Source Notice
#
# Copyright (c) 2026 Alex.Zhao. All rights reserved.
#
# This repository is released under the MIT License (see LICENSE file).
# Intended use: learning, evaluation, and engineering reference for Utility-scale
# BESS/ESS sizing and Reporting workflows.
#
# DISCLAIMER: This software is provided "AS IS", without warranty of any kind,
# express or implied. In no event shall the author(s) be liable for any claim,
# damages, or other liability arising from, out of, or in connection with the
# software or the use or other dealings in the software.
#
# NOTE: This is a personal project. It is not an official product or statement
# of any company or organization.
# -----------------------------------------------------------------------------

"""Geometry tests for the L2 concept site-array engine.

Owner rule under test (docs/AC_BLOCK_PRODUCT_KNOWLEDGE_2026-07-18.md §5,
LAYOUT_ROADMAP_V1_2026-07-18.md §2-L2): mirrored blocks share a central MV
corridor; rows are separated by a fire road flanked by maintenance aisles;
all spacing comes from the rule profiles.
"""

import pytest

from calb_diagrams.ac_block_arrangement_v2 import US_NFPA_OIL
from calb_diagrams.site_array_concept import (
    SITE_RULE_PROFILES,
    US_NFPA_SITE,
    compute_site_array,
    render_site_svg,
)


def test_site_profile_values():
    assert US_NFPA_SITE.mv_corridor_m == pytest.approx(2.0)
    assert US_NFPA_SITE.maintenance_aisle_m == pytest.approx(3.0)
    assert US_NFPA_SITE.fire_road_m == pytest.approx(6.0)
    assert US_NFPA_SITE.perimeter_clear_m == pytest.approx(3.0)
    assert "us_nfpa_site" in SITE_RULE_PROFILES


def test_row_allocation_two_per_row():
    layout = compute_site_array(4, 2)
    assert layout.rows == 2
    assert layout.blocks_per_row == (2, 2)


def test_row_allocation_odd_last_row_single():
    layout = compute_site_array(3, 4)
    assert layout.rows == 2
    assert layout.blocks_per_row == (2, 1)
    assert sum(layout.blocks_per_row) == 3


def test_single_block_no_corridor_in_width():
    layout = compute_site_array(1, 2)
    # lone block: width = block_w + 2*perimeter (no corridor added)
    # block 2xDC = 15.116; + 2*3.0 = 21.116
    assert layout.envelope_w_m == pytest.approx(21.116, abs=0.01)
    # One project group still has apparatus-access roads at its top and
    # bottom: 5.176 m block depth + 2 * 6.0 m perimeter fire roads.
    assert layout.envelope_d_m == pytest.approx(17.176, abs=0.01)


def test_envelope_4x2dc():
    layout = compute_site_array(4, 2)
    # width = 2*15.116 + 2.0 corridor + 2*3.0 = 38.232
    assert layout.envelope_w_m == pytest.approx(38.23, abs=0.01)
    # 4 blocks = 1 group (2 rows), no internal fire road:
    # depth = 2*5.176 + 1*3.0 aisle + 2*6.0 perimeter roads = 25.352
    assert layout.envelope_d_m == pytest.approx(25.35, abs=0.01)
    assert layout.groups == 1
    assert layout.fire_roads == 0


def test_grouping_removes_per_row_fire_roads():
    """8 blocks default to one group: 0 internal fire roads (was 3 per-row)."""
    layout = compute_site_array(8, 2)
    assert layout.groups == 1
    assert layout.rows == 4
    assert layout.fire_roads == 0
    assert layout.fire_access_ok is True


def test_explicit_small_group_adds_roads():
    layout = compute_site_array(8, 2, blocks_per_group=4)
    assert layout.groups == 2
    assert layout.rows_per_group == (2, 2)
    assert layout.fire_roads == 1


def test_fire_access_reach_within_limit():
    layout = compute_site_array(8, 2)
    # tallest group 4 rows: (4*5.176 + 3*3.0)/2 = 14.85 m <= 45.7
    assert layout.fire_access_reach_m == pytest.approx(14.85, abs=0.02)
    assert layout.fire_access_ok is True


def test_blocks_per_group_too_small_rejected():
    with pytest.raises(ValueError):
        compute_site_array(4, 2, blocks_per_group=1)


def test_envelope_4x4dc_wider_than_2dc():
    two = compute_site_array(4, 2)
    four = compute_site_array(4, 4)
    # 4xDC block is wider (22.074 vs 15.116) so the site is wider, same depth
    assert four.envelope_w_m > two.envelope_w_m
    assert four.envelope_d_m == pytest.approx(two.envelope_d_m, abs=0.01)


def test_single_block_still_no_internal_road():
    layout = compute_site_array(1, 2)
    assert layout.groups == 1
    assert layout.fire_roads == 0


def test_energy_scales_with_dc_count():
    two = compute_site_array(4, 2)
    four = compute_site_array(4, 4)
    assert two.total_power_mw == pytest.approx(20.0)
    assert four.total_power_mw == pytest.approx(20.0)   # power set by AC blocks
    assert four.total_energy_mwh == pytest.approx(2 * two.total_energy_mwh, abs=0.1)


def test_eight_blocks_four_rows():
    layout = compute_site_array(8, 2)
    assert layout.rows == 4
    assert layout.blocks_per_row == (2, 2, 2, 2)


def test_invalid_block_count_rejected():
    with pytest.raises(ValueError):
        compute_site_array(0, 2)


def test_render_site_svg_markers():
    svg = render_site_svg(compute_site_array(4, 2))
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "CONCEPT SITE ARRANGEMENT" in svg
    assert "CONCEPT ONLY" in svg
    assert "MV FEEDERS -&gt; SUBSTATION" in svg or "MV FEEDERS -> SUBSTATION" in svg
    assert "site envelope" in svg
    assert "AC BLOCK 1" in svg and "AC BLOCK 4" in svg
    # no ampersand-unescaped raw text that would break XML
    import xml.dom.minidom
    xml.dom.minidom.parseString(svg)   # raises on malformed XML


# ---------------------------------------------------------------------------
# P1-4 regression lock — the site array may never assume a station size or a
# nameplate. Both come from the run, exactly as they do in the arrangement
# figure one section earlier in the same report.
# ---------------------------------------------------------------------------


def test_station_length_follows_the_ac_block_class_not_a_constant():
    """A 10 MW / 8-PCS block tiles with the 40 ft station, not the 20 ft cabin.

    The old call passed neither PCS count nor block power, so every 10 MW row was
    drawn 6.13 m short and contradicted the Typical AC Block Arrangement figure.
    """
    small = compute_site_array(4, 4, US_NFPA_OIL, US_NFPA_SITE,
                               block_power_mw=5.0, pcs_per_block=4)
    assert small.station_length_m == pytest.approx(6.058, abs=0.001)

    big = compute_site_array(4, 8, US_NFPA_OIL, US_NFPA_SITE,
                             block_power_mw=10.0, pcs_per_block=8)
    assert big.station_length_m == pytest.approx(12.192, abs=0.001)
    # 4 mirrored pairs + 3 x 3.0 m equipment-end gaps + 3.0 m aisle + 40 ft station
    assert big.block_w_m == pytest.approx(4 * 6.058 + 3 * 3.0 + 3.0 + 12.192, abs=0.001)
    assert big.block_w_m - small.block_w_m > 6.0


def test_site_block_width_equals_the_arrangement_engine_envelope():
    """§9 must tile the SAME block §8 draws — one product, one footprint."""
    from calb_diagrams.ac_block_arrangement_v2 import compute_layout

    for dc, pcs, mw in ((4, 4, 5.0), (6, 6, 7.5), (8, 8, 10.0)):
        site = compute_site_array(6, dc, US_NFPA_OIL, US_NFPA_SITE,
                                  block_power_mw=mw, pcs_per_block=pcs)
        block = compute_layout(dc, US_NFPA_OIL, pcs_count=pcs, block_power_mw=mw)
        assert site.block_w_m == pytest.approx(block.envelope_w_m, abs=0.001)
        assert site.block_d_m == pytest.approx(block.envelope_d_m, abs=0.001)
        assert site.end_gap_m == pytest.approx(block.end_gap_m, abs=0.001)


def test_site_glyph_draws_the_resolved_station_not_a_hardcoded_one():
    layout = compute_site_array(4, 8, US_NFPA_OIL, US_NFPA_SITE,
                                block_power_mw=10.0, pcs_per_block=8)
    svg = render_site_svg(layout, US_NFPA_SITE)
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    # The MV glyph is drawn at station_length_m px-scaled; a 40 ft station is
    # twice the 20 ft one, so the two renders cannot be byte-identical.
    small = compute_site_array(4, 8, US_NFPA_OIL, US_NFPA_SITE,
                               block_power_mw=5.0, pcs_per_block=4)
    assert render_site_svg(small, US_NFPA_SITE) != svg
