from __future__ import annotations

from calb_sizing_tool.adapters.excel_loader_adapter import load_dc_excel_bundle_from_path
from calb_sizing_tool.schemas.case import SizingCaseInput
from calb_sizing_tool.services.dc_pipeline_service import size_with_guarantee
from calb_sizing_tool.services.run_persistence_service import persist_dc_run
from calb_sizing_tool.services.run_restore_service import load_dc_run_bundle
from calb_sizing_tool.services.stage1_service import run_stage1 as service_run_stage1


def test_dc_run_persist_and_restore(sample_excel_path, tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'dc_run.sqlite').as_posix()}"

    bundle = load_dc_excel_bundle_from_path(sample_excel_path)
    defaults = dict(bundle.defaults)

    def _to_float(value, fallback):
        try:
            if isinstance(value, str):
                value = value.replace("%", "").replace(",", "").strip()
            return float(value)
        except Exception:
            return float(fallback)

    stage1_inputs = {
        "project_name": "Persist Restore Test",
        "poi_power_req_mw": 50.0,
        "poi_energy_req_mwh": 200.0,
        "project_life_years": 20,
        "cycles_per_year": 365,
        "poi_guarantee_year": 0,
        "sc_time_months": 3,
        "dod_pct": _to_float(defaults.get("dod_pct", 95.0), 95.0),
        "dc_round_trip_efficiency_pct": _to_float(defaults.get("dc_round_trip_efficiency_pct", 94.0), 94.0),
        "eff_dc_cables": _to_float(defaults.get("eff_dc_cables", 99.5), 99.5),
        "eff_pcs": _to_float(defaults.get("eff_pcs", 98.5), 98.5),
        "eff_mvt": _to_float(defaults.get("eff_mvt", 99.5), 99.5),
        "eff_ac_cables_sw_rmu": _to_float(defaults.get("eff_ac_cables_sw_rmu", 99.2), 99.2),
        "eff_hvt_others": _to_float(defaults.get("eff_hvt_others", 100.0), 100.0),
        "rte_curve_adjust_pp": _to_float(defaults.get("rte_curve_adjust_pp", 0.0), 0.0),
        "rte_monotonic_enforce": defaults.get("rte_monotonic_enforce", True),
    }

    stage1 = service_run_stage1(stage1_inputs, defaults)
    snapshot = size_with_guarantee(stage1, "container_only", bundle)

    case_input = SizingCaseInput(
        project_name=stage1_inputs["project_name"],
        scenario_id="container_only",
        poi_power_req_mw=stage1_inputs["poi_power_req_mw"],
        poi_energy_req_mwh=stage1_inputs["poi_energy_req_mwh"],
        poi_nominal_voltage_kv=33.0,
        poi_frequency_hz=50.0,
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

    persist_result = persist_dc_run(
        case_input,
        snapshot,
        db_url=db_url,
        defaults=defaults,
        source_ref="test",
    )
    run_id = persist_result.get("run_id")
    assert run_id

    bundle_restored = load_dc_run_bundle(run_id, db_url=db_url)
    assert bundle_restored is not None
    restored = bundle_restored.snapshot

    assert restored.stage1.eff_dc_to_poi_frac == snapshot.stage1.eff_dc_to_poi_frac
    assert restored.stage1.dc_power_required_mw == snapshot.stage1.dc_power_required_mw
    assert restored.stage1.dc_energy_capacity_required_mwh == snapshot.stage1.dc_energy_capacity_required_mwh
    assert restored.stage3.meta.effective_c_rate == snapshot.stage3.meta.effective_c_rate
    assert restored.stage3.meta.soh_profile_id == snapshot.stage3.meta.soh_profile_id
    assert restored.stage3.meta.rte_profile_id == snapshot.stage3.meta.rte_profile_id
    assert restored.stage3.meta.dc_usable_bol_mwh == snapshot.stage3.meta.dc_usable_bol_mwh
    assert restored.stage3.meta.dc_usable_cod_mwh == snapshot.stage3.meta.dc_usable_cod_mwh
    assert restored.poi_usable_energy_mwh_at_guarantee_year == snapshot.poi_usable_energy_mwh_at_guarantee_year
    assert restored.iteration_count == snapshot.iteration_count
