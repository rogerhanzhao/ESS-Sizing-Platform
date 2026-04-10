from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import Base, SourceVersionMixin, TimestampMixin, new_uuid


class RunInputSnapshot(Base, TimestampMixin, SourceVersionMixin):
    __tablename__ = "run_input_snapshot"

    run_input_snapshot_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    sizing_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sizing_run.sizing_run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
