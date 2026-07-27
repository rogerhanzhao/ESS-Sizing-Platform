from __future__ import annotations

from collections import defaultdict

from calb_sizing_tool.adapters.excel_loader_adapter import load_dc_excel_bundle_from_path
from calb_sizing_tool.infra.db.models import ArtifactRegistry
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.schemas.case import SizingCaseInput
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, SldRenderOptions
from calb_sizing_tool.schemas.sld_render_input import SldInputOverride, legacy_sld_override_preset
from calb_sizing_tool.services.dc_pipeline_service import size_with_guarantee
from calb_sizing_tool.services.diagram_service import render_sld_from_run_bundle
from calb_sizing_tool.services.run_persistence_service import persist_dc_run
from calb_sizing_tool.services.run_restore_service import load_dc_run_bundle
from calb_sizing_tool.services.stage1_service import run_stage1 as service_run_stage1


def _to_float(value, fallback):
    try:
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", "").strip()
        return float(value)
    except Exception:
        return float(fallback)


def _make_ac_snapshot() -> AcSnapshot:
    return AcSnapshot(
        inputs={"grid_kv": 33.0, "lv_voltage_v": 690.0},
        output={
            "num_blocks": 1,
            "pcs_count_by_block": [4],
            "pcs_per_block": 4,
            "pcs_kw": 1250.0,
            "block_size_mw": 5.0,
            "pcs_rating_kw_list_by_block": [[1250.0, 1250.0, 1250.0, 1250.0]],
            "transformer_mva": 6.0,
            "dc_allocation_plan": [
                {"ac_block_index": 1, "dc_blocks_total": 4, "feeder_allocations": [1, 1, 1, 1]}
            ],
        },
        results={},
    )


def _make_project_settings() -> dict:
    preset = legacy_sld_override_preset()
    return {
        "transformer": {
            "vector_group": "Dyn11yn11",
            "uk_percent": preset["transformer_uk_percent"],
        },
        "dc_block_voltage_v": 1500.0,
        "labels": preset["labels"],
        "equipment_ratings": preset["equipment_ratings"],
    }


def _build_run_id(sample_excel_path, db_url: str) -> str:
    bundle = load_dc_excel_bundle_from_path(sample_excel_path)
    defaults = dict(bundle.defaults)
    stage1_inputs = {
        "project_name": "SLD Artifact Mode Separation",
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
    return run_id


def test_sld_artifact_mode_separation(sample_excel_path, tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'sld_artifact_mode_separation.sqlite').as_posix()}"
    run_id = _build_run_id(sample_excel_path, db_url)
    run_bundle = load_dc_run_bundle(run_id, db_url=db_url)
    assert run_bundle is not None

    render_sld_from_run_bundle(
        run_bundle,
        ac_snapshot=_make_ac_snapshot(),
        project_settings=_make_project_settings(),
        options=SldRenderOptions(group_index=1),
        actor="mode-tester",
        db_url=db_url,
    )

    override_payload = legacy_sld_override_preset()
    override_payload["transformer_vector_group"] = "Dyn11yn11"
    override_payload["dc_block_voltage_v"] = 1500.0
    override_payload["dc_blocks_per_feeder"] = [1, 1, 1, 1]
    render_sld_from_run_bundle(
        run_bundle,
        ac_snapshot=_make_ac_snapshot(),
        project_settings=_make_project_settings(),
        options=SldRenderOptions(
            group_index=1,
            override_mode=True,
            overrides=SldInputOverride.model_validate(override_payload),
        ),
        actor="mode-tester",
        db_url=db_url,
    )

    by_kind = defaultdict(set)
    file_names_by_mode = defaultdict(list)
    with session_scope(db_url) as session:
        artifacts = session.query(ArtifactRegistry).filter_by(sizing_run_id=run_id).all()
        for artifact in artifacts:
            mode = artifact.metadata_json["artifact_mode"]
            by_kind[artifact.artifact_kind].add(mode)
            file_names_by_mode[mode].append(artifact.file_name)
            if mode == "concept":
                assert artifact.metadata_json["validation_mode"] == "strict"
                assert ".concept." in artifact.file_name
                assert artifact.metadata_json["not_for_construction"] is True
            if mode == "draft_override":
                assert artifact.metadata_json["validation_mode"] == "draft"
                assert ".draft." in artifact.file_name

    expected_kinds = {
        "sld_svg",
        "sld_png",
        "sld_topology_json",
        "sld_render_spec_json",
        "sld_readiness_manifest_json",
        "site_electrical_index_json",
        "site_electrical_index_svg",
        "site_electrical_index_png",
        "sld_design_basis_schedule_json",
        "sld_design_basis_schedule_svg",
        "sld_design_basis_schedule_png",
        "sld_interface_scope_json",
        "sld_interface_scope_svg",
        "sld_interface_scope_png",
    }
    assert set(by_kind.keys()) == expected_kinds
    for artifact_kind in expected_kinds:
        assert by_kind[artifact_kind] == {"concept", "draft_override"}
    assert file_names_by_mode["concept"]
    assert file_names_by_mode["draft_override"]
