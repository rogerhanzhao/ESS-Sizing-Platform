from __future__ import annotations

import json
from pathlib import Path

from calb_sizing_tool.adapters.excel_loader_adapter import load_dc_excel_bundle_from_path
from calb_sizing_tool.schemas.case import SizingCaseInput
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, SldRenderOptions
from calb_sizing_tool.schemas.run_bundle import DcRunBundle
from calb_sizing_tool.schemas.run_snapshot import RunInputSnapshotSchema
from calb_sizing_tool.schemas.sld_render_input import SldInputOverride
from calb_sizing_tool.services.dc_pipeline_service import size_with_guarantee
from calb_sizing_tool.services.stage1_service import run_stage1 as service_run_stage1


def load_case_definition(case_dir: Path) -> dict:
    return json.loads((case_dir / "case_definition.json").read_text(encoding="utf-8"))


def build_case_inputs(case_definition: dict) -> tuple[DcRunBundle, AcSnapshot, SldRenderOptions]:
    project_root = Path(__file__).resolve().parents[2]
    sample_excel_path = project_root / "tests" / "fixtures" / "sample_excels" / "dc_dictionary_minimal.xlsx"
    excel_bundle = load_dc_excel_bundle_from_path(sample_excel_path)
    defaults = dict(excel_bundle.defaults)

    stage1_inputs = dict(case_definition["stage1_inputs"])
    stage1 = service_run_stage1(stage1_inputs, defaults)
    snapshot = size_with_guarantee(stage1, case_definition["scenario_mode"], excel_bundle)

    case_input = SizingCaseInput(
        project_name=stage1_inputs["project_name"],
        scenario_id=case_definition["scenario_mode"],
        poi_power_req_mw=stage1_inputs["poi_power_req_mw"],
        poi_energy_req_mwh=stage1_inputs["poi_energy_req_mwh"],
        poi_nominal_voltage_kv=case_definition["case_input"]["poi_nominal_voltage_kv"],
        poi_frequency_hz=case_definition["case_input"]["poi_frequency_hz"],
        project_life_years=stage1_inputs["project_life_years"],
        cycles_per_year=stage1_inputs["cycles_per_year"],
        poi_guarantee_year=stage1_inputs["poi_guarantee_year"],
        eff_dc_cables=stage1_inputs["eff_dc_cables"],
        eff_pcs=stage1_inputs["eff_pcs"],
        eff_mvt=stage1_inputs["eff_mvt"],
        eff_ac_cables_sw_rmu=stage1_inputs["eff_ac_cables_sw_rmu"],
        eff_hvt_others=stage1_inputs["eff_hvt_others"],
        sc_time_months=stage1_inputs["sc_time_months"],
        dod_pct=stage1_inputs["dod_pct"],
        dc_round_trip_efficiency_pct=stage1_inputs["dc_round_trip_efficiency_pct"],
        rte_curve_adjust_pp=stage1_inputs["rte_curve_adjust_pp"],
        rte_monotonic_enforce=stage1_inputs["rte_monotonic_enforce"],
    )
    run_bundle = DcRunBundle(
        run_id=case_definition["run_id"],
        project_name=stage1_inputs["project_name"],
        scenario_mode=case_definition["scenario_mode"],
        input_snapshot=RunInputSnapshotSchema(
            snapshot_kind="dc_case_input",
            payload={
                "case_input": case_input.model_dump(mode="python"),
                "defaults": defaults,
            },
        ),
        snapshot=snapshot,
    )

    ac_snapshot = AcSnapshot.model_validate(case_definition["ac_snapshot"])
    options_payload = dict(case_definition["options"])
    override_payload = case_definition.get("override_payload")
    if override_payload is not None:
        options_payload["overrides"] = SldInputOverride.model_validate(override_payload)
    options = SldRenderOptions.model_validate(options_payload)
    return run_bundle, ac_snapshot, options
