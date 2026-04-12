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

from dataclasses import dataclass
from typing import List, Optional, Sequence

from calb_sizing_tool.services.sld_topology_builder import build_legacy_sld_topology


def _safe_int(value, default=0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _normalize_counts(values: Sequence, expected_len: int) -> List[int]:
    if not isinstance(values, (list, tuple)) or expected_len <= 0:
        return []
    counts = []
    for entry in values:
        counts.append(_safe_int(entry, 0))
    if len(counts) == expected_len:
        return counts
    if len(counts) > expected_len:
        return counts[:expected_len]
    counts.extend([0 for _ in range(expected_len - len(counts))])
    return counts


def _resolve_pcs_count_by_block(ac_output: dict, ac_blocks_total: int) -> List[int]:
    pcs_counts = _normalize_counts(ac_output.get("pcs_count_by_block"), ac_blocks_total)
    if pcs_counts:
        return pcs_counts

    pcs_per_block = _safe_int(ac_output.get("pcs_per_block"), 0)
    total_pcs = _safe_int(ac_output.get("total_pcs"), 0)
    if ac_blocks_total > 0 and total_pcs > 0:
        return evenly_distribute(total_pcs, ac_blocks_total)
    if ac_blocks_total > 0 and pcs_per_block > 0:
        return [pcs_per_block for _ in range(ac_blocks_total)]
    return [4] if ac_blocks_total == 1 else []


def _resolve_dc_blocks_total_by_block(
    ac_output: dict,
    stage13_output: dict,
    dc_summary: dict,
    ac_blocks_total: int,
) -> List[int]:
    totals = _normalize_counts(ac_output.get("dc_blocks_total_by_block"), ac_blocks_total)
    if totals:
        return totals

    dc_per_ac = _safe_int(ac_output.get("dc_blocks_per_ac"), 0)
    if ac_blocks_total > 0 and dc_per_ac > 0:
        return [dc_per_ac for _ in range(ac_blocks_total)]

    total_dc_blocks = _safe_int(stage13_output.get("dc_block_total_qty"), 0)
    if total_dc_blocks <= 0:
        total_dc_blocks = _safe_int(stage13_output.get("container_count"), 0) + _safe_int(
            stage13_output.get("cabinet_count"), 0
        )
    if total_dc_blocks <= 0 and isinstance(dc_summary, dict):
        dc_block = dc_summary.get("dc_block")
        if dc_block is not None:
            total_dc_blocks = _safe_int(getattr(dc_block, "count", 0))

    if ac_blocks_total > 0:
        return evenly_distribute(total_dc_blocks, ac_blocks_total)
    return []


@dataclass
class AcBlockGroupSpec:
    group_index: int
    mv_voltage_kv: float
    lv_voltage_v_ll: float
    transformer_rating_mva: float
    transformer_uk_percent: Optional[float]
    transformer_vector_group: Optional[str]
    pcs_count: int
    pcs_rating_kva_list: List[float]
    dc_block_energy_mwh: float
    dc_blocks_per_feeder: List[int]
    dc_blocks_total_in_group: int
    rmu_ratings_text: Optional[str] = None
    ct_text: Optional[str] = None
    cable_specs: Optional[dict] = None
    fuse_spec: Optional[str] = None


def build_ac_block_group_spec(
    stage13_output: dict,
    ac_output: dict,
    dc_summary: dict,
    sld_inputs: dict,
    group_index: int,
) -> AcBlockGroupSpec:
    """DEPRECATED LEGACY compatibility only.

    Authoritative engineering relationship data now comes from SldTopology.
    This wrapper is kept only for old snapshot code paths that still expect AcBlockGroupSpec.
    """
    topology = build_legacy_sld_topology(
        stage13_output=stage13_output,
        ac_output=ac_output,
        dc_summary=dc_summary,
        sld_inputs=sld_inputs,
        group_index=group_index,
    )
    summary = topology.summary
    return AcBlockGroupSpec(
        group_index=summary.group_index,
        mv_voltage_kv=summary.mv_voltage_kv,
        lv_voltage_v_ll=summary.lv_voltage_v_ll,
        transformer_rating_mva=summary.transformer_rating_mva,
        transformer_uk_percent=summary.transformer_uk_percent,
        transformer_vector_group=summary.transformer_vector_group,
        pcs_count=summary.pcs_count,
        pcs_rating_kva_list=list(summary.pcs_rating_kw_list),
        dc_block_energy_mwh=summary.dc_block_energy_mwh,
        dc_blocks_per_feeder=list(summary.dc_blocks_per_feeder),
        dc_blocks_total_in_group=summary.dc_blocks_total_in_group,
    )
