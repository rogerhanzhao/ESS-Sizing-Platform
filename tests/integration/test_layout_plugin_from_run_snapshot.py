from __future__ import annotations

from calb_sizing_tool.adapters.excel_loader_adapter import load_dc_excel_bundle_from_path
from calb_sizing_tool.schemas.case import SizingCaseInput
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot
from calb_sizing_tool.schemas.layout_inputs import LayoutRenderOptions
from calb_sizing_tool.services.dc_pipeline_service import size_with_guarantee
from calb_sizing_tool.services.layout_service import render_layout_from_run_bundle
from calb_sizing_tool.services.run_persistence_service import persist_dc_run
from calb_sizing_tool.services.run_restore_service import load_dc_run_bundle
from calb_sizing_tool.services.site_constraint_readiness_service import build_site_constraint_template
from calb_sizing_tool.services.site_constraint_set_service import (
    load_persisted_site_constraint_set,
    register_site_constraint_set,
)
from calb_sizing_tool.services.stage1_service import run_stage1 as service_run_stage1


def _make_ac_snapshot() -> AcSnapshot:
    return AcSnapshot(
        inputs={"grid_kv": 33.0, "lv_voltage_v": 690.0},
        output={
            "num_blocks": 1,
            "pcs_per_block": 4,
            "block_size_mw": 5.0,
            "transformer_mva": 6.0,
            "dc_allocation_plan": [
                {"ac_block_index": 1, "dc_blocks_total": 4, "feeder_allocations": [1, 1, 1, 1]}
            ],
        },
        results={},
    )


def test_layout_plugin_from_run_snapshot(sample_excel_path, tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'layout_plugin.sqlite').as_posix()}"

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
        "project_name": "Layout Plugin Test",
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

    persist_result = persist_dc_run(case_input, snapshot, db_url=db_url, defaults=defaults, source_ref="test")
    run_id = persist_result.get("run_id")
    assert run_id

    run_bundle = load_dc_run_bundle(run_id, db_url=db_url)
    assert run_bundle is not None

    options = LayoutRenderOptions(block_index=1, arrangement="Auto", show_skid=True)
    artifact_bundle = render_layout_from_run_bundle(
        run_bundle,
        ac_snapshot=_make_ac_snapshot(),
        options=options,
        actor="tester",
        db_url=db_url,
    )

    kinds = {artifact["artifact_kind"] for artifact in artifact_bundle.artifacts}
    assert "layout_svg" in kinds
    assert "layout_png" in kinds
    assert "layout_spec_json" in kinds
    assert "layout_metadata_json" in kinds
    assert "layout_master_readiness_manifest_json" in kinds
    assert artifact_bundle.metadata["document_status"] == "concept"
    assert artifact_bundle.metadata["not_for_construction"] is True
    assert artifact_bundle.metadata["scope"] == "typical_ac_block_arrangement"
    assert artifact_bundle.metadata["master_layout_readiness"]["ready"] is False

    artifacts = {artifact["artifact_kind"]: artifact for artifact in artifact_bundle.artifacts}
    assert "CONCEPT ONLY - NOT FOR CONSTRUCTION" in artifacts["layout_svg"]["content"].decode("utf-8")
    assert artifacts["layout_svg"]["file_name"] == "typical_ac_block_arrangement.concept.svg"
    assert b"site_constraint_template" in artifacts["layout_master_readiness_manifest_json"]["content"]

    constraint_set = build_site_constraint_template(
        run_id=run_id,
        project_context={"project_name": run_bundle.project_name, "case_name": run_bundle.case_name},
        ac_output=_make_ac_snapshot().output,
    )
    registration = register_site_constraint_set(
        run_id=run_id,
        constraint_set=constraint_set,
        actor="tester",
        db_url=db_url,
    )
    persisted_constraint_set = load_persisted_site_constraint_set(run_id, db_url=db_url)

    assert registration["constraint_set_status"] == "draft_incomplete"
    assert registration["master_layout_readiness"]["ready"] is False
    assert persisted_constraint_set == constraint_set
