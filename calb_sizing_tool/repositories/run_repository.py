from __future__ import annotations

from sqlalchemy.orm import Session

from calb_sizing_tool.infra.db.models import (
    ArtifactRegistry,
    AuditLog,
    Project,
    RunInputSnapshot,
    RunOutputSnapshot,
    SizingCase,
    SizingRun,
)
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
        parent_run_id: str | None = None,
        input_summary_json: dict | None = None,
        output_summary_json: dict | None = None,
        version_tag: str | None = None,
        source_ref: str | None = None,
    ) -> SizingRun:
        row = SizingRun(
            project_id=project_id,
            sizing_case_id=sizing_case_id,
            parent_run_id=parent_run_id,
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

    def get_latest_input_snapshot_by_kind(self, sizing_run_id: str, snapshot_kind: str) -> RunInputSnapshot | None:
        return (
            self.session.query(RunInputSnapshot)
            .filter_by(sizing_run_id=sizing_run_id, snapshot_kind=snapshot_kind)
            .order_by(RunInputSnapshot.created_at.desc())
            .first()
        )

    def get_latest_output_snapshot_by_kind(self, sizing_run_id: str, snapshot_kind: str) -> RunOutputSnapshot | None:
        return (
            self.session.query(RunOutputSnapshot)
            .filter_by(sizing_run_id=sizing_run_id, snapshot_kind=snapshot_kind)
            .order_by(RunOutputSnapshot.created_at.desc())
            .first()
        )

    def get_run_bundle(self, sizing_run_id: str) -> dict[str, object] | None:
        run = self.get_run(sizing_run_id)
        if run is None:
            return None
        sizing_case = (
            self.session.query(SizingCase)
            .filter_by(sizing_case_id=run.sizing_case_id)
            .one_or_none()
        )
        project = (
            self.session.query(Project)
            .filter_by(project_id=run.project_id)
            .one_or_none()
        )
        inputs = self.get_input_snapshots(sizing_run_id)
        outputs = self.get_output_snapshots(sizing_run_id)
        input_snapshot = (
            self.get_latest_input_snapshot_by_kind(sizing_run_id, "dc_case_input")
            or (inputs[-1] if inputs else None)
        )
        output_snapshot = (
            self.get_latest_output_snapshot_by_kind(sizing_run_id, "dc_pipeline_output")
            or (outputs[-1] if outputs else None)
        )
        return {
            "run": run,
            "case": sizing_case,
            "project": project,
            "input_snapshot": input_snapshot,
            "output_snapshot": output_snapshot,
        }

    def list_runs_by_project(self, project_id: str, *, limit: int | None = None) -> list[SizingRun]:
        query = (
            self.session.query(SizingRun)
            .filter_by(project_id=project_id)
            .order_by(SizingRun.created_at.desc())
        )
        if limit:
            query = query.limit(int(limit))
        return query.all()

    def list_runs_by_case(self, sizing_case_id: str, *, limit: int | None = None) -> list[SizingRun]:
        query = (
            self.session.query(SizingRun)
            .filter_by(sizing_case_id=sizing_case_id)
            .order_by(SizingRun.created_at.desc())
        )
        if limit:
            query = query.limit(int(limit))
        return query.all()

    def list_artifacts(
        self,
        sizing_run_id: str,
        *,
        artifact_kind: str | None = None,
        artifact_mode: str | None = None,
    ) -> list[ArtifactRegistry]:
        """Registered artifacts, newest first.

        (sizing_run_id, artifact_kind) is the key readers use — see
        artifact_service.load_artifact_bytes_from_db, which takes the newest row
        of each kind — so it is also the key generations are counted by.
        """
        query = self.session.query(ArtifactRegistry).filter(
            ArtifactRegistry.sizing_run_id == sizing_run_id
        )
        if artifact_kind:
            query = query.filter(ArtifactRegistry.artifact_kind == artifact_kind)
        rows = query.order_by(ArtifactRegistry.created_at.desc()).all()
        if artifact_mode is not None:
            # artifact_mode lives in metadata_json, not a column: an SLD run holds
            # a "concept" AND a "draft_override" artifact of the SAME kind, and
            # they are separate lineages that must not supersede each other.
            rows = [
                row for row in rows
                if str((row.metadata_json or {}).get("artifact_mode") or "") == artifact_mode
            ]
        return rows

    def delete_artifact(self, artifact_registry_id: str) -> None:
        row = (
            self.session.query(ArtifactRegistry)
            .filter_by(artifact_registry_id=artifact_registry_id)
            .one_or_none()
        )
        if row is not None:
            self.session.delete(row)

    def list_child_runs(self, parent_run_id: str, *, run_type: str | None = None) -> list[SizingRun]:
        """Runs branching off ``parent_run_id``, newest first."""
        query = self.session.query(SizingRun).filter(
            SizingRun.parent_run_id == parent_run_id
        )
        if run_type:
            query = query.filter(SizingRun.run_type == run_type)
        return query.order_by(SizingRun.started_at.desc()).all()

    def find_child_run_by_hash(
        self, parent_run_id: str, run_type: str, content_hash: str
    ) -> SizingRun | None:
        """A child run whose INPUT snapshot carries ``content_hash``.

        This is what stops the run table growing per click: re-running with an
        unchanged configuration finds the existing branch instead of adding one.
        """
        if not content_hash:
            return None
        return (
            self.session.query(SizingRun)
            .join(RunInputSnapshot, RunInputSnapshot.sizing_run_id == SizingRun.sizing_run_id)
            .filter(
                SizingRun.parent_run_id == parent_run_id,
                SizingRun.run_type == run_type,
                RunInputSnapshot.content_hash == content_hash,
            )
            .order_by(SizingRun.started_at.desc())
            .first()
        )
