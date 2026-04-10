from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import ActivePublishMixin, Base, SourceVersionMixin, TimestampMixin, new_uuid


class SizingCase(Base, TimestampMixin, SourceVersionMixin, ActivePublishMixin):
    __tablename__ = "sizing_case"

    sizing_case_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("project.project_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    case_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stage_scope: Mapped[str] = mapped_column(String(64), nullable=False)
    scenario_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    input_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
