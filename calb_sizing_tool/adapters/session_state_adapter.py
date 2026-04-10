from __future__ import annotations

"""Legacy adapter only.

This module bridges DB snapshots into legacy `stage13_output` shapes for
downstream pages that still depend on session_state. It must not be treated
as a runtime source of truth.
"""

from typing import Any

from calb_sizing_tool.schemas.run_snapshot import DcPipelineRunSnapshot
from calb_sizing_tool.ui.stage4_interface import pack_stage13_output


def build_dc_result_summary(snapshot: DcPipelineRunSnapshot) -> dict[str, Any]:
    stage1 = snapshot.stage1
    stage2 = snapshot.stage2
    stage3_df = snapshot.stage3.dataframe()
    guarantee_row = stage3_df[stage3_df["Is_Guarantee_Year"]]
    guarantee_poi = (
        float(guarantee_row["POI_Usable_Energy_MWh"].iloc[0]) if not guarantee_row.empty else 0.0
    )
    return {
        "target_mw": stage1.poi_power_req_mw,
        "mwh": stage1.poi_energy_req_mwh,
        "dc_nameplate_bol_mwh": stage2.dc_nameplate_bol_mwh,
        "dc_blocks_total": stage2.container_count + stage2.cabinet_count,
        "guarantee_year_poi_usable_mwh": guarantee_poi,
        "iterations": snapshot.iteration_count,
        "converged": snapshot.converged,
    }


def build_stage13_output(
    snapshot: DcPipelineRunSnapshot,
    *,
    dc_block_total_qty: int,
    selected_scenario: str,
    poi_nominal_voltage_kv: float,
    poi_frequency_hz: float | None = None,
) -> dict[str, Any]:
    return pack_stage13_output(
        snapshot.stage1.to_legacy_dict(),
        snapshot.stage2.to_legacy_dict(),
        snapshot.stage3.meta.to_legacy_dict(),
        dc_block_total_qty=dc_block_total_qty,
        selected_scenario=selected_scenario,
        poi_nominal_voltage_kv=poi_nominal_voltage_kv,
        poi_frequency_hz=poi_frequency_hz,
        stage3_df=snapshot.stage3.dataframe(),
    )
