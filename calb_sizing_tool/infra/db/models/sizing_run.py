from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import ActivePublishMixin, Base, SourceVersionMixin, TimestampMixin, new_uuid, utc_now


class SizingRun(Base, TimestampMixin, SourceVersionMixin, ActivePublishMixin):
    __tablename__ = "sizing_run"

    sizing_run_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("project.project_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sizing_case_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("sizing_case.sizing_case_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # A run may hang off another run. Today: an AC run under its DC run — the DC
    # result is fixed and the AC configuration is the branch (owner ruling B,
    # 2026-08-04). Self-referential, CASCADE, so deleting a DC run takes its AC
    # branches with it rather than orphaning them.
    parent_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("sizing_run.sizing_run_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    run_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    input_summary_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    output_summary_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
