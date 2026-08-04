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

"""THE Typical AC Block Arrangement — one rule, one label, one drawing.

Owner instruction 2026-08-03: "无论是导出的报告还是页面展示的 typical ac block
arrangement 都要一致的逻辑排布和绘制."

Before this module the exported report and the web page each had their OWN copy
of four decisions:

1. which engine draws this block (central-station bilateral vs linear row);
2. what the drawing is titled;
3. how the block's power and station class are resolved;
4. how the CONCEPT ONLY marking is applied.

Four duplicated rules meant four ways to drift, and that drift is exactly the
defect chain recorded in docs/LAYOUT_ARRANGEMENT_DEFECTS_2026-08-03.md — a 10 MW
product drawn with a 20 ft cabin in one place and a 40 ft station in another.

Both surfaces now call :func:`render_typical_ac_block`. If a rule has to change,
there is one place to change it, and
``tests/unit/test_typical_ac_block_arrangement.py`` proves the two surfaces emit
the same drawing byte for byte.

WHAT EACH CALLER STILL OWNS: resolving the block's shape from its own data
source. The report reads a ReportContext; the page reads an AcSnapshot for the
block the user selected. That difference is real and intended — the SHAPE is an
input, the arrangement is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from calb_diagrams.ac_block_arrangement_v2 import (
    ArrangementRuleProfile,
    US_NFPA_OIL,
    compute_layout,
    render_plan_svg,
    resolve_station_length_m,
)
from calb_diagrams.ac_block_bilateral_layout import (
    LAYOUT_VARIANT as CENTRAL_STATION_VARIANT,
    compute_bilateral_layout,
    render_bilateral_plan_svg,
)

LINEAR_VARIANT = "linear_mirrored_pairs"

# The 10 MW / 40 ft product: 8 PCS, one DC Block per PCS, central 40 ft station
# with mirrored west and east DC fields.
CENTRAL_STATION_PCS_COUNT = 8
CENTRAL_STATION_DC_COUNT = 8

# The page hands out a standalone SVG, so it stamps the SVG; the report embeds a
# raster and stamps that instead (fail-closed, see report_v2._stamp_not_for_
# construction). Same marking, different medium — this group id is what lets the
# consistency test compare the two drawings without tripping over it.
DOCUMENT_STATUS_GROUP_ID = "calb-document-status"
_CONCEPT_OVERLAY = (
    f'<g id="{DOCUMENT_STATUS_GROUP_ID}" pointer-events="none">'
    '<text x="50%" y="52%" text-anchor="middle" '
    'font-family="Arial, sans-serif" font-size="30" font-weight="700" '
    'fill="#B42318" fill-opacity="0.25">'
    'CONCEPT ONLY - NOT FOR CONSTRUCTION</text></g>'
)


@dataclass(frozen=True)
class AcBlockShape:
    """Everything the arrangement needs to know about ONE AC Block.

    ``block_index`` is the block being drawn (1-based). ``model_name`` is the
    governed configuration code or product name when the run has one; it wins
    over the generated label. ``layout_variant`` is the governed hint, used only
    to force the central-station engine for a governed run whose shape somehow
    reads otherwise.
    """

    dc_blocks: int
    pcs_count: int
    block_power_mw: float = 0.0
    block_index: int = 1
    model_name: str = ""
    layout_variant: str = ""


@dataclass(frozen=True)
class TypicalArrangement:
    """The drawing plus everything a caller might want to state about it."""

    layout_variant: str
    svg: str
    label: str
    envelope_w_m: float
    envelope_d_m: float
    envelope_area_m2: float
    station_length_m: float
    dc_blocks: int
    pcs_count: int
    block_power_mw: float
    profile_key: str
    placements: Tuple[Dict[str, Any], ...] = ()
    provisional_notes: Tuple[str, ...] = ()
    # Engine-native layout object, for callers that need more than the summary.
    layout: Any = field(default=None, repr=False)

    @property
    def uses_central_station(self) -> bool:
        return self.layout_variant == CENTRAL_STATION_VARIANT


def uses_central_station(pcs_count: int | None, dc_blocks: int | None,
                         layout_variant: str | None = None) -> bool:
    """THE engine-selection rule. Do not reimplement it anywhere else.

    An 8-PCS block with 8 DC Blocks IS the 10 MW / 40 ft product, whether or not
    the run was bound to the governed configuration — so a generic run draws
    exactly what a governed run draws. One product, one geometry.
    """
    if str(layout_variant or "").strip() == CENTRAL_STATION_VARIANT:
        return True
    try:
        pcs = int(pcs_count or 0)
        dc = int(dc_blocks or 0)
    except (TypeError, ValueError):
        return False
    return pcs == CENTRAL_STATION_PCS_COUNT and dc == CENTRAL_STATION_DC_COUNT


def block_label(shape: AcBlockShape, *, station_length_m: float) -> str:
    """THE title rule. A governed model name wins; otherwise describe the block."""
    model = str(shape.model_name or "").strip()
    if model:
        return model
    station = "40 FT CENTRAL STATION" if uses_central_station(
        shape.pcs_count, shape.dc_blocks, shape.layout_variant
    ) else f"{station_length_m:.3g} M STATION"
    return (
        f"TYPICAL AC BLOCK {max(1, int(shape.block_index or 1))} · "
        f"{int(shape.pcs_count or 0)} PCS / {int(shape.dc_blocks or 0)} DC · {station}"
    )


def apply_concept_watermark(svg: str) -> str:
    """Overlay the CONCEPT ONLY marking on a standalone SVG."""
    if "</svg>" not in svg:
        raise ValueError("Arrangement renderer returned malformed SVG without a closing tag.")
    return svg.rsplit("</svg>", 1)[0] + _CONCEPT_OVERLAY + "</svg>"


def strip_document_status(svg: str) -> str:
    """Remove the document-status overlay, so two drawings can be compared.

    The report stamps its raster and the page stamps its SVG; that difference is
    intended and is NOT a difference in the drawing.
    """
    open_tag = f'<g id="{DOCUMENT_STATUS_GROUP_ID}"'
    start = svg.find(open_tag)
    if start < 0:
        return svg
    end = svg.find("</g>", start)
    if end < 0:
        return svg
    return svg[:start] + svg[end + len("</g>"):]


def render_typical_ac_block(
    shape: AcBlockShape,
    profile: ArrangementRuleProfile = US_NFPA_OIL,
    *,
    watermark: bool = False,
) -> TypicalArrangement:
    """Draw one AC Block. The ONLY entry point for report and page alike.

    ``watermark=True`` overlays the CONCEPT ONLY marking, for a caller that hands
    the SVG out directly. A caller that rasterises and stamps the raster leaves
    it off and marks the raster instead.
    """
    dc_blocks = max(0, int(shape.dc_blocks or 0))
    if dc_blocks < 1:
        raise ValueError(
            "AC Block has no DC Blocks; run AC sizing before drawing the arrangement."
        )
    pcs_count = max(0, int(shape.pcs_count or 0))
    power_mw = float(shape.block_power_mw or 0.0)

    if uses_central_station(pcs_count, dc_blocks, shape.layout_variant):
        layout = compute_bilateral_layout(CENTRAL_STATION_DC_COUNT)
        station = layout.by_type("ac_station")[0]
        station_len = station.height_m
        label = block_label(shape, station_length_m=station_len)
        svg = render_bilateral_plan_svg(layout, block_label=label)
        placements = tuple(
            {
                "equipment_id": p.equipment_id,
                "equipment_type": p.equipment_type,
                "x_m": p.x_m, "y_m": p.y_m,
                "width_m": p.width_m, "height_m": p.height_m,
                "door_orientation": p.door_orientation,
                "equipment_end": p.equipment_end,
                "feeder_index": p.feeder_index,
                "provisional": p.provisional,
            }
            for p in layout.placements
        )
        notes = tuple(layout.provisional_notes)
        variant = layout.layout_variant
        env_w, env_d = layout.envelope_w_m, layout.envelope_d_m
    else:
        station_len = resolve_station_length_m(pcs_count, power_mw)
        label = block_label(shape, station_length_m=station_len)
        svg, layout = render_plan_svg(
            dc_blocks, profile, label,
            pcs_count=pcs_count, block_power_mw=power_mw,
        )
        placements = ()
        notes = ()
        variant = LINEAR_VARIANT
        env_w, env_d = layout.envelope_w_m, layout.envelope_d_m
        station_len = layout.station_length_m

    if watermark:
        svg = apply_concept_watermark(svg)

    return TypicalArrangement(
        layout_variant=variant,
        svg=svg,
        label=label,
        envelope_w_m=env_w,
        envelope_d_m=env_d,
        envelope_area_m2=round(env_w * env_d, 1),
        station_length_m=round(float(station_len), 3),
        dc_blocks=dc_blocks,
        pcs_count=pcs_count,
        block_power_mw=round(power_mw, 3),
        profile_key=profile.key,
        placements=placements,
        provisional_notes=notes,
        layout=layout,
    )


def arrangement_spec(arrangement: TypicalArrangement,
                     profile: ArrangementRuleProfile = US_NFPA_OIL) -> Dict[str, Any]:
    """Machine-readable description of the drawing, with its code basis.

    Shared so the page's downloadable spec and anything the report states about
    the arrangement are generated from the same values as the drawing itself.
    """
    return {
        "engine": "typical_ac_block_arrangement",
        "layout_variant": arrangement.layout_variant,
        "label": arrangement.label,
        "rule_profile_key": profile.key,
        "rule_profile_market": profile.market_label,
        "pcs_count": arrangement.pcs_count,
        "block_power_mw": arrangement.block_power_mw,
        "dc_blocks_total": arrangement.dc_blocks,
        "station_length_m": arrangement.station_length_m,
        "envelope_w_m": arrangement.envelope_w_m,
        "envelope_d_m": arrangement.envelope_d_m,
        "envelope_area_m2": arrangement.envelope_area_m2,
        "clearances_m": {
            "dc_pair_gap": profile.dc_pair_gap_m,
            "dc_to_mv_aisle": profile.dc_to_mv_aisle_m,
            "pair_to_pair_plain_end": profile.pair_to_pair_gap_m,
            "dc_equipment_end": profile.dc_equipment_end_gap_m,
        },
        "code_basis": [
            {"parameter": item, "value": value, "basis": basis}
            for item, value, basis in profile.basis
        ],
        "placements": list(arrangement.placements),
        "provisional_notes": list(arrangement.provisional_notes),
    }


def resolve_dc_blocks_for_block(ac_output: Dict[str, Any], block_index: int) -> int:
    """DC Blocks on ONE AC Block, from the run's allocation plan.

    Shared so the page and the report count the same way. The plan is per-block
    truth; ``dc_blocks_total / num_blocks`` is an average that matches no real
    block on a mixed station.
    """
    plan = ac_output.get("dc_allocation_plan")
    if isinstance(plan, list):
        by_index = {}
        for entry in plan:
            if not isinstance(entry, dict):
                continue
            idx, total = entry.get("ac_block_index"), entry.get("dc_blocks_total")
            if isinstance(idx, int) and isinstance(total, int):
                by_index[idx] = total
        if by_index:
            return int(by_index.get(block_index) or next(iter(by_index.values())))
    return 0


def resolve_pcs_for_block(ac_output: Dict[str, Any], block_index: int) -> int:
    """PCS on ONE AC Block: the per-block list wins over the fleet nominal."""
    per_block = ac_output.get("pcs_count_by_block")
    if isinstance(per_block, list) and 1 <= block_index <= len(per_block):
        try:
            resolved = int(per_block[block_index - 1])
        except (TypeError, ValueError):
            resolved = 0
        if resolved > 0:
            return resolved
    try:
        return int(ac_output.get("pcs_per_block") or 0)
    except (TypeError, ValueError):
        return 0


def resolve_block_power_mw(ac_output: Dict[str, Any], pcs_count: int) -> float:
    """THIS block's power — never the fleet nominal when the PCS count is known.

    A tail AC Block with fewer PCS is a smaller block and, past the 8-PCS / 10 MW
    threshold, a smaller station.
    """
    def _f(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    pcs_kw = _f(ac_output.get("pcs_kw"))
    if pcs_count > 0 and pcs_kw > 0:
        return pcs_count * pcs_kw / 1000.0
    return _f(ac_output.get("block_size_mw"))


__all__ = [
    "AcBlockShape",
    "TypicalArrangement",
    "CENTRAL_STATION_VARIANT",
    "LINEAR_VARIANT",
    "DOCUMENT_STATUS_GROUP_ID",
    "apply_concept_watermark",
    "arrangement_spec",
    "block_label",
    "render_typical_ac_block",
    "resolve_block_power_mw",
    "resolve_dc_blocks_for_block",
    "resolve_pcs_for_block",
    "strip_document_status",
    "uses_central_station",
]
