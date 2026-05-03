from __future__ import annotations

from sqlalchemy import JSON, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import ActivePublishMixin, Base, SourceVersionMixin, TimestampMixin, new_uuid


class ProductACBlock(Base, TimestampMixin, SourceVersionMixin, ActivePublishMixin):
    __tablename__ = "product_ac_block"

    product_ac_block_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    block_code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    block_name: Mapped[str] = mapped_column(String(255), nullable=False)
    pcs_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pcs_power_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    pcs_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transformer_kva: Mapped[float | None] = mapped_column(Float, nullable=True)
    hv_voltage_kv: Mapped[float | None] = mapped_column(Float, nullable=True)
    lv_voltage_v: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_efficiency_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    aux_load_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    efficiency_curve_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
