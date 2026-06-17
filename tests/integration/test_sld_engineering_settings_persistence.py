from __future__ import annotations

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.models import SldProjectSettings
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.case_repository import CaseRepository
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.schemas.sld_render_input import (
    SldCableSpecs,
    SldDcFuseSpec,
    SldEquipmentRatings,
    SldInputOverride,
    SldLabels,
    SldLvBusbarRatings,
    SldRmuRatings,
)
from calb_sizing_tool.services.sld_engineering_settings_service import (
    build_persisted_sld_project_settings,
    list_case_sld_project_settings_history,
    load_case_sld_project_settings,
    load_case_sld_project_settings_record,
    load_run_sld_project_settings,
    save_case_sld_project_settings,
)


def _make_override() -> SldInputOverride:
    return SldInputOverride(
        transformer_vector_group="Dyn11",
        transformer_uk_percent=7.0,
        dc_block_voltage_v=1500.0,
        labels=SldLabels(
            to_switchgear="To Switchgear",
            to_other_rmu="To Other RMU",
        ),
        equipment_ratings=SldEquipmentRatings(
            rmu=SldRmuRatings(
                rated_kv=24.0,
                rated_a=630.0,
                short_circuit_ka_3s=25.0,
                ct_ratio="200/1",
                ct_class="5P20",
                ct_va=10.0,
            ),
            lv_busbar=SldLvBusbarRatings(
                rated_a=2500.0,
                short_circuit_ka=25.0,
            ),
            cables=SldCableSpecs(
                mv_cable_spec="MV-240",
                lv_cable_spec="LV-1C",
                dc_cable_spec="DC-1C",
            ),
            dc_fuse=SldDcFuseSpec(
                fuse_spec="NH-1600A",
            ),
            transformer_tap_range="+/-2x2.5%",
            transformer_cooling="ONAN",
        ),
    )


def test_case_project_settings_roundtrip_and_mv_rmu_sync(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'sld_engineering_settings.sqlite').as_posix()}"
    with session_scope(db_url) as session:
        Base.metadata.create_all(bind=session.get_bind())
        case_repo = CaseRepository(session)
        project = case_repo.get_or_create_project(project_code="proj-a", project_name="Project A")
        session.flush()
        case_row = case_repo.create_case(
            project_id=project.project_id,
            case_code="proj-a-case-1",
            case_name="Case 1",
            stage_scope="dc",
            scenario_mode="container_only",
            input_json={"case_input": {"poi_nominal_voltage_kv": 33.0}},
        )
        session.flush()
        case_id = case_row.sizing_case_id

    payload = build_persisted_sld_project_settings(_make_override(), mv_nominal_voltage_kv=33.0)
    save_case_sld_project_settings(case_id, payload, actor="tester", db_url=db_url)

    loaded = load_case_sld_project_settings(case_id, db_url=db_url)
    record = load_case_sld_project_settings_record(case_id, db_url=db_url)
    assert loaded["transformer"]["vector_group"] == "Dyn11"
    assert record["source"] == "dedicated_table"
    assert record["project_settings"]["transformer"]["vector_group"] == "Dyn11"
    assert loaded["transformer"]["uk_percent"] == 7.0
    assert loaded["dc_block_voltage_v"] == 1500.0
    assert loaded["labels"]["to_switchgear"] == "To Switchgear"
    assert loaded["equipment_ratings"]["rmu"]["rated_kv"] == 33.0
    with session_scope(db_url) as session:
        settings_row = session.query(SldProjectSettings).filter_by(sizing_case_id=case_id).one_or_none()
        case_row = CaseRepository(session).get_case_by_id(case_id)
        assert settings_row is not None
        assert settings_row.settings_json["transformer"]["vector_group"] == "Dyn11"
        assert "project_settings" not in (case_row.input_json or {})

    history = list_case_sld_project_settings_history(case_id, db_url=db_url)
    assert history
    assert history[0]["actor"] == "tester"


def test_load_run_project_settings_resolves_from_case_record(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'sld_engineering_settings_run.sqlite').as_posix()}"
    with session_scope(db_url) as session:
        Base.metadata.create_all(bind=session.get_bind())
        case_repo = CaseRepository(session)
        run_repo = RunRepository(session)
        project = case_repo.get_or_create_project(project_code="proj-b", project_name="Project B")
        session.flush()
        case_row = case_repo.create_case(
            project_id=project.project_id,
            case_code="proj-b-case-1",
            case_name="Case 1",
            stage_scope="dc",
            scenario_mode="container_only",
            input_json={},
        )
        session.flush()
        run = run_repo.create_run(
            project_id=project.project_id,
            sizing_case_id=case_row.sizing_case_id,
            run_type="dc_pipeline",
            status="succeeded",
        )
        session.flush()
        run_id = run.sizing_run_id
        case_id = case_row.sizing_case_id

    payload = build_persisted_sld_project_settings(_make_override(), mv_nominal_voltage_kv=22.0)
    save_case_sld_project_settings(case_id, payload, actor="tester", db_url=db_url)

    loaded = load_run_sld_project_settings(run_id, db_url=db_url)
    assert loaded["equipment_ratings"]["rmu"]["rated_kv"] == 22.0
    assert loaded["labels"]["to_other_rmu"] == "To Other RMU"


def test_case_project_settings_falls_back_to_legacy_case_json(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'sld_legacy_settings.sqlite').as_posix()}"
    legacy_payload = {
        "transformer": {"vector_group": "Yd11", "uk_percent": 6.5},
        "dc_block_voltage_v": 1500.0,
        "labels": {"to_switchgear": "Legacy Switchgear"},
        "equipment_ratings": {"rmu": {"rated_kv": 33.0}},
    }
    with session_scope(db_url) as session:
        Base.metadata.create_all(bind=session.get_bind())
        case_repo = CaseRepository(session)
        project = case_repo.get_or_create_project(project_code="proj-legacy", project_name="Project Legacy")
        session.flush()
        case_row = case_repo.create_case(
            project_id=project.project_id,
            case_code="proj-legacy-case-1",
            case_name="Case 1",
            stage_scope="dc",
            scenario_mode="container_only",
            input_json={"project_settings": legacy_payload},
        )
        session.flush()
        case_id = case_row.sizing_case_id

    loaded = load_case_sld_project_settings(case_id, db_url=db_url)
    record = load_case_sld_project_settings_record(case_id, db_url=db_url)
    assert loaded["transformer"]["vector_group"] == "Yd11"
    assert record["source"] == "legacy_case_json"
    assert loaded["labels"]["to_switchgear"] == "Legacy Switchgear"


def test_dedicated_sld_project_settings_take_priority_over_legacy_json(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'sld_settings_priority.sqlite').as_posix()}"
    legacy_payload = {
        "transformer": {"vector_group": "Legacy", "uk_percent": 6.5},
        "labels": {"to_switchgear": "Legacy Switchgear"},
    }
    with session_scope(db_url) as session:
        Base.metadata.create_all(bind=session.get_bind())
        case_repo = CaseRepository(session)
        project = case_repo.get_or_create_project(project_code="proj-priority", project_name="Project Priority")
        session.flush()
        case_row = case_repo.create_case(
            project_id=project.project_id,
            case_code="proj-priority-case-1",
            case_name="Case 1",
            stage_scope="dc",
            scenario_mode="container_only",
            input_json={"project_settings": legacy_payload},
        )
        session.flush()
        case_id = case_row.sizing_case_id

    payload = build_persisted_sld_project_settings(_make_override(), mv_nominal_voltage_kv=33.0)
    save_case_sld_project_settings(case_id, payload, actor="tester", db_url=db_url)

    loaded = load_case_sld_project_settings(case_id, db_url=db_url)
    assert loaded["transformer"]["vector_group"] == "Dyn11"
    assert loaded["labels"]["to_switchgear"] == "To Switchgear"
