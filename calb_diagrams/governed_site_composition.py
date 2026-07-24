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

"""Concept site-composition diagram for a governed (Phase B) mixed site.

Renders the heterogeneous site as one horizontal band per governed group (e.g.
23 x 10 MW bilateral units + 1 x 5 MW linear tail), with a small-multiple row of
AC-block glyphs sized by each configuration's equipment envelope. This is a
COMPOSITION overview — how many governed units of each type make up the site —
NOT a geometric Master Layout against a real site boundary (that stays L3 / P2).
"""

from __future__ import annotations

from typing import List, Sequence
from xml.sax.saxutils import escape as _xml_escape

from calb_diagrams.ac_block_arrangement_v2 import US_NFPA_OIL, compute_layout
from calb_diagrams.ac_block_bilateral_layout import LAYOUT_VARIANT as BILATERAL_VARIANT
from calb_diagrams.ac_block_bilateral_layout import compute_bilateral_layout

_INK = "#1f4e79"
_GROUND = "#c6cac5"
_PANEL = "#e8ebe8"
_PANEL_EDGE = "#aeb5b4"
_UNIT = "#eef0ef"
_UNIT_EDGE = "#9fa7a5"
_BADGE = "#1f4e79"
_MUTED = "#5b6367"

_MAX_GLYPHS = 8  # cap the small-multiple row per group


def _envelope_w_m(configuration_code: str, layout_variant: str, dc_per_block: int) -> float:
    """Equipment-envelope width (m) of one AC block of this configuration."""
    if layout_variant == BILATERAL_VARIANT:
        return compute_bilateral_layout(8).envelope_w_m
    return compute_layout(max(1, int(dc_per_block)), US_NFPA_OIL).envelope_w_m


def _rect(parts, x, y, w, h, fill, stroke=None, sw=1.0, rx=3.0):
    extra = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                 f'fill="{fill}" rx="{rx}"{extra}/>')


def _text(parts, x, y, s, size=12, anchor="start", weight=700, fill=_INK):
    parts.append(f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-size="{size}" '
                 f'font-family="Consolas, monospace" font-weight="{weight}" '
                 f'text-anchor="{anchor}">{_xml_escape(s)}</text>')


def render_governed_site_composition_svg(plan, *, title: str = "GOVERNED SITE COMPOSITION") -> str:
    """Render a concept composition diagram from a GovernedSitePlan.

    ``plan`` is a services.governed_ac_block_service.GovernedSitePlan (duck-typed:
    needs ``dc_blocks_total``, ``ac_blocks_total``, ``ac_power_mw_total`` and a
    ``groups`` iterable of items with configuration_code / layout_variant /
    ac_block_count / dc_blocks_per_ac_block / pcs_per_ac_block /
    ac_power_mw_total / eligible_product_codes).
    """
    groups: Sequence = tuple(plan.groups)
    margin_l, margin_r, margin_t = 40.0, 40.0, 92.0
    band_h = 118.0
    band_gap = 16.0
    content_w = 1180.0
    width = margin_l + content_w + margin_r
    height = margin_t + len(groups) * (band_h + band_gap) + 60.0

    parts: List[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
                 f'font-family="Consolas, monospace">')
    _rect(parts, 0, 0, width, height, _GROUND, rx=0)

    _text(parts, margin_l, 40, title, size=16)
    _text(parts, margin_l, 62,
          f"{plan.dc_blocks_total} DC Blocks  ·  {plan.ac_blocks_total} AC Blocks  ·  "
          f"{plan.ac_power_mw_total:.2f} MW  ·  {len(groups)} governed group(s)",
          size=11.5, weight=600, fill=_MUTED)

    # relative glyph scale: map the widest envelope to a fixed pixel width
    env_ws = [_envelope_w_m(g.configuration_code, g.layout_variant, g.dc_blocks_per_ac_block) for g in groups]
    max_env = max(env_ws) if env_ws else 1.0
    glyph_max_px = 150.0

    y = margin_t
    for g, env_w in zip(groups, env_ws):
        _rect(parts, margin_l, y, content_w, band_h, _PANEL, _PANEL_EDGE, 1.0)
        # badge: count
        _rect(parts, margin_l + 14, y + 20, 78, 40, _BADGE, rx=6.0)
        _text(parts, margin_l + 14 + 39, y + 47, f"x{g.ac_block_count}", size=20,
              anchor="middle", fill="#ffffff")
        # config label + metrics
        _text(parts, margin_l + 110, y + 30, g.configuration_code, size=13)
        _text(parts, margin_l + 110, y + 50,
              f"{g.dc_blocks_per_ac_block} DC / {g.pcs_per_ac_block} PCS per AC Block  ·  "
              f"{g.ac_power_mw_total:.2f} MW total  ·  {g.layout_variant}",
              size=10.5, weight=600, fill=_MUTED)
        products = ", ".join(getattr(g, "eligible_product_codes", ()) or []) or "no catalogue product (use Engineering Settings)"
        _text(parts, margin_l + 110, y + 68, f"eligible: {products}", size=9.5,
              weight=600, fill=_MUTED)

        # small-multiple glyph row (capped)
        gw = glyph_max_px * (env_w / max_env)
        gh = 30.0
        gx = margin_l + 110
        gy = y + 80
        shown = min(g.ac_block_count, _MAX_GLYPHS)
        step = gw * 0.55 + 8.0
        for i in range(shown):
            _rect(parts, gx + i * step, gy, gw * 0.5, gh, _UNIT, _UNIT_EDGE, 0.9, rx=2.0)
        if g.ac_block_count > shown:
            _text(parts, gx + shown * step + 4, gy + 20,
                  f"+{g.ac_block_count - shown} more", size=10, weight=600, fill=_MUTED)
        y += band_h + band_gap

    _text(parts, margin_l, height - 24,
          "CONCEPT ONLY — composition overview (how many governed units of each type), "
          "not a geometric Master Layout.", size=10.5, weight=600, fill=_MUTED)
    parts.append("</svg>")
    return "".join(parts)


__all__ = ["render_governed_site_composition_svg"]
