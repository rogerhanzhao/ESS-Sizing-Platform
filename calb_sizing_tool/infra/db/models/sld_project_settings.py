from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import ActivePublishMixin, Base, SourceVersionMixin, TimestampMixin, new_uuid


class SldProjectSettings(Base, TimestampMixin, SourceVersionMixin, ActivePublishMixin):
    __tablename__ = "sld_project_settings"

    sld_project_settings_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    sizing_case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sizing_case.sizing_case_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    settings_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
