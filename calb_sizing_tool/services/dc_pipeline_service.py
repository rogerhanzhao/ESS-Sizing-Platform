from __future__ import annotations

from copy import deepcopy

from calb_sizing_tool.domain.enums import ScenarioMode
from calb_sizing_tool.schemas.case import SizingCaseInput
from calb_sizing_tool.schemas.master_data import DcExcelMasterDataBundle
from calb_sizing_tool.schemas.run_snapshot import DcPipelineRunSnapshot
from calb_sizing_tool.schemas.stage1 import Stage1Result
from calb_sizing_tool.schemas.stage2 import Stage2Result
from calb_sizing_tool.services.stage1_service import run_stage1
from calb_sizing_tool.services.stage2_service import (
    K_MAX_FIXED,
    build_config_cabinet_only,
    build_config_container_only,
    build_config_hybrid,
    pick_dc_block,
    rebuild_stage2_counts,
)
from calb_sizing_tool.services.stage3_service import run_stage3


def _poi_at_year(stage3_result, year: int) -> float | None:
    for row in stage3_result.rows:
        if row.year_index == int(year):
            return float(row.poi_usable_energy_mwh)
    return None


def _initial_stage2(mode: str, required_dc: float, bundle: DcExcelMasterDataBundle, k_max: int) -> tuple[Stage2Result, tuple, tuple]:
    picked_container = pick_dc_block(bundle.df_blocks, "container")
    picked_cabinet = pick_dc_block(bundle.df_blocks, "cabinet")
    if picked_container is None:
        raise ValueError("No active 'container' DC block template found in Excel.")
    if picked_cabinet is None and mode != ScenarioMode.CONTAINER_ONLY.value:
        raise ValueError("No active 'cabinet' DC block template found in Excel (needed for hybrid/cabinet-only).")

    cont_code, cont_name, cont_unit = picked_container
    cab_code, cab_name, cab_unit = ("", "", 0.0) if picked_cabinet is None else picked_cabinet

    if mode == ScenarioMode.CONTAINER_ONLY.value:
        stage2 = build_config_container_only(required_dc, cont_unit, cont_code, cont_name)
    elif mode == ScenarioMode.CABINET_ONLY.value:
        stage2 = build_config_cabinet_only(required_dc, cab_unit, cab_code, cab_name, k_max=k_max)
    elif mode == ScenarioMode.HYBRID.value:
        stage2 = build_config_hybrid(required_dc, cont_unit, cont_code, cont_name, cab_unit, cab_code, cab_name, k_max=k_max)
    else:
        raise ValueError(f"Unknown mode: {mode}")

    return stage2, (cont_code, cont_name, cont_unit), (cab_code, cab_name, cab_unit)


def size_with_guarantee(
    stage1: Stage1Result,
    mode: str,
    bundle: DcExcelMasterDataBundle,
    *,
    k_max: int = K_MAX_FIXED,
    max_iter: int = 60,
) -> DcPipelineRunSnapshot:
    required_dc = float(stage1.dc_energy_capacity_required_mwh)
    poi_energy_req = float(stage1.poi_energy_req_mwh)
    guarantee_year = max(0, min(int(stage1.poi_guarantee_year), int(stage1.project_life_years)))

    stage2, container_ref, cabinet_ref = _initial_stage2(mode, required_dc, bundle, k_max)
    stage3 = run_stage3(stage1, stage2, bundle)
    poi_g = _poi_at_year(stage3, guarantee_year)
    iter_count = 1
    converged = poi_g is not None and (poi_g + 1e-6 >= poi_energy_req)

    while not converged and iter_count < max_iter:
        stage2 = deepcopy(stage2)
        if mode == ScenarioMode.CONTAINER_ONLY.value:
            stage2.container_count += 1
        elif mode == ScenarioMode.CABINET_ONLY.value:
            stage2.cabinet_count += 1
        elif mode == ScenarioMode.HYBRID.value:
            if stage2.cabinet_count < k_max and stage2.cabinet_count > 0:
                stage2.cabinet_count += 1
            elif stage2.cabinet_count == 0:
                stage2.cabinet_count = 1
            else:
                stage2.container_count += 1

        stage2 = rebuild_stage2_counts(
            stage2,
            required_dc_mwh=required_dc,
            container_code=container_ref[0],
            container_name=container_ref[1],
            container_unit=container_ref[2],
            cabinet_code=cabinet_ref[0],
            cabinet_name=cabinet_ref[1],
            cabinet_unit=cabinet_ref[2],
            k_max=k_max,
        )
        stage3 = run_stage3(stage1, stage2, bundle)
        poi_g = _poi_at_year(stage3, guarantee_year)
        iter_count += 1
        converged = poi_g is not None and (poi_g + 1e-6 >= poi_energy_req)

    margin = (poi_g - poi_energy_req) if poi_g is not None else None
    summary = {
        "scenario_id": mode,
        "eff_chain": stage1.eff_dc_to_poi_frac,
        "dc_power_required_mw": stage1.dc_power_required_mw,
        "dc_energy_capacity_required_mwh": stage1.dc_energy_capacity_required_mwh,
        "effective_c_rate": stage3.meta.effective_c_rate,
        "soh_profile_id": stage3.meta.soh_profile_id,
        "rte_profile_id": stage3.meta.rte_profile_id,
        "guarantee_year_poi_usable_mwh": poi_g,
        "margin_mwh": margin,
        "iterations": iter_count,
        "converged": converged,
    }
    return DcPipelineRunSnapshot(
        stage1=stage1,
        stage2=stage2,
        stage3=stage3,
        iteration_count=iter_count,
        poi_usable_energy_mwh_at_guarantee_year=poi_g,
        converged=converged,
        summary=summary,
    )


def run_dc_pipeline(case_input: SizingCaseInput, bundle: DcExcelMasterDataBundle) -> DcPipelineRunSnapshot:
    stage1_inputs = case_input.model_dump(mode="python")
    stage1 = run_stage1(stage1_inputs, bundle.defaults)
    return size_with_guarantee(stage1, str(case_input.scenario_id), bundle, k_max=K_MAX_FIXED)
