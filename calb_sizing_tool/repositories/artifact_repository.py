from __future__ import annotations

from sqlalchemy.orm import Session

from calb_sizing_tool.infra.db.models import ExternalArtifactSubmission, LayoutReview


class ArtifactRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_external_submission(
        self,
        *,
        sizing_run_id: str,
        plugin_id: str,
        plugin_version: str,
        artifact_kind: str,
        file_name: str,
        file_path: str,
        media_type: str | None,
        content_hash: str | None,
        status: str,
        ai_label: str,
        actor: str | None,
        notes: str | None,
        metadata_json: dict,
        version_tag: str | None = None,
        source_ref: str | None = None,
    ) -> ExternalArtifactSubmission:
        row = ExternalArtifactSubmission(
            sizing_run_id=sizing_run_id,
            plugin_id=plugin_id,
            plugin_version=plugin_version,
            artifact_kind=artifact_kind,
            file_name=file_name,
            file_path=file_path,
            media_type=media_type,
            content_hash=content_hash,
            status=status,
            ai_label=ai_label,
            actor=actor,
            notes=notes,
            metadata_json=metadata_json,
            version_tag=version_tag,
            source_ref=source_ref,
        )
        self.session.add(row)
        return row

    def list_submissions_by_run(self, sizing_run_id: str) -> list[ExternalArtifactSubmission]:
        return (
            self.session.query(ExternalArtifactSubmission)
            .filter_by(sizing_run_id=sizing_run_id)
            .order_by(ExternalArtifactSubmission.created_at.desc())
            .all()
        )

    def get_submission(self, submission_id: str) -> ExternalArtifactSubmission | None:
        return (
            self.session.query(ExternalArtifactSubmission)
            .filter_by(submission_id=submission_id)
            .one_or_none()
        )

    def add_review(
        self,
        *,
        submission_id: str,
        decision: str,
        reviewer: str | None,
        comments: str | None,
    ) -> LayoutReview:
        row = LayoutReview(
            submission_id=submission_id,
            decision=decision,
            reviewer=reviewer,
            comments=comments,
        )
        self.session.add(row)
        return row

    def list_reviews(self, submission_id: str) -> list[LayoutReview]:
        return (
            self.session.query(LayoutReview)
            .filter_by(submission_id=submission_id)
            .order_by(LayoutReview.created_at.desc())
            .all()
        )
