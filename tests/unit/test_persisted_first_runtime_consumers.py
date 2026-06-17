from __future__ import annotations

from types import SimpleNamespace

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.models import Project, SizingCase, SizingRun
from calb_sizing_tool.infra.db.session import create_engine_for_url
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services.sld_data_source_service import persist_ac_runtime_snapshot
from calb_sizing_tool.ui import report_export_view, site_layout_view


def _prepare_persisted_ac_snapshot(tmp_path, run_id: str) -> str:
    db_url = f"sqlite:///{(tmp_path / 'runtime_consumers.sqlite').as_posix()}"
    engine = create_engine_for_url(db_url)
    Base.metadata.create_all(bind=engine)
    with session_scope(db_url) as session:
        project = Project(project_code=f"{run_id}-project", project_name="Runtime Consumer Test")
        session.add(project)
        session.flush()
        case = SizingCase(
            project_id=project.project_id,
            case_code=f"{run_id}-case",
            case_name="Runtime Consumer Case",
            stage_scope="dc",
            scenario_mode="container_only",
            input_json={},
        )
        session.add(case)
        session.flush()
        session.add(
            SizingRun(
                sizing_run_id=run_id,
                project_id=project.project_id,
                sizing_case_id=case.sizing_case_id,
                run_type="dc",
                status="completed",
                input_summary_json={},
                output_summary_json={},
            )
        )
    persist_ac_runtime_snapshot(
        run_id=run_id,
        db_url=db_url,
        ac_inputs={"grid_kv": 33.0},
        ac_output={
            "source_run_id": run_id,
            "num_blocks": 5,
            "pcs_per_block": 4,
            "pcs_kw": 1250.0,
        },
    )
    return db_url


def test_layout_ac_resolution_prefers_persisted_snapshot(monkeypatch, tmp_path):
    run_id = "run-layout-persisted"
    db_url = _prepare_persisted_ac_snapshot(tmp_path, run_id)
    monkeypatch.setattr(
        site_layout_view,
        "st",
        SimpleNamespace(
            session_state={
                "ac_inputs": {"grid_kv": 11.0},
                "ac_output": {"source_run_id": run_id, "num_blocks": 1},
            }
        ),
    )

    resolution = site_layout_view._resolve_layout_ac_snapshot(
        SimpleNamespace(ac_inputs={"grid_kv": 22.0}, ac_results={"source_run_id": run_id, "num_blocks": 2}),
        {"ac_inputs": {"grid_kv": 22.0}, "ac_results": {"source_run_id": run_id, "num_blocks": 2}},
        run_id=run_id,
        db_url=db_url,
    )

    assert resolution.source == "persisted_run_snapshot"
    assert resolution.snapshot is not None
    assert resolution.snapshot.output["num_blocks"] == 5
    assert resolution.snapshot.inputs["grid_kv"] == 33.0


def test_report_ac_resolution_prefers_persisted_snapshot(tmp_path):
    run_id = "run-report-persisted"
    db_url = _prepare_persisted_ac_snapshot(tmp_path, run_id)

    resolution = report_export_view._resolve_report_ac_snapshot(
        run_id,
        state=SimpleNamespace(
            ac_inputs={"grid_kv": 22.0},
            ac_results={"source_run_id": run_id, "num_blocks": 2},
        ),
        project_state={
            "ac_inputs": {"grid_kv": 22.0},
            "ac_results": {"source_run_id": run_id, "num_blocks": 2},
        },
        session_state={
            "ac_inputs": {"grid_kv": 11.0},
            "ac_output": {"source_run_id": run_id, "num_blocks": 1},
        },
        db_url=db_url,
    )

    assert resolution.source == "persisted_run_snapshot"
    assert resolution.snapshot is not None
    assert resolution.snapshot.output["num_blocks"] == 5
    assert resolution.snapshot.inputs["grid_kv"] == 33.0
