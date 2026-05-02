from __future__ import annotations

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import ActivePublishMixin, Base, SourceVersionMixin, TimestampMixin, new_uuid


# Future: ParameterSet model is scaffolded but not yet wired to any UI or service.
class ParameterSet(Base, TimestampMixin, SourceVersionMixin, ActivePublishMixin):
    __tablename__ = "parameter_set"

    parameter_set_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    set_code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    set_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stage_scope: Mapped[str] = mapped_column(String(64), nullable=False)
    parameter_values_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
