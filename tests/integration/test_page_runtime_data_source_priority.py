from __future__ import annotations

from types import SimpleNamespace

from calb_sizing_tool.adapters.excel_loader_adapter import load_dc_excel_bundle_from_path
from calb_sizing_tool.schemas.case import SizingCaseInput
from calb_sizing_tool.services.dc_pipeline_service import size_with_guarantee
from calb_sizing_tool.services.run_persistence_service import persist_dc_run
from calb_sizing_tool.services.run_restore_service import load_dc_run_bundle
from calb_sizing_tool.services.sld_data_source_service import persist_ac_runtime_snapshot
from calb_sizing_tool.services.stage1_service import run_stage1 as service_run_stage1
from calb_sizing_tool.ui import single_line_diagram_view


def _to_float(value, fallback):
    try:
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", "").strip()
        return float(value)
    except Exception:
        return float(fallback)


def _persist_dc_run_for_test(sample_excel_path, db_url: str, project_name: str) -> tuple[str, float]:
    bundle = load_dc_excel_bundle_from_path(sample_excel_path)
    defaults = dict(bundle.defaults)
    stage1_inputs = {
        "project_name": project_name,
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
    persist_result = persist_dc_run(
        SizingCaseInput(
            project_name=project_name,
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
        ),
        snapshot,
        db_url=db_url,
        defaults=defaults,
        source_ref="test",
    )
    return str(persist_result["run_id"]), float(snapshot.stage1.dc_power_required_mw)


def test_runtime_priority_prefers_compatibility_adapter_before_session_cache(monkeypatch, tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'priority.sqlite').as_posix()}"
    run_id = "run-priority"

    session_state = {
        "ac_inputs": {"grid_kv": 11.0},
        "ac_output": {
            "source_run_id": run_id,
            "num_blocks": 1,
            "pcs_per_block": 2,
        },
    }
    monkeypatch.setattr(single_line_diagram_view, "st", SimpleNamespace(session_state=session_state))

    state = SimpleNamespace(
        ac_inputs={"grid_kv": 33.0},
        ac_results={
            "source_run_id": run_id,
            "num_blocks": 2,
            "pcs_per_block": 4,
            "pcs_kw": 1250.0,
        },
    )
    project_state = {
        "ac_inputs": {"grid_kv": 33.0},
        "ac_results": {
            "source_run_id": run_id,
            "num_blocks": 2,
            "pcs_per_block": 4,
            "pcs_kw": 1250.0,
        },
    }

    resolution = single_line_diagram_view._resolve_ac_snapshot(
        state,
        project_state,
        run_id=run_id,
        db_url=db_url,
    )

    assert resolution.source == "compatibility_adapter"
    assert resolution.snapshot is not None
    assert resolution.snapshot.output["num_blocks"] == 2
    assert resolution.snapshot.inputs["grid_kv"] == 33.0


def test_load_dc_run_bundle_ignores_ac_runtime_output_snapshots(sample_excel_path, tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'dc_bundle_priority.sqlite').as_posix()}"
    run_id, expected_dc_power_required_mw = _persist_dc_run_for_test(
        sample_excel_path,
        db_url,
        "Runtime Priority Restore",
    )

    persist_ac_runtime_snapshot(
        run_id=run_id,
        db_url=db_url,
        ac_inputs={"grid_kv": 33.0, "grid_frequency_hz": 50.0},
        ac_output={
            "source_run_id": run_id,
            "num_blocks": 2,
            "pcs_per_block": 4,
            "pcs_kw": 1250.0,
            "transformer_mva": 6.0,
        },
    )

    restored = load_dc_run_bundle(run_id, db_url=db_url)

    assert restored is not None
    assert restored.input_snapshot is not None
    assert restored.output_snapshot is not None
    assert restored.input_snapshot.snapshot_kind == "dc_case_input"
    assert restored.output_snapshot.snapshot_kind == "dc_pipeline_output"
    assert restored.snapshot.stage1.dc_power_required_mw == expected_dc_power_required_mw
