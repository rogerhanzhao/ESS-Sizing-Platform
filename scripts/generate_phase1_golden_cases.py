from __future__ import annotations

import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from calb_sizing_tool.adapters.excel_loader_adapter import load_dc_excel_bundle_from_path
from calb_sizing_tool.config import DC_DATA_PATH
from calb_sizing_tool.schemas.case import SizingCaseInput
from calb_sizing_tool.services.dc_pipeline_service import run_dc_pipeline


GOLDEN_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "golden_cases"


BASELINE_CASES = [
    {
        "fixture_id": "case01_standard_4h_container_y0",
        "project_name": "Baseline Standard 4H Container Y0",
        "scenario_id": "container_only",
        "poi_power_req_mw": 100.0,
        "poi_energy_req_mwh": 400.0,
        "poi_guarantee_year": 0,
    },
    {
        "fixture_id": "case02_standard_4h_hybrid_y0",
        "project_name": "Baseline Standard 4H Hybrid Y0",
        "scenario_id": "hybrid",
        "poi_power_req_mw": 100.0,
        "poi_energy_req_mwh": 400.0,
        "poi_guarantee_year": 0,
    },
    {
        "fixture_id": "case03_standard_4h_cabinet_y0",
        "project_name": "Baseline Standard 4H Cabinet Y0",
        "scenario_id": "cabinet_only",
        "poi_power_req_mw": 100.0,
        "poi_energy_req_mwh": 400.0,
        "poi_guarantee_year": 0,
    },
    {
        "fixture_id": "case04_two_hour_container_y0",
        "project_name": "Baseline 2H Container Y0",
        "scenario_id": "container_only",
        "poi_power_req_mw": 100.0,
        "poi_energy_req_mwh": 200.0,
        "poi_guarantee_year": 0,
    },
    {
        "fixture_id": "case05_one_hour_hybrid_y0",
        "project_name": "Baseline 1H Hybrid Y0",
        "scenario_id": "hybrid",
        "poi_power_req_mw": 100.0,
        "poi_energy_req_mwh": 100.0,
        "poi_guarantee_year": 0,
    },
    {
        "fixture_id": "case06_standard_4h_container_y5",
        "project_name": "Baseline Standard 4H Container Y5",
        "scenario_id": "container_only",
        "poi_power_req_mw": 100.0,
        "poi_energy_req_mwh": 400.0,
        "poi_guarantee_year": 5,
    },
    {
        "fixture_id": "case07_standard_4h_container_y10",
        "project_name": "Baseline Standard 4H Container Y10",
        "scenario_id": "container_only",
        "poi_power_req_mw": 100.0,
        "poi_energy_req_mwh": 400.0,
        "poi_guarantee_year": 10,
    },
    {
        "fixture_id": "case08_hybrid_sc3",
        "project_name": "Baseline Hybrid SC3",
        "scenario_id": "hybrid",
        "poi_power_req_mw": 100.0,
        "poi_energy_req_mwh": 400.0,
        "poi_guarantee_year": 5,
        "sc_time_months": 3,
    },
    {
        "fixture_id": "case09_hybrid_sc12",
        "project_name": "Baseline Hybrid SC12",
        "scenario_id": "hybrid",
        "poi_power_req_mw": 100.0,
        "poi_energy_req_mwh": 400.0,
        "poi_guarantee_year": 5,
        "sc_time_months": 12,
    },
    {
        "fixture_id": "case10_container_dod90_rte_adj",
        "project_name": "Baseline Container DoD90 RTEAdj",
        "scenario_id": "container_only",
        "poi_power_req_mw": 100.0,
        "poi_energy_req_mwh": 400.0,
        "poi_guarantee_year": 5,
        "dod_pct": 90.0,
        "dc_round_trip_efficiency_pct": 93.0,
        "rte_curve_adjust_pp": 1.5,
    },
]


def _round_value(value):
    if isinstance(value, dict):
        return {k: _round_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_round_value(v) for v in value]
    if isinstance(value, float):
        return round(value, 10)
    return value


def _stage2_json(snapshot) -> dict:
    data = snapshot.stage2.model_dump()
    data["block_config_items"] = [_round_value(item.model_dump()) for item in snapshot.stage2.block_config_items]
    return _round_value(data)


def _summary_json(case_input: dict, snapshot) -> dict:
    return _round_value(
        {
            "fixture_id": case_input["fixture_id"],
            "scenario_id": case_input["scenario_id"],
            "eff_chain": snapshot.stage1.eff_dc_to_poi_frac,
            "dc_power_required_mw": snapshot.stage1.dc_power_required_mw,
            "dc_energy_capacity_required_mwh": snapshot.stage1.dc_energy_capacity_required_mwh,
            "effective_c_rate": snapshot.stage3.meta.effective_c_rate,
            "soh_profile_id": snapshot.stage3.meta.soh_profile_id,
            "rte_profile_id": snapshot.stage3.meta.rte_profile_id,
            "guarantee_year": snapshot.stage1.poi_guarantee_year,
            "guarantee_year_poi_usable_mwh": snapshot.poi_usable_energy_mwh_at_guarantee_year,
            "margin_mwh": snapshot.summary["margin_mwh"],
            "iterations": snapshot.iteration_count,
            "converged": snapshot.converged,
            "container_count": snapshot.stage2.container_count,
            "cabinet_count": snapshot.stage2.cabinet_count,
            "dc_nameplate_bol_mwh": snapshot.stage2.dc_nameplate_bol_mwh,
        }
    )


def main() -> int:
    GOLDEN_ROOT.mkdir(parents=True, exist_ok=True)
    bundle = load_dc_excel_bundle_from_path(DC_DATA_PATH)

    for payload in BASELINE_CASES:
        case_dir = GOLDEN_ROOT / payload["fixture_id"]
        case_dir.mkdir(parents=True, exist_ok=True)

        case_input = SizingCaseInput.model_validate(payload)
        snapshot = run_dc_pipeline(case_input, bundle)

        (case_dir / "case_input.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (case_dir / "stage1_expected.json").write_text(
            json.dumps(_round_value(snapshot.stage1.model_dump()), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (case_dir / "stage2_expected.json").write_text(
            json.dumps(_stage2_json(snapshot), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        snapshot.stage3.dataframe().round(10).to_csv(case_dir / "stage3_expected.csv", index=False)
        (case_dir / "summary_expected.json").write_text(
            json.dumps(_summary_json(payload, snapshot), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    print(f"Wrote {len(BASELINE_CASES)} baseline cases to {GOLDEN_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
