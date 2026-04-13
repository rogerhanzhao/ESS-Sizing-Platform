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
from typing import List, Optional

from calb_sizing_tool.services.sld_topology_builder import build_legacy_sld_topology


@dataclass
class AcBlockGroupSpec:
    group_index: int
    ac_blocks_total: int
    mv_voltage_kv: float
    lv_voltage_v_ll: float
    transformer_rating_mva: float
    transformer_uk_percent: Optional[float]
    transformer_vector_group: Optional[str]
    pcs_count: int
    pcs_rating_kw_list: List[float]
    dc_block_energy_mwh: float
    dc_blocks_per_feeder: List[int]
    dc_blocks_total_in_group: int
    rmu_ratings_text: Optional[str] = None
    ct_text: Optional[str] = None
    cable_specs: Optional[dict] = None
    fuse_spec: Optional[str] = None

    @property
    def pcs_rating_kva_list(self) -> List[float]:
        """Legacy alias only.

        Older snapshot helpers still reference `pcs_rating_kva_list`, but the
        authoritative SLD contract uses kW-based PCS ratings.
        """
        return list(self.pcs_rating_kw_list)


def build_ac_block_group_spec(
    stage13_output: dict,
    ac_output: dict,
    dc_summary: dict,
    sld_inputs: dict,
    group_index: int,
) -> AcBlockGroupSpec:
    """DEPRECATED LEGACY compatibility only.

    Authoritative engineering relationship data now comes from SldTopology.
    This wrapper projects the already-built compatibility topology into the
    older AcBlockGroupSpec shape without re-deriving feeder allocation.
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
        ac_blocks_total=summary.ac_blocks_total,
        mv_voltage_kv=summary.mv_voltage_kv,
        lv_voltage_v_ll=summary.lv_voltage_v_ll,
        transformer_rating_mva=summary.transformer_rating_mva,
        transformer_uk_percent=summary.transformer_uk_percent,
        transformer_vector_group=summary.transformer_vector_group,
        pcs_count=summary.pcs_count,
        pcs_rating_kw_list=list(summary.pcs_rating_kw_list),
        dc_block_energy_mwh=summary.dc_block_energy_mwh,
        dc_blocks_per_feeder=list(summary.dc_blocks_per_feeder),
        dc_blocks_total_in_group=summary.dc_blocks_total_in_group,
    )
