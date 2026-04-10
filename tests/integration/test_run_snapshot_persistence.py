from __future__ import annotations

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import session_scope
import calb_sizing_tool.infra.db.models  # noqa: F401
from calb_sizing_tool.repositories.case_repository import CaseRepository
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.schemas.run_snapshot import RunInputSnapshotSchema, RunOutputSnapshotSchema


def test_run_snapshot_persistence(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'snapshot.sqlite').as_posix()}"

    with session_scope(db_url) as session:
        Base.metadata.create_all(bind=session.get_bind())
        case_repo = CaseRepository(session)
        run_repo = RunRepository(session)

        project = case_repo.get_or_create_project(project_code="demo-project", project_name="Demo Project")
        session.flush()
        sizing_case = case_repo.create_case(
            project_id=project.project_id,
            case_code="demo-case",
            case_name="Demo Case",
            stage_scope="dc",
            scenario_mode="container_only",
            input_json={"poi_power_req_mw": 100.0},
        )
        session.flush()
        run = run_repo.create_run(
            project_id=project.project_id,
            sizing_case_id=sizing_case.sizing_case_id,
            run_type="dc_pipeline",
            status="succeeded",
            input_summary_json={"poi_power_req_mw": 100.0},
            output_summary_json={"dc_power_required_mw": 103.5},
        )
        session.flush()
        run_repo.add_input_snapshot(
            run.sizing_run_id,
            RunInputSnapshotSchema(snapshot_kind="case_input", payload={"project_name": "Demo"}),
        )
        run_repo.add_output_snapshot(
            run.sizing_run_id,
            RunOutputSnapshotSchema(snapshot_kind="stage1_output", payload={"dc_power_required_mw": 103.5}),
        )
        run_repo.register_artifact(
            sizing_run_id=run.sizing_run_id,
            artifact_kind="snapshot",
            file_name="demo.json",
            file_path="/tmp/demo.json",
            media_type="application/json",
            content_hash="abc123",
            metadata_json={"kind": "demo"},
        )
        run_repo.add_audit_log(entity_type="sizing_run", entity_id=run.sizing_run_id, action="created")

    with session_scope(db_url) as session:
        from calb_sizing_tool.infra.db.models import ArtifactRegistry, AuditLog, RunInputSnapshot, RunOutputSnapshot, SizingRun

        assert session.query(SizingRun).count() == 1
        assert session.query(RunInputSnapshot).count() == 1
        assert session.query(RunOutputSnapshot).count() == 1
        assert session.query(ArtifactRegistry).count() == 1
        assert session.query(AuditLog).count() == 1
