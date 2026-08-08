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

"""
Test suite for report context and validation.
Ensures report data sources are consistent and complete.
"""
import pytest
from calb_sizing_tool.reporting.report_context import (
    build_report_context,
)


def test_report_context_basic_build():
    """Test building a basic report context with minimal data."""
    stage13_output = {
        "project_name": "Test Project",
        "poi_power_req_mw": 100.0,
        "poi_energy_req_mwh": 500.0,
        "poi_guarantee_year": 10,
        "project_life_years": 25,
        "cycles_per_year": 365,
        "eff_dc_to_poi_frac": 0.85,
        "eff_dc_cables_frac": 0.97,
        "eff_pcs_frac": 0.97,
        "eff_mvt_frac": 0.98,
        "eff_ac_cables_sw_rmu_frac": 0.98,
        "eff_hvt_others_frac": 0.98,
        "dc_block_total_qty": 4,
        "container_count": 4,
        "cabinet_count": 0,
        "poi_frequency_hz": 50,
        "selected_scenario": "container_only",
        "stage2_raw": {
            "container_count": 4,
            "cabinet_count": 0,
            "dc_nameplate_bol_mwh": 500.0,
            "oversize_mwh": 10.0,
            "block_config_table_records": [],
        },
        "stage3_meta": {},
    }
    
    ac_output = {
        "num_blocks": 2,
        "block_size_mw": 50.0,
        "pcs_count_total": 8,
        "pcs_count_by_block": [4, 4],
        "mv_voltage_kv": 33.0,
        "lv_voltage_v": 690.0,
        "grid_power_factor": 0.95,
        "transformer_kva": 52631.6,
    }
    
    ctx = build_report_context(
        session_state={},
        stage_outputs={
            "stage13_output": stage13_output,
            "ac_output": ac_output,
        },
        project_inputs={
            "poi_power_mw": 100.0,
            "poi_energy_mwh": 500.0,
            "poi_energy_guarantee_mwh": 500.0,
            "poi_guarantee_year": 10,
        }
    )
    
    # Verify context is built
    assert ctx.project_name == "Test Project"
    assert ctx.poi_power_requirement_mw == 100.0
    assert ctx.poi_energy_requirement_mwh == 500.0
    assert ctx.poi_energy_guarantee_mwh == 500.0
    assert ctx.poi_guarantee_year == 10
    assert ctx.dc_blocks_total == 4
    assert ctx.ac_blocks_total == 2
    assert ctx.pcs_modules_total == 8


def test_report_context_with_stage3_data():
    """Test that stage3 DataFrame is properly stored in context."""
    import pandas as pd
    
    stage13_output = {
        "project_name": "Test Project",
        "poi_power_req_mw": 100.0,
        "poi_energy_req_mwh": 500.0,
        "poi_guarantee_year": 10,
        "project_life_years": 25,
        "cycles_per_year": 365,
        "eff_dc_to_poi_frac": 0.85,
        "eff_dc_cables_frac": 0.97,
        "eff_pcs_frac": 0.97,
        "eff_mvt_frac": 0.98,
        "eff_ac_cables_sw_rmu_frac": 0.98,
        "eff_hvt_others_frac": 0.98,
        "dc_block_total_qty": 4,
        "selected_scenario": "container_only",
        "stage2_raw": {},
        "stage3_meta": {},
    }
    
    # Create a simple stage3 DataFrame
    stage3_df = pd.DataFrame({
        "Year_Index": [0, 5, 10],
        "POI_Usable_Energy_MWh": [500.0, 485.0, 470.0],
        "DC_RTE_Pct": [88.0, 86.5, 85.0],
        "System_RTE_Pct": [62.0, 60.5, 59.0],
        "DC_Usable_MWh": [588.0, 561.0, 554.0],
        "SOH_Absolute_Pct": [100.0, 97.0, 94.0],
    })
    
    ac_output = {
        "num_blocks": 2,
        "block_size_mw": 50.0,
        "pcs_count_total": 8,
    }
    
    ctx = build_report_context(
        session_state={},
        stage_outputs={
            "stage13_output": stage13_output,
            "stage3_df": stage3_df,
            "ac_output": ac_output,
        },
        project_inputs={
            "poi_energy_guarantee_mwh": 500.0,
            "poi_guarantee_year": 10,
        }
    )
    
    # Verify stage3 data is stored
    assert ctx.stage3_df is not None
    assert not ctx.stage3_df.empty
    assert len(ctx.stage3_df) == 3
    assert ctx.poi_usable_energy_mwh_at_year0 == 500.0
    assert ctx.poi_usable_energy_mwh_at_guarantee_year == 470.0
