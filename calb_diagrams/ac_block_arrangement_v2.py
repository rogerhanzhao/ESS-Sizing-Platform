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

"""Rule-based Typical AC Block Arrangement engine (Layout Roadmap L1).

Geometry basis: docs/AC_BLOCK_PRODUCT_KNOWLEDGE_2026-07-18.md (§2 appearance,
§4 composition) and docs/LAYOUT_ROADMAP_V1_2026-07-18.md §1.1.

Owner rules encoded here:
- DC containers install as MIRRORED back-to-back pairs (doors outward,
  corrugated backs facing the pair gap); roof explosion-vent row sits on the
  NO-DOOR edge, i.e. toward the pair gap.
- Every spacing value comes from an ArrangementRuleProfile — no hardcoded
  aisles. The US/international profile is the default design basis.
- The PCS & MV station is a containerized turnkey unit drawn brand-neutral; its
  LENGTH is resolved from the AC Block class (see resolve_station_length_m).

NOTHING DIMENSIONAL MAY BE HARDCODED IN A LAYOUT MODULE (owner, 2026-08-03)
--------------------------------------------------------------------------
Station size, per-block power and per-DC-Block energy must all be resolved from
the run or from a rule profile — never written as a module constant that happens
to match one product. Two defects in the 2026-08-03 report came from exactly
that: a 10 MW / 8-PCS AC Block drawn with the 20 ft cabin (MV_LENGTH_M was a
constant), and a site figure that reported half the project's power (the
nameplate was a constant in site_array_concept). The ISO constants below are
CATALOGUE dimensions selected by resolve_station_length_m; they are not defaults
any caller may silently inherit.

The equipment glyphs (draw_dc_container / draw_mv_station) are shared with
calb_diagrams.ac_block_bilateral_layout so both engines draw the same product
from the same viewpoint. Do not fork a private copy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple
from xml.sax.saxutils import escape as _xml_escape

DC_LENGTH_M = 6.058
DC_WIDTH_M = 2.438
DC_HEIGHT_M = 2.896

# SHARED ISO station dimensions — the single source of truth for BOTH this linear
# engine and calb_diagrams/ac_block_bilateral_layout.py. They used to be written
# separately in each module, which is exactly how a 10 MW / 8-PCS AC Block ended
# up drawn with a 20 ft station in the 2026-08-03 report.
AC_STATION_20FT_LENGTH_M = 6.058
AC_STATION_40FT_LENGTH_M = 12.192
AC_STATION_WIDTH_M = 2.438

# A 5 MW / <=4 PCS AC Block is a 20 ft integrated cabin; the 8-PCS / 10 MW class
# is the 40 ft flagship (docs/AC_BLOCK_PRODUCT_KNOWLEDGE_2026-07-18.md §4, and the
# governed configuration code ACBLK-10MW-8PCS-8DC-40FT-BILATERAL).
AC_STATION_40FT_MIN_PCS = 8
AC_STATION_40FT_MIN_MW = 10.0

# Back-compat aliases (the 20 ft cabin remains the default station).
MV_LENGTH_M = AC_STATION_20FT_LENGTH_M
MV_WIDTH_M = AC_STATION_WIDTH_M


def resolve_station_length_m(pcs_count: int | None = None,
                             block_power_mw: float | None = None) -> float:
    """PCS & MV Station length from the AC Block class — never a fixed constant.

    >= 8 PCS or >= 10 MW resolves to the 40 ft station; anything smaller (and the
    unknown case) keeps the 20 ft integrated cabin.
    """
    try:
        pcs = int(pcs_count or 0)
    except (TypeError, ValueError):
        pcs = 0
    try:
        power = float(block_power_mw or 0.0)
    except (TypeError, ValueError):
        power = 0.0
    if pcs >= AC_STATION_40FT_MIN_PCS or power >= AC_STATION_40FT_MIN_MW:
        return AC_STATION_40FT_LENGTH_M
    return AC_STATION_20FT_LENGTH_M


@dataclass(frozen=True)
class ArrangementRuleProfile:
    """Per-market spacing rule set for the AC block arrangement."""

    key: str
    market_label: str
    dc_pair_gap_m: float        # mirrored back-to-back adjacency
    dc_to_mv_aisle_m: float     # DC row to PCS & MV station
    pair_to_pair_gap_m: float   # between adjacent mirrored pairs (plain END faces)
    # The DC Block's EQUIPMENT END (liquid-cooling unit + fan grilles) needs the
    # same clearance as the AC Block aisle; only the opposite plain end may take
    # the reduced pair-to-pair gap (owner ruling, 2026-08-03).
    dc_equipment_end_gap_m: float
    mvt_type: str               # "oil" | "dry"
    basis: Tuple[Tuple[str, str, str], ...]  # (parameter, value, code basis)


US_NFPA_OIL = ArrangementRuleProfile(
    key="us_nfpa_oil",
    market_label="International — IFC / NFPA 855 / NFPA 850 / UL 9540A",
    dc_pair_gap_m=0.30,
    dc_to_mv_aisle_m=3.0,
    pair_to_pair_gap_m=0.9,
    dc_equipment_end_gap_m=3.0,
    mvt_type="oil",
    basis=(
        ("DC pair adjacency (back-to-back)", "0.30 m",
         "UL 9540A large-scale fire-test exemption (NFPA 855 default 3 ft)"),
        ("DC to PCS & MV station aisle", "3.0 m (10 ft)",
         "NFPA 850 — oil-insulated equipment (< 500 gal) to BESS"),
        ("Pair-to-pair gap (plain end)", "0.9 m (3 ft)",
         "NFPA 855 §9.5 unit separation — owner: 0.9 m preferred over 0.3 m"),
        ("DC Block equipment end (liquid-cooling + fan grilles)", "3.0 m (10 ft)",
         "Owner ruling 2026-08-03 — same clearance as the AC Block aisle"),
        ("Maintenance access", "Door sides face outward aisles",
         "Owner rule / mirrored pairing"),
    ),
)

ARRANGEMENT_RULE_PROFILES = {profile.key: profile for profile in (US_NFPA_OIL,)}


def end_gap_sequence(units: int,
                     profile: ArrangementRuleProfile) -> Tuple[float, ...]:
    """Gaps between adjacent DC units along a row, in order.

    LAND RULE (owner 2026-08-03, "综合整站占地面积最小"): the DC Block's EQUIPMENT
    END (liquid-cooling unit + fan grilles) needs 3.0 m; the opposite plain end
    needs only 0.9 m. Point every other unit the other way round, so the
    3.0-demanding ends land on the BLOCK BOUNDARY — where the site already has to
    provide a >= 3.0 m maintenance aisle for access — and the plain ends meet
    INSIDE the block at 0.9 m.

    Putting the equipment ends inward instead makes the block 2.1 m deeper per
    pair of rows and buys nothing: the boundary aisle is required either way.
    Measured over a 13-block site that costs about 10% of the total land.

    Returns ``units - 1`` gaps alternating 0.9 / 3.0, starting at 0.9.
    """
    return tuple(
        profile.pair_to_pair_gap_m if i % 2 == 0 else profile.dc_equipment_end_gap_m
        for i in range(max(0, units - 1))
    )


def unit_offsets_m(units: int, profile: ArrangementRuleProfile) -> Tuple[float, ...]:
    """Along-row offset of each DC unit's near edge, from the field origin."""
    offsets, cursor = [], 0.0
    for i in range(max(0, units)):
        offsets.append(round(cursor, 3))
        gaps = end_gap_sequence(units, profile)
        if i < len(gaps):
            cursor += DC_LENGTH_M + gaps[i]
    return tuple(offsets)


@dataclass(frozen=True)
class ArrangementLayout:
    dc_count: int
    pair_count: int
    has_single_tail: bool
    envelope_w_m: float
    envelope_d_m: float
    profile_key: str
    station_length_m: float = MV_LENGTH_M   # 20 ft cabin or 40 ft flagship
    # Alternating DC END-face clearances. ``end_gap_m`` is the SMALLEST gap used
    # (plain end to plain end); ``boundary_end_gap_m`` is what the site must give
    # the equipment ends that now face outward.
    end_gap_m: float = 0.9
    boundary_end_gap_m: float = 3.0
    end_gaps_m: Tuple[float, ...] = ()
    unit_offsets_m: Tuple[float, ...] = ()


def compute_layout(dc_count: int, profile: ArrangementRuleProfile,
                   *, pcs_count: int | None = None,
                   block_power_mw: float | None = None,
                   station_length_m: float | None = None) -> ArrangementLayout:
    """Envelope of one AC block: mirrored DC pairs + aisle + PCS & MV station.

    ``station_length_m`` overrides the station size; otherwise it is resolved from
    the AC Block class (``pcs_count`` / ``block_power_mw``) — a 10 MW / 8-PCS block
    is a 40 ft station, never the 20 ft cabin.

    Gaps between adjacent mirrored pairs ALTERNATE 0.9 / 3.0 (see
    end_gap_sequence): every other unit is turned end-for-end so the equipment
    ends face the block boundary, where the site aisle already provides 3.0 m,
    and the plain ends meet inside the block at 0.9 m.
    """
    if dc_count < 1:
        raise ValueError(f"dc_count must be >= 1, got {dc_count}")
    pairs = dc_count // 2
    tail = dc_count % 2
    units = pairs + tail
    station_len = (
        float(station_length_m) if station_length_m
        else resolve_station_length_m(pcs_count, block_power_mw)
    )
    gaps = end_gap_sequence(units, profile)
    offsets = unit_offsets_m(units, profile)
    dc_span = units * DC_LENGTH_M + sum(gaps)
    envelope_w = dc_span + profile.dc_to_mv_aisle_m + station_len
    envelope_d = (DC_WIDTH_M * 2 + profile.dc_pair_gap_m) if dc_count >= 2 else DC_WIDTH_M
    return ArrangementLayout(
        dc_count=dc_count,
        pair_count=pairs,
        has_single_tail=bool(tail),
        envelope_w_m=round(envelope_w, 3),
        envelope_d_m=round(envelope_d, 3),
        profile_key=profile.key,
        station_length_m=round(station_len, 3),
        end_gap_m=round(profile.pair_to_pair_gap_m, 3),
        boundary_end_gap_m=round(profile.dc_equipment_end_gap_m, 3),
        end_gaps_m=gaps,
        unit_offsets_m=offsets,
    )


# ---------------------------------------------------------------------------
# Plan-view SVG rendering
# ---------------------------------------------------------------------------

_INK = "#1f4e79"
_PAD = "#d3d5d1"
_PAD_EDGE = "#b3b6b2"
_BOX = "#eef0ef"
_BOX_EDGE = "#aeb5b4"
_VENT = "#e2e5e4"
_VENT_EDGE = "#b9c0bf"
_SHADOW = "#3a3f42"
_TRENCH = "#9fa5a3"
_TRENCH_EDGE = "#868c8a"
_LOUVER = "#c2c8c7"
_GROUND = "#c6cac5"
_MV_BODY = "#f0f2f1"
_DOOR = "#1f4e79"


def _rect(parts: List[str], x: float, y: float, w: float, h: float, fill: str,
          stroke: Optional[str] = None, stroke_w: float = 1.0, rx: float = 2.0,
          opacity: Optional[float] = None) -> None:
    extra = f' stroke="{stroke}" stroke-width="{stroke_w}"' if stroke else ""
    if opacity is not None:
        extra += f' opacity="{opacity}"'
    parts.append(
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
        f'fill="{fill}" rx="{rx}"{extra}/>'
    )


def _text(parts: List[str], x: float, y: float, s: str, size: float = 12,
          anchor: str = "middle", weight: int = 700, fill: str = _INK) -> None:
    # NOTE: no stroke halo — cairosvg does not honour paint-order and would
    # stroke over the glyph fill, making text unreadable in the report PNG.
    parts.append(
        f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-size="{size}" '
        f'font-family="Consolas, monospace" font-weight="{weight}" '
        f'text-anchor="{anchor}">{_xml_escape(s)}</text>'
    )


def _dim(parts: List[str], x1: float, y1: float, x2: float, y2: float,
         label: str, above: bool = True, size: float = 11.5) -> None:
    parts.append(
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{_INK}" stroke-width="1.2"/>'
    )
    for px, py in ((x1, y1), (x2, y2)):
        parts.append(
            f'<line x1="{px - 3.5:.1f}" y1="{py - 3.5:.1f}" x2="{px + 3.5:.1f}" '
            f'y2="{py + 3.5:.1f}" stroke="{_INK}" stroke-width="1.1"/>'
        )
    off = -6 if above else 14
    _text(parts, (x1 + x2) / 2, (y1 + y2) / 2 + off, label, size=size)


# ---------------------------------------------------------------------------
# Shared equipment glyphs
#
# BOTH arrangement engines — this linear one and
# calb_diagrams/ac_block_bilateral_layout — draw their equipment through these
# helpers, so a DC Block and a PCS & MV Station always read as the same product
# whichever engine produced the plan. Two private copies of the same glyph is
# exactly how the 2026-08-03 report ended up showing two "typical AC Block"
# drawings that did not look like the same product.
# ---------------------------------------------------------------------------

_VENTS_PER_CONTAINER = 4
_VENT_SIZE_M = 0.88
_VENT_END_MARGIN_M = 0.62   # along the container's long axis
_VENT_FACE_MARGIN_M = 0.20  # from the door-free edge


def draw_dc_container(parts: List[str], s: float, x: float, y: float, *,
                      width_m: float = DC_LENGTH_M,
                      height_m: float = DC_WIDTH_M,
                      door_orientation: str = "south",
                      equipment_end: Optional[str] = None) -> None:
    """One DC Block in plan view, at pixel origin ``(x, y)``.

    ``width_m`` / ``height_m`` are the AS-PLACED east-west / north-south
    footprint, so the same helper draws a container laid along the row
    (6.058 x 2.438) or standing across it (2.438 x 6.058).

    The roof explosion-vent row always sits on the DOOR-FREE edge — that edge is
    the corrugated back that faces the 0.30 m mirrored-pair gap — and the door
    edge carries a solid marker.

    ``equipment_end`` ("north"/"south"/"east"/"west") draws the liquid-cooling +
    fan-grille end as a louvred band. Which end that is decides real land: it
    demands 3.0 m while the opposite plain end needs 0.9 m, so the drawing has to
    show it rather than leave the reader to assume the container is symmetric.
    """
    w_px, h_px = width_m * s, height_m * s
    _rect(parts, x + 3, y + 3, w_px, h_px, _SHADOW, opacity=0.15)
    _rect(parts, x, y, w_px, h_px, _BOX, _BOX_EDGE, 1.0)

    vent = _VENT_SIZE_M
    n = _VENTS_PER_CONTAINER
    horizontal = width_m >= height_m
    span_m = width_m if horizontal else height_m
    pitch = max(0.0, (span_m - 2 * _VENT_END_MARGIN_M - vent) / max(1, n - 1))
    for i in range(n):
        along = _VENT_END_MARGIN_M + i * pitch
        if horizontal:
            vy = (_VENT_FACE_MARGIN_M if door_orientation == "south"
                  else height_m - vent - _VENT_FACE_MARGIN_M)
            _rect(parts, x + along * s, y + vy * s, vent * s, vent * s,
                  _VENT, _VENT_EDGE, 0.8, rx=1.5)
        else:
            vx = (_VENT_FACE_MARGIN_M if door_orientation == "east"
                  else width_m - vent - _VENT_FACE_MARGIN_M)
            _rect(parts, x + vx * s, y + along * s, vent * s, vent * s,
                  _VENT, _VENT_EDGE, 0.8, rx=1.5)

    # Liquid-cooling unit + fan grilles on the equipment end.
    if equipment_end in ("north", "south"):
        band_h = min(0.55, height_m * 0.18)
        by = y if equipment_end == "north" else y + h_px - band_h * s
        for i in range(5):
            _rect(parts, x + (0.18 + i * (width_m - 0.5) / 5) * s, by + 2,
                  (width_m - 0.5) / 5 * 0.7 * s, band_h * s - 4, _LOUVER, rx=0)
    elif equipment_end in ("east", "west"):
        band_w = min(0.55, width_m * 0.18)
        bx = x if equipment_end == "west" else x + w_px - band_w * s
        for i in range(5):
            _rect(parts, bx + 2, y + (0.18 + i * (height_m - 0.5) / 5) * s,
                  band_w * s - 4, (height_m - 0.5) / 5 * 0.7 * s, _LOUVER, rx=0)

    bar = 2.5
    if door_orientation == "north":
        _rect(parts, x + w_px * 0.30, y, w_px * 0.40, bar, _DOOR, rx=0)
    elif door_orientation == "south":
        _rect(parts, x + w_px * 0.30, y + h_px - bar, w_px * 0.40, bar, _DOOR, rx=0)
    elif door_orientation == "west":
        _rect(parts, x, y + h_px * 0.30, bar, h_px * 0.40, _DOOR, rx=0)
    elif door_orientation == "east":
        _rect(parts, x + w_px - bar, y + h_px * 0.30, bar, h_px * 0.40, _DOOR, rx=0)


def draw_mv_station(parts: List[str], s: float, x: float, y: float, *,
                    length_m: float = MV_LENGTH_M,
                    width_m: float = MV_WIDTH_M,
                    vertical: bool = False) -> None:
    """PCS & MV Station — 20 ft cabin or 40 ft flagship, per ``length_m``.

    ``vertical=True`` stands the cabin on end (long axis north-south) for the
    bilateral engine; the louvred PCS bays and the MV termination louvres follow
    the long axis either way.
    """
    w_px = (width_m if vertical else length_m) * s
    h_px = (length_m if vertical else width_m) * s
    _rect(parts, x + 3, y + 3, w_px, h_px, _SHADOW, opacity=0.15)
    _rect(parts, x, y, w_px, h_px, _MV_BODY, _BOX_EDGE, 1.0)

    # Louvred PCS door bays scale with the cabin length (a 40 ft station carries
    # roughly twice the string-PCS bays of a 20 ft one) and spread across the
    # whole cabin instead of bunching at one end.
    bays = max(2, int(round(length_m / 3.0)))
    _bay_start, _mv_reserve = 1.05, 1.60
    _pitch = max(0.0, (length_m - _bay_start - _mv_reserve)) / bays
    for i in range(bays):
        along = _bay_start + i * _pitch
        if along + 0.85 > length_m:
            break
        if vertical:
            _rect(parts, x + 0.55 * s, y + along * s, 0.55 * s, 0.85 * s,
                  _VENT, _VENT_EDGE, 0.8)
        else:
            _rect(parts, x + along * s, y + 0.55 * s, 0.85 * s, 0.55 * s,
                  _VENT, _VENT_EDGE, 0.8)
    # MV termination louvres at the far end of the cabin
    for i in range(6):
        if vertical:
            _rect(parts, x + 0.55 * s, y + (length_m - 1.05 + i * 0.13) * s,
                  1.35 * s, 0.05 * s, _LOUVER, rx=0)
        else:
            _rect(parts, x + (length_m - 1.05 + i * 0.13) * s, y + 0.55 * s,
                  0.05 * s, 1.35 * s, _LOUVER, rx=0)


def _dc_pair_at(parts: List[str], s: float, ox: float, oy: float,
                pair_gap_m: float, equipment_end: str = "west") -> None:
    """One mirrored pair; roof vents on the NO-DOOR edges facing the pair gap."""
    for row_m, door in ((0.0, "north"), (DC_WIDTH_M + pair_gap_m, "south")):
        draw_dc_container(parts, s, ox, oy + row_m * s, door_orientation=door,
                          equipment_end=equipment_end)


def _single_dc(parts: List[str], s: float, ox: float, oy: float,
               equipment_end: str = "west") -> None:
    """Unpaired tail container: doors outward (south), vents on the north edge."""
    draw_dc_container(parts, s, ox, oy, door_orientation="south",
                      equipment_end=equipment_end)


def _mv_station(parts: List[str], s: float, ox: float, oy: float,
                station_len_m: float = MV_LENGTH_M) -> None:
    """PCS & MV Station — 20 ft cabin or 40 ft flagship, per station_len_m."""
    draw_mv_station(parts, s, ox, oy, length_m=station_len_m, width_m=MV_WIDTH_M)


def render_plan_svg(dc_count: int,
                    profile: ArrangementRuleProfile = US_NFPA_OIL,
                    block_label: str = "TYPICAL AC BLOCK",
                    *, pcs_count: int | None = None,
                    block_power_mw: float | None = None,
                    station_length_m: float | None = None) -> Tuple[str, ArrangementLayout]:
    """Top-down typical AC block arrangement drawing (concept).

    The PCS & MV Station is sized from the AC Block class: a 10 MW / 8-PCS block
    draws the 40 ft station, not the 20 ft cabin.
    """
    layout = compute_layout(
        dc_count, profile, pcs_count=pcs_count,
        block_power_mw=block_power_mw, station_length_m=station_length_m,
    )
    s = 44.0  # px per metre
    margin_l, margin_r = 70.0, 40.0
    margin_t, margin_b = 64.0, 96.0
    width = margin_l + (layout.envelope_w_m + 1.2) * s + margin_r
    depth_m = layout.envelope_d_m
    height = margin_t + (depth_m + 1.2) * s + margin_b

    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'font-family="Consolas, monospace">'
    )
    _rect(parts, 0, 0, width, height, _GROUND, rx=0)
    ox0 = margin_l + 0.6 * s
    oy0 = margin_t + 0.6 * s

    # equipment pad under the whole block
    _rect(parts, ox0 - 0.45 * s, oy0 - 0.45 * s,
          (layout.envelope_w_m + 0.9) * s, (depth_m + 0.9) * s,
          _PAD, _PAD_EDGE, 1.0)

    # DC units west, MV station east. Units alternate end-for-end so the
    # equipment ends face the block boundary (see end_gap_sequence).
    units = layout.pair_count + (1 if layout.has_single_tail else 0)
    for u in range(layout.pair_count):
        ux = ox0 + layout.unit_offsets_m[u] * s
        _dc_pair_at(parts, s, ux, oy0, profile.dc_pair_gap_m,
                    equipment_end="west" if u % 2 == 0 else "east")
    if layout.has_single_tail:
        ux = ox0 + layout.unit_offsets_m[units - 1] * s
        _single_dc(parts, s, ux, oy0,
                   equipment_end="west" if (units - 1) % 2 == 0 else "east")

    dc_span_m = units * DC_LENGTH_M + sum(layout.end_gaps_m)
    aisle_x0 = ox0 + dc_span_m * s
    mv_x = aisle_x0 + profile.dc_to_mv_aisle_m * s
    mv_y = oy0 + max(0.0, (depth_m - MV_WIDTH_M) / 2) * s
    _mv_station(parts, s, mv_x, mv_y, layout.station_length_m)

    # cable trench covers across the aisle (bottom cable entries per spec)
    for i in range(4):
        _rect(parts, aisle_x0 + 0.25 * s,
              oy0 + (0.62 + i * 1.05) * s,
              (profile.dc_to_mv_aisle_m - 0.5) * s, 0.30 * s,
              _TRENCH, _TRENCH_EDGE, 0.8, rx=1)

    # labels
    # Raised clear of the aisle / end-gap dimension line that runs at -0.30 m.
    _text(parts, ox0 + dc_span_m * s / 2, oy0 - 0.52 * s - 22,
          f"{dc_count} × DC BLOCK (5.015 MWh, mirrored pairs)", size=12)
    # Centre on the ACTUAL station, not on the 20 ft constant — a 40 ft station
    # would otherwise carry its label a full 3 m off centre.
    _text(parts, mv_x + layout.station_length_m * s / 2, mv_y - 10,
          "PCS & MV STATION", size=12)
    _text(parts, margin_l + 4, 30, block_label + f"  ·  {profile.market_label}",
          size=13, anchor="start")
    _text(parts, margin_l + 4, height - 16,
          "CONCEPT ONLY — NOT FOR CONSTRUCTION", size=10.5, anchor="start",
          weight=600, fill="#5b6367")

    # dimensions
    y_dim = oy0 + (depth_m + 0.55) * s
    _dim(parts, ox0, y_dim, ox0 + layout.envelope_w_m * s, y_dim,
         f"{layout.envelope_w_m:.2f} m envelope", above=False)
    _dim(parts, aisle_x0, oy0 - 0.30 * s, aisle_x0 + profile.dc_to_mv_aisle_m * s,
         oy0 - 0.30 * s, f"{profile.dc_to_mv_aisle_m:.1f} m aisle")
    if dc_count >= 2:
        gx = ox0 - 0.32 * s
        _dim(parts, gx, oy0 + DC_WIDTH_M * s, gx,
             oy0 + (DC_WIDTH_M + profile.dc_pair_gap_m) * s,
             f"{profile.dc_pair_gap_m:.2f} m", size=10.5)
    if units > 1:
        px0 = ox0 + DC_LENGTH_M * s
        _dim(parts, px0, oy0 - 0.30 * s, px0 + layout.end_gaps_m[0] * s,
             oy0 - 0.30 * s, f"{layout.end_gaps_m[0]:.1f} m", size=10.5)
        _text(parts, ox0 + dc_span_m * s / 2, oy0 + (depth_m + 0.22) * s,
              f"DC end gaps alternate "
              f"{layout.end_gap_m:.1f} / {layout.boundary_end_gap_m:.1f} m — "
              f"equipment ends (cooling + fan grilles) face the block boundary",
              size=9.5, weight=600, fill="#5b6367")

    parts.append("</svg>")
    return "".join(parts), layout
