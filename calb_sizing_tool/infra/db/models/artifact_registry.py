from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import ActivePublishMixin, Base, SourceVersionMixin, TimestampMixin, new_uuid


class ArtifactRegistry(Base, TimestampMixin, SourceVersionMixin, ActivePublishMixin):
    __tablename__ = "artifact_registry"

    artifact_registry_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    sizing_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sizing_run.sizing_run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    artifact_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    media_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
