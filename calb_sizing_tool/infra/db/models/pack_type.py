from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import ActivePublishMixin, Base, SourceVersionMixin, TimestampMixin, new_uuid


class PackType(Base, TimestampMixin, SourceVersionMixin, ActivePublishMixin):
    __tablename__ = "pack_type"

    pack_type_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    battery_cell_type_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("battery_cell_type.battery_cell_type_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_pack_type_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    pack_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cells_in_series: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cells_in_parallel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pack_nominal_voltage_v: Mapped[float | None] = mapped_column(Float, nullable=True)
    pack_nameplate_capacity_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_row_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
