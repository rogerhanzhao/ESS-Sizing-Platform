from __future__ import annotations

from calb_sizing_tool.adapters.excel_loader_adapter import load_dc_excel_bundle_from_path
from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.case_repository import CaseRepository
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.schemas.case import SizingCaseInput
from calb_sizing_tool.services.dc_pipeline_service import size_with_guarantee
from calb_sizing_tool.services.run_persistence_service import persist_dc_run
from calb_sizing_tool.services.stage1_service import run_stage1 as service_run_stage1


def test_project_case_run_flow(sample_excel_path, tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'project_case.sqlite').as_posix()}"

    bundle = load_dc_excel_bundle_from_path(sample_excel_path)
    defaults = dict(bundle.defaults)

    with session_scope(db_url) as session:
        Base.metadata.create_all(bind=session.get_bind())
        repo = CaseRepository(session)
        project = repo.get_or_create_project(project_code="proj-alpha", project_name="Project Alpha")
        session.flush()
        sizing_case = repo.create_case(
            project_id=project.project_id,
            case_code="proj-alpha-case1",
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
        "project_name": "Project Alpha",
        "poi_power_req_mw": 40.0,
        "poi_energy_req_mwh": 160.0,
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
            project_name="Project Alpha",
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
        run_repo = RunRepository(session)
        runs = run_repo.list_runs_by_case(sizing_case_id)
        assert len(runs) == 1
        assert runs[0].project_id == project_id
