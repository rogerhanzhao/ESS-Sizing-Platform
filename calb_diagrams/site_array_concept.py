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

NOTHING DIMENSIONAL MAY BE HARDCODED HERE (owner, 2026-08-03)
-------------------------------------------------------------
Station size, per-block power and per-DC-Block energy all come from the run:

- the per-block envelope is taken from compute_layout() with the run's PCS count
  and block power, so a 10 MW / 8-PCS block tiles as a 40 ft station — the same
  footprint the Typical AC Block Arrangement figure draws;
- block power and DC-Block energy are caller-supplied; the module constants that
  remain are a LAST-RESORT fallback only, never a design default.

Both rules exist because the 2026-08-03 report printed a 130 MW project as 65 MW
and drew its 10 MW blocks with the 20 ft cabin.

ROW MODEL LIMIT: this engine tiles blocks whose PCS & MV Station sits at the ROW
END and faces the shared MV corridor. The central-station bilateral block
(ac_block_bilateral_layout) does not satisfy that model — do not tile it here;
the report states its site composition in words until Master Layout (L3) lands.
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
    mv_corridor_m: float          # shared central corridor between mirrored blocks
    maintenance_aisle_m: float    # row-to-row maintenance aisle inside a group
    fire_road_m: float            # fire apparatus access road (between groups)
    perimeter_clear_m: float      # equipment to fence/lot line (non-road sides)
    default_blocks_per_group: int # blocks per project group (roads only between groups)
    fire_access_limit_m: float    # max distance from any block to a fire road
    basis: Tuple[Tuple[str, str, str], ...]


US_NFPA_SITE = SiteRuleProfile(
    key="us_nfpa_site",
    label="International — IFC / NFPA 855 / NFPA 850",
    mv_corridor_m=2.0,
    maintenance_aisle_m=3.0,
    fire_road_m=6.0,
    perimeter_clear_m=3.0,
    default_blocks_per_group=8,
    fire_access_limit_m=45.7,   # 150 ft — IFC §503.1.1 apparatus access reach
    basis=(
        ("Central MV corridor", "2.0 m",
         "Owner rule — mirrored blocks share one MV collection corridor"),
        ("Row-to-row aisle (within group)", "3.0 m",
         "Maintenance access; no fire road needed inside a group"),
        ("Fire apparatus access road (between groups)", "6.0 m (20 ft)",
         "IFC §503 / NFPA 855 — one road per group boundary, not per row"),
        ("Fire access reach", "≤ 45.7 m (150 ft)",
         "IFC §503.1.1 — every block within reach of a fire road"),
        ("Perimeter clearance", "3.0 m (10 ft)",
         "IFC §1207.8.3 / NFPA 855 clearance to lot line"),
    ),
)

SITE_RULE_PROFILES = {profile.key: profile for profile in (US_NFPA_SITE,)}


@dataclass(frozen=True)
class SiteArrayLayout:
    n_blocks: int
    dc_per_block: int
    rows: int                            # total rows across all groups
    blocks_per_row: Tuple[int, ...]      # blocks placed in each row (<= 2)
    groups: int                          # project groups (fire road only between groups)
    blocks_per_group: int
    rows_per_group: Tuple[int, ...]      # row count in each group
    fire_roads: int                      # internal fire roads = groups - 1
    fire_access_reach_m: float           # worst-case block distance to a fire road
    fire_access_ok: bool
    block_w_m: float
    block_d_m: float
    envelope_w_m: float
    envelope_d_m: float
    total_power_mw: float
    total_energy_mwh: float
    profile_key: str
    site_profile_key: str
    # Resolved from the AC Block class, never assumed: the site glyph has to draw
    # the same PCS & MV Station and the same DC end-face gap that the Typical AC
    # Block Arrangement figure draws.
    station_length_m: float = 6.058
    end_gap_m: float = 0.9
    unit_offsets_m: Tuple[float, ...] = ()
    # Footprint is the objective, so it is reported, not left to be inferred.
    land_area_m2: float = 0.0
    land_per_block_m2: float = 0.0
    land_per_mwh_m2: float = 0.0


# NO NAMEPLATE MAY BE HARDCODED HERE (owner, 2026-08-03).
# Per-block power and per-DC-Block energy previously defaulted to a 5 MW / 5.015
# MWh unit regardless of the actual run, so a 10 MW station was reported at half
# its power and the site figure contradicted the report's own AC Sizing tables.
# Both now come from the run; these constants remain only as the LAST-RESORT
# fallback for a caller that supplies nothing, and callers in the report always
# supply real values.
_FALLBACK_BLOCK_POWER_MW = 5.0
_FALLBACK_DC_ENERGY_MWH = 5.015


def _max_rows_per_group(block_d_m: float, site_profile: SiteRuleProfile) -> int:
    """Deepest group still inside the fire-apparatus access reach.

    Reach is half the group depth (roads bound the group top and bottom), so the
    group may grow until that half-depth hits ``fire_access_limit_m``. Each extra
    group costs one 6.0 m road across the whole site, so under-filling groups is
    pure land loss.
    """
    aisle = site_profile.maintenance_aisle_m
    rows = 1
    while True:
        nxt = rows + 1
        depth = nxt * block_d_m + (nxt - 1) * aisle
        if depth / 2.0 > site_profile.fire_access_limit_m:
            return rows
        rows = nxt


def compute_site_array(
    n_blocks: int,
    dc_per_block: int,
    profile: ArrangementRuleProfile = US_NFPA_OIL,
    site_profile: SiteRuleProfile = US_NFPA_SITE,
    blocks_per_group: Optional[int] = None,
    block_power_mw: Optional[float] = None,
    dc_block_energy_mwh: Optional[float] = None,
    dc_blocks_total: Optional[int] = None,
    pcs_per_block: Optional[int] = None,
) -> SiteArrayLayout:
    """Blocks grouped by project; fire roads only between groups, not per row.

    Within a group, mirrored 2-block rows share a central MV corridor and are
    separated only by a maintenance aisle. Fire apparatus access roads run
    between groups and along the top/bottom perimeter, so a block is never
    more than fire_access_limit_m from a road.
    """
    if n_blocks < 1:
        raise ValueError(f"n_blocks must be >= 1, got {n_blocks}")
    _resolved_block_power_mw = (
        float(block_power_mw) if block_power_mw and float(block_power_mw) > 0
        else _FALLBACK_BLOCK_POWER_MW
    )
    _resolved_dc_energy_mwh = (
        float(dc_block_energy_mwh) if dc_block_energy_mwh and float(dc_block_energy_mwh) > 0
        else _FALLBACK_DC_ENERGY_MWH
    )
    _resolved_dc_blocks = (
        int(dc_blocks_total) if dc_blocks_total and int(dc_blocks_total) > 0
        else n_blocks * dc_per_block
    )
    bpg = blocks_per_group or site_profile.default_blocks_per_group
    if bpg < 2:
        raise ValueError(f"blocks_per_group must be >= 2, got {bpg}")

    # The per-block envelope MUST come from the same AC Block class the report
    # states in its sizing tables. Tiling a 10 MW / 8-PCS block with the 20 ft
    # cabin (the old call, which passed neither PCS count nor power) understated
    # every row width by 6.13 m and contradicted the arrangement figure that sits
    # one section earlier in the same report.
    block = compute_layout(
        dc_per_block, profile,
        pcs_count=pcs_per_block, block_power_mw=_resolved_block_power_mw,
    )
    block_w, block_d = block.envelope_w_m, block.envelope_d_m
    station_len_m = block.station_length_m

    # rows across the whole site (2 blocks per row)
    per_row: List[int] = []
    remaining = n_blocks
    while remaining > 0:
        take = min(2, remaining)
        per_row.append(take)
        remaining -= take
    rows = len(per_row)

    # Partition rows into groups. Every extra group costs a 6.0 m fire road, so
    # the group is made as DEEP as the fire-access reach allows instead of being
    # fixed at ceil(bpg/2) — which silently assumed a block depth and cut large
    # sites into more groups, and more roads, than the code requires.
    rows_pg = _max_rows_per_group(block_d, site_profile)
    if blocks_per_group is not None:
        rows_pg = min(rows_pg, max(1, (bpg + 1) // 2))
    rows_per_group: List[int] = []
    r_left = rows
    while r_left > 0:
        take = min(rows_pg, r_left)
        rows_per_group.append(take)
        r_left -= take
    groups = len(rows_per_group)

    max_in_row = max(per_row)
    row_w = (2 * block_w + site_profile.mv_corridor_m) if max_in_row == 2 else block_w

    aisle = site_profile.maintenance_aisle_m
    road = site_profile.fire_road_m
    # depth: each group is rows*block_d + (rows-1)*aisle; groups joined by a road;
    # a perimeter fire road runs along the top and bottom of the site.
    groups_depth = sum(gr * block_d + (gr - 1) * aisle for gr in rows_per_group)
    stacked_d = groups_depth + (groups - 1) * road + 2 * road

    env_w = row_w + 2 * site_profile.perimeter_clear_m
    env_d = stacked_d

    # worst-case fire-access reach: deepest block within a group is bounded by
    # roads at both group edges; reach = half the tallest group's depth.
    tallest_group_d = max(gr * block_d + (gr - 1) * aisle for gr in rows_per_group)
    reach = round(tallest_group_d / 2.0, 2)

    _land = round(env_w * env_d, 1)
    _energy = round(_resolved_dc_blocks * _resolved_dc_energy_mwh, 2)
    return SiteArrayLayout(
        n_blocks=n_blocks,
        dc_per_block=dc_per_block,
        rows=rows,
        blocks_per_row=tuple(per_row),
        groups=groups,
        blocks_per_group=bpg,
        rows_per_group=tuple(rows_per_group),
        fire_roads=groups - 1,
        fire_access_reach_m=reach,
        fire_access_ok=reach <= site_profile.fire_access_limit_m,
        block_w_m=round(block_w, 3),
        block_d_m=round(block_d, 3),
        envelope_w_m=round(env_w, 2),
        envelope_d_m=round(env_d, 2),
        total_power_mw=round(n_blocks * _resolved_block_power_mw, 2),
        # Energy uses the REAL DC Block count when the caller knows it; a station
        # whose blocks fill unevenly has fewer DC Blocks than n_blocks x dc_per_block.
        total_energy_mwh=round(_resolved_dc_blocks * _resolved_dc_energy_mwh, 2),
        profile_key=profile.key,
        site_profile_key=site_profile.key,
        station_length_m=block.station_length_m,
        end_gap_m=block.end_gap_m,
        unit_offsets_m=block.unit_offsets_m,
        land_area_m2=_land,
        land_per_block_m2=round(_land / max(1, n_blocks), 1),
        land_per_mwh_m2=round(_land / _energy, 2) if _energy > 0 else 0.0,
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
    mv_w = layout.station_length_m   # 20 ft cabin or 40 ft flagship — never fixed
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
    offsets = layout.unit_offsets_m or tuple(
        u * (6.058 + layout.end_gap_m) for u in range(units)
    )
    for u in range(units):
        ux = dc_x0 + offsets[u] * s
        _r(parts, ux, y0 + 0.15 * s, 6.058 * s, 2.438 * s, _DC, _BLOCK_EDGE, 0.7)
        _r(parts, ux, y0 + (0.15 + 2.438 + 0.3) * s, 6.058 * s, 2.438 * s, _DC, _BLOCK_EDGE, 0.7)


def render_site_svg(layout: SiteArrayLayout,
                    site_profile: SiteRuleProfile = US_NFPA_SITE) -> str:
    """Whole-site concept arrangement (top-down), grouped with fire roads only
    between groups and along the top/bottom perimeter."""
    s = 8.0  # px per metre (site scale)
    margin_l, margin_r, margin_t, margin_b = 60.0, 100.0, 70.0, 96.0
    per = site_profile.perimeter_clear_m
    corridor = site_profile.mv_corridor_m
    aisle = site_profile.maintenance_aisle_m
    road = site_profile.fire_road_m
    bw, bd = layout.block_w_m, layout.block_d_m

    width = margin_l + layout.envelope_w_m * s + margin_r
    height = margin_t + layout.envelope_d_m * s + margin_b

    parts: List[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} '
                 f'{height:.0f}" font-family="Consolas, monospace">')
    _r(parts, 0, 0, width, height, _GROUND, rx=0)

    ox, oy = margin_l, margin_t
    env_w_px = layout.envelope_w_m * s
    # perimeter fence
    _r(parts, ox, oy, env_w_px, layout.envelope_d_m * s, "none", _FENCE, 2.0, rx=0)

    row_w = (2 * bw + corridor) if max(layout.blocks_per_row) == 2 else bw
    row_x0 = ox + (layout.envelope_w_m - row_w) / 2 * s
    cx = row_x0 + (bw + corridor / 2) * s  # corridor centre (2-block rows)

    def fire_road(y_top_m: float, label: bool = False) -> None:
        ry = oy + y_top_m * s
        _r(parts, ox + 2, ry, env_w_px - 4, road * s, _ROAD, rx=0)
        for dash_x in range(int(ox), int(ox + env_w_px), 44):
            _r(parts, dash_x + 8, ry + road * s / 2 - 1, 22, 2, "#e4e6e2", rx=0)

    # walk groups top→bottom: [road] group [road] group ... [road]
    y = 0.0
    fire_road(y)                       # top perimeter road
    y += road
    row_idx = 0
    corridor_top = None
    corridor_bot = None
    for gi, gr in enumerate(layout.rows_per_group):
        group_top = y
        for r in range(gr):
            ry_m = y
            ry = oy + ry_m * s
            n_in_row = layout.blocks_per_row[row_idx]
            _block_glyph(parts, s, row_x0, ry, layout, mv_left=False)
            _t(parts, row_x0 + bw * s / 2, ry - 5, f"AC BLOCK {row_idx*2+1}", size=9.5)
            if n_in_row == 2:
                rx0 = row_x0 + (bw + corridor) * s
                _block_glyph(parts, s, rx0, ry, layout, mv_left=True)
                _t(parts, rx0 + bw * s / 2, ry - 5, f"AC BLOCK {row_idx*2+2}", size=9.5)
                _r(parts, row_x0 + bw * s, ry, corridor * s, bd * s, "#dfe1dd", rx=0)
            row_idx += 1
            y += bd
            if r < gr - 1:
                y += aisle          # maintenance aisle between rows in a group
        # MV corridor duct spanning this group
        if corridor_top is None:
            corridor_top = oy + (group_top + bd / 2) * s
        corridor_bot = oy + (y - bd / 2) * s
        parts.append(f'<line x1="{cx:.1f}" y1="{oy + (group_top+bd/2)*s:.1f}" '
                     f'x2="{cx:.1f}" y2="{oy + (y-bd/2)*s:.1f}" stroke="{_DUCT}" '
                     f'stroke-width="2.5" stroke-dasharray="8 5" opacity="0.85"/>')
        # fire road after each group (between groups + bottom perimeter)
        fire_road(y)
        y += road

    # feeder collection down the corridor + east to substation, on the top road
    fy = oy + (road / 2) * s
    if corridor_top is not None:
        parts.append(f'<line x1="{cx:.1f}" y1="{fy:.1f}" x2="{cx:.1f}" '
                     f'y2="{corridor_top:.1f}" stroke="{_DUCT}" stroke-width="2" '
                     f'stroke-dasharray="6 4" opacity="0.7"/>')
    parts.append(f'<line x1="{cx:.1f}" y1="{fy:.1f}" x2="{ox + env_w_px - 8:.1f}" '
                 f'y2="{fy:.1f}" stroke="{_DUCT}" stroke-width="2.5" '
                 f'stroke-dasharray="8 5" opacity="0.85"/>')
    _t(parts, ox + env_w_px - 10, fy - 6, "MV FEEDERS -> SUBSTATION",
       size=9.5, anchor="end")
    # hydrants on the top perimeter road
    for hx in (ox + 8, ox + env_w_px - 8):
        parts.append(f'<circle cx="{hx:.1f}" cy="{fy:.1f}" r="4.2" fill="{_HYDRANT}" '
                     f'stroke="#801d15" stroke-width="1.3"/>')

    # title + dims + concept note
    grp_txt = (f"{layout.groups} group(s) of ≤ {layout.blocks_per_group} blocks · "
               f"{layout.fire_roads} internal fire road(s)")
    _t(parts, margin_l, 30,
       f"CONCEPT SITE ARRANGEMENT · {layout.n_blocks} × AC BLOCK "
       f"({layout.dc_per_block}×DC) · {layout.total_power_mw:.0f} MW / "
       f"{layout.total_energy_mwh:.1f} MWh", size=11.5, anchor="start")
    _t(parts, margin_l, 46, grp_txt, size=10, anchor="start", weight=600, fill="#5b6367")
    _dim(parts, ox, oy + layout.envelope_d_m * s + 22,
         ox + env_w_px, oy + layout.envelope_d_m * s + 22,
         f"{layout.envelope_w_m:.1f} m site envelope", above=False)
    _dim(parts, ox - 22, oy, ox - 22, oy + layout.envelope_d_m * s,
         f"{layout.envelope_d_m:.1f} m", above=True)
    _t(parts, margin_l, height - 16,
       "CONCEPT ONLY — NOT FOR CONSTRUCTION · envelope estimate, not a site layout",
       size=10.5, anchor="start", weight=600, fill="#5b6367")

    parts.append("</svg>")
    return "".join(parts)
