from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import ActivePublishMixin, Base, SourceVersionMixin, TimestampMixin, new_uuid


class Project(Base, TimestampMixin, SourceVersionMixin, ActivePublishMixin):
    __tablename__ = "project"

    project_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
