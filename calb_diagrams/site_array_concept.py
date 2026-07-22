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

"""Concept site-array engine (Layout Roadmap L2).

Composes N AC blocks into a whole-site concept arrangement following the
owner-approved rule (docs/AC_BLOCK_PRODUCT_KNOWLEDGE_2026-07-18.md §5):

- Within a row, two AC blocks are MIRRORED so both PCS & MV stations face a
  shared central MV corridor; MV feeders collect there and route one
  direction along the fire road to the substation.
- Rows are separated by a fire access road flanked by maintenance aisles.
- Spacing comes only from the rule profiles — no hardcoded site dimensions.

This is a CONCEPT estimate (envelope + arrangement), NOT a Master Layout: it
does not place equipment against a real site boundary. That remains L3 / P2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple
from xml.sax.saxutils import escape as _xml_escape

from calb_diagrams.ac_block_arrangement_v2 import (
    ArrangementRuleProfile,
    US_NFPA_OIL,
    compute_layout,
)


@dataclass(frozen=True)
class SiteRuleProfile:
    """Site-level spacing (fire road, aisles, corridor, perimeter)."""

    key: str
    label: str
    mv_corridor_m: float        # shared central corridor between mirrored blocks
    maintenance_aisle_m: float  # door-side clearance to the fire road
    fire_road_m: float          # fire apparatus access road
    perimeter_clear_m: float    # equipment to fence/lot line
    basis: Tuple[Tuple[str, str, str], ...]


US_NFPA_SITE = SiteRuleProfile(
    key="us_nfpa_site",
    label="International — IFC / NFPA 855 / NFPA 850",
    mv_corridor_m=2.0,
    maintenance_aisle_m=3.0,
    fire_road_m=6.0,
    perimeter_clear_m=3.0,
    basis=(
        ("Central MV corridor", "2.0 m",
         "Owner rule — mirrored blocks share one MV collection corridor"),
        ("Maintenance aisle", "3.0 m", "Door-side access to fire road"),
        ("Fire apparatus access road", "6.0 m (20 ft)",
         "IFC §503 / NFPA 855 fire department access"),
        ("Perimeter clearance", "3.0 m (10 ft)",
         "IFC §1207.8.3 / NFPA 855 clearance to lot line"),
    ),
)

SITE_RULE_PROFILES = {profile.key: profile for profile in (US_NFPA_SITE,)}


@dataclass(frozen=True)
class SiteArrayLayout:
    n_blocks: int
    dc_per_block: int
    rows: int
    blocks_per_row: Tuple[int, ...]     # blocks placed in each row (<= 2)
    block_w_m: float
    block_d_m: float
    envelope_w_m: float
    envelope_d_m: float
    total_power_mw: float
    total_energy_mwh: float
    profile_key: str
    site_profile_key: str


# Nameplate assumptions per AC block (5 MW PCS & MV station; 5.015 MWh DC).
_BLOCK_POWER_MW = 5.0
_DC_ENERGY_MWH = 5.015


def compute_site_array(
    n_blocks: int,
    dc_per_block: int,
    profile: ArrangementRuleProfile = US_NFPA_OIL,
    site_profile: SiteRuleProfile = US_NFPA_SITE,
) -> SiteArrayLayout:
    """Two blocks per row (mirrored about a central MV corridor); rows stacked."""
    if n_blocks < 1:
        raise ValueError(f"n_blocks must be >= 1, got {n_blocks}")
    block = compute_layout(dc_per_block, profile)
    block_w, block_d = block.envelope_w_m, block.envelope_d_m

    rows = (n_blocks + 1) // 2
    per_row: List[int] = []
    remaining = n_blocks
    for _ in range(rows):
        take = min(2, remaining)
        per_row.append(take)
        remaining -= take

    # widest row: 2 blocks + central corridor; a lone block has no corridor
    max_in_row = max(per_row)
    row_w = (2 * block_w + site_profile.mv_corridor_m) if max_in_row == 2 else block_w

    between_rows = (site_profile.maintenance_aisle_m + site_profile.fire_road_m
                    + site_profile.maintenance_aisle_m)
    stacked_d = rows * block_d + (rows - 1) * between_rows

    env_w = row_w + 2 * site_profile.perimeter_clear_m
    env_d = stacked_d + 2 * site_profile.perimeter_clear_m

    return SiteArrayLayout(
        n_blocks=n_blocks,
        dc_per_block=dc_per_block,
        rows=rows,
        blocks_per_row=tuple(per_row),
        block_w_m=round(block_w, 3),
        block_d_m=round(block_d, 3),
        envelope_w_m=round(env_w, 2),
        envelope_d_m=round(env_d, 2),
        total_power_mw=round(n_blocks * _BLOCK_POWER_MW, 2),
        total_energy_mwh=round(n_blocks * dc_per_block * _DC_ENERGY_MWH, 2),
        profile_key=profile.key,
        site_profile_key=site_profile.key,
    )


# ---------------------------------------------------------------------------
# Plan-view SVG rendering
# ---------------------------------------------------------------------------

_INK = "#1f4e79"
_GROUND = "#c6cac5"
_PAD = "#d3d5d1"
_PAD_EDGE = "#b3b6b2"
_BLOCK = "#e8ebe8"
_BLOCK_EDGE = "#aeb5b4"
_DC = "#eef0ef"
_MV = "#f0f2f1"
_ROAD = "#b7bab6"
_DUCT = "#454d52"
_HYDRANT = "#c33127"
_FENCE = "#4a5055"


def _r(parts, x, y, w, h, fill, stroke=None, sw=1.0, rx=2.0, opacity=None):
    extra = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    if opacity is not None:
        extra += f' opacity="{opacity}"'
    parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                 f'fill="{fill}" rx="{rx}"{extra}/>')


def _t(parts, x, y, s, size=12, anchor="middle", weight=700, fill=_INK):
    parts.append(f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-size="{size}" '
                 f'font-family="Consolas, monospace" font-weight="{weight}" '
                 f'text-anchor="{anchor}">{_xml_escape(s)}</text>')


def _dim(parts, x1, y1, x2, y2, label, above=True, size=11):
    parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                 f'stroke="{_INK}" stroke-width="1.2"/>')
    for px, py in ((x1, y1), (x2, y2)):
        parts.append(f'<line x1="{px-3.5:.1f}" y1="{py-3.5:.1f}" x2="{px+3.5:.1f}" '
                     f'y2="{py+3.5:.1f}" stroke="{_INK}" stroke-width="1.1"/>')
    _t(parts, (x1+x2)/2, (y1+y2)/2 + (-6 if above else 13), label, size=size)


def _block_glyph(parts, s, x0, y0, layout: SiteArrayLayout, mv_left: bool):
    """Top-down AC block: DC pairs + MV station, MV toward the corridor side."""
    bw, bd = layout.block_w_m, layout.block_d_m
    _r(parts, x0, y0, bw * s, bd * s, _BLOCK, _BLOCK_EDGE, 1.0)
    mv_w = 6.058
    if mv_left:
        _r(parts, x0 + 3, y0 + 0.5 * s, mv_w * s, (bd - 1.0) * s, _MV, _BLOCK_EDGE, 0.8)
        for i in range(5):
            _r(parts, x0 + (0.4 + i * 0.15) * s, y0 + 0.55 * s, 0.06 * s, (bd - 1.1) * s, "#c2c8c7", rx=0)
        dc_x0 = x0 + (mv_w + 3.0) * s
    else:
        dc_x0 = x0
        mv_x = x0 + (bw - mv_w) * s
        _r(parts, mv_x, y0 + 0.5 * s, mv_w * s, (bd - 1.0) * s, _MV, _BLOCK_EDGE, 0.8)
        for i in range(5):
            _r(parts, mv_x + (mv_w - 1.0 + i * 0.15) * s, y0 + 0.55 * s, 0.06 * s, (bd - 1.1) * s, "#c2c8c7", rx=0)
    # DC containers as two stacked rows
    units = (layout.dc_per_block + 1) // 2
    for u in range(units):
        ux = dc_x0 + u * (6.058 + 0.9) * s
        _r(parts, ux, y0 + 0.15 * s, 6.058 * s, 2.438 * s, _DC, _BLOCK_EDGE, 0.7)
        _r(parts, ux, y0 + (0.15 + 2.438 + 0.3) * s, 6.058 * s, 2.438 * s, _DC, _BLOCK_EDGE, 0.7)


def render_site_svg(layout: SiteArrayLayout,
                    site_profile: SiteRuleProfile = US_NFPA_SITE) -> str:
    """Whole-site concept arrangement (top-down)."""
    s = 8.0  # px per metre (site scale)
    margin_l, margin_r, margin_t, margin_b = 60.0, 60.0, 70.0, 96.0
    per = site_profile.perimeter_clear_m
    corridor = site_profile.mv_corridor_m
    between = (site_profile.maintenance_aisle_m + site_profile.fire_road_m
               + site_profile.maintenance_aisle_m)
    bw, bd = layout.block_w_m, layout.block_d_m

    width = margin_l + layout.envelope_w_m * s + margin_r
    height = margin_t + layout.envelope_d_m * s + margin_b

    parts: List[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} '
                 f'{height:.0f}" font-family="Consolas, monospace">')
    _r(parts, 0, 0, width, height, _GROUND, rx=0)

    ox = margin_l
    oy = margin_t
    # perimeter fence
    _r(parts, ox, oy, layout.envelope_w_m * s, layout.envelope_d_m * s,
       "none", _FENCE, 2.0, rx=0)

    row_w = (2 * bw + corridor) if max(layout.blocks_per_row) == 2 else bw
    row_x0 = ox + (layout.envelope_w_m - row_w) / 2 * s
    cx = row_x0 + (bw + corridor / 2) * s  # corridor centre (2-block rows)

    for ri, n_in_row in enumerate(layout.blocks_per_row):
        ry = oy + per * s + ri * (bd + between) * s
        # fire road below each row except the last
        if ri < layout.rows - 1:
            road_y = ry + bd * s + site_profile.maintenance_aisle_m * s
            _r(parts, ox + 2, road_y, layout.envelope_w_m * s - 4,
               site_profile.fire_road_m * s, _ROAD, rx=0)
            for dash_x in range(int(ox), int(ox + layout.envelope_w_m * s), 44):
                _r(parts, dash_x + 8, road_y + site_profile.fire_road_m * s / 2 - 1,
                   22, 2, "#e4e6e2", rx=0)
        # left block: MV on right (toward corridor); right block mirrored
        _block_glyph(parts, s, row_x0, ry, layout, mv_left=False)
        _t(parts, row_x0 + bw * s / 2, ry - 6, f"AC BLOCK {ri*2+1}", size=10)
        if n_in_row == 2:
            rx0 = row_x0 + (bw + corridor) * s
            _block_glyph(parts, s, rx0, ry, layout, mv_left=True)
            _t(parts, rx0 + bw * s / 2, ry - 6, f"AC BLOCK {ri*2+2}", size=10)
            # MV corridor + collection duct
            _r(parts, row_x0 + bw * s, ry, corridor * s, bd * s, "#dfe1dd", rx=0)
            parts.append(f'<line x1="{cx:.1f}" y1="{ry + bd*s/2:.1f}" '
                         f'x2="{cx:.1f}" y2="{oy + per*s + (layout.rows*bd + (layout.rows-1)*between)*s - bd*s/2 if layout.rows>1 else ry+bd*s/2:.1f}" '
                         f'stroke="{_DUCT}" stroke-width="2.5" stroke-dasharray="8 5" opacity="0.85"/>')

    # hydrants at the perimeter corners near the road
    for hx in (ox + 6, ox + layout.envelope_w_m * s - 6):
        hy = oy + per * s + bd * s + between * s / 2
        parts.append(f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="4.2" fill="{_HYDRANT}" '
                     f'stroke="#801d15" stroke-width="1.3"/>')

    # feeder exit arrow to substation (east)
    fy = oy + per * s + bd * s + between * s / 2
    parts.append(f'<line x1="{cx:.1f}" y1="{fy:.1f}" x2="{ox + layout.envelope_w_m*s - 8:.1f}" '
                 f'y2="{fy:.1f}" stroke="{_DUCT}" stroke-width="2.5" '
                 f'stroke-dasharray="8 5" opacity="0.85"/>')
    _t(parts, ox + layout.envelope_w_m * s - 10, fy - 6,
       "MV FEEDERS -> SUBSTATION", size=9.5, anchor="end")

    # title + dims + concept note
    _t(parts, margin_l, 30,
       f"CONCEPT SITE ARRANGEMENT · {layout.n_blocks} × AC BLOCK "
       f"({layout.dc_per_block}×DC) · {layout.total_power_mw:.0f} MW / "
       f"{layout.total_energy_mwh:.1f} MWh", size=11.5, anchor="start")
    _dim(parts, ox, oy + layout.envelope_d_m * s + 22,
         ox + layout.envelope_w_m * s, oy + layout.envelope_d_m * s + 22,
         f"{layout.envelope_w_m:.1f} m site envelope", above=False)
    _dim(parts, ox - 22, oy, ox - 22, oy + layout.envelope_d_m * s,
         f"{layout.envelope_d_m:.1f} m", above=True)
    _t(parts, margin_l, height - 16,
       "CONCEPT ONLY — NOT FOR CONSTRUCTION · envelope estimate, not a site layout",
       size=10.5, anchor="start", weight=600, fill="#5b6367")

    parts.append("</svg>")
    return "".join(parts)
