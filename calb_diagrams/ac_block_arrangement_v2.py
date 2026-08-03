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
- The PCS & MV station is a 20 ft containerized turnkey unit drawn
  brand-neutral.
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


@dataclass(frozen=True)
class ArrangementLayout:
    dc_count: int
    pair_count: int
    has_single_tail: bool
    envelope_w_m: float
    envelope_d_m: float
    profile_key: str
    station_length_m: float = MV_LENGTH_M   # 20 ft cabin or 40 ft flagship
    end_gap_m: float = 0.9                  # governing DC END-face clearance


def compute_layout(dc_count: int, profile: ArrangementRuleProfile,
                   *, pcs_count: int | None = None,
                   block_power_mw: float | None = None,
                   station_length_m: float | None = None) -> ArrangementLayout:
    """Envelope of one AC block: mirrored DC pairs + aisle + PCS & MV station.

    ``station_length_m`` overrides the station size; otherwise it is resolved from
    the AC Block class (``pcs_count`` / ``block_power_mw``) — a 10 MW / 8-PCS block
    is a 40 ft station, never the 20 ft cabin.

    The gap between adjacent mirrored pairs is the DC Block's END-face clearance.
    With a uniform container orientation one of the two facing ends is always the
    EQUIPMENT END (liquid-cooling unit + fan grilles), so that larger clearance
    governs (owner ruling, 2026-08-03).
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
    end_gap = max(profile.pair_to_pair_gap_m, profile.dc_equipment_end_gap_m)
    dc_span = units * DC_LENGTH_M + (units - 1) * end_gap
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
        end_gap_m=round(end_gap, 3),
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


def _dc_pair_at(parts: List[str], s: float, ox: float, oy: float,
                pair_gap_m: float) -> None:
    """One mirrored pair; roof vents on the NO-DOOR edges facing the pair gap."""
    for row_m, vents_south in ((0.0, True), (DC_WIDTH_M + pair_gap_m, False)):
        x = ox
        y = oy + row_m * s
        _rect(parts, x + 3, y + 3, DC_LENGTH_M * s, DC_WIDTH_M * s, _SHADOW, opacity=0.15)
        _rect(parts, x, y, DC_LENGTH_M * s, DC_WIDTH_M * s, _BOX, _BOX_EDGE, 1.0)
        vent = 0.88
        vy_m = (DC_WIDTH_M - vent - 0.20) if vents_south else 0.20
        for i in range(4):
            vx = 0.62 + i * 1.32
            _rect(parts, x + vx * s, y + vy_m * s, vent * s, vent * s,
                  _VENT, _VENT_EDGE, 0.8, rx=1.5)


def _single_dc(parts: List[str], s: float, ox: float, oy: float) -> None:
    """Unpaired tail container: doors outward (south), vents on the north edge."""
    _rect(parts, ox + 3, oy + 3, DC_LENGTH_M * s, DC_WIDTH_M * s, _SHADOW, opacity=0.15)
    _rect(parts, ox, oy, DC_LENGTH_M * s, DC_WIDTH_M * s, _BOX, _BOX_EDGE, 1.0)
    vent = 0.88
    for i in range(4):
        vx = 0.62 + i * 1.32
        _rect(parts, ox + vx * s, oy + 0.20 * s, vent * s, vent * s,
              _VENT, _VENT_EDGE, 0.8, rx=1.5)


def _mv_station(parts: List[str], s: float, ox: float, oy: float,
                station_len_m: float = MV_LENGTH_M) -> None:
    """PCS & MV Station — 20 ft cabin or 40 ft flagship, per station_len_m."""
    _rect(parts, ox + 3, oy + 3, station_len_m * s, MV_WIDTH_M * s, _SHADOW, opacity=0.15)
    _rect(parts, ox, oy, station_len_m * s, MV_WIDTH_M * s, "#f0f2f1", _BOX_EDGE, 1.0)
    # Louvred PCS door bays scale with the cabin length (a 40 ft station carries
    # roughly twice the string-PCS bays of a 20 ft one).
    bays = max(2, int(round(station_len_m / 3.0)))
    for i in range(bays):
        _rect(parts, ox + (1.05 + i * 1.8) * s, oy + 0.55 * s, 0.85 * s, 0.55 * s,
              _VENT, _VENT_EDGE, 0.8)
    for i in range(6):
        _rect(parts, ox + (station_len_m - 1.05 + i * 0.13) * s, oy + 0.55 * s,
              0.05 * s, 1.35 * s, _LOUVER, rx=0)


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

    # DC units west, MV station east
    units = layout.pair_count + (1 if layout.has_single_tail else 0)
    for u in range(layout.pair_count):
        ux = ox0 + u * (DC_LENGTH_M + layout.end_gap_m) * s
        _dc_pair_at(parts, s, ux, oy0, profile.dc_pair_gap_m)
    if layout.has_single_tail:
        ux = ox0 + layout.pair_count * (DC_LENGTH_M + layout.end_gap_m) * s
        _single_dc(parts, s, ux, oy0)

    dc_span_m = units * DC_LENGTH_M + (units - 1) * layout.end_gap_m
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
    _text(parts, ox0 + dc_span_m * s / 2, oy0 - 0.52 * s - 6,
          f"{dc_count} × DC BLOCK (5.015 MWh, mirrored pairs)", size=12)
    _text(parts, mv_x + MV_LENGTH_M * s / 2, mv_y - 10, "PCS & MV STATION", size=12)
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
        _dim(parts, px0, oy0 - 0.30 * s, px0 + layout.end_gap_m * s,
             oy0 - 0.30 * s, f"{layout.end_gap_m:.1f} m", size=10.5)

    parts.append("</svg>")
    return "".join(parts), layout
