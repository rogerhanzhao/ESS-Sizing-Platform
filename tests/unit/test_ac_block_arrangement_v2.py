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

"""Geometry tests for the L1 rule-based AC block arrangement engine.

Owner rules under test (docs/LAYOUT_ROADMAP_V1_2026-07-18.md §1.1):
- spacing comes only from the ArrangementRuleProfile (US/NFPA default);
- mirrored pairs with 0.30 m adjacency (the DC Block's door-free wide face);
  3.0 m DC-to-MV aisle; and — per the owner ruling of 2026-08-03 — 3.0 m between
  adjacent pairs, because one of the two facing END faces is always the EQUIPMENT
  END (liquid-cooling unit + fan grilles), which takes the same clearance as the
  AC Block aisle. Only the opposite plain end could take the reduced 0.9 m.
  Envelopes: 15.12 m (2xDC) and 24.17 m (4xDC, 20 ft station).
"""

import pytest

from calb_diagrams.ac_block_arrangement_v2 import (
    ARRANGEMENT_RULE_PROFILES,
    US_NFPA_OIL,
    compute_layout,
    render_plan_svg,
)


def test_us_nfpa_profile_values():
    assert US_NFPA_OIL.dc_pair_gap_m == pytest.approx(0.30)
    assert US_NFPA_OIL.dc_to_mv_aisle_m == pytest.approx(3.0)
    assert US_NFPA_OIL.pair_to_pair_gap_m == pytest.approx(0.9)
    assert US_NFPA_OIL.mvt_type == "oil"
    # the legacy hardcoded 2.0 m aisle must not resurface in the profile
    assert 2.0 not in (
        US_NFPA_OIL.dc_pair_gap_m,
        US_NFPA_OIL.dc_to_mv_aisle_m,
        US_NFPA_OIL.pair_to_pair_gap_m,
    )
    assert "us_nfpa_oil" in ARRANGEMENT_RULE_PROFILES


def test_envelope_2dc():
    layout = compute_layout(2, US_NFPA_OIL)
    assert layout.pair_count == 1 and not layout.has_single_tail
    assert layout.envelope_w_m == pytest.approx(15.116, abs=0.001)
    assert layout.envelope_d_m == pytest.approx(5.176, abs=0.001)


def test_envelope_4dc():
    layout = compute_layout(4, US_NFPA_OIL)
    assert layout.pair_count == 2 and not layout.has_single_tail
    # 2 pairs: 6.058*2 + 3.0 (equipment end) = 15.116; + 3.0 aisle + 6.058 station
    assert layout.envelope_w_m == pytest.approx(24.174, abs=0.001)
    assert layout.envelope_d_m == pytest.approx(5.176, abs=0.001)


def test_envelope_odd_count_has_single_tail():
    layout = compute_layout(5, US_NFPA_OIL)
    assert layout.pair_count == 2 and layout.has_single_tail
    # 3 DC units along the row: 3*6.058 + 2*0.9 = 19.974; + 3.0 + 6.058
    assert layout.envelope_w_m == pytest.approx(33.232, abs=0.001)


def test_envelope_single_dc():
    layout = compute_layout(1, US_NFPA_OIL)
    assert layout.pair_count == 0 and layout.has_single_tail
    assert layout.envelope_d_m == pytest.approx(2.438, abs=0.001)


def test_invalid_count_rejected():
    with pytest.raises(ValueError):
        compute_layout(0, US_NFPA_OIL)


def test_plan_svg_markers_2dc():
    svg, layout = render_plan_svg(2, US_NFPA_OIL)
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "PCS &amp; MV STATION" in svg or "PCS & MV STATION" in svg
    assert "CONCEPT ONLY" in svg
    assert "3.0 m aisle" in svg
    assert "0.30 m" in svg                 # pair adjacency dim
    assert "15.12 m envelope" in svg
    # single pair: no pair-to-pair dim
    assert "0.9 m" not in svg
    # 2 containers x 4 vents + 2 MV roof vents drawn as vent-fill rects
    assert svg.count('fill="#e2e5e4"') == 10


def test_plan_svg_markers_4dc():
    svg, layout = render_plan_svg(4, US_NFPA_OIL)
    assert "24.17 m envelope" in svg
    assert "3.0 m" in svg                  # equipment-end dim present
    assert svg.count('fill="#e2e5e4"') == 18   # 4x4 container vents + 2 MV vents


def test_vents_face_the_pair_gap():
    """North container vents on its south (gap) edge; south container on north."""
    svg, _ = render_plan_svg(2, US_NFPA_OIL)
    import re
    vents = [(float(m.group(1)), float(m.group(2)))
             for m in re.finditer(
                 r'<rect x="([0-9.]+)" y="([0-9.]+)" width="38.7" height="38.7"',
                 svg)]
    assert len(vents) == 8
    ys = sorted({round(v[1], 1) for v in vents})
    assert len(ys) == 2
    # the two vent rows must be closer to each other (the 0.30 m gap) than the
    # container width apart: row pitch < DC width in px (2.438 * 44 = 107.3)
    assert (ys[1] - ys[0]) < 107.3

def test_station_size_follows_the_ac_block_class_not_a_constant():
    """A 10 MW / 8-PCS AC Block is a 40 ft station, never the 20 ft cabin.

    MV_LENGTH_M used to be a fixed 6.058 m, so the 2026-08-03 report drew a
    10 MW / 8-PCS block with a 20 ft station (envelope 35.99 m).
    """
    from calb_diagrams.ac_block_arrangement_v2 import (
        AC_STATION_20FT_LENGTH_M,
        AC_STATION_40FT_LENGTH_M,
        US_NFPA_OIL,
        compute_layout,
        resolve_station_length_m,
    )

    assert resolve_station_length_m(4, 5.0) == AC_STATION_20FT_LENGTH_M
    assert resolve_station_length_m(8, 10.0) == AC_STATION_40FT_LENGTH_M
    # 8 PCS alone, or 10 MW alone, is enough to resolve the 40 ft station.
    assert resolve_station_length_m(8, None) == AC_STATION_40FT_LENGTH_M
    assert resolve_station_length_m(None, 10.0) == AC_STATION_40FT_LENGTH_M

    big = compute_layout(8, US_NFPA_OIL, pcs_count=8, block_power_mw=10.0)
    assert big.station_length_m == AC_STATION_40FT_LENGTH_M
    # 4 pairs: 4*6.058 + 3*3.0 = 33.232; + 3.0 aisle + 12.192 station = 48.424
    assert big.envelope_w_m == pytest.approx(48.424, abs=0.001)

    small = compute_layout(4, US_NFPA_OIL, pcs_count=4, block_power_mw=5.0)
    assert small.station_length_m == AC_STATION_20FT_LENGTH_M


def test_linear_and_bilateral_engines_share_the_same_iso_station_length():
    """The two engines must not each carry their own 40 ft constant.

    They did, which is how one path stayed at 20 ft while the other was correct.
    """
    from calb_diagrams import ac_block_bilateral_layout as bilateral
    from calb_diagrams.ac_block_arrangement_v2 import AC_STATION_40FT_LENGTH_M

    assert bilateral.AC40_STATION_LENGTH_M == AC_STATION_40FT_LENGTH_M
