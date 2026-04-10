from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import ActivePublishMixin, Base, SourceVersionMixin, TimestampMixin, new_uuid


class ParameterDefinition(Base, TimestampMixin, SourceVersionMixin, ActivePublishMixin):
    __tablename__ = "parameter_definition"

    parameter_definition_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    field_code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    display_name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name_zh: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    nullable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    required_for_stage: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_rule: Mapped[str] = mapped_column(Text, nullable=False)
    source_sheet: Mapped[str] = mapped_column(String(128), nullable=False)
    legacy_field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
