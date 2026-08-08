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

import sys
import types
import pandas as pd


def _inject_dummy_dc_view():
    # Provide a lightweight dummy for calb_sizing_tool.ui.dc_view so that
    # report_context can be imported without pulling heavy dependencies
    mod = types.SimpleNamespace()

    def load_data(path):
        # returns the expected tuple shape; the actual contents aren't used in
        # the first test
        return {}, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    def run_stage3(stage1, stage2, df_soh_profile, df_soh_curve, df_rte_profile, df_rte_curve):
        df = pd.DataFrame({"Year_Index": [0], "POI_Usable_Energy_MWh": [123.45]})
        meta = {"effective_c_rate": 1.0}
        return df, meta

    mod.load_data = load_data
    mod.run_stage3 = run_stage3
    sys.modules["calb_sizing_tool.ui.dc_view"] = mod


def test_build_report_context_uses_embedded_stage3_df():
    _inject_dummy_dc_view()

    from calb_sizing_tool.reporting.report_context import build_report_context

    stage1 = {
        "project_name": "p",
        "poi_power_req_mw": 100.0,
        "poi_energy_req_mwh": 400.0,
        "project_life_years": 20,
        "cycles_per_year": 365,
        "poi_guarantee_year": 0,
    }
    stage2 = {"dc_nameplate_bol_mwh": 500.0, "container_count": 10, "cabinet_count": 0}
    s3_df = pd.DataFrame({"Year_Index": [0, 1], "POI_Usable_Energy_MWh": [999.0, 888.0]})

    stage13_output = {**stage1, "stage2_raw": stage2, "stage3_meta": {"eff": 1.0}, "stage3_df": s3_df}

    ctx = build_report_context(
        session_state={"dc_results": {}},
        stage_outputs={"stage13_output": stage13_output, "ac_output": {}},
        project_inputs={"poi_energy_guarantee_mwh": 400.0},
        scenario_ids=stage13_output.get("selected_scenario"),
    )

    assert ctx.stage3_df is not None
    assert int(ctx.poi_usable_energy_mwh_at_year0) == 999


def test_build_report_context_never_recomputes_stage3():
    """Owner ruling 2026-08-08: the report CONSUMES Stage 3, it does not compute it.

    This used to assert the opposite — that a context built without a Stage 3
    frame silently recomputed one. The recompute read the SOH/RTE curves from the
    EXCEL workbook, while dc_view.show() prefers the DB curves once the admin has
    migrated them, so it was a second calculation scheme presenting itself as the
    run's own result. SIZING_LOGIC_CANON_V1 "权威边界" forbids reporting/* from
    recomputing sizing at all.

    Measured before removal: it fired 0 times in the live DC-run path and 0
    times in the restore-a-saved-run path. A caller that supplies no Stage 3 now
    gets a context that says so, instead of numbers from other curves.
    """
    _inject_dummy_dc_view()

    from calb_sizing_tool.reporting import report_context
    from calb_sizing_tool.reporting.report_context import build_report_context

    assert not hasattr(report_context, "_get_stage3_df"), (
        "the Excel recompute is back; the report must consume Stage 3, not compute it"
    )

    stage1 = {
        "project_name": "p",
        "poi_power_req_mw": 100.0,
        "poi_energy_req_mwh": 400.0,
        "project_life_years": 20,
        "cycles_per_year": 365,
        "poi_guarantee_year": 0,
    }
    stage2 = {"dc_nameplate_bol_mwh": 500.0, "container_count": 10, "cabinet_count": 0}
    stage13_output = {**stage1, "stage2_raw": stage2, "stage3_meta": {"eff": 1.0}}

    ctx = build_report_context(
        session_state={"dc_results": {}},
        stage_outputs={"stage13_output": stage13_output, "ac_output": {}},
        project_inputs={"poi_energy_guarantee_mwh": 400.0},
        scenario_ids=stage13_output.get("selected_scenario"),
    )

    # The dummy dc_view would have produced 123.45 had anything called it.
    assert ctx.stage3_df is None
    assert ctx.poi_usable_energy_mwh_at_year0 is None
    assert ctx.poi_usable_energy_mwh_at_guarantee_year is None
    assert "does not recompute" in ctx.stage3_meta.get("error", ""), (
        "the missing Stage 3 must be stated, not silently substituted"
    )
