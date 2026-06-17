from __future__ import annotations

from calb_sizing_tool.adapters.excel_loader_adapter import load_dc_excel_bundle_from_path
from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import create_engine_for_url
from calb_sizing_tool.schemas.case import SizingCaseInput
from calb_sizing_tool.services.auth_service import AuthService
from calb_sizing_tool.services.dc_pipeline_service import size_with_guarantee
from calb_sizing_tool.services.external_layout_service import generate_layout_prompt
from calb_sizing_tool.services.run_persistence_service import persist_dc_run
from calb_sizing_tool.services.run_restore_service import load_dc_run_bundle
from calb_sizing_tool.services.sld_data_source_service import persist_ac_runtime_snapshot
from calb_sizing_tool.services.stage1_service import run_stage1 as service_run_stage1


def test_layout_prompt_payload_generation(sample_excel_path, tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'layout_prompt.sqlite').as_posix()}"
    engine = create_engine_for_url(db_url)
    Base.metadata.create_all(bind=engine)

    auth_service = AuthService(db_url)
    auth_service.ensure_system_roles()
    admin = auth_service.create_user(username="admin", password="secret", role_codes=["admin"])

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
        "project_name": "Prompt Payload Test",
        "poi_power_req_mw": 40.0,
        "poi_energy_req_mwh": 160.0,
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

    persist_result = persist_dc_run(case_input, snapshot, db_url=db_url, defaults=defaults, source_ref="test")
    run_id = persist_result.get("run_id")
    assert run_id

    run_bundle = load_dc_run_bundle(run_id, db_url=db_url)
    assert run_bundle is not None

    persist_ac_runtime_snapshot(
        run_id=run_id,
        db_url=db_url,
        ac_inputs={"grid_kv": 33.0, "grid_frequency_hz": 50.0},
        ac_output={
            "source_run_id": run_id,
            "num_blocks": 3,
            "pcs_per_block": 4,
            "transformer_mva": 6.0,
        },
    )

    result = generate_layout_prompt(run_id=run_id, auth_user=admin, db_url=db_url)
    payload = result["payload"]
    assert payload["run_id"] == run_id
    assert payload["project"]["project_name"] == stage1_inputs["project_name"]
    assert "layout_rules" in payload
    assert payload["ac_assumptions"]["ac_block_count"] == 3
    assert payload["ac_assumptions"]["pcs_per_block"] == 4
    assert payload["ac_assumptions"]["transformer_mva"] == 6.0
    assert payload["ac_assumptions"]["assumption_note"] == "Loaded from persisted AC snapshot."
