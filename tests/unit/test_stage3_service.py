from __future__ import annotations

from calb_sizing_tool.adapters.excel_loader_adapter import load_dc_excel_bundle_from_path
from calb_sizing_tool.config import DC_DATA_PATH
from calb_sizing_tool.services.stage1_service import run_stage1
from calb_sizing_tool.services.stage2_service import build_config_container_only, pick_dc_block
from calb_sizing_tool.services.stage3_service import run_stage3


def test_stage3_service_selects_profiles_and_returns_full_life_curve():
    bundle = load_dc_excel_bundle_from_path(DC_DATA_PATH)
    stage1 = run_stage1({"project_name": "Unit Stage3", "poi_power_req_mw": 100, "poi_energy_req_mwh": 400}, bundle.defaults)
    cont_code, cont_name, cont_unit = pick_dc_block(bundle.df_blocks, "container")
    stage2 = build_config_container_only(stage1.dc_energy_capacity_required_mwh, cont_unit, cont_code, cont_name)
    stage3 = run_stage3(stage1, stage2, bundle)

    assert len(stage3.rows) == stage1.project_life_years + 1
    assert stage3.meta.soh_profile_id > 0
    assert stage3.meta.rte_profile_id > 0
    assert stage3.rows[0].poi_usable_energy_mwh > 0
    assert stage3.meta.dc_usable_bol_mwh > 0
    assert stage3.meta.dc_usable_cod_mwh > 0
    assert stage3.meta.dc_usable_cod_mwh < stage3.meta.dc_usable_bol_mwh
