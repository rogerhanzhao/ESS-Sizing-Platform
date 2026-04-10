from __future__ import annotations

from typing import Any

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.schemas.run_bundle import DcRunBundle
from calb_sizing_tool.schemas.run_snapshot import DcPipelineRunSnapshot, RunInputSnapshotSchema, RunOutputSnapshotSchema
from calb_sizing_tool.schemas.stage1 import Stage1Result
from calb_sizing_tool.schemas.stage2 import Stage2Result
from calb_sizing_tool.schemas.stage3 import Stage3Result


def _build_snapshot_from_payload(payload: dict[str, Any]) -> DcPipelineRunSnapshot:
    stage1 = Stage1Result.model_validate(payload.get("stage1") or {})
    stage2 = Stage2Result.model_validate(payload.get("stage2") or {})
    stage3 = Stage3Result.model_validate(payload.get("stage3") or {})
    return DcPipelineRunSnapshot(
        stage1=stage1,
        stage2=stage2,
        stage3=stage3,
        iteration_count=int(payload.get("iteration_count", 0) or 0),
        poi_usable_energy_mwh_at_guarantee_year=payload.get("poi_usable_energy_mwh_at_guarantee_year"),
        converged=bool(payload.get("converged", True)),
        summary=payload.get("summary") or {},
    )


def load_dc_run_bundle(run_id: str, *, db_url: str | None = None) -> DcRunBundle | None:
    with session_scope(db_url) as session:
        run_repo = RunRepository(session)
        bundle = run_repo.get_run_bundle(run_id)
        if bundle is None:
            return None

        run = bundle.get("run")
        sizing_case = bundle.get("case")
        project = bundle.get("project")
        input_snapshot = bundle.get("input_snapshot")
        output_snapshot = bundle.get("output_snapshot")

        output_payload = output_snapshot.snapshot_json if output_snapshot else {}
        snapshot = _build_snapshot_from_payload(output_payload)
        input_schema = (
            RunInputSnapshotSchema(
                snapshot_kind=input_snapshot.snapshot_kind,
                payload=input_snapshot.snapshot_json,
                content_hash=input_snapshot.content_hash,
            )
            if input_snapshot
            else None
        )
        output_schema = (
            RunOutputSnapshotSchema(
                snapshot_kind=output_snapshot.snapshot_kind,
                payload=output_payload,
                content_hash=output_snapshot.content_hash,
            )
            if output_snapshot
            else None
        )

        return DcRunBundle(
            run_id=run.sizing_run_id if run else run_id,
            project_id=getattr(project, "project_id", None),
            project_code=getattr(project, "project_code", None),
            project_name=getattr(project, "project_name", None),
            sizing_case_id=getattr(sizing_case, "sizing_case_id", None),
            case_code=getattr(sizing_case, "case_code", None),
            case_name=getattr(sizing_case, "case_name", None),
            scenario_mode=getattr(sizing_case, "scenario_mode", None),
            input_snapshot=input_schema,
            output_snapshot=output_schema,
            snapshot=snapshot,
        )
