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
from typing import Any, Dict, List, Optional

from calb_sizing_tool.schemas.sld_topology import SldTopology
from calb_sizing_tool.schemas.sld_render_input import SldEquipmentRatings, SldLabels

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
    ac_blocks_total: int
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
        ac_blocks_total=summary.ac_blocks_total,
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


def _require_legacy_text(value: Any, field_name: str) -> str:
    resolved = str(value or "").strip()
    if not resolved:
        raise ValueError(f"Legacy SLD spec is missing required field: {field_name}.")
    return resolved


def _require_legacy_positive_float(value: Any, field_name: str, *, missing_message: str | None = None) -> float:
    try:
        resolved = float(value)
    except Exception as exc:
        raise ValueError(missing_message or f"Legacy SLD spec is missing required field: {field_name}.") from exc
    if resolved <= 0:
        raise ValueError(missing_message or f"Legacy SLD spec is missing required field: {field_name}.")
    return resolved


def build_topology_from_legacy_sld_group_spec(spec: SldGroupSpec) -> SldTopology:
    """Compatibility adapter only.

    This converts legacy renderer-facing SldGroupSpec objects into SldTopology.
    It must not invent feeder allocation, PCS count, or engineering ratings.
    Missing required engineering fields raise immediately.
    """
    equipment_list = spec.equipment_list if isinstance(spec.equipment_list, dict) else {}
    mv_labels = equipment_list.get("mv_labels") if isinstance(equipment_list.get("mv_labels"), dict) else {}
    transformer = equipment_list.get("transformer") if isinstance(equipment_list.get("transformer"), dict) else {}

    labels = SldLabels.model_validate(
        {
            "to_switchgear": _require_legacy_text(mv_labels.get("to_switchgear"), "equipment_list.mv_labels.to_switchgear"),
            "to_other_rmu": _require_legacy_text(mv_labels.get("to_other_rmu"), "equipment_list.mv_labels.to_other_rmu"),
        }
    )

    if not isinstance(equipment_list.get("rmu"), dict):
        raise ValueError("Legacy SLD spec is missing required field: equipment_list.rmu.")
    if not isinstance(equipment_list.get("lv_busbar"), dict):
        raise ValueError("Legacy SLD spec is missing required field: equipment_list.lv_busbar.")
    if not isinstance(equipment_list.get("cables"), dict):
        raise ValueError("Legacy SLD spec is missing required field: equipment_list.cables.")
    if not isinstance(equipment_list.get("dc_fuse"), dict):
        raise ValueError("Legacy SLD spec is missing required field: equipment_list.dc_fuse.")

    rmu_payload = dict(equipment_list["rmu"])
    _require_legacy_positive_float(
        rmu_payload.get("rated_kv"),
        "equipment_list.rmu.rated_kv",
        missing_message="Legacy SLD spec is missing equipment_list.rmu.rated_kv. Renderer will not infer RMU equipment class.",
    )

    equipment_ratings = SldEquipmentRatings.model_validate(
        {
            "rmu": rmu_payload,
            "lv_busbar": dict(equipment_list["lv_busbar"]),
            "cables": dict(equipment_list["cables"]),
            "dc_fuse": dict(equipment_list["dc_fuse"]),
            "transformer_tap_range": transformer.get("tap_range"),
            "transformer_cooling": transformer.get("cooling"),
        }
    )

    transformer_vector_group = _require_legacy_text(
        transformer.get("vector_group") or spec.transformer_vector_group,
        "transformer.vector_group",
    )
    transformer_uk_percent = _require_legacy_positive_float(
        transformer.get("uk_percent") if transformer.get("uk_percent") is not None else spec.transformer_uk_percent,
        "transformer.uk_percent",
    )
    dc_block_voltage_v = _require_legacy_positive_float(
        equipment_list.get("dc_block_voltage_v"),
        "equipment_list.dc_block_voltage_v",
    )

    dc_bus_nodes: list[dict[str, Any]] = []
    pcs_nodes: list[dict[str, Any]] = []
    dc_block_nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for feeder_index, rating in enumerate(spec.pcs_rating_kw_list, start=1):
        pcs_node_id = f"G{spec.group_index:02d}-F{feeder_index:02d}-PCS-NODE"
        dc_bus_node_id = f"G{spec.group_index:02d}-F{feeder_index:02d}-DC-BUSBAR-NODE"
        pcs_nodes.append(
            {
                "node_id": pcs_node_id,
                "node_type": "pcs",
                "display_name": f"PCS {feeder_index}",
                "equipment_id": f"G{spec.group_index:02d}-F{feeder_index:02d}-PCS",
                "feeder_index": feeder_index,
                "attributes": {"pcs_rating_kw": rating},
            }
        )
        dc_bus_nodes.append(
            {
                "node_id": dc_bus_node_id,
                "node_type": "dc_busbar",
                "display_name": f"DC Busbar {feeder_index}",
                "equipment_id": f"G{spec.group_index:02d}-F{feeder_index:02d}-DC-BUSBAR",
                "feeder_index": feeder_index,
                "attributes": {"dc_block_count": spec.dc_blocks_per_feeder[feeder_index - 1]},
            }
        )
        edges.append(
            {
                "edge_id": f"G{spec.group_index:02d}-EDGE-LV-PCS-{feeder_index:02d}",
                "edge_type": "lv_busbar_to_pcs",
                "source_node_id": f"G{spec.group_index:02d}-LV-BUSBAR-NODE",
                "target_node_id": pcs_node_id,
                "feeder_index": feeder_index,
            }
        )
        edges.append(
            {
                "edge_id": f"G{spec.group_index:02d}-EDGE-PCS-DCBUS-{feeder_index:02d}",
                "edge_type": "pcs_to_dc_busbar",
                "source_node_id": pcs_node_id,
                "target_node_id": dc_bus_node_id,
                "feeder_index": feeder_index,
            }
        )

    dc_block_index = 0
    for feeder_index, count in enumerate(spec.dc_blocks_per_feeder, start=1):
        for local_index in range(1, count + 1):
            dc_block_index += 1
            node_id = f"G{spec.group_index:02d}-F{feeder_index:02d}-DC-BLOCK-{local_index:02d}-NODE"
            dc_block_nodes.append(
                {
                    "node_id": node_id,
                    "node_type": "dc_block",
                    "display_name": f"DC Block {dc_block_index}",
                    "equipment_id": f"G{spec.group_index:02d}-F{feeder_index:02d}-DC-BLOCK-{local_index:02d}",
                    "feeder_index": feeder_index,
                    "dc_block_index": dc_block_index,
                    "attributes": {
                        "dc_block_energy_mwh": spec.dc_block_energy_mwh,
                        "dc_block_voltage_v": dc_block_voltage_v,
                    },
                }
            )
            edges.append(
                {
                    "edge_id": f"G{spec.group_index:02d}-EDGE-DCBUS-BLOCK-{dc_block_index:02d}",
                    "edge_type": "dc_busbar_to_dc_block",
                    "source_node_id": f"G{spec.group_index:02d}-F{feeder_index:02d}-DC-BUSBAR-NODE",
                    "target_node_id": node_id,
                    "feeder_index": feeder_index,
                }
            )

    topology_payload = {
        "run_id": None,
        "project_name": "Legacy SLD Group",
        "scenario_id": "legacy_sld_group_spec",
        "source_trace": {
            "A": "deprecated spec compatibility adapter",
            "B": "legacy SldGroupSpec inputs must already contain explicit engineering topology and ratings",
        },
        "validation_mode": "draft",
        "labels": labels.model_dump(mode="python"),
        "equipment_ratings": equipment_ratings.model_dump(mode="python"),
        "summary": {
            "group_index": spec.group_index,
            "ac_blocks_total": spec.ac_blocks_total,
            "feeder_count": spec.pcs_count,
            "pcs_count": spec.pcs_count,
            "dc_blocks_total_in_group": spec.dc_blocks_total_in_group,
            "dc_blocks_per_feeder": list(spec.dc_blocks_per_feeder),
            "mv_voltage_kv": spec.mv_voltage_kv,
            "lv_voltage_v_ll": spec.lv_voltage_v_ll,
            "transformer_rating_mva": spec.transformer_mva,
            "transformer_vector_group": transformer_vector_group,
            "transformer_uk_percent": transformer_uk_percent,
            "pcs_rating_kw_list": list(spec.pcs_rating_kw_list),
            "dc_block_energy_mwh": spec.dc_block_energy_mwh,
            "dc_block_voltage_v": dc_block_voltage_v,
            "project_frequency_hz": equipment_list.get("project_hz"),
            "diagram_mode": "one_ac_block_group",
            "theme": (spec.layout_params or {}).get("theme") or "light",
            "compact_mode": bool((spec.layout_params or {}).get("compact_mode")),
            "draw_summary": bool((spec.layout_params or {}).get("draw_summary")),
        },
        "nodes": [
            {
                "node_id": f"G{spec.group_index:02d}-MV-BUS",
                "node_type": "mv_bus",
                "display_name": "MV Bus",
                "attributes": {"mv_voltage_kv": spec.mv_voltage_kv},
            },
            {
                "node_id": f"G{spec.group_index:02d}-RMU-NODE",
                "node_type": "rmu",
                "display_name": "RMU",
                "equipment_id": f"G{spec.group_index:02d}-RMU",
            },
            {
                "node_id": f"G{spec.group_index:02d}-TX-NODE",
                "node_type": "transformer",
                "display_name": "Transformer",
                "equipment_id": f"G{spec.group_index:02d}-TX",
            },
            {
                "node_id": f"G{spec.group_index:02d}-LV-BUSBAR-NODE",
                "node_type": "lv_busbar",
                "display_name": "LV Busbar",
                "equipment_id": f"G{spec.group_index:02d}-LV-BUSBAR",
            },
            *pcs_nodes,
            *dc_bus_nodes,
            *dc_block_nodes,
        ],
        "equipment": [
            {"equipment_id": f"G{spec.group_index:02d}-RMU", "equipment_type": "rmu", "display_name": "RMU"},
            {"equipment_id": f"G{spec.group_index:02d}-TX", "equipment_type": "transformer", "display_name": "Transformer"},
            {"equipment_id": f"G{spec.group_index:02d}-LV-BUSBAR", "equipment_type": "lv_busbar", "display_name": "LV Busbar"},
            *[
                {
                    "equipment_id": f"G{spec.group_index:02d}-F{feeder_index:02d}-PCS",
                    "equipment_type": "pcs",
                    "display_name": f"PCS {feeder_index}",
                    "feeder_index": feeder_index,
                }
                for feeder_index in range(1, spec.pcs_count + 1)
            ],
            *[
                {
                    "equipment_id": f"G{spec.group_index:02d}-F{feeder_index:02d}-DC-BUSBAR",
                    "equipment_type": "dc_busbar",
                    "display_name": f"DC Busbar {feeder_index}",
                    "feeder_index": feeder_index,
                }
                for feeder_index in range(1, spec.pcs_count + 1)
            ],
            *[
                {
                    "equipment_id": item["equipment_id"],
                    "equipment_type": "dc_block",
                    "display_name": item["display_name"],
                    "feeder_index": item["feeder_index"],
                    "dc_block_index": item["dc_block_index"],
                }
                for item in dc_block_nodes
            ],
        ],
        "edges": [
            {
                "edge_id": f"G{spec.group_index:02d}-EDGE-MV-RMU",
                "edge_type": "mv_link",
                "source_node_id": f"G{spec.group_index:02d}-MV-BUS",
                "target_node_id": f"G{spec.group_index:02d}-RMU-NODE",
            },
            {
                "edge_id": f"G{spec.group_index:02d}-EDGE-RMU-TX",
                "edge_type": "rmu_to_transformer",
                "source_node_id": f"G{spec.group_index:02d}-RMU-NODE",
                "target_node_id": f"G{spec.group_index:02d}-TX-NODE",
            },
            {
                "edge_id": f"G{spec.group_index:02d}-EDGE-TX-LVBUS",
                "edge_type": "transformer_to_lv_busbar",
                "source_node_id": f"G{spec.group_index:02d}-TX-NODE",
                "target_node_id": f"G{spec.group_index:02d}-LV-BUSBAR-NODE",
            },
            *edges,
        ],
    }
    return SldTopology.model_validate(topology_payload)


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
