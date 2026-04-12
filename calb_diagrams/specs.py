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

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from calb_sizing_tool.schemas.sld_topology import SldTopology

SLD_FONT_FAMILY = "Arial, 'DejaVu Sans', sans-serif"
SLD_FONT_SIZE = 11
SLD_FONT_SIZE_SMALL = 10
SLD_FONT_SIZE_TITLE = 12
SLD_STROKE_THIN = 1.0
SLD_STROKE_THICK = 2.0
SLD_STROKE_OUTLINE = 1.4
SLD_DASH_ARRAY = "6,4"

LAYOUT_FONT_FAMILY = "Arial, 'DejaVu Sans', sans-serif"
LAYOUT_FONT_SIZE = 11
LAYOUT_FONT_SIZE_SMALL = 10
LAYOUT_FONT_SIZE_TITLE = 12
LAYOUT_STROKE_THIN = 1.0
LAYOUT_STROKE_OUTLINE = 1.2
LAYOUT_DASH_ARRAY = "6,4"


def _safe_int(value, default=0) -> int:
    try:
        return int(value)
    except Exception:
        return default


@dataclass
class SldGroupSpec:
    group_index: int
    mv_voltage_kv: float
    lv_voltage_v_ll: float
    transformer_mva: float
    transformer_vector_group: Optional[str]
    transformer_uk_percent: Optional[float]
    pcs_count: int
    pcs_rating_kw_list: List[float]
    dc_block_energy_mwh: float
    dc_blocks_total_in_group: int
    dc_blocks_per_feeder: List[int]
    equipment_list: Dict[str, Dict] = field(default_factory=dict)
    layout_params: Dict[str, float] = field(default_factory=dict)


@dataclass
class LayoutBlockSpec:
    block_indices_to_render: List[int]
    pcs_count: int = 4
    dc_blocks_per_block: int = 4
    dc_block_counts_by_block: Dict[int, int] = field(default_factory=dict)
    arrangement: str = "2x2"
    show_skid: bool = True
    labels: Dict[str, str] = field(default_factory=dict)
    container_length_mm: int = 6058
    container_width_mm: int = 2438
    dc_to_dc_clearance_m: Optional[float] = None
    dc_to_ac_clearance_m: Optional[float] = None
    perimeter_clearance_m: Optional[float] = None
    dc_block_mirrored: bool = False
    use_template: bool = False
    dc_block_svg_path: Optional[str] = None
    ac_block_svg_path: Optional[str] = None
    scale: float = 0.04
    left_margin: int = 40
    top_margin: int = 40
    theme: str = "light"


def build_sld_group_spec(
    stage13_output: dict,
    ac_output: dict,
    dc_summary: dict,
    sld_inputs: dict,
    group_index: int,
) -> SldGroupSpec:
    """LEGACY compatibility wrapper.

    Authoritative builder chain is:
    canonical input -> SldTopology -> SldGroupSpec adapter -> renderer.
    Old dict-based callers must route through this wrapper only for backward compatibility.
    """
    from calb_sizing_tool.services.sld_topology_builder import build_legacy_sld_topology

    topology = build_legacy_sld_topology(
        stage13_output=stage13_output,
        ac_output=ac_output,
        dc_summary=dc_summary,
        sld_inputs=sld_inputs,
        group_index=group_index,
    )
    return build_sld_group_spec_from_topology(topology)


def build_sld_group_spec_from_topology(topology: SldTopology) -> SldGroupSpec:
    """Compatibility adapter only.

    Renderer-facing SldGroupSpec is now derived strictly from authoritative
    topology. No engineering allocation logic is allowed here.
    """
    summary = topology.summary
    equipment_ratings = topology.equipment_ratings
    equipment_list = {
        "mv_labels": topology.labels.model_dump(mode="python"),
        "rmu": equipment_ratings.rmu.model_dump(mode="python"),
        "transformer": {
            "vector_group": summary.transformer_vector_group,
            "uk_percent": summary.transformer_uk_percent,
            "tap_range": equipment_ratings.transformer_tap_range,
            "cooling": equipment_ratings.transformer_cooling,
        },
        "lv_busbar": equipment_ratings.lv_busbar.model_dump(mode="python"),
        "cables": equipment_ratings.cables.model_dump(mode="python"),
        "dc_fuse": equipment_ratings.dc_fuse.model_dump(mode="python"),
        "dc_block_voltage_v": summary.dc_block_voltage_v,
    }
    if summary.project_frequency_hz is not None and summary.project_frequency_hz > 0:
        equipment_list["project_hz"] = summary.project_frequency_hz

    layout_params = {
        "svg_width": 1750.0,
        "svg_height": 900.0,
        "left_margin": 40.0,
        "top_margin": 40.0,
        "column_width": 420.0,
        "row_height": 16.0,
        "pcs_gap": 60.0,
        "busbar_gap": 22.0,
        "font_scale": 1.0,
        "compact_mode": summary.compact_mode,
        "theme": summary.theme,
        "draw_summary": summary.draw_summary,
    }

    return SldGroupSpec(
        group_index=summary.group_index,
        mv_voltage_kv=summary.mv_voltage_kv,
        lv_voltage_v_ll=summary.lv_voltage_v_ll,
        transformer_mva=summary.transformer_rating_mva,
        transformer_vector_group=summary.transformer_vector_group,
        transformer_uk_percent=summary.transformer_uk_percent,
        pcs_count=summary.pcs_count,
        pcs_rating_kw_list=list(summary.pcs_rating_kw_list),
        dc_block_energy_mwh=summary.dc_block_energy_mwh,
        dc_blocks_total_in_group=summary.dc_blocks_total_in_group,
        dc_blocks_per_feeder=list(summary.dc_blocks_per_feeder),
        equipment_list=equipment_list,
        layout_params=layout_params,
    )


def build_layout_block_spec(
    ac_output: dict,
    block_indices_to_render: List[int],
    labels: Optional[Dict[str, str]] = None,
    pcs_count: int = 4,
    dc_blocks_per_block: int = 4,
    dc_block_counts_by_block: Optional[Dict[int, int]] = None,
    arrangement: str = "2x2",
    show_skid: bool = True,
    container_length_mm: int = 6058,
    container_width_mm: int = 2438,
    dc_to_dc_clearance_m: Optional[float] = None,
    dc_to_ac_clearance_m: Optional[float] = None,
    perimeter_clearance_m: Optional[float] = None,
    dc_block_mirrored: bool = False,
    use_template: bool = False,
    dc_block_svg_path: Optional[str] = None,
    ac_block_svg_path: Optional[str] = None,
    scale: float = 0.04,
    left_margin: int = 40,
    top_margin: int = 40,
    theme: str = "light",
) -> LayoutBlockSpec:
    block_indices = block_indices_to_render or [1]
    normalized = []
    for idx in block_indices:
        value = _safe_int(idx, 0)
        if value > 0:
            normalized.append(value)
    if not normalized:
        normalized = [1]

    output_labels = labels or {}
    if not isinstance(output_labels, dict):
        output_labels = {}

    normalized_counts: Dict[int, int] = {}
    if isinstance(dc_block_counts_by_block, dict):
        for key, value in dc_block_counts_by_block.items():
            idx = _safe_int(key, 0)
            if idx > 0:
                normalized_counts[idx] = max(0, _safe_int(value, 0))

    return LayoutBlockSpec(
        block_indices_to_render=normalized,
        pcs_count=int(pcs_count),
        dc_blocks_per_block=int(dc_blocks_per_block),
        dc_block_counts_by_block=normalized_counts,
        arrangement=arrangement,
        show_skid=bool(show_skid),
        labels=output_labels,
        container_length_mm=int(container_length_mm),
        container_width_mm=int(container_width_mm),
        dc_to_dc_clearance_m=dc_to_dc_clearance_m,
        dc_to_ac_clearance_m=dc_to_ac_clearance_m,
        perimeter_clearance_m=perimeter_clearance_m,
        dc_block_mirrored=bool(dc_block_mirrored),
        use_template=bool(use_template),
        dc_block_svg_path=dc_block_svg_path,
        ac_block_svg_path=ac_block_svg_path,
        scale=scale,
        left_margin=left_margin,
        top_margin=top_margin,
        theme=str(theme or "light"),
    )
