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

"""Bilateral 4+4 AC Block arrangement engine (layout variant
``central_40ft_bilateral_4plus4``).

Confirmed physical concept (docs/CLAUDE_HANDOFF_10MW_8PCS_8DC_2026-07-24.md
§1-§2 and §6):

- one central, vertically placed 40 ft AC Block / PCS-MV station;
- four DC Blocks on the WEST, four on the EAST, left/right mirror images;
- each side is a 2x2 ``田`` field of two mirrored back-to-back DC pairs, the two
  pairs shoulder-to-shoulder;
- the removed single-row eight-DC draft must NOT be reintroduced.

Unlike the linear L1 engine, this variant returns a PER-EQUIPMENT placement list
(id, x/y, size, rotation, side, pair, door/service orientation, provenance) plus
the equipment-only envelope — so Report / Site Array consume real geometry rather
than reconstructing the unit from an average DC-per-AC ratio.

Every spacing value comes from an :class:`ArrangementRuleProfile`. The 0.90 m
pair-to-pair gap, 3.00 m aisle and nominal 40 ft station dimensions remain
rule-profile / provisional assumptions until the owner confirms them for this
exact product; each placement records that provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from xml.sax.saxutils import escape as _xml_escape

from calb_diagrams.ac_block_arrangement_v2 import (
    ArrangementRuleProfile,
    AC_STATION_40FT_LENGTH_M,
    AC_STATION_WIDTH_M,
    DC_LENGTH_M,
    DC_WIDTH_M,
    US_NFPA_OIL,
)

LAYOUT_VARIANT = "central_40ft_bilateral_4plus4"

# Nominal ISO 40 ft station (vertical). PROVISIONAL — owner confirmation of the
# actual 40 ft product dimensions is pending (handoff §10.5).
# Shared with the linear engine so the two can never drift apart.
AC40_STATION_LENGTH_M = AC_STATION_40FT_LENGTH_M
AC40_STATION_WIDTH_M = AC_STATION_WIDTH_M


@dataclass(frozen=True)
class EquipmentPlacement:
    """One placed piece of equipment in the equipment-only coordinate frame.

    Origin (0, 0) is the north-west corner of the equipment envelope; ``x`` grows
    east, ``y`` grows south. Sizes are the equipment footprint BEFORE rotation;
    ``rotation_deg`` is applied about the placement's own centre.
    """

    equipment_id: str
    equipment_type: str          # "dc_block" | "ac_station"
    x_m: float
    y_m: float
    width_m: float               # east-west footprint (pre-rotation)
    height_m: float              # north-south footprint (pre-rotation)
    rotation_deg: float
    side: str                    # "west" | "center" | "east"
    pair_id: Optional[str]       # mirrored-pair id, e.g. "W1"; None for station
    door_orientation: str        # "west" | "east" | "north" | "south"
    service_orientation: str     # aisle the maintenance doors open onto
    feeder_index: Optional[int]  # DC-to-PCS dedicated feeder (1..8); None station
    provenance: str              # rule-profile / concept-status provenance
    provisional: bool            # True while any driving dimension is unconfirmed

    @property
    def center_x_m(self) -> float:
        return self.x_m + self.width_m / 2.0

    @property
    def center_y_m(self) -> float:
        return self.y_m + self.height_m / 2.0


@dataclass(frozen=True)
class AislePolygon:
    aisle_id: str
    x_m: float
    y_m: float
    width_m: float
    height_m: float
    role: str


@dataclass(frozen=True)
class BilateralLayout:
    layout_variant: str
    dc_count: int
    dc_field_split: Tuple[int, int]
    placements: Tuple[EquipmentPlacement, ...]
    aisles: Tuple[AislePolygon, ...]
    cable_trenches: Tuple[dict, ...]
    envelope_w_m: float
    envelope_d_m: float
    profile_key: str
    provisional_notes: Tuple[str, ...] = field(default_factory=tuple)

    def by_type(self, equipment_type: str) -> List[EquipmentPlacement]:
        return [p for p in self.placements if p.equipment_type == equipment_type]


def _dc_field_placements(
    *,
    field_origin_x: float,
    field_origin_y: float,
    side: str,
    dc_ids: List[int],
    pair_labels: Tuple[str, str],
    profile: ArrangementRuleProfile,
    aisle_side: str,
    provenance: str,
    provisional: bool,
) -> List[EquipmentPlacement]:
    """Place one 2x2 ``田`` field of four DC Blocks.

    Containers are oriented length north-south. Two containers side-by-side
    east-west form a mirrored back-to-back pair (backs face the ``dc_pair_gap_m``
    slot between them, doors face outward). Two such pairs stack north-south,
    separated by ``pair_to_pair_gap_m``.

    ``dc_ids`` is ordered [top-left, top-right, bottom-left, bottom-right] to
    match the handoff numbering (DC-1..DC-4 west, DC-5..DC-8 east).
    """
    col_w = DC_WIDTH_M                     # east-west footprint of one container
    row_h = DC_LENGTH_M                    # north-south footprint of one container
    col_x = (0.0, col_w + profile.dc_pair_gap_m)
    # Two pairs stack north-south, so the touching faces are the DC Block END
    # faces; one of them is always the EQUIPMENT END (liquid-cooling + fan
    # grilles), which takes the AC-Block-aisle clearance (owner, 2026-08-03).
    _end_gap = max(profile.pair_to_pair_gap_m, profile.dc_equipment_end_gap_m)
    row_y = (0.0, row_h + _end_gap)

    # (col, row, pair_label, feeder-order-within-field)
    slots = [
        (0, 0, pair_labels[0]),   # top-left
        (1, 0, pair_labels[0]),   # top-right
        (0, 1, pair_labels[1]),   # bottom-left
        (1, 1, pair_labels[1]),   # bottom-right
    ]
    placements: List[EquipmentPlacement] = []
    for dc_id, (col, row, pair_label) in zip(dc_ids, slots):
        # Within a back-to-back pair the two backs face the pair gap; doors face
        # outward. Left column doors face west, right column doors face east.
        door = "west" if col == 0 else "east"
        # The aisle-facing container's doors serve the central AC-station aisle;
        # the outer container serves the perimeter maintenance aisle.
        inner_col = 1 if side == "west" else 0
        service = aisle_side if col == inner_col else "perimeter"
        placements.append(
            EquipmentPlacement(
                equipment_id=f"DC-{dc_id}",
                equipment_type="dc_block",
                x_m=round(field_origin_x + col_x[col], 3),
                y_m=round(field_origin_y + row_y[row], 3),
                width_m=col_w,
                height_m=row_h,
                rotation_deg=0.0,
                side=side,
                pair_id=pair_label,
                door_orientation=door,
                service_orientation=service,
                feeder_index=dc_id,
                provenance=provenance,
                provisional=provisional,
            )
        )
    return placements


def compute_bilateral_layout(
    dc_count: int = 8,
    profile: ArrangementRuleProfile = US_NFPA_OIL,
    *,
    dc_field_to_station_aisle_m: Optional[float] = None,
    station_length_m: Optional[float] = None,
    station_width_m: Optional[float] = None,
) -> BilateralLayout:
    """Compute the bilateral 4+4 arrangement with per-equipment placements.

    Phase A supports exactly eight DC Blocks split 4+4 around one central
    vertical 40 ft station. ``dc_field_to_station_aisle_m`` and the station
    dimensions default to the rule-profile / nominal ISO values and are flagged
    provisional; a caller may override them from owner-confirmed Engineering
    Settings.
    """
    if dc_count != 8:
        raise ValueError(
            f"central_40ft_bilateral_4plus4 is a fixed 4+4 field; dc_count must be 8, got {dc_count}"
        )

    aisle_m = profile.dc_to_mv_aisle_m if dc_field_to_station_aisle_m is None else float(dc_field_to_station_aisle_m)
    station_len = AC40_STATION_LENGTH_M if station_length_m is None else float(station_length_m)
    station_wid = AC40_STATION_WIDTH_M if station_width_m is None else float(station_width_m)
    aisle_is_provisional = dc_field_to_station_aisle_m is None
    station_is_provisional = station_length_m is None or station_width_m is None

    # One 4-DC field footprint.
    field_w = 2 * DC_WIDTH_M + profile.dc_pair_gap_m          # east-west
    field_d = 2 * DC_LENGTH_M + max(profile.pair_to_pair_gap_m, profile.dc_equipment_end_gap_m)  # north-south

    envelope_w = field_w + aisle_m + station_wid + aisle_m + field_w
    envelope_d = max(field_d, station_len)

    # Vertically centre the shorter of field/station within the envelope depth.
    field_origin_y = round((envelope_d - field_d) / 2.0, 3)
    station_origin_y = round((envelope_d - station_len) / 2.0, 3)

    west_field_x = 0.0
    aisle_west_x = field_w
    station_x = field_w + aisle_m
    aisle_east_x = station_x + station_wid
    east_field_x = aisle_east_x + aisle_m

    field_provenance = (
        f"rule_profile={profile.key}; concept_confirmed_partial; "
        f"pair_gap={profile.dc_pair_gap_m} m, pair_to_pair={profile.pair_to_pair_gap_m} m"
    )
    field_provisional = True  # pair-to-pair gap is a rule-profile assumption

    placements: List[EquipmentPlacement] = []
    placements += _dc_field_placements(
        field_origin_x=west_field_x,
        field_origin_y=field_origin_y,
        side="west",
        dc_ids=[1, 2, 3, 4],
        pair_labels=("W1", "W2"),
        profile=profile,
        aisle_side="central",
        provenance=field_provenance,
        provisional=field_provisional,
    )
    placements += _dc_field_placements(
        field_origin_x=east_field_x,
        field_origin_y=field_origin_y,
        side="east",
        dc_ids=[5, 6, 7, 8],
        pair_labels=("E1", "E2"),
        profile=profile,
        aisle_side="central",
        provenance=field_provenance,
        provisional=field_provisional,
    )

    station_provenance = (
        f"nominal ISO 40ft {station_len:g}x{station_wid:g} m (vertical); "
        f"aisle={aisle_m:g} m"
        + ("; PROVISIONAL station dims" if station_is_provisional else "")
        + ("; PROVISIONAL aisle" if aisle_is_provisional else "")
    )
    placements.append(
        EquipmentPlacement(
            equipment_id="AC-STATION-40FT",
            equipment_type="ac_station",
            x_m=round(station_x, 3),
            y_m=station_origin_y,
            width_m=round(station_wid, 3),
            height_m=round(station_len, 3),
            rotation_deg=90.0,   # 40 ft placed vertically at the centre
            side="center",
            pair_id=None,
            door_orientation="east",
            service_orientation="central",
            feeder_index=None,
            provenance=station_provenance,
            provisional=station_is_provisional or aisle_is_provisional,
        )
    )

    aisles = (
        AislePolygon("AISLE-WEST", round(aisle_west_x, 3), 0.0, round(aisle_m, 3),
                     round(envelope_d, 3), "dc_field_to_station"),
        AislePolygon("AISLE-EAST", round(aisle_east_x, 3), 0.0, round(aisle_m, 3),
                     round(envelope_d, 3), "dc_field_to_station"),
    )

    # Cable trenches run from each DC field across the aisle into the station.
    cable_trenches = (
        {"trench_id": "TRENCH-WEST", "from_side": "west", "to": "AC-STATION-40FT",
         "x_m": round(aisle_west_x, 3), "width_m": round(aisle_m, 3),
         "y_center_m": round(envelope_d / 2.0, 3)},
        {"trench_id": "TRENCH-EAST", "from_side": "east", "to": "AC-STATION-40FT",
         "x_m": round(aisle_east_x, 3), "width_m": round(aisle_m, 3),
         "y_center_m": round(envelope_d / 2.0, 3)},
    )

    provisional_notes: List[str] = []
    if field_provisional:
        provisional_notes.append(
            f"pair-to-pair gap {profile.pair_to_pair_gap_m:g} m is a rule-profile assumption"
        )
    if aisle_is_provisional:
        provisional_notes.append(f"DC-field-to-station aisle {aisle_m:g} m is a rule-profile assumption")
    if station_is_provisional:
        provisional_notes.append(
            f"40 ft station {station_len:g}x{station_wid:g} m uses nominal ISO dimensions"
        )

    return BilateralLayout(
        layout_variant=LAYOUT_VARIANT,
        dc_count=dc_count,
        dc_field_split=(4, 4),
        placements=tuple(placements),
        aisles=aisles,
        cable_trenches=cable_trenches,
        envelope_w_m=round(envelope_w, 3),
        envelope_d_m=round(envelope_d, 3),
        profile_key=profile.key,
        provisional_notes=tuple(provisional_notes),
    )


# ---------------------------------------------------------------------------
# Plan-view SVG rendering (concept only)
# ---------------------------------------------------------------------------

_INK = "#1f4e79"
_GROUND = "#c6cac5"
_PAD = "#d3d5d1"
_PAD_EDGE = "#b3b6b2"
_BOX = "#eef0ef"
_BOX_EDGE = "#aeb5b4"
_MV = "#f0f2f1"
_SHADOW = "#3a3f42"
_DOOR = "#1f4e79"
_TRENCH = "#9fa5a3"
_TRENCH_EDGE = "#868c8a"
_AISLE = "#dfe1dd"


def _rect(parts, x, y, w, h, fill, stroke=None, sw=1.0, rx=2.0, opacity=None):
    extra = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    if opacity is not None:
        extra += f' opacity="{opacity}"'
    parts.append(
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
        f'fill="{fill}" rx="{rx}"{extra}/>'
    )


def _text(parts, x, y, s, size=12, anchor="middle", weight=700, fill=_INK):
    parts.append(
        f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-size="{size}" '
        f'font-family="Consolas, monospace" font-weight="{weight}" '
        f'text-anchor="{anchor}">{_xml_escape(s)}</text>'
    )


def render_bilateral_plan_svg(
    layout: BilateralLayout,
    block_label: str = "ACBLK-10MW-8PCS-8DC-40FT-BILATERAL",
) -> str:
    """Top-down concept drawing of the bilateral 4+4 AC Block."""
    s = 26.0  # px per metre
    margin_l, margin_r, margin_t, margin_b = 60.0, 60.0, 64.0, 96.0

    # Header / footer strings, sized so the SVG is wide enough for the longest
    # line of text as well as the equipment envelope (the title never clips).
    title = str(block_label)
    subtitle = (
        f"{layout.envelope_w_m:.2f} m x {layout.envelope_d_m:.2f} m equipment envelope"
        + ("  ·  N/W/E/S 2-DC each | center 40 ft"
           if layout.layout_variant == QUAD_LAYOUT_VARIANT
           else "  ·  west 4-DC | center 40 ft | east 4-DC")
    )
    footer = "CONCEPT ONLY — NOT FOR CONSTRUCTION · provisional spacing, not a site layout"

    def _mono_w(text: str, font_px: float) -> float:
        return len(text) * font_px * 0.62  # Consolas advance width estimate

    content_w = layout.envelope_w_m * s
    text_w = max(_mono_w(title, 13.0), _mono_w(subtitle, 10.5), _mono_w(footer, 10.5))
    width = margin_l + max(content_w, text_w) + margin_r
    height = margin_t + layout.envelope_d_m * s + margin_b

    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'font-family="Consolas, monospace">'
    )
    _rect(parts, 0, 0, width, height, _GROUND, rx=0)
    ox, oy = margin_l, margin_t

    # equipment pad
    _rect(parts, ox - 0.25 * s, oy - 0.25 * s,
          (layout.envelope_w_m + 0.5) * s, (layout.envelope_d_m + 0.5) * s,
          _PAD, _PAD_EDGE, 1.0)

    # aisles
    for aisle in layout.aisles:
        _rect(parts, ox + aisle.x_m * s, oy + aisle.y_m * s,
              aisle.width_m * s, aisle.height_m * s, _AISLE, rx=0)

    # cable trenches across the aisles
    for trench in layout.cable_trenches:
        ty = oy + (trench["y_center_m"] - 0.15) * s
        _rect(parts, ox + trench["x_m"] * s, ty, trench["width_m"] * s, 0.30 * s,
              _TRENCH, _TRENCH_EDGE, 0.8, rx=1)

    # equipment
    for p in layout.placements:
        px = ox + p.x_m * s
        py = oy + p.y_m * s
        pw = p.width_m * s
        ph = p.height_m * s
        _rect(parts, px + 3, py + 3, pw, ph, _SHADOW, opacity=0.15)
        if p.equipment_type == "ac_station":
            _rect(parts, px, py, pw, ph, _MV, _BOX_EDGE, 1.2)
            _text(parts, px + pw / 2, py - 8, "40FT AC BLOCK", size=10.5)
            _text(parts, px + pw / 2, py + ph / 2, "PCS & MV", size=9,
                  fill="#5b6367")
        else:
            _rect(parts, px, py, pw, ph, _BOX, _BOX_EDGE, 1.0)
            _text(parts, px + pw / 2, py + ph / 2 + 4, p.equipment_id, size=10)
            # door marker on the door edge
            if p.door_orientation == "west":
                _rect(parts, px, py + ph * 0.3, 2.5, ph * 0.4, _DOOR, rx=0)
            elif p.door_orientation == "east":
                _rect(parts, px + pw - 2.5, py + ph * 0.3, 2.5, ph * 0.4, _DOOR, rx=0)
            elif p.door_orientation == "north":
                _rect(parts, px + pw * 0.3, py, pw * 0.4, 2.5, _DOOR, rx=0)
            elif p.door_orientation == "south":
                _rect(parts, px + pw * 0.3, py + ph - 2.5, pw * 0.4, 2.5, _DOOR, rx=0)

    # labels
    _text(parts, margin_l + 4, 30, title, size=13, anchor="start")
    _text(parts, margin_l + 4, 48, subtitle, size=10.5, anchor="start",
          weight=600, fill="#5b6367")
    _text(parts, margin_l + 4, height - 16, footer, size=10.5, anchor="start",
          weight=600, fill="#5b6367")

    parts.append("</svg>")
    return "".join(parts)


QUAD_LAYOUT_VARIANT = "central_40ft_quad_2plus2plus2plus2"


def compute_quad_layout(
    dc_count: int = 8,
    profile: ArrangementRuleProfile = US_NFPA_OIL,
    *,
    dc_field_to_station_aisle_m: Optional[float] = None,
    station_length_m: Optional[float] = None,
    station_width_m: Optional[float] = None,
) -> BilateralLayout:
    """8 DC Blocks placed on ALL FOUR sides of the central 40 ft AC Block.

    Owner instruction (2026-08-03): with eight DC Blocks the field need not be
    restricted to the two lateral sides. Each side carries ONE mirrored pair, so
    every DC Block still presents its door face to a 3.0 m aisle and shares only
    its door-free wide face (0.30 m) with its partner.

    Trade-off, stated plainly: this costs a third and fourth 3.0 m aisle, so the
    footprint grows from ~284 m2 (bilateral 4+4) to ~536 m2. Cable runs to the
    north/south pairs also route around the station.
    """
    if dc_count != 8:
        raise ValueError(
            f"{QUAD_LAYOUT_VARIANT} is a fixed 2+2+2+2 field; dc_count must be 8, got {dc_count}"
        )
    aisle = profile.dc_to_mv_aisle_m if dc_field_to_station_aisle_m is None else float(dc_field_to_station_aisle_m)
    st_len = AC40_STATION_LENGTH_M if station_length_m is None else float(station_length_m)
    st_wid = AC40_STATION_WIDTH_M if station_width_m is None else float(station_width_m)

    pair_long = 2 * DC_WIDTH_M + profile.dc_pair_gap_m   # across the pair (5.176)
    prov = (f"rule_profile={profile.key}; owner 2026-08-03 four-side field; "
            f"pair_gap={profile.dc_pair_gap_m} m, aisle={aisle} m")

    envelope_w = pair_long + aisle + st_wid + aisle + pair_long
    envelope_d = pair_long + aisle + st_len + aisle + pair_long

    station_x = pair_long + aisle
    station_y = pair_long + aisle
    lateral_y = station_y + (st_len - DC_LENGTH_M) / 2.0     # centre on the station
    vertical_x = (envelope_w - DC_LENGTH_M) / 2.0            # centre horizontally

    placements: List[EquipmentPlacement] = []

    def _add(dc_id, x, y, w, h, side, door, rot):
        placements.append(EquipmentPlacement(
            equipment_id=f"DC-{dc_id}", equipment_type="dc_block",
            x_m=round(x, 3), y_m=round(y, 3), width_m=round(w, 3), height_m=round(h, 3),
            rotation_deg=rot, side=side, pair_id=f"{side}-pair",
            door_orientation=door,
            service_orientation="station_aisle" if door in ("east", "west", "north", "south") else "perimeter",
            feeder_index=dc_id, provenance=prov, provisional=True,
        ))

    # West pair: containers upright, side by side, backs facing each other.
    _add(1, 0.0, lateral_y, DC_WIDTH_M, DC_LENGTH_M, "west", "west", 0.0)
    _add(2, DC_WIDTH_M + profile.dc_pair_gap_m, lateral_y, DC_WIDTH_M, DC_LENGTH_M, "west", "east", 0.0)
    # East pair.
    east_x = station_x + st_wid + aisle
    _add(3, east_x, lateral_y, DC_WIDTH_M, DC_LENGTH_M, "east", "west", 0.0)
    _add(4, east_x + DC_WIDTH_M + profile.dc_pair_gap_m, lateral_y, DC_WIDTH_M, DC_LENGTH_M, "east", "east", 0.0)
    # North pair: containers laid on their side, stacked, backs facing each other.
    _add(5, vertical_x, 0.0, DC_LENGTH_M, DC_WIDTH_M, "north", "north", 90.0)
    _add(6, vertical_x, DC_WIDTH_M + profile.dc_pair_gap_m, DC_LENGTH_M, DC_WIDTH_M, "north", "south", 90.0)
    # South pair.
    south_y = station_y + st_len + aisle
    _add(7, vertical_x, south_y, DC_LENGTH_M, DC_WIDTH_M, "south", "north", 90.0)
    _add(8, vertical_x, south_y + DC_WIDTH_M + profile.dc_pair_gap_m, DC_LENGTH_M, DC_WIDTH_M, "south", "south", 90.0)

    placements.append(EquipmentPlacement(
        equipment_id="AC-STATION-40FT", equipment_type="ac_station",
        x_m=round(station_x, 3), y_m=round(station_y, 3),
        width_m=round(st_wid, 3), height_m=round(st_len, 3),
        rotation_deg=90.0, side="center", pair_id=None,
        door_orientation="east", service_orientation="station_aisle",
        feeder_index=None,
        provenance="nominal ISO 40 ft station",
        provisional=station_length_m is None or station_width_m is None,
    ))

    aisles = (
        AislePolygon(aisle_id="AISLE-WEST", x_m=round(pair_long, 3), y_m=0.0,
                     width_m=round(aisle, 3), height_m=round(envelope_d, 3),
                     role="dc_field_to_station"),
        AislePolygon(aisle_id="AISLE-EAST", x_m=round(station_x + st_wid, 3), y_m=0.0,
                     width_m=round(aisle, 3), height_m=round(envelope_d, 3),
                     role="dc_field_to_station"),
        AislePolygon(aisle_id="AISLE-NORTH", x_m=0.0, y_m=round(pair_long, 3),
                     width_m=round(envelope_w, 3), height_m=round(aisle, 3),
                     role="dc_field_to_station"),
        AislePolygon(aisle_id="AISLE-SOUTH", x_m=0.0, y_m=round(station_y + st_len, 3),
                     width_m=round(envelope_w, 3), height_m=round(aisle, 3),
                     role="dc_field_to_station"),
    )

    return BilateralLayout(
        dc_count=8,
        dc_field_split=(4, 4),   # 2 per side x 4 sides
        layout_variant=QUAD_LAYOUT_VARIANT,
        envelope_w_m=round(envelope_w, 3),
        envelope_d_m=round(envelope_d, 3),
        placements=tuple(placements),
        aisles=aisles,
        cable_trenches=(),
        profile_key=profile.key,
        provisional_notes=(
            "four-side DC field is an owner concept variant (2026-08-03)",
            f"DC-field-to-station aisle {aisle} m is a rule-profile assumption",
            "40 ft station 12.192x2.438 m uses nominal ISO dimensions",
        ),
    )
