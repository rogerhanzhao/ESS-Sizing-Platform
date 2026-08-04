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

MINIMUM LAND IS THE OBJECTIVE (owner, 2026-08-03)
-------------------------------------------------
- Blocks per row is SEARCHED (plan_site_packing), not fixed at 2. A site is a
  rectangle whose road and perimeter cost scales with its PERIMETER, so the
  blocks-per-row that squares it up is the cheap one. Fixed 2/row happens to be
  right for a small site and costs ~10% on a large one.
- Groups are filled to the fire-access reach, because every extra group costs a
  6.0 m road across the whole site.
- Fire roads form a connected PERIMETER LOOP. Internal E-W roads used to end at
  the fence with nothing joining them: no apparatus route, no site entrance, and
  a land figure that flattered long thin sites because only their two short ends
  paid for road.
- perimeter_clear_m is NOT stacked on top of the loop road; a 6.0 m road already
  exceeds the 3.0 m clearance to the lot line.

Any block form can be tiled: pass a ``BlockForm``. A block whose PCS & MV Station
sits at the ROW END is ``mirrorable`` and two neighbours share the narrow MV
corridor; a central-station block is not, and takes the full maintenance aisle
between blocks. A BlockForm may carry the block's REAL placements, which is how
the central-station bilateral unit gets composed as the block it is instead of a
linear stand-in.

WHAT THE LAND FIGURE IS NOT: equipment and access inside the perimeter road. It
excludes the substation, O&M building, laydown, stormwater and lot-line setbacks.
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
    blocks_per_row: Tuple[int, ...]      # blocks placed in each row
    groups: int                          # project groups (fire road only between groups)
    # The blocks in the LARGEST group as actually packed — a RESULT, not the cap
    # that was asked for. Reporting the requested cap here made the report state
    # "groups of <= 8 blocks" for a site whose groups hold 40.
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
    # Chosen to minimise land, not fixed at 2 (see plan_site_packing).
    blocks_per_row_target: int = 2
    block_form_label: str = "linear_mirrored_pairs"
    block_mirrorable: bool = True
    block_placements: Tuple[dict, ...] = ()
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


@dataclass(frozen=True)
class BlockForm:
    """The AC Block as the SITE sees it: a footprint plus how it may be tiled."""

    w_m: float
    d_m: float
    label: str = "linear_mirrored_pairs"
    dc_per_block: int = 0
    station_length_m: float = 6.058
    unit_offsets_m: Tuple[float, ...] = ()
    # True when the PCS & MV Station sits at the ROW END, so two mirrored blocks
    # can put their stations face to face and share the narrow MV corridor. A
    # central-station block cannot: its outward faces are DC doors and DC
    # equipment ends, which need the full maintenance aisle between blocks.
    mirrorable: bool = True
    # Real block-local equipment placements, when the caller has them. The site
    # glyph draws these instead of reconstructing a generic linear block — that
    # reconstruction is what made a central-station block undrawable.
    placements: Tuple[dict, ...] = ()


@dataclass(frozen=True)
class SitePacking:
    blocks_per_row: int
    rows: int
    rows_per_group: Tuple[int, ...]
    groups: int
    envelope_w_m: float
    envelope_d_m: float
    land_area_m2: float
    fire_access_reach_m: float


def _row_separator_span_m(b: int, form: BlockForm,
                          site_profile: SiteRuleProfile) -> float:
    """Total separator width inside a row of ``b`` blocks."""
    if b <= 1:
        return 0.0
    if not form.mirrorable:
        return (b - 1) * site_profile.maintenance_aisle_m
    # [B][corridor][B'] pairs, maintenance aisle between pairs.
    pairs = b // 2
    between = (b + 1) // 2 - 1
    return pairs * site_profile.mv_corridor_m + between * site_profile.maintenance_aisle_m


def _pack_at(n_blocks: int, b: int, form: BlockForm,
             site_profile: SiteRuleProfile,
             max_blocks_per_group: Optional[int] = None) -> SitePacking:
    rows = -(-n_blocks // b)
    rpg = _max_rows_per_group(form.d_m, site_profile)
    if max_blocks_per_group is not None:
        # A group cap is stated in BLOCKS, so it converts to rows only once the
        # blocks-per-row is known. Deriving it as ceil(cap / 2) — as the code did
        # while 2 per row was hardcoded — silently turned a cap of 8 into groups
        # of 20 as soon as the packing search picked a wider row.
        # FLOOR, not ceil: ceil(cap / b) overshoots — a cap of 8 with 5 blocks
        # per row would allow 2 rows, i.e. 10 blocks in a group.
        rpg = max(1, min(rpg, max(1, int(max_blocks_per_group)) // b))
    sizes: List[int] = []
    left = rows
    while left > 0:
        take = min(rpg, left)
        sizes.append(take)
        left -= take
    aisle = site_profile.maintenance_aisle_m
    road = site_profile.fire_road_m
    inner_w = b * form.w_m + _row_separator_span_m(b, form, site_profile)
    inner_d = (sum(g * form.d_m + (g - 1) * aisle for g in sizes)
               + (len(sizes) - 1) * road)
    # The perimeter LOOP road: internal roads are stubs unless something joins
    # them, and a site with no loop has no apparatus route and no entrance.
    env_w = inner_w + 2 * road
    env_d = inner_d + 2 * road
    reach = max(g * form.d_m + (g - 1) * aisle for g in sizes) / 2.0
    return SitePacking(
        blocks_per_row=b,
        rows=rows,
        rows_per_group=tuple(sizes),
        groups=len(sizes),
        envelope_w_m=round(env_w, 2),
        envelope_d_m=round(env_d, 2),
        land_area_m2=round(env_w * env_d, 1),
        fire_access_reach_m=round(reach, 2),
    )


def plan_site_packing(n_blocks: int, form: BlockForm,
                      site_profile: SiteRuleProfile = US_NFPA_SITE,
                      *, blocks_per_row: Optional[int] = None,
                      max_blocks_per_group: Optional[int] = None) -> SitePacking:
    """Blocks-per-row that MINIMISES site land, subject to fire access.

    Owner objective 2026-08-03: "综合整站占地面积最小". Blocks per row used to be
    fixed at 2 regardless of the block's shape or the project size, which is
    right for small sites and costs up to ~10% on large ones — a site is a
    rectangle, and its road and perimeter cost scales with the PERIMETER, so the
    number of blocks per row that squares it up is the cheap one.

    Pass ``blocks_per_row`` to force a value instead of searching.
    """
    if n_blocks < 1:
        raise ValueError(f"n_blocks must be >= 1, got {n_blocks}")
    if blocks_per_row is not None:
        return _pack_at(n_blocks, max(1, int(blocks_per_row)), form,
                        site_profile, max_blocks_per_group)
    # A group cap of N blocks also caps the ROW: a row wider than the cap could
    # never fit inside one group, whatever the row count.
    widest = n_blocks if max_blocks_per_group is None else min(
        n_blocks, max(1, int(max_blocks_per_group)))
    candidates = [
        _pack_at(n_blocks, b, form, site_profile, max_blocks_per_group)
        for b in range(1, widest + 1)
    ]
    # Ties broken toward fewer blocks per row: shallower rows keep the fire
    # access reach shorter and the MV runs inside a row shorter.
    return min(candidates, key=lambda p: (p.land_area_m2, p.blocks_per_row))


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
    block_form: Optional[BlockForm] = None,
    blocks_per_row: Optional[int] = None,
) -> SiteArrayLayout:
    """Blocks grouped by project; fire roads only between groups, not per row.

    Within a group, mirrored blocks share a central MV corridor and are separated
    only by a maintenance aisle. Fire apparatus roads run between groups and as a
    PERIMETER LOOP, so every block is inside ``fire_access_limit_m`` of a road AND
    the roads are actually connected to one another and to a site entrance.

    Blocks per row is CHOSEN to minimise land (see plan_site_packing) unless the
    caller forces it; ``block_form`` lets the caller tile a block this module
    cannot reconstruct from ``dc_per_block`` alone, such as the central-station
    bilateral unit.
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

    form = block_form or BlockForm(
        w_m=block_w,
        d_m=block_d,
        label="linear_mirrored_pairs",
        dc_per_block=dc_per_block,
        station_length_m=station_len_m,
        unit_offsets_m=block.unit_offsets_m,
        mirrorable=True,
    )
    block_w, block_d = form.w_m, form.d_m

    # An explicit blocks_per_group only ever TIGHTENS the automatic grouping.
    packing = plan_site_packing(
        n_blocks, form, site_profile,
        blocks_per_row=blocks_per_row,
        max_blocks_per_group=None if blocks_per_group is None else bpg,
    )

    b = packing.blocks_per_row
    per_row: List[int] = []
    remaining = n_blocks
    while remaining > 0:
        take = min(b, remaining)
        per_row.append(take)
        remaining -= take
    rows = packing.rows
    rows_per_group = list(packing.rows_per_group)
    groups = packing.groups
    env_w = packing.envelope_w_m
    env_d = packing.envelope_d_m
    reach = packing.fire_access_reach_m

    _land = round(env_w * env_d, 1)
    _energy = round(_resolved_dc_blocks * _resolved_dc_energy_mwh, 2)
    return SiteArrayLayout(
        n_blocks=n_blocks,
        dc_per_block=dc_per_block,
        rows=rows,
        blocks_per_row=tuple(per_row),
        groups=groups,
        blocks_per_group=b * max(rows_per_group),
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
        station_length_m=form.station_length_m,
        end_gap_m=block.end_gap_m,
        unit_offsets_m=form.unit_offsets_m,
        blocks_per_row_target=b,
        block_form_label=form.label,
        block_mirrorable=form.mirrorable,
        block_placements=tuple(form.placements),
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

    # When the caller supplied real block-local placements, draw THOSE. A
    # central-station block cannot be reconstructed from dc_per_block alone, and
    # guessing it as a linear block is how the same product ends up with two
    # different footprints in one report.
    if layout.block_placements:
        for p in layout.block_placements:
            fill = _MV if p.get("equipment_type") == "ac_station" else _DC
            _r(parts, x0 + float(p["x_m"]) * s, y0 + float(p["y_m"]) * s,
               float(p["width_m"]) * s, float(p["height_m"]) * s,
               fill, _BLOCK_EDGE, 0.7)
        return

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
    # perimeter_clear_m is not added on top of the loop road: a 6.0 m road already
    # exceeds the 3.0 m clearance to the lot line, and stacking both would report
    # land the code does not ask for.
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

    # Block x-offsets within a row, from the row's own separator sequence.
    b = max(1, layout.blocks_per_row_target)

    def _block_x_offsets(count: int) -> List[float]:
        offsets, cursor = [], 0.0
        for i in range(count):
            offsets.append(cursor)
            cursor += bw
            if i < count - 1:
                if layout.block_mirrorable and i % 2 == 0:
                    cursor += corridor      # inside a mirrored pair
                else:
                    cursor += aisle         # between pairs / non-mirrorable
        return offsets

    row_offsets = _block_x_offsets(b)
    row_w = (row_offsets[-1] + bw) if row_offsets else bw
    row_x0 = ox + (layout.envelope_w_m - row_w) / 2 * s
    # MV collection spine runs down the FIRST separator, whatever kind it is.
    # Centring it on the row instead puts it straight through a block as soon as
    # a row holds an odd number of them.
    if b >= 2:
        _gap0 = row_offsets[1] - (row_offsets[0] + bw)
        cx = row_x0 + (bw + _gap0 / 2) * s
    else:
        cx = row_x0 + row_w * s / 2

    def fire_road(y_top_m: float) -> None:
        ry = oy + y_top_m * s
        _r(parts, ox, ry, env_w_px, road * s, _ROAD, rx=0)
        for dash_x in range(int(ox), int(ox + env_w_px), 44):
            _r(parts, dash_x + 8, ry + road * s / 2 - 1, 22, 2, "#e4e6e2", rx=0)

    # PERIMETER LOOP ROAD. Without it the internal roads are disconnected stubs:
    # apparatus cannot travel from one to the next and the site has no entrance.
    _r(parts, ox, oy, env_w_px, road * s, _ROAD, rx=0)
    _r(parts, ox, oy + (layout.envelope_d_m - road) * s, env_w_px, road * s, _ROAD, rx=0)
    _r(parts, ox, oy, road * s, layout.envelope_d_m * s, _ROAD, rx=0)
    _r(parts, ox + (layout.envelope_w_m - road) * s, oy, road * s,
       layout.envelope_d_m * s, _ROAD, rx=0)

    # walk groups top→bottom: [loop road] group [road] group ... [loop road]
    y = road
    row_idx = 0
    placed = 0
    corridor_top = None
    for gi, gr in enumerate(layout.rows_per_group):
        group_top = y
        for r in range(gr):
            ry = oy + y * s
            n_in_row = layout.blocks_per_row[row_idx]
            for k in range(n_in_row):
                bx = row_x0 + row_offsets[k] * s
                # In a mirrored pair the second block faces its station back at
                # the first, so the two stations share one MV corridor.
                _block_glyph(parts, s, bx, ry, layout,
                             mv_left=bool(layout.block_mirrorable and k % 2 == 1))
                placed += 1
                _t(parts, bx + bw * s / 2, ry - 5, f"AC BLOCK {placed}", size=9.5)
                if k < n_in_row - 1:
                    gap = row_offsets[k + 1] - (row_offsets[k] + bw)
                    _r(parts, bx + bw * s, ry, gap * s, bd * s, "#dfe1dd", rx=0)
            row_idx += 1
            y += bd
            if r < gr - 1:
                y += aisle          # maintenance aisle between rows in a group
        # MV corridor duct spanning this group
        if corridor_top is None:
            corridor_top = oy + (group_top + bd / 2) * s
        parts.append(f'<line x1="{cx:.1f}" y1="{oy + (group_top+bd/2)*s:.1f}" '
                     f'x2="{cx:.1f}" y2="{oy + (y-bd/2)*s:.1f}" stroke="{_DUCT}" '
                     f'stroke-width="2.5" stroke-dasharray="8 5" opacity="0.85"/>')
        if gi < len(layout.rows_per_group) - 1:
            fire_road(y)            # internal road, tied into the loop at both ends
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
    _t(parts, margin_l, height - 32,
       f"{layout.land_area_m2:,.0f} m2 inside the perimeter road "
       f"({layout.land_per_block_m2:,.0f} m2/AC Block · "
       f"{layout.land_per_mwh_m2:.1f} m2/MWh) — EQUIPMENT AND ACCESS ONLY: "
       f"excludes substation, O&M building, laydown, stormwater and setbacks",
       size=9.5, anchor="start", weight=600, fill="#5b6367")
    _t(parts, margin_l, height - 16,
       "CONCEPT ONLY — NOT FOR CONSTRUCTION · envelope estimate, not a site layout",
       size=10.5, anchor="start", weight=600, fill="#5b6367")

    parts.append("</svg>")
    return "".join(parts)
