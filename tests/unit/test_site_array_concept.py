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
    assert layout.envelope_d_m == pytest.approx(11.176, abs=0.01)


def test_envelope_4x2dc():
    layout = compute_site_array(4, 2)
    # width = 2*15.116 + 2.0 corridor + 2*3.0 = 38.232
    assert layout.envelope_w_m == pytest.approx(38.23, abs=0.01)
    # depth = 2*5.176 + (3.0+6.0+3.0) + 2*3.0 = 28.352
    assert layout.envelope_d_m == pytest.approx(28.35, abs=0.01)


def test_envelope_4x4dc_wider_than_2dc():
    two = compute_site_array(4, 2)
    four = compute_site_array(4, 4)
    # 4xDC block is wider (22.074 vs 15.116) so the site is wider, same depth
    assert four.envelope_w_m > two.envelope_w_m
    assert four.envelope_d_m == pytest.approx(two.envelope_d_m, abs=0.01)


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
