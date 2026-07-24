"""Concept site-composition diagram for a governed (Phase B) mixed site."""
from __future__ import annotations

from calb_diagrams.governed_site_composition import render_governed_site_composition_svg
from calb_sizing_tool.services.governed_ac_block_service import build_governed_site_plan


def test_composition_svg_lists_all_groups_and_totals():
    plan = build_governed_site_plan(190)  # 23x8 + 4 + 2
    svg = render_governed_site_composition_svg(plan)
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "ACBLK-10MW-8PCS-8DC-40FT-BILATERAL" in svg
    assert "ACBLK-5MW-4PCS-4DC-40FT-LINEAR" in svg
    assert "ACBLK-2P5MW-2PCS-2DC-20FT-LINEAR" in svg
    assert "x23" in svg                     # count badge
    assert "+15 more" in svg                # glyph cap note
    assert "25 AC Blocks" in svg
    assert "237.50 MW" in svg
    assert "CONCEPT ONLY" in svg


def test_composition_single_bilateral_group():
    plan = build_governed_site_plan(16)     # 2x8, one group
    svg = render_governed_site_composition_svg(plan)
    assert "x2" in svg
    assert "1 governed group(s)" in svg
    assert "20.00 MW" in svg
