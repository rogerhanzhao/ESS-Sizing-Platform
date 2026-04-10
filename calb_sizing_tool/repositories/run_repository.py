from __future__ import annotations

from sqlalchemy.orm import Session

from calb_sizing_tool.infra.db.models import ArtifactRegistry, AuditLog, RunInputSnapshot, RunOutputSnapshot, SizingRun
from calb_sizing_tool.schemas.run_snapshot import RunInputSnapshotSchema, RunOutputSnapshotSchema


class RunRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_run(
        self,
        *,
        project_id: str,
        sizing_case_id: str | None,
        run_type: str,
        status: str,
        input_summary_json: dict | None = None,
        output_summary_json: dict | None = None,
        version_tag: str | None = None,
        source_ref: str | None = None,
    ) -> SizingRun:
        row = SizingRun(
            project_id=project_id,
            sizing_case_id=sizing_case_id,
            run_type=run_type,
            status=status,
            input_summary_json=input_summary_json or {},
            output_summary_json=output_summary_json or {},
            version_tag=version_tag,
            source_ref=source_ref,
        )
        self.session.add(row)
        return row

    def add_input_snapshot(self, sizing_run_id: str, schema: RunInputSnapshotSchema, *, version_tag: str | None = None, source_ref: str | None = None) -> RunInputSnapshot:
        row = RunInputSnapshot(
            sizing_run_id=sizing_run_id,
            snapshot_kind=schema.snapshot_kind,
            content_hash=schema.content_hash,
            snapshot_json=schema.payload,
            version_tag=version_tag,
            source_ref=source_ref,
        )
        self.session.add(row)
        return row

    def add_output_snapshot(self, sizing_run_id: str, schema: RunOutputSnapshotSchema, *, version_tag: str | None = None, source_ref: str | None = None) -> RunOutputSnapshot:
        row = RunOutputSnapshot(
            sizing_run_id=sizing_run_id,
            snapshot_kind=schema.snapshot_kind,
            content_hash=schema.content_hash,
            snapshot_json=schema.payload,
            version_tag=version_tag,
            source_ref=source_ref,
        )
        self.session.add(row)
        return row

    def register_artifact(
        self,
        *,
        sizing_run_id: str,
        artifact_kind: str,
        file_name: str,
        file_path: str,
        media_type: str | None,
        content_hash: str | None,
        metadata_json: dict | None = None,
        version_tag: str | None = None,
        source_ref: str | None = None,
    ) -> ArtifactRegistry:
        row = ArtifactRegistry(
            sizing_run_id=sizing_run_id,
            artifact_kind=artifact_kind,
            file_name=file_name,
            file_path=file_path,
            media_type=media_type,
            content_hash=content_hash,
            metadata_json=metadata_json or {},
            version_tag=version_tag,
            source_ref=source_ref,
        )
        self.session.add(row)
        return row

    def add_audit_log(
        self,
        *,
        entity_type: str,
        entity_id: str,
        action: str,
        payload_json: dict | None = None,
        actor: str | None = None,
        remarks: str | None = None,
        version_tag: str | None = None,
        source_ref: str | None = None,
    ) -> AuditLog:
        row = AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor=actor,
            payload_json=payload_json or {},
            remarks=remarks,
            version_tag=version_tag,
            source_ref=source_ref,
        )
        self.session.add(row)
        return row

    def get_run(self, sizing_run_id: str) -> SizingRun | None:
        return self.session.query(SizingRun).filter_by(sizing_run_id=sizing_run_id).one_or_none()

    def get_input_snapshots(self, sizing_run_id: str) -> list[RunInputSnapshot]:
        return (
            self.session.query(RunInputSnapshot)
            .filter_by(sizing_run_id=sizing_run_id)
            .order_by(RunInputSnapshot.created_at.asc())
            .all()
        )

    def get_output_snapshots(self, sizing_run_id: str) -> list[RunOutputSnapshot]:
        return (
            self.session.query(RunOutputSnapshot)
            .filter_by(sizing_run_id=sizing_run_id)
            .order_by(RunOutputSnapshot.created_at.asc())
            .all()
        )
