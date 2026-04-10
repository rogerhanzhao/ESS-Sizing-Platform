from __future__ import annotations

from calb_sizing_tool.adapters.excel_loader_adapter import load_dc_excel_bundle_from_path
from calb_sizing_tool.config import DC_DATA_PATH
from calb_sizing_tool.services.stage1_service import run_stage1


def test_stage1_service_default_case_matches_expected_chain():
    bundle = load_dc_excel_bundle_from_path(DC_DATA_PATH)
    result = run_stage1({"project_name": "Unit Stage1"}, bundle.defaults)

    assert result.project_name == "Unit Stage1"
    assert round(result.eff_dc_to_poi_frac, 10) == round(
        result.eff_dc_cables_frac
        * result.eff_pcs_frac
        * result.eff_mvt_frac
        * result.eff_ac_cables_sw_rmu_frac
        * result.eff_hvt_others_frac,
        10,
    )
    assert result.dc_power_required_mw > 0
    assert result.dc_energy_capacity_required_mwh > 0
    assert result.sc_time_months >= 3
