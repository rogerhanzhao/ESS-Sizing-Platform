from __future__ import annotations

from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from calb_sizing_tool.adapters.excel_loader_adapter import load_dc_excel_bundle_from_path
from calb_sizing_tool.config import DC_DATA_PATH
from calb_sizing_tool.schemas.case import SizingCaseInput
from calb_sizing_tool.services.dc_pipeline_service import run_dc_pipeline
from tests.conftest import _round_value, load_json, load_stage3_csv


def _snapshot_summary(snapshot) -> dict:
    return _round_value(snapshot.summary | {"guarantee_year": snapshot.stage1.poi_guarantee_year})


def test_dc_pipeline_regression_against_golden_cases(golden_case_dirs: list[Path]):
    bundle = load_dc_excel_bundle_from_path(DC_DATA_PATH)

    for case_dir in golden_case_dirs:
        case_input = SizingCaseInput.model_validate(load_json(case_dir / "case_input.json"))
        expected_stage1 = load_json(case_dir / "stage1_expected.json")
        expected_stage2 = load_json(case_dir / "stage2_expected.json")
        expected_stage3 = load_stage3_csv(case_dir / "stage3_expected.csv").round(10)
        expected_summary = load_json(case_dir / "summary_expected.json")

        snapshots = [run_dc_pipeline(case_input, bundle) for _ in range(3)]
        first = snapshots[0]

        assert _round_value(first.stage1.model_dump()) == expected_stage1
        assert _round_value(first.stage2.model_dump()) == expected_stage2
        assert _round_value(
            {
                "fixture_id": case_input.fixture_id,
                "scenario_id": first.summary["scenario_id"],
                "eff_chain": first.summary["eff_chain"],
                "dc_power_required_mw": first.summary["dc_power_required_mw"],
                "dc_energy_capacity_required_mwh": first.summary["dc_energy_capacity_required_mwh"],
                "effective_c_rate": first.summary["effective_c_rate"],
                "soh_profile_id": first.summary["soh_profile_id"],
                "rte_profile_id": first.summary["rte_profile_id"],
                "guarantee_year": first.stage1.poi_guarantee_year,
                "guarantee_year_poi_usable_mwh": first.summary["guarantee_year_poi_usable_mwh"],
                "margin_mwh": first.summary["margin_mwh"],
                "iterations": first.summary["iterations"],
                "converged": first.summary["converged"],
                "container_count": first.stage2.container_count,
                "cabinet_count": first.stage2.cabinet_count,
                "dc_nameplate_bol_mwh": first.stage2.dc_nameplate_bol_mwh,
            }
        ) == expected_summary
        assert_frame_equal(first.stage3.dataframe().round(10), expected_stage3, check_dtype=False)

        for rerun in snapshots[1:]:
            assert _round_value(rerun.stage1.model_dump()) == _round_value(first.stage1.model_dump())
            assert _round_value(rerun.stage2.model_dump()) == _round_value(first.stage2.model_dump())
            assert _snapshot_summary(rerun) == _snapshot_summary(first)
            assert_frame_equal(rerun.stage3.dataframe().round(10), first.stage3.dataframe().round(10), check_dtype=False)
