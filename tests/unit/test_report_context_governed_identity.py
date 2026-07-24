"""ReportContext carries the governed configuration identity from ac_output.

Report / Site Array must route by ``configuration_code`` / ``layout_variant``
directly, not rebuild the unit from an average DC-per-AC ratio.
"""
from __future__ import annotations

from calb_sizing_tool.reporting.report_context import build_report_context
from calb_sizing_tool.schemas.governed_ac_block_config import (
    ACBLK_10MW_8PCS_8DC_40FT_BILATERAL as CFG,
)


def _minimal_stage13() -> dict:
    return {
        "project_name": "Governed Identity Test",
        "poi_power_req_mw": 10.0,
        "poi_energy_req_mwh": 40.0,
        "project_life_years": 20,
        "poi_guarantee_year": 0,
        "cycles_per_year": 365,
    }


def test_report_context_carries_configuration_code_and_variant():
    ac_output = CFG.to_ac_sld_output(
        engineering_overrides={"transformer_mva": 11.11, "lv_voltage_v": 690.0}
    )
    ctx = build_report_context(
        session_state={},
        stage_outputs={"stage13_output": _minimal_stage13(), "ac_output": ac_output, "stage2": {}},
        project_inputs={},
    )
    assert ctx.configuration_code == "ACBLK-10MW-8PCS-8DC-40FT-BILATERAL"
    assert ctx.layout_variant == "central_40ft_bilateral_4plus4"


def test_report_context_identity_is_none_for_ungoverned_runs():
    ctx = build_report_context(
        session_state={},
        stage_outputs={
            "stage13_output": _minimal_stage13(),
            "ac_output": {"num_blocks": 2, "pcs_per_block": 4},
            "stage2": {},
        },
        project_inputs={},
    )
    assert ctx.configuration_code is None
    assert ctx.layout_variant is None
