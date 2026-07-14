from __future__ import annotations

from calb_sizing_tool.adapters.excel_loader_adapter import load_dc_excel_bundle_from_path
from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.case_repository import CaseRepository
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.schemas.case import SizingCaseInput
from calb_sizing_tool.services.dc_pipeline_service import size_with_guarantee
from calb_sizing_tool.services.run_persistence_service import persist_dc_run
from calb_sizing_tool.services.run_restore_service import load_dc_run_bundle
from calb_sizing_tool.services.stage1_service import run_stage1 as service_run_stage1


def test_run_restore_from_history(sample_excel_path, tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'run_history.sqlite').as_posix()}"

    bundle = load_dc_excel_bundle_from_path(sample_excel_path)
    defaults = dict(bundle.defaults)

    with session_scope(db_url) as session:
        Base.metadata.create_all(bind=session.get_bind())
        repo = CaseRepository(session)
        project = repo.get_or_create_project(project_code="proj-beta", project_name="Project Beta")
        session.flush()
        sizing_case = repo.create_case(
            project_id=project.project_id,
            case_code="proj-beta-case1",
            case_name="Case 1",
            stage_scope="dc",
            scenario_mode="container_only",
            input_json={},
        )
        session.flush()
        project_id = project.project_id
        sizing_case_id = sizing_case.sizing_case_id
        case_code = sizing_case.case_code
        case_name = sizing_case.case_name

    stage1_inputs = {
        "project_name": "Project Beta",
        "poi_power_req_mw": 60.0,
        "poi_energy_req_mwh": 240.0,
        "project_life_years": 20,
        "cycles_per_year": 365,
        "poi_guarantee_year": 0,
        "sc_time_months": 3,
        "dod_pct": defaults.get("dod_pct", 95.0),
        "dc_round_trip_efficiency_pct": defaults.get("dc_round_trip_efficiency_pct", 94.0),
    }

    stage1 = service_run_stage1(stage1_inputs, defaults)
    snapshot = size_with_guarantee(stage1, "container_only", bundle)

    persist_dc_run(
        SizingCaseInput(
            project_name="Project Beta",
            scenario_id="container_only",
            poi_power_req_mw=stage1_inputs["poi_power_req_mw"],
            poi_energy_req_mwh=stage1_inputs["poi_energy_req_mwh"],
            project_life_years=stage1_inputs["project_life_years"],
            cycles_per_year=stage1_inputs["cycles_per_year"],
            poi_guarantee_year=stage1_inputs["poi_guarantee_year"],
        ),
        snapshot,
        db_url=db_url,
        project_id=project_id,
        sizing_case_id=sizing_case_id,
        case_code=case_code,
        case_name=case_name,
        defaults=defaults,
    )

    with session_scope(db_url) as session:
        saved_case = CaseRepository(session).get_case_by_id(sizing_case_id)
        assert saved_case is not None
        assert saved_case.input_json["poi_power_req_mw"] == 60.0
        assert saved_case.input_json["poi_energy_req_mwh"] == 240.0
        run_repo = RunRepository(session)
        runs = run_repo.list_runs_by_case(sizing_case_id)
        assert runs
        run_id = runs[0].sizing_run_id

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
