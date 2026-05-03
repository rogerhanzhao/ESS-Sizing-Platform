from __future__ import annotations

from sqlalchemy import Boolean, JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import ActivePublishMixin, Base, SourceVersionMixin, TimestampMixin, new_uuid


class ProductAsset(Base, TimestampMixin, SourceVersionMixin, ActivePublishMixin):
    __tablename__ = "product_asset"

    product_asset_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    asset_code: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    owner_entity: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    owner_code: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    asset_kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposal_section: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    data_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
