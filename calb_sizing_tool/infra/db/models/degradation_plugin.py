from __future__ import annotations

from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import ActivePublishMixin, Base, SourceVersionMixin, TimestampMixin, new_uuid


class DegradationPlugin(Base, TimestampMixin, SourceVersionMixin, ActivePublishMixin):
    __tablename__ = "degradation_plugin"

    degradation_plugin_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    plugin_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plugin_version: Mapped[str] = mapped_column(String(64), nullable=False)
    entrypoint: Mapped[str] = mapped_column(String(512), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="draft")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    schema_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
